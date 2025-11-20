"""
Tests for CLI factory utilities.

Tests the shared factory functions that eliminate duplication
in CLI instance creation across commands.py and other modules.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from tests.helpers import MockIO, ConfigurableTestOrchestrator


class TestCreateCLIFromContext:
    """Test create_cli_from_context factory function."""

    def test_creates_cli_with_all_context_values(self):
        """Should create CLI instance with all values from context."""
        from src.cli.utils.cli_factory import create_cli_from_context

        # Create mock Click context with all values
        ctx = Mock()
        ctx.obj = {
            'brain': 'cerebras',
            'auto_explore': True,
            'context_aware': False,
            'verbose_selection': True,
            'show_providers': True
        }

        io = MockIO()
        cli = create_cli_from_context(ctx, io=io)

        # Verify CLI was created with correct brain
        assert cli.orchestrator.brain == 'cerebras'
        # Verify CLI has all required components
        assert cli.orchestrator is not None
        assert cli.io is io
        assert hasattr(cli, 'display')
        assert hasattr(cli, 'session_mgr')

    def test_uses_default_values_when_not_in_context(self):
        """Should use default values when context doesn't have them."""
        from src.cli.utils.cli_factory import create_cli_from_context

        ctx = Mock()
        ctx.obj = {}  # Empty context

        io = MockIO()
        cli = create_cli_from_context(ctx, io=io)

        # Verify defaults were applied - CLI was created successfully
        # Note: brain may be None if no providers are available (e.g., in CI)
        # but the orchestrator should still be created
        assert cli.orchestrator is not None
        assert cli.io is io
        assert hasattr(cli, 'display')
        assert hasattr(cli, 'session_mgr')

    def test_uses_provided_io_interface(self):
        """Should use the provided IO interface."""
        from src.cli.utils.cli_factory import create_cli_from_context

        ctx = Mock()
        ctx.obj = {'brain': 'groq'}

        io = MockIO()
        cli = create_cli_from_context(ctx, io=io)

        assert cli.io is io


    def test_handles_none_obj_in_context(self):
        """Should handle when ctx.obj is None."""
        from src.cli.utils.cli_factory import create_cli_from_context

        ctx = Mock()
        ctx.obj = None

        io = MockIO()
        cli = create_cli_from_context(ctx, io=io)

        # Should still create CLI with defaults
        assert cli.orchestrator is not None
        assert cli.orchestrator.context_aware is True



class TestInitializeCLIHandlers:
    """Test initialize_cli_handlers factory function."""

    def test_creates_all_eight_handlers(self):
        """Should create all 8 standard CLI handlers."""
        from src.cli.utils.cli_factory import initialize_cli_handlers

        orchestrator = ConfigurableTestOrchestrator()
        session_start = datetime.now()

        handlers = initialize_cli_handlers(orchestrator, session_start)

        # Verify all 8 handlers are created
        assert 'display' in handlers
        assert 'session_mgr' in handlers
        assert 'codebase' in handlers
        assert 'tasks' in handlers
        assert 'multiprovider' in handlers
        assert 'smart' in handlers
        assert 'agent_mgr' in handlers
        assert 'task_router' in handlers
        assert len(handlers) == 8


    def test_display_handler_receives_session_start(self):
        """Should pass session_start to CLIDisplay handler."""
        from src.cli.utils.cli_factory import initialize_cli_handlers

        orchestrator = ConfigurableTestOrchestrator()
        session_start = datetime(2024, 1, 15, 10, 30, 0)

        handlers = initialize_cli_handlers(orchestrator, session_start)

        assert handlers['display'].session_start == session_start

    def test_all_handlers_receive_orchestrator(self):
        """Should pass orchestrator to all handlers."""
        from src.cli.utils.cli_factory import initialize_cli_handlers

        orchestrator = ConfigurableTestOrchestrator()
        session_start = datetime.now()

        handlers = initialize_cli_handlers(orchestrator, session_start)

        # Each handler should have access to orchestrator
        assert handlers['display'].orchestrator is orchestrator
        assert handlers['session_mgr'].orchestrator is orchestrator
        assert handlers['codebase'].orchestrator is orchestrator
        assert handlers['tasks'].orchestrator is orchestrator
        assert handlers['multiprovider'].orchestrator is orchestrator
        assert handlers['smart'].orchestrator is orchestrator
        assert handlers['agent_mgr'].orchestrator is orchestrator
        assert handlers['task_router'].orchestrator is orchestrator


    def test_handlers_are_independent_instances(self):
        """Each call should create new handler instances."""
        from src.cli.utils.cli_factory import initialize_cli_handlers

        orchestrator = ConfigurableTestOrchestrator()
        session_start = datetime.now()

        handlers1 = initialize_cli_handlers(orchestrator, session_start)
        handlers2 = initialize_cli_handlers(orchestrator, session_start)

        # Each call should create new instances
        assert handlers1['display'] is not handlers2['display']
        assert handlers1['session_mgr'] is not handlers2['session_mgr']


