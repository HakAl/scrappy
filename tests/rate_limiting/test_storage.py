"""Tests for rate limit storage."""
import json
from pathlib import Path
import pytest

from scrappy.orchestrator.rate_limiting.storage import RateLimitStorage
from tests.helpers import FakeFileSystem


def test_load_returns_empty_dict_when_file_not_exists():
    """Should return empty dict when file doesn't exist."""
    fs = FakeFileSystem()
    storage = RateLimitStorage(Path("/data.json"), fs)

    result = storage.load()

    assert result == {}


def test_load_returns_data_when_file_exists():
    """Should return parsed JSON when file exists."""
    fs = FakeFileSystem()
    path = Path("/data.json")
    data = {"providers": {"openai": {}}}
    fs.write_text(path, json.dumps(data))

    storage = RateLimitStorage(path, fs)
    result = storage.load()

    assert result == data


def test_load_returns_empty_dict_when_file_corrupted():
    """Should return empty dict when JSON is invalid."""
    fs = FakeFileSystem()
    path = Path("/data.json")
    fs.write_text(path, "invalid json{")

    storage = RateLimitStorage(path, fs)
    result = storage.load()

    assert result == {}


def test_save_writes_json_to_file():
    """Should write formatted JSON to file."""
    fs = FakeFileSystem()
    path = Path("/data/usage.json")
    storage = RateLimitStorage(path, fs)

    data = {"providers": {"openai": {"gpt-4": {"requests_today": 5}}}}
    storage.save(data)

    saved_content = fs.read_text(path)
    assert json.loads(saved_content) == data


def test_save_creates_parent_directory():
    """Should create parent directories if they don't exist."""
    fs = FakeFileSystem()
    path = Path("/data/subdir/usage.json")
    storage = RateLimitStorage(path, fs)

    storage.save({"test": "data"})

    assert fs.exists(Path("/data"))
    assert fs.exists(Path("/data/subdir"))


def test_save_does_nothing_when_path_is_none():
    """Should not save when path is None."""
    fs = FakeFileSystem()
    storage = RateLimitStorage(None, fs)

    storage.save({"test": "data"})

    # Should not raise, should not write anything
    assert len(fs._files) == 0


def test_load_returns_empty_when_path_is_none():
    """Should return empty dict when path is None."""
    fs = FakeFileSystem()
    storage = RateLimitStorage(None, fs)

    result = storage.load()

    assert result == {}
