"""
CLI factory utilities for eliminating duplication.

Provides factory functions for creating CLI instances, handlers, and
extracting configuration from Click contexts.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from ..io_interface import CLIIOProtocol, ClickIO, TestIO
from ..display import CLIDisplay
from ..session import CLISessionManager
from ..codebase import CLICodebaseAnalysis
from ..tasks import CLITaskExecution
from ..multiprovider import CLIMultiProvider
from ..smart_query import CLISmartQuery
from ..agent_manager import CLIAgentManager
from ..task_router_handler import CLITaskRouterHandler


def get_io_interface(
    io: Optional[CLIIOProtocol] = None,
    test_mode: bool = False
) -> CLIIOProtocol:
    """
    Get or create appropriate IO interface.

    Args:
        io: Existing IO interface to use (takes precedence)
        test_mode: If True and no io provided, create TestIO

    Returns:
        CLIIOProtocol compatible interface
    """
    if io is not None:
        return io
    if test_mode:
        return TestIO()
    return ClickIO()


def create_context_state(ctx) -> Dict[str, Any]:
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


def extract_context_options(ctx) -> Dict[str, Any]:
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


def initialize_cli_handlers(orchestrator, session_start: datetime) -> Dict[str, Any]:
    """
    Create and return all CLI component handlers.

    Args:
        orchestrator: AgentOrchestrator instance
        session_start: Session start datetime for display handler

    Returns:
        Dict with all 8 standard handlers
    """
    return {
        'display': CLIDisplay(orchestrator, session_start),
        'session_mgr': CLISessionManager(orchestrator),
        'codebase': CLICodebaseAnalysis(orchestrator),
        'tasks': CLITaskExecution(orchestrator),
        'multiprovider': CLIMultiProvider(orchestrator),
        'smart': CLISmartQuery(orchestrator),
        'agent_mgr': CLIAgentManager(orchestrator),
        'task_router': CLITaskRouterHandler(orchestrator),
    }


def create_cli_from_context(ctx, io: Optional[CLIIOProtocol] = None):
    """
    Create CLI instance from Click context object.

    Args:
        ctx: Click context object with configuration in ctx.obj
        io: Optional IO interface (creates ClickIO if not provided)

    Returns:
        CLI instance configured from context
    """
    from ..core import CLI

    options = extract_context_options(ctx)

    return CLI(
        brain=options['brain'],
        auto_explore=options['auto_explore'],
        context_aware=options['context_aware'],
        verbose_selection=options['verbose_selection'],
        show_provider_status=options['show_provider_status'],
        io=io
    )
