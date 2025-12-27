"""
Lightweight API key validator with lazy imports.

Provides key validation without requiring the full LLMService.
litellm is only imported when validate_key() is called, enabling
instant wizard startup.

This module exists to break the import chain:
- SetupWizard needs key validation
- Full LLMService imports litellm at module level (via callbacks)
- litellm import takes ~2 seconds
- By using this lightweight validator, wizard can start instantly
"""

from typing import Optional


class LiteLLMKeyValidator:
    """
    Lightweight API key validator using lazy litellm imports.

    Unlike LLMService which imports litellm at module level,
    this class only imports litellm when validate_key() is called.
    This enables instant wizard startup.

    Usage:
        validator = LiteLLMKeyValidator()
        is_valid, error = validator.validate_key("groq/llama-3.1-8b", "gsk_...")
    """

    def validate_key(
        self,
        model: str,
        api_key: str,
        timeout: float = 10.0,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an API key by making a minimal completion call.

        Imports litellm lazily to avoid startup delay.

        Args:
            model: LiteLLM model ID (e.g., "groq/llama-3.1-8b-instant")
            api_key: API key to validate
            timeout: Timeout in seconds

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Lazy import - only pay the cost when actually validating
        import litellm

        try:
            litellm.completion(
                model=model,
                api_key=api_key,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                timeout=timeout,
            )
            return True, None

        except Exception as e:
            error_str = str(e)
            error_lower = error_str.lower()

            # Parse common error patterns for user-friendly messages
            if "401" in error_str or "unauthorized" in error_lower:
                return False, "Invalid API key"
            if "403" in error_str or "forbidden" in error_lower:
                return False, "API key does not have required permissions"
            if "404" in error_str or "not found" in error_lower:
                return False, "Model not found or not accessible"
            if "timeout" in error_lower:
                return False, "Request timed out - try again"
            if "connection" in error_lower:
                return False, "Connection error - check network"
            if "rate limit" in error_lower or "429" in error_str:
                # Rate limit during validation still means key is valid
                return True, None

            # Generic error
            return False, f"Validation failed: {error_str[:100]}"


def create_key_validator() -> LiteLLMKeyValidator:
    """
    Factory function for creating a key validator.

    Returns:
        LiteLLMKeyValidator instance
    """
    return LiteLLMKeyValidator()
