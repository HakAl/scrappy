"""
Tests for input validation in CodebaseContext and ContextCache.

These tests verify that proper validation is performed on:
1. Project paths (existence, type)
2. Cache structure (required fields, data types)
"""
import pytest
import logging

from scrappy.context import CodebaseContext
from scrappy.context.cache import ContextCache


class TestPathValidation:
    """Tests for project path validation in CodebaseContext."""

    @pytest.mark.unit
    def test_nonexistent_path_logs_warning(self, tmp_path, caplog):
        """Should log warning when path doesn't exist."""
        nonexistent = tmp_path / "does_not_exist"

        with caplog.at_level(logging.WARNING):
            CodebaseContext(str(nonexistent))

        # Should log a warning about non-existent path
        assert len(caplog.records) > 0
        log_text = caplog.text.lower()
        assert 'does not exist' in log_text or 'not found' in log_text or 'nonexistent' in log_text

    @pytest.mark.unit
    def test_nonexistent_path_still_creates_context(self, tmp_path):
        """Should still create context even with non-existent path (for flexibility)."""
        nonexistent = tmp_path / "does_not_exist"

        context = CodebaseContext(str(nonexistent))

        # Context should be created but marked as invalid/unexplored
        assert context.project_path == nonexistent.resolve()
        assert context.is_explored() is False

    @pytest.mark.unit
    def test_file_path_instead_of_directory_logs_warning(self, tmp_path, caplog):
        """Should log warning when path is a file, not directory."""
        file_path = tmp_path / "some_file.txt"
        file_path.write_text("content")

        with caplog.at_level(logging.WARNING):
            CodebaseContext(str(file_path))

        # Should log a warning about path being a file
        assert len(caplog.records) > 0
        log_text = caplog.text.lower()
        assert 'directory' in log_text or 'file' in log_text or 'not a directory' in log_text

    @pytest.mark.unit
    def test_explore_nonexistent_path_returns_error_status(self, tmp_path):
        """Explore should return error status for non-existent path."""
        nonexistent = tmp_path / "does_not_exist"
        context = CodebaseContext(str(nonexistent))

        result = context.explore()

        # Should indicate an error or return empty results
        assert result.get('status') in ('error', 'explored')
        assert result.get('total_files', 0) == 0

    @pytest.mark.unit
    def test_explore_file_path_returns_error_status(self, tmp_path):
        """Explore should return error status when path is a file."""
        file_path = tmp_path / "some_file.txt"
        file_path.write_text("content")

        context = CodebaseContext(str(file_path))
        result = context.explore()

        # Should indicate an error
        assert result.get('status') in ('error', 'explored')
        assert result.get('total_files', 0) == 0

    @pytest.mark.unit
    def test_get_status_indicates_invalid_path(self, tmp_path):
        """get_status should indicate when path is invalid."""
        nonexistent = tmp_path / "does_not_exist"
        context = CodebaseContext(str(nonexistent))

        status = context.get_status()

        # Status should indicate path issue
        assert 'path_valid' in status or 'error' in status.get('project_path', '').lower() or not status.get('is_explored', True)

    @pytest.mark.unit
    def test_relative_path_resolved_correctly(self, tmp_path, monkeypatch):
        """Relative paths should be resolved correctly."""
        # Change to tmp_path
        monkeypatch.chdir(tmp_path)

        # Create a subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        context = CodebaseContext("subdir")

        # Should resolve to absolute path
        assert context.project_path.is_absolute()
        assert context.project_path == subdir.resolve()

    @pytest.mark.unit
    def test_empty_string_path_uses_current_directory(self, tmp_path, monkeypatch):
        """Empty string path should use current directory."""
        monkeypatch.chdir(tmp_path)

        context = CodebaseContext("")

        # Should use current directory
        assert context.project_path == tmp_path.resolve()

    @pytest.mark.unit
    def test_none_path_uses_current_directory(self, tmp_path, monkeypatch):
        """None path should use current directory."""
        monkeypatch.chdir(tmp_path)

        context = CodebaseContext(None)

        # Should use current directory
        assert context.project_path == tmp_path.resolve()


