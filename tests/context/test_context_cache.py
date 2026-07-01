"""
Tests for ContextCache - context persistence and caching.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime

from scrappy.context.cache import ContextCache


class TestContextCacheBasics:
    """Basic cache operations."""

    @pytest.mark.unit
    def test_save_creates_file(self, tmp_path):
        """save() creates cache file on disk."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        data = {'key': 'value'}
        cache.save(cache_file, data)

        assert cache_file.exists()

    @pytest.mark.unit
    def test_save_writes_valid_json(self, tmp_path):
        """save() writes valid JSON to file."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        data = {'key': 'value', 'number': 42}
        cache.save(cache_file, data)

        with open(cache_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        assert loaded == data

    @pytest.mark.unit
    def test_load_returns_dict(self, tmp_path):
        """load() returns a dictionary."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"key": "value"}')

        cache = ContextCache()
        result = cache.load(cache_file)

        assert isinstance(result, dict)
        assert result == {'key': 'value'}

    @pytest.mark.unit
    def test_load_nonexistent_returns_none(self, tmp_path):
        """load() returns None for nonexistent file."""
        cache_file = tmp_path / "nonexistent.json"

        cache = ContextCache()
        result = cache.load(cache_file)

        assert result is None

    @pytest.mark.unit
    def test_clear_deletes_file(self, tmp_path):
        """clear() removes the cache file."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{}')
        assert cache_file.exists()

        cache = ContextCache()
        cache.clear(cache_file)

        assert not cache_file.exists()


class TestCacheRoundTrip:
    """Tests for save/load round-trip."""

    @pytest.mark.unit
    def test_simple_data_roundtrip(self, tmp_path):
        """Simple data survives save/load cycle."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        original = {
            'string': 'hello',
            'number': 42,
            'float': 3.14,
            'boolean': True,
            'null': None
        }

        cache.save(cache_file, original)
        loaded = cache.load(cache_file)

        assert loaded == original

    @pytest.mark.unit
    def test_nested_data_roundtrip(self, tmp_path):
        """Nested data structures survive save/load cycle."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        original = {
            'structure': {
                'total_files': 100,
                'by_type': {'python': 50, 'javascript': 30}
            },
            'file_index': {
                'python': ['main.py', 'utils.py'],
                'javascript': ['app.js']
            }
        }

        cache.save(cache_file, original)
        loaded = cache.load(cache_file)

        assert loaded == original

    @pytest.mark.unit
    def test_list_data_roundtrip(self, tmp_path):
        """Lists survive save/load cycle."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        original = {
            'files': ['a.py', 'b.py', 'c.py'],
            'nested': [[1, 2], [3, 4]]
        }

        cache.save(cache_file, original)
        loaded = cache.load(cache_file)

        assert loaded == original


class TestDatetimeHandling:
    """Tests for datetime serialization."""

    @pytest.mark.unit
    def test_saves_datetime_as_isoformat(self, tmp_path):
        """Datetime is saved as ISO format string."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        now = datetime.now()
        data = {'explored_at': now}

        cache.save(cache_file, data)

        with open(cache_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        # Should be stored as ISO format string
        assert isinstance(raw['explored_at'], str)
        assert now.isoformat() == raw['explored_at']

    @pytest.mark.unit
    def test_loads_datetime_from_isoformat(self, tmp_path):
        """ISO format string is loaded as datetime."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        now = datetime.now()
        data = {'explored_at': now}

        cache.save(cache_file, data)
        loaded = cache.load(cache_file)

        # Should be restored as datetime
        assert isinstance(loaded['explored_at'], datetime)
        # Compare with reasonable precision (microseconds may differ)
        assert loaded['explored_at'].replace(microsecond=0) == now.replace(microsecond=0)

    @pytest.mark.unit
    def test_datetime_roundtrip(self, tmp_path):
        """Datetime survives save/load cycle."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        original_time = datetime(2024, 1, 15, 10, 30, 45)
        data = {'explored_at': original_time}

        cache.save(cache_file, data)
        loaded = cache.load(cache_file)

        assert loaded['explored_at'] == original_time

    @pytest.mark.unit
    def test_none_datetime_handled(self, tmp_path):
        """None datetime value is preserved."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        data = {'explored_at': None}

        cache.save(cache_file, data)
        loaded = cache.load(cache_file)

        assert loaded['explored_at'] is None


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.unit
    def test_corrupted_json_returns_none(self, tmp_path):
        """load() returns None for corrupted JSON."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not valid json {")

        cache = ContextCache()
        result = cache.load(cache_file)

        assert result is None

    @pytest.mark.unit
    def test_empty_file_returns_none(self, tmp_path):
        """load() returns None for empty file."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("")

        cache = ContextCache()
        result = cache.load(cache_file)

        assert result is None

    @pytest.mark.unit
    def test_invalid_datetime_handled(self, tmp_path):
        """load() handles invalid datetime strings by setting to None."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"explored_at": "not-a-date"}')

        cache = ContextCache()
        result = cache.load(cache_file)

        # Should load but set invalid datetime to None (not crash)
        assert result is not None
        assert result['explored_at'] is None

    @pytest.mark.unit
    def test_accepts_path_object(self, tmp_path):
        """Methods accept Path objects."""
        cache_file = Path(tmp_path) / "cache.json"
        cache = ContextCache()

        data = {'key': 'value'}
        cache.save(cache_file, data)
        loaded = cache.load(cache_file)

        assert loaded == data

    @pytest.mark.unit
    def test_accepts_string_path(self, tmp_path):
        """Methods accept string paths."""
        cache_file = str(tmp_path / "cache.json")
        cache = ContextCache()

        data = {'key': 'value'}
        cache.save(cache_file, data)
        loaded = cache.load(cache_file)

        assert loaded == data

    @pytest.mark.unit
    def test_save_overwrites_existing(self, tmp_path):
        """save() overwrites existing cache file."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        # Save first version
        cache.save(cache_file, {'version': 1})

        # Save second version
        cache.save(cache_file, {'version': 2})

        loaded = cache.load(cache_file)
        assert loaded == {'version': 2}

    @pytest.mark.unit
    def test_save_creates_parent_dirs(self, tmp_path):
        """save() creates parent directories if needed."""
        cache_file = tmp_path / "nested" / "dir" / "cache.json"
        cache = ContextCache()

        data = {'key': 'value'}
        cache.save(cache_file, data)

        assert cache_file.exists()
        loaded = cache.load(cache_file)
        assert loaded == data


