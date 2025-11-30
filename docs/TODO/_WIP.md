# SearchCodeTool Refactoring Plan

## Problem

Custom Python reimplementation of search in SearchCodeTool:

### Issues with Current Approach

1. **Custom Python search vs battle-tested tools** - Lines 52-62 do simple `pattern in line` check. Reinventing the wheel.

2. **Silent failures everywhere:**
   - Line 94-98: AST parse fails -> returns empty `[]`
   - Line 194-195: Any exception -> `continue` (silently skipped)

3. **Path filtering may exclude valid files** - Line 179: `is_safe_path()` could filter out paths that grep would find.

4. **Uses pathlib.rglob** - Less robust than rg/grep for traversing complex directory structures.

5. **Layered abstraction** - `CodeSearchHandler` -> `__getattr__` wrapper -> `SearchCodeTool` -> custom Python search. Many places for silent breakage.

---

## Strategy

### Keep
- Tool interface (renamed to `FindExactTextTool`)

### Replace
- All search logic -> shell out to best available system tool (rg/grep/findstr)

### Delete
- `CodeSearchHandler` - Redundant
- `QueryIntent.CODE_SEARCH` - Dead code after handler deletion
- AST search (`search_type="function"`, etc.) - Python-only, limited value
- All tests for deleted functionality

### Result
- Simple, focused tool: `find_exact_text` = literal pattern matching
- Reliable text search (rg/grep/findstr)
- Proper dependency injection throughout

---

## Architecture

### Simplified Design

```
                FindExactTextTool
                       |
                       | (injected)
                       v
               TextSearchProtocol
                       |
            +----------+----------+
            |          |          |
           rg        grep      findstr
           (1)        (2)        (3)
              fallback chain

Dependencies:
  - PlatformDetectorProtocol (from src/platform)
  - SubprocessRunnerProtocol (existing)
  - SearchOutputParserProtocol (new)
```

**No AST search.** Python-only, limited value.

**No Python fallback.** System tools only.

### Fallback Chain

| Priority | Tool | Platform | Notes |
|----------|------|----------|-------|
| 1 | `rg` (ripgrep) | All | Fastest, best defaults, recommended |
| 2 | `grep` | All | Check on all platforms (Git Bash, WSL, Cygwin) |
| 3 | `findstr` | Windows | Built-in since DOS, always available |

If no tool available, fail with clear error:
```
No search tool available. Install ripgrep (rg) for best performance,
or ensure grep (Unix) / findstr (Windows) is accessible in PATH.
```

---

## Decisions

