"""
Behavior tests for bounded server-reported cooldowns (provider PR-3a).

Declared behavior deltas (guardrails: provider-pr3-guardrails.md rev 2, D2
and D3', operator-ratified):
- Server-reported retry_after is clamped at mark_unhealthy: floor 1s, cap
  86400s; non-finite/negative/zero values fall back to the failure-policy
  default. Stored ModelHealthState.retry_after is the clamped value (None
  when the server value was unusable).
- The last-resort message regex in _extract_retry_after only extracts
  durations adjacent to a retry/wait phrase (no unrelated-duration
  misfires), and now covers "try again in N" shapes.
"""

import math

import pytest

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind
from scrappy.orchestrator.failure_policy import FAILURE_POLICIES
from scrappy.orchestrator.litellm_service import _extract_retry_after
from scrappy.orchestrator.model_selection import (
    ModelAvailabilityTracker,
    ModelSelectionService,
    ModelSelectionType,
    RETRY_AFTER_CAP_SECONDS,
    RETRY_AFTER_FLOOR_SECONDS,
    clamp_retry_after,
)


class FakeClock:
    """Controllable clock for availability tests."""

    def __init__(self, now: float = 100.0):
        self.value = now

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


PRIORITIES = {ModelSelectionType.FAST: ["prov/model-a", "prov/model-b"]}
CONFIGURED = {"prov/model-a", "prov/model-b"}


def make_service(clock: FakeClock) -> ModelSelectionService:
    """Hermetic selection service: two fake models, injected clock."""
    tracker = ModelAvailabilityTracker(now=clock)
    return ModelSelectionService(
        configured_models=set(CONFIGURED),
        model_priorities=PRIORITIES,
        availability_tracker=tracker,
    )


RATE_LIMIT_DEFAULT = FAILURE_POLICIES[FailureKind.RATE_LIMIT].cooldown_seconds
AUTH_DEFAULT = FAILURE_POLICIES[FailureKind.AUTH].cooldown_seconds