class TestGetIOInterface:
    """Test get_io_interface factory function."""

    def test_returns_provided_io(self):
        """Should return the provided IO interface unchanged."""
        from src.cli.utils.cli_factory import get_io_interface

        io = MockIO()
        result = get_io_interface(io=io)

        assert result is io



    def test_provided_io_takes_precedence_over_test_mode(self):
        """Provided IO should be used even if test_mode is True."""
        from src.cli.utils.cli_factory import get_io_interface

        io = MockIO()
        result = get_io_interface(io=io, test_mode=True)

        # Provided IO should win
        assert result is io



class TestCreateContextState:
    """Test create_context_state utility function."""

    def test_extracts_all_context_values(self):
        """Should extract all standard context values."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = {
            'brain': 'cerebras',
            'auto_explore': True,
            'context_aware': False,
            'resume': True,
            'auto_save': False,
            'show_providers': True,
            'verbose_selection': True
        }

        state = create_context_state(ctx)

        assert state['brain'] == 'cerebras'
        assert state['auto_explore'] is True
        assert state['context_aware'] is False
        assert state['resume'] is True
        assert state['auto_save'] is False
        assert state['show_providers'] is True
        assert state['verbose_selection'] is True

    def test_uses_defaults_for_missing_values(self):
        """Should use sensible defaults for missing context values."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = {}  # Empty context

        state = create_context_state(ctx)

        # Verify all keys exist with defaults
        assert 'brain' in state
        assert state['auto_explore'] is False
        assert state['context_aware'] is True
        assert state['resume'] is False
        assert state['auto_save'] is True
        assert state['show_providers'] is False
        assert state['verbose_selection'] is False

    def test_handles_none_obj(self):
        """Should handle when ctx.obj is None."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = None

        state = create_context_state(ctx)

        # Should return dict with defaults
        assert isinstance(state, dict)
        assert state['context_aware'] is True

    def test_returns_independent_dict(self):
        """Should return a new dict, not a reference to ctx.obj."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = {'brain': 'groq'}

        state = create_context_state(ctx)

        # Modifying state should not affect original
        state['brain'] = 'gemini'
        assert ctx.obj['brain'] == 'groq'

    def test_preserves_brain_value_including_none(self):
        """Should preserve None brain value (uses orchestrator default)."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = {'brain': None}

        state = create_context_state(ctx)

        assert state['brain'] is None

    def test_returns_all_seven_standard_keys(self):
        """Should always return all 7 standard configuration keys."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = {}

        state = create_context_state(ctx)

        expected_keys = {
            'brain', 'auto_explore', 'context_aware',
            'resume', 'auto_save', 'show_providers', 'verbose_selection'
        }
        assert set(state.keys()) == expected_keys


