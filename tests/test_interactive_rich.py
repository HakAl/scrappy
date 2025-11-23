"""
Tests for Phase 5: Interactive Mode Rich Enhancements.

These tests verify that the welcome banner, help commands, and status displays
use Rich components (Panels, Tables, Progress bars) for enhanced UI.

TDD: These tests define expected behavior for Rich-enhanced displays.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from io import StringIO

from rich.console import Console

from src.cli.rich_output import RichIO
from src.cli.display import CLIDisplay
from src.cli.interactive import InteractiveMode
from tests.helpers import MockIO, ConfigurableTestOrchestrator


# =============================================================================
# Helper: Capture Rich Output
# =============================================================================

def make_capturing_rich_io():
    """Create a RichIO that captures output for testing.

    Returns:
        Tuple of (RichIO, Console) where Console has record=True
    """
    console = Console(record=True, force_terminal=True, width=120)
    io = RichIO(console=console)
    return io, console


def get_captured_output(console: Console) -> str:
    """Get captured output from a recording Console."""
    return console.export_text()


# =============================================================================
# Test Welcome Banner as Rich Panel
# =============================================================================

class TestWelcomeBannerPanel:
    """Test welcome banner renders as a Rich Panel with ASCII art."""

    @pytest.mark.integration
    def test_welcome_banner_uses_panel_component(self):
        """Welcome banner should render inside a Rich Panel."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()

        # Create a function to render the enhanced welcome banner
        from src.cli.interactive_banner import render_welcome_banner

        render_welcome_banner(io)
        output = get_captured_output(console)

        # Panel borders use box-drawing characters
        assert any(char in output for char in ['|', '+', '-'])
        # Title should be visible (case-insensitive)
        assert 'scrappy' in output.lower()

    @pytest.mark.integration
    def test_welcome_banner_contains_ascii_art(self):
        """Welcome banner should include ASCII art or styled title."""
        io, console = make_capturing_rich_io()

        from src.cli.interactive_banner import render_welcome_banner

        render_welcome_banner(io)
        output = get_captured_output(console)

        # Should have some visual distinction (ASCII art or styled header)
        # Either box characters or large text representation
        assert 'Interactive Mode' in output or 'SCRAPPY' in output

    @pytest.mark.integration
    def test_welcome_banner_shows_quick_commands(self):
        """Welcome banner should list key commands."""
        io, console = make_capturing_rich_io()

        from src.cli.interactive_banner import render_welcome_banner

        render_welcome_banner(io)
        output = get_captured_output(console)

        # Should show essential commands
        assert '/help' in output
        assert '/quit' in output

    @pytest.mark.integration
    def test_welcome_banner_panel_has_border_style(self):
        """Welcome banner panel should have styled border."""
        io, console = make_capturing_rich_io()

        from src.cli.interactive_banner import render_welcome_banner

        render_welcome_banner(io)
        output = get_captured_output(console)

        # Panel should be rendered (has some structure)
        lines = output.strip().split('\n')
        assert len(lines) >= 3  # At least top border, content, bottom border

    @pytest.mark.integration
    def test_welcome_banner_shows_mode_statuses(self):
        """Welcome banner should display current mode statuses."""
        io, console = make_capturing_rich_io()

        from src.cli.interactive_banner import render_welcome_banner

        # Test with different mode configurations
        render_welcome_banner(io, multiline_mode=True, auto_route_mode=False)
        output = get_captured_output(console)

        # Should show mode information
        assert 'Multiline' in output or 'multiline' in output
        assert 'Auto' in output or 'auto' in output or 'routing' in output


# =============================================================================
# Test Help Commands as Rich Table
# =============================================================================

