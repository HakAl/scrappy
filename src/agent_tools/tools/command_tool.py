"""
Command execution tool for the code agent.

Provides shell command execution with security checks, platform fixes,
retry logic, and output parsing.
"""

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .base import Tool, ToolParameter, ToolResult, ToolContext

if TYPE_CHECKING:
    from ...agent_config import AgentConfig

# Import platform utilities
try:
    from ...platform_utils import (
        is_windows,
        normalize_command_paths,
        normalize_npm_command_for_windows,
        intercept_spring_initializr_download,
        fix_spring_initializr_command,
        validate_command_for_platform,
        get_python_fallback,
    )
    HAS_PLATFORM_UTILS = True
except ImportError:
    HAS_PLATFORM_UTILS = False

    def is_windows():
        return os.name == 'nt'

    def normalize_command_paths(cmd):
        return cmd, False, ""

    def normalize_npm_command_for_windows(cmd):
        return cmd, False, ""

    def intercept_spring_initializr_download(cmd, root):
        return None

    def fix_spring_initializr_command(cmd):
        return cmd, False, ""

    def validate_command_for_platform(cmd):
        return True, ""

    def get_python_fallback(cmd, root):
        return None


def safe_print(msg: str) -> None:
    """Print message safely, handling encoding errors."""
    try:
        print(msg)
    except (UnicodeEncodeError, UnicodeDecodeError):
        print(msg.encode('utf-8', errors='replace').decode('utf-8'))


