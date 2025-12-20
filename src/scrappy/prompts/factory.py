"""Stateless prompt factory for mode-specific prompt generation."""

from .protocols import AgentPromptConfig, ResearchPromptConfig, ResearchSubtype
from .sections import (
    DEGRADED_MODE_SECTION,
    codebase_hint_section,
    codebase_structure_section,
    completion_section,
    efficiency_section,
    platform_section,
    project_section,
    quality_section,
    safety_section,
    strategy_section,
    task_tracking_section,
    tool_format_section,
)


class PromptFactory:
    """Stateless prompt factory - all data passed via config.

    Generates mode-specific prompts:
    - CHAT: Simple, no tools, direct answers
    - AGENT: Full tools, behavioral guidelines, iterative
    - RESEARCH: Tools depend on subtype (codebase vs general)
    """

    def create_chat_system_prompt(self) -> str:
        """Generate simple chat system prompt without tool instructions.

        Returns:
            Minimal system prompt for direct Q&A
        """
        return """You are Scrappy, an intelligent coding assistant.

Guidelines:
- Answer questions directly and concisely
- When explaining code, use clear examples
- If you're unsure, say so rather than guessing
- For complex topics, break down your explanation into steps
- Use markdown formatting for code blocks"""

    def create_chat_user_prompt(self, query: str) -> str:
        """Generate chat user prompt - just the query.

        Args:
            query: User's question or request

        Returns:
            The query itself (no modifications needed for chat mode)
        """
        return query

    def create_agent_system_prompt(self, config: AgentPromptConfig) -> str:
        """Generate agent system prompt with tools and behavioral guidelines.

        Args:
            config: Agent configuration with platform, tools, and context

        Returns:
            Complete agent system prompt with all sections
        """
        sections = [
            "You are a software development assistant with access to file system tools.",
            platform_section(config.platform),
            project_section(config.project_type),
            codebase_structure_section(config.codebase_structure),
            f"## Available Tools\n\n{config.tool_descriptions}",
            tool_format_section(use_json=not config.use_native_tools),
            task_tracking_section(),
            strategy_section(),
            efficiency_section(),
            quality_section(),
            completion_section(),
            safety_section(),
        ]

        return "\n\n".join(filter(None, sections))

    def create_agent_user_prompt(self, task: str, config: AgentPromptConfig) -> str:
        """Generate agent user prompt with task.

        Args:
            task: Task description
            config: Agent configuration (currently unused but available for future)

        Returns:
            User prompt with task description
        """
        return f"Please complete this task: {task}"

    def create_research_system_prompt(self, config: ResearchPromptConfig) -> str:
        """Generate research system prompt - tools depend on subtype.

        Args:
            config: Research configuration with subtype and optional tools

        Returns:
            System prompt appropriate for research subtype
        """
        if config.subtype == ResearchSubtype.GENERAL:
            if not config.tool_descriptions:
                return "You are a helpful assistant. Answer the question directly."
            return self._general_research_prompt(config)
        else:
            return self._codebase_research_prompt(config)

    def create_research_user_prompt(
        self, query: str, config: ResearchPromptConfig
    ) -> str:
        """Generate research user prompt with query and hints.

        Args:
            query: User's research question
            config: Research configuration with context and hints

        Returns:
            User prompt with query, context, and relevant hints
        """
        parts = [f"User Request:\n{query}"]

        if config.context_summary:
            parts.append(f"\nProject Context:\n{config.context_summary}")

        if config.subtype == ResearchSubtype.CODEBASE:
            hint = codebase_hint_section(
                config.extracted_files,
                config.extracted_directories,
                config.matched_project_files,
                config.matched_file_contents
            )
            if hint:
                parts.append(hint)

        parts.append(
            "\nRespond appropriately. If information is needed, use a tool first."
        )

        return "\n".join(parts)

    def _general_research_prompt(self, config: ResearchPromptConfig) -> str:
        """Generate general research prompt with optional web tools.

        Args:
            config: Research configuration with tool descriptions

        Returns:
            General research system prompt
        """
        assert config.tool_descriptions is not None, "Expected tool descriptions for general research"

        return f"""You are a helpful research assistant.

## Available Tools

{config.tool_descriptions}

{tool_format_section()}"""

    def _codebase_research_prompt(self, config: ResearchPromptConfig) -> str:
        """Generate codebase research prompt with file/search tools.

        Args:
            config: Research configuration with codebase tool descriptions

        Returns:
            Codebase research system prompt
        """
        tool_section = ""
        if config.tool_descriptions:
            tool_section = f"""## Available Tools

{config.tool_descriptions}

{tool_format_section()}"""

        degraded_mode = ""
        if not config.semantic_available:
            degraded_mode = f"\n\n{DEGRADED_MODE_SECTION}"

        return f"""You are a codebase research assistant with access to file system tools.

Your role:
- Find and explain code patterns, implementations, and architecture
- Search thoroughly before answering - use search_code and read_file
- Cite specific files and line numbers when referencing code
- If information isn't found, say so clearly

{tool_section}{degraded_mode}

Strategy:
1. CAST A WIDE NET: Use search_code for keywords first
2. VERIFY: Read the actual files found. Do not guess implementation details
3. CITATIONS: You MUST quote the filepath and line numbers in your findings
4. HONESTY: If you find conflicting patterns, report the conflict
5. Indicate confidence level in your findings""".strip()
