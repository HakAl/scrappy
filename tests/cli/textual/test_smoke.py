"""
Smoke tests for Scrappy TUI using Textual native testing.

These tests verify basic app functionality works:
- App starts without crashing
- Correct screen is shown based on configuration
- Basic keyboard interactions work
- App exits cleanly

Run with: python -m pytest tests/cli/textual/test_smoke.py -v
"""

import os
import pytest
from unittest.mock import MagicMock

# Set mock mode for testing (must be before app import)
os.environ["SCRAPPY_MOCK_LLM"] = "1"

from scrappy.cli.textual.app import ScrappyApp


def create_mock_cli():
    """Create a mock CLI for testing.

    The CLI is needed for ScrappyApp initialization.
    We mock it to avoid real LLM/API dependencies.
    """
    mock_cli = MagicMock()
    mock_cli.interactive_mode = MagicMock()
    mock_cli.interactive_mode.command_router = MagicMock()
    mock_cli.interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
    return mock_cli


def create_test_app():
    """Create a ScrappyApp instance for testing."""
    return ScrappyApp(cli_factory=create_mock_cli)


class TestAppStartup:
    """Tests for app startup behavior."""

    @pytest.mark.asyncio
    async def test_app_starts_without_crashing(self):
        """App should start and initialize without errors."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # App should have a screen
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_app_shows_screen_on_startup(self):
        """App should display a screen after startup."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Should have an active screen
            screen = app.screen
            screen_name = type(screen).__name__

            # In mock mode, should show main screen (not wizard)
            # Accept any screen that isn't an error state
            assert screen_name != ""
            assert "Error" not in screen_name

    @pytest.mark.asyncio
    async def test_mock_mode_bypasses_wizard(self):
        """With SCRAPPY_MOCK_LLM=1, app should skip wizard."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            screen_name = type(app.screen).__name__

            # Should NOT be on wizard screen
            assert "Wizard" not in screen_name, \
                f"Mock mode should bypass wizard, got {screen_name}"


class TestKeyboardInteraction:
    """Tests for basic keyboard interactions."""

    @pytest.mark.asyncio
    async def test_escape_key_does_not_crash(self):
        """Pressing escape should not crash the app."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape
            await pilot.press("escape")
            await pilot.pause()

            # App should still be running
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_enter_key_does_not_crash(self):
        """Pressing enter should not crash the app."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press enter (might submit empty input)
            await pilot.press("enter")
            await pilot.pause()

            # App should still be running
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_arrow_keys_do_not_crash(self):
        """Arrow keys should not crash the app."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press various arrow keys
            await pilot.press("up")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()

            # App should still be running
            assert app.screen is not None


class TestAppExit:
    """Tests for app exit behavior."""

    @pytest.mark.asyncio
    async def test_app_exit_method_works(self):
        """Calling app.exit() should cleanly exit."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Request exit
            app.exit()
            await pilot.pause()

            # Context manager will clean up

    @pytest.mark.asyncio
    async def test_ctrl_c_does_not_crash(self):
        """Ctrl+C should not crash (may show exit prompt)."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Ctrl+C
            await pilot.press("ctrl+c")
            await pilot.pause()

            # App might still be running (waiting for confirmation)
            # or might have started exit process
            # Either way, it shouldn't crash


class TestAppState:
    """Tests for app state inspection."""

    @pytest.mark.asyncio
    async def test_app_has_output_adapter(self):
        """App should have an output adapter."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.output_adapter is not None

    @pytest.mark.asyncio
    async def test_app_has_bridge(self):
        """App should have async bridge for prompts."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.bridge is not None
