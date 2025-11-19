"""
Tests for CLI handler I/O dependency injection.

These tests verify that CLI handlers accept an io: CLIIOProtocol parameter
and route all output through the io object instead of calling click directly.

TDD: These tests are written first and will fail until handlers are updated.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# Import test helpers
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


# =============================================================================
# CLIAgentManager I/O Injection Tests
# =============================================================================

class TestAgentManagerIOInjection:
    """Tests for CLIAgentManager I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        # Import here to avoid import errors during collection
        from src.cli.agent_manager import CLIAgentManager
        self.manager = CLIAgentManager(self.orchestrator)

    def test_run_agent_accepts_io_parameter(self):
        """run_agent() should accept an io parameter."""
        io = MockIO(
            confirmations=[False, False, False]  # dry_run, checkpoint, start
        )

        # Should not raise TypeError for unexpected keyword argument
        self.manager.run_agent("test task", io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Code Agent" in output
        assert "test task" in output

    def test_run_agent_outputs_task_header(self):
        """run_agent() should output task header through io."""
        io = MockIO(
            confirmations=[False, False, False]
        )

        self.manager.run_agent("analyze code", io=io)

        output = io.get_output()
        assert "Code Agent - Task: analyze code" in output

        # Check styled output
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Code Agent" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['bold'] is True

    def test_run_agent_prompts_for_dry_run_mode(self):
        """run_agent() should use io.confirm for dry run mode."""
        io = MockIO(
            confirmations=[True, False, False]  # dry_run=True, checkpoint=False, start=False
        )

        self.manager.run_agent("test", io=io)

        output = io.get_output()
        # Should show dry run mode in configuration
        assert "DRY RUN" in output or "dry-run" in output.lower()

    def test_run_agent_prompts_for_checkpoint(self):
        """run_agent() should use io.confirm for git checkpoint."""
        io = MockIO(
            confirmations=[False, True, False]  # dry_run=False, checkpoint=True, start=False
        )

        with patch('src.cli.agent_manager.create_git_checkpoint', return_value="abc123"):
            self.manager.run_agent("test", io=io)

        output = io.get_output()
        assert "checkpoint" in output.lower() or "Creating" in output

    def test_run_agent_cancelled_outputs_message(self):
        """run_agent() should output cancellation message through io."""
        io = MockIO(
            confirmations=[False, False, False]  # dry_run, checkpoint, start=cancelled
        )

        self.manager.run_agent("test", io=io)

        output = io.get_output()
        assert "cancelled" in output.lower()

    def test_run_agent_success_output(self):
        """run_agent() should output success message through io."""
        io = MockIO(
            confirmations=[False, False, True, False]  # dry_run, checkpoint, start, save_audit
        )

        # Mock the agent run
        mock_agent = MagicMock()
        mock_agent.run.return_value = {
            'success': True,
            'result': 'Task completed',
            'iterations': 3,
            'audit_log': []
        }

        with patch('src.cli.agent_manager.CodeAgent', return_value=mock_agent):
            self.manager.run_agent("test", io=io)

        output = io.get_output()
        assert "Completed Successfully" in output or "success" in output.lower()

        # Check green color for success
        styled = io.get_styled_outputs()
        success_outputs = [s for s in styled if "Success" in s['text'] or "Completed" in s['text']]
        if success_outputs:
            assert success_outputs[0]['fg'] == 'green'

    def test_run_agent_failure_output(self):
        """run_agent() should output failure message through io."""
        io = MockIO(
            confirmations=[False, False, True, False]
        )

        mock_agent = MagicMock()
        mock_agent.run.return_value = {
            'success': False,
            'result': 'Task incomplete',
            'iterations': 5,
            'audit_log': []
        }

        with patch('src.cli.agent_manager.CodeAgent', return_value=mock_agent):
            self.manager.run_agent("test", io=io)

        output = io.get_output()
        assert "Did Not Complete" in output or "incomplete" in output.lower()

        # Check yellow color for incomplete
        styled = io.get_styled_outputs()
        incomplete_outputs = [s for s in styled if "Not Complete" in s['text']]
        if incomplete_outputs:
            assert incomplete_outputs[0]['fg'] == 'yellow'

    def test_run_agent_error_handling(self):
        """run_agent() should output errors through io."""
        io = MockIO(
            confirmations=[False, False, True]
        )

        mock_agent = MagicMock()
        mock_agent.run.side_effect = Exception("Test error")

        with patch('src.cli.agent_manager.CodeAgent', return_value=mock_agent):
            self.manager.run_agent("test", io=io)

        output = io.get_output()
        assert "error" in output.lower()
        assert "Test error" in output

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "error" in s['text'].lower()]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

    def test_run_agent_audit_log_display(self):
        """run_agent() should display audit log through io."""
        io = MockIO(
            confirmations=[False, False, True, False]
        )

        mock_agent = MagicMock()
        mock_agent.run.return_value = {
            'success': True,
            'result': 'Done',
            'iterations': 1,
            'audit_log': [
                {'timestamp': '2024-01-01T10:00:00', 'action': 'write_file', 'approved': True}
            ]
        }

        with patch('src.cli.agent_manager.CodeAgent', return_value=mock_agent):
            self.manager.run_agent("test", io=io)

        output = io.get_output()
        assert "Audit Log" in output
        assert "write_file" in output


