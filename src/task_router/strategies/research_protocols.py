"""
Protocol definitions for ResearchExecutor components.

These protocols define the contracts for all dependencies that ResearchExecutor
requires, enabling dependency injection, testing with test doubles, and
swapping implementations.
"""

from pathlib import Path
from typing import Protocol, Optional, Dict, List
from ..classifier import ClassifiedTask
from .research_subtype import ResearchSubtype


class PromptBuilderProtocol(Protocol):
    """Defines the contract for building prompts for research tasks."""

    def build_system_prompt(self, has_tools: bool) -> str:
        """
        Build the system prompt for the research assistant.

        Args:
            has_tools: Whether tools are available to the assistant

        Returns:
            System prompt string
        """
        ...

    def build_research_prompt(
        self,
        task: ClassifiedTask,
        context_summary: Optional[str] = None
    ) -> str:
        """
        Build the user-facing research prompt.

        Args:
            task: The classified task to build prompt for
            context_summary: Optional project context summary

        Returns:
            Research prompt string
        """
        ...


class ToolBundleProtocol(Protocol):
    """Defines the contract for tool management and execution."""

    def has_tools(self) -> bool:
        """Check if tools are available."""
        ...

    def get_tool_descriptions(self) -> str:
        """
        Get formatted descriptions of all available tools.

        Returns:
            Multi-line string with tool descriptions
        """
        ...

    def is_allowed_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed for research tasks.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed, False otherwise
        """
        ...

    def execute_tool(self, tool_call: Dict[str, object]) -> str:
        """
        Execute a tool call and return the result.

        Args:
            tool_call: Dictionary with 'tool' and 'parameters' keys

        Returns:
            Tool execution result as string
        """
        ...


class PathResolverProtocol(Protocol):
    """Defines the contract for file path resolution and exploration."""

    def auto_explore_if_needed(self, task: ClassifiedTask) -> None:
        """
        Automatically trigger codebase exploration if the task needs it.

        Args:
            task: The classified task to check
        """
        ...

    def resolve_file_paths(self, task: ClassifiedTask) -> None:
        """
        Resolve extracted file names to full paths.

        Modifies task.extracted_files in place with resolved paths.

        Args:
            task: The classified task with extracted file references
        """
        ...


class ProviderPickerProtocol(Protocol):
    """Defines the contract for provider selection and validation."""

    def pick_provider(self, preferred_provider: str) -> str:
        """
        Select and validate a provider for the task.

        Args:
            preferred_provider: The preferred provider name

        Returns:
            The validated provider name to use

        Raises:
            ValueError: If provider is not available
        """
        ...


class ResearchLoopProtocol(Protocol):
    """Defines the contract for the research iteration loop."""

    def run(
        self,
        provider: str,
        initial_prompt: str,
        system_prompt: str,
        task: ClassifiedTask,
        max_iterations: int,
        allowed_tools: Optional[List[str]] = None
    ) -> tuple[str, List[Dict[str, object]], int]:
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
        ...


class ResponseCleanerProtocol(Protocol):
    """Defines the contract for cleaning up LLM responses."""

    def clean_response(self, response: str) -> str:
        """
        Remove tool call syntax and artifacts from response.

        Args:
            response: Raw LLM response text

        Returns:
            Cleaned response text
        """
        ...

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
        ...


class ResearchSubclassifierProtocol(Protocol):
    """
    Defines the contract for sub-classifying research queries.

    Determines whether a research query is about the codebase (requiring
    codebase tools) or general knowledge (requiring only web tools or
    direct LLM response).
    """

    def classify(
        self,
        query: str,
        context_summary: Optional[str] = None
    ) -> ResearchSubtype:
        """
        Classify a research query as codebase or general knowledge.

        Args:
            query: The user's research query
            context_summary: Optional project context summary for better classification

        Returns:
            ResearchSubtype.CODEBASE or ResearchSubtype.GENERAL
        """
        ...
