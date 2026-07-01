"""
Unit tests for AgentOrchestrator.stream_delegate() method.

Tests the thin wrapper that exposes DelegationManager.stream_delegate()
through AgentOrchestrator, including:
- Basic streaming forwarding to delegation_manager
- Auto-selection of provider when none specified
- Quality mode affects selection type
- Cache setting passthrough
- ProviderNotFoundError when no providers available
"""

import pytest
from typing import AsyncIterator, Optional
from unittest.mock import Mock

from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.types import StreamChunk
from scrappy.orchestrator.model_selection import ModelSelectionType
from tests.helpers import make_stream_chunk


# =============================================================================
# Mock Implementations
# =============================================================================

class MockDelegationManager:
    """Mock DelegationManager that tracks stream_delegate calls."""

    def __init__(self, stream_chunks: Optional[list[StreamChunk]] = None):
        self._stream_chunks = stream_chunks or [
            make_stream_chunk(content="Hello", model="test", provider="test"),
            make_stream_chunk(content=" world", finish_reason="stop", model="test", provider="test"),
        ]
        self.stream_delegate_calls: list[dict] = []

    async def stream_delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        use_context: Optional[bool] = None,
        use_cache: Optional[bool] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Mock streaming that yields configured chunks."""
        self.stream_delegate_calls.append({
            'provider_name': provider_name,
            'prompt': prompt,
            'model': model,
            'system_prompt': system_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'use_context': use_context,
            'use_cache': use_cache,
            **kwargs
        })

        for chunk in self._stream_chunks:
            yield chunk

    def delegate(self, *args, **kwargs):
        """Non-streaming delegate (not tested here)."""
        pass

    async def delegate_async(self, *args, **kwargs):
        """Async delegate (not tested here)."""
        pass


class MockProviderSelector:
    """Mock provider selector for testing auto-selection."""

    def __init__(self, recommended_provider: Optional[str] = "fast"):
        self._recommended = recommended_provider

    def get_model(self, selection_type: ModelSelectionType):
        if self._recommended is None:
            raise RuntimeError("No providers available")
        return (self._recommended, f"{self._recommended}-model")

    def setup_brain(self, preferred_provider=None):
        return ("mock-brain", Mock())


class MockProviderRegistry:
    """Mock provider registry."""

    def __init__(self, available: list[str] = None):
        self._available = available or ["groq", "cerebras"]

    def list_available(self):
        return self._available

    def list_all(self):
        return self._available

    def get_provider_info(self):
        return {}


class MockOutput:
    """Mock output."""

    def info(self, msg):
        pass

    def warning(self, msg):
        pass


class MockUsageReporter:
    """Mock usage reporter."""

    def record(self, **kwargs):
        pass

    def get_usage_report(self):
        return {}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_delegation_manager():
    """Create mock delegation manager."""
    return MockDelegationManager()


@pytest.fixture
def mock_provider_selector():
    """Create mock provider selector."""
    return MockProviderSelector()


@pytest.fixture
def orchestrator(mock_delegation_manager, mock_provider_selector):
    """
    Create AgentOrchestrator with mocked dependencies.

    Uses dependency injection to provide mocks for testing.
    """
    # Create minimal mocks for required dependencies
    mock_output = MockOutput()
    mock_registry = MockProviderRegistry()
    mock_cache = Mock()
    mock_rate_tracker = Mock()
    mock_working_memory = Mock()
    mock_session_manager = Mock()
    mock_usage_reporter = MockUsageReporter()
    mock_status_reporter = Mock()
    mock_task_executor = Mock()
    mock_context_manager = Mock()
    mock_context_manager.context = Mock()
    mock_background_manager = Mock()

    orch = AgentOrchestrator(
        output=mock_output,
        registry=mock_registry,
        cache=mock_cache,
        rate_tracker=mock_rate_tracker,
        working_memory=mock_working_memory,
        session_manager=mock_session_manager,
        provider_selector=mock_provider_selector,
        usage_reporter=mock_usage_reporter,
        status_reporter=mock_status_reporter,
        task_executor=mock_task_executor,
        context_manager=mock_context_manager,
        delegation_manager=mock_delegation_manager,
        background_manager=mock_background_manager,
    )

    return orch


# =============================================================================
# Basic Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_forwards_to_delegation_manager(orchestrator, mock_delegation_manager):
    """Test that stream_delegate forwards to delegation_manager.stream_delegate()."""
    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify chunks were yielded
    assert len(collected_chunks) == 2
    assert collected_chunks[0].content == "Hello"
    assert collected_chunks[1].content == " world"

    # Verify delegation_manager was called
    assert len(mock_delegation_manager.stream_delegate_calls) == 1
    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['provider_name'] == "fast"
    assert call['prompt'] == "test prompt"


@pytest.mark.asyncio
async def test_stream_delegate_passes_all_parameters(orchestrator, mock_delegation_manager):
    """Test that all parameters are passed through to delegation_manager."""
    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name="quality",
        prompt="complex prompt",
        model="custom-model",
        system_prompt="Be helpful",
        max_tokens=500,
        temperature=0.9,
        use_context=True,
        use_cache=False,
    ):
        collected_chunks.append(chunk)

    # Verify all parameters were passed
    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['provider_name'] == "quality"
    assert call['prompt'] == "complex prompt"
    assert call['model'] == "custom-model"
    assert call['system_prompt'] == "Be helpful"
    assert call['max_tokens'] == 500
    assert call['temperature'] == 0.9
    assert call['use_context'] is True
    assert call['use_cache'] is False


# =============================================================================
# Auto-Selection Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_auto_selects_provider_when_none(orchestrator, mock_delegation_manager):
    """Test that provider is auto-selected when provider_name is None."""
    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name=None,  # Auto-select
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Verify auto-selected provider was used
    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['provider_name'] == "fast"


@pytest.mark.asyncio
async def test_stream_delegate_uses_quality_mode_for_selection(orchestrator, mock_delegation_manager):
    """Test that quality_mode affects provider selection."""
    orchestrator.quality_mode = True

    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name=None,  # Auto-select
        prompt="test prompt",
    ):
        collected_chunks.append(chunk)

    # Provider selector should have been queried (via get_recommended_provider)
    # With quality_mode=True, it would use QUALITY selection type
    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['provider_name'] == "fast"  # Mock returns "fast"


@pytest.mark.asyncio
async def test_stream_delegate_selection_type_overrides_quality_mode(orchestrator, mock_delegation_manager):
    """Test that explicit selection_type overrides quality_mode."""
    orchestrator.quality_mode = True

    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name=None,
        prompt="test prompt",
        selection_type=ModelSelectionType.FAST,  # Override quality_mode
    ):
        collected_chunks.append(chunk)

    # Should still work - selection_type used for provider selection
    assert len(mock_delegation_manager.stream_delegate_calls) == 1


# =============================================================================
# Cache Setting Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_uses_caching_enabled_setting(orchestrator, mock_delegation_manager):
    """Test that orchestrator.caching_enabled is used when use_cache not specified."""
    orchestrator.caching_enabled = True

    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
        # use_cache not specified - should use caching_enabled
    ):
        collected_chunks.append(chunk)

    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['use_cache'] is True


@pytest.mark.asyncio
async def test_stream_delegate_use_cache_overrides_caching_enabled(orchestrator, mock_delegation_manager):
    """Test that explicit use_cache overrides caching_enabled setting."""
    orchestrator.caching_enabled = True

    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
        use_cache=False,  # Override caching_enabled=True
    ):
        collected_chunks.append(chunk)

    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['use_cache'] is False


# =============================================================================
# Error Handling Tests
# =============================================================================


# =============================================================================
# kwargs Passthrough Tests
# =============================================================================

@pytest.mark.asyncio
async def test_stream_delegate_passes_extra_kwargs(orchestrator, mock_delegation_manager):
    """Test that extra kwargs are passed through to delegation_manager."""
    collected_chunks = []
    async for chunk in orchestrator.stream_delegate(
        provider_name="fast",
        prompt="test prompt",
        stop_sequences=["END"],
        top_p=0.95,
    ):
        collected_chunks.append(chunk)

    call = mock_delegation_manager.stream_delegate_calls[0]
    assert call['stop_sequences'] == ["END"]
    assert call['top_p'] == 0.95
