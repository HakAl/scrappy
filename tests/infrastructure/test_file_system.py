"""
Tests for file system implementations.

Tests both RealFileSystem and InMemoryFileSystem to ensure they:
1. Follow the FileSystemProtocol contract
2. Handle edge cases correctly
3. Raise appropriate errors
4. Provide consistent behavior

These tests prove the features work, not just that code runs.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.infrastructure import RealFileSystem, InMemoryFileSystem


class TestRealFileSystem:
    """Tests for RealFileSystem using actual (temporary) file I/O."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def fs(self):
        """Create RealFileSystem instance."""
        return RealFileSystem()

    def test_write_and_read_text(self, fs, temp_dir):
        """Writing text and reading it back returns the same content."""
        file_path = str(Path(temp_dir) / "test.txt")
        content = "Hello, World!"

        fs.write_text(file_path, content)
        result = fs.read_text(file_path)

        assert result == content

    def test_write_text_creates_parent_directories(self, fs, temp_dir):
        """Writing to nested path creates parent directories automatically."""
        file_path = str(Path(temp_dir) / "sub" / "dir" / "test.txt")
        content = "nested file"

        fs.write_text(file_path, content)

        assert fs.exists(file_path)
        assert fs.read_text(file_path) == content

    def test_write_and_read_bytes(self, fs, temp_dir):
        """Writing bytes and reading them back returns the same content."""
        file_path = str(Path(temp_dir) / "binary.dat")
        content = b"\x00\x01\x02\x03\xFF"

        fs.write_bytes(file_path, content)
        result = fs.read_bytes(file_path)

        assert result == content

    def test_read_text_nonexistent_file_raises_error(self, fs, temp_dir):
        """Reading nonexistent file raises FileNotFoundError."""
        file_path = str(Path(temp_dir) / "nonexistent.txt")

        with pytest.raises(FileNotFoundError):
            fs.read_text(file_path)

    def test_read_bytes_nonexistent_file_raises_error(self, fs, temp_dir):
        """Reading nonexistent binary file raises FileNotFoundError."""
        file_path = str(Path(temp_dir) / "nonexistent.dat")

        with pytest.raises(FileNotFoundError):
            fs.read_bytes(file_path)

    def test_exists_returns_true_for_file(self, fs, temp_dir):
        """exists() returns True for existing file."""
        file_path = str(Path(temp_dir) / "exists.txt")
        fs.write_text(file_path, "content")

        assert fs.exists(file_path) is True

    def test_exists_returns_true_for_directory(self, fs, temp_dir):
        """exists() returns True for existing directory."""
        dir_path = str(Path(temp_dir) / "subdir")
        fs.mkdir(dir_path)

        assert fs.exists(dir_path) is True

    def test_exists_returns_false_for_nonexistent(self, fs, temp_dir):
        """exists() returns False for nonexistent path."""
        file_path = str(Path(temp_dir) / "nope.txt")

        assert fs.exists(file_path) is False

    def test_is_file_returns_true_for_file(self, fs, temp_dir):
        """is_file() returns True only for files."""
        file_path = str(Path(temp_dir) / "file.txt")
        fs.write_text(file_path, "content")

        assert fs.is_file(file_path) is True

    def test_is_file_returns_false_for_directory(self, fs, temp_dir):
        """is_file() returns False for directories."""
        dir_path = str(Path(temp_dir) / "subdir")
        fs.mkdir(dir_path)

        assert fs.is_file(dir_path) is False

    def test_is_dir_returns_true_for_directory(self, fs, temp_dir):
        """is_dir() returns True only for directories."""
        dir_path = str(Path(temp_dir) / "subdir")
        fs.mkdir(dir_path)

        assert fs.is_dir(dir_path) is True

    def test_is_dir_returns_false_for_file(self, fs, temp_dir):
        """is_dir() returns False for files."""
        file_path = str(Path(temp_dir) / "file.txt")
        fs.write_text(file_path, "content")

        assert fs.is_dir(file_path) is False

    def test_mkdir_creates_directory(self, fs, temp_dir):
        """mkdir() creates a directory that can be detected."""
        dir_path = str(Path(temp_dir) / "newdir")

        fs.mkdir(dir_path)

        assert fs.exists(dir_path)
        assert fs.is_dir(dir_path)

    def test_mkdir_with_parents_creates_nested_dirs(self, fs, temp_dir):
        """mkdir with parents=True creates nested directories."""
        dir_path = str(Path(temp_dir) / "a" / "b" / "c")

        fs.mkdir(dir_path, parents=True)

        assert fs.exists(dir_path)
        assert fs.is_dir(dir_path)

    def test_mkdir_without_parents_raises_error_for_nested(self, fs, temp_dir):
        """mkdir without parents=True raises error for nested path."""
        dir_path = str(Path(temp_dir) / "a" / "b" / "c")

        with pytest.raises(FileNotFoundError):
            fs.mkdir(dir_path, parents=False)

    def test_mkdir_with_exist_ok_does_not_raise_if_exists(self, fs, temp_dir):
        """mkdir with exist_ok=True doesn't raise if directory exists."""
        dir_path = str(Path(temp_dir) / "existing")
        fs.mkdir(dir_path)

        fs.mkdir(dir_path, exist_ok=True)  # Should not raise

    def test_mkdir_without_exist_ok_raises_if_exists(self, fs, temp_dir):
        """mkdir without exist_ok raises if directory exists."""
        dir_path = str(Path(temp_dir) / "existing")
        fs.mkdir(dir_path)

        with pytest.raises(FileExistsError):
            fs.mkdir(dir_path, exist_ok=False)

    def test_list_dir_returns_directory_contents(self, fs, temp_dir):
        """list_dir() returns names of files and directories."""
        fs.write_text(str(Path(temp_dir) / "file1.txt"), "a")
        fs.write_text(str(Path(temp_dir) / "file2.txt"), "b")
        fs.mkdir(str(Path(temp_dir) / "subdir"))

        contents = fs.list_dir(temp_dir)

        assert "file1.txt" in contents
        assert "file2.txt" in contents
        assert "subdir" in contents
        assert len(contents) == 3

    def test_list_dir_nonexistent_raises_error(self, fs, temp_dir):
        """list_dir() on nonexistent directory raises FileNotFoundError."""
        dir_path = str(Path(temp_dir) / "nonexistent")

        with pytest.raises(FileNotFoundError):
            fs.list_dir(dir_path)

    def test_list_dir_on_file_raises_error(self, fs, temp_dir):
        """list_dir() on file raises NotADirectoryError."""
        file_path = str(Path(temp_dir) / "file.txt")
        fs.write_text(file_path, "content")

        with pytest.raises(NotADirectoryError):
            fs.list_dir(file_path)

    def test_delete_removes_file(self, fs, temp_dir):
        """delete() removes file."""
        file_path = str(Path(temp_dir) / "delete_me.txt")
        fs.write_text(file_path, "content")

        fs.delete(file_path)

        assert not fs.exists(file_path)

    def test_delete_removes_empty_directory(self, fs, temp_dir):
        """delete() removes empty directory."""
        dir_path = str(Path(temp_dir) / "empty_dir")
        fs.mkdir(dir_path)

        fs.delete(dir_path)

        assert not fs.exists(dir_path)

    def test_delete_nonexistent_raises_error(self, fs, temp_dir):
        """delete() on nonexistent path raises FileNotFoundError."""
        file_path = str(Path(temp_dir) / "nonexistent.txt")

        with pytest.raises(FileNotFoundError):
            fs.delete(file_path)

    def test_delete_nonempty_directory_raises_error(self, fs, temp_dir):
        """delete() on non-empty directory raises OSError."""
        dir_path = str(Path(temp_dir) / "nonempty")
        fs.mkdir(dir_path)
        fs.write_text(str(Path(dir_path) / "file.txt"), "content")

        with pytest.raises(OSError):
            fs.delete(dir_path)

    def test_delete_tree_removes_directory_and_contents(self, fs, temp_dir):
        """delete_tree() removes directory with all contents."""
        dir_path = str(Path(temp_dir) / "tree")
        fs.mkdir(dir_path, parents=True)
        fs.write_text(str(Path(dir_path) / "file1.txt"), "a")
        fs.mkdir(str(Path(dir_path) / "subdir"), parents=True)
        fs.write_text(str(Path(dir_path) / "subdir" / "file2.txt"), "b")

        fs.delete_tree(dir_path)

        assert not fs.exists(dir_path)

    def test_delete_tree_nonexistent_raises_error(self, fs, temp_dir):
        """delete_tree() on nonexistent directory raises FileNotFoundError."""
        dir_path = str(Path(temp_dir) / "nonexistent")

        with pytest.raises(FileNotFoundError):
            fs.delete_tree(dir_path)

    def test_resolve_returns_absolute_path(self, fs):
        """resolve() returns absolute path."""
        result = fs.resolve("relative/path.txt")

        assert Path(result).is_absolute()

    def test_text_encoding_utf8(self, fs, temp_dir):
        """Text files use UTF-8 encoding by default."""
        file_path = str(Path(temp_dir) / "unicode.txt")
        content = "Hello 世界 🌍"

        fs.write_text(file_path, content)
        result = fs.read_text(file_path)

        assert result == content


