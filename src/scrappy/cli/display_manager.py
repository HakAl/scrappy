"""
Display manager for coordinating between UnifiedIO and RichDashboard.

This module provides DisplayManager, which coordinates between simple
UnifiedIO output and full RichDashboard display, enabling seamless mode
switching based on configuration.

Protocol-First Design:
- Implements DisplayManagerProtocol for testability
- Depends on CLIIOProtocol and DashboardProtocol abstractions
- Fully injectable dependencies

Usage:
    from scrappy.cli.display_manager import DisplayManager
    from scrappy.cli.unified_io import UnifiedIO
    from scrappy.cli.rich_dashboard import RichDashboard

    # Create display manager with dashboard enabled
    display = DisplayManager(
        io=UnifiedIO(),
        dashboard=RichDashboard(),
        dashboard_enabled=True
    )

    # Use in handlers
    io = display.get_io()
    io.echo("Starting operation...")

    if display.is_dashboard_enabled():
        dashboard = display.get_dashboard()
        dashboard.set_state("thinking", "Analyzing...")
        dashboard.update_thought_process("Considering options...")
"""

from typing import Optional
from contextlib import contextmanager
from rich.live import Live

from .io_interface import CLIIOProtocol
from .protocols import DashboardProtocol
from .unified_io import UnifiedIO
from .rich_dashboard import RichDashboard


class DisplayManager:
    """
    Manages display output coordination between UnifiedIO and RichDashboard.

    Implements DisplayManagerProtocol for protocol-based dependency injection.
    Coordinates between simple output (UnifiedIO) and live dashboard display
    (RichDashboard), enabling mode switching at runtime.

    Responsibilities:
    - Provide access to IO and Dashboard interfaces
    - Manage dashboard enabled/disabled state
    - Provide context manager for Rich.Live dashboard display

    This class follows SOLID principles:
    - Single Responsibility: Only coordinates display modes
    - Open/Closed: Extensible via protocol implementation
    - Liskov Substitution: Fully substitutable via protocol
    - Interface Segregation: Focused protocol interface
    - Dependency Inversion: Depends on protocols, not concretions
    """

    def __init__(
        self,
        io: Optional[CLIIOProtocol] = None,
        dashboard: Optional[DashboardProtocol] = None,
        dashboard_enabled: bool = False,
    ):
        """
        Initialize display manager with IO and optional dashboard.

        Args:
            io: IO interface for output. Creates default UnifiedIO if not provided.
            dashboard: Optional dashboard interface. Creates default if enabled.
            dashboard_enabled: Whether dashboard mode is initially enabled.

        Design Notes:
            - Follows dependency injection pattern
            - Provides sensible defaults via factory methods
            - No side effects in constructor
        """
        self._io = io if io is not None else self._create_default_io()
        self._dashboard_enabled = dashboard_enabled

        if dashboard_enabled and dashboard is None:
            self._dashboard = self._create_default_dashboard()
        else:
            self._dashboard = dashboard

        self._live_context: Optional[Live] = None

    def _create_default_io(self) -> CLIIOProtocol:
        """Factory method for default IO.

        WARNING: This factory should ONLY be used by tests for convenience.
        Production code MUST inject IO via the constructor parameter.
        Creating multiple UnifiedIO instances breaks TUI mode routing.
        """
        return UnifiedIO()

    def _create_default_dashboard(self) -> DashboardProtocol:
        """Factory method for default dashboard."""
        return RichDashboard()

    def get_io(self) -> CLIIOProtocol:
        """
        Get the IO interface for output.

        Returns:
            CLIIOProtocol implementation (typically UnifiedIO)
        """
        return self._io

    def get_dashboard(self) -> Optional[DashboardProtocol]:
        """
        Get the dashboard interface if enabled.

        Returns:
            DashboardProtocol implementation or None if dashboard disabled
        """
        if not self._dashboard_enabled:
            return None
        return self._dashboard

    def is_dashboard_enabled(self) -> bool:
        """
        Check if dashboard mode is enabled.

        Returns:
            True if dashboard is available and enabled
        """
        return self._dashboard_enabled and self._dashboard is not None

    def enable_dashboard(self) -> None:
        """
        Enable dashboard mode.

        Creates default dashboard if none exists.
        """
        if self._dashboard is None:
            self._dashboard = self._create_default_dashboard()
        self._dashboard_enabled = True

    def disable_dashboard(self) -> None:
        """
        Disable dashboard mode.

        Dashboard instance is retained but not used.
        """
        self._dashboard_enabled = False

    @contextmanager
    def live_dashboard(self, refresh_per_second: int = 4):
        """
        Context manager for live dashboard display.

        Provides a Rich.Live context for the dashboard, enabling
        real-time updates during long-running operations.

        Args:
            refresh_per_second: Dashboard refresh rate (default 4)

        Yields:
            The dashboard instance for updates during operation

        Example:
            with display.live_dashboard():
                dashboard = display.get_dashboard()
                dashboard.set_state("executing")
                dashboard.append_terminal("$ running command...")
                # Long operation here
                dashboard.set_state("idle")

        Raises:
            RuntimeError: If dashboard is not enabled
        """
        if not self.is_dashboard_enabled():
            raise RuntimeError("Cannot create live dashboard context: dashboard is disabled")

        dashboard = self.get_dashboard()
        if dashboard is None:
            raise RuntimeError("Cannot create live dashboard context: dashboard is None")

        with Live(
            dashboard.get_renderable(),
            console=dashboard.console,
            refresh_per_second=refresh_per_second,
            transient=False
        ) as live:
            self._live_context = live
            try:
                yield dashboard
            finally:
                self._live_context = None

    def update_live_display(self) -> None:
        """
        Manually trigger a live display update.

        Useful when dashboard content changes and immediate refresh is needed.
        Only works when inside a live_dashboard() context.
        """
        if self._live_context and self._dashboard:
            self._live_context.update(self._dashboard.get_renderable())

    def reset(self) -> None:
        """
        Reset display manager to initial state.

        Resets both IO and dashboard if present.
        """
        if self._dashboard:
            self._dashboard.reset()
        self._live_context = None
