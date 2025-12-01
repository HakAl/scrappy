"""
Tests for ProviderRegistrar - provider auto-registration functionality.

TDD tests written before implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict

from scrappy.orchestrator.output import CapturingOutput
from scrappy.orchestrator.provider_definitions import ProviderDefinition
from scrappy.providers import ProviderRegistry


def make_test_providers(provider_classes: Dict[str, Mock]) -> Dict[str, ProviderDefinition]:
    """Create a PROVIDERS dict for testing with mock provider classes."""
    providers = {}
    for name, mock_class in provider_classes.items():
        providers[name] = ProviderDefinition(
            quota='test quota',
            description='test description',
            env_var=f'{name.upper()}_API_KEY',
            console_url='test.com',
            provider_class=mock_class,
            priority=list(provider_classes.keys()).index(name),
        )
    return providers


def make_mock_config_service(available_keys: Dict[str, str]) -> Mock:
    """Create a mock config service that returns specified keys."""
    mock_service = Mock()
    mock_service.get_key = lambda key: available_keys.get(key)
    return mock_service


class TestProviderRegistrarInit:
    """Test ProviderRegistrar initialization."""

    def test_init_stores_registry(self):
        """Registrar should store the registry reference."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()

        registrar = ProviderRegistrar(registry, output)

        assert registrar.registry is registry

    def test_init_stores_output(self):
        """Registrar should store the output interface reference."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()

        registrar = ProviderRegistrar(registry, output)

        assert registrar.output is output


class TestAutoRegisterAll:
    """Test auto_register_all method behavior."""

    def test_returns_dict_with_provider_status(self):
        """auto_register_all should return dict mapping provider names to success status."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        mock_classes = {
            'github_models': Mock(return_value=make_mock_provider('github_models')),
            'cerebras': Mock(return_value=make_mock_provider('cerebras')),
            'groq': Mock(return_value=make_mock_provider('groq')),
            'gemini': Mock(return_value=make_mock_provider('gemini')),
            'cohere': Mock(return_value=make_mock_provider('cohere')),
        }
        test_providers = make_test_providers(mock_classes)

        # All providers have API keys
        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
            'GROQ_API_KEY': 'key3',
            'GEMINI_API_KEY': 'key4',
            'COHERE_API_KEY': 'key5',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        assert isinstance(result, dict)
        assert 'github_models' in result
        assert 'cerebras' in result
        assert 'groq' in result
        assert 'gemini' in result
        assert 'cohere' in result

    def test_successful_registration_returns_true(self):
        """Successfully registered provider should have True status."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        mock_provider = Mock()
        mock_provider.name = 'github_models'

        mock_classes = {
            'github_models': Mock(return_value=mock_provider),
            'cerebras': Mock(side_effect=Exception("Provider error")),
        }
        test_providers = make_test_providers(mock_classes)

        # Only github_models has API key, cerebras has key but provider fails
        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        assert result['github_models'] is True

    def test_failed_registration_returns_false(self):
        """Failed provider registration should have False status."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        mock_classes = {
            'github_models': Mock(side_effect=ValueError("Provider error")),
            'cerebras': Mock(side_effect=Exception("Provider error")),
        }
        test_providers = make_test_providers(mock_classes)

        # Both have API keys but providers fail
        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        assert result['github_models'] is False
        assert result['cerebras'] is False

    def test_all_providers_succeed(self):
        """When all providers register successfully, all should be True."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        mock_classes = {
            'github_models': Mock(return_value=make_mock_provider('github_models')),
            'cerebras': Mock(return_value=make_mock_provider('cerebras')),
            'groq': Mock(return_value=make_mock_provider('groq')),
            'gemini': Mock(return_value=make_mock_provider('gemini')),
            'cohere': Mock(return_value=make_mock_provider('cohere')),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
            'GROQ_API_KEY': 'key3',
            'GEMINI_API_KEY': 'key4',
            'COHERE_API_KEY': 'key5',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        assert all(result.values()), f"Not all providers succeeded: {result}"

    def test_all_providers_fail(self):
        """When all providers fail to register, all should be False."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        mock_classes = {
            'github_models': Mock(side_effect=Exception("Provider error")),
            'cerebras': Mock(side_effect=Exception("Provider error")),
            'groq': Mock(side_effect=Exception("Provider error")),
            'gemini': Mock(side_effect=Exception("Provider error")),
            'cohere': Mock(side_effect=Exception("Provider error")),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
            'GROQ_API_KEY': 'key3',
            'GEMINI_API_KEY': 'key4',
            'COHERE_API_KEY': 'key5',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        assert not any(result.values()), f"Some providers succeeded unexpectedly: {result}"

    def test_mixed_success_and_failure(self):
        """Some providers succeed while others fail."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        mock_classes = {
            'github_models': Mock(return_value=make_mock_provider('github_models')),
            'cerebras': Mock(return_value=make_mock_provider('cerebras')),
            'groq': Mock(side_effect=Exception("Provider error")),
            'gemini': Mock(return_value=make_mock_provider('gemini')),
            'cohere': Mock(side_effect=Exception("Provider error")),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
            'GROQ_API_KEY': 'key3',
            'GEMINI_API_KEY': 'key4',
            'COHERE_API_KEY': 'key5',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        assert result['github_models'] is True
        assert result['cerebras'] is True
        assert result['groq'] is False
        assert result['gemini'] is True
        assert result['cohere'] is False



class TestProviderRegistration:
    """Test that providers are actually registered in the registry."""

    def test_multiple_providers_registered(self):
        """Multiple successful providers should all be registered."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        mock_classes = {
            'github_models': Mock(return_value=make_mock_provider('github_models')),
            'cerebras': Mock(return_value=make_mock_provider('cerebras')),
            'groq': Mock(return_value=make_mock_provider('groq')),
            'gemini': Mock(side_effect=Exception("Provider error")),
            'cohere': Mock(side_effect=Exception("Provider error")),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
            'GROQ_API_KEY': 'key3',
            'GEMINI_API_KEY': 'key4',
            'COHERE_API_KEY': 'key5',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            registrar.auto_register_all()

        available = registry.list_available()
        assert 'github_models' in available
        assert 'cerebras' in available
        assert 'groq' in available
        assert 'gemini' not in available
        assert 'cohere' not in available