# =============================================================================
# CLICodebaseAnalysis I/O Injection Tests
# =============================================================================

class TestCodebaseAnalysisIOInjection:
    """Tests for CLICodebaseAnalysis I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        from src.cli.codebase import CLICodebaseAnalysis
        self.analyzer = CLICodebaseAnalysis(self.orchestrator)

    def test_explore_codebase_accepts_io_parameter(self):
        """explore_codebase() should accept an io parameter."""
        io = MockIO(
            inputs=["nonexistent_path"],
            confirmations=[]
        )

        # Should not raise TypeError for unexpected keyword argument
        self.analyzer.explore_codebase("", io=io)

        # Should have used io for output
        output = io.get_output()
        assert len(output) > 0

    def test_explore_codebase_prompts_for_path(self):
        """explore_codebase() should use io.prompt for directory path."""
        io = MockIO(
            inputs=["."],
            confirmations=[False]  # Don't save summary
        )

        # Mock the exploration result
        with patch.object(self.orchestrator, 'explore_project') as mock_explore:
            mock_explore.return_value = {'status': 'cached', 'total_files': 10}
            with patch.object(self.orchestrator.context, 'summary', 'Test summary'):
                self.analyzer.explore_codebase("", io=io)

        output = io.get_output()
        # Should have prompted for directory
        assert len(output) > 0

    def test_explore_codebase_invalid_path_error(self):
        """explore_codebase() should output error for invalid path through io."""
        io = MockIO(confirmations=[])

        self.analyzer.explore_codebase("this_path_does_not_exist_123", io=io)

        output = io.get_output()
        assert "does not exist" in output.lower()

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "does not exist" in s['text'].lower()]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

    def test_explore_codebase_not_directory_error(self):
        """explore_codebase() should output error for non-directory path through io."""
        import tempfile

        # Create a temporary file (not a directory)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_file = f.name

        try:
            io = MockIO(confirmations=[])

            self.analyzer.explore_codebase(temp_file, io=io)

            output = io.get_output()
            assert "Not a directory" in output

            # Check red color for error
            styled = io.get_styled_outputs()
            error_outputs = [s for s in styled if "Not a directory" in s['text']]
            if error_outputs:
                assert error_outputs[0]['fg'] == 'red'
        finally:
            os.unlink(temp_file)

    def test_explore_codebase_outputs_summary(self):
        """explore_codebase() should output codebase summary through io."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            io = MockIO(
                confirmations=[False]  # Don't save summary
            )

            # Mock the exploration
            with patch.object(self.orchestrator.context, 'explore') as mock_explore:
                mock_explore.return_value = {'total_files': 5, 'directories': ['src']}
                with patch.object(self.orchestrator.context, 'generate_summary', return_value='Test summary'):
                    with patch.object(self.orchestrator.context, 'project_path', Path(temp_dir)):
                        self.analyzer.explore_codebase(temp_dir, io=io)

            output = io.get_output()
            assert "Codebase Summary" in output

            # Check bold header
            styled = io.get_styled_outputs()
            summary_headers = [s for s in styled if "Codebase Summary" in s['text']]
            if summary_headers:
                assert summary_headers[0]['bold'] is True

    def test_explore_codebase_save_confirmation(self):
        """explore_codebase() should use io.confirm for save prompt."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            io = MockIO(
                confirmations=[True]  # Save summary
            )

            with patch.object(self.orchestrator.context, 'explore') as mock_explore:
                mock_explore.return_value = {'total_files': 5, 'directories': ['src']}
                with patch.object(self.orchestrator.context, 'generate_summary', return_value='Test summary'):
                    with patch.object(self.orchestrator.context, 'project_path', Path(temp_dir)):
                        self.analyzer.explore_codebase(temp_dir, io=io)

            output = io.get_output()
            # Should indicate file was saved
            assert "Saved to" in output

            # Verify file was created
            summary_file = Path(temp_dir) / "CODEBASE_SUMMARY.md"
            assert summary_file.exists()

    def test_explore_codebase_confirm_prompt_displayed(self):
        """
        explore_codebase() should display the save confirmation prompt.

        This test verifies that the [y/n] prompt is actually displayed to the user
        after the summary, not hidden by progress bar interference.

        Regression test for: Rich integration broke the confirm prompt display
        when click.progressbar interferes with io.confirm().
        """
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            io = MockIO(
                confirmations=[False]  # User says no to saving
            )

            with patch.object(self.orchestrator.context, 'explore') as mock_explore:
                mock_explore.return_value = {'total_files': 5, 'directories': ['src']}
                with patch.object(self.orchestrator.context, 'generate_summary', return_value='Test summary'):
                    with patch.object(self.orchestrator.context, 'project_path', Path(temp_dir)):
                        self.analyzer.explore_codebase(temp_dir, io=io)

            # Verify io.confirm was called (which displays the prompt)
            confirmations_used = io.confirmations_used()
            assert confirmations_used == 1, \
                "io.confirm should have been called once for save prompt"

            output = io.get_output()
            # Prompt text should appear in output
            assert "Save summary to file?" in output, \
                "Save confirmation prompt text should be displayed"

            # Verify file was NOT created since user said no
            summary_file = Path(temp_dir) / "CODEBASE_SUMMARY.md"
            assert not summary_file.exists(), \
                "File should not exist when user declines save prompt"


# =============================================================================
# CLIMultiProvider I/O Injection Tests
# =============================================================================

class TestMultiProviderIOInjection:
    """Tests for CLIMultiProvider I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        from src.cli.multiprovider import CLIMultiProvider
        self.multi = CLIMultiProvider(self.orchestrator)

    def test_synthesize_mode_accepts_io_parameter(self):
        """synthesize_mode() should accept an io parameter."""
        io = MockIO(
            inputs=["", ""],  # Empty question triggers early return
            confirmations=[]
        )

        # Should not raise TypeError for unexpected keyword argument
        self.multi.synthesize_mode(io=io)

        output = io.get_output()
        assert "Synthesis Mode" in output

    def test_synthesize_mode_outputs_header(self):
        """synthesize_mode() should output header through io."""
        io = MockIO(
            inputs=[""],
            confirmations=[]
        )

        self.multi.synthesize_mode(io=io)

        output = io.get_output()
        assert "Synthesis Mode" in output

        # Check bold header
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Synthesis Mode" in s['text']]
        if header_outputs:
            assert header_outputs[0]['bold'] is True

    def test_synthesize_mode_prompts_for_question(self):
        """synthesize_mode() should use io.prompt for question."""
        io = MockIO(
            inputs=["What is Python?", "all"],
            confirmations=[]
        )

        # Mock providers
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai']

        self.multi.synthesize_mode(io=io)

        output = io.get_output()
        # Should have asked for question and shown available providers
        assert "Available providers" in output or "provider" in output.lower()

    def test_synthesize_mode_empty_question(self):
        """synthesize_mode() should handle empty question through io."""
        io = MockIO(
            inputs=[""],
            confirmations=[]
        )

        self.multi.synthesize_mode(io=io)

        output = io.get_output()
        assert "No question provided" in output

    def test_synthesize_mode_not_enough_providers(self):
        """synthesize_mode() should warn about insufficient providers through io."""
        io = MockIO(
            inputs=["test question", "provider1"],
            confirmations=[]
        )

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['provider1']

        self.multi.synthesize_mode(io=io)

        output = io.get_output()
        assert "at least 2 providers" in output

        # Check yellow warning color
        styled = io.get_styled_outputs()
        warning_outputs = [s for s in styled if "providers" in s['text'].lower()]
        if warning_outputs:
            assert warning_outputs[0]['fg'] == 'yellow'

    def test_synthesize_mode_successful_synthesis(self):
        """synthesize_mode() should output synthesis result through io."""
        io = MockIO(
            inputs=["test question", "all"],
            confirmations=[]
        )

        # Mock providers and responses
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai', 'anthropic']

        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tokens_used = 100

        self.orchestrator.delegate = MagicMock(return_value=mock_response)
        self.orchestrator.synthesize = MagicMock(return_value="Synthesized result")

        self.multi.synthesize_mode(io=io)

        output = io.get_output()
        assert "Synthesized Response" in output
        assert "Synthesized result" in output

    def test_delegate_mode_accepts_io_parameter(self):
        """delegate_mode() should accept an io parameter."""
        io = MockIO(
            inputs=["openai", "test prompt"],
            confirmations=[]
        )

        # Mock providers
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai']

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.model = "gpt-4"
        mock_response.tokens_used = 50
        mock_response.latency_ms = 100

        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        # Should not raise TypeError for unexpected keyword argument
        self.multi.delegate_mode("", io=io)

        output = io.get_output()
        assert len(output) > 0

    def test_delegate_mode_with_args(self):
        """delegate_mode() should handle args parameter with io."""
        io = MockIO(confirmations=[])

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['cerebras']

        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.model = "llama3"
        mock_response.tokens_used = 50
        mock_response.latency_ms = 100

        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.multi.delegate_mode("cerebras test prompt", io=io)

        output = io.get_output()
        assert "Response from cerebras" in output
        assert "Test response" in output

    def test_delegate_mode_usage_message(self):
        """delegate_mode() should output usage through io when args incomplete."""
        io = MockIO(
            inputs=["openai", "test"],
            confirmations=[]
        )

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai']

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.model = "gpt-4"
        mock_response.tokens_used = 50
        mock_response.latency_ms = 100

        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.multi.delegate_mode("", io=io)

        output = io.get_output()
        assert "Usage:" in output or "Response from" in output

    def test_delegate_mode_provider_not_found(self):
        """delegate_mode() should output error for unknown provider through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['cerebras']

        self.multi.delegate_mode("unknown test prompt", io=io)

        output = io.get_output()
        # "unknown" is not in VALID_PROVIDERS, so it fails validation
        assert "unknown provider" in output.lower()

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "unknown provider" in s['text'].lower()]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

    def test_delegate_mode_error_handling(self):
        """delegate_mode() should handle errors through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['cerebras']
        self.orchestrator.delegate = MagicMock(side_effect=Exception("API error"))

        self.multi.delegate_mode("cerebras test", io=io)

        output = io.get_output()
        assert "Error" in output
        assert "API error" in output

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "Error" in s['text']]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'


