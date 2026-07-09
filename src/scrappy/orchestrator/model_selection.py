"""
Model selection types and service.

Provides deterministic model selection with session stickiness and rate limit awareness.
"""

import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Protocol

from scrappy.infrastructure.exceptions.failure_kinds import FailureKind

from .failure_policy import FailureRecord, HealthScope, get_failure_policy
from .provider_catalog import build_default_catalog


logger = logging.getLogger(__name__)


class SelectionExhaustedError(Exception):
    """Raised when no model remains available for a selection type."""

    def __init__(
        self,
        message: str,
        failure_summary: Optional[dict[str, FailureRecord]] = None,
    ) -> None:
        super().__init__(message)
        self.failure_summary = failure_summary or {}
        self.suggestion = _build_selection_exhausted_suggestion(
            self.failure_summary
        )


AllModelsRateLimitedError = SelectionExhaustedError


def _build_selection_exhausted_suggestion(
    failure_summary: dict[str, FailureRecord],
) -> str:
    """Build user guidance from concrete model failure records."""
    if not failure_summary:
        return "Configure another model or try again later."

    entries = []
    for model, record in sorted(failure_summary.items()):
        provider = record.provider or "unknown"
        entries.append(f"{model} ({provider}: {record.kind.value})")

    kinds = {record.kind for record in failure_summary.values()}
    parts = [f"Unavailable models: {', '.join(entries)}."]

    if FailureKind.RATE_LIMIT in kinds:
        waits = [
            record.retry_after
            for record in failure_summary.values()
            if record.kind == FailureKind.RATE_LIMIT and record.retry_after is not None
        ]
        if waits:
            parts.append(
                f"Wait at least {min(waits):.0f}s before retrying rate-limited models."
            )
        else:
            parts.append("Wait before retrying rate-limited models.")

    if FailureKind.AUTH in kinds or FailureKind.PAYMENT_REQUIRED in kinds:
        parts.append("Run /setup or update API keys and billing for affected providers.")

    if FailureKind.RATE_LIMIT not in kinds and not (
        FailureKind.AUTH in kinds or FailureKind.PAYMENT_REQUIRED in kinds
    ):
        parts.append("Configure another provider or try again later.")

    return " ".join(parts)


class ModelSelectionType(Enum):
    """Types of model selection strategies."""
    FAST = "fast"        # Quick responses, 8B models
    CHAT = "chat"        # Conversation, 70B models
    INSTRUCT = "instruct"  # Agent/tools, instruction-tuned (Qwen 235B, Gemini)
    EMBED = "embed"      # Embeddings


_CATALOG = build_default_catalog()


def _selection_type_to_group() -> dict[ModelSelectionType, str]:
    """Derive the selection-type -> router-group mapping from the catalog.

    A selection type the catalog cannot map is a catalog integrity error;
    fail at import rather than leaking None into routing.
    """
    mapping: dict[ModelSelectionType, str] = {}
    for selection_type in ModelSelectionType:
        group = _CATALOG.group_for_selection_type(selection_type.value)
        if group is None:
            raise RuntimeError(
                f"Provider catalog has no router group for selection type "
                f"{selection_type.value!r}"
            )
        mapping[selection_type] = group
    return mapping


# Canonical mapping from ModelSelectionType to LiteLLM model groups.
# Single source of truth - import this instead of defining your own.
SELECTION_TYPE_TO_GROUP: dict[ModelSelectionType, str] = _selection_type_to_group()

# Valid model groups for the LiteLLM router
MODEL_GROUPS: set[str] = set(_CATALOG.router_groups())


def _model_priorities() -> dict[ModelSelectionType, list[str]]:
    """Derive per-selection-type priority lists from the catalog.

    A selection type with no priority models is a catalog integrity
    error; fail at import rather than silently selecting nothing.
    """
    priorities: dict[ModelSelectionType, list[str]] = {}
    for selection_type in ModelSelectionType:
        model_ids = _CATALOG.priority_model_ids(selection_type.value)
        if not model_ids:
            raise RuntimeError(
                f"Provider catalog has no priority models for selection type "
                f"{selection_type.value!r}"
            )
        priorities[selection_type] = list(model_ids)
    return priorities


# Priority order for each selection type.
# First model is highest priority, tried first.
# Ordering rationale (JSON compliance, context, RPD) lives with the
# facts in provider_catalog.build_default_catalog.
MODEL_PRIORITIES: dict[ModelSelectionType, list[str]] = _model_priorities()


