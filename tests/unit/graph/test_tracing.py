"""Unit tests for tracing module."""

import pytest

from scrappy.graph.tracing import (
    NoOpSpan,
    NoOpTracer,
    get_tracer,
    set_tracer,
    trace_node,
    trace_context,
    is_tracing_enabled,
    shutdown_tracing,
    get_langfuse_callback,
    TracerProtocol,
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
            assert s is span

    def test_set_attribute_is_noop(self) -> None:
        """set_attribute does nothing but doesn't raise."""
        span = NoOpSpan("test")
        span.set_attribute("key", "value")
        span.set_attribute("number", 42)
        span.set_attribute("dict", {"nested": True})

    def test_add_event_is_noop(self) -> None:
        """add_event does nothing but doesn't raise."""
        span = NoOpSpan("test")
        span.add_event("event_name")
        span.add_event("event_with_attrs", {"attr1": "value1"})
        span.add_event("event_empty_attrs", {})

    def test_end_is_noop(self) -> None:
        """end does nothing but doesn't raise."""
        span = NoOpSpan("test")
        span.end()
        span.end()  # Multiple calls should be safe


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

    def test_flush_is_noop(self) -> None:
        """flush() does nothing but doesn't raise."""
        tracer = NoOpTracer()
        tracer.flush()
        tracer.flush()  # Multiple calls should be safe

    def test_shutdown_is_noop(self) -> None:
        """shutdown() does nothing but doesn't raise."""
        tracer = NoOpTracer()
        tracer.shutdown()
        tracer.shutdown()  # Multiple calls should be safe

    def test_shutdown_accepts_timeout(self) -> None:
        """shutdown() accepts timeout parameter."""
        tracer = NoOpTracer()
        tracer.shutdown(timeout=5.0)
        tracer.shutdown(timeout=0.1)

    def test_implements_tracer_protocol(self) -> None:
        """NoOpTracer implements TracerProtocol."""
        tracer = NoOpTracer()
        assert isinstance(tracer, TracerProtocol)


class TestSetTracer:
    """Tests for set_tracer function."""

    def test_sets_global_tracer(self) -> None:
        """set_tracer sets the global tracer."""
        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            custom_tracer = NoOpTracer()
            set_tracer(custom_tracer)
            assert tracing_module._tracer is custom_tracer
        finally:
            tracing_module._tracer = original

    def test_allows_none_to_reset(self) -> None:
        """set_tracer(None) resets global tracer."""
        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(NoOpTracer())
            assert tracing_module._tracer is not None
            set_tracer(None)
            assert tracing_module._tracer is None
        finally:
            tracing_module._tracer = original

    def test_get_tracer_returns_set_tracer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tracer returns tracer set via set_tracer."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        custom_tracer = NoOpTracer()
        set_tracer(custom_tracer)

        try:
            result = get_tracer()
            assert result is custom_tracer
        finally:
            set_tracer(None)


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

    def test_returns_noop_tracer_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tracer returns NoOpTracer when Langfuse keys not set."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        tracer = get_tracer()
        assert isinstance(tracer, NoOpTracer)

    def test_returns_noop_tracer_with_only_public_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tracer returns NoOpTracer when only public key is set."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        tracer = get_tracer()
        assert isinstance(tracer, NoOpTracer)

    def test_returns_noop_tracer_with_only_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tracer returns NoOpTracer when only secret key is set."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = get_tracer()
        assert isinstance(tracer, NoOpTracer)


class TestIsTracingEnabled:
    """Tests for is_tracing_enabled function."""

    def test_returns_false_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without API keys, tracing is not enabled."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        assert is_tracing_enabled() is False

    def test_returns_false_with_noop_tracer(self) -> None:
        """With NoOpTracer explicitly set, tracing is not enabled."""
        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(NoOpTracer())
            assert is_tracing_enabled() is False
        finally:
            tracing_module._tracer = original


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
            assert hasattr(span, "end")

    def test_accepts_kwargs(self) -> None:
        """trace_context passes kwargs to tracer.trace()."""
        with trace_context("test-context", metadata={"key": "value"}) as span:
            assert span is not None

    def test_span_end_called_on_normal_exit(self) -> None:
        """span.end() is called when context exits normally."""
        end_called = []

        class MockSpan:
            def end(self):
                end_called.append(True)

        class MockTracer:
            def trace(self, name, **kwargs):
                return MockSpan()

        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(MockTracer())
            with trace_context("test"):
                pass
            assert end_called == [True]
        finally:
            tracing_module._tracer = original

    def test_span_end_called_on_exception(self) -> None:
        """span.end() is called even when exception occurs."""
        end_called = []

        class MockSpan:
            def end(self):
                end_called.append(True)

        class MockTracer:
            def trace(self, name, **kwargs):
                return MockSpan()

        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(MockTracer())
            with pytest.raises(ValueError):
                with trace_context("test"):
                    raise ValueError("test error")
            assert end_called == [True]
        finally:
            tracing_module._tracer = original


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

    def test_calls_tracer_shutdown(self) -> None:
        """shutdown_tracing calls shutdown on the tracer."""
        shutdown_called = []

        class MockTracer:
            def shutdown(self, timeout=2.0):
                shutdown_called.append(timeout)

        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(MockTracer())
            shutdown_tracing()
            assert shutdown_called == [2.0]
        finally:
            tracing_module._tracer = original

    def test_accepts_custom_timeout(self) -> None:
        """shutdown_tracing passes custom timeout to tracer."""
        shutdown_called = []

        class MockTracer:
            def shutdown(self, timeout=2.0):
                shutdown_called.append(timeout)

        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(MockTracer())
            shutdown_tracing(timeout=5.0)
            assert shutdown_called == [5.0]
        finally:
            tracing_module._tracer = original

    def test_safe_when_no_tracer(self) -> None:
        """shutdown_tracing is safe when no tracer is set."""
        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            tracing_module._tracer = None
            shutdown_tracing()  # Should not raise
            assert tracing_module._tracer is None
        finally:
            tracing_module._tracer = original

    def test_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """shutdown_tracing can be called multiple times safely."""
        import scrappy.graph.tracing as tracing_module

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        tracing_module._tracer = None
        get_tracer()

        shutdown_tracing()
        shutdown_tracing()  # Second call should be safe
        shutdown_tracing()  # Third call should be safe
        assert tracing_module._tracer is None


class TestGetLangfuseCallback:
    """Tests for get_langfuse_callback function."""

    def test_returns_none_without_langfuse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_langfuse_callback returns None when Langfuse not configured."""
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        result = get_langfuse_callback()
        assert result is None

    def test_returns_none_with_noop_tracer(self) -> None:
        """get_langfuse_callback returns None with NoOpTracer."""
        import scrappy.graph.tracing as tracing_module
        original = tracing_module._tracer

        try:
            set_tracer(NoOpTracer())
            result = get_langfuse_callback()
            assert result is None
        finally:
            tracing_module._tracer = original


class TestLangfuseTracer:
    """Tests for LangfuseTracer behavior with mocked socket."""

    @pytest.fixture
    def mock_socket_fail(self, monkeypatch: pytest.MonkeyPatch):
        """Mock socket.connect to fail."""
        import socket

        class MockSocket:
            def __init__(self, *args, **kwargs):
                pass
            def settimeout(self, timeout):
                pass
            def connect(self, address):
                raise ConnectionRefusedError("Connection refused")
            def close(self):
                pass

        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: MockSocket())

    def test_falls_back_when_connection_fails(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer falls back to unavailable when server not reachable."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        assert tracer.available is False

    def test_trace_returns_noop_when_unavailable(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer.trace returns NoOpSpan when unavailable."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        span = tracer.trace("test")
        assert isinstance(span, NoOpSpan)

    def test_span_always_returns_noop(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer.span always returns NoOpSpan (stub)."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        span = tracer.span("test")
        assert isinstance(span, NoOpSpan)

    def test_generation_always_returns_noop(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer.generation always returns NoOpSpan (stub)."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        span = tracer.generation("test")
        assert isinstance(span, NoOpSpan)

    def test_flush_safe_when_unavailable(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer.flush is safe when unavailable."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        tracer.flush()  # Should not raise

    def test_shutdown_safe_when_unavailable(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer.shutdown is safe when unavailable."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        tracer.shutdown()  # Should not raise

    def test_get_callback_handler_returns_none_when_unavailable(self, monkeypatch: pytest.MonkeyPatch, mock_socket_fail) -> None:
        """LangfuseTracer.get_callback_handler returns None when unavailable."""
        from scrappy.graph.tracing import LangfuseTracer

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = LangfuseTracer()
        handler = tracer.get_callback_handler()
        assert handler is None


class TestGetTracerWithLangfuseConfigured:
    """Tests for get_tracer when Langfuse keys are set but server unavailable."""

    def test_returns_noop_when_langfuse_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_tracer returns NoOpTracer when Langfuse configured but unavailable."""
        import socket
        import scrappy.graph.tracing as tracing_module
        tracing_module._tracer = None

        # Mock socket to fail connection
        class MockSocket:
            def __init__(self, *args, **kwargs):
                pass
            def settimeout(self, timeout):
                pass
            def connect(self, address):
                raise ConnectionRefusedError("Connection refused")
            def close(self):
                pass

        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: MockSocket())
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        tracer = get_tracer()
        assert isinstance(tracer, NoOpTracer)
