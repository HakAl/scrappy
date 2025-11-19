"""
Tests for PlatformDetector - platform and tool detection.

TDD: These tests define the expected behavior for the PlatformDetector class
that will be extracted from CodebaseContext.
"""
import pytest
import sys
import shutil
from unittest.mock import patch, MagicMock


class TestPlatformDetection:
    """Tests for platform detection functionality."""

    @pytest.mark.unit
    def test_returns_platform_string(self):
        """Should return a string identifying the platform."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        platform = detector.get_platform()

        assert isinstance(platform, str)
        assert len(platform) > 0

    @pytest.mark.unit
    def test_returns_valid_platform_value(self):
        """Should return one of the expected platform values."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        platform = detector.get_platform()

        valid_platforms = ('windows', 'darwin', 'linux', 'unix')
        assert platform in valid_platforms

    @pytest.mark.unit
    def test_windows_platform_detection(self):
        """Should return 'windows' when sys.platform is 'win32'."""
        from src.context.platform import PlatformDetector

        with patch('sys.platform', 'win32'):
            # Create new instance to avoid cached value
            detector = PlatformDetector()
            platform = detector.get_platform()

        assert platform == 'windows'

    @pytest.mark.unit
    def test_darwin_platform_detection(self):
        """Should return 'darwin' when sys.platform is 'darwin'."""
        from src.context.platform import PlatformDetector

        with patch('sys.platform', 'darwin'):
            detector = PlatformDetector()
            platform = detector.get_platform()

        assert platform == 'darwin'

    @pytest.mark.unit
    def test_linux_platform_detection(self):
        """Should return 'linux' when sys.platform starts with 'linux'."""
        from src.context.platform import PlatformDetector

        with patch('sys.platform', 'linux'):
            detector = PlatformDetector()
            platform = detector.get_platform()

        assert platform == 'linux'

    @pytest.mark.unit
    def test_linux_variant_platform_detection(self):
        """Should return 'linux' for linux variants like 'linux2'."""
        from src.context.platform import PlatformDetector

        with patch('sys.platform', 'linux2'):
            detector = PlatformDetector()
            platform = detector.get_platform()

        assert platform == 'linux'

    @pytest.mark.unit
    def test_unknown_platform_defaults_to_unix(self):
        """Should return 'unix' for unknown platforms."""
        from src.context.platform import PlatformDetector

        with patch('sys.platform', 'freebsd12'):
            detector = PlatformDetector()
            platform = detector.get_platform()

        assert platform == 'unix'

    @pytest.mark.unit
    def test_platform_is_cached(self):
        """Platform value should be cached after first detection."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()

        # First call
        platform1 = detector.get_platform()

        # Patch sys.platform to a different value
        with patch('sys.platform', 'completely_different'):
            platform2 = detector.get_platform()

        # Should return cached value, not re-detect
        assert platform1 == platform2

    @pytest.mark.unit
    def test_new_instance_does_not_use_other_instance_cache(self):
        """Each instance should have its own cache."""
        from src.context.platform import PlatformDetector

        detector1 = PlatformDetector()
        _ = detector1.get_platform()

        # New instance should detect fresh
        detector2 = PlatformDetector()
        # Both should work independently
        assert detector2.get_platform() is not None

    @pytest.mark.unit
    def test_matches_current_system(self):
        """Platform detection should match the actual system."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        platform = detector.get_platform()

        if sys.platform == 'win32':
            assert platform == 'windows'
        elif sys.platform == 'darwin':
            assert platform == 'darwin'
        elif sys.platform.startswith('linux'):
            assert platform == 'linux'
        else:
            assert platform in ('unix', 'linux')


class TestToolAvailability:
    """Tests for tool/command availability detection."""

    @pytest.mark.unit
    def test_returns_boolean(self):
        """Should return a boolean value."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        result = detector.has_tool('python')

        assert isinstance(result, bool)

    @pytest.mark.unit
    def test_detects_python_available(self):
        """Should detect that Python is available (we're running in Python)."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        has_python = detector.has_tool('python')

        assert has_python is True

    @pytest.mark.unit
    def test_detects_nonexistent_tool(self):
        """Should return False for tools that don't exist."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        has_fake = detector.has_tool('definitely_not_a_real_command_xyz123')

        assert has_fake is False

    @pytest.mark.unit
    def test_tool_detection_is_cached(self):
        """Tool detection should be cached for performance."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()

        # First check
        _ = detector.has_tool('python')

        # Mock shutil.which to return different value
        with patch('shutil.which', return_value=None):
            # Should return cached value
            result = detector.has_tool('python')

        assert result is True  # Cached value, not new detection

    @pytest.mark.unit
    def test_different_tools_cached_separately(self):
        """Different tools should be cached independently."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()

        # Check two different tools
        has_python = detector.has_tool('python')
        has_fake = detector.has_tool('fake_tool_xyz')

        assert has_python is True
        assert has_fake is False

    @pytest.mark.unit
    def test_empty_tool_name(self):
        """Should handle empty tool name gracefully."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        result = detector.has_tool('')

        assert result is False

    @pytest.mark.unit
    def test_tool_with_spaces(self):
        """Should handle tool names with spaces (likely invalid)."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        result = detector.has_tool('tool with spaces')

        assert result is False

    @pytest.mark.unit
    def test_detects_git_if_installed(self):
        """Should correctly detect git availability."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()
        has_git = detector.has_tool('git')

        # Verify against actual system
        actual_has_git = shutil.which('git') is not None
        assert has_git == actual_has_git

    @pytest.mark.unit
    def test_multiple_checks_same_tool(self):
        """Multiple checks for the same tool should be efficient (cached)."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()

        # Multiple checks should not cause issues
        results = [detector.has_tool('python') for _ in range(10)]

        assert all(r is True for r in results)

    @pytest.mark.unit
    def test_uses_shutil_which(self):
        """Should use shutil.which for tool detection."""
        from src.context.platform import PlatformDetector

        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/mytool'

            detector = PlatformDetector()
            result = detector.has_tool('mytool')

            mock_which.assert_called_with('mytool')
            assert result is True

    @pytest.mark.unit
    def test_shutil_which_returns_none_means_not_available(self):
        """Should return False when shutil.which returns None."""
        from src.context.platform import PlatformDetector

        with patch('shutil.which') as mock_which:
            mock_which.return_value = None

            detector = PlatformDetector()
            result = detector.has_tool('missingtool')

            assert result is False


class TestPlatformDetectorIntegration:
    """Integration tests for PlatformDetector with CodebaseContext."""

    @pytest.mark.unit
    def test_codebase_context_uses_platform_detector(self, temp_project_dir):
        """CodebaseContext should delegate to PlatformDetector."""
        from src.context import CodebaseContext

        context = CodebaseContext(str(temp_project_dir))

        # These methods should work as before
        platform = context.get_platform()
        has_python = context.has_tool('python')

        assert platform in ('windows', 'darwin', 'linux', 'unix')
        assert has_python is True

    @pytest.mark.unit
    def test_platform_detector_standalone_usage(self):
        """PlatformDetector should work independently of CodebaseContext."""
        from src.context.platform import PlatformDetector

        detector = PlatformDetector()

        # Should work without any project path
        platform = detector.get_platform()
        has_tool = detector.has_tool('python')

        assert platform is not None
        assert has_tool is True
