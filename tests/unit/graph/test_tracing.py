"""Unit tests for tracing module."""

import pytest

from scrappy.graph.tracing import (
    NoOpSpan,
    NoOpTracer,
    get_tracer,
    trace_node,
    trace_context,
    is_tracing_enabled,
    shutdown_tracing,
)


class TestNoOpSpan:
    """Tests for NoOpSpan behavior."""

    def test_init_with_name(self) -> None:
        """NoOpSpan stores the name."""
        span = NoOpSpan("test-span")
        assert span.name == "test-span"

    def test_init_with_empty_name(self) -> None:
        """NoOpSpan accepts empty name."""
        span = NoOpSpan("")
        assert span.name == ""

    def test_context_manager_protocol(self) -> None:
        """NoOpSpan works as context manager."""
        span = NoOpSpan("test")
        with span as s:
            assert s is span  # Multiple calls should be safe


class TestNoOpTracer:
    """Tests for NoOpTracer behavior."""

    def test_trace_returns_noop_span(self) -> None:
        """trace() returns a NoOpSpan."""
        tracer = NoOpTracer()
        span = tracer.trace("test-trace")
        assert isinstance(span, NoOpSpan)
        assert span.name == "test-trace"

    def test_span_returns_noop_span(self) -> None:
        """span() returns a NoOpSpan."""
        tracer = NoOpTracer()
        span = tracer.span("test-span")
        assert isinstance(span, NoOpSpan)
        assert span.name == "test-span"

    def test_generation_returns_noop_span(self) -> None:
        """generation() returns a NoOpSpan."""
        tracer = NoOpTracer()
        span = tracer.generation("test-gen")
        assert isinstance(span, NoOpSpan)
        assert span.name == "test-gen"  # Multiple calls should be safe

    def test_trace_accepts_kwargs(self) -> None:
        """trace() accepts arbitrary kwargs."""
        tracer = NoOpTracer()
        span = tracer.trace("test", metadata={"key": "value"}, user_id="123")
        assert isinstance(span, NoOpSpan)

    def test_span_accepts_kwargs(self) -> None:
        """span() accepts arbitrary kwargs."""
        tracer = NoOpTracer()
        span = tracer.span("test", parent_id="abc", level="debug")
        assert isinstance(span, NoOpSpan)

    def test_generation_accepts_kwargs(self) -> None:
        """generation() accepts arbitrary kwargs."""
        tracer = NoOpTracer()
        span = tracer.generation("test", model="gpt-4", tokens=100)
        assert isinstance(span, NoOpSpan)


class TestGetTracer:
    """Tests for get_tracer function."""

    def test_caches_tracer_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tracer returns the same instance on subsequent calls."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        tracer1 = get_tracer()
        tracer2 = get_tracer()
        assert tracer1 is tracer2


class TestIsTracingEnabled:
    """Tests for is_tracing_enabled function."""

    def test_returns_false_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without API keys, tracing is not enabled."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        assert is_tracing_enabled() is False


class TestTraceNodeDecorator:
    """Tests for trace_node decorator."""

    def test_decorator_preserves_function_behavior(self) -> None:
        """Decorated function returns the same result."""
        @trace_node("test-node")
        def sample_function(x: int, y: int) -> int:
            return x + y

        result = sample_function(2, 3)
        assert result == 5

    def test_decorator_preserves_function_name(self) -> None:
        """Decorated function keeps its name."""
        @trace_node("test-node")
        def sample_function() -> str:
            return "hello"

        assert sample_function.__name__ == "sample_function"

    def test_decorator_works_with_kwargs(self) -> None:
        """Decorated function handles kwargs correctly."""
        @trace_node("test-node")
        def sample_function(a: int, b: int = 10) -> int:
            return a * b

        assert sample_function(5) == 50
        assert sample_function(5, b=20) == 100


class TestTraceContext:
    """Tests for trace_context context manager."""

    def test_yields_span(self) -> None:
        """trace_context yields a span."""
        with trace_context("test-context") as span:
            assert span is not None
            # Should be a NoOpSpan when Langfuse not configured
            assert hasattr(span, "end")
        # No exception means success
        # No exception from cleanup means success


class TestShutdownTracing:
    """Tests for shutdown_tracing function."""

    def test_clears_global_tracer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """shutdown_tracing clears the global tracer."""
        import scrappy.graph.tracing as tracing_module

        # Initialize a tracer
        tracing_module._tracer = None
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        get_tracer()

        assert tracing_module._tracer is not None

        # Shutdown
        shutdown_tracing()
        assert tracing_module._tracer is None
        # No exception means success  # Should not raise
