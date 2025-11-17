"""
Platform detection and cross-platform utilities.

Provides platform-aware command validation and translation.
"""

import platform
import shutil
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlencode, quote_plus


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
        List of dangerous command patterns to block (regex patterns)
    """
    # Common dangerous patterns (regex)
    common_dangerous = [
        r'\bformat\s+[a-zA-Z]:',  # Disk formatting with drive letter
        r'\bmkfs\b',              # Make filesystem
    ]

    if is_windows():
        return common_dangerous + [
            # Only block recursive deletes on drive roots or system paths
            r'\bdel\s+/[fqs].*\s+[a-zA-Z]:\\$',      # del /f /s /q C:\
            r'\bdel\s+/[fqs].*\s+[a-zA-Z]:\\\*',     # del /f /s /q C:\*
            r'\brmdir\s+/s\s+/q\s+[a-zA-Z]:\\$',     # rmdir /s /q C:\
            r'\brmdir\s+/s\s+/q\s+[a-zA-Z]:\\\s*$',  # rmdir /s /q C: (end of command)
            r'\brd\s+/s\s+/q\s+[a-zA-Z]:\\$',        # rd /s /q C:\
            r'\brd\s+/s\s+/q\s+[a-zA-Z]:\\\s*$',     # rd /s /q C: (end of command)
            r'\bformat\s+[a-zA-Z]:',                  # Format any drive
            r'\bdiskpart\b',                          # Disk partitioning
            r'\breg\s+delete\s+HKLM',                 # Registry deletion (system hive)
            r'\breg\s+delete\s+HKEY_LOCAL_MACHINE',   # Registry deletion (system hive)
        ]
    else:
        return common_dangerous + [
            r'\brm\s+-rf\s+/$',           # Delete root
            r'\brm\s+-rf\s+~',            # Delete home
            r'\brm\s+-rf\s+/\*',          # Delete everything in root
            r'\brm\s+-rf\s+\*\s*$',       # Delete everything in cwd
            r'>\s*/dev/sd',               # Write to disk device
            r'\bsudo\s+rm\s+-rf\s+/',     # Privileged delete of root
            r'\bdd\s+if=.*of=/dev/sd',    # Disk dump to drive
            r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:',  # Fork bomb
            r'\bchmod\s+-R\s+777\s+/',    # Insecure permissions on root
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

    # PowerShell cmdlets (Verb-Noun pattern) that won't work in cmd.exe
    powershell_cmdlets = {
        'new-item', 'remove-item', 'copy-item', 'move-item', 'rename-item',
        'get-childitem', 'set-content', 'get-content', 'add-content', 'clear-content',
        'test-path', 'invoke-webrequest', 'invoke-restmethod',
        'convertto-json', 'convertfrom-json', 'out-file',
        'get-item', 'set-item', 'clear-item',
        'new-object', 'select-object', 'where-object', 'foreach-object',
        'get-location', 'set-location', 'push-location', 'pop-location',
    }

    # Check for shell-specific syntax
    if is_windows():
        # Check for PowerShell cmdlets (won't work in cmd.exe subprocess)
        if base_cmd in powershell_cmdlets:
            return False, f"PowerShell cmdlet '{base_cmd}' not available in cmd.exe. Use cmd.exe equivalent or Python fallback."

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


def normalize_command_paths(command: str) -> Tuple[str, bool, str]:
    """
    Normalize paths in shell commands for the current platform.

    On Windows, converts forward slashes to backslashes in path arguments.
    This fixes issues where commands like 'mkdir website/frontend' fail
    because Windows cmd.exe doesn't accept forward slashes in paths.

    Args:
        command: Shell command that may contain paths

    Returns:
        Tuple of (normalized_command, was_modified, message)
    """
    if not is_windows():
        return command, False, ""

    original_command = command

    # Commands that take path arguments
    path_commands = [
        'mkdir', 'md', 'rmdir', 'rd', 'cd', 'dir', 'copy', 'xcopy',
        'move', 'del', 'erase', 'type', 'more', 'attrib'
    ]

    # PowerShell parameters that contain paths
    powershell_path_params = [
        '-Path', '-LiteralPath', '-Destination', '-Source', '-FilePath',
        '-OutputPath', '-InputPath', '-TargetPath'
    ]

    # Split command into parts, preserving quotes
    parts = []
    current = ""
    in_quote = False
    quote_char = None

    for char in command:
        if char in ('"', "'") and not in_quote:
            in_quote = True
            quote_char = char
            current += char
        elif char == quote_char and in_quote:
            in_quote = False
            quote_char = None
            current += char
        elif char == ' ' and not in_quote:
            if current:
                parts.append(current)
                current = ""
        else:
            current += char
    if current:
        parts.append(current)

    if not parts:
        return command, False, ""

    base_cmd = parts[0].lower()

    # Check if this is a command that uses paths
    is_path_command = any(base_cmd == cmd or base_cmd.endswith('\\' + cmd) for cmd in path_commands)

    # Also check for PowerShell path parameters in any command
    has_powershell_path_param = any(
        any(part.lower() == param.lower() for param in powershell_path_params)
        for part in parts
    )

    if not is_path_command and not has_powershell_path_param:
        return command, False, ""

    # Normalize paths in arguments
    modified = False
    new_parts = [parts[0]]
    next_is_path = False

    for i, part in enumerate(parts[1:], 1):
        # Check if this is a PowerShell path parameter
        is_path_param = any(part.lower() == param.lower() for param in powershell_path_params)

        if is_path_param:
            new_parts.append(part)
            next_is_path = True
            continue

        # If previous part was a path parameter, this is the path value
        if next_is_path:
            next_is_path = False
            if '/' in part and not part.startswith('http://') and not part.startswith('https://'):
                if part.startswith('"') and part.endswith('"'):
                    inner = part[1:-1]
                    normalized = inner.replace('/', '\\')
                    new_parts.append(f'"{normalized}"')
                elif part.startswith("'") and part.endswith("'"):
                    inner = part[1:-1]
                    normalized = inner.replace('/', '\\')
                    new_parts.append(f"'{normalized}'")
                else:
                    normalized = part.replace('/', '\\')
                    new_parts.append(normalized)
                modified = True
            else:
                new_parts.append(part)
            continue

        # Skip flags (but not PowerShell parameters which start with -)
        if (part.startswith('-') or part.startswith('/')) and not is_path_command:
            new_parts.append(part)
            continue

        # For path commands, check if this looks like a path
        if is_path_command and '/' in part and not part.startswith('http://') and not part.startswith('https://'):
            # Skip cmd.exe flags (like /s, /b, /y) - they start with / and are short
            if part.startswith('/') and len(part) <= 3 and not '/' in part[1:]:
                new_parts.append(part)
                continue

            # Preserve quotes around the path
            if part.startswith('"') and part.endswith('"'):
                inner = part[1:-1]
                normalized = inner.replace('/', '\\')
                new_parts.append(f'"{normalized}"')
            elif part.startswith("'") and part.endswith("'"):
                inner = part[1:-1]
                normalized = inner.replace('/', '\\')
                new_parts.append(f"'{normalized}'")
            else:
                normalized = part.replace('/', '\\')
                new_parts.append(normalized)
            modified = True
        else:
            new_parts.append(part)

    if modified:
        new_command = ' '.join(new_parts)
        message = f"Normalized paths for Windows: {original_command} -> {new_command}"
        return new_command, True, message

    return command, False, ""


def normalize_npm_command_for_windows(command: str) -> Tuple[str, bool, str]:
    """
    Normalize npm commands for Windows to prevent Unicode output issues.

    On Windows, npm commands with spinners and progress bars can crash due to
    Unicode encoding issues. This function adds flags to suppress these.

    Args:
        command: npm command to normalize

    Returns:
        Tuple of (normalized_command, was_modified, message)
    """
    if not is_windows():
        return command, False, ""

    original_command = command
    modified = False

    # Check for npm create commands (Vite, React, etc.)
    npm_create_patterns = [
        r'npm\s+create\s+',
        r'npx\s+create-',
        r'npm\s+init\s+',
    ]

    for pattern in npm_create_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            # Add environment variable to suppress colors/Unicode
            if 'NO_COLOR=' not in command and 'set NO_COLOR' not in command:
                # Prepend environment variable setting
                command = f'set NO_COLOR=1 && {command}'
                modified = True

            # Add --no-color flag if not present (for npm)
            if '--no-color' not in command and 'npm' in command:
                # Insert before any -- separator
                if ' -- ' in command:
                    parts = command.split(' -- ', 1)
                    command = f'{parts[0]} --no-color -- {parts[1]}'
                else:
                    command = command.rstrip() + ' --no-color'
                modified = True
            break

    # Check for npm install/run commands
    if re.search(r'npm\s+(install|i|run|start|build|test)', command, re.IGNORECASE):
        if '--no-progress' not in command:
            command = command.rstrip() + ' --no-progress'
            modified = True
        if '--no-color' not in command:
            command = command.rstrip() + ' --no-color'
            modified = True

    if modified:
        message = f"Added Windows npm flags to suppress Unicode output"
        return command, True, message

    return command, False, ""


def intercept_spring_initializr_download(command: str, target_dir: str = ".") -> Optional[Dict[str, Any]]:
    """
    Intercept Spring Initializr download commands and suggest using local templates.

    On Windows, downloading from start.spring.io often fails due to URL encoding issues.
    This function detects such commands and returns information to use local templates instead.

    Args:
        command: Shell command that might be downloading from Spring Initializr
        target_dir: Directory where the project should be created

    Returns:
        Dict with 'should_intercept', 'reason', 'suggested_action', and 'template_params'
        or None if not a Spring Initializr command
    """
    if 'start.spring.io' not in command:
        return None

    # Extract parameters from the URL
    params = {
        'group_id': 'com.example',
        'artifact_id': 'demo',
        'package_name': 'com.example.demo',
        'dependencies': ['web', 'data-jpa', 'h2', 'validation', 'security']
    }

    # Try to extract actual parameters from URL
    url_match = re.search(r'https?://start\.spring\.io[^"\'\s]+', command)
    if url_match:
        url = url_match.group(0)
        if '?' in url:
            query = url.split('?', 1)[1]
            for param in query.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    if key == 'groupId':
                        params['group_id'] = value
                    elif key == 'artifactId':
                        params['artifact_id'] = value
                    elif key == 'packageName':
                        params['package_name'] = value
                    elif key == 'dependencies':
                        params['dependencies'] = value.split(',')
                    elif key == 'baseDir':
                        params['artifact_id'] = value  # Use baseDir as artifact name

    return {
        'should_intercept': True,
        'reason': 'Spring Initializr downloads often fail on Windows due to URL encoding issues',
        'suggested_action': 'Use write_file to create Spring Boot project files directly',
        'template_params': params,
        'original_command': command
    }


def get_python_fallback(command: str, cwd: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Execute Unix commands using Python implementations when native commands fail.

    Args:
        command: Unix command to execute
        cwd: Working directory

    Returns:
        Dict with 'output', 'returncode', 'used_fallback' if fallback was used, None otherwise
    """
    if not is_windows():
        return None

    cmd_parts = command.strip().split()
    if not cmd_parts:
        return None

    base_cmd = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []
    working_dir = Path(cwd) if cwd else Path.cwd()

    try:
        # ls - list directory
        if base_cmd == 'ls':
            return _python_ls(args, working_dir)

        # pwd - print working directory
        elif base_cmd == 'pwd':
            return {
                'output': str(working_dir.resolve()),
                'returncode': 0,
                'used_fallback': True
            }

        # cat - concatenate files
        elif base_cmd == 'cat':
            return _python_cat(args, working_dir)

        # head - show first lines
        elif base_cmd == 'head':
            return _python_head(args, working_dir)

        # tail - show last lines
        elif base_cmd == 'tail':
            return _python_tail(args, working_dir)

        # grep - search pattern in files
        elif base_cmd == 'grep':
            return _python_grep(args, working_dir)

        # find - search for files
        elif base_cmd == 'find':
            return _python_find(args, working_dir)

        # wc - word count
        elif base_cmd == 'wc':
            return _python_wc(args, working_dir)

        # which - find command location
        elif base_cmd == 'which':
            return _python_which(args)

        # touch - create empty file
        elif base_cmd == 'touch':
            return _python_touch(args, working_dir)

        # mkdir with -p flag
        elif base_cmd == 'mkdir' and '-p' in args:
            return _python_mkdir_p(args, working_dir)

        # rm - remove files
        elif base_cmd == 'rm':
            return _python_rm(args, working_dir)

        # cp - copy files
        elif base_cmd == 'cp':
            return _python_cp(args, working_dir)

        # mv - move files
        elif base_cmd == 'mv':
            return _python_mv(args, working_dir)

    except Exception as e:
        return {
            'output': f'Python fallback error: {str(e)}',
            'returncode': 1,
            'used_fallback': True
        }

    return None


