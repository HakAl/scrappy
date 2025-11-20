"""
Core Code Agent implementation.

The main CodeAgent class with tool use and safety features.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional, Union, Any

from ..agent_config import AgentConfig
from ..agent_tools.tools import ToolRegistry, ToolContext
from ..agent_tools.tools.command_tool import ShellCommandExecutor

# Import IO interfaces - avoid circular import by importing module directly
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..cli.io_interface import CLIIOProtocol


def safe_print(*args, **kwargs):
    """
    Print function that safely handles Unicode encoding errors on Windows.

    Replaces unencodable characters instead of crashing with 'charmap' codec error.
    """
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Fallback: encode with 'replace' error handling
        text = ' '.join(str(arg) for arg in args)
        # Replace problematic characters with '?'
        safe_text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        # Try to print the safe version
        try:
            print(safe_text, **kwargs)
        except Exception:
            # Last resort: strip all non-ASCII
            ascii_text = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(ascii_text, **kwargs)
    except Exception as e:
        # Catch-all for any other print errors
        try:
            print(f"[Output encoding error: {type(e).__name__}]", **kwargs)
        except Exception:
            pass  # Give up silently if we can't print at all
from ..orchestrator_adapter import (
    OrchestratorAdapter,
    AgentOrchestratorAdapter,
)
from ..agent_tools.registry_factory import create_default_registry

from .types import (
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState
)
from .audit import AuditLogger
from .response_parser import ResponseParser, JSONResponseParser, ParseResult, UnifiedResponseParser


class CodeAgent:
    """
    AI-powered code agent with tool use and safety features.

    Key features:
    - Human-in-the-loop confirmation for all file operations
    - Sandboxed to project directory
    - Audit logging of all actions
    - Hybrid model approach (Gemini for reasoning, Cerebras for speed)
    - Injectable tool system with registry
    """

    def __init__(
        self,
        orchestrator: Union[OrchestratorAdapter, object],
        project_path: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        tool_registry: Optional[ToolRegistry] = None,
        io: Optional[Any] = None,  # CLIIOProtocol - Any to avoid circular import
        file_system: Optional[Any] = None,  # FileSystemProtocol
        platform_utils: Optional[Any] = None,  # PlatformUtilsProtocol
        audit_logger: Optional[Any] = None,  # AuditLoggerProtocol
        response_parser: Optional[Any] = None,  # ResponseParserProtocol
        tool_context: Optional[Any] = None,  # ToolContextProtocol
        command_executor: Optional[Any] = None,  # ShellCommandExecutor
    ):
        """
        Initialize the code agent with dependency injection.

        Args:
            orchestrator: OrchestratorAdapter instance or AgentOrchestrator
                         (will be wrapped in adapter if not already)
            project_path: Root directory to sandbox operations (default: cwd)
            config: AgentConfig instance (uses defaults if not provided)
            tool_registry: ToolRegistry instance (creates default if not provided)
            io: IO interface for output (defaults to RichIO)
            file_system: FileSystemProtocol implementation (defaults to RealFileSystem)
            platform_utils: PlatformUtilsProtocol implementation (defaults to RealPlatformUtils)
            audit_logger: AuditLoggerProtocol implementation (defaults to AuditLogger)
            response_parser: ResponseParserProtocol implementation (defaults to UnifiedResponseParser)
            tool_context: ToolContextProtocol implementation (created if not provided)
            command_executor: ShellCommandExecutor instance (created if not provided)
        """
        # Initialize dependencies with defaults via factory methods
        # This allows testing with mock dependencies while providing
        # sensible defaults for production use

        # Store config for factory methods
        self._initial_config = config
        self._initial_orchestrator = orchestrator
        self._initial_project_path = project_path

        # IO interface
        self.io = io or self._create_default_io()

        # File system
        self._file_system = file_system or self._create_default_file_system()

        # Platform utilities
        self._platform_utils = platform_utils or self._create_default_platform_utils()

        # Wrap orchestrator in adapter if needed
        if isinstance(orchestrator, OrchestratorAdapter):
            self.adapter = orchestrator
        else:
            # Assume it's a full AgentOrchestrator, wrap it
            self.adapter = AgentOrchestratorAdapter(orchestrator)

        # Keep orch as alias for backward compatibility
        self.orch = self.adapter

        # Resolve project root using file system abstraction
        # Infrastructure file system returns str, convert to Path for compatibility
        if project_path:
            self.project_root = Path(self._file_system.resolve(project_path))
        else:
            self.project_root = Path(self._file_system.resolve("."))

        self.config = config or AgentConfig()
        self.dry_run = False

        # Audit logger
        self._audit_logger = audit_logger or self._create_default_audit_logger()

        # Response parser
        self._response_parser: ResponseParser = response_parser or self._create_default_response_parser()

        # Tool context
        self._show_progress("Preparing agent tools...")
        self.tool_context = tool_context or self._create_default_tool_context()

        # Tool registry
        self.tool_registry = tool_registry or self._create_default_tool_registry()

        # Build tools mapping for backward compatibility
        self.tools = {
            tool.name: lambda ctx=self.tool_context, t=tool, **kw: t(ctx, **kw)
            for tool in self.tool_registry.list_all()
        }

        # Add run_command tool (kept inline for security reasons)
        self.tools['run_command'] = self._tool_run_command

        # Build tool name mapping for dynamic _tool_* method resolution
        self._tool_name_map = {
            tool.name: tool.name for tool in self.tool_registry.list_all()
        }
        # Add common aliases for convenience
        self._tool_name_map.update({
            'list_directory': 'list_directory',
            'search_code': 'search_code',
            'read_file': 'read_file',
            'write_file': 'write_file',
            'git_log': 'git_log',
            'git_status': 'git_status',
            'git_diff': 'git_diff',
            'git_blame': 'git_blame',
        })

        # Command executor
        self._command_executor = command_executor or self._create_default_command_executor()

        # Use orchestrator's intelligent provider selection
        self._show_progress("Selecting AI providers...")
        available = self.adapter.list_providers()

        # Store orchestrator reference for dynamic provider selection
        self._orchestrator = orchestrator

        # Check if orchestrator supports smart provider selection
        self._use_dynamic_selection = hasattr(orchestrator, 'get_recommended_provider')

        if self._use_dynamic_selection:
            # Let orchestrator decide provider based on task type and rate limits
            # Get initial recommendation for display purposes
            if hasattr(orchestrator, 'get_recommended_provider'):
                self.planner = orchestrator.get_recommended_provider('planning')
                self.executor = orchestrator.get_recommended_provider('execution')
            else:
                self.planner = available[0] if available else None
                self.executor = self.planner
        else:
            # Fallback to legacy static selection if orchestrator doesn't support it
            # Check if adapter has a preferred provider override (from task routing)
            preferred_provider = None
            if hasattr(self.adapter, 'get_preferred_provider'):
                pref_provider, pref_model = self.adapter.get_preferred_provider()
                if pref_provider and pref_provider in available:
                    preferred_provider = pref_provider

            # Select planner based on preferences (prefer adapter override)
            self.planner = None
            if preferred_provider:
                self.planner = preferred_provider
            else:
                for pref in self.config.planner_preferences:
                    if pref in available:
                        self.planner = pref
                        break
            if self.planner is None:
                self.planner = available[0] if available else None

            # Select executor based on preferences (prefer adapter override)
            self.executor = None
            if preferred_provider:
                self.executor = preferred_provider
            else:
                for pref in self.config.executor_preferences:
                    if pref in available:
                        self.executor = pref
                        break
            if self.executor is None:
                self.executor = self.planner

    # Factory methods for default dependencies

    def _create_default_io(self):
        """Create default IO interface."""
        from ..cli.rich_output import RichIO
        return RichIO()

    def _create_default_file_system(self):
        """Create default file system."""
        from ..infrastructure.file_system import RealFileSystem
        return RealFileSystem()

    def _create_default_platform_utils(self):
        """Create default platform utilities."""
        from .platform_adapter import RealPlatformUtils
        return RealPlatformUtils()

    def _create_default_audit_logger(self):
        """Create default audit logger."""
        return AuditLogger(max_result_length=self.config.audit_log_result_truncation)

    def _create_default_response_parser(self):
        """Create default response parser."""
        return UnifiedResponseParser()

    def _create_default_tool_context(self):
        """Create default tool context."""
        return ToolContext(
            project_root=self.project_root,
            dry_run=self.dry_run,
            config=self.config,
            orchestrator=self._initial_orchestrator
        )

    def _create_default_tool_registry(self):
        """Create default tool registry."""
        return create_default_registry()

    def _create_default_command_executor(self):
        """Create default shell command executor."""
        return ShellCommandExecutor(self.config)

    def __getattr__(self, name: str):
        """Dynamic attribute resolution for _tool_* methods.

        Allows calling agent._tool_search_code(...) which routes to self.tools['search_code'](...)
        This bridges the gap between smart_query.py expectations and the tool registry pattern.
        """
        if name.startswith('_tool_'):
            tool_name = name[6:]  # Remove '_tool_' prefix

            # Check if this is a registered tool
            if hasattr(self, '_tool_name_map') and tool_name in self._tool_name_map:
                actual_tool_name = self._tool_name_map[tool_name]

                # Define parameter mappings for common tools (positional to keyword)
                param_maps = {
                    'search_code': ['pattern', 'file_pattern'],
                    'read_file': ['file_path', 'max_lines'],
                    'write_file': ['file_path', 'content'],
                    'list_directory': ['path', 'depth'],
                    'git_log': ['n'],
                    'git_diff': ['ref1', 'ref2'],
                    'git_blame': ['file_path'],
                    'git_show': ['ref'],
                }

                # Return a wrapper function that calls the tool
                def tool_wrapper(*args, **kwargs):
                    if hasattr(self, 'tools') and actual_tool_name in self.tools:
                        # Convert positional args to keyword args
                        if args and actual_tool_name in param_maps:
                            param_names = param_maps[actual_tool_name]
                            for i, arg in enumerate(args):
                                if i < len(param_names):
                                    kwargs[param_names[i]] = arg

                        try:
                            result = self.tools[actual_tool_name](**kwargs)
                            # Return the output string for backward compatibility
                            if hasattr(result, 'output'):
                                if result.success:
                                    return result.output
                                else:
                                    return f"Error: {result.error}" if result.error else "Error: Tool execution failed"
                            return str(result)
                        except Exception as e:
                            return f"Error: {str(e)}"
                    raise AttributeError(f"Tool '{actual_tool_name}' not found in tools registry")

                return tool_wrapper

        # Default behavior - raise AttributeError for unknown attributes
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @property
    def audit_log(self):
        """Get the audit log (backward compatibility)."""
        return self._audit_logger.get_log()

    def _log_action(self, action: str, params: dict, result: str, approved: bool):
        """Log an action to the audit trail."""
        self._audit_logger.log_action(action, params, result, approved)

    # ========== Rich Output Helper Methods ==========

    def _show_thinking(self, text: str) -> None:
        """Display thinking/reasoning output in a blue-bordered panel."""
        if not text or not text.strip():
            return
        if hasattr(self.io, 'panel'):
            self.io.panel(text, title="Thinking", border_style="blue")
        else:
            self.io.secho(f"[Thinking] {text}", fg="blue")

    def _show_tool_request(self, tool_name: str, params: dict) -> None:
        """Display tool request as a formatted table."""
        if hasattr(self.io, 'table'):
            headers = ["Property", "Value"]
            rows = [["Tool", tool_name]]
            for key, value in params.items():
                # Truncate long values for display
                str_value = str(value)
                if len(str_value) > 100:
                    str_value = str_value[:100] + "..."
                rows.append([key, str_value])
            self.io.table(headers, rows, title="Tool Request")
        else:
            self.io.secho(f"Tool: {tool_name}", fg="cyan", bold=True)
            self.io.echo(f"Parameters: {json.dumps(params, indent=2)}")

    def _show_command(self, command: str) -> None:
        """Display command in syntax-highlighted block."""
        if hasattr(self.io, 'syntax'):
            self.io.syntax(command, language="shell")
        else:
            self.io.secho(f"$ {command}", fg="yellow")

    def _show_error(self, message: str) -> None:
        """Display error in red-bordered panel."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Error", border_style="red")
        else:
            self.io.secho(f"Error: {message}", fg="red")

    def _show_result(self, result: str, title: str = "Result") -> None:
        """Display result in green-bordered panel."""
        if hasattr(self.io, 'panel'):
            self.io.panel(result, title=title, border_style="green")
        else:
            self.io.secho(f"{title}: {result}", fg="green")

    def _show_warning(self, message: str) -> None:
        """Display warning in yellow-bordered panel."""
        if hasattr(self.io, 'panel'):
            self.io.panel(message, title="Warning", border_style="yellow")
        else:
            self.io.secho(f"Warning: {message}", fg="yellow")

    def _show_progress(self, message: str) -> None:
        """Display progress/status message."""
        self.io.secho(message, fg="cyan")

    def _show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None:
        """Display provider status message."""
        self.io.secho(f"[{provider}] {message}", fg=color)

    def _show_rule(self, title: Optional[str] = None) -> None:
        """Display horizontal rule separator."""
        if hasattr(self.io, 'rule'):
            self.io.rule(title)
        else:
            if title:
                self.io.echo(f"\n{'='*60}")
                self.io.echo(f" {title} ")
                self.io.echo(f"{'='*60}")
            else:
                self.io.echo(f"\n{'='*60}")

    def _tool_run_command(self, command: str) -> str:
        """Run a shell command using the extracted command executor."""
        # Check for interactive commands BEFORE delegating to executor
        # This is agent-specific behavior that requires user prompting
        cmd_lower = command.lower()
        for pattern in self.config.interactive_commands:
            if pattern in cmd_lower:
                self._show_warning(f"'{pattern}' may require interactive input")
                # Suggest workarounds for common cases
                if 'npx' in cmd_lower:
                    self.io.echo("   Tip: Add '-y' flag to skip prompts: npx -y create-react-app ...")
                # Ask if user wants interactive mode
                try:
                    use_interactive = self.io.prompt(
                        "   Run in interactive mode (you can respond to prompts)?",
                        default="y"
                    ).strip().lower()
                    if use_interactive != 'n':
                        return self._run_command_interactive(command)
                except (KeyboardInterrupt, EOFError):
                    self.io.echo("\n   Skipping interactive mode, running with captured output...")
                break

        # Delegate to the command executor for all other processing
        # This includes: security checks, platform fixes, retries, output parsing
        return self._command_executor.run(command, self.project_root, dry_run=self.dry_run)

    def _run_command_interactive(self, command: str) -> str:
        """
        Run a command in interactive mode - passes I/O directly to terminal.
        User can respond to prompts directly.
        """
        self._show_rule("INTERACTIVE MODE")
        self._show_command(command)
        self.io.echo("You can respond to any prompts. Output goes directly to terminal.")

        try:
            # Run command with direct terminal I/O (no capture)
            # This allows the user to see output and respond to prompts
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.project_root),
                # Don't capture - let it go directly to terminal
                # This allows interactive prompts to work
            )

            self._show_rule()
            self.io.secho(f"Command finished with exit code: {result.returncode}",
                         fg="green" if result.returncode == 0 else "red")

            if result.returncode == 0:
                return f"Command completed successfully (exit code 0). Output was displayed directly to terminal."
            else:
                return f"Command finished with exit code {result.returncode}. Check terminal output for details."

        except KeyboardInterrupt:
            self._show_rule()
            self.io.secho("Command stopped by user (Ctrl+C)", fg="yellow")

            # Provide context-aware message based on command type
            cmd_lower = command.lower()

            # Check if this was likely a successful setup followed by a dev server
            if any(pattern in cmd_lower for pattern in ['create', 'init', 'new', 'vite', 'next', 'nuxt']):
                return (
                    "Command was stopped by user (Ctrl+C). This is normal if a dev server was started. "
                    "The project setup likely completed successfully before the server started. "
                    "Check the terminal output above to confirm files were created, then use 'list_files' "
                    "to verify the project structure. Do NOT re-run the create/init command."
                )
            elif any(pattern in cmd_lower for pattern in ['dev', 'start', 'serve', 'watch']):
                return (
                    "Dev server was stopped by user (Ctrl+C). This is expected behavior - "
                    "the server was running successfully until stopped. No need to re-run."
                )
            else:
                return (
                    "Command was stopped by user (Ctrl+C). Check terminal output above to see "
                    "what was accomplished before the interrupt. The command may have partially "
                    "or fully completed its main task."
                )
        except Exception as e:
            return f"Error running interactive command: {str(e)}"

    def _categorize_command_approach(self, command: str) -> str:
        """
        Categorize a command into an approach type for retry tracking.

        This helps detect when the LLM is retrying the same failing approach.
        Delegates to the command executor's implementation.

        Args:
            command: The shell command

        Returns:
            String describing the approach type
        """
        return self._command_executor._categorize_command_approach(command)

    def _check_retry_pattern(self, command: str, failed_commands: list) -> str:
        """
        Check if a command follows a pattern that has already failed.

        Delegates to the command executor's implementation.

        Args:
            command: The command about to be executed
            failed_commands: List of previously failed commands with their approaches

        Returns:
            Warning message if retry pattern detected, empty string otherwise
        """
        return self._command_executor._check_retry_pattern(command, failed_commands)

    def _check_duplicate_action(self, action: AgentAction, state: ConversationState) -> str:
        """
        Check if an action is a duplicate of recent actions (infinite loop detection).

        Args:
            action: The action about to be executed
            state: Current conversation state with action history

        Returns:
            Warning message if duplicate detected, empty string otherwise
        """
        # Only check for actions that modify state (write operations)
        if action.action not in ['write_file', 'run_command']:
            return ""

        # Build current action signature for comparison
        current_sig = {
            "action": action.action,
            "parameters": action.parameters
        }

        # Check immediate duplicate (same as last action)
        if state.last_action:
            if (state.last_action.get("action") == action.action and
                state.last_action.get("parameters") == action.parameters):
                return (
                    f"Duplicate action detected: You just executed '{action.action}' with identical parameters. "
                    f"This action already succeeded. If you need to verify the result, use 'read_file' instead of repeating the write. "
                    f"If you think the file needs changes, make sure the new content is actually different."
                )

        # Check for repeated pattern (3+ times in action history)
        if hasattr(state, 'action_history') and len(state.action_history) >= 2:
            # Count how many times this exact action appears in recent history
            identical_count = sum(
                1 for hist_action in state.action_history[-5:]  # Check last 5 actions
                if (hist_action.get("action") == action.action and
                    hist_action.get("parameters") == action.parameters)
            )

            if identical_count >= 2:
                return (
                    f"Repeated action pattern detected: '{action.action}' with these exact parameters "
                    f"has been executed {identical_count} times already. This suggests an infinite loop. "
                    f"You MUST try a different approach:\n"
                    f"- If writing a file: Read it first to see what's actually there\n"
                    f"- If the content has a bug: Make sure your new content actually fixes it\n"
                    f"- If the file is correct: Mark the task as complete instead of rewriting"
                )

        return ""

    def _get_user_confirmation(self, action: str, params: dict) -> bool:
        """Ask user for confirmation before executing action."""
        # Auto-approve safe read-only operations
        safe_actions = ['read_file', 'list_files', 'list_directory', 'search_files', 'search_code', 'git_status', 'git_log', 'git_diff']
        if action in safe_actions:
            # Display tool request with auto-approval status
            display_params = params.copy()
            display_params['_status'] = 'Auto-approved (safe operation)'
            self._show_tool_request(action, params)
            self.io.secho("Auto-approved (safe operation)", fg="green")
            return True

        # Display tool request for approval
        self._show_tool_request(action, params)

        # Show preview for write operations
        if action == 'write_file' and 'content' in params:
            content = params['content']
            max_preview = self.config.write_preview_truncation
            preview = content[:max_preview] + "..." if len(content) > max_preview else content
            if hasattr(self.io, 'syntax'):
                # Try to detect language from file extension
                file_path = params.get('path', '')
                lang = 'text'
                if file_path.endswith('.py'):
                    lang = 'python'
                elif file_path.endswith(('.js', '.jsx')):
                    lang = 'javascript'
                elif file_path.endswith(('.ts', '.tsx')):
                    lang = 'typescript'
                elif file_path.endswith('.json'):
                    lang = 'json'
                elif file_path.endswith(('.yml', '.yaml')):
                    lang = 'yaml'
                elif file_path.endswith('.md'):
                    lang = 'markdown'
                self.io.echo("\nContent preview:")
                self.io.syntax(preview, language=lang)
            else:
                self.io.echo(f"\nContent preview:\n{preview}")

        try:
            return self.io.confirm("Allow?", default=False)
        except (KeyboardInterrupt, EOFError):
            self.io.echo("\nAction cancelled.")
            raise  # Re-raise to stop the agent loop

    # ========== Decoupled Agent Loop Methods ==========

    def _think(self, state: ConversationState) -> AgentThought:
        """
        Generate the next thought/action from the LLM.

        This is the reasoning stage where the agent decides what to do next.

        Args:
            state: Current conversation state

        Returns:
            AgentThought containing raw LLM response
        """
        import sys
        import time

        # Get current recommended provider (may change between calls due to rate limits)
        if self._use_dynamic_selection and hasattr(self._orchestrator, 'get_recommended_provider'):
            current_provider = self._orchestrator.get_recommended_provider('planning')
            # Update cached value for display
            self.planner = current_provider
        else:
            current_provider = self.planner

        # Show progress indicator during API call
        if state.iteration == 1:
            self._show_provider_status(current_provider, "Analyzing task (this may take a moment)...")
        else:
            self._show_provider_status(current_provider, "Thinking...")

        # Build the prompt with conversation history for multi-turn
        if len(state.messages) == 2:
            # First iteration: just use the task
            user_prompt = state.messages[-1]['content']
        else:
            # Subsequent iterations: include conversation history
            history_parts = []
            for msg in state.messages[2:]:  # Skip system prompt and initial task
                role = msg['role'].upper()
                history_parts.append(f"{role}: {msg['content']}")
            history_text = "\n\n".join(history_parts)
            user_prompt = f"Previous conversation:\n{history_text}\n\nBased on the above, continue with the task. Remember to respond with valid JSON."

        # Track API call time for first iteration
        start_time = time.time()

        # Check if orchestrator adapter has delegate_with_tools
        # and if provider supports native tool calling
        has_delegate_with_tools = hasattr(self.orch, 'delegate_with_tools')
        provider_supports_tools = False

        if has_delegate_with_tools and hasattr(self._orchestrator, '_registry'):
            provider_obj = self._orchestrator._registry.get(current_provider)
            if provider_obj and hasattr(provider_obj, 'supports_tool_calling'):
                provider_supports_tools = provider_obj.supports_tool_calling

        # Use native tool calling if both adapter and provider support it
        if has_delegate_with_tools and provider_supports_tools:
            # Get tool schemas in OpenAI format
            tools = self.tool_registry.to_openai_schema()

            # Add run_command tool (not in registry, manual schema)
            tools.append({
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Execute a shell command. Use for git operations, builds, tests, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Brief explanation of what the command does"
                            }
                        },
                        "required": ["command"]
                    }
                }
            })

            # Add "complete" tool for task completion
            tools.append({
                "type": "function",
                "function": {
                    "name": "complete",
                    "description": "Mark the task as complete and provide final result",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "result": {
                                "type": "string",
                                "description": "Final result or summary of completed task"
                            }
                        },
                        "required": ["result"]
                    }
                }
            })

            response = self.orch.delegate_with_tools(
                provider_name=current_provider,
                prompt=user_prompt,
                tools=tools,
                system_prompt=state.system_prompt,
                max_tokens=self.config.default_max_tokens,
                temperature=self.config.default_temperature,
                tool_choice="auto"
            )
            actual_provider = response.provider
        else:
            # Fall back to regular delegate with JSON parsing
            if self._use_dynamic_selection:
                response = self.orch.delegate(
                    provider_name=None,  # Let orchestrator decide
                    prompt=user_prompt,
                    system_prompt=state.system_prompt,
                    max_tokens=self.config.default_max_tokens,
                    temperature=self.config.default_temperature,
                    use_context=False,  # Context already in system prompt
                    task_type='planning'  # Inform orchestrator this is a planning task
                )
                # Update planner to reflect what was actually used
                actual_provider = response.provider
            else:
                response = self.orch.delegate(
                    current_provider,
                    user_prompt,
                    system_prompt=state.system_prompt,
                    max_tokens=self.config.default_max_tokens,
                    temperature=self.config.default_temperature,
                    use_context=False  # Context already in system prompt
                )
                actual_provider = current_provider

        # Report latency on first call (helps user understand wait times)
        if state.iteration == 1:
            elapsed = time.time() - start_time
            self._show_provider_status(actual_provider, f"Response received ({elapsed:.1f}s)", color="green")

        return AgentThought(
            raw_response=response.content,
            provider=actual_provider,
            iteration=state.iteration,
            llm_response=response  # Store full response for native tool calls
        )

    def _plan_action(self, thought: AgentThought) -> AgentAction:
        """
        Parse the LLM response into a structured action.

        This is the planning stage where we extract the action to take.

        Args:
            thought: Raw thought from _think()

        Returns:
            AgentAction with parsed action details
        """
        # Check if we have a full LLMResponse with actual tool_calls (non-empty list)
        # Empty list or None means fall back to JSON parsing
        if (thought.llm_response and
            thought.llm_response.tool_calls is not None and
            len(thought.llm_response.tool_calls) > 0):
            # Use the response parser to handle LLMResponse objects
            # UnifiedResponseParser will automatically detect and use NativeToolCallParser
            parse_result = self._response_parser.parse(thought.llm_response)
        else:
            # Fall back to parsing raw text response (JSON format)
            # This handles: no llm_response, tool_calls=None, or tool_calls=[]
            parse_result = self._response_parser.parse(thought.raw_response)

        return AgentAction(
            thought=parse_result.thought,
            action=parse_result.action,
            parameters=parse_result.parameters,
            is_complete=parse_result.is_complete,
            result_text=parse_result.result_text
        )

    def _execute(self, action: AgentAction, state: ConversationState) -> ActionResult:
        """
        Execute the planned action (tool call).

        This is the execution stage where the tool is actually run.

        Args:
            action: Parsed action from _plan_action()
            state: Current conversation state (for auto_confirm)

        Returns:
            ActionResult with execution details
        """
        # Display thinking in panel
        self._show_thinking(action.thought)

        # Handle parse failure - provide feedback to LLM to retry with valid JSON
        if action.action == 'retry_parse':
            # Show what the LLM actually returned for debugging
            raw_response = action.parameters.get('raw_response', 'No response captured')
            self._show_error(f"Response parsing failed. LLM returned:\n{raw_response[:300]}...")
            self.io.secho("Requesting JSON format retry...", fg="yellow")
            error_msg = (
                "Your previous response could not be parsed as JSON. "
                "You MUST respond with ONLY a valid JSON object (no other text). "
                "Use this exact format:\n"
                '{\n'
                '  "thought": "Your reasoning here",\n'
                '  "action": "tool_name",\n'
                '  "parameters": {"param": "value"},\n'
                '  "is_complete": false\n'
                '}\n'
                "Available tools: read_file, write_file, list_files, list_directory, search_code, run_command\n"
                "Make sure all strings are properly quoted with double quotes. Do not include any text outside the JSON object."
            )
            return ActionResult(
                success=False,
                output=error_msg,
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Check if this is a valid tool action
        if action.action not in self.tools or action.action == 'complete':
            return ActionResult(
                success=True,  # Not a failure, just no execution
                output="",
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # Handle unknown actions
        if action.action not in self.tools and action.action != 'complete' and action.action != 'error':
            self._show_error(f"Unknown action: {action.action}")
            return ActionResult(
                success=False,
                output=f"Unknown action '{action.action}'. Available tools: {', '.join(self.tools.keys())}",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Get user confirmation (unless auto_confirm)
        if state.auto_confirm:
            approved = True
        else:
            approved = self._get_user_confirmation(action.action, action.parameters)

        if not approved:
            self.io.secho("Action denied by user", fg="yellow")
            self._log_action(action.action, action.parameters, "Denied by user", False)
            return ActionResult(
                success=False,
                output="Denied by user",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Check for duplicate actions - prevent infinite loops
        duplicate_warning = self._check_duplicate_action(action, state)
        if duplicate_warning:
            self._show_warning(f"Duplicate Action: {duplicate_warning}")
            # Return warning to LLM instead of executing
            return ActionResult(
                success=False,
                output=duplicate_warning,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # Check for retry patterns - detect if same approach is being repeated
        if action.action == 'run_command' and state.failed_commands:
            command = action.parameters.get('command', '')
            retry_warning = self._check_retry_pattern(command, state.failed_commands)
            if retry_warning:
                self._show_warning(f"Retry Pattern: {retry_warning}")
                # Add warning to state for next iteration
                state.retry_warnings.append(retry_warning)

        # Execute the tool
        self.io.secho(f"Executing: {action.action}", fg="cyan", bold=True)

        # Show command in syntax block for run_command
        if action.action == 'run_command':
            cmd = action.parameters.get('command', '')
            if cmd:
                self._show_command(cmd)
        tool_result = self.tools[action.action](**action.parameters)

        # Track failed commands for retry detection
        if action.action == 'run_command':
            command = action.parameters.get('command', '')
            if 'Error' in tool_result or 'failed' in tool_result.lower():
                # Categorize the approach for better tracking
                approach = self._categorize_command_approach(command)
                state.failed_commands.append({
                    'command': command,
                    'error': tool_result[:200],  # Truncate error
                    'approach': approach,
                    'iteration': state.iteration
                })
                self.io.secho(f"   [Tracked] Failed '{approach}' approach - will suggest alternatives", fg="yellow")

                # Check if this is a scaffolding approach
                scaffolding_approaches = [
                    'spring_initializr_download', 'curl_download',
                    'powershell_download', 'npm_create_project'
                ]

                # If ANY scaffolding approach failed, inject strong write_file suggestion
                if approach in scaffolding_approaches:
                    scaffolding_failures = sum(
                        1 for f in state.failed_commands
                        if f['approach'] in scaffolding_approaches
                    )
                    if scaffolding_failures >= 1:
                        warning = (
                            f"MANDATORY STRATEGY CHANGE: Scaffolding/download approaches have failed {scaffolding_failures} time(s). "
                            f"You MUST now use write_file tool to create project files directly. "
                            f"Do NOT attempt any more curl, npm create, or spring initializr commands. "
                            f"For Spring Boot: write_file to create pom.xml, Application.java, etc. "
                            f"For React: write_file to create package.json, App.jsx, etc."
                        )
                        state.retry_warnings.append(warning)
                        self.io.secho("   [MANDATORY] Switching to write_file strategy after scaffolding failure", fg="red", bold=True)

                # If same approach failed twice, inject strong warning
                approach_failures = sum(1 for f in state.failed_commands if f['approach'] == approach)
                if approach_failures >= 2:
                    warning = (
                        f"CRITICAL: The '{approach}' approach has failed {approach_failures} times. "
                        f"You MUST try a completely different strategy. "
                        f"If using shell commands, switch to write_file tool instead."
                    )
                    state.retry_warnings.append(warning)

        # Display result
        max_display = self.config.result_display_truncation
        if len(tool_result) > max_display:
            display_result = tool_result[:max_display] + "... [truncated]"
        else:
            display_result = tool_result

        # Use panel for results if available
        if hasattr(self.io, 'panel'):
            # Determine result style based on content
            if 'Error' in tool_result or 'failed' in tool_result.lower():
                self.io.panel(display_result, title="Result", border_style="red")
            else:
                self.io.panel(display_result, title="Result", border_style="green")
        else:
            self.io.echo(f"Result: {display_result}")

        self._log_action(action.action, action.parameters, tool_result, True)

        return ActionResult(
            success=True,
            output=tool_result,
            action=action.action,
            parameters=action.parameters,
            approved=True,
            executed=True
        )

    def _evaluate(
        self,
        action: AgentAction,
        result: ActionResult,
        state: ConversationState
    ) -> EvaluationResult:
        """
        Evaluate whether the task is complete and if we should continue.

        This is the evaluation stage where we check completion criteria.

        Args:
            action: The action that was planned
            result: The result of executing the action
            state: Current conversation state

        Returns:
            EvaluationResult indicating whether to continue or complete
        """
        # Check if task is complete (AFTER executing any actions)
        if action.is_complete or action.action == 'complete':
            # Verify that at least one meaningful action was performed
            meaningful_actions = [
                t for t in state.tools_executed
                if t in self.config.meaningful_actions
            ]

            if not meaningful_actions and not self.dry_run:
                self._show_warning("Agent declared completion without performing any file operations.")
                self.io.echo("Requesting agent to actually execute the task...")
                return EvaluationResult(
                    is_complete=False,
                    should_continue=True,
                    reason="No meaningful actions performed yet"
                )

            final_result = action.result_text or 'Task completed'
            self._show_rule("Task Complete")
            self._show_result(final_result, title="Final Result")
            self._log_action('complete', {}, final_result, True)

            return EvaluationResult(
                is_complete=True,
                should_continue=False,
                reason="Task marked as complete",
                final_result=final_result
            )

        # Smart completion: DISABLED - rely on explicit agent completion signals
        # The heuristic approach was too aggressive, stopping after simple write operations
        # even when the task had multiple components. Let the LLM decide when it's done.
        #
        # Previous logic checked for write_file operations and declared "done" prematurely.
        # This caused issues with complex multi-part tasks (e.g., backend + frontend).
        #
        # Now the agent must explicitly call action='complete' or set is_complete=True.
        # This gives the LLM control over task completion semantics.
        pass  # Intentionally disabled heuristic completion

        # Check max iterations
        if state.iteration >= state.max_iterations:
            return EvaluationResult(
                is_complete=False,
                should_continue=False,
                reason=f"Max iterations ({state.max_iterations}) reached"
            )

        # Continue with more iterations
        return EvaluationResult(
            is_complete=False,
            should_continue=True,
            reason="Task not yet complete"
        )

    def _update_conversation(
        self,
        state: ConversationState,
        thought: AgentThought,
        action: AgentAction,
        result: ActionResult
    ) -> None:
        """
        Update the conversation history based on the action and result.

        Args:
            state: Conversation state to update
            thought: The raw thought from LLM
            action: The parsed action
            result: The execution result
        """
        if result.executed:
            # Tool was executed successfully
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })

            # Track action in history for duplicate detection
            action_record = {
                "action": result.action,
                "parameters": result.parameters
            }
            state.action_history.append(action_record)
            state.last_action = action_record

            # Build user message with tool result and any retry warnings
            user_message = f"Tool result for {result.action}:\n{result.output}\n"

            # Inject retry warnings if any failures were tracked
            if state.retry_warnings:
                user_message += "\n--- IMPORTANT WARNINGS ---\n"
                for warning in state.retry_warnings:
                    user_message += f"- {warning}\n"
                user_message += "--- END WARNINGS ---\n"
                # Clear warnings after injecting
                state.retry_warnings.clear()

            # For write_file operations, encourage verification
            if result.action == 'write_file':
                file_path = result.parameters.get('path', 'the file')
                user_message += f"\nSuggestion: Consider reading {file_path} to verify the content is correct.\n"

            user_message += "\nContinue with the task or mark as complete if done."

            state.messages.append({
                'role': 'user',
                'content': user_message
            })
            state.tools_executed.append(result.action)
        elif not result.approved and result.action in self.tools:
            # Tool was denied by user
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': f"User denied the {result.action} action. Please try a different approach or explain why this action is necessary."
            })
        elif result.approved and not result.executed and result.action in self.tools:
            # Tool was approved but not executed (e.g., duplicate detected)
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': result.output  # Contains warning message (e.g., duplicate detection)
            })
        elif action.action == 'retry_parse':
            # Parse failure - provide detailed JSON format instructions
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': result.output  # Contains the detailed JSON format instructions
            })
        elif action.action not in self.tools and action.action != 'complete' and action.action != 'error':
            # Unknown action
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': f"Unknown action '{action.action}'. Available tools: {', '.join(self.tools.keys())}"
            })
        elif action.is_complete and not result.executed:
            # Agent wants to complete but no action executed and no meaningful work done
            meaningful_actions = [t for t in state.tools_executed if t in self.config.meaningful_actions]
            if not meaningful_actions and not self.dry_run:
                state.messages.append({
                    'role': 'assistant',
                    'content': thought.raw_response
                })
                state.messages.append({
                    'role': 'user',
                    'content': "You declared the task complete but haven't actually created or modified any files. Please respond with a JSON object containing an action to execute. Use the write_file tool to actually create the requested code. Example format:\n{\n  \"thought\": \"your reasoning\",\n  \"action\": \"write_file\",\n  \"parameters\": {\"path\": \"filename\", \"content\": \"code here\"}\n}"
                })

    def run(self, task: str, max_iterations: int = 10, auto_confirm: bool = False) -> dict:
        """
        Run the agent on a task using decoupled stages.

        The agent loop follows clear stages:
        1. Think - LLM generates next thought/action
        2. Plan - Parse response into structured action
        3. Execute - Run the tool
        4. Evaluate - Check if task is complete

        Args:
            task: The task to accomplish
            max_iterations: Maximum number of tool uses
            auto_confirm: Skip user confirmation (use with caution)

        Returns:
            dict with 'success', 'result', 'audit_log'
        """
        # Update tool context dry_run state
        self.tool_context.dry_run = self.dry_run

        # Enable auto-save for crash safety
        self._audit_logger.enable_auto_save(self.project_root, ".llm_agent_audit.json")
        self._audit_logger.set_task_info(task, max_iterations, auto_confirm)

        # Concise header
        task_preview = task[:80] + "..." if len(task) > 80 else task
        self._show_rule("Agent Task")
        self.io.secho(task_preview, fg="white", bold=True)
        if self.dry_run:
            self.io.secho("[DRY RUN MODE]", fg="yellow", bold=True)

        # Build initial context
        self._show_progress("Building context...")

        # System prompt for agent - use SystemPromptBuilder for context-aware construction
        self._show_progress("Preparing system prompt...")
        from src.agent.system_prompt_builder import SystemPromptBuilder

        # Create SystemPromptBuilder with tool registry for unified prompt generation
        prompt_builder = SystemPromptBuilder(
            context=self.orch.context,
            tool_registry=self.tool_registry
        )

        # Check if we should use native tool calling
        # Determine this early so we can build the appropriate system prompt
        use_native_tools = False
        current_provider = self.planner
        if hasattr(self._orchestrator, '_registry'):
            provider_obj = self._orchestrator._registry.get(current_provider)
            if provider_obj and hasattr(provider_obj, 'supports_tool_calling'):
                use_native_tools = provider_obj.supports_tool_calling and hasattr(self.orch, 'delegate_with_tools')

        # Build the complete system prompt with task context
        # PromptBuilder now includes all operational guidance (strategy, efficiency,
        # completion semantics, safety rules) as proper sections
        # Skip JSON format instructions if using native tool calling
        system_prompt = prompt_builder.build(task=task, use_native_tools=use_native_tools)

        # Initialize conversation state
        state = ConversationState(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Please complete this task: {task}"}
            ],
            system_prompt=system_prompt,
            iteration=0,
            max_iterations=max_iterations,
            tools_executed=[],
            auto_confirm=auto_confirm
        )

        # Main agent loop - decoupled stages with crash safety
        self._show_progress("Starting agent loop...")
        try:
            while state.iteration < state.max_iterations:
                state.iteration += 1
                # Minimal iteration indicator (only show on first iteration)
                if state.iteration == 1:
                    self.io.secho("Working...", fg="cyan")

                # Stage 1: Think - LLM generates next thought/action
                thought = self._think(state)

                # Stage 2: Plan - Parse response into structured action
                action = self._plan_action(thought)

                # Stage 3: Execute - Run the tool
                result = self._execute(action, state)

                # Stage 4: Evaluate - Check if task is complete
                evaluation = self._evaluate(action, result, state)

                # Update conversation history
                self._update_conversation(state, thought, action, result)

                # Check evaluation result
                if evaluation.is_complete:
                    self._audit_logger.mark_complete(True, evaluation.final_result)
                    return {
                        'success': True,
                        'result': evaluation.final_result,
                        'iterations': state.iteration,
                        'audit_log': self.audit_log
                    }

                if not evaluation.should_continue:
                    # Max iterations or other stopping condition
                    self._audit_logger.mark_complete(False, evaluation.reason)
                    return {
                        'success': False,
                        'result': evaluation.reason,
                        'iterations': state.iteration,
                        'audit_log': self.audit_log
                    }

            # Max iterations reached (shouldn't get here but safety check)
            self._audit_logger.mark_complete(False, f'Max iterations ({max_iterations}) reached')
            return {
                'success': False,
                'result': f'Max iterations ({max_iterations}) reached',
                'iterations': state.iteration,
                'audit_log': self.audit_log
            }
        except KeyboardInterrupt:
            # User cancelled - save partial state
            self.io.echo("")  # New line
            self._show_warning("Agent interrupted by user. Saving audit log...")
            self._audit_logger.mark_complete(False, "Interrupted by user (KeyboardInterrupt)")
            raise  # Re-raise to let caller handle
        except Exception as e:
            # Unexpected error - save partial state for debugging
            self.io.echo("")  # New line
            self._show_error(f"Agent error: {str(e)}\nSaving audit log...")
            self._audit_logger.mark_complete(False, f"Error: {str(e)}")
            raise  # Re-raise to let caller handle

    def get_audit_log(self) -> list:
        """Get the audit log of all actions."""
        return self.audit_log

    def save_audit_log(self, path: str = ".agent_audit.json"):
        """Save audit log to file."""
        return self._audit_logger.save(self.project_root, path)
