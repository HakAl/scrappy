#!/usr/bin/env python3
"""
Click command handlers for the Scrappy CLI.
Provides the main entry point and subcommands.
"""

import click
import sys
import os
from datetime import datetime
from pathlib import Path

from ..orchestrator import AgentOrchestrator
from .utils.session_utils import restore_session_to_cli
from .utils.error_handler import format_error, get_error_suggestion
from .utils.dependency_check import check_agent_dependencies
from .validators import validate_path, validate_provider
from .exceptions import (
    CLIError,
    ValidationError,
    TaskExecutionError,
    FileOperationError,
)
from .logging import get_logger
from ..agent import CodeAgent, create_git_checkpoint
from .config_factory import get_config
from scrappy.infrastructure.output_mode import OutputModeContext
from .utils.cli_factory import create_cli_from_context

# Load environment variables from .env file (supplements, doesn't override existing env vars)
# Suppress dotenv warnings for malformed .env files - users may have syntax issues
import warnings
import logging
try:
    from dotenv import load_dotenv
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        logging.getLogger("dotenv.main").setLevel(logging.ERROR)
        load_dotenv(override=False)
except ImportError:
    pass  # python-dotenv not installed, skip


def create_orchestrator_for_command(ctx):
    """Create orchestrator for one-off commands (no CLI/Textual).

    Args:
        ctx: Click context

    Returns:
        Initialized AgentOrchestrator
    """

    orchestrator = AgentOrchestrator(
        context_aware=ctx.obj.get('context_aware', True),
        verbose_selection=ctx.obj.get('verbose_selection', False),
        enable_semantic_search=False  # Not needed for one-off commands
    )
    orchestrator.initialize(
        auto_register=True,
        orchestrator_provider=ctx.obj.get('brain'),
        auto_explore=ctx.obj.get('auto_explore', False)
    )
    return orchestrator


def display_command_error(e: Exception, operation: str) -> None:
    """Display a user-friendly error message for CLI commands.

    Args:
        e: The exception that occurred
        operation: Description of the operation that failed (e.g., "query", "plan")
    """
    error_msg = format_error(e)
    suggestion = get_error_suggestion(e, operation)

    click.secho(f"Error during {operation}: {error_msg}", fg="red")
    if suggestion:
        click.secho(f"Suggestion: {suggestion}", fg="yellow")


@click.group(invoke_without_command=True)
@click.option("--brain", "-b", default=None, help="Orchestrator brain provider (cerebras, groq, gemini)")
@click.option("--auto-explore", "-a", is_flag=True, help="Automatically explore codebase on startup")
@click.option("--no-context", is_flag=True, help="Disable context-aware prompts")
@click.option("--resume", "-r", is_flag=True, help="Resume from last saved session")
@click.option("--no-save", is_flag=True, help="Disable auto-save on exit")
@click.option("--show-providers", "-p", is_flag=True, help="Show detailed provider status on startup")
@click.option("--verbose-selection", "-v", is_flag=True, help="Show verbose provider selection logic")
@click.pass_context
def cli(ctx, brain, auto_explore, no_context, resume, no_save, show_providers, verbose_selection):
    """Scrappy CLI - Multi-provider orchestrator interface.

    Start interactive mode by running without arguments, or use subcommands
    for one-shot operations.

    Sessions are auto-saved on /quit by default. Use --resume to continue.

    Provider Selection:
      By default, the orchestrator auto-selects the brain based on availability.
      Priority: cerebras (14,400 RPD) > groq (7,000 RPD) > gemini (auto-fallback)

      Use --brain to override, --show-providers to see status, --verbose-selection for details.
    """
    ctx.ensure_object(dict)

    # Store preferences
    ctx.obj['brain'] = brain
    ctx.obj['auto_explore'] = auto_explore
    ctx.obj['context_aware'] = not no_context
    ctx.obj['resume'] = resume
    ctx.obj['auto_save'] = not no_save
    ctx.obj['show_providers'] = show_providers
    ctx.obj['verbose_selection'] = verbose_selection

    # Get theme from global config
    config = get_config()
    theme = config.theme

    # If no subcommand, start interactive mode with deferred initialization
    if ctx.invoked_subcommand is None:
        start_tui_deferred(ctx, theme, resume)


