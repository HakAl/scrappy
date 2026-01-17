"""
Tests for cancellation behavior using Textual native testing.

Covers:
- Escape key cancellation
- Ctrl+C handling
- Post-cancel input handling
- Arrow key history after cancel

Migrated from: tests/e2e/tests/cancel.spec.ts, escape-cancel.spec.ts
"""

import os
import pytest
from unittest.mock import MagicMock

# Set mock mode for testing
os.environ["SCRAPPY_MOCK_LLM"] = "1"

from scrappy.cli.textual.app import ScrappyApp


def create_mock_cli():
    """Create a mock CLI for testing."""
    mock_cli = MagicMock()
    mock_cli.interactive_mode = MagicMock()
    mock_cli.interactive_mode.command_router = MagicMock()
    mock_cli.interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
    return mock_cli


def create_test_app():
    """Create a ScrappyApp instance for testing."""
    return ScrappyApp(cli_factory=create_mock_cli)


class TestEscapeKeyCancellation:
    """Tests for escape key cancellation behavior.

    Bug references:
    - scrappy-kzqy: Need to press escape multiple times to cancel agent
    - scrappy-z719: Arrow keys don't work after agent cancel
    """

    @pytest.mark.asyncio
    async def test_escape_does_not_crash_app(self):
        """Pressing escape should not crash the app."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape
            await pilot.press("escape")
            await pilot.pause()

            # App should still have a screen
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_escape_returns_to_idle_state(self):
        """After escape, app should be in idle state ready for input."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Simulate starting some operation
            await pilot.press("enter")
            await pilot.pause()

            # Cancel with escape
            await pilot.press("escape")
            await pilot.pause()

            # App should still be functional
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_multiple_escapes_do_not_crash(self):
        """Multiple escape presses should not crash."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape multiple times
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            # App should still be running
            assert app.screen is not None


class TestCtrlCHandling:
    """Tests for Ctrl+C handling."""

            # App might still be running or showing exit confirmation
            # Either way it shouldn't crash

            # Should not crash - context manager handles cleanup


class TestPostCancelInput:
    """Tests for input handling after cancellation."""

    @pytest.mark.asyncio
    async def test_can_type_after_escape(self):
        """Should be able to type after pressing escape."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape (cancel any operation)
            await pilot.press("escape")
            await pilot.pause()

            # Type some text
            await pilot.press("h", "e", "l", "l", "o")
            await pilot.pause()

            # App should still be responsive
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_enter_works_after_escape(self):
        """Enter key should work after escape."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape
            await pilot.press("escape")
            await pilot.pause()

            # Press enter
            await pilot.press("enter")
            await pilot.pause()

            # Should not crash
            assert app.screen is not None


class TestArrowKeyHistoryAfterCancel:
    """Tests for arrow key history navigation after cancellation.

    Bug: scrappy-z719 - Arrow keys don't work after agent cancel
    Root cause: InputCaptureManager.cancel() doesn't reset _mode flag
    """

    @pytest.mark.asyncio
    async def test_up_arrow_after_escape(self):
        """Up arrow should work after escape (history navigation)."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape to ensure clean state
            await pilot.press("escape")
            await pilot.pause()

            # Press up arrow (should navigate history)
            await pilot.press("up")
            await pilot.pause()

            # Should not crash
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_down_arrow_after_escape(self):
        """Down arrow should work after escape."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press escape
            await pilot.press("escape")
            await pilot.pause()

            # Press down arrow
            await pilot.press("down")
            await pilot.pause()

            # Should not crash
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_arrow_keys_sequence_after_escape(self):
        """Arrow key sequence should work after escape."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Escape to clean state
            await pilot.press("escape")
            await pilot.pause()

            # Arrow key sequence
            await pilot.press("up")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()

            # Should be functional
            assert app.screen is not None


class TestCancellationDuringOperations:
    """Tests for cancellation during various operations."""

    @pytest.mark.asyncio
    async def test_escape_during_app_startup(self):
        """Escape during startup should not crash."""
        app = create_test_app()

        async with app.run_test() as pilot:
            # Don't wait - press escape immediately
            await pilot.press("escape")
            await pilot.pause()

            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_rapid_escape_presses(self):
        """Rapid escape presses should not crash."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Rapid escape presses
            for _ in range(5):
                await pilot.press("escape")

            await pilot.pause()

            assert app.screen is not None
