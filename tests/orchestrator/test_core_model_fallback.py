"""Focused tests for model-unavailable fallback behavior in AgentOrchestrator."""

import asyncio
from unittest.mock import Mock

import pytest

from scrappy.infrastructure.exceptions import FailureKind, ProviderExecutionError, RateLimitError
from scrappy.orchestrator import core as core_module
from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.fallback_metrics import provider_fallback_metrics
from scrappy.orchestrator.failure_policy import SHOULD_RETRY_KINDS
from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelSelectionService,
    ModelSelectionType,
    SelectionExhaustedError,
)
from scrappy.orchestrator.provider_types import LLMResponse
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
from tests.helpers import MockApiKeyService


PRIMARY_MODEL = "cerebras/gpt-oss-120b"
FALLBACK_MODEL = "groq/moonshotai/kimi-k2-instruct"
CHAT_8K_MODEL = "cerebras/llama-3.3-70b"
CHAT_32K_MODEL = "groq/llama-3.3-70b-versatile"
FAST_128K_MODEL = "groq/llama-3.1-8b-instant"


def make_orchestrator(*, llm_service, model_selector, delegation_manager) -> AgentOrchestrator:
    """Construct an orchestrator with direct mock dependencies."""
    return AgentOrchestrator(
        output=Mock(),
        registry=Mock(),
        cache=Mock(),
        rate_tracker=Mock(),
        working_memory=Mock(),
        session_manager=Mock(),
        provider_selector=Mock(),
        usage_reporter=Mock(),
        status_reporter=Mock(),
        task_executor=Mock(),
        context_manager=Mock(),
        delegation_manager=delegation_manager,
        background_manager=Mock(),
        llm_service=llm_service,
        provider_status_tracker=Mock(),
        model_selector=model_selector,
    )


def make_model_selector() -> ModelSelectionService:
    """Create a selector with a deterministic two-model instruct chain."""
    return ModelSelectionService(
        configured_models={PRIMARY_MODEL, FALLBACK_MODEL},
        model_priorities={
            ModelSelectionType.INSTRUCT: [PRIMARY_MODEL, FALLBACK_MODEL],
        },
    )


class FailingThenWorkingLLMService:
    """LLM service stub for streaming fallback tests."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_completion_direct(self, model, messages, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            raise ProviderExecutionError(
                f"Model '{PRIMARY_MODEL}' not available from cerebras",
                provider_name="cerebras",
                failure_kind=FailureKind.DEPRECATED,
            )

        yield StreamChunk(
            content="hello",
            model=model,
            provider=model.split("/", 1)[0],
        )


class ContentThenFailingLLMService:
    """Streaming stub that fails after visible content is emitted."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_completion_direct(self, model, messages, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            yield StreamChunk(
                content="partial",
                model=model,
                provider=model.split("/", 1)[0],
            )
            raise RateLimitError(
                f"Rate limit hit for {model}",
                provider_name=model.split("/", 1)[0],
            )

        yield StreamChunk(
            content="fallback",
            model=model,
            provider=model.split("/", 1)[0],
        )


class ToolFragmentThenFailingLLMService:
    """Streaming stub that fails after semantic tool output is emitted."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_completion_direct(self, model, messages, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            yield StreamChunk(
                tool_call_fragments=[
                    ToolCallFragment(
                        id="call-1",
                        type="function",
                        name="lookup",
                        arguments="{}",
                        index=0,
                    )
                ],
                model=model,
                provider=model.split("/", 1)[0],
            )
            raise RateLimitError(
                f"Rate limit hit for {model}",
                provider_name=model.split("/", 1)[0],
            )

        yield StreamChunk(
            content="fallback",
            model=model,
            provider=model.split("/", 1)[0],
        )


class MetadataThenFailingLLMService:
    """Streaming stub that fails after provider metadata only."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_completion_direct(self, model, messages, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            yield StreamChunk(
                model=model,
                provider=model.split("/", 1)[0],
                metadata={"request_id": "req-primary"},
            )
            raise RateLimitError(
                f"Rate limit hit for {model}",
                provider_name=model.split("/", 1)[0],
            )

        yield StreamChunk(
            content="fallback",
            model=model,
            provider=model.split("/", 1)[0],
        )


