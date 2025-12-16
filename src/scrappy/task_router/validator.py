"""
Input validation for task router.

This module provides defensive validation at system boundaries.
Following the fail-fast principle, we validate inputs early and
provide meaningful error messages.
"""
from typing import Optional, Tuple

from .classifier import TaskType
from scrappy.infrastructure.validation import validate_user_input as validate_user_input_impl


class InputValidator:
    """
    Validates inputs at system boundaries.

    Benefits:
    1. Fail fast - catch errors early
    2. Security - prevent injection attacks, DoS
    3. Better error messages - guide users to correct usage
    4. Type safety - validate enums and ranges
    """

    def __init__(self, max_length: int = 10000):
        """
        Initialize input validator.

        Args:
            max_length: Maximum allowed input length (DoS protection)
        """
        self.max_length = max_length

    def validate_user_input(self, user_input: object) -> Tuple[bool, Optional[str]]:
        """
        Validate user input string.

        Uses centralized validation from infrastructure.validation module
        which handles null bytes, control characters, and length limits.

        Args:
            user_input: The user's input to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid
        """
        # Check for None
        if user_input is None:
            return False, "User input cannot be None"

        # Check type
        if not isinstance(user_input, str):
            return False, f"User input must be a string, got {type(user_input).__name__}"

        # Use centralized validation for sanitization and security checks
        result = validate_user_input_impl(user_input, context="chat", max_length=self.max_length)
        if not result.is_valid:
            return False, result.error

        return True, None

    def validate_confidence(self, confidence: object) -> Tuple[bool, Optional[str]]:
        """
        Validate confidence value.

        Args:
            confidence: The confidence score to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check type
        if not isinstance(confidence, (int, float)):
            return False, f"Confidence must be a number, got {type(confidence).__name__}"

        # Check range
        if confidence < 0.0 or confidence > 1.0:
            return False, f"Confidence must be between 0.0 and 1.0, got {confidence}"

        return True, None

    def validate_task_type(self, task_type: object) -> Tuple[bool, Optional[str]]:
        """
        Validate task type.

        Args:
            task_type: The task type to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for None
        if task_type is None:
            return False, "Task type cannot be None"

        # Check type
        if not isinstance(task_type, TaskType):
            return False, f"Task type must be a TaskType enum, got {type(task_type).__name__}"

        return True, None

    def validate_complexity(self, complexity: object) -> Tuple[bool, Optional[str]]:
        """
        Validate complexity score.

        Args:
            complexity: The complexity score to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check type
        if not isinstance(complexity, int):
            return False, f"Complexity must be an integer, got {type(complexity).__name__}"

        # Check range
        if complexity < 1 or complexity > 10:
            return False, f"Complexity must be between 1 and 10, got {complexity}"

        return True, None

    def validate_provider_name(self, provider: object) -> Tuple[bool, Optional[str]]:
        """
        Validate provider name.

        Args:
            provider: The provider name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if provider is None:
            # None is allowed (means no provider specified)
            return True, None

        # Check type
        if not isinstance(provider, str):
            return False, f"Provider name must be a string or None, got {type(provider).__name__}"

        # Check not empty
        if not provider.strip():
            return False, "Provider name cannot be empty string"

        return True, None

    def validate_all(
        self,
        user_input: str,
        confidence: Optional[float] = None,
        task_type: Optional[TaskType] = None,
        complexity: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate multiple fields at once.

        Args:
            user_input: User input to validate (required)
            confidence: Confidence to validate (optional)
            task_type: Task type to validate (optional)
            complexity: Complexity to validate (optional)

        Returns:
            Tuple of (is_valid, error_message)
            Returns first error found, or (True, None) if all valid
        """
        # Validate user input (required)
        valid, error = self.validate_user_input(user_input)
        if not valid:
            return False, error

        # Validate confidence if provided
        if confidence is not None:
            valid, error = self.validate_confidence(confidence)
            if not valid:
                return False, error

        # Validate task type if provided
        if task_type is not None:
            valid, error = self.validate_task_type(task_type)
            if not valid:
                return False, error

        # Validate complexity if provided
        if complexity is not None:
            valid, error = self.validate_complexity(complexity)
            if not valid:
                return False, error

        return True, None


class ValidationError(Exception):
    """
    Raised when validation fails.

    This is a domain-specific exception that provides clear
    error messages for validation failures.
    """

    def __init__(self, message: str, field: Optional[str] = None):
        """
        Initialize validation error.

        Args:
            message: Error message describing the validation failure
            field: Optional field name that failed validation
        """
        self.field = field
        super().__init__(message)
