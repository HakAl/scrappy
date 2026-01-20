"""
Pilot test for metrics status updates in the TUI.
"""

import os
import pytest

from textual.css.query import NoMatches
from textual.widgets import Label

# Set mock mode before importing app and CLI
os.environ["SCRAPPY_MOCK_LLM"] = "1"
os.environ["SCRAPPY_MOCK_TOKENS"] = "64"
os.environ["SCRAPPY_MOCK_LATENCY_MS"] = "0"
os.environ["SCRAPPY_MOCK_RESPONSE"] = "Mock response"

from scrappy.cli.core import CLI
from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.screens import MainAppScreen, SetupWizardScreen
from scrappy.cli.screens.chat_layout import ChatLayout


def create_test_app() -> ScrappyApp:
    """Create a ScrappyApp instance with a real CLI in mock mode."""
    return ScrappyApp(cli_factory=lambda: CLI())


class TestMetricsStatusPilot:
    """Tests that metrics update after sending input."""

    @pytest.mark.asyncio
    async def test_metrics_status_updates_after_message(self):
        """Metrics line should update after an LLM response."""
        app = create_test_app()

        async with app.run_test() as pilot:
            for _ in range(50):
                if app.ready:
                    break
                await pilot.pause(delay=0.1)

            assert app.ready is True

            for _ in range(50):
                if isinstance(app.screen, MainAppScreen):
                    break
                await pilot.pause(delay=0.1)

            if isinstance(app.screen, SetupWizardScreen):
                app._show_main_screen()
                for _ in range(50):
                    if isinstance(app.screen, MainAppScreen):
                        break
                    await pilot.pause(delay=0.1)

            assert isinstance(app.screen, MainAppScreen)

            status_bar_found = False
            for _ in range(50):
                try:
                    # Query from screen which is more direct
                    screen = app.screen
                    screen.query_one(ChatLayout)
                    screen.query_one("#status_bar")
                    status_bar_found = True
                    break
                except NoMatches:
                    await pilot.pause(delay=0.1)

            assert status_bar_found is True, f"Screen type: {type(app.screen).__name__}"

            await pilot.press("h", "i")
            await pilot.press("enter")

            metrics_text = ""
            for _ in range(50):
                await pilot.pause(delay=0.1)
                try:
                    label = app.screen.query_one("#metrics_status", Label)
                except NoMatches:
                    continue
                # Get label content - use render() and convert to plain text
                from rich.console import Console
                from io import StringIO
                console = Console(file=StringIO(), force_terminal=False, width=200)
                console.print(label.render())
                metrics_text = console.file.getvalue().strip()
                # New format uses "in:-- out:--" instead of "--/--"
                if "mock:" in metrics_text and "in:--" not in metrics_text:
                    break

            assert "mock:" in metrics_text, f"Expected 'mock:' in metrics, got: {metrics_text}"
            assert "in:--" not in metrics_text, f"Expected no 'in:--' placeholder, got: {metrics_text}"
