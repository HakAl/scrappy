"""
Mock LLM Service for testing.

Provides a test double for LLMServiceProtocol that returns pre-configured
responses without making real API calls. Enabled via SCRAPPY_MOCK_LLM env var.

Usage:
    # In e2e tests
    env: { SCRAPPY_MOCK_LLM: "1" }

    # For specific responses
    env: { SCRAPPY_MOCK_LLM: "1", SCRAPPY_MOCK_RESPONSE: "Custom response text" }
"""

import os
import time
from datetime import datetime
from typing import Any, Iterator, Optional, AsyncIterator

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.orchestrator.types import StreamChunk
from .model_selection import ModelSelectionType
from .provider_types import LLMResponse


class MockLLMService:
    """
    Mock LLM service for testing.

    Returns pre-configured responses without API calls.
    Implements LLMServiceProtocol for drop-in replacement.

    Environment Variables:
        SCRAPPY_MOCK_LLM: Set to "1" to enable mock mode (checked by factory)
        SCRAPPY_MOCK_RESPONSE: Custom response content (optional)
        SCRAPPY_MOCK_TOKENS: Token count to return (optional, default 42)
        SCRAPPY_MOCK_LATENCY_MS: Simulated latency in ms (optional, default 100)
    """

    def __init__(
        self,
        default_response: Optional[str] = None,
        default_tokens: int = 42,
        default_latency_ms: float = 100.0,
    ):
        """
        Initialize mock service.

        Args:
            default_response: Default response content (can be overridden by env var)
            default_tokens: Default token count
            default_latency_ms: Default simulated latency
        """
        self._default_response = default_response or os.environ.get(
            "SCRAPPY_MOCK_RESPONSE",
            "This is a mock response for testing. The actual LLM is not being called."
        )
        self._default_tokens = int(os.environ.get(
            "SCRAPPY_MOCK_TOKENS",
            str(default_tokens)
        ))
        self._default_latency_ms = float(os.environ.get(
            "SCRAPPY_MOCK_LATENCY_MS",
            str(default_latency_ms)
        ))

        # Track calls for test assertions
        self._call_count = 0
        self._calls: list[dict[str, Any]] = []

        # Service is always "configured" in mock mode
        self._configured = True

    @property
    def configured(self) -> bool:
        """Check if service is configured."""
        return self._configured

    def configure(self) -> bool:
        """Configure the service (no-op in mock mode)."""
        return True

    async def completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> tuple[LLMResponse, dict]:
        """
        Async completion (returns mock response).

        Args:
            model: Model group name (ignored in mock)
            messages: Chat messages
            **kwargs: Additional params (ignored in mock)

        Returns:
            Tuple of (LLMResponse, task_record dict)
        """
        return self._create_response(model, messages, **kwargs)

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> tuple[LLMResponse, dict]:
        """
        Sync completion (returns mock response).

        Args:
            model: Model group name (ignored in mock)
            messages: Chat messages
            **kwargs: Additional params (ignored in mock)

        Returns:
            Tuple of (LLMResponse, task_record dict)
        """
        return self._create_response(model, messages, **kwargs)

    def _create_response(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> tuple[LLMResponse, dict]:
        """
        Create mock response and task record.

        Args:
            model: Model group name
            messages: Chat messages
            **kwargs: Additional params

        Returns:
            Tuple of (LLMResponse, task_record dict)
        """
        self._call_count += 1

        # Record call for test assertions
        call_record = {
            "model": model,
            "messages": messages,
            "kwargs": kwargs,
            "timestamp": datetime.now().isoformat(),
        }
        self._calls.append(call_record)

        # Simulate latency if configured
        if self._default_latency_ms > 0:
            time.sleep(self._default_latency_ms / 1000.0)

        # Calculate approximate input tokens from messages
        input_text = " ".join(
            msg.get("content", "") for msg in messages if msg.get("content")
        )
        input_tokens = len(input_text) // 4  # Rough estimate

        # Output tokens from response
        output_tokens = self._default_tokens - input_tokens
        if output_tokens < 1:
            output_tokens = self._default_tokens // 2

        # Create response
        response = LLMResponse(
            content=self._default_response,
            model=f"mock/{model}",
            provider="mock",
            tokens_used=self._default_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=self._default_latency_ms,
            raw_response=None,
            metadata={"finish_reason": "stop", "mock": True},
            timestamp=datetime.now(),
            tool_calls=None,
        )

        # Create task record (matches real LiteLLMService format)
        task_record = {
            "provider": "mock",
            "model": f"mock/{model}",
            "tokens_used": self._default_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": self._default_latency_ms,
            "cached": False,
            "timestamp": datetime.now().isoformat(),
        }

        return response, task_record

    def completion_direct(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> tuple[LLMResponse, dict]:
        """
        Direct completion (bypasses Router, used for fallback).

        In mock mode, behaves identically to completion_sync.

        Args:
            model: Specific model name (ignored in mock)
            messages: Chat messages
            **kwargs: Additional params (ignored in mock)

        Returns:
            Tuple of (LLMResponse, task_record dict)
        """
        return self._create_response(model, messages, **kwargs)

    def stream_completion_sync(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> Iterator[StreamChunk]:
        """
        Sync streaming completion (returns mock chunks).

        Yields a single chunk containing the full mock response.

        Args:
            model: Model group name (ignored in mock)
            messages: Chat messages
            **kwargs: Additional params (ignored in mock)

        Yields:
            Single StreamChunk with full mock response
        """
        response, _ = self._create_response(model, messages, **kwargs)

        # Yield single chunk with all content
        yield StreamChunk(
            content=response.content,
            model=response.model,
            provider=response.provider,
            finish_reason="stop",
            tool_call_fragments=None,
        )

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        """
        Async streaming completion (returns mock chunks).

        Yields a single chunk containing the full mock response.

        Args:
            model: Model group name (ignored in mock)
            messages: Chat messages
            **kwargs: Additional params (ignored in mock)

        Yields:
            Single StreamChunk with full mock response
        """
        response, _ = self._create_response(model, messages, **kwargs)

        # Yield single chunk with all content
        yield StreamChunk(
            content=response.content,
            model=response.model,
            provider=response.provider,
            finish_reason="stop",
            tool_call_fragments=None,
        )

    def stream_completion_direct(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any
    ) -> Iterator[StreamChunk]:
        """
        Stream completion with specific model (mock implementation).

        In mock mode, this behaves identically to stream_completion_sync.
        Accepts specific model names like "cerebras/qwen-3-235b-a22b-instruct-2507".

        Args:
            model: Specific model name (treated same as group in mock)
            messages: Chat messages
            **kwargs: Additional params (ignored in mock)

        Yields:
            Single StreamChunk with full mock response
        """
        # In mock mode, direct streaming behaves same as tier-based
        yield from self.stream_completion_sync(model, messages, **kwargs)

    def stream_completion_with_fallback(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        selection_type: Any = None,
        **kwargs: Any
    ) -> Iterator[StreamChunk]:
        """
        Orchestrator-compatible streaming method (mock implementation).

        This allows MockLLMService to be used as an orchestrator in tests.

        Args:
            messages: Chat messages
            model: Optional model name (defaults to "mock")
            selection_type: Model selection type (ignored in mock)
            **kwargs: Additional params (ignored in mock)

        Yields:
            StreamChunk with mock response
        """
        yield from self.stream_completion_sync(model or "mock", messages, **kwargs)

    # Test helper methods

    @property
    def call_count(self) -> int:
        """Get number of calls made to the mock service."""
        return self._call_count

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Get list of all calls made to the mock service."""
        return self._calls.copy()

    @property
    def last_call(self) -> Optional[dict[str, Any]]:
        """Get the last call made to the mock service."""
        return self._calls[-1] if self._calls else None

    def reset(self) -> None:
        """Reset call tracking."""
        self._call_count = 0
        self._calls.clear()


class MockModelSelectionService:
    """
    Model selection service for mock mode (implements ModelSelectionServiceProtocol).

    In mock mode there are no API keys, so the real selector is built with an
    empty configured set. The orchestrator's normal selection path then returns
    no model: _select_initial_model returns None and
    stream_completion_with_fallback raises "No model available" BEFORE
    MockLLMService ever runs. The metrics path consequently posts provider=None
    and the TUI status line stays stuck at "provider: --".

    This service makes a single mock model always selectable for every selection
    type and any context requirement, so streaming reaches MockLLMService and the
    resulting chunks carry provider="mock" through the same path real providers
    use. The mock model is never unhealthy and is treated as having unlimited
    context.
    """

    MOCK_MODEL_ID = "mock/mock-model"

    def select(
        self,
        selection_type: ModelSelectionType,
        min_context: int = 0,
        session_preferred: Optional[str] = None,
        exclude: Optional[set[str]] = None,
    ) -> str:
        """Always return the mock model, honoring session stickiness trivially."""
        if session_preferred == self.MOCK_MODEL_ID:
            return session_preferred
        return self.MOCK_MODEL_ID

    def get_models_for_type(self, selection_type: ModelSelectionType) -> list[str]:
        """The mock model is configured for every selection type."""
        return [self.MOCK_MODEL_ID]

    def mark_unhealthy(
        self,
        model: str,
        kind: FailureKind,
        retry_after: Optional[float] = None,
    ) -> None:
        """No-op: the mock model never becomes unhealthy."""
        return None

    def update_configured(self, new_set: set[str]) -> None:
        """No-op: the mock configured set is fixed."""
        return None

    def clear_failure_kinds(self, kinds: set[FailureKind]) -> None:
        """No-op: the mock model has no tracked health state to clear."""
        return None

    def is_available(self, model_id: str) -> bool:
        """The mock model is always available; nothing else is configured."""
        return model_id == self.MOCK_MODEL_ID


def is_mock_mode_enabled() -> bool:
    """
    Check if mock LLM mode is enabled via environment variable.

    Returns:
        True if SCRAPPY_MOCK_LLM is set to a truthy value
    """
    mock_env = os.environ.get("SCRAPPY_MOCK_LLM", "").lower()
    return mock_env in ("1", "true", "yes", "on")