class TestRegistrationOrder:
    """Test that providers are registered in the correct priority order."""

    def test_registration_order_is_documented(self):
        """Providers should be registered in documented priority order."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        registration_order = []

        def track_registration(name):
            def create_provider(*args, **kwargs):
                registration_order.append(name)
                mock = Mock()
                mock.name = name
                return mock
            return create_provider

        # Use ordered dict-like structure to ensure order
        mock_classes = {
            'github_models': track_registration('github_models'),
            'cerebras': track_registration('cerebras'),
            'groq': track_registration('groq'),
            'gemini': track_registration('gemini'),
            'cohere': track_registration('cohere'),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
            'GROQ_API_KEY': 'key3',
            'GEMINI_API_KEY': 'key4',
            'COHERE_API_KEY': 'key5',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            registrar.auto_register_all()

        # Order should match the order in the test_providers dict
        expected_order = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']
        assert registration_order == expected_order


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_registry_exception_during_register(self):
        """Handle exceptions during registry.register call."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        registry = Mock(spec=ProviderRegistry)
        registry.register.side_effect = Exception("Registry error")
        registry.list_available.return_value = []

        mock_provider = Mock()
        mock_provider.name = 'github_models'

        mock_classes = {
            'github_models': Mock(return_value=mock_provider),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
        })

        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result = registrar.auto_register_all()

        # Provider creation succeeded but registration failed
        assert result['github_models'] is False

    def test_can_be_called_multiple_times(self):
        """auto_register_all can be called multiple times."""
        from scrappy.orchestrator.registration import ProviderRegistrar

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        mock_classes = {
            'github_models': Mock(return_value=make_mock_provider('github_models')),
            'cerebras': Mock(side_effect=Exception("Provider error")),
        }
        test_providers = make_test_providers(mock_classes)

        config_service = make_mock_config_service({
            'GITHUB_MODELS_API_KEY': 'key1',
            'CEREBRAS_API_KEY': 'key2',
        })

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output, config_service=config_service)

        with patch('scrappy.orchestrator.registration.PROVIDERS', test_providers):
            result1 = registrar.auto_register_all()
            result2 = registrar.auto_register_all()

        # Both calls should return the same structure
        assert result1.keys() == result2.keys()

