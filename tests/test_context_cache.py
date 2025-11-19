"""
Tests for ContextCache - context persistence and caching.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime

from src.context.cache import ContextCache


class TestContextCacheBasics:
    """Basic cache operations."""

    @pytest.mark.unit
    def test_cache_creation(self):
        """ContextCache can be instantiated."""
        cache = ContextCache()
        assert cache is not None

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

    @pytest.mark.unit
    def test_clear_nonexistent_no_error(self, tmp_path):
        """clear() handles nonexistent file gracefully."""
        cache_file = tmp_path / "nonexistent.json"

        cache = ContextCache()
        # Should not raise
        cache.clear(cache_file)


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
        """load() handles invalid datetime strings."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"explored_at": "not-a-date"}')

        cache = ContextCache()
        result = cache.load(cache_file)

        # Should load but keep as string (not crash)
        assert result is not None
        assert result['explored_at'] == 'not-a-date'

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


class TestCacheIntegration:
    """Integration-style tests mimicking CodebaseContext usage."""

    @pytest.mark.unit
    def test_context_cache_format(self, tmp_path):
        """Cache format matches CodebaseContext expectations."""
        cache_file = tmp_path / ".llm_team_context.json"
        cache = ContextCache()

        # Simulate what CodebaseContext saves
        data = {
            'explored_at': datetime.now(),
            'summary': 'Python project with main.py and tests.',
            'structure': {
                'total_files': 10,
                'by_type': {'python': 5, 'config': 3, 'docs': 2},
                'has_readme': True,
                'has_requirements': True,
                'has_git': True
            },
            'file_index': {
                'python': ['main.py', 'src/utils.py'],
                'config': ['pyproject.toml', 'setup.cfg'],
                'docs': ['README.md']
            },
            'git_history': {
                'current_branch': 'main',
                'recent_commits': ['abc123 feat: add feature']
            }
        }

        cache.save(cache_file, data)
        loaded = cache.load(cache_file)

        assert loaded['summary'] == data['summary']
        assert loaded['structure']['total_files'] == 10
        assert loaded['file_index']['python'] == data['file_index']['python']
        assert isinstance(loaded['explored_at'], datetime)

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
