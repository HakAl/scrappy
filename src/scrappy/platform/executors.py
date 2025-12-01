"""
Command executor implementations.

Provides different strategies for executing shell commands with
appropriate platform handling and fallback mechanisms.
"""

import subprocess
from pathlib import Path
from typing import Optional

from scrappy.platform.protocols.execution import CommandExecutorProtocol, ExecutionResult
from scrappy.platform.protocols.detection import PlatformDetectorProtocol
from scrappy.platform.protocols.translation import CommandTranslatorProtocol
from scrappy.platform.protocols.fallback import PythonCommandFallbackProtocol


class NativeCommandExecutor:
    """
    Execute commands natively without translation.

    Attempts to run commands as-is on the current platform.
    Suitable for platform-appropriate commands that don't require translation.
    """

    def __init__(self, detector: PlatformDetectorProtocol):
        """
        Initialize the native command executor.

        Args:
            detector: Platform detector (unused but kept for consistency)
        """
        self._detector = detector

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute command natively without translation.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            ExecutionResult with output, returncode, and method
        """
        working_dir = cwd or str(Path.cwd())

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            return ExecutionResult(
                output=result.stdout + result.stderr,
                returncode=result.returncode,
                method='native'
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                output=f'Command timed out after {timeout} seconds',
                returncode=124,
                method='timeout'
            )
        except Exception as e:
            return ExecutionResult(
                output=f'Execution error: {str(e)}',
                returncode=1,
                method='error'
            )


class TranslatedCommandExecutor:
    """
    Execute commands after translating them for the current platform.

    Translates Unix commands to Windows equivalents before execution.
    Falls back to native execution if translation is not needed.
    """

    def __init__(
        self,
        detector: PlatformDetectorProtocol,
        translator: CommandTranslatorProtocol
    ):
        """
        Initialize the translated command executor.

        Args:
            detector: Platform detector
            translator: Command translator
        """
        self._detector = detector
        self._translator = translator

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Translate and execute command.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            ExecutionResult with output, returncode, and method
        """
        working_dir = cwd or str(Path.cwd())

        translated_cmd, was_translated = self._translator.translate_command(command)

        if not was_translated:
            return ExecutionResult(
                output='',
                returncode=1,
                method='not_translated'
            )

        try:
            result = subprocess.run(
                translated_cmd,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            return ExecutionResult(
                output=result.stdout + result.stderr,
                returncode=result.returncode,
                method='translated'
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                output=f'Command timed out after {timeout} seconds',
                returncode=124,
                method='timeout'
            )
        except Exception as e:
            return ExecutionResult(
                output=f'Translation execution error: {str(e)}',
                returncode=1,
                method='error'
            )


class FallbackCommandExecutor:
    """
    Execute commands using Python fallback implementations.

    Uses pure Python implementations of Unix commands when native
    execution is not available. Primarily for Windows without Git Bash.
    """

    def __init__(
        self,
        detector: PlatformDetectorProtocol,
        fallback: PythonCommandFallbackProtocol
    ):
        """
        Initialize the fallback command executor.

        Args:
            detector: Platform detector
            fallback: Python command fallback implementation
        """
        self._detector = detector
        self._fallback = fallback

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute command using Python fallback.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds (unused for fallback)

        Returns:
            ExecutionResult with output, returncode, and method
        """
        if not self._detector.is_windows():
            return ExecutionResult(
                output='',
                returncode=1,
                method='fallback_not_needed'
            )

        working_dir = Path(cwd) if cwd else Path.cwd()

        cmd_parts = command.strip().split()
        if not cmd_parts:
            return ExecutionResult(
                output='Empty command',
                returncode=1,
                method='error'
            )

        base_cmd = cmd_parts[0].lower()
        args = cmd_parts[1:] if len(cmd_parts) > 1 else []

        try:
            result_dict = None

            if base_cmd == 'ls':
                result_dict = self._fallback.ls(args, working_dir)
            elif base_cmd == 'pwd':
                result_dict = self._fallback.pwd(working_dir)
            elif base_cmd == 'cat':
                result_dict = self._fallback.cat(args, working_dir)
            elif base_cmd == 'head':
                result_dict = self._fallback.head(args, working_dir)
            elif base_cmd == 'tail':
                result_dict = self._fallback.tail(args, working_dir)
            elif base_cmd == 'grep':
                result_dict = self._fallback.grep(args, working_dir)
            elif base_cmd == 'find':
                result_dict = self._fallback.find(args, working_dir)
            elif base_cmd == 'wc':
                result_dict = self._fallback.wc(args, working_dir)
            elif base_cmd == 'which':
                result_dict = self._fallback.which(args)
            elif base_cmd == 'touch':
                result_dict = self._fallback.touch(args, working_dir)
            elif base_cmd == 'mkdir' and '-p' in args:
                result_dict = self._fallback.mkdir_p(args, working_dir)
            elif base_cmd == 'rm':
                result_dict = self._fallback.rm(args, working_dir)
            elif base_cmd == 'cp':
                result_dict = self._fallback.cp(args, working_dir)
            elif base_cmd == 'mv':
                result_dict = self._fallback.mv(args, working_dir)

            if result_dict is None:
                return ExecutionResult(
                    output='',
                    returncode=1,
                    method='fallback_unavailable'
                )

            return ExecutionResult(
                output=result_dict['output'],
                returncode=result_dict['returncode'],
                method='python_fallback'
            )

        except Exception as e:
            return ExecutionResult(
                output=f'Python fallback error: {str(e)}',
                returncode=1,
                method='error'
            )
