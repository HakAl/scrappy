"""
LiteLLM integration layer.

Provides LiteLLMService which replaces RetryOrchestrator + all individual providers.
LiteLLM handles retry, fallback, and rate limits internally via Router configuration.

This module handles:
- Response normalization to LLMResponse
- Exception mapping to our types
- ContextWindowExceededError -> escalate fast->chat->instruct (with depth guard)
- Request/response logging
- API key validation (for wizard)

Model Tiers:
- "fast": 8B models, speed priority
- "chat": 70B models, conversation
- "instruct": Instruction-tuned models (Qwen 235B, Gemini) for agent/tools

Architecture:
- LiteLLMService implements LLMServiceProtocol
- Router is injected at construction (can be empty initially)
- configure() populates router when API keys become available
- Rate tracking handled by RateTrackingCallback (see litellm_callbacks.py)
"""

import asyncio
import json
import logging
import re
import time
import threading
from typing import Iterator, Optional, TYPE_CHECKING, AsyncIterator, Type, TypeVar

from pydantic import BaseModel

# NOTE: litellm and instructor are imported lazily in LiteLLMService.__init__
# to avoid 4s startup delay. They are accessed via local imports in methods.

from ..infrastructure.logging import StructuredLogger
from .provider_types import LLMResponse, ToolCall
from ..infrastructure.exceptions.provider_errors import (
    AllProvidersRateLimitedError,
    RateLimitError,
    AuthenticationError,
    NetworkError,
    TimeoutError as ProviderTimeoutError,
    ProviderExecutionError,
)
from ..cli.protocols import BaseOutputProtocol
from ..infrastructure.config.api_keys import ApiKeyConfigServiceProtocol
from .types import StreamChunk, ToolCallFragment
from .litellm_config import build_model_list

if TYPE_CHECKING:
    import instructor
    import litellm
    from .litellm_callbacks import RateTrackingCallback

logger = logging.getLogger(__name__)

# Type variable for generic structured output responses
T = TypeVar("T", bound=BaseModel)

# Force httpx transport for LiteLLM streaming
# aiohttp has issues with session lifecycle that cause incomplete streams
# and "unclosed client session" warnings on exit
_transport_configured = False

def _configure_litellm_transport():
    """Configure LiteLLM to use httpx instead of aiohttp. Called lazily on first use."""
    global _transport_configured
    if _transport_configured:
        return
    try:
        import litellm
        import httpx
        litellm.disable_aiohttp_transport = True
        litellm.use_aiohttp_transport = False
        litellm.client_session = httpx.Client()
        litellm.aclient_session = httpx.AsyncClient()
        _transport_configured = True
    except ImportError:
        pass  # litellm or httpx not installed, skip


# Maximum escalation depth to prevent infinite recursion
# 3 tiers: fast -> chat -> instruct
MAX_ESCALATION_DEPTH = 3

