"""
Platform detection and cross-platform utilities.

Provides platform-aware command validation and translation.
"""

import platform
import shutil
from typing import Dict, List, Optional, Tuple


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_unix() -> bool:
    """Check if running on Unix-like system (Linux, macOS, BSD)."""
    return platform.system() in ("Linux", "Darwin", "FreeBSD", "OpenBSD", "NetBSD")


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


def get_platform_name() -> str:
    """Get human-readable platform name."""
    system = platform.system()
    if system == "Windows":
        return "Windows"
    elif system == "Darwin":
        return "macOS"
    elif system == "Linux":
        return "Linux"
    else:
        return system


def get_shell_info() -> Dict[str, Optional[str]]:
    """
    Get information about available shells.

    Returns:
        Dict with 'default', 'bash', 'powershell', 'cmd' keys.
    """
    info = {
        'default': None,
        'bash': shutil.which('bash'),
        'powershell': None,
        'cmd': None,
        'sh': shutil.which('sh'),
    }

    if is_windows():
        info['cmd'] = shutil.which('cmd')
        info['powershell'] = shutil.which('powershell') or shutil.which('pwsh')
        # Default on Windows is cmd.exe
        info['default'] = info['cmd'] or info['powershell']
    else:
        # Default on Unix is sh or bash
        info['default'] = info['bash'] or info['sh']

    return info


def has_git_bash() -> bool:
    """Check if Git Bash is available (common on Windows)."""
    if not is_windows():
        return False
    bash_path = shutil.which('bash')
    return bash_path is not None and 'git' in bash_path.lower()


def get_file_check_command(path: str) -> str:
    """
    Get platform-appropriate command to check if a file exists.

    Args:
        path: File path to check

    Returns:
        Shell command that checks file existence
    """
    if is_windows():
        # Use PowerShell's Test-Path or cmd's IF EXIST
        return f'if exist "{path}" (echo File exists) else (echo File does not exist)'
    else:
        return f'test -f "{path}" && echo "File exists" || echo "File does not exist"'


def get_directory_list_command(path: str = ".") -> str:
    """
    Get platform-appropriate command to list directory contents.

    Args:
        path: Directory path to list

    Returns:
        Shell command to list directory
    """
    if is_windows():
        return f'dir "{path}"'
    else:
        return f'ls -la "{path}"'


def translate_command_for_platform(command: str) -> Tuple[str, bool]:
    """
    Translate Unix commands to Windows equivalents when necessary.

    Args:
        command: Original command

    Returns:
        Tuple of (translated_command, was_translated)
    """
    if not is_windows():
        return command, False

    # Command translation map for common Unix commands
    translations = {
        'ls': 'dir',
        'ls -la': 'dir',
        'ls -l': 'dir',
        'ls -a': 'dir /a',
        'pwd': 'cd',
        'cat': 'type',
        'rm': 'del',
        'rm -rf': 'rmdir /s /q',
        'cp': 'copy',
        'cp -r': 'xcopy /e /i',
        'mv': 'move',
        'mkdir -p': 'mkdir',
        'touch': 'type nul >',
        'grep': 'findstr',
        'clear': 'cls',
        'which': 'where',
    }

    # Check if command starts with a Unix command
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return command, False

    base_cmd = cmd_parts[0].lower()

    # Check for exact matches first
    for unix_cmd, win_cmd in translations.items():
        if command.strip().lower().startswith(unix_cmd):
            # Translate the command
            new_cmd = win_cmd + command[len(unix_cmd):]
            return new_cmd, True

    # Check if the base command exists in translations
    if base_cmd in translations:
        # Replace just the command part
        new_cmd = translations[base_cmd] + command[len(base_cmd):]
        return new_cmd, True

    return command, False


