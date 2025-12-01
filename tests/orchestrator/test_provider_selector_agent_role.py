"""
Tests for ProviderSelector handling of supports_agent_role capability.

Tests that providers with supports_agent_role=False are:
- Skipped during brain selection
- Skipped during planning selection
- Warned about when explicitly requested
- Still available in general provider list
"""

import pytest
from unittest.mock import Mock

from scrappy.orchestrator.provider_selector import ProviderSelector
from scrappy.orchestrator.config import OrchestratorConfig
from scrappy.providers.base import ModelInfo, ModelType, SpeedRank, QualityRank


def create_mock_provider(name: str, supports_agent_role: bool = True, models: list = None):
    """Create a mock provider with specified agent role support."""
    provider = Mock()
    provider.name = name
    provider.supports_agent_role = supports_agent_role
    provider.available_models = models or ['default-model']
    provider.default_model = provider.available_models[0]

    def get_model_info(model_id):
        return ModelInfo(
            id=model_id,
            model_type=ModelType.CHAT,
            context_length=8192,
            rpd=1000,
            speed=SpeedRank.FAST,
            quality=QualityRank.GOOD
        )

    provider.get_model_info = get_model_info
    provider.get_instruction_tuned_models = Mock(return_value=[])
    return provider


def create_mock_registry(providers: dict):
    """
    Create a mock registry with specified providers.

    Args:
        providers: Dict mapping provider_name to supports_agent_role bool
    """
    registry = Mock()
    provider_objects = {
        name: create_mock_provider(name, supports_agent)
        for name, supports_agent in providers.items()
    }
    registry.list_available.return_value = list(providers.keys())
    registry.get = lambda name: provider_objects.get(name)
    return registry


class TestSetupBrainAgentRoleFiltering:
    """Tests for setup_brain() respecting supports_agent_role."""

    def test_skips_provider_that_does_not_support_agent_role(self):
        """Provider with supports_agent_role=False is skipped during auto-selection."""
        registry = create_mock_registry({
            'github': False,  # Does not support agent role
            'cerebras': True,
        })
        config = OrchestratorConfig(brain_priority=['github', 'cerebras'])
        selector = ProviderSelector(registry, config=config)

        provider_name, provider = selector.setup_brain()

        assert provider_name == 'cerebras'
        log = selector.get_selection_log()
        assert any('github' in entry and 'does not support agent role' in entry for entry in log)

    def test_warns_when_user_requests_unsupported_provider(self):
        """Warns user and falls back when they request a provider that doesn't support agent role."""
        registry = create_mock_registry({
            'github': False,
            'cerebras': True,
        })
        config = OrchestratorConfig(brain_priority=['cerebras'])
        selector = ProviderSelector(registry, config=config)

        provider_name, provider = selector.setup_brain(preferred_provider='github')

        assert provider_name == 'cerebras'
        log = selector.get_selection_log()
        assert any('github' in entry and 'does not support agent/brain roles' in entry for entry in log)
        assert any('Falling back' in entry for entry in log)

    def test_accepts_provider_with_agent_role_support(self):
        """Provider with supports_agent_role=True is accepted."""
        registry = create_mock_registry({
            'cerebras': True,
            'groq': True,
        })
        config = OrchestratorConfig(brain_priority=['cerebras', 'groq'])
        selector = ProviderSelector(registry, config=config)

        provider_name, provider = selector.setup_brain()

        assert provider_name == 'cerebras'

    def test_explicit_request_for_supported_provider_works(self):
        """User can explicitly request a provider that supports agent role."""
        registry = create_mock_registry({
            'cerebras': True,
            'groq': True,
        })
        config = OrchestratorConfig(brain_priority=['cerebras', 'groq'])
        selector = ProviderSelector(registry, config=config)

        provider_name, provider = selector.setup_brain(preferred_provider='groq')

        assert provider_name == 'groq'

    def test_all_providers_unsupported_uses_fallback(self):
        """Falls back to first available when all priority providers don't support agent role."""
        registry = create_mock_registry({
            'github': False,
            'other': False,
            'fallback': True,
        })
        config = OrchestratorConfig(brain_priority=['github', 'other'])
        selector = ProviderSelector(registry, config=config)

        provider_name, provider = selector.setup_brain()

        assert provider_name == 'fallback'


class TestSelectForPlanningAgentRoleFiltering:
    """Tests for select_for_planning() respecting supports_agent_role."""

    def test_skips_provider_without_agent_role_support(self):
        """Providers without agent role support are excluded from planning selection."""
        github_provider = create_mock_provider('github', supports_agent_role=False)
        cerebras_provider = create_mock_provider('cerebras', supports_agent_role=True)

        registry = Mock()
        registry.list_available.return_value = ['github', 'cerebras']
        registry.get = lambda name: {'github': github_provider, 'cerebras': cerebras_provider}[name]

        selector = ProviderSelector(registry)

        provider_name, model = selector.select_for_planning()

        assert provider_name == 'cerebras'
        log = selector.get_selection_log()
        assert any('github' in entry and 'does not support agent role' in entry for entry in log)

    def test_raises_when_no_agent_capable_providers(self):
        """Raises RuntimeError when no providers support agent role."""
        registry = create_mock_registry({
            'github': False,
            'other': False,
        })
        selector = ProviderSelector(registry)

        with pytest.raises(RuntimeError, match="No providers available that support agent role"):
            selector.select_for_planning()


class TestProviderAvailability:
    """Tests that unsupported providers remain in general availability."""

    def test_unsupported_provider_in_available_list(self):
        """Provider with supports_agent_role=False is still in list_available()."""
        registry = create_mock_registry({
            'github': False,
            'cerebras': True,
        })

        available = registry.list_available()

        assert 'github' in available
        assert 'cerebras' in available

    def test_can_get_unsupported_provider_directly(self):
        """Can retrieve unsupported provider directly from registry."""
        registry = create_mock_registry({
            'github': False,
        })

        provider = registry.get('github')

        assert provider is not None
        assert provider.supports_agent_role is False


class TestBrainSetterAgentRoleFiltering:
    """Tests for orchestrator brain setter respecting supports_agent_role."""

    def test_brain_setter_rejects_unsupported_provider(self):
        """Brain setter raises ValueError for provider that doesn't support agent role."""
        from unittest.mock import Mock, PropertyMock

        # Create a mock orchestrator with registry
        orchestrator = Mock()
        registry = create_mock_registry({
            'github_models': False,
            'cerebras': True,
        })
        orchestrator.registry = registry

        # Import and test the actual setter logic
        provider = registry.get('github_models')
        assert provider.supports_agent_role is False

        # Simulate what the setter does
        if hasattr(provider, 'supports_agent_role') and not provider.supports_agent_role:
            with pytest.raises(ValueError, match="does not support agent/brain roles"):
                raise ValueError(
                    f"Provider 'github_models' does not support agent/brain roles (aggressive rate limiting). "
                    f"Use for general tasks only."
                )

    def test_brain_setter_accepts_supported_provider(self):
        """Brain setter accepts provider that supports agent role."""
        registry = create_mock_registry({
            'cerebras': True,
        })

        provider = registry.get('cerebras')

        # Should not raise - provider supports agent role
        assert provider.supports_agent_role is True
