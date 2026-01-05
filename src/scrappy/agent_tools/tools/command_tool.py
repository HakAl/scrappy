"""
Command execution tool for the code agent.

Provides shell command execution with security checks, platform fixes,
retry logic, and output parsing.
"""

import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .base import ToolBase, ToolParameter, ToolResult, ToolContext

if TYPE_CHECKING:
    from ..protocols import (
        CommandSecurityProtocol,
        CommandAdvisorProtocol,
        SubprocessRunnerProtocol,
        OutputParserProtocol,
    )
    from scrappy.protocols.io import CLIIOProtocol
else:
    # Runtime import for type annotation
    from ..protocols import SubprocessRunnerProtocol
from ..constants import (
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_MAX_COMMAND_OUTPUT,
    DEFAULT_LONG_RUNNING_COMMANDS,
    LONG_RUNNING_COMMAND_TIMEOUT,
)

# Import platform utilities
from scrappy.platform import (
    is_windows,
    normalize_command_paths,
    normalize_npm_command_for_windows,
    intercept_spring_initializr_download,
    fix_spring_initializr_command,
    validate_command_for_platform,
    get_python_fallback,
)

from ..components import (
    CommandSecurity,
    CommandAdvisor,
    SubprocessRunner,
    OutputParser,
)
from ..components.sandboxed_runner import SandboxedSubprocessRunner


def create_shell_executor(
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
    max_command_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
    dangerous_commands: Optional[list[str]] = None,
    runner: Optional["SubprocessRunnerProtocol"] = None,
) -> "ShellCommandExecutor":
    """
    Factory function for creating ShellCommandExecutor with default dependencies.

    Creates a fully-wired ShellCommandExecutor with appropriate components
    for the current platform.

    Args:
        command_timeout: Timeout for command execution in seconds
        max_command_output: Maximum output size to capture in bytes
        dangerous_commands: List of dangerous command patterns to block
        runner: Optional subprocess runner (default: SubprocessRunner)

    Returns:
        Fully configured ShellCommandExecutor instance
    """

    # Create security validator with custom patterns if provided (None = use defaults)
    security = CommandSecurity(dangerous_patterns=dangerous_commands)

    # Create other components
    advisor = CommandAdvisor()
    if runner is None:
        runner = SubprocessRunner()
    parser = OutputParser()

    # Wire everything together
    return ShellCommandExecutor(
        timeout=command_timeout,
        max_output=max_command_output,
        dangerous_patterns=dangerous_commands,
        security=security,
        advisor=advisor,
        runner=runner,
        parser=parser,
    )


