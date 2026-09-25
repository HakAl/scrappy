"""Ambient rate-limit file is not mutated by a provider-routed tracker (scrappy-i2jo).

THE OBLIGATION. `tests/containment/seed.py` seeds command history and the
platform config but NOT `rate_limits.json`, so no measurement has ever shown that
a PRE-EXISTING ambient rate-limits file survives a run untouched. Provider
migration and tracker persistence are proved separately; neither proves
non-mutation of an independently seeded ambient file, because no such file exists
during those runs.

SEED BEFORE CONSTRUCTION. The seed is written BEFORE the real orchestrator and
tracker are composed, so construction genuinely runs against a pre-existing
ambient file. Seeding afterwards could not exercise that at all. The negative
control uses the SAME ordering, so the only difference between it and the
positive case is the omitted provider.

WHY NO cktc FIX IS NEEDED. `tracker.py:466` reads `last_reset` via `.get`, but
`:472-473` index it DIRECTLY, so a KeyError needs BOTH a state lacking
`last_reset` AND a reset being judged necessary. A COMPLETE VALID state never
hits the missing-key failure. Note this is NOT the same as saying validity avoids
the reset: a valid but EXPIRED state DOES reach that indexing, and it is safe
precisely because the mapping exists. `test_expired_valid_state_resets_through_the_real_tracker`
exercises exactly that. `scrappy-cktc` remains a separate bug about genuinely
malformed state, untouched here.

TWO SEPARATE CLOCKS. The policy captures a DATE at construction; the tracker
reads `datetime.now` independently when it writes. The routing tests pin only the
policy date and assert no tracker timestamps. The expired-reset leaf pins BOTH,
to deliberately different values, so its persisted dates are deterministic rather
than dependent on the real calendar. A superseded version of that leaf asserted
the persisted dates equalled the POLICY date with the tracker clock left
unpatched; it passed only because the real date happened to match, and it
contradicted this module's own stated claim. That is corrected, and the history
is recorded rather than quietly dropped.

WHAT THIS ESTABLISHES, and what it does not. It establishes that a routed
tracker persists to the PROVIDER file while the pre-existing ambient file's FINAL
BYTES are unchanged. It does NOT establish absence of reads, absence of a
transient write-and-restore, anything about other platforms, or the separate
full-workload rate-seed obligation. It does not close i2jo.
"""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scrappy.infrastructure import paths as paths_module
from scrappy.infrastructure.paths import TempPathProvider, create_default_path_provider
from scrappy.orchestrator.core import create_orchestrator
from scrappy.orchestrator.rate_limiting import httpx_patcher
from scrappy.orchestrator.rate_limiting import policy as policy_module
from scrappy.orchestrator.rate_limiting.policy import RateLimitPolicy
from scrappy.orchestrator.rate_limiting import tracker as tracker_module
from scrappy.orchestrator.rate_limiting.factory import create_rate_limit_tracker

PINNED = date(2026, 9, 25)

# DELIBERATELY DIFFERENT from PINNED. The policy date and the tracker's own
# datetime.now are SEPARATE clocks, and the expired-reset proof pins the tracker
# one so its persisted values are deterministic rather than whatever today
# happens to be. Choosing a distinct date also makes the separation observable:
# if the two were the same clock, the assertions below could not both hold.
TRACKER_NOW = datetime(2026, 10, 3, 11, 22, 33)

# Literal declared seeds. Exactly these bytes; any write is visible as a size or
# digest change against the manifest.
AMBIENT_SEED = (
    b'{\n'
    b'  "providers": {},\n'
    b'  "last_reset": {"daily": "2026-09-25", "monthly": "2026-09"},\n'
    b'  "created_at": "2026-09-25T00:00:00"\n'
    b'}\n'
)
EXPIRED_SEED = (
    b'{\n'
    b'  "providers": {},\n'
    b'  "last_reset": {"daily": "2026-08-01", "monthly": "2026-08"},\n'
    b'  "created_at": "2026-08-01T00:00:00"\n'
    b'}\n'
)
AMBIENT_SEED_SHA256 = "98a22c7727888e98b0a9202a0440967d41e0ffdeaf6e0b9e1541757bd97cc501"
EXPIRED_SEED_SHA256 = "e8a5b9bb73b62b20a61664958fae010bea8e26ffd1433d906acbb470cb951a9e"