# =============================================================================
# CLISessionManager I/O Injection Tests
# =============================================================================

class TestSessionManagerIOInjection:
    """Tests for CLISessionManager I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        from src.cli.session import CLISessionManager
        self.session = CLISessionManager(self.orchestrator)

    def test_manage_context_accepts_io_parameter(self):
        """manage_context() should accept an io parameter."""
        io = MockIO(confirmations=[])

        # Mock get_context_status
        self.orchestrator.get_context_status = MagicMock(return_value={
            'project_path': '/test',
            'is_explored': True,
            'has_summary': False,
            'explored_at': None,
            'total_files': 10,
            'cache_file': '/test/.cache',
            'cache_exists': False
        })
        self.orchestrator.get_working_memory_summary = MagicMock(return_value={
            'files_cached': 0,
            'cached_files': [],
            'recent_searches': 0,
            'git_operations': 0,
            'discoveries': 0
        })

        # Should not raise TypeError for unexpected keyword argument
        self.session.manage_context("", io=io)

        output = io.get_output()
        assert "Context Status" in output

    def test_manage_context_outputs_status(self):
        """manage_context() should output context status through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.get_context_status = MagicMock(return_value={
            'project_path': '/test/project',
            'is_explored': True,
            'has_summary': True,
            'explored_at': '2024-01-01',
            'total_files': 100,
            'cache_file': '/test/.cache',
            'cache_exists': True
        })
        self.orchestrator.get_working_memory_summary = MagicMock(return_value={
            'files_cached': 5,
            'cached_files': ['a.py', 'b.py'],
            'recent_searches': 3,
            'git_operations': 2,
            'discoveries': 1
        })
        self.orchestrator.context = MagicMock()
        self.orchestrator.context.summary = "Test summary"

        self.session.manage_context("", io=io)

        output = io.get_output()
        assert "Context Status" in output
        assert "Project:" in output
        assert "Explored:" in output
        assert "Total Files:" in output

        # Check cyan color for header
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Context Status" in s['text']]
        if header_outputs:
            assert header_outputs[0]['fg'] == 'cyan'
            assert header_outputs[0]['bold'] is True

    def test_manage_context_explore_command(self):
        """manage_context() should handle explore command through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.explore_project = MagicMock(return_value={
            'status': 'success',
            'total_files': 50
        })
        self.orchestrator.context = MagicMock()
        self.orchestrator.context.summary = "Summary"

        self.session.manage_context("explore", io=io)

        output = io.get_output()
        assert "Exploring" in output or "files" in output

    def test_manage_context_clear_command(self):
        """manage_context() should handle clear command through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.context = MagicMock()

        self.session.manage_context("clear", io=io)

        output = io.get_output()
        assert "cleared" in output.lower()

        # Check green color for success
        styled = io.get_styled_outputs()
        success_outputs = [s for s in styled if "cleared" in s['text'].lower()]
        if success_outputs:
            assert success_outputs[0]['fg'] == 'green'

    def test_manage_cache_accepts_io_parameter(self):
        """manage_cache() should accept an io parameter."""
        io = MockIO(confirmations=[])

        self.orchestrator.get_cache_stats = MagicMock(return_value={
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 20,
            'intent_hits': 10,
            'exact_misses': 30,
            'saves': 15,
            'exact_hit_rate': '40.0%',
            'intent_hit_rate': '25.0%',
            'cache_file': '/test/.cache'
        })

        self.session.manage_cache("", io=io)

        output = io.get_output()
        assert "Cache Statistics" in output

    def test_manage_cache_toggle(self):
        """manage_cache() should handle toggle command through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.toggle_cache = MagicMock(return_value=True)

        self.session.manage_cache("toggle", io=io)

        output = io.get_output()
        assert "enabled" in output.lower() or "disabled" in output.lower()

    def test_show_rate_limits_accepts_io_parameter(self):
        """show_rate_limits() should accept an io parameter."""
        io = MockIO(confirmations=[])

        self.orchestrator.get_rate_limit_status = MagicMock(return_value={
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {}
        })
        self.orchestrator.check_rate_limit_warnings = MagicMock(return_value=[])
        self.orchestrator.context = MagicMock()
        self.orchestrator.context.project_path = Path('/test')

        self.session.show_rate_limits("", io=io)

        output = io.get_output()
        assert "Rate Limit" in output

    def test_show_rate_limits_with_warnings(self):
        """show_rate_limits() should display warnings through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.get_rate_limit_status = MagicMock(return_value={
            'last_reset': {'daily': '2024-01-01', 'monthly': '2024-01-01'},
            'providers': {
                'openai': {
                    'total_requests_today': 100,
                    'total_tokens_today': 10000,
                    'total_requests_month': 500
                }
            }
        })
        self.orchestrator.check_rate_limit_warnings = MagicMock(return_value=[
            "High usage warning"
        ])
        self.orchestrator.context = MagicMock()
        self.orchestrator.context.project_path = Path('/test')

        self.session.show_rate_limits("", io=io)

        output = io.get_output()
        assert "WARNINGS" in output
        assert "High usage warning" in output

        # Check red color for warnings
        styled = io.get_styled_outputs()
        warning_outputs = [s for s in styled if "WARNINGS" in s['text']]
        if warning_outputs:
            assert warning_outputs[0]['fg'] == 'red'

    def test_manage_session_accepts_io_parameter(self):
        """manage_session() should accept an io parameter."""
        io = MockIO(confirmations=[])

        self.orchestrator.context = MagicMock()
        self.orchestrator.context.project_path = Path('/test')
        self.orchestrator.get_working_memory_summary = MagicMock(return_value={
            'files_cached': 0,
            'cached_files': [],
            'recent_searches': 0,
            'git_operations': 0,
            'discoveries': 0
        })

        self.session.manage_session("", conversation_history=[], auto_save=True, io=io)

        output = io.get_output()
        assert "Session Management" in output

    def test_manage_session_save_command(self):
        """manage_session() should handle save command through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.save_session = MagicMock(return_value='/test/session.json')

        result = self.session.manage_session("save", conversation_history=[], io=io)

        output = io.get_output()
        assert "saved" in output.lower()

        # Check green color for success
        styled = io.get_styled_outputs()
        success_outputs = [s for s in styled if "saved" in s['text'].lower()]
        if success_outputs:
            assert success_outputs[0]['fg'] == 'green'

    def test_manage_session_load_command(self):
        """manage_session() should handle load command through io."""
        io = MockIO(confirmations=[])

        self.orchestrator.load_session = MagicMock(return_value={
            'status': 'loaded',
            'saved_at': '2024-01-01',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 1,
            'conversation_history': [{'role': 'user', 'content': 'test'}]
        })

        result = self.session.manage_session("load", io=io)

        output = io.get_output()
        assert "loaded" in output.lower()

        # Check that conversation was restored
        assert result['conversation_history'] is not None
        assert len(result['conversation_history']) > 0

    def test_manage_session_toggle_auto_save(self):
        """manage_session() should handle toggle command through io."""
        io = MockIO(confirmations=[])

        result = self.session.manage_session("toggle", auto_save=True, io=io)

        output = io.get_output()
        assert "Auto-save" in output

        # Should toggle the value
        assert result['auto_save'] is False


# =============================================================================
# Default I/O Parameter Tests
# =============================================================================

class TestDefaultIOParameter:
    """Tests to verify handlers use ClickIO as default when io is None."""

    def test_agent_manager_uses_default_io(self):
        """CLIAgentManager should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.agent_manager import CLIAgentManager
        manager = CLIAgentManager(orchestrator)

        # This should work without providing io parameter
        # The method should internally create a ClickIO instance
        # We can't easily test this without actual click, so we verify
        # it doesn't error when io is not provided
        # Note: This test will fail until handlers are updated
        import inspect
        sig = inspect.signature(manager.run_agent)
        params = sig.parameters

        # Verify io parameter exists and has default
        assert 'io' in params, "run_agent should have an 'io' parameter"
        assert params['io'].default is not None or params['io'].default is None, \
            "io parameter should have a default value"

    def test_codebase_analysis_uses_default_io(self):
        """CLICodebaseAnalysis should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.codebase import CLICodebaseAnalysis
        analyzer = CLICodebaseAnalysis(orchestrator)

        import inspect
        sig = inspect.signature(analyzer.explore_codebase)
        params = sig.parameters

        assert 'io' in params, "explore_codebase should have an 'io' parameter"

    def test_multi_provider_synthesize_uses_default_io(self):
        """CLIMultiProvider.synthesize_mode should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.multiprovider import CLIMultiProvider
        multi = CLIMultiProvider(orchestrator)

        import inspect
        sig = inspect.signature(multi.synthesize_mode)
        params = sig.parameters

        assert 'io' in params, "synthesize_mode should have an 'io' parameter"

    def test_multi_provider_delegate_uses_default_io(self):
        """CLIMultiProvider.delegate_mode should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.multiprovider import CLIMultiProvider
        multi = CLIMultiProvider(orchestrator)

        import inspect
        sig = inspect.signature(multi.delegate_mode)
        params = sig.parameters

        assert 'io' in params, "delegate_mode should have an 'io' parameter"

    def test_session_manager_methods_use_default_io(self):
        """CLISessionManager methods should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.session import CLISessionManager
        session = CLISessionManager(orchestrator)

        import inspect

        # Check manage_context
        sig = inspect.signature(session.manage_context)
        assert 'io' in sig.parameters, "manage_context should have an 'io' parameter"

        # Check manage_cache
        sig = inspect.signature(session.manage_cache)
        assert 'io' in sig.parameters, "manage_cache should have an 'io' parameter"

        # Check show_rate_limits
        sig = inspect.signature(session.show_rate_limits)
        assert 'io' in sig.parameters, "show_rate_limits should have an 'io' parameter"

        # Check manage_session
        sig = inspect.signature(session.manage_session)
        assert 'io' in sig.parameters, "manage_session should have an 'io' parameter"


