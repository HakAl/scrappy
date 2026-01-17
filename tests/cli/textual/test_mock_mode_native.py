"""
Native Textual tests for mock LLM mode.

Uses Textual's built-in run_test() and Pilot instead of external tui-test framework.
This is faster, more reliable, and allows direct widget state inspection.
"""

import os
import pytest
from unittest.mock import MagicMock

# Set mock mode BEFORE importing app
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


class TestMockModeNative:
    """Test mock LLM mode using Textual's native testing."""

    @pytest.mark.asyncio
    async def test_mock_mode_bypasses_wizard(self):
        """In mock mode, app should show main screen, not wizard."""
        app = create_test_app()

        async with app.run_test() as pilot:
            # Wait for app to initialize
            await pilot.pause()

            # Check we're on the main screen, not wizard
            # app.screen gives us the current active screen
            screen = app.screen
            screen_name = type(screen).__name__

            # In mock mode, should be MainAppScreen (not SetupWizardScreen)
            assert "Wizard" not in screen_name, f"Expected main screen, got {screen_name}"

    @pytest.mark.asyncio
    async def test_mock_mode_app_is_responsive(self):
        """App should respond to key presses in mock mode."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Try pressing escape - should not crash
            await pilot.press("escape")
            await pilot.pause()

            # App should still be running
            assert app.is_running

            # App should have exited
            # (run_test context manager handles cleanup)


class TestMockModeWithEnvVars:
    """Test mock mode respects environment variables."""

    @pytest.mark.asyncio
    async def test_custom_mock_response_env_var(self, monkeypatch):
        """SCRAPPY_MOCK_RESPONSE should customize mock responses."""
        monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
        monkeypatch.setenv("SCRAPPY_MOCK_RESPONSE", "Custom test response")

        # Verify the mock service picks up the env var
        from scrappy.orchestrator.mock_llm_service import MockLLMService

        service = MockLLMService()
        response, _ = service.completion_sync(
            model="fast",
            messages=[{"role": "user", "content": "test"}],
        )

        assert response.content == "Custom test response"
