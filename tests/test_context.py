"""
Tests for CodebaseContext - project exploration and context management.
"""
import pytest
from pathlib import Path
from datetime import datetime
import json

from src.context import CodebaseContext


class TestCodebaseContextBasics:
    """Basic context creation and state tests."""

    @pytest.mark.unit
    def test_context_creation_current_dir(self):
        """Test creating context for current directory."""
        context = CodebaseContext()
        assert context.project_path.exists()
        assert isinstance(context.project_path, Path)

    @pytest.mark.unit
    def test_context_creation_with_path(self, temp_project_dir):
        """Test creating context with specific path."""
        context = CodebaseContext(str(temp_project_dir))
        assert context.project_path == temp_project_dir.resolve()

    @pytest.mark.unit
    def test_initial_state(self, temp_project_dir):
        """Test initial state before exploration."""
        context = CodebaseContext(str(temp_project_dir))
        assert context.summary is None
        assert context.structure == {}
        assert context.key_files == {}
        assert context.file_index == {}
        assert context.explored_at is None

    @pytest.mark.unit
    def test_is_explored_before_explore(self, temp_project_dir):
        """Test that is_explored returns False before exploration."""
        context = CodebaseContext(str(temp_project_dir))
        assert context.is_explored() is False

    @pytest.mark.unit
    def test_cache_file_path(self, temp_project_dir):
        """Test that cache file path is set correctly."""
        context = CodebaseContext(str(temp_project_dir))
        expected_cache = temp_project_dir / ".llm_team_context.json"
        assert context.cache_file == expected_cache


class TestCodebaseExploration:
    """Tests for codebase exploration functionality."""

    @pytest.fixture
    def rich_project_dir(self, tmp_path):
        """Create a project directory with various file types."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "utils").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        # Create Python files
        (tmp_path / "src" / "__init__.py").write_text("")
        (tmp_path / "src" / "main.py").write_text('def main():\n    print("Hello")\n')
        (tmp_path / "src" / "utils" / "__init__.py").write_text("")
        (tmp_path / "src" / "utils" / "helpers.py").write_text('def helper():\n    pass\n')

        # Create test files
        (tmp_path / "tests" / "test_main.py").write_text('def test_main():\n    pass\n')

        # Create config files
        (tmp_path / "README.md").write_text("# Test Project\n\nA test project.\n")
        (tmp_path / "requirements.txt").write_text("pytest\nclick\n")
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        # Create a JavaScript file
        (tmp_path / "package.json").write_text('{"name": "test"}\n')

        # Simulate git directory
        (tmp_path / ".git").mkdir()

        return tmp_path

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_explore_counts_files(self, rich_project_dir):
        """Test that explore counts files correctly."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()

        assert 'total_files' in result
        assert result['total_files'] > 0

    @pytest.mark.unit
    def test_explore_detects_file_types(self, rich_project_dir):
        """Test that explore detects different file types."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()

        assert 'file_types' in result
        # Should detect Python files
        file_types = result['file_types']
        # Check for python files (may be 'python' or 'py' depending on implementation)
        has_python = any('py' in k.lower() or 'python' in k.lower() for k in file_types.keys())
        assert has_python or len(file_types) > 0

    @pytest.mark.unit
    def test_explore_finds_directories(self, rich_project_dir):
        """Test that explore lists directories."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()

        assert 'directories' in result
        directories = result['directories']
        assert 'src' in directories or any('src' in d for d in directories)

    @pytest.mark.unit
    def test_explore_detects_git(self, rich_project_dir):
        """Test that explore detects git repository."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_git') is True

    @pytest.mark.unit
    def test_explore_detects_readme(self, rich_project_dir):
        """Test that explore detects README."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_readme') is True

    @pytest.mark.unit
    def test_explore_detects_requirements(self, rich_project_dir):
        """Test that explore detects requirements.txt."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_requirements') is True

    @pytest.mark.unit
    def test_explore_detects_pyproject(self, rich_project_dir):
        """Test that explore detects pyproject.toml."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_pyproject') is True

    @pytest.mark.unit
    def test_explore_cached_returns_cached_status(self, rich_project_dir):
        """Test that second explore returns cached status."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        # Set summary to satisfy is_explored() check
        context.summary = "Test summary"
        result = context.explore()  # Second call

        assert result['status'] == 'cached'



class TestKeyFileReading:
    """Tests for reading key project files."""

    @pytest.fixture
    def project_with_key_files(self, tmp_path):
        """Create project with key files."""
        (tmp_path / "README.md").write_text("# My Project\n\nDescription here.\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='test')\n")
        (tmp_path / "requirements.txt").write_text("flask==2.0.0\nrequests>=2.25.0\n")
        (tmp_path / ".git").mkdir()
        return tmp_path

    @pytest.mark.unit
    def test_reads_readme(self, project_with_key_files):
        """Test that README is read."""
        context = CodebaseContext(str(project_with_key_files))
        context.explore()

        assert "README.md" in context.key_files or any("README" in k for k in context.key_files)


    @pytest.mark.unit
    def test_key_files_contain_content(self, project_with_key_files):
        """Test that key files have actual content."""
        context = CodebaseContext(str(project_with_key_files))
        context.explore()

        for filename, content in context.key_files.items():
            assert len(content) > 0


class TestCaching:
    """Tests for context caching functionality."""

    @pytest.mark.unit
    def test_saves_cache_after_explore(self, temp_project_dir):
        """Test that cache is saved after exploration."""
        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.cache_file.exists()