@dataclass(frozen=True)
class ModelHealthState:
    """Resolved health state stored for an unavailable model."""

    expires_at: float
    failure_kind: FailureKind
    retry_after: Optional[float] = None


def default_model_cooldowns_path() -> Path:
    """Default persist path for model cooldown state."""
    return Path.home() / ".scrappy" / "model_cooldowns.json"


# Bounds for server-reported retry-after values (PR-3a, operator-ratified):
# a provider-reported cooldown outside these bounds is a parse glitch or a
# hostile value, not a real instruction to stall selection for months.
RETRY_AFTER_FLOOR_SECONDS = 1.0
RETRY_AFTER_CAP_SECONDS = 86400.0


def clamp_retry_after(retry_after: Optional[float]) -> Optional[float]:
    """Clamp a server-reported retry-after to sane bounds.

    Returns None when the value is unusable (None, non-finite, or
    non-positive); the caller then falls back to the failure-policy default.
    """
    if retry_after is None or not math.isfinite(retry_after) or retry_after <= 0:
        return None
    return min(
        max(retry_after, RETRY_AFTER_FLOOR_SECONDS), RETRY_AFTER_CAP_SECONDS
    )


class ModelAvailabilityTrackerProtocol(Protocol):
    """
    Selection-facing contract for the model availability/cooldown store.

    This is the honest minimal surface ModelSelectionService consumes; it does
    not mirror the concrete tracker. clear() and get_available() have no
    selection caller and stay off the protocol. Selection depends on this
    protocol, never on a concrete tracker or a persistence detail.
    """

    def now(self) -> float:
        """Return the tracker's clock value (used to compute expiry)."""
        ...

    def mark(self, model: str, state: ModelHealthState) -> None:
        """Store resolved health state for a model."""
        ...

    def is_available(self, model: str) -> bool:
        """Return whether a model is currently available (no live cooldown)."""
        ...

    def get_cooldown_remaining(self, model: str) -> float:
        """Return seconds of cooldown remaining for a model, or 0.0."""
        ...

    def get_unavailable_state(self, model: str) -> Optional[ModelHealthState]:
        """Return current health state for a model, clearing expired entries."""
        ...

    def clear_kinds(self, kinds: set[FailureKind]) -> None:
        """Clear health states matching any of the given failure kinds."""
        ...