class ShellCommandExecutor:
    """
    Core shell command execution engine.

    Handles:
    - Security validation (dangerous command blocking)
    - Platform-specific command normalization
    - Interactive command detection
    - Streaming output capture
    - Automatic retry with exponential backoff
    - Output parsing (JSON/YAML detection)
    - Command categorization for retry pattern detection
    """

    def __init__(self, config: "AgentConfig"):
        """
        Initialize executor with configuration.

        Args:
            config: AgentConfig with command settings
        """
        self.config = config
        self.timeout = getattr(config, 'command_timeout', 120)
        self.max_output = getattr(config, 'max_command_output', 50000)

    def run(self, command: str, project_root: Path, dry_run: bool = False) -> str:
        """
        Execute a shell command with all safety and convenience features.

        Args:
            command: Shell command to execute
            project_root: Working directory for command
            dry_run: If True, don't actually execute

        Returns:
            Command output or error message
        """
        # Security: Block dangerous commands
        error = self._check_dangerous_command(command)
        if error:
            return error

        # Platform-specific interceptions and fixes
        intercept_result = self._check_platform_intercepts(command, project_root)
        if intercept_result:
            return intercept_result

        command = self._apply_platform_fixes(command)

        # Validate command for platform
        is_valid, warning = validate_command_for_platform(command)
        if not is_valid:
            fallback_result = get_python_fallback(command, str(project_root))
            if fallback_result:
                output = fallback_result['output']
                if fallback_result['returncode'] != 0:
                    return f"[Python fallback] {output}"
                return f"[Python fallback] {output}" if output else "[Python fallback] Command completed successfully"
            return f"Error: {warning}. Use platform-appropriate tools instead."

        if dry_run:
            return f"[DRY RUN] Would run: {command}"

        # Check for interactive commands
        if self._is_interactive_command(command):
            suggestion = self._get_interactive_suggestion(command)
            safe_print(f"Warning: Command may require interactive input")
            if suggestion:
                safe_print(f"   Tip: {suggestion}")

        # Check for long-running commands
        is_long_running = self._is_long_running_command(command)
        if is_long_running:
            safe_print(f"Long-running command detected")
            safe_print(f"   Timeout: {self.timeout}s | Streaming output enabled")

        try:
            # Use streaming with retry for all commands
            show_progress = is_long_running
            return self._run_command_with_retry(command, self.timeout, show_progress=show_progress, cwd=project_root)
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out ({self.timeout}s limit)"
        except Exception as e:
            return f"Error running command: {str(e)}"

    def _check_dangerous_command(self, command: str) -> Optional[str]:
        """
        Check if command matches dangerous patterns.

        Args:
            command: Command to check

        Returns:
            Error message if dangerous, None if safe
        """
        dangerous_patterns = getattr(self.config, 'dangerous_commands', [
            r'rm\s+-rf\s+/',
            r'rm\s+-rf\s+\*',
            r'format\s+[A-Za-z]:',
            r'mkfs\.',
            r'dd\s+if=',
            r':\(\)\s*\{.*\}',  # Fork bomb
            r'sudo\s+rm',
        ])

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Error: Command matches dangerous pattern '{pattern}'"

        return None

    def _check_platform_intercepts(self, command: str, project_root: Path) -> Optional[str]:
        """
        Check for platform-specific command interceptions.

        Args:
            command: Command to check
            project_root: Project root path

        Returns:
            Error/guidance message if intercepted, None otherwise
        """
        if is_windows():
            intercept_info = intercept_spring_initializr_download(command, str(project_root))
            if intercept_info and intercept_info.get('should_intercept'):
                safe_print(f"   [Platform] {intercept_info['reason']}")
                safe_print(f"   [Suggestion] {intercept_info['suggested_action']}")
                params = intercept_info.get('template_params', {})
                return (
                    f"Error: Spring Initializr downloads are unreliable on Windows. "
                    f"Instead, use write_file to create the project structure directly. "
                    f"Detected parameters: groupId={params.get('group_id', 'unknown')}, "
                    f"artifactId={params.get('artifact_id', 'unknown')}, "
                    f"dependencies={','.join(params.get('dependencies', []))}. "
                    f"Create these files manually: 1) pom.xml, 2) Application.java, "
                    f"3) application.properties"
                )
        return None

    def _apply_platform_fixes(self, command: str) -> str:
        """
        Apply platform-specific command fixes.

        Args:
            command: Original command

        Returns:
            Fixed command
        """
        # Fix Spring Initializr URLs
        fixed_command, was_fixed, fix_message = fix_spring_initializr_command(command)
        if was_fixed:
            safe_print(f"   [Auto-fix] {fix_message}")
            command = fixed_command

        # Normalize npm commands for Windows
        npm_normalized, npm_was_normalized, npm_message = normalize_npm_command_for_windows(command)
        if npm_was_normalized:
            safe_print(f"   [Auto-fix] {npm_message}")
            command = npm_normalized

        # Normalize paths for Windows
        normalized_command, was_normalized, norm_message = normalize_command_paths(command)
        if was_normalized:
            safe_print(f"   [Auto-fix] {norm_message}")
            command = normalized_command

        return command

    def _normalize_command_paths(self, command: str) -> str:
        """
        Normalize paths in command for current platform.

        Args:
            command: Command with paths

        Returns:
            Command with normalized paths
        """
        normalized, _, _ = normalize_command_paths(command)
        return normalized

    def _normalize_npm_command(self, command: str) -> str:
        """
        Normalize npm command for current platform.

        Args:
            command: npm command

        Returns:
            Normalized npm command
        """
        normalized, _, _ = normalize_npm_command_for_windows(command)
        return normalized

    def _is_interactive_command(self, command: str) -> bool:
        """
        Check if command may require interactive input.

        Args:
            command: Command to check

        Returns:
            True if command is interactive
        """
        cmd_lower = command.lower()
        interactive_patterns = getattr(self.config, 'interactive_commands', [
            'npm init',
            'npx',
            'yarn create',
        ])

        for pattern in interactive_patterns:
            if pattern in cmd_lower:
                return True

        return False

    def _get_interactive_suggestion(self, command: str) -> str:
        """
        Get suggestion for handling interactive command.

        Args:
            command: Interactive command

        Returns:
            Suggestion string
        """
        cmd_lower = command.lower()

        if 'npx' in cmd_lower:
            return "Add '-y' flag to skip prompts: npx -y create-react-app ..."

        if 'npm init' in cmd_lower:
            return "Use 'npm init -y' to skip prompts"

        if 'yarn create' in cmd_lower:
            return "Yarn create may prompt for choices"

        return ""

    def _is_long_running_command(self, command: str) -> bool:
        """
        Check if command is expected to be long-running.

        Args:
            command: Command to check

        Returns:
            True if long-running
        """
        cmd_lower = command.lower()
        long_running_patterns = getattr(self.config, 'long_running_commands', [
            'npm install',
            'docker build',
            'pip install',
            'yarn install',
            'cargo build',
            'mvn package',
            'gradle build',
        ])

        for pattern in long_running_patterns:
            if pattern in cmd_lower:
                return True

        return False

    def _run_command_with_retry(
        self,
        command: str,
        timeout: int,
        show_progress: bool = True,
        max_retries: int = 3,
        cwd: Optional[Path] = None
    ) -> str:
        """
        Run command with automatic retry on recoverable errors.

        Uses exponential backoff: 2s, 4s, 8s between retries.

        Args:
            command: Shell command to execute
            timeout: Maximum time in seconds
            show_progress: Show detailed progress
            max_retries: Maximum retry attempts
            cwd: Working directory for command

        Returns:
            Command output with optional retry info
        """
        last_error = None
        retry_count = 0

        recoverable_patterns = [
            'connection reset',
            'connection refused',
            'network is unreachable',
            'temporary failure',
            'timed out',
            'ECONNRESET',
            'ETIMEDOUT',
            'ENOTFOUND',
            'socket hang up',
            'certificate has expired',
            'unable to get local issuer certificate',
        ]

        for attempt in range(max_retries):
            if attempt > 0:
                wait_time = 2 ** attempt
                safe_print(f"   Retry attempt {attempt + 1}/{max_retries} after {wait_time}s delay...")
                time.sleep(wait_time)
                retry_count = attempt

            output = self._run_command_streaming(command, timeout, show_progress, cwd=cwd)

            # Check for recoverable errors
            is_recoverable_error = False
            output_lower = output.lower()

            for pattern in recoverable_patterns:
                if pattern.lower() in output_lower and 'error' in output_lower:
                    is_recoverable_error = True
                    last_error = output
                    safe_print(f"   Recoverable error detected: {pattern}")
                    break

            if not is_recoverable_error:
                # Success or non-recoverable error
                parsed_output = self._parse_command_output(output)
                if retry_count > 0:
                    parsed_output = f"[Succeeded after {retry_count} retries]\n{parsed_output}"
                return parsed_output

        # All retries exhausted
        return f"Error: Command failed after {max_retries} attempts.\nLast error:\n{last_error}"

    def _run_command_streaming(self, command: str, timeout: int, show_progress: bool = True, cwd: Optional[Path] = None) -> str:
        """
        Run command with streaming output capture.

        Args:
            command: Shell command
            timeout: Timeout in seconds
            show_progress: Show progress indicators
            cwd: Working directory for command (defaults to current directory)

        Returns:
            Captured output or error message
        """
        output_lines = []
        process = None
        working_dir = str(cwd) if cwd else str(Path.cwd())

        try:
            # Set environment for unbuffered output
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['NODE_ENV'] = 'development'
            env['CI'] = 'true'
            env['npm_config_yes'] = 'true'

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                encoding='utf-8',
                errors='replace',
            )

            start_time = time.time()
            last_output_time = start_time

            def read_output():
                nonlocal last_output_time
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            output_lines.append(line.rstrip())
                            last_output_time = time.time()
                            if show_progress and len(output_lines) % 10 == 0:
                                safe_print(f"   ... {len(output_lines)} lines processed")
                except Exception:
                    pass

            reader_thread = threading.Thread(target=read_output)
            reader_thread.daemon = True
            reader_thread.start()

            stall_warning_shown = False
            while process.poll() is None:
                elapsed = time.time() - start_time
                stall_time = time.time() - last_output_time

                if elapsed > timeout:
                    process.kill()
                    return f"Error: Command timed out after {timeout}s\nPartial output ({len(output_lines)} lines):\n" + "\n".join(output_lines[-50:])

                if stall_time > 30 and not stall_warning_shown and show_progress:
                    safe_print(f"   No output for 30s - command may be waiting for input")
                    safe_print(f"   Press Ctrl+C to interrupt if stuck")
                    stall_warning_shown = True

                time.sleep(0.5)

            reader_thread.join(timeout=5)

            output = "\n".join(output_lines)
            output = self._truncate_output(output)

            if show_progress:
                safe_print(f"   Command completed ({len(output_lines)} lines)")

            return output if output else "(no output)"

        except KeyboardInterrupt:
            if process:
                process.kill()
            return "Command interrupted by user (Ctrl+C)"
        except Exception as e:
            if process:
                process.kill()
            return f"Error running command: {str(e)}"

    def _truncate_output(self, output: str) -> str:
        """
        Truncate output if it exceeds max size.

        Args:
            output: Raw output

        Returns:
            Truncated output with indicator
        """
        if len(output) > self.max_output:
            return "... [truncated, showing last portion]\n" + output[-self.max_output:]
        return output

    def _parse_command_output(self, output: str) -> str:
        """
        Parse command output and auto-detect format.

        Adds metadata for JSON/YAML detection and provides
        helpful guidance for common errors.

        Args:
            output: Raw command output

        Returns:
            Annotated output
        """
        if not output or output == "(no output)":
            return output

        stripped = output.strip()

        # Detect Spring Initializr errors
        if 'start.spring.io' in output or 'spring' in output.lower():
            error_indicators = [
                '400 bad request', '404 not found', '500 internal server error',
                'connection refused', 'unable to resolve', 'network error'
            ]
            output_lower = output.lower()
            for error in error_indicators:
                if error in output_lower:
                    guidance = (
                        "\n\n[Spring Initializr Error Detected]\n"
                        "The Spring Initializr service returned an error. Common causes:\n"
                        "1. Invalid dependency names (use 'web' not 'spring-boot-starter-web')\n"
                        "2. Malformed URL parameters\n"
                        "3. Network connectivity issues\n\n"
                        "RECOMMENDED: Use write_file to create Spring Boot files directly:\n"
                        "- Create pom.xml with required dependencies\n"
                        "- Create main Application.java class\n"
                        "- Create application.properties\n"
                        "This is more reliable than downloading from Spring Initializr."
                    )
                    return output + guidance

        # Try JSON detection
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                parsed = json.loads(stripped)
                format_info = "[Auto-detected: JSON output]\n"
                if isinstance(parsed, dict):
                    format_info += f"[Structure: Object with {len(parsed)} keys]\n"
                elif isinstance(parsed, list):
                    format_info += f"[Structure: Array with {len(parsed)} items]\n"
                return format_info + output
            except json.JSONDecodeError:
                pass

        # Try YAML detection
        try:
            import yaml
            if ':' in stripped and not stripped.startswith('Error'):
                lines = stripped.split('\n')
                yaml_indicators = 0
                for line in lines[:10]:
                    if line.strip() and ':' in line:
                        if line.strip().endswith(':') or ': ' in line:
                            yaml_indicators += 1
                    if line.startswith('  ') or line.startswith('- '):
                        yaml_indicators += 1

                if yaml_indicators >= 3:
                    try:
                        parsed = yaml.safe_load(stripped)
                        if isinstance(parsed, (dict, list)):
                            format_info = "[Auto-detected: YAML output]\n"
                            if isinstance(parsed, dict):
                                format_info += f"[Structure: Object with {len(parsed)} keys]\n"
                            elif isinstance(parsed, list):
                                format_info += f"[Structure: Array with {len(parsed)} items]\n"
                            return format_info + output
                    except Exception:
                        pass
        except ImportError:
            pass

        return output

    def _categorize_command_approach(self, command: str) -> str:
        """
        Categorize command into approach type for retry tracking.

        This helps detect when the LLM retries the same failing approach.

        Args:
            command: Shell command

        Returns:
            Approach type string
        """
        command_lower = command.lower()

        # Network download approaches
        if 'start.spring.io' in command_lower:
            return 'spring_initializr_download'
        if 'curl' in command_lower or 'wget' in command_lower:
            return 'curl_download'
        if 'invoke-webrequest' in command_lower or 'downloadfile' in command_lower:
            return 'powershell_download'

        # Project scaffolding
        if 'npm create' in command_lower or 'npx create' in command_lower:
            return 'npm_create_project'
        if 'npm init' in command_lower:
            return 'npm_init'

        # Directory operations
        if command_lower.startswith('mkdir '):
            if '/' in command and '\\' not in command:
                return 'mkdir_unix_style'
            return 'mkdir'

        # Package management
        if 'npm install' in command_lower or 'npm i ' in command_lower:
            return 'npm_install'

        # General command categories
        if any(unix_cmd in command_lower.split()[0] for unix_cmd in ['grep', 'cat', 'sed', 'awk', 'find']):
            return 'unix_command'

        return 'shell_command'

    def _check_retry_pattern(self, command: str, failed_commands: list) -> str:
        """
        Check if command follows a pattern that has already failed.

        Args:
            command: Command about to be executed
            failed_commands: List of previously failed commands

        Returns:
            Warning message if retry pattern detected, empty string otherwise
        """
        if not failed_commands:
            return ""

        current_approach = self._categorize_command_approach(command)
        failed_approaches = [f['approach'] for f in failed_commands]

        if current_approach in failed_approaches:
            count = failed_approaches.count(current_approach)
            if count >= 1:
                same_approach_failures = [f for f in failed_commands if f['approach'] == current_approach]
                last_failure = same_approach_failures[-1]

                suggestions = {
                    'spring_initializr_download': "STOP using network downloads. Use write_file to create Spring Boot files directly: pom.xml, Application.java, etc.",
                    'curl_download': "STOP using curl. Use write_file tool to create files directly instead of downloading",
                    'powershell_download': "STOP using PowerShell downloads. Use write_file tool to create files directly",
                    'mkdir_unix_style': "Use backslashes (website\\\\frontend) or PowerShell New-Item command",
                    'npm_create_project': "STOP using npm create. Use write_file to create package.json and source files directly",
                    'unix_command': "Use platform tools (read_file, search_code, list_files) instead of Unix commands",
                }

                suggestion = suggestions.get(current_approach, "Try a completely different approach")

                return (
                    f"CRITICAL: '{current_approach}' approach already failed {count} time(s). "
                    f"Last error: {last_failure['error'][:100]}... "
                    f"YOU MUST USE A DIFFERENT STRATEGY. {suggestion}"
                )

        # Warn if trying scaffolding when others have failed
        scaffolding_approaches = [
            'spring_initializr_download', 'curl_download', 'powershell_download', 'npm_create_project'
        ]
        if current_approach in scaffolding_approaches:
            scaffolding_failures = [f for f in failed_commands if f['approach'] in scaffolding_approaches]
            if scaffolding_failures:
                return (
                    f"WARNING: Scaffolding/download approaches have failed {len(scaffolding_failures)} time(s). "
                    f"STRONGLY RECOMMEND using write_file to create project files directly instead of {current_approach}."
                )

        return ""


