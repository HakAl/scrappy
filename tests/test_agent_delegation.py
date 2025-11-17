"""
Tests for agent provider delegation behavior.

These tests enforce that the agent lets the orchestrator decide provider selection,
rather than hardcoding provider choices based on static configuration.

Expected behavior:
- Agent should delegate provider selection to orchestrator
- Orchestrator decides based on task type, rate limits, availability
- Agent should NOT hardcode provider preferences
- Rate-limited providers should be avoided
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from src.agent.core import CodeAgent
from src.agent.types import ConversationState
from src.agent_config import AgentConfig
from src.orchestrator_adapter import LLMResponse


class TestAgentProviderDelegation:
    """Tests that agent properly delegates provider selection to orchestrator."""

    @pytest.fixture
    def fake_orchestrator(self):
        """Create orchestrator that tracks how it's called."""
        class TrackingOrchestrator:
            def __init__(self):
                self.delegate_calls = []
                self.registry = self
                self.context = Mock()
                self.context.is_explored.return_value = False
                self.context.get_summary.return_value = ""

            def list_available(self):
                return ['cerebras', 'groq', 'gemini']

            def get_recommended_provider(self, task_type='general'):
                """Smart provider selection based on task type."""
                if task_type == 'planning':
                    return 'cerebras'  # Not gemini!
                return 'cerebras'

            def delegate(self, provider_name=None, prompt="", **kwargs):
                # Auto-select if not specified
                if provider_name is None:
                    task_type = kwargs.get('task_type', 'general')
                    provider_name = self.get_recommended_provider(task_type)
                self.delegate_calls.append({
                    'provider': provider_name,
                    'prompt': prompt,
                    'kwargs': kwargs
                })
                return LLMResponse(
                    content='{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}',
                    provider=provider_name,
                    model="test-model",
                    tokens_used=100
                )

        return TrackingOrchestrator()

    @pytest.mark.unit
    def test_agent_should_not_hardcode_gemini_as_planner(self, fake_orchestrator, tmp_path):
        """Agent should not always use gemini just because it's first in preferences."""
        agent = CodeAgent(fake_orchestrator, project_path=str(tmp_path))

        # Even though gemini is available, agent shouldn't automatically pick it
        # This test will FAIL because current implementation picks gemini as first preference
        assert agent.planner != 'gemini', (
            "Agent hardcodes gemini as planner. "
            "Should let orchestrator decide based on task type and rate limits."
        )

    @pytest.mark.unit
    def test_agent_should_respect_orchestrator_provider_recommendation(self, tmp_path):
        """Agent should use provider recommended by orchestrator."""
        class RecommendingOrchestrator:
            def __init__(self):
                self.registry = self
                self.context = Mock()
                self.context.is_explored.return_value = False
                self.recommended_provider = 'cerebras'  # Orchestrator recommends cerebras

            def list_available(self):
                return ['cerebras', 'groq', 'gemini']

            def get_recommended_provider(self, task_type='planning'):
                """Orchestrator's recommendation based on rate limits and task type."""
                return self.recommended_provider

            def delegate(self, provider, prompt, **kwargs):
                return LLMResponse(
                    content='{"thought": "test", "action": "complete", "is_complete": true}',
                    provider=provider
                )

        orch = RecommendingOrchestrator()
        agent = CodeAgent(orch, project_path=str(tmp_path))

        # Agent should ask orchestrator for recommendation
        # This test will FAIL because agent doesn't call get_recommended_provider
        assert agent.planner == 'cerebras', (
            f"Agent picked {agent.planner} instead of orchestrator's recommended 'cerebras'. "
            "Agent should respect orchestrator's provider recommendation."
        )

    @pytest.mark.unit
    def test_agent_should_avoid_rate_limited_provider(self, tmp_path):
        """Agent should not use a provider that's rate limited."""
        class RateLimitAwareOrchestrator:
            def __init__(self):
                self.registry = self
                self.context = Mock()
                self.context.is_explored.return_value = False
                self.rate_limited_providers = {'gemini'}  # gemini is rate limited

            def list_available(self):
                return ['cerebras', 'groq', 'gemini']

            def is_rate_limited(self, provider):
                return provider in self.rate_limited_providers

            def get_recommended_provider(self, task_type='general'):
                """Skip rate-limited providers."""
                preferences = ['gemini', 'groq', 'cerebras']
                for prov in preferences:
                    if prov not in self.rate_limited_providers:
                        return prov
                return 'cerebras'

            def delegate(self, provider_name=None, prompt="", **kwargs):
                if provider_name is None:
                    task_type = kwargs.get('task_type', 'general')
                    provider_name = self.get_recommended_provider(task_type)
                if self.is_rate_limited(provider_name):
                    raise Exception(f"{provider_name} is rate limited")
                return LLMResponse(
                    content='{"thought": "test", "action": "complete", "is_complete": true}',
                    provider=provider_name
                )

        orch = RateLimitAwareOrchestrator()
        agent = CodeAgent(orch, project_path=str(tmp_path))

        # Agent should check rate limits before selecting provider
        # Orchestrator's get_recommended_provider skips gemini (rate limited)
        assert agent.planner != 'gemini', (
            "Agent selected gemini even though it's rate limited. "
            "Agent should check orchestrator's rate limit status before selecting provider."
        )

    @pytest.mark.unit
    def test_agent_think_should_let_orchestrator_pick_provider(self, fake_orchestrator, tmp_path):
        """When agent thinks, it should let orchestrator decide which provider to use."""
        agent = CodeAgent(fake_orchestrator, project_path=str(tmp_path))

        state = ConversationState(
            system_prompt="You are a helpful assistant",
            messages=[
                {'role': 'system', 'content': 'You are a helpful assistant'},
                {'role': 'user', 'content': 'Test task'}
            ],
            iteration=1,
            max_iterations=5,
            auto_confirm=False
        )

        # Call _think which should delegate to orchestrator
        agent._think(state)

        # Check what provider was requested
        assert len(fake_orchestrator.delegate_calls) == 1
        call_info = fake_orchestrator.delegate_calls[0]

        # Agent should pass task_type to let orchestrator make informed decision
        # The orchestrator picks the provider, not the agent
        assert 'task_type' in call_info['kwargs'], (
            "Agent should pass task_type to orchestrator for intelligent provider selection."
        )
        assert call_info['kwargs']['task_type'] == 'planning', (
            f"Agent should pass task_type='planning' when thinking, got '{call_info['kwargs'].get('task_type')}'."
        )
        # Provider should be what orchestrator decided (cerebras), not hardcoded gemini
        assert call_info['provider'] == 'cerebras', (
            f"Orchestrator recommended 'cerebras' but agent used '{call_info['provider']}'. "
            "Agent should respect orchestrator's provider selection."
        )

    @pytest.mark.unit
    def test_agent_should_use_task_type_for_provider_selection(self, tmp_path):
        """Agent should indicate task type so orchestrator can pick appropriate provider."""
        class TaskAwareOrchestrator:
            def __init__(self):
                self.registry = self
                self.context = Mock()
                self.context.is_explored.return_value = False
                self.delegate_calls = []

            def list_available(self):
                return ['cerebras', 'groq', 'gemini']

            def get_recommended_provider(self, task_type='general'):
                return 'cerebras'

            def delegate(self, provider_name=None, prompt="", **kwargs):
                if provider_name is None:
                    task_type = kwargs.get('task_type', 'general')
                    provider_name = self.get_recommended_provider(task_type)
                self.delegate_calls.append({
                    'provider': provider_name,
                    'task_type': kwargs.get('task_type'),
                    'kwargs': kwargs
                })
                return LLMResponse(
                    content='{"thought": "test", "action": "complete", "is_complete": true}',
                    provider=provider_name
                )

        orch = TaskAwareOrchestrator()
        agent = CodeAgent(orch, project_path=str(tmp_path))

        state = ConversationState(
            system_prompt="test",
            messages=[
                {'role': 'system', 'content': 'test'},
                {'role': 'user', 'content': 'Test task'}
            ],
            iteration=1,
            max_iterations=5,
            auto_confirm=False
        )

        agent._think(state)

        # Agent should pass task_type so orchestrator knows what kind of provider to pick
        # This test will FAIL because agent doesn't pass task_type
        call_info = orch.delegate_calls[0]
        assert 'task_type' in call_info['kwargs'], (
            "Agent should pass task_type to orchestrator so it can select appropriate provider. "
            "Planning tasks need reasoning capability, execution needs speed."
        )

    @pytest.mark.unit
    def test_agent_should_not_override_orchestrator_with_config_preferences(self, tmp_path):
        """Config preferences should not override orchestrator's intelligent selection."""
        class SmartOrchestrator:
            def __init__(self):
                self.registry = self
                self.context = Mock()
                self.context.is_explored.return_value = False
                # Orchestrator knows cerebras is best right now (fast, not rate limited)
                self.best_provider = 'cerebras'

            def list_available(self):
                return ['cerebras', 'groq', 'gemini']

            def get_recommended_provider(self, task_type='general'):
                """Smart selection based on current state."""
                return self.best_provider

            def delegate(self, provider_name=None, prompt="", **kwargs):
                if provider_name is None:
                    task_type = kwargs.get('task_type', 'general')
                    provider_name = self.get_recommended_provider(task_type)
                return LLMResponse(
                    content='{"thought": "test", "action": "complete", "is_complete": true}',
                    provider=provider_name
                )

        # Config says prefer gemini
        config = AgentConfig()
        config.planner_preferences = ['gemini', 'groq', 'cerebras']

        orch = SmartOrchestrator()
        agent = CodeAgent(orch, project_path=str(tmp_path), config=config)

        # Orchestrator's smart selection should win over static config preferences
        assert agent.planner == 'cerebras', (
            f"Agent picked {agent.planner} from config preferences, ignoring orchestrator's "
            "recommendation of 'cerebras'. Static config should not override intelligent selection."
        )

    @pytest.mark.unit
    def test_multiple_think_calls_should_allow_provider_rotation(self, tmp_path):
        """Orchestrator should be able to rotate providers between calls if needed."""
        class RotatingOrchestrator:
            def __init__(self):
                self.registry = self
                self.context = Mock()
                self.context.is_explored.return_value = False
                self.call_count = 0
                self.providers_used = []
                self.rotation = ['cerebras', 'groq', 'gemini']

            def list_available(self):
                return ['cerebras', 'groq', 'gemini']

            def get_recommended_provider(self, task_type='general'):
                """Rotate through providers on each call."""
                provider = self.rotation[self.call_count % len(self.rotation)]
                return provider

            def delegate(self, provider_name=None, prompt="", **kwargs):
                if provider_name is None:
                    task_type = kwargs.get('task_type', 'general')
                    provider_name = self.get_recommended_provider(task_type)
                self.providers_used.append(provider_name)
                self.call_count += 1
                return LLMResponse(
                    content='{"thought": "test", "action": "read_file", "parameters": {"file_path": "test.py"}, "is_complete": false}',
                    provider=provider_name
                )

        orch = RotatingOrchestrator()
        agent = CodeAgent(orch, project_path=str(tmp_path))

        state = ConversationState(
            system_prompt="test",
            messages=[
                {'role': 'system', 'content': 'test'},
                {'role': 'user', 'content': 'Test task'}
            ],
            iteration=1,
            max_iterations=5,
            auto_confirm=False
        )

        # Make multiple think calls
        agent._think(state)
        state.iteration = 2
        agent._think(state)
        state.iteration = 3
        agent._think(state)

        # Orchestrator should have opportunity to pick different providers
        # Agent should pass task_type and let orchestrator rotate
        unique_providers = set(orch.providers_used)
        assert len(unique_providers) > 1 or 'task_type' in str(orch.providers_used), (
            f"Agent used same provider for all calls: {orch.providers_used}. "
            "Orchestrator should be able to rotate providers based on rate limits and availability."
        )


