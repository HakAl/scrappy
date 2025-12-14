"""
LiteLLM integration layer.

Provides LiteLLMService which replaces RetryOrchestrator + all individual providers.
LiteLLM handles retry, fallback, and rate limits internally via Router configuration.

This module handles:
- Response normalization to LLMResponse
- Exception mapping to our types
- ContextWindowExceededError -> escalate fast->quality (with depth guard)
- Request/response logging
- API key validation (for wizard)

Architecture:
- LiteLLMService implements LLMServiceProtocol
- Router is injected at construction (can be empty initially)
- configure() populates router when API keys become available
- Rate tracking handled by RateTrackingCallback (see litellm_callbacks.py)
"""

import json
import time
from typing import Optional, TYPE_CHECKING

from ..providers.base import LLMResponse, ToolCall
from ..infrastructure.exceptions.provider_errors import AllProvidersRateLimitedError
from ..protocols.output import BaseOutputProtocol
from ..infrastructure.config.api_keys import ApiKeyConfigServiceProtocol

if TYPE_CHECKING:
    import litellm
    from .litellm_callbacks import RateTrackingCallback


# Maximum escalation depth to prevent infinite recursion
MAX_ESCALATION_DEPTH = 2

# Escalation path: fast -> quality
ESCALATION_PATH = {
    "fast": "quality",
}


class NotConfiguredError(Exception):
    """Raised when LLM service is used before API keys are configured."""
    pass


