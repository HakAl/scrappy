import pytest
import re
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Import the class to test
from src.platform.fallback import PythonCommandFallbackImpl


class TestPythonCommandFallbackImpl:
    """Comprehensive test suite for PythonCommandFallbackImpl."""

    @pytest.fixture
    def fallback(self):
        """Create a fresh fallback instance for each test."""
        return PythonCommandFallbackImpl()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory with test files."""
        # Create test directory structure
        (tmp_path / "subdir").mkdir()
        (tmp_path / "empty_file.txt").write_text("")
        (tmp_path / "test_file.txt").write_text("Hello\nWorld\nTest")
        (tmp_path / "special_chars.txt").write_text("Hello!@#$%^&*()\nLine2")
        (tmp_path / "subdir" / "nested_file.txt").write_text("Nested content")
        (tmp_path / ".hidden_file").write_text("Hidden content")

        # Create binary-like file
        binary_file = tmp_path / "binary_like.txt"
        binary_file.write_bytes(b"Hello\x00World\xFF\xFE")

        return tmp_path

    def test_ls_basic_directory_listing(self, fallback, temp_dir):
        """Test basic ls functionality."""
        result = fallback.ls([], temp_dir)

        assert result['returncode'] == 0
        assert result['used_fallback'] == True
        assert 'empty_file.txt' in result['output']
        assert 'test_file.txt' in result['output']
        assert 'subdir' in result['output']
        assert '.hidden_file' not in result['output']  # Hidden files not shown by default

    def test_ls_show_all_files(self, fallback, temp_dir):
        """Test ls with -a flag to show hidden files."""
        result = fallback.ls(['-a'], temp_dir)

        assert result['returncode'] == 0
        assert '.hidden_file' in result['output']

    def test_ls_long_format(self, fallback, temp_dir):
        """Test ls with -l flag for long format."""
        result = fallback.ls(['-l'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        for line in lines:
            if line.strip():
                # Should contain file permissions, size, date, and name
                assert 'user' in line
                assert any(char.isdigit() for char in line)

    def test_ls_specific_file(self, fallback, temp_dir):
        """Test ls with specific file argument."""
        result = fallback.ls(['test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert result['output'] == 'test_file.txt'

    def test_ls_nonexistent_file(self, fallback, temp_dir):
        """Test ls with nonexistent file."""
        result = fallback.ls(['nonexistent.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_cat_single_file(self, fallback, temp_dir):
        """Test cat with single file."""
        result = fallback.cat(['test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert result['output'] == 'Hello\nWorld\nTest'

    def test_cat_multiple_files(self, fallback, temp_dir):
        """Test cat with multiple files."""
        result = fallback.cat(['test_file.txt', 'empty_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Hello\nWorld\nTest' in result['output']

    def test_cat_nonexistent_file(self, fallback, temp_dir):
        """Test cat with nonexistent file."""
        result = fallback.cat(['nonexistent.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_cat_no_arguments(self, fallback, temp_dir):
        """Test cat without arguments."""
        result = fallback.cat([], temp_dir)

        assert result['returncode'] == 1
        assert 'missing file operand' in result['output']

    def test_grep_basic_pattern(self, fallback, temp_dir):
        """Test basic grep functionality."""
        result = fallback.grep(['Hello', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Hello' in result['output']

    def test_grep_case_insensitive(self, fallback, temp_dir):
        """Test grep with -i flag."""
        result = fallback.grep(['-i', 'hello', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Hello' in result['output']

    def test_grep_line_numbers(self, fallback, temp_dir):
        """Test grep with -n flag."""
        result = fallback.grep(['-n', 'Hello', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert '1:Hello' in result['output']

    def test_grep_invert_match(self, fallback, temp_dir):
        """Test grep with -v flag."""
        result = fallback.grep(['-v', 'Hello', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Hello' not in result['output']
        assert 'World' in result['output']

    def test_grep_recursive(self, fallback, temp_dir):
        """Test grep with -r flag."""
        result = fallback.grep(['-r', 'content', '.'], temp_dir)

        assert result['returncode'] == 0
        assert 'content' in result['output']

    def test_grep_invalid_pattern(self, fallback, temp_dir):
        """Test grep with invalid regex pattern."""
        result = fallback.grep(['[invalid', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'invalid pattern' in result['output']

# todo
    # def test_find_basic(self, fallback, temp_dir):
    #     """Test basic find functionality."""
    #     result = fallback.find([], temp_dir)
    #
    #     assert result['returncode'] == 0
    #     assert 'test_file.txt' in result['output']
    #     assert 'subdir/nested_file.txt' in result['output']

    def test_find_name_pattern(self, fallback, temp_dir):
        """Test find with name pattern."""
        result = fallback.find(['-name', '*.txt'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        assert any(line.endswith('.txt') for line in lines if line)

    def test_find_type_file(self, fallback, temp_dir):
        """Test find with type filter for files."""
        result = fallback.find(['-type', 'f'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        for line in lines:
            if line.strip():
                assert not line.endswith('/')  # Should not be directories

    def test_find_type_directory(self, fallback, temp_dir):
        """Test find with type filter for directories."""
        result = fallback.find(['-type', 'd'], temp_dir)

        assert result['returncode'] == 0
        assert 'subdir' in result['output']

    def test_wc_basic(self, fallback, temp_dir):
        """Test basic wc functionality."""
        result = fallback.wc(['test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        # Should show lines, words, chars, filename
        assert 'test_file.txt' in result['output']
        lines = result['output'].split()
        assert len(lines) >= 3  # At least lines, words, filename

    def test_wc_lines_only(self, fallback, temp_dir):
        """Test wc with -l flag."""
        result = fallback.wc(['-l', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        # Should show 3 lines (Hello, World, Test)
        assert '3' in result['output']

    def test_wc_words_only(self, fallback, temp_dir):
        """Test wc with -w flag."""
        result = fallback.wc(['-w', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        # Should show 3 words (Hello, World, Test)
        assert '3' in result['output']

    def test_wc_multiple_files(self, fallback, temp_dir):
        """Test wc with multiple files."""
        result = fallback.wc(['test_file.txt', 'empty_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'total' in result['output']

    def test_wc_nonexistent_file(self, fallback, temp_dir):
        """Test wc with nonexistent file."""
        result = fallback.wc(['nonexistent.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_head_basic(self, fallback, temp_dir):
        """Test basic head functionality."""
        result = fallback.head(['test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        assert len(lines) <= 10  # Default is 10 lines

    def test_head_specific_lines(self, fallback, temp_dir):
        """Test head with specific number of lines."""
        result = fallback.head(['-n', '2', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        assert len(lines) == 2
        assert 'Hello' in lines[0]
        assert 'World' in lines[1]

    def test_head_multiple_files(self, fallback, temp_dir):
        """Test head with multiple files."""
        result = fallback.head(['-n', '1', 'test_file.txt', 'empty_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert '==> test_file.txt <==' in result['output']
        assert 'Hello' in result['output']

    def test_head_nonexistent_file(self, fallback, temp_dir):
        """Test head with nonexistent file."""
        result = fallback.head(['nonexistent.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_tail_basic(self, fallback, temp_dir):
        """Test basic tail functionality."""
        result = fallback.tail(['test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        assert len(lines) <= 10  # Default is 10 lines

    def test_tail_specific_lines(self, fallback, temp_dir):
        """Test tail with specific number of lines."""
        result = fallback.tail(['-n', '2', 'test_file.txt'], temp_dir)

        assert result['returncode'] == 0
        lines = result['output'].split('\n')
        assert len(lines) == 2
        assert 'World' in lines[0]
        assert 'Test' in lines[1]

    def test_touch_basic(self, fallback, temp_dir):
        """Test basic touch functionality."""
        new_file = temp_dir / "new_file.txt"

        result = fallback.touch(['new_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert new_file.exists()
        assert new_file.stat().st_size == 0

    def test_touch_multiple_files(self, fallback, temp_dir):
        """Test touch with multiple files."""
        result = fallback.touch(['file1.txt', 'file2.txt'], temp_dir)

        assert result['returncode'] == 0
        assert (temp_dir / 'file1.txt').exists()
        assert (temp_dir / 'file2.txt').exists()

    def test_touch_no_arguments(self, fallback, temp_dir):
        """Test touch without arguments."""
        result = fallback.touch([], temp_dir)

        assert result['returncode'] == 1
        assert 'missing file operand' in result['output']

    def test_mkdir_p_basic(self, fallback, temp_dir):
        """Test basic mkdir -p functionality."""
        nested_path = temp_dir / "nested" / "path" / "dir"

        result = fallback.mkdir_p(['nested/path/dir'], temp_dir)

        assert result['returncode'] == 0
        assert nested_path.exists()
        assert nested_path.is_dir()

    def test_mkdir_p_existing_directory(self, fallback, temp_dir):
        """Test mkdir -p with existing directory (should not fail)."""
        existing_dir = temp_dir / "existing"
        existing_dir.mkdir()

        result = fallback.mkdir_p(['existing'], temp_dir)

        assert result['returncode'] == 0
        assert existing_dir.exists()

    def test_mkdir_p_no_arguments(self, fallback, temp_dir):
        """Test mkdir without arguments."""
        result = fallback.mkdir_p([], temp_dir)

        assert result['returncode'] == 1
        assert 'missing operand' in result['output']

    def test_rm_file(self, fallback, temp_dir):
        """Test rm with file."""
        file_to_remove = temp_dir / "remove_me.txt"
        file_to_remove.write_text("Remove me")

        result = fallback.rm(['remove_me.txt'], temp_dir)

        assert result['returncode'] == 0
        assert not file_to_remove.exists()

    def test_rm_directory_recursive(self, fallback, temp_dir):
        """Test rm with -r flag for directory."""
        dir_to_remove = temp_dir / "remove_dir"
        dir_to_remove.mkdir()
        (dir_to_remove / "file.txt").write_text("content")

        result = fallback.rm(['-r', 'remove_dir'], temp_dir)

        assert result['returncode'] == 0
        assert not dir_to_remove.exists()

    def test_rm_directory_without_recursive(self, fallback, temp_dir):
        """Test rm with directory but no -r flag."""
        dir_to_remove = temp_dir / "remove_dir"
        dir_to_remove.mkdir()

        result = fallback.rm(['remove_dir'], temp_dir)

        assert result['returncode'] == 1
        assert 'is a directory' in result['output']
        assert dir_to_remove.exists()  # Should not be removed

    def test_rm_nonexistent_file_force(self, fallback, temp_dir):
        """Test rm with -f flag on nonexistent file."""
        result = fallback.rm(['-f', 'nonexistent.txt'], temp_dir)

        assert result['returncode'] == 0
        assert result['output'] == ''

    def test_rm_nonexistent_file_no_force(self, fallback, temp_dir):
        """Test rm without -f flag on nonexistent file."""
        result = fallback.rm(['nonexistent.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_cp_file_to_file(self, fallback, temp_dir):
        """Test cp from file to file."""
        source = temp_dir / "source.txt"
        source.write_text("Source content")
        dest = temp_dir / "dest.txt"

        result = fallback.cp(['source.txt', 'dest.txt'], temp_dir)

        assert result['returncode'] == 0
        assert dest.exists()
        assert dest.read_text() == "Source content"

    def test_cp_file_to_directory(self, fallback, temp_dir):
        """Test cp from file to directory."""
        source = temp_dir / "source.txt"
        source.write_text("Source content")
        dest_dir = temp_dir / "dest_dir"
        dest_dir.mkdir()

        result = fallback.cp(['source.txt', 'dest_dir'], temp_dir)

        assert result['returncode'] == 0
        assert (dest_dir / "source.txt").exists()
        assert (dest_dir / "source.txt").read_text() == "Source content"

    def test_cp_directory_recursive(self, fallback, temp_dir):
        """Test cp directory with -r flag."""
        source_dir = temp_dir / "source_dir"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("content")

        result = fallback.cp(['-r', 'source_dir', 'dest_dir'], temp_dir)

        assert result['returncode'] == 0
        assert (temp_dir / "dest_dir").exists()
        assert (temp_dir / "dest_dir" / "file.txt").exists()

    def test_cp_directory_without_recursive(self, fallback, temp_dir):
        """Test cp directory without -r flag."""
        source_dir = temp_dir / "source_dir"
        source_dir.mkdir()

        result = fallback.cp(['source_dir', 'dest_dir'], temp_dir)

        assert result['returncode'] == 1
        assert '-r not specified' in result['output']

    def test_cp_nonexistent_source(self, fallback, temp_dir):
        """Test cp with nonexistent source."""
        result = fallback.cp(['nonexistent.txt', 'dest.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_mv_file(self, fallback, temp_dir):
        """Test mv with file."""
        source = temp_dir / "source.txt"
        source.write_text("Source content")
        dest = temp_dir / "dest.txt"

        result = fallback.mv(['source.txt', 'dest.txt'], temp_dir)

        assert result['returncode'] == 0
        assert not source.exists()
        assert dest.exists()
        assert dest.read_text() == "Source content"

    def test_mv_directory(self, fallback, temp_dir):
        """Test mv with directory."""
        source_dir = temp_dir / "source_dir"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("content")
        dest_dir = temp_dir / "dest_dir"

        result = fallback.mv(['source_dir', 'dest_dir'], temp_dir)

        assert result['returncode'] == 0
        assert not source_dir.exists()
        assert dest_dir.exists()
        assert (dest_dir / "file.txt").exists()

    def test_mv_nonexistent_source(self, fallback, temp_dir):
        """Test mv with nonexistent source."""
        result = fallback.mv(['nonexistent.txt', 'dest.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'No such file or directory' in result['output']

    def test_mv_missing_destination(self, fallback, temp_dir):
        """Test mv without destination."""
        result = fallback.mv(['source.txt'], temp_dir)

        assert result['returncode'] == 1
        assert 'missing destination operand' in result['output']

    def test_which_existing_command(self, fallback, temp_dir):
        """Test which with existing command."""
        # Mock shutil.which to return a path
        with patch('shutil.which', return_value='/usr/bin/python'):
            result = fallback.which(['python'])

        assert result['returncode'] == 0
        assert '/usr/bin/python' in result['output']

    # def test_which_nonexistent_command(self, fallback, temp_dir):
    #     """Test which with nonexistent command."""
    #     with patch('shutil.which', return_value=None):
    #         result = fallback.which(['nonexistent'])
    #
    #     assert result['returncode'] == 1
    #     assert 'not found' in result['output']

    def test_which_no_arguments(self, fallback, temp_dir):
        """Test which without arguments."""
        result = fallback.which([])

        assert result['returncode'] == 1
        assert 'missing argument' in result['output']

    def test_pwd(self, fallback, temp_dir):
        """Test pwd command."""
        result = fallback.pwd(temp_dir)

        assert result['returncode'] == 0
        assert str(temp_dir.resolve()) in result['output']

    def test_binary_file_handling(self, fallback, temp_dir):
        """Test handling of files with binary content."""
        # Test cat with binary-like content
        result = fallback.cat(['binary_like.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Hello' in result['output']
        # Should handle encoding errors gracefully
        assert 'used_fallback' in result
        assert result['used_fallback'] == True

    def test_special_characters_in_filenames(self, fallback, temp_dir):
        """Test handling of special characters in filenames."""
        special_file = temp_dir / "file with spaces.txt"
        special_file.write_text("Content with spaces")

        result = fallback.cat(['file with spaces.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Content with spaces' in result['output']

    def test_very_large_file(self, fallback, temp_dir):
        """Test handling of very large files."""
        large_file = temp_dir / "large_file.txt"
        # Create a file with many lines
        content = '\n'.join([f'Line {i}' for i in range(1000)])
        large_file.write_text(content)

        result = fallback.wc(['-l', 'large_file.txt'], temp_dir)

        assert result['returncode'] == 0
        assert '1000' in result['output']

    def test_empty_directory_operations(self, fallback, temp_dir):
        """Test operations on empty directories."""
        empty_dir = temp_dir / "empty_dir"
        empty_dir.mkdir()

        result = fallback.ls(['empty_dir'], temp_dir)

        assert result['returncode'] == 0
        # Should not crash, output should be empty or minimal
        assert isinstance(result['output'], str)

    def test_symbolic_links_handling(self, fallback, temp_dir):
        """Test handling of symbolic links if supported."""
        # Create a file and try to create a symbolic link
        source_file = temp_dir / "source.txt"
        source_file.write_text("Source content")

        try:
            link_file = temp_dir / "link.txt"
            link_file.symlink_to(source_file)

            result = fallback.cat(['link.txt'], temp_dir)
            assert result['returncode'] == 0
            assert 'Source content' in result['output']
        except (OSError, NotImplementedError):
            # Skip if symlinks not supported (e.g., Windows without admin)
            pytest.skip("Symbolic links not supported on this platform")

    def test_permission_errors_handling(self, fallback, temp_dir):
        """Test graceful handling of permission errors."""
        # Create a file and try to make it read-only
        protected_file = temp_dir / "protected.txt"
        protected_file.write_text("Protected content")

        try:
            # Try to make file read-only
            protected_file.chmod(0o444)

            # Try to remove it without force
            result = fallback.rm(['protected.txt'], temp_dir)
            # Should handle permission error gracefully
            assert result['returncode'] in [0, 1]  # Either succeeds or fails gracefully

        except (OSError, PermissionError):
            # Skip if we can't change permissions
            pytest.skip("Cannot test permission errors on this platform")
        finally:
            # Restore permissions for cleanup
            try:
                protected_file.chmod(0o644)
            except:
                pass

    def test_concurrent_file_operations(self, fallback, temp_dir):
        """Test that operations work correctly with multiple files."""
        # Create multiple files
        for i in range(5):
            (temp_dir / f"file_{i}.txt").write_text(f"Content {i}")

        # Test operations on multiple files
        result = fallback.cat(['file_0.txt', 'file_1.txt', 'file_2.txt'], temp_dir)

        assert result['returncode'] == 0
        assert 'Content 0' in result['output']
        assert 'Content 1' in result['output']
        assert 'Content 2' in result['output']

    def test_protocol_compliance(self, fallback):
        """Test that the class implements the protocol correctly."""
        # Should have all required methods
        required_methods = [
            'ls', 'cat', 'grep', 'find', 'wc', 'head', 'tail',
            'touch', 'mkdir_p', 'rm', 'cp', 'mv', 'which', 'pwd'
        ]

        for method in required_methods:
            assert hasattr(fallback, method)
            assert callable(getattr(fallback, method))

        # All methods should return dict with required keys
        temp_dir = Path('/tmp')
        result = fallback.pwd(temp_dir)
        assert isinstance(result, dict)
        assert 'output' in result
        assert 'returncode' in result
        assert 'used_fallback' in result
        assert result['used_fallback'] == True


# class TestEdgeCasesAndErrorHandling:
#     """Test edge cases and error handling scenarios."""
#
#     def test_malformed_command_arguments(self, fallback, tmp_path):
#         """Test handling of malformed arguments."""
#         # Test with various malformed arguments
#         test_cases = [
#             ([''], "Empty string argument"),
#             (['-'], "Just dash"),
#             (['--'], "Double dash"),
#             (['-xyz'], "Combined flags"),
#         ]
#
#         for args, description in test_cases:
#             # These should not crash, even if they don't work as expected
#             try:
#                 result = fallback.ls(args, tmp_path)
#                 assert isinstance(result, dict)
#                 assert 'returncode' in result
#             except Exception as e:
#                 pytest.fail(f"ls crashed with {description}: {e}")
#
#     def test_very_long_filenames(self, fallback, tmp_path):
#         """Test handling of very long filenames."""
#         long_name = "a" * 200 + ".txt"
#         long_file = tmp_path / long_name
#         long_file.write_text("Content")
#
#         result = fallback.cat([long_name], tmp_path)
#
#         # Should handle long filenames gracefully
#         assert isinstance(result, dict)
#         assert 'returncode' in result
#
#     def test_circular_directory_structure(self, fallback, tmp_path):
#         """Test handling of complex directory structures."""
#         # Create nested directories
#         deep_path = tmp_path
#         for i in range(10):
#             deep_path = deep_path / f"level_{i}"
#             deep_path.mkdir()
#             (deep_path / f"file_{i}.txt").write_text(f"Level {i}")
#
#         result = fallback.find([], tmp_path)
#
#         assert result['returncode'] == 0
#         # Should find all nested files
#         assert 'level_9' in result['output']
#
#     def test_unicode_filenames_and_content(self, fallback, tmp_path):
#         """Test handling of unicode characters."""
#         unicode_file = tmp_path / "测试文件.txt"
#         unicode_file.write_text("Hello 世界 🌍")
#
#         result = fallback.cat(["测试文件.txt"], tmp_path)
#
#         assert result['returncode'] == 0
#         assert '世界' in result['output']
#         assert '🌍' in result['output']
#
#     def test_very_large_numbers_in_arguments(self, fallback, tmp_path):
#         """Test handling of very large numbers in arguments."""
#         # Create a file with many lines
#         large_file = tmp_path / "large.txt"
#         large_file.write_text('\n'.join([f"Line {i}" for i in range(100)]))
#
#         # Test with very large line numbers
#         result = fallback.head(['-n', '999999999', 'large.txt'], tmp_path)
#
#         assert result['returncode'] == 0
#         # Should handle large numbers gracefully
#         assert 'Line 0' in result['output']
#
#     def test_mixed_valid_invalid_arguments(self, fallback, tmp_path):
#         """Test handling of mixed valid and invalid arguments."""
#         # Create some files
#         (tmp_path / "valid1.txt").write_text("Valid 1")
#         (tmp_path / "valid2.txt").write_text("Valid 2")
#
#         # Mix valid and invalid files
#         result = fallback.cat(['valid1.txt', 'nonexistent.txt', 'valid2.txt'], tmp_path)
#
#         # Should fail on first invalid file
#         assert result['returncode'] == 1
#         assert 'nonexistent.txt' in result['output']
#
#     def test_files_with_different_encodings(self, fallback, tmp_path):
#         """Test handling of files with different encodings."""
#         # Create files with different content
#         ascii_file = tmp_path / "ascii.txt"
#         ascii_file.write_text("ASCII content")
#
#         # Test that cat handles them
#         result = fallback.cat(["ascii.txt"], tmp_path)
#
#         assert result['returncode'] == 0
#         assert 'ASCII content' in result['output']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])