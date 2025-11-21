"""
Tests for ProviderRegistrar - provider auto-registration functionality.

TDD tests written before implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict

from src.orchestrator.output import CapturingOutput
from src.providers import ProviderRegistry


class TestProviderRegistrarInit:
    """Test ProviderRegistrar initialization."""

    def test_init_stores_registry(self):
        """Registrar should store the registry reference."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()

        registrar = ProviderRegistrar(registry, output)

        assert registrar.registry is registry

    def test_init_stores_output(self):
        """Registrar should store the output interface reference."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()

        registrar = ProviderRegistrar(registry, output)

        assert registrar.output is output


class TestAutoRegisterAll:
    """Test auto_register_all method behavior."""

    def test_returns_dict_with_provider_status(self):
        """auto_register_all should return dict mapping provider names to success status."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=Mock()),
            CerebrasProvider=Mock(return_value=Mock()),
            GroqProvider=Mock(return_value=Mock()),
            GeminiProvider=Mock(return_value=Mock()),
            CohereProvider=Mock(return_value=Mock()),
        ):
            result = registrar.auto_register_all()

        assert isinstance(result, dict)
        assert 'github_models' in result
        assert 'cerebras' in result
        assert 'groq' in result
        assert 'gemini' in result
        assert 'cohere' in result

    def test_successful_registration_returns_true(self):
        """Successfully registered provider should have True status."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        mock_provider = Mock()
        mock_provider.name = 'github_models'

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=mock_provider),
            CerebrasProvider=Mock(side_effect=Exception("No API key")),
            GroqProvider=Mock(side_effect=Exception("No API key")),
            GeminiProvider=Mock(side_effect=Exception("No API key")),
            CohereProvider=Mock(side_effect=Exception("No API key")),
        ):
            result = registrar.auto_register_all()

        assert result['github_models'] is True

    def test_failed_registration_returns_false(self):
        """Failed provider registration should have False status."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(side_effect=ValueError("No API key")),
            CerebrasProvider=Mock(side_effect=Exception("No API key")),
            GroqProvider=Mock(side_effect=Exception("No API key")),
            GeminiProvider=Mock(side_effect=Exception("No API key")),
            CohereProvider=Mock(side_effect=Exception("No API key")),
        ):
            result = registrar.auto_register_all()

        assert result['github_models'] is False
        assert result['cerebras'] is False

    def test_all_providers_succeed(self):
        """When all providers register successfully, all should be True."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=make_mock_provider('github_models')),
            CerebrasProvider=Mock(return_value=make_mock_provider('cerebras')),
            GroqProvider=Mock(return_value=make_mock_provider('groq')),
            GeminiProvider=Mock(return_value=make_mock_provider('gemini')),
            CohereProvider=Mock(return_value=make_mock_provider('cohere')),
        ):
            result = registrar.auto_register_all()

        assert all(result.values()), f"Not all providers succeeded: {result}"

    def test_all_providers_fail(self):
        """When all providers fail to register, all should be False."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(side_effect=Exception("No API key")),
            CerebrasProvider=Mock(side_effect=Exception("No API key")),
            GroqProvider=Mock(side_effect=Exception("No API key")),
            GeminiProvider=Mock(side_effect=Exception("No API key")),
            CohereProvider=Mock(side_effect=Exception("No API key")),
        ):
            result = registrar.auto_register_all()

        assert not any(result.values()), f"Some providers succeeded unexpectedly: {result}"

    def test_mixed_success_and_failure(self):
        """Some providers succeed while others fail."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=make_mock_provider('github_models')),
            CerebrasProvider=Mock(return_value=make_mock_provider('cerebras')),
            GroqProvider=Mock(side_effect=Exception("No API key")),
            GeminiProvider=Mock(return_value=make_mock_provider('gemini')),
            CohereProvider=Mock(side_effect=Exception("No API key")),
        ):
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
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=make_mock_provider('github_models')),
            CerebrasProvider=Mock(return_value=make_mock_provider('cerebras')),
            GroqProvider=Mock(return_value=make_mock_provider('groq')),
            GeminiProvider=Mock(side_effect=Exception("fail")),
            CohereProvider=Mock(side_effect=Exception("fail")),
        ):
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
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        registration_order = []

        def track_registration(name):
            def create_provider():
                registration_order.append(name)
                mock = Mock()
                mock.name = name
                return mock
            return create_provider

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=track_registration('github_models'),
            CerebrasProvider=track_registration('cerebras'),
            GroqProvider=track_registration('groq'),
            GeminiProvider=track_registration('gemini'),
            CohereProvider=track_registration('cohere'),
        ):
            registrar.auto_register_all()

        # Order should be: github_models, cerebras, groq, gemini, cohere
        expected_order = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']
        assert registration_order == expected_order


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_registry_exception_during_register(self):
        """Handle exceptions during registry.register call."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = Mock(spec=ProviderRegistry)
        registry.register.side_effect = Exception("Registry error")
        registry.list_available.return_value = []

        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        mock_provider = Mock()
        mock_provider.name = 'github_models'

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=mock_provider),
            CerebrasProvider=Mock(side_effect=Exception("fail")),
            GroqProvider=Mock(side_effect=Exception("fail")),
            GeminiProvider=Mock(side_effect=Exception("fail")),
            CohereProvider=Mock(side_effect=Exception("fail")),
        ):
            result = registrar.auto_register_all()

        # Provider creation succeeded but registration failed
        assert result['github_models'] is False
        error_messages = output.get_by_level('error')
        assert any('GitHub Models' in msg for msg in error_messages)

    def test_can_be_called_multiple_times(self):
        """auto_register_all can be called multiple times."""
        from src.orchestrator.registration import ProviderRegistrar

        registry = ProviderRegistry()
        output = CapturingOutput()
        registrar = ProviderRegistrar(registry, output)

        def make_mock_provider(name):
            mock = Mock()
            mock.name = name
            return mock

        with patch.multiple(
            'src.orchestrator.registration',
            GitHubModelsProvider=Mock(return_value=make_mock_provider('github_models')),
            CerebrasProvider=Mock(side_effect=Exception("fail")),
            GroqProvider=Mock(side_effect=Exception("fail")),
            GeminiProvider=Mock(side_effect=Exception("fail")),
            CohereProvider=Mock(side_effect=Exception("fail")),
        ):
            result1 = registrar.auto_register_all()
            result2 = registrar.auto_register_all()

        # Both calls should return the same structure
        assert result1.keys() == result2.keys()

