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
from scrappy.graph.protocols import StreamingOrchestratorProtocol, ThinkResult
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
    Production implementation of ThinkDelegatorProtocol using orchestrator.

    Composes:
    - Orchestrator for streaming completions with fallback (owns model selection)
    - ThinkErrorHandler for error recovery decisions
    - ToolCallProcessor for streaming fragment accumulation

    Model Selection & Fallback:
    Delegated entirely to orchestrator.stream_completion_with_fallback(), which handles:
    - Model selection via model_selector
    - Rate limit detection and marking models as unavailable
    - Automatic fallback to alternative models
    - Session-sticky model preferences

    Error Recovery:
    - Orchestrator handles rate limits with automatic fallback
    - This class handles other errors (network, auth) via error_handler
    """

    def __init__(
        self,
        orchestrator: StreamingOrchestratorProtocol,
        error_handler: Optional[ThinkErrorHandlerProtocol] = None,
        tool_call_processor: Optional[ToolCallProcessor] = None,
    ):
        """
        Initialize delegator with dependencies.

        Args:
            orchestrator: Orchestrator for streaming completions with fallback
            error_handler: Handler for error recovery (uses default if not provided)
            tool_call_processor: Processor for tool call format conversion
        """
        self._orchestrator = orchestrator
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

        Model selection and rate limit fallback are delegated to the orchestrator.
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

        # Build LLM kwargs
        llm_kwargs = self._build_llm_kwargs(tools)

        # Get cancellation token
        cancellation_token = run_context.cancellation_token if run_context else None

        # Map tier to selection type for orchestrator
        selection_type = self._tier_to_selection_type(current_tier)

        try:
            result = self._do_streaming_completion(
                messages=messages,
                llm_kwargs=llm_kwargs,
                run_context=run_context,
                cancellation_token=cancellation_token,
                selection_type=selection_type,
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
            # Let error handler decide recovery action
            # Note: Rate limit errors are handled by orchestrator with fallback,
            # so if we get here with a rate limit error, all models are exhausted
            return self._error_handler.handle(e, run_context)

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

        Note: Currently delegates to sync complete() since orchestrator only
        provides sync streaming. The on_chunk callback is not invoked.
        TODO: Add async streaming support to orchestrator.
        """
        # For now, fall back to sync completion
        # Async streaming would require orchestrator async support
        return self.complete(messages, tools, run_context, current_tier)

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
        messages: list[dict],
        llm_kwargs: dict[str, Any],
        run_context: Optional[AgentRunContextProtocol],
        cancellation_token: Any,
        selection_type: ModelSelectionType,
    ) -> ThinkResult:
        """
        Perform synchronous streaming completion via orchestrator.

        Orchestrator handles model selection and fallback on rate limit.
        """
        content_parts: list[str] = []
        all_fragments: list[ToolCallFragment] = []
        response_model = ""
        response_provider = ""

        # Pass cancellation token to orchestrator via kwargs
        if cancellation_token is not None:
            llm_kwargs["cancellation_token"] = cancellation_token

        # Stream from orchestrator - it handles model selection and fallback
        stream = self._orchestrator.stream_completion_with_fallback(
            messages=messages,
            selection_type=selection_type,
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
    orchestrator: StreamingOrchestratorProtocol,
    error_handler: Optional[ThinkErrorHandlerProtocol] = None,
) -> LiteLLMThinkDelegator:
    """
    Factory function to create a think delegator.

    Args:
        orchestrator: Orchestrator for streaming completions with fallback
        error_handler: Optional custom error handler

    Returns:
        Configured LiteLLMThinkDelegator
    """
    return LiteLLMThinkDelegator(
        orchestrator=orchestrator,
        error_handler=error_handler,
    )
