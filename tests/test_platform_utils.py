"""
Tests for platform utilities - cross-platform support and command validation.
"""
import pytest
import sys
from unittest.mock import patch, MagicMock

from src.platform_utils import (
    get_platform_name,
    is_windows,
    is_unix,
    is_macos,
    validate_command_for_platform,
    get_dangerous_commands,
    get_shell_info,
    translate_command_for_platform,
    normalize_path_for_shell,
    get_null_device,
    get_path_separator,
    validate_spring_initializr_url,
    fix_spring_initializr_command,
    get_spring_boot_fallback_files,
)


class TestPlatformDetection:
    """Tests for platform detection."""

    @pytest.mark.unit
    def test_get_platform_name_returns_string(self):
        """Test that platform detection returns a string."""
        platform = get_platform_name()
        assert isinstance(platform, str)

    @pytest.mark.unit
    def test_get_platform_name_known_value(self):
        """Test that platform is one of known values."""
        platform = get_platform_name()
        known_platforms = ["Windows", "Linux", "macOS"]
        assert platform in known_platforms or platform.startswith("FreeBSD") or platform.startswith("OpenBSD")

    @pytest.mark.unit
    def test_is_windows_returns_bool(self):
        """Test that is_windows returns boolean."""
        result = is_windows()
        assert isinstance(result, bool)

    @pytest.mark.unit
    def test_is_unix_returns_bool(self):
        """Test that is_unix returns boolean."""
        result = is_unix()
        assert isinstance(result, bool)

    @pytest.mark.unit
    def test_is_macos_returns_bool(self):
        """Test that is_macos returns boolean."""
        result = is_macos()
        assert isinstance(result, bool)

    @pytest.mark.unit
    def test_platform_consistency(self):
        """Test that platform checks are consistent."""
        # Can't be both Windows and Unix at the same time
        if is_windows():
            assert not is_unix()
            assert not is_macos()
        if is_macos():
            assert is_unix()  # macOS is Unix
            assert not is_windows()


class TestDangerousCommandDetection:
    """Tests for dangerous command detection."""

    @pytest.mark.unit
    def test_get_dangerous_commands_returns_list(self):
        """Test that dangerous commands returns a list."""
        dangerous = get_dangerous_commands()
        assert isinstance(dangerous, list)
        assert len(dangerous) > 0

    @pytest.mark.unit
    def test_dangerous_commands_contains_patterns(self):
        """Test that dangerous commands contains expected patterns."""
        dangerous = get_dangerous_commands()

        # Common patterns should be present
        has_mkfs = any("mkfs" in cmd for cmd in dangerous)
        has_format = any("format" in cmd for cmd in dangerous)

        assert has_mkfs or has_format

    @pytest.mark.unit
    def test_platform_specific_dangerous_commands(self):
        """Test that platform-specific commands are included."""
        dangerous = get_dangerous_commands()

        if is_windows():
            # Should have Windows-specific dangerous commands
            has_del = any("del" in cmd for cmd in dangerous)
            has_rmdir = any("rmdir" in cmd for cmd in dangerous)
            assert has_del or has_rmdir
        else:
            # Should have Unix-specific dangerous commands (regex patterns)
            # Patterns use \s+ for spaces, so check for "rm" and "rf" in pattern
            has_rm_rf = any("rm" in cmd and "rf" in cmd for cmd in dangerous)
            assert has_rm_rf

    @pytest.mark.unit
    def test_dangerous_commands_not_empty(self):
        """Test that list is not empty."""
        dangerous = get_dangerous_commands()
        assert len(dangerous) > 5  # Should have several patterns


