"""Characterization pins for AgentOrchestrator selection surface (PR-5).

Real-object pins: ModelSelectionService is the real implementation, so
these tests fail if the selection mapping or the quality_mode defaults
change.
"""

from unittest.mock import Mock, patch

import pytest

from scrappy.orchestrator.core import AgentOrchestrator
from scrappy.orchestrator.model_selection import (
    ModelSelectionService,
    ModelSelectionType,
)
from scrappy.orchestrator.provider_types import LLMResponse


CHAT_32K_MODEL = "groq/llama-3.3-70b-versatile"
FAST_MODEL = "groq/llama-3.1-8b-instant"


class KwargRecordingDelegationManager:
    """Delegation stub that records the kwargs each attempt received."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.received_kwargs: list[dict] = []

    def delegate(self, provider_name, prompt, model=None, **kwargs):
        self.calls.append(model)
        self.received_kwargs.append(kwargs)
        response_model = model or "none/none"
        return (
            LLMResponse(
                content="ok",
                model=response_model,
                provider=response_model.split("/", 1)[0],
            ),
            {
                "provider": response_model.split("/", 1)[0],
                "model": response_model,
                "tokens_used": 1,
            },
        )


def make_orchestrator(
    *,
    quality_mode: bool = True,
    model_selector=None,
    delegation_manager=None,
) -> AgentOrchestrator:
    """Build an orchestrator with real selection surfaces and mock edges."""
    return AgentOrchestrator(
        quality_mode=quality_mode,
        output=Mock(),
        registry=Mock(),
        cache=Mock(),
        rate_tracker=Mock(),
        working_memory=Mock(),
        session_manager=Mock(),
        usage_reporter=Mock(),
        status_reporter=Mock(),
        task_executor=Mock(),
        context_manager=Mock(),
        delegation_manager=delegation_manager or Mock(),
        background_manager=Mock(),
        model_selector=model_selector,
    )


class TestGetRecommendedProviderPins:
    """get_recommended_provider returns the catalog group per selection type."""

    @pytest.mark.parametrize(
        "selection_type, expected_group",
        [
            (ModelSelectionType.FAST, "fast"),
            (ModelSelectionType.CHAT, "chat"),
            (ModelSelectionType.INSTRUCT, "instruct"),
            (ModelSelectionType.EMBED, "fast"),
        ],
    )
    def test_get_recommended_provider_group(self, selection_type, expected_group):
        """The selection surface maps each selection type to its group."""
        orchestrator = make_orchestrator()

        assert orchestrator.get_recommended_provider(selection_type) == expected_group


class TestSetupBrainPins:
    """_setup_brain group and _brain_name per hint class."""

    @pytest.mark.parametrize(
        "hint, expected_group",
        [
            ("fast", "fast"),
            ("chat", "chat"),
            ("instruct", "instruct"),
            ("quality", "instruct"),
            ("groq", "instruct"),
            ("no-such-provider", "instruct"),
            (None, "instruct"),
        ],
    )
    def test_setup_brain_group_per_hint(self, hint, expected_group):
        """Each hint class resolves to its documented brain group."""
        orchestrator = make_orchestrator()

        orchestrator._setup_brain(hint)

        assert orchestrator._brain_name == expected_group
        assert orchestrator.brain == expected_group


class TestStatusQualityModePin:
    """status() reports the constructed quality_mode value."""

    @pytest.mark.parametrize("quality_mode", [True, False])
    def test_status_quality_mode_field(self, quality_mode):
        """The status dict carries the quality_mode the orchestrator was built with."""
        with patch(
            "scrappy.orchestrator.litellm_config.get_configured_models",
            return_value=[],
        ), patch(
            "scrappy.orchestrator.litellm_config.get_available_groups",
            return_value=[],
        ), patch("scrappy.orchestrator.core.create_api_key_service"):
            orchestrator = make_orchestrator(quality_mode=quality_mode)

            status = orchestrator.status()

        assert status["quality_mode"] is quality_mode


class TestQualityModeConstructionSelectionPins:
    """Construction-time quality_mode drives the default selection type.

    Pinned via construction only: quality_mode becomes a read-only property
    in a later commit, so these tests never assign it directly.
    """

    def test_quality_mode_true_delegates_with_chat_selection(self):
        """quality_mode=True defaults delegate() to CHAT selection."""
        delegation_manager = KwargRecordingDelegationManager()
        selector = ModelSelectionService(
            configured_models={CHAT_32K_MODEL},
            model_priorities={ModelSelectionType.CHAT: [CHAT_32K_MODEL]},
        )
        orchestrator = make_orchestrator(
            quality_mode=True,
            model_selector=selector,
            delegation_manager=delegation_manager,
        )

        orchestrator.delegate(prompt="hello")

        assert delegation_manager.calls == [CHAT_32K_MODEL]
        assert delegation_manager.received_kwargs[0]["selection_type"] == "chat"

    def test_quality_mode_false_delegates_with_fast_selection(self):
        """quality_mode=False defaults delegate() to FAST selection."""
        delegation_manager = KwargRecordingDelegationManager()
        selector = ModelSelectionService(
            configured_models={FAST_MODEL},
            model_priorities={ModelSelectionType.FAST: [FAST_MODEL]},
        )
        orchestrator = make_orchestrator(
            quality_mode=False,
            model_selector=selector,
            delegation_manager=delegation_manager,
        )

        orchestrator.delegate(prompt="hello")

        assert delegation_manager.calls == [FAST_MODEL]
        assert delegation_manager.received_kwargs[0]["selection_type"] == "fast"


class TestDefaultTypeMutationPin:
    """set_default_type on the service flips the orchestrator delegate default."""

    def test_set_default_type_flips_delegate_default(self):
        """Switching the service default to FAST redirects implicit delegate()."""
        delegation_manager = KwargRecordingDelegationManager()
        selector = ModelSelectionService(
            configured_models={CHAT_32K_MODEL, FAST_MODEL},
            model_priorities={
                ModelSelectionType.CHAT: [CHAT_32K_MODEL],
                ModelSelectionType.FAST: [FAST_MODEL],
            },
        )
        orchestrator = make_orchestrator(
            quality_mode=True,
            model_selector=selector,
            delegation_manager=delegation_manager,
        )

        selector.set_default_type(ModelSelectionType.FAST)
        orchestrator.delegate(prompt="hello")

        assert orchestrator.quality_mode is False
        assert delegation_manager.calls == [FAST_MODEL]
        assert delegation_manager.received_kwargs[0]["selection_type"] == "fast"