def _python_ls(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of ls command."""
    show_all = '-a' in args or '-la' in args or '-al' in args
    show_long = '-l' in args or '-la' in args or '-al' in args

    # Get target directory
    target = cwd
    for arg in args:
        if not arg.startswith('-'):
            target = cwd / arg
            break

    if not target.exists():
        return {'output': f'ls: {target}: No such file or directory', 'returncode': 1, 'used_fallback': True}

    if target.is_file():
        return {'output': str(target.name), 'returncode': 0, 'used_fallback': True}

    items = []
    for item in sorted(target.iterdir(), key=lambda x: x.name.lower()):
        if not show_all and item.name.startswith('.'):
            continue

        if show_long:
            stat = item.stat()
            size = stat.st_size
            mtime = stat.st_mtime
            from datetime import datetime
            date_str = datetime.fromtimestamp(mtime).strftime('%b %d %H:%M')
            type_char = 'd' if item.is_dir() else '-'
            items.append(f'{type_char}rw-r--r--  1 user  user  {size:>8} {date_str} {item.name}')
        else:
            items.append(item.name)

    output = '\n'.join(items) if show_long else '  '.join(items)
    return {'output': output, 'returncode': 0, 'used_fallback': True}


def _python_cat(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of cat command."""
    if not args:
        return {'output': 'cat: missing file operand', 'returncode': 1, 'used_fallback': True}

    output_parts = []
    for arg in args:
        if arg.startswith('-'):
            continue
        filepath = cwd / arg
        if not filepath.exists():
            return {'output': f'cat: {arg}: No such file or directory', 'returncode': 1, 'used_fallback': True}
        try:
            output_parts.append(filepath.read_text(encoding='utf-8', errors='replace'))
        except Exception as e:
            return {'output': f'cat: {arg}: {str(e)}', 'returncode': 1, 'used_fallback': True}

    return {'output': ''.join(output_parts), 'returncode': 0, 'used_fallback': True}


def _python_head(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of head command."""
    num_lines = 10
    files = []

    i = 0
    while i < len(args):
        if args[i] == '-n' and i + 1 < len(args):
            num_lines = int(args[i + 1])
            i += 2
        elif args[i].startswith('-') and args[i][1:].isdigit():
            num_lines = int(args[i][1:])
            i += 1
        elif not args[i].startswith('-'):
            files.append(args[i])
            i += 1
        else:
            i += 1

    if not files:
        return {'output': 'head: missing file operand', 'returncode': 1, 'used_fallback': True}

    output_parts = []
    for filepath_str in files:
        filepath = cwd / filepath_str
        if not filepath.exists():
            return {'output': f'head: {filepath_str}: No such file or directory', 'returncode': 1, 'used_fallback': True}

        lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()[:num_lines]
        if len(files) > 1:
            output_parts.append(f'==> {filepath_str} <==')
        output_parts.extend(lines)

    return {'output': '\n'.join(output_parts), 'returncode': 0, 'used_fallback': True}


def _python_tail(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of tail command."""
    num_lines = 10
    files = []

    i = 0
    while i < len(args):
        if args[i] == '-n' and i + 1 < len(args):
            num_lines = int(args[i + 1])
            i += 2
        elif args[i].startswith('-') and args[i][1:].isdigit():
            num_lines = int(args[i][1:])
            i += 1
        elif not args[i].startswith('-'):
            files.append(args[i])
            i += 1
        else:
            i += 1

    if not files:
        return {'output': 'tail: missing file operand', 'returncode': 1, 'used_fallback': True}

    output_parts = []
    for filepath_str in files:
        filepath = cwd / filepath_str
        if not filepath.exists():
            return {'output': f'tail: {filepath_str}: No such file or directory', 'returncode': 1, 'used_fallback': True}

        lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()[-num_lines:]
        if len(files) > 1:
            output_parts.append(f'==> {filepath_str} <==')
        output_parts.extend(lines)

    return {'output': '\n'.join(output_parts), 'returncode': 0, 'used_fallback': True}


def _python_grep(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of grep command."""
    case_insensitive = '-i' in args
    show_line_numbers = '-n' in args
    recursive = '-r' in args or '-R' in args
    invert_match = '-v' in args

    # Remove flags from args
    pattern = None
    files = []
    for arg in args:
        if arg.startswith('-'):
            continue
        if pattern is None:
            pattern = arg
        else:
            files.append(arg)

    if pattern is None:
        return {'output': 'grep: missing pattern', 'returncode': 1, 'used_fallback': True}

    if not files:
        files = ['.']

    # Compile regex
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return {'output': f'grep: invalid pattern: {str(e)}', 'returncode': 1, 'used_fallback': True}

    matches = []

    def search_file(filepath: Path, prefix: str = ''):
        nonlocal matches
        try:
            lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()
            for i, line in enumerate(lines, 1):
                match = regex.search(line)
                if (match and not invert_match) or (not match and invert_match):
                    if show_line_numbers:
                        matches.append(f'{prefix}{filepath}:{i}:{line}')
                    elif prefix or len(files) > 1:
                        matches.append(f'{prefix}{filepath}:{line}')
                    else:
                        matches.append(line)
        except Exception:
            pass

    for file_arg in files:
        path = cwd / file_arg
        if path.is_file():
            search_file(path)
        elif path.is_dir() and recursive:
            for item in path.rglob('*'):
                if item.is_file():
                    search_file(item, '')
        elif path.is_dir():
            return {'output': f'grep: {file_arg}: Is a directory', 'returncode': 1, 'used_fallback': True}
        else:
            return {'output': f'grep: {file_arg}: No such file or directory', 'returncode': 1, 'used_fallback': True}

    returncode = 0 if matches else 1
    return {'output': '\n'.join(matches), 'returncode': returncode, 'used_fallback': True}


def _python_find(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of find command."""
    search_path = cwd
    name_pattern = None
    type_filter = None

    i = 0
    while i < len(args):
        if args[i] == '-name' and i + 1 < len(args):
            name_pattern = args[i + 1]
            i += 2
        elif args[i] == '-type' and i + 1 < len(args):
            type_filter = args[i + 1]
            i += 2
        elif not args[i].startswith('-'):
            search_path = cwd / args[i]
            i += 1
        else:
            i += 1

    if not search_path.exists():
        return {'output': f'find: {search_path}: No such file or directory', 'returncode': 1, 'used_fallback': True}

    results = []

    def matches_pattern(name: str) -> bool:
        if name_pattern is None:
            return True
        # Convert glob pattern to regex
        regex_pattern = name_pattern.replace('.', r'\.').replace('*', '.*').replace('?', '.')
        return re.match(f'^{regex_pattern}$', name) is not None

    for item in search_path.rglob('*'):
        if type_filter == 'f' and not item.is_file():
            continue
        if type_filter == 'd' and not item.is_dir():
            continue
        if matches_pattern(item.name):
            results.append(str(item.relative_to(cwd)))

    return {'output': '\n'.join(sorted(results)), 'returncode': 0, 'used_fallback': True}


def _python_wc(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of wc command."""
    count_lines = '-l' in args
    count_words = '-w' in args
    count_chars = '-c' in args or '-m' in args

    # Default: count all
    if not any([count_lines, count_words, count_chars]):
        count_lines = count_words = count_chars = True

    files = [arg for arg in args if not arg.startswith('-')]

    if not files:
        return {'output': 'wc: missing file operand', 'returncode': 1, 'used_fallback': True}

    results = []
    total_lines = total_words = total_chars = 0

    for file_arg in files:
        filepath = cwd / file_arg
        if not filepath.exists():
            return {'output': f'wc: {file_arg}: No such file or directory', 'returncode': 1, 'used_fallback': True}

        content = filepath.read_text(encoding='utf-8', errors='replace')
        lines = len(content.splitlines())
        words = len(content.split())
        chars = len(content)

        parts = []
        if count_lines:
            parts.append(f'{lines:>8}')
            total_lines += lines
        if count_words:
            parts.append(f'{words:>8}')
            total_words += words
        if count_chars:
            parts.append(f'{chars:>8}')
            total_chars += chars
        parts.append(file_arg)
        results.append(' '.join(parts))

    if len(files) > 1:
        parts = []
        if count_lines:
            parts.append(f'{total_lines:>8}')
        if count_words:
            parts.append(f'{total_words:>8}')
        if count_chars:
            parts.append(f'{total_chars:>8}')
        parts.append('total')
        results.append(' '.join(parts))

    return {'output': '\n'.join(results), 'returncode': 0, 'used_fallback': True}


def _python_which(args: List[str]) -> Dict[str, Any]:
    """Python implementation of which command."""
    if not args:
        return {'output': 'which: missing argument', 'returncode': 1, 'used_fallback': True}

    results = []
    for cmd in args:
        if cmd.startswith('-'):
            continue
        path = shutil.which(cmd)
        if path:
            results.append(path)
        else:
            results.append(f'{cmd} not found')

    return {'output': '\n'.join(results), 'returncode': 0 if results else 1, 'used_fallback': True}


def _python_touch(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of touch command."""
    files = [arg for arg in args if not arg.startswith('-')]

    if not files:
        return {'output': 'touch: missing file operand', 'returncode': 1, 'used_fallback': True}

    for file_arg in files:
        filepath = cwd / file_arg
        filepath.touch()

    return {'output': '', 'returncode': 0, 'used_fallback': True}


def _python_mkdir_p(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of mkdir -p command."""
    dirs = [arg for arg in args if not arg.startswith('-')]

    if not dirs:
        return {'output': 'mkdir: missing operand', 'returncode': 1, 'used_fallback': True}

    for dir_arg in dirs:
        dirpath = cwd / dir_arg
        dirpath.mkdir(parents=True, exist_ok=True)

    return {'output': '', 'returncode': 0, 'used_fallback': True}


def _python_rm(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of rm command."""
    recursive = '-r' in args or '-rf' in args or '-R' in args
    force = '-f' in args or '-rf' in args

    files = [arg for arg in args if not arg.startswith('-')]

    if not files:
        return {'output': 'rm: missing operand', 'returncode': 1, 'used_fallback': True}

    for file_arg in files:
        filepath = cwd / file_arg
        if not filepath.exists():
            if not force:
                return {'output': f'rm: {file_arg}: No such file or directory', 'returncode': 1, 'used_fallback': True}
            continue

        if filepath.is_dir():
            if not recursive:
                return {'output': f'rm: {file_arg}: is a directory', 'returncode': 1, 'used_fallback': True}
            import shutil as sh
            sh.rmtree(filepath)
        else:
            filepath.unlink()

    return {'output': '', 'returncode': 0, 'used_fallback': True}


def _python_cp(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of cp command."""
    recursive = '-r' in args or '-R' in args

    files = [arg for arg in args if not arg.startswith('-')]

    if len(files) < 2:
        return {'output': 'cp: missing destination operand', 'returncode': 1, 'used_fallback': True}

    *sources, dest = files
    dest_path = cwd / dest

    import shutil as sh

    for src_arg in sources:
        src_path = cwd / src_arg
        if not src_path.exists():
            return {'output': f'cp: {src_arg}: No such file or directory', 'returncode': 1, 'used_fallback': True}

        if src_path.is_dir():
            if not recursive:
                return {'output': f'cp: -r not specified; omitting directory {src_arg}', 'returncode': 1, 'used_fallback': True}
            if dest_path.exists() and dest_path.is_dir():
                sh.copytree(src_path, dest_path / src_path.name)
            else:
                sh.copytree(src_path, dest_path)
        else:
            if dest_path.is_dir():
                sh.copy2(src_path, dest_path / src_path.name)
            else:
                sh.copy2(src_path, dest_path)

    return {'output': '', 'returncode': 0, 'used_fallback': True}


def _python_mv(args: List[str], cwd: Path) -> Dict[str, Any]:
    """Python implementation of mv command."""
    files = [arg for arg in args if not arg.startswith('-')]

    if len(files) < 2:
        return {'output': 'mv: missing destination operand', 'returncode': 1, 'used_fallback': True}

    *sources, dest = files
    dest_path = cwd / dest

    import shutil as sh

    for src_arg in sources:
        src_path = cwd / src_arg
        if not src_path.exists():
            return {'output': f'mv: {src_arg}: No such file or directory', 'returncode': 1, 'used_fallback': True}

        if dest_path.is_dir():
            sh.move(str(src_path), str(dest_path / src_path.name))
        else:
            sh.move(str(src_path), str(dest_path))

    return {'output': '', 'returncode': 0, 'used_fallback': True}


def smart_execute_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute a command with automatic platform translation and Python fallback.

    This function attempts to:
    1. Translate Unix commands to Windows equivalents if on Windows
    2. Fall back to Python implementations if translation fails
    3. Execute the command natively as a last resort

    Args:
        command: Command to execute
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Dict with 'output', 'returncode', 'method' (native/translated/python_fallback)
    """
    working_dir = cwd or str(Path.cwd())

    # First, try Python fallback for common Unix commands on Windows
    if is_windows():
        fallback_result = get_python_fallback(command, working_dir)
        if fallback_result:
            return {
                'output': fallback_result['output'],
                'returncode': fallback_result['returncode'],
                'method': 'python_fallback'
            }

        # Try command translation
        translated_cmd, was_translated = translate_command_for_platform(command)
        if was_translated:
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
                return {
                    'output': result.stdout + result.stderr,
                    'returncode': result.returncode,
                    'method': 'translated'
                }
            except Exception as e:
                # If translation failed, try Python fallback again
                pass

    # Execute natively
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
        return {
            'output': result.stdout + result.stderr,
            'returncode': result.returncode,
            'method': 'native'
        }
    except subprocess.TimeoutExpired:
        return {
            'output': f'Command timed out after {timeout} seconds',
            'returncode': 124,
            'method': 'timeout'
        }
    except Exception as e:
        return {
            'output': f'Execution error: {str(e)}',
            'returncode': 1,
            'method': 'error'
        }


def validate_spring_initializr_url(url: str) -> Tuple[bool, str, str]:
    """
    Validate and fix Spring Initializr URLs to prevent 400 Bad Request errors.

    Args:
        url: The Spring Initializr URL to validate

    Returns:
        Tuple of (is_valid, fixed_url, error_message)
    """
    if 'start.spring.io' not in url:
        return True, url, ""

    # Extract base URL and parameters
    if '?' not in url:
        return True, url, ""

    base_url, query_string = url.split('?', 1)

    # Parse existing parameters
    params = {}
    for param in query_string.split('&'):
        if '=' in param:
            key, value = param.split('=', 1)
            # Handle multiple dependencies (e.g., dependencies=web,jpa,security)
            params[key] = value

    # Validate required parameters
    valid_params = {
        'type': ['maven-project', 'gradle-project', 'gradle-project-kotlin'],
        'language': ['java', 'kotlin', 'groovy'],
        'bootVersion': None,  # Any version string
        'baseDir': None,
        'groupId': None,
        'artifactId': None,
        'name': None,
        'description': None,
        'packageName': None,
        'packaging': ['jar', 'war'],
        'javaVersion': ['8', '11', '17', '21'],
        'dependencies': None,  # Comma-separated list
    }

    # Fix common parameter issues
    fixed_params = {}
    errors = []

    for key, value in params.items():
        # URL encode the value properly
        if key == 'dependencies':
            # Dependencies should be comma-separated, each properly encoded
            deps = value.split(',')
            # Remove invalid characters from dependency names
            clean_deps = []
            for dep in deps:
                # Spring Initializr uses lowercase hyphenated names
                clean_dep = dep.strip().lower()
                # Common corrections
                corrections = {
                    'jjwt': 'security',  # jjwt is not a Spring Initializr dependency
                    'jwt': 'security',   # Use spring-security instead
                    'spring-boot-starter-web': 'web',
                    'spring-boot-starter-data-jpa': 'data-jpa',
                    'spring-boot-starter-security': 'security',
                    'spring-boot-starter-validation': 'validation',
                }
                if clean_dep in corrections:
                    clean_dep = corrections[clean_dep]
                if clean_dep:
                    clean_deps.append(clean_dep)
            fixed_params[key] = ','.join(clean_deps)
        elif key in valid_params and valid_params[key] is not None:
            # Check if value is in allowed list
            if value not in valid_params[key]:
                errors.append(f"Invalid {key}: {value}. Must be one of {valid_params[key]}")
            else:
                fixed_params[key] = value
        else:
            # URL encode special characters
            fixed_params[key] = quote_plus(value, safe='')

    # Ensure required parameters have defaults
    defaults = {
        'type': 'maven-project',
        'language': 'java',
        'bootVersion': '3.2.0',
        'packaging': 'jar',
        'javaVersion': '17',
        'groupId': 'com.example',
        'artifactId': 'demo',
        'name': 'demo',
    }

    for key, default in defaults.items():
        if key not in fixed_params:
            fixed_params[key] = default

    # Rebuild URL with properly encoded parameters
    # Use urlencode for proper encoding
    fixed_query = '&'.join(f"{k}={v}" for k, v in fixed_params.items())
    fixed_url = f"{base_url}?{fixed_query}"

    if errors:
        return False, fixed_url, "; ".join(errors)

    return True, fixed_url, ""


def fix_spring_initializr_command(command: str) -> Tuple[str, bool, str]:
    """
    Fix curl/PowerShell commands that use Spring Initializr.

    Args:
        command: The shell command to fix

    Returns:
        Tuple of (fixed_command, was_fixed, message)
    """
    if 'start.spring.io' not in command:
        return command, False, ""

    # Extract URL from curl command
    curl_match = re.search(r'curl\s+[^"\']*["\']?(https?://start\.spring\.io[^"\'\s]+)["\']?', command)
    if curl_match:
        url = curl_match.group(1).strip("'\"")
        is_valid, fixed_url, error = validate_spring_initializr_url(url)

        if not is_valid or url != fixed_url:
            # Replace URL in command
            fixed_command = command.replace(url, f'"{fixed_url}"')
            message = f"Fixed Spring Initializr URL. {error}" if error else "Fixed Spring Initializr URL encoding"
            return fixed_command, True, message

    # Extract URL from PowerShell DownloadFile
    ps_match = re.search(r'DownloadFile\s*\(\s*["\']([^"\']+)["\']', command)
    if ps_match:
        url = ps_match.group(1)
        is_valid, fixed_url, error = validate_spring_initializr_url(url)

        if not is_valid or url != fixed_url:
            fixed_command = command.replace(url, fixed_url)
            message = f"Fixed Spring Initializr URL. {error}" if error else "Fixed Spring Initializr URL encoding"
            return fixed_command, True, message

    # Extract URL from Invoke-WebRequest
    iwr_match = re.search(r'-Uri\s+["\']?([^"\'\s]+start\.spring\.io[^"\'\s]+)["\']?', command)
    if iwr_match:
        url = iwr_match.group(1).strip("'\"")
        is_valid, fixed_url, error = validate_spring_initializr_url(url)

        if not is_valid or url != fixed_url:
            fixed_command = command.replace(url, f'"{fixed_url}"')
            message = f"Fixed Spring Initializr URL. {error}" if error else "Fixed Spring Initializr URL encoding"
            return fixed_command, True, message

    return command, False, ""


def get_spring_boot_fallback_files(
    group_id: str = "com.example",
    artifact_id: str = "demo",
    package_name: str = "com.example.demo",
    dependencies: List[str] = None
) -> Dict[str, str]:
    """
    Generate fallback Spring Boot project files when network download fails.

    Args:
        group_id: Maven group ID
        artifact_id: Maven artifact ID
        package_name: Java package name
        dependencies: List of dependencies (web, data-jpa, security, h2, validation)

    Returns:
        Dict mapping file paths to file contents
    """
    if dependencies is None:
        dependencies = ['web', 'data-jpa', 'h2', 'validation', 'security']

    # Convert package name to directory structure
    package_path = package_name.replace('.', '/')

    files = {}

    # pom.xml
    dep_xml = ""
    if 'web' in dependencies:
        dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
"""
    if 'data-jpa' in dependencies:
        dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
"""
    if 'h2' in dependencies:
        dep_xml += """        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
"""
    if 'validation' in dependencies:
        dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
"""
    if 'security' in dependencies:
        dep_xml += """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-api</artifactId>
            <version>0.11.5</version>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-impl</artifactId>
            <version>0.11.5</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-jackson</artifactId>
            <version>0.11.5</version>
            <scope>runtime</scope>
        </dependency>
"""

    files['pom.xml'] = f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>{artifact_id}</name>
    <description>Spring Boot Application</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
{dep_xml}        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
'''

    # Main application class
    class_name = ''.join(word.capitalize() for word in artifact_id.replace('-', ' ').split())
    files[f'src/main/java/{package_path}/{class_name}Application.java'] = f'''package {package_name};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class {class_name}Application {{

    public static void main(String[] args) {{
        SpringApplication.run({class_name}Application.class, args);
    }}
}}
'''

    # application.properties
    files['src/main/resources/application.properties'] = '''# Spring Boot Configuration
spring.application.name=demo
server.port=8080

# H2 Database Configuration
spring.datasource.url=jdbc:h2:mem:testdb
spring.datasource.driverClassName=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.h2.console.enabled=true
spring.h2.console.path=/h2-console

# JPA Configuration
spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
'''

    # Test class
    files[f'src/test/java/{package_path}/{class_name}ApplicationTests.java'] = f'''package {package_name};

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class {class_name}ApplicationTests {{

    @Test
    void contextLoads() {{
    }}
}}
'''

    # .gitignore
    files['.gitignore'] = '''HELP.md
target/
!.mvn/wrapper/maven-wrapper.jar
!**/src/main/**/target/
!**/src/test/**/target/

### STS ###
.apt_generated
.classpath
.factorypath
.project
.settings
.springBeans
.sts4-cache

### IntelliJ IDEA ###
.idea
*.iws
*.iml
*.ipr

### NetBeans ###
/nbproject/private/
/nbbuild/
/dist/
/nbdist/
/.nb-gradle/
build/
!**/src/main/**/build/
!**/src/test/**/build/

### VS Code ###
.vscode/
'''

    # Maven wrapper files (minimal)
    files['.mvn/wrapper/maven-wrapper.properties'] = '''distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.5/apache-maven-3.9.5-bin.zip
wrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.2.0/maven-wrapper-3.2.0.jar
'''

    return files
