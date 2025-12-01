"""Text search implementations using external tools."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from scrappy.platform.protocols.detection import PlatformDetectorProtocol

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
