"""
Tests for ContextCoordinator.

Focuses on proving BEHAVIOR works, not structure.
Following CLAUDE.md guidelines:
- Tests prove features work, not just that code runs
- Edge cases covered (failures, missing summaries, re-exploration)
- Minimal mocking (only CodebaseContext and OutputInterface)
- Tests would fail if feature breaks
"""

import pytest
from unittest.mock import Mock
from src.orchestrator.context_coordinator import ContextCoordinator

class MockCodebaseContext:
    """Test double for CodebaseContext."""

    def __init__(self, explored=False, total_files=0):
        self._explored = explored
        self._total_files = total_files
        self.project_path = Mock(name='test_project')
        self.explore_called = False
        self.scan_called = False
        self.clear_cache_called = False
        self.generate_summary_called = False

    def is_explored(self):
        return self._explored

    def explore(self, force=False):
        self.explore_called = True
        if force or not self._explored:
            self._explored = True
            return {
                'status': 'explored',
                'total_files': self._total_files
            }
        return {
            'status': 'cached',
            'total_files': self._total_files
        }

    def get_status(self):
        return {
            'total_files': self._total_files,
            'explored': self._explored
        }

    def clear_cache(self):
        self.clear_cache_called = True
        self._explored = False

    def generate_summary(self, func):
        self.generate_summary_called = True
        # Call the function to simulate summary generation
        if func:
            func("test prompt")


class MockOutput:
    """Test double for OutputInterface."""

    def __init__(self):
        self.info_messages = []
        self.error_messages = []
        self.section_messages = []

    def info(self, message: str):
        self.info_messages.append(message)

    def error(self, message: str):
        self.error_messages.append(message)

    def section(self, message: str):
        self.section_messages.append(message)


