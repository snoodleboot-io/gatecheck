"""Unit tests for gatecheck.registry.UrllibRegistryClient (STY-0006 / TSK-011).

Contract under test is LOCKED by
``planning/build-plans/0006-architecture-decision.md`` §5. These exercise the REAL
``UrllibRegistryClient`` — the only module that touches the network — against a
**loopback** ``http.server`` (bound to 127.0.0.1 on an ephemeral port). Nothing
external is contacted; ``urllib`` is NOT monkeypatched (the real client drives real
sockets to localhost).

Covered paths:
- PEP 691 JSON content negotiation (``application/vnd.pypi.simple.v1+json``).
- PEP 503 HTML fallback (``text/html``): ``href`` → ``url`` (fragment stripped),
  anchor text → ``filename``, ``data-yanked`` → ``yanked``, ``#sha256=`` → ``sha256``.
- malformed JSON body → ``MalformedIndexResponse``.
- HTTP 404 → ``PackageNotFound``.
- non-404 ``HTTPError`` (500) → propagates (the resolver wraps it upstream).
- connection refused (no listener) → ``URLError`` / ``OSError`` propagates.

AAA throughout; no broad ``except``; no ``pytest.raises(Exception)``.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gatecheck.registry import ProjectPage, UrllibRegistryClient
from gatecheck.registry.registry_client import MalformedIndexResponse, PackageNotFound

_JSON_CONTENT_TYPE = "application/vnd.pypi.simple.v1+json"


# ---------------------------------------------------------------------------
# Loopback simple-index server — returns a single canned response
# ---------------------------------------------------------------------------


class _CannedHandler(BaseHTTPRequestHandler):
    """Serve one canned ``(status, content_type, body)`` for any GET."""

    def do_GET(self) -> None:
        status, content_type, body = self.server.response  # type: ignore[attr-defined]
        if status >= 400:
            self.send_error(status)
            return
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # silence test-server logging
        pass


@contextmanager
def _running_index(
    *,
    status: int = 200,
    content_type: str = _JSON_CONTENT_TYPE,
    body: bytes = b"",
) -> Iterator[str]:
    """Run a loopback index serving the canned response; yield its base index URL."""
    server = HTTPServer(("127.0.0.1", 0), _CannedHandler)
    server.response = (status, content_type, body)  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/simple"
    finally:
        server.shutdown()
        thread.join()


# ---------------------------------------------------------------------------
# PEP 691 JSON content negotiation
# ---------------------------------------------------------------------------


def test_json_response_is_parsed_into_project_page() -> None:
    # Arrange
    document = {
        "meta": {"api-version": "1.0"},
        "name": "ruff",
        "files": [
            {
                "filename": "ruff-0.4.9-py3-none-any.whl",
                "url": "https://files.example/ruff-0.4.9-py3-none-any.whl",
                "hashes": {"sha256": "deadbeef"},
                "yanked": False,
            },
            {
                "filename": "ruff-0.5.0-py3-none-any.whl",
                "url": "https://files.example/ruff-0.5.0-py3-none-any.whl",
                "hashes": {"sha256": "cafef00d"},
                "yanked": True,
            },
        ],
    }
    body = json.dumps(document).encode("utf-8")

    # Act
    with _running_index(content_type=_JSON_CONTENT_TYPE, body=body) as index_url:
        page = UrllibRegistryClient().fetch_project(index_url, "ruff")

    # Assert
    assert isinstance(page, ProjectPage)
    assert page.name == "ruff"
    assert len(page.files) == 2
    first, second = page.files
    assert first.filename == "ruff-0.4.9-py3-none-any.whl"
    assert first.url == "https://files.example/ruff-0.4.9-py3-none-any.whl"
    assert first.sha256 == "deadbeef"
    assert first.yanked is False
    assert second.yanked is True
    assert second.sha256 == "cafef00d"


def test_json_response_tolerates_missing_optional_fields() -> None:
    # Arrange — a file entry with no url and no hashes.
    document = {"name": "ruff", "files": [{"filename": "ruff-0.4.9-py3-none-any.whl"}]}
    body = json.dumps(document).encode("utf-8")

    # Act
    with _running_index(body=body) as index_url:
        page = UrllibRegistryClient().fetch_project(index_url, "ruff")

    # Assert
    assert page.files[0].url is None
    assert page.files[0].sha256 is None
    assert page.files[0].yanked is False


def test_json_body_with_ambiguous_content_type_is_parsed_as_json() -> None:
    # A JSON body served WITHOUT a json/html Content-Type must still parse as JSON:
    # we negotiated PEP 691 via Accept, so the client prefers JSON for an ambiguous
    # Content-Type and only falls back to HTML if the body isn't JSON.
    # Arrange
    document = {"name": "ruff", "files": [{"filename": "ruff-0.4.9-py3-none-any.whl"}]}
    body = json.dumps(document).encode("utf-8")

    # Act
    with _running_index(content_type="application/octet-stream", body=body) as index_url:
        page = UrllibRegistryClient().fetch_project(index_url, "ruff")

    # Assert
    assert page.name == "ruff"
    assert page.files[0].filename == "ruff-0.4.9-py3-none-any.whl"


# ---------------------------------------------------------------------------
# PEP 503 HTML fallback
# ---------------------------------------------------------------------------


def test_html_fallback_parses_anchors_yanked_and_sha256() -> None:
    # Arrange — a PEP 503 HTML page served as text/html.
    html = (
        "<!DOCTYPE html><html><body>\n"
        '<a href="https://files.example/ruff-0.4.1-py3-none-any.whl#sha256=aaa111">'
        "ruff-0.4.1-py3-none-any.whl</a>\n"
        '<a href="https://files.example/ruff-0.4.9-py3-none-any.whl#sha256=bbb222" '
        'data-yanked="withdrawn">ruff-0.4.9-py3-none-any.whl</a>\n'
        '<a href="https://files.example/ruff-1.0.0.tar.gz">ruff-1.0.0.tar.gz</a>\n'
        "</body></html>\n"
    )
    body = html.encode("utf-8")

    # Act
    with _running_index(content_type="text/html", body=body) as index_url:
        page = UrllibRegistryClient().fetch_project(index_url, "ruff")

    # Assert
    assert page.name == "ruff"
    assert len(page.files) == 3

    unyanked_wheel, yanked_wheel, sdist = page.files
    # href → url (fragment stripped); anchor text → filename; #sha256= → sha256.
    assert unyanked_wheel.filename == "ruff-0.4.1-py3-none-any.whl"
    assert unyanked_wheel.url == "https://files.example/ruff-0.4.1-py3-none-any.whl"
    assert unyanked_wheel.sha256 == "aaa111"
    assert unyanked_wheel.yanked is False
    # data-yanked present → yanked True.
    assert yanked_wheel.filename == "ruff-0.4.9-py3-none-any.whl"
    assert yanked_wheel.sha256 == "bbb222"
    assert yanked_wheel.yanked is True
    # no fragment → sha256 None; no data-yanked → not yanked.
    assert sdist.filename == "ruff-1.0.0.tar.gz"
    assert sdist.url == "https://files.example/ruff-1.0.0.tar.gz"
    assert sdist.sha256 is None
    assert sdist.yanked is False


# ---------------------------------------------------------------------------
# Malformed body
# ---------------------------------------------------------------------------


def test_malformed_json_body_raises_malformed_index_response() -> None:
    # Arrange — a JSON content-type with an unparseable body.
    # Act / Assert
    with (
        _running_index(content_type=_JSON_CONTENT_TYPE, body=b"not json{") as index_url,
        pytest.raises(MalformedIndexResponse),
    ):
        UrllibRegistryClient().fetch_project(index_url, "ruff")


def test_json_body_missing_files_key_raises_malformed_index_response() -> None:
    # Arrange — valid JSON but no "files" key (KeyError path).
    body = json.dumps({"meta": {"api-version": "1.0"}, "name": "ruff"}).encode("utf-8")
    # Act / Assert
    with (
        _running_index(content_type=_JSON_CONTENT_TYPE, body=body) as index_url,
        pytest.raises(MalformedIndexResponse),
    ):
        UrllibRegistryClient().fetch_project(index_url, "ruff")


# ---------------------------------------------------------------------------
# HTTP status handling
# ---------------------------------------------------------------------------


def test_http_404_raises_package_not_found() -> None:
    # Arrange / Act / Assert
    with (
        _running_index(status=404) as index_url,
        pytest.raises(PackageNotFound),
    ):
        UrllibRegistryClient().fetch_project(index_url, "ruff")


def test_non_404_http_error_propagates() -> None:
    # Arrange — a 500 must NOT be swallowed; the resolver wraps it upstream.
    # Act / Assert
    with (
        _running_index(status=500) as index_url,
        pytest.raises(urllib.error.HTTPError) as exc_info,
    ):
        UrllibRegistryClient().fetch_project(index_url, "ruff")
    assert exc_info.value.code == 500


# ---------------------------------------------------------------------------
# Network error — connection refused (no listener on the port)
# ---------------------------------------------------------------------------


def test_connection_refused_propagates_url_error() -> None:
    # Arrange — reserve an ephemeral port, then close it so nothing is listening.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    index_url = f"http://127.0.0.1:{dead_port}/simple"

    # Act / Assert — urllib surfaces connection refused as URLError (an OSError).
    with pytest.raises(urllib.error.URLError):
        UrllibRegistryClient(timeout=2.0).fetch_project(index_url, "ruff")
