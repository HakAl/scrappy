"""
Tests for LiteLLMKeyValidator.

Tests the API key validation functionality with mocked litellm calls.
"""

from unittest.mock import patch, MagicMock

from scrappy.orchestrator.key_validator import LiteLLMKeyValidator, create_key_validator


class TestLiteLLMKeyValidator:
    """Tests for LiteLLMKeyValidator.validate_key method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = LiteLLMKeyValidator()

    @patch("litellm.completion")
    def test_valid_key_returns_true(self, mock_completion):
        """Valid API key returns (True, None)."""
        mock_completion.return_value = MagicMock()

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key_123",
        )

        assert is_valid is True
        assert error is None
        mock_completion.assert_called_once()

    @patch("litellm.completion")
    def test_default_timeout_is_ten_seconds(self, mock_completion):
        """Default timeout is 10 seconds."""
        mock_completion.return_value = MagicMock()

        self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="test_key",
        )

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["timeout"] == 10.0

    @patch("litellm.completion")
    def test_401_error_returns_invalid_key(self, mock_completion):
        """401 error returns user-friendly invalid key message."""
        mock_completion.side_effect = Exception("Error 401: Unauthorized")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="bad_key",
        )

        assert is_valid is False
        assert error == "Invalid API key"

    @patch("litellm.completion")
    def test_unauthorized_error_returns_invalid_key(self, mock_completion):
        """'unauthorized' in error returns invalid key message."""
        mock_completion.side_effect = Exception("Request unauthorized")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="bad_key",
        )

        assert is_valid is False
        assert error == "Invalid API key"

    @patch("litellm.completion")
    def test_403_error_returns_permissions_message(self, mock_completion):
        """403 error returns permissions message."""
        mock_completion.side_effect = Exception("Error 403: Access denied")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="limited_key",
        )

        assert is_valid is False
        assert error == "API key does not have required permissions"

    @patch("litellm.completion")
    def test_forbidden_error_returns_permissions_message(self, mock_completion):
        """'forbidden' in error returns permissions message."""
        mock_completion.side_effect = Exception("Access forbidden for this model")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="limited_key",
        )

        assert is_valid is False
        assert error == "API key does not have required permissions"

    @patch("litellm.completion")
    def test_404_error_returns_model_not_found(self, mock_completion):
        """404 error returns model not found message."""
        mock_completion.side_effect = Exception("Error 404: Model not available")

        is_valid, error = self.validator.validate_key(
            model="groq/nonexistent-model",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == "Model not found or not accessible"

    @patch("litellm.completion")
    def test_not_found_error_returns_model_not_found(self, mock_completion):
        """'not found' in error returns model not found message."""
        mock_completion.side_effect = Exception("The requested model was not found")

        is_valid, error = self.validator.validate_key(
            model="groq/nonexistent-model",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == "Model not found or not accessible"

    @patch("litellm.completion")
    def test_timeout_error_returns_timeout_message(self, mock_completion):
        """Timeout error returns retry message."""
        mock_completion.side_effect = Exception("Request timeout after 10s")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == "Request timed out - try again"

    @patch("litellm.completion")
    def test_connection_error_returns_network_message(self, mock_completion):
        """Connection error returns network message."""
        mock_completion.side_effect = Exception("Connection refused")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == "Connection error - check network"

    @patch("litellm.completion")
    def test_429_rate_limit_returns_valid(self, mock_completion):
        """429 rate limit error still means key is valid."""
        mock_completion.side_effect = Exception("Error 429: Rate limit exceeded")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is True
        assert error is None

    @patch("litellm.completion")
    def test_rate_limit_text_returns_valid(self, mock_completion):
        """'rate limit' in error text still means key is valid."""
        mock_completion.side_effect = Exception("You have exceeded the rate limit")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is True
        assert error is None

    @patch("litellm.completion")
    def test_generic_error_returns_truncated_message(self, mock_completion):
        """Generic error returns truncated error message."""
        mock_completion.side_effect = Exception("Some unexpected error occurred")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == "Validation failed: Some unexpected error occurred"

    @patch("litellm.completion")
    def test_long_error_is_truncated(self, mock_completion):
        """Long error messages are truncated to 100 chars."""
        long_error = "x" * 200
        mock_completion.side_effect = Exception(long_error)

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == f"Validation failed: {'x' * 100}"
        assert len(error) == len("Validation failed: ") + 100

    @patch("litellm.completion")
    def test_case_insensitive_error_matching(self, mock_completion):
        """Error matching is case insensitive."""
        mock_completion.side_effect = Exception("UNAUTHORIZED ACCESS")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="bad_key",
        )

        assert is_valid is False
        assert error == "Invalid API key"

    @patch("litellm.completion")
    def test_mixed_case_connection_error(self, mock_completion):
        """Mixed case connection error is detected."""
        mock_completion.side_effect = Exception("CONNECTION Error: host unreachable")

        is_valid, error = self.validator.validate_key(
            model="groq/llama-3.1-8b-instant",
            api_key="valid_key",
        )

        assert is_valid is False
        assert error == "Connection error - check network"


class TestCreateKeyValidator:
    """Tests for create_key_validator factory function."""

    def test_returns_validator_instance(self):
        """Factory returns LiteLLMKeyValidator instance."""
        validator = create_key_validator()

        assert isinstance(validator, LiteLLMKeyValidator)

    def test_returns_new_instance_each_time(self):
        """Factory returns a new instance each time."""
        validator1 = create_key_validator()
        validator2 = create_key_validator()

        assert validator1 is not validator2