def get_dangerous_commands() -> List[str]:
    """
    Get list of dangerous command patterns for the current platform.

    Returns:
        List of dangerous command patterns to block
    """
    common_dangerous = [
        'format',   # Disk formatting
        'mkfs',     # Make filesystem
    ]

    if is_windows():
        return common_dangerous + [
            'del /f /s /q',  # Force delete recursively
            'rmdir /s /q',   # Remove directory tree quietly
            'format c:',     # Format C drive
            'rd /s /q',      # Remove directory silently
            '> nul',         # Redirect to null (less dangerous but can hide output)
            'diskpart',      # Disk partitioning
            'reg delete',    # Registry deletion
        ]
    else:
        return common_dangerous + [
            'rm -rf /',      # Delete root
            'rm -rf ~',      # Delete home
            'rm -rf *',      # Delete everything
            '> /dev/',       # Write to device
            'sudo rm',       # Privileged delete
            'dd if=',        # Disk dump (can overwrite disks)
            ':(){:|:&};:',   # Fork bomb
            'chmod -R 777 /',  # Insecure permissions on root
        ]


def get_interactive_commands() -> List[str]:
    """
    Get list of commands that may prompt for user input.

    Returns:
        List of interactive command patterns
    """
    common_interactive = [
        # Package managers
        'npm init', 'npm create', 'yarn init', 'yarn create',
        'pnpm init', 'pnpm create',
        'pip install',  # May prompt for confirmation
        'cargo init', 'cargo new',
        'go mod init',
        # Version control
        'git commit', 'git rebase -i', 'git merge',
        'git add -p', 'git checkout -p',
        # Database clients
        'mysql', 'psql', 'mongo', 'redis-cli', 'sqlite3',
    ]

    if is_windows():
        return common_interactive + [
            'choco install',  # Chocolatey
            'winget install', # Windows Package Manager
            'scoop install',  # Scoop
        ]
    else:
        return common_interactive + [
            'sudo ',          # Requires password
            'ssh ', 'scp ',   # SSH commands
            'apt install', 'apt-get install',
            'dnf install', 'yum install',
            'brew install',
        ]


def validate_command_for_platform(command: str) -> Tuple[bool, str]:
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

    # Unix-only commands that don't exist on Windows by default
    unix_only = {
        'test', 'grep', 'sed', 'awk', 'curl', 'wget',
        'chmod', 'chown', 'ln', 'tar', 'gzip', 'gunzip',
        'head', 'tail', 'wc', 'sort', 'uniq', 'diff',
        'find', 'xargs', 'tee', 'nohup', 'bg', 'fg',
    }

    # Windows-only commands
    windows_only = {
        'dir', 'copy', 'xcopy', 'move', 'ren', 'rename',
        'del', 'erase', 'rd', 'rmdir', 'md', 'mkdir',
        'type', 'more', 'find', 'findstr', 'where',
        'cls', 'echo', 'set', 'path', 'vol', 'ver',
        'attrib', 'cacls', 'cipher', 'compact',
    }

    # Check for shell-specific syntax
    if is_windows():
        # Check for Unix-specific syntax
        if cmd_lower.startswith('[') and ']' in cmd_lower:
            return False, "Unix test syntax '[ ]' not supported on Windows. Use 'if exist' instead."
        if cmd_lower.startswith('test '):
            return False, "'test' command not available on Windows. Use 'if exist' instead."
        if base_cmd in unix_only:
            # Check if Git Bash or WSL might be available
            if has_git_bash():
                return True, f"Command '{base_cmd}' may work via Git Bash"
            return False, f"Unix command '{base_cmd}' not available on Windows. Use Windows equivalent."
    else:
        # Check for Windows-specific commands on Unix
        if base_cmd in windows_only and base_cmd not in {'mkdir', 'find', 'echo'}:
            return False, f"Windows command '{base_cmd}' not available on Unix systems."

    return True, ""


def get_null_device() -> str:
    """Get the null device path for the current platform."""
    if is_windows():
        return "NUL"
    else:
        return "/dev/null"


def get_path_separator() -> str:
    """Get the path separator for the current platform."""
    if is_windows():
        return "\\"
    else:
        return "/"


def normalize_path_for_shell(path: str) -> str:
    """
    Normalize a path for use in shell commands.

    On Windows, this handles the difference between Python paths (/)
    and cmd.exe paths (\\).

    Args:
        path: Path to normalize

    Returns:
        Normalized path string
    """
    if is_windows():
        # Windows cmd.exe prefers backslashes
        return path.replace('/', '\\')
    else:
        # Unix uses forward slashes
        return path.replace('\\', '/')
