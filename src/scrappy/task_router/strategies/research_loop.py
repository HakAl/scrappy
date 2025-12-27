"""
Research iteration loop with tool calling.

Manages the iterative conversation with LLM, including tool calls,
conversation history, and response processing.
"""

import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from ..classifier import ClassifiedTask
from ..pure_functions import extract_json_from_text
from .base import OrchestratorLike
from .research_protocols import (
    ToolBundleProtocol,
    ResponseCleanerProtocol
)


@dataclass
class HistoryEntry:
    """Structured history entry preserving message semantics."""
    iteration: int
    assistant_content: str      # Agent's response text - NEVER MASK (may be "")
    tool_call: Dict[str, Any]   # {tool, parameters}
    tool_call_id: str           # Required for API validation
    tool_result: str            # Raw output - CAN BE MASKED
    result_length: int          # For masked placeholder


class ResearchLoop:
    """
    Manages the research iteration loop with tool calling.

    Single responsibility: Orchestrate the iterative conversation between
    the LLM and tools, managing conversation history and determining when
    to stop.

    Uses observation masking to manage context window:
    - Recent tool results kept in full
    - Older tool results masked to "[X chars returned]"
    - Assistant reasoning (content) is NEVER masked
    """

    # Context management constants
    FULL_CONTEXT_WINDOW = 2     # Keep last N iterations with full tool results
    CONTEXT_THRESHOLD = 0.8     # Compact aggressively when at 80% of limit
    DEFAULT_CONTEXT_LIMIT = 65536  # Conservative default if model limit unknown

    def __init__(
        self,
        orchestrator: "OrchestratorLike",
        tool_bundle: ToolBundleProtocol,
        response_cleaner: ResponseCleanerProtocol
    ):
        """
        Initialize research loop.

        Args:
            orchestrator: Orchestrator for LLM delegation
            tool_bundle: Tool bundle for tool execution
            response_cleaner: Response cleaner for cleaning and fallbacks
        """
        self.orchestrator = orchestrator
        self.tool_bundle = tool_bundle
        self.response_cleaner = response_cleaner

    def run(
        self,
        provider: str,
        initial_prompt: str,
        system_prompt: str,
        task: ClassifiedTask,
        max_iterations: int,
        allowed_tools: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict[str, object]], int]:
        """
        Run the research loop with tool calling.

        Args:
            provider: Provider name to use
            initial_prompt: Initial research prompt
            system_prompt: System prompt with tool instructions
            task: The classified task being executed
            max_iterations: Maximum number of tool iterations
            allowed_tools: Optional list of allowed tool names.
                          If None, all tools in the bundle are allowed.
                          If provided, only these tools can be executed.

        Returns:
            Tuple of (final_response, tool_calls_made, total_tokens)
        """
        history: List[HistoryEntry] = []
        final_response = ""
        tool_calls_made: List[Dict[str, object]] = []
        total_tokens = 0
        last_input_tokens = 0
        current_window = self.FULL_CONTEXT_WINDOW

        # Get context limit for the model (if available)
        context_limit = self._get_context_limit(provider)

        for iteration in range(max_iterations + 1):
            # Build structured messages with observation masking
            messages = self._build_messages(
                initial_prompt,
                system_prompt,
                history,
                keep_full=current_window,
                remaining_iterations=max_iterations - iteration
            )

            # Delegate using messages parameter
            response = self.orchestrator.delegate(
                provider,
                prompt="",  # Empty - using messages instead
                messages=messages,
                system_prompt=None,  # Included in messages
                max_tokens=2000,
                temperature=0.3,
            )

            # Track token usage from API response
            last_input_tokens = getattr(response, 'input_tokens', 0)
            total_tokens += getattr(response, 'tokens_used', 0)

            # Check if we need aggressive compaction for next iteration
            if last_input_tokens > context_limit * self.CONTEXT_THRESHOLD:
                current_window = 1  # Aggressive: keep only 1 iteration full

            # Extract response content (handle null)
            response_text = response.content or "" if hasattr(response, 'content') else str(response)

            # Check for tool call
            tool_call = self._parse_tool_call(response_text) if self.tool_bundle.has_tools() else None

            # Validate tool is in allowed list (if restricted)
            if tool_call and allowed_tools is not None:
                tool_name = tool_call.get('tool')
                if tool_name not in allowed_tools:
                    tool_call = None

            if tool_call and iteration < max_iterations:
                # Execute tool
                tool_result = self.tool_bundle.execute_tool(tool_call)
                tool_call_id = f"call_{iteration}"

                tool_calls_made.append({
                    'tool': tool_call.get('tool'),
                    'parameters': tool_call.get('parameters', {}),
                    'result_length': len(tool_result)
                })

                # Store structured history entry
                history.append(HistoryEntry(
                    iteration=iteration,
                    assistant_content=response_text,  # Full reasoning - NEVER MASK
                    tool_call=tool_call,
                    tool_call_id=tool_call_id,
                    tool_result=tool_result,
                    result_length=len(tool_result)
                ))
            else:
                # No tool call or max iterations reached - this is the final response
                final_response = self.response_cleaner.clean_response(response_text)

                # Handle empty response after cleanup
                if not final_response:
                    if tool_calls_made:
                        # Tools were executed but LLM didn't summarize
                        # Convert history to legacy format for fallback
                        legacy_history = self._history_to_legacy(history)
                        final_response = self.response_cleaner.generate_fallback_response(
                            task,
                            tool_calls_made,
                            legacy_history
                        )
                    else:
                        final_response = self._generate_no_response_fallback(response_text)

                break

        return final_response, tool_calls_made, total_tokens

    def _build_messages(
        self,
        initial_prompt: str,
        system_prompt: str,
        history: List[HistoryEntry],
        keep_full: int,
        remaining_iterations: int
    ) -> List[Dict[str, Any]]:
        """
        Build structured message list with native tool protocol.

        Uses observation masking: older tool results are replaced with
        "[X chars returned]" while assistant reasoning is preserved.

        Args:
            initial_prompt: Initial user prompt
            system_prompt: System prompt with instructions
            history: List of history entries from previous iterations
            keep_full: Number of recent iterations to keep full results
            remaining_iterations: How many iterations remain

        Returns:
            List of messages in native tool protocol format
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_prompt},
        ]

        for i, entry in enumerate(history):
            is_recent = i >= len(history) - keep_full

            # Assistant message WITH tool_calls field (required for tool protocol)
            messages.append({
                "role": "assistant",
                "content": entry.assistant_content,  # May be "" - that's valid
                "tool_calls": [{
                    "id": entry.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": entry.tool_call['tool'],
                        "arguments": json.dumps(entry.tool_call.get('parameters', {}))
                    }
                }]
            })

            # Tool result with role: "tool" and matching ID
            if is_recent:
                result_content = entry.tool_result
            else:
                # Observation masking: replace with placeholder
                result_content = f"[{entry.result_length} chars returned]"

            messages.append({
                "role": "tool",
                "tool_call_id": entry.tool_call_id,
                "content": result_content
            })

        # Add continuation prompt if we have history
        if history and remaining_iterations > 0:
            if remaining_iterations > 1:
                continuation = (
                    f"You have {remaining_iterations} tool call(s) remaining. "
                    f"If you have enough information to answer the user's question, "
                    f"provide your FINAL ANSWER now (no JSON, just plain text). "
                    f"Otherwise, make another tool call."
                )
            else:
                continuation = (
                    "This is your LAST tool call. You MUST now provide your FINAL ANSWER "
                    "in plain text (no JSON, no tool calls). Summarize what you found."
                )
            messages.append({"role": "user", "content": continuation})

        return messages

    def _get_context_limit(self, provider: str) -> int:
        """
        Get context limit for the provider/model.

        Args:
            provider: Provider name

        Returns:
            Context limit in tokens
        """
        try:
            from ...orchestrator.litellm_config import MODEL_METADATA
            # Try to find a matching model for this provider
            for model_id, metadata in MODEL_METADATA.items():
                if model_id.startswith(provider + "/"):
                    return metadata.context_length
        except ImportError:
            pass
        return self.DEFAULT_CONTEXT_LIMIT

    def _history_to_legacy(self, history: List[HistoryEntry]) -> List[str]:
        """
        Convert structured history to legacy string format.

        Used for backward compatibility with response_cleaner.generate_fallback_response().

        Args:
            history: Structured history entries

        Returns:
            Legacy format: list of strings
        """
        legacy: List[str] = []
        for entry in history:
            legacy.append(f"\nTool Call: {json.dumps(entry.tool_call)}")
            legacy.append(f"\nTool Result:\n{entry.tool_result}")
        return legacy

    def _generate_no_response_fallback(self, original_response: str) -> str:
        """
        Generate fallback when LLM outputs only tool-call syntax but no tool was executed.

        This happens when:
        - Tool call was rejected (not in allowed_tools list)
        - Tool call parsing failed
        - No tools available but LLM output tool JSON anyway

        Args:
            original_response: The raw LLM response before cleaning

        Returns:
            User-friendly fallback message
        """
        if '{"tool"' in original_response or '"tool":' in original_response:
            return (
                "I attempted to use a tool that is not available for this query type. "
                "Please try rephrasing your question or ask about a different topic."
            )
        return (
            "I was unable to generate a response. "
            "Please try rephrasing your question."
        )

    def _parse_tool_call(self, response: str) -> Optional[Dict[str, object]]:
        """
        Parse tool call from LLM response.

        Extracts and parses JSON from various formats including
        code blocks, plain text, and Python-style booleans.

        Args:
            response: Raw LLM response text

        Returns:
            Parsed tool call dict with 'tool' and 'parameters' keys, or None
        """
        result = extract_json_from_text(response)

        if result and 'tool' in result:
            return result

        return None
