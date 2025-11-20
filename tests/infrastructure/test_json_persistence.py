"""
Tests for JSON persistence infrastructure.

Tests JSONPersistence for both synchronous and asynchronous operations,
error handling, and edge cases.
"""

import pytest
import json
import tempfile
from pathlib import Path

from src.infrastructure.persistence import JSONPersistence
from src.orchestrator.output import CapturingOutput


class TestJSONPersistenceLoad:
    """Test loading data from JSON files."""

    def test_load_returns_data_when_file_exists(self):
        """load() should return data when file exists and contains valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.json"
            file_path.write_text('{"key": "value", "number": 42}', encoding='utf-8')

            storage = JSONPersistence(str(file_path))
            data = storage.load()

            assert data is not None
            assert data == {"key": "value", "number": 42}

    def test_load_returns_none_when_file_missing(self):
        """load() should return None when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nonexistent.json"

            storage = JSONPersistence(str(file_path))
            data = storage.load()

            assert data is None

    def test_load_returns_none_on_corrupted_json(self):
        """load() should return None and log error when JSON is corrupted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "corrupted.json"
            file_path.write_text('{"key": invalid json}', encoding='utf-8')

            output = CapturingOutput()
            storage = JSONPersistence(str(file_path), output=output)
            data = storage.load()

            assert data is None
            errors = output.get_by_level('error')
            assert len(errors) == 1
            assert 'JSON decode failed' in errors[0]

    def test_load_handles_empty_file(self):
        """load() should return None when file is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.json"
            file_path.write_text('', encoding='utf-8')

            output = CapturingOutput()
            storage = JSONPersistence(str(file_path), output=output)
            data = storage.load()

            assert data is None
            errors = output.get_by_level('error')
            assert len(errors) == 1

    def test_load_handles_nested_data(self):
        """load() should handle complex nested data structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nested.json"
            nested_data = {
                "level1": {
                    "level2": {
                        "level3": ["item1", "item2"]
                    }
                },
                "list": [1, 2, 3]
            }
            file_path.write_text(json.dumps(nested_data), encoding='utf-8')

            storage = JSONPersistence(str(file_path))
            data = storage.load()

            assert data == nested_data


class TestJSONPersistenceSave:
    """Test saving data to JSON files."""

    def test_save_creates_file_with_data(self):
        """save() should create file with properly formatted JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "output.json"
            data = {"key": "value", "number": 42}

            storage = JSONPersistence(str(file_path))
            storage.save(data)

            assert file_path.exists()
            saved_data = json.loads(file_path.read_text(encoding='utf-8'))
            assert saved_data == data

    def test_save_creates_parent_directories(self):
        """save() should create parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "subdir1" / "subdir2" / "output.json"
            data = {"key": "value"}

            storage = JSONPersistence(str(file_path))
            storage.save(data)

            assert file_path.exists()
            assert file_path.parent.exists()
            saved_data = json.loads(file_path.read_text(encoding='utf-8'))
            assert saved_data == data

    def test_save_overwrites_existing_file(self):
        """save() should overwrite existing file with new data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "output.json"
            file_path.write_text('{"old": "data"}', encoding='utf-8')

            new_data = {"new": "data"}
            storage = JSONPersistence(str(file_path))
            storage.save(new_data)

            saved_data = json.loads(file_path.read_text(encoding='utf-8'))
            assert saved_data == new_data
            assert "old" not in saved_data

    def test_save_formats_with_indentation(self):
        """save() should format JSON with indentation for readability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "formatted.json"
            data = {"key": "value"}

            storage = JSONPersistence(str(file_path), indent=2)
            storage.save(data)

            content = file_path.read_text(encoding='utf-8')
            assert '\n' in content  # Has newlines (formatted)
            assert '  ' in content  # Has indentation

    def test_save_handles_empty_dict(self):
        """save() should handle empty dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.json"
            data = {}

            storage = JSONPersistence(str(file_path))
            storage.save(data)

            assert file_path.exists()
            saved_data = json.loads(file_path.read_text(encoding='utf-8'))
            assert saved_data == {}

    def test_save_handles_nested_data(self):
        """save() should handle complex nested data structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nested.json"
            nested_data = {
                "level1": {
                    "level2": {
                        "level3": ["item1", "item2"]
                    }
                },
                "list": [1, 2, 3],
                "null_value": None
            }

            storage = JSONPersistence(str(file_path))
            storage.save(nested_data)

            saved_data = json.loads(file_path.read_text(encoding='utf-8'))
            assert saved_data == nested_data


class TestJSONPersistenceRoundTrip:
    """Test save and load work together correctly."""

    def test_save_then_load_returns_same_data(self):
        """Saving data then loading it should return identical data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "roundtrip.json"
            original_data = {
                "string": "value",
                "number": 42,
                "float": 3.14,
                "bool": True,
                "null": None,
                "list": [1, 2, 3],
                "nested": {"key": "value"}
            }

            storage = JSONPersistence(str(file_path))
            storage.save(original_data)
            loaded_data = storage.load()

            assert loaded_data == original_data