class ModelAvailabilityTracker:
    """
    Track temporary model health states with automatic recovery.

    Callers pass a resolved health state, including its expiration timestamp.
    After the state expires, the model becomes available again.

    With a persist_path, state is written through on mutation and reloaded on
    construction, so cooldowns survive restart. expires_at is an absolute
    wall-clock timestamp, so persisted expiry needs no timing adjustment.
    Without a persist_path, state is process-local (the old behavior).
    """

    DEFAULT_COOLDOWN_SECONDS = 60

    def __init__(
        self,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        now: Callable[[], float] = time.time,
        persist_path: Optional[Path] = None,
    ):
        """
        Initialize availability tracker.

        Args:
            cooldown_seconds: Legacy constructor value retained for callers that
                instantiate the tracker directly. ModelSelectionService resolves
                cooldowns before storing health state.
            now: Clock returning an absolute wall-clock timestamp.
            persist_path: File to persist cooldown state to. None disables
                persistence. A corrupt or absent file never fails construction.
        """
        self._legacy_cooldown_seconds = cooldown_seconds
        self._now = now
        self._lock = threading.Lock()
        self._unavailable: dict[str, ModelHealthState] = {}
        self._persist_path = persist_path
        if persist_path is None:
            logger.info(
                "Provider cooldown state is process-local and resets on restart."
            )
        else:
            self._load()
            logger.info(f"Model cooldown state persists to {persist_path}")

    def mark(self, model: str, state: ModelHealthState) -> None:
        """Store resolved health state for a model."""
        with self._lock:
            existing = self._unavailable.get(model)
            if existing is None or state.expires_at >= existing.expires_at:
                self._unavailable[model] = state
                self._persist_locked()

    def now(self) -> float:
        """Return the tracker's injected clock value."""
        return self._now()

    def is_available(self, model: str) -> bool:
        """
        Check if a model is available (not rate limited or cooldown expired).

        Args:
            model: Model ID to check

        Returns:
            True if model is available
        """
        return self.get_unavailable_state(model) is None

    def get_available(self, models: list[str]) -> list[str]:
        """
        Filter a list of models to only available ones.

        Args:
            models: List of model IDs to filter

        Returns:
            List of available model IDs (preserves order)
        """
        return [m for m in models if self.is_available(m)]

    def get_cooldown_remaining(self, model: str) -> float:
        """
        Get remaining cooldown time for a rate-limited model.

        Args:
            model: Model ID to check

        Returns:
            Seconds remaining, or 0 if available
        """
        state = self.get_unavailable_state(model)
        if state is None:
            return 0.0

        return max(0.0, state.expires_at - self._now())

    def clear(self) -> None:
        """Clear all rate limit tracking."""
        with self._lock:
            if self._unavailable:
                self._unavailable.clear()
                self._persist_locked()

    def clear_kinds(self, kinds: set[FailureKind]) -> None:
        """Clear health states matching any failure kind."""
        with self._lock:
            cleared = False
            for model, state in list(self._unavailable.items()):
                if state.failure_kind in kinds:
                    del self._unavailable[model]
                    cleared = True
            if cleared:
                self._persist_locked()

    def get_unavailable_state(self, model: str) -> Optional[ModelHealthState]:
        """Return current health state for a model, clearing expired entries.

        Deliberately does NOT write through: the read path stays I/O-free.
        An expired entry left on disk is pruned at the next load or write.
        """
        with self._lock:
            state = self._unavailable.get(model)
            if state is None:
                return None

            if self._now() >= state.expires_at:
                del self._unavailable[model]
                return None

            return state

    def _load(self) -> None:
        """Load persisted cooldown state, pruning entries already expired.

        Never raises: a corrupt or absent file starts the tracker empty, and
        a malformed entry drops that entry only. If pruning or skipping
        changed the loaded set, the file is rewritten so stale state does not
        accumulate. A corrupt file is left in place for diagnosis until the
        next write replaces it.
        """
        path = self._persist_path
        if path is None or not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise ValueError(
                    f"expected a JSON object, got {type(data).__name__}"
                )
        except Exception as e:
            logger.warning(f"Failed to load model cooldowns: {e}")
            return

        now = self._now()
        loaded: dict[str, ModelHealthState] = {}
        dropped = 0
        for model, entry in data.items():
            try:
                retry_after = entry.get("retry_after")
                state = ModelHealthState(
                    expires_at=float(entry["expires_at"]),
                    failure_kind=FailureKind(entry["failure_kind"]),
                    retry_after=(
                        float(retry_after) if retry_after is not None else None
                    ),
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                dropped += 1
                continue
            if now >= state.expires_at:
                dropped += 1
                continue
            loaded[model] = state

        with self._lock:
            self._unavailable = loaded
            if dropped:
                logger.debug(
                    f"Pruned {dropped} stale or malformed model cooldown entries"
                )
                self._persist_locked()

    def _persist_locked(self) -> None:
        """Write current state to the persist path. Caller must hold the lock.

        Atomic (write temp file, then replace) so a crash mid-write cannot
        leave a truncated file. Never raises: persistence failure degrades to
        process-local behavior.
        """
        path = self._persist_path
        if path is None:
            return

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                model: {
                    "expires_at": state.expires_at,
                    "failure_kind": state.failure_kind.value,
                    "retry_after": state.retry_after,
                }
                for model, state in self._unavailable.items()
            }
            tmp_path = path.with_name(path.name + ".tmp")
            tmp_path.write_text(json.dumps(data, indent=2))
            os.replace(tmp_path, path)
        except Exception as e:
            logger.warning(f"Failed to persist model cooldowns: {e}")