PROVIDER_NAME = "groq"
MODEL_NAME = "llama-3.3-70b-versatile"


@pytest.fixture
def mock_mode(monkeypatch):
    """Deterministic, latency-free mock mode so the helper needs no API keys."""
    monkeypatch.setenv("SCRAPPY_MOCK_LLM", "1")
    monkeypatch.setenv("SCRAPPY_MOCK_LATENCY_MS", "0")
    monkeypatch.setenv("SCRAPPY_MOCK_RESPONSE", "Mock response")


@pytest.fixture
def restored_http_hooks():
    """Snapshot and RESTORE all six pieces of HTTP hook state.

    The real factory installs hooks (factory.py:377-381) and
    httpx_patcher.install_rate_limit_hooks mutates four module fields plus BOTH
    httpx client constructors. Its uninstall resets to the NO-HOOKS state, so an
    unconditional uninstall would DISCARD whatever was installed before this
    test rather than restore it. Real installation behaviour is left intact.
    """
    saved = (
        httpx_patcher._handler,
        httpx_patcher._installed,
        httpx_patcher._original_client_init,
        httpx_patcher._original_async_client_init,
        httpx.Client.__init__,
        httpx.AsyncClient.__init__,
    )
    try:
        yield
    finally:
        (
            httpx_patcher._handler,
            httpx_patcher._installed,
            httpx_patcher._original_client_init,
            httpx_patcher._original_async_client_init,
            httpx.Client.__init__,
            httpx.AsyncClient.__init__,
        ) = saved


def _roots(tmp_path: Path) -> SimpleNamespace:
    """Five distinct disposable roots. Fresh per case, so an earlier positive
    file can never mask a dropped provider."""
    code = tmp_path / "code_root"
    cwd = tmp_path / "cwd_root"
    provider = tmp_path / "provider_root"
    profile = tmp_path / "profile_root"
    legacy = tmp_path / "legacy" / ".scrappy"
    for p in (code, cwd, provider, profile):
        p.mkdir(parents=True)
    legacy.mkdir(parents=True)
    return SimpleNamespace(code=code, cwd=cwd, provider=provider,
                           profile=profile, legacy=legacy)


def _control_discovery(monkeypatch, roots) -> None:
    """Patch the PATHS MODULE, not Path.home.

    create_default_path_provider reads the three platformdirs lookups and
    CAPTURES the import-bound LEGACY_USER_DIR, so a Path.home patch would not
    reach the legacy source. Neither the ambient nor the provider destination may
    fall back to the real profile.
    """
    monkeypatch.setattr(paths_module, "user_data_dir",
                        lambda app: str(roots.profile / app / "data"))
    monkeypatch.setattr(paths_module, "user_config_dir",
                        lambda app: str(roots.profile / app / "config"))
    monkeypatch.setattr(paths_module, "user_cache_dir",
                        lambda app: str(roots.profile / app / "cache"))
    monkeypatch.setattr(paths_module, "LEGACY_USER_DIR", roots.legacy)


def _pin_policy_date(monkeypatch) -> None:
    """Pin ONLY the external date boundary the policy reads.

    Real policy and real tracker logic stay intact. The tracker's own
    datetime.now is a SEPARATE clock and is NOT pinned by this helper; the
    routing tests below do not assert tracker timestamps at all.
    """
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return PINNED

    monkeypatch.setattr(policy_module, "date", _FixedDate)


