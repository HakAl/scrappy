"""
Prompt building for research tasks.

Handles construction of system prompts and research prompts with tool instructions
and context integration.
"""

from typing import Optional, List
from ..classifier import ClassifiedTask


class PromptBuilder:
    """
    Builds prompts for research tasks.

    Single responsibility: Convert task information and tool availability
    into properly formatted prompts for the LLM.
    """

    RESEARCH_TOOLS = [
        'web_fetch',
        'web_search',
        'read_file',
        'list_files',
        'list_directory',
        'search_code',
        'git_log',
        'git_diff',
        'git_blame',
        'git_show',
        'git_recent_changes',
    ]

    def __init__(self, tool_descriptions_provider: Optional[callable] = None):
        """
        Initialize the prompt builder.

        Args:
            tool_descriptions_provider: Optional callable that returns tool descriptions.
                                       Signature: () -> str
        """
        self._tool_descriptions_provider = tool_descriptions_provider

    def build_system_prompt(self, has_tools: bool) -> str:
        """
        Build the system prompt for the research assistant.

        Args:
            has_tools: Whether tools are available to the assistant

        Returns:
            System prompt string
        """
        base_prompt = "You are a helpful research assistant. Provide concise, accurate information."

        if not has_tools or not self._tool_descriptions_provider:
            return base_prompt

        tool_desc = self._tool_descriptions_provider()
        return f"""{base_prompt}

IMPORTANT: You have access to tools for fetching real information. USE THEM when asked to fetch, check, or look up external data.

Available tools:
{tool_desc}

HOW TO USE TOOLS:
When you need information (package versions, documentation, web content, or codebase details), respond ONLY with:
```json
{{"tool": "tool_name", "parameters": {{"param1": "value1"}}}}
```

EXAMPLES FOR WEB/EXTERNAL INFO:
- User asks about Django version -> Use: {{"tool": "web_search", "parameters": {{"registry": "pypi", "query": "django"}}}}
- User asks about React package -> Use: {{"tool": "web_search", "parameters": {{"registry": "npm", "query": "react"}}}}
- User asks to fetch from URL -> Use: {{"tool": "web_fetch", "parameters": {{"url": "https://..."}}}}
- User asks about scikit-learn docs -> Use: {{"tool": "web_fetch", "parameters": {{"url": "https://scikit-learn.org/stable/api/index.html"}}}}

EXAMPLES FOR CODEBASE SEARCHES:
- User asks about "frontend/App.js" -> Use: {{"tool": "search_code", "parameters": {{"pattern": "register", "file_pattern": "**/App.js"}}}}
- User asks "does app.js have X" -> Use: {{"tool": "search_code", "parameters": {{"pattern": "X", "file_pattern": "**/*.js"}}}}
- User asks about a class -> Use: {{"tool": "search_code", "parameters": {{"pattern": "ClassName", "search_type": "class", "file_pattern": "**/*.py"}}}}
- User mentions specific file -> Use: {{"tool": "read_file", "parameters": {{"file_path": "frontend/src/App.js"}}}}
- User asks about directory -> Use: {{"tool": "list_directory", "parameters": {{"path": "frontend", "depth": 3}}}}

IMPORTANT FOR FILE SEARCHES:
- Use "**/" prefix for RECURSIVE search (e.g., "**/App.js" finds frontend/src/App.js)
- File patterns are CASE-SENSITIVE, so use "**/[Aa]pp.js" or "**/*.js" if unsure
- When user mentions a directory path like "frontend/", check that directory first with list_directory
- If searching for text in a specific file, use search_code with that exact file pattern

CRITICAL RULES:
1. If the user asks to FETCH, CHECK, or LOOK UP external info, you MUST use a tool first
2. If the user asks about FILES, CODE, or DIRECTORIES in the project, use search_code, read_file, or list_directory
3. Do NOT give generic advice - USE THE TOOLS to get real data
4. After receiving tool results, provide a helpful summary
5. Only give your final answer (without tool calls) after you have the information"""

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
        # Add context if provided
        context_info = ""
        if context_summary:
            context_info = f"\n\nProject Context:\n{context_summary}\n"

        # Build tool hint based on task characteristics
        tool_hint = self._build_tool_hint(task)

        return f"""User Request:
{task.original_input}
{context_info}{tool_hint}

Respond appropriately. If information is needed, use a tool first."""

    def _build_tool_hint(self, task: ClassifiedTask) -> str:
        """
        Build a hint about which tools to use based on task characteristics.

        Args:
            task: The classified task

        Returns:
            Tool hint string (may be empty)
        """
        if not self._tool_descriptions_provider:
            return ""

        lower_input = task.original_input.lower()
        original_input = task.original_input

        # Detect if this likely needs web tools
        needs_web = any(kw in lower_input for kw in [
            'fetch', 'look up', 'latest', 'version', 'pypi', 'npm',
            'github.com', 'documentation', 'website', 'url', 'http'
        ])

        # Detect codebase/file queries
        needs_codebase = any([
            # File extension mentions
            any(ext in lower_input for ext in [
                '.js', '.py', '.ts', '.tsx', '.jsx', '.java', '.cpp',
                '.rs', '.go', '.rb', '.php', '.css', '.html', '.json',
                '.yaml', '.yml', '.md'
            ]),
            # File path patterns
            '/' in original_input and 'http' not in lower_input,
            # Keywords indicating file/code queries
            any(kw in lower_input for kw in [
                'file', 'directory', 'folder', 'codebase', 'source',
                'frontend', 'backend', 'src/', 'does the', 'is there',
                'where is', 'find the', 'show me', 'check if', 'contain',
                'have a', 'has a', 'include', 'import'
            ])
        ])

        if needs_web:
            return "\n\nIMPORTANT: This request requires fetching external information. You MUST use a tool (web_fetch or web_search) to get real data. Respond with a JSON tool call first."

        if needs_codebase:
            return self._build_codebase_hint(task)

        return "\n\nYou have tools available if you need to fetch external information or search the codebase."

    def _build_codebase_hint(self, task: ClassifiedTask) -> str:
        """
        Build specific hints for codebase queries.

        Args:
            task: The classified task with extracted files/directories

        Returns:
            Codebase-specific hint string
        """
        file_hints = []

        if task.extracted_files:
            file_hints.append(f"Detected file reference(s): {', '.join(task.extracted_files)}")
            # Suggest search patterns
            for f in task.extracted_files[:2]:
                basename = f.split('/')[-1]
                file_hints.append(f"  -> To search in {basename}, use file_pattern: \"**/{basename}\"")

        if task.extracted_directories:
            file_hints.append(f"Detected directory reference(s): {', '.join(task.extracted_directories)}")
            for d in task.extracted_directories[:2]:
                file_hints.append(f"  -> To explore {d}/, use: list_directory with path=\"{d}\"")

        hint_text = "\n".join(file_hints) if file_hints else ""
        if hint_text:
            hint_text = f"\n{hint_text}"

        return f"""\n\nIMPORTANT: This request is about the LOCAL CODEBASE. You MUST use file/search tools to answer:
- Use search_code to find text patterns (with file_pattern like "**/*.js" for recursive search)
- Use read_file to read specific files
- Use list_directory to explore directories
{hint_text}
Respond with a JSON tool call FIRST, do not guess or make assumptions about file contents."""
