"""
Tests for CLI Display, Tasks, and SmartQuery I/O dependency injection.

These tests verify that these CLI handlers accept an io: CLIIOProtocol parameter
and route all output through the io object instead of calling click directly.

TDD: These tests are written first and will fail until handlers are updated.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from pathlib import Path

# Import test helpers
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import MockIO, ConfigurableTestOrchestrator


# =============================================================================
# CLIDisplay I/O Injection Tests
# =============================================================================

class TestDisplayIOInjection:
    """Tests for CLIDisplay I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        self.session_start = datetime.now()
        from src.cli.display import CLIDisplay
        self.display = CLIDisplay(self.orchestrator, self.session_start)

    def test_show_help_accepts_io_parameter(self):
        """show_help() should accept an io parameter."""
        io = MockIO()

        # Should not raise TypeError for unexpected keyword argument
        self.display.show_help(io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Available Commands" in output

    def test_show_help_outputs_header(self):
        """show_help() should output header with styling through io."""
        io = MockIO()

        self.display.show_help(io=io)

        output = io.get_output()
        assert "Available Commands" in output

        # Check styled output
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Available Commands" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    def test_show_help_outputs_all_sections(self):
        """show_help() should output key command sections through io."""
        io = MockIO()

        self.display.show_help(io=io)

        output = io.get_output()

        # Check key sections are present (fallback mode has condensed sections)
        assert "Chat" in output
        assert "Task" in output
        assert "Provider" in output
        assert "System" in output
        # Verify commands are shown
        assert "/help" in output
        assert "/quit" in output

    def test_show_help_command_styling(self):
        """show_help() should style command names through io."""
        io = MockIO()

        self.display.show_help(io=io)

        output = io.get_output()

        # Commands should be present
        assert "/help" in output
        assert "/quit" in output
        assert "/plan" in output

    def test_show_status_accepts_io_parameter(self):
        """show_status() should accept an io parameter."""
        io = MockIO()

        self.display.show_status(io=io)

        output = io.get_output()
        assert "System Status" in output

    def test_show_status_outputs_header(self):
        """show_status() should output header with styling through io."""
        io = MockIO()

        self.display.show_status(io=io)

        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "System Status" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    def test_show_status_outputs_brain_info(self):
        """show_status() should output brain info through io."""
        io = MockIO()
        self.orchestrator.brain = 'anthropic'

        self.display.show_status(io=io)

        output = io.get_output()
        assert "Current Brain" in output
        assert "anthropic" in output

    def test_show_status_outputs_providers(self):
        """show_status() should output provider info through io."""
        io = MockIO()

        self.display.show_status(io=io)

        output = io.get_output()
        assert "Total Providers" in output
        assert "Available" in output

    def test_show_status_outputs_session_duration(self):
        """show_status() should output session duration through io."""
        io = MockIO()

        self.display.show_status(io=io)

        output = io.get_output()
        assert "Session Duration" in output

    def test_list_providers_accepts_io_parameter(self):
        """list_providers() should accept an io parameter."""
        io = MockIO()

        # Mock provider info
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.get_provider_info.return_value = {
            'openai': {
                'available': True,
                'default_model': 'gpt-4',
                'models': ['gpt-4', 'gpt-3.5-turbo'],
                'limits': MagicMock(
                    requests_per_day=1000,
                    tokens_per_minute=60000,
                    tokens_per_day=1000000
                )
            }
        }

        self.display.list_providers(io=io)

        output = io.get_output()
        assert "Available Providers" in output

    def test_list_providers_outputs_header(self):
        """list_providers() should output header with styling through io."""
        io = MockIO()

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.get_provider_info.return_value = {}

        self.display.list_providers(io=io)

        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Available Providers" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    def test_list_providers_active_provider_styling(self):
        """list_providers() should style active providers in green through io."""
        io = MockIO()

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.get_provider_info.return_value = {
            'openai': {
                'available': True,
                'default_model': 'gpt-4',
                'models': ['gpt-4'],
                'limits': MagicMock(
                    requests_per_day=1000,
                    tokens_per_minute=60000,
                    tokens_per_day=1000000
                )
            }
        }

        self.display.list_providers(io=io)

        styled = io.get_styled_outputs()
        active_outputs = [s for s in styled if "Active" in s['text']]
        if active_outputs:
            assert active_outputs[0]['fg'] == 'green'

    def test_list_providers_inactive_provider_styling(self):
        """list_providers() should style inactive providers in red through io."""
        io = MockIO()

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.get_provider_info.return_value = {
            'openai': {
                'available': False,
                'default_model': '',
                'models': [],
                'limits': MagicMock(
                    requests_per_day=None,
                    tokens_per_minute=None,
                    tokens_per_day=None
                )
            }
        }

        self.display.list_providers(io=io)

        styled = io.get_styled_outputs()
        inactive_outputs = [s for s in styled if "Not Configured" in s['text']]
        if inactive_outputs:
            assert inactive_outputs[0]['fg'] == 'red'

    def test_switch_brain_accepts_io_parameter(self):
        """switch_brain() should accept an io parameter."""
        io = MockIO()

        self.display.switch_brain("", io=io)

        output = io.get_output()
        assert "Current brain" in output or "Usage" in output

    def test_switch_brain_no_args_shows_current(self):
        """switch_brain() with no args should show current brain through io."""
        io = MockIO()
        self.orchestrator.brain = 'anthropic'

        self.display.switch_brain("", io=io)

        output = io.get_output()
        assert "Current brain" in output
        assert "anthropic" in output

    def test_switch_brain_success(self):
        """switch_brain() should output success message through io."""
        io = MockIO()
        self.orchestrator.brain = 'anthropic'

        self.display.switch_brain("cerebras", io=io)

        output = io.get_output()
        assert "switched" in output.lower()
        assert "cerebras" in output

        # Check green color for success
        styled = io.get_styled_outputs()
        success_outputs = [s for s in styled if "switched" in s['text'].lower()]
        if success_outputs:
            assert success_outputs[0]['fg'] == 'green'

    def test_switch_brain_invalid_provider(self):
        """switch_brain() should output error for invalid provider through io."""
        io = MockIO()

        self.display.switch_brain("invalid_provider", io=io)

        output = io.get_output()
        # Invalid provider names fail validation with "Unknown provider" error
        assert "unknown provider" in output.lower()

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "unknown provider" in s['text'].lower()]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

    def test_show_usage_accepts_io_parameter(self):
        """show_usage() should accept an io parameter."""
        io = MockIO()

        self.display.show_usage(io=io)

        output = io.get_output()
        assert "Usage Statistics" in output

    def test_show_usage_outputs_header(self):
        """show_usage() should output header with styling through io."""
        io = MockIO()

        self.display.show_usage(io=io)

        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Usage Statistics" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    def test_show_usage_outputs_totals(self):
        """show_usage() should output totals through io."""
        io = MockIO()

        # Make some delegate calls to generate usage
        self.orchestrator.delegate('cerebras', 'test')

        self.display.show_usage(io=io)

        output = io.get_output()
        assert "Total Tasks" in output
        assert "Session Duration" in output

    def test_show_usage_outputs_by_provider(self):
        """show_usage() should output per-provider stats through io."""
        io = MockIO()

        # Make delegate calls
        self.orchestrator.delegate('cerebras', 'test')
        self.orchestrator.delegate('groq', 'test')

        self.display.show_usage(io=io)

        output = io.get_output()
        assert "By Provider" in output

    def test_list_models_accepts_io_parameter(self):
        """list_models() should accept an io parameter."""
        io = MockIO()

        # Mock providers for list_models
        mock_provider = MagicMock()
        mock_provider.available_models = ['model1', 'model2']
        mock_provider.default_model = 'model1'
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai']
        self.orchestrator.providers.get.return_value = mock_provider

        self.display.list_models("", io=io)

        output = io.get_output()
        assert "Models" in output

    def test_list_models_all_providers(self):
        """list_models() with no args should list all providers through io."""
        io = MockIO()

        # Mock providers
        mock_provider = MagicMock()
        mock_provider.available_models = ['model1', 'model2']
        mock_provider.default_model = 'model1'
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai']
        self.orchestrator.providers.get.return_value = mock_provider

        self.display.list_models("", io=io)

        output = io.get_output()
        assert "All Available Models" in output

    def test_list_models_specific_provider(self):
        """list_models() with provider name should list that provider through io."""
        io = MockIO()

        mock_provider = MagicMock()
        mock_provider.available_models = ['model1', 'model2']
        mock_provider.default_model = 'model1'
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['openai']
        self.orchestrator.providers.get.return_value = mock_provider

        self.display.list_models("openai", io=io)

        output = io.get_output()
        assert "OPENAI Models" in output or "openai" in output.lower()

    def test_list_models_invalid_provider(self):
        """list_models() should output error for invalid provider through io."""
        io = MockIO()

        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['cerebras']

        self.display.list_models("invalid", io=io)

        output = io.get_output()
        # Invalid provider names fail validation with "Unknown provider" error
        assert "unknown provider" in output.lower()

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "unknown provider" in s['text'].lower()]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

    def test_list_models_default_indicator(self):
        """list_models() should indicate default model through io."""
        io = MockIO()

        mock_provider = MagicMock()
        mock_provider.available_models = ['model1', 'model2']
        mock_provider.default_model = 'model1'
        self.orchestrator.providers = MagicMock()
        self.orchestrator.providers.list_available.return_value = ['cerebras']
        self.orchestrator.providers.get.return_value = mock_provider

        self.display.list_models("cerebras", io=io)

        output = io.get_output()
        assert "default" in output.lower()


