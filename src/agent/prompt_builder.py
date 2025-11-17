"""
Context-aware system prompt builder.

Constructs dynamic prompts based on:
- Platform (Windows cmd.exe vs Unix shell)
- Project type (Python, Java, Node.js, etc.)
- Available tools
- Task context
"""
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import sys

from src.context import CodebaseContext
from src.platform_utils import is_windows

if TYPE_CHECKING:
    from src.agent_tools.tools import ToolRegistry


class PromptBuilder:
    """Builds context-aware system prompts for LLM agents."""

    def __init__(
        self,
        context: Optional[CodebaseContext] = None,
        project_root: Optional[Path] = None,
        tool_registry: Optional["ToolRegistry"] = None
    ):
        """
        Initialize PromptBuilder.

        Args:
            context: Existing CodebaseContext instance (preferred)
            project_root: Path to project root (creates new context if context not provided)
            tool_registry: ToolRegistry instance for dynamic tool descriptions
        """
        if context is not None:
            self.context = context
        elif project_root is not None:
            self.context = CodebaseContext(str(project_root))
        else:
            self.context = CodebaseContext()

        # Tool registry for dynamic tool descriptions
        self.tool_registry = tool_registry

        # Platform detection (deferred to property for mockability)
        self._cached_platform = None

        # Custom sections
        self._custom_sections = {}
        self._section_overrides = {}

    @property
    def platform(self) -> str:
        """Current platform (detected on first access for mockability)."""
        if self._cached_platform is None:
            if is_windows():
                self._cached_platform = 'windows'
            elif sys.platform == 'darwin':
                self._cached_platform = 'darwin'
            else:
                self._cached_platform = 'unix'
        return self._cached_platform

    @property
    def project_type(self) -> str:
        """Detected project type from context."""
        if not self.context.is_explored():
            self.context.explore()
        return self.context.get_project_type()

    def add_section(self, name: str, content: str) -> None:
        """Add a custom section to the prompt."""
        self._custom_sections[name] = content

    def set_section(self, name: str, content: str) -> None:
        """Override a default section."""
        self._section_overrides[name] = content

    def build(self, task: Optional[str] = None) -> str:
        """
        Build the complete system prompt.

        Args:
            task: Optional task description to include

        Returns:
            Complete system prompt string
        """
        # Ensure context is explored
        if not self.context.is_explored():
            self.context.explore()

        sections = []

        # Core identity and capabilities
        sections.append(self._build_core_section())

        # Platform-specific guidance
        if 'platform' in self._section_overrides:
            sections.append(self._section_overrides['platform'])
        else:
            sections.append(self._build_platform_section())

        # Project-specific guidance
        sections.append(self._build_project_section())

        # Available tools (use registry if provided, skip if custom tools section)
        if 'tools' not in self._custom_sections:
            sections.append(self._build_tools_section())

        # Operational guidance sections (built-in, not bolted on)
        sections.append(self._build_strategy_section())
        sections.append(self._build_efficiency_section())
        sections.append(self._build_completion_section())
        sections.append(self._build_safety_section())

        # Task context (if provided)
        if task:
            sections.append(f"\n## Current Task\n{task}")

        # Custom sections (appended at end)
        for name, content in self._custom_sections.items():
            sections.append(f"\n## {name.title()}\n{content}")

        return '\n'.join(sections)

    def _build_core_section(self) -> str:
        """Build core identity section."""
        return """You are a software development assistant with access to file system tools.
Your job is to help complete coding tasks by reading, analyzing, and modifying code."""

    def _build_platform_section(self) -> str:
        """Build platform-specific guidance."""
        if self.platform == 'windows':
            return """
## Platform: Windows (cmd.exe)

CRITICAL: You are running in cmd.exe, NOT PowerShell.
- Use cmd.exe commands: mkdir, copy, xcopy, del, dir
- Do NOT use PowerShell cmdlets: New-Item, Copy-Item, Remove-Item, Get-ChildItem
- Paths use backslashes: C:\\Users\\project\\src
- mkdir creates parent directories by default (no -p flag needed)
- Use 'type' instead of 'cat' for file contents
- Use 'dir' instead of 'ls' for directory listing"""
        else:
            return """
## Platform: Unix/Linux

Use standard Unix commands:
- mkdir -p for creating directories with parents
- cp for copying files
- rm for removing files
- ls for listing directories
- cat for viewing file contents"""

    def _build_project_section(self) -> str:
        """Build project-type-specific guidance."""
        project_type = self.project_type

        if project_type == 'python':
            return """
## Project Type: Python

- Package management: pip, requirements.txt, or pyproject.toml
- Virtual environments: venv, virtualenv, or conda
- Testing: pytest, unittest
- Entry points: setup.py, pyproject.toml, __main__.py"""

        elif project_type == 'java':
            return """
## Project Type: Java

- Build tool: Maven (pom.xml) or Gradle (build.gradle)
- Package management: Maven Central, local repository
- Testing: JUnit, TestNG
- Compilation: javac or via build tool"""

        elif project_type == 'nodejs':
            return """
## Project Type: Node.js

- Package management: npm (package.json) or yarn
- Testing: Jest, Mocha, or built-in test runner
- Entry point: package.json main field
- Dependencies: node_modules directory"""

        elif project_type == 'go':
            return """
## Project Type: Go

- Module management: go.mod
- Testing: go test
- Build: go build
- Dependencies: go mod download"""

        elif project_type == 'rust':
            return """
## Project Type: Rust

- Package management: Cargo (Cargo.toml)
- Testing: cargo test
- Build: cargo build
- Dependencies: crates.io"""

        else:
            return """
## Project Type: Generic

Analyze the codebase structure to determine:
- Build system and package management
- Testing framework
- Entry points and configuration files"""

    def _build_tools_section(self) -> str:
        """Build available tools section."""
        if self.tool_registry is not None:
            # Use registry for dynamic tool descriptions
            return f"\n## Available Tools\n\n{self.tool_registry.get_full_prompt_section()}"
        else:
            # Fallback to static list
            return """
## Available Tools

- read_file: Read file contents
- write_file: Write or create files (prefer over shell redirection)
- list_files: List directory contents
- search_code: Search for patterns in codebase
- run_command: Execute shell commands

IMPORTANT: Prefer write_file over shell commands for creating files.
This ensures proper encoding and cross-platform compatibility.

## Response Format

Response format (JSON):
{
    "thought": "What I'm thinking about the task",
    "action": "tool_name",
    "parameters": {"param1": "value1"},
    "is_complete": false
}

When task is complete:
{
    "thought": "Task completed successfully",
    "action": "complete",
    "result": "Summary of what was done",
    "is_complete": true
}"""

    def _build_strategy_section(self) -> str:
        """Build strategy guidance section."""
        return """
## Strategy

Prefer write_file over scaffolding tools (curl, npm create).
Direct file creation is more reliable and predictable."""

    def _build_efficiency_section(self) -> str:
        """Build efficiency rules section."""
        return """
## Efficiency

Skip redundant operations. Reuse information already gathered.
Don't re-read files you've already seen in this conversation."""

    def _build_completion_section(self) -> str:
        """Build completion semantics section."""
        return """
## Completion

Mark task complete when primary goal is done.
Don't add optional extras unless explicitly requested."""

    def _build_safety_section(self) -> str:
        """Build safety rules section."""
        return """
## Safety

Use JSON with lowercase true/false (not Python True/False).
Never write empty files. Make incremental, careful changes."""

    def _build_format_section(self) -> str:
        """Build response format section (legacy, kept for backward compatibility)."""
        # This is now integrated into _build_tools_section when registry is used
        return ""