class ModelSelectionServiceProtocol(Protocol):
    """Protocol for model selection service."""

    def select(
        self,
        selection_type: ModelSelectionType,
        min_context: int = 0,
        session_preferred: Optional[str] = None,
        exclude: Optional[set[str]] = None,
    ) -> str:
        """
        Select specific model ID.

        Args:
            selection_type: FAST, CHAT, INSTRUCT, or EMBED
            min_context: Minimum context window required (0 = no requirement)
            session_preferred: Previously selected model for session stickiness

        Returns:
            Specific model ID (e.g., 'groq/llama-3.1-8b-instant')

        Raises:
            SelectionExhaustedError: If all models are unhealthy or no model has sufficient context
        """
        ...

    def get_models_for_type(self, selection_type: ModelSelectionType) -> list[str]:
        """Get available models for selection type, ordered by priority."""
        ...

    def mark_unhealthy(
        self,
        model: str,
        kind: FailureKind,
        retry_after: Optional[float] = None,
    ) -> None:
        """Mark a model or provider unhealthy according to failure policy."""
        ...

    def update_configured(self, new_set: set[str]) -> None:
        """Replace configured models without resetting health state."""
        ...

    def clear_failure_kinds(self, kinds: set[FailureKind]) -> None:
        """Clear tracked health states matching failure kinds."""
        ...

    def is_available(self, model_id: str) -> bool:
        """Check if a model is configured and currently healthy."""
        ...


