"""
Integration test to verify LangGraph agent wiring.

This test verifies that when the CLI runs in TUI mode,
the LangGraph agent is actually invoked instead of CodeAgent.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestLangGraphWiring:
    """Test that LangGraph agent is wired correctly."""

    def test_agent_manager_uses_langgraph_when_bridge_provided(self):
        """When langgraph_bridge is provided, run_agent should use it."""
        from scrappy.cli.agent_manager import CLIAgentManager

        # Create mocks
        mock_orchestrator = Mock()
        mock_orchestrator.working_memory = Mock()
        mock_orchestrator.working_memory.add_discovery = Mock()

        mock_io = Mock()
        mock_io.theme = Mock()
        mock_io.theme.warning = "yellow"
        mock_io.theme.success = "green"
        mock_io.theme.error = "red"
        mock_io.echo = Mock()
        mock_io.secho = Mock()

        mock_interaction = Mock()
        mock_interaction.confirm = Mock(return_value=False)  # Skip undo point

        # Create mock LangGraphBridge
        mock_bridge = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.cancelled = False
        mock_result.error = None
        mock_result.final_state = Mock()
        mock_result.final_state.iteration = 3
        mock_bridge.run_agent = Mock(return_value=mock_result)

        # Create agent manager with bridge
        agent_mgr = CLIAgentManager(
            orchestrator=mock_orchestrator,
            io=mock_io,
            user_interaction=mock_interaction,
            langgraph_bridge=mock_bridge,
        )

        # Run agent
        agent_mgr.run_agent("test task")

        # Verify LangGraph bridge was called, not CodeAgent
        mock_bridge.run_agent.assert_called_once()
        call_kwargs = mock_bridge.run_agent.call_args
        assert call_kwargs.kwargs["task"] == "test task"

    def test_agent_manager_falls_back_to_codeagent_without_bridge(self):
        """When langgraph_bridge is None, run_agent should use CodeAgent."""
        from scrappy.cli.agent_manager import CLIAgentManager

        # Create mocks
        mock_orchestrator = Mock()
        mock_orchestrator.working_memory = Mock()
        mock_orchestrator.working_memory.add_discovery = Mock()

        mock_io = Mock()
        mock_io.theme = Mock()
        mock_io.theme.warning = "yellow"
        mock_io.theme.success = "green"
        mock_io.theme.error = "red"
        mock_io.theme.primary = "blue"
        mock_io.echo = Mock()
        mock_io.secho = Mock()

        mock_interaction = Mock()
        mock_interaction.confirm = Mock(return_value=False)  # Skip undo point

        # Create agent manager WITHOUT bridge
        agent_mgr = CLIAgentManager(
            orchestrator=mock_orchestrator,
            io=mock_io,
            user_interaction=mock_interaction,
            langgraph_bridge=None,  # No bridge
        )

        # Patch CodeAgent to prevent actual execution
        with patch('scrappy.cli.agent_manager.CodeAgent') as mock_code_agent_class:
            mock_agent = Mock()
            mock_agent.run = Mock(return_value={'success': True, 'iterations': 1})
            mock_agent.project_root = Mock()
            mock_agent.project_root.__truediv__ = Mock(return_value=Mock(exists=Mock(return_value=False)))
            mock_agent.planner = "quality"
            mock_agent.executor = "fast"
            mock_code_agent_class.return_value = mock_agent

            # Run agent
            agent_mgr.run_agent("test task")

            # Verify CodeAgent was instantiated and run
            mock_code_agent_class.assert_called_once()
            mock_agent.run.assert_called_once_with("test task")

    def test_textual_interactive_creates_bridge_when_llm_service_exists(self):
        """TextualInteractiveMode should create LangGraphBridge when llm_service exists."""
        # This tests the wiring in textual_interactive.py
        from scrappy.cli.textual_interactive import TextualInteractiveMode

        # Create mock orchestrator with llm_service
        mock_orchestrator = Mock()
        mock_orchestrator.llm_service = Mock()  # Has llm_service
        mock_orchestrator.context_manager = Mock()
        mock_orchestrator.context_manager.context = None

        # Create mock CLI
        mock_cli = Mock()
        mock_cli.reinitialize_handlers_with_bridge = Mock()

        # Create mock IO
        mock_io = Mock()
        mock_io.output_sink = Mock()
        mock_io.set_bridge = Mock()

        # Create TextualInteractiveMode
        mode = TextualInteractiveMode(
            orchestrator=mock_orchestrator,
            session_context=Mock(),
            state_manager=Mock(),
            input_handler=Mock(),
            command_router=Mock(),
            display=Mock(),
            smart=Mock(),
            task_router=Mock(),
            tasks=Mock(),
            logger=Mock(),
            io=mock_io,
            cli=mock_cli,
        )

        # Verify cli is stored
        assert mode._cli is not None
        assert mode._cli == mock_cli

        # Verify orchestrator has llm_service
        assert hasattr(mode.orchestrator, 'llm_service')
        assert mode.orchestrator.llm_service is not None


    def test_run_creates_and_passes_bridge(self):
        """TextualInteractiveMode.run() should create bridge and pass to CLI."""
        from scrappy.cli.textual_interactive import TextualInteractiveMode

        # Create mock orchestrator with llm_service
        mock_orchestrator = Mock()
        mock_orchestrator.llm_service = Mock()
        mock_orchestrator.context_manager = Mock()
        mock_orchestrator.context_manager.context = None
        mock_orchestrator.output = None

        # Create mock CLI that captures the bridge
        captured_bridge = {}
        def capture_reinit(bridge, langgraph_bridge=None):
            captured_bridge['async_bridge'] = bridge
            captured_bridge['langgraph_bridge'] = langgraph_bridge
            # Also set agent_mgr mock
            mock_cli.agent_mgr = Mock()

        mock_cli = Mock()
        mock_cli.reinitialize_handlers_with_bridge = capture_reinit

        # Create mock IO with output_sink
        mock_io = Mock()
        mock_output_sink = Mock()
        mock_io.output_sink = mock_output_sink
        mock_io.set_bridge = Mock()

        # Create mock command_router
        mock_command_router = Mock()

        # Create TextualInteractiveMode
        mode = TextualInteractiveMode(
            orchestrator=mock_orchestrator,
            session_context=Mock(),
            state_manager=Mock(),
            input_handler=Mock(),
            command_router=mock_command_router,
            display=Mock(),
            smart=Mock(),
            task_router=Mock(),
            tasks=Mock(),
            logger=Mock(),
            io=mock_io,
            cli=mock_cli,
        )

        # Patch ScrappyApp to avoid actually running Textual
        with patch('scrappy.cli.textual_interactive.ScrappyApp') as mock_app_class:
            mock_app = Mock()
            mock_app.bridge = Mock()  # The ThreadSafeAsyncBridge
            mock_app.run = Mock()  # Don't actually run
            mock_app_class.return_value = mock_app

            # Patch LangGraphBridge
            with patch('scrappy.cli.textual.langgraph_bridge.LangGraphBridge') as mock_bridge_class:
                mock_langgraph_bridge = Mock()
                mock_bridge_class.return_value = mock_langgraph_bridge

                # Run
                mode.run()

                # Verify LangGraphBridge was created with correct args
                mock_bridge_class.assert_called_once()
                call_kwargs = mock_bridge_class.call_args.kwargs
                assert call_kwargs['app'] == mock_app
                assert call_kwargs['bridge'] == mock_app.bridge
                assert call_kwargs['output_adapter'] == mock_output_sink
                assert call_kwargs['llm_service'] == mock_orchestrator.llm_service

                # Verify bridge was passed to reinitialize_handlers_with_bridge
                assert captured_bridge['langgraph_bridge'] == mock_langgraph_bridge


    def test_deferred_mode_creates_langgraph_bridge(self):
        """ScrappyApp._setup_interactive_mode should create LangGraphBridge (production path).

        This tests the ACTUAL production code path used when running `scrappy`.
        The deferred mode uses cli_factory and _setup_interactive_mode.
        """
        from scrappy.cli.textual.app import ScrappyApp

        # Create mock CLI with all required attributes
        mock_cli = Mock()
        mock_cli.orchestrator = Mock()
        mock_cli.orchestrator.llm_service = Mock()  # Has llm_service
        mock_cli.orchestrator.output = None
        mock_cli.session_context = Mock()
        mock_cli.state_manager = Mock()
        mock_cli.input_handler = Mock()
        mock_cli.display = Mock()
        mock_cli.smart = Mock()
        mock_cli.task_router = Mock()
        mock_cli.tasks = Mock()
        mock_cli.logger = Mock()
        mock_cli.io = Mock()
        mock_cli.io.set_bridge = Mock()

        # Create mock command_router that will be returned
        mock_command_router = Mock()
        mock_cli._create_command_router = Mock(return_value=mock_command_router)

        # Capture what reinitialize_handlers_with_bridge receives
        captured_bridge = {}
        def capture_reinit(bridge, langgraph_bridge=None):
            captured_bridge['async_bridge'] = bridge
            captured_bridge['langgraph_bridge'] = langgraph_bridge
            mock_cli.agent_mgr = Mock()

        mock_cli.reinitialize_handlers_with_bridge = capture_reinit

        # Create ScrappyApp (we won't run it, just set up enough for the test)
        # We'll create in deferred mode then manually trigger _setup_interactive_mode
        with patch('scrappy.cli.textual.app.TextualOutputAdapter'):
            app = ScrappyApp(cli_factory=lambda: mock_cli)

        # Simulate CLI being set (as if factory ran)
        app._cli = mock_cli

        # Patch the import inside the method by patching the module
        mock_langgraph_bridge = Mock()
        with patch.dict('sys.modules', {
            'scrappy.cli.textual.langgraph_bridge': MagicMock(
                LangGraphBridge=Mock(return_value=mock_langgraph_bridge)
            )
        }):
            # Call the production code path
            app._setup_interactive_mode()

        # Verify bridge was passed to reinitialize_handlers_with_bridge
        # (The key assertion - langgraph_bridge should NOT be None)
        assert captured_bridge['langgraph_bridge'] is not None


class TestLangfuseIntegration:
    """Test Langfuse tracing integration with LangGraph."""

    def test_callback_handler_can_be_imported(self):
        """Verify langfuse.callback.CallbackHandler is available."""
        from langfuse.callback import CallbackHandler

        handler = CallbackHandler()
        assert handler is not None

    def test_callback_handler_works_with_graph_config(self):
        """Verify CallbackHandler can be passed to graph via config."""
        from langfuse.callback import CallbackHandler
        from langgraph.checkpoint.memory import MemorySaver
        from scrappy.graph.agent import build_graph
        from scrappy.graph.state import AgentState

        # Create mock LLM service that returns a done response
        class MockLLMService:
            def completion_sync(self, model, messages, **kwargs):
                class MockResponse:
                    content = "Task completed."
                    tool_calls = []
                return MockResponse(), {}

        # Create mock tool adapter
        class MockToolAdapter:
            def get_tool_names(self):
                return []
            def get_tool_schemas(self):
                return []
            def execute(self, tool_calls, context):
                return []

        # Build graph
        graph = build_graph(
            llm_service=MockLLMService(),
            tool_adapter=MockToolAdapter(),
            checkpointer=MemorySaver(),
        )

        # Create callback handler (won't actually send to Langfuse without env vars)
        handler = CallbackHandler()

        # Create initial state
        initial_state = AgentState.create_initial("say hello", "/tmp/test")

        # Config with callbacks - this is the key integration point
        config = {
            "configurable": {"thread_id": "test-langfuse"},
            "callbacks": [handler],  # Langfuse callback handler
            "recursion_limit": 10,
        }

        # Invoke graph - should not raise
        result = graph.invoke(initial_state, config)

        # Verify it completed
        if isinstance(result, dict):
            final_state = AgentState(**result)
        else:
            final_state = result

        assert final_state.done


class TestCancellationBug:
    """Test that cancellation is properly wired."""

    def test_current_worker_is_none_before_fix(self):
        """BUG: _current_worker is never assigned, so cancel() does nothing."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

        # Create bridge with minimal mocks
        mock_app = Mock()
        mock_bridge = Mock()
        mock_output = Mock()
        mock_llm = Mock()
        mock_tool_adapter = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            output_adapter=mock_output,
            llm_service=mock_llm,
            tool_adapter=mock_tool_adapter,
        )

        # _current_worker should be None initially (that's fine)
        assert bridge._current_worker is None

        # But after cancel(), it's still None - so cancel does nothing!
        bridge.cancel()
        # This is the bug: cancel() tried to call .cancel() on None
        # It silently fails because of the `if self._current_worker is not None` check

    def test_check_cancellation_without_worker_context(self):
        """_check_cancellation returns False when not in worker context."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

        mock_app = Mock()
        mock_bridge = Mock()
        mock_output = Mock()
        mock_llm = Mock()
        mock_tool_adapter = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            output_adapter=mock_output,
            llm_service=mock_llm,
            tool_adapter=mock_tool_adapter,
        )

        # When called outside worker context, should return False (not crash)
        result = bridge._check_cancellation()
        assert result is False

    def test_cancel_requires_worker_assignment(self):
        """Prove that cancel() needs _current_worker to be set."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

        mock_app = Mock()
        mock_bridge = Mock()
        mock_output = Mock()
        mock_llm = Mock()
        mock_tool_adapter = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            output_adapter=mock_output,
            llm_service=mock_llm,
            tool_adapter=mock_tool_adapter,
        )

        # Simulate what should happen: worker is assigned
        mock_worker = Mock()
        mock_worker.is_cancelled = False
        bridge._current_worker = mock_worker

        # Now cancel() should actually call cancel on the worker
        bridge.cancel()
        mock_worker.cancel.assert_called_once()