def _pin_tracker_clock(monkeypatch) -> None:
    """Pin ONLY the external datetime boundary the TRACKER module reads.

    Used by the expired-reset leaf test alone, so its persisted values are
    deterministic instead of depending on whatever the real calendar says.
    tracker.py does `from datetime import datetime`, so the module attribute is
    the seam. monkeypatch restores it automatically; real tracker, policy and
    storage logic are untouched and no production clock changes.
    """
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return TRACKER_NOW

    monkeypatch.setattr(tracker_module, "datetime", _FixedDateTime)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_and_validate(roots) -> SimpleNamespace:
    """Resolve both destinations and assert they are where they must be.

    Runs BEFORE the seed is written, so the test knows which file it is watching
    rather than discovering it afterwards.
    """
    default_provider = create_default_path_provider(roots.code)
    ambient = default_provider.rate_limits_file()
    provider = TempPathProvider(roots.provider)
    provider_file = provider.rate_limits_file()

    assert ambient.is_relative_to(roots.profile), (
        f"ambient destination {ambient} is not under the disposable profile {roots.profile}"
    )
    assert provider_file.is_relative_to(roots.provider), (
        f"provider destination {provider_file} is not under {roots.provider}"
    )
    assert ambient != provider_file
    return SimpleNamespace(provider=provider, ambient=ambient, provider_file=provider_file)


def _seed_ambient(ambient: Path) -> None:
    """Write the pre-existing ambient file BEFORE any composition."""
    ambient.parent.mkdir(parents=True, exist_ok=True)
    ambient.write_bytes(AMBIENT_SEED)
    assert _digest(ambient) == AMBIENT_SEED_SHA256


def _assert_routed_persistence(targets, monkeypatch, roots, *, path_provider) -> None:
    """THE SHARED ORACLE, run unchanged by the positive case and the control.

    Seed-before-construction ordering, then a real composed request, then the
    destination and ambient assertions.
    """
    # Compose at the CODE root so the code root is captured at composition.
    monkeypatch.chdir(roots.code)
    if path_provider is None:
        orch = create_orchestrator()
    else:
        orch = create_orchestrator(path_provider=path_provider)

    # Move to a DISTINCT cwd before any usage or assertion.
    monkeypatch.chdir(roots.cwd)
    orch.rate_tracker.record_request(PROVIDER_NAME, MODEL_NAME, input_tokens=7)

    # EXISTENCE asserted with the intended message BEFORE opening, so a dropped
    # provider is rejected HERE and not as an incidental FileNotFoundError.
    assert targets.provider_file.is_file(), (
        f"expected the routed tracker to persist requests_today==1 for "
        f"{PROVIDER_NAME}/{MODEL_NAME} at the provider destination "
        f"{targets.provider_file}, but no file exists there"
    )
    recorded = json.loads(targets.provider_file.read_text())
    assert recorded["providers"][PROVIDER_NAME][MODEL_NAME]["requests_today"] == 1

    # FINAL-BYTE preservation of the pre-existing ambient seed. This is final
    # state only; it does not establish absence of reads or transient writes.
    assert targets.ambient.read_bytes() == AMBIENT_SEED
    assert _digest(targets.ambient) == AMBIENT_SEED_SHA256


