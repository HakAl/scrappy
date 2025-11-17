"""
Context-aware system prompt builder.

Constructs dynamic prompts based on:
- Platform (Windows cmd.exe vs Unix shell)
- Project type (Python, Java, Node.js, etc.)
- Available tools
- Task context
"""
from pathlib import Path
from typing import Optional
import sys

from src.context import CodebaseContext
from src.platform_utils import is_windows


class PromptBuilder:
    """Builds context-aware system prompts for LLM agents."""

    def __init__(
        self,
        context: Optional[CodebaseContext] = None,
        project_root: Optional[Path] = None
    ):
        """
        Initialize PromptBuilder.

        Args:
            context: Existing CodebaseContext instance (preferred)
            project_root: Path to project root (creates new context if context not provided)
        """
        if context is not None:
            self.context = context
        elif project_root is not None:
            self.context = CodebaseContext(str(project_root))
        else:
            self.context = CodebaseContext()

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

        # Available tools (skip if custom tools section provided)
        if 'tools' not in self._custom_sections:
            sections.append(self._build_tools_section())

        # Response format
        sections.append(self._build_format_section())

        # Task context (if provided)
        if task:
            sections.append(f"\n## Current Task\n{task}")

        # Custom sections
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
        return """
## Available Tools

- read_file: Read file contents
- write_file: Write or create files (prefer over shell redirection)
- list_files: List directory contents
- search_code: Search for patterns in codebase
- run_command: Execute shell commands

IMPORTANT: Prefer write_file over shell commands for creating files.
This ensures proper encoding and cross-platform compatibility."""

    def _build_format_section(self) -> str:
        """Build response format section."""
        return """
## Response Format

Return a JSON object with:
- "action": The tool to use (or "respond" for text response)
- "parameters": Tool parameters as key-value pairs
- "reasoning": Brief explanation of your choice

Use lowercase true/false for booleans, not Python's True/False."""
