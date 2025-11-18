"""
Core CLI functionality.
Main entry point and command routing for the LLM Agent Team CLI.
"""

import click
import sys
from datetime import datetime
from typing import Optional

try:
    from ..orchestrator import AgentOrchestrator
    from .display import CLIDisplay
    from .session import CLISessionManager
    from .codebase import CLICodebaseAnalysis
    from .tasks import CLITaskExecution
    from .multiprovider import CLIMultiProvider
    from .smart_query import CLISmartQuery
    from .agent_manager import CLIAgentManager
    from .task_router_handler import CLITaskRouterHandler
    from .io_interface import CLIIOProtocol, ClickIO
except ImportError:
    # Allow running as script
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from orchestrator import AgentOrchestrator
    from cli.display import CLIDisplay
    from cli.session import CLISessionManager
    from cli.codebase import CLICodebaseAnalysis
    from cli.tasks import CLITaskExecution
    from cli.multiprovider import CLIMultiProvider
    from cli.smart_query import CLISmartQuery
    from cli.agent_manager import CLIAgentManager
    from cli.task_router_handler import CLITaskRouterHandler
    from cli.io_interface import CLIIOProtocol, ClickIO


class CLI:
    """Interactive CLI for the LLM Agent Team."""

    def __init__(
        self,
        brain: Optional[str] = None,
        auto_explore: bool = False,
        context_aware: bool = True,
        verbose_selection: bool = False,
        show_provider_status: bool = False,
        io: Optional[CLIIOProtocol] = None
    ):
        """Initialize CLI with orchestrator and component handlers."""
        if io is None:
            io = ClickIO()
        self.io = io

        io.secho("Initializing LLM Agent Team...", fg="cyan")

        # Show verbose selection info if requested
        if verbose_selection:
            io.secho("Verbose provider selection enabled", fg="yellow")

        self.orchestrator = AgentOrchestrator(
            orchestrator_provider=brain,
            auto_explore=auto_explore,
            context_aware=context_aware,
            verbose_selection=verbose_selection,
            show_provider_status=show_provider_status
        )
        self.session_start = datetime.now()
        self.smart_mode = False  # Smart query mode (uses tools for research)
        self.multiline_mode = True  # Multiline input mode (enabled by default)
        self.auto_route_mode = True  # Task-type aware routing (auto-select execution strategy)
        self.conversation_history = []  # Store conversation for session persistence
        self.auto_save = True  # Auto-save session on exit (can be toggled)

        # Task tracking state
        self.active_plan = []  # List of plan steps
        self.current_task_index = 0  # Current task being worked on
        self.plan_active = False  # Whether we're actively tracking a plan
        self.auto_execute_tasks = True  # Auto-execute tasks using TaskRouter (now enabled)

        # Initialize component handlers
        self.display = CLIDisplay(self.orchestrator, self.session_start)
        self.session_mgr = CLISessionManager(self.orchestrator)
        self.codebase = CLICodebaseAnalysis(self.orchestrator)
        self.tasks = CLITaskExecution(self.orchestrator)
        self.multiprovider = CLIMultiProvider(self.orchestrator)
        self.smart = CLISmartQuery(self.orchestrator)
        self.agent_mgr = CLIAgentManager(self.orchestrator)
        self.task_router = CLITaskRouterHandler(self.orchestrator)

        # Display initialization info (unless show_provider_status already did)
        if not show_provider_status:
            io.echo(f"Brain: {io.style(self.orchestrator.brain, fg='green', bold=True)}")
            providers_list = ', '.join(self.orchestrator.providers.list_available())
            io.echo(f"Available providers: {io.style(providers_list, fg='cyan')}")

        # Show context status
        if self.orchestrator.context.is_explored():
            io.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif context_aware:
            io.secho("Context: Not explored (use /context to explore)", fg="yellow")

        # Auto-detect and offer to load previous session
        self._check_and_offer_session_restore(io=io)

        io.echo()

    def _read_multiline_input(self, prompt_text: str = "... ", io: Optional[CLIIOProtocol] = None) -> str:
        """
        Read multiline input from user until they enter a blank line or 'END'.

        Returns:
            The complete multiline string.
        """
        if io is None:
            io = self.io

        io.secho("Enter your multiline input (blank line or 'END' to finish):", fg="cyan")
        lines = []

        while True:
            try:
                line = io.prompt(prompt_text, default="", show_default=False)

                # Check for termination
                if line.strip() == "" or line.strip().upper() == "END":
                    break

                lines.append(line)
            except Exception:
                io.echo("\nMultiline input cancelled.")
                return ""

        return "\n".join(lines)

    def _needs_tool_support(self, user_input: str) -> bool:
        """
        Detect if the user query needs tool support (web fetch, package lookup, codebase exploration, etc.)

        This allows auto-enabling tool use for research queries even when auto_route_mode is OFF.
        """
        import re
        lower_input = user_input.lower()

        # Web fetching patterns
        web_patterns = [
            r'\bfetch\b.*\b(docs?|documentation|api|website|url|page)\b',
            r'\b(get|retrieve|download|pull)\b.*\b(from|the)\b.*\b(web|url|site|docs?)\b',
            r'\bcheck\b.*\b(package|npm|pypi|github|version)\b',
            r'\blook\s*up\b.*\b(package|library|module|dependency)\b',
            r'\bwhat\s+(is|are)\s+the\s+(latest|current|newest)\b.*\b(version|release)\b',
            r'\b(pypi|npm|github)\b.*\b(info|details|package)\b',
            r'\bfrom\s+(the\s+)?(website|web|url|docs)\b',
            r'\b(scikit|sklearn|react|django|flask|express|numpy|pandas)\b.*\b(docs?|documentation|api)\b',
        ]

        for pattern in web_patterns:
            if re.search(pattern, lower_input):
                return True

        # Direct URL mention
        if re.search(r'https?://', user_input):
            return True

        # Package registry keywords with action verbs
        package_keywords = ['pypi', 'npm', 'github.com', 'registry']
        action_keywords = ['fetch', 'get', 'check', 'look', 'find', 'show', 'what']

        has_package = any(kw in lower_input for kw in package_keywords)
        has_action = any(kw in lower_input for kw in action_keywords)

        if has_package and has_action:
            return True

        # Codebase exploration patterns - questions about the code
        codebase_patterns = [
            # File-specific questions
            r'\b(does|do|is|are|has|have|where)\b.*\b(file|directory|folder|code|class|function|method)\b',
            r'\b(file|directory|folder)\b.*\b(contain|have|include|exist)\b',
            r'\bwhat\b.*\b(in|inside)\b.*\b(file|directory|folder|codebase|project)\b',
            r'\bshow\s+(me\s+)?(the\s+)?(file|code|function|class|directory)\b',
            r'\bread\b.*\b(file|code)\b',
            r'\blist\b.*\b(files?|directories?|folders?)\b',
            # Structure questions
            r'\b(structure|architecture|layout|organization)\b.*\b(of|in)\b.*\b(project|codebase|code)\b',
            r'\bhow\s+(is|are)\b.*\b(organized|structured|laid out)\b',
            # Content questions
            r'\b(does|do)\b.*\b(have|contain|include|use|import)\b',
            r'\bwhere\s+(is|are|does|do)\b',
            r'\bfind\b.*\b(in|inside|within)\b.*\b(code|project|codebase)\b',
            # Specific file extensions/names
            r'\b\w+\.(js|py|ts|tsx|jsx|java|cpp|c|h|rs|go|rb|php|css|html|json|yaml|yml|md|txt)\b',
        ]

        for pattern in codebase_patterns:
            if re.search(pattern, lower_input):
                return True

        # File path patterns (e.g., "frontend/app.js", "src/main.py")
        if re.search(r'\b\w+/\w+', user_input):  # path-like pattern
            return True

        return False

    def _show_current_task(self, io: Optional[CLIIOProtocol] = None):
        """Display the current task being worked on."""
        if io is None:
            io = self.io

        if not self.plan_active or not self.active_plan:
            return

        total = len(self.active_plan)
        current = self.current_task_index + 1

        io.secho("=" * 60, fg="cyan")
        io.secho(f"[{current}/{total}] ", fg="cyan", bold=True, nl=False)

        task = self.active_plan[self.current_task_index]
        if isinstance(task, dict):
            io.secho(task.get('step', task.get('description', 'Task')), bold=True)
            if 'description' in task and 'step' in task:
                io.echo(f"    {task['description']}")
        else:
            io.secho(str(task), bold=True)

        io.secho("=" * 60, fg="cyan")
        io.echo()

    def _prompt_task_progression(self, io: Optional[CLIIOProtocol] = None) -> bool:
        """
        Prompt user for next action after completing work.
        Returns True to continue loop, False if plan is finished.
        """
        if io is None:
            io = self.io

        if not self.plan_active:
            return True

        # Skip prompts if not in interactive mode
        if not sys.stdin.isatty():
            io.secho("Non-interactive mode: ending plan execution.", fg="yellow")
            self.plan_active = False
            return True

        io.echo()
        io.secho("What next?", fg="cyan", bold=True)
        io.echo("  1. Mark complete & continue")
        io.echo("  2. Stay on this task")
        io.echo("  3. Skip this task")
        io.echo("  4. Finish planning session")
        io.echo()

        try:
            choice = io.prompt("Choice", default="1", show_default=True).strip()
        except (EOFError, Exception):
            # Non-interactive or cancelled - end plan
            io.secho("\nEnding planning session...", fg="yellow")
            self.plan_active = False
            return True

        if choice == "1":
            # Mark complete and advance
            task = self.active_plan[self.current_task_index]
            task_name = task.get('step', str(task)) if isinstance(task, dict) else str(task)
            io.secho(f"[DONE] Task {self.current_task_index + 1} complete", fg="green", bold=True)
            io.echo()

            self.current_task_index += 1
            if self.current_task_index >= len(self.active_plan):
                io.secho("All tasks complete!", fg="green", bold=True)
                self._show_plan_summary(io=io)
                self.plan_active = False
                return True

            self._show_current_task(io=io)
            # Auto-execute the next task (if enabled)
            if self.auto_execute_tasks:
                self._execute_current_task(io=io)

        elif choice == "2":
            # Stay on current task
            io.secho("Continuing with current task...", fg="yellow")
            io.echo()

        elif choice == "3":
            # Skip task
            io.secho(f"Skipped task {self.current_task_index + 1}", fg="yellow")
            io.echo()

            self.current_task_index += 1
            if self.current_task_index >= len(self.active_plan):
                io.secho("Plan complete (some tasks skipped)", fg="yellow", bold=True)
                self._show_plan_summary(io=io)
                self.plan_active = False
                return True

            self._show_current_task(io=io)
            # Auto-execute the next task (if enabled)
            if self.auto_execute_tasks:
                self._execute_current_task(io=io)

        elif choice == "4":
            # End planning session
            io.secho("Ending planning session...", fg="yellow")
            self._show_plan_summary(io=io)
            self.plan_active = False

        return True

    def _check_and_offer_session_restore(self, io: Optional[CLIIOProtocol] = None):
        """Check for existing session and offer to restore it automatically."""
        if io is None:
            io = self.io

        # Skip session restore if not in interactive mode
        if not sys.stdin.isatty():
            return

        session_info = self.orchestrator.session_manager.get_session_info()

        if not session_info.get('exists', False):
            return

        if 'error' in session_info:
            return

        # Show session info
        io.secho("\nPrevious session detected:", fg="yellow", bold=True)
        io.echo(f"  Saved: {session_info.get('saved_at', 'unknown')}")
        io.echo(f"  Files cached: {session_info.get('file_count', 0)}")
        io.echo(f"  Searches: {session_info.get('search_count', 0)}")
        io.echo(f"  Discoveries: {session_info.get('discovery_count', 0)}")
        io.echo(f"  Tasks: {session_info.get('task_count', 0)}")

        if session_info.get('has_conversation', False):
            io.echo(f"  Has conversation history: Yes")

        # Offer to restore
        try:
            if io.confirm("Restore previous session?", default=True):
                result = self.orchestrator.load_session()
                if result['status'] == 'loaded':
                    io.secho("Session restored successfully!", fg="green")
                    io.echo(f"  Files: {result['files_restored']}")
                    io.echo(f"  Searches: {result['searches_restored']}")
                    io.echo(f"  Git ops: {result['git_ops_restored']}")
                    io.echo(f"  Discoveries: {result['discoveries_restored']}")

                    # Restore conversation history
                    conversation = result.get('conversation_history', [])
                    if conversation:
                        self.conversation_history = conversation
                        io.echo(f"  Conversation: {len(conversation)} messages")
                else:
                    io.secho(f"Could not restore session: {result.get('message', 'unknown error')}", fg="red")
            else:
                io.secho("Starting fresh session.", fg="yellow")
        except (EOFError, Exception):
            # Non-interactive environment or user cancelled
            io.secho("Starting fresh session.", fg="yellow")

    def _show_plan_summary(self, io: Optional[CLIIOProtocol] = None):
        """Show summary of plan progress."""
        if io is None:
            io = self.io

        if not self.active_plan:
            return

        total = len(self.active_plan)
        completed = self.current_task_index

        io.echo()
        io.secho("Plan Summary:", fg="cyan", bold=True)
        io.echo(f"  Completed: {completed}/{total} tasks")

        # Progress bar
        progress = int((completed / total) * 20)
        bar = "#" * progress + "-" * (20 - progress)
        percentage = int((completed / total) * 100)
        io.echo(f"  Progress: [{bar}] {percentage}%")
        io.echo()

    def _execute_current_task(self, io: Optional[CLIIOProtocol] = None):
        """Automatically execute the current task using intelligent routing."""
        if io is None:
            io = self.io

        if not self.plan_active or not self.active_plan:
            return

        task = self.active_plan[self.current_task_index]

        # Build task description
        if isinstance(task, dict):
            task_name = task.get('step', 'Task')
            task_desc = task.get('description', task_name)
            full_task = f"{task_name}: {task_desc}"
        else:
            full_task = str(task)

        io.secho(f"\nAuto-executing task...", fg="cyan", bold=True)

        # Use TaskRouter to intelligently route the task
        # This automatically selects the right strategy:
        # - DIRECT_COMMAND: Runs immediately (no LLM)
        # - RESEARCH: Fast LLM call (no approval)
        # - CODE_GENERATION: Full agent with approval
        # - CONVERSATION: Simple response
        try:
            result = self.task_router.router.route(full_task)

            if result.success:
                io.secho("[OK] Task executed successfully", fg="green")
                if result.output:
                    io.echo(result.output[:1000])  # Truncate long output
            else:
                io.secho(f"[FAIL] Task failed: {result.error}", fg="red")

            # Show execution metadata
            if "classification" in result.metadata:
                cls_info = result.metadata["classification"]
                io.secho(
                    f"  [Strategy: {cls_info.get('type', 'unknown')} | "
                    f"Provider: {cls_info.get('resolved_provider', 'none')}]",
                    fg="bright_black"
                )
        except Exception as e:
            io.secho(f"Error executing task: {e}", fg="red")
            # Fallback to agent manager if TaskRouter fails
            io.secho("Falling back to agent manager...", fg="yellow")
            self.agent_mgr.run_agent(full_task, io=io)

        # After task completes, prompt for next action
        self._prompt_task_progression(io=io)

    def interactive_mode(self):
        """Run interactive chat mode."""
        # Check if running in interactive environment
        if not sys.stdin.isatty():
            click.secho("Error: Interactive mode requires a TTY (terminal).", fg="red", bold=True)
            click.echo("Cannot run interactive mode without stdin.")
            click.echo("Use one-shot commands instead (e.g., llm-team query 'your question')")
            return

        click.secho("=" * 60, fg="cyan")
        click.secho("LLM Agent Team - Interactive Mode", fg="cyan", bold=True)
        click.secho("=" * 60, fg="cyan")
        click.echo("Commands:")
        click.echo(f"  {click.style('/help', fg='yellow')}          - Show all commands")
        click.echo(f"  {click.style('/auto', fg='yellow')}          - Toggle auto-routing (task-aware execution)")
        click.echo(f"  {click.style('/plan', fg='yellow')} <task>   - Create a task plan")
        click.echo(f"  {click.style('/reason', fg='yellow')} <q>    - Reason about a question")
        click.echo(f"  {click.style('/agent', fg='yellow')} <task>  - Run code agent (with human approval)")
        click.echo(f"  {click.style('/smart', fg='yellow')} <q>     - Research-first query (uses tools)")
        click.echo(f"  {click.style('/context', fg='yellow')}       - Manage codebase context")
        click.echo(f"  {click.style('/autoexec', fg='yellow')}      - Toggle auto-execute for plan tasks")
        click.echo(f"  {click.style('/status', fg='yellow')}        - Show system status")
        click.echo(f"  {click.style('/quit', fg='yellow')}          - Exit the CLI")
        click.echo(f"  {click.style('(any text)', fg='bright_white')}     - Chat with current brain")
        click.secho("=" * 60, fg="cyan")

        # Show mode statuses
        if self.multiline_mode:
            click.secho("Multiline input: ON (end line with \\ to continue, /ml to toggle)", fg="green")
        else:
            click.secho("Multiline input: OFF (/ml to toggle)", fg="yellow")

        if self.auto_route_mode:
            click.secho("Auto-routing: ON (task-aware execution)", fg="green")
        else:
            click.secho("Auto-routing: OFF (/auto to enable)", fg="yellow")
        click.echo()

        while True:
            try:
                if self.multiline_mode:
                    # Multiline input mode - read until blank line or complete input
                    click.secho("You> ", fg="green", bold=True, nl=False)
                    lines = []
                    first_line = True
                    while True:
                        if first_line:
                            line = input()
                            first_line = False

                            # If first line is a command, process it immediately
                            if line.strip().startswith("/"):
                                lines.append(line)
                                break

                            # If line doesn't end with continuation marker (\), treat as complete
                            # This fixes the "press enter twice" bug
                            if not line.rstrip().endswith("\\"):
                                lines.append(line)
                                break
                            else:
                                # Remove the continuation marker and continue reading
                                lines.append(line.rstrip()[:-1])
                        else:
                            click.secho("... ", fg="green", nl=False)
                            line = input()

                            # Blank line terminates input
                            if line.strip() == "":
                                break

                            # Check for continuation marker
                            if line.rstrip().endswith("\\"):
                                lines.append(line.rstrip()[:-1])
                            else:
                                lines.append(line)
                                break

                    user_input = "\n".join(lines).strip()
                else:
                    # Single-line input mode
                    user_input = click.prompt(click.style("You", fg="green", bold=True), default="", show_default=False).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    if self._handle_command(user_input):
                        continue
                    else:
                        break

                # Regular chat
                self.conversation_history.append({
                    "role": "user",
                    "content": user_input
                })

                # Use auto-routing if enabled (task-aware execution)
                if self.auto_route_mode:
                    result = self.task_router.handle_auto_route(user_input)
                    # Store result as response for history
                    response_content = result.output if result.success else f"Error: {result.error}"
                    response = type('Response', (), {'content': response_content})()
                # Use smart mode if enabled
                elif self.smart_mode:
                    response = self.smart.smart_query(user_input)
                else:
                    # Check if this looks like a research task that needs tools
                    # (fetch, check package, lookup docs, etc.)
                    needs_tools = self._needs_tool_support(user_input)

                    if needs_tools:
                        # Use ResearchExecutor with tool support
                        click.secho("Using tools for research...", fg="cyan")
                        result = self.task_router.handle_auto_route(user_input)
                        response_content = result.output if result.success else f"Error: {result.error}"
                        response = type('Response', (), {'content': response_content})()

                        # Show tool usage info if available
                        if hasattr(result, 'metadata') and result.metadata:
                            tool_calls = result.metadata.get('tool_calls', [])
                            if tool_calls:
                                click.secho(f"  Tools used: {[tc['tool'] for tc in tool_calls]}", fg="cyan")

                        click.secho("Assistant: ", fg="blue", bold=True)
                        click.echo(response.content)

                        # Show execution metadata
                        provider_used = result.provider_used if hasattr(result, 'provider_used') else "unknown"
                        tokens = result.tokens_used if hasattr(result, 'tokens_used') else 0
                        exec_time = result.execution_time if hasattr(result, 'execution_time') else 0
                        click.secho(
                            f"[{provider_used} | {tokens} tokens | {exec_time*1000:.0f}ms]",
                            fg="cyan"
                        )
                    else:
                        click.secho("Assistant: ", fg="blue", bold=True, nl=False)

                        response = self.orchestrator.delegate(
                            self.orchestrator.brain,
                            user_input,
                            system_prompt="You are a helpful AI assistant. Be concise and informative."
                        )

                        click.echo(response.content)
                        click.secho(
                            f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                            fg="cyan"
                        )
                click.echo()

                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })

                # Prompt for task progression if plan is active
                if self.plan_active:
                    self._prompt_task_progression()

            except click.Abort:
                click.echo("\n\nInterrupted. Type /quit to exit.")
                continue
            except EOFError:
                # Handle EOF gracefully (e.g., when stdin is closed)
                click.echo("\n")
                click.secho("EOF received. Exiting...", fg="yellow")
                # Auto-save session on exit if enabled
                if self.auto_save:
                    try:
                        session_file = self.orchestrator.save_session(self.conversation_history)
                        click.secho(f"Session saved to: {session_file}", fg="green")
                    except Exception as save_error:
                        click.secho(f"Warning: Could not save session: {save_error}", fg="yellow")
                self.display.show_usage()
                click.secho("Goodbye!", fg="cyan", bold=True)
                break
            except KeyboardInterrupt:
                click.echo("\n\nInterrupted. Type /quit to exit.")
                continue
            except Exception as e:
                click.secho(f"\nError: {e}", fg="red")
                click.echo("Type /help for available commands.\n")

    def _handle_command(self, command: str, io: Optional[CLIIOProtocol] = None) -> bool:
        """
        Handle slash commands. Returns True to continue loop, False to exit.
        """
        if io is None:
            io = self.io

        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ["/quit", "/exit", "/q"]:
            # Auto-save session on exit if enabled
            if self.auto_save:
                try:
                    session_file = self.orchestrator.save_session(self.conversation_history)
                    io.secho(f"\nSession saved to: {session_file}", fg="green")
                    io.echo(f"  Conversation: {len(self.conversation_history)} messages")
                    io.echo("Use 'llm-team --resume' to continue later.")
                except Exception as e:
                    io.secho(f"Warning: Could not save session: {e}", fg="yellow")
            else:
                io.secho("\nSession not saved (auto-save disabled).", fg="yellow")
                io.echo("Use '/session save' to manually save before quitting.")

            self.display.show_usage()
            io.secho("\nGoodbye!", fg="cyan", bold=True)
            return False

        elif cmd == "/help":
            self.display.show_help()

        elif cmd == "/status":
            self.display.show_status()

        elif cmd == "/autoexec":
            # Toggle auto-execute for plan tasks
            self.auto_execute_tasks = not self.auto_execute_tasks
            status = io.style("ENABLED", fg="green") if self.auto_execute_tasks else io.style("DISABLED", fg="red")
            io.echo(f"Auto-execute tasks: {status}")
            if self.auto_execute_tasks:
                io.echo("  Tasks in plans will be automatically executed using intelligent routing")
                io.echo("  (DIRECT_COMMAND -> immediate, RESEARCH -> fast LLM, CODE_GEN -> agent with approval)")
            else:
                io.echo("  Tasks in plans will wait for manual execution")

        elif cmd == "/providers":
            self.display.list_providers()

        elif cmd == "/brain":
            self.display.switch_brain(args)

        elif cmd == "/usage":
            self.display.show_usage()

        elif cmd == "/plan":
            if not args:
                io.echo("Usage: /plan <task description>")
            else:
                steps = self.tasks.plan_task(args)
                if steps and len(steps) > 0:
                    # Prompt to start tracking
                    if io.confirm("Start working on this plan?", default=True):
                        self.active_plan = steps
                        self.current_task_index = 0
                        self.plan_active = True
                        io.echo()
                        self._show_current_task(io=io)
                        # Auto-execute the first task (if enabled)
                        if self.auto_execute_tasks:
                            self._execute_current_task(io=io)

        elif cmd == "/reason":
            if not args:
                io.echo("Usage: /reason <question>")
            else:
                self.tasks.reason(args)

        elif cmd == "/synthesize":
            self.multiprovider.synthesize_mode(io=io)

        elif cmd == "/delegate":
            self.multiprovider.delegate_mode(args, io=io)

        elif cmd == "/clear":
            self.conversation_history.clear()
            io.secho("Conversation history cleared.", fg="green")

        elif cmd == "/models":
            self.display.list_models(args)

        elif cmd == "/explore":
            self.codebase.explore_codebase(args, io=io)

        elif cmd == "/context":
            self.session_mgr.manage_context(args, io=io)

        elif cmd == "/agent":
            if not args:
                io.echo("Usage: /agent <task description>")
            else:
                self.agent_mgr.run_agent(args, io=io)
                # Prompt for task progression if plan is active
                if self.plan_active:
                    self._prompt_task_progression(io=io)

        elif cmd == "/smart":
            if not args:
                # Show smart mode status
                status = io.style("ON", fg="green") if self.smart_mode else io.style("OFF", fg="yellow")
                io.echo(f"Smart query mode: {status}")
                io.echo("Usage: /smart <query> or /smart toggle")
            elif args.lower() == "toggle":
                self.smart_mode = not self.smart_mode
                status = "enabled" if self.smart_mode else "disabled"
                io.secho(f"Smart query mode {status}.", fg="green" if self.smart_mode else "yellow")
                if self.smart_mode:
                    io.echo("All queries will now use tools for research (higher quota usage).")
            else:
                self.smart.smart_query(args)

        elif cmd == "/cache":
            self.session_mgr.manage_cache(args, io=io)

        elif cmd == "/session":
            result = self.session_mgr.manage_session(args, self.conversation_history, self.auto_save, io=io)
            # Update state if changed
            if result.get('conversation_history') is not None:
                self.conversation_history = result['conversation_history']
            if result.get('auto_save') is not None:
                self.auto_save = result['auto_save']

        elif cmd == "/limits":
            self.session_mgr.show_rate_limits(args, io=io)

        elif cmd == "/tasks":
            if not self.plan_active or not self.active_plan:
                io.secho("No active plan. Use /plan <task> to create one.", fg="yellow")
            else:
                io.secho("\nCurrent Plan:", fg="cyan", bold=True)
                io.secho("-" * 50, fg="cyan")
                for i, task in enumerate(self.active_plan):
                    if i < self.current_task_index:
                        # Completed
                        status = io.style("[x]", fg="green")
                    elif i == self.current_task_index:
                        # Current
                        status = io.style("->", fg="yellow", bold=True)
                    else:
                        # Pending
                        status = io.style("o", fg="white")

                    if isinstance(task, dict):
                        task_name = task.get('step', task.get('description', 'Task'))
                    else:
                        task_name = str(task)

                    io.echo(f"  {status} {i+1}. {task_name}")
                io.echo()
                self._show_plan_summary(io=io)

        elif cmd in ["/paste", "/ml", "/multiline"]:
            # Toggle multiline input mode
            self.multiline_mode = not self.multiline_mode
            if self.multiline_mode:
                io.secho("Multiline input mode: ON", fg="green", bold=True)
                io.echo("  - End a line with \\ to continue on next line")
                io.echo("  - Press Enter normally to send (no double-enter needed)")
                io.echo("  - Commands still work on the first line")
            else:
                io.secho("Multiline input mode: OFF", fg="yellow", bold=True)
                io.echo("  - Single line input (press Enter to send)")
                io.echo("  - Each line is processed separately")

        elif cmd in ["/auto", "/route", "/autoroute"]:
            if not args:
                # Toggle auto-routing mode
                self.auto_route_mode = not self.auto_route_mode
                if self.auto_route_mode:
                    io.secho("Auto-routing mode: ON", fg="green", bold=True)
                    io.echo("  Tasks are automatically classified and routed:")
                    io.echo("  - Direct commands (pip, git) -> Shell execution")
                    io.echo("  - Code generation -> Full agent loop with planning")
                    io.echo("  - Research queries -> Fast provider (Cerebras)")
                    io.echo("  - Simple chat -> Instant responses")
                else:
                    io.secho("Auto-routing mode: OFF", fg="yellow", bold=True)
                    io.echo("  All input goes to default chat mode.")
            elif args.lower() == "status":
                self.task_router.handle_route_status()
            elif args.lower() == "history":
                self.task_router.handle_route_history()
            else:
                io.echo("Usage: /auto [status|history]")
                io.echo("  /auto         - Toggle auto-routing mode")
                io.echo("  /auto status  - Show routing metrics")
                io.echo("  /auto history - Show routing history")

        elif cmd == "/classify":
            if not args:
                io.echo("Usage: /classify <task description>")
                io.echo("  Preview how a task would be classified without executing.")
            else:
                self.task_router.handle_classify_only(args)

        else:
            io.secho(f"Unknown command: {cmd}", fg="yellow")
            io.echo("Type /help for available commands.")

        io.echo()
        return True
