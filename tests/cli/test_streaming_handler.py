"""
Unit tests for CLI streaming handler (CLIStreamingOutput and handle_auto_route_streaming).

Tests the CLI streaming infrastructure including:
- CLIStreamingOutput implements StreamingOutputProtocol correctly
- Token streaming writes to IO immediately
- handle_auto_route_streaming routes and streams correctly
- Sync wrapper bridges async to sync correctly
"""

import pytest
from typing import Optional, Any, List
from unittest.mock import Mock, AsyncMock
from pathlib import Path

from scrappy.cli.task_router_handler import (
    CLIStreamingOutput,
    CLITaskRouterHandler,
    CLIIOInputAdapter,
)
from scrappy.orchestrator.types import StreamingConfig
from scrappy.task_router.strategies.base import ExecutionResult
from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.config import ClarificationConfig


# =============================================================================
# Mock Implementations
# =============================================================================

class MockCLIIO:
    """Mock CLI IO that captures all output."""

    def __init__(self):
        self.echoed: List[tuple] = []  # (message, kwargs)
        self.secho_calls: List[tuple] = []  # (message, kwargs)

    def echo(self, message: str = "", nl: bool = True) -> None:
        self.echoed.append((message, {"nl": nl}))

    def secho(self, message: str, fg: Optional[str] = None, bold: bool = False, nl: bool = True) -> None:
        self.secho_calls.append((message, {"fg": fg, "bold": bold, "nl": nl}))

    def prompt(self, text: str, default: str = "") -> str:
        return default

    def confirm(self, text: str, default: bool = False) -> bool:
        return default

    def style(self, text: str, **kwargs) -> str:
        return text


class MockTheme:
    """Mock theme for styling."""
    primary = "blue"
    success = "green"
    error = "red"
    warning = "yellow"
    info = "cyan"
    accent = "magenta"
    text = "white"


class MockRouter:
    """Mock router with streaming support."""

    def __init__(self, result: Optional[ExecutionResult] = None):
        self._result = result or ExecutionResult(
            success=True,
            output="Streamed response",
            execution_time=0.1,
            tokens_used=10,
            provider_used="mock",
            metadata={"streaming": True},
        )
        self.route_calls: List[str] = []
        self.route_streaming_calls: List[tuple] = []
        self.verbose = False

    def route(self, user_input: str) -> ExecutionResult:
        self.route_calls.append(user_input)
        return self._result

    async def route_streaming(self, user_input: str, output) -> ExecutionResult:
        self.route_streaming_calls.append((user_input, output))

        # Simulate streaming
        await output.stream_start(metadata={"task_type": "research"})
        await output.stream_token("Hello ")
        await output.stream_token("world")
        await output.stream_end(metadata={"tokens": 2})

        return self._result


class MockOrchestrator:
    """Mock orchestrator."""
    pass


# =============================================================================
# CLIStreamingOutput Tests
# =============================================================================

