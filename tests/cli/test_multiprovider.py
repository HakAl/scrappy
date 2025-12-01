"""
Behavior tests for CLI multi-provider operations.

Tests actual behavior of synthesis and delegation modes.
Focuses on:
- User input validation and workflows
- Provider selection and validation
- Multi-provider synthesis
- Direct provider delegation
- Error handling
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from scrappy.cli.multiprovider import CLIMultiProvider
from scrappy.cli.validators import ProviderValidationResult
from tests.helpers import MockIO, make_response


class TestSynthesizeMode:
    """Test multi-provider synthesis functionality."""

    def test_rejects_empty_question(self):
        """Should exit when user provides empty question."""
        orchestrator = MagicMock()
        io = MockIO(inputs=[""])  # Empty question
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        output = io.get_output()
        assert "No question provided" in output

    def test_accepts_all_providers(self):
        """Should query all available providers when user enters 'all'."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic', 'gemini']
        orchestrator.delegate.return_value = make_response("Response", tokens_used=100)
        orchestrator.synthesize.return_value = "Synthesized answer"

        io = MockIO(inputs=["What is AI?", "all"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        # Should have queried all 3 providers
        assert orchestrator.delegate.call_count == 3

    def test_accepts_comma_separated_providers(self):
        """Should query only specified providers from comma-separated list."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic', 'gemini']
        orchestrator.delegate.return_value = make_response("Response", tokens_used=100)
        orchestrator.synthesize.return_value = "Synthesized answer"

        io = MockIO(inputs=["What is AI?", "openai, anthropic"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        # Should have queried only 2 providers
        assert orchestrator.delegate.call_count == 2
        calls = orchestrator.delegate.call_args_list
        providers_called = [call[0][0] for call in calls]
        assert 'openai' in providers_called
        assert 'anthropic' in providers_called
        assert 'gemini' not in providers_called

    def test_filters_invalid_providers(self):
        """Should ignore providers not in available list."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']
        orchestrator.delegate.return_value = make_response("Response", tokens_used=100)
        orchestrator.synthesize.return_value = "Synthesized answer"

        io = MockIO(inputs=["Test question", "openai, invalid, anthropic"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        # Should only call valid providers
        assert orchestrator.delegate.call_count == 2
        calls = orchestrator.delegate.call_args_list
        providers_called = [call[0][0] for call in calls]
        assert 'invalid' not in providers_called

    def test_requires_minimum_two_providers(self):
        """Should warn when fewer than 2 providers selected."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']

        io = MockIO(inputs=["Test question", "openai"])  # Only 1 provider
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        output = io.get_output()
        assert "at least 2 providers" in output.lower()
        # Should not have called delegate
        orchestrator.delegate.assert_not_called()

    def test_handles_provider_errors_gracefully(self):
        """Should continue synthesis even if some providers fail."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic', 'gemini']

        # First call succeeds, second fails, third succeeds
        orchestrator.delegate.side_effect = [
            make_response("Response 1", tokens_used=100),
            Exception("API error"),
            make_response("Response 2", tokens_used=150)
        ]
        orchestrator.synthesize.return_value = "Synthesized from 2 responses"

        io = MockIO(inputs=["Test question", "all"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        output = io.get_output()
        # Should show error for failed provider
        assert "Error" in output
        # Should still synthesize from successful responses
        orchestrator.synthesize.assert_called_once()

    def test_requires_minimum_two_successful_responses(self):
        """Should warn when fewer than 2 providers respond successfully."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']

        # First succeeds, second fails
        orchestrator.delegate.side_effect = [
            make_response("Response", tokens_used=100),
            Exception("API error")
        ]

        io = MockIO(inputs=["Test question", "all"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        output = io.get_output()
        assert "Not enough responses for synthesis" in output
        # Should not call synthesize
        orchestrator.synthesize.assert_not_called()

    def test_displays_synthesis_result(self):
        """Should display synthesized response to user."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']
        orchestrator.delegate.return_value = make_response("Provider response", tokens_used=100)
        orchestrator.synthesize.return_value = "This is the synthesized answer"

        io = MockIO(inputs=["What is AI?", "all"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        output = io.get_output()
        assert "Synthesized Response" in output
        assert "This is the synthesized answer" in output

    def test_adds_discovery_to_working_memory(self):
        """Should record synthesis in working memory."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']
        orchestrator.delegate.return_value = make_response("Response", tokens_used=100)
        orchestrator.synthesize.return_value = "Synthesized"

        io = MockIO(inputs=["What is AI?", "all"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.synthesize_mode()

        # Should have recorded discovery
        orchestrator.working_memory.add_discovery.assert_called_once()
        call_args = orchestrator.working_memory.add_discovery.call_args[0]
        assert "Synthesized 2 provider responses" in call_args[0]
        assert "synthesis" == call_args[1]


class TestDelegateMode:
    """Test direct provider delegation functionality."""

    @patch('scrappy.cli.multiprovider.validate_provider')
    def test_delegates_with_args(self, mock_validate):
        """Should parse provider and prompt from args string."""
        mock_validate.return_value = ProviderValidationResult(
            is_valid=True,
            provider='openai',
            error=None
        )

        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']
        orchestrator.delegate.return_value = make_response(
            "Response from provider",
            model="gpt-4",
            tokens_used=150
        )

        io = MockIO()
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("openai What is AI?")

        # Should have called delegate with correct provider and prompt
        orchestrator.delegate.assert_called_once_with('openai', 'What is AI?')
        output = io.get_output()
        assert "Response from provider" in output
        assert "150 tokens" in output

    @patch('scrappy.cli.multiprovider.validate_provider')
    def test_prompts_interactively_when_no_args(self, mock_validate):
        """Should prompt for provider and prompt when args is empty."""
        mock_validate.return_value = ProviderValidationResult(
            is_valid=True,
            provider='openai',
            error=None
        )

        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai']
        orchestrator.delegate.return_value = make_response("Response", tokens_used=100)

        io = MockIO(inputs=["openai", "Test prompt"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("")

        # Should have used inputs
        assert orchestrator.delegate.called
        call_args = orchestrator.delegate.call_args[0]
        assert call_args[0] == 'openai'
        assert call_args[1] == 'Test prompt'

    def test_rejects_missing_prompt(self):
        """Should show usage when only provider provided."""
        orchestrator = MagicMock()
        io = MockIO()
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("openai")  # Missing prompt

        output = io.get_output()
        assert "Usage:" in output
        # Should not have called delegate
        orchestrator.delegate.assert_not_called()

    def test_rejects_empty_provider(self):
        """Should warn when provider is empty."""
        orchestrator = MagicMock()
        io = MockIO(inputs=["", "Some prompt"])
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("")

        output = io.get_output()
        assert "required" in output.lower()
        orchestrator.delegate.assert_not_called()

    def test_rejects_empty_prompt(self):
        """Should warn when prompt is empty."""
        orchestrator = MagicMock()
        io = MockIO(inputs=["openai", ""])
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("")

        output = io.get_output()
        assert "required" in output.lower()
        orchestrator.delegate.assert_not_called()

    def test_validates_provider_availability(self):
        """Should check if provider is available before delegating."""
        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai', 'anthropic']

        io = MockIO()
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("invalid_provider What is AI?")

        output = io.get_output()
        # Should show error from validation
        assert any(word in output.lower() for word in ['error', 'invalid', 'unknown'])
        # Should not have called delegate
        orchestrator.delegate.assert_not_called()

    @patch('scrappy.cli.multiprovider.validate_provider')
    def test_displays_response_metadata(self, mock_validate):
        """Should display model, tokens, and latency info."""
        mock_validate.return_value = ProviderValidationResult(
            is_valid=True,
            provider='openai',
            error=None
        )

        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai']

        response = make_response("AI answer", model="gpt-4-turbo", tokens_used=250)
        response.latency_ms = 1500.5
        orchestrator.delegate.return_value = response

        io = MockIO()
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("openai What is AI?")

        output = io.get_output()
        assert "gpt-4-turbo" in output
        assert "250 tokens" in output
        assert "1500" in output or "1501ms" in output  # May round

    @patch('scrappy.cli.multiprovider.validate_provider')
    def test_handles_delegation_error(self, mock_validate):
        """Should display error when delegation fails."""
        mock_validate.return_value = ProviderValidationResult(
            is_valid=True,
            provider='openai',
            error=None
        )

        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai']
        orchestrator.delegate.side_effect = Exception("API rate limit exceeded")

        io = MockIO()
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("openai Test prompt")

        output = io.get_output()
        assert "Error" in output
        assert "rate limit" in output.lower()

    @patch('scrappy.cli.multiprovider.validate_provider')
    def test_adds_delegation_to_working_memory(self, mock_validate):
        """Should record delegation in working memory."""
        mock_validate.return_value = ProviderValidationResult(
            is_valid=True,
            provider='openai',
            error=None
        )

        orchestrator = MagicMock()
        orchestrator.providers.list_available.return_value = ['openai']
        orchestrator.delegate.return_value = make_response("Response", tokens_used=175)

        io = MockIO()
        handler = CLIMultiProvider(orchestrator, io)

        handler.delegate_mode("openai What is AI?")

        # Should have recorded discovery
        orchestrator.working_memory.add_discovery.assert_called_once()
        call_args = orchestrator.working_memory.add_discovery.call_args[0]
        assert "Delegated" in call_args[0]
        assert "openai" in call_args[0]
        assert "175 tokens" in call_args[0]
        assert "delegation" == call_args[1]
