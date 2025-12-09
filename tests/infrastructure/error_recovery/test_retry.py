"""
Tests for retry strategy implementation.

Following CLAUDE.md: Test BEHAVIOR. Prove retry works with backoff, jitter, and conditions.
"""

import pytest
import time
import asyncio
from unittest.mock import Mock, call
from scrappy.infrastructure.error_recovery import (
    ExponentialBackoffRetry,
    RetryConfig,
    retry_operation,
    retry_operation_async,
)
from scrappy.infrastructure.exceptions import (
    BaseError,
    RetryableError,
    NonRetryableError,
    NetworkError,
    AuthenticationError,
)


class TestExponentialBackoffRetry:
    """Test retry strategy with exponential backoff."""

    def test_succeeds_on_first_attempt(self):
        """Test successful operation on first attempt doesn't retry."""
        retry = ExponentialBackoffRetry()
        func = Mock(return_value="success")

        result = retry.execute(func, max_retries=3)

        assert result == "success"
        assert func.call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        """Test retry on failure, then success."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=3, base_delay=0.01, jitter=False)
        )
        func = Mock(side_effect=[ValueError("fail 1"), ValueError("fail 2"), "success"])

        result = retry.execute(func, max_retries=3)

        assert result == "success"
        assert func.call_count == 3

    def test_exhausts_all_retries_then_raises(self):
        """Test all retries exhausted, raises last exception."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False)
        )
        func = Mock(side_effect=ValueError("always fails"))

        with pytest.raises(ValueError, match="always fails"):
            retry.execute(func, max_retries=2)

        # Should try: initial + 2 retries = 3 attempts
        assert func.call_count == 3

    def test_exponential_backoff_timing(self):
        """Test exponential backoff delays are correct."""
        config = RetryConfig(
            max_retries=3,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False
        )
        retry = ExponentialBackoffRetry(config=config)

        # Test delay calculation
        assert config.calculate_delay(0) == 0.1  # 0.1 * 2^0
        assert config.calculate_delay(1) == 0.2  # 0.1 * 2^1
        assert config.calculate_delay(2) == 0.4  # 0.1 * 2^2
        assert config.calculate_delay(3) == 0.8  # 0.1 * 2^3

    def test_max_delay_cap(self):
        """Test delays are capped at max_delay."""
        config = RetryConfig(
            base_delay=10.0,
            multiplier=2.0,
            max_delay=15.0,
            jitter=False
        )

        # 10 * 2^3 = 80, but should be capped at 15
        assert config.calculate_delay(3) == 15.0

    def test_jitter_adds_randomness(self):
        """Test jitter adds randomness to delays."""
        config = RetryConfig(
            base_delay=1.0,
            multiplier=2.0,
            jitter=True
        )

        # Run multiple times to check randomness
        delays = [config.calculate_delay(1) for _ in range(10)]

        # Should have variation (not all the same)
        assert len(set(delays)) > 1

        # All should be within jitter range (50% to 150% of 2.0)
        for delay in delays:
            assert 1.0 <= delay <= 3.0

    def test_retry_only_on_specific_exceptions(self):
        """Test retry only occurs for specified exception types."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=3, base_delay=0.01)
        )

        # Should retry on ValueError
        func = Mock(side_effect=[ValueError("fail"), "success"])
        result = retry.execute(func, retry_on=(ValueError,))
        assert result == "success"
        assert func.call_count == 2

        # Should NOT retry on TypeError (not in retry_on)
        func = Mock(side_effect=TypeError("no retry"))
        with pytest.raises(TypeError, match="no retry"):
            retry.execute(func, retry_on=(ValueError,))
        assert func.call_count == 1  # Only one attempt

    def test_respects_baseError_is_retryable(self):
        """Test respects BaseError.is_retryable property."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=3, base_delay=0.01)
        )

        # RetryableError should retry
        func = Mock(side_effect=[RetryableError("retryable"), "success"])
        result = retry.execute(func)
        assert result == "success"
        assert func.call_count == 2

        # NonRetryableError should NOT retry
        func = Mock(side_effect=NonRetryableError("no retry"))
        with pytest.raises(NonRetryableError):
            retry.execute(func)
        assert func.call_count == 1  # Only one attempt

    def test_passes_arguments_to_function(self):
        """Test positional and keyword arguments are passed correctly."""
        retry = ExponentialBackoffRetry()
        func = Mock(return_value="result")

        result = retry.execute(func, "arg1", "arg2", kwarg1="value1", kwarg2="value2")

        assert result == "result"
        func.assert_called_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")

    def test_override_max_retries(self):
        """Test max_retries parameter overrides config."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=10, base_delay=0.01, jitter=False)
        )
        func = Mock(side_effect=ValueError("always fails"))

        with pytest.raises(ValueError):
            retry.execute(func, max_retries=2)  # Override to 2

        # Should try: initial + 2 retries = 3 attempts (not 11)
        assert func.call_count == 3


class TestExponentialBackoffRetryAsync:
    """Test async retry strategy."""

    @pytest.mark.asyncio
    async def test_async_succeeds_on_first_attempt(self):
        """Test successful async operation on first attempt."""
        retry = ExponentialBackoffRetry()

        async def async_func():
            return "success"

        result = await retry.execute_async(async_func, max_retries=3)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_retries_then_succeeds(self):
        """Test async retry on failure, then success."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=3, base_delay=0.01, jitter=False)
        )

        attempt = 0

        async def async_func():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ValueError(f"fail {attempt}")
            return "success"

        result = await retry.execute_async(async_func, max_retries=3)

        assert result == "success"
        assert attempt == 3

    @pytest.mark.asyncio
    async def test_async_exhausts_retries(self):
        """Test async all retries exhausted."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False)
        )

        async def async_func():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await retry.execute_async(async_func, max_retries=2)

    @pytest.mark.asyncio
    async def test_async_backoff_timing(self):
        """Test async uses proper backoff timing."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=2, base_delay=0.05, jitter=False)
        )

        attempt = 0
        start_time = time.time()

        async def async_func():
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ValueError("fail")
            return "success"

        await retry.execute_async(async_func, max_retries=2)

        elapsed = time.time() - start_time

        # Should have delays: 0.05s (attempt 0) + 0.1s (attempt 1) = 0.15s minimum
        assert elapsed >= 0.15

    @pytest.mark.asyncio
    async def test_async_respects_is_retryable(self):
        """Test async respects BaseError.is_retryable."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(max_retries=3, base_delay=0.01)
        )

        attempt = 0

        async def retryable_func():
            nonlocal attempt
            attempt += 1
            if attempt < 2:
                raise RetryableError("retry me")
            return "success"

        result = await retry.execute_async(retryable_func)
        assert result == "success"
        assert attempt == 2

        # NonRetryableError should not retry
        async def non_retryable_func():
            raise NonRetryableError("no retry")

        with pytest.raises(NonRetryableError):
            await retry.execute_async(non_retryable_func)


class TestConvenienceFunctions:
    """Test backward compatibility convenience functions."""

    def test_retry_operation_function(self):
        """Test retry_operation convenience function."""
        func = Mock(side_effect=[ValueError("fail"), "success"])

        result = retry_operation(func, max_retries=3, backoff=True)

        assert result == "success"
        assert func.call_count == 2

    def test_retry_operation_no_backoff(self):
        """Test retry without backoff (immediate retry)."""
        func = Mock(side_effect=[ValueError("fail"), "success"])

        result = retry_operation(func, max_retries=3, backoff=False)

        assert result == "success"
        # Should still work but with minimal delay

    def test_retry_operation_with_retry_on(self):
        """Test retry_operation with retry_on parameter."""
        func = Mock(side_effect=[NetworkError("network fail"), "success"])

        result = retry_operation(
            func,
            max_retries=3,
            retry_on=(NetworkError, TimeoutError)
        )

        assert result == "success"
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_operation_async_function(self):
        """Test retry_operation_async convenience function."""
        attempt = 0

        async def async_func():
            nonlocal attempt
            attempt += 1
            if attempt < 2:
                raise ValueError("fail")
            return "success"

        result = await retry_operation_async(async_func, max_retries=3)

        assert result == "success"
        assert attempt == 2


class TestRetryEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_retries(self):
        """Test with max_retries=0 (only try once)."""
        retry = ExponentialBackoffRetry()
        func = Mock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            retry.execute(func, max_retries=0)

        assert func.call_count == 1
  # This test documents that negative retries is an edge case

    def test_empty_retry_on_tuple(self):
        """Test empty retry_on tuple means retry nothing."""
        retry = ExponentialBackoffRetry(
            config=RetryConfig(base_delay=0.01)
        )
        func = Mock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            retry.execute(func, retry_on=())

        # Should not retry (empty tuple matches nothing)
        assert func.call_count == 1

    def test_function_with_no_arguments(self):
        """Test retry works with no-argument functions."""
        retry = ExponentialBackoffRetry()

        def no_args():
            return 42

        result = retry.execute(no_args)
        assert result == 42
