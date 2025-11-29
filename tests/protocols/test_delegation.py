"""
Tests for delegation protocol definitions.

Focuses on LLMRequest behavior, particularly kwargs filtering.
"""

import pytest
from src.protocols.delegation import LLMRequest, INTERNAL_KWARGS


class TestLLMRequestKwargsFiltering:
    """Tests for LLMRequest internal kwargs filtering."""

    def test_filters_task_type_from_kwargs(self):
        """task_type should be filtered out as it's internal-only."""
        request = LLMRequest(
            prompt="test prompt",
            kwargs={'task_type': 'planning', 'valid_param': 'value'}
        )

        assert 'task_type' not in request.kwargs
        assert request.kwargs['valid_param'] == 'value'

    def test_preserves_valid_kwargs(self):
        """Valid provider kwargs should be preserved."""
        request = LLMRequest(
            prompt="test prompt",
            kwargs={'stream': True, 'stop': ['\n']}
        )

        assert request.kwargs['stream'] is True
        assert request.kwargs['stop'] == ['\n']

    def test_handles_none_kwargs(self):
        """None kwargs should become empty dict."""
        request = LLMRequest(prompt="test prompt", kwargs=None)

        assert request.kwargs == {}

    def test_handles_empty_kwargs(self):
        """Empty kwargs should remain empty."""
        request = LLMRequest(prompt="test prompt", kwargs={})

        assert request.kwargs == {}

    def test_filters_multiple_internal_kwargs(self):
        """All internal kwargs should be filtered out."""
        # Build kwargs with all internal kwargs plus some valid ones
        kwargs = {
            'valid_param_1': 'value1',
            'valid_param_2': 'value2',
        }
        # Add all internal kwargs
        for internal_kwarg in INTERNAL_KWARGS:
            kwargs[internal_kwarg] = 'should_be_filtered'

        request = LLMRequest(prompt="test prompt", kwargs=kwargs)

        # Verify none of the internal kwargs made it through
        for internal_kwarg in INTERNAL_KWARGS:
            assert internal_kwarg not in request.kwargs

        # Verify valid kwargs are preserved
        assert request.kwargs['valid_param_1'] == 'value1'
        assert request.kwargs['valid_param_2'] == 'value2'

    def test_filters_only_internal_kwargs_preserves_similar_names(self):
        """Only exact matches of internal kwargs should be filtered."""
        request = LLMRequest(
            prompt="test prompt",
            kwargs={
                'task_type': 'planning',  # Should be filtered
                'task_type_id': 123,      # Should NOT be filtered (different key)
                'my_task_type': 'custom', # Should NOT be filtered (different key)
            }
        )

        assert 'task_type' not in request.kwargs
        assert request.kwargs['task_type_id'] == 123
        assert request.kwargs['my_task_type'] == 'custom'


class TestLLMRequestValidation:
    """Tests for LLMRequest parameter validation."""

    def test_rejects_empty_prompt(self):
        """Empty prompt should raise ValueError."""
        with pytest.raises(ValueError, match="prompt cannot be empty"):
            LLMRequest(prompt="")

    def test_rejects_whitespace_only_prompt(self):
        """Whitespace-only prompt should raise ValueError."""
        with pytest.raises(ValueError, match="prompt cannot be empty"):
            LLMRequest(prompt="   \n\t  ")

    def test_rejects_temperature_too_low(self):
        """Temperature below 0.0 should raise ValueError."""
        with pytest.raises(ValueError, match="temperature must be 0.0-2.0"):
            LLMRequest(prompt="test", temperature=-0.1)

    def test_rejects_temperature_too_high(self):
        """Temperature above 2.0 should raise ValueError."""
        with pytest.raises(ValueError, match="temperature must be 0.0-2.0"):
            LLMRequest(prompt="test", temperature=2.1)

    def test_accepts_temperature_at_boundaries(self):
        """Temperature at 0.0 and 2.0 should be accepted."""
        request1 = LLMRequest(prompt="test", temperature=0.0)
        assert request1.temperature == 0.0

        request2 = LLMRequest(prompt="test", temperature=2.0)
        assert request2.temperature == 2.0

    def test_rejects_negative_max_tokens(self):
        """Negative max_tokens should raise ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            LLMRequest(prompt="test", max_tokens=-1)

    def test_rejects_zero_max_tokens(self):
        """Zero max_tokens should raise ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            LLMRequest(prompt="test", max_tokens=0)

    def test_accepts_positive_max_tokens(self):
        """Positive max_tokens should be accepted."""
        request = LLMRequest(prompt="test", max_tokens=100)
        assert request.max_tokens == 100


class TestLLMRequestImmutability:
    """Tests for LLMRequest frozen dataclass behavior."""

    def test_frozen_dataclass(self):
        """LLMRequest should be immutable (frozen)."""
        request = LLMRequest(prompt="test")

        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            request.prompt = "modified"

    def test_kwargs_dict_is_not_shared(self):
        """Each LLMRequest should have its own kwargs dict."""
        kwargs1 = {'param': 'value1'}
        request1 = LLMRequest(prompt="test1", kwargs=kwargs1)

        kwargs2 = {'param': 'value2'}
        request2 = LLMRequest(prompt="test2", kwargs=kwargs2)

        # Modifying original dict should not affect request
        kwargs1['param'] = 'modified'

        assert request1.kwargs['param'] == 'value1'
        assert request2.kwargs['param'] == 'value2'
