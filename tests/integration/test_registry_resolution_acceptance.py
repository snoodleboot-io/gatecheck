"""Acceptance tests for STY-0006 — resolving `pypi:` sources against a registry.

Mirrors the acceptance criteria in
``planning/features/FEAT-0002-source-resolution/stories/STY-0006-resolve-pypi-registry-specs.md``
and the LOCKED contract in ``planning/build-plans/0006-architecture-decision.md``.

Two layers, both HERMETIC by default:

- The real ``UrllibRegistryClient`` is exercised against a **loopback**
  ``http.server`` serving a canned PEP 691 JSON project page (§10 / TSK-011) — this
  covers the actual HTTP + JSON parse path without leaving the machine. 404 handling
  is covered too.
- AC-17: ``load_config`` of a ``pypi:`` hook SUCCEEDS (network resolution is not run
  at load time) and a ``RegistryError`` is never a ``ConfigError``.

One optional real-PyPI smoke test is marked ``@pytest.mark.network`` and is
deselected by default (run with ``-m network`` to include it).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from hooksmith.config import ConfigError, SourceSpec, load_config
from hooksmith.registry import RegistryError, UrllibRegistryClient, resolve_pypi_source
from hooksmith.sources import PyPISource

# ---------------------------------------------------------------------------
# Loopback PEP 691 simple-index server
# ---------------------------------------------------------------------------

_PROJECT_JSON = {
    "meta": {"api-version": "1.0"},
    "name": "ruff",
    "files": [
        {
            "filename": "ruff-0.4.1-py3-none-any.whl",
            "url": "https://files.example/ruff-0.4.1-py3-none-any.whl",
            "hashes": {"sha256": "hash041"},
            "yanked": False,
        },
        {
            "filename": "ruff-0.4.9-py3-none-any.whl",
            "url": "https://files.example/ruff-0.4.9-py3-none-any.whl",
            "hashes": {"sha256": "hash049"},
            "yanked": False,
        },
        {
            "filename": "ruff-1.0.0-py3-none-any.whl",
            "url": "https://files.example/ruff-1.0.0-py3-none-any.whl",
            "hashes": {"sha256": "hash100"},
            "yanked": False,
        },
    ],
}


class _SimpleIndexHandler(BaseHTTPRequestHandler):
    """Serve ``GET /simple/ruff/`` as PEP 691 JSON; everything else is 404."""

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/ruff"):
            body = json.dumps(_PROJECT_JSON).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.pypi.simple.v1+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "not found")

    def log_message(self, *args: object) -> None:  # silence test-server logging
        pass


@pytest.fixture
def loopback_index() -> Iterator[str]:
    """Start a loopback simple-index server; yield its base index URL."""
    server = HTTPServer(("127.0.0.1", 0), _SimpleIndexHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/simple"
    finally:
        server.shutdown()
        thread.join()


# ---------------------------------------------------------------------------
# Real UrllibRegistryClient against the loopback index
# ---------------------------------------------------------------------------


def test_urllib_client_resolves_against_loopback_index(loopback_index: str) -> None:
    """Given a loopback index serving PEP 691 JSON for ruff, When resolve_pypi_source
    runs with the real UrllibRegistryClient, Then it returns the expected pin."""
    # Arrange
    sources = SourceSpec(default_registry=loopback_index)
    source = PyPISource(requirement="ruff>=0.4,<1", registry=None)

    # Act
    result = resolve_pypi_source(source, sources, client=UrllibRegistryClient())

    # Assert
    assert result.name == "ruff"
    assert result.version == "0.4.9"
    assert result.index_url == loopback_index
    assert result.sha256 == "hash049"
    assert result.url == "https://files.example/ruff-0.4.9-py3-none-any.whl"
    assert result.filename == "ruff-0.4.9-py3-none-any.whl"


def test_urllib_client_404_raises_registry_error(loopback_index: str) -> None:
    """Given a project the loopback index 404s on, When resolve_pypi_source runs with
    the real client, Then a RegistryError (package not found) is raised, not a crash."""
    # Arrange
    sources = SourceSpec(default_registry=loopback_index)
    source = PyPISource(requirement="doesnotexist", registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, sources, client=UrllibRegistryClient())

    # Assert
    assert "not found" in exc_info.value.reason


# ---------------------------------------------------------------------------
# AC-17 — registry failures are NOT ConfigError; load_config runs no resolution
# ---------------------------------------------------------------------------


def test_load_config_of_pypi_hook_succeeds_without_network(tmp_path: Path) -> None:
    """Given a check.toml with a pypi: hook, When load_config runs, Then it SUCCEEDS
    (no network resolution at load time) and the hook's `from` survives verbatim."""
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text(
        '[[hook]]\nid = "ruff"\nfrom = "pypi:ruff>=0.4"\nrun = "ruff check"\n',
        encoding="utf-8",
    )

    # Act — must not raise; resolution is a runtime concern.
    result = load_config(cfg_file)

    # Assert
    assert [h.from_ for h in result.hook] == ["pypi:ruff>=0.4"]


def test_registry_error_is_not_config_error() -> None:
    """A RegistryError is a runtime/environment condition, never a ConfigError."""
    # Arrange / Act
    err = RegistryError("ruff", None, "unknown registry alias 'internal'")

    # Assert
    assert not isinstance(err, ConfigError)
    assert isinstance(err, ValueError)


# ---------------------------------------------------------------------------
# Optional real-PyPI smoke test — deselected by default (AC-14)
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_resolves_real_package_from_pypi() -> None:
    """Given the default (real) UrllibRegistryClient, When resolving a known PyPI
    package, Then a concrete pinned descriptor is returned. Marked `network` so it is
    skipped by default; run explicitly with `-m network`."""
    # Arrange
    source = PyPISource(requirement="pip", registry=None)

    # Act
    result = resolve_pypi_source(source, None)

    # Assert
    assert result.name == "pip"
    assert result.index_url == "https://pypi.org/simple"
    assert result.version  # some concrete version string