class TestFixtureValidity:
    """Leaf-level validity, separate from routing."""

    def test_current_valid_state_needs_no_reset(self):
        policy = RateLimitPolicy(today=PINNED)
        state = json.loads(AMBIENT_SEED)
        assert policy.reset_needed(state["last_reset"]) == {"daily": False, "monthly": False}

    def test_expired_valid_state_needs_a_reset(self):
        policy = RateLimitPolicy(today=PINNED)
        state = json.loads(EXPIRED_SEED)
        assert policy.reset_needed(state["last_reset"]) == {"daily": True, "monthly": True}

    def test_expired_valid_state_resets_through_the_real_tracker(self, tmp_path, monkeypatch):
        """The reset branch runs to completion, with no KeyError.

        Flags alone would not establish this. A real tracker loads the expired
        bytes and performs the reset, reaching tracker.py:472-473, which is safe
        because the last_reset MAPPING EXISTS. Validity does not imply no reset.

        CALENDAR INDEPENDENCE. The persisted reset dates come from the TRACKER's
        own datetime.now, NOT from the policy date, so this test pins the tracker
        module's datetime boundary and asserts against THAT clock. An earlier
        version asserted these fields equalled the POLICY date while leaving the
        tracker clock unpatched: that passed only because the real date happened
        to be 2026-09-25, and it contradicted this module's own claim not to
        compare tracker timestamps to the policy date. Both clocks are pinned
        here, to DELIBERATELY DIFFERENT values, which makes the proof
        deterministic and makes their separation observable.
        """
        _pin_policy_date(monkeypatch)      # policy sees 2026-09-25
        _pin_tracker_clock(monkeypatch)    # tracker sees 2026-10-03
        assert TRACKER_NOW.date() != PINNED, "the two clocks must differ for this to discriminate"

        state_file = tmp_path / "rate_limits.json"
        state_file.write_bytes(EXPIRED_SEED)
        assert _digest(state_file) == EXPIRED_SEED_SHA256

        tracker = create_rate_limit_tracker(tracker_file=str(state_file), auto_load=True)
        tracker.record_request(PROVIDER_NAME, MODEL_NAME, input_tokens=7)

        recorded = json.loads(state_file.read_text())

        # The reset actually happened: the stored dates moved off the expired
        # seed's August values, which is what discriminates a reset from a no-op.
        seeded = json.loads(EXPIRED_SEED)["last_reset"]
        assert recorded["last_reset"]["daily"] != seeded["daily"]
        assert recorded["last_reset"]["monthly"] != seeded["monthly"]

        # And they carry the TRACKER's clock, not the policy's.
        assert recorded["last_reset"]["daily"] == TRACKER_NOW.date().isoformat()
        assert recorded["last_reset"]["monthly"] == TRACKER_NOW.strftime("%Y-%m")
        assert recorded["last_reset"]["daily"] != PINNED.isoformat()

        assert recorded["providers"][PROVIDER_NAME][MODEL_NAME]["requests_today"] == 1


class TestAmbientPreservationUnderRouting:
    """The routing proof, and its negative control, on identical ordering."""

    def test_routed_tracker_persists_to_provider_and_leaves_the_ambient_seed_intact(
        self, tmp_path, monkeypatch, mock_mode, restored_http_hooks
    ):
        roots = _roots(tmp_path)
        _control_discovery(monkeypatch, roots)
        _pin_policy_date(monkeypatch)

        targets = _resolve_and_validate(roots)
        _seed_ambient(targets.ambient)

        _assert_routed_persistence(targets, monkeypatch, roots,
                                   path_provider=targets.provider)

    def test_omitting_the_provider_is_rejected_by_the_destination_assertion(
        self, tmp_path, monkeypatch, mock_mode, restored_http_hooks
    ):
        """ROUTING NEGATIVE CONTROL, identical ordering, provider omitted.

        core.py forwards None and the factory then builds a DEFAULT provider from
        the controlled discovery inputs, so the write lands at the disposable
        AMBIENT destination. That is a real routing failure against the declared
        provider destination. It is NOT the separate falsey-provider project
        fallback at factory.py:364-370, which this control does not exercise.
        """
        roots = _roots(tmp_path)
        _control_discovery(monkeypatch, roots)
        _pin_policy_date(monkeypatch)

        targets = _resolve_and_validate(roots)
        _seed_ambient(targets.ambient)

        with pytest.raises(
            AssertionError, match=r"expected the routed tracker to persist"
        ) as excinfo:
            _assert_routed_persistence(targets, monkeypatch, roots, path_provider=None)
        assert str(targets.provider_file) in str(excinfo.value)

        # Supporting evidence for where the write actually went: the ambient file
        # received it, which is exactly why the provider destination is empty.
        assert not targets.provider_file.exists()
        assert targets.ambient.is_file()
        fallback = json.loads(targets.ambient.read_text())
        assert fallback["providers"][PROVIDER_NAME][MODEL_NAME]["requests_today"] == 1
