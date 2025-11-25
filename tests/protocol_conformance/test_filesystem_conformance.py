"""FileSystem protocol conformance tests.

Tests that file system implementations correctly conform to FileSystemProtocol.
"""

import pytest
import tempfile
import os

from tests.protocol_conformance.conftest import (
    assert_implements_protocol,
    assert_has_method,
)

from src.infrastructure.protocols import FileSystemProtocol


class TestRealFileSystemConformance:
    """Tests for RealFileSystem implementation."""

    def test_real_filesystem_implements_protocol(self):
        """RealFileSystem should implement FileSystemProtocol."""
        from src.infrastructure.file_system import RealFileSystem

        assert_implements_protocol(RealFileSystem, FileSystemProtocol)

    def test_real_filesystem_has_all_methods(self):
        """RealFileSystem should have all protocol methods."""
        from src.infrastructure.file_system import RealFileSystem

        methods = [
            'read_text', 'write_text', 'read_bytes', 'write_bytes',
            'exists', 'is_file', 'is_dir', 'mkdir', 'list_dir',
            'glob', 'delete', 'delete_tree', 'resolve', 'join_path'
        ]

        for method in methods:
            assert_has_method(RealFileSystem, method)


class TestInMemoryFileSystemConformance:
    """Tests for InMemoryFileSystem implementation."""

    def test_in_memory_filesystem_implements_protocol(self):
        """InMemoryFileSystem should implement FileSystemProtocol."""
        from src.infrastructure.file_system import InMemoryFileSystem

        assert_implements_protocol(InMemoryFileSystem, FileSystemProtocol)

    def test_in_memory_filesystem_has_all_methods(self):
        """InMemoryFileSystem should have all protocol methods."""
        from src.infrastructure.file_system import InMemoryFileSystem

        methods = [
            'read_text', 'write_text', 'read_bytes', 'write_bytes',
            'exists', 'is_file', 'is_dir', 'mkdir', 'list_dir',
            'glob', 'delete', 'delete_tree', 'resolve', 'join_path'
        ]

        for method in methods:
            assert_has_method(InMemoryFileSystem, method)


