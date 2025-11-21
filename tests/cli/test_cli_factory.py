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