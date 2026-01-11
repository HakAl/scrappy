"""
Tests for command executors.

Tests the different execution strategies: native, translated, and fallback.
"""
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scrappy.platform.executors import (
    NativeCommandExecutor,
    TranslatedCommandExecutor,
    FallbackCommandExecutor,
)
from scrappy.platform.protocols.execution import ExecutionResult


class TestNativeCommandExecutor:
    """Tests for NativeCommandExecutor."""

    def _create_executor(self):
        """Create executor with mock detector."""
        detector = Mock()
        return NativeCommandExecutor(detector)

    @pytest.mark.unit
    def test_init_stores_detector(self):
        """Executor should store the detector."""
        detector = Mock()
        executor = NativeCommandExecutor(detector)
        assert executor._detector is detector

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_success(self, mock_run):
        """Successful execution should return output with returncode 0."""
        mock_run.return_value = Mock(
            stdout="file1.txt\nfile2.txt\n",
            stderr="",
            returncode=0
        )
        executor = self._create_executor()

        result = executor.execute("ls -la")

        assert result.output == "file1.txt\nfile2.txt\n"
        assert result.returncode == 0
        assert result.method == 'native'
        assert result.success is True

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_with_stderr(self, mock_run):
        """Execution should combine stdout and stderr."""
        mock_run.return_value = Mock(
            stdout="output\n",
            stderr="warning: something\n",
            returncode=0
        )
        executor = self._create_executor()

        result = executor.execute("some_command")

        assert result.output == "output\nwarning: something\n"
        assert result.returncode == 0

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_failure(self, mock_run):
        """Failed execution should return non-zero returncode."""
        mock_run.return_value = Mock(
            stdout="",
            stderr="command not found\n",
            returncode=127
        )
        executor = self._create_executor()

        result = executor.execute("nonexistent_command")

        assert result.output == "command not found\n"
        assert result.returncode == 127
        assert result.method == 'native'
        assert result.success is False

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_with_custom_cwd(self, mock_run):
        """Execution should use provided working directory."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        executor = self._create_executor()

        executor.execute("ls", cwd="/tmp/test")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['cwd'] == "/tmp/test"

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_with_custom_timeout(self, mock_run):
        """Execution should use provided timeout."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        executor = self._create_executor()

        result = executor.execute("long_command", timeout=60)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['timeout'] == 60
        assert result.success is True

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_timeout_expired(self, mock_run):
        """Timeout should return special result."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)
        executor = self._create_executor()

        result = executor.execute("slow_command", timeout=30)

        assert result.returncode == 124
        assert result.method == 'timeout'
        assert "timed out after 30 seconds" in result.output

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_exception(self, mock_run):
        """Generic exception should return error result."""
        mock_run.side_effect = Exception("Something went wrong")
        executor = self._create_executor()

        result = executor.execute("bad_command")

        assert result.returncode == 1
        assert result.method == 'error'
        assert "Execution error" in result.output
        assert "Something went wrong" in result.output

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_uses_shell_true(self, mock_run):
        """Execution should use shell=True."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        executor = self._create_executor()

        executor.execute("echo hello")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['shell'] is True

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_uses_utf8_encoding(self, mock_run):
        """Execution should use UTF-8 encoding."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        executor = self._create_executor()

        executor.execute("echo test")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['encoding'] == 'utf-8'
        assert call_kwargs['errors'] == 'replace'


class TestTranslatedCommandExecutor:
    """Tests for TranslatedCommandExecutor."""

    def _create_executor(self, was_translated=True, translated_cmd="dir"):
        """Create executor with mock dependencies."""
        detector = Mock()
        translator = Mock()
        translator.translate_command.return_value = (translated_cmd, was_translated)
        return TranslatedCommandExecutor(detector, translator), translator

    @pytest.mark.unit
    def test_init_stores_dependencies(self):
        """Executor should store detector and translator."""
        detector = Mock()
        translator = Mock()
        executor = TranslatedCommandExecutor(detector, translator)

        assert executor._detector is detector
        assert executor._translator is translator

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_translates_command(self, mock_run):
        """Execution should translate command before running."""
        mock_run.return_value = Mock(stdout="output", stderr="", returncode=0)
        executor, translator = self._create_executor(
            was_translated=True,
            translated_cmd="dir /b"
        )

        result = executor.execute("ls -1")

        translator.translate_command.assert_called_once_with("ls -1")
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == "dir /b"
        assert result.method == 'translated'
        assert result.success is True

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_success_returns_translated_method(self, mock_run):
        """Successful translated execution should use 'translated' method."""
        mock_run.return_value = Mock(stdout="output", stderr="", returncode=0)
        executor, _ = self._create_executor()

        result = executor.execute("ls")

        assert result.method == 'translated'
        assert result.returncode == 0

    @pytest.mark.unit
    def test_execute_not_translated_returns_early(self):
        """If translation fails, should return without running."""
        executor, translator = self._create_executor(
            was_translated=False,
            translated_cmd=""
        )

        result = executor.execute("unknown_command")

        assert result.returncode == 1
        assert result.method == 'not_translated'
        assert result.output == ''

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_with_custom_cwd(self, mock_run):
        """Execution should use provided working directory."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        executor, _ = self._create_executor()

        executor.execute("ls", cwd="/custom/path")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['cwd'] == "/custom/path"

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_timeout_expired(self, mock_run):
        """Timeout should return special result."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 45)
        executor, _ = self._create_executor()

        result = executor.execute("slow_cmd", timeout=45)

        assert result.returncode == 124
        assert result.method == 'timeout'
        assert "45 seconds" in result.output

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_exception(self, mock_run):
        """Generic exception should return error result."""
        mock_run.side_effect = Exception("Translation failed")
        executor, _ = self._create_executor()

        result = executor.execute("cmd")

        assert result.returncode == 1
        assert result.method == 'error'
        assert "Translation execution error" in result.output

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_execute_combines_stdout_stderr(self, mock_run):
        """Output should combine stdout and stderr."""
        mock_run.return_value = Mock(
            stdout="standard output\n",
            stderr="error output\n",
            returncode=0
        )
        executor, _ = self._create_executor()

        result = executor.execute("cmd")

        assert result.output == "standard output\nerror output\n"


class TestFallbackCommandExecutor:
    """Tests for FallbackCommandExecutor."""

    def _create_executor(self, is_windows=True):
        """Create executor with mock dependencies."""
        detector = Mock()
        detector.is_windows.return_value = is_windows
        fallback = Mock()
        return FallbackCommandExecutor(detector, fallback), fallback, detector

    @pytest.mark.unit
    def test_init_stores_dependencies(self):
        """Executor should store detector and fallback."""
        detector = Mock()
        fallback = Mock()
        executor = FallbackCommandExecutor(detector, fallback)

        assert executor._detector is detector
        assert executor._fallback is fallback

    @pytest.mark.unit
    def test_execute_not_windows_returns_early(self):
        """On non-Windows, should return fallback_not_needed."""
        executor, fallback, _ = self._create_executor(is_windows=False)

        result = executor.execute("ls -la")

        assert result.returncode == 1
        assert result.method == 'fallback_not_needed'
        fallback.ls.assert_not_called()

    @pytest.mark.unit
    def test_execute_empty_command(self):
        """Empty command should return error."""
        executor, _, _ = self._create_executor()

        result = executor.execute("   ")

        assert result.returncode == 1
        assert result.method == 'error'
        assert result.output == 'Empty command'

    @pytest.mark.unit
    def test_execute_ls_command(self):
        """ls command should dispatch to fallback.ls."""
        executor, fallback, _ = self._create_executor()
        fallback.ls.return_value = {'output': 'file1\nfile2', 'returncode': 0}

        result = executor.execute("ls -la")

        fallback.ls.assert_called_once()
        assert result.output == 'file1\nfile2'
        assert result.returncode == 0
        assert result.method == 'python_fallback'

    @pytest.mark.unit
    def test_execute_pwd_command(self):
        """pwd command should dispatch to fallback.pwd."""
        executor, fallback, _ = self._create_executor()
        fallback.pwd.return_value = {'output': '/home/user', 'returncode': 0}

        result = executor.execute("pwd")

        fallback.pwd.assert_called_once()
        assert result.output == '/home/user'

    @pytest.mark.unit
    def test_execute_cat_command(self):
        """cat command should dispatch to fallback.cat."""
        executor, fallback, _ = self._create_executor()
        fallback.cat.return_value = {'output': 'file contents', 'returncode': 0}

        result = executor.execute("cat file.txt")

        fallback.cat.assert_called_once()
        assert result.output == 'file contents'

    @pytest.mark.unit
    def test_execute_mkdir_without_p_not_handled(self):
        """mkdir without -p should not be handled."""
        executor, fallback, _ = self._create_executor()

        result = executor.execute("mkdir newdir")

        fallback.mkdir_p.assert_not_called()
        assert result.method == 'fallback_unavailable'

    @pytest.mark.unit
    def test_execute_unknown_command(self):
        """Unknown command should return fallback_unavailable."""
        executor, fallback, _ = self._create_executor()

        result = executor.execute("unknown_command arg1 arg2")

        assert result.returncode == 1
        assert result.method == 'fallback_unavailable'
        assert result.output == ''

    @pytest.mark.unit
    def test_execute_fallback_exception(self):
        """Exception in fallback should return error result."""
        executor, fallback, _ = self._create_executor()
        fallback.ls.side_effect = Exception("Fallback failed")

        result = executor.execute("ls")

        assert result.returncode == 1
        assert result.method == 'error'
        assert "Python fallback error" in result.output
        assert "Fallback failed" in result.output

    @pytest.mark.unit
    def test_execute_passes_args_to_fallback(self):
        """Arguments should be passed to fallback methods."""
        executor, fallback, _ = self._create_executor()
        fallback.ls.return_value = {'output': '', 'returncode': 0}

        executor.execute("ls -la /tmp")

        args, kwargs = fallback.ls.call_args
        # First arg should be ['-la', '/tmp']
        assert args[0] == ['-la', '/tmp']

    @pytest.mark.unit
    def test_execute_case_insensitive_command(self):
        """Command matching should be case insensitive."""
        executor, fallback, _ = self._create_executor()
        fallback.ls.return_value = {'output': '', 'returncode': 0}

        result = executor.execute("LS -la")

        fallback.ls.assert_called_once()
        assert result.method == 'python_fallback'


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    @pytest.mark.unit
    def test_success_property_true_when_returncode_zero(self):
        """success should be True when returncode is 0."""
        result = ExecutionResult(output="ok", returncode=0, method="native")
        assert result.success is True

    @pytest.mark.unit
    def test_success_property_false_when_returncode_nonzero(self):
        """success should be False when returncode is non-zero."""
        result = ExecutionResult(output="error", returncode=1, method="native")
        assert result.success is False

    @pytest.mark.unit
    def test_error_message_none_when_successful(self):
        """error_message should be None when successful."""
        result = ExecutionResult(output="ok", returncode=0, method="native")
        assert result.error_message is None

    @pytest.mark.unit
    def test_error_message_returns_output_when_failed(self):
        """error_message should return output when failed."""
        result = ExecutionResult(output="command failed", returncode=1, method="native")
        assert result.error_message == "command failed"

    @pytest.mark.unit
    def test_error_classmethod(self):
        """error() should create error result."""
        result = ExecutionResult.error("Something went wrong")

        assert result.output == "Something went wrong"
        assert result.returncode == 1
        assert result.method == "error"
        assert result.success is False


class TestExecutorIntegration:
    """Integration tests for executor behavior."""

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_native_executor_default_cwd(self, mock_run):
        """Native executor should use current directory when cwd not specified."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        detector = Mock()
        executor = NativeCommandExecutor(detector)

        result = executor.execute("ls")

        call_kwargs = mock_run.call_args[1]
        # Should use current working directory
        assert call_kwargs['cwd'] == str(Path.cwd())
        assert result.success is True

    @pytest.mark.unit
    @patch('scrappy.platform.executors.subprocess.run')
    def test_translated_executor_default_cwd(self, mock_run):
        """Translated executor should use current directory when cwd not specified."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)
        detector = Mock()
        translator = Mock()
        translator.translate_command.return_value = ("dir", True)
        executor = TranslatedCommandExecutor(detector, translator)

        result = executor.execute("ls")

        call_kwargs = mock_run.call_args[1]
        # Should use current working directory
        assert call_kwargs['cwd'] == str(Path.cwd())
        assert result.success is True

    @pytest.mark.unit
    def test_fallback_executor_handles_command_with_only_spaces(self):
        """Fallback executor should handle commands that are only whitespace."""
        detector = Mock()
        detector.is_windows.return_value = True
        fallback = Mock()
        executor = FallbackCommandExecutor(detector, fallback)

        result = executor.execute("     ")

        assert result.returncode == 1
        assert result.method == 'error'