def start_tui_deferred(ctx, theme, resume: bool = False) -> None:
    """Start TUI immediately with deferred CLI initialization.

    Shows the TUI skeleton instantly while CLI/orchestrator loads in background.
    This provides sub-500ms startup time for the UI.

    The factory pattern ensures CLI creation happens in a background thread
    via @work(thread=True), preventing UI freezes from blocking I/O.

    Args:
        ctx: Click context with configuration
        theme: Theme for styling
        resume: Whether to restore previous session
    """
    from .textual_app import ScrappyApp, TextualOutputAdapter
    from .unified_io import UnifiedIO

    # Create output adapter first (needed for skeleton screen)
    # CRITICAL: This same adapter must be used by CLI so output goes to the right place
    output_adapter = TextualOutputAdapter()

    # Create IO with this adapter - will be passed to CLI
    io = UnifiedIO(output_sink=output_adapter, theme=theme)

    def cli_factory():
        """Factory function called in background thread."""
        # Pass the shared IO so CLI uses the same output adapter
        cli_instance = create_cli_from_context(ctx, io=io, theme=theme)
        cli_instance.auto_save = ctx.obj.get('auto_save', True)

        # Resume previous session if requested
        if resume:
            restore_session_to_cli(cli_instance, cli_instance.io)

        return cli_instance

    # Create app with factory - TUI shows immediately
    app = ScrappyApp(
        cli_factory=cli_factory,
        output_adapter=output_adapter,
        theme=theme,
    )
    app.run()


@cli.command()
def version():
    """Show scrappy version."""
    from scrappy import __version__
    click.echo(f"scrappy v{__version__}")


@cli.command()
@click.argument("prompt")
@click.option("--provider", "-p", default=None, help="Specific provider to use")
@click.option("--model", "-m", default=None, help="Specific model to use")
@click.option("--temperature", "-t", default=0.7, type=float, help="Temperature (0-1)")
@click.option("--max-tokens", default=1000, type=int, help="Max tokens in response")
@click.option("--with-context", "-c", is_flag=True, help="Include codebase context in prompt")
@click.option("--brain", "-b", default=None, help="Orchestrator brain provider")
@click.pass_context
def query(ctx, prompt, provider, model, temperature, max_tokens, with_context, brain):
    """Send a one-shot query to the orchestrator."""
    from ..orchestrator import AgentOrchestrator

    # Create orchestrator directly (no CLI for one-off commands)
    orchestrator = AgentOrchestrator(
        context_aware=ctx.obj.get('context_aware', True),
        enable_semantic_search=False  # Not needed for one-off queries
    )
    orchestrator.initialize(
        auto_register=True,
        orchestrator_provider=brain or ctx.obj.get('brain')
    )

    # Validate provider if explicitly specified
    if provider:
        provider_validation = validate_provider(provider)
        if not provider_validation.is_valid:
            error = ValidationError(
                f"Invalid provider: {provider_validation.error}",
                field="provider",
                value=provider
            )
            click.secho(f"Error: {error}", fg="red")
            click.echo(f"Suggestion: {error.suggestion}")
            sys.exit(1)
        target_provider = provider_validation.provider
    else:
        target_provider = orchestrator.brain

    logger = get_logger("cli.query")
    logger.info("Query started", extra={"provider": target_provider, "with_context": with_context})
    click.echo(f"Querying {target_provider}...\n")

    try:
        response = orchestrator.delegate(
            target_provider,
            prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=with_context if with_context else None
        )

        click.echo(response.content)
        click.secho(
            f"\n[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
            fg="cyan"
        )
    except Exception as e:
        display_command_error(e, "query")
        sys.exit(1)


@cli.command()
@click.argument("task")
@click.option("--max-steps", default=5, type=int, help="Maximum number of steps")
@click.pass_context
def plan(ctx, task, max_steps):
    """Create a task plan."""
    orchestrator = create_orchestrator_for_command(ctx)

    click.echo(f"Planning: {task}\n")
    try:
        # Use orchestrator to create plan
        plan_result = orchestrator.delegate(
            orchestrator.brain,
            f"Create a detailed step-by-step plan to accomplish this task:\n{task}\n\nProvide {max_steps} concrete steps.",
            use_context=True
        )
        click.echo(plan_result.content)
    except Exception as e:
        display_command_error(e, "plan")
        sys.exit(1)