class LiteLLMService:
    """
    LiteLLM integration layer.

    Replaces: RetryOrchestrator + all individual providers

    LiteLLM handles internally:
    - Retries with exponential backoff (num_retries)
    - Provider fallback (multiple models with same model_name)
    - Rate limit detection and handling
    - AuthenticationError -> triggers fallback to next provider

    We handle:
    - Response normalization to LLMResponse
    - Exception mapping to our types
    - ContextWindowExceededError -> escalate fast->quality (with depth guard)
    - Request/response logging
    - API key validation (for wizard)

    NOTE: Rate tracking is handled by RateTrackingCallback (see litellm_callbacks.py),
    NOT by methods on this class. Callbacks are wired at Router creation time.
    """

    def __init__(
        self,
        router: "litellm.Router",
        api_key_service: ApiKeyConfigServiceProtocol,
        output: BaseOutputProtocol,
        callback: Optional["RateTrackingCallback"] = None,
    ):
        """
        Initialize LiteLLM service.

        Args:
            router: LiteLLM Router instance (can be empty, configured via configure())
            api_key_service: Service for API key access
            output: Output interface for logging/warnings
            callback: Optional callback for escalation tracking
        """
        self._router = router
        self._api_key_service = api_key_service
        self._output = output
        self._callback = callback
        self._configured = False
        # NOTE: Router-level callbacks handle rate tracking.
        # The callback reference here is for escalation metrics only.

    def is_configured(self) -> bool:
        """Check if service has been configured with API keys."""
        return self._configured

    def configure(self) -> bool:
        """
        Configure router with current API keys.

        Call after wizard saves keys to enable completions.

        Returns:
            True if at least one model group is available
        """
        from .litellm_config import build_model_list

        model_list = build_model_list(self._api_key_service)
        if not model_list:
            return False

        self._router.set_model_list(model_list)
        self._configured = True
        return True

    def validate_key(
        self,
        model: str,
        api_key: str,
        timeout: float = 10.0,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an API key by making a minimal completion call.

        Used by wizard to test keys before saving. Does not use the router -
        makes a direct litellm.completion() call with the provided key.

        Args:
            model: LiteLLM model ID (e.g., "groq/llama-3.1-8b-instant")
            api_key: API key to validate
            timeout: Timeout in seconds

        Returns:
            Tuple of (is_valid, error_message)
        """
        import litellm

        try:
            litellm.completion(
                model=model,
                api_key=api_key,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                timeout=timeout,
            )
            return True, None

        except Exception as e:
            error_str = str(e)
            error_lower = error_str.lower()

            # Parse common error patterns for user-friendly messages
            if "401" in error_str or "unauthorized" in error_lower:
                return False, "Invalid API key"
            if "403" in error_str or "forbidden" in error_lower:
                return False, "API key does not have required permissions"
            if "429" in error_str or "rate limit" in error_lower:
                # Rate limit means key is valid, just temporarily blocked
                return True, None
            if "connection" in error_lower or "timeout" in error_lower:
                return False, "Network error - check your connection"

            return False, error_str

    async def completion(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        _escalated_from: Optional[str] = None,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Execute completion via LiteLLM Router.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion (do not set)
            _escalated_from: Internal tracking of original tier (do not set)
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)
                      Tools are passed through to provider: tools=[...], tool_choice="auto"

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
        """
        if not self._configured:
            raise NotConfiguredError("LLM service not configured. Run setup wizard first.")

        # Import here to avoid import errors if litellm not installed
        from litellm import ContextWindowExceededError
        from litellm import RateLimitError as LiteLLMRateLimitError

        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        start = time.time()

        try:
            response = await self._router.acompletion(
                model=model,
                messages=messages,
                num_retries=3,
                **kwargs
            )
            elapsed = time.time() - start
            return self._convert_response(response, elapsed, escalated_from=_escalated_from)

        except ContextWindowExceededError as e:
            # Smart recovery: fast tier -> try quality tier (has larger context models)
            next_tier = ESCALATION_PATH.get(model)
            if next_tier:
                self._output.warn(
                    f"Context window exceeded on {model} tier, retrying with {next_tier} tier..."
                )
                # Track escalation for monitoring
                if self._callback:
                    self._callback.record_escalation(model, next_tier)
                return await self.completion(
                    next_tier,
                    messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from=model,
                    **kwargs
                )
            # No escalation path available - fatal, re-raise
            raise

        except LiteLLMRateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message=str(e),
                attempted_providers=[provider] if provider else [],
            )
        # NOTE: AuthenticationError is NOT caught here.
        # LiteLLM Router handles auth failures internally by trying next provider in group.
        # If all providers in group fail auth, Router raises the error which propagates up.

    def completion_sync(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        _escalated_from: Optional[str] = None,
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Sync version for non-async contexts (Textual workers).

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion (do not set)
            _escalated_from: Internal tracking of original tier (do not set)
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
        """
        if not self._configured:
            raise NotConfiguredError("LLM service not configured. Run setup wizard first.")

        # Import here to avoid import errors if litellm not installed
        from litellm import ContextWindowExceededError
        from litellm import RateLimitError as LiteLLMRateLimitError

        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        start = time.time()

        try:
            response = self._router.completion(
                model=model,
                messages=messages,
                num_retries=3,
                **kwargs
            )
            elapsed = time.time() - start
            return self._convert_response(response, elapsed, escalated_from=_escalated_from)

        except ContextWindowExceededError as e:
            # Smart recovery: fast tier -> try quality tier (has larger context models)
            next_tier = ESCALATION_PATH.get(model)
            if next_tier:
                self._output.warn(
                    f"Context window exceeded on {model} tier, retrying with {next_tier} tier..."
                )
                # Track escalation for monitoring
                if self._callback:
                    self._callback.record_escalation(model, next_tier)
                return self.completion_sync(
                    next_tier,
                    messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from=model,
                    **kwargs
                )
            # No escalation path available - fatal, re-raise
            raise

        except LiteLLMRateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message=str(e),
                attempted_providers=[provider] if provider else [],
            )
        # NOTE: AuthenticationError is NOT caught here. See async version for rationale.

    def _convert_response(
        self,
        response,
        elapsed: float,
        escalated_from: Optional[str] = None,
    ) -> tuple[LLMResponse, dict]:
        """
        Map LiteLLM ModelResponse to our LLMResponse.

        Args:
            response: LiteLLM ModelResponse object
            elapsed: Request elapsed time in seconds
            escalated_from: Original tier if escalated (e.g., "fast")

        Returns:
            Tuple of (LLMResponse, task_record dict)
        """
        choice = response.choices[0]
        usage = response.usage

        # Extract provider from model string "cerebras/llama-3.3-70b" -> "cerebras"
        model_str = response.model or ""
        provider = model_str.split("/")[0] if "/" in model_str else "unknown"

        # Handle usage gracefully (may be None)
        prompt_tokens = 0
        completion_tokens = 0
        if usage:
            prompt_tokens = getattr(usage, 'prompt_tokens', 0) or 0
            completion_tokens = getattr(usage, 'completion_tokens', 0) or 0

        # Build metadata with escalation info for observability
        metadata = {"finish_reason": choice.finish_reason}
        if escalated_from:
            metadata["escalated_from"] = escalated_from

        llm_response = LLMResponse(
            content=choice.message.content or "",
            model=model_str,
            provider=provider,
            tokens_used=prompt_tokens + completion_tokens,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=elapsed * 1000,
            raw_response=response,
            metadata=metadata,
            tool_calls=self._extract_tool_calls(choice.message),
        )

        task_record = {
            "provider": provider,
            "model": model_str,
            "tokens_used": llm_response.tokens_used,
            "latency_ms": llm_response.latency_ms,
            "escalated_from": escalated_from,  # Track escalation for monitoring
        }

        return llm_response, task_record

    def _extract_tool_calls(self, message) -> Optional[list[ToolCall]]:
        """
        Extract tool calls from response message if present.

        Args:
            message: LiteLLM message object

        Returns:
            List of ToolCall objects, or None if no tool calls
        """
        if not hasattr(message, 'tool_calls') or not message.tool_calls:
            return None

        tool_calls = []
        for tc in message.tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                arguments = {}

            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments
                )
            )

        return tool_calls if tool_calls else None