| Issue | Decision |
|-------|----------|
| Platform detection | Use existing `PlatformDetectorProtocol` from `src/platform` |
| Search output parsing | Create new `SearchOutputParserProtocol` (distinct from existing `PlatformSanitizerProtocol`) |
| Windows path parsing | Platform-aware regex (handle `C:\` drive letters) |
| grep on Windows | Check on all platforms (doesn't hurt) |
| findstr context lines | Add warning to metadata via typed `SearchMetadata` |
| Shell execution | Pass command as list to runner, not joined string |
| QueryIntent.CODE_SEARCH | Delete enum value and all references |
| AST search | Remove entirely - Python-only, limited value |
| Backward compat alias | None - update all call sites directly |
| Silent failures | Return error info in `SearchMetadata`, never silently return `[]` |

---

## Implementation Plan

### Step 1: Create SearchOutputParserProtocol and Implementation

**File:** `src/agent_tools/protocols/__init__.py` (ADD to existing)

```python
from dataclasses import dataclass, field
from typing import Protocol, Optional, List
from pathlib import Path


@dataclass
class SearchMatch:
    """Single search match result."""
    file_path: str
    line_number: int
    line_content: str
    is_match: bool = True  # False for context lines


@dataclass
class SearchMetadata:
    """Typed metadata from search operations."""
    warning: Optional[str] = None
    context_lines_supported: bool = True
    error: Optional[str] = None
    stderr: Optional[str] = None


class SearchOutputParserProtocol(Protocol):
    """Contract for parsing search tool output.

    Distinct from PlatformSanitizerProtocol which handles command sanitization.
    This protocol handles parsing rg/grep/findstr output formats.
    """

    def parse_line(self, line: str) -> Optional[tuple[str, int, str, bool]]:
        """Parse a search tool output line.

        Args:
            line: Raw output line from rg/grep/findstr

        Returns:
            Tuple of (file_path, line_number, content, is_match) or None if unparseable.
            is_match is False for context lines (marked with - instead of :).
        """
        ...

    def normalize_path(self, path: str) -> str:
        """Normalize path separators for consistent output."""
        ...


class TextSearchProtocol(Protocol):
    """Contract for text-based code search."""

    def search(
        self,
        pattern: str,
        path: Path,
        file_glob: str = "*",
        use_regex: bool = False,
        case_sensitive: bool = False,
        context_lines: int = 0,
        max_results: int = 100,
    ) -> tuple[List[SearchMatch], SearchMetadata]:
        """Search for pattern in files.

        Returns:
            Tuple of (matches, metadata). Metadata contains warnings/errors.
            Never silently returns empty list on error - always populate metadata.error.
        """
        ...

    def is_available(self) -> bool:
        """Check if this search backend is available."""
        ...

    @property
    def name(self) -> str:
        """Backend name for logging/debugging."""
        ...


class NoSearchToolError(Exception):
    """Raised when no search tool is available."""
    pass
```

**File:** `src/agent_tools/components/search_output_parser.py` (NEW)

```python
"""Search output parsing for rg/grep/findstr."""

import re
from typing import Optional

from src.platform.protocols.detection import PlatformDetectorProtocol


class SearchOutputParser:
    """Parses search tool output with platform awareness.

    Implements SearchOutputParserProtocol.
    """

    def __init__(self, platform_detector: PlatformDetectorProtocol):
        """Initialize with injected platform detector.

        Args:
            platform_detector: Platform detection for Windows path handling.
        """
        self._platform = platform_detector

    def normalize_path(self, path: str) -> str:
        """Normalize path separators for consistent output."""
        return path.replace("\\", "/")

    def parse_line(self, line: str) -> Optional[tuple[str, int, str, bool]]:
        """Parse a search tool output line, handling platform differences.

        Returns:
            Tuple of (file_path, line_number, content, is_match) or None if unparseable.
        """
        if not line or line == "--":
            return None

        # Windows paths: C:\foo\bar.py:10:content
        # Need to handle drive letter colon specially
        if self._platform.is_windows() and len(line) > 2 and line[1] == ':':
            # Skip drive letter, parse rest
            rest = line[2:]
            match = re.match(r'^(.+?)([:\-])(\d+)\2(.*)$', rest)
            if match:
                file_path = line[0:2] + match.group(1)  # Reconstruct with drive
                separator = match.group(2)
                line_num = int(match.group(3))
                content = match.group(4)
                return (
                    self.normalize_path(file_path),
                    line_num,
                    content,
                    separator == ":"
                )
        else:
            # Unix paths: /foo/bar.py:10:content
            match = re.match(r'^(.+?)([:\-])(\d+)\2(.*)$', line)
            if match:
                return (
                    self.normalize_path(match.group(1)),
                    int(match.group(3)),
                    match.group(4),
                    match.group(2) == ":"
                )

        return None
```

### Step 2: Text Search Implementations

**File:** `src/agent_tools/components/text_search.py` (NEW)

```python
"""Text search implementations using external tools."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from src.platform.protocols.detection import PlatformDetectorProtocol

from ..protocols import (
    SearchMatch,
    SearchMetadata,
    SubprocessRunnerProtocol,
    SearchOutputParserProtocol,
)


class BaseTextSearch(ABC):
    """Base class for text search implementations."""

    def __init__(
        self,
        runner: SubprocessRunnerProtocol,
        output_parser: SearchOutputParserProtocol,
        platform_detector: PlatformDetectorProtocol,
    ):
        self._runner = runner
        self._parser = output_parser
        self._platform = platform_detector

    @abstractmethod
    def search(
        self,
        pattern: str,
        path: Path,
        file_glob: str = "*",
        use_regex: bool = False,
        case_sensitive: bool = False,
        context_lines: int = 0,
        max_results: int = 100,
    ) -> tuple[List[SearchMatch], SearchMetadata]:
        """Execute search and return (matches, metadata)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name."""
        ...

    def _parse_output(self, output: str) -> List[SearchMatch]:
        """Parse tool output into SearchMatch objects."""
        results = []
        for line in output.strip().split("\n"):
            parsed = self._parser.parse_line(line)
            if parsed:
                file_path, line_num, content, is_match = parsed
                results.append(SearchMatch(
                    file_path=file_path,
                    line_number=line_num,
                    line_content=content,
                    is_match=is_match,
                ))
        return results


class RipgrepSearch(BaseTextSearch):
    """Text search using ripgrep."""

    @property
    def name(self) -> str:
        return "ripgrep"

    def is_available(self) -> bool:
        return self._platform.has_tool("rg")

    def search(
        self,
        pattern: str,
        path: Path,
        file_glob: str = "*",
        use_regex: bool = False,
        case_sensitive: bool = False,
        context_lines: int = 0,
        max_results: int = 100,
    ) -> tuple[List[SearchMatch], SearchMetadata]:
        cmd_parts = ["rg", "--line-number", "--no-heading", "--with-filename"]

        if not use_regex:
            cmd_parts.append("--fixed-strings")
        if not case_sensitive:
            cmd_parts.append("--ignore-case")
        if context_lines > 0:
            cmd_parts.append(f"--context={context_lines}")
        if file_glob != "*":
            cmd_parts.extend(["--glob", file_glob])

        cmd_parts.extend(["--max-count", str(max_results)])
        cmd_parts.append("--")
        cmd_parts.append(pattern)
        cmd_parts.append(str(path))

        result = self._runner.execute_list(cmd_parts, str(path), timeout=30)

        if result.exit_code not in (0, 1):  # 1 = no matches
            return [], SearchMetadata(
                error=f"ripgrep exited with code {result.exit_code}",
                stderr=result.stderr
            )

        return self._parse_output(result.stdout), SearchMetadata()


class GrepSearch(BaseTextSearch):
    """Text search using GNU grep."""

    @property
    def name(self) -> str:
        return "grep"

    def is_available(self) -> bool:
        return self._platform.has_tool("grep")

    def search(
        self,
        pattern: str,
        path: Path,
        file_glob: str = "*",
        use_regex: bool = False,
        case_sensitive: bool = False,
        context_lines: int = 0,
        max_results: int = 100,
    ) -> tuple[List[SearchMatch], SearchMetadata]:
        cmd_parts = ["grep", "-r", "-n", "--with-filename"]

        if not use_regex:
            cmd_parts.append("--fixed-strings")
        if not case_sensitive:
            cmd_parts.append("--ignore-case")
        if context_lines > 0:
            cmd_parts.append(f"-C{context_lines}")
        if file_glob != "*":
            cmd_parts.extend(["--include", file_glob])

        cmd_parts.extend(["-m", str(max_results)])
        cmd_parts.append("--")
        cmd_parts.append(pattern)
        cmd_parts.append(str(path))

        result = self._runner.execute_list(cmd_parts, str(path), timeout=30)

        if result.exit_code not in (0, 1):
            return [], SearchMetadata(
                error=f"grep exited with code {result.exit_code}",
                stderr=result.stderr
            )

        return self._parse_output(result.stdout), SearchMetadata()


class FindstrSearch(BaseTextSearch):
    """Text search using Windows findstr."""

    @property
    def name(self) -> str:
        return "findstr"

    def is_available(self) -> bool:
        return self._platform.has_tool("findstr")

    def search(
        self,
        pattern: str,
        path: Path,
        file_glob: str = "*",
        use_regex: bool = False,
        case_sensitive: bool = False,
        context_lines: int = 0,
        max_results: int = 100,
    ) -> tuple[List[SearchMatch], SearchMetadata]:
        metadata = SearchMetadata()

        # Warn about unsupported context_lines
        if context_lines > 0:
            metadata.context_lines_supported = False
            metadata.warning = "findstr does not support context lines"

        cmd_parts = ["findstr", "/S", "/N"]

        if use_regex:
            cmd_parts.append("/R")
        else:
            cmd_parts.append("/L")

        if not case_sensitive:
            cmd_parts.append("/I")

        cmd_parts.append(pattern)
        cmd_parts.append(str(path / file_glob))

        result = self._runner.execute_list(cmd_parts, str(path), timeout=30)

        if result.exit_code != 0:
            # findstr returns 1 for no matches, 2 for errors
            if result.exit_code == 1:
                return [], metadata
            metadata.error = f"findstr exited with code {result.exit_code}"
            metadata.stderr = result.stderr
            return [], metadata

        matches = self._parse_output(result.stdout)[:max_results]
        return matches, metadata
```

### Step 3: Backend Factory

**File:** `src/agent_tools/components/text_search_factory.py` (NEW)

```python
"""Factory for creating text search backends."""

from typing import Optional, Callable

from src.platform.protocols.detection import PlatformDetectorProtocol
from src.platform.detection import SystemPlatformDetector

from ..protocols import SubprocessRunnerProtocol, TextSearchProtocol, NoSearchToolError
from .subprocess_runner import SubprocessRunner
from .search_output_parser import SearchOutputParser
from .text_search import RipgrepSearch, GrepSearch, FindstrSearch


class TextSearchFactory:
    """Factory for creating text search backends with proper DI."""

    def __init__(
        self,
        runner: Optional[SubprocessRunnerProtocol] = None,
        platform_detector: Optional[PlatformDetectorProtocol] = None,
    ):
        """Initialize factory with optional injected dependencies.

        Args:
            runner: Subprocess runner. Defaults to SubprocessRunner.
            platform_detector: Platform detector. Defaults to SystemPlatformDetector.
        """
        self._runner = runner
        self._platform = platform_detector

    def _get_runner(self) -> SubprocessRunnerProtocol:
        if self._runner is None:
            self._runner = SubprocessRunner()
        return self._runner

    def _get_platform(self) -> PlatformDetectorProtocol:
        if self._platform is None:
            self._platform = SystemPlatformDetector()
        return self._platform

    def create_backend(self) -> TextSearchProtocol:
        """Create the best available search backend.

        Returns:
            TextSearchProtocol implementation.

        Raises:
            NoSearchToolError: If no search tool is available.
        """
        runner = self._get_runner()
        platform = self._get_platform()
        parser = SearchOutputParser(platform)

        backends = [
            RipgrepSearch(runner, parser, platform),
            GrepSearch(runner, parser, platform),
            FindstrSearch(runner, parser, platform),
        ]

        for backend in backends:
            if backend.is_available():
                return backend

        raise NoSearchToolError(
            "No search tool available. Install ripgrep (rg) for best performance, "
            "or ensure grep (Unix) / findstr (Windows) is accessible in PATH."
        )
```

### Step 4: FindExactTextTool

**File:** `src/agent_tools/tools/search_tools.py` (REPLACE)

```python
"""
Exact text search tool for the code agent.

Provides literal pattern matching using system tools (rg/grep/findstr).
"""

from typing import Optional, Callable, List

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
            "Exact-match text search. Use when you know the precise string "
            "(e.g., error code, variable name, function signature) and need "
            "every occurrence. Supports regex patterns."
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
```

### Step 5: Update SubprocessRunner Protocol

**File:** `src/agent_tools/protocols/__init__.py` (ADD method to existing protocol)

```python
class SubprocessRunnerProtocol(Protocol):
    """Contract for executing subprocesses."""

    def execute(
        self,
        command: str,
        cwd: str,
        timeout: Optional[float] = None,
        stream_output: bool = False,
    ) -> ExecutionResult:
        """Execute command string in subprocess."""
        ...

    def execute_list(
        self,
        command: List[str],
        cwd: str,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute command as list (no shell interpolation).

        Safer than execute() - no shell injection risk.
        """
        ...
```

### Step 6: Delete and Update Files

**DELETE:**
- `src/cli/research_handlers/code_search.py`

**DELETE TESTS:**
- `tests/cli/test_research_handlers.py` - `TestCodeSearchHandler` class (lines 159-268)
- `tests/task_router/intent/test_service.py` - tests using `CODE_SEARCH`
- `tests/task_router/intent/test_actions.py` - tests using `CODE_SEARCH`
- `tests/task_router/intent/test_classifier.py` - tests using `CODE_SEARCH`
- `tests/cli/test_prompt_builder.py` - tests using `CODE_SEARCH`

**MODIFY `src/task_router/protocols.py`:**
```python
class QueryIntent(Enum):
    """All possible intent classifications."""
    FILE_STRUCTURE = "file_structure"
    # CODE_SEARCH = "code_search"  # DELETED
    CODE_EXPLANATION = "code_explanation"
    # ... rest unchanged
```

**MODIFY `src/cli/research_handlers/registry.py`:**
```python
# Remove:
from .code_search import CodeSearchHandler
registry.register(CodeSearchHandler())
```

**MODIFY `src/task_router/intent/patterns.py`:**
```python
# Remove CODE_SEARCH patterns and entity mappings
# Delete lines referencing QueryIntent.CODE_SEARCH
```

**MODIFY `src/task_router/intent/actions.py`:**
```python
# Remove CODE_SEARCH branch from intent handling
# Delete: elif intent == QueryIntent.CODE_SEARCH:
```

**MODIFY `src/task_router/strategies/tool_bundle.py`:**
```python
# Replace SearchCodeTool with FindExactTextTool
from src.agent_tools.tools.search_tools import FindExactTextTool
# Update registration to use FindExactTextTool
```

**MODIFY `src/agent_tools/registry_factory.py`:**
```python
from .tools.search_tools import FindExactTextTool
# Change: registry.register(SearchCodeTool()) -> registry.register(FindExactTextTool())
```

**MODIFY `src/agent_tools/tools/registry.py`:**
```python
from .search_tools import FindExactTextTool
# In create_default(): registry.register(FindExactTextTool())
```

**MODIFY `src/agent_tools/tools/__init__.py`:**
```python
from .search_tools import FindExactTextTool
# Update __all__ to export FindExactTextTool instead of SearchCodeTool
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `src/agent_tools/protocols/__init__.py` | MODIFY | Add SearchMatch, SearchMetadata, SearchOutputParserProtocol, TextSearchProtocol, NoSearchToolError, execute_list to SubprocessRunnerProtocol |
| `src/agent_tools/components/search_output_parser.py` | NEW | Platform-aware search output parsing |
| `src/agent_tools/components/text_search.py` | NEW | rg/grep/findstr backends |
| `src/agent_tools/components/text_search_factory.py` | NEW | Factory for DI-compliant backend creation |
| `src/agent_tools/components/subprocess_runner.py` | MODIFY | Add execute_list method |
| `src/agent_tools/tools/search_tools.py` | REPLACE | Simplified FindExactTextTool |
| `src/agent_tools/tools/registry.py` | MODIFY | Register FindExactTextTool |
| `src/agent_tools/tools/__init__.py` | MODIFY | Export FindExactTextTool |
| `src/agent_tools/registry_factory.py` | MODIFY | Use FindExactTextTool |
| `src/task_router/protocols.py` | MODIFY | Remove CODE_SEARCH from QueryIntent |
| `src/task_router/intent/patterns.py` | MODIFY | Remove CODE_SEARCH patterns |
| `src/task_router/intent/actions.py` | MODIFY | Remove CODE_SEARCH handling |
| `src/task_router/strategies/tool_bundle.py` | MODIFY | Use FindExactTextTool |
| `src/cli/research_handlers/code_search.py` | DELETE | Redundant |
| `src/cli/research_handlers/registry.py` | MODIFY | Remove CodeSearchHandler |
| `tests/agent_tools/test_search_tools.py` | MODIFY | Update for FindExactTextTool |
| `tests/agent_tools/test_text_search.py` | NEW | Backend unit tests |
| `tests/agent_tools/test_search_output_parser.py` | NEW | Parser tests |
| `tests/cli/test_research_handlers.py` | MODIFY | Delete TestCodeSearchHandler |
| `tests/task_router/intent/test_*.py` | MODIFY | Remove CODE_SEARCH tests |
| `tests/cli/test_prompt_builder.py` | MODIFY | Remove CODE_SEARCH tests |

---

## Testing Strategy

### Search Output Parser Tests

```python
class TestSearchOutputParser:
    def test_parse_unix_path(self):
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("src/main.py:42:def hello():")

        assert result == ("src/main.py", 42, "def hello():", True)

    def test_parse_windows_path(self):
        mock_platform = Mock()
        mock_platform.is_windows.return_value = True

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("C:\\src\\main.py:42:def hello():")

        assert result == ("C:/src/main.py", 42, "def hello():", True)

    def test_parse_context_line(self):
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("src/main.py-43-    pass")

        assert result == ("src/main.py", 43, "    pass", False)

    def test_parse_separator_returns_none(self):
        mock_platform = Mock()
        mock_platform.is_windows.return_value = False

        parser = SearchOutputParser(mock_platform)
        result = parser.parse_line("--")

        assert result is None
```

### Backend Tests

```python
class TestRipgrepSearch:
    def test_search_returns_matches(self):
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="test.py:1:match\ntest.py:5:another",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = False
        mock_parser = Mock()
        mock_parser.parse_line.side_effect = [
            ("test.py", 1, "match", True),
            ("test.py", 5, "another", True),
        ]

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert len(matches) == 2
        assert metadata.error is None

    def test_search_error_populates_metadata(self):
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="", stderr="error message", exit_code=2, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_parser = Mock()

        search = RipgrepSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."))

        assert matches == []
        assert metadata.error is not None
        assert "exit code 2" in metadata.error


class TestFindstrSearch:
    def test_context_lines_warning(self):
        mock_runner = Mock()
        mock_runner.execute_list.return_value = ExecutionResult(
            stdout="test.py:1:match", stderr="", exit_code=0, execution_time=0.1
        )
        mock_platform = Mock()
        mock_platform.has_tool.return_value = True
        mock_platform.is_windows.return_value = True
        mock_parser = Mock()
        mock_parser.parse_line.return_value = ("test.py", 1, "match", True)

        search = FindstrSearch(mock_runner, mock_parser, mock_platform)
        matches, metadata = search.search(pattern="test", path=Path("."), context_lines=2)

        assert metadata.context_lines_supported is False
        assert metadata.warning is not None
```

### Tool Tests

```python
class TestFindExactTextTool:
    def test_uses_injected_backend(self, mock_context):
        mock_search = Mock()
        mock_search.search.return_value = (
            [SearchMatch("test.py", 10, "hello", True)],
            SearchMetadata()
        )
        mock_search.name = "mock"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert result.success
        assert "test.py:10" in result.output

    def test_no_tool_returns_error(self, mock_context):
        mock_factory = Mock()
        mock_factory.create_backend.side_effect = NoSearchToolError("No tool")

        tool = FindExactTextTool(backend_factory=mock_factory)
        result = tool.execute(mock_context, pattern="hello")

        assert not result.success
        assert "No tool" in result.error

    def test_search_error_returns_failure(self, mock_context):
        mock_search = Mock()
        mock_search.search.return_value = (
            [],
            SearchMetadata(error="grep failed", stderr="permission denied")
        )
        mock_search.name = "grep"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello")

        assert not result.success
        assert "grep failed" in result.error

    def test_findstr_warning_shown(self, mock_context):
        mock_search = Mock()
        mock_search.search.return_value = (
            [SearchMatch("test.py", 10, "hello", True)],
            SearchMetadata(warning="findstr does not support context lines", context_lines_supported=False)
        )
        mock_search.name = "findstr"

        tool = FindExactTextTool(text_search=mock_search)
        result = tool.execute(mock_context, pattern="hello", context_lines=2)

        assert result.success
        assert "[Warning:" in result.output
```

### Factory Tests

```python
class TestTextSearchFactory:
    def test_creates_ripgrep_when_available(self):
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "rg"

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend.name == "ripgrep"

    def test_falls_back_to_grep(self):
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "grep"

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend.name == "grep"

    def test_raises_when_no_tool_available(self):
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.return_value = False

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)

        with pytest.raises(NoSearchToolError):
            factory.create_backend()
```

---

## Acceptance Criteria

- [ ] Tool renamed to `find_exact_text`
- [ ] No `search_type` parameter (AST search removed)
- [ ] No backward compatibility alias
- [ ] Uses rg when available, falls back to grep -> findstr
- [ ] Clear error when no tool available
- [ ] Backend reported in metadata
- [ ] Windows paths parsed correctly (handles `C:\`)
- [ ] Commands executed as list (no shell injection risk)
- [ ] findstr warns when context_lines requested
- [ ] Search errors populate metadata, never silent empty `[]`
- [ ] `QueryIntent.CODE_SEARCH` deleted from enum
- [ ] `CodeSearchHandler` deleted
- [ ] All CODE_SEARCH tests deleted
- [ ] All call sites updated (no `SearchCodeTool` imports)
- [ ] `intent/patterns.py` cleaned of CODE_SEARCH entries
- [ ] `intent/actions.py` CODE_SEARCH branch removed
- [ ] `tool_bundle.py` uses FindExactTextTool
- [ ] All dependencies injected (PlatformDetectorProtocol, SubprocessRunnerProtocol)
- [ ] All tests use mocked dependencies
