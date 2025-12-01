"""
Configuration validator implementation.

Provides clear, actionable error messages for configuration validation failures.
"""

from typing import Any, Dict, Optional


class ConfigValidator:
    """
    Validates configuration values with clear error messages.

    Implements ConfigValidatorProtocol.
    """

    def validate_required(
        self,
        config: Dict[str, Any],
        required_keys: list[str]
    ) -> None:
        """
        Validate that required keys are present.

        Args:
            config: Configuration dictionary
            required_keys: List of required keys

        Raises:
            ValueError: If required keys are missing
        """
        missing = [key for key in required_keys if key not in config]
        if missing:
            raise ValueError(
                f"Missing required configuration keys: {', '.join(missing)}\n"
                f"Please provide values for: {', '.join(missing)}"
            )

    def validate_type(
        self,
        value: Any,
        expected_type: type,
        field_name: str
    ) -> None:
        """
        Validate that value is of expected type.

        Args:
            value: Value to validate
            expected_type: Expected type
            field_name: Name of field

        Raises:
            TypeError: If value is not of expected type
        """
        if not isinstance(value, expected_type):
            raise TypeError(
                f"Configuration field '{field_name}' must be {expected_type.__name__}, "
                f"got {type(value).__name__}: {value!r}\n"
                f"Please provide a valid {expected_type.__name__} value."
            )

    def validate_range(
        self,
        value: int | float,
        min_value: Optional[int | float],
        max_value: Optional[int | float],
        field_name: str
    ) -> None:
        """
        Validate that numeric value is within range.

        Args:
            value: Value to validate
            min_value: Minimum allowed value (inclusive)
            max_value: Maximum allowed value (inclusive)
            field_name: Name of field

        Raises:
            ValueError: If value is out of range
        """
        if min_value is not None and value < min_value:
            raise ValueError(
                f"Configuration field '{field_name}' must be >= {min_value}, "
                f"got {value}\n"
                f"Please provide a value >= {min_value}."
            )

        if max_value is not None and value > max_value:
            raise ValueError(
                f"Configuration field '{field_name}' must be <= {max_value}, "
                f"got {value}\n"
                f"Please provide a value <= {max_value}."
            )

    def validate_one_of(
        self,
        value: Any,
        allowed_values: list[Any],
        field_name: str
    ) -> None:
        """
        Validate that value is one of allowed values.

        Args:
            value: Value to validate
            allowed_values: List of allowed values
            field_name: Name of field

        Raises:
            ValueError: If value is not in allowed values
        """
        if value not in allowed_values:
            raise ValueError(
                f"Configuration field '{field_name}' must be one of: "
                f"{', '.join(repr(v) for v in allowed_values)}, "
                f"got {value!r}\n"
                f"Please use one of the allowed values."
            )

    def validate_positive(
        self,
        value: int | float,
        field_name: str
    ) -> None:
        """
        Validate that value is positive (> 0).

        Args:
            value: Value to validate
            field_name: Name of field

        Raises:
            ValueError: If value is not positive
        """
        self.validate_range(value, min_value=0.0001, max_value=None, field_name=field_name)

    def validate_non_negative(
        self,
        value: int | float,
        field_name: str
    ) -> None:
        """
        Validate that value is non-negative (>= 0).

        Args:
            value: Value to validate
            field_name: Name of field

        Raises:
            ValueError: If value is negative
        """
        self.validate_range(value, min_value=0, max_value=None, field_name=field_name)

    def validate_non_empty(
        self,
        value: str,
        field_name: str
    ) -> None:
        """
        Validate that string is not empty.

        Args:
            value: Value to validate
            field_name: Name of field

        Raises:
            ValueError: If value is empty
        """
        if not value or not value.strip():
            raise ValueError(
                f"Configuration field '{field_name}' cannot be empty.\n"
                f"Please provide a non-empty value."
            )

    def validate_path_exists(
        self,
        value: str,
        field_name: str,
        must_be_file: bool = False,
        must_be_dir: bool = False
    ) -> None:
        """
        Validate that path exists.

        Args:
            value: Path to validate
            field_name: Name of field
            must_be_file: If True, path must be a file
            must_be_dir: If True, path must be a directory

        Raises:
            ValueError: If path doesn't exist or has wrong type
        """
        import os

        if not os.path.exists(value):
            raise ValueError(
                f"Configuration field '{field_name}' path does not exist: {value}\n"
                f"Please provide a valid path."
            )

        if must_be_file and not os.path.isfile(value):
            raise ValueError(
                f"Configuration field '{field_name}' must be a file, "
                f"got directory: {value}\n"
                f"Please provide a file path."
            )

        if must_be_dir and not os.path.isdir(value):
            raise ValueError(
                f"Configuration field '{field_name}' must be a directory, "
                f"got file: {value}\n"
                f"Please provide a directory path."
            )

    def validate_url(
        self,
        value: str,
        field_name: str,
        require_https: bool = False
    ) -> None:
        """
        Validate that value is a valid URL.

        Args:
            value: URL to validate
            field_name: Name of field
            require_https: If True, URL must use HTTPS

        Raises:
            ValueError: If URL is invalid
        """
        import re

        # Basic URL pattern
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$',
            re.IGNORECASE
        )

        if not url_pattern.match(value):
            raise ValueError(
                f"Configuration field '{field_name}' must be a valid URL, "
                f"got: {value}\n"
                f"Please provide a valid URL (e.g., https://example.com)."
            )

        if require_https and not value.startswith('https://'):
            raise ValueError(
                f"Configuration field '{field_name}' must use HTTPS, "
                f"got: {value}\n"
                f"Please provide an HTTPS URL."
            )


# Default validator instance
default_validator = ConfigValidator()