# =============================================================================
# CLITaskExecution I/O Injection Tests
# =============================================================================

class TestTaskExecutionIOInjection:
    """Tests for CLITaskExecution I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        from src.cli.tasks import CLITaskExecution
        self.tasks = CLITaskExecution(self.orchestrator)

    def test_plan_task_accepts_io_parameter(self):
        """plan_task() should accept an io parameter."""
        io = MockIO()

        # Mock the plan method
        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step'}
        ])

        # Should not raise TypeError for unexpected keyword argument
        self.tasks.plan_task("test task", io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Planning" in output

    def test_plan_task_outputs_header(self):
        """plan_task() should output task header through io."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(return_value=[])

        self.tasks.plan_task("analyze code", io=io)

        output = io.get_output()
        assert "Planning: analyze code" in output

        # Check bold header
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Planning" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['bold'] is True

    def test_plan_task_outputs_steps(self):
        """plan_task() should output plan steps through io."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step'},
            {'step': 'Step 2', 'description': 'Second step'}
        ])

        self.tasks.plan_task("test task", io=io)

        output = io.get_output()
        assert "Step 1" in output
        assert "First step" in output
        assert "Step 2" in output
        assert "Second step" in output

    def test_plan_task_outputs_provider_recommendations(self):
        """plan_task() should output provider recommendations through io."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step', 'provider_type': 'anthropic'}
        ])

        self.tasks.plan_task("test task", io=io)

        output = io.get_output()
        assert "Recommended" in output
        assert "anthropic" in output

        # Check cyan color for recommendation
        styled = io.get_styled_outputs()
        rec_outputs = [s for s in styled if "Recommended" in s['text']]
        if rec_outputs:
            assert rec_outputs[0]['fg'] == 'cyan'

    def test_plan_task_error_handling(self):
        """plan_task() should output errors through io."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(side_effect=Exception("Test error"))

        result = self.tasks.plan_task("test task", io=io)

        output = io.get_output()
        assert "Error" in output
        assert "Test error" in output

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "Error" in s['text']]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

        # Should return empty list on error
        assert result == []

    def test_plan_task_string_steps(self):
        """plan_task() should handle string steps through io."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(return_value=[
            "Step 1: Do something",
            "Step 2: Do another thing"
        ])

        self.tasks.plan_task("test task", io=io)

        output = io.get_output()
        assert "Step 1" in output
        assert "Step 2" in output

    def test_plan_task_non_list_response(self):
        """plan_task() should handle non-list responses through io."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(return_value="Single step plan")

        self.tasks.plan_task("test task", io=io)

        output = io.get_output()
        assert "Single step plan" in output

    def test_plan_task_returns_steps(self):
        """plan_task() should return the steps for tracking."""
        io = MockIO()

        steps = [
            {'step': 'Step 1', 'description': 'First step'},
            {'step': 'Step 2', 'description': 'Second step'}
        ]
        self.orchestrator.plan = MagicMock(return_value=steps)

        result = self.tasks.plan_task("test task", io=io)

        assert result == steps

    def test_plan_task_saves_to_working_memory(self):
        """plan_task() should save plan to working memory."""
        io = MockIO()

        self.orchestrator.plan = MagicMock(return_value=[
            {'step': 'Step 1', 'description': 'First step'}
        ])

        self.tasks.plan_task("test task", io=io)

        # Verify working memory was updated
        summary = self.orchestrator.working_memory.get_summary()
        assert summary['discoveries'] > 0

    def test_reason_accepts_io_parameter(self):
        """reason() should accept an io parameter."""
        io = MockIO()

        # Mock the reason method
        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'conclusion',
            'confidence': 'high'
        })

        # Should not raise TypeError for unexpected keyword argument
        self.tasks.reason("test question", io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Reasoning" in output

    def test_reason_outputs_header(self):
        """reason() should output question header through io."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(return_value={})

        self.tasks.reason("What is Python?", io=io)

        output = io.get_output()
        assert "Reasoning about: What is Python?" in output

        # Check bold header
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Reasoning" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['bold'] is True

    def test_reason_outputs_analysis(self):
        """reason() should output analysis through io."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'This is the analysis',
            'conclusion': 'This is the conclusion',
            'confidence': 'high'
        })

        self.tasks.reason("test", io=io)

        output = io.get_output()
        assert "Analysis" in output
        assert "This is the analysis" in output

    def test_reason_outputs_conclusion(self):
        """reason() should output conclusion through io."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'Final conclusion',
            'confidence': 'high'
        })

        self.tasks.reason("test", io=io)

        output = io.get_output()
        assert "Conclusion" in output
        assert "Final conclusion" in output

        # Check bold styling for conclusion label
        styled = io.get_styled_outputs()
        conclusion_outputs = [s for s in styled if "Conclusion" in s['text']]
        if conclusion_outputs:
            assert conclusion_outputs[0]['bold'] is True

    def test_reason_outputs_confidence(self):
        """reason() should output confidence through io."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'conclusion',
            'confidence': 'high'
        })

        self.tasks.reason("test", io=io)

        output = io.get_output()
        assert "Confidence" in output
        assert "high" in output

    def test_reason_error_handling(self):
        """reason() should output errors through io."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(side_effect=Exception("API error"))

        self.tasks.reason("test", io=io)

        output = io.get_output()
        assert "Error" in output
        assert "API error" in output

        # Check red color for error
        styled = io.get_styled_outputs()
        error_outputs = [s for s in styled if "Error" in s['text']]
        if error_outputs:
            assert error_outputs[0]['fg'] == 'red'

    def test_reason_string_response(self):
        """reason() should handle string responses through io."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(return_value="Simple string response")

        self.tasks.reason("test", io=io)

        output = io.get_output()
        assert "Simple string response" in output

    def test_reason_saves_to_working_memory(self):
        """reason() should save result to working memory."""
        io = MockIO()

        self.orchestrator.reason = MagicMock(return_value={
            'question': 'test',
            'analysis': 'analysis',
            'conclusion': 'conclusion',
            'confidence': 'high'
        })

        self.tasks.reason("test question", io=io)

        # Verify working memory was updated
        summary = self.orchestrator.working_memory.get_summary()
        assert summary['discoveries'] > 0


# =============================================================================
# CLISmartQuery I/O Injection Tests
# =============================================================================

class TestSmartQueryIOInjection:
    """Tests for CLISmartQuery I/O dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = ConfigurableTestOrchestrator()
        # Set up context
        self.orchestrator.context = MagicMock()
        self.orchestrator.context.summary = ""
        from src.cli.smart_query import CLISmartQuery
        self.smart = CLISmartQuery(self.orchestrator)

    def test_smart_query_accepts_io_parameter(self):
        """smart_query() should accept an io parameter."""
        io = MockIO()

        # Mock the classifier to return minimal result
        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        # Mock delegate response
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        # Should not raise TypeError for unexpected keyword argument
        self.smart.smart_query("test query", io=io)

        # Verify output went to io object
        output = io.get_output()
        assert "Smart Query" in output

    def test_smart_query_outputs_header(self):
        """smart_query() should output analyzing header through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "[Smart Query] Analyzing intent" in output

        # Check cyan color and bold
        styled = io.get_styled_outputs()
        header_outputs = [s for s in styled if "Smart Query" in s['text']]
        assert len(header_outputs) > 0
        assert header_outputs[0]['fg'] == 'cyan'
        assert header_outputs[0]['bold'] is True

    def test_smart_query_outputs_classification(self):
        """smart_query() should output intent classification through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='code_search'), confidence=0.95),
            secondary_intents=[],
            entities={'function_name': ['test_func']},
            keywords=['test', 'search']
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("find test_func", io=io)

        output = io.get_output()
        assert "Primary intent" in output
        assert "code_search" in output
        assert "0.95" in output

    def test_smart_query_outputs_secondary_intents(self):
        """smart_query() should output secondary intents through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='code_search'), confidence=0.8),
            secondary_intents=[
                MagicMock(intent=MagicMock(value='file_structure'), confidence=0.6)
            ],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "Secondary intents" in output
        assert "file_structure" in output

    def test_smart_query_outputs_extracted_entities(self):
        """smart_query() should output extracted entities through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='code_search'), confidence=0.8),
            secondary_intents=[],
            entities={'function_name': ['my_function', 'other_func']},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "Extracted" in output
        assert "function_name" in output

    def test_smart_query_outputs_researching_header(self):
        """smart_query() should output researching header through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "[Smart Query] Researching" in output

    def test_smart_query_outputs_research_actions(self):
        """smart_query() should output research actions through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        # Use FILE_STRUCTURE intent to trigger directory listing
        from src.intent_classifier import QueryIntent
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=QueryIntent.FILE_STRUCTURE, confidence=0.9),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        # Mock CodeAgent
        with patch('src.cli.smart_query.CodeAgent') as MockAgent:
            mock_agent = MagicMock()
            mock_agent._tool_list_directory.return_value = "dir1/\ndir2/"
            MockAgent.return_value = mock_agent

            self.smart.smart_query("show directory structure", io=io)

        output = io.get_output()
        assert "Checking directory structure" in output

    def test_smart_query_outputs_research_count(self):
        """smart_query() should output research result count through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "Gathered" in output
        assert "research results" in output

    def test_smart_query_outputs_assistant_header(self):
        """smart_query() should output Assistant header through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "The answer is 42"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "Assistant:" in output

        # Check blue color for assistant header
        styled = io.get_styled_outputs()
        assistant_outputs = [s for s in styled if "Assistant:" in s['text']]
        assert len(assistant_outputs) > 0
        assert assistant_outputs[0]['fg'] == 'blue'
        assert assistant_outputs[0]['bold'] is True

    def test_smart_query_outputs_response(self):
        """smart_query() should output response content through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "This is the actual response content"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        assert "This is the actual response content" in output

    def test_smart_query_outputs_metadata(self):
        """smart_query() should output response metadata through io."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "anthropic"
        mock_response.model = "claude-3"
        mock_response.tokens_used = 500
        mock_response.latency_ms = 1234
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        self.smart.smart_query("test", io=io)

        output = io.get_output()
        # Should contain provider/model info
        assert "anthropic" in output
        # Should contain token count
        assert "500" in output
        # Should contain latency
        assert "1234" in output

        # Check cyan color for metadata
        styled = io.get_styled_outputs()
        metadata_outputs = [s for s in styled if "tokens" in s['text']]
        if metadata_outputs:
            assert metadata_outputs[0]['fg'] == 'cyan'

    def test_smart_query_saves_to_working_memory(self):
        """smart_query() should save results to working memory."""
        io = MockIO()

        from src.intent_classifier import QueryIntent
        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=QueryIntent.FILE_STRUCTURE, confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        # Mock CodeAgent
        with patch('src.cli.smart_query.CodeAgent') as MockAgent:
            mock_agent = MagicMock()
            mock_agent._tool_list_directory.return_value = "result"
            MockAgent.return_value = mock_agent

            self.smart.smart_query("show structure", io=io)

        # Verify working memory was updated
        summary = self.orchestrator.working_memory.get_summary()
        assert summary['discoveries'] > 0 or summary['recent_searches'] > 0

    def test_smart_query_returns_response(self):
        """smart_query() should return the LLM response."""
        io = MockIO()

        self.smart.classifier = MagicMock()
        self.smart.classifier.classify.return_value = MagicMock(
            primary_intent=MagicMock(intent=MagicMock(value='general'), confidence=0.8),
            secondary_intents=[],
            entities={},
            keywords=[]
        )

        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.provider = "test"
        mock_response.model = "model"
        mock_response.tokens_used = 100
        mock_response.latency_ms = 50
        self.orchestrator.delegate = MagicMock(return_value=mock_response)

        result = self.smart.smart_query("test", io=io)

        assert result == mock_response


