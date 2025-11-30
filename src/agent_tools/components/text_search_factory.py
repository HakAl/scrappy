"""Factory for creating text search backends."""

from typing import Optional

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
