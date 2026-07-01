"""
Tests for circuit breaker implementation.

Following CLAUDE.md: Test BEHAVIOR. Prove state machine works correctly.
"""

import pytest
import asyncio
from unittest.mock import Mock
from pathlib import Path
import tempfile
import json
from scrappy.infrastructure.error_recovery import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from scrappy.infrastructure.exceptions import CircuitBreakerOpenError


class TestCircuitBreakerStates:
    """Test circuit breaker state machine."""

    def test_starts_in_closed_state(self):
        """Test circuit starts in CLOSED state."""
        circuit = CircuitBreaker("test", config=CircuitBreakerConfig())

        assert circuit.is_closed is True
        assert circuit.is_open is False
        assert circuit.is_half_open is False
        assert circuit.state == CircuitState.CLOSED

    def test_transitions_to_open_after_failures(self):
        """Test circuit opens after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        circuit = CircuitBreaker("test", config=config)

        func = Mock(side_effect=ValueError("fail"))

        # Record 3 failures (at threshold)
        for _ in range(3):
            try:
                circuit.call(func)
            except ValueError:
                pass

        # Should now be open
        assert circuit.is_open is True
        assert circuit.state == CircuitState.OPEN

    def test_blocks_calls_when_open(self):
        """Test circuit blocks calls when open."""
        config = CircuitBreakerConfig(failure_threshold=2)
        circuit = CircuitBreaker("test", config=config)

        func = Mock(side_effect=ValueError("fail"))

        # Record 2 failures to open circuit
        for _ in range(2):
            try:
                circuit.call(func)
            except ValueError:
                pass

        assert circuit.is_open is True

        # Next call should be blocked before calling func
        func_after_open = Mock(return_value="should not run")

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            circuit.call(func_after_open)

        # Function should not have been called
        func_after_open.assert_not_called()

        # Exception should have circuit info
        error = exc_info.value
        assert error.circuit_name == "test"
        assert error.failure_count == 2






class TestCircuitBreakerRecording:
    """Test circuit breaker recording success and failure."""

    def test_record_success_resets_failure_count(self):
        """Test record_success resets failure count in closed state."""
        circuit = CircuitBreaker("test")

        func_fail = Mock(side_effect=ValueError("fail"))
        func_success = Mock(return_value="success")

        # Record some failures (not enough to open)
        try:
            circuit.call(func_fail)
        except ValueError:
            pass

        stats = circuit.get_stats()
        assert stats['failure_count'] > 0

        # Record success should reset failure count
        circuit.call(func_success)

        stats = circuit.get_stats()
        assert stats['failure_count'] == 0

    def test_record_success_increments_success_count(self):
        """Test successes are counted."""
        circuit = CircuitBreaker("test")
        func = Mock(return_value="success")

        circuit.call(func)
        circuit.call(func)
        circuit.call(func)

        stats = circuit.get_stats()
        assert stats['total_successes'] == 3

    def test_record_failure_increments_failure_count(self):
        """Test failures are counted."""
        circuit = CircuitBreaker("test")
        func = Mock(side_effect=ValueError("fail"))

        for _ in range(3):
            try:
                circuit.call(func)
            except ValueError:
                pass

        stats = circuit.get_stats()
        assert stats['total_failures'] == 3


class TestCircuitBreakerReset:
    """Test manual circuit reset."""

    def test_manual_reset_closes_circuit(self):
        """Test manual reset transitions to closed."""
        config = CircuitBreakerConfig(failure_threshold=2)
        circuit = CircuitBreaker("test", config=config)

        func_fail = Mock(side_effect=ValueError("fail"))

        # Open circuit
        for _ in range(2):
            try:
                circuit.call(func_fail)
            except ValueError:
                pass

        assert circuit.is_open is True

        # Manual reset
        circuit.reset()

        assert circuit.is_closed is True
        assert circuit.state == CircuitState.CLOSED

    def test_reset_clears_failure_count(self):
        """Test reset clears failure counters."""
        circuit = CircuitBreaker("test")
        func_fail = Mock(side_effect=ValueError("fail"))

        for _ in range(3):
            try:
                circuit.call(func_fail)
            except ValueError:
                pass

        stats_before = circuit.get_stats()
        assert stats_before['failure_count'] > 0

        circuit.reset()

        stats_after = circuit.get_stats()
        assert stats_after['failure_count'] == 0
        assert stats_after['success_count'] == 0


class TestCircuitBreakerAsync:
    """Test async circuit breaker operations."""

    @pytest.mark.asyncio
    async def test_async_call_success(self):
        """Test successful async call through circuit."""
        circuit = CircuitBreaker("test")

        async def async_func():
            return "success"

        result = await circuit.call_async(async_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_call_blocks_when_open(self):
        """Test async call is blocked when circuit open."""
        config = CircuitBreakerConfig(failure_threshold=2)
        circuit = CircuitBreaker("test", config=config)

        async def async_fail():
            raise ValueError("fail")

        # Open circuit
        for _ in range(2):
            try:
                await circuit.call_async(async_fail)
            except ValueError:
                pass

        assert circuit.is_open is True

        # Should block
        async def async_success():
            return "should not run"

        with pytest.raises(CircuitBreakerOpenError):
            await circuit.call_async(async_success)

    @pytest.mark.asyncio
    async def test_async_half_open_to_closed(self):
        """Test async circuit transitions from half-open to closed."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            reset_timeout=0.1,
            half_open_max_calls=3  # Allow enough calls to hit success threshold
        )
        circuit = CircuitBreaker("test", config=config)

        async def async_fail():
            raise ValueError("fail")

        # Open circuit
        for _ in range(2):
            try:
                await circuit.call_async(async_fail)
            except ValueError:
                pass

        # Wait for half-open
        await asyncio.sleep(0.15)
        assert circuit.is_half_open is True

        # Record successes
        async def async_success():
            return "success"

        await circuit.call_async(async_success)
        await circuit.call_async(async_success)

        assert circuit.is_closed is True