class TestJSONPersistenceExists:
    """Test checking file existence."""

    def test_exists_returns_true_when_file_exists(self):
        """exists() should return True when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "exists.json"
            file_path.write_text('{}', encoding='utf-8')

            storage = JSONPersistence(str(file_path))

            assert storage.exists() is True

    def test_exists_returns_false_when_file_missing(self):
        """exists() should return False when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nonexistent.json"

            storage = JSONPersistence(str(file_path))

            assert storage.exists() is False


class TestJSONPersistenceClear:
    """Test clearing/deleting storage."""

    def test_clear_deletes_existing_file(self):
        """clear() should delete the file if it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "delete.json"
            file_path.write_text('{}', encoding='utf-8')

            storage = JSONPersistence(str(file_path))
            assert file_path.exists()

            storage.clear()

            assert not file_path.exists()

    def test_clear_does_nothing_when_file_missing(self):
        """clear() should not error when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nonexistent.json"

            storage = JSONPersistence(str(file_path))
            storage.clear()  # Should not raise error

            assert not file_path.exists()


class TestJSONPersistenceErrorHandling:
    """Test error handling and logging."""

    def test_load_logs_errors_via_output_interface(self):
        """load() should log errors via output interface."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "corrupted.json"
            file_path.write_text('invalid json', encoding='utf-8')

            output = CapturingOutput()
            storage = JSONPersistence(str(file_path), output=output)
            data = storage.load()

            assert data is None
            errors = output.get_by_level('error')
            assert len(errors) >= 1
            assert file_path.name in errors[0]

    def test_save_logs_errors_via_output_interface_on_failure(self):
        """save() should log errors when save fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a directory and try to save to it (should fail)
            dir_path = Path(tmpdir) / "somedir"
            dir_path.mkdir()

            output = CapturingOutput()
            storage = JSONPersistence(str(dir_path), output=output)
            storage.save({"key": "value"})

            errors = output.get_by_level('error')
            # Should log error when trying to write to a directory
            assert len(errors) >= 1


class TestJSONPersistenceConfiguration:
    """Test configuration options."""

    def test_custom_indent_is_used(self):
        """JSONPersistence should use custom indent setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "custom_indent.json"
            data = {"key": {"nested": "value"}}

            storage = JSONPersistence(str(file_path), indent=4)
            storage.save(data)

            content = file_path.read_text(encoding='utf-8')
            # 4-space indent means nested key has 4 spaces
            assert '    ' in content

    def test_custom_encoding_is_used(self):
        """JSONPersistence should use custom encoding setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "encoding.json"
            data = {"key": "value"}

            # Test with utf-8 (default)
            storage = JSONPersistence(str(file_path), encoding='utf-8')
            storage.save(data)

            loaded = storage.load()
            assert loaded == data


@pytest.mark.asyncio
class TestJSONPersistenceAsync:
    """Test asynchronous operations."""

    async def test_load_async_returns_data_when_file_exists(self):
        """load_async() should return data when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "async_test.json"
            file_path.write_text('{"key": "value"}', encoding='utf-8')

            storage = JSONPersistence(str(file_path))
            data = await storage.load_async()

            assert data == {"key": "value"}

    async def test_save_async_creates_file_with_data(self):
        """save_async() should create file with data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "async_output.json"
            data = {"async": "test"}

            storage = JSONPersistence(str(file_path))
            await storage.save_async(data)

            assert file_path.exists()
            saved_data = json.loads(file_path.read_text(encoding='utf-8'))
            assert saved_data == data

    async def test_async_round_trip(self):
        """Async save then async load should return same data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "async_roundtrip.json"
            original_data = {"async": True, "value": 123}

            storage = JSONPersistence(str(file_path))
            await storage.save_async(original_data)
            loaded_data = await storage.load_async()

            assert loaded_data == original_data

    async def test_clear_async_deletes_file(self):
        """clear_async() should delete the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "async_delete.json"
            file_path.write_text('{}', encoding='utf-8')

            storage = JSONPersistence(str(file_path))
            assert file_path.exists()

            await storage.clear_async()

            assert not file_path.exists()