class ShellCommandExecutor:
    """
    Core shell command execution engine with dependency injection.

    Coordinates command execution through injected components following
    the Single Responsibility Principle. Each concern is delegated to
    a focused protocol implementation.
    """

    def __init__(
        self,
        timeout: int = 30,
        max_output: int = 10000,
        dangerous_patterns: Optional[list[str]] = None,
        security: Optional["CommandSecurityProtocol"] = None,
        advisor: Optional["CommandAdvisorProtocol"] = None,
        runner: Optional["SubprocessRunnerProtocol"] = None,
        parser: Optional["OutputParserProtocol"] = None,
        io: Optional["CLIIOProtocol"] = None,
    ):
        """
        Initialize executor with configuration and optional dependencies.

        Args:
            timeout: Command execution timeout in seconds
            max_output: Maximum output size to capture in bytes
            dangerous_patterns: List of dangerous command patterns to block
            security: Command security validator (default: creates CommandSecurity)
            advisor: Command advisor (default: creates CommandAdvisor)
            runner: Subprocess runner (default: creates SubprocessRunner)
            parser: Output parser (default: creates OutputParser)
            io: Optional IO interface for progress output (default: None, suppresses output)
        """

        self.timeout = timeout
        self.max_output = max_output
        self._io = io

        # Inject dependencies with defaults
        self._security = security or CommandSecurity(
            dangerous_patterns=dangerous_patterns or []
        )
        self._advisor = advisor or CommandAdvisor()
        self._runner = runner or SubprocessRunner(io=io)
        self._parser = parser or OutputParser()

    def run(self, command: str, project_root: Path, dry_run: bool = False) -> str:
        """
        Execute a shell command using injected components.

        Coordinates the full execution pipeline:
        1. Security validation
        2. Platform sanitization
        3. Pre-execution advice
        4. Command execution
        5. Output parsing and enrichment

        Args:
            command: Shell command to execute
            project_root: Working directory for command
            dry_run: If True, don't actually execute

        Returns:
            Command output or error message
        """
        # 1. Security validation
        try:
            self._security.validate(command)
        except ValueError as e:
            return f"Error: {str(e)}"

        # 2. Platform-specific intercepts (still using platform_utils for now)
        if is_windows():
            intercept_info = intercept_spring_initializr_download(command, str(project_root))
            if intercept_info and intercept_info.get('should_intercept'):
                if self._io:
                    self._io.echo(f"   [Platform] {intercept_info['reason']}")
                    self._io.echo(f"   [Suggestion] {intercept_info['suggested_action']}")
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

        # 3. Platform sanitization (using platform_utils functions directly)
        command, _, _ = fix_spring_initializr_command(command)
        command, _, _ = normalize_npm_command_for_windows(command)
        command, _, _ = normalize_command_paths(command)

        # 4. Platform validation
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

        # 5. Pre-execution advice
        advice = self._advisor.analyze_command(command)
        if advice and self._io:
            self._io.echo(f"   [ADVICE] {advice}")

        # 6. Check for long-running commands and get effective timeout
        is_long_running = self._is_long_running_command(command)
        effective_timeout = self._get_effective_timeout(command)
        if is_long_running and self._io:
            self._io.echo("Long-running command detected")
            self._io.echo(f"   Timeout: {effective_timeout}s | Streaming output enabled")

        # 7. Execute with retry logic using effective timeout
        try:
            show_progress = is_long_running
            output = self._run_command_with_retry(command, effective_timeout, show_progress=show_progress, cwd=project_root)

            # 8. Parse and enrich output
            parsed_output = self._parser.parse(output, max_length=self.max_output)
            enriched_output = self._advisor.enrich_output(parsed_output, command)

            return enriched_output

        except TimeoutError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error running command: {str(e)}"


    def _is_long_running_command(self, command: str) -> bool:
        """
        Check if command is expected to be long-running.

        Uses the centralized DEFAULT_LONG_RUNNING_COMMANDS list from constants
        to determine if a command should have an extended timeout.

        Args:
            command: Command to check

        Returns:
            True if long-running
        """
        cmd_lower = command.lower()

        for pattern in DEFAULT_LONG_RUNNING_COMMANDS:
            if pattern.lower() in cmd_lower:
                return True

        return False

    def _get_effective_timeout(self, command: str) -> int:
        """
        Get the effective timeout for a command.

        Long-running commands (npm install, cargo build, etc.) get an extended
        timeout (LONG_RUNNING_COMMAND_TIMEOUT), while regular commands use the
        default timeout (DEFAULT_COMMAND_TIMEOUT).

        Args:
            command: Command to check

        Returns:
            Timeout in seconds
        """
        if self._is_long_running_command(command):
            return LONG_RUNNING_COMMAND_TIMEOUT
        return self.timeout

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
        Delegates execution to injected SubprocessRunner.

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
                if self._io:
                    self._io.echo(f"   Retry attempt {attempt + 1}/{max_retries} after {wait_time}s delay...")
                time.sleep(wait_time)
                retry_count = attempt

            # Use injected runner for execution
            try:
                result = self._runner.execute(
                    command=command,
                    cwd=str(cwd) if cwd else str(Path.cwd()),
                    timeout=timeout,
                    stream_output=show_progress
                )
                output = result.stdout
            except TimeoutError as e:
                return f"Error: {str(e)}"
            except Exception as e:
                return f"Error running command: {str(e)}"

            # Check for recoverable errors
            is_recoverable_error = False
            output_lower = output.lower()

            for pattern in recoverable_patterns:
                if pattern.lower() in output_lower and 'error' in output_lower:
                    is_recoverable_error = True
                    last_error = output
                    if self._io:
                        self._io.echo(f"   Recoverable error detected: {pattern}")
                    break

            if not is_recoverable_error:
                # Success or non-recoverable error
                if retry_count > 0:
                    output = f"[Succeeded after {retry_count} retries]\n{output}"
                return output

        # All retries exhausted
        return f"Error: Command failed after {max_retries} attempts.\nLast error:\n{last_error}"

    def _categorize_command_approach(self, command: str) -> str:
        """
        Backward compatibility: Categorize command approach for retry pattern detection.

        Args:
            command: Shell command to categorize

        Returns:
            Category string (e.g., "spring_initializr_download", "npm_create_project")
        """
        cmd_lower = command.lower()

        # Spring Initializr downloads
        if 'start.spring.io' in cmd_lower:
            return "spring_initializr_download"

        # PowerShell downloads
        if 'invoke-webrequest' in cmd_lower or 'downloadfile' in cmd_lower:
            return "powershell_download"

        # curl/wget downloads
        if ('curl' in cmd_lower or 'wget' in cmd_lower) and ('http://' in cmd_lower or 'https://' in cmd_lower):
            return "curl_download"

        # npm create/npx create
        if ('npm create' in cmd_lower or 'npx create' in cmd_lower or 'npx -y create' in cmd_lower):
            return "npm_create_project"

        # npm init
        if 'npm init' in cmd_lower:
            return "npm_init"

        # mkdir with unix-style paths (forward slashes)
        if 'mkdir' in cmd_lower and '/' in command:
            return "mkdir_unix_style"

        # mkdir (general)
        if 'mkdir' in cmd_lower:
            return "mkdir"

        # npm install
        if 'npm install' in cmd_lower or 'npm i ' in cmd_lower or cmd_lower.endswith('npm i'):
            return "npm_install"

        # Unix commands
        unix_commands = ['grep', 'cat', 'find', 'ls', 'head', 'tail', 'sed', 'awk']
        for unix_cmd in unix_commands:
            if cmd_lower.startswith(unix_cmd + ' ') or cmd_lower == unix_cmd:
                return "unix_command"

        # Default: shell command
        return "shell_command"

    def _check_retry_pattern(self, command: str, failed_commands: list) -> str:
        """
        Backward compatibility: Check if command approach has failed before.

        Args:
            command: Command about to be executed
            failed_commands: List of previous failed commands with approach/error info

        Returns:
            Warning message if retry pattern detected, empty string otherwise
        """
        if not failed_commands:
            return ""

        current_approach = self._categorize_command_approach(command)

        # Count how many times this approach has failed
        failure_count = 0
        last_error = ""
        for failed in failed_commands:
            if failed.get('approach') == current_approach:
                failure_count += 1
                last_error = failed.get('error', '')

        # Check for scaffolding approach failures (cross-approach warning)
        scaffolding_approaches = {
            'spring_initializr_download', 'npm_create_project', 'npm_init',
            'curl_download', 'powershell_download'
        }
        is_current_scaffolding = current_approach in scaffolding_approaches
        has_scaffolding_failed = any(
            failed.get('approach') in scaffolding_approaches
            for failed in failed_commands
        )

        if failure_count == 0:
            # No exact match, but check for scaffolding cross-failure
            if is_current_scaffolding and has_scaffolding_failed:
                return (
                    "\n[WARNING] A scaffolding approach has already failed. "
                    "Consider using write_file to create the project structure directly.\n"
                )
            return ""

        # Specific warnings for known problematic approaches
        warning_msg = f"\n[CRITICAL WARNING] The approach '{current_approach}' has already failed {failure_count} time(s).\n"
        # Truncate error message if 200 chars or longer
        if len(last_error) >= 200:
            warning_msg += f"Last error: {last_error[:200]}...\n\n"
        else:
            warning_msg += f"Last error: {last_error}\n\n"

        # Spring Initializr specific advice
        if 'spring_initializr' in current_approach:
            warning_msg += (
                "RECOMMENDED: Stop trying Spring Initializr downloads.\n"
                "Instead, use write_file to create the Spring Boot project structure directly:\n"
                "1. Create pom.xml with required dependencies\n"
                "2. Create src/main/java/com/example/Application.java\n"
                "3. Create src/main/resources/application.properties\n"
            )

        # mkdir unix-style specific advice
        elif 'mkdir_unix_style' in current_approach:
            warning_msg += (
                "RECOMMENDED: Use backslashes (\\) instead of forward slashes (/) for Windows paths,\n"
                "or use PowerShell's New-Item cmdlet.\n"
            )

        # General scaffolding advice
        elif any(term in current_approach for term in ['npm_create', 'npm_init']):
            warning_msg += (
                "WARNING: Scaffolding commands often fail in non-interactive environments.\n"
                "Consider using write_file to create project structure manually.\n"
            )

        return warning_msg

    def _parse_command_output(self, output: str) -> str:
        """
        Backward compatibility: Parse command output.

        Delegates to the injected OutputParser component.

        Args:
            output: Raw command output

        Returns:
            Parsed and formatted output
        """
        return self._parser.parse(output, max_length=self.max_output)

    def _run_command_streaming(
        self,
        command: str,
        timeout: int,
        show_progress: bool = True
    ) -> str:
        """
        Backward compatibility: Run command with streaming output.

        This method is kept for backward compatibility with tests.
        Delegates to the injected SubprocessRunner.

        Args:
            command: Shell command to execute
            timeout: Maximum time in seconds
            show_progress: Show detailed progress

        Returns:
            Command output
        """
        try:
            result = self._runner.execute(
                command=command,
                cwd=str(Path.cwd()),
                timeout=timeout,
                stream_output=show_progress
            )
            return result.stdout if result.stdout else "(no output)"
        except TimeoutError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error running command: {str(e)}"


