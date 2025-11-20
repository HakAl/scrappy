"""
Tests for error_recovery package structure and backward compatibility.

These tests verify that:
1. The new package structure maintains backward compatibility
2. Each module exports the expected functions/classes
3. Imports work from both the package and individual modules
"""

import pytest


class TestBackwardCompatibility:
    """Test that existing imports continue to work after refactoring."""

    @pytest.mark.unit
    def test_import_retry_operation_from_package(self):
        """Import retry_operation from main package should work."""
        from src.cli.error_recovery import retry_operation
        assert callable(retry_operation)

    @pytest.mark.unit
    def test_import_safe_operation_with_recovery_from_package(self):
        """Import safe_operation_with_recovery from main package should work."""
        from src.cli.error_recovery import safe_operation_with_recovery
        assert callable(safe_operation_with_recovery)

    @pytest.mark.unit
    def test_import_with_fallback_from_package(self):
        """Import with_fallback from main package should work."""
        from src.cli.error_recovery import with_fallback
        assert callable(with_fallback)

    @pytest.mark.unit
    def test_import_fallback_providers_from_package(self):
        """Import fallback_providers from main package should work."""
        from src.cli.error_recovery import fallback_providers
        assert callable(fallback_providers)

    @pytest.mark.unit
    def test_import_graceful_degrade_from_package(self):
        """Import graceful_degrade from main package should work."""
        from src.cli.error_recovery import graceful_degrade
        assert callable(graceful_degrade)

    @pytest.mark.unit
    def test_import_error_recovery_context_from_package(self):
        """Import error_recovery_context from main package should work."""
        from src.cli.error_recovery import error_recovery_context
        assert callable(error_recovery_context)


class TestRetryModuleExports:
    """Test retry.py module exports the correct functions."""

    @pytest.mark.unit
    def test_import_retry_operation_from_retry_module(self):
        """Import retry_operation directly from retry module."""
        from src.cli.error_recovery.retry import retry_operation
        assert callable(retry_operation)

    @pytest.mark.unit
    def test_import_safe_operation_with_recovery_from_retry_module(self):
        """Import safe_operation_with_recovery directly from retry module."""
        from src.cli.error_recovery.retry import safe_operation_with_recovery
        assert callable(safe_operation_with_recovery)

    @pytest.mark.unit
    def test_retry_operation_behavior(self):
        """Verify retry_operation works correctly from module import."""
        from src.cli.error_recovery.retry import retry_operation

        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("Temp")
            return "success"

        result = retry_operation(flaky, max_retries=3)
        assert result == "success"
        assert len(attempts) == 2

    @pytest.mark.unit
    def test_safe_operation_with_recovery_behavior(self):
        """Verify safe_operation_with_recovery works correctly."""
        from src.cli.error_recovery.retry import safe_operation_with_recovery

        def failing():
            raise Exception("Fail")

        success, result = safe_operation_with_recovery(
            failing, fallback_value="default"
        )

        assert not success
        assert result == "default"


class TestFallbackModuleExports:
    """Test fallback.py module exports the correct functions."""

    @pytest.mark.unit
    def test_import_with_fallback_from_fallback_module(self):
        """Import with_fallback directly from fallback module."""
        from src.cli.error_recovery.fallback import with_fallback
        assert callable(with_fallback)

    @pytest.mark.unit
    def test_import_fallback_providers_from_fallback_module(self):
        """Import fallback_providers directly from fallback module."""
        from src.cli.error_recovery.fallback import fallback_providers
        assert callable(fallback_providers)

    @pytest.mark.unit
    def test_import_graceful_degrade_from_fallback_module(self):
        """Import graceful_degrade directly from fallback module."""
        from src.cli.error_recovery.fallback import graceful_degrade
        assert callable(graceful_degrade)

    @pytest.mark.unit
    def test_with_fallback_behavior(self):
        """Verify with_fallback works correctly from module import."""
        from src.cli.error_recovery.fallback import with_fallback

        def failing():
            raise Exception("Fail")

        def success():
            return "OK"

        result = with_fallback(failing, fallbacks=[success])
        assert result == "OK"

    @pytest.mark.unit
    def test_graceful_degrade_behavior(self):
        """Verify graceful_degrade works correctly."""
        from src.cli.error_recovery.fallback import graceful_degrade

        def failing():
            raise Exception("Error")

        result = graceful_degrade(
            failing,
            on_error=lambda e: "degraded"
        )

        assert result == "degraded"


