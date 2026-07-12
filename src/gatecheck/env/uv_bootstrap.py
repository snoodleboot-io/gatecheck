"""uv_bootstrap — download a pinned, checksum-verified uv binary (STY-0010 / GAT-12).

Fills the ``SubprocessUvRunner`` discovery seam GAT-10 left: when ``uv`` is absent,
fetch a **version-pinned** release from the Astral ``astral-sh/uv`` GitHub releases,
**verify its SHA-256 against a hardcoded digest**, extract the ``uv`` binary, and
cache it under ``<cache_root>/bin/uv`` (bootstrap once, then reuse). POSIX only;
Windows and unknown platforms raise ``UvBootstrapError``.

Bumping ``_UV_VERSION`` requires updating the four ``_ASSETS`` digests — a reviewed
change. The network boundary is the injectable ``UvDownloader`` Protocol so the unit
suite runs fully offline against a fake.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from gatecheck import venv

_UV_VERSION = "0.11.28"
_RELEASE_BASE = "https://github.com/astral-sh/uv/releases/download"
_DOWNLOAD_TIMEOUT = 60.0

# (os, arch) -> (asset filename, sha256 of that asset). Verified against the
# published <asset>.sha256 sidecars for _UV_VERSION. POSIX targets only.
_ASSETS: dict[tuple[str, str], tuple[str, str]] = {
    ("linux", "x86_64"): (
        "uv-x86_64-unknown-linux-gnu.tar.gz",
        "e490a6464492183c5d4534a5527fb4440f7f2bb2f228162ad7e4afe076dc0224",
    ),
    ("linux", "aarch64"): (
        "uv-aarch64-unknown-linux-gnu.tar.gz",
        "03e9fe0a81b0718d0bc84625de3885df6cc3f89a8b6af6121d6b9f6113fb6533",
    ),
    ("darwin", "x86_64"): (
        "uv-x86_64-apple-darwin.tar.gz",
        "2ad79983127ffca7d77b77ce6a24278d7e4f7b817a1acf72fea5f8124b4aac5e",
    ),
    ("darwin", "aarch64"): (
        "uv-aarch64-apple-darwin.tar.gz",
        "33540eb7c883ab857eff79bd5ac2aa31fe27b595abecb4a9c003a2c998447232",
    ),
    ("windows", "x86_64"): (
        "uv-x86_64-pc-windows-msvc.zip",
        "0a23463216d09c6a72ff80ef5dc5a795f07dc1575cb84d24596c2f124a441b7b",
    ),
    ("windows", "aarch64"): (
        "uv-aarch64-pc-windows-msvc.zip",
        "3248109afad3ec59baad299d324ff53de17e2d9a3b3e21580ffd26744b11e036",
    ),
}

_OS_ALIASES = {"linux": "linux", "darwin": "darwin", "windows": "windows"}
_ARCH_ALIASES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}


class UvBootstrapError(Exception):
    """Raised when a pinned uv binary cannot be provisioned (platform / checksum / archive)."""


class UvDownloader(Protocol):
    """The injectable network seam: fetch the bytes at ``url``."""

    def fetch(self, url: str) -> bytes: ...


class UrllibUvDownloader:
    """Default ``UvDownloader`` over stdlib ``urllib.request`` (follows redirects)."""

    def __init__(self, *, timeout: float = _DOWNLOAD_TIMEOUT) -> None:
        self._timeout = timeout

    def fetch(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=self._timeout) as response:
            data: bytes = response.read()
            return data


def select_asset(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """Resolve the host platform to a pinned ``(download_url, sha256)``.

    ``system`` / ``machine`` default to ``platform.system()`` / ``platform.machine()``
    (injectable for tests). Raises ``UvBootstrapError`` for any platform not in the
    pinned table (e.g. Windows).
    """
    system_raw = platform.system() if system is None else system
    machine_raw = platform.machine() if machine is None else machine
    os_key = _OS_ALIASES.get(system_raw.lower())
    arch_key = _ARCH_ALIASES.get(machine_raw.lower())
    asset = _ASSETS.get((os_key, arch_key)) if os_key and arch_key else None
    if asset is None:
        raise UvBootstrapError(
            f"auto-bootstrap of uv is not supported on {system_raw}/{machine_raw}; "
            "install uv manually or set GATECHECK_UV"
        )
    asset_name, sha256 = asset
    return f"{_RELEASE_BASE}/{_UV_VERSION}/{asset_name}", sha256


def bootstrap_uv(
    cache_root: Path,
    *,
    downloader: UvDownloader | None = None,
    asset: tuple[str, str] | None = None,
) -> Path:
    """Return a cached, checksum-verified ``uv`` binary, downloading it once.

    A previously bootstrapped ``<cache_root>/bin/uv`` is returned immediately. On a
    miss, download the pinned artifact (``asset`` overrides the platform lookup as
    ``(url, sha256)`` — for tests), verify its SHA-256, extract the ``uv`` binary,
    and atomically publish it (chmod +x). Raises ``UvBootstrapError`` on an
    unsupported platform, checksum mismatch, or an archive missing ``uv``.
    """
    dest = cache_root / "bin" / _uv_binary_name()
    if venv.is_executable(dest):
        return dest

    url, expected_sha = asset if asset is not None else select_asset()
    payload = (downloader or UrllibUvDownloader()).fetch(url)
    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != expected_sha:
        raise UvBootstrapError(
            f"checksum mismatch for {url}: expected {expected_sha}, got {actual_sha}"
        )

    binary = _extract_uv_binary(payload)
    _publish(dest, binary)
    return dest


def _uv_binary_name() -> str:
    """The bootstrapped uv filename: ``uv.exe`` on Windows, else ``uv``."""
    return "uv.exe" if venv.is_windows() else "uv"


def _extract_uv_binary(payload: bytes) -> bytes:
    """Return the ``uv`` binary bytes from a ``.zip`` (Windows) or ``.tar.gz`` payload.

    Reads a single member (no bulk extract — no path-traversal surface). Raises
    ``UvBootstrapError`` if the archive is unreadable or has no ``uv`` executable.
    """
    if zipfile.is_zipfile(io.BytesIO(payload)):
        return _extract_from_zip(payload)
    return _extract_from_tar(payload)


def _extract_from_tar(payload: bytes) -> bytes:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and Path(member.name).name in ("uv", "uv.exe"):
                    handle = tar.extractfile(member)
                    if handle is not None:
                        return handle.read()
    except tarfile.TarError as exc:
        raise UvBootstrapError(f"could not read the uv archive: {exc}") from exc
    raise UvBootstrapError("no 'uv' binary found in the downloaded archive")


def _extract_from_zip(payload: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if Path(name).name in ("uv", "uv.exe"):
                    return archive.read(name)
    except zipfile.BadZipFile as exc:
        raise UvBootstrapError(f"could not read the uv archive: {exc}") from exc
    raise UvBootstrapError("no 'uv' binary found in the downloaded archive")


def _publish(dest: Path, binary: bytes) -> None:
    """Atomically write ``binary`` to ``dest`` as an executable (temp + os.replace)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".uv-")
    try:
        with os.fdopen(handle, "wb") as tmp_file:
            tmp_file.write(binary)
        os.chmod(tmp, 0o755)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def default_bootstrapper(cache_root: Path, environ: Mapping[str, str] | None = None) -> Path:
    """Bootstrap uv into ``cache_root`` using the real network downloader.

    ``environ`` is accepted for signature symmetry with the discovery seam; platform
    detection uses ``platform``, not the environment.
    """
    return bootstrap_uv(cache_root)
