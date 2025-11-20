"""
Tests for cache_manager.py - Cache operations split from session.py.

Tests verify behavior of cache management commands:
- Show cache statistics
- Clear cache
- Toggle caching on/off
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestCacheManagerShowStats:
    """Tests for showing cache statistics (no args)."""

    def test_show_cache_stats_displays_total_entries(self):
        """Should display total cache entries."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        output = io.get_output()
        assert "Cache Statistics:" in output
        assert "Total Entries:" in output

    def test_show_cache_stats_displays_hit_counts(self):
        """Should display exact and intent cache hit counts."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        output = io.get_output()
        assert "Exact Cache Hits:" in output
        assert "Intent Cache Hits:" in output

    def test_show_cache_stats_displays_miss_count(self):
        """Should display cache miss count."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        output = io.get_output()
        assert "Cache Misses:" in output

    def test_show_cache_stats_displays_hit_rates(self):
        """Should display hit rate percentages."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        output = io.get_output()
        assert "Hit Rate:" in output

    def test_show_cache_stats_displays_cache_file_location(self):
        """Should display cache file path."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        output = io.get_output()
        assert "Cache File:" in output

    def test_show_cache_stats_displays_caching_enabled_status(self):
        """Should display whether caching is enabled or disabled."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.caching_enabled = True
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        output = io.get_output()
        assert "Caching:" in output

    def test_show_cache_stats_colors_good_hit_rate_green(self):
        """Should style good hit rates (>50%) in green."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.get_cache_stats = lambda: {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 60,
            'intent_hits': 40,
            'exact_misses': 40,
            'saves': 15,
            'exact_hit_rate': '60.0%',
            'intent_hit_rate': '50.0%',
            'cache_file': '/test/.cache'
        }
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        styled = io.get_styled_outputs()
        # Find styled outputs with hit rates
        hit_rate_styles = [s for s in styled if '%' in s['text']]
        # At least one should be green (hit rate > 50%)
        green_styles = [s for s in hit_rate_styles if s['fg'] == 'green']
        assert len(green_styles) > 0

    def test_show_cache_stats_colors_poor_hit_rate_yellow(self):
        """Should style poor hit rates (<=50%) in yellow."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.get_cache_stats = lambda: {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 20,
            'intent_hits': 10,
            'exact_misses': 80,
            'saves': 15,
            'exact_hit_rate': '20.0%',
            'intent_hit_rate': '10.0%',
            'cache_file': '/test/.cache'
        }
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="", io=io)

        styled = io.get_styled_outputs()
        # Find styled outputs with hit rates
        hit_rate_styles = [s for s in styled if '%' in s['text']]
        # Should have yellow styles (hit rate <= 50%)
        yellow_styles = [s for s in hit_rate_styles if s['fg'] == 'yellow']
        assert len(yellow_styles) > 0


class TestCacheManagerClear:
    """Tests for clear cache command."""

    def test_clear_calls_orchestrator_clear_cache(self):
        """Should call orchestrator's clear_cache method."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        clear_called = []
        orchestrator.clear_cache = lambda: clear_called.append(True)

        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="clear", io=io)

        assert clear_called == [True]

    def test_clear_shows_confirmation_message(self):
        """Should display confirmation that cache was cleared."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="clear", io=io)

        output = io.get_output()
        assert "cleared" in output.lower()

    def test_clear_confirmation_is_styled_green(self):
        """Should style the confirmation message in green."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="clear", io=io)

        styled = io.get_styled_outputs()
        green_messages = [s for s in styled if s['fg'] == 'green']
        assert len(green_messages) > 0


class TestCacheManagerToggle:
    """Tests for toggle caching command."""

    def test_toggle_disables_caching_when_enabled(self):
        """Should disable caching when currently enabled."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.caching_enabled = True
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="toggle", io=io)

        assert orchestrator.caching_enabled is False
        output = io.get_output()
        assert "disabled" in output.lower()

    def test_toggle_enables_caching_when_disabled(self):
        """Should enable caching when currently disabled."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.caching_enabled = False
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="toggle", io=io)

        assert orchestrator.caching_enabled is True
        output = io.get_output()
        assert "enabled" in output.lower()

    def test_toggle_returns_new_state(self):
        """Should call toggle_cache and return new state."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        toggle_results = []
        original_toggle = orchestrator.toggle_cache
        orchestrator.toggle_cache = lambda: (
            toggle_results.append(original_toggle()),
            toggle_results[-1]
        )[1]

        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="toggle", io=io)

        assert len(toggle_results) == 1


class TestCacheManagerInvalidCommand:
    """Tests for invalid/unknown commands."""

    def test_invalid_command_shows_usage(self):
        """Should display usage information for unknown commands."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="invalid", io=io)

        output = io.get_output()
        assert "Usage:" in output
        assert "clear" in output
        assert "toggle" in output

    def test_usage_shows_command_descriptions(self):
        """Should show descriptions for each command in usage."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)
        io = MockIO()

        manager.manage_cache(args="help", io=io)

        output = io.get_output()
        # Should have descriptions
        assert "statistics" in output.lower() or "Show" in output


class TestCacheManagerCaseInsensitivity:
    """Tests for command case handling."""

    def test_commands_are_case_insensitive(self):
        """Commands should work regardless of case."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)

        for cmd in ["CLEAR", "Clear", "clear", "ClEaR"]:
            io = MockIO()
            manager.manage_cache(args=cmd, io=io)
            output = io.get_output()
            # Should not show usage
            assert "Usage:" not in output

    def test_toggle_is_case_insensitive(self):
        """Toggle command should work regardless of case."""
        from src.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        manager = CacheManager(orchestrator)

        for cmd in ["TOGGLE", "Toggle", "toggle"]:
            orchestrator.caching_enabled = True  # Reset state
            io = MockIO()
            manager.manage_cache(args=cmd, io=io)
            assert orchestrator.caching_enabled is False


class TestCacheManagerDefaultIO:
    """Tests for default IO behavior."""