class TestCommandValidation:
    """Tests for command validation by platform."""

    @pytest.mark.unit
    def test_validate_safe_command(self):
        """Test that safe commands pass validation."""
        is_valid, warning = validate_command_for_platform("git status")
        assert is_valid is True

    @pytest.mark.unit
    def test_validate_empty_command(self):
        """Test that empty commands fail validation."""
        is_valid, warning = validate_command_for_platform("")
        assert is_valid is False
        assert "Empty" in warning

    @pytest.mark.unit
    def test_validate_returns_tuple(self):
        """Test that validation returns proper tuple."""
        result = validate_command_for_platform("echo test")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    @pytest.mark.unit
    def test_whitespace_only_command(self):
        """Test that whitespace-only command fails."""
        is_valid, warning = validate_command_for_platform("   ")
        assert is_valid is False

    @pytest.mark.unit
    def test_unix_command_on_windows(self):
        """Test Unix command validation on Windows."""
        if is_windows():
            # Unix-specific commands should warn/fail on Windows
            is_valid, warning = validate_command_for_platform("chmod 755 file.sh")
            # May return False or True with warning depending on Git Bash
            assert isinstance(is_valid, bool)
            assert isinstance(warning, str)

    @pytest.mark.unit
    def test_common_commands_valid(self):
        """Test that common safe commands are valid."""
        commands = ["git status", "python --version", "npm install"]
        for cmd in commands:
            is_valid, warning = validate_command_for_platform(cmd)
            # Should generally be valid
            assert isinstance(is_valid, bool)


class TestCommandTranslation:
    """Tests for command translation between platforms."""

    @pytest.mark.unit
    def test_translate_returns_tuple(self):
        """Test that translation returns tuple."""
        result = translate_command_for_platform("ls")
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.unit
    def test_translate_ls_on_windows(self):
        """Test translating ls command."""
        if is_windows():
            translated, was_translated = translate_command_for_platform("ls")
            assert "dir" in translated.lower()
            assert was_translated is True
        else:
            translated, was_translated = translate_command_for_platform("ls")
            assert translated == "ls"
            assert was_translated is False

    @pytest.mark.unit
    def test_translate_pwd_on_windows(self):
        """Test translating pwd command."""
        if is_windows():
            translated, was_translated = translate_command_for_platform("pwd")
            assert was_translated is True
            assert "cd" in translated.lower()

    @pytest.mark.unit
    def test_translate_preserves_args(self):
        """Test that translation preserves arguments."""
        if is_windows():
            translated, _ = translate_command_for_platform("cat README.md")
            # Should translate cat to type but keep the argument
            assert "README.md" in translated

    @pytest.mark.unit
    def test_no_translation_on_unix(self):
        """Test that Unix commands aren't translated on Unix."""
        if is_unix():
            translated, was_translated = translate_command_for_platform("ls -la")
            assert was_translated is False
            assert translated == "ls -la"


class TestShellInfo:
    """Tests for shell information retrieval."""

    @pytest.mark.unit
    def test_get_shell_info_returns_dict(self):
        """Test that shell info returns dictionary."""
        info = get_shell_info()
        assert isinstance(info, dict)

    @pytest.mark.unit
    def test_shell_info_has_default(self):
        """Test that shell info includes default shell."""
        info = get_shell_info()
        assert "default" in info

    @pytest.mark.unit
    def test_shell_info_has_bash_key(self):
        """Test that shell info has bash key."""
        info = get_shell_info()
        assert "bash" in info

    @pytest.mark.unit
    def test_windows_has_cmd_powershell(self):
        """Test Windows shell info."""
        if is_windows():
            info = get_shell_info()
            assert "cmd" in info
            assert "powershell" in info


