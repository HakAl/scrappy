"""
Research iteration loop with tool calling.

Manages the iterative conversation with LLM, including tool calls,
conversation history, and response processing.
"""

import json
from typing import List, Dict, Optional, Tuple
from ..classifier import ClassifiedTask
from ..json_extractor import JSONExtractor
from .research_protocols import (
    ToolBundleProtocol,
    ResponseCleanerProtocol
)


class ResearchLoop:
    """
    Manages the research iteration loop with tool calling.

    Single responsibility: Orchestrate the iterative conversation between
    the LLM and tools, managing conversation history and determining when
    to stop.
    """

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
        self._json_extractor = JSONExtractor()

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
        conversation_history: List[str] = []
        final_response = ""
        tool_calls_made: List[Dict[str, object]] = []
        total_tokens = 0

        for iteration in range(max_iterations + 1):
            # Build full prompt with history
            if conversation_history:
                full_prompt = initial_prompt + "\n\n" + "\n".join(conversation_history)
            else:
                full_prompt = initial_prompt

            # Delegate to provider
            response = self.orchestrator.delegate(
                provider,
                full_prompt,
                system_prompt=system_prompt,
                max_tokens=2000,
                temperature=0.3,
                use_context=True
            )

            # Extract response
            if hasattr(response, 'content'):
                response_text = response.content
                total_tokens += getattr(response, 'tokens_used', 0)
            else:
                response_text = str(response)

            # Check for tool call
            tool_call = self._parse_tool_call(response_text) if self.tool_bundle.has_tools() else None

            # Validate tool is in allowed list (if restricted)
            if tool_call and allowed_tools is not None:
                tool_name = tool_call.get('tool')
                if tool_name not in allowed_tools:
                    # Tool not allowed - treat as if no tool call was made
                    tool_call = None

            if tool_call and iteration < max_iterations:
                # Execute tool
                tool_result = self.tool_bundle.execute_tool(tool_call)
                tool_calls_made.append({
                    'tool': tool_call.get('tool'),
                    'parameters': tool_call.get('parameters', {}),
                    'result_length': len(tool_result)
                })

                # Add to conversation history
                conversation_history.append(f"\nTool Call: {json.dumps(tool_call)}")
                conversation_history.append(f"\nTool Result:\n{tool_result}")

                # Adjust continuation prompt based on remaining iterations
                remaining = max_iterations - iteration - 1
                if remaining > 0:
                    conversation_history.append(
                        f"\nYou have {remaining} tool call(s) remaining. "
                        f"If you have enough information to answer the user's question, "
                        f"provide your FINAL ANSWER now (no JSON, just plain text). "
                        f"Otherwise, make another tool call."
                    )
                else:
                    conversation_history.append(
                        "\nThis is your LAST tool call. You MUST now provide your FINAL ANSWER "
                        "in plain text (no JSON, no tool calls). Summarize what you found from "
                        "the tool results above."
                    )
            else:
                # No tool call or max iterations reached - this is the final response
                final_response = self.response_cleaner.clean_response(response_text)

                # If response is empty after cleanup but we have tool results, generate a summary
                if not final_response and tool_calls_made:
                    final_response = self.response_cleaner.generate_fallback_response(
                        task,
                        tool_calls_made,
                        conversation_history
                    )

                break

        return final_response, tool_calls_made, total_tokens

    def _parse_tool_call(self, response: str) -> Optional[Dict[str, object]]:
        """
        Parse tool call from LLM response.

        Uses JSONExtractor to extract and parse JSON from various formats
        including code blocks, plain text, and Python-style booleans.

        Args:
            response: Raw LLM response text

        Returns:
            Parsed tool call dict with 'tool' and 'parameters' keys, or None
        """
        result = self._json_extractor.parse(response)

        # Verify it's a tool call (has 'tool' key)
        if result and 'tool' in result:
            return result

        return None
