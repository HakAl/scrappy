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


PROFILE_MARKER = ".pytest_profile"


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


def _scan_valued_flag(tokens: list[str], long: str, short: str | None = None) -> list[str]:
    """Return every value given to a valued flag, in the UNCLUSTERED forms modelled here.

    Supported contract, and nothing beyond it: ``--flag value``, ``--flag=value``,
    ``-x value``, ``-xvalue`` and ``-x=value``, where ``-x`` is the flag's own short
    option. THIS HELPER ALONE IS NOT SUFFICIENT: it returns no override for
    ``-voaddopts=x``, which argparse does accept, and safety there depends on its caller
    refusing that token first (see _unmodelled_short_clusters).
    Written generically because the same shapes carry BOTH of the config channels the
    original scanner missed (finding scrappy-f7l7): ``-o``/``--override-ini`` and ``-c``.

    These are the ONLY short forms this scanner models. CLUSTERED short options such as
    ``-voaddopts=...`` are NOT modelled here; they are refused outright before any scan
    runs (see _unmodelled_short_clusters and finding scrappy-tnyy).

    THE ``-x=value`` FORM IS NOT OPTIONAL (finding scrappy-wwm9). argparse strips the
    separator, so ``-o=addopts=@args.txt`` reaches pytest as the override
    ``addopts=@args.txt``. Returning the raw remainder ``=addopts=@args.txt`` instead put
    an empty ini name in front of it, the override was discarded as unparseable, and the
    response file behind it became invisible to every later check.
    """
    values: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == long or (short is not None and tok == short):
            if i + 1 < len(tokens):
                values.append(tokens[i + 1])
            i += 2
            continue
        if tok.startswith(long + "="):
            values.append(tok.split("=", 1)[1])
        elif short is not None and tok.startswith(short) and len(tok) > len(short):
            remainder = tok[len(short):]
            # argparse consumes a single separator between a short option and its value.
            values.append(remainder[1:] if remainder.startswith("=") else remainder)
        i += 1
    return values


# Short options whose ATTACHED form this scanner models: -o/-c plus their value.
MODELLED_SHORT_OPTIONS = frozenset({"o", "c"})


def _unmodelled_short_clusters(tokens: list[str]) -> list[str]:
    """Return short-option tokens whose grammar this preflight does not model.

    argparse (which pytest subclasses without changing cluster parsing) accepts CLUSTERED
    short options, so ``-voaddopts=--basetemp=/outside`` is ``-v`` followed by ``-o`` with
    a value. A scanner that looks for tokens beginning ``-o`` never sees it, and the same
    trick hides ``-c`` and, through an addopts override, a response file (scrappy-tnyy).

    Modelling clusters correctly would require knowing the arity of EVERY pytest short
    option, including those added by plugins, and getting it wrong in the permissive
    direction reopens the hole while getting it wrong in the restrictive direction breaks
    ordinary use. Every previous attempt in this bead to model an argument grammar more
    cleverly introduced a new gap, so this REFUSES instead.

    Cost: combined short flags must be passed separately, ``-x -v -s`` rather than
    ``-xvs``, and ``-k expr`` rather than ``-kexpr``. That is a small, clearly-reported
    ergonomic cost, paid once at the launcher, in exchange for an argument surface that
    can actually be analysed.
    """
    unmodelled: list[str] = []
    for tok in tokens:
        if not tok.startswith("-") or tok.startswith("--") or len(tok) <= 2:
            continue
        if tok[1] in MODELLED_SHORT_OPTIONS:
            continue
        unmodelled.append(tok)
    return unmodelled


def _override_addopts_tokens(tokens: list[str]) -> list[str]:
    """Return addopts tokens injected via ``-o addopts=...`` / ``--override-ini``.

    _pytest/config/__init__.py:1501-1503 reads override_ini and :1527-1529 prepends the
    EFFECTIVE addopts, so an override reaches pytest exactly like a config file would.
    The launcher forwards argv unchanged, so this channel must be scanned or a hostile
    --basetemp hides behind a token that merely begins "addopts=" (finding scrappy-f7l7).
    """
    injected: list[str] = []
    for override in _scan_valued_flag(tokens, "--override-ini", "-o"):
        name, sep, value = override.partition("=")
        if sep and name.strip() == "addopts":
            injected.extend(shlex.split(value))
    return injected


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