class AsyncFallbackDelegationManager:
    """Async delegation stub that fails selected models then records fallback calls."""

    def __init__(
        self,
        *,
        failing_models: set[str],
        failure_kind: FailureKind = FailureKind.RATE_LIMIT,
        error_cls=RateLimitError,
    ) -> None:
        self.failing_models = set(failing_models)
        self.failure_kind = failure_kind
        self.error_cls = error_cls
        self.calls: list[str | None] = []
        self.received_kwargs: list[dict] = []

    async def delegate_async(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        self.received_kwargs.append(kwargs)
        if model in self.failing_models:
            self.failing_models.remove(model)
            raise self.error_cls(
                f"{self.failure_kind.value} hit for {model}",
                provider_name=(model or "").split("/", 1)[0] or None,
                failure_kind=self.failure_kind,
            )

        response_model = model or FALLBACK_MODEL
        return (
            LLMResponse(
                content="async fallback response",
                model=response_model,
                provider=response_model.split("/", 1)[0],
            ),
            {
                "provider": response_model.split("/", 1)[0],
                "model": response_model,
                "tokens_used": 1,
            },
        )


class AsyncExhaustingDelegationManager:
    """Async delegation stub that fails every model before success."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def delegate_async(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        raise RateLimitError(
            f"Rate limit hit for {model}",
            provider_name=(model or "").split("/", 1)[0] or None,
        )


class ConcurrentPrimaryFailingAsyncDelegationManager:
    """Async stub that makes all requests fail the primary concurrently."""

    def __init__(self, expected_primary_calls: int) -> None:
        self.expected_primary_calls = expected_primary_calls
        self.primary_started = 0
        self.primary_release = asyncio.Event()
        self.calls: list[str | None] = []

    async def delegate_async(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            self.primary_started += 1
            retry_after = float(self.primary_started)
            if self.primary_started == self.expected_primary_calls:
                self.primary_release.set()
            await self.primary_release.wait()
            raise RateLimitError(
                f"Rate limit hit for {model}",
                provider_name=model.split("/", 1)[0],
                retry_after=retry_after,
            )

        response_model = model or FALLBACK_MODEL
        return (
            LLMResponse(
                content="async fallback response",
                model=response_model,
                provider=response_model.split("/", 1)[0],
            ),
            {
                "provider": response_model.split("/", 1)[0],
                "model": response_model,
                "tokens_used": 1,
            },
        )


class AsyncFailingThenWorkingStreamDelegationManager:
    """Async streaming stub for pre-output fallback tests."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def stream_delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            raise ProviderExecutionError(
                f"Model '{PRIMARY_MODEL}' not available from cerebras",
                provider_name="cerebras",
                failure_kind=FailureKind.DEPRECATED,
            )

        yield StreamChunk(
            content="hello",
            model=model or FALLBACK_MODEL,
            provider=(model or FALLBACK_MODEL).split("/", 1)[0],
        )


class AsyncContentThenFailingStreamDelegationManager:
    """Async streaming stub that fails after visible content is emitted."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def stream_delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            yield StreamChunk(
                content="partial",
                model=model,
                provider=model.split("/", 1)[0],
            )
            raise RateLimitError(
                f"Rate limit hit for {model}",
                provider_name=model.split("/", 1)[0],
            )

        yield StreamChunk(
            content="fallback",
            model=model or FALLBACK_MODEL,
            provider=(model or FALLBACK_MODEL).split("/", 1)[0],
        )


class AsyncExhaustingStreamDelegationManager:
    """Async streaming stub that fails every model before yielding output."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def stream_delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        raise RateLimitError(
            f"Rate limit hit for {model}",
            provider_name=(model or "").split("/", 1)[0] or None,
        )
        yield StreamChunk()


