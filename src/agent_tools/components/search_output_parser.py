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