class TestRealFileSystemBehavior:
    """Tests that verify RealFileSystem behavior matches protocol contract."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as td:
            yield td

    @pytest.fixture
    def fs(self):
        """Create RealFileSystem instance."""
        from src.infrastructure.file_system import RealFileSystem
        return RealFileSystem()

    def test_write_and_read_text(self, fs, temp_dir):
        """write_text and read_text should work together."""
        file_path = os.path.join(temp_dir, "test.txt")

        fs.write_text(file_path, "hello world")
        content = fs.read_text(file_path)

        assert content == "hello world"

    def test_write_and_read_bytes(self, fs, temp_dir):
        """write_bytes and read_bytes should work together."""
        file_path = os.path.join(temp_dir, "test.bin")

        fs.write_bytes(file_path, b"\x00\x01\x02")
        content = fs.read_bytes(file_path)

        assert content == b"\x00\x01\x02"

    def test_exists_returns_true_for_existing(self, fs, temp_dir):
        """exists() should return True for existing paths."""
        file_path = os.path.join(temp_dir, "test.txt")
        fs.write_text(file_path, "content")

        assert fs.exists(file_path) is True
        assert fs.exists(temp_dir) is True

    def test_exists_returns_false_for_missing(self, fs, temp_dir):
        """exists() should return False for non-existent paths."""
        file_path = os.path.join(temp_dir, "nonexistent.txt")

        assert fs.exists(file_path) is False

    def test_is_file_returns_true_for_file(self, fs, temp_dir):
        """is_file() should return True for files."""
        file_path = os.path.join(temp_dir, "test.txt")
        fs.write_text(file_path, "content")

        assert fs.is_file(file_path) is True

    def test_is_file_returns_false_for_dir(self, fs, temp_dir):
        """is_file() should return False for directories."""
        assert fs.is_file(temp_dir) is False

    def test_is_dir_returns_true_for_dir(self, fs, temp_dir):
        """is_dir() should return True for directories."""
        assert fs.is_dir(temp_dir) is True

    def test_is_dir_returns_false_for_file(self, fs, temp_dir):
        """is_dir() should return False for files."""
        file_path = os.path.join(temp_dir, "test.txt")
        fs.write_text(file_path, "content")

        assert fs.is_dir(file_path) is False

    def test_mkdir_creates_directory(self, fs, temp_dir):
        """mkdir() should create a directory."""
        dir_path = os.path.join(temp_dir, "new_dir")

        fs.mkdir(dir_path)

        assert fs.is_dir(dir_path) is True

    def test_mkdir_with_parents(self, fs, temp_dir):
        """mkdir(parents=True) should create parent directories."""
        dir_path = os.path.join(temp_dir, "a", "b", "c")

        fs.mkdir(dir_path, parents=True)

        assert fs.is_dir(dir_path) is True

    def test_list_dir_returns_names(self, fs, temp_dir):
        """list_dir() should return file/dir names."""
        fs.write_text(os.path.join(temp_dir, "file1.txt"), "content")
        fs.write_text(os.path.join(temp_dir, "file2.txt"), "content")
        fs.mkdir(os.path.join(temp_dir, "subdir"))

        contents = fs.list_dir(temp_dir)

        assert set(contents) == {"file1.txt", "file2.txt", "subdir"}

    def test_delete_removes_file(self, fs, temp_dir):
        """delete() should remove files."""
        file_path = os.path.join(temp_dir, "test.txt")
        fs.write_text(file_path, "content")

        fs.delete(file_path)

        assert fs.exists(file_path) is False

    def test_delete_tree_removes_directory(self, fs, temp_dir):
        """delete_tree() should remove directory and contents."""
        dir_path = os.path.join(temp_dir, "to_delete")
        fs.mkdir(dir_path)
        fs.write_text(os.path.join(dir_path, "file.txt"), "content")

        fs.delete_tree(dir_path)

        assert fs.exists(dir_path) is False

    def test_resolve_returns_absolute(self, fs):
        """resolve() should return absolute path."""
        result = fs.resolve("relative/path")

        assert os.path.isabs(result)

    def test_join_path_combines_parts(self, fs):
        """join_path() should combine path parts."""
        result = fs.join_path("a", "b", "c")

        assert "a" in result
        assert "b" in result
        assert "c" in result


class TestInMemoryFileSystemBehavior:
    """Tests that verify InMemoryFileSystem behavior matches protocol contract."""

    @pytest.fixture
    def fs(self):
        """Create InMemoryFileSystem instance."""
        from src.infrastructure.file_system import InMemoryFileSystem
        return InMemoryFileSystem()

    def test_write_and_read_text(self, fs):
        """write_text and read_text should work together."""
        fs.write_text("/test.txt", "hello world")
        content = fs.read_text("/test.txt")

        assert content == "hello world"

    def test_write_and_read_bytes(self, fs):
        """write_bytes and read_bytes should work together."""
        fs.write_bytes("/test.bin", b"\x00\x01\x02")
        content = fs.read_bytes("/test.bin")

        assert content == b"\x00\x01\x02"

    def test_exists_returns_true_for_existing(self, fs):
        """exists() should return True for existing paths."""
        fs.write_text("/test.txt", "content")

        assert fs.exists("/test.txt") is True
        assert fs.exists("/") is True  # Root always exists

    def test_exists_returns_false_for_missing(self, fs):
        """exists() should return False for non-existent paths."""
        assert fs.exists("/nonexistent.txt") is False

    def test_is_file_returns_true_for_file(self, fs):
        """is_file() should return True for files."""
        fs.write_text("/test.txt", "content")

        assert fs.is_file("/test.txt") is True

    def test_is_file_returns_false_for_dir(self, fs):
        """is_file() should return False for directories."""
        fs.mkdir("/mydir")

        assert fs.is_file("/mydir") is False

    def test_is_dir_returns_true_for_dir(self, fs):
        """is_dir() should return True for directories."""
        fs.mkdir("/mydir")

        assert fs.is_dir("/mydir") is True

    def test_is_dir_returns_false_for_file(self, fs):
        """is_dir() should return False for files."""
        fs.write_text("/test.txt", "content")

        assert fs.is_dir("/test.txt") is False

    def test_mkdir_creates_directory(self, fs):
        """mkdir() should create a directory."""
        fs.mkdir("/new_dir")

        assert fs.is_dir("/new_dir") is True

    def test_mkdir_with_parents(self, fs):
        """mkdir(parents=True) should create parent directories."""
        fs.mkdir("/a/b/c", parents=True)

        assert fs.is_dir("/a/b/c") is True
        assert fs.is_dir("/a/b") is True
        assert fs.is_dir("/a") is True

    def test_list_dir_returns_names(self, fs):
        """list_dir() should return file/dir names."""
        fs.write_text("/file1.txt", "content")
        fs.write_text("/file2.txt", "content")
        fs.mkdir("/subdir")

        contents = fs.list_dir("/")

        assert set(contents) == {"file1.txt", "file2.txt", "subdir"}

    def test_delete_removes_file(self, fs):
        """delete() should remove files."""
        fs.write_text("/test.txt", "content")

        fs.delete("/test.txt")

        assert fs.exists("/test.txt") is False

    def test_delete_tree_removes_directory(self, fs):
        """delete_tree() should remove directory and contents."""
        fs.mkdir("/to_delete")
        fs.write_text("/to_delete/file.txt", "content")

        fs.delete_tree("/to_delete")

        assert fs.exists("/to_delete") is False

    def test_resolve_returns_normalized(self, fs):
        """resolve() should return normalized absolute path."""
        result = fs.resolve("relative/path")

        assert result.startswith("/")

    def test_join_path_combines_parts(self, fs):
        """join_path() should combine path parts."""
        result = fs.join_path("/a", "b", "c")

        assert "/a" in result or "a" in result
        assert "b" in result
        assert "c" in result

    def test_read_nonexistent_raises_error(self, fs):
        """read_text() should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            fs.read_text("/nonexistent.txt")

    def test_list_dir_nonexistent_raises_error(self, fs):
        """list_dir() should raise FileNotFoundError for missing directories."""
        with pytest.raises(FileNotFoundError):
            fs.list_dir("/nonexistent")

    def test_list_dir_on_file_raises_error(self, fs):
        """list_dir() should raise NotADirectoryError for files."""
        fs.write_text("/file.txt", "content")

        with pytest.raises(NotADirectoryError):
            fs.list_dir("/file.txt")

    def test_clear_removes_all(self, fs):
        """clear() should remove all files and directories."""
        fs.write_text("/a.txt", "content")
        fs.mkdir("/dir")
        fs.write_text("/dir/b.txt", "content")

        fs.clear()

        assert fs.exists("/a.txt") is False
        assert fs.exists("/dir") is False
        # Root should still exist
        assert fs.is_dir("/") is True