class TestAgentOrchestratorContract:
    """Tests that define the contract between agent and orchestrator."""

    @pytest.mark.unit
    def test_orchestrator_should_provide_smart_provider_selection(self):
        """Orchestrator must have method for smart provider selection."""
        from src.orchestrator.core import AgentOrchestrator

        # Orchestrator should have method to recommend provider
        # This test defines the expected contract
        assert hasattr(AgentOrchestrator, 'get_recommended_provider') or \
               hasattr(AgentOrchestrator, 'delegate_for_task'), (
            "Orchestrator should have get_recommended_provider() or delegate_for_task() method "
            "that selects provider based on task type and current rate limit status."
        )

    @pytest.mark.unit
    def test_orchestrator_delegate_should_support_auto_provider_selection(self):
        """Orchestrator delegate should work without explicit provider specification."""
        from src.orchestrator.core import AgentOrchestrator
        import inspect

        sig = inspect.signature(AgentOrchestrator.delegate)
        params = sig.parameters

        # Provider parameter should be optional (has default) or method should accept task_type
        # This test will FAIL because current delegate requires provider name
        provider_param = params.get('provider_name')
        has_default = provider_param and provider_param.default != inspect.Parameter.empty
        has_task_type = 'task_type' in params

        assert has_default or has_task_type, (
            "Orchestrator.delegate() requires explicit provider name. "
            "Should support auto-selection: either provider_name has default, "
            "or method accepts task_type parameter for smart selection."
        )