class TestCircuitBreakerPersistence:
    """Test circuit state persistence."""

    def test_persistence_saves_state(self):
        """Test circuit state is persisted to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence_path = Path(tmpdir) / "circuit_state.json"

            circuit = CircuitBreaker(
                "test",
                persistence_path=persistence_path
            )

            func = Mock(return_value="success")
            circuit.call(func)
            circuit.call(func)

            # State should be saved
            assert persistence_path.exists()

            with open(persistence_path) as f:
                data = json.load(f)

            assert data['name'] == 'test'
            assert data['stats']['total_successes'] == 2

    def test_persistence_loads_state(self):
        """Test circuit state is loaded from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence_path = Path(tmpdir) / "circuit_state.json"

            # Create circuit, record some calls
            circuit1 = CircuitBreaker(
                "test",
                persistence_path=persistence_path
            )

            func_success = Mock(return_value="success")
            circuit1.call(func_success)
            circuit1.call(func_success)

            stats1 = circuit1.get_stats()

            # Create new circuit with same persistence path
            circuit2 = CircuitBreaker(
                "test",
                persistence_path=persistence_path
            )

            stats2 = circuit2.get_stats()

            # Should have loaded previous state
            assert stats2['total_successes'] == stats1['total_successes']

    def test_persistence_handles_missing_file(self):
        """Test circuit handles missing persistence file gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence_path = Path(tmpdir) / "nonexistent.json"

            # Should not crash
            circuit = CircuitBreaker(
                "test",
                persistence_path=persistence_path
            )

            assert circuit.is_closed is True


class TestCircuitBreakerStats:
    """Test circuit statistics."""

    def test_get_stats_returns_complete_info(self):
        """Test get_stats returns all circuit information."""
        circuit = CircuitBreaker("my_circuit")
        func_success = Mock(return_value="success")

        circuit.call(func_success)

        stats = circuit.get_stats()

        assert stats['name'] == 'my_circuit'
        assert stats['state'] == 'closed'
        assert stats['failure_count'] == 0
        assert stats['success_count'] == 1  # Incremented on success
        assert stats['total_calls'] == 1
        assert stats['total_successes'] == 1
        assert stats['total_failures'] == 0
        assert 'last_success' in stats
        assert 'last_failure' in stats

    def test_stats_track_last_failure_time(self):
        """Test last failure time is recorded."""
        circuit = CircuitBreaker("test")
        func_fail = Mock(side_effect=ValueError("fail"))

        try:
            circuit.call(func_fail)
        except ValueError:
            pass

        stats = circuit.get_stats()
        assert stats['last_failure'] is not None
        assert isinstance(stats['last_failure'], float)

    def test_stats_track_last_success_time(self):
        """Test last success time is recorded."""
        circuit = CircuitBreaker("test")
        func_success = Mock(return_value="success")

        circuit.call(func_success)

        stats = circuit.get_stats()
        assert stats['last_success'] is not None
        assert isinstance(stats['last_success'], float)
