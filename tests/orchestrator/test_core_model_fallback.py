"""Focused tests for model-unavailable fallback behavior in AgentOrchestrator."""

from unittest.mock import Mock

from scrappy.infrastructure.exceptions import ProviderExecutionError
from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.model_selection import ModelSelectionService, ModelSelectionType
from scrappy.orchestrator.provider_types import LLMResponse
from scrappy.orchestrator.types import StreamChunk


PRIMARY_MODEL = "cerebras/gpt-oss-120b"
FALLBACK_MODEL = "groq/moonshotai/kimi-k2-instruct"


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
            )

        yield StreamChunk(
            content="hello",
            model=model,
            provider=model.split("/", 1)[0],
        )


class FailingThenWorkingDelegationManager:
    """Delegation manager stub for sync fallback tests."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        if model == PRIMARY_MODEL:
            raise ProviderExecutionError(
                f"Model '{PRIMARY_MODEL}' not available from cerebras",
                provider_name="cerebras",
            )

        return (
            LLMResponse(
                content="fallback response",
                model=model or FALLBACK_MODEL,
                provider=(model or FALLBACK_MODEL).split("/", 1)[0],
            ),
            {},
        )


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
        "trace_chain": "cerebras(unavailable)->groq: moonshotai/kimi-k2-instruct",
    }


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
