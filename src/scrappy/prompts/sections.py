"""Pure functions for building prompt sections."""

from typing import Optional

from .protocols import Platform


def platform_section(platform: Platform) -> str:
    """Generate platform-specific shell instructions.

    Args:
        platform: Target operating system platform

    Returns:
        Platform-specific command instructions
    """
    if platform == Platform.WINDOWS:
        return """## Platform: Windows (cmd.exe)

- Use cmd.exe commands: mkdir, copy, del, dir, type
- Do NOT use PowerShell cmdlets
- Paths use backslashes (e.g., C:\\Users\\...)
- Line continuation: use ^ at end of line"""

    return """## Platform: Unix/Linux

- Use standard Unix commands: mkdir -p, cp, rm, ls, cat
- Paths use forward slashes (e.g., /home/...)
- Line continuation: use \\ at end of line"""


def project_section(project_type: Optional[str]) -> str:
    """Generate project-type-specific instructions.

    Args:
        project_type: Language or framework identifier (e.g., "python", "nodejs")

    Returns:
        Project-specific instructions or empty string if unknown
    """
    if not project_type:
        return ""

    sections = {
        "python": """## Project: Python

- Package manager: pip
- Testing: pytest
- Virtual environments: venv or virtualenv
- Dependencies: requirements.txt or pyproject.toml""",
        "nodejs": """## Project: Node.js

- Package manager: npm or yarn
- Configuration: package.json
- Testing: Jest, Mocha, or framework-specific
- Dependencies: node_modules/""",
        "java": """## Project: Java

- Build tools: Maven (pom.xml) or Gradle (build.gradle)
- Testing: JUnit
- Dependencies: Maven Central or JCenter""",
        "go": """## Project: Go

- Module system: go.mod
- Testing: go test
- Build: go build
- Dependencies: managed via go.mod""",
        "rust": """## Project: Rust

- Build tool: Cargo
- Configuration: Cargo.toml
- Testing: cargo test
- Build: cargo build""",
    }

    return sections.get(project_type, "")


def codebase_structure_section(structure: Optional[str]) -> str:
    """Generate codebase structure section.

    Args:
        structure: Pre-formatted codebase structure summary

    Returns:
        Formatted structure section or empty string if none provided
    """
    if not structure:
        return ""

    return f"""## Codebase Structure

{structure}"""


def tool_format_section(use_json: bool = True) -> str:
    """Generate tool calling format instructions.

    Args:
        use_json: Whether to include JSON format instructions (False for native tool calling)

    Returns:
        Tool format instructions or empty string for native tools
    """
    if not use_json:
        return ""

    return """## Response Format

Respond with valid JSON only:
{
    "thought": "Your reasoning about the task",
    "action": "tool_name",
    "parameters": {"param1": "value1"},
    "is_complete": false
}

When task is complete, use the complete tool:
{
    "thought": "Task completed successfully",
    "action": "complete",
    "parameters": {"result": "Summary of what was done"},
    "is_complete": true
}

Use lowercase true/false for booleans (not Python True/False)."""


def strategy_section() -> str:
    """Generate strategic approach guidelines.

    Returns:
        Strategy section with file creation preferences
    """
    return """## Strategy

Prefer write_file over scaffolding tools (curl, npm create, etc.).
Direct file creation is more reliable and predictable.
When implementing features, create files with complete implementations rather than relying on external generators."""


def efficiency_section() -> str:
    """Generate efficiency guidelines.

    Returns:
        Efficiency section with redundancy avoidance rules
    """
    return """## Efficiency

Skip redundant operations. Reuse information already gathered.
Don't re-read files you've already seen in this conversation.
Don't re-run searches for information you already have.
Batch related operations when possible."""


def completion_section() -> str:
    """Generate task completion guidelines.

    Returns:
        Completion section with scope management rules
    """
    return """## Completion

Mark task complete when primary goal is done.
Don't add optional extras unless explicitly requested.
Don't gold-plate or over-engineer solutions.
Simple, working code is better than complex, feature-rich code."""


def safety_section() -> str:
    """Generate safety and correctness guidelines.

    Returns:
        Safety section with error prevention rules
    """
    return """## Safety

Use JSON with lowercase true/false (not Python True/False).
Never write empty files - always include minimal valid content.
Make incremental, careful changes.
Test changes before marking complete.
Don't delete files unless explicitly requested."""


def quality_section() -> str:
    """Generate quality standards guidelines.

    Returns:
        Quality section with code standards and best practices
    """
    return """## Quality Standards

- Write clean, maintainable code following existing patterns
- Include appropriate error handling
- Consider edge cases
- Prefer simple solutions over complex ones
- Test your changes when possible"""


def codebase_hint_section(
    extracted_files: tuple[str, ...],
    extracted_directories: tuple[str, ...],
    matched_project_files: tuple[str, ...] = (),
    matched_file_contents: tuple[tuple[str, str], ...] = ()
) -> str:
    """Generate hints for codebase queries based on extracted references.

    Args:
        extracted_files: File paths mentioned in the query
        extracted_directories: Directory paths mentioned in the query
        matched_project_files: Project files matching query terms from file_index
        matched_file_contents: (filepath, content_snippet) pairs for matched files

    Returns:
        Formatted hints or empty string if no references found
    """
    hints = []

    if extracted_files:
        file_list = ", ".join(extracted_files)
        hints.append(f"Detected file reference(s): {file_list}")

    if extracted_directories:
        dir_list = ", ".join(extracted_directories)
        hints.append(f"Detected directory reference(s): {dir_list}")

    # Include actual file contents if available (passive RAG)
    if matched_file_contents:
        hints.append("Relevant file contents from your project:")
        for filepath, content in matched_file_contents:
            hints.append(f"\n--- {filepath} ---\n{content}")
    elif matched_project_files:
        # Fallback to just file names if no content loaded
        files_to_show = matched_project_files[:10]
        file_list = "\n  - ".join(files_to_show)
        hints.append(f"Relevant project files matching your query:\n  - {file_list}")
        if len(matched_project_files) > 10:
            hints.append(f"  ... and {len(matched_project_files) - 10} more files")

    if not hints:
        return ""

    return "\n\n" + "\n".join(hints)