class ModelSelectionService:
    """
    Selects specific model based on session preference and rate limits.

    Selection logic:
    1. Filter out rate-limited models
    2. If session_preferred is set and available -> use it
    3. Otherwise, iterate priority list and pick first available
    4. If none available, raise SelectionExhaustedError

    This replaces the random simple-shuffle behavior of LiteLLM Router
    with deterministic, priority-based selection.
    """

    def __init__(
        self,
        configured_models: set[str],
        model_priorities: Optional[dict[ModelSelectionType, list[str]]] = None,
        availability_tracker: Optional[ModelAvailabilityTrackerProtocol] = None,
    ):
        """
        Initialize model selection service.

        Args:
            configured_models: Set of model IDs that have API keys configured.
                              Format: "provider/model" (e.g., "groq/llama-3.1-8b-instant")
            model_priorities: Priority order for each selection type.
                             Defaults to MODEL_PRIORITIES.
            availability_tracker: Tracker for rate-limited models.
                                 Creates new one if not provided.
        """
        self._configured = set(configured_models)
        self._configured_lock = threading.Lock()
        self._priorities = model_priorities or MODEL_PRIORITIES
        self._availability: ModelAvailabilityTrackerProtocol = (
            availability_tracker or ModelAvailabilityTracker()
        )

    def select(
        self,
        selection_type: ModelSelectionType,
        min_context: int = 0,
        session_preferred: Optional[str] = None,
        exclude: Optional[set[str]] = None,
    ) -> str:
        """
        Select specific model ID.

        Args:
            selection_type: What kind of model is needed
            min_context: Minimum context window required (0 = no requirement)
            session_preferred: Previously selected model for session stickiness

        Returns:
            Specific model ID (e.g., 'groq/llama-3.1-8b-instant')

        Raises:
            ValueError: If no models configured for selection type
            SelectionExhaustedError: If all configured models are unhealthy or no model has sufficient context
        """
        excluded = exclude or set()

        # Get configured models for this type
        configured = self.get_models_for_type(selection_type)

        if not configured:
            # Get expected models for this type
            expected = self._priorities.get(selection_type, [])
            # Get all configured models
            all_configured = list(self._configured_snapshot())
            raise ValueError(
                f"No models configured for {selection_type.value}. "
                f"Expected one of: {expected}. "
                f"Configured models: {all_configured}. "
                f"Run /setup to configure API keys."
            )

        candidates = self._filter_candidates(
            configured,
            min_context=min_context,
            exclude=excluded,
        )

        if min_context > 0 and not any(
            self._model_satisfies_context(model, min_context)
            for model in configured
        ):
            raise AllModelsRateLimitedError(
                f"No models with >= {min_context} token context available. "
                f"Try reducing prompt size or configure a larger context model.",
                failure_summary={},
            )

        if not candidates:
            raise AllModelsRateLimitedError(
                f"All {selection_type.value} models are rate limited. "
                f"Try again in {self._get_min_cooldown(configured):.0f} seconds.",
                failure_summary=self._build_failure_summary(configured),
            )

        # 1. Try session preferred if available and not rate limited
        if session_preferred and session_preferred in candidates:
            return session_preferred

        # 2. Return first available (highest priority)
        return candidates[0]

    def get_models_for_type(self, selection_type: ModelSelectionType) -> list[str]:
        """
        Get configured models for selection type, ordered by priority.

        Only returns models that have API keys configured.
        Does NOT filter by rate limit status.

        Args:
            selection_type: What kind of model is needed

        Returns:
            List of configured model IDs, ordered by priority
        """
        priorities = self._priorities.get(selection_type, [])
        configured = self._configured_snapshot()
        return [m for m in priorities if m in configured]

    def mark_unhealthy(
        self,
        model: str,
        kind: FailureKind,
        retry_after: Optional[float] = None,
    ) -> None:
        """Mark a model or provider unhealthy according to failure policy.

        Server-reported retry_after is clamped to
        [RETRY_AFTER_FLOOR_SECONDS, RETRY_AFTER_CAP_SECONDS]; an unusable
        value (non-finite or non-positive) falls back to the policy default.
        The stored health state carries the clamped value, not the raw one.
        """
        policy = get_failure_policy(kind)
        if policy.scope == HealthScope.NONE:
            return

        clamped = clamp_retry_after(retry_after)
        cooldown = clamped if clamped is not None else policy.cooldown_seconds
        state = ModelHealthState(
            expires_at=self._availability.now() + cooldown,
            failure_kind=kind,
            retry_after=clamped,
        )

        if policy.scope == HealthScope.PER_MODEL:
            self._availability.mark(model, state)
            return

        configured_now = self._configured_snapshot()
        provider = self._extract_provider_from(model, configured_now)
        if provider is None:
            logger.warning(
                "Could not derive provider for %r; marking only that model",
                model,
            )
            self._availability.mark(model, state)
            return

        for configured_model in configured_now:
            if configured_model.startswith(f"{provider}/"):
                self._availability.mark(configured_model, state)

    def update_configured(self, new_set: set[str]) -> None:
        """Replace configured models without resetting health state."""
        with self._configured_lock:
            self._configured = set(new_set)

    def clear_failure_kinds(self, kinds: set[FailureKind]) -> None:
        """Clear tracked health states matching failure kinds."""
        self._availability.clear_kinds(kinds)

    def is_configured(self, model_id: str) -> bool:
        """Check if a model has API keys configured."""
        return model_id in self._configured_snapshot()

    def is_available(self, model_id: str) -> bool:
        """Check if a model is configured and not rate limited."""
        return model_id in self._configured_snapshot() and self._availability.is_available(model_id)

    def _get_min_cooldown(self, models: list[str]) -> float:
        """Get minimum cooldown remaining across models."""
        if not models:
            return 0.0
        return min(self._availability.get_cooldown_remaining(m) for m in models)

    @property
    def _known_prefixes(self) -> set[str]:
        """Provider prefixes from currently configured model IDs."""
        return {
            model.split("/", 1)[0]
            for model in self._configured_snapshot()
            if "/" in model
        }

    def _configured_snapshot(self) -> set[str]:
        """Return a thread-safe snapshot of configured model IDs."""
        with self._configured_lock:
            return set(self._configured)

    def _extract_provider(self, model_id: str) -> Optional[str]:
        """Extract provider only when the prefix is currently configured."""
        return self._extract_provider_from(model_id, self._configured_snapshot())

    def _extract_provider_from(
        self,
        model_id: str,
        configured_models: set[str],
    ) -> Optional[str]:
        """Extract provider only when the prefix exists in configured models."""
        if "/" not in model_id:
            return None

        provider = model_id.split("/", 1)[0]
        known_prefixes = {
            model.split("/", 1)[0]
            for model in configured_models
            if "/" in model
        }
        if provider not in known_prefixes:
            return None
        return provider

    def _build_failure_summary(self, models: list[str]) -> dict[str, FailureRecord]:
        """Build failure summary from current tracker state."""
        summary: dict[str, FailureRecord] = {}
        for model in models:
            state = self._availability.get_unavailable_state(model)
            if state is not None:
                summary[model] = FailureRecord.from_health_state(model, state)
        return summary

    def _filter_candidates(
        self,
        models: list[str],
        min_context: int,
        exclude: set[str],
    ) -> list[str]:
        """Apply context, exclude, and health filters in one pass."""
        candidates: list[str] = []
        for model in models:
            if model in exclude:
                continue
            if not self._model_satisfies_context(model, min_context):
                continue
            if not self._availability.is_available(model):
                continue
            candidates.append(model)
        return candidates

    def _model_satisfies_context(self, model: str, min_context: int) -> bool:
        """Return whether a model has enough context for the request."""
        if min_context <= 0:
            return True

        from .litellm_config import MODEL_METADATA

        metadata = MODEL_METADATA.get(model)
        return bool(metadata and metadata.context_length >= min_context)
