"""
Tests for PathResolver.

Tests the behavior of file path resolution and automatic codebase exploration
for research tasks.
"""

import pytest
from src.task_router.strategies.path_resolver import PathResolver
from src.task_router.classifier import ClassifiedTask, TaskType


def make_task(
    original_input: str,
    extracted_files: list = None,
    extracted_directories: list = None,
    task_type: TaskType = TaskType.RESEARCH,
    complexity_score: int = 1,
    confidence: float = 0.9,
    reasoning: str = "Test classification"
) -> ClassifiedTask:
    """Factory for creating test tasks."""
    return ClassifiedTask(
        original_input=original_input,
        task_type=task_type,
        confidence=confidence,
        reasoning=reasoning,
        complexity_score=complexity_score,
        extracted_files=tuple(extracted_files or []),
        extracted_directories=tuple(extracted_directories or [])
    )


class MockContext:
    """Mock codebase context for testing."""

    def __init__(self, explored: bool = False, file_index: dict = None):
        self._explored = explored
        self.file_index = file_index or {}
        self.explore_called = False
        self.explore_force = None

    def is_explored(self) -> bool:
        return self._explored

    def explore(self, force: bool = False) -> None:
        self.explore_called = True
        self.explore_force = force
        self._explored = True


class MockContextProvider:
    """Mock context provider (like orchestrator)."""

    def __init__(self, context: MockContext = None):
        self.context = context or MockContext()


class TestPathResolverAutoExplore:
    """Test automatic exploration triggering."""

    def test_triggers_exploration_when_task_has_extracted_files(self):
        """Auto-explore triggers when task has extracted files."""
        context = MockContext(explored=False)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.auto_explore_if_needed(task)

        assert context.explore_called
        assert context.explore_force is True

    def test_triggers_exploration_when_task_has_extracted_directories(self):
        """Auto-explore triggers when task has extracted directories."""
        context = MockContext(explored=False)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check src/ directory", extracted_directories=["src"])

        resolver.auto_explore_if_needed(task)

        assert context.explore_called

    def test_triggers_exploration_for_file_keywords(self):
        """Auto-explore triggers when query contains file-related keywords."""
        context = MockContext(explored=False)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)

        test_inputs = [
            "show me the file",
            "what's in the code",
            "find the function",
            "check the class",
            "where is the component",
            "list directory contents",
            "show folder structure"
        ]

        for input_text in test_inputs:
            context.explore_called = False
            task = make_task(input_text)
            resolver.auto_explore_if_needed(task)
            assert context.explore_called, f"Should trigger for: {input_text}"

    def test_skips_exploration_for_non_file_queries(self):
        """Auto-explore skips when query doesn't involve files/codebase."""
        context = MockContext(explored=False)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)

        test_inputs = [
            "What is Django?",
            "Explain React hooks",
            "How does OAuth work?",
            "fetch latest npm version"
        ]

        for input_text in test_inputs:
            context.explore_called = False
            task = make_task(input_text)
            resolver.auto_explore_if_needed(task)
            assert not context.explore_called, f"Should skip for: {input_text}"

    def test_forces_exploration_when_not_explored(self):
        """Auto-explore uses force=True when codebase not explored."""
        context = MockContext(explored=False)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.auto_explore_if_needed(task)

        assert context.explore_force is True

    def test_forces_exploration_when_file_index_empty(self):
        """Auto-explore uses force=True when file index is empty."""
        context = MockContext(explored=True, file_index={})
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.auto_explore_if_needed(task)

        assert context.explore_called
        assert context.explore_force is True

    def test_skips_exploration_when_already_explored_with_index(self):
        """Auto-explore skips when already explored with populated file index."""
        context = MockContext(
            explored=True,
            file_index={"python": ["src/main.py"]}
        )
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.auto_explore_if_needed(task)

        # Should not call explore again
        assert not context.explore_called


