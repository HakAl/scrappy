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

import asyncio
import json
import logging
import time
import threading
from typing import Optional, TYPE_CHECKING, AsyncIterator

from ..infrastructure.logging import StructuredLogger
from ..providers.base import LLMResponse, ToolCall
from ..infrastructure.exceptions.provider_errors import (
    AllProvidersRateLimitedError,
    RateLimitError,
    AuthenticationError,
    NetworkError,
    TimeoutError as ProviderTimeoutError,
    ProviderExecutionError,
)
from ..protocols.output import BaseOutputProtocol
from ..infrastructure.config.api_keys import ApiKeyConfigServiceProtocol
from .types import StreamChunk, ToolCallFragment
from .litellm_config import build_model_list

import litellm
from litellm import ContextWindowExceededError
from litellm import RateLimitError as LiteLLMRateLimitError

if TYPE_CHECKING:
    from .litellm_callbacks import RateTrackingCallback

logger = logging.getLogger(__name__)

# Force httpx transport for LiteLLM streaming
# aiohttp has issues with session lifecycle that cause incomplete streams
# and "unclosed client session" warnings on exit
def _configure_litellm_transport():
    """Configure LiteLLM to use httpx instead of aiohttp."""
    try:
        import litellm
        import httpx
        litellm.disable_aiohttp_transport = True
        litellm.use_aiohttp_transport = False
        litellm.client_session = httpx.Client()
        litellm.aclient_session = httpx.AsyncClient()
    except ImportError:
        pass  # litellm or httpx not installed, skip

_configure_litellm_transport()


# Maximum escalation depth to prevent infinite recursion
MAX_ESCALATION_DEPTH = 2

# Escalation path: fast -> quality
ESCALATION_PATH = {
    "fast": "quality",
}

# Default timeout for stuck stream detection (ms)
DEFAULT_STREAM_TIMEOUT_MS = 30000  # 30 seconds

# Per-provider request throttle delays (seconds)
# Groq is very fast but has strict rate limits - need to slow down
PROVIDER_THROTTLE_DELAYS = {
    "groq": 1.0,      # 1 second between Groq requests
    "cerebras": 0.5,  # Cerebras is more lenient
    "gemini": 0.3,    # Gemini is lenient
    "sambanova": 0.5,
}
DEFAULT_THROTTLE_DELAY = 0.5  # Default for unknown providers


class RequestThrottle:
    """
    Per-provider request throttling to avoid rate limits.

    Tracks the last request time for each provider and enforces
    a minimum delay between requests.
    """

    def __init__(self):
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()

    def _get_provider(self, model: str) -> str:
        """Extract provider from model string (e.g., 'groq/llama-3.1' -> 'groq')."""
        if "/" in model:
            return model.split("/")[0]
        return model

    def _get_delay(self, provider: str) -> float:
        """Get throttle delay for provider."""
        return PROVIDER_THROTTLE_DELAYS.get(provider, DEFAULT_THROTTLE_DELAY)

    def wait_sync(self, model: str) -> None:
        """Wait if needed before making a request (sync version)."""
        provider = self._get_provider(model)
        delay = self._get_delay(provider)

        with self._lock:
            now = time.time()
            last = self._last_request.get(provider, 0)
            wait_time = delay - (now - last)

            if wait_time > 0:
                time.sleep(wait_time)

            self._last_request[provider] = time.time()

    async def wait_async(self, model: str) -> None:
        """Wait if needed before making a request (async version)."""
        provider = self._get_provider(model)
        delay = self._get_delay(provider)

        with self._lock:
            now = time.time()
            last = self._last_request.get(provider, 0)
            wait_time = delay - (now - last)

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        with self._lock:
            self._last_request[provider] = time.time()


# Global throttle instance
_request_throttle = RequestThrottle()


