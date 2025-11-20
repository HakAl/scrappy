"""
Tests for ContextManager.

These tests verify that ContextManager properly coordinates codebase context
operations with orchestrator components (logging, task execution).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from src.orchestrator.context_manager import ContextManager
from src.context.codebase_context import CodebaseContext


class TestContextManagerAutoExplore:
    """Test auto-exploration behavior on startup."""

    def test_auto_explore_uses_cached_context_when_available(self, tmp_path):
        """When context is already explored, auto_explore should use cached data."""
        # Create a context that's already explored
        context = CodebaseContext(str(tmp_path))
        context.explore()  # Explore to populate cache

        output = Mock()
        manager = ContextManager(context, output)

        # Act
        result = manager.auto_explore()

        # Assert
        assert result['status'] == 'cached'
        assert result['cache_used'] is True
        assert result['total_files'] >= 0
        assert output.info.called
        assert '[CONTEXT] Loaded cached context' in output.info.call_args[0][0]

    def test_auto_explore_explores_when_not_cached(self, tmp_path):
        """When context is not explored, auto_explore should trigger exploration."""
        # Create files for exploration
        (tmp_path / "test.py").write_text("# test file")
        (tmp_path / "README.md").write_text("# README")

        context = CodebaseContext(str(tmp_path))
        output = Mock()
        summary_func = Mock(return_value="Test summary")
        manager = ContextManager(context, output, summary_func)

        # Act
        result = manager.auto_explore()

        # Assert
        assert result['status'] == 'explored'
        assert result['cache_used'] is False
        assert result['total_files'] > 0
        # Should log exploration and summary generation
        assert output.info.call_count >= 2
        assert summary_func.called

    def test_auto_explore_skips_summary_when_no_func_provided(self, tmp_path):
        """When no summary function provided, auto_explore should skip summary generation."""
        (tmp_path / "test.py").write_text("# test")

        context = CodebaseContext(str(tmp_path))
        output = Mock()
        manager = ContextManager(context, output, generate_summary_func=None)

        # Act
        result = manager.auto_explore()

        # Assert - Should explore but not generate summary
        assert result['status'] == 'explored'
        # Should NOT mention summary generation in logs
        info_calls = [call[0][0] for call in output.info.call_args_list]
        summary_mentioned = any('Generated project summary' in msg for msg in info_calls)
        assert not summary_mentioned

    def test_auto_explore_handles_empty_directory(self, tmp_path):
        """Auto-exploration of empty directory should complete gracefully."""
        context = CodebaseContext(str(tmp_path))
        output = Mock()
        manager = ContextManager(context, output)

        # Act
        result = manager.auto_explore()

        # Assert
        assert result['status'] in ['explored', 'skipped']
        assert result['total_files'] == 0


class TestContextManagerExploreProject:
    """Test manual project exploration."""

    def test_explore_project_without_force_uses_cache(self, tmp_path):
        """When force=False, explore_project should use cached context."""
        context = CodebaseContext(str(tmp_path))
        context.explore()  # Pre-populate cache

        output = Mock()
        manager = ContextManager(context, output)

        # Act
        result = manager.explore_project(force=False)

        # Assert
        assert result['status'] == 'cached'

    def test_explore_project_with_force_reexplores(self, tmp_path):
        """When force=True, explore_project should force re-exploration."""
        (tmp_path / "test.py").write_text("# test")

        context = CodebaseContext(str(tmp_path))
        context.explore()  # Pre-populate cache

        output = Mock()
        summary_func = Mock(return_value="Summary")
        manager = ContextManager(context, output, summary_func)

        # Act
        result = manager.explore_project(force=True)

        # Assert
        assert result['status'] == 'explored'
        assert summary_func.called

    def test_explore_project_generates_summary_when_func_provided(self, tmp_path):
        """explore_project should generate summary when function is provided."""
        (tmp_path / "test.py").write_text("# test")

        context = CodebaseContext(str(tmp_path))
        output = Mock()
        summary_func = Mock(return_value="Generated summary")
        manager = ContextManager(context, output, summary_func)

        # Act
        result = manager.explore_project(force=True)

        # Assert
        assert result['status'] == 'explored'
        assert summary_func.called
        # Should log summary generation
        info_calls = [call[0][0] for call in output.info.call_args_list]
        summary_mentioned = any('Generated project summary' in msg for msg in info_calls)
        assert summary_mentioned

    def test_explore_project_handles_exploration_error(self, tmp_path):
        """explore_project should handle and report exploration errors."""
        # Create a mock context that raises an error
        context = Mock()
        context.clear_cache = Mock()
        context.explore = Mock(side_effect=RuntimeError("Exploration failed"))
        context.project_path = tmp_path

        output = Mock()
        manager = ContextManager(context, output)

        # Act
        result = manager.explore_project(force=True)

        # Assert
        assert result['status'] == 'failed'
        assert 'error' in result
        assert 'Exploration failed' in result['error']
        assert output.error.called


class TestContextManagerContextProperty:
    """Test the context property accessor."""

    def test_context_property_returns_underlying_context(self, tmp_path):
        """The context property should return the underlying CodebaseContext."""
        context = CodebaseContext(str(tmp_path))
        manager = ContextManager(context)

        # Act
        retrieved_context = manager.context

        # Assert
        assert retrieved_context is context

    def test_context_property_allows_direct_operations(self, tmp_path):
        """The context property should allow direct CodebaseContext operations."""
        context = CodebaseContext(str(tmp_path))
        manager = ContextManager(context)

        # Act - Use context directly through property
        status = manager.context.get_status()

        # Assert
        assert 'project_path' in status
        assert 'is_explored' in status


class TestContextManagerOutputLogging:
    """Test output logging behavior."""

    def test_uses_provided_output_interface(self, tmp_path):
        """ContextManager should use the provided OutputInterface."""
        context = CodebaseContext(str(tmp_path))
        custom_output = Mock()
        manager = ContextManager(context, custom_output)

        # Act
        manager.auto_explore()

        # Assert
        assert custom_output.info.called



class TestContextManagerIntegration:
    """Integration tests with real CodebaseContext."""

    def test_force_reexploration_clears_cache(self, tmp_path):
        """Force exploration should clear and rebuild cache."""
        (tmp_path / "test.py").write_text("# test")

        context = CodebaseContext(str(tmp_path))
        output = Mock()
        manager = ContextManager(context, output)

        # First exploration
        result1 = manager.auto_explore()

        # Add new file
        (tmp_path / "new.py").write_text("# new file")

        # Force re-exploration
        result2 = manager.explore_project(force=True)

        # Assert
        assert result1['status'] == 'explored'
        assert result2['status'] == 'explored'
        # Second exploration should find more files
        assert result2['total_files'] > result1['total_files']


class TestContextManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_nonexistent_directory(self, tmp_path):
        """ContextManager should handle nonexistent directories gracefully."""
        nonexistent = tmp_path / "does_not_exist"
        context = CodebaseContext(str(nonexistent))
        output = Mock()
        manager = ContextManager(context, output)

        # Act
        result = manager.auto_explore()

        # Assert - Should complete without raising
        assert 'status' in result

    def test_handles_None_summary_function(self, tmp_path):
        """ContextManager should work when summary function is None."""
        (tmp_path / "test.py").write_text("# test")

        context = CodebaseContext(str(tmp_path))
        output = Mock()
        manager = ContextManager(context, output, generate_summary_func=None)

        # Act
        result = manager.explore_project(force=True)

        # Assert - Should explore successfully without summary
        assert result['status'] == 'explored'


class TestContextManagerProtocolCompliance:
    """Test that ContextManager implements ContextManagerProtocol."""



class TestContextManagerDependencyInjection:
    """Test dependency injection behavior."""

    def test_accepts_codebase_context_dependency(self, tmp_path):
        """ContextManager should accept CodebaseContext as dependency."""
        context = CodebaseContext(str(tmp_path))

        # Act
        manager = ContextManager(context)

        # Assert
        assert manager.context is context

    def test_accepts_output_interface_dependency(self, tmp_path):
        """ContextManager should accept OutputInterface as dependency."""
        context = CodebaseContext(str(tmp_path))
        custom_output = Mock()

        # Act
        manager = ContextManager(context, custom_output)

        # Assert
        assert manager.output is custom_output
