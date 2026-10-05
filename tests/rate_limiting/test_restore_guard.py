"""Behavior tests for the persisted rate-limit state startup guard (scrappy-cktc).

These tests exercise REAL business objects (RateLimitTracker + RateLimitPolicy +
RateLimitCalculator + RateLimitRecommender + QuotaScorer + RateLimitStorage) over a
REAL FileSystemAdapter pointed at pytest tmp_path files. The ONLY test double is a
spy wrapped around the external IO boundary (FileSystemAdapter.write_text) used to
count write attempts; policy, reset, calculator, and restore logic are the real
units under test and are never replaced.

Rationale for real tmp_path files (not a FakeFileSystem): storage.load_async calls
aiofiles.open on the real path whenever aiofiles is installed, so a FakeFileSystem
async test would swallow FileNotFoundError into {} and pass without reading the
fixture. Real files make the async read actually read.

NO REAL API CALLS. NO network. Determinism comes from seeding last_reset stamps and
from RateLimitPolicy(today=...); the tracker clock (datetime.now) and the policy
clock are intentionally distinct and are never asserted equal.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from scrappy.orchestrator.provider_types import ProviderLimits
from scrappy.orchestrator.rate_limiting.calculator import RateLimitCalculator
from scrappy.orchestrator.rate_limiting.factory import (
    create_rate_limit_components,
    create_rate_limit_tracker,
)
from scrappy.orchestrator.rate_limiting.policy import RateLimitPolicy
from scrappy.orchestrator.rate_limiting.recommender import RateLimitRecommender
from scrappy.orchestrator.rate_limiting.scorer import QuotaScorer
from scrappy.orchestrator.rate_limiting.storage import (
    FileSystemAdapter,
    RateLimitStorage,
)
from scrappy.orchestrator.rate_limiting.tracker import RateLimitTracker
from scrappy.orchestrator.rate_limiting import storage as storage_module

LIMITS = ProviderLimits(
    requests_per_minute=60,
    requests_per_day=1000,
    requests_per_month=10000,
    tokens_per_minute=10000,
    tokens_per_day=100000,
)

FOREIGN_SEED = {"real": "rate limit state"}


# --------------------------------------------------------------------------- #
# Spy at the external IO boundary only.
# --------------------------------------------------------------------------- #

@pytest.fixture
def write_spy(monkeypatch):
    """Count every FileSystemAdapter.write_text call, delegating to the real writer.

    This is the single allowed external-boundary spy. It wraps the real method so
    the on-disk bytes still change on a genuine save, letting a test assert BOTH
    zero write attempts AND unchanged file bytes on rejection.
    """
    calls: list[tuple[Path, str]] = []
    original = FileSystemAdapter.write_text

    def spy(self, path, content, encoding="utf-8"):
        calls.append((Path(path), content))
        return original(self, path, content, encoding=encoding)

    monkeypatch.setattr(FileSystemAdapter, "write_text", spy)
    return calls


# --------------------------------------------------------------------------- #
# Real-object builders (direct wiring => these are TRACKER tests, not factory).
# --------------------------------------------------------------------------- #

def _real_tracker(path: Path, policy: RateLimitPolicy | None = None) -> RateLimitTracker:
    """Wire a fully-real tracker over a real FileSystemAdapter + RateLimitStorage."""
    fs = FileSystemAdapter()
    storage = RateLimitStorage(path, fs)
    calculator = RateLimitCalculator()
    tracker = RateLimitTracker(
        storage=storage,
        policy=policy or RateLimitPolicy(),
        calculator=calculator,
        recommender=None,  # type: ignore[arg-type]  # wired right after construction
        auto_load=False,
    )
    scorer = QuotaScorer(usage_query=tracker)
    tracker._recommender = RateLimitRecommender(usage_query=tracker, scorer=scorer)
    return tracker


def _seed(path: Path, obj: Any) -> bytes:
    """Write raw JSON to a real file and return its exact bytes for identity checks."""
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return path.read_bytes()


def _model_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "requests_today": 0,
        "requests_this_month": 0,
        "tokens_today": 0,
        "tokens_this_month": 0,
        "input_tokens_today": 0,
        "output_tokens_today": 0,
        "total_requests": 0,
        "total_tokens": 0,
        "last_request": None,
        "errors": [],
    }
    entry.update(overrides)
    return entry


def _valid_doc(
    daily: str,
    monthly: str,
    *,
    providers: dict[str, Any] | None = None,
    provider_headers: dict[str, Any] | None = None,
    include_providers: bool = True,
) -> dict[str, Any]:
    doc: dict[str, Any] = {"last_reset": {"daily": daily, "monthly": monthly}}
    if include_providers:
        doc["providers"] = providers if providers is not None else {}
    if provider_headers is not None:
        doc["provider_headers"] = provider_headers
    doc["created_at"] = "2026-01-01T00:00:00"
    return doc


def _today_stamps() -> tuple[str, str]:
    today = date.today()
    return today.isoformat(), today.strftime("%Y-%m")


# =========================================================================== #
# Case 1: exact foreign seed -> pre-fix KeyError; post-fix usable empty state.
# =========================================================================== #

def test_foreign_seed_rejected_sync_no_raise_no_write(tmp_path, write_spy, caplog):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, FOREIGN_SEED)
    tracker = _real_tracker(path)

    before = len(write_spy)
    with caplog.at_level("WARNING"):
        tracker.restore_from_disk()

    summary = tracker.get_all_usage_summary()
    assert summary["providers"] == {}
    assert len(write_spy) == before  # zero writes during restore
    assert path.read_bytes() == original_bytes  # file byte-for-byte unchanged
    assert sum("malformed persisted rate-limit state" in r.message for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_foreign_seed_rejected_async_no_raise_no_write(tmp_path, write_spy, caplog):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, FOREIGN_SEED)
    tracker = _real_tracker(path)

    before = len(write_spy)
    with caplog.at_level("WARNING"):
        await tracker.restore_from_disk_async()

    assert tracker.get_all_usage_summary()["providers"] == {}
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes


# =========================================================================== #
# Case 2 + addendum B: full falsy matrix rejected; {} is a silent sentinel.
# =========================================================================== #

FALSY_AND_NONOBJECT = [
    ("null", None),
    ("false", False),
    ("true", True),
    ("zero_int", 0),
    ("zero_float", 0.0),
    ("int", 42),
    ("float", 1.5),
    ("empty_string", ""),
    ("string", "hello"),
    ("empty_list", []),
    ("list", [1, 2, 3]),
]


@pytest.mark.parametrize("label,value", FALSY_AND_NONOBJECT, ids=[c[0] for c in FALSY_AND_NONOBJECT])
def test_nonobject_json_rejected_sync(tmp_path, write_spy, caplog, label, value):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, value)
    tracker = _real_tracker(path)

    before = len(write_spy)
    with caplog.at_level("WARNING"):
        tracker.restore_from_disk()

    assert tracker.get_all_usage_summary()["providers"] == {}
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes
    assert sum("malformed persisted rate-limit state" in r.message for r in caplog.records) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("label,value", FALSY_AND_NONOBJECT, ids=[c[0] for c in FALSY_AND_NONOBJECT])
async def test_nonobject_json_rejected_async(tmp_path, write_spy, caplog, label, value):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, value)
    tracker = _real_tracker(path)

    before = len(write_spy)
    with caplog.at_level("WARNING"):
        await tracker.restore_from_disk_async()

    assert tracker.get_all_usage_summary()["providers"] == {}
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes
    assert sum("malformed persisted rate-limit state" in r.message for r in caplog.records) == 1


def test_empty_object_is_silent_sentinel_sync(tmp_path, write_spy, caplog):
    """{} is the missing/parse-error sentinel: no warning, no write, memory retained."""
    path = tmp_path / "rate_limits.json"
    # pre-populate the tracker with its own nonzero state so we can prove retention
    tracker = _real_tracker(path)
    tracker.record_request("openai", "gpt-4", input_tokens=10, output_tokens=5)
    before_summary = tracker.get_all_usage_summary()
    assert before_summary["providers"]["openai"]["total_requests_today"] == 1

    original_bytes = _seed(path, {})
    before = len(write_spy)
    with caplog.at_level("WARNING"):
        tracker.restore_from_disk()

    # empty sentinel => no warning emitted
    assert not any("malformed persisted rate-limit state" in r.message for r in caplog.records)
    assert len(write_spy) == before  # no write during the {} restore
    assert path.read_bytes() == original_bytes
    # current in-memory counters retained
    assert tracker.get_all_usage_summary()["providers"]["openai"]["total_requests_today"] == 1


@pytest.mark.asyncio
async def test_empty_object_is_silent_sentinel_async(tmp_path, write_spy, caplog):
    path = tmp_path / "rate_limits.json"
    tracker = _real_tracker(path)
    tracker.record_request("openai", "gpt-4", input_tokens=10, output_tokens=5)

    original_bytes = _seed(path, {})
    before = len(write_spy)
    with caplog.at_level("WARNING"):
        await tracker.restore_from_disk_async()

    assert not any("malformed persisted rate-limit state" in r.message for r in caplog.records)
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes
    assert tracker.get_all_usage_summary()["providers"]["openai"]["total_requests_today"] == 1


# =========================================================================== #
# Case 3: invalid nested / field values parametrized (value-level).
# =========================================================================== #

def _invalid_docs() -> list[tuple[str, dict[str, Any]]]:
    today, month = _today_stamps()
    return [
        # last_reset shape / stamps
        ("last_reset_missing", {"providers": {}}),
        ("last_reset_non_mapping", {"last_reset": "nope", "providers": {}}),
        ("daily_non_date", _valid_doc("not-a-date", month)),
        ("daily_noncanonical_width", _valid_doc("2026-1-5", month)),
        ("daily_impossible", _valid_doc("2026-02-30", month)),
        ("daily_not_string", {"last_reset": {"daily": 20260101, "monthly": month}}),
        ("monthly_non_month", _valid_doc(today, "not-a-month")),
        ("monthly_impossible", _valid_doc(today, "2026-13")),
        ("monthly_wrong_width", _valid_doc(today, "2026-1")),
        # providers container
        ("providers_non_mapping", {"last_reset": {"daily": today, "monthly": month}, "providers": "nope"}),
        ("providers_null", {"last_reset": {"daily": today, "monthly": month}, "providers": None}),
        ("provider_value_non_mapping", _valid_doc(today, month, providers={"openai": "nope"})),
        ("model_entry_non_mapping", _valid_doc(today, month, providers={"openai": {"gpt-4": "nope"}})),
        (
            "model_entry_missing_counter",
            _valid_doc(today, month, providers={"openai": {"gpt-4": {k: 0 for k in (
                "requests_today", "requests_this_month", "tokens_today", "tokens_this_month",
                "input_tokens_today", "output_tokens_today", "total_requests",
            )} | {"errors": []}}}),
        ),
        (
            "counter_is_string",
            _valid_doc(today, month, providers={"openai": {"gpt-4": _model_entry(requests_today="5")}}),
        ),
        (
            "counter_is_bool",
            _valid_doc(today, month, providers={"openai": {"gpt-4": _model_entry(requests_today=True)}}),
        ),
        (
            "counter_negative",
            _valid_doc(today, month, providers={"openai": {"gpt-4": _model_entry(requests_today=-1)}}),
        ),
        (
            "errors_not_list",
            _valid_doc(today, month, providers={"openai": {"gpt-4": _model_entry(errors={})}}),
        ),
        (
            "last_request_wrong_type",
            _valid_doc(today, month, providers={"openai": {"gpt-4": _model_entry(last_request=123)}}),
        ),
        # provider_headers
        (
            "provider_headers_non_mapping",
            _valid_doc(today, month, provider_headers="nope"),
        ),
        (
            "provider_headers_scalar_value",
            _valid_doc(today, month, provider_headers={"groq": 5}),
        ),
        (
            "remaining_requests_string",
            _valid_doc(today, month, provider_headers={"groq": {"remaining_requests": "bad"}}),
        ),
        (
            "remaining_requests_month_string",
            _valid_doc(today, month, provider_headers={"groq": {"remaining_requests_month": "bad"}}),
        ),
        (
            "remaining_requests_month_bool",
            _valid_doc(today, month, provider_headers={"groq": {"remaining_requests_month": True}}),
        ),
        (
            "limit_tokens_bool",
            _valid_doc(today, month, provider_headers={"groq": {"limit_tokens": False}}),
        ),
        (
            "last_updated_non_iso",
            _valid_doc(today, month, provider_headers={"groq": {"last_updated": "yesterday"}}),
        ),
        (
            "last_updated_date_only",
            _valid_doc(today, month, provider_headers={"groq": {"last_updated": "2026-10-05"}}),
        ),
        (
            "retry_at_offset_aware",
            _valid_doc(today, month, provider_headers={"groq": {"retry_at": "2026-10-05T01:02:03+00:00"}}),
        ),
    ]


@pytest.mark.parametrize("label,doc", _invalid_docs(), ids=[c[0] for c in _invalid_docs()])
def test_invalid_documents_rejected_sync(tmp_path, write_spy, caplog, label, doc):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, doc)
    tracker = _real_tracker(path)

    before = len(write_spy)
    with caplog.at_level("WARNING"):
        tracker.restore_from_disk()

    assert tracker.get_all_usage_summary()["providers"] == {}
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes
    assert sum("malformed persisted rate-limit state" in r.message for r in caplog.records) == 1


# =========================================================================== #
# Addendum C: accepted header values (int / null / signed / zero) are adopted.
# =========================================================================== #

@pytest.mark.parametrize(
    "month_value, expected_downstream_month",
    [
        (250, 250),  # int adopted verbatim
        (None, 10),  # null accepted; consumer approximates from remaining_requests
    ],
    ids=["month_int", "month_null"],
)
def test_valid_header_values_accepted(
    tmp_path, write_spy, month_value, expected_downstream_month
):
    today, month = _today_stamps()
    headers = {
        "groq": {
            "remaining_requests": 10,
            "remaining_requests_month": month_value,
            "remaining_tokens": 0,  # zero accepted
            "limit_requests": -1,  # signed accepted (parser can store negatives)
            "limit_tokens": None,  # null accepted
            "last_updated": datetime.now().isoformat(),  # fractional naive iso
            "retry_at": "2026-10-05T01:02:03",  # zero-microsecond naive iso
            "raw_headers": {"x-foo": "bar"},  # opaque, retained
            "reset_requests": "6s",  # opaque free string, retained
        }
    }
    doc = _valid_doc(today, month, providers={}, provider_headers=headers)
    _seed(path := tmp_path / "rate_limits.json", doc)
    tracker = _real_tracker(path)

    tracker.restore_from_disk()  # must not raise

    stored = tracker.get_provider_headers("groq")
    assert stored is not None
    assert stored["remaining_requests"] == 10
    assert stored["limit_tokens"] is None
    assert stored["raw_headers"] == {"x-foo": "bar"}  # opaque metadata retained
    # remaining_requests_month is a CONSUMED key the parser never emits, so both an
    # int and an explicit null must survive the guard and reach the consumer.
    assert stored["remaining_requests_month"] == month_value  # adopted verbatim
    remaining = tracker.get_remaining_quota("groq", "llama-3.3-70b-versatile", LIMITS)
    assert remaining["_source"] == "headers"  # header data was fresh and used
    assert remaining["requests_remaining_month"] == expected_downstream_month


# =========================================================================== #
# Case 4: pathless StorageProtocol dependency -> warning, no AttributeError.
# =========================================================================== #

class _PathlessStorage:
    """A conforming StorageProtocol double WITHOUT a `path` attribute."""

    def __init__(self, blob: Any):
        self._blob = blob

    def load(self) -> dict[str, Any]:
        return self._blob

    async def load_async(self) -> dict[str, Any]:
        return self._blob

    def save(self, data: dict[str, Any]) -> None:  # pragma: no cover - must not fire
        raise AssertionError("save must not be called on a rejected restore")

    async def save_async(self, data: dict[str, Any]) -> None:  # pragma: no cover
        raise AssertionError("save_async must not be called on a rejected restore")


def test_pathless_storage_warns_without_attributeerror(caplog):
    tracker = RateLimitTracker(
        storage=_PathlessStorage(FOREIGN_SEED),
        policy=RateLimitPolicy(),
        calculator=RateLimitCalculator(),
        recommender=None,  # type: ignore[arg-type]
        auto_load=False,
    )
    assert not hasattr(tracker._storage, "path")

    with caplog.at_level("WARNING"):
        tracker.restore_from_disk()  # must not raise AttributeError

    assert sum("malformed persisted rate-limit state" in r.message for r in caplog.records) == 1
    assert tracker.get_all_usage_summary()["providers"] == {}


# =========================================================================== #
# Case 5: fresh-startup rejection -> usable empty state, no write.
# =========================================================================== #

def test_fresh_startup_rejection_usable_empty(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, FOREIGN_SEED)

    before = len(write_spy)
    tracker = _real_tracker(path)
    tracker.restore_from_disk()

    summary = tracker.get_all_usage_summary()
    assert summary["providers"] == {}
    # the rejected restore performed no write and left the file byte-for-byte intact
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes
    # usable: a subsequent deliberate record works and is the FIRST write to occur
    tracker.record_request("openai", "gpt-4", input_tokens=1, output_tokens=1)
    assert tracker.get_all_usage_summary()["providers"]["openai"]["total_requests_today"] == 1
    assert len(write_spy) == before + 1


# =========================================================================== #
# Case 6: used-tracker rejection retains nonzero period AND lifetime counters.
# =========================================================================== #

def test_used_tracker_rejection_retains_counters(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    tracker = _real_tracker(path)
    tracker.record_request("openai", "gpt-4", input_tokens=100, output_tokens=50)
    tracker.record_request("openai", "gpt-4", input_tokens=10, output_tokens=5)

    usage_before = tracker.get_usage("openai", "gpt-4")
    assert usage_before["requests_today"] == 2
    assert usage_before["total_requests"] == 2
    assert usage_before["total_tokens"] == 165

    _seed(path, FOREIGN_SEED)
    before = len(write_spy)
    tracker.restore_from_disk()  # malformed -> no-op

    usage_after = tracker.get_usage("openai", "gpt-4")
    assert usage_after["requests_today"] == 2  # period counter retained
    assert usage_after["total_requests"] == 2  # lifetime counter retained
    assert usage_after["total_tokens"] == 165
    assert len(write_spy) == before  # zero writes during the rejected restore


# =========================================================================== #
# Case 7: valid-current NONZERO -> adopted verbatim, no reset, no write; both APIs.
# =========================================================================== #

def _valid_current_nonzero() -> dict[str, Any]:
    today, month = _today_stamps()
    return _valid_doc(
        today,
        month,
        providers={
            "openai": {
                "gpt-4": _model_entry(
                    requests_today=7,
                    requests_this_month=70,
                    tokens_today=700,
                    tokens_this_month=7000,
                    input_tokens_today=400,
                    output_tokens_today=300,
                    total_requests=123,
                    total_tokens=45678,
                    last_request="2026-10-05T00:00:00",
                )
            }
        },
    )


def test_valid_current_nonzero_adopted_no_write_sync(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, _valid_current_nonzero())
    tracker = _real_tracker(path)

    before = len(write_spy)
    tracker.restore_from_disk()

    usage = tracker.get_usage("openai", "gpt-4")
    assert usage["requests_today"] == 7
    assert usage["total_requests"] == 123
    assert usage["total_tokens"] == 45678
    assert len(write_spy) == before  # valid-current => no reset => no write
    assert path.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_valid_current_nonzero_roundtrips_async(tmp_path, write_spy):
    """Proves the real file is read on the async API (not a swallowed FileNotFoundError)."""
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, _valid_current_nonzero())
    tracker = _real_tracker(path)

    before = len(write_spy)
    await tracker.restore_from_disk_async()

    usage = tracker.get_usage("openai", "gpt-4")
    assert usage["requests_today"] == 7  # nonzero ONLY if the file was truly parsed
    assert usage["total_requests"] == 123
    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_valid_current_nonzero_async_fallback_branch(tmp_path, write_spy, monkeypatch):
    """Documented no-aiofiles fallback: load_async delegates to sync load."""
    monkeypatch.setattr(storage_module, "_AIO", False)
    path = tmp_path / "rate_limits.json"
    _seed(path, _valid_current_nonzero())
    tracker = _real_tracker(path)

    await tracker.restore_from_disk_async()

    assert tracker.get_usage("openai", "gpt-4")["requests_today"] == 7


@pytest.mark.asyncio
async def test_valid_current_nonzero_async_normal_aiofiles_branch(tmp_path, write_spy):
    """Normal aiofiles path when installed; otherwise explicitly SKIPPED (not reinterpreted)."""
    if not storage_module._AIO:
        pytest.skip("aiofiles not installed: normal async branch unavailable in this env")
    path = tmp_path / "rate_limits.json"
    _seed(path, _valid_current_nonzero())
    tracker = _real_tracker(path)

    await tracker.restore_from_disk_async()

    assert tracker.get_usage("openai", "gpt-4")["requests_today"] == 7


# =========================================================================== #
# Case 8: valid-expired -> selected-period reset, lifetime preserved, one rewrite.
# =========================================================================== #

def test_valid_expired_resets_period_preserves_lifetime(tmp_path, write_spy):
    # stale stamps => real policy (today) fires both daily and monthly reset
    doc = _valid_doc(
        "2000-01-01",
        "2000-01",
        providers={
            "openai": {
                "gpt-4": _model_entry(
                    requests_today=7,
                    requests_this_month=70,
                    tokens_today=700,
                    tokens_this_month=7000,
                    input_tokens_today=400,
                    output_tokens_today=300,
                    total_requests=123,
                    total_tokens=45678,
                )
            }
        },
    )
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, doc)
    tracker = _real_tracker(path)

    before = len(write_spy)
    tracker.restore_from_disk()

    usage = tracker.get_usage("openai", "gpt-4")
    assert usage["requests_today"] == 0  # daily period reset
    assert usage["tokens_today"] == 0
    assert usage["requests_this_month"] == 0  # monthly period reset
    assert usage["tokens_this_month"] == 0
    assert usage["total_requests"] == 123  # lifetime NEVER reset
    assert usage["total_tokens"] == 45678
    assert len(write_spy) == before + 1  # exactly one legitimate rewrite
    assert path.read_bytes() != original_bytes  # file was rewritten


# =========================================================================== #
# Case 9/C: meaningful consumer exercise after restore (not mere construction).
# =========================================================================== #

def test_consumers_operate_after_valid_adoption(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    _seed(path, _valid_current_nonzero())
    tracker = _real_tracker(path)
    tracker.restore_from_disk()

    # summarise over real calculator
    summary = tracker.get_all_usage_summary()
    assert summary["providers"]["openai"]["total_requests_today"] == 7

    # remaining quota math over real calculator
    remaining = tracker.get_remaining_quota("openai", "gpt-4", LIMITS)
    assert remaining["requests_remaining_today"] == 1000 - 7

    # successful record increments; failed record appends an error
    tracker.record_request("openai", "gpt-4", input_tokens=5, output_tokens=5)
    assert tracker.get_usage("openai", "gpt-4")["requests_today"] == 8
    tracker.record_request("openai", "gpt-4", success=False, error_message="boom")
    assert tracker.get_usage("openai", "gpt-4")["errors"][-1]["message"] == "boom"


def test_consumers_operate_after_malformed_rejection(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    _seed(path, FOREIGN_SEED)
    tracker = _real_tracker(path)
    tracker.restore_from_disk()

    assert tracker.get_all_usage_summary()["providers"] == {}
    remaining = tracker.get_remaining_quota("openai", "gpt-4", LIMITS)
    assert remaining["requests_remaining_today"] == 1000
    tracker.record_request("openai", "gpt-4", input_tokens=5, output_tokens=5)
    assert tracker.get_usage("openai", "gpt-4")["requests_today"] == 1


# =========================================================================== #
# Addendum C: providers MAY be absent (accepted subset).
# =========================================================================== #

def test_missing_providers_accepted_with_valid_stamps(tmp_path, write_spy, caplog):
    today, month = _today_stamps()
    # DISTINGUISHING observation. An empty summary, no startup write and a working
    # subsequent record all hold whether the document is accepted OR rejected, so
    # those assertions alone cannot detect a guard that wrongly rejects this valid
    # document. Only acceptance ADOPTS this unique opaque metadata.
    headers = {
        "groq": {
            "remaining_requests": 7,
            "raw_headers": {"x-trace": "missing-providers-marker"},
        }
    }
    doc = _valid_doc(
        today, month, include_providers=False, provider_headers=headers
    )  # no providers key
    path = tmp_path / "rate_limits.json"
    _seed(path, doc)
    tracker = _real_tracker(path)

    before = len(write_spy)
    with caplog.at_level("WARNING"):
        tracker.restore_from_disk()  # accepted; no forced startup save

    assert sum(
        "malformed persisted rate-limit state" in r.message for r in caplog.records
    ) == 0  # accepted, so no rejection warning
    stored = tracker.get_provider_headers("groq")
    assert stored is not None  # rejection would adopt nothing
    assert stored["remaining_requests"] == 7
    assert stored["raw_headers"] == {"x-trace": "missing-providers-marker"}
    # the absent providers key is PRESERVED, not coerced into existence
    assert tracker.get_all_usage_summary()["providers"] == {}
    assert len(write_spy) == before  # valid-current, missing providers => no write
    # a subsequent normal record works
    tracker.record_request("openai", "gpt-4", input_tokens=1, output_tokens=1)
    assert tracker.get_usage("openai", "gpt-4")["requests_today"] == 1


# =========================================================================== #
# Case 9b: the REAL current writers produce a document the guard accepts.
# =========================================================================== #

WRITER_MODEL = "llama-3.3-70b-versatile"


def test_real_writer_output_restores_into_useful_state(tmp_path, write_spy, caplog):
    """Real writers -> real disk -> fresh tracker restore -> useful state.

    This is the writer-compatibility oracle. Every other acceptance case seeds a
    hand-built document, which establishes only that example: a guard incompatible
    with a different VALID writer shape would still pass. Here the document is
    produced by the CURRENT writers themselves, through both required APIs.
    """
    path = tmp_path / "rate_limits.json"
    writer = _real_tracker(path)

    # Writer API 1: the real record path, success AND error, so counters and the
    # errors list are both genuinely nonzero.
    writer.record_request(
        "groq", WRITER_MODEL, input_tokens=120, output_tokens=80, success=True
    )
    # A failure deliberately does NOT increment counters (see _update_counters);
    # it appends to the errors list, and only when error_message is supplied. That
    # makes the errors list genuinely nonempty in real writer output.
    writer.record_request(
        "groq",
        WRITER_MODEL,
        input_tokens=10,
        output_tokens=5,
        success=False,
        error_message="upstream 429",
    )
    # Writer API 2: the real header writer.
    writer.update_from_headers(
        "groq",
        {
            "x-ratelimit-remaining-requests": "42",
            "x-ratelimit-limit-requests": "100",
            "x-ratelimit-remaining-tokens": "9000",
            "x-ratelimit-reset-requests": "6s",
        },
    )
    # Writer API 3: the real error writer.
    writer.update_from_error(
        "groq",
        {
            "retry_after_seconds": 30,
            "quota_type": "requests",
            "message": "rate limit exceeded",
        },
    )

    # The state must have actually reached disk, and be nonzero there.
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    disk_entry = on_disk["providers"]["groq"][WRITER_MODEL]
    assert disk_entry["requests_today"] == 1  # only the success counts against quota
    assert disk_entry["total_tokens"] > 0
    assert len(disk_entry["errors"]) == 1  # real writer populated the errors list

    # A FRESH tracker over the SAME real file: the guard must ACCEPT real output.
    restored = _real_tracker(path)
    before = len(write_spy)
    with caplog.at_level("WARNING"):
        restored.restore_from_disk()

    assert sum(
        "malformed persisted rate-limit state" in r.message for r in caplog.records
    ) == 0  # real writer output is not malformed
    assert len(write_spy) == before  # valid-current => no reset => no write

    # Useful restored quota state, compared against the actual persisted values
    # rather than re-deriving the writers' arithmetic.
    usage = restored.get_usage("groq", WRITER_MODEL)
    assert usage["requests_today"] == 1
    assert usage["errors"] == disk_entry["errors"]  # real error entries survived
    assert usage["total_tokens"] == disk_entry["total_tokens"]
    assert usage["total_requests"] == disk_entry["total_requests"]
    assert "groq" in restored.get_all_usage_summary()["providers"]  # not empty

    # Both writers' provider data survived the roundtrip.
    headers = restored.get_provider_headers("groq")
    assert headers["remaining_requests"] == 42  # from update_from_headers
    assert headers["retry_after_seconds"] == 30  # from update_from_error
    assert headers["quota_exceeded"] == "requests"
    remaining = restored.get_remaining_quota("groq", WRITER_MODEL, LIMITS)
    assert remaining["_source"] == "headers"
    assert remaining["requests_remaining_today"] == 42

    # Success AND error operations still work on top of the restored counters.
    restored.record_request(
        "groq", WRITER_MODEL, input_tokens=1, output_tokens=1, success=True
    )
    restored.record_request(
        "groq",
        WRITER_MODEL,
        input_tokens=1,
        output_tokens=1,
        success=False,
        error_message="later 429",
    )
    after = restored.get_usage("groq", WRITER_MODEL)
    assert after["requests_today"] == 2  # restored 1 + 1 new success
    assert len(after["errors"]) == 2  # restored 1 + 1 new error


# =========================================================================== #
# Case 10: sync/async parity on the foreign seed and one invalid-field case.
# =========================================================================== #

@pytest.mark.asyncio
async def test_sync_async_parity_invalid_field(tmp_path, write_spy):
    today, month = _today_stamps()
    doc = _valid_doc(today, month, providers={"openai": {"gpt-4": _model_entry(requests_today="5")}})

    sync_path = tmp_path / "sync.json"
    _seed(sync_path, doc)
    sync_tracker = _real_tracker(sync_path)
    sync_tracker.restore_from_disk()

    async_path = tmp_path / "async.json"
    _seed(async_path, doc)
    async_tracker = _real_tracker(async_path)
    await async_tracker.restore_from_disk_async()

    assert sync_tracker.get_all_usage_summary()["providers"] == {}
    assert async_tracker.get_all_usage_summary()["providers"] == {}


# =========================================================================== #
# Case 11: factory auto_load usable-state proof (exercises the real failing call).
# =========================================================================== #

def test_factory_create_tracker_autoload_malformed_usable(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, FOREIGN_SEED)

    before = len(write_spy)
    tracker = create_rate_limit_tracker(tracker_file=str(path), auto_load=True)

    assert len(write_spy) == before  # zero writes during construction
    assert path.read_bytes() == original_bytes
    assert tracker.get_all_usage_summary()["providers"] == {}  # usable empty state


def test_factory_create_components_autoload_malformed_usable(tmp_path, write_spy):
    path = tmp_path / "rate_limits.json"
    original_bytes = _seed(path, FOREIGN_SEED)

    before = len(write_spy)
    components = create_rate_limit_components(tracker_file=str(path), auto_load=True)

    assert len(write_spy) == before
    assert path.read_bytes() == original_bytes
    assert components.tracker.get_all_usage_summary()["providers"] == {}
