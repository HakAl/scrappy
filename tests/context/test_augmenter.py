"""
Tests for ContextAugmenter - prompt augmentation with codebase context.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock

from scrappy.context.augmenter import ContextAugmenter, NullContextAugmenter


@pytest.fixture
def test_path():
    """Create a test path that exists."""
    # Use the project root as a test path that definitely exists
    return Path(__file__).parent.parent.parent


class MockSemanticManager:
    """Mock semantic search manager for testing."""

    def __init__(self, search_result=None):
        self._search_result = search_result

    def search(self, query, max_tokens=4000):
        return self._search_result

    def is_ready(self):
        return self._search_result is not None


class TestContextAugmenterCreation:
    """Tests for ContextAugmenter creation."""

    @pytest.mark.unit
    def test_creation_with_providers(self, test_path):
        """Test creating augmenter with all providers."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: "Test summary",
            structure_provider=lambda: {"total_files": 10},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
        )
        assert augmenter is not None

    @pytest.mark.unit
    def test_creation_with_semantic_manager(self, test_path):
        """Test creating augmenter with semantic manager."""
        manager = MockSemanticManager()
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
            semantic_manager=manager,
        )
        assert augmenter is not None


class TestContextAugmenterAugment:
    """Tests for prompt augmentation."""

    @pytest.mark.unit
    def test_augment_returns_original_when_not_explored(self, test_path):
        """Test that augment returns original prompt when not explored."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: "Test summary",
            structure_provider=lambda: {"total_files": 10},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: False,  # Not explored
        )
        prompt = "Fix the bug"
        result = augmenter.augment(prompt)
        assert result == prompt

    @pytest.mark.unit
    def test_augment_includes_summary(self, test_path):
        """Test that augment includes project summary."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: "A Python web application",
            structure_provider=lambda: {"total_files": 10, "by_type": {"python": 5}},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
        )
        result = augmenter.augment("Fix the bug")
        assert "A Python web application" in result
        assert "[Codebase Context]" in result
        assert "[User Request]" in result
        assert "Fix the bug" in result

    @pytest.mark.unit
    def test_augment_includes_structure(self, test_path):
        """Test that augment includes structure info."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {
                "total_files": 25,
                "by_type": {"python": 10, "javascript": 5, "other": 10},
            },
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
        )
        result = augmenter.augment("Fix the bug")
        assert "Files: 25 total" in result
        assert "python" in result

    @pytest.mark.unit
    def test_augment_includes_git_history(self, test_path):
        """Test that augment includes git history."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {"total_files": 10, "by_type": {}},
            git_history_provider=lambda: {
                "current_branch": "main",
                "recent_commits": ["abc123 Fix bug", "def456 Add feature"],
                "recently_changed_files": ["src/main.py", "tests/test_main.py"],
            },
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
        )
        result = augmenter.augment("Fix the bug")
        assert "Branch: main" in result
        assert "Fix bug" in result
        assert "Recently changed:" in result

    @pytest.mark.unit
    def test_augment_includes_files_when_requested(self, test_path):
        """Test that augment includes file listings when requested."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {"total_files": 10, "by_type": {}},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {"python": ["main.py", "utils.py", "config.py"]},
            is_explored_provider=lambda: True,
        )
        result = augmenter.augment("Fix the bug", include_files=True)
        assert "Python files:" in result
        assert "main.py" in result

    @pytest.mark.unit
    def test_augment_does_not_include_files_by_default(self, test_path):
        """Test that augment does not include file listings by default."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {"total_files": 10, "by_type": {}},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {"python": ["main.py", "utils.py"]},
            is_explored_provider=lambda: True,
        )
        result = augmenter.augment("Fix the bug")
        assert "Python files:" not in result


class TestContextAugmenterRelevantContext:
    """Tests for getting relevant context."""

    @pytest.mark.unit
    def test_get_relevant_context_empty_when_not_explored(self, test_path):
        """Test that get_relevant_context returns empty when not explored."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: "Test summary",
            structure_provider=lambda: {},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: False,
        )
        result = augmenter.get_relevant_context("test query")
        assert result == ""

    @pytest.mark.unit
    def test_get_relevant_context_uses_semantic_search(self, test_path):
        """Test that get_relevant_context uses semantic search when available."""
        # Create mock search result
        mock_result = Mock()
        mock_result.chunks = [
            {
                "path": "src/main.py",
                "lines": (10, 20),
                "content": "def main():\n    pass",
            }
        ]

        manager = MockSemanticManager(search_result=mock_result)
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
            semantic_manager=manager,
        )
        result = augmenter.get_relevant_context("main function")
        assert "src/main.py" in result
        assert "def main():" in result

    @pytest.mark.unit
    def test_get_relevant_context_fallback_to_keyword(self, test_path):
        """Test that get_relevant_context falls back to keyword matching."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: "A Python CLI tool",
            structure_provider=lambda: {"directories": ["src", "tests", "docs"]},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {"python": ["main.py", "cli.py"]},
            is_explored_provider=lambda: True,
            semantic_manager=None,
        )
        # Query for architecture should trigger keyword matching
        result = augmenter.get_relevant_context("architecture structure")
        assert "Project directories:" in result

    @pytest.mark.unit
    def test_get_relevant_context_includes_summary(self, test_path):
        """Test that keyword context includes summary."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: "A web application for task management",
            structure_provider=lambda: {},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {},
            is_explored_provider=lambda: True,
        )
        result = augmenter.get_relevant_context("general query")
        assert "A web application for task management" in result

    @pytest.mark.unit
    def test_get_relevant_context_file_keywords(self, test_path):
        """Test that file-related keywords return file listings."""
        augmenter = ContextAugmenter(
            project_path=test_path,
            summary_provider=lambda: None,
            structure_provider=lambda: {},
            git_history_provider=lambda: {},
            file_index_provider=lambda: {"python": ["models.py", "views.py", "urls.py"]},
            is_explored_provider=lambda: True,
        )
        result = augmenter.get_relevant_context("where is the class definition")
        assert "Key Python files:" in result
        assert "models.py" in result


class TestNullContextAugmenter:
    """Tests for NullContextAugmenter."""

    @pytest.mark.unit
    def test_augment_returns_original_prompt(self):
        """Test that augment returns prompt unchanged."""
        augmenter = NullContextAugmenter()
        prompt = "Fix the bug in authentication"
        result = augmenter.augment(prompt)
        assert result == prompt

    @pytest.mark.unit
    def test_augment_ignores_include_files(self):
        """Test that augment ignores include_files parameter."""
        augmenter = NullContextAugmenter()
        prompt = "Fix the bug"
        result = augmenter.augment(prompt, include_files=True)
        assert result == prompt

    @pytest.mark.unit
    def test_get_relevant_context_returns_empty(self):
        """Test that get_relevant_context returns empty string."""
        augmenter = NullContextAugmenter()
        result = augmenter.get_relevant_context("any query")
        assert result == ""

    @pytest.mark.unit
    def test_get_relevant_context_ignores_max_tokens(self):
        """Test that get_relevant_context ignores max_tokens parameter."""
        augmenter = NullContextAugmenter()
        result = augmenter.get_relevant_context("query", max_tokens=1000)
        assert result == ""
