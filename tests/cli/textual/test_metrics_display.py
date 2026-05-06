"""
Tests for metrics display using Textual pilot.

Verifies that MetricsUpdated events are received and displayed in the UI.
This tests the data flow from langgraph_bridge to the status bar.
"""

import pytest
from unittest.mock import MagicMock, Mock

from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.textual.tui_events import MetricsUpdated
from scrappy.cli.textual.status_components import MetricsStatus


@pytest.fixture(autouse=True)
def force_mock_mode(monkeypatch):
    """Run metrics screen tests on the main screen path."""
    monkeypatch.setattr(
        "scrappy.orchestrator.mock_llm_service.is_mock_mode_enabled",
        lambda: True,
    )


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


class TestMetricsStatusComponent:
    """Unit tests for MetricsStatus component."""

    def test_format_metrics_with_all_values(self):
        """MetricsStatus should format all values correctly."""
        status = MetricsStatus()
        status.update(
            provider_display="cerebras: llama-3.3-70b",
            input_tokens=1000,
            output_tokens=250,
            session_total=1250,
            context_percent=15,
        )

        formatted = status._format_metrics()
        assert "cerebras: llama-3.3-70b" in formatted
        assert "in:1,000" in formatted  # input tokens with label
        assert "out:250" in formatted  # output tokens with label
        assert "session:1,250" in formatted  # session total with label
        assert "ctx:15%" in formatted  # context percent with label

    def test_format_metrics_with_none_values(self):
        """MetricsStatus should show '--' for None values."""
        status = MetricsStatus()
        status.update(
            provider_display="cerebras: llama-3.3-70b",
            input_tokens=None,
            output_tokens=None,
            session_total=None,
            context_percent=None,
        )

        formatted = status._format_metrics()
        assert "cerebras: llama-3.3-70b" in formatted
        assert "--" in formatted  # None values show as --

    def test_format_metrics_provider_only(self):
        """MetricsStatus should show provider even when tokens are None."""
        status = MetricsStatus()
        status.update(
            provider_display="groq: llama-3.1-8b",
            input_tokens=None,
            output_tokens=None,
            session_total=None,
            context_percent=None,
        )

        formatted = status._format_metrics()
        assert "groq: llama-3.1-8b" in formatted


class TestMetricsUpdatedEvent:
    """Tests for MetricsUpdated event handling."""

    @pytest.mark.asyncio
    async def test_metrics_update_reaches_screen(self):
        """MetricsUpdated event should update the status bar."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            app.tui_event_sink.post_event(MetricsUpdated(
                provider_display="cerebras: llama-3.3-70b",
                input_tokens=500,
                output_tokens=100,
                session_total=600,
                context_percent=10,
            ))
            await pilot.pause()

            # Get the main screen
            from scrappy.cli.screens import MainAppScreen
            screen = app.screen
            if isinstance(screen, MainAppScreen):
                # Check that metrics_status was updated
                assert screen.metrics_status._provider_display == "cerebras: llama-3.3-70b"
                assert screen.metrics_status._input_tokens == 500
                assert screen.metrics_status._output_tokens == 100
                assert screen.metrics_status._session_total == 600

    @pytest.mark.asyncio
    async def test_metrics_update_with_none_tokens(self):
        """MetricsUpdated with None tokens should still update provider."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            app.tui_event_sink.post_event(MetricsUpdated(
                provider_display="groq: llama-3.1-70b",
                input_tokens=None,
                output_tokens=None,
                session_total=None,
                context_percent=None,
            ))
            await pilot.pause()

            # Get the main screen
            from scrappy.cli.screens import MainAppScreen
            screen = app.screen
            if isinstance(screen, MainAppScreen):
                # Provider should be updated even with None tokens
                assert screen.metrics_status._provider_display == "groq: llama-3.1-70b"


class TestMetricsIntegrationWithBridge:
    """Integration tests for metrics flow from bridge to UI."""

    @pytest.mark.asyncio
    async def test_bridge_posts_metrics_on_think_complete(self):
        """Bridge should post MetricsUpdated after think node completes."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Simulate what the bridge does after think node
            # This is the exact code path from langgraph_bridge._post_metrics_update
            from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

            # Create a minimal bridge mock that can post messages
            mock_bridge = Mock()
            mock_output_adapter = Mock()
            mock_output_adapter.write = Mock()
            mock_orchestrator = Mock()
            mock_tool_adapter = Mock()

            bridge = LangGraphBridge(
                app=app,
                bridge=mock_bridge,
                output_adapter=mock_output_adapter,
                orchestrator=mock_orchestrator,
                tool_adapter=mock_tool_adapter,
            )

            # Call the internal method that posts metrics
            bridge._post_metrics_update(
                provider_display="test: model",
                input_tokens=100,
                output_tokens=50,
                context_percent=5,
            )
            await pilot.pause()

            # Verify the screen received the update
            from scrappy.cli.screens import MainAppScreen
            screen = app.screen
            if isinstance(screen, MainAppScreen):
                assert screen.metrics_status._provider_display == "test: model"
                assert screen.metrics_status._input_tokens == 100
                assert screen.metrics_status._output_tokens == 50

    @pytest.mark.asyncio
    async def test_bridge_posts_metrics_without_tokens(self):
        """Bridge should post metrics even when tokens are None."""
        app = create_test_app()

        async with app.run_test() as pilot:
            await pilot.pause()

            from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

            mock_bridge = Mock()
            mock_output_adapter = Mock()
            mock_output_adapter.write = Mock()
            mock_orchestrator = Mock()
            mock_tool_adapter = Mock()

            bridge = LangGraphBridge(
                app=app,
                bridge=mock_bridge,
                output_adapter=mock_output_adapter,
                orchestrator=mock_orchestrator,
                tool_adapter=mock_tool_adapter,
            )

            # Post with provider only, no tokens
            bridge._post_metrics_update(
                provider_display="cerebras: llama-3.3-70b",
                input_tokens=None,
                output_tokens=None,
                context_percent=None,
            )
            await pilot.pause()

            from scrappy.cli.screens import MainAppScreen
            screen = app.screen
            if isinstance(screen, MainAppScreen):
                # Provider should still be set
                assert screen.metrics_status._provider_display == "cerebras: llama-3.3-70b"
