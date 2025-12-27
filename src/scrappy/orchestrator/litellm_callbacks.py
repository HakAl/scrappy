"""
LiteLLM callback implementations for usage tracking and monitoring.

Provides:
- RateTrackingCallback: LiteLLM callback for usage tracking and provider status
- EscalationMetrics: Tracks context window escalation events
- create_rate_tracking_callback: Factory for lazy callback creation

Architecture:
- Callbacks are wired at Router creation time (see litellm_config.py)
- RateTrackingCallback implements LiteLLM's CustomLogger interface
- EscalationMetrics is a simple dataclass for escalation tracking

Implements:
- D9: Usage tracking records actual provider/model (not group name)
- D10: Status tracking for provider health monitoring

NOTE: This module uses lazy imports for litellm to avoid 2s+ startup delay.
The CustomLogger base class is imported inside create_rate_tracking_callback().
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Optional, Any, Dict, TYPE_CHECKING

# NOTE: CustomLogger is imported lazily in create_rate_tracking_callback()
# to avoid slow litellm import at module load time.

if TYPE_CHECKING:
    from ..orchestrator.protocols import RateLimitTrackerProtocol
    from ..orchestrator.provider_status import ProviderStatusTracker


def parse_gemini_rate_limit_error(error_message: str) -> Optional[Dict[str, Any]]:
    """Parse Gemini rate limit error message to extract retry info.

    Gemini returns rate limit info in error responses (429), not headers.
    Common formats:
    - "Resource has been exhausted (e.g. check quota)."
    - "Please retry in 7.215400659s"
    - "Quota exceeded for quota metric"

    Args:
        error_message: The error message string from the exception

    Returns:
        Dict with parsed data or None if not a rate limit error:
        - retry_after_seconds: Float seconds until retry (if found)
        - quota_type: Type of quota exceeded (if identifiable)
        - message: Original error message
    """
    if not error_message:
        return None

    error_lower = error_message.lower()

    # Check if this is a rate limit error
    rate_limit_indicators = [
        "rate limit",
        "quota",
        "exhausted",
        "too many requests",
        "429",
        "retry in",
    ]
    if not any(indicator in error_lower for indicator in rate_limit_indicators):
        return None

    result: Dict[str, Any] = {"message": error_message}

    # Parse "Please retry in Xs" or "retry in Xs"
    # Matches: "retry in 7.215400659s", "Please retry in 30s", etc.
    retry_match = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", error_lower)
    if retry_match:
        result["retry_after_seconds"] = float(retry_match.group(1))

    # Try to identify quota type
    if "token" in error_lower:
        result["quota_type"] = "tokens"
    elif "request" in error_lower:
        result["quota_type"] = "requests"
    elif "quota" in error_lower:
        result["quota_type"] = "quota"

    return result


@dataclass
class EscalationMetrics:
    """
    Track context window escalation events for monitoring.

    Records when requests escalate from one tier to another due to
    context window limitations (e.g., fast -> quality).
    """
    total_escalations: int = 0
    escalations_by_path: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record_escalation(self, from_tier: str, to_tier: str) -> None:
        """
        Record an escalation event.

        Args:
            from_tier: Original model tier (e.g., "fast")
            to_tier: Target model tier (e.g., "quality")
        """
        self.total_escalations += 1
        path_key = f"{from_tier}->{to_tier}"
        self.escalations_by_path[path_key] += 1

    def get_summary(self) -> dict[str, Any]:
        """
        Get escalation summary for monitoring/display.

        Returns:
            Dictionary with total_escalations and by_path breakdown
        """
        return {
            "total_escalations": self.total_escalations,
            "by_path": dict(self.escalations_by_path),
        }


class RateTrackingCallbackBase:
    """
    Base implementation for rate tracking callback logic.

    This class contains all the callback logic but doesn't inherit from
    CustomLogger. The actual RateTrackingCallback class is created lazily
    via create_rate_tracking_callback() to avoid importing litellm at
    module load time.

    Implements D9 (usage tracking) and D10 (status display).
    Also tracks escalation metrics (context window fallbacks).
    """

    def __init__(
        self,
        rate_tracker: Optional["RateLimitTrackerProtocol"] = None,
        status_tracker: Optional["ProviderStatusTracker"] = None,
        escalation_metrics: Optional[EscalationMetrics] = None,
    ):
        """
        Initialize rate tracking callback.

        Args:
            rate_tracker: Optional tracker for rate limit monitoring
            status_tracker: Optional tracker for provider health status (D10)
            escalation_metrics: Optional metrics for escalation tracking
        """
        self._rate_tracker = rate_tracker
        self._status_tracker = status_tracker
        self._escalation_metrics = escalation_metrics or EscalationMetrics()

    @property
    def escalation_metrics(self) -> EscalationMetrics:
        """Access escalation metrics for monitoring."""
        return self._escalation_metrics

    def record_escalation(self, from_tier: str, to_tier: str) -> None:
        """
        Record a context window escalation event.

        Called by LiteLLMService when escalating fast->quality.

        Args:
            from_tier: Original model tier
            to_tier: Target model tier
        """
        self._escalation_metrics.record_escalation(from_tier, to_tier)

    def log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """
        Called by LiteLLM after successful request.

        Extracts actual provider/model from the response (not the group name)
        and records to rate tracker and status tracker.

        Args:
            kwargs: Original request kwargs
            response_obj: LiteLLM response object
            start_time: Request start time
            end_time: Request end time
        """
        # Extract actual provider/model (not group name)
        model_str = getattr(response_obj, 'model', '') or ''
        provider = self._extract_provider(model_str, kwargs)

        usage = getattr(response_obj, 'usage', None)
        input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
        output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
        latency_ms = (end_time - start_time).total_seconds() * 1000

        # Record to rate tracker (D9)
        if self._rate_tracker:
            self._rate_tracker.record_request(
                provider=provider,
                model=model_str,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
            )

        # Record to status tracker (D10)
        if self._status_tracker:
            total_tokens = input_tokens + output_tokens
            self._status_tracker.on_success(
                provider, model_str, latency_ms, tokens=total_tokens
            )

    def log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """
        Called by LiteLLM after failed request.

        Records failure to rate tracker and status tracker.
        For Gemini, also parses rate limit info from error message.

        Args:
            kwargs: Original request kwargs
            response_obj: LiteLLM response object (usually None)
            start_time: Request start time
            end_time: Request end time
        """
        # Extract provider - try exception first, then use _extract_provider
        exception = kwargs.get('exception', None)
        provider = getattr(exception, 'llm_provider', None)
        model = kwargs.get('model', 'unknown')

        if not provider:
            # Use _extract_provider as fallback
            provider = self._extract_provider(model, kwargs)

        error_msg = str(exception) if exception else "Unknown error"
        latency_ms = (end_time - start_time).total_seconds() * 1000

        # Record failure to rate tracker (D9)
        if self._rate_tracker:
            self._rate_tracker.record_request(
                provider=provider,
                model=model,
                input_tokens=0,
                output_tokens=0,
                success=False,
                error_message=error_msg,
            )

            # For Gemini, parse rate limit info from error message
            # Gemini returns rate limit details in error body, not headers
            if provider == "gemini" and hasattr(self._rate_tracker, 'update_from_error'):
                parsed_error = parse_gemini_rate_limit_error(error_msg)
                if parsed_error:
                    self._rate_tracker.update_from_error(provider, parsed_error)

        # Record failure to status tracker (D10)
        if self._status_tracker:
            self._status_tracker.on_failure(provider, error_msg, latency_ms=latency_ms)

    # LiteLLM CustomLogger interface methods
    # These are called by LiteLLM Router automatically

    def log_pre_api_call(self, model: str, messages: list, kwargs: dict) -> None:
        """Called before API call. No-op for rate tracking."""
        pass

    def log_post_api_call(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Called after API call (success or failure)."""
        # Check if this was a successful response
        if response_obj and hasattr(response_obj, 'choices'):
            self.log_success_event(kwargs, response_obj, start_time, end_time)

    def log_stream_event(self, kwargs: dict, response_obj: Any, start_time: datetime, end_time: datetime) -> None:
        """Called for streaming events. No-op for now."""
        pass

    def log_success_fallback_event(self, original_model_group: str, kwargs: dict, original_exception: Exception) -> None:
        """Called when fallback succeeds. Useful for monitoring fallback frequency."""
        pass

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Async version of log_success_event."""
        self.log_success_event(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Async version of log_failure_event."""
        self.log_failure_event(kwargs, response_obj, start_time, end_time)

    def _extract_provider(self, model_str: str, kwargs: dict) -> str:
        """
        Extract provider name from model string or kwargs.

        Tries multiple sources in order of reliability:
        1. Model string with provider prefix (e.g., "groq/llama-3.3-70b")
        2. custom_llm_provider from kwargs
        3. litellm_params.custom_llm_provider
        4. Infer from known model patterns
        5. Fall back to "unknown"

        Args:
            model_str: Model string from response
            kwargs: Request kwargs from LiteLLM

        Returns:
            Provider name (lowercase)
        """
        # 1. Check if model string has provider prefix
        if "/" in model_str:
            return model_str.split("/")[0].lower()

        # 2. Check custom_llm_provider in kwargs
        provider = kwargs.get("custom_llm_provider")
        if provider:
            return provider.lower()

        # 3. Check litellm_params
        litellm_params = kwargs.get("litellm_params", {})
        provider = litellm_params.get("custom_llm_provider")
        if provider:
            return provider.lower()

        # 4. Infer from known model patterns
        model_lower = model_str.lower()
        if any(pattern in model_lower for pattern in ["llama", "mixtral", "gemma"]):
            # These are typically Groq models when not prefixed
            if "70b" in model_lower or "versatile" in model_lower:
                return "groq"
            if "8b" in model_lower:
                return "groq"  # Could also be cerebras, but groq more common
        if "gemini" in model_lower:
            return "gemini"
        if "claude" in model_lower:
            return "anthropic"
        if "gpt" in model_lower:
            return "openai"

        # 5. Fall back to unknown
        return "unknown"