class TestCLIStreamingOutput:
    """Tests for CLIStreamingOutput class."""

    @pytest.mark.asyncio
    async def test_stream_start_sets_streaming_state(self):
        """Test that stream_start enables streaming state."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io, config=StreamingConfig(show_metadata=False))

        assert output._streaming is False
        await output.stream_start()
        assert output._streaming is True

    @pytest.mark.asyncio
    async def test_stream_token_buffers_until_newline(self):
        """Test that stream_token buffers tokens until newline."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io)

        await output.stream_start()
        await output.stream_token("Hello")

        # Token without newline is buffered, not written immediately
        assert len(io.echoed) == 0
        assert output._buffer == "Hello"

    @pytest.mark.asyncio
    async def test_stream_token_flushes_on_newline(self):
        """Test that stream_token flushes buffer when newline encountered."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io)

        await output.stream_start()
        await output.stream_token("Hello\n")

        # Line is flushed on newline
        assert len(io.echoed) == 1
        assert io.echoed[0][0] == "Hello"
        assert output._buffer == ""

    @pytest.mark.asyncio
    async def test_stream_token_increments_counter(self):
        """Test that stream_token increments token count."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io)

        await output.stream_start()
        assert output._token_count == 0

        await output.stream_token("a")
        assert output._token_count == 1

        await output.stream_token("b")
        assert output._token_count == 2

    @pytest.mark.asyncio
    async def test_stream_token_ignored_before_start(self):
        """Test that stream_token is ignored if stream not started."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io)

        # Don't call stream_start
        await output.stream_token("ignored")

        assert len(io.echoed) == 0

    @pytest.mark.asyncio
    async def test_stream_end_flushes_buffer(self):
        """Test that stream_end flushes remaining buffer."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io, config=StreamingConfig(show_metadata=False))

        await output.stream_start()
        await output.stream_token("Hello")  # No newline, stays in buffer
        await output.stream_end()

        # Buffer flushed on stream_end
        assert len(io.echoed) == 1
        assert io.echoed[0][0] == "Hello"

    @pytest.mark.asyncio
    async def test_stream_end_clears_streaming_state(self):
        """Test that stream_end clears streaming state."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io)

        await output.stream_start()
        assert output._streaming is True

        await output.stream_end()
        assert output._streaming is False

    @pytest.mark.asyncio
    async def test_show_metadata_on_start(self):
        """Test that metadata is shown on stream_start when enabled."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io, config=StreamingConfig(show_metadata=True), theme=MockTheme())

        await output.stream_start(metadata={"task_type": "research", "strategy": "ResearchExecutor"})

        assert len(io.secho_calls) == 1
        assert "[Streaming: research via ResearchExecutor]" in io.secho_calls[0][0]

    @pytest.mark.asyncio
    async def test_show_metadata_on_end(self):
        """Test that metadata is shown on stream_end when enabled."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io, config=StreamingConfig(show_metadata=True), theme=MockTheme())

        await output.stream_start()
        await output.stream_token("Hello")
        await output.stream_end(metadata={"tokens": 10})

        # Should have secho call for completion
        assert any("[Stream complete: 10 tokens]" in call[0] for call in io.secho_calls)

    @pytest.mark.asyncio
    async def test_full_streaming_lifecycle(self):
        """Test complete streaming lifecycle with buffering."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io, config=StreamingConfig(show_metadata=False))

        await output.stream_start()
        await output.stream_token("Hello ")
        await output.stream_token("world")
        await output.stream_token("!")
        await output.stream_end()

        # Tokens without newlines are buffered, flushed together at end
        assert len(io.echoed) == 1
        assert io.echoed[0][0] == "Hello world!"

    @pytest.mark.asyncio
    async def test_multiline_streaming(self):
        """Test streaming with multiple lines."""
        io = MockCLIIO()
        output = CLIStreamingOutput(io, config=StreamingConfig(show_metadata=False))

        await output.stream_start()
        await output.stream_token("Line 1\n")
        await output.stream_token("Line 2\n")
        await output.stream_token("Partial")
        await output.stream_end()

        # Two complete lines + final partial
        assert len(io.echoed) == 3
        assert io.echoed[0][0] == "Line 1"
        assert io.echoed[1][0] == "Line 2"
        assert io.echoed[2][0] == "Partial"

    @pytest.mark.asyncio
    async def test_buffer_threshold_flush(self):
        """Test that buffer flushes when exceeding threshold."""
        io = MockCLIIO()
        # Use explicit buffer threshold of 80
        output = CLIStreamingOutput(io, config=StreamingConfig(buffer_threshold=80, show_metadata=False))

        await output.stream_start()
        # Send enough tokens to exceed 80 char threshold
        long_text = "x" * 85
        await output.stream_token(long_text)

        # Should have flushed due to length threshold
        assert len(io.echoed) == 1
        assert io.echoed[0][0] == long_text
        assert output._buffer == ""

    @pytest.mark.asyncio
    async def test_token_delay_config(self):
        """Test that token_delay_ms is respected from config."""
        io = MockCLIIO()
        # Use readable config with delay
        output = CLIStreamingOutput(io, config=StreamingConfig.readable())

        await output.stream_start()
        # Should apply delay (we can't easily test timing, but verify config is used)
        assert output._config.token_delay_ms == 20  # readable() uses 20ms
        await output.stream_token("test")
        await output.stream_end()


# =============================================================================
# handle_auto_route_streaming Tests
# =============================================================================

