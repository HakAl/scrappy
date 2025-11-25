"""
Code search tools for the code agent.

Provides pattern matching and code search capabilities.
"""

import ast
import re
from pathlib import Path
from typing import Optional

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


class SearchCodeTool(ToolBase):
    """Search for patterns in code files with regex, AST-aware, and context support."""

    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return "Search for pattern in code with regex, AST-aware search, and context lines support"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("pattern", str, "Search pattern (string or regex)", required=True),
            ToolParameter("file_pattern", str, "File glob pattern", required=False, default="*.py"),
            ToolParameter("use_regex", bool, "Use regex pattern matching", required=False, default=False),
            ToolParameter("case_sensitive", bool, "Case-sensitive search (default: False)", required=False, default=False),
            ToolParameter("context_lines", int, "Number of lines to show before/after match", required=False, default=0),
            ToolParameter("search_type", str, "AST-aware search type: 'text', 'function', 'class', 'method', 'import'", required=False, default="text")
        ]

    def _search_text(self, content: str, pattern: str, use_regex: bool, case_sensitive: bool, context_lines: int, rel_path: Path) -> list[str]:
        """Perform text-based search with optional regex and context lines."""
        results = []
        lines = content.splitlines()

        # Compile regex pattern if needed
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")

        matched_lines = set()  # Track which lines matched to avoid duplicates in context

        for i, line in enumerate(lines):
            match_found = False

            if use_regex:
                if regex.search(line):
                    match_found = True
            else:
                if case_sensitive:
                    match_found = pattern in line
                else:
                    match_found = pattern.lower() in line.lower()

            if match_found:
                matched_lines.add(i)

        # Build results with context
        processed_lines = set()
        for match_idx in sorted(matched_lines):
            start = max(0, match_idx - context_lines)
            end = min(len(lines), match_idx + context_lines + 1)

            for idx in range(start, end):
                if idx in processed_lines:
                    continue
                processed_lines.add(idx)

                line_num = idx + 1
                marker = ">" if idx in matched_lines else " "
                results.append(f"{rel_path}:{line_num}:{marker} {lines[idx].rstrip()}")

            # Add separator between context blocks if there's a gap
            if context_lines > 0 and match_idx != max(matched_lines):
                next_match = min(m for m in matched_lines if m > match_idx)
                if next_match - match_idx > context_lines * 2 + 1:
                    results.append("---")

        return results

    def _search_ast(self, content: str, pattern: str, search_type: str, case_sensitive: bool, rel_path: Path) -> list[str]:
        """Perform AST-aware search for Python code structures."""
        results = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to text search if AST parsing fails
            return []

        lines = content.splitlines()

        # Compile pattern for matching
        if case_sensitive:
            def matches(name: str) -> bool:
                return pattern in name
        else:
            pattern_lower = pattern.lower()
            def matches(name: str) -> bool:
                return pattern_lower in name.lower()

        if search_type == "function":
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and matches(node.name):
                    line_num = node.lineno
                    line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                    results.append(f"{rel_path}:{line_num}: [function] {node.name} - {line_content.strip()}")

        elif search_type == "class":
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and matches(node.name):
                    line_num = node.lineno
                    line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                    results.append(f"{rel_path}:{line_num}: [class] {node.name} - {line_content.strip()}")

        elif search_type == "method":
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and matches(item.name):
                            line_num = item.lineno
                            line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                            results.append(f"{rel_path}:{line_num}: [method] {node.name}.{item.name} - {line_content.strip()}")

        elif search_type == "import":
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if matches(alias.name):
                            line_num = node.lineno
                            line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                            results.append(f"{rel_path}:{line_num}: [import] {alias.name} - {line_content.strip()}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if matches(module):
                        line_num = node.lineno
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                        results.append(f"{rel_path}:{line_num}: [from-import] {module} - {line_content.strip()}")
                    for alias in node.names:
                        if matches(alias.name):
                            line_num = node.lineno
                            line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                            results.append(f"{rel_path}:{line_num}: [from-import] {module}.{alias.name} - {line_content.strip()}")

        return results

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        pattern = kwargs["pattern"]
        file_pattern = kwargs.get("file_pattern", "*.py")
        use_regex = kwargs.get("use_regex", False)
        case_sensitive = kwargs.get("case_sensitive", False)
        context_lines = kwargs.get("context_lines", 0)
        search_type = kwargs.get("search_type", "text")

        # Validate search_type
        valid_types = {"text", "function", "class", "method", "import"}
        if search_type not in valid_types:
            return ToolResult(False, "", f"Invalid search_type '{search_type}'. Must be one of: {', '.join(valid_types)}")

        try:
            results = []
            max_results = context.config.max_search_results

            for file_path in context.project_root.rglob(file_pattern):
                # Skip git and cache directories
                if '.git' in str(file_path) or '__pycache__' in str(file_path):
                    continue

                rel_path = file_path.relative_to(context.project_root)
                if not context.is_safe_path(str(rel_path)):
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8')

                    if search_type == "text":
                        file_results = self._search_text(content, pattern, use_regex, case_sensitive, context_lines, rel_path)
                    else:
                        file_results = self._search_ast(content, pattern, search_type, case_sensitive, rel_path)

                    results.extend(file_results)
                except ValueError as e:
                    # Regex compilation error
                    return ToolResult(False, "", str(e))
                except Exception:
                    continue

                if len(results) > max_results:
                    break

            if not results:
                return ToolResult(
                    True,
                    f"No matches found for '{pattern}' (type: {search_type})",
                    metadata={"matches": 0, "pattern": pattern, "search_type": search_type}
                )

            truncated = len(results) > max_results
            results = results[:max_results]

            # Store in working memory
            context.remember_search(f"{pattern} ({file_pattern}, type={search_type})", results)

            output = "\n".join(results)
            if truncated:
                output += f"\n... [truncated to {max_results} matches]"

            return ToolResult(
                True,
                output,
                metadata={
                    "matches": len(results),
                    "pattern": pattern,
                    "search_type": search_type,
                    "use_regex": use_regex,
                    "case_sensitive": case_sensitive,
                    "context_lines": context_lines,
                    "truncated": truncated
                }
            )
        except Exception as e:
            return ToolResult(False, "", f"Error searching: {str(e)}")
