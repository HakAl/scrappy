"""PR-2a: selection depends on ModelAvailabilityTrackerProtocol, not a concrete.

These tests inject a fake availability store that conforms to the protocol (and
is NOT the concrete ModelAvailabilityTracker) into ModelSelectionService, then
assert selection consumes the protocol and preserves priority ordering. They are
the executable contract for the PR-2a decoupling seam; PR-2b (persisted
cooldowns) builds on the same seam and must not change this behavior.
"""

from typing import Optional

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTrackerProtocol,
    ModelHealthState,
    ModelSelectionService,
    ModelSelectionType,
)

# groq is first, cerebras second in MODEL_PRIORITIES[FAST] (see existing
# test_model_selection.py assertions).
GROQ = "groq/llama-3.1-8b-instant"
CEREBRAS = "cerebras/llama3.1-8b"
FAST_MODELS = {GROQ, CEREBRAS}


class FakeAvailabilityStore:
    """In-test availability store implementing the protocol surface only.

    Availability is driven directly by ``unavailable`` so a test controls it
    without the concrete cooldown/clock machinery. Its only job is to prove
    selection talks to the protocol rather than to a concrete type.
    """

    def __init__(self, unavailable: Optional[set[str]] = None) -> None:
        self.unavailable: set[str] = set(unavailable or set())
        self.marked: dict[str, ModelHealthState] = {}
        self.cleared_kinds: list[set[FailureKind]] = []

    def now(self) -> float:
        return 1000.0

    def mark(self, model: str, state: ModelHealthState) -> None:
        self.marked[model] = state
        self.unavailable.add(model)

    def is_available(self, model: str) -> bool:
        return model not in self.unavailable

    def get_cooldown_remaining(self, model: str) -> float:
        return 0.0

    def get_unavailable_state(self, model: str) -> Optional[ModelHealthState]:
        return self.marked.get(model)

    def clear_kinds(self, kinds: set[FailureKind]) -> None:
        self.cleared_kinds.append(set(kinds))
        self.unavailable.clear()


def test_fake_store_conforms_to_protocol():
    """The fake satisfies the protocol surface (also a static mypy check)."""
    store: ModelAvailabilityTrackerProtocol = FakeAvailabilityStore()
    assert store.is_available(GROQ)


class TestSelectionConsumesAvailabilityProtocol:
    """Selection reads availability through the injected protocol."""

    def test_skips_model_the_protocol_reports_unavailable(self):
        """Highest-priority model is skipped when the protocol says unavailable."""
        store = FakeAvailabilityStore(unavailable={GROQ})
        service = ModelSelectionService(
            configured_models=FAST_MODELS,
            availability_tracker=store,
        )

        assert service.select(ModelSelectionType.FAST) == CEREBRAS

    def test_includes_model_when_protocol_reports_available(self):
        """Highest-priority model is chosen when the protocol says available."""
        store = FakeAvailabilityStore(unavailable=set())
        service = ModelSelectionService(
            configured_models=FAST_MODELS,
            availability_tracker=store,
        )

        assert service.select(ModelSelectionType.FAST) == GROQ

    def test_clear_failure_kinds_delegates_to_protocol(self):
        """clear_failure_kinds routes to the protocol's clear_kinds."""
        store = FakeAvailabilityStore(unavailable={GROQ})
        service = ModelSelectionService(
            configured_models=FAST_MODELS,
            availability_tracker=store,
        )

        service.clear_failure_kinds({FailureKind.RATE_LIMIT})

        assert store.cleared_kinds == [{FailureKind.RATE_LIMIT}]
        assert service.select(ModelSelectionType.FAST) == GROQ


class TestOrderingPreserved:
    """Guards against an accidental reorder/semantics change in filtering."""

    def test_priority_order_preserved_among_available_models(self):
        """First available candidate is the highest-priority available model."""
        store = FakeAvailabilityStore(unavailable=set())
        service = ModelSelectionService(
            configured_models=FAST_MODELS,
            availability_tracker=store,
        )

        assert service.select(ModelSelectionType.FAST) == GROQ
        ordered = service.get_models_for_type(ModelSelectionType.FAST)
        assert ordered.index(GROQ) < ordered.index(CEREBRAS)

    def test_session_preferred_wins_only_when_it_survives_filtering(self):
        """session_preferred wins iff available; otherwise priority order holds."""
        available = FakeAvailabilityStore(unavailable=set())
        service = ModelSelectionService(
            configured_models=FAST_MODELS,
            availability_tracker=available,
        )
        assert (
            service.select(ModelSelectionType.FAST, session_preferred=CEREBRAS)
            == CEREBRAS
        )

        blocked = FakeAvailabilityStore(unavailable={CEREBRAS})
        service_blocked = ModelSelectionService(
            configured_models=FAST_MODELS,
            availability_tracker=blocked,
        )
        assert (
            service_blocked.select(ModelSelectionType.FAST, session_preferred=CEREBRAS)
            == GROQ
        )
