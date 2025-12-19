"""
Core Code Agent implementation.

The main CodeAgent class with tool use and safety features.

Note: The agent loop logic has been extracted to AgentLoop (agent_loop.py)
and provider selection to ProviderSelectionStrategy (provider_strategy.py)
as part of the god class refactoring effort.
"""

import subprocess
from pathlib import Path
from typing import Optional, Union, Any

from ..agent_config import AgentConfig
from ..agent_tools.tools import ToolContext
from ..agent_tools.tools.command_tool import ShellCommandExecutor

from ..orchestrator_adapter import (
    OrchestratorAdapter,
    AgentOrchestratorAdapter,
)
from ..infrastructure.exceptions import AllProvidersRateLimitedError
from ..agent_tools.registry_factory import create_default_registry

from .types import (
    ConversationState,
)
from .audit import AuditLogger
from .response_parser import UnifiedResponseParser
from .protocols import ResponseParserProtocol

# Import new components
from .ui import AgentUI
from .safety_checker import SafetyChecker
from .duplicate_detector import DuplicateDetector
from .tool_runner import ToolRunner
from .action_executor import ActionExecutor

# Import extracted components (Phase 1 refactoring)
from .agent_loop import AgentLoop
from .provider_strategy import create_provider_strategy

# Import prompt factory
from scrappy.prompts import PromptFactory, AgentPromptConfig, Platform

# Import context factory
from .context_factory import AgentContextFactory

