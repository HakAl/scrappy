"""
Tests for cache_manager.py - Cache operations split from session.py.

Tests verify behavior of cache management commands:
- Show cache statistics
- Clear cache
- Toggle caching on/off
"""


import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestCacheManagerShowStats:
    """Tests for showing cache statistics (no args).

    Note: The /cache command now uses io.table() for output, which displays
    data in a table format without ANSI color codes. This avoids the ANSI
    artifacts that occurred with the old format_stats() approach.
    """

    def test_show_cache_stats_displays_total_entries(self):
        """Should display total cache entries in table format."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        assert "Cache Statistics" in output
        assert "Total Entries" in output

    def test_show_cache_stats_displays_hit_counts(self):
        """Should display exact and intent cache hit counts in table format."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        assert "Exact Cache Hits" in output
        assert "Intent Cache Hits" in output

    def test_show_cache_stats_displays_miss_count(self):
        """Should display cache miss count in table format."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        assert "Cache Misses" in output

    def test_show_cache_stats_displays_hit_rates(self):
        """Should display hit rate percentages in table format."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        assert "Hit Rate" in output

    def test_show_cache_stats_displays_cache_file_location(self):
        """Should display cache file path in table format."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        assert "Cache File" in output

    def test_show_cache_stats_displays_caching_enabled_status(self):
        """Should display whether caching is enabled or disabled in table format."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.caching_enabled = True
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        assert "Status" in output
        assert "Enabled" in output

    def test_show_cache_stats_displays_hit_rate_values(self):
        """Should display hit rate values in table format (no ANSI codes)."""
        from scrappy.cli.cache_manager import CacheManager

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
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        # Verify hit rates are displayed without ANSI artifacts
        assert '60.0%' in output
        assert '50.0%' in output
        # Verify no raw ANSI codes are present (the fix for Issue 2.4)
        assert '\x1b[' not in output

    def test_show_cache_stats_no_ansi_artifacts(self):
        """Should not contain raw ANSI code artifacts in output."""
        from scrappy.cli.cache_manager import CacheManager

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
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="")

        output = io.get_all_output()
        # Verify data is displayed
        assert '20.0%' in output
        # This is the key fix - no ANSI codes should appear as literal text
        assert '\x1b[' not in output
        assert '[36m' not in output  # No raw cyan code
        assert '[0m' not in output   # No raw reset code


class TestCacheManagerClear:
    """Tests for clear cache command."""

    def test_clear_calls_orchestrator_clear_cache(self):
        """Should call orchestrator's clear_cache method."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        clear_called = []
        orchestrator.clear_cache = lambda: clear_called.append(True)

        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="clear")

        assert clear_called == [True]

    def test_clear_shows_confirmation_message(self):
        """Should display confirmation that cache was cleared."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="clear")

        output = io.get_all_output()
        assert "cleared" in output.lower()

    def test_clear_confirmation_is_styled_green(self):
        """Should style the confirmation message in green."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="clear")

        output = io.get_all_output()
        # Check that cleared message contains green ANSI code
        # ANSI green code is \x1b[32m
        assert 'cleared' in output
        assert '\x1b[32m' in output  # Contains green color code


class TestCacheManagerToggle:
    """Tests for toggle caching command."""

    def test_toggle_disables_caching_when_enabled(self):
        """Should disable caching when currently enabled."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.caching_enabled = True
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="toggle")

        assert orchestrator.caching_enabled is False
        output = io.get_all_output()
        assert "disabled" in output.lower()

    def test_toggle_enables_caching_when_disabled(self):
        """Should enable caching when currently disabled."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        orchestrator.caching_enabled = False
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="toggle")

        assert orchestrator.caching_enabled is True
        output = io.get_all_output()
        assert "enabled" in output.lower()

    def test_toggle_returns_new_state(self):
        """Should call toggle_cache and return new state."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        toggle_results = []
        original_toggle = orchestrator.toggle_cache
        orchestrator.toggle_cache = lambda: (
            toggle_results.append(original_toggle()),
            toggle_results[-1]
        )[1]

        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="toggle")

        assert len(toggle_results) == 1


class TestCacheManagerInvalidCommand:
    """Tests for invalid/unknown commands."""

    def test_invalid_command_shows_usage(self):
        """Should display usage information for unknown commands."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="invalid")

        output = io.get_all_output()
        assert "Usage:" in output
        assert "clear" in output
        assert "toggle" in output

    def test_usage_shows_command_descriptions(self):
        """Should show descriptions for each command in usage."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        manager.manage_cache(args="help")

        output = io.get_all_output()
        # Should have descriptions
        assert "statistics" in output.lower() or "Show" in output


class TestCacheManagerCaseInsensitivity:
    """Tests for command case handling."""

    def test_commands_are_case_insensitive(self):
        """Commands should work regardless of case."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        for cmd in ["CLEAR", "Clear", "clear", "ClEaR"]:
            manager.manage_cache(args=cmd)
            output = io.get_all_output()
            # Should not show usage
            assert "Usage:" not in output

    def test_toggle_is_case_insensitive(self):
        """Toggle command should work regardless of case."""
        from scrappy.cli.cache_manager import CacheManager

        orchestrator = ConfigurableTestOrchestrator()
        io = MockIO()
        manager = CacheManager(orchestrator, io)

        for cmd in ["TOGGLE", "Toggle", "toggle"]:
            orchestrator.caching_enabled = True  # Reset state
            manager.manage_cache(args=cmd)
            assert orchestrator.caching_enabled is False


class TestCacheManagerDefaultIO:
    """Tests for default IO behavior."""

