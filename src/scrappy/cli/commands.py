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

    # SELECTION OWNERSHIP. main() captures before invoking Click and deposits the
    # capture here, so an ordinary invocation performs ONE selection. Presence of
    # the key, not truthiness, decides: a captured None is a real answer meaning
    # "no explicit selection", and re-selecting would discard it. Direct Click
    # entry, with no main() above it, finds no key and selects for itself.
    if CONFIG_CAPTURE_KEY not in ctx.obj:
        captured, source = capture_configuration_at_entry()
        ctx.obj[CONFIG_CAPTURE_KEY] = captured
        ctx.obj[CONFIG_SOURCE_KEY] = source

    captured = ctx.obj[CONFIG_CAPTURE_KEY]

    # If no subcommand, start TUI
    if ctx.invoked_subcommand is None:
        config = captured if captured is not None else get_config()
        start_tui_deferred(ctx, config.theme, resume, cli_config=captured)


CONFIG_CAPTURE_KEY = 'cli_config'
CONFIG_SOURCE_KEY = 'cli_config_source'


def capture_configuration_at_entry(code_root=None):
    """Capture the configuration selection ONCE, as an EXPLICIT OBJECT.

    Returns (config, source_path), or (None, None) when nothing is explicitly
    selected. A returned object means "explicitly injected"; None means
    "no injection, ordinary precedence applies". Downstream consumers keep their
    standalone fallback in the None case, so behaviour is unchanged there.

    WHY AN OBJECT AND NOT A PATH. get_config(config_path=...) does NOT replace an
    already-cached global (config_factory.py:248-251 only rebuilds when reload or
    _global_config is None). Handing a path down therefore loses to any object
    cached earlier in the process, even when the selection here is correct. The
    captured object is forwarded directly instead, so an explicit selection wins
    without changing get_config's cache or reload semantics.

    CAPTURED ONCE, NOT RE-READ. The code root is resolved a single time and the
    selection is resolved to an ABSOLUTE path against it, so a later CWD change
    cannot retarget it, and both entry points forward the SAME capture rather
    than each performing its own.

    PRECEDENCE IS PRESERVED EXACTLY, mirroring CLIConfigFactory.create:
      - CLI_CONFIG_PATH outranks the code-root scan.
      - If CLI_CONFIG_PATH is set but names no existing file, we do NOT fall
        through to the scan, because production does not either: branch 3 is an
        `else`, so an unreadable environment selection yields defaults.
      - Otherwise the same DEFAULT_CONFIG_FILES are searched in the same order.
      - The object itself is built by the production factory, so parsing and
        environment merging are untouched (scrappy-bj58 stays out of scope).
    """
    import os
    from pathlib import Path

    from .config_factory import CLIConfigFactory

    root = Path(code_root).resolve() if code_root is not None else Path.cwd().resolve()

    # PRESENCE, not truthiness, to match CLIConfigFactory.create:151-152. With
    # CLI_CONFIG_PATH set to the empty string, production selects Path(''),
    # fails to load it and retains defaults plus environment merging; it does
    # NOT fall through to the code-root scan. Testing truthiness here would have
    # scanned instead, silently changing precedence in that edge case.
    if 'CLI_CONFIG_PATH' in os.environ:
        candidate = Path(os.environ['CLI_CONFIG_PATH'])
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        if not candidate.exists():
            return None, None
        selected = candidate
    else:
        selected = None
        for filename in CLIConfigFactory.DEFAULT_CONFIG_FILES:
            candidate = (root / filename).resolve()
            if candidate.exists():
                selected = candidate
                break
        if selected is None:
            return None, None

    return CLIConfigFactory().create(config_path=str(selected)), selected


def start_tui_deferred(ctx, theme, resume: bool = False, cli_config=None) -> None:
    """Start TUI with deferred CLI initialization.

    Shows the TUI skeleton instantly while CLI/orchestrator loads in background.
    """
    from pathlib import Path

    from .textual.app import ScrappyApp
    from .textual.output_adapter import TextualOutputAdapter
    from .unified_io import UnifiedIO
    from scrappy.infrastructure.paths import create_default_path_provider
    from scrappy.orchestrator.api_key_composition import create_api_key_service

    output_adapter = TextualOutputAdapter()
    io = UnifiedIO(output_sink=output_adapter, theme=theme)

    # Resolve ONE provider at this composition root and share the SAME object
    # between the CLI (built later on a background thread) and the app that owns
    # the main screen, so history/cooldowns resolve through a single provider.
    path_provider = create_default_path_provider(Path("."))

    # Same for the API key service. Sharing one instance across the main thread
    # and the CLI worker needs no lock: the app completes both of its mount
    # reads before initialize_cli() starts the worker that builds the CLI, and
    # the banner read runs on the main thread after the worker finishes.
    api_key_service = create_api_key_service()

    def cli_factory():
        """Factory function called in background thread."""
        cli_instance = create_cli_from_context(
            ctx,
            io=io,
            theme=theme,
            path_provider=path_provider,
            api_key_service=api_key_service,
            cli_config=cli_config,
        )
        cli_instance.auto_save = ctx.obj.get('auto_save', True)

        if resume:
            restore_session_to_cli(cli_instance, cli_instance.io)

        return cli_instance

    app = ScrappyApp(
        cli_factory=cli_factory,
        output_adapter=output_adapter,
        theme=theme,
        path_provider=path_provider,
        api_key_service=api_key_service,
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
        # main OWNS the selection. The captured object and its resolved source
        # are handed to Click below, so the callback does not select again and
        # the object validated here is the one the deferred CLI receives.
        captured, source = capture_configuration_at_entry()
        config = captured if captured is not None else get_config()
        config.validate()
    except Exception as e:
        from .logging import get_logger
        logger = get_logger("cli.main")
        logger.error(f"Warning: Config validation failed: {e}")
        captured, source = None, None

    cli(obj={CONFIG_CAPTURE_KEY: captured, CONFIG_SOURCE_KEY: source})


if __name__ == "__main__":
    main()
