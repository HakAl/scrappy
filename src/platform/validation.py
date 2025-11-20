"""
Command validation implementation.

Provides platform-specific command validation to ensure safety and
compatibility before execution.
"""

from typing import List, Tuple

from src.platform.protocols.validation import CommandValidatorProtocol
from src.platform.protocols.detection import PlatformDetectorProtocol


class SecurityCommandValidator:
    """
    Concrete implementation of command validation protocol.

    Validates commands for safety (dangerous patterns) and platform
    compatibility before execution.

    All dependencies are injected via constructor to enable testing.
    """

    def __init__(
        self,
        detector: PlatformDetectorProtocol
    ):
        """
        Initialize the command validator.

        Args:
            detector: Platform detector to determine current platform.
        """
        self._detector = detector

    def validate_command_for_platform(self, command: str) -> Tuple[bool, str]:
        """
        Validate if a command is appropriate for the current platform.

        Args:
            command: Command to validate

        Returns:
            Tuple of (is_valid, warning_message)
        """
        if not command.strip():
            return False, "Empty command"

        cmd_lower = command.lower().strip()
        cmd_parts = cmd_lower.split()
        base_cmd = cmd_parts[0] if cmd_parts else ""

        unix_only = {
            'test', 'grep', 'sed', 'awk', 'curl', 'wget',
            'chmod', 'chown', 'ln', 'tar', 'gzip', 'gunzip',
            'head', 'tail', 'wc', 'sort', 'uniq', 'diff',
            'find', 'xargs', 'tee', 'nohup', 'bg', 'fg',
        }

        windows_only = {
            'dir', 'copy', 'xcopy', 'move', 'ren', 'rename',
            'del', 'erase', 'rd', 'rmdir', 'md', 'mkdir',
            'type', 'more', 'find', 'findstr', 'where',
            'cls', 'echo', 'set', 'path', 'vol', 'ver',
            'attrib', 'cacls', 'cipher', 'compact',
        }

        powershell_cmdlets = {
            'new-item', 'remove-item', 'copy-item', 'move-item', 'rename-item',
            'get-childitem', 'set-content', 'get-content', 'add-content', 'clear-content',
            'test-path', 'invoke-webrequest', 'invoke-restmethod',
            'convertto-json', 'convertfrom-json', 'out-file',
            'get-item', 'set-item', 'clear-item',
            'new-object', 'select-object', 'where-object', 'foreach-object',
            'get-location', 'set-location', 'push-location', 'pop-location',
        }

        if self._detector.is_windows():
            if base_cmd in powershell_cmdlets:
                return False, f"PowerShell cmdlet '{base_cmd}' not available in cmd.exe. Use cmd.exe equivalent or Python fallback."

            if cmd_lower.startswith('[') and ']' in cmd_lower:
                return False, "Unix test syntax '[ ]' not supported on Windows. Use 'if exist' instead."

            if cmd_lower.startswith('test '):
                return False, "'test' command not available on Windows. Use 'if exist' instead."

            if base_cmd in unix_only:
                if self._detector.has_git_bash():
                    return True, f"Command '{base_cmd}' may work via Git Bash"
                return False, f"Unix command '{base_cmd}' not available on Windows. Use Windows equivalent."
        else:
            if base_cmd in windows_only and base_cmd not in {'mkdir', 'find', 'echo'}:
                return False, f"Windows command '{base_cmd}' not available on Unix systems."

        return True, ""

    def get_dangerous_commands(self) -> List[str]:
        """
        Get list of dangerous command patterns for the current platform.

        Returns:
            List of dangerous command patterns to block (regex patterns)
        """
        common_dangerous = [
            r'\bformat\s+[a-zA-Z]:',
            r'\bmkfs\b',
        ]

        if self._detector.is_windows():
            return common_dangerous + [
                r'\bdel\s+/[fqs].*\s+[a-zA-Z]:\\$',
                r'\bdel\s+/[fqs].*\s+[a-zA-Z]:\\\*',
                r'\brmdir\s+/s\s+/q\s+[a-zA-Z]:\\$',
                r'\brmdir\s+/s\s+/q\s+[a-zA-Z]:\\\s*$',
                r'\brd\s+/s\s+/q\s+[a-zA-Z]:\\$',
                r'\brd\s+/s\s+/q\s+[a-zA-Z]:\\\s*$',
                r'\bformat\s+[a-zA-Z]:',
                r'\bdiskpart\b',
                r'\breg\s+delete\s+HKLM',
                r'\breg\s+delete\s+HKEY_LOCAL_MACHINE',
            ]
        else:
            return common_dangerous + [
                r'\brm\s+-rf\s+/$',
                r'\brm\s+-rf\s+~',
                r'\brm\s+-rf\s+/\*',
                r'\brm\s+-rf\s+\*\s*$',
                r'>\s*/dev/sd',
                r'\bsudo\s+rm\s+-rf\s+/',
                r'\bdd\s+if=.*of=/dev/sd',
                r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:',
                r'\bchmod\s+-R\s+777\s+/',
            ]

    def get_interactive_commands(self) -> List[str]:
        """
        Get list of commands that may prompt for user input.

        Returns:
            List of interactive command patterns
        """
        common_interactive = [
            'npm init', 'npm create', 'yarn init', 'yarn create',
            'pnpm init', 'pnpm create',
            'pip install',
            'cargo init', 'cargo new',
            'go mod init',
            'git commit', 'git rebase -i', 'git merge',
            'git add -p', 'git checkout -p',
            'mysql', 'psql', 'mongo', 'redis-cli', 'sqlite3',
        ]

        if self._detector.is_windows():
            return common_interactive + [
                'choco install',
                'winget install',
                'scoop install',
            ]
        else:
            return common_interactive + [
                'sudo ',
                'ssh ', 'scp ',
                'apt install', 'apt-get install',
                'dnf install', 'yum install',
                'brew install',
            ]