class ExhaustingLLMService:
    """Streaming stub that fails every model before yielding output."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_completion_direct(self, model, messages, **kwargs):
        self.calls.append(model)
        raise RateLimitError(
            f"Rate limit hit for {model}",
            provider_name=model.split("/", 1)[0],
        )


class ConfigurableLLMService:
    """LLM service stub for provider configuration refresh tests."""

    def __init__(self) -> None:
        self.configure_calls = 0

    def configure(self) -> bool:
        self.configure_calls += 1
        return True


class RecordingDelegationManager:
    """Delegation manager that records concrete models and succeeds."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        return (
            LLMResponse(
                content="response",
                model=model or "fallback",
                provider=(model or "fallback").split("/", 1)[0],
            ),
            {},
        )


class RateLimitThenWorkingDelegationManager:
    """Fails selected models once, then records successful fallback calls."""

    def __init__(self, failing_models: set[str]) -> None:
        self.failing_models = set(failing_models)
        self.calls: list[str | None] = []

    def delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        if model in self.failing_models:
            self.failing_models.remove(model)
            raise RateLimitError(
                f"Rate limit hit for {model}",
                provider_name=(model or "").split("/", 1)[0] or None,
            )

        return (
            LLMResponse(
                content="fallback response",
                model=model or FALLBACK_MODEL,
                provider=(model or FALLBACK_MODEL).split("/", 1)[0],
            ),
            {
                "provider": (model or FALLBACK_MODEL).split("/", 1)[0],
                "model": model or FALLBACK_MODEL,
                "tokens_used": 1,
            },
        )