def _map_litellm_error(error: Exception, provider: str = "", model: str = "") -> Exception:
    """
    Map LiteLLM exceptions to user-friendly exceptions with actionable suggestions.

    Args:
        error: The original LiteLLM exception
        provider: Provider name for context
        model: Model name for context

    Returns:
        A mapped exception with user-friendly message and suggestion
    """
    error_msg = str(error).lower()
    error_type = type(error).__name__

    # Provider name for messages
    provider_display = provider or "the provider"

    # Authentication errors
    if "auth" in error_type.lower() or "401" in str(error) or "unauthorized" in error_msg:
        return AuthenticationError(
            f"Authentication failed for {provider_display}",
            provider_name=provider,
            suggestion=f"Check your API key for {provider_display} is correct in .env file."
        )

    # Rate limiting - more specific than base RateLimitError
    if "rate" in error_type.lower() or "429" in str(error) or "rate limit" in error_msg or "quota" in error_msg:
        return RateLimitError(
            f"Rate limit exceeded for {provider_display}",
            provider_name=provider,
            suggestion="Wait a few seconds before retrying, or try a different provider."
        )

    # Connection errors
    if "connection" in error_type.lower() or "connection" in error_msg or "unreachable" in error_msg:
        return NetworkError(
            f"Could not connect to {provider_display}",
            suggestion="Check your internet connection and try again."
        )

    # Timeout errors
    if "timeout" in error_type.lower() or "timeout" in error_msg or "timed out" in error_msg:
        return ProviderTimeoutError(
            f"Request to {provider_display} timed out",
            suggestion="The provider may be slow. Try again or use a different provider."
        )

    # Content filtering / safety errors
    if "content" in error_msg and ("filter" in error_msg or "blocked" in error_msg or "safety" in error_msg):
        return ProviderExecutionError(
            f"Content was blocked by {provider_display}'s safety filters",
            provider_name=provider,
            suggestion="Try rephrasing your request to avoid triggering content filters."
        )

    # Model not found
    if "model" in error_msg and ("not found" in error_msg or "unknown" in error_msg or "invalid" in error_msg):
        return ProviderExecutionError(
            f"Model '{model}' not available from {provider_display}",
            provider_name=provider,
            suggestion="Check the model name or run '/providers' to see available models."
        )

    # Service unavailable
    if "503" in str(error) or "service unavailable" in error_msg or "overloaded" in error_msg:
        return ProviderExecutionError(
            f"{provider_display} is temporarily unavailable",
            provider_name=provider,
            suggestion="The provider is experiencing issues. Try again later or use a different provider."
        )

    # Bad request (400) - often malformed input
    if "400" in str(error) or "bad request" in error_msg:
        return ProviderExecutionError(
            f"Invalid request to {provider_display}",
            provider_name=provider,
            original_error=error,
            suggestion="There may be an issue with the request format. Try a simpler prompt."
        )

    # Server errors (500)
    if "500" in str(error) or "internal server error" in error_msg:
        return ProviderExecutionError(
            f"{provider_display} experienced an internal error",
            provider_name=provider,
            suggestion="This is a provider-side issue. Try again or use a different provider."
        )

    # Fallback: wrap with context but preserve original message
    return ProviderExecutionError(
        f"Error from {provider_display}: {error}",
        provider_name=provider,
        original_error=error,
        suggestion="Try again or use a different provider."
    )


class NotConfiguredError(Exception):
    """Raised when LLM service is used before API keys are configured."""
    pass


class StreamStuckError(Exception):
    """Raised when streaming stalls with no content received within timeout."""

    def __init__(self, message: str, partial_content: str = "", timeout_ms: int = 0):
        super().__init__(message)
        self.partial_content = partial_content
        self.timeout_ms = timeout_ms