# Import protocols
from .protocols import (
    AgentUIProtocol,
    SafetyCheckerProtocol,
    DuplicateDetectorProtocol,
    ToolRunnerProtocol,
    ActionExecutorProtocol,
    ToolRegistryProtocol,
    AgentLoopProtocol,
    ProviderSelectionStrategyProtocol,
)
from ..infrastructure.protocols import PathProviderProtocol
from ..infrastructure.paths import ScrappyPathProvider


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
        tool_registry: Optional[ToolRegistryProtocol] = None,
        io: Optional[Any] = None,  # CLIIOProtocol - Any to avoid circular import
        file_system: Optional[Any] = None,  # FileSystemProtocol
        audit_logger: Optional[Any] = None,  # AuditLoggerProtocol
        response_parser: Optional[Any] = None,  # ResponseParserProtocol
        tool_context: Optional[Any] = None,  # ToolContextProtocol
        command_executor: Optional[Any] = None,  # ShellCommandExecutor
        path_provider: Optional[PathProviderProtocol] = None,  # PathProviderProtocol
        # New component parameters
        ui: Optional[AgentUIProtocol] = None,
        safety_checker: Optional[SafetyCheckerProtocol] = None,
        duplicate_detector: Optional[DuplicateDetectorProtocol] = None,
        tool_runner: Optional[ToolRunnerProtocol] = None,
        action_executor: Optional[ActionExecutorProtocol] = None,
        # Phase 1 refactoring: extracted components
        provider_strategy: Optional[ProviderSelectionStrategyProtocol] = None,
        agent_loop: Optional[AgentLoopProtocol] = None,
        prompt_factory: Optional[Any] = None,  # PromptFactoryProtocol
        cancellation_token: Optional[Any] = None,  # CancellationTokenProtocol
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
        self._cancellation_token = cancellation_token

        # IO interface
        self.io = io or self._create_default_io()

        # File system
        self._file_system = file_system or self._create_default_file_system()

        # Path provider (store for use in audit logger)
        self._path_provider = path_provider

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

        # Create default path provider if not provided
        if self._path_provider is None:
            self._path_provider = ScrappyPathProvider(self.project_root)

        # Audit logger
        self._audit_logger = audit_logger or self._create_default_audit_logger()

        # Response parser
        self._response_parser: ResponseParserProtocol = response_parser or self._create_default_response_parser()

        # Tool context
        # Note: Can't use self.ui yet as it's not created until after tool_context
        self.io.secho("Preparing agent tools...", fg="cyan")
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

        # Setup new agent components
        # UI wraps the IO interface
        self.ui = ui or AgentUI(self.io, verbose=self.config.verbose)

        # Setup execution components (in dependency order)
        self._safety_checker = safety_checker or SafetyChecker()
        self._duplicate_detector = duplicate_detector or DuplicateDetector()
        self._tool_runner = tool_runner or ToolRunner(
            tool_registry=self.tool_registry,
            command_executor=self._command_executor,
            tool_context=self.tool_context,
        )
        self.action_executor = action_executor or ActionExecutor(
            safety_checker=self._safety_checker,
            duplicate_detector=self._duplicate_detector,
            tool_runner=self._tool_runner,
            ui=self.ui,
            cancellation_token=self._cancellation_token,
        )

        # Use orchestrator's intelligent provider selection
        self.ui.show_progress("Selecting AI providers...")
        available = self.adapter.list_providers()

        # Store orchestrator reference for dynamic provider selection
        self._orchestrator = orchestrator

        # Phase 1 refactoring: Use ProviderSelectionStrategy instead of inline logic
        # Check if adapter has a preferred provider override (from task routing)
        preferred_provider = None
        if hasattr(self.adapter, 'get_preferred_provider'):
            pref_provider, pref_model = self.adapter.get_preferred_provider()
            if pref_provider and pref_provider in available:
                preferred_provider = pref_provider

        # Create provider strategy (factory chooses dynamic vs static)
        self._provider_strategy = provider_strategy or create_provider_strategy(
            orchestrator=orchestrator,
            config=self.config,
            available_providers=available,
            preferred_provider=preferred_provider,
        )

        # Backward compatibility: expose planner/executor properties
        self._use_dynamic_selection = self._provider_strategy.supports_dynamic_selection()
        self.planner = self._provider_strategy.get_planner()
        self.executor = self._provider_strategy.get_executor()

        # Get semantic search manager from orchestrator context for context factory
        semantic_manager = None
        if hasattr(self._orchestrator, 'context'):
            semantic_manager = self._orchestrator.context.semantic_manager

        # Create context factory for per-iteration context building
        self._context_factory = AgentContextFactory(
            semantic_manager=semantic_manager,
            config=self.config,
            tool_registry=self.tool_registry,
        )

        # Phase 1 refactoring: Create AgentLoop
        self._agent_loop = agent_loop or AgentLoop(
            orchestrator=self.adapter,
            action_executor=self.action_executor,
            response_parser=self._response_parser,
            ui=self.ui,
            tool_registry=self.tool_registry,
            provider_strategy=self._provider_strategy,
            config=self.config,
            context_factory=self._context_factory,
            audit_logger=self._audit_logger,
            tools=self.tools,
            cancellation_token=self._cancellation_token,
        )

        # Prompt factory for stateless prompt generation
        self._prompt_factory = prompt_factory or PromptFactory()

    # Factory methods for default dependencies

    def _create_default_io(self):
        """Create default IO interface.

        WARNING: This factory should ONLY be used by tests for convenience.
        Production code MUST inject IO via the constructor parameter.
        Creating multiple UnifiedIO instances breaks TUI mode routing.
        """
        from ..cli.unified_io import UnifiedIO
        return UnifiedIO()

    def _create_default_file_system(self):
        """Create default file system."""
        from ..infrastructure.file_system import RealFileSystem
        return RealFileSystem()

    def _create_default_audit_logger(self):
        """Create default audit logger."""
        return AuditLogger(
            max_result_length=self.config.audit_log_result_truncation,
            path_provider=self._path_provider
        )

    def _create_default_response_parser(self):
        """Create default response parser."""
        return UnifiedResponseParser()

    def _create_default_tool_context(self):
        """Create default tool context."""
        # Get semantic search provider from orchestrator context
        semantic_search = None
        if hasattr(self._initial_orchestrator, 'context') and hasattr(self._initial_orchestrator.context, 'get_search_provider'):
            semantic_search = self._initial_orchestrator.context.get_search_provider()

        return ToolContext(
            project_root=self.project_root,
            dry_run=self.dry_run,
            config=self.config,
            orchestrator=self._initial_orchestrator,
            semantic_search=semantic_search
        )

    def _create_default_tool_registry(self):
        """Create default tool registry."""
        # Get semantic search from tool_context (already created)
        semantic_search = getattr(self.tool_context, 'semantic_search', None)

        return create_default_registry(
            command_timeout=self.config.command_timeout,
            max_command_output=self.config.max_command_output,
            dangerous_commands=self.config.dangerous_commands,
            semantic_search=semantic_search,
            profile=self.config.tool_profile,
        )

    def _create_default_command_executor(self):
        """Create default shell command executor."""
        return ShellCommandExecutor(
            timeout=self.config.command_timeout,
            max_output=self.config.max_command_output,
            dangerous_patterns=self.config.dangerous_commands
        )

    def _format_codebase_structure(self) -> Optional[str]:
        """Format codebase structure for prompt inclusion."""
        file_index = self.orch.context.file_index
        if not file_index:
            return None

        # Extract unique directories for each file type
        dir_map = {}
        for lang, files in file_index.items():
            if not files or lang in ('config', 'docs', 'other', 'web'):
                continue

            dirs = set()
            for file_path in files:
                normalized = file_path.replace('\\', '/')
                if '/' in normalized:
                    dir_path = '/'.join(normalized.split('/')[:-1])
                    dirs.add(dir_path)
                else:
                    dirs.add('.')

            if dirs:
                dir_map[lang] = dirs

        if not dir_map:
            return None

        # Build concise structure description
        lines = []
        for lang, dirs in sorted(dir_map.items()):
            file_count = len(file_index.get(lang, []))
            dir_list = ', '.join(sorted(dirs)[:5])
            if len(dirs) > 5:
                dir_list += f' (+{len(dirs) - 5} more)'
            lines.append(f"- {lang}: {dir_list} ({file_count} files)")

        return '\n'.join(lines)

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

    def _tool_run_command(self, command: str) -> str:
        """Run a shell command using the extracted command executor."""
        # Check for interactive commands BEFORE delegating to executor
        # This is agent-specific behavior that requires user prompting
        cmd_lower = command.lower()
        for pattern in self.config.interactive_commands:
            if pattern in cmd_lower:
                self.ui.show_warning(f"'{pattern}' may require interactive input")
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
        self.ui.show_rule("INTERACTIVE MODE")
        self.ui.show_command(command)
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

            self.ui.show_rule()
            self.io.secho(f"Command finished with exit code: {result.returncode}",
                         fg="green" if result.returncode == 0 else "red")

            if result.returncode == 0:
                return "Command completed successfully (exit code 0). Output was displayed directly to terminal."
            else:
                return f"Command finished with exit code {result.returncode}. Check terminal output for details."

        except KeyboardInterrupt:
            self.ui.show_rule()
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

    def run(self, task: str, max_iterations: int = 10, auto_confirm: bool = False) -> dict:
        """
        Run the agent on a task using decoupled stages.

        The agent loop follows clear stages (delegated to AgentLoop):
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

        # Enable auto-save for crash safety (uses path_provider)
        self._audit_logger.enable_auto_save()
        self._audit_logger.set_task_info(task, max_iterations, auto_confirm)

        # Concise header
        task_preview = task[:80] + "..." if len(task) > 80 else task
        self.ui.show_rule("Agent Task")
        self.io.secho(task_preview, fg="white", bold=True)
        if self.dry_run:
            self.io.secho("[DRY RUN MODE]", fg="yellow", bold=True)

        # Build initial context
        self.ui.show_progress("Building context...")

        # System prompt for agent - use PromptFactory for stateless prompt generation
        self.ui.show_progress("Preparing system prompt...")

        # Ensure context is explored
        if not self.orch.context.is_explored():
            self.orch.context.explore()

        # Check if we should use native tool calling
        # Determine this early so we can build the appropriate system prompt
        use_native_tools = False
        current_provider = self.planner
        if hasattr(self._orchestrator, '_registry'):
            provider_obj = self._orchestrator._registry.get(current_provider)
            if provider_obj and hasattr(provider_obj, 'supports_tool_calling'):
                use_native_tools = provider_obj.supports_tool_calling and hasattr(self.orch, 'delegate_with_tools')

        # Build config for prompt generation
        platform = Platform.WINDOWS if self.orch.context.platform.is_windows() else Platform.UNIX
        config = AgentPromptConfig(
            platform=platform,
            tool_descriptions=self.tool_registry.generate_descriptions(),
            use_native_tools=use_native_tools,
            project_type=self.orch.context.get_project_type(),
            codebase_structure=self._format_codebase_structure()
        )

        # Build the base system prompt
        base_system_prompt = self._prompt_factory.create_agent_system_prompt(config)

        # Build agent context with passive RAG and tool filtering using injected factory
        agent_context = self._context_factory.build_context(
            task=task,
            base_system_prompt=base_system_prompt,
        )

        # Use the enriched system prompt from context factory
        system_prompt = agent_context.system_prompt

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

        # Phase 1 refactoring: Delegate to AgentLoop
        # AgentLoop now uses injected context_factory to rebuild context per iteration
        try:
            self.io.secho("Working...", fg="cyan")
            result = self._agent_loop.run(
                task,
                state,
                dry_run=self.dry_run,
            )

            # Update audit log with result
            if result['success']:
                self._audit_logger.mark_complete(True, result['result'])
            else:
                self._audit_logger.mark_complete(False, result['result'])

            # Add audit_log to result for backward compatibility
            result['audit_log'] = self.audit_log
            return result

        except KeyboardInterrupt:
            # User cancelled - save partial state
            self.io.echo("")  # New line
            self.ui.show_warning("Agent interrupted by user. Saving audit log...")
            self._audit_logger.mark_complete(False, "Interrupted by user (KeyboardInterrupt)")
            raise  # Re-raise to let caller handle
        except AllProvidersRateLimitedError as e:
            # All providers exhausted - graceful degradation
            self.io.echo("")  # New line
            self.ui.show_error(
                f"All LLM providers are rate limited.\n"
                f"Attempted providers: {', '.join(e.attempted_providers)}\n"
                f"Please wait a few minutes before retrying, or configure additional providers."
            )
            self._audit_logger.mark_complete(False, f"Rate limited: {str(e)}")
            # Return a result instead of raising, for graceful degradation
            return {
                'success': False,
                'result': f"Task paused: All providers rate limited ({', '.join(e.attempted_providers)})",
                'iterations': state.iteration,
                'tools_executed': state.tools_executed,
                'audit_log': self.audit_log,
                'rate_limited': True,
                'attempted_providers': e.attempted_providers,
            }
        except Exception as e:
            # Unexpected error - save partial state for debugging
            # Don't display error here - let caller handle display
            self._audit_logger.mark_complete(False, f"Error: {str(e)}")
            raise  # Re-raise to let caller handle

    def get_audit_log(self) -> list:
        """Get the audit log of all actions."""
        return self.audit_log

    def save_audit_log(self) -> str:
        """
        Save audit log to file.

        Uses path_provider to determine correct location (.scrappy/audit.json).

        Returns:
            Path to the saved audit log file.
        """
        return self._audit_logger.save()
