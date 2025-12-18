"""
Model selection types and service.

Provides deterministic model selection with session stickiness and rate limit awareness.
"""

import time
from enum import Enum
from typing import Optional, Protocol


class AllModelsRateLimitedError(Exception):
    """Raised when all models for a selection type are rate limited."""
    pass


class ModelSelectionType(Enum):
    """Types of model selection strategies."""
    FAST = "fast"        # Quick responses, high throughput
    QUALITY = "quality"  # Best output quality
    INSTRUCT = "instruct"  # Instruction-tuned for JSON/structured output
    EMBED = "embed"      # Embeddings


# Canonical mapping from ModelSelectionType to LiteLLM model groups.
# Single source of truth - import this instead of defining your own.
SELECTION_TYPE_TO_GROUP: dict[ModelSelectionType, str] = {
    ModelSelectionType.FAST: "fast",
    ModelSelectionType.QUALITY: "quality",
    ModelSelectionType.INSTRUCT: "quality",  # Instruct maps to quality tier
    ModelSelectionType.EMBED: "fast",        # Embeddings use fast tier
}


# Priority order for each selection type.
# First model is highest priority, tried first.
# Based on JSON compliance testing (2025-12):
# - Cerebras & Groq: 110/100 (perfect JSON)
# - Gemini: 80/100 (adds markdown code fences - causes parse failures)
MODEL_PRIORITIES: dict[ModelSelectionType, list[str]] = {
    ModelSelectionType.FAST: [
        "groq/llama-3.1-8b-instant",           # Fast, 128k context
        "cerebras/llama3.1-8b",                # Ultra-fast, 8k context
        "sambanova/Meta-Llama-3.1-8B-Instruct",  # Low RPD fallback
    ],
    ModelSelectionType.QUALITY: [
        "cerebras/qwen-3-235b-a22b-instruct-2507",  # Best quality, instruction-tuned
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",  # Fast, good tool use
        "groq/moonshotai/kimi-k2-instruct",    # Fast, 128k context
        "gemini/gemini-2.5-flash",             # Huge context, JSON issues (fallback)
    ],
    ModelSelectionType.INSTRUCT: [
        "cerebras/qwen-3-235b-a22b-instruct-2507",
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",
        "groq/moonshotai/kimi-k2-instruct",
        "gemini/gemini-2.5-flash",             # Fallback - good tool use, JSON needs sanitizing
    ],
    ModelSelectionType.EMBED: [
        "groq/llama-3.1-8b-instant",
        "cerebras/llama3.1-8b",
    ],
}


