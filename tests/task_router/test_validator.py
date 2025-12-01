import pytest
from scrappy.task_router.validator import InputValidator, TaskType, ValidationError

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def validator():
    """Returns a default InputValidator instance."""
    return InputValidator()

@pytest.fixture
def strict_validator():
    """Returns a validator with a short max length for boundary testing."""
    return InputValidator(max_length=10)

# -----------------------------------------------------------------------------
# User Input Validation Tests
# -----------------------------------------------------------------------------

class TestUserInput:
    def test_valid_input(self, validator):
        """Test standard valid string input."""
        valid, error = validator.validate_user_input("List my files")
        assert valid is True
        assert error is None

    @pytest.mark.parametrize("invalid_input, expected_msg_part", [
        (None, "cannot be None"),
        (123, "must be a string"),
        (["list"], "must be a string"),
        ("", "empty or whitespace"),
        ("   ", "empty or whitespace"),
        ("\t\n", "empty or whitespace"),
    ])
    def test_invalid_types_and_empty(self, validator, invalid_input, expected_msg_part):
        """Test various invalid input types and empty strings."""
        valid, error = validator.validate_user_input(invalid_input)
        assert valid is False
        assert expected_msg_part in error

    def test_max_length_boundary(self, strict_validator):
        """Test boundary conditions for max length."""
        # Exact length (10 chars) -> Valid
        valid, _ = strict_validator.validate_user_input("0123456789")
        assert valid is True

        # Length + 1 (11 chars) -> Invalid
        valid, error = strict_validator.validate_user_input("0123456789A")
        assert valid is False
        assert "User input too long" in error

# -----------------------------------------------------------------------------
# Confidence Score Validation Tests
# -----------------------------------------------------------------------------

class TestConfidence:
    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0, 0, 1])
    def test_valid_confidence(self, validator, confidence):
        """Test valid confidence scores (floats and ints)."""
        valid, error = validator.validate_confidence(confidence)
        assert valid is True
        assert error is None

    @pytest.mark.parametrize("confidence, expected_msg_part", [
        (1.1, "between 0.0 and 1.0"),
        (-0.1, "between 0.0 and 1.0"),
        ("0.9", "must be a number"),
        (None, "must be a number"),
    ])
    def test_invalid_confidence(self, validator, confidence, expected_msg_part):
        """Test out-of-bounds and invalid types for confidence."""
        valid, error = validator.validate_confidence(confidence)
        assert valid is False
        assert expected_msg_part in error

# -----------------------------------------------------------------------------
# Task Type Validation Tests
# -----------------------------------------------------------------------------

class TestTaskType:
    @pytest.mark.parametrize("task_type", [
        TaskType.DIRECT_COMMAND,
        TaskType.CODE_GENERATION,
        TaskType.RESEARCH,
        TaskType.CONVERSATION
    ])
    def test_valid_task_types(self, validator, task_type):
        """Test all defined Enum values."""
        valid, error = validator.validate_task_type(task_type)
        assert valid is True
        assert error is None

    def test_invalid_task_type_value(self, validator):
        """Test that strings or other objects are not accepted, even if matching the value."""
        # Passing the string value "direct_command" instead of the Enum
        valid, error = validator.validate_task_type("direct_command")
        assert valid is False
        assert "must be a TaskType enum" in error

    def test_none_task_type(self, validator):
        valid, error = validator.validate_task_type(None)
        assert valid is False
        assert "cannot be None" in error

# -----------------------------------------------------------------------------
# Complexity Validation Tests
# -----------------------------------------------------------------------------

class TestComplexity:
    @pytest.mark.parametrize("complexity", [1, 5, 10])
    def test_valid_complexity(self, validator, complexity):
        """Test boundaries and middle values."""
        valid, error = validator.validate_complexity(complexity)
        assert valid is True
        assert error is None

    @pytest.mark.parametrize("complexity, expected_msg_part", [
        (0, "between 1 and 10"),
        (11, "between 1 and 10"),
        (5.5, "must be an integer"),
        ("5", "must be an integer"),
        (None, "must be an integer"),
    ])
    def test_invalid_complexity(self, validator, complexity, expected_msg_part):
        valid, error = validator.validate_complexity(complexity)
        assert valid is False
        assert expected_msg_part in error

# -----------------------------------------------------------------------------
# Provider Name Validation Tests
# -----------------------------------------------------------------------------

class TestProviderName:
    def test_valid_provider_none(self, validator):
        """None is a valid provider (implies default)."""
        valid, error = validator.validate_provider_name(None)
        assert valid is True
        assert error is None

    def test_valid_provider_string(self, validator):
        valid, error = validator.validate_provider_name("openai")
        assert valid is True
        assert error is None

    @pytest.mark.parametrize("provider, expected_msg_part", [
        (123, "must be a string"),
        ("", "cannot be empty"),
        ("   ", "cannot be empty"),
    ])
    def test_invalid_provider(self, validator, provider, expected_msg_part):
        valid, error = validator.validate_provider_name(provider)
        assert valid is False
        assert expected_msg_part in error

# -----------------------------------------------------------------------------
# Validate All (Integration) Tests
# -----------------------------------------------------------------------------

class TestValidateAll:
    def test_validate_all_success(self, validator):
        """Test when all provided arguments are valid."""
        valid, error = validator.validate_all(
            user_input="Run simulation",
            confidence=0.9,
            task_type=TaskType.CODE_GENERATION,
            complexity=5
        )
        assert valid is True
        assert error is None

    def test_validate_all_optional_args(self, validator):
        """Test validate_all with only required arguments."""
        valid, error = validator.validate_all(user_input="Just checking")
        assert valid is True

    def test_validate_all_fail_user_input(self, validator):
        """Test fail fast: User input fails first."""
        valid, error = validator.validate_all(
            user_input="", # Invalid
            confidence=0.9 # Valid
        )
        assert valid is False
        assert "empty" in error

    def test_validate_all_fail_middle_arg(self, validator):
        """Test fail fast: Stops at confidence error."""
        valid, error = validator.validate_all(
            user_input="Valid input",
            confidence=1.5, # Invalid
            task_type=TaskType.RESEARCH # Valid
        )
        assert valid is False
        assert "Confidence" in error

    def test_validate_all_fail_last_arg(self, validator):
        """Test fail fast: Stops at complexity error."""
        valid, error = validator.validate_all(
            user_input="Valid input",
            complexity=11 # Invalid
        )
        assert valid is False
        assert "Complexity" in error

# -----------------------------------------------------------------------------
# Exception Class Tests
# -----------------------------------------------------------------------------

def test_validation_error_exception():
    """Test the custom exception properties."""
    err = ValidationError("Something went wrong", field="user_input")
    assert str(err) == "Something went wrong"
    assert err.field == "user_input"
    assert isinstance(err, Exception)