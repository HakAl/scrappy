"""
Tests for configuration schema dataclasses.

These tests verify:
- Default values are correctly set
- Validation rejects invalid values
- Immutability is enforced (frozen dataclass)
"""
import pytest

from src.config.schema import ClarificationConfig


class TestClarificationConfig:
    """Tests for ClarificationConfig dataclass."""

    @pytest.mark.unit
    def test_default_values(self):
        """Default values should be set correctly."""
        config = ClarificationConfig()
        assert config.confidence_threshold == 0.7
        assert config.high_confidence_bypass == 0.9

    @pytest.mark.unit
    def test_custom_values(self):
        """Should accept custom values."""
        config = ClarificationConfig(
            confidence_threshold=0.6,
            high_confidence_bypass=0.85
        )
        assert config.confidence_threshold == 0.6
        assert config.high_confidence_bypass == 0.85

    @pytest.mark.unit
    def test_immutable(self):
        """Config should be immutable (frozen)."""
        config = ClarificationConfig()
        with pytest.raises(AttributeError):
            config.confidence_threshold = 0.5

    @pytest.mark.unit
    def test_confidence_threshold_must_be_valid_range(self):
        """confidence_threshold must be between 0.0 and 1.0."""
        with pytest.raises(ValueError) as exc_info:
            ClarificationConfig(confidence_threshold=-0.1)
        assert "confidence_threshold" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            ClarificationConfig(confidence_threshold=1.5)
        assert "confidence_threshold" in str(exc_info.value)

    @pytest.mark.unit
    def test_high_confidence_bypass_must_be_valid_range(self):
        """high_confidence_bypass must be between 0.0 and 1.0."""
        with pytest.raises(ValueError) as exc_info:
            ClarificationConfig(high_confidence_bypass=-0.1)
        assert "high_confidence_bypass" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            ClarificationConfig(high_confidence_bypass=1.5)
        assert "high_confidence_bypass" in str(exc_info.value)

    @pytest.mark.unit
    def test_threshold_must_be_less_than_bypass(self):
        """confidence_threshold must be less than high_confidence_bypass."""
        with pytest.raises(ValueError) as exc_info:
            ClarificationConfig(
                confidence_threshold=0.9,
                high_confidence_bypass=0.7
            )
        assert "confidence_threshold" in str(exc_info.value)
        assert "high_confidence_bypass" in str(exc_info.value)

    @pytest.mark.unit
    def test_equal_thresholds_invalid(self):
        """Equal thresholds should be invalid."""
        with pytest.raises(ValueError) as exc_info:
            ClarificationConfig(
                confidence_threshold=0.8,
                high_confidence_bypass=0.8
            )
        assert "confidence_threshold" in str(exc_info.value)

    @pytest.mark.unit
    def test_boundary_values_valid(self):
        """Boundary values 0.0 and 1.0 should be valid."""
        # Lower bound
        config = ClarificationConfig(
            confidence_threshold=0.0,
            high_confidence_bypass=0.5
        )
        assert config.confidence_threshold == 0.0

        # Upper bound
        config = ClarificationConfig(
            confidence_threshold=0.5,
            high_confidence_bypass=1.0
        )
        assert config.high_confidence_bypass == 1.0

    @pytest.mark.unit
    def test_implements_protocol(self):
        """ClarificationConfig should implement ClarificationConfigProtocol."""
        from src.task_router.protocols import ClarificationConfigProtocol

        config = ClarificationConfig()
        # Check that it has the protocol attributes
        assert hasattr(config, 'confidence_threshold')
        assert hasattr(config, 'high_confidence_bypass')
        # Check it's runtime checkable
        assert isinstance(config, ClarificationConfigProtocol)