def _pinned_config_file(repo_root: Path) -> Path | None:
    """Return the config file the launcher will pin with -c, or None if there is none.

    pytest.ini wins over pyproject.toml, matching what pytest itself honours (it reports
    "ignoring pytest config in pyproject.toml" when both exist).
    """
    for name in ("pytest.ini", "pyproject.toml"):
        candidate = repo_root / name
        if candidate.exists():
            return candidate
    return None


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
    # IN-REPO IS NOT ENOUGH. A session id such as "../escape" or "sub/../../escape"
    # traverses OUT of .pytest_profile/ while still resolving inside the repo, so the
    # repo check alone passes. That profile is then (a) NOT covered by the
    # ".pytest_profile/" .gitignore entry, so it can be committed, and (b) invisible to
    # every marker-based guard: tests/containment/test_positive_control.py gates on
    # ".pytest_profile" in Path.home().parts and would SILENTLY SKIP the entire positive
    # control while the suite still reported green. Require the marker.
    # The marker region is taken LITERALLY, never resolved. Resolving both sides would
    # let the boundary move: a .pytest_profile symlink pointing at another in-repo
    # directory resolves to that directory on BOTH sides, so every check passes while the
    # launcher writes outside the region .gitignore actually ignores.
    marker_root = repo_root / PROFILE_MARKER
    if marker_root.is_symlink():
        _fail(
            "profile-under-marker",
            f"{marker_root} is a symlink to {os.readlink(marker_root)!r}. The marker "
            "region defines the containment boundary and the .gitignore entry that covers "
            "it; it must be a real directory, not an indirection.",
        )
    if not _is_inside(marker_root, profile_root):
        _fail(
            "profile-under-marker",
            f"{profile_root} is inside the repo but escapes {marker_root}; session id "
            f"{args.session_id!r} traverses out of the {PROFILE_MARKER} region",
        )
    _ok("profile-under-marker", f"{profile_root} is under {marker_root}")

    home = Path(args.home).resolve()
    if not _is_inside(repo_root, home):
        _fail("home-contained", f"HOME {home} not under repo {repo_root}")
    # Repo containment alone is not enough for HOME either: an existing session-home
    # symlink pointing at another in-repo directory satisfies it while placing the
    # measured region outside the ignored marker region.
    if not _is_inside(marker_root, home):
        _fail(
            "home-contained",
            f"HOME {home} is inside the repo but escapes the {PROFILE_MARKER} region "
            f"{marker_root}; it resolves outside the disposable, ignored profile area",
        )
    if args.original_home:
        original = Path(args.original_home).expanduser().resolve()
        if home == original:
            _fail("home-not-real", f"HOME still resolves to the real profile {original}")
    _ok("home-contained", f"HOME {home} is contained and distinct from the real profile")

    # --- effective pytest CONFIG must be the repo's own (R2 finding 2) --------
    # pytest discovers its config from the invocation CWD and from test-path ancestors
    # (_pytest/config/findpaths.py). The launcher execs in the caller's CWD, so running
    # it from ANOTHER project would have pytest load THAT project's config, whose addopts
    # this preflight never scanned, while the preflight approved the scrappy root config.
    # Two things close that: this check, and the launcher PINNING -c to the validated
    # config file at exec (STEP E), which stops discovery entirely.
    cwd = Path.cwd().resolve()
    if not _is_inside(repo_root, cwd):
        _fail(
            "cwd-contained",
            f"invoked from {cwd}, outside the repository {repo_root}. pytest would "
            "discover configuration from there, and this preflight validates only the "
            "repository's own config. Run the launcher from inside the repository.",
        )
    _ok("cwd-contained", f"invocation cwd {cwd} is inside the repo")

    pinned_config = _pinned_config_file(repo_root)
    if pinned_config is None:
        _fail(
            "config-pinned",
            f"no pytest.ini or pyproject.toml at {repo_root} to pin. Without a pinned "
            "config pytest would discover one, and an undiscovered config's addopts "
            "cannot be validated. Refusing rather than running unpinned.",
        )
    _ok("config-pinned", f"launcher will pin -c {pinned_config}")

    # --- N2: effective --basetemp across argv, PYTEST_ADDOPTS, pyproject -------
    argv_tokens = list(args.pytest_args)
    addopts_env = shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))
    config_tokens, config_source = _config_addopts_tokens(repo_root)
    # Tokens injected via -o/--override-ini addopts=..., from EVERY channel that can
    # carry such an override. These are effective pytest arguments and must be validated
    # exactly like literal argv (finding scrappy-9f74).
    override_tokens = (
        _override_addopts_tokens(argv_tokens)
        + _override_addopts_tokens(addopts_env)
        + _override_addopts_tokens(config_tokens)
    )
    effective_tokens = argv_tokens + addopts_env + config_tokens + override_tokens

    # FAIL CLOSED on ARGPARSE RESPONSE FILES, ACROSS EVERY EFFECTIVE CHANNEL.
    # _pytest/config/argparsing.py:463 sets fromfile_prefix_chars="@", so a token like
    # @args.txt is expanded BY PYTEST into arbitrary further arguments, recursively.
    # Nothing scanned here would see a --basetemp or a -c inside it.
    #
    # CHECKING ONLY LITERAL ARGV IS NOT ENOUGH: `-o 'addopts=@args.txt'` contains no
    # token beginning with @ and names no --basetemp, yet pytest applies the override,
    # prepends the resulting addopts, and expands the response file. The refusal
    # therefore runs over argv, PYTEST_ADDOPTS, the repository config addopts, AND the
    # tokens extracted from every ini override.
    # FAIL CLOSED on short-option CLUSTERS before anything is scanned: a cluster can
    # carry -o, -c or a response file past every scanner below (finding scrappy-tnyy).
    clusters = _unmodelled_short_clusters(effective_tokens)
    if clusters:
        _fail(
            "no-short-clusters",
            f"clustered or attached short option(s) {clusters} supplied. argparse accepts "
            "these, so a cluster can carry -o, -c or an @response-file past every check "
            "here. This preflight models only -o/-c with attached values. Pass short "
            "options separately, for example '-x -v -s' rather than '-xvs' and "
            "'-k expr' rather than '-kexpr'.",
        )
    _ok("no-short-clusters", "no unmodelled short-option cluster in any argument channel")

    response_files = [token for token in effective_tokens if token.startswith("@")]
    if response_files:
        _fail(
            "no-response-files",
            f"argparse response file(s) {response_files} reachable from argv, "
            "PYTEST_ADDOPTS, the repository config addopts or an -o addopts override. "
            "pytest expands these recursively into arbitrary arguments, including "
            "--basetemp and -c, none of which this preflight can see. Pass arguments "
            "directly instead.",
        )
    _ok("no-response-files", "no @response-file token in any effective argument channel")

    # FAIL CLOSED on an alternate config file. -c selects a config this preflight has
    # not scanned, so its addopts (and any --basetemp inside them) are UNKNOWN. An
    # unscanned channel must refuse, never approve by silence (finding scrappy-f7l7).
    alternate_configs = _scan_valued_flag(effective_tokens, "--config-file", "-c")
    if alternate_configs:
        _fail(
            "basetemp-contained",
            f"alternate pytest config {alternate_configs} selected via -c/--config-file; "
            "its addopts are not scanned by this preflight, so containment cannot be "
            "established. Refusing rather than approving an unexamined channel.",
        )

    found = _scan_basetemp(effective_tokens)
    if found:
        for raw in found:
            resolved = (Path.cwd() / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            if not _is_inside(repo_root, resolved):
                _fail("basetemp-contained", f"--basetemp={raw!r} resolves to {resolved}, outside repo")
        _ok("basetemp-contained", f"effective --basetemp value(s) {found} resolve inside repo")
    else:
        _ok(
            "basetemp-contained",
            f"no effective --basetemp in argv/PYTEST_ADDOPTS/-o addopts/{config_source}",
        )

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