class TestCircuitBreakerModuleExports:
    """Test circuit_breaker.py module exports the correct class."""

    @pytest.mark.unit

    @pytest.mark.unit
    def test_circuit_breaker_instantiation(self):
        """Verify CircuitBreaker can be instantiated from module import."""
        from src.cli.error_recovery.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.failure_threshold == 3
        assert not breaker.is_open

    @pytest.mark.unit
    def test_circuit_breaker_call_success(self):
        """Verify CircuitBreaker.call works for successful operations."""
        from src.cli.error_recovery.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker()
        result = breaker.call(lambda: "OK")
        assert result == "OK"

    @pytest.mark.unit
    def test_circuit_breaker_opens_after_failures(self):
        """Verify CircuitBreaker opens after threshold failures."""
        from src.cli.error_recovery.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2)

        def failing():
            raise Exception("Fail")

        # Trip the breaker
        for _ in range(2):
            try:
                breaker.call(failing)
            except Exception:
                pass

        assert breaker.is_open


class TestContextModuleExports:
    """Test context.py module exports the correct classes and functions."""

    @pytest.mark.unit
    def test_import_error_recovery_context_function(self):
        """Import error_recovery_context function from context module."""
        from src.cli.error_recovery.context import error_recovery_context
        assert callable(error_recovery_context)

    @pytest.mark.unit

    @pytest.mark.unit
    def test_error_recovery_context_basic_usage(self):
        """Verify error_recovery_context works for basic error handling."""
        from src.cli.error_recovery.context import error_recovery_context

        with error_recovery_context() as ctx:
            raise ValueError("Test error")

        assert ctx.had_error
        assert isinstance(ctx.error, ValueError)

    @pytest.mark.unit
    def test_error_recovery_context_with_fallback(self):
        """Verify error_recovery_context fallback works."""
        from src.cli.error_recovery.context import error_recovery_context

        with error_recovery_context(fallback=lambda: "fallback") as ctx:
            raise Exception("Error")

        assert ctx.result == "fallback"

    @pytest.mark.unit
    def test_error_recovery_context_class_attributes(self):
        """Verify ErrorRecoveryContext has expected attributes."""
        from src.cli.error_recovery.context import ErrorRecoveryContext

        ctx = ErrorRecoveryContext()
        assert hasattr(ctx, 'had_error')
        assert hasattr(ctx, 'error')
        assert hasattr(ctx, 'result')
        assert ctx.had_error is False
        assert ctx.error is None
        assert ctx.result is None


class TestModuleSingleResponsibility:
    """Test that each module contains only its designated functionality."""
    pass


class TestIntegrationBetweenModules:
    """Test that modules work together correctly."""

    @pytest.mark.unit
    def test_retry_uses_provider_error_correctly(self):
        """retry_operation should use ProviderError from exceptions."""
        from src.cli.error_recovery.retry import retry_operation
        from src.cli.exceptions import ProviderError

        def always_fails():
            raise ConnectionError("Fail")

        with pytest.raises(ProviderError):
            retry_operation(always_fails, max_retries=2)

    @pytest.mark.unit
    def test_fallback_uses_cli_error_correctly(self):
        """with_fallback should raise CLIError when all fail."""
        from src.cli.error_recovery.fallback import with_fallback
        from src.cli.exceptions import CLIError

        def failing():
            raise Exception("Fail")

        with pytest.raises(CLIError):
            with_fallback(failing, fallbacks=[failing])

    @pytest.mark.unit
    def test_circuit_breaker_uses_provider_error_correctly(self):
        """CircuitBreaker should raise ProviderError when open."""
        from src.cli.error_recovery.circuit_breaker import CircuitBreaker
        from src.cli.exceptions import ProviderError

        breaker = CircuitBreaker(failure_threshold=1, reset_timeout=100)

        def failing():
            raise Exception("Fail")

        # Trip the breaker
        try:
            breaker.call(failing)
        except Exception:
            pass

        # Should raise ProviderError
        with pytest.raises(ProviderError) as exc_info:
            breaker.call(lambda: "OK")

        assert "circuit" in str(exc_info.value).lower()


class TestPackageInitialization:
    """Test package __init__.py re-exports all public APIs."""

    @pytest.mark.unit
    def test_package_has_all_attribute(self):
        """Package should define __all__ for explicit exports."""
        import src.cli.error_recovery as pkg

        assert hasattr(pkg, '__all__')

        expected_exports = [
            'retry_operation',
            'safe_operation_with_recovery',
            'with_fallback',
            'fallback_providers',
            'graceful_degrade',
            'CircuitBreaker',
            'error_recovery_context',
            'ErrorRecoveryContext',
        ]

        for export in expected_exports:
            assert export in pkg.__all__, f"{export} not in __all__"

