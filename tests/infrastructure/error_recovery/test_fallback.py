"""
Tests for fallback strategy implementation.

Following CLAUDE.md: Test BEHAVIOR. Prove fallback chain works correctly.
"""

import pytest
from unittest.mock import Mock
from scrappy.infrastructure.error_recovery import (
    FallbackChain,
    with_fallback_async,
    graceful_degrade,
)
from scrappy.infrastructure.exceptions import RetryExhaustedError


class TestFallbackChain:
    """Test fallback chain strategy."""




    def test_all_operations_fail_raises_error(self):
        """Test all operations fail raises RetryExhaustedError."""
        fallback_chain = FallbackChain()
        primary = Mock(side_effect=ValueError("primary failed"))
        fallback1 = Mock(side_effect=TypeError("fallback1 failed"))
        fallback2 = Mock(side_effect=RuntimeError("fallback2 failed"))

        with pytest.raises(RetryExhaustedError) as exc_info:
            fallback_chain.execute(primary, [fallback1, fallback2])

        error = exc_info.value
        assert len(error.attempted_providers) == 3
        assert error.total_attempts == 3
        # Last error should be from fallback2
        assert isinstance(error.last_error, RuntimeError)


    def test_suppress_errors_returns_none(self):
        """Test suppress_errors=True returns None instead of raising."""
        fallback_chain = FallbackChain(suppress_errors=True)
        primary = Mock(side_effect=ValueError("fail"))
        fallback1 = Mock(side_effect=ValueError("fail"))

        result = fallback_chain.execute(primary, [fallback1])

        assert result is None  # No exception raised

    def test_empty_fallback_list(self):
        """Test with empty fallback list (only try primary)."""
        fallback_chain = FallbackChain()
        primary = Mock(side_effect=ValueError("fail"))

        with pytest.raises(RetryExhaustedError) as exc_info:
            fallback_chain.execute(primary, [])

        error = exc_info.value
        assert error.total_attempts == 1
        assert len(error.attempted_providers) == 1


class TestFallbackChainAsync:
    """Test async fallback chain."""

    @pytest.mark.asyncio
    async def test_async_primary_succeeds(self):
        """Test async primary succeeds, no fallback."""
        fallback_chain = FallbackChain()

        async def primary():
            return "primary success"

        async def fallback1():
            return "fallback1"

        result = await fallback_chain.execute_async(primary, [fallback1])

        assert result == "primary success"

    @pytest.mark.asyncio
    async def test_async_primary_fails_uses_fallback(self):
        """Test async primary fails, fallback succeeds."""
        fallback_chain = FallbackChain()

        async def primary():
            raise ValueError("primary failed")

        async def fallback1():
            return "fallback1 success"

        result = await fallback_chain.execute_async(primary, [fallback1])

        assert result == "fallback1 success"

    @pytest.mark.asyncio
    async def test_async_tries_all_fallbacks(self):
        """Test async tries all fallbacks in sequence."""
        fallback_chain = FallbackChain()

        attempts = []

        async def primary():
            attempts.append("primary")
            raise ValueError("fail")

        async def fallback1():
            attempts.append("fallback1")
            raise ValueError("fail")

        async def fallback2():
            attempts.append("fallback2")
            return "success"

        result = await fallback_chain.execute_async(primary, [fallback1, fallback2])

        assert result == "success"
        assert attempts == ["primary", "fallback1", "fallback2"]


class TestConvenienceFunctions:
    """Test convenience wrapper functions."""


    @pytest.mark.asyncio
    async def test_with_fallback_async_function(self):
        """Test with_fallback_async convenience function."""
        async def primary():
            raise ValueError("fail")

        async def fallback1():
            return "fallback success"

        result = await with_fallback_async(primary, [fallback1])

        assert result == "fallback success"



    def test_graceful_degrade_with_message(self):
        """Test graceful_degrade logs degraded message."""
        operation = Mock(side_effect=ValueError("fail"))
        on_error = Mock(return_value="degraded")

        result = graceful_degrade(
            operation,
            on_error,
            degraded_message="Entering degraded mode due to error"
        )

        assert result == "degraded"



class TestFallbackEdgeCases:
    """Test edge cases and error conditions."""

    def test_single_fallback(self):
        """Test with single fallback (common case)."""
        fallback_chain = FallbackChain()
        primary = Mock(side_effect=ValueError("fail"))
        single_fallback = Mock(return_value="success")

        result = fallback_chain.execute(primary, [single_fallback])

        assert result == "success"

    def test_many_fallbacks(self):
        """Test with many fallbacks."""
        fallback_chain = FallbackChain()
        primary = Mock(side_effect=ValueError("fail"))

        # Create 10 failing fallbacks + 1 success
        fallbacks = [Mock(side_effect=ValueError(f"fail{i}")) for i in range(10)]
        fallbacks.append(Mock(return_value="success"))

        result = fallback_chain.execute(primary, fallbacks)

        assert result == "success"
        # All should have been tried
        assert primary.call_count == 1
        for fb in fallbacks[:-1]:
            assert fb.call_count == 1


    def test_no_arguments(self):
        """Test fallback works with no-argument functions."""
        fallback_chain = FallbackChain()

        def primary():
            raise ValueError("fail")

        def fallback1():
            return 42

        result = fallback_chain.execute(primary, [fallback1])
        assert result == 42