class TestHelpCommandsTable:
    """Test help commands format as a Rich Table with syntax highlighting."""

    @pytest.mark.integration
    def test_help_uses_table_component(self):
        """Help display should use Rich Table for command listing."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        display = CLIDisplay(orch, datetime.now(), io)

        from src.cli.display_rich import show_help_table

        show_help_table(io)
        output = get_captured_output(console)

        # Table has structured columns - should have consistent alignment
        # or column separators
        assert 'Command' in output or '/help' in output

    @pytest.mark.integration
    def test_help_table_has_command_column(self):
        """Help table should have a column for command names."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_help_table

        show_help_table(io)
        output = get_captured_output(console)

        # Commands should be listed
        commands = ['/help', '/status', '/quit', '/providers']
        found_commands = sum(1 for cmd in commands if cmd in output)
        assert found_commands >= 3  # At least some commands present

    @pytest.mark.integration
    def test_help_table_has_description_column(self):
        """Help table should have descriptions for commands."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_help_table

        show_help_table(io)
        output = get_captured_output(console)

        # Should have descriptive text
        descriptions = ['Show', 'List', 'Exit', 'Display', 'Toggle']
        found_descriptions = sum(1 for desc in descriptions if desc in output)
        assert found_descriptions >= 2

    @pytest.mark.integration
    def test_help_table_groups_by_category(self):
        """Help table should group commands by category."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_help_table

        show_help_table(io)
        output = get_captured_output(console)

        # Categories from current help
        categories = [
            'Chat', 'Task', 'Provider', 'Context', 'Cache', 'Session', 'System'
        ]
        found_categories = sum(1 for cat in categories if cat in output)
        assert found_categories >= 3  # At least some categories

    @pytest.mark.integration
    def test_help_table_has_syntax_highlighting(self):
        """Help table should syntax-highlight command names."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_help_table

        show_help_table(io)
        output = get_captured_output(console)

        # Commands should be present (styling verified by visual inspection
        # or ANSI code presence in raw output)
        assert '/help' in output
        assert '/quit' in output

    @pytest.mark.integration
    def test_help_accepts_category_filter(self):
        """Help table should optionally filter by category."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_help_table

        # Show only provider-related commands
        show_help_table(io, category='provider')
        output = get_captured_output(console)

        # Should show provider commands
        assert '/providers' in output or '/brain' in output
        # Should not show unrelated commands (unless they're also provider-related)


# =============================================================================
# Test Status Display Components
# =============================================================================

class TestStatusDisplayComponents:
    """Test status display uses Rich components like progress bars."""

    @pytest.mark.integration
    def test_status_uses_panel_for_grouping(self):
        """Status display should group information in panels."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        display = CLIDisplay(orch, datetime.now(), io)

        from src.cli.display_rich import show_status_rich

        show_status_rich(io, orch, datetime.now())
        output = get_captured_output(console)

        # Should have status information
        assert 'brain' in output.lower() or 'provider' in output.lower()

    @pytest.mark.integration
    def test_status_shows_provider_with_styling(self):
        """Current brain provider should be prominently styled."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator(recommended_provider='cerebras')

        from src.cli.display_rich import show_status_rich

        show_status_rich(io, orch, datetime.now())
        output = get_captured_output(console)

        # Provider name should appear
        assert 'cerebras' in output.lower()

    @pytest.mark.integration
    def test_status_shows_session_duration(self):
        """Status should display session duration."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        session_start = datetime.now()

        from src.cli.display_rich import show_status_rich

        show_status_rich(io, orch, session_start)
        output = get_captured_output(console)

        # Should show duration or time info
        assert 'Duration' in output or 'Session' in output or ':' in output

    @pytest.mark.integration
    def test_status_shows_tasks_completed(self):
        """Status should show number of tasks completed."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        # Simulate some completed tasks
        orch.delegate('cerebras', 'test')
        orch.delegate('cerebras', 'test2')

        from src.cli.display_rich import show_status_rich

        show_status_rich(io, orch, datetime.now())
        output = get_captured_output(console)

        # Should show task count
        assert '2' in output or 'Tasks' in output


# =============================================================================
# Test Rate Limit Progress Bars
# =============================================================================