# Escalation path: fast -> chat -> instruct
# When context window exceeded, try tier with larger context models
ESCALATION_PATH = {
    "fast": "chat",       # 8B -> 70B (more context options)
    "chat": "instruct",   # 70B -> instruction-tuned (Gemini has 1M context)
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


def _extract_retry_after(error: Exception) -> Optional[float]:
    """Extract retry-after time from litellm RateLimitError.

    Checks multiple sources:
    1. response headers (Retry-After, x-ratelimit-reset-requests)
    2. error body for retry_after field
    3. error message for time patterns

    Args:
        error: A litellm exception (usually RateLimitError)

    Returns:
        Retry-after time in seconds, or None if not available
    """
    # Try response headers first
    response = getattr(error, 'response', None)
    if response:
        headers = getattr(response, 'headers', {})
        if headers:
            # Standard Retry-After header (seconds or HTTP date)
            retry_after = headers.get('Retry-After') or headers.get('retry-after')
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass  # HTTP date format, skip

            # OpenAI/Anthropic rate limit headers
            reset_requests = headers.get('x-ratelimit-reset-requests')
            reset_tokens = headers.get('x-ratelimit-reset-tokens')
            if reset_requests:
                # Parse time like "1s", "1m30s", "1h"
                return _parse_time_string(reset_requests)
            if reset_tokens:
                return _parse_time_string(reset_tokens)

    # Try error body
    body = getattr(error, 'body', None)
    if body and isinstance(body, dict):
        retry = body.get('retry_after') or body.get('retryAfter')
        if retry:
            try:
                return float(retry)
            except (ValueError, TypeError):
                pass

    # Try parsing from error message (e.g., "retry after 45 seconds")
    message = str(error).lower()
    if 'retry' in message or 'wait' in message:
        import re
        # Match patterns like "45 seconds", "2 minutes", "1.5 hours"
        time_match = re.search(r'(\d+(?:\.\d+)?)\s*(second|minute|hour|s|m|h)', message)
        if time_match:
            value = float(time_match.group(1))
            unit = time_match.group(2)
            if unit.startswith('m'):
                value *= 60
            elif unit.startswith('h'):
                value *= 3600
            return value

    return None


def _parse_time_string(time_str: str) -> Optional[float]:
    """Parse time strings like '1s', '1m30s', '1h2m3s' into seconds."""
    import re
    total_seconds = 0.0
    time_str = time_str.lower().strip()

    # Match hours, minutes, seconds patterns
    hours = re.search(r'(\d+(?:\.\d+)?)\s*h', time_str)
    minutes = re.search(r'(\d+(?:\.\d+)?)\s*m(?!s)', time_str)  # m but not ms
    seconds = re.search(r'(\d+(?:\.\d+)?)\s*s', time_str)

    if hours:
        total_seconds += float(hours.group(1)) * 3600
    if minutes:
        total_seconds += float(minutes.group(1)) * 60
    if seconds:
        total_seconds += float(seconds.group(1))

    # If no time units found, try parsing as plain number
    if total_seconds == 0.0 and time_str:
        try:
            total_seconds = float(time_str)
        except ValueError:
            return None

    return total_seconds if total_seconds > 0 else None


def _build_provider_details(
    error: Exception,
    provider: Optional[str]
) -> dict[str, dict]:
    """Build provider_details dict from a rate limit error.

    Args:
        error: The litellm error
        provider: Provider name if known

    Returns:
        Dict like {"openai": {"retry_after": 45, "error": "..."}}
    """
    if not provider:
        return {}

    details: dict = {"error": str(error)[:200]}
    retry_after = _extract_retry_after(error)
    if retry_after is not None:
        details["retry_after"] = retry_after

    return {provider: details}

# Instructor retry limit - keep low since LiteLLM Router already handles retries
DEFAULT_INSTRUCTOR_RETRIES = 1


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


# Global throttle instance (lazy singleton)
_request_throttle: Optional[RequestThrottle] = None

def _get_throttle() -> RequestThrottle:
    """Get or create the global throttle instance."""
    global _request_throttle
    if _request_throttle is None:
        _request_throttle = RequestThrottle()
    return _request_throttle


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
    - ContextWindowExceededError -> escalate fast->chat->instruct (with depth guard)
    - Request/response logging
    - API key validation (for wizard)

    Model Tiers:
    - "fast": 8B models, speed priority
    - "chat": 70B models, conversation
    - "instruct": Instruction-tuned models (Qwen 235B, Gemini) for agent/tools

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
        # Lazy import of heavy dependencies (saves ~4s on startup)
        import instructor
        _configure_litellm_transport()

        self._router = router
        self._api_key_service = api_key_service
        self._output = output
        self._callback = callback
        self._logger = logger
        self._configured = False
        # NOTE: Router-level callbacks handle rate tracking.
        # The callback reference here is for escalation metrics only.

        # Instructor clients for structured output - separate clients per mode
        # Mode must be set at client creation time, not call time
        self._instructor_clients = {
            instructor.Mode.TOOLS: instructor.from_litellm(
                self._router.acompletion, mode=instructor.Mode.TOOLS
            ),
            instructor.Mode.JSON: instructor.from_litellm(
                self._router.acompletion, mode=instructor.Mode.JSON
            ),
        }
        self._instructor_clients_sync = {
            instructor.Mode.TOOLS: instructor.from_litellm(
                self._router.completion, mode=instructor.Mode.TOOLS
            ),
            instructor.Mode.JSON: instructor.from_litellm(
                self._router.completion, mode=instructor.Mode.JSON
            ),
        }

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

        Uses run_coroutine_threadsafe to properly await async closes when
        called from a sync context with a running event loop.
        """
        import litellm  # Lazy import (fast after first __init__)

        # Close httpx sync client we created at module level
        if hasattr(litellm, 'client_session') and litellm.client_session is not None:
            try:
                litellm.client_session.close()
            except Exception as e:
                logger.debug("Error closing httpx client: %s", e)
            finally:
                litellm.client_session = None

        # Check if we have a usable event loop BEFORE creating coroutines
        # Creating coroutines without awaiting them triggers RuntimeWarning
        loop = self._get_usable_loop()
        if loop is None:
            # No usable loop - just clear references, let GC handle cleanup
            if hasattr(litellm, 'aclient_session'):
                litellm.aclient_session = None
            if hasattr(litellm, '_client_session'):
                litellm._client_session = None
            return

        # Collect async close coroutines (only if we have a usable loop)
        async_closes: list = []

        # httpx AsyncClient needs async close
        if hasattr(litellm, 'aclient_session') and litellm.aclient_session is not None:
            async_closes.append(('aclient_session', litellm.aclient_session.aclose()))
            litellm.aclient_session = None

        # aiohttp sessions LiteLLM created internally
        if hasattr(litellm, '_client_session') and litellm._client_session is not None:
            async_closes.append(('_client_session', litellm._client_session.close()))
            litellm._client_session = None

        # Run async closes with proper waiting
        if async_closes:
            self._run_async_closes_with_loop(async_closes, loop)

    def _run_async_closes(self, closes: list) -> None:
        """Run async close operations, waiting for completion.

        Uses defensive approach: if we can't reliably get a working event loop,
        we skip async cleanup. The coroutines will be garbage collected anyway.
        Better to exit cleanly than hang indefinitely.
        """
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            # No event loop - coroutines will be garbage collected
            logger.debug("No event loop available for async closes")
            return

        # Check if loop is usable
        if loop.is_closed():
            logger.debug("Event loop is closed - skipping async closes")
            return

        async def close_all():
            for name, coro in closes:
                try:
                    await coro
                except Exception as e:
                    logger.debug("Error closing %s: %s", name, e)

        if loop.is_running():
            # Schedule on running loop and wait with timeout
            try:
                future = asyncio.run_coroutine_threadsafe(close_all(), loop)
                future.result(timeout=2.0)  # 2s timeout for cleanup
            except TimeoutError:
                logger.debug("Timeout waiting for async session closes")
            except RuntimeError as e:
                # Loop might have stopped between is_running() check and scheduling
                logger.debug("Event loop unavailable during async closes: %s", e)
            except Exception as e:
                logger.debug("Error in async closes: %s", e)
        else:
            # No running loop - try to run directly but with caution
            try:
                loop.run_until_complete(close_all())
            except RuntimeError as e:
                # Loop might be closing or in bad state
                logger.debug("Cannot run async closes on loop: %s", e)
            except Exception as e:
                logger.debug("Error running async closes: %s", e)

    async def aclose(self) -> None:
        """Async version of close for async contexts."""
        import litellm  # Lazy import (fast after first __init__)

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
            model: Model group name ("fast", "chat", or "instruct")
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
        import litellm  # Lazy import (fast after first __init__)

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
        await _get_throttle().wait_async(model)

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

        except litellm.ContextWindowExceededError:
            # Smart recovery: escalate to next tier (has larger context models)
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

        except litellm.RateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message="",  # Will be auto-generated
                attempted_providers=[provider] if provider else [],
                provider_details=_build_provider_details(e, provider),
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
            model: Model group name ("fast", "chat", or "instruct")
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
        import litellm  # Lazy import (fast after first __init__)

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
        _get_throttle().wait_sync(model)

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

        except litellm.ContextWindowExceededError:
            # Smart recovery: escalate to next tier (has larger context models)
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

        except litellm.RateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message="",  # Will be auto-generated
                attempted_providers=[provider] if provider else [],
                provider_details=_build_provider_details(e, provider),
            )
        # NOTE: AuthenticationError is NOT caught here. See async version for rationale.

    def completion_direct(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> tuple[LLMResponse, dict]:
        """
        Execute completion directly with a specific model (bypasses Router).

        Use this for fallback calls when you need to try a specific model
        after Router's model group is exhausted. This calls litellm.completion
        directly instead of going through the Router.

        Args:
            model: Specific model name (e.g., "gemini/gemini-2.5-flash")
            messages: Chat messages
            **kwargs: Additional params (max_tokens, temperature, tools, etc.)

        Returns:
            Tuple of (LLMResponse, task_record dict)

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When model is rate limited
        """
        import litellm  # Lazy import (fast after first __init__)

        if not self._configured:
            raise NotConfiguredError("LLM service not configured. Run setup wizard first.")

        # Extract provider from model string to get API key
        provider = model.split("/")[0] if "/" in model else model

        # Map provider to API key name
        provider_key_map = {
            "cerebras": "CEREBRAS_API_KEY",
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
        }

        key_name = provider_key_map.get(provider)
        if not key_name:
            raise ValueError(f"Unknown provider: {provider}")

        api_key = self._api_key_service.get_key(key_name)
        if not api_key:
            raise NotConfiguredError(f"API key not configured for {provider}")

        start = time.time()

        # Log request
        if self._logger:
            tools = kwargs.get("tools") if kwargs else None
            self._logger.debug(
                f"Direct API request: model={model}, messages={len(messages)}, "
                f"tools={len(tools) if tools else 0}"
            )

        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                api_key=api_key,
                **kwargs
            )
            elapsed = time.time() - start

            # Log response
            if self._logger and response and response.choices:
                msg = response.choices[0].message
                tc = getattr(msg, "tool_calls", None)
                if tc:
                    for t in tc:
                        self._logger.debug(
                            f"Tool call: {t.function.name} args={t.function.arguments}"
                        )

            return self._convert_response(response, elapsed)

        except litellm.RateLimitError as e:
            raise AllProvidersRateLimitedError(
                message="",  # Will be auto-generated
                attempted_providers=[provider],
                provider_details=_build_provider_details(e, provider),
            )

    def stream_completion_direct(
        self,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> Iterator[StreamChunk]:
        """
        Stream completion directly with a specific model (bypasses Router).

        Use this for deterministic model selection when you need to stream
        from a specific model rather than letting the Router shuffle.
        This calls litellm.completion directly with stream=True.

        Args:
            model: Specific model name (e.g., "cerebras/qwen-3-235b-a22b-instruct-2507")
            messages: Chat messages
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When model is rate limited
            ValueError: When provider is unknown
        """
        import litellm  # Lazy import (fast after first __init__)

        if not self._configured:
            raise NotConfiguredError("LLM service not configured. Run setup wizard first.")

        # Extract provider from model string to get API key
        provider = model.split("/")[0] if "/" in model else model

        # Map provider to API key name
        provider_key_map = {
            "cerebras": "CEREBRAS_API_KEY",
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
        }

        key_name = provider_key_map.get(provider)
        if not key_name:
            raise ValueError(f"Unknown provider: {provider}")

        api_key = self._api_key_service.get_key(key_name)
        if not api_key:
            raise NotConfiguredError(f"API key not configured for {provider}")

        # Log request
        if self._logger:
            tools = kwargs.get("tools") if kwargs else None
            self._logger.debug(
                f"Direct streaming request: model={model}, messages={len(messages)}, "
                f"tools={len(tools) if tools else 0}"
            )

        # Track partial content for error recovery
        partial_content = ""
        seen_final = False  # For Groq double-final chunk dedup

        # Throttle requests to avoid rate limits
        _get_throttle().wait_sync(model)

        try:
            # Call LiteLLM directly (not via Router)
            stream = litellm.completion(
                model=model,
                messages=messages,
                api_key=api_key,
                stream=True,
                **kwargs
            )

            # Stream chunks
            for chunk in stream:
                converted = self._convert_chunk(chunk)

                # Groq double-final chunk dedup
                # Some providers send finish_reason twice - skip duplicates
                if converted.finish_reason:
                    if seen_final:
                        continue  # Skip duplicate final chunk
                    seen_final = True

                # Accumulate content for error recovery
                if converted.content:
                    partial_content += converted.content

                yield converted

        except litellm.RateLimitError as e:
            raise AllProvidersRateLimitedError(
                message="",  # Will be auto-generated
                attempted_providers=[provider],
                provider_details=_build_provider_details(e, provider),
            )

        except Exception as e:
            # Map LiteLLM exceptions to user-friendly exceptions
            mapped_error = _map_litellm_error(e, provider=provider, model=model)

            # Mid-stream error handling: preserve partial content info
            if partial_content:
                mapped_error.context = {
                    **(getattr(mapped_error, 'context', {}) or {}),
                    'partial_content_chars': len(partial_content)
                }

            raise mapped_error

    def stream_completion_sync(
        self,
        model: str,
        messages: list[dict],
        _escalation_depth: int = 0,
        _escalated_from: Optional[str] = None,
        **kwargs
    ) -> Iterator[StreamChunk]:
        """
        Sync streaming completion via LiteLLM Router.

        Used by think_node when stream_callback is provided, allowing
        token-by-token streaming to the UI from a sync context.

        Args:
            model: Model group name ("fast", "chat", or "instruct")
            messages: Chat messages
            _escalation_depth: Internal counter to prevent infinite recursion (do not set)
            _escalated_from: Internal tracking of original tier (do not set)
            **kwargs: Additional params (max_tokens, temperature, tools, tool_choice, etc.)

        Yields:
            StreamChunk objects as they arrive from the provider

        Raises:
            NotConfiguredError: When service not configured with API keys
            AllProvidersRateLimitedError: When all providers exhausted
            ContextWindowExceededError: When quality tier also exceeds context (fatal)
            RuntimeError: When max escalation depth exceeded (safety guard)
        """
        import litellm  # Lazy import (fast after first __init__)

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

        # Throttle requests to avoid rate limits (especially for Groq)
        _get_throttle().wait_sync(model)

        try:
            # Call LiteLLM Router's sync streaming method
            stream = self._router.completion(
                model=model,
                messages=messages,
                stream=True,
                num_retries=0,  # Don't retry - let Orchestrator handle model fallback
                **kwargs
            )

            # Stream chunks
            for chunk in stream:
                converted = self._convert_chunk(chunk)

                # Groq double-final chunk dedup
                # Some providers send finish_reason twice - skip duplicates
                if converted.finish_reason:
                    if seen_final:
                        continue  # Skip duplicate final chunk
                    seen_final = True

                # Accumulate content for error recovery
                if converted.content:
                    partial_content += converted.content

                yield converted

        except litellm.ContextWindowExceededError:
            # Smart recovery: escalate to next tier (has larger context models)
            next_tier = ESCALATION_PATH.get(model)
            if next_tier:
                self._output.warn(
                    f"Context window exceeded on {model} tier, retrying with {next_tier} tier..."
                )
                # Track escalation for monitoring
                if self._callback:
                    self._callback.record_escalation(model, next_tier)
                # Recursively call with next tier
                yield from self.stream_completion_sync(
                    next_tier,
                    messages,
                    _escalation_depth=_escalation_depth + 1,
                    _escalated_from=model,
                    **kwargs
                )
                return
            # No escalation path available - fatal, re-raise
            raise

        except litellm.RateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message="",  # Will be auto-generated
                attempted_providers=[provider] if provider else [],
                provider_details=_build_provider_details(e, provider),
            )

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
            model: Model group name ("fast", "chat", or "instruct")
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
        import litellm  # Lazy import (fast after first __init__)

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
        await _get_throttle().wait_async(model)

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

        except litellm.ContextWindowExceededError:
            # Smart recovery: escalate to next tier (has larger context models)
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

        except litellm.RateLimitError as e:
            provider = getattr(e, 'llm_provider', None)
            raise AllProvidersRateLimitedError(
                message="",  # Will be auto-generated
                attempted_providers=[provider] if provider else [],
                provider_details=_build_provider_details(e, provider),
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

        # Extract tool calls first (may come from malformed content field)
        tool_calls = self._extract_tool_calls(choice.message)

        # Normalize content: if it's a dict (malformed tool call), use empty string
        # since we already extracted the tool call from it
        raw_content = choice.message.content
        if isinstance(raw_content, dict):
            content = ""  # Tool call was in content, extracted above
        else:
            content = raw_content or ""

        llm_response = LLMResponse(
            content=content,
            model=model_str,
            provider=provider,
            tokens_used=prompt_tokens + completion_tokens,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=elapsed * 1000,
            raw_response=response,
            metadata=metadata,
            tool_calls=tool_calls,
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

        Handles three formats:
        1. Standard: message.tool_calls contains array of tool call objects
        2. Malformed dict: message.content is a dict with name/arguments (some providers)
        3. XML tags: message.content contains <tool_name>{...}</tool_name> (some models)

        Args:
            message: LiteLLM message object

        Returns:
            List of ToolCall objects, or None if no tool calls
        """
        # Standard format: tool_calls array
        if hasattr(message, 'tool_calls') and message.tool_calls:
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

        # Malformed format: content is dict with name/arguments
        # Some providers return tool calls in content field instead of tool_calls
        content = getattr(message, 'content', None)
        if isinstance(content, dict) and 'name' in content:
            logger.warning(
                "Provider returned tool call in content field (malformed): %s",
                content.get('name')
            )
            arguments = content.get('arguments', {})
            if isinstance(arguments, str):
                arguments = self._parse_tool_arguments(arguments, content['name'])
            return [
                ToolCall(
                    id=f"malformed_{content['name']}",
                    name=content['name'],
                    arguments=arguments if isinstance(arguments, dict) else {}
                )
            ]

        # XML tag format: <tool_name>{...json...}</tool_name>
        # Some models output tool calls as XML tags instead of using function calling
        if isinstance(content, str) and '<' in content:
            xml_tool_calls = self._extract_xml_tool_calls(content)
            if xml_tool_calls:
                logger.warning(
                    "Provider returned tool calls as XML tags in content (malformed): %s",
                    [tc.name for tc in xml_tool_calls]
                )
                return xml_tool_calls

        return None

    def _extract_xml_tool_calls(self, content: str) -> Optional[list[ToolCall]]:
        """
        Extract tool calls from XML-style tags in content.

        Handles format like: <write_file>{"path": "...", "content": "..."}</write_file>

        Args:
            content: String content that may contain XML-style tool calls

        Returns:
            List of ToolCall objects, or None if no tool calls found
        """
        # Pattern matches <tool_name>{...json...}</tool_name>
        # Uses non-greedy match and handles multiline JSON
        pattern = r'<(\w+)>\s*(\{[^}]*\}|\{[\s\S]*?\})\s*</\1>'
        matches = re.findall(pattern, content)

        if not matches:
            return None

        tool_calls = []
        for i, (tool_name, json_str) in enumerate(matches):
            try:
                arguments = json.loads(json_str)
            except json.JSONDecodeError:
                # Try to fix common JSON issues
                arguments = self._parse_tool_arguments(json_str, tool_name)

            tool_calls.append(
                ToolCall(
                    id=f"xml_{tool_name}_{i}",
                    name=tool_name,
                    arguments=arguments if isinstance(arguments, dict) else {}
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
            model: Model group name ("fast", "chat", or "instruct")
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
        import litellm  # Lazy import (fast after first __init__)

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

        except litellm.ContextWindowExceededError:
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

    def _pick_mode(self, model: str) -> "instructor.Mode":
        """
        Derive instructor mode from model string.

        TOOLS mode is more reliable for models that support function calling.
        JSON mode is the fallback for models without native tool support.

        Args:
            model: The model identifier (e.g., "groq/llama-3.1-8b", "openai/gpt-4")

        Returns:
            instructor.Mode.TOOLS for models with function calling support,
            instructor.Mode.JSON otherwise
        """
        import instructor  # Lazy import (fast after first __init__)

        model_lower = model.lower()
        # Models with reliable function/tool calling support
        if any(x in model_lower for x in {"gpt-4", "gpt-3.5", "claude", "command-r"}):
            return instructor.Mode.TOOLS
        return instructor.Mode.JSON

    async def completion_structured(
        self,
        model: str,
        messages: list[dict],
        response_model: Type[T],
        max_retries: Optional[int] = None,
        mode_override: Optional["instructor.Mode"] = None,
        **kwargs,
    ) -> T:
        """
        Async structured output with validation retries.

        Uses Instructor to get validated Pydantic model responses from LLM.
        Inherits all router benefits: caching, rate limiting, provider fallback.

        Args:
            model: Model identifier (e.g., "fast", "chat", "instruct", "groq/llama-3.1-8b")
            messages: List of message dicts with role/content
            response_model: Pydantic model class to validate response against
            max_retries: Override retry count (default: DEFAULT_INSTRUCTOR_RETRIES)
            mode_override: Override auto-detected instructor mode (escape hatch)
            **kwargs: Additional params passed to completion

        Returns:
            Validated instance of response_model

        Raises:
            pydantic.ValidationError: If response cannot be validated after retries
        """
        retries = max_retries if max_retries is not None else DEFAULT_INSTRUCTOR_RETRIES
        mode = mode_override if mode_override else self._pick_mode(model)

        # Select client initialized with the correct mode
        client = self._instructor_clients[mode]
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            response_model=response_model,
            max_retries=retries,
            **kwargs,
        )

    def completion_structured_sync(
        self,
        model: str,
        messages: list[dict],
        response_model: Type[T],
        max_retries: Optional[int] = None,
        mode_override: Optional["instructor.Mode"] = None,
        **kwargs,
    ) -> T:
        """
        Sync structured output with validation retries.

        Uses Instructor to get validated Pydantic model responses from LLM.
        This is the sync version for non-async contexts (like TaskRouter.classify).

        Args:
            model: Model identifier (e.g., "fast", "chat", "instruct", "groq/llama-3.1-8b")
            messages: List of message dicts with role/content
            response_model: Pydantic model class to validate response against
            max_retries: Override retry count (default: DEFAULT_INSTRUCTOR_RETRIES)
            mode_override: Override auto-detected instructor mode (escape hatch)
            **kwargs: Additional params passed to completion

        Returns:
            Validated instance of response_model

        Raises:
            pydantic.ValidationError: If response cannot be validated after retries
        """
        retries = max_retries if max_retries is not None else DEFAULT_INSTRUCTOR_RETRIES
        mode = mode_override if mode_override else self._pick_mode(model)

        # Select client initialized with the correct mode
        client = self._instructor_clients_sync[mode]
        return client.chat.completions.create(
            model=model,
            messages=messages,
            response_model=response_model,
            max_retries=retries,
            **kwargs,
        )
