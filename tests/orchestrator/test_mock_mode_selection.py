"""
Behavior tests for mock-mode model selection (scrappy-h4q9).

Regression: in mock mode the factory swapped in MockLLMService but built the
model selector with an empty configured set (no API keys). The orchestrator's
normal selection path then returned no model, so
stream_completion_with_fallback raised "No model available" before the mock
service ran. Metrics consequently posted provider=None and the TUI status line
stuck at "provider: --".

These tests prove that mock mode now resolves a selectable model for every
selection type and that streaming reaches MockLLMService, emitting chunks with
provider="mock" (the value the metrics path turns into the "mock:" display).
"""

import pytest

from scrappy.orchestrator.core import create_orchestrator
from scrappy.orchestrator.mock_llm_service import (
    MockLLMService,
    MockModelSelectionService,
)
from scrappy.orchestrator.model_selection import ModelSelectionType


class TestMockModelSelectionService:
    """The mock selector honors the selection contract for every type."""

    def test_selects_a_model_for_every_selection_type(self):
        service = MockModelSelectionService()

        for selection_type in ModelSelectionType:
            selected = service.select(selection_type)
            assert selected
            assert selected in service.get_models_for_type(selection_type)
            assert service.is_available(selected)

    def test_satisfies_large_min_context(self):
        """CHAT requests a 32k min context; the mock model must still resolve."""
        service = MockModelSelectionService()

        selected = service.select(ModelSelectionType.CHAT, min_context=32768)

        assert selected == MockModelSelectionService.MOCK_MODEL_ID

    def test_honors_session_preference_for_mock_model(self):
        service = MockModelSelectionService()
        mock_model = MockModelSelectionService.MOCK_MODEL_ID

        result = service.select(
            ModelSelectionType.INSTRUCT,
            session_preferred=mock_model,
        )

        assert result == mock_model

    def test_unconfigured_model_is_not_available(self):
        service = MockModelSelectionService()

        assert service.is_available("groq/llama-3.1-8b-instant") is False


@pytest.fixture
def mock_mode(monkeypatch):
    """Enable deterministic, latency-free mock mode for the orchestrator."""
    monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
    monkeypatch.setenv("SCRAPPY_MOCK_LATENCY_MS", "0")
    monkeypatch.setenv("SCRAPPY_MOCK_RESPONSE", "Mock response")


class TestMockModeStreaming:
    """End-to-end: mock-mode streaming emits mock-provider chunks, not errors."""

    def test_orchestrator_uses_mock_services_in_mock_mode(self, mock_mode):
        orch = create_orchestrator()

        assert isinstance(orch.llm_service, MockLLMService)
        assert isinstance(orch.model_selector, MockModelSelectionService)

    def test_instruct_streaming_emits_mock_provider(self, mock_mode):
        """The failing path: INSTRUCT streaming must not raise and must carry
        provider='mock' so metrics show 'mock:' instead of 'provider: --'."""
        orch = create_orchestrator()

        chunks = list(
            orch.stream_completion_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                selection_type=ModelSelectionType.INSTRUCT,
            )
        )

        assert chunks, "expected at least one stream chunk"
        assert all(chunk.provider == "mock" for chunk in chunks)
        assert "".join(chunk.content or "" for chunk in chunks) == "Mock response"

    @pytest.mark.parametrize(
        "selection_type",
        [ModelSelectionType.FAST, ModelSelectionType.CHAT],
    )
    def test_other_selection_types_do_not_raise(self, mock_mode, selection_type):
        """delegate() reaches FAST/CHAT in mock mode; neither may raise."""
        orch = create_orchestrator()

        chunks = list(
            orch.stream_completion_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                selection_type=selection_type,
            )
        )

        assert all(chunk.provider == "mock" for chunk in chunks)
