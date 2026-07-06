"""
Behavior tests for persisted model cooldown state (provider PR-2b).

Declared behavior delta: a model in cooldown at shutdown stays suppressed
across restart until its expires_at passes, instead of being re-hammered
immediately. Restart is modeled by constructing a NEW tracker from the same
persist path. Guardrails: .docs/plans/provider-pr2-guardrails.md rev 3.
"""

import json
from pathlib import Path

import pytest

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.orchestrator.factory import OrchestratorFactory
from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelHealthState,
    default_model_cooldowns_path,
)


class FakeClock:
    """Controllable clock for availability tests."""

    def __init__(self, now: float = 100.0):
        self.value = now

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def mark_unavailable(
    tracker: ModelAvailabilityTracker,
    model: str,
    retry_after: float = 60.0,
    kind: FailureKind = FailureKind.RATE_LIMIT,
) -> None:
    """Mark a tracker entry with the canonical health-state API."""
    tracker.mark(
        model,
        ModelHealthState(
            expires_at=tracker.now() + retry_after,
            failure_kind=kind,
            retry_after=retry_after,
        ),
    )


@pytest.fixture
def persist_path(tmp_path: Path) -> Path:
    return tmp_path / "model_cooldowns.json"


class TestCooldownSurvivesRestart:
    """The declared PR-2b delta: cooldown state outlives the process."""

    def test_cooldown_survives_restart_until_expiry(self, persist_path):
        """A model in cooldown stays suppressed in a new tracker instance."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        mark_unavailable(first, "groq/model-a", retry_after=60.0)

        clock.advance(30.0)
        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)

        assert restarted.is_available("groq/model-a") is False
        assert restarted.get_cooldown_remaining("groq/model-a") == pytest.approx(30.0)

    def test_persisted_state_round_trips_fields(self, persist_path):
        """failure_kind and retry_after survive the restart intact."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        mark_unavailable(
            first, "groq/model-a", retry_after=45.0, kind=FailureKind.SERVER_ERROR
        )

        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        state = restarted.get_unavailable_state("groq/model-a")

        assert state is not None
        assert state.expires_at == pytest.approx(145.0)
        assert state.failure_kind is FailureKind.SERVER_ERROR
        assert state.retry_after == pytest.approx(45.0)

    def test_restarted_tracker_recovers_after_expiry(self, persist_path):
        """Self-healing still works on persisted state once expires_at passes."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        mark_unavailable(first, "groq/model-a", retry_after=60.0)

        clock.advance(30.0)
        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        assert restarted.is_available("groq/model-a") is False

        clock.advance(31.0)
        assert restarted.is_available("groq/model-a") is True

    def test_expired_entry_is_pruned_on_load(self, persist_path):
        """Entries already past expires_at at load are dropped from the file."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        mark_unavailable(first, "groq/short-lived", retry_after=10.0)
        mark_unavailable(first, "groq/long-lived", retry_after=1000.0)

        clock.advance(500.0)
        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)

        assert restarted.is_available("groq/short-lived") is True
        assert restarted.is_available("groq/long-lived") is False
        on_disk = json.loads(persist_path.read_text())
        assert "groq/short-lived" not in on_disk
        assert "groq/long-lived" in on_disk