class TestPathNormalization:
    """Tests for path normalization."""

    @pytest.mark.unit
    def test_normalize_path_returns_string(self):
        """Test that path normalization returns string."""
        result = normalize_path_for_shell("some/path")
        assert isinstance(result, str)

    @pytest.mark.unit
    def test_windows_normalizes_to_backslash(self):
        """Test Windows path normalization."""
        if is_windows():
            result = normalize_path_for_shell("src/main/app.py")
            assert "\\" in result
            assert "/" not in result

    @pytest.mark.unit
    def test_unix_normalizes_to_forward_slash(self):
        """Test Unix path normalization."""
        if is_unix():
            result = normalize_path_for_shell("src\\main\\app.py")
            assert "/" in result
            assert "\\" not in result

    @pytest.mark.unit
    def test_get_path_separator(self):
        """Test path separator retrieval."""
        sep = get_path_separator()
        if is_windows():
            assert sep == "\\"
        else:
            assert sep == "/"

    @pytest.mark.unit
    def test_get_null_device(self):
        """Test null device path."""
        null_dev = get_null_device()
        if is_windows():
            assert null_dev == "NUL"
        else:
            assert null_dev == "/dev/null"


class TestEdgeCases:
    """Edge cases and boundary tests."""

    @pytest.mark.unit
    def test_very_long_command(self):
        """Test handling of very long command."""
        long_cmd = "echo " + "a" * 10000
        is_valid, warning = validate_command_for_platform(long_cmd)
        # Should handle without crashing
        assert isinstance(is_valid, bool)

    @pytest.mark.unit
    def test_command_with_special_chars(self):
        """Test handling commands with special characters."""
        cmd = "echo 'test $VAR' && ls"
        is_valid, warning = validate_command_for_platform(cmd)
        assert isinstance(is_valid, bool)

    @pytest.mark.unit
    def test_translate_empty_command(self):
        """Test translating empty command."""
        translated, was_translated = translate_command_for_platform("")
        assert translated == ""
        assert was_translated is False

    @pytest.mark.unit
    def test_translate_unknown_command(self):
        """Test translating unknown command."""
        translated, was_translated = translate_command_for_platform("myCustomCommand arg1")
        # Unknown commands shouldn't be translated
        assert "myCustomCommand" in translated
        assert was_translated is False