class ModelAvailabilityTracker:
    """
    Track rate-limited models with automatic cooldown recovery.

    When a model returns a rate limit error, mark it unavailable.
    After the cooldown period, the model becomes available again.
    """

    DEFAULT_COOLDOWN_SECONDS = 60

    def __init__(self, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
        """
        Initialize availability tracker.

        Args:
            cooldown_seconds: How long to mark a model unavailable after rate limit
        """
        self._cooldown = cooldown_seconds
        self._unavailable: dict[str, float] = {}  # model -> timestamp when marked

    def mark_rate_limited(self, model: str) -> None:
        """
        Mark a model as rate limited.

        Args:
            model: Model ID that hit rate limit
        """
        self._unavailable[model] = time.time()

    def is_available(self, model: str) -> bool:
        """
        Check if a model is available (not rate limited or cooldown expired).

        Args:
            model: Model ID to check

        Returns:
            True if model is available
        """
        if model not in self._unavailable:
            return True

        elapsed = time.time() - self._unavailable[model]
        if elapsed >= self._cooldown:
            # Cooldown expired, remove from unavailable
            del self._unavailable[model]
            return True

        return False

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
        if model not in self._unavailable:
            return 0.0

        elapsed = time.time() - self._unavailable[model]
        remaining = self._cooldown - elapsed
        return max(0.0, remaining)

    def clear(self) -> None:
        """Clear all rate limit tracking."""
        self._unavailable.clear()


class ModelSelectionServiceProtocol(Protocol):
    """Protocol for model selection service."""

    def select(
        self,
        selection_type: ModelSelectionType,
        session_preferred: Optional[str] = None,
    ) -> str:
        """
        Select specific model ID.

        Args:
            selection_type: FAST, QUALITY, INSTRUCT, or EMBED
            session_preferred: Previously selected model for session stickiness

        Returns:
            Specific model ID (e.g., 'groq/llama-3.1-8b-instant')

        Raises:
            AllModelsRateLimitedError: If all models are rate limited
        """
        ...

    def get_models_for_type(self, selection_type: ModelSelectionType) -> list[str]:
        """Get available models for selection type, ordered by priority."""
        ...

    def mark_rate_limited(self, model: str) -> None:
        """Mark a model as rate limited."""
        ...


class ModelSelectionService:
    """
    Selects specific model based on session preference and rate limits.

    Selection logic:
    1. Filter out rate-limited models
    2. If session_preferred is set and available -> use it
    3. Otherwise, iterate priority list and pick first available
    4. If none available, raise AllModelsRateLimitedError

    This replaces the random simple-shuffle behavior of LiteLLM Router
    with deterministic, priority-based selection.
    """

    def __init__(
        self,
        configured_models: set[str],
        model_priorities: Optional[dict[ModelSelectionType, list[str]]] = None,
        availability_tracker: Optional[ModelAvailabilityTracker] = None,
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
        self._configured = configured_models
        self._priorities = model_priorities or MODEL_PRIORITIES
        self._availability = availability_tracker or ModelAvailabilityTracker()

    def select(
        self,
        selection_type: ModelSelectionType,
        session_preferred: Optional[str] = None,
    ) -> str:
        """
        Select specific model ID.

        Args:
            selection_type: What kind of model is needed
            session_preferred: Previously selected model for session stickiness

        Returns:
            Specific model ID (e.g., 'groq/llama-3.1-8b-instant')

        Raises:
            ValueError: If no models configured for selection type
            AllModelsRateLimitedError: If all configured models are rate limited
        """
        # Get configured models for this type
        configured = self.get_models_for_type(selection_type)

        if not configured:
            # Get expected models for this type
            expected = self._priorities.get(selection_type, [])
            # Get all configured models
            all_configured = list(self._configured)
            raise ValueError(
                f"No models configured for {selection_type.value}. "
                f"Expected one of: {expected}. "
                f"Configured models: {all_configured}. "
                f"Run /setup to configure API keys."
            )

        # Filter out rate-limited models
        available = self._availability.get_available(configured)

        if not available:
            raise AllModelsRateLimitedError(
                f"All {selection_type.value} models are rate limited. "
                f"Try again in {self._get_min_cooldown(configured):.0f} seconds."
            )

        # 1. Try session preferred if available and not rate limited
        if session_preferred and session_preferred in available:
            return session_preferred

        # 2. Return first available (highest priority)
        return available[0]

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
        return [m for m in priorities if m in self._configured]

    def mark_rate_limited(self, model: str) -> None:
        """
        Mark a model as rate limited.

        The model will be unavailable for selection until cooldown expires.

        Args:
            model: Model ID that hit rate limit
        """
        self._availability.mark_rate_limited(model)

    def is_configured(self, model_id: str) -> bool:
        """Check if a model has API keys configured."""
        return model_id in self._configured

    def is_available(self, model_id: str) -> bool:
        """Check if a model is configured and not rate limited."""
        return model_id in self._configured and self._availability.is_available(model_id)

    def _get_min_cooldown(self, models: list[str]) -> float:
        """Get minimum cooldown remaining across models."""
        if not models:
            return 0.0
        return min(self._availability.get_cooldown_remaining(m) for m in models)
