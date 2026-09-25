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
from ..agent_manager import CLIAgentManager
from ..context_commands import CLIContextCommands
from ..cache_manager import CacheManager
from ..rate_limiter import RateLimiter
from ..persistence import SessionPersistence
from ..user_interaction import get_user_interaction
from scrappy.infrastructure.config.api_keys import ApiKeyConfigServiceProtocol
from scrappy.infrastructure.persistence import ConversationStore
from scrappy.infrastructure.protocols import PathProviderProtocol
from scrappy.infrastructure.theme import ThemeProtocol, DEFAULT_THEME

if TYPE_CHECKING:
    from ..config_factory import CLIConfig
    from ..core import CLI
    from ...orchestrator.protocols import Orchestrator
    from ..textual import ThreadSafeAsyncBridge


def create_conversation_store(
    orchestrator: "Orchestrator",
    *,
    path_provider: Optional[PathProviderProtocol] = None,
) -> Optional[ConversationStore]:
    """
    Create ConversationStore, preferring an explicitly supplied path provider.

    CONTRACT B (scrappy-su47). When a provider is EXPLICITLY supplied it owns the
    destination and the store is created under ``provider.data_dir()``, which is
    where ``conversations.db`` and its companion ``config.json`` project identity
    belong. When no provider is supplied the LEGACY destination is preserved
    exactly: ``orchestrator.context.project_path / ".scrappy"``.

    That distinction is load-bearing and is why the parameter is the CALLER'S
    EXPLICIT provider rather than a resolved one. ``CLI`` builds its default
    provider from the CWD, while this helper has always followed the
    orchestrator's project path. Forwarding a CWD-derived default here would MOVE
    the database for the supported configuration where an injected orchestrator
    points somewhere other than the CWD.

    ``data_dir()`` is an existing member of ``PathProviderProtocol``; no new
    protocol member is introduced. The parameter is KEYWORD-ONLY and appended
    after the existing positional one, so every standalone
    ``create_conversation_store(orchestrator)`` call keeps working unchanged.

    Args:
        orchestrator: AgentOrchestrator instance with context
        path_provider: Explicitly supplied provider, or None to preserve the
            legacy orchestrator-derived destination. Held with an ``is None``
            check so a falsey-but-valid provider is not silently discarded.

    Returns:
        Initialized ConversationStore or None if creation fails
    """
    try:
        if path_provider is not None:
            scrappy_dir = path_provider.data_dir()
        else:
            # Get .scrappy directory from project path
            project_path = orchestrator.context.project_path
            scrappy_dir = project_path / ".scrappy"

        # Use factory method for initialization
        return ConversationStore.create(scrappy_dir)
    except Exception:
        # Graceful degradation - conversation persistence is optional
        return None


def get_io_interface(
    io: Optional[CLIIOProtocol] = None,
    test_mode: bool = False,
    theme: Optional[ThemeProtocol] = None
) -> CLIIOProtocol:
    """
    Get or create appropriate IO interface for CLI (interactive mode).

    CLI always uses Textual, so this creates UnifiedIO with OutputSink.

    Args:
        io: Existing IO interface to use (takes precedence)
        test_mode: If True and no io provided, create TestIO
        theme: Optional theme for styling. Defaults to DEFAULT_THEME.

    Returns:
        CLIIOProtocol compatible interface with Textual OutputSink
    """
    if io is not None:
        return io
    if test_mode:
        return TestIO()

    # CLI === Textual (interactive mode)
    # Create UnifiedIO with OutputSink for Textual routing
    from ..textual import TextualOutputAdapter
    output_adapter = TextualOutputAdapter()
    return UnifiedIO(output_sink=output_adapter, theme=theme or DEFAULT_THEME)


def create_context_state(ctx: Any) -> Dict[str, Any]:
    """
    Create context state dict from Click context.

    Extracts all standard configuration values with sensible defaults.

    Args:
        ctx: Click context object

    Returns:
        Dict with all 6 standard configuration keys
    """
    obj = ctx.obj if ctx.obj is not None else {}

    return {
        'brain': obj.get('brain'),
        'auto_explore': obj.get('auto_explore', False),
        'context_aware': obj.get('context_aware', True),
        'resume': obj.get('resume', False),
        'auto_save': obj.get('auto_save', True),
        'show_providers': obj.get('show_providers', False),
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
        'show_provider_status': obj.get('show_providers', False),
    }


