"""
Standardized error message formatting for the LLM Agent Team framework.

This module provides consistent error message formats across the codebase.
"""

from typing import Optional, List

from ..exceptions import RateLimitError


class ErrorFormatter:
    """Standardized error message formatting."""

    @staticmethod
    def package_not_installed(package_name: str, pip_name: Optional[str] = None) -> str:
        """
        Format error for missing package.

        Args:
            package_name: Display name of the package
            pip_name: pip install name (defaults to package_name)

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.package_not_installed('groq')
            'groq package not installed. Run: pip install groq'
        """
        pip_name = pip_name or package_name
        return f"{package_name} package not installed. Run: pip install {pip_name}"

    @staticmethod
    def env_var_not_found(var_name: str) -> str:
        """
        Format error for missing environment variable.

        Args:
            var_name: Name of the environment variable

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.env_var_not_found('GROQ_API_KEY')
            'GROQ_API_KEY not found in environment'
        """
        return f"{var_name} not found in environment"

    @staticmethod
    def model_not_supported(model: str, available_models: List[str]) -> str:
        """
        Format error for unsupported model.

        Args:
            model: The requested model name
            available_models: List of available model names

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.model_not_supported('gpt-4', ['llama-3.1-8b', 'mixtral'])
            "Model 'gpt-4' not supported. Available: ['llama-3.1-8b', 'mixtral']"
        """
        return f"Model '{model}' not supported. Available: {available_models}"

    @staticmethod
    def provider_not_available(provider_name: str, available_providers: List[str]) -> str:
        """
        Format error for unavailable provider.

        Args:
            provider_name: The requested provider name
            available_providers: List of available provider names

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.provider_not_available('openai', ['groq', 'cerebras'])
            "Provider 'openai' not available. Available: ['groq', 'cerebras']"
        """
        return f"Provider '{provider_name}' not available. Available: {available_providers}"

    @staticmethod
    def no_providers_available() -> str:
        """
        Format error when no providers are available.

        Returns:
            Formatted error message
        """
        return "No providers available. Check API keys and package installations."

    @staticmethod
    def operation_failed(operation: str, error: Exception) -> str:
        """
        Format error for a failed operation.

        Args:
            operation: Description of the operation
            error: The exception that occurred

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.operation_failed('save session', Exception('disk full'))
            'Failed to save session: disk full'
        """
        return f"Failed to {operation}: {error}"

    @staticmethod
    def tool_not_found(tool_name: str) -> str:
        """
        Format error for missing tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.tool_not_found('web_fetch')
            "Tool 'web_fetch' not found in registry"
        """
        return f"Tool '{tool_name}' not found in registry"

    @staticmethod
    def tool_already_registered(tool_name: str) -> str:
        """
        Format error for duplicate tool registration.

        Args:
            tool_name: Name of the tool

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.tool_already_registered('file_read')
            "Tool 'file_read' is already registered"
        """
        return f"Tool '{tool_name}' is already registered"

    @staticmethod
    def rate_limit_exceeded(provider: str, limit_type: str = "requests") -> str:
        """
        Format error for rate limit exceeded.

        Args:
            provider: Provider name
            limit_type: Type of limit (requests, tokens, etc.)

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.rate_limit_exceeded('groq', 'requests')
            "Rate limit exceeded for groq (requests). Please wait before retrying."
        """
        return f"Rate limit exceeded for {provider} ({limit_type}). Please wait before retrying."

    @staticmethod
    def all_providers_rate_limited(attempted: List[str]) -> str:
        """
        Format error when all providers are rate limited.

        Args:
            attempted: List of attempted provider names

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.all_providers_rate_limited(['gemini-2.0', 'gemini-2.5'])
            "All providers rate limited. Tried: ['gemini-2.0', 'gemini-2.5']"
        """
        return f"All providers rate limited. Tried: {attempted}"

    @staticmethod
    def invalid_json_response(expected_type: str, actual_type: str) -> str:
        """
        Format error for invalid JSON response type.

        Args:
            expected_type: Expected type name
            actual_type: Actual type received

        Returns:
            Formatted error message

        Example:
            >>> ErrorFormatter.invalid_json_response('object', 'list')
            'Expected JSON object, got: list'
        """
        return f"Expected JSON {expected_type}, got: {actual_type}"


# Log level prefixes for consistent formatting
class LogPrefix:
    """Standardized log message prefixes."""

    OK = "[OK]"
    ERROR = "[ERROR]"
    WARNING = "[WARNING]"
    INFO = "[INFO]"
    CONTEXT = "[CONTEXT]"
    DEBUG = "[DEBUG]"

    @staticmethod
    def provider(name: str) -> str:
        """Format provider-specific log prefix."""
        return f"[{name.upper()}]"

    @staticmethod
    def tool(name: str) -> str:
        """Format tool-specific log prefix."""
        return f"[TOOL:{name}]"

    @staticmethod
    def agent(step: int) -> str:
        """Format agent step prefix."""
        return f"[STEP {step}]"


# Convenience functions for common error raising patterns
def raise_package_not_installed(package_name: str, pip_name: Optional[str] = None):
    """Raise ImportError for missing package with standardized message."""
    raise ImportError(ErrorFormatter.package_not_installed(package_name, pip_name))


def raise_env_var_not_found(var_name: str):
    """Raise ValueError for missing environment variable with standardized message."""
    raise ValueError(ErrorFormatter.env_var_not_found(var_name))


def raise_model_not_supported(model: str, available_models: List[str]):
    """Raise ValueError for unsupported model with standardized message."""
    raise ValueError(ErrorFormatter.model_not_supported(model, available_models))


def raise_provider_not_available(provider_name: str, available_providers: List[str]):
    """Raise ValueError for unavailable provider with standardized message."""
    raise ValueError(ErrorFormatter.provider_not_available(provider_name, available_providers))


def raise_no_providers_available():
    """Raise RuntimeError when no providers are available."""
    raise RuntimeError(ErrorFormatter.no_providers_available())


def raise_operation_failed(operation: str, error: Exception):
    """Raise RuntimeError for failed operation with standardized message."""
    raise RuntimeError(ErrorFormatter.operation_failed(operation, error))


def is_rate_limit_error(error: Exception) -> bool:
    """
    Detect if an exception is a rate limit error.

    Checks error message for common rate limit indicators across providers.

    Args:
        error: The exception to check

    Returns:
        True if this appears to be a rate limit error

    Example:
        >>> is_rate_limit_error(Exception("429 Too Many Requests"))
        True
        >>> is_rate_limit_error(Exception("quota exceeded"))
        True
    """
    if isinstance(error, RateLimitError):
        return True

    error_str = str(error).lower()

    # Common rate limit indicators across different providers
    rate_limit_indicators = [
        '429',                      # HTTP status code
        'rate limit',               # Explicit rate limit
        'rate_limit',               # Underscore variant
        'ratelimit',                # No space variant
        'quota',                    # Quota exceeded
        'too many requests',        # Common HTTP message
        'resource exhausted',       # Google/Gemini style
        'resource_exhausted',       # Underscore variant
        'capacity',                 # Capacity limit
        'throttl',                  # Throttling
        'requests per',             # "X requests per minute/day"
        'tokens per',               # Token limits
        'limit exceeded',           # Generic limit exceeded
        'limit_exceeded',           # Underscore variant
    ]

    return any(indicator in error_str for indicator in rate_limit_indicators)