# Cache for the lazily-created class
_RateTrackingCallback = None


def create_rate_tracking_callback(
    rate_tracker: Optional["RateLimitTrackerProtocol"] = None,
    status_tracker: Optional["ProviderStatusTracker"] = None,
    escalation_metrics: Optional[EscalationMetrics] = None,
) -> "RateTrackingCallbackBase":
    """
    Factory function for creating RateTrackingCallback with lazy litellm import.

    This function imports litellm.CustomLogger only when called, avoiding
    the 2s+ startup delay that would occur if imported at module level.

    The actual RateTrackingCallback class inherits from both
    RateTrackingCallbackBase (our logic) and CustomLogger (LiteLLM interface).

    Args:
        rate_tracker: Optional tracker for rate limit monitoring
        status_tracker: Optional tracker for provider health status
        escalation_metrics: Optional metrics for escalation tracking

    Returns:
        RateTrackingCallback instance (inherits from CustomLogger)

    Usage:
        callback = create_rate_tracking_callback(rate_tracker=tracker)
        router = create_litellm_router(callbacks=[callback])
    """
    global _RateTrackingCallback

    if _RateTrackingCallback is None:
        # Lazy import - only pay the cost when actually creating a callback
        from litellm.integrations.custom_logger import CustomLogger

        # Create the class that inherits from both our base and CustomLogger
        class RateTrackingCallback(RateTrackingCallbackBase, CustomLogger):
            """
            LiteLLM callback for usage tracking and provider status.

            Inherits from CustomLogger for LiteLLM Router compatibility.
            All logic is in RateTrackingCallbackBase.
            """
            pass

        _RateTrackingCallback = RateTrackingCallback

    return _RateTrackingCallback(
        rate_tracker=rate_tracker,
        status_tracker=status_tracker,
        escalation_metrics=escalation_metrics,
    )


# Backwards compatibility alias - imports will trigger lazy class creation
# when instantiated, not when imported
RateTrackingCallback = RateTrackingCallbackBase
