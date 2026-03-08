"""Tests for pytest temp directory configuration."""

import os
import tempfile
from pathlib import Path

from tests.conftest import _configure_test_temp_dirs, _get_session_temp_root


def test_get_session_temp_root_defaults_to_repo_local(monkeypatch):
    """Default temp root should live under the repo."""
    monkeypatch.delenv("SCRAPPY_TEST_TEMP", raising=False)
    monkeypatch.setenv("SCRAPPY_TEST_SESSION_ID", "run-test")

    root = _get_session_temp_root(Path("/repo"))

    assert root == Path("/repo/.pytest_tmp/run-test")


def test_get_session_temp_root_honors_env_override(monkeypatch):
    """Env override should take precedence for test temp roots."""
    monkeypatch.setenv("SCRAPPY_TEST_TEMP", "C:/custom-temp")
    monkeypatch.setenv("SCRAPPY_TEST_SESSION_ID", "run-test")

    root = _get_session_temp_root(Path("/repo"))

    assert root == Path("C:/custom-temp/run-test")


def test_configure_test_temp_dirs_sets_tempfile_root(tmp_path, monkeypatch):
    """tempfile and env vars should point at the repo-local temp area."""
    monkeypatch.delenv("SCRAPPY_TEST_TEMP", raising=False)
    monkeypatch.setenv("SCRAPPY_TEST_SESSION_ID", "run-test")

    pytest_temp, system_temp = _configure_test_temp_dirs(tmp_path)

    assert pytest_temp == (tmp_path / ".pytest_tmp" / "run-test" / "pytest").resolve()
    assert system_temp == (tmp_path / ".pytest_tmp" / "run-test" / "system").resolve()
    assert Path(os.environ["TEMP"]) == system_temp
    assert Path(os.environ["TMP"]) == system_temp
    assert Path(os.environ["TMPDIR"]) == system_temp
    assert Path(tempfile.gettempdir()) == system_temp