class TestAutoExploration:
    """Test that auto-exploration coordinates context scanning correctly."""

    def test_explores_when_not_yet_explored(self):
        """auto_explore should trigger exploration if context not yet explored."""
        context = MockCodebaseContext(explored=False, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.auto_explore()

        assert context.explore_called is True
        assert result['status'] == 'explored'
        assert result['total_files'] == 50

    def test_uses_cache_when_already_explored(self):
        """auto_explore should use cache if already explored."""
        context = MockCodebaseContext(explored=True, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.auto_explore()

        assert result['status'] == 'cached'
        assert result['cache_used'] is True
        assert result['total_files'] == 50

    def test_logs_exploration_status(self):
        """auto_explore should log what it's doing."""
        context = MockCodebaseContext(explored=False, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        coordinator.auto_explore()

        # Should have logged something
        assert len(output.info_messages) > 0
        assert any('Exploring' in msg or 'Found' in msg for msg in output.info_messages)

    def test_logs_cached_context_status(self):
        """auto_explore should log when using cached context."""
        context = MockCodebaseContext(explored=True, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        coordinator.auto_explore()

        # Should have logged cache usage
        assert len(output.info_messages) > 0
        assert any('cached' in msg.lower() for msg in output.info_messages)

    def test_generates_summary_when_explored(self):
        """auto_explore should generate summary after exploration."""
        context = MockCodebaseContext(explored=False, total_files=50)
        output = MockOutput()
        summary_func = Mock(return_value="Project summary")
        coordinator = ContextCoordinator(context, output, generate_summary_func=summary_func)

        coordinator.auto_explore()

        assert context.generate_summary_called is True

    def test_skips_summary_when_no_function_provided(self):
        """auto_explore should not crash if no summary function provided."""
        context = MockCodebaseContext(explored=False, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output, generate_summary_func=None)

        # Should not crash
        result = coordinator.auto_explore()

        assert result['status'] == 'explored'


class TestManualExploration:
    """Test that manual exploration (explore_project) works correctly."""

    def test_triggers_exploration(self):
        """explore_project should trigger context exploration."""
        context = MockCodebaseContext(explored=False, total_files=100)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.explore_project()

        assert context.explore_called is True
        assert result['status'] == 'explored'
        assert result['total_files'] == 100

    def test_force_clears_cache_before_exploration(self):
        """explore_project with force=True should clear cache first."""
        context = MockCodebaseContext(explored=True, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.explore_project(force=True)

        assert context.clear_cache_called is True
        assert context.explore_called is True

    def test_force_generates_summary_even_if_cached(self):
        """explore_project with force=True should regenerate summary."""
        context = MockCodebaseContext(explored=True, total_files=50)
        output = MockOutput()
        summary_func = Mock(return_value="Summary")
        coordinator = ContextCoordinator(context, output, generate_summary_func=summary_func)

        coordinator.explore_project(force=True)

        # Should generate summary even though cached
        assert context.generate_summary_called is True

    def test_handles_exploration_errors(self):
        """explore_project should handle and log errors gracefully."""
        context = Mock()
        context.explore = Mock(side_effect=RuntimeError("Scan failed"))
        context.clear_cache = Mock()
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.explore_project()

        assert result['status'] == 'failed'
        assert 'error' in result
        assert len(output.error_messages) > 0

    def test_logs_results_when_summary_generated(self):
        """explore_project should log when summary is generated."""
        context = MockCodebaseContext(explored=False, total_files=75)
        output = MockOutput()
        summary_func = Mock(return_value="Summary")
        coordinator = ContextCoordinator(context, output, generate_summary_func=summary_func)

        coordinator.explore_project()

        # Should have logged info about summary generation
        assert len(output.info_messages) > 0
        assert any('summary' in msg.lower() for msg in output.info_messages)


class TestContextAccess:
    """Test that context property provides access to underlying context."""

    def test_context_property_returns_underlying_context(self):
        """context property should return the CodebaseContext instance."""
        mock_context = MockCodebaseContext()
        output = MockOutput()
        coordinator = ContextCoordinator(mock_context, output)

        result = coordinator.context

        assert result is mock_context

    def test_can_call_context_methods_through_property(self):
        """Should be able to call context methods through property."""
        mock_context = MockCodebaseContext(explored=True, total_files=50)
        output = MockOutput()
        coordinator = ContextCoordinator(mock_context, output)

        # Access context through property
        is_explored = coordinator.context.is_explored()
        status = coordinator.context.get_status()

        assert is_explored is True
        assert status['total_files'] == 50


class TestSummaryGeneration:
    """Test summary generation coordination."""

    def test_generates_summary_after_successful_exploration(self):
        """Should generate summary when exploration succeeds."""
        context = MockCodebaseContext(explored=False, total_files=50)
        output = MockOutput()
        summary_func = Mock(return_value="Summary text")
        coordinator = ContextCoordinator(context, output, generate_summary_func=summary_func)

        coordinator.explore_project()

        assert context.generate_summary_called is True
        # Summary function should have been called
        assert summary_func.called is True

    def test_logs_summary_generation(self):
        """Should log when summary is generated."""
        context = MockCodebaseContext(explored=False, total_files=50)
        output = MockOutput()
        summary_func = Mock(return_value="Summary")
        coordinator = ContextCoordinator(context, output, generate_summary_func=summary_func)

        coordinator.explore_project()

        # Should have logged summary generation
        assert any('summary' in msg.lower() for msg in output.info_messages)


class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_handles_zero_files_found(self):
        """Should handle case where no files are found."""
        context = MockCodebaseContext(explored=False, total_files=0)
        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.auto_explore()

        assert result['total_files'] == 0
        # Should still complete successfully
        assert result['status'] == 'explored'

    def test_handles_missing_project_path_name(self):
        """Should handle context without project_path.name attribute."""
        context = Mock()
        context.is_explored = Mock(return_value=True)
        context.get_status = Mock(return_value={'total_files': 50})
        context.project_path = None  # No name attribute

        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        # Should not crash
        result = coordinator.auto_explore()

        assert result['status'] == 'cached'

    def test_handles_context_status_missing_fields(self):
        """Should handle when context status is missing expected fields."""
        context = Mock()
        context.is_explored = Mock(return_value=True)
        context.get_status = Mock(return_value={})  # Missing total_files
        context.project_path = Mock(name='project')

        output = MockOutput()
        coordinator = ContextCoordinator(context, output)

        result = coordinator.auto_explore()

        # Should use default value for missing fields
        assert result['total_files'] == 0

    def test_handles_summary_generation_failure(self):
        """Should handle errors in summary generation (marks as failed)."""
        context = Mock()
        context.explore = Mock(return_value={'status': 'explored', 'total_files': 50})
        context.clear_cache = Mock()
        # generate_summary raises error
        context.generate_summary = Mock(side_effect=RuntimeError("Summary failed"))
        output = MockOutput()
        summary_func = Mock(return_value="Summary")
        coordinator = ContextCoordinator(context, output, generate_summary_func=summary_func)

        # Summary error causes whole operation to fail
        result = coordinator.explore_project()

        # Operation failed due to summary error
        assert result['status'] == 'failed'
        assert 'error' in result
        # Error should be logged
        assert len(output.error_messages) > 0
