"""Tests for dependency checking utilities."""

from unittest.mock import patch

from scrappy.cli.utils.dependency_check import (
    check_git,
    check_rg,
    check_pytest,
    check_agent_dependencies,
    check_optional_dependencies,
)


class TestCheckGit:
    """Tests for check_git function."""

    def test_git_available(self):
        """Returns available=True when git is found."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            result = check_git()
            assert result.available is True
            assert result.path == "/usr/bin/git"
            assert result.error is None

    def test_git_not_available(self):
        """Returns available=False with error when git not found."""
        with patch("shutil.which", return_value=None):
            result = check_git()
            assert result.available is False
            assert result.path is None
            assert "git not found" in result.error


class TestCheckRg:
    """Tests for check_rg function."""

    def test_rg_available(self):
        """Returns available=True when ripgrep is found."""
        with patch("shutil.which", return_value="/usr/bin/rg"):
            result = check_rg()
            assert result.available is True
            assert result.path == "/usr/bin/rg"
            assert result.error is None

    def test_rg_not_available(self):
        """Returns available=False with error when ripgrep not found."""
        with patch("shutil.which", return_value=None):
            result = check_rg()
            assert result.available is False
            assert result.path is None
            assert "ripgrep" in result.error
            assert "rg" in result.error


class TestCheckPytest:
    """Tests for check_pytest function."""

    def test_pytest_available(self):
        """Returns available=True when pytest is found."""
        with patch("shutil.which", return_value="/usr/bin/pytest"):
            result = check_pytest()
            assert result.available is True
            assert result.path == "/usr/bin/pytest"

    def test_pytest_not_available_but_python_is(self):
        """Returns available=True with python -m pytest when pytest not found."""
        def mock_which(cmd):
            if cmd == "pytest":
                return None
            if cmd == "python":
                return "/usr/bin/python"
            return None

        with patch("shutil.which", side_effect=mock_which):
            result = check_pytest()
            assert result.available is True
            assert "python" in result.path
            assert "-m pytest" in result.path

    def test_pytest_and_python_not_available(self):
        """Returns available=False when neither pytest nor python found."""
        with patch("shutil.which", return_value=None):
            result = check_pytest()
            assert result.available is False
            assert "pytest not found" in result.error


class TestCheckAgentDependencies:
    """Tests for check_agent_dependencies function."""

    def test_all_deps_available(self):
        """Returns (True, []) when all required deps available."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            ok, errors = check_agent_dependencies()
            assert ok is True
            assert errors == []

    def test_git_missing(self):
        """Returns (False, [error]) when git missing."""
        with patch("shutil.which", return_value=None):
            ok, errors = check_agent_dependencies()
            assert ok is False
            assert len(errors) == 1
            assert "git" in errors[0]


class TestCheckOptionalDependencies:
    """Tests for check_optional_dependencies function."""

    def test_all_optional_deps_available(self):
        """Returns empty list when all optional deps available."""
        with patch("shutil.which", return_value="/usr/bin/rg"):
            warnings = check_optional_dependencies()
            assert warnings == []

    def test_rg_missing(self):
        """Returns warning when ripgrep missing."""
        with patch("shutil.which", return_value=None):
            warnings = check_optional_dependencies()
            assert len(warnings) == 1
            assert "ripgrep" in warnings[0]
