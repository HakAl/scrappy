"""
LiteLLM-based think delegator implementation.

Encapsulates all LLM call logic that was previously inline in think.py:
- Model selection (affinity, model_selection service, or tier fallback)
- Streaming with cancellation support
- Error handling with automatic fallback
- Provider affinity tracking

Single Responsibility: Make LLM calls with proper model selection and error recovery.
"""

from typing import Any, Callable, Optional

from scrappy.graph.nodes.think_error_handler import (
    DefaultThinkErrorHandler,
    ThinkErrorHandlerProtocol,
)
from scrappy.graph.nodes.tool_call_processor import ToolCallProcessor
from scrappy.graph.protocols import LLMServiceProtocol, StreamingLLMServiceProtocol, ThinkResult
from scrappy.graph.run_context import AgentRunContextProtocol
from scrappy.graph.state import ToolCall
from scrappy.infrastructure.exceptions import RecoveryAction
from scrappy.infrastructure.logging import get_logger
from scrappy.orchestrator.litellm_service import StreamCancelledError
from scrappy.orchestrator.model_selection import ModelSelectionType
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment

logger = get_logger(__name__)

# Default LLM call parameters
DEFAULT_MAX_RESPONSE_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.3


class LiteLLMThinkDelegator:
    """
    Production implementation of ThinkDelegatorProtocol using LiteLLM.

    Composes:
    - LLMService for actual completions
    - ModelSelectionService (via run_context) for model selection
    - ThinkErrorHandler for error recovery decisions
    - ToolCallProcessor for streaming fragment accumulation

    Model Selection Priority:
    1. run_context.preferred_model (affinity from previous success)
    2. run_context.model_selection.select() (priority-based)
    3. current_tier via Router (fallback)

    Error Recovery:
    - On rate limit: try fallback model via model_selection
    - On network error: retry same model
    - On auth error: abort (fatal)
    """

    def __init__(
        self,
        llm_service: LLMServiceProtocol,
        error_handler: Optional[ThinkErrorHandlerProtocol] = None,
        tool_call_processor: Optional[ToolCallProcessor] = None,
    ):
        """
        Initialize delegator with dependencies.

        Args:
            llm_service: LLM service for completions
            error_handler: Handler for error recovery (uses default if not provided)
            tool_call_processor: Processor for tool call format conversion
        """
        self._llm = llm_service
        self._error_handler = error_handler or DefaultThinkErrorHandler()
        self._tool_processor = tool_call_processor or ToolCallProcessor()

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
    ) -> ThinkResult:
        """
        Synchronous completion with automatic model selection and fallback.

        Uses streaming internally for cancellation support, accumulates result.
        """
        # Check cancellation before starting
        if run_context is not None and run_context.is_cancelled():
            logger.info("Think delegator cancelled before start")
            return ThinkResult(
                error="Cancelled by user",
                recovery_action=RecoveryAction.ABORT.value,
                is_fatal=True,
            )

        # Select model
        model = self._select_model(run_context, current_tier)

        # Build LLM kwargs
        llm_kwargs = self._build_llm_kwargs(tools)

        # Get cancellation token
        cancellation_token = run_context.cancellation_token if run_context else None

        # Try completion with fallback on error
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                result = self._do_streaming_completion(
                    model=model,
                    messages=messages,
                    llm_kwargs=llm_kwargs,
                    run_context=run_context,
                    cancellation_token=cancellation_token,
                    is_direct=(model is not None),
                    tier=current_tier,
                )

                # Check for empty response
                if result.is_success and not result.content.strip() and not result.has_tool_calls:
                    logger.warning("LLM returned empty response")
                    return ThinkResult(
                        error="LLM returned empty response. This may indicate an API issue.",
                        recovery_action=RecoveryAction.RETRY.value,
                        error_category="empty_response",
                    )

                return result

            except StreamCancelledError:
                return ThinkResult(
                    error="Cancelled by user",
                    recovery_action=RecoveryAction.ABORT.value,
                    is_fatal=True,
                )

            except Exception as e:
                error_result = self._error_handler.handle(e, run_context)

                if error_result.is_fatal:
                    return error_result

                if error_result.recovery_action == RecoveryAction.FALLBACK.value:
                    # Try to get fallback model
                    fallback_model = self._get_fallback_model(run_context, current_tier)
                    if fallback_model:
                        logger.warning(
                            "Rate limited on %s, falling back to %s",
                            model or current_tier,
                            fallback_model,
                        )
                        model = fallback_model
                        continue
                    else:
                        # No fallback available
                        return ThinkResult(
                            error="All models exhausted. Please try again later.",
                            recovery_action=RecoveryAction.ABORT.value,
                            error_category="rate_limit",
                            is_fatal=True,
                        )

                # For retry, continue with same model
                if error_result.recovery_action == RecoveryAction.RETRY.value:
                    continue

                # Other recovery actions: return the error result
                return error_result

        # Max attempts exhausted
        return ThinkResult(
            error="Max retry attempts exceeded",
            recovery_action=RecoveryAction.ABORT.value,
            error_category="exhausted",
            is_fatal=True,
        )

    async def complete_streaming(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ThinkResult:
        """
        Async streaming completion with chunk callback.

        Similar to complete() but:
        - Uses async streaming for real-time output
        - Invokes on_chunk callback with each content piece
        - Checks cancellation between chunks
        """
        # Check cancellation before starting
        if run_context is not None and run_context.is_cancelled():
            logger.info("Streaming think delegator cancelled before start")
            return ThinkResult(
                error="Cancelled by user",
                recovery_action=RecoveryAction.ABORT.value,
                is_fatal=True,
            )

        # Select model
        model = self._select_model(run_context, current_tier)

        # Build LLM kwargs
        llm_kwargs = self._build_llm_kwargs(tools)

        # Try completion with fallback on error
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                result = await self._do_async_streaming_completion(
                    model=model,
                    messages=messages,
                    llm_kwargs=llm_kwargs,
                    run_context=run_context,
                    on_chunk=on_chunk,
                    tier=current_tier,
                )

                # Check for empty response
                if result.is_success and not result.content.strip() and not result.has_tool_calls:
                    logger.warning("LLM returned empty response")
                    return ThinkResult(
                        error="LLM returned empty response. This may indicate an API issue.",
                        recovery_action=RecoveryAction.RETRY.value,
                        error_category="empty_response",
                    )

                return result

            except Exception as e:
                error_result = self._error_handler.handle(e, run_context)

                if error_result.is_fatal:
                    return error_result

                if error_result.recovery_action == RecoveryAction.FALLBACK.value:
                    fallback_model = self._get_fallback_model(run_context, current_tier)
                    if fallback_model:
                        logger.warning(
                            "Rate limited on %s, falling back to %s",
                            model or current_tier,
                            fallback_model,
                        )
                        model = fallback_model
                        continue
                    else:
                        return ThinkResult(
                            error="All models exhausted. Please try again later.",
                            recovery_action=RecoveryAction.ABORT.value,
                            error_category="rate_limit",
                            is_fatal=True,
                        )

                if error_result.recovery_action == RecoveryAction.RETRY.value:
                    continue

                return error_result

        return ThinkResult(
            error="Max retry attempts exceeded",
            recovery_action=RecoveryAction.ABORT.value,
            error_category="exhausted",
            is_fatal=True,
        )

    def _select_model(
        self,
        run_context: Optional[AgentRunContextProtocol],
        current_tier: str,
    ) -> Optional[str]:
        """
        Select model using affinity and priority.

        Returns specific model ID or None to use tier-based selection.

        Priority:
        1. Affinity (preferred_model) if no handoff triggered
        2. model_selection.select() if service available
        3. None (use tier via Router)
        """
        if run_context is None:
            return None

        # If preferred model set and no handoff triggered, use affinity
        if run_context.preferred_model and not run_context.should_handoff():
            return run_context.preferred_model

        # Try model selection service
        if run_context.model_selection is not None:
            try:
                # Agent mode uses INSTRUCT, chat mode uses tier mapping
                selection_type = self._tier_to_selection_type(current_tier)
                return run_context.model_selection.select(
                    selection_type=selection_type,
                    session_preferred=run_context.preferred_model,
                )
            except Exception as e:
                logger.warning("Model selection failed: %s", e)

        return None

    def _get_fallback_model(
        self,
        run_context: Optional[AgentRunContextProtocol],
        current_tier: str,
    ) -> Optional[str]:
        """Get fallback model after rate limit."""
        if run_context is None or run_context.model_selection is None:
            return None

        # Clear handoff to allow fresh selection
        run_context.clear_handoff()

        try:
            selection_type = self._tier_to_selection_type(current_tier)
            return run_context.model_selection.select(
                selection_type=selection_type,
                session_preferred=None,  # Don't prefer current model - it failed
            )
        except Exception as e:
            logger.warning("Fallback model selection failed: %s", e)
            return None

    def _tier_to_selection_type(self, tier: str) -> ModelSelectionType:
        """Map tier string to ModelSelectionType."""
        mapping = {
            "fast": ModelSelectionType.FAST,
            "chat": ModelSelectionType.CHAT,
            "instruct": ModelSelectionType.INSTRUCT,
        }
        return mapping.get(tier, ModelSelectionType.INSTRUCT)

    def _build_llm_kwargs(self, tools: Optional[list[dict]]) -> dict[str, Any]:
        """Build common LLM call kwargs."""
        kwargs: dict[str, Any] = {
            "max_tokens": DEFAULT_MAX_RESPONSE_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return kwargs

    def _do_streaming_completion(
        self,
        model: Optional[str],
        messages: list[dict],
        llm_kwargs: dict[str, Any],
        run_context: Optional[AgentRunContextProtocol],
        cancellation_token: Any,
        is_direct: bool,
        tier: str,
    ) -> ThinkResult:
        """
        Perform synchronous streaming completion.

        Uses stream_completion_direct for specific models,
        stream_completion_sync for tier-based.
        """
        content_parts: list[str] = []
        all_fragments: list[ToolCallFragment] = []
        response_model = ""
        response_provider = ""

        if is_direct and model:
            # Direct call to specific model (affinity or explicit)
            logger.info("Using direct model: %s", model)
            stream = self._llm.stream_completion_direct(
                model=model,
                messages=messages,
                cancellation_token=cancellation_token,
                **llm_kwargs,
            )
        else:
            # Tier-based via Router
            stream = self._llm.stream_completion_sync(
                model=tier,
                messages=messages,
                cancellation_token=cancellation_token,
                **llm_kwargs,
            )

        for chunk in stream:
            if isinstance(chunk, StreamChunk):
                if chunk.content:
                    content_parts.append(chunk.content)
                if chunk.tool_call_fragments:
                    all_fragments.extend(chunk.tool_call_fragments)
                if chunk.model:
                    response_model = chunk.model
                if chunk.provider:
                    response_provider = chunk.provider

        # Assemble result
        content = "".join(content_parts)
        tool_calls = self._process_tool_calls(all_fragments)
        model_display = self._format_model_display(response_provider, response_model)

        # Record success for affinity
        if run_context and response_provider:
            run_context.record_provider_success(response_provider, response_model)

        return ThinkResult(
            content=content,
            tool_calls=tuple(tool_calls),
            model_display=model_display,
        )

    async def _do_async_streaming_completion(
        self,
        model: Optional[str],
        messages: list[dict],
        llm_kwargs: dict[str, Any],
        run_context: Optional[AgentRunContextProtocol],
        on_chunk: Optional[Callable[[str], None]],
        tier: str,
    ) -> ThinkResult:
        """
        Perform async streaming completion with chunk callback.

        Requires llm_service to implement StreamingLLMServiceProtocol.
        """
        # Type check for streaming support
        if not isinstance(self._llm, StreamingLLMServiceProtocol):
            # Fall back to sync
            return self.complete(messages, llm_kwargs.get("tools"), run_context, tier)

        content_parts: list[str] = []
        all_fragments: list[ToolCallFragment] = []
        response_model = ""
        response_provider = ""

        async for chunk in self._llm.stream_completion(
            model=tier,
            messages=messages,
            **llm_kwargs,
        ):
            # Check cancellation between chunks
            if run_context is not None and run_context.is_cancelled():
                logger.info("Async streaming cancelled")
                return ThinkResult(
                    error="Cancelled by user",
                    recovery_action=RecoveryAction.ABORT.value,
                    is_fatal=True,
                )

            if isinstance(chunk, StreamChunk):
                if chunk.content:
                    content_parts.append(chunk.content)
                    if on_chunk:
                        on_chunk(chunk.content)
                if chunk.tool_call_fragments:
                    all_fragments.extend(chunk.tool_call_fragments)
                if chunk.model:
                    response_model = chunk.model
                if chunk.provider:
                    response_provider = chunk.provider

        content = "".join(content_parts)
        tool_calls = self._process_tool_calls(all_fragments)
        model_display = self._format_model_display(response_provider, response_model)

        if run_context and response_provider:
            run_context.record_provider_success(response_provider, response_model)

        return ThinkResult(
            content=content,
            tool_calls=tuple(tool_calls),
            model_display=model_display,
        )

    def _process_tool_calls(self, fragments: list[ToolCallFragment]) -> list[ToolCall]:
        """Convert streaming fragments to tool calls."""
        if not fragments:
            return []

        accumulated = self._tool_processor.accumulate(fragments)
        return self._tool_processor.fragments_to_calls(accumulated)

    def _format_model_display(self, provider: str, model: str) -> Optional[str]:
        """Format model display string (e.g., 'cerebras: llama-3.3-70b')."""
        if not provider or not model:
            return None

        # Strip provider prefix from model if present
        model_name = model
        if "/" in model_name:
            model_name = model_name.split("/", 1)[1]

        return f"{provider}: {model_name}"


def create_think_delegator(
    llm_service: LLMServiceProtocol,
    error_handler: Optional[ThinkErrorHandlerProtocol] = None,
) -> LiteLLMThinkDelegator:
    """
    Factory function to create a think delegator.

    Args:
        llm_service: LLM service for completions
        error_handler: Optional custom error handler

    Returns:
        Configured LiteLLMThinkDelegator
    """
    return LiteLLMThinkDelegator(
        llm_service=llm_service,
        error_handler=error_handler,
    )
