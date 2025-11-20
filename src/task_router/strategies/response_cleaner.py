"""
Response cleaning for research tasks.

Handles removal of tool call syntax and artifacts from LLM responses,
and generates fallback responses when needed.
"""

import re
from typing import List, Dict
from ..classifier import ClassifiedTask


class ResponseCleaner:
    """
    Cleans and processes LLM responses.

    Single responsibility: Transform raw LLM responses into clean,
    user-facing output by removing tool call artifacts and generating
    fallbacks when necessary.
    """

    def clean_response(self, response: str) -> str:
        """
        Remove tool call syntax and artifacts from response.

        Args:
            response: Raw LLM response text

        Returns:
            Cleaned response text
        """
        if not response:
            return response

        # Remove JSON code blocks with tool calls
        cleaned = re.sub(r'```json\s*\n?\s*\{[^`]+\}\s*\n?```', '', response)

        # Remove XML-style tool call tags
        cleaned = re.sub(r'<tool_call>.*?</tool_call>', '', cleaned, flags=re.DOTALL)

        # Remove explicit TOOL_CALL: markers
        cleaned = re.sub(r'TOOL_CALL:\s*\{.+?\}', '', cleaned, flags=re.DOTALL)

        # Remove role-played tool calls (LLM describing what it would do)
        cleaned = re.sub(r'Tool Call:\s*\{[^}]+\}.*?(?=\n\n|\Z)', '', cleaned, flags=re.DOTALL)

        # Remove bare JSON tool calls (LLM outputting raw JSON in final response)
        # Handle nested braces by matching lines that look like tool calls
        lines = cleaned.split('\n')
        filtered_lines = []
        for line in lines:
            # Skip lines that are just JSON tool calls
            if not line.strip().startswith('{"tool"'):
                filtered_lines.append(line)
        cleaned = '\n'.join(filtered_lines)

        # Remove common artifacts
        cleaned = re.sub(r'Please wait for the result\.\.\.', '', cleaned)
        cleaned = re.sub(r'Tool Result:\s*\n*', '', cleaned)

        # Clean up excessive newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()

    def generate_fallback_response(
        self,
        task: ClassifiedTask,
        tool_calls_made: List[Dict[str, object]],
        conversation_history: List[str]
    ) -> str:
        """
        Generate a fallback response when LLM doesn't provide one.

        Args:
            task: The classified task
            tool_calls_made: List of tool calls that were executed
            conversation_history: Full conversation history

        Returns:
            Fallback response summarizing tool results
        """
        # Extract tool results from conversation history
        results_summary = []

        for item in conversation_history:
            if item.startswith("\nTool Result:"):
                result_text = item.replace("\nTool Result:\n", "").strip()
                if result_text and len(result_text) > 10:
                    # Truncate long results
                    if len(result_text) > 500:
                        result_text = result_text[:500] + "..."
                    results_summary.append(result_text)

        if results_summary:
            # Provide a summary of what was found
            response = f"Based on the research conducted ({len(tool_calls_made)} tool calls made):\n\n"
            for i, result in enumerate(results_summary[:3], 1):
                response += f"Result {i}:\n{result}\n\n"
            return response.strip()
        else:
            # No results found
            tools_used = [tc.get('tool', 'unknown') for tc in tool_calls_made]
            return f"Research completed using {tools_used}, but no relevant information was found. The files may not exist or may not contain the requested information."
