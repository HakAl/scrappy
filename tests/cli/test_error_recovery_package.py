"""
Tests for error_recovery package structure and backward compatibility.

These tests verify that:
1. The new package structure maintains backward compatibility
2. Each module exports the expected functions/classes
3. Imports work from both the package and individual modules
"""

import pytest



class TestRetryModuleExports:
    """Test retry.py module exports the correct functions."""



    @pytest.mark.unit
    def test_retry_operation_behavior(self):
        """Verify retry_operation works correctly from module import."""
        from scrappy.cli.error_recovery.retry import retry_operation

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
        from scrappy.cli.error_recovery.retry import safe_operation_with_recovery

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
    def test_with_fallback_behavior(self):
        """Verify with_fallback works correctly from module import."""
        from scrappy.cli.error_recovery.fallback import with_fallback

        def failing():
            raise Exception("Fail")

        def success():
            return "OK"

        result = with_fallback(failing, fallbacks=[success])
        assert result == "OK"

    @pytest.mark.unit
    def test_graceful_degrade_behavior(self):
        """Verify graceful_degrade works correctly."""
        from scrappy.cli.error_recovery.fallback import graceful_degrade

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
        from scrappy.cli.error_recovery.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.failure_threshold == 3
        assert not breaker.is_open

    @pytest.mark.unit
    def test_circuit_breaker_call_success(self):
        """Verify CircuitBreaker.call works for successful operations."""
        from scrappy.cli.error_recovery.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker()
        result = breaker.call(lambda: "OK")
        assert result == "OK"



class TestContextModuleExports:
    """Test context.py module exports the correct classes and functions."""


    @pytest.mark.unit

    @pytest.mark.unit
    def test_error_recovery_context_basic_usage(self):
        """Verify error_recovery_context works for basic error handling."""
        from scrappy.cli.error_recovery.context import error_recovery_context

        with error_recovery_context() as ctx:
            raise ValueError("Test error")

        assert ctx.had_error
        assert isinstance(ctx.error, ValueError)

    @pytest.mark.unit
    def test_error_recovery_context_with_fallback(self):
        """Verify error_recovery_context fallback works."""
        from scrappy.cli.error_recovery.context import error_recovery_context

        with error_recovery_context(fallback=lambda: "fallback") as ctx:
            raise Exception("Error")

        assert ctx.result == "fallback"



class TestModuleSingleResponsibility:
    """Test that each module contains only its designated functionality."""
    pass


class TestIntegrationBetweenModules:
    """Test that modules work together correctly."""





class TestPackageInitialization:
    """Test package __init__.py re-exports all public APIs."""

    @pytest.mark.unit
    def test_package_has_all_attribute(self):
        """Package should define __all__ for explicit exports."""
        import scrappy.cli.error_recovery as pkg

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

