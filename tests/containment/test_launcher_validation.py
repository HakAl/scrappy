"""Committed regression tests for the launcher's FAIL-CLOSED PREFLIGHT.

Until now the preflight's refusals existed only as architect-seat probes run by hand,
so nothing in the tree would notice if a refusal silently stopped refusing. These tests
invoke scripts/_contained_pytest_preflight.py as a SUBPROCESS with crafted arguments and
assert the exit status and the named check.

This is safe to run anywhere: the preflight imports only the standard library plus
python-dotenv, never imports scrappy, never starts pytest, and creates no directories
(the launcher creates the profile tree only AFTER the preflight returns 0).

Covered refusals:
  - profile-under-marker: a session id that traverses OUT of .pytest_profile/ while
    still resolving inside the repo (found during PR-1 final verification; the repo
    containment check alone accepted it).
  - basetemp-contained via the -o/--override-ini addopts channel and the -c alternate
    config channel (finding scrappy-f7l7).
  - the S-13 inherited-input and home-not-real refusals.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPO_ROOT / "scripts" / "_contained_pytest_preflight.py"

# Deliberately NOT the system scratch directory: the property under test is "outside the
# repository root", and a path that cannot exist makes that unambiguous.
OUTSIDE_ROOT = "/nonexistent-outside-root/escape"

PREFLIGHT_FAIL_RC = 11


def run_preflight(
    *,
    session_id: str = "unit-probe",
    profile_root: str | None = None,
    home: str | None = None,
    original_home: str = "/nonexistent-real-home",
    inherited_test_temp: str = "",
    inherited_session_id: str = "",
    pytest_args: tuple[str, ...] = (),
    env_addopts: str | None = None,
    repo_root: Path | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the preflight exactly as scripts/contained-pytest.sh does."""
    repo = repo_root or REPO_ROOT
    root = profile_root if profile_root is not None else f"{repo}/.pytest_profile/{session_id}"
    env = {"PATH": "/usr/bin:/bin", "HOME": original_home}
    if env_addopts is not None:
        env["PYTEST_ADDOPTS"] = env_addopts
    return subprocess.run(
        [
            sys.executable,
            str(PREFLIGHT),
            "--repo-root", str(repo),
            "--profile-root", root,
            "--home", home if home is not None else f"{root}/home",
            "--original-home", original_home,
            "--session-id", session_id,
            "--inherited-test-temp", inherited_test_temp,
            "--inherited-session-id", inherited_session_id,
            "--dotenv-floor", "1.2.0",
            "--", *pytest_args,
        ],
        cwd=str(cwd or repo),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def assert_refused(proc: subprocess.CompletedProcess[str], check: str) -> None:
    assert proc.returncode == PREFLIGHT_FAIL_RC, (
        f"expected fail-closed rc={PREFLIGHT_FAIL_RC}, got {proc.returncode}\n{proc.stderr}"
    )
    assert f"FAIL {check}" in proc.stderr, proc.stderr


def test_a_legitimate_invocation_passes():
    """The gate is not vacuous: an ordinary session id is ACCEPTED."""
    proc = run_preflight()
    assert proc.returncode == 0, proc.stderr
    assert "all checks passed" in proc.stderr


# ---------------------------------------------------------------------------
# profile-under-marker: in-repo is NOT enough.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("session_id", ["../escape", "sub/../../escape", "./../escape"])
def test_session_id_traversing_out_of_the_marker_region_is_refused(session_id):
    """A session id may not leave .pytest_profile/, even staying inside the repo.

    Such a profile is not covered by the ".pytest_profile/" gitignore entry and is
    invisible to every marker-based guard, including the positive control's own
    CONTAINED gate, which would silently skip while the suite still reported green.
    """
    proc = run_preflight(session_id=session_id)
    assert_refused(proc, "profile-under-marker")


def test_absolute_session_id_is_refused():
    proc = run_preflight(session_id="/etc/escape")
    assert proc.returncode == PREFLIGHT_FAIL_RC, proc.stderr


def test_profile_root_outside_the_repo_is_refused():
    """Refused at S13-chosen-session-id, which is reached FIRST.

    The launcher derives its scratch base from the profile root, so an outside-repo
    profile root escapes the S-13 model before the profile-under-repo check is reached.
    Asserting the check that actually fires rather than the one that reads most obviously,
    because a test that names the wrong mechanism stops being evidence about the
    mechanism. What matters is that it fails CLOSED, and it does.
    """
    proc = run_preflight(profile_root=OUTSIDE_ROOT)
    assert_refused(proc, "S13-chosen-session-id")
    assert OUTSIDE_ROOT in proc.stderr


# ---------------------------------------------------------------------------
# basetemp: every channel that can reach pytest must be scanned or refused.
# ---------------------------------------------------------------------------


def test_outside_root_basetemp_in_argv_is_refused():
    proc = run_preflight(pytest_args=("--basetemp", OUTSIDE_ROOT))
    assert_refused(proc, "basetemp-contained")


@pytest.mark.parametrize(
    "tokens",
    [
        ("-o", f"addopts=--basetemp={OUTSIDE_ROOT}"),
        (f"--override-ini=addopts=--basetemp={OUTSIDE_ROOT}",),
        ("--override-ini", f"addopts=--basetemp={OUTSIDE_ROOT}"),
        (f"-oaddopts=--basetemp={OUTSIDE_ROOT}",),
    ],
)
def test_basetemp_hidden_in_an_ini_override_is_refused(tokens):
    """scrappy-f7l7: the token begins "addopts=", not "--basetemp=".

    pytest reads override_ini and prepends the effective addopts, so this reaches the
    same place a config file would. Scanning only for "--basetemp" missed it entirely.
    """
    proc = run_preflight(pytest_args=tokens)
    assert_refused(proc, "basetemp-contained")


def test_basetemp_override_via_the_environment_channel_is_refused():
    proc = run_preflight(env_addopts=f"-o addopts=--basetemp={OUTSIDE_ROOT}")
    assert_refused(proc, "basetemp-contained")


@pytest.mark.parametrize("tokens", [("-c", "alternate.ini"), ("--config-file=alternate.ini",)])
def test_an_unscanned_alternate_config_fails_closed(tokens):
    """An UNSCANNED channel must refuse, never approve by silence."""
    proc = run_preflight(pytest_args=tokens)
    assert_refused(proc, "basetemp-contained")
    assert "not scanned by this preflight" in proc.stderr


def test_an_in_repo_basetemp_override_is_accepted():
    """The override scanner refuses ESCAPES, not the channel itself."""
    inside = f"{REPO_ROOT}/.pytest_profile/unit-probe/scratch"
    proc = run_preflight(pytest_args=("-o", f"addopts=--basetemp={inside}"))
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# S-13 inherited inputs and the real-HOME identity check.
# ---------------------------------------------------------------------------


def test_inherited_test_temp_outside_the_repo_is_refused():
    proc = run_preflight(inherited_test_temp=OUTSIDE_ROOT, inherited_session_id="sid")
    assert_refused(proc, "S13-inherited-temp")


def test_contained_home_equal_to_the_real_home_is_refused():
    """The exact refusal behind scrappy-jxh4: rc=11, and pytest never starts."""
    home = f"{REPO_ROOT}/.pytest_profile/unit-probe/home"
    proc = run_preflight(home=home, original_home=home)
    assert_refused(proc, "home-not-real")


# ---------------------------------------------------------------------------
# The containment boundary must not be movable by a symlink, and the effective
# pytest config must be the repository's own. Both found in review round 2.
# ---------------------------------------------------------------------------


def synthetic_repo(tmp_path: Path) -> Path:
    """A minimal repository root: a pytest config, and nothing else."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    return repo


def test_a_synthetic_repo_is_accepted(tmp_path):
    """Baseline for the symlink tests below: this shape passes when nothing is a symlink."""
    repo = synthetic_repo(tmp_path)
    (repo / ".pytest_profile").mkdir()
    proc = run_preflight(repo_root=repo)
    assert proc.returncode == 0, proc.stderr


def test_a_symlinked_marker_directory_is_refused(tmp_path):
    """The marker region defines the boundary AND the .gitignore entry that covers it.

    Resolving both sides of the containment check would let a ``.pytest_profile`` symlink
    move the boundary: the profile resolves under the symlink target on both sides, every
    check passes, and the launcher writes into a directory git does not ignore.
    """
    repo = synthetic_repo(tmp_path)
    (repo / "profile-data").mkdir()
    (repo / ".pytest_profile").symlink_to(repo / "profile-data")

    proc = run_preflight(repo_root=repo)
    assert_refused(proc, "profile-under-marker")
    assert "symlink" in proc.stderr


def test_a_session_home_symlinked_out_of_the_marker_region_is_refused(tmp_path):
    """HOME must stay in the ignored marker region, not merely inside the repo."""
    repo = synthetic_repo(tmp_path)
    session = repo / ".pytest_profile" / "unit-probe"
    session.mkdir(parents=True)
    (repo / "elsewhere").mkdir()
    (session / "home").symlink_to(repo / "elsewhere")

    proc = run_preflight(repo_root=repo)
    assert_refused(proc, "home-contained")


def test_a_symlinked_session_directory_is_refused(tmp_path):
    """The session directory itself may not redirect the profile out of the region."""
    repo = synthetic_repo(tmp_path)
    (repo / ".pytest_profile").mkdir()
    (repo / "elsewhere").mkdir()
    (repo / ".pytest_profile" / "unit-probe").symlink_to(repo / "elsewhere")

    proc = run_preflight(repo_root=repo)
    assert_refused(proc, "profile-under-marker")


def test_invocation_from_outside_the_repository_is_refused(tmp_path):
    """pytest discovers config from the invocation CWD.

    Launching from another project would have pytest load THAT project's config, whose
    addopts this preflight never scanned, while the preflight approved the repository's
    own. _pytest/tmpdir.py removes and recreates whatever basetemp it ends up with.
    """
    repo = synthetic_repo(tmp_path)
    (repo / ".pytest_profile").mkdir()
    outside = tmp_path / "another-project"
    outside.mkdir()

    proc = run_preflight(repo_root=repo, cwd=outside)
    assert_refused(proc, "cwd-contained")


def test_a_repository_with_no_pytest_config_to_pin_is_refused(tmp_path):
    """Without a config to pin, pytest would discover one that was never validated."""
    repo = tmp_path / "repo"
    (repo / ".pytest_profile").mkdir(parents=True)

    proc = run_preflight(repo_root=repo)
    assert_refused(proc, "config-pinned")


@pytest.mark.parametrize("subdir", ["plain", "dir with spaces"])
def test_the_launcher_execs_pytest_with_the_pinned_config(tmp_path, subdir):
    """BEHAVIOURAL: capture the argv the launcher actually execs pytest with.

    A source-string assertion would stay green if someone reintroduced an unpinned exec
    beside this one, and would break on harmless reformatting. So the launcher is copied
    into a synthetic repository whose ``.venv/bin/python`` is a stub: the stub delegates
    to the real interpreter for the preflight, and for the ``-m pytest`` invocation it
    RECORDS ITS ARGV and exits without starting pytest.
    """
    parent = tmp_path / subdir
    parent.mkdir()
    repo = synthetic_repo(parent)
    (repo / ".pytest_profile").mkdir()
    (repo / "scripts").mkdir()

    # A spaced INTERPRETER path too, so both shlex.quote'd words are exercised. A
    # WRAPPER rather than a symlink: a symlinked interpreter has no pyvenv.cfg beside it,
    # so it would lose the virtualenv and fail to import python-dotenv for reasons that
    # have nothing to do with quoting.
    interpreter = sys.executable
    if " " in subdir:
        spaced_bin = parent / "interpreter dir"
        spaced_bin.mkdir()
        wrapper = spaced_bin / "py wrapper"
        wrapper.write_text(
            f'#!/bin/bash\nexec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8"
        )
        wrapper.chmod(0o755)
        interpreter = str(wrapper)
    for name in ("contained-pytest.sh", "_contained_pytest_preflight.py"):
        shutil.copy(REPO_ROOT / "scripts" / name, repo / "scripts" / name)

    recorded = repo / "exec-argv.txt"
    stub_dir = repo / ".venv" / "bin"
    stub_dir.mkdir(parents=True)
    stub = stub_dir / "python"
    stub.write_text(
        "#!/bin/bash\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "pytest" ]; then\n'
        f'    printf "%s\\n" "$@" > {shlex.quote(str(recorded))}\n'
        "    exit 0\n"
        "  fi\n"
        "done\n"
        f'exec {shlex.quote(interpreter)} "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)

    proc = subprocess.run(
        [str(repo / "scripts" / "contained-pytest.sh"), "tests/some_test.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent-real-home"},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    argv = recorded.read_text(encoding="utf-8").split("\n")

    assert "-m" in argv and "pytest" in argv
    assert "-c" in argv, f"launcher must pin the config file; argv was {argv}"
    assert argv[argv.index("-c") + 1] == str(repo / "pytest.ini")
    # The caller's own arguments are still forwarded.
    assert "tests/some_test.py" in argv


# ---------------------------------------------------------------------------
# ARGPARSE RESPONSE FILES. _pytest/config/argparsing.py:463 sets
# fromfile_prefix_chars="@", so @file expands recursively into arbitrary arguments.
# Round 4 review found that checking only literal argv left the -o addopts channel
# open, and that the tests for this were claimed but never written. Both fixed here.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tokens",
    [
        ("@args.txt",),
        ("tests/some_test.py", "@args.txt"),
        ("-o", "addopts=@args.txt"),
        ("--override-ini=addopts=@args.txt"),
        ("-o", "addopts=--basetemp=x @nested.txt"),
    ],
)
def test_response_files_are_refused_in_argv(tokens):
    """Direct, positional, and ini-override forms all reach pytest's @ expansion."""
    proc = run_preflight(pytest_args=tuple(tokens) if isinstance(tokens, tuple) else (tokens,))
    assert_refused(proc, "no-response-files")


def test_response_files_are_refused_in_the_environment_channel():
    proc = run_preflight(env_addopts="-o addopts=@args.txt")
    assert_refused(proc, "no-response-files")


def test_a_bare_response_file_in_the_environment_channel_is_refused():
    proc = run_preflight(env_addopts="@args.txt")
    assert_refused(proc, "no-response-files")


def test_a_response_file_in_the_repository_config_addopts_is_refused(tmp_path):
    """The repository's OWN config addopts are an effective channel too."""
    repo = tmp_path / "repo"
    (repo / ".pytest_profile").mkdir(parents=True)
    (repo / "pytest.ini").write_text("[pytest]\naddopts = @args.txt\n", encoding="utf-8")

    proc = run_preflight(repo_root=repo)
    assert_refused(proc, "no-response-files")


def test_a_basetemp_hidden_behind_an_override_response_file_is_refused(tmp_path):
    """The exact R4-1 scenario, end to end.

    ``-o 'addopts=@args.txt'`` contains no token beginning with @ and names no
    --basetemp, so a scan of literal argv approves it. pytest applies the override,
    prepends the resulting addopts, and expands the response file, at which point
    _pytest/tmpdir.py removes and recreates whatever basetemp it finds.
    """
    args_file = tmp_path / "args.txt"
    args_file.write_text(f"--basetemp={OUTSIDE_ROOT}\n", encoding="utf-8")

    proc = run_preflight(pytest_args=("-o", f"addopts=@{args_file}"))
    assert_refused(proc, "no-response-files")


def test_an_ordinary_at_sign_inside_a_value_is_not_refused():
    """Only a token that STARTS with @ triggers pytest expansion; refuse no more."""
    proc = run_preflight(pytest_args=("-k", "test_email@example"))
    assert proc.returncode == 0, proc.stderr




@pytest.mark.parametrize(
    "token",
    [
        "-o=addopts=@args.txt",
        "-oaddopts=@args.txt",
        "--override-ini=addopts=@args.txt",
    ],
)
def test_short_option_equals_syntax_cannot_hide_a_response_file(token):
    """scrappy-wwm9: argparse strips the separator in ``-o=value``.

    The scanner previously returned the raw remainder ``=addopts=@args.txt``, whose ini
    name partitions to empty, so the override was discarded as unparseable and the
    response file behind it was invisible to every later check.
    """
    proc = run_preflight(pytest_args=(token,))
    assert_refused(proc, "no-response-files")


@pytest.mark.parametrize(
    "token",
    [
        f"-o=addopts=--basetemp={OUTSIDE_ROOT}",
        f"-oaddopts=--basetemp={OUTSIDE_ROOT}",
    ],
)
def test_short_option_equals_syntax_cannot_hide_a_basetemp(token):
    proc = run_preflight(pytest_args=(token,))
    assert_refused(proc, "basetemp-contained")


def test_short_option_equals_syntax_is_scanned_in_the_environment_channel():
    proc = run_preflight(env_addopts=f"-o=addopts=--basetemp={OUTSIDE_ROOT}")
    assert_refused(proc, "basetemp-contained")


def test_short_option_equals_syntax_cannot_hide_an_alternate_config():
    proc = run_preflight(pytest_args=("-c=alternate.ini",))
    assert_refused(proc, "basetemp-contained")
    assert "not scanned by this preflight" in proc.stderr


# ---------------------------------------------------------------------------
# ARGPARSE SHORT-OPTION CLUSTERS (scrappy-tnyy).
# argparse, which pytest subclasses without changing cluster parsing, accepts
# "-voaddopts=..." as -v followed by -o with a value. A scanner looking for tokens
# beginning "-o" never sees it, so -o, -c and @response-files can all ride through a
# cluster. The preflight refuses unmodelled clusters rather than reimplementing the
# grammar; these tests pin both the refusal and its limits.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tokens",
    [
        ("-voaddopts=@args.txt",),
        ("-qvoaddopts=@args.txt",),
        ("-vo", "addopts=--basetemp=/nonexistent-outside-root/escape"),
        ("-vcalt.ini",),
        ("-xvs",),
        ("-kcolor",),
    ],
)
def test_unmodelled_short_option_clusters_are_refused(tokens):
    """Fail closed on any short cluster the scanner does not model.

    The last two cases are ORDINARY pytest usage and are refused too. That is the
    deliberate cost of not modelling the grammar: the refusal message tells the caller to
    pass them separately. Asserted here so the cost is visible and cannot regress
    silently into a permissive parse.
    """
    proc = run_preflight(pytest_args=tokens)
    assert_refused(proc, "no-short-clusters")
    assert "Pass short options separately" in proc.stderr