class StreamCancelledError(Exception):
    """Raised when streaming is cancelled by user (e.g., Ctrl-C)."""

    def __init__(self, message: str = "Stream cancelled", partial_content: str = ""):
        super().__init__(message)
        self.partial_content = partial_content


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
        logger: Optional[StructuredLogger] = None,
    ):
        """
        Initialize LiteLLM service.

        Args:
            router: LiteLLM Router instance (can be empty, configured via configure())
            api_key_service: Service for API key access
            output: Output interface for logging/warnings
            callback: Optional callback for escalation tracking
            logger: Optional structured logger for API request/response debugging
        """
        self._router = router
        self._api_key_service = api_key_service
        self._output = output
        self._callback = callback
        self._logger = logger
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
        Forces reload from disk to pick up any newly saved keys.

        Returns:
            True if at least one model group is available
        """

        # Force reload from disk to get freshly saved keys
        self._api_key_service.reload()

        model_list = build_model_list(self._api_key_service)
        if not model_list:
            return False

        self._router.set_model_list(model_list)
        self._configured = True
        return True

    def close(self) -> None:
        """
        Close HTTP sessions to prevent 'unclosed client session' warnings.

        Call on app shutdown. Closes httpx clients we created and any
        aiohttp sessions that LiteLLM may have created internally.
        """
        # Close httpx sync client we created at module level
        if hasattr(litellm, 'client_session') and litellm.client_session is not None:
            try:
                litellm.client_session.close()
            except Exception as e:
                logger.debug("Error closing httpx client: %s", e)
            finally:
                litellm.client_session = None

        # AsyncClient needs async close - mark for GC
        if hasattr(litellm, 'aclient_session') and litellm.aclient_session is not None:
            litellm.aclient_session = None

        # Close any aiohttp sessions LiteLLM created internally
        if hasattr(litellm, '_client_session') and litellm._client_session is not None:
            try:
                loop = asyncio.get_event_loop_policy().get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(litellm._client_session.close())
                else:
                    loop.run_until_complete(litellm._client_session.close())
            except Exception as e:
                logger.debug("Error closing aiohttp session: %s", e)
            finally:
                litellm._client_session = None

    async def aclose(self) -> None:
        """Async version of close for async contexts."""
        # Close httpx sync client
        if hasattr(litellm, 'client_session') and litellm.client_session is not None:
            try:
                litellm.client_session.close()
            except Exception as e:
                logger.debug("Error closing httpx client: %s", e)
            finally:
                litellm.client_session = None

        # Close httpx async client
        if hasattr(litellm, 'aclient_session') and litellm.aclient_session is not None:
            try:
                await litellm.aclient_session.aclose()
            except Exception as e:
                logger.debug("Error closing httpx async client: %s", e)
            finally:
                litellm.aclient_session = None

        # Close aiohttp sessions
        if hasattr(litellm, '_client_session') and litellm._client_session is not None:
            try:
                await litellm._client_session.close()
            except Exception as e:
                logger.debug("Error closing aiohttp session: %s", e)
            finally:
                litellm._client_session = None

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


        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        start = time.time()

        # Log request with full prompt content for debugging
        if self._logger:
            tools = kwargs.get("tools") if kwargs else None
            self._logger.debug(
                f"API request: model={model}, messages={len(messages)}, tools={len(tools) if tools else 0}"
            )
            # Full messages JSON for prompt debugging
            self._logger.debug(
                f"PROMPT_MESSAGES: {json.dumps(messages, indent=2, default=str)}"
            )
            if tools:
                self._logger.debug(
                    f"PROMPT_TOOLS: {json.dumps(tools, indent=2, default=str)}"
                )

        # Throttle requests to avoid rate limits (especially for Groq)
        await _request_throttle.wait_async(model)

        try:
            response = await self._router.acompletion(
                model=model,
                messages=messages,
                num_retries=0,  # Don't retry - let Orchestrator handle model fallback
                **kwargs
            )
            elapsed = time.time() - start

            # Log response tool calls (key for debugging missing params)
            if self._logger and response and response.choices:
                msg = response.choices[0].message
                tc = getattr(msg, "tool_calls", None)
                if tc:
                    for t in tc:
                        self._logger.debug(
                            f"Tool call: {t.function.name} args={t.function.arguments}"
                        )

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

        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        start = time.time()

        # Log request with full prompt content for debugging
        if self._logger:
            tools = kwargs.get("tools") if kwargs else None
            self._logger.debug(
                f"API request: model={model}, messages={len(messages)}, tools={len(tools) if tools else 0}"
            )
            # Full messages JSON for prompt debugging
            self._logger.debug(
                f"PROMPT_MESSAGES: {json.dumps(messages, indent=2, default=str)}"
            )
            if tools:
                self._logger.debug(
                    f"PROMPT_TOOLS: {json.dumps(tools, indent=2, default=str)}"
                )

        # Throttle requests to avoid rate limits (especially for Groq)
        _request_throttle.wait_sync(model)

        try:
            response = self._router.completion(
                model=model,
                messages=messages,
                num_retries=0,  # Don't retry - let Orchestrator handle model fallback
                **kwargs
            )
            elapsed = time.time() - start

            # Log response tool calls (key for debugging missing params)
            if self._logger and response and response.choices:
                msg = response.choices[0].message
                tc = getattr(msg, "tool_calls", None)
                if tc:
                    for t in tc:
                        self._logger.debug(
                            f"Tool call: {t.function.name} args={t.function.arguments}"
                        )

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

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        _escalated_from: Optional[str] = None,
        timeout_ms: int = DEFAULT_STREAM_TIMEOUT_MS,
        cancellation_token: Optional["asyncio.Event"] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Execute streaming completion via LiteLLM Router.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion (do not set)
            _escalated_from: Internal tracking of original tier (do not set)
            timeout_ms: Max time to wait for next chunk (default 30s). Raises StreamStuckError if exceeded.
            cancellation_token: Optional asyncio.Event to cancel stream. Set event to cancel.
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
            StreamStuckError: When no chunk received within timeout_ms
            StreamCancelledError: When cancellation_token is set
        """
        import asyncio

        if not self._configured:
            raise NotConfiguredError("LLM service not configured. Run setup wizard first.")

        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        # Track partial content for error recovery
        partial_content = ""
        seen_final = False  # For Groq double-final chunk dedup
        timeout_seconds = timeout_ms / 1000.0

        # Throttle requests to avoid rate limits (especially for Groq)
        await _request_throttle.wait_async(model)

        try:
            # Call LiteLLM Router's async streaming method
            stream = await self._router.acompletion(
                model=model,
                messages=messages,
                stream=True,
                num_retries=0,  # Don't retry - let Orchestrator handle model fallback
                **kwargs
            )

            # Stream chunks with timeout and cancellation support
            stream_iter = stream.__aiter__()
            while True:
                # Check cancellation token before waiting for next chunk
                if cancellation_token and cancellation_token.is_set():
                    raise StreamCancelledError(
                        "Stream cancelled by user",
                        partial_content=partial_content
                    )

                try:
                    # Wait for next chunk with timeout (stuck stream detection)
                    chunk = await asyncio.wait_for(
                        stream_iter.__anext__(),
                        timeout=timeout_seconds
                    )
                except StopAsyncIteration:
                    # Stream completed normally
                    break
                except asyncio.TimeoutError:
                    raise StreamStuckError(
                        f"Stream stalled: no chunk received in {timeout_ms}ms",
                        partial_content=partial_content,
                        timeout_ms=timeout_ms
                    )

                converted = self._convert_chunk(chunk)

                # Groq double-final chunk dedup (5b)
                # Some providers send finish_reason twice - skip duplicates
                if converted.finish_reason:
                    if seen_final:
                        continue  # Skip duplicate final chunk
                    seen_final = True

                # Accumulate content for error recovery
                if converted.content:
                    partial_content += converted.content

                yield converted

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
                # Recursively call with next tier (preserve timeout and cancellation settings)
                async for chunk in self.stream_completion(
                    next_tier,
                    messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from=model,
                    timeout_ms=timeout_ms,
                    cancellation_token=cancellation_token,
                    **kwargs
                ):
                    yield chunk
                return
            # No escalation path available - fatal, re-raise
            raise

        except LiteLLMRateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message=str(e),
                attempted_providers=[provider] if provider else [],
            )

        except (StreamStuckError, StreamCancelledError):
            # Re-raise our custom exceptions unchanged
            raise

        except Exception as e:
            # Map LiteLLM exceptions to user-friendly exceptions
            # Extract provider from error if available
            provider = getattr(e, 'llm_provider', '') or ''
            mapped_error = _map_litellm_error(e, provider=provider, model=model)

            # Mid-stream error handling: preserve partial content info
            if partial_content:
                # Add partial content context to the mapped error
                mapped_error.context = {
                    **(getattr(mapped_error, 'context', {}) or {}),
                    'partial_content_chars': len(partial_content)
                }

            raise mapped_error from e

    def _convert_chunk(self, chunk) -> StreamChunk:
        """
        Convert LiteLLM streaming chunk to our StreamChunk format.

        Args:
            chunk: LiteLLM streaming chunk object

        Returns:
            StreamChunk with normalized data
        """
        # Extract content delta if present
        choice = chunk.choices[0] if chunk.choices else None
        content = ""
        if choice and hasattr(choice, 'delta') and choice.delta:
            content = getattr(choice.delta, 'content', None) or ""

        # Extract finish reason
        finish_reason = None
        if choice:
            finish_reason = getattr(choice, 'finish_reason', None)

        # Extract model and provider
        model_str = getattr(chunk, 'model', "") or ""
        provider = model_str.split("/")[0] if "/" in model_str else ""

        # Extract tool call fragments using helper method
        tool_call_fragments = []
        if choice and hasattr(choice, 'delta') and choice.delta:
            tool_call_fragments = self._extract_tool_fragments(choice.delta)

        return StreamChunk(
            content=content,
            tool_call_fragments=tool_call_fragments,
            finish_reason=finish_reason,
            model=model_str,
            provider=provider,
            metadata={}
        )

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
            arguments = self._parse_tool_arguments(tc.function.arguments, tc.function.name)

            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments
                )
            )

        return tool_calls if tool_calls else None

    def _parse_tool_arguments(self, raw_arguments, tool_name: str = "") -> dict:
        """
        Parse tool call arguments with robust handling.

        Handles:
        - Already-parsed dict (some providers)
        - JSON string
        - JSON wrapped in markdown code fences (Gemini issue)

        Args:
            raw_arguments: Arguments from provider (str or dict)
            tool_name: Tool name for logging context

        Returns:
            Parsed arguments dict (empty dict on failure)
        """
        # Already a dict - some providers return parsed
        if isinstance(raw_arguments, dict):
            return raw_arguments

        # Not a string - unexpected type
        if not isinstance(raw_arguments, str):
            if self._logger:
                self._logger.warning(
                    f"Tool {tool_name}: unexpected arguments type {type(raw_arguments)}"
                )
            return {}

        # Empty string
        if not raw_arguments.strip():
            return {}

        # Try direct JSON parse first
        try:
            return json.loads(raw_arguments)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fences (Gemini issue)
        text = raw_arguments.strip()
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                json_str = text[start:end].strip()
            else:
                # Truncated - no closing ```
                json_str = text[start:].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Try generic ``` extraction
        if "```" in text:
            start = text.find("```") + 3
            # Skip language identifier if present
            newline_pos = text.find("\n", start)
            if newline_pos != -1 and newline_pos < start + 20:
                start = newline_pos + 1
            end = text.find("```", start)
            if end > start:
                json_str = text[start:end].strip()
            else:
                json_str = text[start:].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Log failure for debugging
        if self._logger:
            self._logger.warning(
                f"Tool {tool_name}: failed to parse arguments: {raw_arguments[:200]}"
            )

        return {}

    def _extract_tool_fragments(self, delta) -> list[ToolCallFragment]:
        """
        Extract tool call fragments from a streaming delta.

        During streaming, tool calls arrive incrementally across multiple chunks.
        This method extracts the fragments from a single chunk's delta.

        Args:
            delta: Delta object from LiteLLM streaming chunk

        Returns:
            List of ToolCallFragment objects (empty if no tool calls in delta)
        """
        if not hasattr(delta, 'tool_calls') or not delta.tool_calls:
            return []

        fragments = []
        for tc in delta.tool_calls:
            fragment = ToolCallFragment(
                id=getattr(tc, 'id', '') or '',
                type=getattr(tc, 'type', 'function'),
                name=getattr(tc.function, 'name', '') if hasattr(tc, 'function') else '',
                arguments=getattr(tc.function, 'arguments', '') if hasattr(tc, 'function') else '',
                index=getattr(tc, 'index', 0),
                complete=False
            )
            fragments.append(fragment)

        return fragments

    async def _escalate_and_stream(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        _escalated_from: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Handle context window escalation for streaming before first chunk.

        This method wraps stream_completion to detect context window errors
        that occur BEFORE the first chunk arrives (during request initiation).
        If detected, it escalates to the next tier transparently.

        This is critical because context window errors can happen in two phases:
        1. Pre-stream: LiteLLM rejects request before streaming starts
        2. Mid-stream: Provider rejects after streaming starts (rare)

        This method handles phase 1. The stream_completion method handles phase 2
        by catching errors during chunk iteration.

        Args:
            model: Model group name ("fast" or "quality")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion
            _escalated_from: Internal tracking of original tier
            **kwargs: Additional params passed to stream_completion

        Yields:
            StreamChunk objects from the (possibly escalated) stream

        Raises:
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
            AllProvidersRateLimitedError: When all providers exhausted

        Note:
            This method does NOT replace stream_completion - it wraps it to add
            pre-stream escalation detection. The stream_completion method still
            handles mid-stream errors and normal streaming logic.
        """
        # Safety guard against infinite recursion
        if _escalation_depth >= MAX_ESCALATION_DEPTH:
            raise RuntimeError(
                f"Max escalation depth ({MAX_ESCALATION_DEPTH}) exceeded. "
                "Context window too small for all available model tiers."
            )

        try:
            # Attempt to start streaming
            async for chunk in self.stream_completion(
                model=model,
                messages=messages,
                _escalation_depth=_escalation_depth,
                _escalated_from=_escalated_from,
                **kwargs
            ):
                yield chunk

        except ContextWindowExceededError as e:
            # Context window exceeded before first chunk
            next_tier = ESCALATION_PATH.get(model)
            if next_tier:
                self._output.warn(
                    f"Context window exceeded on {model} tier (pre-stream), "
                    f"retrying with {next_tier} tier..."
                )
                # Track escalation for monitoring
                if self._callback:
                    self._callback.record_escalation(model, next_tier)

                # Recursively try next tier
                async for chunk in self._escalate_and_stream(
                    next_tier,
                    messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from=model,
                    **kwargs
                ):
                    yield chunk
                return

            # No escalation path available - fatal, re-raise
            raise
