"""UvRunner — the uv subprocess boundary for building pypi environments (STY-0008 / GAT-10).

The only module that discovers and shells out to the external ``uv`` binary.
``UvRunner`` is a single injectable ``typing.Protocol`` (mirroring the
``RegistryClient`` seam in ``gatecheck.registry``) so ``EnvManager``'s pypi branch
is unit-testable against a fake — no real ``uv``, no ``subprocess`` monkeypatching.
``SubprocessUvRunner`` is the default impl; it raises ``UvNotFound`` when the binary
is absent (the seam STY-0010 fills with auto-bootstrap) and ``UvBuildError`` on a
non-zero ``uv`` exit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from gatecheck.registry import ResolvedPyPISource

_STDERR_TAIL = 2000  # bytes of uv stderr kept in a UvBuildError message


class UvNotFound(Exception):  # noqa: N818  (a signal, not an *Error — mirrors PackageNotFound)
    """Raised when the ``uv`` binary cannot be located (auto-bootstrap is STY-0010)."""


class UvBuildError(Exception):
    """Raised when a ``uv`` subprocess exits non-zero while building an environment."""


class UvRunner(Protocol):
    """The injectable uv boundary: build a venv at ``dest`` with ``pinned`` installed."""

    def build_venv(self, pinned: ResolvedPyPISource, dest: Path) -> None: ...


class SubprocessUvRunner:
    """Default ``UvRunner`` — discovers ``uv`` and shells out to ``uv venv`` / ``uv pip install``."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ  # None → os.environ, resolved lazily in _find_uv

    def build_venv(self, pinned: ResolvedPyPISource, dest: Path) -> None:
        """Create a venv at ``dest`` and install ``pinned`` into it.

        Raises ``UvNotFound`` if ``uv`` is absent and ``UvBuildError`` on a non-zero
        ``uv`` exit. ``dest`` is a fresh directory owned by the caller (the atomic
        build temp); this method never touches the cache layout.
        """
        uv = self._find_uv()
        self._run([uv, "venv", str(dest)])
        self._install(uv, pinned, dest / "bin" / "python")

    def _install(self, uv: str, pinned: ResolvedPyPISource, python: Path) -> None:
        """Install ``pinned`` into the venv at ``python``, using ``--require-hashes`` when known."""
        if pinned.sha256 is None:
            self._run(self._install_argv(uv, pinned, python))
            return
        # uv requires the hash to travel with the requirement, via a requirements file.
        requirement = f"{pinned.name}=={pinned.version} --hash=sha256:{pinned.sha256}\n"
        handle, req_path = tempfile.mkstemp(prefix="gatecheck-req-", suffix=".txt")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as req_file:
                req_file.write(requirement)
            self._run(self._install_argv(uv, pinned, python, req_path))
        finally:
            os.unlink(req_path)

    @staticmethod
    def _install_argv(
        uv: str, pinned: ResolvedPyPISource, python: Path, req_path: str | None = None
    ) -> list[str]:
        """Build the ``uv pip install`` argv (``--require-hashes -r`` when ``req_path`` is set)."""
        argv = [uv, "pip", "install", "--python", str(python)]
        if req_path is not None:
            argv += ["--require-hashes", "-r", req_path]
        else:
            argv += [f"{pinned.name}=={pinned.version}"]
        argv += ["--index-url", pinned.index_url]
        return argv

    def _find_uv(self) -> str:
        """Locate ``uv`` via ``GATECHECK_UV`` override, else ``shutil.which`` on the injected PATH.

        Raises ``UvNotFound`` (naming the override and the STY-0010 bootstrap) when
        no usable ``uv`` binary is found.
        """
        env = os.environ if self._environ is None else self._environ
        override = env.get("GATECHECK_UV")
        if override:
            candidate = Path(override)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
            raise UvNotFound(f"GATECHECK_UV={override!r} is not an executable file")
        located = shutil.which("uv", path=env.get("PATH", os.defpath))
        if located is None:
            raise UvNotFound(
                "uv not found on PATH (set GATECHECK_UV or install uv; auto-bootstrap is STY-0010)"
            )
        return located

    def _run(self, argv: list[str]) -> None:
        """Run ``argv`` to completion; raise ``UvBuildError`` on non-zero exit."""
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:  # uv vanished between discovery and exec
            raise UvNotFound(f"uv binary could not be executed: {exc}") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or "")[-_STDERR_TAIL:].strip()
            raise UvBuildError(f"`{' '.join(argv)}` exited {completed.returncode}: {tail}")