class TestExtractContextOptions:
    """Test extract_context_options for CLI command parameter extraction."""

    def test_extracts_cli_creation_options(self):
        """Should extract only the options needed for CLI creation."""
        from src.cli.utils.cli_factory import extract_context_options

        ctx = Mock()
        ctx.obj = {
            'brain': 'groq',
            'auto_explore': True,
            'context_aware': True,
            'verbose_selection': False,
            'show_providers': True,
            'resume': True,  # Not needed for CLI creation
            'auto_save': False  # Not needed for CLI creation
        }

        options = extract_context_options(ctx)

        # Should only have CLI creation options
        assert options['brain'] == 'groq'
        assert options['auto_explore'] is True
        assert options['context_aware'] is True
        assert options['verbose_selection'] is False
        assert options['show_provider_status'] is True  # Renamed from show_providers

        # Should not have non-CLI options
        assert 'resume' not in options
        assert 'auto_save' not in options
        assert 'show_providers' not in options  # Renamed to show_provider_status

    def test_maps_show_providers_to_show_provider_status(self):
        """Should map show_providers to show_provider_status parameter name."""
        from src.cli.utils.cli_factory import extract_context_options

        ctx = Mock()
        ctx.obj = {'show_providers': True}

        options = extract_context_options(ctx)

        # Should use CLI constructor parameter name
        assert options['show_provider_status'] is True
        assert 'show_providers' not in options

    def test_defaults_match_cli_constructor(self):
        """Defaults should match CLI constructor defaults."""
        from src.cli.utils.cli_factory import extract_context_options

        ctx = Mock()
        ctx.obj = {}

        options = extract_context_options(ctx)

        # Defaults should match CLI.__init__ defaults
        assert options.get('brain') is None
        assert options['auto_explore'] is False
        assert options['context_aware'] is True
        assert options['verbose_selection'] is False
        assert options['show_provider_status'] is False


class TestCLIFactoryIntegration:
    """Integration tests for CLI factory utilities."""


    def test_handlers_initialized_by_factory_work_correctly(self):
        """Handlers created by factory should work the same as manual creation."""
        from src.cli.utils.cli_factory import initialize_cli_handlers

        orchestrator = ConfigurableTestOrchestrator(
            available_providers=['cerebras', 'groq', 'gemini']
        )
        session_start = datetime.now()

        handlers = initialize_cli_handlers(orchestrator, session_start)

        # Display handler should be able to format session duration
        display = handlers['display']
        assert display.session_start == session_start

        # Session manager should have orchestrator reference
        session_mgr = handlers['session_mgr']
        assert session_mgr.orchestrator is orchestrator

    def test_full_context_to_cli_workflow(self):
        """Test complete workflow from Click context to working CLI."""
        from src.cli.utils.cli_factory import (
            create_context_state,
            extract_context_options,
            get_io_interface
        )

        # Simulate Click command receiving options
        ctx = Mock()
        ctx.obj = {
            'brain': 'cerebras',
            'auto_explore': True,
            'context_aware': True,
            'verbose_selection': False,
            'show_providers': False,
            'resume': True,
            'auto_save': True
        }

        # Extract state for logging/persistence
        state = create_context_state(ctx)
        assert state['brain'] == 'cerebras'
        assert state['resume'] is True

        # Extract options for CLI creation
        options = extract_context_options(ctx)
        assert 'resume' not in options  # Not a CLI parameter
        assert options['auto_explore'] is True

        # Get IO interface
        io = get_io_interface(test_mode=True)
        assert hasattr(io, 'echo')

    def test_factory_enables_consistent_cli_across_commands(self):
        """Multiple commands should create consistent CLIs via factory."""
        from src.cli.utils.cli_factory import extract_context_options

        # Same context for different commands
        ctx = Mock()
        ctx.obj = {
            'brain': 'groq',
            'auto_explore': True,
            'context_aware': True,
            'verbose_selection': True,
            'show_providers': False
        }

        # Extract options multiple times
        options1 = extract_context_options(ctx)
        options2 = extract_context_options(ctx)

        # Should be equal but independent
        assert options1 == options2
        assert options1 is not options2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_extra_keys_in_context(self):
        """Should ignore extra keys in context that aren't standard."""
        from src.cli.utils.cli_factory import create_context_state

        ctx = Mock()
        ctx.obj = {
            'brain': 'groq',
            'custom_key': 'custom_value',
            'another_extra': 123
        }

        state = create_context_state(ctx)

        # Should not include extra keys
        assert 'custom_key' not in state
        assert 'another_extra' not in state


    def test_initialize_handlers_with_minimal_orchestrator(self):
        """Should work with orchestrator having minimal required interface."""
        from src.cli.utils.cli_factory import initialize_cli_handlers

        # Create minimal mock orchestrator
        orchestrator = Mock()
        orchestrator.context = Mock()
        orchestrator.context.project_path = Mock()
        orchestrator.session_manager = Mock()
        session_start = datetime.now()

        # Should not raise
        handlers = initialize_cli_handlers(orchestrator, session_start)
        assert len(handlers) == 8
