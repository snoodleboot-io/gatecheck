"""Map a parsed pre-commit config onto gatecheck hooks (STY-0020 / GAT-23).

Best-effort translation: a small known-repo table maps common pre-commit repos to
``pypi:`` sources + run commands; unknown repos and lossy translations are still
mapped but flagged as warnings (nothing is silently dropped).
"""

from __future__ import annotations

import re

from gatecheck.config import GatecheckConfig
from gatecheck.config.hook_def import HookDef
from gatecheck.migration.precommit_config import PreCommitConfig, PreCommitHook, PreCommitRepo

# repo-URL substring -> pypi package name.
_KNOWN_REPOS = {
    "astral-sh/ruff-pre-commit": "ruff",
    "psf/black": "black",
    "pycqa/isort": "isort",
    "pycqa/flake8": "flake8",
    "pre-commit/mirrors-mypy": "mypy",
    "pre-commit/pre-commit-hooks": "pre-commit-hooks",
    "pycqa/bandit": "bandit",
}
# hook id -> the run command (subcommand); default is the package name.
_RUN_OVERRIDES = {"ruff": "ruff check", "ruff-format": "ruff format"}
_VERSION_RE = re.compile(r"^v?\d")


def map_precommit(precommit: PreCommitConfig) -> tuple[GatecheckConfig, list[str]]:
    """Translate ``precommit`` into a ``GatecheckConfig`` plus best-effort warnings."""
    hooks: list[HookDef] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}

    for repo in precommit.repos:
        for hook in repo.hooks:
            from_, run = _map_source(repo, hook, warnings)
            if hook.files:
                warnings.append(
                    f"hook '{hook.id}': pre-commit 'files' is a regex and was not translated; "
                    "set a glob in check.toml if needed"
                )
            hook_id = _unique_id(hook.id, seen)
            hooks.append(HookDef.model_validate({"id": hook_id, "from": from_, "run": run}))

    return GatecheckConfig(hook=hooks), warnings


def _map_source(repo: PreCommitRepo, hook: PreCommitHook, warnings: list[str]) -> tuple[str, str]:
    """Return the ``(from, run)`` for one hook, appending any warnings."""
    if repo.repo.strip().lower() == "local":
        return "system", _command(hook.entry or hook.id, hook)

    package = _known_package(repo.repo)
    if package is not None:
        base = _RUN_OVERRIDES.get(hook.id, package)
        return _pypi_source(package, repo.rev, hook.id, warnings), _command(base, hook)

    guess = _guess_package(repo.repo)
    warnings.append(
        f"hook '{hook.id}': best-effort mapping for unknown repo '{repo.repo}' (from = 'pypi:{guess}')"
    )
    return f"pypi:{guess}", _command(hook.entry or hook.id, hook)


def _pypi_source(package: str, rev: str | None, hook_id: str, warnings: list[str]) -> str:
    """Build the ``pypi:`` from-spec, pinning the rev to a version when it looks like one."""
    if rev and _VERSION_RE.match(rev):
        return f"pypi:{package}=={rev.lstrip('v')}"
    if rev:
        warnings.append(
            f"hook '{hook_id}': rev '{rev}' could not be pinned to a version; using unpinned 'pypi:{package}'"
        )
    return f"pypi:{package}"


def _command(base: str, hook: PreCommitHook) -> str:
    """The run command: the base command plus the hook's args."""
    return " ".join([base, *hook.args])


def _guess_package(repo_url: str) -> str:
    """Best-effort package name from a repo URL (last path segment, sans ``.git``)."""
    segment = repo_url.rstrip("/").rsplit("/", 1)[-1]
    return segment[:-4] if segment.endswith(".git") else segment


def _known_package(repo_url: str) -> str | None:
    lowered = repo_url.lower()
    for substring, package in _KNOWN_REPOS.items():
        if substring in lowered:
            return package
    return None


def _unique_id(hook_id: str, seen: dict[str, int]) -> str:
    """De-duplicate repeated hook ids (``ruff``, ``ruff-2``, …)."""
    if hook_id not in seen:
        seen[hook_id] = 1
        return hook_id
    seen[hook_id] += 1
    return f"{hook_id}-{seen[hook_id]}"
