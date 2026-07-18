"""
Tests for error recovery strategies.

These tests define the behavior of error recovery mechanisms including
retry logic, fallback providers, and graceful degradation.
"""

import pytest
from unittest.mock import Mock, patch


class TestFallbackStrategy:
    """Test fallback mechanism for provider failures."""

    @pytest.mark.unit
    def test_fallback_uses_alternative_provider(self):
        """Fallback should try alternative providers."""
        from scrappy.cli.error_recovery import with_fallback

        providers_tried = []

        def try_provider(name):
            providers_tried.append(name)
            if name == "primary":
                raise ConnectionError("Primary down")
            return f"Result from {name}"

        result = with_fallback(
            lambda: try_provider("primary"),
            fallbacks=[
                lambda: try_provider("secondary"),
                lambda: try_provider("tertiary"),
            ]
        )

        assert result == "Result from secondary"
        assert providers_tried == ["primary", "secondary"]

    @pytest.mark.unit
    def test_fallback_tries_all_alternatives(self):
        """Fallback should try all alternatives before failing."""
        from scrappy.cli.error_recovery import with_fallback
        from scrappy.cli.exceptions import CLIError

        providers_tried = []

        def try_provider(name):
            providers_tried.append(name)
            raise ConnectionError(f"{name} down")

        with pytest.raises(CLIError):
            with_fallback(
                lambda: try_provider("primary"),
                fallbacks=[
                    lambda: try_provider("secondary"),
                    lambda: try_provider("tertiary"),
                ]
            )

        assert providers_tried == ["primary", "secondary", "tertiary"]

    @pytest.mark.unit
    def test_fallback_returns_first_success(self):
        """Fallback should return immediately on first success."""
        from scrappy.cli.error_recovery import with_fallback

        call_count = []

        def failing():
            call_count.append("fail")
            raise Exception("Fail")

        def success():
            call_count.append("success")
            return "OK"

        def never_called():
            call_count.append("never")
            return "Never"

        result = with_fallback(
            failing,
            fallbacks=[success, never_called]
        )

        assert result == "OK"
        assert "never" not in call_count

    @pytest.mark.unit
    def test_fallback_with_provider_registry(self):
        """Fallback should work with provider registry."""
        from scrappy.cli.error_recovery import fallback_providers

        mock_orchestrator = Mock()
        mock_orchestrator.list_available.return_value = ["primary", "secondary", "tertiary"]

        call_sequence = []

        def mock_delegate(provider):
            call_sequence.append(provider)
            if provider == "primary":
                raise ConnectionError("Primary down")
            return f"Result from {provider}"

        result = fallback_providers(
            mock_delegate,
            primary="primary",
            orchestrator=mock_orchestrator
        )

        assert "secondary" in result or "tertiary" in result
        assert call_sequence[0] == "primary"


class TestGracefulDegradation:
    """Test graceful degradation for partial failures."""

    @pytest.mark.unit
    def test_degraded_returns_partial_result(self):
        """Degraded operation should return partial results."""
        from scrappy.cli.error_recovery import graceful_degrade

        def partial_operation():
            results = ["step1", "step2"]
            raise Exception("Failed at step 3")
            results.append("step3")
            return results

        result = graceful_degrade(
            partial_operation,
            on_error=lambda e: ["step1", "step2"]  # Return what we have
        )

        assert result == ["step1", "step2"]

    @pytest.mark.unit
    def test_degraded_notifies_user(self):
        """Degraded operation should notify user of partial results."""
        from scrappy.cli.error_recovery import graceful_degrade
        from tests.helpers import MockIO

        io = MockIO()

        def failing_operation():
            raise Exception("Partial failure")

        graceful_degrade(
            failing_operation,
            on_error=lambda e: "partial",
            io=io,
            degraded_message="Operating in degraded mode"
        )

        output = io.get_output()
        assert "degraded" in output.lower()


class TestErrorRecoveryContext:
    """Test error recovery context manager."""

    @pytest.mark.unit
    def test_recovery_context_catches_and_handles(self):
        """Recovery context should catch and handle errors."""
        from scrappy.cli.error_recovery import error_recovery_context
        from tests.helpers import MockIO

        io = MockIO()

        with error_recovery_context(io=io) as ctx:
            raise ConnectionError("Network issue")

        assert ctx.had_error
        assert ctx.error is not None
        output = io.get_output()
        assert len(output) > 0

    @pytest.mark.unit
    def test_recovery_context_with_retry(self):
        """Recovery context should support retry strategy."""
        from scrappy.cli.error_recovery import error_recovery_context

        attempts = [0]

        with error_recovery_context(retry=True, max_retries=3) as ctx:
            attempts[0] += 1
            if attempts[0] < 2:
                raise ConnectionError("Temporary")
            ctx.result = "success"

        assert ctx.result == "success"
        assert attempts[0] == 2

    @pytest.mark.unit
    def test_recovery_context_with_fallback(self):
        """Recovery context should support fallback strategy."""
        from scrappy.cli.error_recovery import error_recovery_context

        with error_recovery_context(fallback=lambda: "fallback_value") as ctx:
            raise Exception("Primary failed")

        assert ctx.result == "fallback_value"


class TestRecoveryLogging:
    """Test that recovery actions are logged properly."""

    @pytest.mark.unit
    def test_fallback_logs_provider_switch(self):
        """Fallback should log when switching providers."""
        from scrappy.cli.error_recovery import with_fallback

        def failing():
            raise Exception("Fail")

        def working():
            return "OK"

        with patch('logging.getLogger') as mock_logger:
            logger_instance = Mock()
            mock_logger.return_value = logger_instance

            with_fallback(
                failing,
                fallbacks=[working],
                logger=logger_instance
            )

            # Should have logged the fallback
            assert logger_instance.warning.called or logger_instance.info.called

