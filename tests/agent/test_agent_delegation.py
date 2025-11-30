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
from helpers import ConfigurableTestOrchestrator


class TestAgentProviderDelegation:
    """Tests that agent properly delegates provider selection to orchestrator."""

    @pytest.fixture
    def tracking_orchestrator(self):
        """Create orchestrator that tracks how it's called."""
        return ConfigurableTestOrchestrator(
            recommended_provider='cerebras',
            response_content='{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}',
            response_tokens=100
        )

    @pytest.mark.unit
    def test_agent_should_not_hardcode_gemini_as_planner(self, tracking_orchestrator, tmp_path):
        """Agent should not always use gemini just because it's first in preferences."""
        agent = CodeAgent(tracking_orchestrator, project_path=str(tmp_path))

        # Even though gemini is available, agent shouldn't automatically pick it
        # This test will FAIL because current implementation picks gemini as first preference
        assert agent.planner != 'gemini', (
            "Agent hardcodes gemini as planner. "
            "Should let orchestrator decide based on task type and rate limits."
        )

    @pytest.mark.unit
    def test_agent_should_respect_orchestrator_provider_recommendation(self, tmp_path):
        """Agent should use provider recommended by orchestrator."""
        orch = ConfigurableTestOrchestrator(recommended_provider='cerebras')
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
        orch = ConfigurableTestOrchestrator(
            rate_limited={'gemini'},
            recommended_provider='groq'  # Should skip gemini since it's rate limited
        )
        agent = CodeAgent(orch, project_path=str(tmp_path))

        # Agent should check rate limits before selecting provider
        # Orchestrator's get_recommended_provider skips gemini (rate limited)
        assert agent.planner != 'gemini', (
            "Agent selected gemini even though it's rate limited. "
            "Agent should check orchestrator's rate limit status before selecting provider."
        )

    @pytest.mark.unit
    def test_agent_think_should_let_orchestrator_pick_provider(self, tracking_orchestrator, tmp_path):
        """When agent thinks, it should let orchestrator decide which provider to use."""
        agent = CodeAgent(tracking_orchestrator, project_path=str(tmp_path))

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
        agent._agent_loop.think(state)

        # Check what provider was requested
        assert len(tracking_orchestrator.delegate_calls) == 1
        call_info = tracking_orchestrator.delegate_calls[0]

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
        orch = ConfigurableTestOrchestrator(recommended_provider='cerebras')
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

        agent._agent_loop.think(state)

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
        orch = ConfigurableTestOrchestrator(recommended_provider='cerebras')

        # Config says prefer gemini
        config = AgentConfig()
        agent = CodeAgent(orch, project_path=str(tmp_path), config=config)

        # Orchestrator's smart selection should win over static config preferences
        assert agent.planner == 'cerebras', (
            f"Agent picked {agent.planner} from config preferences, ignoring orchestrator's "
            "recommendation of 'cerebras'. Static config should not override intelligent selection."
        )

    @pytest.mark.unit
    def test_multiple_think_calls_should_allow_provider_rotation(self, tmp_path):
        """Orchestrator should be able to rotate providers between calls if needed."""
        orch = ConfigurableTestOrchestrator(
            rotation=['cerebras', 'groq', 'gemini'],
            response_content='{"thought": "test", "action": "read_file", "parameters": {"file_path": "test.py"}, "is_complete": false}'
        )
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
        agent._agent_loop.think(state)
        agent._agent_loop.think(state)
        agent._agent_loop.think(state)

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