@cli.command()
@click.argument("question")
@click.option("--context", "-c", default="", help="Additional context")
@click.option("--evidence", "-e", multiple=True, help="Evidence points (can specify multiple)")
@click.pass_context
def reason(ctx, question, context, evidence):
    """Reason about a question with evidence."""
    orchestrator = create_orchestrator_for_command(ctx)

    click.echo(f"Reasoning: {question}\n")

    try:
        response = orchestrator.reason(
            question,
            context=context,
            evidence=list(evidence)
        )

        if isinstance(response, dict):
            click.secho("Analysis:", bold=True)
            click.echo(response.get('analysis', ''))
            click.secho("\nConclusion: ", bold=True, nl=False)
            click.echo(response.get('conclusion', ''))
            click.echo(f"Confidence: {response.get('confidence', 'N/A')}")
        else:
            click.echo(response)
    except Exception as e:
        display_command_error(e, "reasoning")
        sys.exit(1)


@cli.command()
@click.argument("query")
@click.pass_context
def smart(ctx, query):
    """Perform a research-first query using tools to gather context."""
    click.secho("Note: Smart query requires interactive mode for tool usage", fg="yellow")
    click.echo("Use 'scrappy' (interactive mode) and then '/smart <query>'\n")

    # Fallback to regular query
    orchestrator = create_orchestrator_for_command(ctx)
    try:
        response = orchestrator.delegate(orchestrator.brain, query, use_context=True)
        click.echo(response.content)
    except Exception as e:
        display_command_error(e, "smart query")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status."""
    orchestrator = create_orchestrator_for_command(ctx)

    # Display status directly
    brain = orchestrator.brain or "None"
    providers_list = ', '.join(orchestrator.providers.list_available()) or "None"

    click.echo("\n=== System Status ===")
    click.echo(f"Brain: {brain}")
    click.echo(f"Available providers: {providers_list}")
    click.echo(f"Context: {'Explored' if orchestrator.context.is_explored() else 'Not explored'}")
    if orchestrator.context.is_explored():
        click.echo(f"  Project: {orchestrator.context.project_path}")


@cli.command()
@click.pass_context
def providers(ctx):
    """List available providers."""
    orchestrator = create_orchestrator_for_command(ctx)

    available = orchestrator.providers.list_available()
    click.echo("\n=== Available Providers ===")
    for provider in available:
        click.echo(f"  - {provider}")


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show selection log details")
@click.pass_context
def provider_info(ctx, verbose):
    """Show detailed provider selection information and reasoning.

    Displays which providers are available, why each was selected or skipped,
    and the current brain selection with its reasoning.

    Use this command to understand:
    - Why a particular provider was auto-selected as brain
    - Which providers are unavailable and why
    - The selection priority order
    """
    ctx.obj['verbose_selection'] = verbose
    ctx.obj['show_providers'] = True
    orchestrator = create_orchestrator_for_command(ctx)

    # Show basic info
    click.echo("\n=== Provider Information ===")
    click.echo(f"Selected brain: {orchestrator.brain}")
    available = orchestrator.providers.list_available()
    click.echo(f"Available providers: {', '.join(available)}")

    # Show additional programmatic info if verbose
    if verbose:
        info = orchestrator.get_provider_selection_info()
        click.secho("\nProgrammatic Info:", bold=True)
        click.echo(f"  Available: {info['available_providers']}")
        click.echo(f"  Selected brain: {info['selected_brain']}")
        click.echo(f"  Priority order: {' > '.join(info['selection_priority'])}")


@cli.command()
@click.argument("provider", required=False)
@click.pass_context
def models(ctx, provider):
    """List available models."""
    orchestrator = create_orchestrator_for_command(ctx)

    target_provider = provider or orchestrator.brain
    if not target_provider:
        click.secho("Error: No provider specified and no brain selected", fg="red")
        sys.exit(1)

    try:
        provider_instance = orchestrator.providers.get(target_provider)
        models_list = provider_instance.list_models() if hasattr(provider_instance, 'list_models') else []

        click.echo(f"\n=== Models for {target_provider} ===")
        for model in models_list:
            click.echo(f"  - {model}")
    except Exception as e:
        display_command_error(e, f"listing models for {target_provider}")
        sys.exit(1)


@cli.command()
@click.pass_context
def usage(ctx):
    """Show usage statistics."""
    # Usage stats would typically be stored somewhere, for now just show placeholder
    click.echo("\n=== Usage Statistics ===")
    click.echo("  Feature not yet implemented")
    click.echo("  Will track: queries, tokens, costs, etc.")


@cli.command()
@click.option("--resume", "-r", is_flag=True, help="Resume from last session")
@click.pass_context
def interactive(ctx, resume):
    """Start interactive chat mode."""
    # Get theme from global config
    config = get_config()
    theme = config.theme

    cli_instance = create_cli_from_context(ctx, theme=theme)

    if resume:
        restore_session_to_cli(cli_instance, cli_instance.io)

    cli_instance.interactive_mode()


@cli.command()
@click.option("--clear", is_flag=True, help="Clear cached context")
@click.option("--refresh", is_flag=True, help="Force re-exploration")
@click.pass_context
def context(ctx, clear, refresh):
    """Show and manage codebase context."""
    orchestrator = create_orchestrator_for_command(ctx)

    if clear:
        orchestrator.context.clear_cache()
        click.secho("Context cache cleared.", fg="green")
    elif refresh:
        click.echo("Refreshing context...")
        orchestrator.explore_project(force=True)
        click.secho("Context refreshed.", fg="green")
    else:
        # Show current context
        if orchestrator.context.is_explored():
            click.echo("\n=== Codebase Context ===")
            click.echo(f"Project: {orchestrator.context.project_path}")
            click.echo(f"Summary: {orchestrator.context.summary or 'No summary'}")
        else:
            click.secho("Context not explored. Use --refresh to explore.", fg="yellow")


@cli.command()
@click.argument("path", default=".", required=False)
@click.option("--save", "-s", is_flag=True, help="Save summary to file")
@click.pass_context
def explore(ctx, path, save):
    """Explore and learn about a codebase."""
    # Validate path input
    path_validation = validate_path(path, check_exists=True, must_be_dir=True)
    if not path_validation.is_valid:
        error = FileOperationError(
            f"Invalid path: {path_validation.error}",
            path=Path(path),
            operation="explore"
        )
        click.secho(f"Error: {error}", fg="red")
        click.echo(f"Suggestion: {error.suggestion}")
        sys.exit(1)

    path_obj = Path(path_validation.path).resolve()
    click.secho(f"\nExploring: {path_obj}", bold=True)
    click.echo("-" * 50)

    orchestrator = create_orchestrator_for_command(ctx)
    original_cwd = os.getcwd()
    try:
        os.chdir(path_obj)
        click.echo("Scanning codebase...")
        summary = orchestrator.context.summary or "No summary generated"
    finally:
        os.chdir(original_cwd)

    click.echo()
    click.secho("Codebase Summary:", bold=True)
    click.echo("-" * 50)
    click.echo(summary)

    if save:
        summary_file = path_obj / "CODEBASE_SUMMARY.md"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("# Codebase Summary\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            f.write(summary)
        click.secho(f"\nSaved to: {summary_file}", fg="green")


@cli.command()
@click.argument("task")
@click.option("--dry-run", "-d", is_flag=True, help="Run in dry-run mode (no actual changes)")
@click.option("--no-checkpoint", is_flag=True, help="Skip git checkpoint creation")
@click.option("--auto-confirm", is_flag=True, help="Auto-confirm all actions (use with caution)")
@click.option("--max-iterations", "-m", default=50, type=int, help="Maximum agent iterations (checkpoint every 15)")
@click.pass_context
def agent(ctx, task, dry_run, no_checkpoint, auto_confirm, max_iterations):
    """Run code agent to complete a task.

    Note: Interactive approvals require interactive mode. Use --auto-confirm or
    --dry-run for one-off commands. For full interactive mode, use 'scrappy'
    and then '/agent <task>'.

    Example:
        scrappy agent "Add a health check endpoint" --auto-confirm
    """
    if not auto_confirm and not dry_run:
        click.secho("Error: Agent command requires --auto-confirm or --dry-run in one-off mode", fg="red")
        click.echo("For interactive approvals, use: scrappy (then /agent <task>)")
        sys.exit(1)

    # Check dependencies before running agent
    deps_ok, errors = check_agent_dependencies()
    if not deps_ok:
        click.secho("Agent requires missing dependencies:", fg="red")
        for err in errors:
            click.echo(f"  - {err}")
        sys.exit(1)

    orchestrator = create_orchestrator_for_command(ctx)

    click.secho(f"\nCode Agent - Task: {task}", bold=True)
    click.echo("-" * 60)

    checkpoint_hash = None
    if not no_checkpoint:
        click.echo("Creating git checkpoint...")
        checkpoint_hash = create_git_checkpoint(str(orchestrator.context.project_path))
        if checkpoint_hash:
            click.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
        else:
            click.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

    code_agent = CodeAgent(orchestrator)
    code_agent.dry_run = dry_run

    click.echo("\nAgent Configuration:")
    click.echo(f"  Planner (smart tasks): {code_agent.planner}")
    click.echo(f"  Executor (fast tasks): {code_agent.executor}")
    click.echo(f"  Project root: {code_agent.project_root}")
    click.echo(f"  Max iterations: {max_iterations}")
    if dry_run:
        click.secho("  Mode: DRY RUN (no actual changes)", fg="yellow")
    if auto_confirm:
        click.secho("  WARNING: Auto-confirm enabled - no approval prompts", fg="red", bold=True)
    click.echo()

    logger = get_logger("cli.agent")
    logger.info("Agent started", extra={
        "task": task,
        "dry_run": dry_run,
        "max_iterations": max_iterations,
    })

    try:
        result = code_agent.run(task, max_iterations=max_iterations, auto_confirm=auto_confirm)

        click.echo("\n" + "=" * 60)
        if result['success']:
            click.secho("Task Completed Successfully!", fg="green", bold=True)
            logger.info("Agent task completed", extra={"task": task, "iterations": result['iterations']})
        else:
            click.secho("Task Did Not Complete", fg="yellow", bold=True)
            logger.warning("Agent task incomplete", extra={"task": task, "iterations": result['iterations']})

        log_path = code_agent.save_audit_log()
        click.secho(f"Audit log: {log_path}", fg="cyan")

        if checkpoint_hash and not dry_run:
            click.echo(f"\nTo rollback changes: git reset --hard {checkpoint_hash}")

    except KeyboardInterrupt:
        click.echo("\n\nAgent interrupted by user.")
        logger.info("Agent interrupted by user", extra={"task": task})
        sys.exit(1)
    except CLIError as e:
        click.secho(f"\nAgent error: {e}", fg="red")
        if e.suggestion:
            click.echo(f"Suggestion: {e.suggestion}")
        logger.error("Agent CLI error", extra=e.logging_extra())
        sys.exit(1)
    except Exception as e:
        error = TaskExecutionError(
            f"Agent error: {e}",
            task_name=task,
            original=e
        )
        click.secho(f"\n{error}", fg="red")
        click.echo(f"Suggestion: {error.suggestion}")
        logger.exception("Unexpected agent error")
        sys.exit(1)


# =============================================================================
# Config Command Group - API Key Management
# =============================================================================

@cli.group()
def config():
    """Manage API key configuration.

    Commands to list, add, and remove provider API keys.

    Examples:
        scrappy config list          # Show configured providers
        scrappy config set groq      # Add/update Groq API key
        scrappy config remove groq   # Remove Groq API key
    """
    pass


@config.command('list')
def config_list():
    """List configured API providers.

    Shows which providers have API keys configured, with masked key values
    for security. Also shows unconfigured providers for reference.
    """
    from scrappy.infrastructure.config.api_keys import create_api_key_service
    from scrappy.orchestrator.provider_definitions import PROVIDERS

    config_service = create_api_key_service()

    click.secho("\nAPI Key Configuration", bold=True)
    click.echo("=" * 50)

    configured = []
    unconfigured = []

    for name, info in sorted(PROVIDERS.items(), key=lambda x: x[1].priority):
        key = config_service.get_key(info.env_var)
        if key:
            # Mask the key for display (show first 4 and last 4 chars)
            if len(key) > 12:
                masked = f"{key[:4]}...{key[-4:]}"
            else:
                masked = "****"
            configured.append((name, info, masked))
        else:
            unconfigured.append((name, info))

    if configured:
        click.secho("\nConfigured providers:", fg="green")
        for name, info, masked in configured:
            click.echo(f"  {name:12} {masked:20} ({info.quota})")
    else:
        click.secho("\nNo providers configured.", fg="yellow")

    if unconfigured:
        click.secho("\nUnconfigured providers:", fg="yellow")
        for name, info in unconfigured:
            click.echo(f"  {name:12} {info.env_var:25} ({info.console_url})")

    click.echo()


@config.command('set')
@click.argument('provider')
def config_set(provider: str):
    """Set API key for a provider.

    Prompts for the API key interactively (hidden input for security).
    The key is validated before saving.

    PROVIDER is the name of the provider (e.g., groq, cerebras, gemini).
    """
    from scrappy.infrastructure.config.api_keys import (
        create_api_key_service,
        ApiKeyValidationError,
    )
    from scrappy.orchestrator.provider_definitions import PROVIDERS

    provider = provider.lower()
    if provider not in PROVIDERS:
        click.secho(f"Unknown provider: {provider}", fg="red")
        click.echo(f"Available providers: {', '.join(PROVIDERS.keys())}")
        sys.exit(1)

    info = PROVIDERS[provider]
    click.echo(f"\nSetting API key for {provider}")
    click.echo(f"Get your key from: {info.console_url}")
    click.echo()

    # Prompt for key (hidden input)
    key = click.prompt(
        f"Enter {info.env_var}",
        hide_input=True,
        confirmation_prompt=True
    )

    if not key or not key.strip():
        click.secho("Cancelled - no key provided.", fg="yellow")
        sys.exit(0)

    config_service = create_api_key_service()
    try:
        config_service.set_key(info.env_var, key.strip())
        click.secho(f"\nAPI key for {provider} saved successfully!", fg="green")
    except ApiKeyValidationError as e:
        click.secho(f"\nInvalid API key: {e}", fg="red")
        sys.exit(1)


@config.command('remove')
@click.argument('provider')
@click.option('--force', '-f', is_flag=True, help="Skip confirmation prompt")
def config_remove(provider: str, force: bool):
    """Remove API key for a provider.

    PROVIDER is the name of the provider (e.g., groq, cerebras, gemini).
    """
    from scrappy.infrastructure.config.api_keys import create_api_key_service
    from scrappy.orchestrator.provider_definitions import PROVIDERS

    provider = provider.lower()
    if provider not in PROVIDERS:
        click.secho(f"Unknown provider: {provider}", fg="red")
        click.echo(f"Available providers: {', '.join(PROVIDERS.keys())}")
        sys.exit(1)

    info = PROVIDERS[provider]
    config_service = create_api_key_service()

    # Check if key exists
    if not config_service.get_key(info.env_var):
        click.secho(f"No API key configured for {provider}.", fg="yellow")
        sys.exit(0)

    # Confirm removal
    if not force:
        if not click.confirm(f"Remove API key for {provider}?"):
            click.echo("Cancelled.")
            sys.exit(0)

    # Remove by setting to empty and then removing from config
    config = config_service.load(migrate_env=False)
    if info.env_var in config.api_keys:
        del config.api_keys[info.env_var]
        config_service.save(config)
        click.secho(f"API key for {provider} removed.", fg="green")
    else:
        click.secho(f"No API key found for {provider}.", fg="yellow")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    # Ensure CLI mode is set (default, but explicit for safety)
    # TUI mode will be set by ScrappyApp.on_mount() when Textual starts
    OutputModeContext.set_tui_mode(False)

    # Load configuration early - this initializes the global config
    # Config is loaded from:
    #   1. Explicit file path (via CLI_CONFIG_PATH env var)
    #   2. Default config files (.scrappy.json, .scrappy.yaml, .scrappy.toml)
    #   3. Environment variables (CLI_* prefix)
    #   4. Default values
    try:
        config = get_config()
        config.validate()
    except Exception as e:
        logger = get_logger("cli.agent")
        # Early warning before Textual UI is available
        # Use logger for config warnings (no UnifiedIO needed for non-interactive commands)
        logger.error(f"Warning: Config validation failed: {e}")

    cli(obj={})


if __name__ == "__main__":
    main()