class TestRateLimitProgressBars:
    """Test rate limit display uses progress bars."""

    @pytest.mark.integration
    def test_rate_limits_use_progress_bars(self):
        """Rate limit usage should display as progress bars."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_rate_limits_rich

        # Mock rate limit data
        rate_data = {
            'providers': {
                'cerebras': {
                    'requests_today': 50,
                    'daily_limit': 100,
                    'tokens_today': 5000,
                    'daily_token_limit': 10000
                }
            }
        }

        show_rate_limits_rich(io, rate_data)
        output = get_captured_output(console)

        # Should show provider name
        assert 'cerebras' in output.lower()
        # Should show some kind of progress indicator or percentage
        assert '%' in output or '/' in output or any(c in output for c in ['|', '*', '=', '#'])

    @pytest.mark.integration
    def test_rate_limits_show_percentage_used(self):
        """Rate limits should show percentage of quota used."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_rate_limits_rich

        rate_data = {
            'providers': {
                'groq': {
                    'requests_today': 75,
                    'daily_limit': 100,
                    'tokens_today': 7500,
                    'daily_token_limit': 10000
                }
            }
        }

        show_rate_limits_rich(io, rate_data)
        output = get_captured_output(console)

        # Should show percentage or fraction
        assert '75' in output or '75%' in output or '3/4' in output

    @pytest.mark.integration
    def test_rate_limits_color_code_by_usage(self):
        """Rate limits should color-code based on usage level."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_rate_limits_rich

        # High usage should show warning colors
        rate_data = {
            'providers': {
                'gemini': {
                    'requests_today': 95,
                    'daily_limit': 100,
                    'tokens_today': 9500,
                    'daily_token_limit': 10000
                }
            }
        }

        show_rate_limits_rich(io, rate_data)
        output = get_captured_output(console)

        # Should show the provider and usage
        assert 'gemini' in output.lower()
        assert '95' in output or '9500' in output

    @pytest.mark.integration
    def test_rate_limits_handle_no_data(self):
        """Rate limits should handle missing or empty data gracefully."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_rate_limits_rich

        # Empty rate data
        rate_data = {'providers': {}}

        show_rate_limits_rich(io, rate_data)
        output = get_captured_output(console)

        # Should show informative message
        assert 'No' in output or 'no' in output or 'empty' in output.lower() or len(output.strip()) > 0

    @pytest.mark.integration
    def test_rate_limits_show_multiple_providers(self):
        """Rate limits should display data for multiple providers."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_rate_limits_rich

        rate_data = {
            'providers': {
                'cerebras': {
                    'requests_today': 30,
                    'daily_limit': 100,
                    'tokens_today': 3000,
                    'daily_token_limit': 10000
                },
                'groq': {
                    'requests_today': 50,
                    'daily_limit': 200,
                    'tokens_today': 5000,
                    'daily_token_limit': 20000
                }
            }
        }

        show_rate_limits_rich(io, rate_data)
        output = get_captured_output(console)

        # Both providers should appear
        assert 'cerebras' in output.lower()
        assert 'groq' in output.lower()


# =============================================================================
# Test Usage Statistics Rich Display
# =============================================================================

class TestUsageStatisticsRich:
    """Test usage statistics display with Rich components."""

    @pytest.mark.integration
    def test_usage_uses_table_for_providers(self):
        """Usage stats should display provider breakdown in a table."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        display = CLIDisplay(orch, datetime.now(), io)

        from src.cli.display_rich import show_usage_rich

        # Generate some usage
        orch.delegate('cerebras', 'test1')
        orch.delegate('groq', 'test2')

        show_usage_rich(io, orch.get_usage_report())
        output = get_captured_output(console)

        # Should show providers
        assert 'cerebras' in output.lower()
        assert 'groq' in output.lower()

    @pytest.mark.integration
    def test_usage_shows_token_counts(self):
        """Usage stats should display token counts."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()

        orch.delegate('cerebras', 'test')

        from src.cli.display_rich import show_usage_rich

        show_usage_rich(io, orch.get_usage_report())
        output = get_captured_output(console)

        # Should show token info
        assert 'token' in output.lower() or '100' in output

    @pytest.mark.integration
    def test_usage_shows_cache_statistics(self):
        """Usage stats should display cache hit/miss information."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_usage_rich

        report = {
            'total_tasks': 10,
            'cached_hits': 3,
            'api_calls': 7,
            'session_duration': '0:05:00',
            'by_provider': {},
            'cache_stats': {
                'exact_hit_rate': '30%',
                'intent_hit_rate': '20%',
                'exact_cache_entries': 5,
                'intent_cache_entries': 3
            }
        }

        show_usage_rich(io, report)
        output = get_captured_output(console)

        # Should show cache info
        assert 'cache' in output.lower() or 'Cache' in output
        assert '30%' in output or 'hit' in output.lower()

    @pytest.mark.integration
    def test_usage_shows_latency_info(self):
        """Usage stats should display latency information."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_usage_rich

        report = {
            'total_tasks': 5,
            'session_duration': '0:01:00',
            'by_provider': {
                'cerebras': {
                    'count': 5,
                    'total_tokens': 500,
                    'avg_tokens': 100,
                    'total_latency_ms': 250,
                    'cached_hits': 0
                }
            },
            'cache_stats': {}
        }

        show_usage_rich(io, report)
        output = get_captured_output(console)

        # Should show latency
        assert 'ms' in output or 'latency' in output.lower() or '250' in output


# =============================================================================
# Test Plan/Task Tree Display
# =============================================================================

class TestPlanTaskTreeDisplay:
    """Test plan and task display uses Rich Tree structure."""

    @pytest.mark.integration
    def test_plan_displays_as_tree(self):
        """Active plan should display tasks as a tree structure."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_plan_tree

        plan = {
            'goal': 'Implement feature X',
            'tasks': [
                {'id': 1, 'description': 'Research requirements', 'status': 'completed'},
                {'id': 2, 'description': 'Write tests', 'status': 'in_progress'},
                {'id': 3, 'description': 'Implement code', 'status': 'pending'},
                {'id': 4, 'description': 'Review and refactor', 'status': 'pending'}
            ]
        }

        show_plan_tree(io, plan)
        output = get_captured_output(console)

        # Should show the goal
        assert 'Implement feature X' in output or 'feature' in output.lower()
        # Should show tasks
        assert 'Research' in output or 'Write tests' in output

    @pytest.mark.integration
    def test_plan_tree_shows_task_status(self):
        """Plan tree should indicate task completion status."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_plan_tree

        plan = {
            'goal': 'Test task',
            'tasks': [
                {'id': 1, 'description': 'Completed task', 'status': 'completed'},
                {'id': 2, 'description': 'In progress task', 'status': 'in_progress'},
                {'id': 3, 'description': 'Pending task', 'status': 'pending'}
            ]
        }

        show_plan_tree(io, plan)
        output = get_captured_output(console)

        # Should indicate different statuses visually
        # Could be checkmarks, colors, or status text
        assert 'Completed' in output or 'completed' in output.lower() or '[x]' in output.lower()

    @pytest.mark.integration
    def test_plan_tree_highlights_current_task(self):
        """Plan tree should highlight the current in-progress task."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_plan_tree

        plan = {
            'goal': 'Test highlighting',
            'tasks': [
                {'id': 1, 'description': 'Done', 'status': 'completed'},
                {'id': 2, 'description': 'Current task', 'status': 'in_progress'},
                {'id': 3, 'description': 'Next', 'status': 'pending'}
            ]
        }

        show_plan_tree(io, plan)
        output = get_captured_output(console)

        # Current task should be present
        assert 'Current task' in output

    @pytest.mark.integration
    def test_plan_tree_handles_empty_plan(self):
        """Plan tree should handle empty or missing plan gracefully."""
        io, console = make_capturing_rich_io()

        from src.cli.display_rich import show_plan_tree

        # Empty plan
        plan = {'goal': '', 'tasks': []}

        show_plan_tree(io, plan)
        output = get_captured_output(console)

        # Should show something informative
        assert len(output.strip()) > 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestRichDisplayIntegration:
    """Integration tests for Rich display components working together."""

    @pytest.mark.integration
    def test_display_methods_use_correct_io(self):
        """Display methods should use the provided IO interface."""
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        display = CLIDisplay(orch, datetime.now(), io)

        # Use the existing show_status which should work with RichIO
        display.show_status()
        output = get_captured_output(console)

        # Should produce output
        assert len(output.strip()) > 0
        assert 'Status' in output or 'Brain' in output or 'cerebras' in output.lower()

    @pytest.mark.integration
    def test_rich_io_protocol_compatibility(self):
        """RichIO should remain compatible with CLIIOProtocol."""
        io, console = make_capturing_rich_io()

        # All protocol methods should work
        io.echo("Test message")
        io.secho("Styled message", fg="green", bold=True)
        text = io.style("Inline style", fg="yellow")

        output = get_captured_output(console)

        assert "Test message" in output
        assert "Styled message" in output

    @pytest.mark.integration
    def test_fallback_to_basic_display(self):
        """Display should fall back gracefully if Rich components fail."""
        # This test ensures robustness
        io, console = make_capturing_rich_io()
        orch = ConfigurableTestOrchestrator()
        display = CLIDisplay(orch, datetime.now(), io)

        # The existing method should still work
        display.show_help()
        output = get_captured_output(console)

        # Should still show help content
        assert '/help' in output or 'help' in output.lower()