class TestPathResolverPathResolution:
    """Test file path resolution."""

    def test_resolves_file_by_exact_basename_match(self):
        """Resolves file reference to full path by matching basename."""
        file_index = {
            "python": ["src/main.py", "tests/test_main.py"],
            "javascript": ["frontend/app.js"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.resolve_file_paths(task)

        # Should resolve to both matches
        assert "src/main.py" in task.extracted_files
        assert "tests/test_main.py" in task.extracted_files

    def test_resolves_file_by_partial_path_match(self):
        """Resolves file reference by partial path matching."""
        file_index = {
            "python": ["src/utils/helpers.py", "src/core/helpers.py"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check utils/helpers.py", extracted_files=["utils/helpers.py"])

        resolver.resolve_file_paths(task)

        assert "src/utils/helpers.py" in task.extracted_files

    def test_resolution_is_case_insensitive(self):
        """File resolution works regardless of case."""
        file_index = {
            "python": ["src/Main.py"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.resolve_file_paths(task)

        assert "src/Main.py" in task.extracted_files

    def test_deduplicates_resolved_paths(self):
        """Resolved paths are deduplicated."""
        file_index = {
            "python": ["src/main.py"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        # Both references should resolve to same file
        task = make_task("Check main.py", extracted_files=["main.py", "src/main.py"])

        resolver.resolve_file_paths(task)

        assert task.extracted_files.count("src/main.py") == 1

    def test_resolves_multiple_files(self):
        """Resolves multiple file references correctly."""
        file_index = {
            "python": ["src/main.py", "src/utils.py"],
            "javascript": ["frontend/app.js"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task(
            "Check main.py and app.js",
            extracted_files=["main.py", "app.js"]
        )

        resolver.resolve_file_paths(task)

        assert "src/main.py" in task.extracted_files
        assert "frontend/app.js" in task.extracted_files

    def test_handles_no_file_index(self):
        """Resolution handles missing file index gracefully."""
        context = MockContext(explored=True, file_index=None)
        context.file_index = None  # Explicitly set to None
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        # Should not raise error
        resolver.resolve_file_paths(task)

        # Files should remain unchanged
        assert task.extracted_files == ("main.py",)

    def test_handles_empty_file_index(self):
        """Resolution handles empty file index gracefully."""
        context = MockContext(explored=True, file_index={})
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.resolve_file_paths(task)

        # Files should remain unchanged
        assert task.extracted_files == ("main.py",)

    def test_handles_no_extracted_files(self):
        """Resolution handles tasks with no extracted files."""
        file_index = {"python": ["src/main.py"]}
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("What is Django?", extracted_files=[])

        # Should not raise error
        resolver.resolve_file_paths(task)

        assert task.extracted_files == ()


class TestPathResolverIntegration:
    """Test integration of auto-explore and path resolution."""

    def test_auto_explore_triggers_path_resolution(self):
        """Auto-explore automatically resolves paths when exploration completes."""
        file_index = {"python": ["src/main.py"]}
        context = MockContext(explored=False, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        # Auto-explore should also trigger resolution
        resolver.auto_explore_if_needed(task)

        # File should be resolved
        assert "src/main.py" in task.extracted_files

    def test_handles_context_not_available(self):
        """Handles gracefully when context is not available."""
        provider = MockContextProvider(context=None)
        provider.context = None
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        # Should not raise error
        resolver.auto_explore_if_needed(task)
        resolver.resolve_file_paths(task)

        # Files remain unchanged
        assert task.extracted_files == ("main.py",)

    def test_handles_exploration_failure_gracefully(self):
        """Handles exploration failures without crashing."""
        context = MockContext(explored=False)

        # Make explore raise an error
        def failing_explore(force=False):
            raise RuntimeError("Exploration failed")

        context.explore = failing_explore
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        # Should not propagate error
        resolver.auto_explore_if_needed(task)

        # Task should remain valid
        assert task.extracted_files == ("main.py",)


class TestPathResolverEdgeCases:
    """Test edge cases and error conditions."""

    def test_handles_special_characters_in_filenames(self):
        """Handles files with special characters in names."""
        file_index = {
            "python": ["src/my-file.py", "src/my_file (copy).py"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check my-file.py", extracted_files=["my-file.py"])

        resolver.resolve_file_paths(task)

        assert "src/my-file.py" in task.extracted_files

    def test_handles_unicode_filenames(self):
        """Handles files with unicode characters."""
        file_index = {
            "python": ["src/файл.py", "src/文件.py"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check файл.py", extracted_files=["файл.py"])

        resolver.resolve_file_paths(task)

        assert "src/файл.py" in task.extracted_files

    def test_handles_deep_nested_paths(self):
        """Handles deeply nested file paths."""
        file_index = {
            "python": ["src/a/b/c/d/e/f/deep.py"]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check deep.py", extracted_files=["deep.py"])

        resolver.resolve_file_paths(task)

        assert "src/a/b/c/d/e/f/deep.py" in task.extracted_files

    def test_prefers_more_specific_path_matches(self):
        """When multiple files match, all are included."""
        file_index = {
            "python": [
                "main.py",
                "src/main.py",
                "tests/main.py",
                "backend/src/main.py"
            ]
        }
        context = MockContext(explored=True, file_index=file_index)
        provider = MockContextProvider(context)
        resolver = PathResolver(provider)
        task = make_task("Check main.py", extracted_files=["main.py"])

        resolver.resolve_file_paths(task)

        # All matches should be included
        assert len(task.extracted_files) == 4
        assert "main.py" in task.extracted_files
        assert "src/main.py" in task.extracted_files
        assert "tests/main.py" in task.extracted_files
        assert "backend/src/main.py" in task.extracted_files
