"""
Exact text search tool for the code agent.

Provides literal pattern matching using system tools (rg/grep/findstr).
"""

from typing import Optional, List

from .base import ToolBase, ToolParameter, ToolResult, ToolContext
from ..protocols import TextSearchProtocol, NoSearchToolError, SearchMatch
from ..components.text_search_factory import TextSearchFactory


class FindExactTextTool(ToolBase):
    """
    Exact text/pattern search using system tools.

    Uses the best available backend (ripgrep > grep > findstr).
    """

    def __init__(
        self,
        text_search: Optional[TextSearchProtocol] = None,
        backend_factory: Optional[TextSearchFactory] = None,
    ):
        """Initialize with optional injected dependencies.

        Args:
            text_search: Pre-configured search backend (for testing).
            backend_factory: Factory for creating backends. Defaults to TextSearchFactory.
        """
        self._text_search = text_search
        self._backend_factory = backend_factory or TextSearchFactory()
        self._backend_name: Optional[str] = None

    @property
    def name(self) -> str:
        return "find_exact_text"

    @property
    def description(self) -> str:
        return (
            "EXACT LITERAL MATCH ONLY. Use when you know the precise string "
            "(e.g., specific error code, exact variable name, exact function signature) "
            "and need every occurrence. NOT for conceptual/semantic queries - use "
            "codebase_search for those. Supports regex patterns."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("pattern", str, "Search pattern (string or regex)", required=True),
            ToolParameter("file_pattern", str, "File glob pattern", required=False, default="*"),
            ToolParameter("use_regex", bool, "Use regex pattern matching", required=False, default=False),
            ToolParameter("case_sensitive", bool, "Case-sensitive search", required=False, default=False),
            ToolParameter("context_lines", int, "Lines to show before/after match", required=False, default=0),
        ]

    def _get_backend(self) -> TextSearchProtocol:
        """Get or create text search backend."""
        if self._text_search:
            if not self._backend_name:
                self._backend_name = self._text_search.name
            return self._text_search

        backend = self._backend_factory.create_backend()
        self._text_search = backend
        self._backend_name = backend.name
        return backend

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        pattern = kwargs["pattern"]
        file_pattern = kwargs.get("file_pattern", "*")
        use_regex = kwargs.get("use_regex", False)
        case_sensitive = kwargs.get("case_sensitive", False)
        context_lines = kwargs.get("context_lines", 0)

        try:
            backend = self._get_backend()
        except NoSearchToolError as e:
            return ToolResult(False, "", str(e))

        try:
            max_results = context.config.max_search_results if context.config else 100

            matches, search_metadata = backend.search(
                pattern=pattern,
                path=context.project_root,
                file_glob=file_pattern,
                use_regex=use_regex,
                case_sensitive=case_sensitive,
                context_lines=context_lines,
                max_results=max_results,
            )

            # Check for search errors
            if search_metadata.error:
                return ToolResult(
                    False,
                    "",
                    f"Search error: {search_metadata.error}",
                    metadata={"stderr": search_metadata.stderr}
                )

            if not matches:
                return ToolResult(
                    True,
                    f"No matches found for '{pattern}'",
                    metadata={"matches": 0, "pattern": pattern, "backend": self._backend_name}
                )

            # Format output
            output = self._format_matches(matches, context_lines)
            truncated = len(matches) >= max_results

            if truncated:
                output += f"\n... [truncated to {max_results} matches]"

            # Add warning if backend has limitations
            if search_metadata.warning:
                output = f"[Warning: {search_metadata.warning}]\n\n{output}"

            context.remember_search(f"{pattern} ({file_pattern})", [m.file_path for m in matches])

            return ToolResult(
                True,
                output,
                metadata={
                    "matches": len(matches),
                    "pattern": pattern,
                    "backend": self._backend_name,
                    "truncated": truncated,
                    "context_lines_supported": search_metadata.context_lines_supported,
                }
            )

        except Exception as e:
            return ToolResult(False, "", f"Search error: {str(e)}")

    def _format_matches(self, matches: List[SearchMatch], context_lines: int) -> str:
        """Format matches for output."""
        lines = []
        prev_file = None

        for match in matches:
            if context_lines > 0 and prev_file and prev_file != match.file_path:
                lines.append("---")

            marker = ">" if match.is_match else " "
            lines.append(f"{match.file_path}:{match.line_number}:{marker} {match.line_content}")
            prev_file = match.file_path

        return "\n".join(lines)
