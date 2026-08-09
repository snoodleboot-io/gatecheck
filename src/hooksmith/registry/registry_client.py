"""RegistryClient seam + UrllibRegistryClient default impl (BUILD-0006-ARCH §5).

The network boundary for ``resolve_pypi_source``. ``RegistryClient`` is a single
injectable ``typing.Protocol`` so the resolver suite runs fully offline against a
fake; ``UrllibRegistryClient`` is the only place HTTP status / content negotiation /
parse logic lives (stdlib ``urllib.request`` — no third-party HTTP client). It
raises ``PackageNotFound`` on 404, ``MalformedIndexResponse`` on a body it cannot
parse, and lets ``urllib.error.URLError`` / ``TimeoutError`` / ``OSError`` propagate
for the resolver to wrap with requirement + index context.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Protocol

from pydantic import BaseModel, ConfigDict

_ACCEPT_HEADER = "application/vnd.pypi.simple.v1+json"
_DEFAULT_TIMEOUT = 30.0


class ProjectFile(BaseModel):
    """One file entry from a simple-index project page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    url: str | None = None
    sha256: str | None = None
    yanked: bool = False


class ProjectPage(BaseModel):
    """A parsed simple-index project page: the files available for a project."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    files: tuple[ProjectFile, ...] = ()


class PackageNotFound(Exception):  # noqa: N818  (locked name: a signal, not an *Error)
    """Raised by a RegistryClient when the index has no such project (HTTP 404)."""


class MalformedIndexResponse(Exception):  # noqa: N818  (locked name: a signal, not an *Error)
    """Raised by a RegistryClient when the project page body cannot be parsed."""


class RegistryClient(Protocol):
    """The injectable network seam: fetch a project's simple-index page."""

    def fetch_project(self, index_url: str, name: str) -> ProjectPage: ...


class _SimpleIndexHTMLParser(HTMLParser):
    """Collect ``<a>`` anchors from a PEP 503 HTML simple-index page.

    href (minus any ``#sha256=`` fragment) → ``url``; anchor text → ``filename``;
    the ``data-yanked`` attribute (present) → ``yanked``; the ``#sha256=`` URL
    fragment → ``sha256``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.files: list[ProjectFile] = []
        self._href: str | None = None
        self._sha256: str | None = None
        self._yanked: bool = False
        self._text: list[str] = []
        self._in_anchor: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        url: str | None = None
        sha256: str | None = None
        if href is not None:
            split = urllib.parse.urlsplit(href)
            url = urllib.parse.urlunsplit(split._replace(fragment=""))
            fragment = urllib.parse.parse_qs(split.fragment)
            hashes = fragment.get("sha256")
            if hashes:
                sha256 = hashes[0]
        self._in_anchor = True
        self._href = url
        self._sha256 = sha256
        self._yanked = "data-yanked" in attr_map
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._in_anchor:
            return
        filename = "".join(self._text).strip()
        if filename:
            self.files.append(
                ProjectFile(
                    filename=filename,
                    url=self._href,
                    sha256=self._sha256,
                    yanked=self._yanked,
                )
            )
        self._in_anchor = False


class UrllibRegistryClient:
    """Default ``RegistryClient`` over stdlib ``urllib.request`` (PEP 691 + PEP 503)."""

    def __init__(self, *, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def fetch_project(self, index_url: str, name: str) -> ProjectPage:
        """GET ``{index_url}/{name}/`` and parse the simple-index project page.

        Sends the PEP 691 ``Accept`` header; parses JSON when the response is JSON,
        else falls back to PEP 503 HTML. Raises ``PackageNotFound`` on 404 and
        ``MalformedIndexResponse`` on an unparseable body; ``URLError`` / timeout /
        ``OSError`` propagate.
        """
        url = f"{index_url.rstrip('/')}/{name}/"
        request = urllib.request.Request(url, headers={"Accept": _ACCEPT_HEADER})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise PackageNotFound(name) from exc
            raise

        content_type = content_type.lower()
        if "html" in content_type:
            return self._parse_html(name, body, url)
        if "json" in content_type:
            return self._parse_json(name, body, url)
        # Ambiguous/missing Content-Type: we negotiated PEP 691 JSON via Accept, so
        # prefer JSON and fall back to PEP 503 HTML only if the body isn't JSON.
        try:
            return self._parse_json(name, body, url)
        except MalformedIndexResponse:
            return self._parse_html(name, body, url)

    def _parse_json(self, name: str, body: bytes, url: str) -> ProjectPage:
        try:
            document = json.loads(body)
            raw_files = document["files"]
            files: list[ProjectFile] = []
            for entry in raw_files:
                hashes = entry.get("hashes") or {}
                files.append(
                    ProjectFile(
                        filename=entry["filename"],
                        url=entry.get("url"),
                        sha256=hashes.get("sha256"),
                        yanked=bool(entry.get("yanked", False)),
                    )
                )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise MalformedIndexResponse(url) from exc
        return ProjectPage(name=name, files=tuple(files))

    def _parse_html(self, name: str, body: bytes, url: str) -> ProjectPage:
        # stdlib HTMLParser is deliberately lenient: malformed markup yields an empty
        # anchor set rather than an error, and a legitimately empty project page also
        # has no anchors — so "no files" is not treated as malformed here (it surfaces
        # downstream as "no version satisfies"). Only an undecodable body is a signal.
        try:
            parser = _SimpleIndexHTMLParser()
            parser.feed(body.decode("utf-8"))
            parser.close()
        except (ValueError, UnicodeDecodeError) as exc:
            raise MalformedIndexResponse(url) from exc
        return ProjectPage(name=name, files=tuple(parser.files))