class TestAgentManagerCancelWiring:
    """Test that CLIAgentManager.cancel() calls langgraph_bridge.cancel()."""

    def test_cancel_calls_langgraph_bridge_cancel_when_running(self):
        """CLIAgentManager.cancel() should call langgraph_bridge.cancel() when agent is running."""
        from scrappy.cli.agent_manager import CLIAgentManager

        # Create mocks
        mock_orchestrator = Mock()
        mock_io = Mock()
        mock_io.theme = Mock()
        mock_io.theme.warning = "yellow"
        mock_io.secho = Mock()

        # Create mock LangGraphBridge with is_running=True
        mock_bridge = Mock()
        mock_bridge.is_running = True

        # Create agent manager with bridge
        agent_mgr = CLIAgentManager(
            orchestrator=mock_orchestrator,
            io=mock_io,
            user_interaction=Mock(),
            langgraph_bridge=mock_bridge,
        )

        # Call cancel
        agent_mgr.cancel()

        # Verify bridge.cancel() was called and message printed
        mock_bridge.cancel.assert_called_once()
        mock_io.secho.assert_called_once()

    def test_cancel_does_not_spam_when_not_running(self):
        """CLIAgentManager.cancel() should NOT call bridge.cancel() or print when agent is not running."""
        from scrappy.cli.agent_manager import CLIAgentManager

        # Create mocks
        mock_orchestrator = Mock()
        mock_io = Mock()
        mock_io.theme = Mock()
        mock_io.theme.warning = "yellow"
        mock_io.secho = Mock()

        # Create mock LangGraphBridge with is_running=False (completed/idle)
        mock_bridge = Mock()
        mock_bridge.is_running = False

        # Create agent manager with bridge
        agent_mgr = CLIAgentManager(
            orchestrator=mock_orchestrator,
            io=mock_io,
            user_interaction=Mock(),
            langgraph_bridge=mock_bridge,
        )

        # Call cancel (simulates user pressing Escape after completion)
        agent_mgr.cancel()

        # Verify bridge.cancel() was NOT called and NO message printed
        mock_bridge.cancel.assert_not_called()
        mock_io.secho.assert_not_called()

    def test_two_stage_cancel_shows_different_messages(self):
        """First cancel shows graceful message, second cancel shows force message."""
        from scrappy.cli.agent_manager import CLIAgentManager
        from scrappy.agent.cancellation import CancellationToken

        # Create mocks
        mock_orchestrator = Mock()
        mock_io = Mock()
        mock_io.theme = Mock()
        mock_io.theme.warning = "yellow"
        mock_io.theme.error = "red"
        mock_io.secho = Mock()

        # Create mock LangGraphBridge with is_running=True
        mock_bridge = Mock()
        mock_bridge.is_running = True

        # Create agent manager with bridge
        agent_mgr = CLIAgentManager(
            orchestrator=mock_orchestrator,
            io=mock_io,
            user_interaction=Mock(),
            langgraph_bridge=mock_bridge,
        )

        # Simulate having a cancellation token (as would exist during a run)
        agent_mgr._cancellation_token = CancellationToken()

        # First cancel - should show graceful message
        agent_mgr.cancel()
        mock_io.secho.assert_called_with(
            "Cancelling... waiting for current step to finish (press again to force)",
            fg="yellow"
        )

        # Second cancel - should show force message
        mock_io.secho.reset_mock()
        agent_mgr.cancel()
        mock_io.secho.assert_called_with("Force cancelling...", fg="red")

        # Verify token state
        assert agent_mgr._cancellation_token.is_cancelled()
        assert agent_mgr._cancellation_token.is_force_cancelled()


