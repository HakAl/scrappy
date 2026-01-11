#!/usr/bin/env python3
"""
Click command handlers for the Scrappy CLI.

Simplified CLI with TUI as primary interface.
Keeps: --help, --version, undo commands, TUI (default)
"""

import click
import sys

from .config_factory import get_config
from scrappy.infrastructure.output_mode import OutputModeContext
from .utils.cli_factory import create_cli_from_context
from .utils.session_utils import restore_session_to_cli

# Load environment variables from .env file
import warnings
import logging
try:
    from dotenv import load_dotenv
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        logging.getLogger("dotenv.main").setLevel(logging.ERROR)
        load_dotenv(override=False)
except ImportError:
    pass


@click.group(invoke_without_command=True)
@click.option("--resume", "-r", is_flag=True, help="Resume from last saved session")
@click.option("--no-save", is_flag=True, help="Disable auto-save on exit")
@click.pass_context
def cli(ctx, resume, no_save):
    """Scrappy CLI - Multi-provider orchestrator interface.

    Start interactive mode by running without arguments.
    Sessions are auto-saved on /quit by default. Use --resume to continue.
    """
    ctx.ensure_object(dict)

    ctx.obj['resume'] = resume
    ctx.obj['auto_save'] = not no_save

    # If no subcommand, start TUI
    if ctx.invoked_subcommand is None:
        config = get_config()
        start_tui_deferred(ctx, config.theme, resume)


def start_tui_deferred(ctx, theme, resume: bool = False) -> None:
    """Start TUI with deferred CLI initialization.

    Shows the TUI skeleton instantly while CLI/orchestrator loads in background.
    """
    from .textual import ScrappyApp, TextualOutputAdapter
    from .unified_io import UnifiedIO

    output_adapter = TextualOutputAdapter()
    io = UnifiedIO(output_sink=output_adapter, theme=theme)

    def cli_factory():
        """Factory function called in background thread."""
        cli_instance = create_cli_from_context(ctx, io=io, theme=theme)
        cli_instance.auto_save = ctx.obj.get('auto_save', True)

        if resume:
            restore_session_to_cli(cli_instance, cli_instance.io)

        return cli_instance

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


# =============================================================================
# Undo Commands - Safe rollback of agent changes
# =============================================================================

@cli.command()
@click.argument("n", default=1, type=int)
@click.option("--force", is_flag=True, help="Bypass worktree path check (if directory was moved)")
def undo(n: int, force: bool):
    """Undo the last N agent runs.

    Restores the repository state from before the agent ran.
    Use --force if you moved the project directory since the agent run.

    Examples:
        scrappy undo        # Undo most recent agent run
        scrappy undo 2      # Undo 2nd most recent
        scrappy undo --force  # Bypass path check
    """
    from scrappy import undo as undo_module

    try:
        undo_module.undo(n, force=force)
        click.secho(f"Restored to state before agent run #{n}", fg="green")
    except undo_module.UndoError as e:
        click.secho(f"Undo failed: {e}", fg="red")
        sys.exit(1)


@cli.command("undo-list")
def undo_list():
    """List available undo points.

    Shows all saved snapshots that can be restored with 'scrappy undo'.
    """
    from scrappy import undo as undo_module

    states = undo_module.load_undo_states()

    if not states:
        click.echo("No undo points available")
        return

    click.echo(f"Available undo points ({len(states)}):\n")
    for i, state in enumerate(reversed(states), 1):
        branch_info = state.branch or f"detached@{state.original_head[:7] if state.original_head else 'unknown'}"
        wip_marker = " [dirty]" if state.is_wip else ""
        click.echo(f"  {i}. {state.created_at:%Y-%m-%d %H:%M:%S} on {branch_info}{wip_marker}")


@cli.command("undo-gc")
@click.option("--keep", default=None, type=int, help="Number of undo points to keep (default: SCRAPPY_UNDO_LIMIT or 10)")
def undo_gc(keep: int):
    """Clean up old undo points.

    Removes the oldest undo points, keeping the most recent N.
    Default is controlled by SCRAPPY_UNDO_LIMIT env var (default: 10).
    """
    from scrappy import undo as undo_module

    before = len(undo_module.load_undo_states())
    undo_module.prune_old_undo_states(keep=keep)
    after = len(undo_module.load_undo_states())

    removed = before - after
    click.echo(f"Removed {removed} undo points, kept {after}")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    OutputModeContext.set_tui_mode(False)

    try:
        config = get_config()
        config.validate()
    except Exception as e:
        from .logging import get_logger
        logger = get_logger("cli.main")
        logger.error(f"Warning: Config validation failed: {e}")

    cli(obj={})


if __name__ == "__main__":
    main()
