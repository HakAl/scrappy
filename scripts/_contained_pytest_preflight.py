#!/usr/bin/env python
"""Fail-closed preflight validator for scripts/contained-pytest.sh (scrappy-i2jo PR-1).

This helper is invoked BY the launcher, before it execs pytest. It performs the
checks that need real pathlib join/resolve semantics or a third-party capability
probe, which shell cannot do faithfully:

  - S-13 temp preconditions: model exactly what tests/conftest.py:17-32 computes
    from an INHERITED SCRAPPY_TEST_TEMP / SCRAPPY_TEST_SESSION_ID, and reject when
    the resolved scratch root escapes the repository. Under pathlib join an ABSOLUTE
    session id discards the preceding root, and ``..`` escapes it; both are caught by
    resolving the modelled path and checking containment, never by string matching.
  - Effective --basetemp (input N2): scan argv, PYTEST_ADDOPTS and the pyproject
    addopts, not just the launcher's own argv, and reject an outside-root basetemp.
  - python-dotenv capability gate (S-4): the declared floor does not guarantee the
    PYTHON_DOTENV_DISABLED switch, so verify the INSTALLED distribution honours it.

It imports only the standard library plus python-dotenv (a third-party package that
imports nothing from this project and writes nothing). It never imports scrappy and
never runs pytest.

Exit status: 0 = all checks passed; non-zero = fail closed, pytest must not start.
"""

from __future__ import annotations

import argparse
import configparser
import os
import shlex
import sys
from pathlib import Path

try:  # tomllib is stdlib on the 3.13 interpreter this launcher targets
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - defensive only
    tomllib = None  # type: ignore[assignment]


def _fail(check: str, detail: str) -> None:
    print(f"[preflight] FAIL {check}: {detail}", file=sys.stderr)
    raise SystemExit(11)


def _ok(check: str, detail: str) -> None:
    print(f"[preflight] ok   {check}: {detail}", file=sys.stderr)


