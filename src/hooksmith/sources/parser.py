"""parse_source — classify a hook's `from` spec into a ParsedSource (BUILD-0004-ARCH §4).

Pure string parsing only: no filesystem, network, env, or subprocess (AC-9). The
match order below is first-rule-wins and mirrors the story's parse-rule table.
"""

from __future__ import annotations

import re
from typing import Literal

from hooksmith.sources.parsed_source import ParsedSource
from hooksmith.sources.project_source import ProjectSource
from hooksmith.sources.pypi_source import PyPISource
from hooksmith.sources.source_spec_error import SourceSpecError
from hooksmith.sources.system_source import SystemSource
from hooksmith.sources.unsupported_source import UnsupportedSource

_ALIAS_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9_-]+")
_SCHEME_RE: re.Pattern[str] = re.compile(r"^([A-Za-z0-9_+-]+):")

_UNSUPPORTED_SCHEMES: dict[str, Literal["local", "git", "docker"]] = {
    "local": "local",
    "git": "git",
    "docker": "docker",
}


def parse_source(spec: str) -> ParsedSource:
    """Parse and classify ``spec`` into a typed ``ParsedSource``.

    Raises ``SourceSpecError`` for a syntactically invalid spec. Recognized but
    unsupported schemes (``local:`` / ``git:`` / ``docker:``) return an
    ``UnsupportedSource`` and never raise. The original (un-stripped) ``spec`` is
    used in every error message so the user sees exactly what they wrote.
    """
    s = spec.strip()

    # 1. empty / whitespace
    if s == "":
        raise SourceSpecError(spec, "spec is empty")

    # 2. bare keyword: project
    if s == "project":
        return ProjectSource()

    # 3. bare keyword: system
    if s == "system":
        return SystemSource()

    # 4. pypi+<alias>:<requirement>
    if s.startswith("pypi+"):
        colon = s.find(":")
        if colon == -1:
            raise SourceSpecError(spec, "expected 'pypi+<alias>:<requirement>'")
        alias = s[len("pypi+") : colon]
        req = s[colon + 1 :]
        if alias == "":
            raise SourceSpecError(spec, "registry alias must not be empty")
        if _ALIAS_RE.fullmatch(alias) is None:
            raise SourceSpecError(spec, "registry alias must match [A-Za-z0-9_-]+")
        if req == "":
            raise SourceSpecError(spec, "requirement must not be empty")
        return PyPISource(requirement=req, registry=alias)

    # 5. pypi:<requirement>
    if s.startswith("pypi:"):
        req = s[len("pypi:") :]
        if req == "":
            raise SourceSpecError(spec, "requirement must not be empty")
        return PyPISource(requirement=req, registry=None)

    # 6. recognized-but-unsupported schemes
    scheme_match = _SCHEME_RE.match(s)
    if scheme_match is not None:
        scheme = scheme_match.group(1)
        unsupported = _UNSUPPORTED_SCHEMES.get(scheme)
        if unsupported is not None:
            return UnsupportedSource(scheme=unsupported)
        # 7. any other scheme:-shaped string → unknown scheme
        raise SourceSpecError(spec, f"unknown source scheme '{scheme}'")

    # 8. bare word (or anything else not matching a scheme shape)
    raise SourceSpecError(
        spec,
        "expected one of: project, system, pypi:<req>, pypi+<alias>:<req>",
    )