class TestInMemoryFileSystem:
    """Tests for InMemoryFileSystem using in-memory storage."""

    @pytest.fixture
    def fs(self):
        """Create InMemoryFileSystem instance."""
        return InMemoryFileSystem()

    def test_write_and_read_text(self, fs):
        """Writing text and reading it back returns the same content."""
        content = "Hello, World!"

        fs.write_text("/test.txt", content)
        result = fs.read_text("/test.txt")

        assert result == content

    def test_write_text_creates_parent_directories(self, fs):
        """Writing to nested path creates parent directories automatically."""
        content = "nested file"

        fs.write_text("/sub/dir/test.txt", content)

        assert fs.exists("/sub/dir/test.txt")
        assert fs.read_text("/sub/dir/test.txt") == content

    def test_write_and_read_bytes(self, fs):
        """Writing bytes and reading them back returns the same content."""
        content = b"\x00\x01\x02\x03\xFF"

        fs.write_bytes("/binary.dat", content)
        result = fs.read_bytes("/binary.dat")

        assert result == content

    def test_read_text_nonexistent_file_raises_error(self, fs):
        """Reading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fs.read_text("/nonexistent.txt")

    def test_read_bytes_nonexistent_file_raises_error(self, fs):
        """Reading nonexistent binary file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fs.read_bytes("/nonexistent.dat")

    def test_exists_returns_true_for_file(self, fs):
        """exists() returns True for existing file."""
        fs.write_text("/exists.txt", "content")

        assert fs.exists("/exists.txt") is True

    def test_exists_returns_true_for_directory(self, fs):
        """exists() returns True for existing directory."""
        fs.mkdir("/subdir")

        assert fs.exists("/subdir") is True

    def test_exists_returns_false_for_nonexistent(self, fs):
        """exists() returns False for nonexistent path."""
        assert fs.exists("/nope.txt") is False

    def test_is_file_returns_true_for_file(self, fs):
        """is_file() returns True only for files."""
        fs.write_text("/file.txt", "content")

        assert fs.is_file("/file.txt") is True

    def test_is_file_returns_false_for_directory(self, fs):
        """is_file() returns False for directories."""
        fs.mkdir("/subdir")

        assert fs.is_file("/subdir") is False

    def test_is_dir_returns_true_for_directory(self, fs):
        """is_dir() returns True only for directories."""
        fs.mkdir("/subdir")

        assert fs.is_dir("/subdir") is True

    def test_is_dir_returns_false_for_file(self, fs):
        """is_dir() returns False for files."""
        fs.write_text("/file.txt", "content")

        assert fs.is_dir("/file.txt") is False

    def test_root_directory_exists_by_default(self, fs):
        """Root directory (/) exists by default."""
        assert fs.exists("/")
        assert fs.is_dir("/")

    def test_mkdir_creates_directory(self, fs):
        """mkdir() creates a directory that can be detected."""
        fs.mkdir("/newdir")

        assert fs.exists("/newdir")
        assert fs.is_dir("/newdir")

    def test_mkdir_with_parents_creates_nested_dirs(self, fs):
        """mkdir with parents=True creates nested directories."""
        fs.mkdir("/a/b/c", parents=True)

        assert fs.exists("/a/b/c")
        assert fs.is_dir("/a/b/c")
        assert fs.is_dir("/a/b")
        assert fs.is_dir("/a")

    def test_mkdir_without_parents_raises_error_for_nested(self, fs):
        """mkdir without parents=True raises error for nested path."""
        with pytest.raises(FileNotFoundError):
            fs.mkdir("/a/b/c", parents=False)

    def test_mkdir_with_exist_ok_does_not_raise_if_exists(self, fs):
        """mkdir with exist_ok=True doesn't raise if directory exists."""
        fs.mkdir("/existing")

        fs.mkdir("/existing", exist_ok=True)  # Should not raise

    def test_mkdir_without_exist_ok_raises_if_exists(self, fs):
        """mkdir without exist_ok raises if directory exists."""
        fs.mkdir("/existing")

        with pytest.raises(FileExistsError):
            fs.mkdir("/existing", exist_ok=False)

    def test_mkdir_raises_if_path_exists_as_file(self, fs):
        """mkdir raises error if path exists as file."""
        fs.write_text("/file.txt", "content")

        with pytest.raises(FileExistsError):
            fs.mkdir("/file.txt")

    def test_list_dir_returns_directory_contents(self, fs):
        """list_dir() returns names of files and directories."""
        fs.write_text("/dir/file1.txt", "a")
        fs.write_text("/dir/file2.txt", "b")
        fs.mkdir("/dir/subdir")

        contents = fs.list_dir("/dir")

        assert "file1.txt" in contents
        assert "file2.txt" in contents
        assert "subdir" in contents
        assert len(contents) == 3

    def test_list_dir_returns_only_immediate_children(self, fs):
        """list_dir() returns only immediate children, not nested."""
        fs.write_text("/dir/file.txt", "a")
        fs.write_text("/dir/sub/nested.txt", "b")

        contents = fs.list_dir("/dir")

        assert "file.txt" in contents
        assert "sub" in contents
        assert "nested.txt" not in contents

    def test_list_dir_nonexistent_raises_error(self, fs):
        """list_dir() on nonexistent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fs.list_dir("/nonexistent")

    def test_list_dir_on_file_raises_error(self, fs):
        """list_dir() on file raises NotADirectoryError."""
        fs.write_text("/file.txt", "content")

        with pytest.raises(NotADirectoryError):
            fs.list_dir("/file.txt")

    def test_delete_removes_file(self, fs):
        """delete() removes file."""
        fs.write_text("/delete_me.txt", "content")

        fs.delete("/delete_me.txt")

        assert not fs.exists("/delete_me.txt")

    def test_delete_removes_empty_directory(self, fs):
        """delete() removes empty directory."""
        fs.mkdir("/empty_dir")

        fs.delete("/empty_dir")

        assert not fs.exists("/empty_dir")

    def test_delete_nonexistent_raises_error(self, fs):
        """delete() on nonexistent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fs.delete("/nonexistent.txt")

    def test_delete_nonempty_directory_raises_error(self, fs):
        """delete() on non-empty directory raises OSError."""
        fs.mkdir("/nonempty")
        fs.write_text("/nonempty/file.txt", "content")

        with pytest.raises(OSError):
            fs.delete("/nonempty")

    def test_delete_tree_removes_directory_and_contents(self, fs):
        """delete_tree() removes directory with all contents."""
        fs.write_text("/tree/file1.txt", "a")
        fs.write_text("/tree/subdir/file2.txt", "b")

        fs.delete_tree("/tree")

        assert not fs.exists("/tree")
        assert not fs.exists("/tree/file1.txt")
        assert not fs.exists("/tree/subdir")

    def test_delete_tree_nonexistent_raises_error(self, fs):
        """delete_tree() on nonexistent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fs.delete_tree("/nonexistent")

    def test_delete_tree_on_file_raises_error(self, fs):
        """delete_tree() on file raises NotADirectoryError."""
        fs.write_text("/file.txt", "content")

        with pytest.raises(NotADirectoryError):
            fs.delete_tree("/file.txt")

    def test_resolve_returns_absolute_path(self, fs):
        """resolve() returns absolute path."""
        result = fs.resolve("relative/path.txt")

        assert result.startswith("/")

    def test_resolve_normalizes_path(self, fs):
        """resolve() normalizes path format."""
        result = fs.resolve("a/./b/../c")

        assert "/c" in result

    def test_text_encoding_utf8(self, fs):
        """Text files use UTF-8 encoding by default."""
        content = "Hello 世界 🌍"

        fs.write_text("/unicode.txt", content)
        result = fs.read_text("/unicode.txt")

        assert result == content

    def test_relative_paths_converted_to_absolute(self, fs):
        """Relative paths are converted to absolute."""
        fs.write_text("relative.txt", "content")

        assert fs.exists("/relative.txt")

    def test_glob_basic_wildcard(self, fs):
        """glob() matches files with basic wildcards."""
        fs.write_text("/test1.txt", "a")
        fs.write_text("/test2.txt", "b")
        fs.write_text("/other.md", "c")

        results = fs.glob("/test*.txt")

        assert "/test1.txt" in results
        assert "/test2.txt" in results
        assert "/other.md" not in results

    def test_clear_removes_all_files(self, fs):
        """clear() removes all files and directories."""
        fs.write_text("/file1.txt", "a")
        fs.write_text("/dir/file2.txt", "b")

        fs.clear()

        assert not fs.exists("/file1.txt")
        assert not fs.exists("/dir/file2.txt")
        assert fs.exists("/")  # Root still exists


class TestFileSystemContract:
    """
    Tests that both implementations follow the same contract.

    These tests prove that implementations are interchangeable.
    """

    @pytest.fixture(params=["real", "memory"])
    def fs(self, request, tmp_path):
        """Parametrized fixture providing both file system implementations."""
        if request.param == "real":
            return RealFileSystem(), str(tmp_path)
        else:
            return InMemoryFileSystem(), ""

    def test_write_read_roundtrip(self, fs):
        """Both implementations support write/read roundtrip."""
        file_system, base_path = fs
        path = f"{base_path}/test.txt" if base_path else "/test.txt"
        content = "test content"

        file_system.write_text(path, content)
        result = file_system.read_text(path)

        assert result == content

    def test_exists_behavior(self, fs):
        """Both implementations have consistent exists() behavior."""
        file_system, base_path = fs
        path = f"{base_path}/file.txt" if base_path else "/file.txt"

        assert file_system.exists(path) is False
        file_system.write_text(path, "content")
        assert file_system.exists(path) is True

    def test_directory_creation(self, fs):
        """Both implementations support directory creation."""
        file_system, base_path = fs
        path = f"{base_path}/newdir" if base_path else "/newdir"

        file_system.mkdir(path)

        assert file_system.is_dir(path) is True
        assert file_system.is_file(path) is False

    def test_list_directory(self, fs):
        """Both implementations support directory listing."""
        file_system, base_path = fs
        dir_path = f"{base_path}/dir" if base_path else "/dir"
        file_system.mkdir(dir_path, parents=True, exist_ok=True)
        file_system.write_text(f"{dir_path}/file.txt", "content")

        contents = file_system.list_dir(dir_path)

        assert "file.txt" in contents