def _is_inside(root: Path, candidate: Path) -> bool:
    """True iff ``candidate`` (already resolved) is ``root`` or nested under it."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _model_conftest_scratch(repo_root: Path, test_temp: str, session_id: str) -> Path:
    """Replicate tests/conftest.py:17-32's scratch-root computation exactly.

    _get_session_temp_root: base_root = Path(override).expanduser() if override
    else root_path/'.pytest_tmp'; return base_root / session_id.
    _configure_test_temp_dirs: session_root = that.resolve().
    """
    base_root = Path(test_temp).expanduser() if test_temp else repo_root / ".pytest_tmp"
    session_root = base_root / session_id  # absolute session_id discards base_root
    return session_root.resolve()


def _scan_basetemp(tokens: list[str]) -> list[str]:
    """Return every --basetemp value in a token list (``=`` and space forms)."""
    values: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--basetemp":
            if i + 1 < len(tokens):
                values.append(tokens[i + 1])
            i += 2
            continue
        if tok.startswith("--basetemp="):
            values.append(tok.split("=", 1)[1])
        i += 1
    return values


def _pyproject_addopts_tokens(repo_root: Path) -> list[str]:
    pyproject = repo_root / "pyproject.toml"
    if tomllib is None or not pyproject.exists():
        return []
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    addopts = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("addopts")
    if addopts is None:
        return []
    if isinstance(addopts, str):
        return shlex.split(addopts)
    if isinstance(addopts, list):
        tokens: list[str] = []
        for item in addopts:
            tokens.extend(shlex.split(item) if isinstance(item, str) else [])
        return tokens
    return []


def _pytest_ini_addopts_tokens(repo_root: Path) -> list[str]:
    # pytest.ini, when present, OVERRIDES pyproject's [tool.pytest.ini_options]; this is
    # the EFFECTIVE config for the tree at ba1e1da (the plan cites pyproject.toml:90, but
    # pytest reports "ignoring pytest config in pyproject.toml" in favour of pytest.ini).
    ini = repo_root / "pytest.ini"
    if not ini.exists():
        return []
    parser = configparser.ConfigParser()
    try:
        parser.read(ini, encoding="utf-8")
    except configparser.Error:
        return []
    if not parser.has_option("pytest", "addopts"):
        return []
    return shlex.split(parser.get("pytest", "addopts"))


def _config_addopts_tokens(repo_root: Path) -> tuple[list[str], str]:
    """Return (tokens, source) for the EFFECTIVE pytest addopts.

    Scans both config files but reports the one pytest would actually honour, so an
    outside-root --basetemp hidden in either is caught (input N2).
    """
    ini_tokens = _pytest_ini_addopts_tokens(repo_root)
    pyproject_tokens = _pyproject_addopts_tokens(repo_root)
    if (repo_root / "pytest.ini").exists():
        return ini_tokens + pyproject_tokens, "pytest.ini (pyproject ignored by pytest)"
    return pyproject_tokens, "pyproject.toml"


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--profile-root", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--original-home", default="")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--inherited-test-temp", default="")
    parser.add_argument("--inherited-session-id", default="")
    parser.add_argument("--dotenv-floor", default="1.2.0")
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # --- S-13: inherited SCRAPPY_TEST_TEMP / SCRAPPY_TEST_SESSION_ID -----------
    # Model the value tests/conftest.py would trust verbatim and reject an escape.
    if args.inherited_test_temp or args.inherited_session_id:
        inherited_sid = args.inherited_session_id or args.session_id
        modelled = _model_conftest_scratch(repo_root, args.inherited_test_temp, inherited_sid)
        if not _is_inside(repo_root, modelled):
            _fail(
                "S13-inherited-temp",
                f"inherited SCRAPPY_TEST_TEMP={args.inherited_test_temp!r} "
                f"SCRAPPY_TEST_SESSION_ID={args.inherited_session_id!r} model to {modelled}, "
                f"outside repo {repo_root}",
            )
        _ok("S13-inherited-temp", f"modelled scratch {modelled} is inside repo")
    else:
        _ok("S13-inherited-temp", "no inherited SCRAPPY_TEST_TEMP/SESSION_ID to guard")

    # The session id the launcher is about to assign must itself stay in-repo when
    # joined onto the launcher's own scratch base (defence in depth vs an absolute
    # or dot-dot session id that slipped past the inherited check because it was set
    # only via SCRAPPY_TEST_SESSION_ID with no SCRAPPY_TEST_TEMP).
    chosen = _model_conftest_scratch(repo_root, str(args.profile_root) + "/scratch", args.session_id)
    if not _is_inside(repo_root, chosen):
        _fail("S13-chosen-session-id", f"session id {args.session_id!r} escapes to {chosen}")
    _ok("S13-chosen-session-id", f"assigned scratch {chosen} is inside repo")

    # --- profile root and HOME path containment (validation items 1 and 2) ----
    # These run BEFORE the launcher creates the tree, so they check path
    # containment only. The launcher re-asserts directory EXISTENCE in shell after
    # it has created the profile (STEP C), which is the moment "the launcher just
    # created it" can honestly be checked.
    profile_root = Path(args.profile_root).resolve()
    if not _is_inside(repo_root, profile_root):
        _fail("profile-under-repo", f"{profile_root} not under {repo_root}")
    _ok("profile-under-repo", f"{profile_root} is under repo")

    home = Path(args.home).resolve()
    if not _is_inside(repo_root, home):
        _fail("home-contained", f"HOME {home} not under repo {repo_root}")
    if args.original_home:
        original = Path(args.original_home).expanduser().resolve()
        if home == original:
            _fail("home-not-real", f"HOME still resolves to the real profile {original}")
    _ok("home-contained", f"HOME {home} is contained and distinct from the real profile")

    # --- N2: effective --basetemp across argv, PYTEST_ADDOPTS, pyproject -------
    argv_tokens = list(args.pytest_args)
    addopts_env = shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))
    config_tokens, config_source = _config_addopts_tokens(repo_root)
    found = (
        _scan_basetemp(argv_tokens)
        + _scan_basetemp(addopts_env)
        + _scan_basetemp(config_tokens)
    )
    if found:
        for raw in found:
            resolved = (Path.cwd() / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            if not _is_inside(repo_root, resolved):
                _fail("basetemp-contained", f"--basetemp={raw!r} resolves to {resolved}, outside repo")
        _ok("basetemp-contained", f"effective --basetemp value(s) {found} resolve inside repo")
    else:
        _ok("basetemp-contained", f"no effective --basetemp in argv/PYTEST_ADDOPTS/{config_source}")

    # --- S-4: python-dotenv honours PYTHON_DOTENV_DISABLED --------------------
    try:
        import dotenv.main as dotenv_main
        from importlib import metadata
    except Exception as exc:  # pragma: no cover - dotenv is a declared dependency
        _fail("dotenv-capability", f"could not import python-dotenv: {exc}")
    installed = metadata.version("python-dotenv")
    if not hasattr(dotenv_main, "_load_dotenv_disabled"):
        _fail("dotenv-capability", f"installed python-dotenv {installed} lacks the disable switch")
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    if dotenv_main._load_dotenv_disabled() is not True:
        _fail("dotenv-capability", f"python-dotenv {installed} did not honour PYTHON_DOTENV_DISABLED")
    _ok("dotenv-capability", f"python-dotenv {installed} honours PYTHON_DOTENV_DISABLED (floor {args.dotenv_floor})")

    print("[preflight] all checks passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