class CommandTool(Tool):
    """
    Tool wrapper for shell command execution.

    Provides the Tool interface for command execution with all
    security, platform, and convenience features.
    """

    def __init__(
        self,
        config: "AgentConfig",
        executor: Optional[ShellCommandExecutor] = None
    ):
        """
        Initialize CommandTool with configuration.

        Args:
            config: AgentConfig with command settings
            executor: Injectable shell command executor (default: creates new ShellCommandExecutor)
        """
        self._config = config
        self._executor = executor or self._create_default_executor()

    def _create_default_executor(self) -> ShellCommandExecutor:
        """Create default shell command executor."""
        return ShellCommandExecutor(self._config)

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "Execute a shell command with security checks, platform fixes, and automatic retry"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "command",
                str,
                "Shell command to execute",
                required=True
            )
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        """
        Execute shell command.

        Args:
            context: ToolContext with project root and settings
            **kwargs: Must include 'command' parameter

        Returns:
            ToolResult with command output
        """
        command = kwargs.get("command", "")

        if not command:
            return ToolResult(False, "", "No command specified")

        # Check for dangerous commands first
        danger_check = self._executor._check_dangerous_command(command)
        if danger_check:
            return ToolResult(False, "", danger_check)

        # Check for platform interceptions
        intercept = self._executor._check_platform_intercepts(command, context.project_root)
        if intercept:
            return ToolResult(False, "", intercept)

        # Dry run check
        if context.dry_run:
            return ToolResult(
                True,
                f"[DRY RUN] Would run: {command}",
                metadata={"dry_run": True, "command": command}
            )

        try:
            # Execute command
            output = self._executor.run(command, context.project_root, dry_run=False)

            # Check if output indicates an error
            if output.startswith("Error"):
                return ToolResult(False, "", output)

            return ToolResult(
                True,
                output,
                metadata={"command": command}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error executing command: {str(e)}")
