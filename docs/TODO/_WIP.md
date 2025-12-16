# User Input Validation - COMPLETED

## Summary

Implemented centralized input validation/sanitization module at `src/scrappy/infrastructure/validation/`.

## Module Structure

```
infrastructure/validation/
    __init__.py           # Public API exports
    sanitizer.py          # Core sanitization (dangerous chars, encoding)
    api_key.py            # API key validation (uses sanitizer)
    user_input.py         # General user input validation (uses sanitizer)
```

## Key Functions

### sanitizer.py
- `sanitize_string()` - Main sanitization entry point
- `contains_dangerous_patterns()` - Detects path traversal, shell injection, etc.
- `strip_control_characters()` - Removes control chars
- `normalize_unicode()` - NFC normalization, confusable replacement
- `ValidationResult` - Immutable result dataclass

### api_key.py
- `validate_api_key()` - Full API key validation
- `validate_env_var_name()` - Env var name validation
- `is_placeholder_value()` - Detects placeholder strings

### user_input.py
- `validate_user_input(value, context)` - Context-aware validation
  - context="chat" - lenient (multiline allowed)
  - context="command" - moderate
  - context="choice" - strict (alphanumeric only)
  - context="path" - path-aware
- `sanitize_for_display()` - Safe display of untrusted content
- `validate_numeric_choice()` - Menu choice validation

## Security Checks

- Path traversal (`../`, `..\`, absolute paths, UNC paths, `~`)
- Shell metacharacters (`;`, `|`, `&`, `$`, `` ` ``, `>`, `<`, `||`, `&&`, newlines)
- Null bytes and control characters
- Unicode confusables (fullwidth slash, etc.)
- Placeholder detection ("test", "changeme", "your-api-key-here", repeated chars)
- Length limits (DoS protection)

## Integration Points (All Wired Up)

| Location | File | Function |
|----------|------|----------|
| API key storage | `infrastructure/config/api_keys.py` | `ApiKeyConfigService.set_key()` |
| Wizard key input | `cli/setup_wizard.py` | `_handle_key_input()`, `_configure_provider()` |
| Env migration | `cli/textual_app.py` | `_migrate_env_keys_to_config()` |
| Task router | `task_router/validator.py` | `InputValidator.validate_user_input()` |

## Tests

151 tests in `tests/infrastructure/validation/`:
- `test_sanitizer.py` - Core sanitization tests
- `test_api_key.py` - API key validation tests
- `test_user_input.py` - User input validation tests

## Usage

```python
from scrappy.infrastructure.validation import (
    validate_api_key,
    validate_user_input,
    ValidationResult,
)

# Validate API key
result = validate_api_key(user_provided_key)
if not result.is_valid:
    print(f"Invalid key: {result.error}")
else:
    safe_key = result.sanitized_value

# Validate chat input
result = validate_user_input(user_query, context="chat")
if result.is_valid:
    process(result.sanitized_value)
```

## Error Handling

- `ApiKeyValidationError` - Raised by `ApiKeyConfigService.set_key()` on invalid input
- All validation functions return `ValidationResult` with clear error messages
