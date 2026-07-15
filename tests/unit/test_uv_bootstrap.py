"""Unit tests for gatecheck.env.uv_bootstrap (STY-0010 / GAT-12).

Hermetic — no real network and no real uv download: the network boundary is a
dependency-injected ``FakeDownloader`` returning an in-memory ``.tar.gz``, and the
pinned ``(url, sha256)`` is injected so the checksum path is exercised without the
real artifact. Covers platform selection, the happy download+verify+extract+publish,
checksum mismatch, cache-hit (no download), and a uv-less archive. AAA throughout.
"""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from gatecheck import venv
from gatecheck.env.uv_bootstrap import (
    UvBootstrapError,
    bootstrap_uv,
    select_asset,
)

_UV_BODY = b"#!/bin/sh\necho uv 0.11.28\n"
_UV_NAME = "uv.exe" if venv.is_windows() else "uv"


def _tarball(member: str = "uv-x86_64-unknown-linux-gnu/uv", body: bytes = _UV_BODY) -> bytes:
    """Build an in-memory .tar.gz containing one file ``member`` with ``body``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=member)
        info.size = len(body)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


def _zipball(member: str = "uv-x86_64-pc-windows-msvc/uv.exe", body: bytes = _UV_BODY) -> bytes:
    """Build an in-memory .zip containing one file ``member`` with ``body``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(member, body)
    return buf.getvalue()


class FakeDownloader:
    """In-memory UvDownloader returning canned bytes and recording calls."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.calls: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        return self._payload


# ── select_asset ──────────────────────────────────────────────────


def test_select_asset_linux_x86_64() -> None:
    # Act
    url, sha = select_asset("Linux", "x86_64")
    # Assert
    assert url.endswith("/0.11.28/uv-x86_64-unknown-linux-gnu.tar.gz")
    assert sha == "e490a6464492183c5d4534a5527fb4440f7f2bb2f228162ad7e4afe076dc0224"


def test_select_asset_macos_arm64_alias() -> None:
    # Act — "arm64" (macOS) maps to the aarch64 asset
    url, sha = select_asset("Darwin", "arm64")
    # Assert
    assert url.endswith("uv-aarch64-apple-darwin.tar.gz")
    assert len(sha) == 64


def test_select_asset_windows_x86_64() -> None:
    # Act — Windows AMD64 → the msvc zip
    url, sha = select_asset("Windows", "AMD64")
    # Assert
    assert url.endswith("uv-x86_64-pc-windows-msvc.zip")
    assert sha == "0a23463216d09c6a72ff80ef5dc5a795f07dc1575cb84d24596c2f124a441b7b"


def test_select_asset_unsupported_platform_raises() -> None:
    # Act / Assert — an arch with no pinned target
    with pytest.raises(UvBootstrapError, match="not supported"):
        select_asset("Linux", "mips64")


# ── bootstrap_uv ──────────────────────────────────────────────────


def test_bootstrap_downloads_verifies_and_publishes(tmp_path: Path) -> None:
    # Arrange
    payload = _tarball()
    sha = hashlib.sha256(payload).hexdigest()
    downloader = FakeDownloader(payload)
    # Act
    uv = bootstrap_uv(tmp_path, downloader=downloader, asset=("https://x/uv.tar.gz", sha))
    # Assert
    assert uv == tmp_path / "bin" / _UV_NAME
    assert uv.is_file() and os.access(uv, os.X_OK)
    assert uv.read_bytes() == _UV_BODY
    assert downloader.calls == ["https://x/uv.tar.gz"]


def test_bootstrap_extracts_uv_exe_from_zip(tmp_path: Path) -> None:
    # Arrange — a Windows-style .zip payload
    payload = _zipball()
    sha = hashlib.sha256(payload).hexdigest()
    downloader = FakeDownloader(payload)
    # Act
    uv = bootstrap_uv(tmp_path, downloader=downloader, asset=("https://x/uv.zip", sha))
    # Assert
    assert uv.read_bytes() == _UV_BODY


def test_bootstrap_names_binary_uv_exe_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — simulate Windows (patch the shared platform check, not os.name)
    monkeypatch.setattr(venv, "_is_windows", lambda: True)
    payload = _zipball()
    sha = hashlib.sha256(payload).hexdigest()
    # Act
    uv = bootstrap_uv(tmp_path, downloader=FakeDownloader(payload), asset=("https://x/uv.zip", sha))
    # Assert
    assert uv == tmp_path / "bin" / "uv.exe"
    assert uv.is_file()


def test_bootstrap_checksum_mismatch_raises(tmp_path: Path) -> None:
    # Arrange — expected sha does not match the payload
    downloader = FakeDownloader(_tarball())
    # Act / Assert
    with pytest.raises(UvBootstrapError, match="checksum mismatch"):
        bootstrap_uv(tmp_path, downloader=downloader, asset=("https://x/uv.tar.gz", "00" * 32))
    assert not (tmp_path / "bin" / _UV_NAME).exists()


def test_bootstrap_cache_hit_skips_download(tmp_path: Path) -> None:
    # Arrange — a previously bootstrapped uv
    dest = tmp_path / "bin" / _UV_NAME
    dest.parent.mkdir(parents=True)
    dest.write_text("#!/bin/sh\n", encoding="utf-8")
    dest.chmod(0o755)
    downloader = FakeDownloader(_tarball())
    # Act
    uv = bootstrap_uv(tmp_path, downloader=downloader, asset=("https://x/uv.tar.gz", "unused"))
    # Assert — returned without downloading
    assert uv == dest
    assert downloader.calls == []


def test_bootstrap_archive_without_uv_raises(tmp_path: Path) -> None:
    # Arrange — an archive whose only file is not the uv binary
    payload = _tarball(member="uv-x86_64-unknown-linux-gnu/README.md")
    sha = hashlib.sha256(payload).hexdigest()
    downloader = FakeDownloader(payload)
    # Act / Assert
    with pytest.raises(UvBootstrapError, match="no 'uv' binary"):
        bootstrap_uv(tmp_path, downloader=downloader, asset=("https://x/uv.tar.gz", sha))
