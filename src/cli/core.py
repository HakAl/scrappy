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


class CLI:
    """Interactive CLI for the LLM Agent Team."""

    def __init__(self, brain: Optional[str] = None, auto_explore: bool = False, context_aware: bool = True):
        """Initialize CLI with orchestrator and component handlers."""
        click.secho("Initializing LLM Agent Team...", fg="cyan")
        self.orchestrator = AgentOrchestrator(
            orchestrator_provider=brain,
            auto_explore=auto_explore,
            context_aware=context_aware
        )
        self.session_start = datetime.now()
        self.smart_mode = False  # Smart query mode (uses tools for research)
        self.multiline_mode = True  # Multiline input mode (enabled by default)
        self.auto_route_mode = False  # Task-type aware routing (auto-select execution strategy)
        self.conversation_history = []  # Store conversation for session persistence
        self.auto_save = True  # Auto-save session on exit (can be toggled)

        # Task tracking state
        self.active_plan = []  # List of plan steps
        self.current_task_index = 0  # Current task being worked on
        self.plan_active = False  # Whether we're actively tracking a plan
        self.auto_execute_tasks = False  # Feature flag: auto-execute tasks (disabled for now)

        # Initialize component handlers
        self.display = CLIDisplay(self.orchestrator, self.session_start)
        self.session_mgr = CLISessionManager(self.orchestrator)
        self.codebase = CLICodebaseAnalysis(self.orchestrator)
        self.tasks = CLITaskExecution(self.orchestrator)
        self.multiprovider = CLIMultiProvider(self.orchestrator)
        self.smart = CLISmartQuery(self.orchestrator)
        self.agent_mgr = CLIAgentManager(self.orchestrator)
        self.task_router = CLITaskRouterHandler(self.orchestrator)

        # Display initialization info
        click.echo(f"Brain: {click.style(self.orchestrator.brain, fg='green', bold=True)}")
        providers_list = ', '.join(self.orchestrator.providers.list_available())
        click.echo(f"Available providers: {click.style(providers_list, fg='cyan')}")

        # Show context status
        if self.orchestrator.context.is_explored():
            click.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif context_aware:
            click.secho("Context: Not explored (use /context to explore)", fg="yellow")

        click.echo()

    def _read_multiline_input(self, prompt_text: str = "... ") -> str:
        """
        Read multiline input from user until they enter a blank line or 'END'.

        Returns:
            The complete multiline string.
        """
        click.secho("Enter your multiline input (blank line or 'END' to finish):", fg="cyan")
        lines = []

        while True:
            try:
                line = click.prompt(prompt_text, default="", show_default=False, prompt_suffix="")

                # Check for termination
                if line.strip() == "" or line.strip().upper() == "END":
                    break

                lines.append(line)
            except click.Abort:
                click.echo("\nMultiline input cancelled.")
                return ""

        return "\n".join(lines)

    def _show_current_task(self):
        """Display the current task being worked on."""
        if not self.plan_active or not self.active_plan:
            return

        total = len(self.active_plan)
        current = self.current_task_index + 1

        click.secho("━" * 60, fg="cyan")
        click.secho(f"[{current}/{total}] ", fg="cyan", bold=True, nl=False)

        task = self.active_plan[self.current_task_index]
        if isinstance(task, dict):
            click.secho(task.get('step', task.get('description', 'Task')), bold=True)
            if 'description' in task and 'step' in task:
                click.echo(f"    {task['description']}")
        else:
            click.secho(str(task), bold=True)

        click.secho("━" * 60, fg="cyan")
        click.echo()

    def _prompt_task_progression(self) -> bool:
        """
        Prompt user for next action after completing work.
        Returns True to continue loop, False if plan is finished.
        """
        if not self.plan_active:
            return True

        click.echo()
        click.secho("What next?", fg="cyan", bold=True)
        click.echo("  1. Mark complete & continue")
        click.echo("  2. Stay on this task")
        click.echo("  3. Skip this task")
        click.echo("  4. Finish planning session")
        click.echo()

        choice = click.prompt("Choice", default="1", show_default=True).strip()

        if choice == "1":
            # Mark complete and advance
            task = self.active_plan[self.current_task_index]
            task_name = task.get('step', str(task)) if isinstance(task, dict) else str(task)
            click.secho(f"✓ Task {self.current_task_index + 1} complete", fg="green", bold=True)
            click.echo()

            self.current_task_index += 1
            if self.current_task_index >= len(self.active_plan):
                click.secho("🎉 All tasks complete!", fg="green", bold=True)
                self._show_plan_summary()
                self.plan_active = False
                return True

            self._show_current_task()
            # Auto-execute the next task (if enabled)
            if self.auto_execute_tasks:
                self._execute_current_task()

        elif choice == "2":
            # Stay on current task
            click.secho("Continuing with current task...", fg="yellow")
            click.echo()

        elif choice == "3":
            # Skip task
            click.secho(f"⏭ Skipped task {self.current_task_index + 1}", fg="yellow")
            click.echo()

            self.current_task_index += 1
            if self.current_task_index >= len(self.active_plan):
                click.secho("Plan complete (some tasks skipped)", fg="yellow", bold=True)
                self._show_plan_summary()
                self.plan_active = False
                return True

            self._show_current_task()
            # Auto-execute the next task (if enabled)
            if self.auto_execute_tasks:
                self._execute_current_task()

        elif choice == "4":
            # End planning session
            click.secho("Ending planning session...", fg="yellow")
            self._show_plan_summary()
            self.plan_active = False

        return True

    def _show_plan_summary(self):
        """Show summary of plan progress."""
        if not self.active_plan:
            return

        total = len(self.active_plan)
        completed = self.current_task_index

        click.echo()
        click.secho("Plan Summary:", fg="cyan", bold=True)
        click.echo(f"  Completed: {completed}/{total} tasks")

        # Progress bar
        progress = int((completed / total) * 20)
        bar = "█" * progress + "░" * (20 - progress)
        percentage = int((completed / total) * 100)
        click.echo(f"  Progress: [{bar}] {percentage}%")
        click.echo()

    def _execute_current_task(self):
        """Automatically execute the current task using the code agent."""
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

        click.secho(f"\nExecuting task...", fg="cyan", bold=True)

        # Run the agent on this task
        self.agent_mgr.run_agent(full_task)

        # After agent completes, prompt for next action
        self._prompt_task_progression()

    def interactive_mode(self):
        """Run interactive chat mode."""
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
        click.echo(f"  {click.style('/status', fg='yellow')}        - Show system status")
        click.echo(f"  {click.style('/quit', fg='yellow')}          - Exit the CLI")
        click.echo(f"  {click.style('(any text)', fg='bright_white')}     - Chat with current brain")
        click.secho("=" * 60, fg="cyan")

        # Show mode statuses
        if self.multiline_mode:
            click.secho("Multiline input: ON (blank line to send, /ml to toggle)", fg="green")
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
                    # Multiline input mode - read until blank line
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
                        else:
                            click.secho("... ", fg="green", nl=False)
                            line = input()

                        # Blank line terminates input
                        if line.strip() == "":
                            break

                        lines.append(line)

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
            except Exception as e:
                click.secho(f"\nError: {e}", fg="red")
                click.echo("Type /help for available commands.\n")

    def _handle_command(self, command: str) -> bool:
        """
        Handle slash commands. Returns True to continue loop, False to exit.
        """
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ["/quit", "/exit", "/q"]:
            # Auto-save session on exit if enabled
            if self.auto_save:
                try:
                    session_file = self.orchestrator.save_session(self.conversation_history)
                    click.secho(f"\nSession saved to: {session_file}", fg="green")
                    click.echo(f"  Conversation: {len(self.conversation_history)} messages")
                    click.echo("Use 'llm-team --resume' to continue later.")
                except Exception as e:
                    click.secho(f"Warning: Could not save session: {e}", fg="yellow")
            else:
                click.secho("\nSession not saved (auto-save disabled).", fg="yellow")
                click.echo("Use '/session save' to manually save before quitting.")

            self.display.show_usage()
            click.secho("\nGoodbye!", fg="cyan", bold=True)
            return False

        elif cmd == "/help":
            self.display.show_help()

        elif cmd == "/status":
            self.display.show_status()

        elif cmd == "/providers":
            self.display.list_providers()

        elif cmd == "/brain":
            self.display.switch_brain(args)

        elif cmd == "/usage":
            self.display.show_usage()

        elif cmd == "/plan":
            if not args:
                click.echo("Usage: /plan <task description>")
            else:
                steps = self.tasks.plan_task(args)
                if steps and len(steps) > 0:
                    # Prompt to start tracking
                    if click.confirm("Start working on this plan?", default=True):
                        self.active_plan = steps
                        self.current_task_index = 0
                        self.plan_active = True
                        click.echo()
                        self._show_current_task()
                        # Auto-execute the first task (if enabled)
                        if self.auto_execute_tasks:
                            self._execute_current_task()

        elif cmd == "/reason":
            if not args:
                click.echo("Usage: /reason <question>")
            else:
                self.tasks.reason(args)

        elif cmd == "/synthesize":
            self.multiprovider.synthesize_mode()

        elif cmd == "/delegate":
            self.multiprovider.delegate_mode(args)

        elif cmd == "/clear":
            self.conversation_history.clear()
            click.secho("Conversation history cleared.", fg="green")

        elif cmd == "/models":
            self.display.list_models(args)

        elif cmd == "/explore":
            self.codebase.explore_codebase(args)

        elif cmd == "/context":
            self.session_mgr.manage_context(args)

        elif cmd == "/agent":
            if not args:
                click.echo("Usage: /agent <task description>")
            else:
                self.agent_mgr.run_agent(args)
                # Prompt for task progression if plan is active
                if self.plan_active:
                    self._prompt_task_progression()

        elif cmd == "/smart":
            if not args:
                # Show smart mode status
                status = click.style("ON", fg="green") if self.smart_mode else click.style("OFF", fg="yellow")
                click.echo(f"Smart query mode: {status}")
                click.echo("Usage: /smart <query> or /smart toggle")
            elif args.lower() == "toggle":
                self.smart_mode = not self.smart_mode
                status = "enabled" if self.smart_mode else "disabled"
                click.secho(f"Smart query mode {status}.", fg="green" if self.smart_mode else "yellow")
                if self.smart_mode:
                    click.echo("All queries will now use tools for research (higher quota usage).")
            else:
                self.smart.smart_query(args)

        elif cmd == "/cache":
            self.session_mgr.manage_cache(args)

        elif cmd == "/session":
            result = self.session_mgr.manage_session(args, self.conversation_history, self.auto_save)
            # Update state if changed
            if result.get('conversation_history') is not None:
                self.conversation_history = result['conversation_history']
            if result.get('auto_save') is not None:
                self.auto_save = result['auto_save']

        elif cmd == "/limits":
            self.session_mgr.show_rate_limits(args)

        elif cmd == "/tasks":
            if not self.plan_active or not self.active_plan:
                click.secho("No active plan. Use /plan <task> to create one.", fg="yellow")
            else:
                click.secho("\nCurrent Plan:", fg="cyan", bold=True)
                click.secho("-" * 50, fg="cyan")
                for i, task in enumerate(self.active_plan):
                    if i < self.current_task_index:
                        # Completed
                        status = click.style("✓", fg="green")
                    elif i == self.current_task_index:
                        # Current
                        status = click.style("→", fg="yellow", bold=True)
                    else:
                        # Pending
                        status = click.style("○", fg="white")

                    if isinstance(task, dict):
                        task_name = task.get('step', task.get('description', 'Task'))
                    else:
                        task_name = str(task)

                    click.echo(f"  {status} {i+1}. {task_name}")
                click.echo()
                self._show_plan_summary()

        elif cmd in ["/paste", "/ml", "/multiline"]:
            # Toggle multiline input mode
            self.multiline_mode = not self.multiline_mode
            if self.multiline_mode:
                click.secho("Multiline input mode: ON", fg="green", bold=True)
                click.echo("  - Type your message across multiple lines")
                click.echo("  - Press Enter twice (blank line) to send")
                click.echo("  - Commands still work on the first line")
            else:
                click.secho("Multiline input mode: OFF", fg="yellow", bold=True)
                click.echo("  - Single line input (press Enter to send)")
                click.echo("  - Each line is processed separately")

        elif cmd in ["/auto", "/route", "/autoroute"]:
            if not args:
                # Toggle auto-routing mode
                self.auto_route_mode = not self.auto_route_mode
                if self.auto_route_mode:
                    click.secho("Auto-routing mode: ON", fg="green", bold=True)
                    click.echo("  Tasks are automatically classified and routed:")
                    click.echo("  - Direct commands (pip, git) → Shell execution")
                    click.echo("  - Code generation → Full agent loop with planning")
                    click.echo("  - Research queries → Fast provider (Cerebras)")
                    click.echo("  - Simple chat → Instant responses")
                else:
                    click.secho("Auto-routing mode: OFF", fg="yellow", bold=True)
                    click.echo("  All input goes to default chat mode.")
            elif args.lower() == "status":
                self.task_router.handle_route_status()
            elif args.lower() == "history":
                self.task_router.handle_route_history()
            else:
                click.echo("Usage: /auto [status|history]")
                click.echo("  /auto         - Toggle auto-routing mode")
                click.echo("  /auto status  - Show routing metrics")
                click.echo("  /auto history - Show routing history")

        elif cmd == "/classify":
            if not args:
                click.echo("Usage: /classify <task description>")
                click.echo("  Preview how a task would be classified without executing.")
            else:
                self.task_router.handle_classify_only(args)

        else:
            click.secho(f"Unknown command: {cmd}", fg="yellow")
            click.echo("Type /help for available commands.")

        click.echo()
        return True