def initialize_cli_handlers(
    orchestrator: "Orchestrator",
    session_start: datetime,
    io: CLIIOProtocol,
    bridge: Optional["ThreadSafeAsyncBridge"] = None,
    theme: Optional[ThemeProtocol] = None,
    *,
    api_key_service: ApiKeyConfigServiceProtocol,
    code_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create and return all CLI component handlers.

    Args:
        orchestrator: AgentOrchestrator instance
        session_start: Session start datetime for display handler
        io: I/O interface for output
        bridge: Optional ThreadSafeAsyncBridge for TUI mode modal dialogs
        theme: Optional theme for styling. Defaults to DEFAULT_THEME.
        api_key_service: API key config service handed to the display handler
        code_root: Code working directory captured once at CLI composition, forwarded
            to CLIAgentManager. Keyword-only, joining the existing keyword-only
            section, so no positional caller is affected.

    Returns:
        Dict with all 8 standard handlers
    """
    theme = theme or DEFAULT_THEME

    # Create session manager dependencies first (all need io)
    context_manager = CLIContextCommands(orchestrator, io, theme=theme)
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

    # Get mode-aware user interaction handler
    interaction = get_user_interaction(io, bridge)

    return {
        'display': CLIDisplay(orchestrator, session_start, io, api_key_service),
        'session_mgr': session_mgr,
        'codebase': CLICodebaseAnalysis(orchestrator, io),
        'tasks': CLITaskExecution(orchestrator, io),
        'agent_mgr': CLIAgentManager(orchestrator, io, interaction, code_root=code_root),
    }


def create_cli_from_context(
    ctx: Any,
    io: Optional[CLIIOProtocol] = None,
    theme: Optional[ThemeProtocol] = None,
    path_provider: Optional[PathProviderProtocol] = None,
    api_key_service: Optional[ApiKeyConfigServiceProtocol] = None,
    cli_config: Optional["CLIConfig"] = None
) -> "CLI":
    """
    Create CLI instance from Click context object.

    Args:
        ctx: Click context object with configuration in ctx.obj
        io: IO interface
        theme: Optional theme for styling. Defaults to DEFAULT_THEME.
        path_provider: Path provider threaded to the CLI (default: CLI builds one).
        api_key_service: API key config service threaded to the CLI
            (default: CLI builds one).

    Returns:
        CLI instance configured from context
    """
    from ..core import CLI

    options = extract_context_options(ctx)
    theme = theme or DEFAULT_THEME

    cli = CLI(
        brain=options['brain'],
        auto_explore=options['auto_explore'],
        context_aware=options['context_aware'],
        show_provider_status=options['show_provider_status'],
        io=io,
        theme=theme,
        path_provider=path_provider,
        api_key_service=api_key_service,
        cli_config=cli_config
    )
    cli.initialize()
    return cli


def create_cli(
    config: Dict[str, Any],
    io: Optional[CLIIOProtocol] = None,
    theme: Optional[ThemeProtocol] = None,
    path_provider: Optional[PathProviderProtocol] = None,
    api_key_service: Optional[ApiKeyConfigServiceProtocol] = None
) -> "CLI":
    """
    Create CLI instance from a simple dictionary configuration.

    This is a convenience function for creating CLI instances without
    needing a Click context object. Useful for programmatic usage and testing.

    Args:
        config: Dictionary with configuration options:
            - brain: Provider to use as brain (default None)
            - auto_explore: Auto-explore on startup (default False)
            - context_aware: Enable context-aware prompts (default True)
            - show_provider_status: Show provider status on startup (default False)
        io: IO interface (creates if not provided)
        theme: Optional theme for styling. Defaults to DEFAULT_THEME.
        path_provider: Path provider threaded to the CLI (default: CLI builds one).
        api_key_service: API key config service threaded to the CLI
            (default: CLI builds one).

    Returns:
        CLI instance configured from dict

    Example:
        cli = create_cli({'brain': 'cerebras', 'auto_explore': True})
    """
    from ..core import CLI

    theme = theme or DEFAULT_THEME

    cli = CLI(
        brain=config.get('brain'),
        auto_explore=config.get('auto_explore', False),
        context_aware=config.get('context_aware', True),
        show_provider_status=config.get('show_provider_status', False),
        io=io,
        theme=theme,
        path_provider=path_provider,
        api_key_service=api_key_service
    )
    cli.initialize()
    return cli
