#!/usr/bin/env python3
"""
Click command handlers for the LLM Agent Team CLI.
Provides the main entry point and subcommands.
"""

import click
import sys
import os
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file (supplements, doesn't override existing env vars)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # Don't override existing environment variables
except ImportError:
    pass  # python-dotenv not installed, skip

from .core import CLI
from .utils.cli_factory import create_cli_from_context
from .utils.session_utils import restore_session_to_cli
from .utils.error_utils import run_with_error_handling, run_with_recovery
from .io_interface import ClickIO
from .validators import validate_path, validate_provider
from .exceptions import (
    CLIError,
    ValidationError,
    ProviderError,
    TaskExecutionError,
    FileOperationError,
)
from .logging import get_logger

try:
    from ..agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint
except ImportError:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint


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
    """LLM Agent Team CLI - Multi-provider orchestrator interface.

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

    # If no subcommand, start interactive mode
    if ctx.invoked_subcommand is None:
        cli_instance = create_cli_from_context(ctx)
        cli_instance.auto_save = ctx.obj['auto_save']

        # Resume previous session if requested
        if resume:
            io = ClickIO()
            restore_session_to_cli(cli_instance, io)

        cli_instance.interactive_mode()


@cli.command()
@click.argument("prompt")
@click.option("--provider", "-p", default=None, help="Specific provider to use")
@click.option("--model", "-m", default=None, help="Specific model to use")
@click.option("--temperature", "-t", default=0.7, type=float, help="Temperature (0-1)")
@click.option("--max-tokens", default=1000, type=int, help="Max tokens in response")
@click.option("--with-context", "-c", is_flag=True, help="Include codebase context in prompt")
@click.pass_context
def query(ctx, prompt, provider, model, temperature, max_tokens, with_context):
    """Send a one-shot query to the orchestrator."""
    cli_instance = create_cli_from_context(ctx)
    io = ClickIO()

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
        target_provider = cli_instance.orchestrator.brain

    logger = get_logger("cli.query", io=io)
    logger.info("Query started", extra={"provider": target_provider, "with_context": with_context})
    click.echo(f"Querying {target_provider}...\n")

    def execute_query():
        response = cli_instance.orchestrator.delegate(
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

    run_with_error_handling(io, execute_query)


@cli.command()
@click.argument("task")
@click.option("--max-steps", default=5, type=int, help="Maximum number of steps")
@click.pass_context
def plan(ctx, task, max_steps):
    """Create a task plan."""
    cli_instance = create_cli_from_context(ctx)
    click.echo(f"Planning: {task}\n")
    cli_instance.tasks.plan_task(task)


@cli.command()
@click.argument("question")
@click.option("--context", "-c", default="", help="Additional context")
@click.option("--evidence", "-e", multiple=True, help="Evidence points (can specify multiple)")
@click.pass_context
def reason(ctx, question, context, evidence):
    """Reason about a question with evidence."""
    cli_instance = create_cli_from_context(ctx)
    io = ClickIO()
    click.echo(f"Reasoning: {question}\n")

    def execute_reasoning():
        response = cli_instance.orchestrator.reason(
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

    run_with_error_handling(io, execute_reasoning)


@cli.command()
@click.argument("query")
@click.pass_context
def smart(ctx, query):
    """Perform a research-first query using tools to gather context."""
    cli_instance = create_cli_from_context(ctx)
    cli_instance.smart.smart_query(query)


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status."""
    cli_instance = create_cli_from_context(ctx)
    cli_instance.display.show_status()


@cli.command()
@click.pass_context
def providers(ctx):
    """List available providers."""
    cli_instance = create_cli_from_context(ctx)
    cli_instance.display.list_providers()


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
    # Override context values for this specific command
    ctx.obj['verbose_selection'] = verbose
    ctx.obj['show_providers'] = True  # Always show status for this command
    cli_instance = create_cli_from_context(ctx)

    # Show additional programmatic info if verbose
    if verbose:
        info = cli_instance.orchestrator.get_provider_selection_info()
        click.secho("\nProgrammatic Info:", bold=True)
        click.echo(f"  Available: {info['available_providers']}")
        click.echo(f"  Selected brain: {info['selected_brain']}")
        click.echo(f"  Priority order: {' > '.join(info['selection_priority'])}")


@cli.command()
@click.argument("provider", required=False)
@click.pass_context
def models(ctx, provider):
    """List available models."""
    cli_instance = create_cli_from_context(ctx)
    cli_instance.display.list_models(provider or "")


@cli.command()
@click.pass_context
def usage(ctx):
    """Show usage statistics."""
    cli_instance = create_cli_from_context(ctx)
    cli_instance.display.show_usage()


@cli.command()
@click.option("--resume", "-r", is_flag=True, help="Resume from last session")
@click.pass_context
def interactive(ctx, resume):
    """Start interactive chat mode."""
    cli_instance = create_cli_from_context(ctx)

    if resume:
        io = ClickIO()
        restore_session_to_cli(cli_instance, io)

    cli_instance.interactive_mode()


@cli.command()
@click.option("--clear", is_flag=True, help="Clear cached context")
@click.option("--refresh", is_flag=True, help="Force re-exploration")
@click.pass_context
def context(ctx, clear, refresh):
    """Show and manage codebase context."""
    cli_instance = create_cli_from_context(ctx)

    if clear:
        cli_instance.orchestrator.context.clear_cache()
        click.secho("Context cache cleared.", fg="green")
    elif refresh:
        cli_instance.session_mgr.manage_context("refresh")
    else:
        cli_instance.session_mgr.manage_context("")


@cli.command()
@click.argument("path", default=".", required=False)
@click.option("--save", "-s", is_flag=True, help="Save summary to file")
@click.pass_context
def explore(ctx, path, save):
    """Explore and learn about a codebase."""
    cli_instance = create_cli_from_context(ctx)

    # Validate path input
    path_validation = validate_path(path)
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
    if not path_obj.exists():
        error = FileOperationError(
            f"Path does not exist: {path_obj}",
            path=path_obj,
            operation="explore"
        )
        click.secho(f"Error: {error}", fg="red")
        click.echo(f"Suggestion: Check that the path exists and is spelled correctly.")
        sys.exit(1)

    if not path_obj.is_dir():
        error = FileOperationError(
            f"Not a directory: {path_obj}",
            path=path_obj,
            operation="explore"
        )
        click.secho(f"Error: {error}", fg="red")
        click.echo(f"Suggestion: Provide a directory path, not a file.")
        sys.exit(1)

    click.secho(f"\nExploring: {path_obj}", bold=True)
    click.echo("-" * 50)

    original_cwd = os.getcwd()
    try:
        os.chdir(path_obj)
        click.echo("Scanning codebase...")
        result = cli_instance.orchestrator.explore_project(force=True)
        summary = cli_instance.orchestrator.context.summary or "No summary generated"
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
    """Run code agent to complete a task with human approval.

    The agent uses Gemini for planning/code generation (smart tasks)
    and Cerebras for quick operations. All file modifications require
    your explicit approval unless --auto-confirm is used.

    Example:
        llm-team agent "Add a health check endpoint to the Flask app"
    """
    cli_instance = create_cli_from_context(ctx)

    click.secho(f"\nCode Agent - Task: {task}", bold=True)
    click.echo("-" * 60)

    checkpoint_hash = None
    if not no_checkpoint:
        click.echo("Creating git checkpoint...")
        checkpoint_hash = create_git_checkpoint(str(cli_instance.orchestrator.context.project_path))
        if checkpoint_hash:
            click.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
        else:
            click.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

    code_agent = CodeAgent(cli_instance.orchestrator)
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
                approved = click.style("Approved", fg="green") if entry['approved'] else click.style("Denied", fg="red")
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
    cli(obj={})


if __name__ == "__main__":
    main()
