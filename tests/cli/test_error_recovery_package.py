"""
Tests for error_recovery package structure and backward compatibility.

These tests verify that:
1. The new package structure maintains backward compatibility
2. Each module exports the expected functions/classes
3. Imports work from both the package and individual modules
"""

import pytest



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
            'with_fallback',
            'fallback_providers',
            'graceful_degrade',
            'error_recovery_context',
            'ErrorRecoveryContext',
        ]

        for export in expected_exports:
            assert export in pkg.__all__, f"{export} not in __all__"

