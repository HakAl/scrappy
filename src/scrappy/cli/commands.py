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

from .utils.cli_factory import create_cli_from_context


def create_orchestrator_for_command(ctx):
    """Create orchestrator for one-off commands (no CLI/Textual).

    Args:
        ctx: Click context

    Returns:
        Initialized AgentOrchestrator
    """
    from ..orchestrator import AgentOrchestrator

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
from .utils.session_utils import restore_session_to_cli
from .utils.error_utils import run_with_error_handling, run_with_recovery
from .validators import validate_path, validate_provider
from .exceptions import (
    CLIError,
    ValidationError,
    TaskExecutionError,
    FileOperationError,
)
from .logging import get_logger
from ..agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint
from .config_factory import get_config
from scrappy.infrastructure.output_mode import OutputModeContext


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

    # If no subcommand, start interactive mode
    if ctx.invoked_subcommand is None:
        # Create CLI with theme from config
        cli_instance = create_cli_from_context(ctx, theme=theme)
        cli_instance.auto_save = ctx.obj['auto_save']

        # Resume previous session if requested
        if resume:
            restore_session_to_cli(cli_instance, cli_instance.io)

        cli_instance.interactive_mode()


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
        click.secho(f"Error: {e}", fg="red")
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
        click.secho(f"Error: {e}", fg="red")
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
        click.secho(f"Error: {e}", fg="red")
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
        click.secho(f"Error: {e}", fg="red")
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
        click.secho(f"Error: {e}", fg="red")
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
            click.echo(f"\n=== Codebase Context ===")
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
        result = orchestrator.explore_project(force=True)
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
            f.write(f"# Codebase Summary\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            f.write(summary)
        click.secho(f"\nSaved to: {summary_file}", fg="green")


@cli.command()
@click.argument("task")
@click.option("--dry-run", "-d", is_flag=True, help="Run in dry-run mode (no actual changes)")
@click.option("--no-checkpoint", is_flag=True, help="Skip git checkpoint creation")
@click.option("--auto-confirm", is_flag=True, help="Auto-confirm all actions (use with caution)")
@click.option("--max-iterations", "-m", default=10, type=int, help="Maximum agent iterations")
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

    click.echo(f"\nAgent Configuration:")
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

        click.echo(f"Result: {result['result']}")
        click.echo(f"Iterations: {result['iterations']}")

        if result['audit_log']:
            click.secho("\nAudit Log:", bold=True)
            for entry in result['audit_log']:
                approved = "Approved" if entry['approved'] else "Denied"
                click.echo(f"  [{entry['timestamp'][:19]}] {entry['action']} - {approved}")

        log_path = code_agent.save_audit_log()
        click.secho(f"\nAudit log saved to: {log_path}", fg="cyan")

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
        # Early warning before Textual UI is available
        # Use logger for config warnings (no UnifiedIO needed for non-interactive commands)
        logger.error(f"Warning: Config validation failed: {e}")

    cli(obj={})


if __name__ == "__main__":
    main()