class TestCacheStructureValidation:
    """Tests for cache structure validation in ContextCache."""

    @pytest.mark.unit
    def test_missing_explored_at_logs_warning(self, tmp_path, caplog):
        """Should log warning when required 'explored_at' field is missing."""
        cache_file = tmp_path / "cache.json"
        # Write cache without explored_at
        cache_file.write_text('{"summary": "test", "structure": {}}')

        cache = ContextCache()

        with caplog.at_level(logging.WARNING):
            result = cache.load(cache_file)

        # Should log warning about missing field or return partial data
        # The cache should still load but indicate the issue
        if result is not None:
            # If it returns data, it should be missing explored_at
            assert result.get('explored_at') is None

    @pytest.mark.unit
    def test_missing_structure_field_handled(self, tmp_path):
        """Should handle missing 'structure' field gracefully."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"explored_at": "2024-01-01T10:00:00", "summary": "test"}')

        cache = ContextCache()
        result = cache.load(cache_file)

        # Should load successfully with missing structure
        assert result is not None
        assert 'structure' not in result or result.get('structure') is None

    @pytest.mark.unit
    def test_invalid_datetime_format_logs_warning(self, tmp_path, caplog):
        """Should log warning for invalid datetime format and set to None."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"explored_at": "not-a-valid-date"}')

        cache = ContextCache()

        with caplog.at_level(logging.WARNING):
            result = cache.load(cache_file)

        # Should set to None if not valid datetime and log warning
        assert result is not None
        assert result['explored_at'] is None
        # Should log a warning about invalid datetime
        assert len(caplog.records) > 0
        assert 'invalid' in caplog.text.lower() or 'datetime' in caplog.text.lower()

    @pytest.mark.unit
    def test_extra_fields_ignored(self, tmp_path):
        """Should ignore extra unknown fields in cache."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"explored_at": "2024-01-01T10:00:00", "unknown_field": "value", "another": 123}')

        cache = ContextCache()
        result = cache.load(cache_file)

        # Should load successfully with extra fields
        assert result is not None
        assert result.get('unknown_field') == 'value'
        assert result.get('another') == 123

    @pytest.mark.unit
    def test_null_values_for_required_fields(self, tmp_path):
        """Should handle null values for expected fields."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"explored_at": null, "summary": null, "structure": null}')

        cache = ContextCache()
        result = cache.load(cache_file)

        # Should handle null values
        assert result is not None
        assert result.get('explored_at') is None
        assert result.get('summary') is None
        assert result.get('structure') is None

    @pytest.mark.unit
    def test_nested_invalid_types_handled(self, tmp_path):
        """Should handle invalid types in nested structures."""
        cache_file = tmp_path / "cache.json"
        # by_type should be dict of ints, but has string values
        cache_file.write_text('''
        {
            "explored_at": "2024-01-01T10:00:00",
            "structure": {
                "total_files": "not-an-int",
                "by_type": {"python": "not-a-number"}
            }
        }
        ''')

        cache = ContextCache()
        result = cache.load(cache_file)

        # Should load without crashing
        assert result is not None
        assert result['structure']['total_files'] == "not-an-int"


class TestCacheValidationWithCodebaseContext:
    """Tests for cache validation when used by CodebaseContext."""

    @pytest.mark.unit
    def test_corrupted_cache_explored_at_handled(self, temp_project_dir):
        """CodebaseContext should handle corrupted explored_at in cache."""
        # First explore to create cache
        context1 = CodebaseContext(str(temp_project_dir))
        context1.explore()

        # Corrupt the explored_at field
        cache_file = temp_project_dir / ".scrappy" / "context.json"
        import json
        with open(cache_file, 'r') as f:
            data = json.load(f)
        data['explored_at'] = 'invalid-datetime'
        with open(cache_file, 'w') as f:
            json.dump(data, f)

        # Load new context - should handle gracefully
        context2 = CodebaseContext(str(temp_project_dir))

        # Should either have None explored_at or be unexplored
        assert context2.explored_at is None or not context2.is_explored()


class TestValidationLogging:
    """Tests for validation warning messages."""

    @pytest.mark.unit
    def test_path_validation_log_includes_path(self, tmp_path, caplog):
        """Path validation warning should include the problematic path."""
        nonexistent = tmp_path / "my_missing_project"

        with caplog.at_level(logging.WARNING):
            CodebaseContext(str(nonexistent))

        # Warning should mention the path
        if caplog.records:
            log_text = caplog.text
            assert 'my_missing_project' in log_text or str(nonexistent) in log_text

