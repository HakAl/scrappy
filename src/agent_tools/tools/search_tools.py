"""
Code search tools for the code agent.

Provides pattern matching and code search capabilities.
"""

from pathlib import Path

from .base import Tool, ToolParameter, ToolResult, ToolContext


class SearchCodeTool(Tool):
    """Search for patterns in code files."""

    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return "Search for pattern in code"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("pattern", str, "Search pattern (case-insensitive)", required=True),
            ToolParameter("file_pattern", str, "File glob pattern", required=False, default="*.py")
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        pattern = kwargs["pattern"]
        file_pattern = kwargs.get("file_pattern", "*.py")

        try:
            results = []
            max_results = context.config.max_search_results if context.config else 100

            for file_path in context.project_root.rglob(file_pattern):
                # Skip git and cache directories
                if '.git' in str(file_path) or '__pycache__' in str(file_path):
                    continue

                rel_path = file_path.relative_to(context.project_root)
                if not context.is_safe_path(str(rel_path)):
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8')
                    for i, line in enumerate(content.splitlines(), 1):
                        if pattern.lower() in line.lower():
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                except Exception:
                    continue

                if len(results) > max_results:
                    break

            if not results:
                return ToolResult(
                    True,
                    f"No matches found for '{pattern}'",
                    metadata={"matches": 0, "pattern": pattern}
                )

            truncated = len(results) > max_results
            results = results[:max_results]

            # Store in working memory
            context.remember_search(f"{pattern} ({file_pattern})", results)

            output = "\n".join(results)
            if truncated:
                output += f"\n... [truncated to {max_results} matches]"

            return ToolResult(
                True,
                output,
                metadata={"matches": len(results), "pattern": pattern, "truncated": truncated}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error searching: {str(e)}")