class TestHandleAutoRouteStreaming:
    """Tests for handle_auto_route_streaming method."""

    @pytest.fixture
    def handler_with_mock_router(self):
        """Create handler with mock router."""
        io = MockCLIIO()
        orchestrator = MockOrchestrator()
        router = MockRouter()

        handler = CLITaskRouterHandler(
            orchestrator=orchestrator,
            io=io,
            project_root=Path("/test"),
            router=router,
            theme=MockTheme(),
        )

        return handler, router, io

    @pytest.mark.asyncio
    async def test_streaming_calls_route_streaming(self, handler_with_mock_router):
        """Test that handle_auto_route_streaming calls router.route_streaming."""
        handler, router, io = handler_with_mock_router

        await handler.handle_auto_route_streaming("test query")

        assert len(router.route_streaming_calls) == 1
        assert router.route_streaming_calls[0][0] == "test query"

    @pytest.mark.asyncio
    async def test_streaming_creates_default_output(self, handler_with_mock_router):
        """Test that default CLIStreamingOutput is created."""
        handler, router, io = handler_with_mock_router

        await handler.handle_auto_route_streaming("test query")

        # Verify output was passed to route_streaming
        output = router.route_streaming_calls[0][1]
        assert isinstance(output, CLIStreamingOutput)

    @pytest.mark.asyncio
    async def test_streaming_uses_custom_output(self, handler_with_mock_router):
        """Test that custom output is used when provided."""
        handler, router, io = handler_with_mock_router

        custom_output = Mock()
        custom_output.stream_start = AsyncMock()
        custom_output.stream_token = AsyncMock()
        custom_output.stream_end = AsyncMock()

        await handler.handle_auto_route_streaming("test query", output=custom_output)

        # Verify custom output was passed
        output = router.route_streaming_calls[0][1]
        assert output is custom_output

    @pytest.mark.asyncio
    async def test_streaming_returns_result(self, handler_with_mock_router):
        """Test that handle_auto_route_streaming returns ExecutionResult."""
        handler, router, io = handler_with_mock_router

        result = await handler.handle_auto_route_streaming("test query")

        assert result.success is True
        assert result.output == "Streamed response"

    @pytest.mark.asyncio
    async def test_streaming_tracks_history(self, handler_with_mock_router):
        """Test that streaming result is tracked in history."""
        handler, router, io = handler_with_mock_router

        await handler.handle_auto_route_streaming("test query")

        assert len(handler.history) == 1
        assert handler.history[0]["input"] == "test query"

    @pytest.mark.asyncio
    async def test_streaming_respects_verbose_setting(self, handler_with_mock_router):
        """Test that verbose setting is passed to router."""
        handler, router, io = handler_with_mock_router

        # Create mock session context
        mock_session = Mock()
        mock_session.verbose_mode = True
        handler.session_context = mock_session

        await handler.handle_auto_route_streaming("test query")

        assert router.verbose is True


class TestHandleAutoRouteStreamingSync:
    """Tests for the synchronous wrapper."""

    def test_sync_wrapper_calls_async(self):
        """Test that sync wrapper properly calls async method."""
        io = MockCLIIO()
        orchestrator = MockOrchestrator()
        router = MockRouter()

        handler = CLITaskRouterHandler(
            orchestrator=orchestrator,
            io=io,
            project_root=Path("/test"),
            router=router,
            theme=MockTheme(),
        )

        result = handler.handle_auto_route_streaming_sync("test query")

        assert result.success is True
        assert len(router.route_streaming_calls) == 1


# =============================================================================
# CLIIOInputAdapter Tests
# =============================================================================

class TestCLIIOInputAdapter:
    """Tests for CLIIOInputAdapter class."""

    def test_prompt_delegates_to_io(self):
        """Test that prompt delegates to IO."""
        io = MockCLIIO()
        adapter = CLIIOInputAdapter(io)

        result = adapter.prompt("Enter value:", default="default")

        assert result == "default"

    def test_confirm_delegates_to_io(self):
        """Test that confirm delegates to IO."""
        io = MockCLIIO()
        adapter = CLIIOInputAdapter(io)

        result = adapter.confirm("Continue?", default=True)

        assert result is True

    def test_output_delegates_to_echo(self):
        """Test that output delegates to echo."""
        io = MockCLIIO()
        adapter = CLIIOInputAdapter(io)

        adapter.output("Test message")

        assert len(io.echoed) == 1
        assert io.echoed[0][0] == "Test message"