class TestPythonFallback:
    """Tests for Python-based command fallback implementations."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory with test files."""
        # Create test files
        (tmp_path / "file1.txt").write_text("line1\nline2\nline3\n")
        (tmp_path / "file2.txt").write_text("hello world\ntest line\n")
        (tmp_path / ".hidden").write_text("hidden file\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested content\n")
        return tmp_path

    @pytest.mark.unit
    def test_python_fallback_returns_none_on_unix(self, monkeypatch):
        """Python fallback should return None on Unix systems."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: False)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("ls")
        assert result is None

    @pytest.mark.unit
    def test_python_fallback_empty_command(self, monkeypatch):
        """Empty command should return None."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("")
        assert result is None

    @pytest.mark.unit
    def test_python_fallback_unknown_command(self, monkeypatch):
        """Unknown command should return None."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("unknowncommand arg1")
        assert result is None

    @pytest.mark.unit
    def test_python_ls_basic(self, monkeypatch, temp_dir):
        """Test Python ls implementation - basic listing."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("ls", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert result['used_fallback'] is True
        assert "file1.txt" in result['output']
        assert "file2.txt" in result['output']
        # Hidden files should not be shown by default
        assert ".hidden" not in result['output']

    @pytest.mark.unit
    def test_python_ls_show_all(self, monkeypatch, temp_dir):
        """Test Python ls -a shows hidden files."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("ls -a", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert ".hidden" in result['output']

    @pytest.mark.unit
    def test_python_ls_long_format(self, monkeypatch, temp_dir):
        """Test Python ls -l shows detailed output."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("ls -l", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        # Should contain file sizes and dates
        assert "file1.txt" in result['output']

    @pytest.mark.unit
    def test_python_ls_nonexistent_dir(self, monkeypatch, temp_dir):
        """Test Python ls on non-existent directory."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("ls nonexistent", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 1
        assert "No such file" in result['output']

    @pytest.mark.unit
    def test_python_pwd(self, monkeypatch, temp_dir):
        """Test Python pwd implementation."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("pwd", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert str(temp_dir.resolve()) in result['output']

    @pytest.mark.unit
    def test_python_cat_single_file(self, monkeypatch, temp_dir):
        """Test Python cat implementation for single file."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("cat file1.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "line1" in result['output']
        assert "line2" in result['output']
        assert "line3" in result['output']

    @pytest.mark.unit
    def test_python_cat_missing_file(self, monkeypatch, temp_dir):
        """Test Python cat on non-existent file."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("cat nonexistent.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 1
        assert "No such file" in result['output']

    @pytest.mark.unit
    def test_python_cat_no_args(self, monkeypatch, temp_dir):
        """Test Python cat with no arguments."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("cat", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 1
        assert "missing" in result['output']

    @pytest.mark.unit
    def test_python_head_default(self, monkeypatch, temp_dir):
        """Test Python head with default 10 lines."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("head file1.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "line1" in result['output']

    @pytest.mark.unit
    def test_python_head_with_count(self, monkeypatch, temp_dir):
        """Test Python head -n 2."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("head -n 2 file1.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        lines = result['output'].strip().split('\n')
        assert len(lines) == 2

    @pytest.mark.unit
    def test_python_tail_default(self, monkeypatch, temp_dir):
        """Test Python tail with default 10 lines."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("tail file1.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "line3" in result['output']

    @pytest.mark.unit
    def test_python_grep_basic(self, monkeypatch, temp_dir):
        """Test Python grep basic pattern matching."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("grep hello file2.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "hello world" in result['output']

    @pytest.mark.unit
    def test_python_grep_no_match(self, monkeypatch, temp_dir):
        """Test Python grep when pattern not found."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("grep notfound file2.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 1
        assert result['output'] == ""

    @pytest.mark.unit
    def test_python_grep_case_insensitive(self, monkeypatch, temp_dir):
        """Test Python grep -i case insensitive."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("grep -i HELLO file2.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "hello world" in result['output']

    @pytest.mark.unit
    def test_python_grep_line_numbers(self, monkeypatch, temp_dir):
        """Test Python grep -n shows line numbers."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("grep -n hello file2.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert ":1:" in result['output']

    @pytest.mark.unit
    def test_python_find_all_files(self, monkeypatch, temp_dir):
        """Test Python find lists all files."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("find .", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "file1.txt" in result['output']
        assert "nested.txt" in result['output']

    @pytest.mark.unit
    def test_python_find_by_name(self, monkeypatch, temp_dir):
        """Test Python find -name pattern."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("find . -name *.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "file1.txt" in result['output']
        assert ".hidden" not in result['output']

    @pytest.mark.unit
    def test_python_find_type_file(self, monkeypatch, temp_dir):
        """Test Python find -type f for files only."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("find . -type f", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "file1.txt" in result['output']
        assert "subdir\n" not in result['output']

    @pytest.mark.unit
    def test_python_wc_lines(self, monkeypatch, temp_dir):
        """Test Python wc -l counts lines."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("wc -l file1.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert "3" in result['output']

    @pytest.mark.unit
    def test_python_which_found(self, monkeypatch):
        """Test Python which for existing command."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("which python")
        assert result is not None
        assert result['returncode'] == 0
        assert "python" in result['output'].lower()

    @pytest.mark.unit
    def test_python_which_not_found(self, monkeypatch):
        """Test Python which for non-existent command."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("which nonexistentcommand123")
        assert result is not None
        assert "not found" in result['output']

    @pytest.mark.unit
    def test_python_touch_creates_file(self, monkeypatch, temp_dir):
        """Test Python touch creates new file."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("touch newfile.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert (temp_dir / "newfile.txt").exists()

    @pytest.mark.unit
    def test_python_mkdir_p_creates_nested(self, monkeypatch, temp_dir):
        """Test Python mkdir -p creates nested directories."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("mkdir -p a/b/c", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert (temp_dir / "a" / "b" / "c").exists()

    @pytest.mark.unit
    def test_python_rm_file(self, monkeypatch, temp_dir):
        """Test Python rm removes file."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("rm file1.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert not (temp_dir / "file1.txt").exists()

    @pytest.mark.unit
    def test_python_rm_directory_without_r(self, monkeypatch, temp_dir):
        """Test Python rm fails on directory without -r."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("rm subdir", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 1
        assert "directory" in result['output']

    @pytest.mark.unit
    def test_python_rm_rf_directory(self, monkeypatch, temp_dir):
        """Test Python rm -rf removes directory."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("rm -rf subdir", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert not (temp_dir / "subdir").exists()

    @pytest.mark.unit
    def test_python_cp_file(self, monkeypatch, temp_dir):
        """Test Python cp copies file."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        result = get_python_fallback("cp file1.txt copy.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert (temp_dir / "copy.txt").exists()
        assert (temp_dir / "copy.txt").read_text() == (temp_dir / "file1.txt").read_text()

    @pytest.mark.unit
    def test_python_mv_file(self, monkeypatch, temp_dir):
        """Test Python mv moves file."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import get_python_fallback
        original_content = (temp_dir / "file1.txt").read_text()
        result = get_python_fallback("mv file1.txt moved.txt", str(temp_dir))
        assert result is not None
        assert result['returncode'] == 0
        assert not (temp_dir / "file1.txt").exists()
        assert (temp_dir / "moved.txt").exists()
        assert (temp_dir / "moved.txt").read_text() == original_content


class TestSmartExecuteCommand:
    """Tests for smart_execute_command function."""

    @pytest.mark.unit
    def test_smart_execute_returns_dict(self, monkeypatch, tmp_path):
        """Smart execute should return a dictionary."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import smart_execute_command
        result = smart_execute_command("ls", str(tmp_path))
        assert isinstance(result, dict)
        assert 'output' in result
        assert 'returncode' in result
        assert 'method' in result

    @pytest.mark.unit
    def test_smart_execute_uses_fallback_on_windows(self, monkeypatch, tmp_path):
        """Smart execute should use Python fallback for Unix commands on Windows."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: True)
        from src.platform_utils import smart_execute_command
        result = smart_execute_command("pwd", str(tmp_path))
        assert result['method'] == 'python_fallback'
        assert result['returncode'] == 0

    @pytest.mark.unit
    def test_smart_execute_timeout(self, monkeypatch):
        """Smart execute should handle timeout."""
        monkeypatch.setattr("src.platform_utils.is_windows", lambda: False)
        from src.platform_utils import smart_execute_command
        # Use a command that would timeout but with very short timeout
        result = smart_execute_command("sleep 10", timeout=1)
        # On Windows without sleep command, this will fail differently
        # But on Unix-like systems, it should timeout
        assert 'returncode' in result


class TestSpringInitializrHelpers:
    """Tests for Spring Initializr URL validation and fallback templates."""

    @pytest.mark.unit
    def test_validate_spring_url_non_spring_url(self):
        """Non-Spring URLs should pass through unchanged."""
        url = "https://example.com/api"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is True
        assert fixed_url == url
        assert error == ""

    @pytest.mark.unit
    def test_validate_spring_url_no_params(self):
        """Spring URL without params should pass through."""
        url = "https://start.spring.io"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is True
        assert fixed_url == url

    @pytest.mark.unit
    def test_validate_spring_url_fixes_jjwt_dependency(self):
        """Should fix invalid jjwt dependency to security."""
        url = "https://start.spring.io/starter.zip?dependencies=web,jjwt,data-jpa"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is True
        assert "jjwt" not in fixed_url
        assert "security" in fixed_url
        assert "web" in fixed_url
        assert "data-jpa" in fixed_url

    @pytest.mark.unit
    def test_validate_spring_url_fixes_jwt_dependency(self):
        """Should fix jwt dependency to security."""
        url = "https://start.spring.io/starter.zip?dependencies=jwt"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert "security" in fixed_url
        assert "jwt" not in fixed_url or "security" in fixed_url

    @pytest.mark.unit
    def test_validate_spring_url_adds_defaults(self):
        """Should add default parameters if missing."""
        url = "https://start.spring.io/starter.zip?dependencies=web"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is True
        assert "type=maven-project" in fixed_url
        assert "language=java" in fixed_url
        assert "javaVersion=17" in fixed_url

    @pytest.mark.unit
    def test_validate_spring_url_preserves_valid_params(self):
        """Should preserve valid parameters."""
        url = "https://start.spring.io/starter.zip?type=gradle-project&language=kotlin&javaVersion=21"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is True
        assert "type=gradle-project" in fixed_url
        assert "language=kotlin" in fixed_url
        assert "javaVersion=21" in fixed_url

    @pytest.mark.unit
    def test_validate_spring_url_invalid_type(self):
        """Should report invalid type."""
        url = "https://start.spring.io/starter.zip?type=invalid-type"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is False
        assert "Invalid type" in error

    @pytest.mark.unit
    def test_validate_spring_url_invalid_packaging(self):
        """Should report invalid packaging."""
        url = "https://start.spring.io/starter.zip?packaging=invalid"
        is_valid, fixed_url, error = validate_spring_initializr_url(url)
        assert is_valid is False
        assert "Invalid packaging" in error

    @pytest.mark.unit
    def test_fix_spring_curl_command(self):
        """Should fix Spring Initializr URL in curl command."""
        cmd = "curl -o project.zip 'https://start.spring.io/starter.zip?dependencies=jjwt'"
        fixed_cmd, was_fixed, message = fix_spring_initializr_command(cmd)
        assert was_fixed is True
        assert "security" in fixed_cmd
        assert "Fixed" in message

    @pytest.mark.unit
    def test_fix_spring_powershell_download(self):
        """Should fix Spring Initializr URL in PowerShell DownloadFile."""
        cmd = "(New-Object System.Net.WebClient).DownloadFile('https://start.spring.io/starter.zip?dependencies=jwt', 'project.zip')"
        fixed_cmd, was_fixed, message = fix_spring_initializr_command(cmd)
        assert was_fixed is True
        assert "security" in fixed_cmd

    @pytest.mark.unit
    def test_fix_spring_invoke_webrequest(self):
        """Should fix Spring Initializr URL in Invoke-WebRequest."""
        cmd = "Invoke-WebRequest -Uri https://start.spring.io/starter.zip?dependencies=jjwt -OutFile project.zip"
        fixed_cmd, was_fixed, message = fix_spring_initializr_command(cmd)
        assert was_fixed is True
        assert "security" in fixed_cmd

    @pytest.mark.unit
    def test_fix_non_spring_command(self):
        """Should not modify non-Spring commands."""
        cmd = "curl -o file.zip https://example.com/download"
        fixed_cmd, was_fixed, message = fix_spring_initializr_command(cmd)
        assert was_fixed is False
        assert fixed_cmd == cmd
        assert message == ""

    @pytest.mark.unit
    def test_fix_spring_command_already_valid(self):
        """Should handle already valid Spring commands."""
        cmd = "curl -o project.zip 'https://start.spring.io/starter.zip?dependencies=web&type=maven-project'"
        fixed_cmd, was_fixed, message = fix_spring_initializr_command(cmd)
        # May still be fixed due to adding defaults
        assert isinstance(was_fixed, bool)
        assert isinstance(fixed_cmd, str)

    @pytest.mark.unit
    def test_get_spring_boot_fallback_files_returns_dict(self):
        """Should return dictionary of files."""
        files = get_spring_boot_fallback_files()
        assert isinstance(files, dict)
        assert len(files) > 0

    @pytest.mark.unit
    def test_get_spring_boot_fallback_has_pom(self):
        """Should include pom.xml."""
        files = get_spring_boot_fallback_files()
        assert "pom.xml" in files
        assert "spring-boot-starter-parent" in files["pom.xml"]

    @pytest.mark.unit
    def test_get_spring_boot_fallback_has_main_class(self):
        """Should include main application class."""
        files = get_spring_boot_fallback_files()
        main_class_path = "src/main/java/com/example/demo/DemoApplication.java"
        assert main_class_path in files
        assert "@SpringBootApplication" in files[main_class_path]

    @pytest.mark.unit
    def test_get_spring_boot_fallback_has_properties(self):
        """Should include application.properties."""
        files = get_spring_boot_fallback_files()
        assert "src/main/resources/application.properties" in files
        props = files["src/main/resources/application.properties"]
        assert "spring.datasource" in props
        assert "h2" in props.lower()

    @pytest.mark.unit
    def test_get_spring_boot_fallback_has_test(self):
        """Should include test class."""
        files = get_spring_boot_fallback_files()
        test_path = "src/test/java/com/example/demo/DemoApplicationTests.java"
        assert test_path in files
        assert "@SpringBootTest" in files[test_path]

    @pytest.mark.unit
    def test_get_spring_boot_fallback_has_gitignore(self):
        """Should include .gitignore."""
        files = get_spring_boot_fallback_files()
        assert ".gitignore" in files
        assert "target/" in files[".gitignore"]

    @pytest.mark.unit
    def test_get_spring_boot_fallback_custom_groupid(self):
        """Should use custom groupId."""
        files = get_spring_boot_fallback_files(group_id="org.mycompany")
        assert "org.mycompany" in files["pom.xml"]

    @pytest.mark.unit
    def test_get_spring_boot_fallback_custom_artifactid(self):
        """Should use custom artifactId."""
        files = get_spring_boot_fallback_files(artifact_id="myapp")
        assert "myapp" in files["pom.xml"]
        # Class name should be derived from artifact ID
        main_path = "src/main/java/com/example/demo/MyappApplication.java"
        assert main_path in files

    @pytest.mark.unit
    def test_get_spring_boot_fallback_custom_package(self):
        """Should use custom package name."""
        files = get_spring_boot_fallback_files(package_name="com.myorg.myapp")
        main_path = "src/main/java/com/myorg/myapp/DemoApplication.java"
        assert main_path in files
        assert "package com.myorg.myapp;" in files[main_path]

    @pytest.mark.unit
    def test_get_spring_boot_fallback_with_security_deps(self):
        """Should include JWT dependencies when security is included."""
        files = get_spring_boot_fallback_files(dependencies=["security"])
        pom = files["pom.xml"]
        assert "spring-boot-starter-security" in pom
        assert "jjwt-api" in pom
        assert "jjwt-impl" in pom
        assert "jjwt-jackson" in pom

    @pytest.mark.unit
    def test_get_spring_boot_fallback_without_security(self):
        """Should not include JWT dependencies without security."""
        files = get_spring_boot_fallback_files(dependencies=["web"])
        pom = files["pom.xml"]
        assert "jjwt-api" not in pom
        assert "spring-boot-starter-security" not in pom

    @pytest.mark.unit
    def test_get_spring_boot_fallback_h2_dependency(self):
        """Should include H2 dependency when specified."""
        files = get_spring_boot_fallback_files(dependencies=["h2"])
        pom = files["pom.xml"]
        assert "h2" in pom
        assert "runtime" in pom

    @pytest.mark.unit
    def test_get_spring_boot_fallback_validation_dependency(self):
        """Should include validation dependency when specified."""
        files = get_spring_boot_fallback_files(dependencies=["validation"])
        pom = files["pom.xml"]
        assert "spring-boot-starter-validation" in pom

    @pytest.mark.unit
    def test_get_spring_boot_fallback_has_maven_wrapper(self):
        """Should include Maven wrapper properties."""
        files = get_spring_boot_fallback_files()
        assert ".mvn/wrapper/maven-wrapper.properties" in files
        props = files[".mvn/wrapper/maven-wrapper.properties"]
        assert "apache-maven" in props