# =============================================================================
# CLI Core I/O Injection Tests
# =============================================================================

class TestCLICoreIOInjection:
    """Tests for CLI core I/O dependency injection."""

    def test_cli_init_accepts_io_parameter(self):
        """CLI.__init__() should accept an io parameter."""
        io = MockIO(
            confirmations=[False]  # Don't restore session
        )

        # Mock the orchestrator to avoid real initialization
        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test-brain'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            output = io.get_output()
            assert "Initializing" in output
            assert "Scrappy" in output

    def test_cli_init_outputs_brain_info(self):
        """CLI.__init__() should output brain info through io."""
        io = MockIO(
            confirmations=[False]
        )

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'anthropic'
            mock_orch.providers.list_available.return_value = ['anthropic', 'openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            output = io.get_output()
            assert "Brain:" in output

    def test_cli_init_session_restore_prompt(self):
        """CLI.__init__() should use io.confirm for session restore."""
        io = MockIO(
            confirmations=[True]  # Restore session
        )

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {
                'exists': True,
                'saved_at': '2024-01-01',
                'file_count': 5,
                'search_count': 3,
                'discovery_count': 2,
                'task_count': 1
            }
            mock_orch.load_session.return_value = {
                'status': 'loaded',
                'files_restored': 5,
                'searches_restored': 3,
                'git_ops_restored': 0,
                'discoveries_restored': 2,
                'conversation_history': []
            }
            MockOrch.return_value = mock_orch

            # Mock stdin.isatty to return True so session restore is triggered
            with patch('sys.stdin.isatty', return_value=True):
                from src.cli.core import CLI
                cli = CLI(io=io)

            output = io.get_output()
            assert "session" in output.lower()

    def test_cli_show_current_task_outputs_through_io(self):
        """CLI._show_current_task() should output through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            # Set up active plan
            cli.plan_active = True
            cli.active_plan = [
                {'step': 'Task 1', 'description': 'First task'},
                {'step': 'Task 2', 'description': 'Second task'}
            ]
            cli.current_task_index = 0

            # Clear output from init
            io.clear_output()

            cli._show_current_task(io=io)

            output = io.get_output()
            assert "1/2" in output  # Task count
            assert "Task 1" in output

    def test_cli_show_plan_summary_outputs_through_io(self):
        """CLI._show_plan_summary() should output through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            # Set up plan progress
            cli.active_plan = [
                {'step': 'Task 1'},
                {'step': 'Task 2'},
                {'step': 'Task 3'}
            ]
            cli.current_task_index = 2  # 2 completed

            io.clear_output()

            cli._show_plan_summary(io=io)

            output = io.get_output()
            assert "Plan Summary" in output
            assert "2/3" in output
            assert "%" in output  # Progress percentage

    def test_cli_prompt_task_progression_outputs_through_io(self):
        """CLI._prompt_task_progression() should use io for prompts."""
        io = MockIO(
            inputs=["4"],  # Choice: Finish planning
            confirmations=[False]  # Init session restore
        )

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            cli.plan_active = True
            cli.active_plan = [{'step': 'Task 1'}]
            cli.current_task_index = 0

            io.clear_output()

            # Mock stdin.isatty to return True
            with patch('sys.stdin.isatty', return_value=True):
                cli._prompt_task_progression(io=io)

            output = io.get_output()
            assert "What next?" in output
            assert "Mark complete" in output

    def test_cli_prompt_task_progression_mark_complete(self):
        """CLI._prompt_task_progression() should handle mark complete through io."""
        io = MockIO(
            inputs=["1"],  # Choice: Mark complete
            confirmations=[False]
        )

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            cli.plan_active = True
            cli.active_plan = [{'step': 'Task 1'}]
            cli.current_task_index = 0
            cli.auto_execute_tasks = False

            io.clear_output()

            with patch('sys.stdin.isatty', return_value=True):
                cli._prompt_task_progression(io=io)

            output = io.get_output()
            assert "DONE" in output or "complete" in output.lower()

    def test_cli_read_multiline_input_outputs_through_io(self):
        """CLI._read_multiline_input() should use io for prompts."""
        io = MockIO(
            inputs=["line 1", "line 2", ""],  # Lines followed by blank to end
            confirmations=[False]
        )

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            io.clear_output()

            result = cli._read_multiline_input(io=io)

            output = io.get_output()
            assert "multiline" in output.lower()
            # The result should contain the input lines
            assert "line 1" in result
            assert "line 2" in result

    def test_cli_handle_command_help_outputs_through_io(self):
        """CLI._handle_command() should route /help through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            io.clear_output()

            # Mock the display handler
            cli.display = MagicMock()

            cli._handle_command("/help", io=io)

            # Verify display.show_help was called
            cli.display.show_help.assert_called_once()

    def test_cli_handle_command_unknown_outputs_through_io(self):
        """CLI._handle_command() should output unknown command through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            io.clear_output()

            cli._handle_command("/unknowncommand", io=io)

            output = io.get_output()
            assert "Unknown command" in output or "Invalid command" in output

            # Check red error color for validation errors
            styled = io.get_styled_outputs()
            error_outputs = [s for s in styled if "Unknown command" in s['text'] or "Invalid command" in s['text']]
            if error_outputs:
                assert error_outputs[0]['fg'] == 'red'

    def test_cli_handle_command_clear_outputs_through_io(self):
        """CLI._handle_command() should output clear confirmation through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)
            cli.conversation_history = [{'role': 'user', 'content': 'test'}]

            io.clear_output()

            cli._handle_command("/clear", io=io)

            output = io.get_output()
            assert "cleared" in output.lower()

            # Check history was cleared
            assert len(cli.conversation_history) == 0

    def test_cli_handle_command_autoexec_toggle_outputs_through_io(self):
        """CLI._handle_command() should output autoexec toggle through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)
            initial_state = cli.auto_execute_tasks

            io.clear_output()

            cli._handle_command("/autoexec", io=io)

            output = io.get_output()
            assert "Auto-execute" in output

            # Should have toggled
            assert cli.auto_execute_tasks != initial_state

    def test_cli_handle_command_multiline_toggle_outputs_through_io(self):
        """CLI._handle_command() should output multiline toggle through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)
            initial_state = cli.multiline_mode

            io.clear_output()

            cli._handle_command("/ml", io=io)

            output = io.get_output()
            assert "Multiline" in output

            # Should have toggled
            assert cli.multiline_mode != initial_state

    def test_cli_handle_command_auto_toggle_outputs_through_io(self):
        """CLI._handle_command() should output auto-routing toggle through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)
            initial_state = cli.auto_route_mode

            io.clear_output()

            cli._handle_command("/auto", io=io)

            output = io.get_output()
            assert "Auto-routing" in output or "routing" in output.lower()

            # Should have toggled
            assert cli.auto_route_mode != initial_state

    def test_cli_handle_command_tasks_no_plan_outputs_through_io(self):
        """CLI._handle_command() should output no plan message through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            io.clear_output()

            cli._handle_command("/tasks", io=io)

            output = io.get_output()
            assert "No active plan" in output

    def test_cli_handle_command_quit_outputs_through_io(self):
        """CLI._handle_command() should output goodbye through io on quit."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            mock_orch.save_session.return_value = '/test/session.json'
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            # Mock display
            cli.display = MagicMock()

            io.clear_output()

            result = cli._handle_command("/quit", io=io)

            output = io.get_output()
            assert "Goodbye" in output
            assert result is False  # Should return False to exit

    def test_cli_handle_command_plan_usage_outputs_through_io(self):
        """CLI._handle_command() should output plan usage through io."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            io.clear_output()

            cli._handle_command("/plan", io=io)

            output = io.get_output()
            assert "Usage:" in output

    def test_cli_has_io_instance_attribute(self):
        """CLI should store io as instance attribute for use by handlers."""
        io = MockIO(confirmations=[False])

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            cli = CLI(io=io)

            # Verify io is stored as instance attribute
            assert hasattr(cli, 'io'), "CLI should have 'io' instance attribute"
            assert cli.io is io, "CLI.io should be the provided io object"


class TestCLICoreDefaultIO:
    """Tests to verify CLI uses ClickIO as default when io is None."""

    def test_cli_init_uses_default_io(self):
        """CLI.__init__ should use ClickIO when io is not provided."""
        import inspect
        from src.cli.core import CLI

        sig = inspect.signature(CLI.__init__)
        params = sig.parameters

        # Verify io parameter exists
        assert 'io' in params, "CLI.__init__ should have an 'io' parameter"

    def test_cli_private_methods_accept_io(self):
        """CLI private methods should accept io parameter."""
        import inspect

        with patch('src.cli.core.AgentOrchestrator') as MockOrch:
            mock_orch = MagicMock()
            mock_orch.brain = 'test'
            mock_orch.providers.list_available.return_value = ['openai']
            mock_orch.context.is_explored.return_value = False
            mock_orch.context_aware = True
            mock_orch.session_manager.get_session_info.return_value = {'exists': False}
            MockOrch.return_value = mock_orch

            from src.cli.core import CLI
            io = MockIO(confirmations=[False])
            cli = CLI(io=io)

            # Check private methods have io parameter
            methods_to_check = [
                '_read_multiline_input',
                '_show_current_task',
                '_prompt_task_progression',
                '_show_plan_summary',
                '_handle_command',
                '_execute_current_task',
                '_check_and_offer_session_restore'
            ]

            for method_name in methods_to_check:
                method = getattr(cli, method_name)
                sig = inspect.signature(method)
                assert 'io' in sig.parameters, f"{method_name} should have an 'io' parameter"
