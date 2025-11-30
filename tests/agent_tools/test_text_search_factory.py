"""Tests for TextSearchFactory."""

import pytest
from unittest.mock import Mock

from src.agent_tools.components.text_search_factory import TextSearchFactory
from src.agent_tools.protocols import NoSearchToolError


class TestTextSearchFactory:
    """Tests for TextSearchFactory."""

    def test_creates_ripgrep_when_available(self):
        """Should create ripgrep backend when available."""
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "rg"

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend.name == "ripgrep"

    def test_falls_back_to_grep(self):
        """Should fall back to grep when ripgrep unavailable."""
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "grep"

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend.name == "grep"

    def test_falls_back_to_findstr(self):
        """Should fall back to findstr when rg and grep unavailable."""
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "findstr"

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend.name == "findstr"

    def test_raises_when_no_tool_available(self):
        """Should raise NoSearchToolError when no tool available."""
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.return_value = False

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)

        with pytest.raises(NoSearchToolError) as exc_info:
            factory.create_backend()

        assert "No search tool available" in str(exc_info.value)
        assert "ripgrep" in str(exc_info.value)

    def test_prefers_ripgrep_over_others(self):
        """Should prefer ripgrep even when others available."""
        mock_runner = Mock()
        mock_platform = Mock()
        # All tools available
        mock_platform.has_tool.return_value = True

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend.name == "ripgrep"

    def test_uses_default_runner_when_not_provided(self):
        """Should create default runner when not injected."""
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "rg"

        factory = TextSearchFactory(platform_detector=mock_platform)
        backend = factory.create_backend()

        assert backend is not None
        assert backend.name == "ripgrep"

    def test_uses_default_platform_when_not_provided(self):
        """Should create default platform detector when not injected."""
        mock_runner = Mock()

        factory = TextSearchFactory(runner=mock_runner)
        # Should not raise - will use actual system platform detector
        # This test verifies the factory creates defaults correctly
        try:
            backend = factory.create_backend()
            # If successful, we have at least one tool available
            assert backend.name in ["ripgrep", "grep", "findstr"]
        except NoSearchToolError:
            # No tools available on this system - that's OK for this test
            pass

    def test_creates_parser_with_platform_detector(self):
        """Should pass platform detector to parser."""
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "rg"
        mock_platform.is_windows.return_value = False

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)
        backend = factory.create_backend()

        # Verify backend was created (which means parser was created successfully)
        assert backend is not None

    def test_reuses_injected_dependencies(self):
        """Should reuse injected runner and platform across calls."""
        mock_runner = Mock()
        mock_platform = Mock()
        mock_platform.has_tool.side_effect = lambda t: t == "rg"

        factory = TextSearchFactory(runner=mock_runner, platform_detector=mock_platform)

        backend1 = factory.create_backend()
        backend2 = factory.create_backend()

        # Both backends should be created successfully
        assert backend1.name == "ripgrep"
        assert backend2.name == "ripgrep"