class TestCacheErrorLogging:
    """Tests for error logging and recovery visibility."""

    @pytest.mark.unit
    def test_save_logs_warning_on_permission_error(self, tmp_path, caplog):
        """save() logs a warning when write fails due to permissions."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        # Create a directory with the same name to cause a write error
        cache_file.mkdir()

        with caplog.at_level(logging.WARNING):
            cache.save(cache_file, {'key': 'value'})

        # Should log a warning with file path
        assert len(caplog.records) > 0
        assert 'cache' in caplog.text.lower() or str(cache_file) in caplog.text

    @pytest.mark.unit
    def test_save_logs_warning_on_serialization_error(self, tmp_path, caplog):
        """save() logs a warning when data cannot be serialized."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        # Create unserializable data
        data = {'bad': object()}

        with caplog.at_level(logging.WARNING):
            cache.save(cache_file, data)

        # Should log a warning
        assert len(caplog.records) > 0

    @pytest.mark.unit
    def test_load_logs_warning_on_corrupted_json(self, tmp_path, caplog):
        """load() logs a warning when JSON is corrupted."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not valid json {")

        cache = ContextCache()

        with caplog.at_level(logging.WARNING):
            result = cache.load(cache_file)

        # Should return None
        assert result is None
        # Should log a warning about the corruption
        assert len(caplog.records) > 0
        assert 'json' in caplog.text.lower() or 'corrupt' in caplog.text.lower() or 'invalid' in caplog.text.lower()

    @pytest.mark.unit
    def test_load_logs_warning_on_io_error(self, tmp_path, caplog, monkeypatch):
        """load() logs a warning when file read fails."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"key": "value"}')

        cache = ContextCache()

        # Mock open to raise IOError
        def mock_open(*args, **kwargs):
            raise IOError("Disk read error")

        monkeypatch.setattr("builtins.open", mock_open)

        with caplog.at_level(logging.WARNING):
            result = cache.load(cache_file)

        # Should return None
        assert result is None
        # Should log a warning
        assert len(caplog.records) > 0

    @pytest.mark.unit
    def test_save_log_includes_file_path(self, tmp_path, caplog):
        """save() warning includes the file path for debugging."""
        import logging
        cache_file = tmp_path / "my_cache.json"
        cache = ContextCache()

        # Create unserializable data to trigger error
        data = {'bad': object()}

        with caplog.at_level(logging.WARNING):
            cache.save(cache_file, data)

        # Log should mention the file path
        assert len(caplog.records) > 0
        # Either the full path or filename should be in the log
        log_text = caplog.text.lower()
        assert 'my_cache' in log_text or str(cache_file).lower() in log_text

    @pytest.mark.unit
    def test_load_log_includes_error_context(self, tmp_path, caplog):
        """load() warning includes error context for debugging."""
        import logging
        cache_file = tmp_path / "broken.json"
        cache_file.write_text("{invalid json")

        cache = ContextCache()

        with caplog.at_level(logging.WARNING):
            cache.load(cache_file)

        # Log should provide context about what went wrong
        assert len(caplog.records) > 0
        log_text = caplog.text.lower()
        # Should mention either the file or the error type
        assert 'broken' in log_text or 'json' in log_text or 'decode' in log_text

    @pytest.mark.unit
    def test_save_still_returns_gracefully_after_logging(self, tmp_path, caplog):
        """save() returns without raising even after logging error."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        # Create unserializable data
        data = {'bad': object()}

        with caplog.at_level(logging.WARNING):
            # Should not raise
            result = cache.save(cache_file, data)

        # Should return None (implicit)
        assert result is None

    @pytest.mark.unit
    def test_load_still_returns_none_after_logging(self, tmp_path, caplog):
        """load() returns None gracefully after logging error."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("corrupted")

        cache = ContextCache()

        with caplog.at_level(logging.WARNING):
            result = cache.load(cache_file)

        # Should return None without raising
        assert result is None


class TestCacheIntegration:
    """Integration-style tests mimicking CodebaseContext usage."""

    @pytest.mark.unit
    def test_multiple_save_load_cycles(self, tmp_path):
        """Multiple save/load cycles preserve data integrity."""
        cache_file = tmp_path / "cache.json"
        cache = ContextCache()

        data = {'counter': 0, 'history': []}

        for i in range(5):
            data['counter'] = i
            data['history'].append(f'step_{i}')
            cache.save(cache_file, data)

        loaded = cache.load(cache_file)
        assert loaded['counter'] == 4
        assert len(loaded['history']) == 5
