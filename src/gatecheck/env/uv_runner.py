"""UvRunner — the uv subprocess boundary for building pypi environments (STY-0008 / GAT-10).

The only module that discovers and shells out to the external ``uv`` binary.
``UvRunner`` is a single injectable ``typing.Protocol`` (mirroring the
``RegistryClient`` seam in ``gatecheck.registry``) so ``EnvManager``'s pypi branch
is unit-testable against a fake — no real ``uv``, no ``subprocess`` monkeypatching.
``SubprocessUvRunner`` is the default impl; when ``uv`` is absent it auto-bootstraps
a pinned, checksum-verified copy (``uv_bootstrap``) unless disabled, and it raises
``UvBuildError`` on a non-zero ``uv`` exit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from gatecheck import venv
from gatecheck.env.env_cache import default_cache_root
from gatecheck.env.uv_bootstrap import bootstrap_uv
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

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        *,
        cache_root: Path | None = None,
        bootstrapper: Callable[[Path], Path] | None = None,
        allow_bootstrap: bool = True,
        python_version: str | None = None,
    ) -> None:
        self._environ = environ  # None → os.environ, resolved lazily in _find_uv
        self._cache_root = cache_root  # None → default_cache_root(environ)
        self._bootstrapper = bootstrapper  # injectable seam (tests); None → bootstrap_uv
        self._allow_bootstrap = allow_bootstrap
        self._python_version = python_version  # None → uv's default interpreter

    def build_venv(self, pinned: ResolvedPyPISource, dest: Path) -> None:
        """Create a venv at ``dest`` and install ``pinned`` into it.

        Builds with ``--relocatable`` so Python console scripts get a relative
        ``#!/bin/sh`` wrapper shebang instead of an absolute interpreter path. The
        caller builds here (a temp dir) and then atomically moves the venv into the
        cache slot; without ``--relocatable`` every console script's shebang would
        point at the now-gone build dir and fail to execute (BUG-0007). Native-binary
        tools like ``ruff`` have no shebang and were unaffected, which is why this
        stayed hidden.

        Builds with ``--python <version>`` when a ``python_version`` was requested
        (a package's ``[package].python``); ``uv`` picks or downloads that interpreter.
        Raises ``UvNotFound`` if ``uv`` is absent and ``UvBuildError`` on a non-zero
        ``uv`` exit. ``dest`` is a fresh directory owned by the caller (the atomic
        build temp); this method never touches the cache layout.
        """
        uv = self._find_uv()
        venv_argv = [uv, "venv", "--relocatable"]
        if self._python_version:
            venv_argv += ["--python", self._python_version]
        venv_argv.append(str(dest))
        self._run(venv_argv)
        self._install(uv, pinned, venv.python_executable(dest))

    def _install(self, uv: str, pinned: ResolvedPyPISource, python: Path) -> None:
        """Install ``pinned`` into the venv at ``python`` as an exact version pin.

        Installs ``NAME==VERSION`` and lets ``uv`` resolve and verify the dependency
        tree. gatecheck does **not** use ``--require-hashes``: that mode requires every
        package in the resolution — including transitive dependencies — to be pinned
        and hashed, but gatecheck only knows the top-level package's version, so it
        would fail for any package with dependencies (BUG-0006). The exact version pin
        is the reproducibility guarantee; full-tree hash verification would need a
        lockfile, which is a separate feature.
        """
        self._run(self._install_argv(uv, pinned, python))

    @staticmethod
    def _install_argv(uv: str, pinned: ResolvedPyPISource, python: Path) -> list[str]:
        """Build the ``uv pip install NAME==VERSION --index-url URL`` argv."""
        return [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            f"{pinned.name}=={pinned.version}",
            "--index-url",
            pinned.index_url,
        ]

    def _find_uv(self) -> str:
        """Locate ``uv``: ``GATECHECK_UV`` override → ``PATH`` → auto-bootstrap a pinned uv.

        When ``uv`` is absent and bootstrapping is enabled (default), download a
        pinned, checksum-verified uv into the cache and return it (``UvBootstrapError``
        on failure). Bootstrapping is skipped — raising ``UvNotFound`` as before — when
        ``allow_bootstrap`` is false or ``GATECHECK_NO_BOOTSTRAP`` is set.
        """
        env = os.environ if self._environ is None else self._environ
        override = env.get("GATECHECK_UV")
        if override:
            candidate = Path(override)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
            raise UvNotFound(f"GATECHECK_UV={override!r} is not an executable file")
        located = shutil.which("uv", path=env.get("PATH", os.defpath))
        if located is not None:
            return located
        if not self._allow_bootstrap or env.get("GATECHECK_NO_BOOTSTRAP"):
            raise UvNotFound(
                "uv not found on PATH (set GATECHECK_UV, install uv, or allow "
                "auto-bootstrap by unsetting GATECHECK_NO_BOOTSTRAP)"
            )
        bootstrap = self._bootstrapper if self._bootstrapper is not None else bootstrap_uv
        cache_root = self._cache_root if self._cache_root is not None else default_cache_root(env)
        return str(bootstrap(cache_root))

    def _run(self, argv: list[str]) -> None:
        """Run ``argv`` to completion; raise ``UvBuildError`` on non-zero exit."""
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:  # uv vanished between discovery and exec
            raise UvNotFound(f"uv binary could not be executed: {exc}") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or "")[-_STDERR_TAIL:].strip()
            raise UvBuildError(f"`{' '.join(argv)}` exited {completed.returncode}: {tail}")