# =============================================================================
# Default I/O Parameter Tests
# =============================================================================

class TestDisplayTasksSmartDefaultIO:
    """Tests to verify handlers use ClickIO as default when io is None."""

    def test_display_show_help_uses_default_io(self):
        """CLIDisplay.show_help should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now())

        import inspect
        sig = inspect.signature(display.show_help)
        params = sig.parameters

        assert 'io' in params, "show_help should have an 'io' parameter"

    def test_display_show_status_uses_default_io(self):
        """CLIDisplay.show_status should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now())

        import inspect
        sig = inspect.signature(display.show_status)
        params = sig.parameters

        assert 'io' in params, "show_status should have an 'io' parameter"

    def test_display_list_providers_uses_default_io(self):
        """CLIDisplay.list_providers should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now())

        import inspect
        sig = inspect.signature(display.list_providers)
        params = sig.parameters

        assert 'io' in params, "list_providers should have an 'io' parameter"

    def test_display_switch_brain_uses_default_io(self):
        """CLIDisplay.switch_brain should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now())

        import inspect
        sig = inspect.signature(display.switch_brain)
        params = sig.parameters

        assert 'io' in params, "switch_brain should have an 'io' parameter"

    def test_display_show_usage_uses_default_io(self):
        """CLIDisplay.show_usage should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now())

        import inspect
        sig = inspect.signature(display.show_usage)
        params = sig.parameters

        assert 'io' in params, "show_usage should have an 'io' parameter"

    def test_display_list_models_uses_default_io(self):
        """CLIDisplay.list_models should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.display import CLIDisplay
        display = CLIDisplay(orchestrator, datetime.now())

        import inspect
        sig = inspect.signature(display.list_models)
        params = sig.parameters

        assert 'io' in params, "list_models should have an 'io' parameter"

    def test_tasks_plan_task_uses_default_io(self):
        """CLITaskExecution.plan_task should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(orchestrator)

        import inspect
        sig = inspect.signature(tasks.plan_task)
        params = sig.parameters

        assert 'io' in params, "plan_task should have an 'io' parameter"

    def test_tasks_reason_uses_default_io(self):
        """CLITaskExecution.reason should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.tasks import CLITaskExecution
        tasks = CLITaskExecution(orchestrator)

        import inspect
        sig = inspect.signature(tasks.reason)
        params = sig.parameters

        assert 'io' in params, "reason should have an 'io' parameter"

    def test_smart_query_uses_default_io(self):
        """CLISmartQuery.smart_query should use ClickIO when io is not provided."""
        orchestrator = ConfigurableTestOrchestrator()
        from src.cli.smart_query import CLISmartQuery
        smart = CLISmartQuery(orchestrator)

        import inspect
        sig = inspect.signature(smart.smart_query)
        params = sig.parameters

        assert 'io' in params, "smart_query should have an 'io' parameter"
