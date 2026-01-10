"""Protocol and type definitions for stateless prompt generation."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class Platform(Enum):
    """Operating system platform for environment-specific instructions."""

    WINDOWS = "windows"
    UNIX = "unix"


class ResearchSubtype(Enum):
    """Type of research query to determine tool availability."""

    CODEBASE = "codebase"
    GENERAL = "general"


@dataclass(frozen=True)
class ChatPromptConfig:
    """Configuration for chat mode - minimal, no tools, direct answers."""

    pass


@dataclass(frozen=True)
class AgentPromptConfig:
    """Configuration for agent mode with full tool access and behavioral guidelines.

    Required fields:
        platform: Target OS platform
        tool_names: List of available tool names
        original_task: The user's original task/query
        working_dir: Working directory for file operations

    Optional fields for dynamic state:
        iteration: Current iteration count
        last_error: Error message if recovering from failure
        files_changed: Files modified this session
        working_memory_context: Session context from working memory
        search_strategy: Search guidance based on available tools
        rag_context: Retrieved context from semantic search
    """

    # Required
    platform: Platform
    tool_names: tuple[str, ...]
    original_task: str
    working_dir: str

    # Optional dynamic state
    iteration: int = 0
    last_error: Optional[str] = None
    files_changed: tuple[str, ...] = ()
    working_memory_context: Optional[str] = None
    search_strategy: Optional[str] = None
    rag_context: Optional[str] = None


@dataclass(frozen=True)
class ResearchPromptConfig:
    """Configuration for research mode - tools depend on subtype."""

    subtype: ResearchSubtype
    tool_descriptions: Optional[str] = None
    context_summary: Optional[str] = None
    extracted_files: tuple[str, ...] = ()
    extracted_directories: tuple[str, ...] = ()
    matched_project_files: tuple[str, ...] = ()  # Files from file_index matching query terms
    matched_file_contents: tuple[tuple[str, str], ...] = ()  # (filepath, content_snippet) pairs
    semantic_available: bool = True  # Whether semantic search is available and ready


class PromptFactoryProtocol(Protocol):
    """Stateless prompt generation with mode-specific methods."""

    def create_chat_system_prompt(self) -> str:
        """Generate simple chat system prompt without tool instructions."""
        ...

    def create_chat_user_prompt(self, query: str) -> str:
        """Generate chat user prompt - just the query."""
        ...

    def create_agent_system_prompt(self, config: AgentPromptConfig) -> str:
        """Generate agent system prompt with tools and behavioral guidelines."""
        ...

    def create_agent_user_prompt(self, task: str, config: AgentPromptConfig) -> str:
        """Generate agent user prompt with task and context."""
        ...

    def create_research_system_prompt(self, config: ResearchPromptConfig) -> str:
        """Generate research system prompt - tools depend on subtype."""
        ...

    def create_research_user_prompt(
        self, query: str, config: ResearchPromptConfig
    ) -> str:
        """Generate research user prompt with query and hints."""
        ...