class CommandTool(ToolBase):
    """
    Tool wrapper for shell command execution.

    Provides the Tool interface for command execution with all
    security, platform, and convenience features. Supports Docker
    sandbox for isolated execution.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        max_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
        dangerous_patterns: Optional[list[str]] = None,
        executor: Optional[ShellCommandExecutor] = None,
        use_sandbox: bool = True,
    ):
        """
        Initialize CommandTool with configuration.

        Args:
            timeout: Command execution timeout in seconds
            max_output: Maximum output size to capture in bytes
            dangerous_patterns: List of dangerous command patterns to block
            executor: Injectable shell command executor (default: creates new ShellCommandExecutor)
            use_sandbox: Use Docker sandbox when available (default: True)
        """
        self._timeout = timeout
        self._max_output = max_output
        self._dangerous_patterns = dangerous_patterns  # Keep None to let CommandSecurity use defaults
        self._use_sandbox = use_sandbox
        self._executor = executor  # May be None, created lazily per project
        self._sandboxed_runners: dict[str, SandboxedSubprocessRunner] = {}  # Cache per project

    def _get_executor_for_project(self, project_dir: str) -> tuple[ShellCommandExecutor, str]:
        """Get or create executor for a project directory.

        Args:
            project_dir: Project directory path

        Returns:
            Tuple of (executor, executor_type) where executor_type is 'docker' or 'host'
        """
        if self._executor is not None:
            # User-provided executor, assume host
            return self._executor, "host"

        if not self._use_sandbox:
            # Sandbox disabled, use default host executor
            return create_shell_executor(
                command_timeout=self._timeout,
                max_command_output=self._max_output,
                dangerous_commands=self._dangerous_patterns,
            ), "host"

        # Get or create sandboxed runner for this project
        if project_dir not in self._sandboxed_runners:
            self._sandboxed_runners[project_dir] = SandboxedSubprocessRunner(
                project_dir=project_dir,
                prefer_docker=True,
                network_enabled=False,
            )

        runner = self._sandboxed_runners[project_dir]
        executor = create_shell_executor(
            command_timeout=self._timeout,
            max_command_output=self._max_output,
            dangerous_commands=self._dangerous_patterns,
            runner=runner,
        )
        return executor, runner.executor_type

    def cleanup(self) -> None:
        """Clean up all sandboxed runners (stops Docker containers)."""
        for runner in self._sandboxed_runners.values():
            try:
                runner.cleanup()
            except Exception:
                pass  # Best effort cleanup
        self._sandboxed_runners.clear()

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

        All validation, platform fixes, and execution logic is handled
        by the injected ShellCommandExecutor and its components. Uses
        Docker sandbox when available for isolated execution.

        Args:
            context: ToolContext with project root and settings
            **kwargs: Must include 'command' parameter

        Returns:
            ToolResult with command output
        """
        command = kwargs.get("command", "")

        if not command:
            return ToolResult(False, "", "No command specified")

        try:
            # Get executor for this project (may use Docker sandbox)
            executor, executor_type = self._get_executor_for_project(str(context.project_root))

            # Execute command - all security checks, platform fixes, and
            # validation are handled by the executor and its components
            output = executor.run(command, context.project_root, dry_run=context.dry_run)

            # Check if output indicates an error
            if output.startswith("Error"):
                return ToolResult(False, "", output, metadata={"executor_type": executor_type})

            # Check for dry run indicator
            if output.startswith("[DRY RUN]"):
                return ToolResult(True, output, metadata={"dry_run": True, "command": command, "executor_type": executor_type})

            return ToolResult(
                True,
                output,
                metadata={"command": command, "executor_type": executor_type}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error executing command: {str(e)}")