def test_short_option_clusters_are_refused_in_the_environment_channel():
    proc = run_preflight(env_addopts="-voaddopts=@args.txt")
    assert_refused(proc, "no-short-clusters")


@pytest.mark.parametrize("tokens", [("-v",), ("-q",), ("-x", "-v", "-s"), ("-p", "no:randomly")])
def test_unclustered_short_options_are_accepted(tokens):
    """The refusal must not swallow ordinary separated flags."""
    proc = run_preflight(pytest_args=tokens)
    assert proc.returncode == 0, proc.stderr


def test_the_repository_config_addopts_do_not_trip_the_cluster_refusal():
    """The repo's own pytest.ini addopts are an effective channel and must stay valid."""
    proc = run_preflight()
    assert proc.returncode == 0, proc.stderr
    assert "ok   no-short-clusters" in proc.stderr


@pytest.mark.parametrize("flag_short,flag_long,dest", [("-o", "--override-ini", "append"), ("-c", "--config-file", "store")])
@pytest.mark.parametrize(
    "shape",
    ["long_separated", "long_equals", "short_separated", "short_attached", "short_equals"],
)
@pytest.mark.parametrize("value", ["addopts=x", "", "a=b=c", "-leading-dash", "with space"])
def test_the_scanner_matches_argparse_on_the_modelled_forms(flag_short, flag_long, dest, shape, value):
    """DIFFERENTIAL, across BOTH modelled flags and ALL FIVE documented shapes.

    Deliberately scoped to the forms _scan_valued_flag claims to support, including
    boundary values (empty, embedded separators, a leading dash, a space). Forms outside
    that contract are not compared here because they are REFUSED before any scan runs;
    test_unmodelled_short_option_clusters_are_refused covers those. Between the two there
    is no accepted form whose value this scanner reads differently from argparse.
    """
    import argparse
    import importlib.util

    if value.startswith("-") and shape in {"long_separated", "short_separated"}:
        pytest.skip(
            "argparse REJECTS a separated value beginning with '-' as a usage error, so "
            "pytest never starts and there is no accepted form to compare against"
        )

    if shape == "long_separated":
        tokens = [flag_long, value]
    elif shape == "long_equals":
        tokens = [f"{flag_long}={value}"]
    elif shape == "short_separated":
        tokens = [flag_short, value]
    elif shape == "short_attached":
        if not value:
            pytest.skip("an attached short option cannot carry an empty value")
        tokens = [f"{flag_short}{value}"]
    else:
        tokens = [f"{flag_short}={value}"]

    parser = argparse.ArgumentParser(allow_abbrev=False, add_help=False)
    parser.add_argument(flag_short, flag_long, action="append" if dest == "append" else None)
    known, _ = parser.parse_known_args(tokens)
    expected = getattr(known, flag_long.lstrip("-").replace("-", "_"))
    expected_values = expected if isinstance(expected, list) else ([expected] if expected is not None else [])

    spec = importlib.util.spec_from_file_location("preflight_under_test", PREFLIGHT)
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)

    assert preflight._scan_valued_flag(tokens, flag_long, flag_short) == expected_values, tokens