class TestPersistenceRobustness:
    """Construction must never crash on a bad persist file."""

    def test_absent_file_does_not_crash_and_mark_creates_it(self, persist_path):
        """No file yet: tracker starts empty; first mark writes the file."""
        clock = FakeClock(now=100.0)
        tracker = ModelAvailabilityTracker(now=clock, persist_path=persist_path)

        assert tracker.is_available("groq/model-a") is True
        mark_unavailable(tracker, "groq/model-a")
        assert persist_path.exists()
        leftovers = [
            p for p in persist_path.parent.iterdir() if p.name != persist_path.name
        ]
        assert leftovers == []

    def test_missing_parent_directory_is_created(self, tmp_path):
        """Persist path in a not-yet-existing directory is created on write."""
        clock = FakeClock(now=100.0)
        nested = tmp_path / "not" / "yet" / "model_cooldowns.json"
        tracker = ModelAvailabilityTracker(now=clock, persist_path=nested)

        mark_unavailable(tracker, "groq/model-a")

        restarted = ModelAvailabilityTracker(now=clock, persist_path=nested)
        assert restarted.is_available("groq/model-a") is False

    @pytest.mark.parametrize(
        "content",
        ["{not json at all", "[1, 2, 3]", '"a bare string"', ""],
        ids=["garbage", "json-list", "json-string", "empty"],
    )
    def test_corrupt_file_does_not_crash(self, persist_path, content):
        """Garbage or wrong-shape JSON: start empty, do not raise."""
        persist_path.write_text(content)
        clock = FakeClock(now=100.0)

        tracker = ModelAvailabilityTracker(now=clock, persist_path=persist_path)

        assert tracker.is_available("groq/model-a") is True

    def test_corrupt_file_is_replaced_by_next_write(self, persist_path):
        """After a corrupt load, the next mark writes a readable file again."""
        persist_path.write_text("{not json at all")
        clock = FakeClock(now=100.0)
        tracker = ModelAvailabilityTracker(now=clock, persist_path=persist_path)

        mark_unavailable(tracker, "groq/model-a", retry_after=60.0)

        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        assert restarted.is_available("groq/model-a") is False

    def test_malformed_entries_are_skipped_valid_entry_kept(self, persist_path):
        """Per-entry damage drops that entry only, never the whole store."""
        persist_path.write_text(
            json.dumps(
                {
                    "groq/valid": {
                        "expires_at": 1000.0,
                        "failure_kind": "rate_limit",
                        "retry_after": 60.0,
                    },
                    "groq/missing-expiry": {
                        "failure_kind": "rate_limit",
                        "retry_after": 60.0,
                    },
                    "groq/unknown-kind": {
                        "expires_at": 1000.0,
                        "failure_kind": "not_a_kind",
                        "retry_after": None,
                    },
                    "groq/wrong-shape": "just a string",
                }
            )
        )
        clock = FakeClock(now=100.0)

        tracker = ModelAvailabilityTracker(now=clock, persist_path=persist_path)

        assert tracker.is_available("groq/valid") is False
        assert tracker.is_available("groq/missing-expiry") is True
        assert tracker.is_available("groq/unknown-kind") is True
        assert tracker.is_available("groq/wrong-shape") is True


class TestWriteThrough:
    """Clearing operations must reach the persist file, not just memory."""

    def test_clear_kinds_write_through(self, persist_path):
        """clear_kinds (production path: clear_failure_kinds) survives restart."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        mark_unavailable(
            first, "groq/rate-limited", retry_after=1000.0, kind=FailureKind.RATE_LIMIT
        )
        mark_unavailable(
            first, "groq/erroring", retry_after=1000.0, kind=FailureKind.SERVER_ERROR
        )

        first.clear_kinds({FailureKind.RATE_LIMIT})

        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        assert restarted.is_available("groq/rate-limited") is True
        assert restarted.is_available("groq/erroring") is False

    def test_clear_write_through(self, persist_path):
        """clear() must not let cooldowns resurrect on restart."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        mark_unavailable(first, "groq/model-a", retry_after=1000.0)

        first.clear()

        restarted = ModelAvailabilityTracker(now=clock, persist_path=persist_path)
        assert restarted.is_available("groq/model-a") is True


class TestProcessLocalDefault:
    """Without a persist path the tracker keeps its documented old behavior."""

    def test_default_tracker_stays_process_local(self):
        """No persist path: a new tracker instance starts clean."""
        clock = FakeClock(now=100.0)
        first = ModelAvailabilityTracker(now=clock)
        mark_unavailable(first, "groq/model-a", retry_after=1000.0)
        assert first.is_available("groq/model-a") is False

        restarted = ModelAvailabilityTracker(now=clock)
        assert restarted.is_available("groq/model-a") is True


class TestFactoryWiring:
    """The factory provides the persisted default; DI stays at the seam."""

    def test_factory_tracker_persists_across_restart(self, tmp_path, monkeypatch):
        """Factory-built trackers share cooldown state via the default path."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        factory = OrchestratorFactory()

        first = factory.create_model_availability_tracker()
        mark_unavailable(first, "groq/model-a", retry_after=3600.0)

        assert (tmp_path / ".scrappy" / "model_cooldowns.json").exists()
        restarted = factory.create_model_availability_tracker()
        assert restarted.is_available("groq/model-a") is False

    def test_default_cooldowns_path_is_under_user_scrappy_dir(
        self, tmp_path, monkeypatch
    ):
        """The default persist path is ~/.scrappy/model_cooldowns.json."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert (
            default_model_cooldowns_path()
            == tmp_path / ".scrappy" / "model_cooldowns.json"
        )