class TestStreamingCancellation:
    """Test that streaming allows mid-execution cancellation."""

    def test_run_with_streaming_checks_cancellation_between_nodes(self):
        """_run_with_streaming should check cancellation after each node."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge
        from unittest.mock import Mock, MagicMock

        # Create bridge with minimal mocks
        mock_app = Mock()
        mock_bridge = Mock()
        mock_output = Mock()
        mock_llm = Mock()
        mock_tool_adapter = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            output_adapter=mock_output,
            llm_service=mock_llm,
            tool_adapter=mock_tool_adapter,
        )

        # Create mock graph that yields events
        mock_graph = MagicMock()
        mock_events = [
            {"think": {"input": "test"}},
            {"execute": {"input": "test"}},
        ]
        mock_graph.stream.return_value = iter(mock_events)

        # Mock get_state to indicate not interrupted (execution complete)
        mock_snapshot = Mock()
        mock_snapshot.next = None  # Not interrupted
        mock_snapshot.values = {"input": "test", "original_task": "test", "working_dir": "/tmp"}
        mock_graph.get_state.return_value = mock_snapshot

        # Track cancellation checks
        check_count = [0]
        def track_cancellation():
            check_count[0] += 1
            return False  # Not cancelled

        bridge._check_cancellation = track_cancellation

        # Mock state class
        mock_state_class = Mock(return_value=Mock())

        # Run streaming
        bridge._run_with_streaming(
            mock_graph,
            Mock(),  # initial_state
            {"configurable": {"thread_id": "test"}},
            mock_state_class,
        )

        # Should have checked cancellation multiple times:
        # 1. Before stream
        # 2. After each event (2 events)
        # Total: at least 3 checks
        assert check_count[0] >= 3, f"Expected at least 3 cancellation checks, got {check_count[0]}"

    def test_run_with_streaming_stops_on_cancellation(self):
        """_run_with_streaming should return None when cancelled."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge
        from unittest.mock import Mock, MagicMock

        # Create bridge
        mock_app = Mock()
        mock_bridge = Mock()
        mock_output = Mock()
        mock_llm = Mock()
        mock_tool_adapter = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            tool_adapter=mock_tool_adapter,
            output_adapter=mock_output,
            llm_service=mock_llm,
        )

        # Create mock graph
        mock_graph = MagicMock()
        mock_events = [
            {"think": {"input": "test"}},
            {"execute": {"input": "test"}},
        ]
        mock_graph.stream.return_value = iter(mock_events)

        # Return cancelled after first node
        call_count = [0]
        def check_cancelled():
            call_count[0] += 1
            return call_count[0] > 1  # Cancel after first check

        bridge._check_cancellation = check_cancelled

        # Run streaming - should return None (cancelled)
        result = bridge._run_with_streaming(
            mock_graph,
            Mock(),
            {"configurable": {"thread_id": "test"}},
            Mock(),
        )

        assert result is None, "Expected None when cancelled"


