"""
Core CLI functionality.
Main entry point and command routing for the LLM Agent Team CLI.
"""

import click
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
        self.conversation_history = []  # Store conversation for session persistence
        self.auto_save = True  # Auto-save session on exit (can be toggled)

        # Initialize component handlers
        self.display = CLIDisplay(self.orchestrator, self.session_start)
        self.session_mgr = CLISessionManager(self.orchestrator)
        self.codebase = CLICodebaseAnalysis(self.orchestrator)
        self.tasks = CLITaskExecution(self.orchestrator)
        self.multiprovider = CLIMultiProvider(self.orchestrator)
        self.smart = CLISmartQuery(self.orchestrator)
        self.agent_mgr = CLIAgentManager(self.orchestrator)

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

    def interactive_mode(self):
        """Run interactive chat mode."""
        click.secho("=" * 60, fg="cyan")
        click.secho("LLM Agent Team - Interactive Mode", fg="cyan", bold=True)
        click.secho("=" * 60, fg="cyan")
        click.echo("Commands:")
        click.echo(f"  {click.style('/help', fg='yellow')}          - Show all commands")
        click.echo(f"  {click.style('/plan', fg='yellow')} <task>   - Create a task plan")
        click.echo(f"  {click.style('/reason', fg='yellow')} <q>    - Reason about a question")
        click.echo(f"  {click.style('/agent', fg='yellow')} <task>  - Run code agent (with human approval)")
        click.echo(f"  {click.style('/smart', fg='yellow')} <q>     - Research-first query (uses tools)")
        click.echo(f"  {click.style('/context', fg='yellow')}       - Manage codebase context")
        click.echo(f"  {click.style('/status', fg='yellow')}        - Show system status")
        click.echo(f"  {click.style('/quit', fg='yellow')}          - Exit the CLI")
        click.echo(f"  {click.style('(any text)', fg='bright_white')}     - Chat with current brain")
        click.secho("=" * 60, fg="cyan")
        click.echo()

        while True:
            try:
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

                # Use smart mode if enabled
                if self.smart_mode:
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
                self.tasks.plan_task(args)

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

        else:
            click.secho(f"Unknown command: {cmd}", fg="yellow")
            click.echo("Type /help for available commands.")

        click.echo()
        return True
