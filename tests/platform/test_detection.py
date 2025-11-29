"""
Behavior tests for platform detection.

Tests prove that platform detection features work correctly,
not just that code runs. Focus on behavior, edge cases, and error conditions.
"""

import pytest
from unittest.mock import Mock, patch
from src.platform.detection import SystemPlatformDetector


class TestSystemPlatformDetector:
    """Test SystemPlatformDetector behavior."""

    def test_detects_windows_platform(self):
        """Test that Windows platform is correctly detected."""
        with patch('platform.system', return_value='Windows'):
            detector = SystemPlatformDetector()

            assert detector.is_windows()
            assert not detector.is_unix()
            assert not detector.is_macos()
            assert detector.get_platform_name() == "Windows"

    def test_detects_macos_platform(self):
        """Test that macOS platform is correctly detected."""
        with patch('platform.system', return_value='Darwin'):
            detector = SystemPlatformDetector()

            assert detector.is_macos()
            assert detector.is_unix()
            assert not detector.is_windows()
            assert detector.get_platform_name() == "macOS"

    def test_detects_linux_platform(self):
        """Test that Linux platform is correctly detected."""
        with patch('platform.system', return_value='Linux'):
            detector = SystemPlatformDetector()

            assert detector.is_unix()
            assert not detector.is_windows()
            assert not detector.is_macos()
            assert detector.get_platform_name() == "Linux"

    def test_detects_freebsd_platform(self):
        """Test that FreeBSD platform is correctly detected."""
        with patch('platform.system', return_value='FreeBSD'):
            detector = SystemPlatformDetector()

            assert detector.is_unix()
            assert not detector.is_windows()
            assert not detector.is_macos()
            assert detector.get_platform_name() == "FreeBSD"

    def test_detects_openbsd_platform(self):
        """Test that OpenBSD platform is correctly detected."""
        with patch('platform.system', return_value='OpenBSD'):
            detector = SystemPlatformDetector()

            assert detector.is_unix()
            assert not detector.is_windows()
            assert detector.get_platform_name() == "OpenBSD"

    def test_detects_netbsd_platform(self):
        """Test that NetBSD platform is correctly detected."""
        with patch('platform.system', return_value='NetBSD'):
            detector = SystemPlatformDetector()

            assert detector.is_unix()
            assert not detector.is_windows()
            assert detector.get_platform_name() == "NetBSD"

    def test_unknown_platform_defaults_to_linux(self):
        """Test that unknown platforms default to Linux for compatibility."""
        with patch('platform.system', return_value='UnknownOS'):
            detector = SystemPlatformDetector()

            assert detector.get_platform_name() == "Linux"

    def test_shell_info_on_windows(self):
        """Test that shell info is correctly gathered on Windows."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which') as mock_which:

            def which_side_effect(cmd):
                return {
                    'cmd': 'C:\\Windows\\System32\\cmd.exe',
                    'powershell': 'C:\\Windows\\System32\\WindowsPowerShell\\powershell.exe',
                    'bash': None,
                    'sh': None,
                }.get(cmd)

            mock_which.side_effect = which_side_effect
            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['cmd'] is not None
            assert shell_info['powershell'] is not None
            assert shell_info['default'] is not None
            assert shell_info['bash'] is None
            assert shell_info['sh'] is None

    def test_shell_info_on_unix(self):
        """Test that shell info is correctly gathered on Unix."""
        with patch('platform.system', return_value='Linux'), \
             patch('shutil.which') as mock_which:

            def which_side_effect(cmd):
                return {
                    'bash': '/bin/bash',
                    'sh': '/bin/sh',
                    'cmd': None,
                    'powershell': None,
                }.get(cmd)

            mock_which.side_effect = which_side_effect
            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['bash'] is not None
            assert shell_info['sh'] is not None
            assert shell_info['default'] == '/bin/bash'
            assert shell_info['cmd'] is None
            assert shell_info['powershell'] is None

    def test_shell_info_caching(self):
        """Test that shell info results are cached."""
        with patch('platform.system', return_value='Linux'), \
             patch('shutil.which', return_value='/bin/bash') as mock_which:

            detector = SystemPlatformDetector()

            # First call
            info1 = detector.get_shell_info()
            first_call_count = mock_which.call_count

            # Second call should use cache
            info2 = detector.get_shell_info()
            second_call_count = mock_which.call_count

            assert info1 == info2
            assert first_call_count == second_call_count

    def test_shell_info_returns_copy_not_reference(self):
        """Test that get_shell_info returns a copy, not the cached reference."""
        with patch('platform.system', return_value='Linux'), \
             patch('shutil.which', return_value='/bin/bash'):

            detector = SystemPlatformDetector()

            info1 = detector.get_shell_info()
            info1['modified'] = 'test'

            info2 = detector.get_shell_info()

            assert 'modified' not in info2

    def test_has_git_bash_on_windows_with_git_bash(self):
        """Test that Git Bash is detected on Windows when present."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which', return_value='C:\\Program Files\\Git\\usr\\bin\\bash.exe'):

            detector = SystemPlatformDetector()

            assert detector.has_git_bash()

    def test_has_git_bash_on_windows_without_git_bash(self):
        """Test that Git Bash is not detected when bash is not from Git."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which', return_value='C:\\cygwin\\bin\\bash.exe'):

            detector = SystemPlatformDetector()

            assert not detector.has_git_bash()

    def test_has_git_bash_returns_false_when_bash_not_available(self):
        """Test that has_git_bash returns False when bash command is not found."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which', return_value=None):

            detector = SystemPlatformDetector()

            assert not detector.has_git_bash()

    def test_has_git_bash_returns_false_on_unix(self):
        """Test that has_git_bash always returns False on Unix systems."""
        with patch('platform.system', return_value='Linux'), \
             patch('shutil.which', return_value='/bin/bash'):

            detector = SystemPlatformDetector()

            assert not detector.has_git_bash()

    def test_has_tool_returns_true_when_tool_available(self):
        """Test that has_tool returns True when tool is available."""
        with patch('shutil.which', return_value='/usr/bin/git'):
            detector = SystemPlatformDetector()

            assert detector.has_tool('git')

    def test_has_tool_returns_false_when_tool_not_available(self):
        """Test that has_tool returns False when tool is not available."""
        with patch('shutil.which', return_value=None):
            detector = SystemPlatformDetector()

            assert not detector.has_tool('nonexistent-tool')

    def test_has_tool_caching(self):
        """Test that has_tool results are cached."""
        with patch('shutil.which', return_value='/usr/bin/git') as mock_which:
            detector = SystemPlatformDetector()

            # First call
            result1 = detector.has_tool('git')
            first_call_count = mock_which.call_count

            # Second call should use cache
            result2 = detector.has_tool('git')
            second_call_count = mock_which.call_count

            assert result1 == result2 == True
            assert first_call_count == second_call_count

    def test_has_tool_rejects_empty_tool_name(self):
        """Test that has_tool returns False for empty tool name."""
        detector = SystemPlatformDetector()

        assert not detector.has_tool('')

    def test_has_tool_rejects_tool_name_with_spaces(self):
        """Test that has_tool returns False for tool names with spaces."""
        detector = SystemPlatformDetector()

        assert not detector.has_tool('git status')
        assert not detector.has_tool('npm install')


class TestPlatformDetectorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_windows_shell_prefers_cmd_when_powershell_unavailable(self):
        """Test that default shell is cmd when PowerShell is not available."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which') as mock_which:

            def which_side_effect(cmd):
                return {
                    'cmd': 'C:\\Windows\\System32\\cmd.exe',
                    'powershell': None,
                    'pwsh': None,
                    'bash': None,
                    'sh': None,
                }.get(cmd)

            mock_which.side_effect = which_side_effect
            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['default'] == 'C:\\Windows\\System32\\cmd.exe'

    def test_windows_shell_uses_pwsh_when_powershell_unavailable(self):
        """Test that pwsh is used as PowerShell alternative when available."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which') as mock_which:

            def which_side_effect(cmd):
                return {
                    'cmd': 'C:\\Windows\\System32\\cmd.exe',
                    'powershell': None,
                    'pwsh': 'C:\\Program Files\\PowerShell\\7\\pwsh.exe',
                    'bash': None,
                    'sh': None,
                }.get(cmd)

            mock_which.side_effect = which_side_effect
            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['powershell'] == 'C:\\Program Files\\PowerShell\\7\\pwsh.exe'

    def test_unix_shell_falls_back_to_sh_when_bash_unavailable(self):
        """Test that /bin/sh is used when bash is not available on Unix."""
        with patch('platform.system', return_value='Linux'), \
             patch('shutil.which') as mock_which:

            def which_side_effect(cmd):
                return {
                    'bash': None,
                    'sh': '/bin/sh',
                    'cmd': None,
                    'powershell': None,
                }.get(cmd)

            mock_which.side_effect = which_side_effect
            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['default'] == '/bin/sh'

    def test_unix_shell_when_no_shells_available(self):
        """Test behavior when no shells are available on Unix."""
        with patch('platform.system', return_value='Linux'), \
             patch('shutil.which', return_value=None):

            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['default'] is None
            assert shell_info['bash'] is None
            assert shell_info['sh'] is None

    def test_windows_shell_when_no_shells_available(self):
        """Test behavior when no shells are available on Windows."""
        with patch('platform.system', return_value='Windows'), \
             patch('shutil.which', return_value=None):

            detector = SystemPlatformDetector()
            shell_info = detector.get_shell_info()

            assert shell_info['default'] is None
            assert shell_info['cmd'] is None
            assert shell_info['powershell'] is None
