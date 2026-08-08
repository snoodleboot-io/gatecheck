"""Map a parsed pre-commit config onto hooksmith hooks (STY-0020 / GAT-23, STY-0032).

Best-effort translation: a known-repo table maps common pre-commit repos to
``pypi:`` (or ``system``) sources + run commands; unknown repos and lossy
translations are still mapped but flagged as warnings (nothing is silently dropped).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hooksmith.config import HooksmithConfig
from hooksmith.config.hook_def import HookDef
from hooksmith.migration.precommit_config import PreCommitConfig, PreCommitHook, PreCommitRepo


@dataclass(frozen=True)
class _KnownRepo:
    """How to source and run a recognized pre-commit repo.

    ``source`` is ``"pypi"`` or ``"system"``. For ``pypi`` repos ``package`` is the
    distribution name. ``command`` is the default run command (``None`` means derive
    it from the hook's ``entry``/``id`` — e.g. the multi-hook ``pre-commit-hooks``).
    ``run_by_hook_id`` overrides the command for specific hook ids (e.g. ruff).
    """

    source: str
    package: str | None = None
    command: str | None = None
    run_by_hook_id: dict[str, str] = field(default_factory=dict)


# repo-URL substring -> how to source/run it. Substrings are matched case-insensitively;
# more specific substrings must precede the substrings they contain (e.g. the black
# mirror before plain black).
_KNOWN_REPOS: dict[str, _KnownRepo] = {
    "astral-sh/ruff-pre-commit": _KnownRepo(
        "pypi",
        "ruff",
        "ruff",
        run_by_hook_id={"ruff": "ruff check", "ruff-format": "ruff format"},
    ),
    "psf/black-pre-commit-mirror": _KnownRepo("pypi", "black", "black"),
    "psf/black": _KnownRepo("pypi", "black", "black"),
    "pycqa/isort": _KnownRepo("pypi", "isort", "isort"),
    "pycqa/flake8": _KnownRepo("pypi", "flake8", "flake8"),
    "pycqa/bandit": _KnownRepo("pypi", "bandit", "bandit"),
    "pycqa/pydocstyle": _KnownRepo("pypi", "pydocstyle", "pydocstyle"),
    "pycqa/autoflake": _KnownRepo("pypi", "autoflake", "autoflake"),
    "pycqa/docformatter": _KnownRepo("pypi", "docformatter", "docformatter"),
    "pre-commit/mirrors-mypy": _KnownRepo("pypi", "mypy", "mypy"),
    "pre-commit/pre-commit-hooks": _KnownRepo("pypi", "pre-commit-hooks"),
    "codespell-project/codespell": _KnownRepo("pypi", "codespell", "codespell"),
    "yelp/detect-secrets": _KnownRepo("pypi", "detect-secrets", "detect-secrets"),
    "shellcheck-py/shellcheck-py": _KnownRepo("pypi", "shellcheck-py", "shellcheck"),
    "asottile/pyupgrade": _KnownRepo("pypi", "pyupgrade", "pyupgrade"),
    "asottile/add-trailing-comma": _KnownRepo("pypi", "add-trailing-comma", "add-trailing-comma"),
    # Node / system tools hooksmith cannot source from PyPI → system (must be on PATH).
    "pre-commit/mirrors-prettier": _KnownRepo("system", command="prettier"),
    "rbubley/mirrors-prettier": _KnownRepo("system", command="prettier"),
    "pre-commit/mirrors-eslint": _KnownRepo("system", command="eslint"),
    "koalaman/shellcheck-precommit": _KnownRepo("system", command="shellcheck"),
}

_VERSION_RE = re.compile(r"^v?\d")
# A pre-commit `files` regex that is safely a single anchored extension → glob.
# Matches: `\.py$`, `^\.py$`, `.*\.py$`, `^.*\.py$` → `*.py`.
_SIMPLE_EXT_RE = re.compile(r"^\^?(?:\.\*)?\\\.([A-Za-z0-9]+)\$$")


def map_precommit(precommit: PreCommitConfig) -> tuple[HooksmithConfig, list[str]]:
    """Translate ``precommit`` into a ``HooksmithConfig`` plus best-effort warnings."""
    hooks: list[HookDef] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}

    for repo in precommit.repos:
        for hook in repo.hooks:
            from_, run = _map_source(repo, hook, warnings)
            data: dict[str, object] = {
                "id": _unique_id(hook.id, seen),
                "from": from_,
                "run": run,
            }
            _apply_files(data, hook, warnings)
            if hook.pass_filenames is False:
                data["pass-files"] = False
            hooks.append(HookDef.model_validate(data))

    return HooksmithConfig(hook=hooks), warnings


def _map_source(repo: PreCommitRepo, hook: PreCommitHook, warnings: list[str]) -> tuple[str, str]:
    """Return the ``(from, run)`` for one hook, appending any warnings."""
    if repo.repo.strip().lower() == "local":
        return "system", _command(hook.entry or hook.id, hook)

    known = _known_repo(repo.repo)
    if known is not None:
        run = _known_command(known, hook)
        if known.source == "system":
            tool = run.split(" ", 1)[0]
            warnings.append(
                f"hook '{hook.id}': maps to system tool '{tool}' — ensure it is installed on "
                "PATH (hooksmith does not manage npm/system tools)"
            )
            return "system", run
        return _pypi_source(known.package, repo.rev, hook.id, warnings), run

    guess = _guess_package(repo.repo)
    warnings.append(
        f"hook '{hook.id}': best-effort mapping for unknown repo '{repo.repo}' (from = 'pypi:{guess}')"
    )
    return f"pypi:{guess}", _command(hook.entry or hook.id, hook)


def _known_command(known: _KnownRepo, hook: PreCommitHook) -> str:
    """The run command for a known repo: hook-id override, fixed command, or entry/id."""
    if hook.id in known.run_by_hook_id:
        base = known.run_by_hook_id[hook.id]
    elif known.command is not None:
        base = known.command
    else:
        base = hook.entry or hook.id
    return _command(base, hook)


def _pypi_source(package: str | None, rev: str | None, hook_id: str, warnings: list[str]) -> str:
    """Build the ``pypi:`` from-spec, pinning the rev to a version when it looks like one."""
    if rev and _VERSION_RE.match(rev):
        return f"pypi:{package}=={rev.lstrip('v')}"
    if rev:
        warnings.append(
            f"hook '{hook_id}': rev '{rev}' could not be pinned to a version; using unpinned 'pypi:{package}'"
        )
    return f"pypi:{package}"


def _apply_files(data: dict[str, object], hook: PreCommitHook, warnings: list[str]) -> None:
    """Translate a pre-commit ``files`` regex to a glob when safe; warn otherwise."""
    if not hook.files:
        return
    glob = _regex_to_glob(hook.files)
    if glob is not None:
        data["files"] = glob
    else:
        warnings.append(
            f"hook '{hook.id}': pre-commit 'files' is a regex and was not translated; "
            "set a glob in check.toml if needed"
        )


def _regex_to_glob(files: str) -> str | None:
    """Map a single-extension anchored regex (``\\.py$``) to a glob (``*.py``); else ``None``."""
    match = _SIMPLE_EXT_RE.match(files.strip())
    return f"*.{match.group(1)}" if match else None


def _command(base: str, hook: PreCommitHook) -> str:
    """The run command: the base command plus the hook's args."""
    return " ".join([base, *hook.args])


def _guess_package(repo_url: str) -> str:
    """Best-effort package name from a repo URL (last path segment, sans ``.git``)."""
    segment = repo_url.rstrip("/").rsplit("/", 1)[-1]
    return segment[:-4] if segment.endswith(".git") else segment


def _known_repo(repo_url: str) -> _KnownRepo | None:
    lowered = repo_url.lower()
    for substring, known in _KNOWN_REPOS.items():
        if substring in lowered:
            return known
    return None


def _unique_id(hook_id: str, seen: dict[str, int]) -> str:
    """De-duplicate repeated hook ids (``ruff``, ``ruff-2``, …)."""
    if hook_id not in seen:
        seen[hook_id] = 1
        return hook_id
    seen[hook_id] += 1
    return f"{hook_id}-{seen[hook_id]}"
