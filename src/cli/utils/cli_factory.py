"""
CLI factory utilities for eliminating duplication.

Provides factory functions for creating CLI instances, handlers, and
extracting configuration from Click contexts.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Dict

from ..io_interface import CLIIOProtocol, TestIO
from ..unified_io import UnifiedIO
from ..display import CLIDisplay
from ..session import CLISessionManager
from ..codebase import CLICodebaseAnalysis
from ..tasks import CLITaskExecution
from ..multiprovider import CLIMultiProvider
from ..smart_query import CLISmartQuery
from ..agent_manager import CLIAgentManager
from ..task_router_handler import CLITaskRouterHandler
from ..context_commands import CLIContextCommands
from ..cache_manager import CacheManager
from ..rate_limiter import RateLimiter
from ..persistence import SessionPersistence

if TYPE_CHECKING:
    from ..core import CLI
    from ...orchestrator.protocols import Orchestrator


def get_io_interface(
    io: Optional[CLIIOProtocol] = None,
    test_mode: bool = False
) -> CLIIOProtocol:
    """
    Get or create appropriate IO interface for CLI (interactive mode).

    CLI always uses Textual, so this creates UnifiedIO with OutputSink.

    Args:
        io: Existing IO interface to use (takes precedence)
        test_mode: If True and no io provided, create TestIO

    Returns:
        CLIIOProtocol compatible interface with Textual OutputSink
    """
    if io is not None:
        return io
    if test_mode:
        return TestIO()

    # CLI === Textual (interactive mode)
    # Create UnifiedIO with OutputSink for Textual routing
    from ..textual_app import TextualOutputAdapter
    output_adapter = TextualOutputAdapter()
    return UnifiedIO(output_sink=output_adapter)


def create_context_state(ctx: Any) -> Dict[str, Any]:
    """
    Create context state dict from Click context.

    Extracts all standard configuration values with sensible defaults.

    Args:
        ctx: Click context object

    Returns:
        Dict with all 7 standard configuration keys
    """
    obj = ctx.obj if ctx.obj is not None else {}

    return {
        'brain': obj.get('brain'),
        'auto_explore': obj.get('auto_explore', False),
        'context_aware': obj.get('context_aware', True),
        'resume': obj.get('resume', False),
        'auto_save': obj.get('auto_save', True),
        'show_providers': obj.get('show_providers', False),
        'verbose_selection': obj.get('verbose_selection', False),
    }


def extract_context_options(ctx: Any) -> Dict[str, Any]:
    """
    Extract options needed for CLI creation from Click context.

    Maps context keys to CLI constructor parameter names.

    Args:
        ctx: Click context object

    Returns:
        Dict with CLI constructor parameters
    """
    obj = ctx.obj if ctx.obj is not None else {}

    return {
        'brain': obj.get('brain'),
        'auto_explore': obj.get('auto_explore', False),
        'context_aware': obj.get('context_aware', True),
        'verbose_selection': obj.get('verbose_selection', False),
        'show_provider_status': obj.get('show_providers', False),
    }


def initialize_cli_handlers(
    orchestrator: "Orchestrator",
    session_start: datetime,
    io: CLIIOProtocol
) -> Dict[str, Any]:
    """
    Create and return all CLI component handlers.

    Args:
        orchestrator: AgentOrchestrator instance
        session_start: Session start datetime for display handler
        io: I/O interface for output

    Returns:
        Dict with all 8 standard handlers
    """
    # Create session manager dependencies first (all need io)
    context_manager = CLIContextCommands(orchestrator, io)
    cache_manager = CacheManager(orchestrator, io)
    rate_limiter = RateLimiter(orchestrator, io)
    session_persistence = SessionPersistence(orchestrator, io)

    # Create session manager with all dependencies (no io - delegates have it)
    session_mgr = CLISessionManager(
        orchestrator=orchestrator,
        context_manager=context_manager,
        cache_manager=cache_manager,
        rate_limiter=rate_limiter,
        session_persistence=session_persistence
    )

    return {
        'display': CLIDisplay(orchestrator, session_start, io),
        'session_mgr': session_mgr,
        'codebase': CLICodebaseAnalysis(orchestrator, io),
        'tasks': CLITaskExecution(orchestrator, io),
        'multiprovider': CLIMultiProvider(orchestrator, io),
        'smart': CLISmartQuery(orchestrator, io),
        'agent_mgr': CLIAgentManager(orchestrator, io),
        'task_router': CLITaskRouterHandler(orchestrator, io),
    }


def create_cli_from_context(ctx: Any, io: Optional[CLIIOProtocol] = None) -> "CLI":
    """
    Create CLI instance from Click context object.

    Args:
        ctx: Click context object with configuration in ctx.obj
        io: IO interface

    Returns:
        CLI instance configured from context
    """
    from ..core import CLI

    options = extract_context_options(ctx)

    cli = CLI(
        brain=options['brain'],
        auto_explore=options['auto_explore'],
        context_aware=options['context_aware'],
        verbose_selection=options['verbose_selection'],
        show_provider_status=options['show_provider_status'],
        io=io
    )
    cli.initialize()
    return cli


def create_cli(config: Dict[str, Any], io: Optional[CLIIOProtocol] = None) -> "CLI":
    """
    Create CLI instance from a simple dictionary configuration.

    This is a convenience function for creating CLI instances without
    needing a Click context object. Useful for programmatic usage and testing.

    Args:
        config: Dictionary with configuration options:
            - brain: Provider to use as brain (default None)
            - auto_explore: Auto-explore on startup (default False)
            - context_aware: Enable context-aware prompts (default True)
            - verbose_selection: Show verbose provider selection (default False)
            - show_provider_status: Show provider status on startup (default False)
        io: IO interface (creates if not provided)

    Returns:
        CLI instance configured from dict

    Example:
        cli = create_cli({'brain': 'cerebras', 'auto_explore': True})
    """
    from ..core import CLI

    cli = CLI(
        brain=config.get('brain'),
        auto_explore=config.get('auto_explore', False),
        context_aware=config.get('context_aware', True),
        verbose_selection=config.get('verbose_selection', False),
        show_provider_status=config.get('show_provider_status', False),
        io=io
    )
    cli.initialize()
    return cli