class FakeClock:
    """Controllable clock for fallback preference tests."""

    def __init__(self, now: float = 100.0) -> None:
        self.value = now

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FailingThenWorkingDelegationManager:
    """Delegation manager stub for sync fallback tests."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.received_kwargs: list[dict] = []

    def delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        self.received_kwargs.append(kwargs)
        if model == PRIMARY_MODEL:
            raise ProviderExecutionError(
                f"Model '{PRIMARY_MODEL}' not available from cerebras",
                provider_name="cerebras",
                failure_kind=FailureKind.DEPRECATED,
            )

        return (
            LLMResponse(
                content="fallback response",
                model=model or FALLBACK_MODEL,
                provider=(model or FALLBACK_MODEL).split("/", 1)[0],
            ),
            {
                "provider": (model or FALLBACK_MODEL).split("/", 1)[0],
                "model": model or FALLBACK_MODEL,
                "tokens_used": 1,
            },
        )


class StructuredFallbackDelegationManager:
    """Structured delegation stub that fails selected models once."""

    def __init__(
        self,
        *,
        failing_models: set[str],
        failure_kind: FailureKind = FailureKind.RATE_LIMIT,
        error_cls=RateLimitError,
    ) -> None:
        self.failing_models = set(failing_models)
        self.failure_kind = failure_kind
        self.error_cls = error_cls
        self.calls: list[str | None] = []

    def delegate_structured_sync(self, provider_name, prompt, response_model, model=None, **kwargs):
        self.calls.append(model)
        if model in self.failing_models:
            self.failing_models.remove(model)
            raise self.error_cls(
                f"{self.failure_kind.value} hit for {model}",
                provider_name=(model or "").split("/", 1)[0] or None,
                failure_kind=self.failure_kind,
            )

        return {"model": model, "provider_name": provider_name}


def test_stream_completion_with_fallback_skips_unavailable_primary_model():
    """Streaming agent path should fall back when the first model is stale."""
    llm_service = FailingThenWorkingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )

    chunks = list(orchestrator.stream_completion_with_fallback(
        messages=[{"role": "user", "content": "test"}],
        selection_type=ModelSelectionType.INSTRUCT,
    ))

    assert llm_service.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert "".join(chunk.content for chunk in chunks) == "hello"
    assert chunks[-1].metadata == {
        "trace_chain": "cerebras(deprecated)->groq: moonshotai/kimi-k2-instruct",
    }


def test_stream_completion_with_fallback_emits_provider_fallback_event():
    """Streaming fallback emits the same structured event as sync fallback."""
    core_module.logger.get_records().clear()
    llm_service = FailingThenWorkingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )

    list(orchestrator.stream_completion_with_fallback(
        messages=[{"role": "user", "content": "test"}],
        selection_type=ModelSelectionType.INSTRUCT,
    ))

    fallback_records = [
        record
        for record in core_module.logger.get_records()
        if record["extra"].get("event") == "provider_fallback"
    ]
    assert len(fallback_records) == 1
    extra = fallback_records[0]["extra"]
    assert extra["from_model"] == PRIMARY_MODEL
    assert extra["from_provider"] == "cerebras"
    assert extra["to_model"] == FALLBACK_MODEL
    assert extra["to_provider"] == "groq"
    assert extra["failure_kind"] == FailureKind.DEPRECATED.value
    assert extra["attempt_n"] == 2


def test_stream_completion_with_fallback_auto_fallback_false_raises_immediately():
    """auto_fallback=False prevents streaming fallback attempts."""
    llm_service = FailingThenWorkingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )

    with pytest.raises(ProviderExecutionError):
        list(orchestrator.stream_completion_with_fallback(
            messages=[{"role": "user", "content": "test"}],
            selection_type=ModelSelectionType.INSTRUCT,
            auto_fallback=False,
        ))

    assert llm_service.calls == [PRIMARY_MODEL]


def test_stream_completion_mid_stream_content_error_does_not_fallback():
    """Failures after visible content surface with partial count metadata."""
    llm_service = ContentThenFailingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )
    chunks: list[StreamChunk] = []

    with pytest.raises(RateLimitError) as exc_info:
        for chunk in orchestrator.stream_completion_with_fallback(
            messages=[{"role": "user", "content": "test"}],
            selection_type=ModelSelectionType.INSTRUCT,
        ):
            chunks.append(chunk)

    assert llm_service.calls == [PRIMARY_MODEL]
    assert [chunk.content for chunk in chunks] == ["partial"]
    assert exc_info.value.context["partial_content_chars"] == len("partial")


def test_stream_completion_mid_stream_tool_fragment_error_does_not_fallback():
    """Failures after semantic tool output surface without fallback."""
    llm_service = ToolFragmentThenFailingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )
    chunks: list[StreamChunk] = []

    with pytest.raises(RateLimitError) as exc_info:
        for chunk in orchestrator.stream_completion_with_fallback(
            messages=[{"role": "user", "content": "test"}],
            selection_type=ModelSelectionType.INSTRUCT,
        ):
            chunks.append(chunk)

    assert llm_service.calls == [PRIMARY_MODEL]
    assert len(chunks) == 1
    assert chunks[0].tool_call_fragments[0].name == "lookup"
    assert exc_info.value.context["partial_content_chars"] == 0
    assert exc_info.value.context["emitted_semantic_output"] is True


def test_stream_completion_metadata_only_chunk_does_not_block_fallback():
    """Provider metadata frames are not semantic output for fallback gating."""
    llm_service = MetadataThenFailingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )

    chunks = list(orchestrator.stream_completion_with_fallback(
        messages=[{"role": "user", "content": "test"}],
        selection_type=ModelSelectionType.INSTRUCT,
    ))

    assert llm_service.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert chunks[0].metadata == {"request_id": "req-primary"}
    assert "".join(chunk.content for chunk in chunks) == "fallback"
    assert chunks[-1].metadata["trace_chain"].startswith(
        "cerebras(rate_limit)->groq"
    )


def test_stream_completion_exhaustion_includes_failure_summary():
    """Streaming exhaustion merges pre-output failed attempts into the summary."""
    llm_service = ExhaustingLLMService()
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=make_model_selector(),
        delegation_manager=Mock(),
    )

    with pytest.raises(SelectionExhaustedError) as exc_info:
        list(orchestrator.stream_completion_with_fallback(
            messages=[{"role": "user", "content": "test"}],
            selection_type=ModelSelectionType.INSTRUCT,
        ))

    assert llm_service.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert set(exc_info.value.failure_summary) == {PRIMARY_MODEL, FALLBACK_MODEL}
    assert {
        record.kind
        for record in exc_info.value.failure_summary.values()
    } == {FailureKind.RATE_LIMIT}


@pytest.mark.asyncio
async def test_delegate_async_uses_shared_fallback_dispatch():
    """Async delegation should fall back through concrete models."""
    delegation_manager = AsyncFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    response = await orchestrator.delegate_async(
        provider_name="fast",
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
    )

    assert response.model == FALLBACK_MODEL
    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert all(
        "auto_fallback" not in kwargs
        for kwargs in delegation_manager.received_kwargs
    )
    assert orchestrator.usage_reporter.record.call_args.kwargs["metadata"]["trace_chain"] == (
        "cerebras(rate_limit)->groq: moonshotai/kimi-k2-instruct"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind",
    sorted(SHOULD_RETRY_KINDS, key=lambda kind: kind.value),
)
async def test_delegate_async_falls_back_for_retryable_failure_kind(
    failure_kind: FailureKind,
):
    """Every retryable failure kind falls back through async dispatch."""
    delegation_manager = AsyncFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
        failure_kind=failure_kind,
        error_cls=ProviderExecutionError,
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    response = await orchestrator.delegate_async(
        provider_name="fast",
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
    )

    assert response.model == FALLBACK_MODEL
    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]


@pytest.mark.asyncio
async def test_delegate_async_auto_fallback_false_raises_immediately():
    """auto_fallback=False prevents async fallback attempts."""
    delegation_manager = AsyncFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    with pytest.raises(RateLimitError):
        await orchestrator.delegate_async(
            provider_name="fast",
            prompt="test",
            selection_type=ModelSelectionType.INSTRUCT,
            auto_fallback=False,
        )

    assert delegation_manager.calls == [PRIMARY_MODEL]


@pytest.mark.asyncio
async def test_concurrent_delegate_async_failures_keep_max_retry_after():
    """Concurrent async fallback updates converge on the latest health state."""
    total = 10
    clock = FakeClock()
    tracker = ModelAvailabilityTracker(now=clock)
    selector = ModelSelectionService(
        configured_models={PRIMARY_MODEL, FALLBACK_MODEL},
        model_priorities={
            ModelSelectionType.INSTRUCT: [PRIMARY_MODEL, FALLBACK_MODEL],
        },
        availability_tracker=tracker,
    )
    delegation_manager = ConcurrentPrimaryFailingAsyncDelegationManager(
        expected_primary_calls=total,
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=selector,
        delegation_manager=delegation_manager,
    )

    responses = await asyncio.gather(*[
        orchestrator.delegate_async(
            provider_name="fast",
            prompt=f"test {index}",
            selection_type=ModelSelectionType.INSTRUCT,
        )
        for index in range(total)
    ])

    state = tracker.get_unavailable_state(PRIMARY_MODEL)
    assert [response.model for response in responses] == [FALLBACK_MODEL] * total
    assert delegation_manager.primary_started == total
    assert state is not None
    assert state.retry_after == float(total)
    assert state.expires_at == clock.value + float(total)
    assert state.failure_kind == FailureKind.RATE_LIMIT


@pytest.mark.asyncio
async def test_delegate_async_exhaustion_includes_failure_summary():
    """Async exhaustion merges failed attempts into the summary."""
    delegation_manager = AsyncExhaustingDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    with pytest.raises(SelectionExhaustedError) as exc_info:
        await orchestrator.delegate_async(
            provider_name="fast",
            prompt="test",
            selection_type=ModelSelectionType.INSTRUCT,
        )

    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert set(exc_info.value.failure_summary) == {PRIMARY_MODEL, FALLBACK_MODEL}


@pytest.mark.asyncio
async def test_stream_delegate_async_fallback_emits_trace_and_event():
    """Async streaming fallback mirrors sync streaming observability."""
    core_module.logger.get_records().clear()
    delegation_manager = AsyncFailingThenWorkingStreamDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )
    chunks: list[StreamChunk] = []

    async for chunk in orchestrator.stream_delegate(
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
    ):
        chunks.append(chunk)

    fallback_records = [
        record
        for record in core_module.logger.get_records()
        if record["extra"].get("event") == "provider_fallback"
    ]
    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert "".join(chunk.content for chunk in chunks) == "hello"
    assert chunks[-1].metadata == {
        "trace_chain": "cerebras(deprecated)->groq: moonshotai/kimi-k2-instruct",
    }
    assert len(fallback_records) == 1


@pytest.mark.asyncio
async def test_stream_delegate_async_auto_fallback_false_raises_immediately():
    """auto_fallback=False prevents async streaming fallback attempts."""
    delegation_manager = AsyncFailingThenWorkingStreamDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    with pytest.raises(ProviderExecutionError):
        async for _chunk in orchestrator.stream_delegate(
            prompt="test",
            selection_type=ModelSelectionType.INSTRUCT,
            auto_fallback=False,
        ):
            pass

    assert delegation_manager.calls == [PRIMARY_MODEL]


@pytest.mark.asyncio
async def test_stream_delegate_async_mid_stream_content_error_does_not_fallback():
    """Async streaming failures after visible content surface without fallback."""
    delegation_manager = AsyncContentThenFailingStreamDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )
    chunks: list[StreamChunk] = []

    with pytest.raises(RateLimitError) as exc_info:
        async for chunk in orchestrator.stream_delegate(
            prompt="test",
            selection_type=ModelSelectionType.INSTRUCT,
        ):
            chunks.append(chunk)

    assert delegation_manager.calls == [PRIMARY_MODEL]
    assert [chunk.content for chunk in chunks] == ["partial"]
    assert exc_info.value.context["partial_content_chars"] == len("partial")


@pytest.mark.asyncio
async def test_stream_delegate_async_exhaustion_includes_failure_summary():
    """Async streaming exhaustion merges pre-output failures into the summary."""
    delegation_manager = AsyncExhaustingStreamDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    with pytest.raises(SelectionExhaustedError) as exc_info:
        async for _chunk in orchestrator.stream_delegate(
            prompt="test",
            selection_type=ModelSelectionType.INSTRUCT,
        ):
            pass

    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert set(exc_info.value.failure_summary) == {PRIMARY_MODEL, FALLBACK_MODEL}


def test_delegate_skips_unavailable_primary_model():
    """Sync delegate should also fall back when the primary model is stale."""
    delegation_manager = FailingThenWorkingDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    response = orchestrator.delegate(
        provider_name="fast",
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
    )

    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    assert response.model == FALLBACK_MODEL
    assert response.provider == "groq"


def test_delegate_adds_trace_chain_after_successful_fallback():
    """Sync delegate attaches fallback trace metadata to the task record."""
    delegation_manager = FailingThenWorkingDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    response = orchestrator.delegate(
        provider_name="fast",
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
    )

    assert response.model == FALLBACK_MODEL
    assert orchestrator.usage_reporter.record.call_args.kwargs["metadata"]["trace_chain"] == (
        "cerebras(deprecated)->groq: moonshotai/kimi-k2-instruct"
    )


def test_delegate_emits_provider_fallback_event():
    """Sync delegate emits a structured fallback event after recovery."""
    core_module.logger.get_records().clear()
    provider_fallback_metrics.reset()
    delegation_manager = FailingThenWorkingDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    orchestrator.delegate(
        provider_name="fast",
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
    )

    fallback_records = [
        record
        for record in core_module.logger.get_records()
        if record["extra"].get("event") == "provider_fallback"
    ]
    assert len(fallback_records) == 1
    extra = fallback_records[0]["extra"]
    assert extra["from_model"] == PRIMARY_MODEL
    assert extra["from_provider"] == "cerebras"
    assert extra["to_model"] == FALLBACK_MODEL
    assert extra["to_provider"] == "groq"
    assert extra["failure_kind"] == FailureKind.DEPRECATED.value
    assert extra["scope"] == "per_model"
    assert extra["attempt_n"] == 2
    assert isinstance(extra["request_id"], str)
    assert extra["elapsed_ms"] >= 0
    assert set(extra) == {
        "event",
        "request_id",
        "attempt_n",
        "from_model",
        "from_provider",
        "to_model",
        "to_provider",
        "failure_kind",
        "retry_after",
        "scope",
        "elapsed_ms",
    }

    snapshot = provider_fallback_metrics.snapshot()
    assert snapshot.provider_fallbacks_total[
        ("cerebras", "groq", FailureKind.DEPRECATED.value)
    ] == 1


def test_delegate_does_not_forward_auto_fallback_to_manager():
    """Orchestrator owns sync fallback gating before calling the manager."""
    delegation_manager = FailingThenWorkingDelegationManager()
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    orchestrator.delegate(
        provider_name="fast",
        prompt="test",
        selection_type=ModelSelectionType.INSTRUCT,
        auto_fallback=True,
    )

    assert all(
        "auto_fallback" not in kwargs
        for kwargs in delegation_manager.received_kwargs
    )


def test_delegate_structured_uses_shared_fallback_dispatch():
    """Structured sync delegation should fall back through concrete models."""
    delegation_manager = StructuredFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    result = orchestrator.delegate_structured(
        provider_name="gemini",
        prompt="test",
        response_model=dict,
    )

    assert result == {"model": FALLBACK_MODEL, "provider_name": "gemini"}
    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]


@pytest.mark.parametrize(
    "failure_kind",
    sorted(SHOULD_RETRY_KINDS, key=lambda kind: kind.value),
)
def test_delegate_structured_falls_back_for_retryable_failure_kind(
    failure_kind: FailureKind,
):
    """Every retryable failure kind falls back to the next valid model."""
    delegation_manager = StructuredFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
        failure_kind=failure_kind,
        error_cls=ProviderExecutionError,
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    result = orchestrator.delegate_structured(
        provider_name="gemini",
        prompt="test",
        response_model=dict,
    )

    assert result == {"model": FALLBACK_MODEL, "provider_name": "gemini"}
    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]


def test_delegate_structured_auto_fallback_false_raises_immediately():
    """auto_fallback=False prevents structured fallback attempts."""
    delegation_manager = StructuredFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    try:
        orchestrator.delegate_structured(
            provider_name="gemini",
            prompt="test",
            response_model=dict,
            auto_fallback=False,
        )
    except RateLimitError:
        pass
    else:
        raise AssertionError("expected RateLimitError")

    assert delegation_manager.calls == [PRIMARY_MODEL]


def test_delegate_structured_content_refused_does_not_fallback_or_mark_health():
    """CONTENT_REFUSED surfaces without selecting another model."""
    selector = make_model_selector()
    delegation_manager = StructuredFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
        failure_kind=FailureKind.CONTENT_REFUSED,
        error_cls=ProviderExecutionError,
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=selector,
        delegation_manager=delegation_manager,
    )

    with pytest.raises(ProviderExecutionError):
        orchestrator.delegate_structured(
            provider_name="gemini",
            prompt="test",
            response_model=dict,
        )

    assert delegation_manager.calls == [PRIMARY_MODEL]
    assert selector.is_available(PRIMARY_MODEL) is True


def test_delegate_structured_unknown_failure_does_not_fallback():
    """UNKNOWN failures surface without selecting another model."""
    delegation_manager = StructuredFallbackDelegationManager(
        failing_models={PRIMARY_MODEL},
        failure_kind=FailureKind.UNKNOWN,
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    try:
        orchestrator.delegate_structured(
            provider_name="gemini",
            prompt="test",
            response_model=dict,
        )
    except RateLimitError:
        pass
    else:
        raise AssertionError("expected RateLimitError")

    assert delegation_manager.calls == [PRIMARY_MODEL]


def test_delegate_structured_exhaustion_includes_failure_summary():
    """Structured exhaustion merges attempted error records into the summary."""
    provider_fallback_metrics.reset()
    delegation_manager = StructuredFallbackDelegationManager(
        failing_models={PRIMARY_MODEL, FALLBACK_MODEL},
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=make_model_selector(),
        delegation_manager=delegation_manager,
    )

    try:
        orchestrator.delegate_structured(
            provider_name="gemini",
            prompt="test",
            response_model=dict,
        )
    except Exception as error:
        from scrappy.orchestrator.model_selection import AllModelsRateLimitedError

        assert isinstance(error, AllModelsRateLimitedError)
        assert set(error.failure_summary) == {PRIMARY_MODEL, FALLBACK_MODEL}
    else:
        raise AssertionError("expected AllModelsRateLimitedError")

    assert delegation_manager.calls == [PRIMARY_MODEL, FALLBACK_MODEL]
    snapshot = provider_fallback_metrics.snapshot()
    assert snapshot.provider_selection_exhausted_total[
        ModelSelectionType.INSTRUCT.value
    ] == 1


def test_chat_initial_selection_respects_min_context():
    """CHAT initial selection should skip configured 8k models."""
    delegation_manager = RecordingDelegationManager()
    selector = ModelSelectionService(
        configured_models={CHAT_8K_MODEL, CHAT_32K_MODEL},
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=selector,
        delegation_manager=delegation_manager,
    )

    response = orchestrator.delegate(
        prompt="test",
        selection_type=ModelSelectionType.CHAT,
    )

    assert delegation_manager.calls == [CHAT_32K_MODEL]
    assert response.model == CHAT_32K_MODEL


def test_chat_fallback_selection_respects_min_context():
    """CHAT fallback should skip lower-context candidates."""
    delegation_manager = RateLimitThenWorkingDelegationManager(
        failing_models={CHAT_32K_MODEL},
    )
    selector = ModelSelectionService(
        configured_models={CHAT_32K_MODEL, CHAT_8K_MODEL, FAST_128K_MODEL},
        model_priorities={
            ModelSelectionType.CHAT: [
                CHAT_32K_MODEL,
                CHAT_8K_MODEL,
                FAST_128K_MODEL,
            ],
        },
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=selector,
        delegation_manager=delegation_manager,
    )

    response = orchestrator.delegate(
        prompt="test",
        selection_type=ModelSelectionType.CHAT,
    )

    assert delegation_manager.calls == [CHAT_32K_MODEL, FAST_128K_MODEL]
    assert response.model == FAST_128K_MODEL


def test_fallback_preference_recovers_after_cooldown():
    """Fallback preference sticks during cooldown and recovers afterward."""
    clock = FakeClock()
    tracker = ModelAvailabilityTracker(cooldown_seconds=60, now=clock)
    primary = "provider/model-a"
    fallback = "provider/model-b"
    delegation_manager = RateLimitThenWorkingDelegationManager(
        failing_models={primary},
    )
    selector = ModelSelectionService(
        configured_models={primary, fallback},
        model_priorities={
            ModelSelectionType.FAST: [primary, fallback],
        },
        availability_tracker=tracker,
    )
    orchestrator = make_orchestrator(
        llm_service=Mock(),
        model_selector=selector,
        delegation_manager=delegation_manager,
    )

    orchestrator.delegate(prompt="first", selection_type=ModelSelectionType.FAST)
    for index in range(10):
        orchestrator.delegate(
            prompt=f"during cooldown {index}",
            selection_type=ModelSelectionType.FAST,
        )

    clock.advance(60)
    orchestrator.delegate(prompt="after cooldown", selection_type=ModelSelectionType.FAST)

    assert delegation_manager.calls[:2] == [primary, fallback]
    assert delegation_manager.calls[2:12] == [fallback] * 10
    assert delegation_manager.calls[12] == primary


def test_refresh_provider_configuration_updates_selector_and_clears_auth(monkeypatch):
    """Setup refresh preserves the selector while clearing credential failures."""
    llm_service = ConfigurableLLMService()
    selector = ModelSelectionService(
        configured_models={"cerebras/llama3.1-8b"},
        model_priorities={
            ModelSelectionType.FAST: [
                "cerebras/llama3.1-8b",
                "groq/llama-3.1-8b-instant",
            ],
        },
    )
    selector.mark_unhealthy("cerebras/llama3.1-8b", FailureKind.AUTH)
    orchestrator = make_orchestrator(
        llm_service=llm_service,
        model_selector=selector,
        delegation_manager=Mock(),
    )

    monkeypatch.setattr(
        "scrappy.orchestrator.core.create_api_key_service",
        lambda: MockApiKeyService(
            keys={
                "CEREBRAS_API_KEY": "test-cerebras",
                "GROQ_API_KEY": "test-groq",
            }
        ),
    )

    result = orchestrator.refresh_provider_configuration()

    assert result is True
    assert llm_service.configure_calls == 1
    assert orchestrator.model_selector is selector
    assert selector.select(ModelSelectionType.FAST) == "cerebras/llama3.1-8b"
    assert selector.is_configured("groq/llama-3.1-8b-instant") is True