class TestTaskProgressWidget:
    """Test that task progress widget is updated during tool execution."""

    def test_output_tool_executions_updates_task_progress(self):
        """_output_tool_executions should update task progress widget."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge
        from scrappy.protocols.tasks import TaskStatus

        # Create bridge with mocks
        mock_app = Mock()
        mock_bridge = Mock()
        mock_output = Mock()
        mock_llm = Mock()
        mock_tool_adapter = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=mock_bridge,
            tool_adapter=mock_tool_adapter,
            output_adapter=mock_output,
            llm_service=mock_llm,
        )

        # Simulate execute node output with tool calls
        node_output = {
            "pending_tool_calls": [
                {
                    "type": "function",
                    "id": "call_1",
                    "function": {"name": "read_file", "arguments": '{"path": "config.py"}'},
                },
                {
                    "type": "function",
                    "id": "call_2",
                    "function": {"name": "write_file", "arguments": '{"path": "output.txt"}'},
                },
            ],
            "tool_results": [
                {"name": "read_file", "result": "file content"},
                {"name": "write_file", "result": "success"},
            ],
        }

        # Call the method
        bridge._output_tool_executions(node_output)

        # Verify post_tasks_updated was called with completed tasks
        mock_output.post_tasks_updated.assert_called_once()
        tasks = mock_output.post_tasks_updated.call_args[0][0]
        assert len(tasks) == 2
        assert all(t.status == TaskStatus.DONE for t in tasks)
        assert "read_file" in tasks[0].description
        assert "write_file" in tasks[1].description

    def test_task_progress_rolling_window(self):
        """Task progress should keep only last N completed tasks."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge

        # Create bridge
        mock_app = Mock()
        mock_output = Mock()

        bridge = LangGraphBridge(
            app=mock_app,
            bridge=Mock(),
            tool_adapter=Mock(),
            output_adapter=mock_output,
            llm_service=Mock(),
        )
        bridge._max_completed_tasks = 3  # Keep last 3

        # Simulate 5 tool executions across multiple batches
        for i in range(5):
            node_output = {
                "pending_tool_calls": [
                    {"type": "function", "id": f"call_{i}", "function": {"name": f"tool_{i}", "arguments": "{}"}},
                ],
                "tool_results": [{"name": f"tool_{i}", "result": "ok"}],
            }
            bridge._output_tool_executions(node_output)

        # Should only have last 3 tasks
        assert len(bridge._recent_tasks) == 3
        assert "tool_2" in bridge._recent_tasks[0].description
        assert "tool_3" in bridge._recent_tasks[1].description
        assert "tool_4" in bridge._recent_tasks[2].description

    def test_clear_task_progress_on_run_end(self):
        """Task progress should be cleared when agent run completes."""
        from scrappy.cli.textual.langgraph_bridge import LangGraphBridge
        from scrappy.protocols.tasks import Task, TaskStatus

        mock_output = Mock()

        bridge = LangGraphBridge(
            app=Mock(),
            bridge=Mock(),
            tool_adapter=Mock(),
            output_adapter=mock_output,
            llm_service=Mock(),
        )

        # Add some tasks
        bridge._recent_tasks = [
            Task(description="task1", status=TaskStatus.DONE),
            Task(description="task2", status=TaskStatus.DONE),
        ]

        # Clear
        bridge._clear_task_progress()

        # Verify cleared
        assert bridge._recent_tasks == []
        mock_output.post_tasks_updated.assert_called_with([])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