class TestClampRetryAfter:
    """Clamp table for the pure helper."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, None),
            (float("nan"), None),
            (float("inf"), None),
            (float("-inf"), None),
            (0.0, None),
            (-30.0, None),
            (0.25, RETRY_AFTER_FLOOR_SECONDS),
            (1.0, 1.0),
            (30.0, 30.0),
            (86400.0, 86400.0),
            (7215400.0, RETRY_AFTER_CAP_SECONDS),
        ],
        ids=[
            "none",
            "nan",
            "inf",
            "neg-inf",
            "zero",
            "negative",
            "subsecond-floored",
            "at-floor",
            "typical",
            "at-cap",
            "bogus-huge-capped",
        ],
    )
    def test_clamp_table(self, value, expected):
        assert clamp_retry_after(value) == expected

    def test_constants_are_the_ratified_bounds(self):
        """D2 ratified: floor 1s, cap 86400s."""
        assert RETRY_AFTER_FLOOR_SECONDS == 1.0
        assert RETRY_AFTER_CAP_SECONDS == 86400.0


class TestMarkUnhealthyBounds:
    """The clamp observed through mark_unhealthy, not the helper alone."""

    def test_bogus_huge_value_capped_at_cap(self):
        clock = FakeClock()
        service = make_service(clock)
        service.mark_unhealthy(
            "prov/model-a", FailureKind.RATE_LIMIT, retry_after=7215400.0
        )
        assert service._availability.get_cooldown_remaining(
            "prov/model-a"
        ) == pytest.approx(RETRY_AFTER_CAP_SECONDS)
        state = service._availability.get_unavailable_state("prov/model-a")
        assert state is not None
        assert state.retry_after == pytest.approx(RETRY_AFTER_CAP_SECONDS)

    @pytest.mark.parametrize(
        "bad_value",
        [float("nan"), float("inf"), 0.0, -30.0],
        ids=["nan", "inf", "zero", "negative"],
    )
    def test_unusable_value_falls_back_to_policy_default(self, bad_value):
        clock = FakeClock()
        service = make_service(clock)
        service.mark_unhealthy(
            "prov/model-a", FailureKind.RATE_LIMIT, retry_after=bad_value
        )
        assert service._availability.get_cooldown_remaining(
            "prov/model-a"
        ) == pytest.approx(RATE_LIMIT_DEFAULT)
        state = service._availability.get_unavailable_state("prov/model-a")
        assert state is not None
        assert state.retry_after is None

    def test_subsecond_value_floored(self):
        clock = FakeClock()
        service = make_service(clock)
        service.mark_unhealthy(
            "prov/model-a", FailureKind.RATE_LIMIT, retry_after=0.25
        )
        assert service._availability.get_cooldown_remaining(
            "prov/model-a"
        ) == pytest.approx(RETRY_AFTER_FLOOR_SECONDS)

    def test_valid_value_used_exactly(self):
        clock = FakeClock()
        service = make_service(clock)
        service.mark_unhealthy(
            "prov/model-a", FailureKind.RATE_LIMIT, retry_after=30.0
        )
        assert service._availability.get_cooldown_remaining(
            "prov/model-a"
        ) == pytest.approx(30.0)
        state = service._availability.get_unavailable_state("prov/model-a")
        assert state is not None
        assert state.retry_after == pytest.approx(30.0)

    def test_absent_value_uses_policy_default(self):
        """Regression: no server value keeps the pre-3a behavior."""
        clock = FakeClock()
        service = make_service(clock)
        service.mark_unhealthy("prov/model-a", FailureKind.RATE_LIMIT)
        assert service._availability.get_cooldown_remaining(
            "prov/model-a"
        ) == pytest.approx(RATE_LIMIT_DEFAULT)

    def test_clamp_applies_across_kinds_and_scopes(self):
        """PER_PROVIDER kinds clamp too (AUTH default when value unusable)."""
        clock = FakeClock()
        service = make_service(clock)
        service.mark_unhealthy(
            "prov/model-a", FailureKind.AUTH, retry_after=float("inf")
        )
        # AUTH is PER_PROVIDER: both configured models are suppressed.
        for model in sorted(CONFIGURED):
            assert service._availability.get_cooldown_remaining(
                model
            ) == pytest.approx(AUTH_DEFAULT)


class TestSelectionSuppressionWindow:
    """Selection excludes the model for exactly the (clamped) window."""

    def test_suppressed_for_exactly_the_reported_window(self):
        clock = FakeClock(now=100.0)
        service = make_service(clock)

        assert service.select(ModelSelectionType.FAST) == "prov/model-a"
        service.mark_unhealthy(
            "prov/model-a", FailureKind.RATE_LIMIT, retry_after=30.0
        )
        assert service.select(ModelSelectionType.FAST) == "prov/model-b"

        clock.advance(29.999)
        assert service.select(ModelSelectionType.FAST) == "prov/model-b"

        clock.advance(0.001)  # exactly expires_at: cooldown is over
        assert service.select(ModelSelectionType.FAST) == "prov/model-a"

    def test_clamped_window_drives_suppression(self):
        """A bogus huge server value suppresses for the cap, no longer."""
        clock = FakeClock(now=100.0)
        service = make_service(clock)
        service.mark_unhealthy(
            "prov/model-a", FailureKind.RATE_LIMIT, retry_after=7215400.0
        )

        clock.advance(RETRY_AFTER_CAP_SECONDS - 1)
        assert service.select(ModelSelectionType.FAST) == "prov/model-b"

        clock.advance(1)
        assert service.select(ModelSelectionType.FAST) == "prov/model-a"


class FakeResponse:
    def __init__(self, headers):
        self.headers = headers


class FakeError(Exception):
    """Exception-like object with optional response/body attributes."""

    def __init__(self, message="", headers=None, body=None):
        super().__init__(message)
        if headers is not None:
            self.response = FakeResponse(headers)
        if body is not None:
            self.body = body


NOW = 1445412467.0  # matches 'Thu, 21 Oct 2015 07:27:47 GMT'


class TestExtractRetryAfterMatrix:
    """Extraction matrix per source; message cases pin the hardened regex."""

    @pytest.mark.parametrize(
        "error,expected",
        [
            (FakeError(headers={"Retry-After": "30"}), 30.0),
            (FakeError(headers={"retry-after": "12"}), 12.0),
            (
                FakeError(headers={"Retry-After": "Thu, 21 Oct 2015 07:28:47 GMT"}),
                60.0,
            ),
            # Past HTTP-date: current extraction returns 0.0 (max(0.0, ...));
            # the D2 clamp turns that 0.0 into the policy default downstream.
            (
                FakeError(headers={"Retry-After": "Thu, 21 Oct 2015 07:26:47 GMT"}),
                0.0,
            ),
            (FakeError(headers={"x-ratelimit-reset-requests": "1m30s"}), 90.0),
            (FakeError(headers={"x-ratelimit-reset-requests": "6s"}), 6.0),
            (FakeError(headers={"x-ratelimit-reset-tokens": "2m"}), 120.0),
            (FakeError(body={"retry_after": 42}), 42.0),
            (FakeError(body={"retryAfter": "15"}), 15.0),
        ],
        ids=[
            "header-seconds",
            "header-lowercase",
            "header-http-date-future",
            "header-http-date-past-is-zero",
            "reset-requests-compound",
            "reset-requests-simple",
            "reset-tokens-minutes",
            "body-number",
            "body-camel-string",
        ],
    )
    def test_structured_sources(self, error, expected):
        assert _extract_retry_after(error, now=lambda: NOW) == pytest.approx(
            expected
        )

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Please retry in 7.215400659s", 7.215400659),
            ("rate limit exceeded, retry after 30 seconds", 30.0),
            ("please wait 30 seconds before retrying", 30.0),
            ("quota exceeded, wait for 2 minutes", 120.0),
            ("retrying in 5s", 5.0),
            # Declared coverage gain (D3'): previously not extracted because
            # the gate required 'retry' or 'wait' in the message.
            ("Too many requests. Please try again in 20s", 20.0),
        ],
        ids=[
            "gemini-retry-in",
            "retry-after-seconds",
            "wait-n-seconds",
            "wait-for-minutes",
            "retrying-in",
            "try-again-in",
        ],
    )
    def test_message_phrases_extract(self, message, expected):
        assert _extract_retry_after(FakeError(message)) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "message",
        [
            # Declared misfire fixes (D3'): 'retry'/'wait' co-occurring with
            # an unrelated duration must NOT extract.
            "Do not retry. Request took 45 seconds and timed out",
            "retry with model prov/x, rate window is 60 minutes",
            "will not retry; upstream reported 3 hours of degraded service",
            "request waited in queue; p99 latency 2 s",
            # No duration at all.
            "please retry later",
            "rate limit exceeded",
            "",
        ],
        ids=[
            "duration-not-adjacent",
            "window-not-cooldown",
            "degraded-report",
            "queue-latency",
            "no-duration",
            "no-signal",
            "empty",
        ],
    )
    def test_message_misfires_do_not_extract(self, message):
        assert _extract_retry_after(FakeError(message)) is None

    def test_math_isfinite_guard_is_what_clamp_uses(self):
        """Pin the clamp's invalid set to math.isfinite semantics."""
        assert clamp_retry_after(math.nan) is None
        assert clamp_retry_after(math.inf) is None
