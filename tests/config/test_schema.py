"""
Tests for configuration schema dataclasses.

These tests verify:
- Default values are correctly set
- Validation rejects invalid values
- Immutability is enforced (frozen dataclass)
"""
import warnings

import pytest

from scrappy.task_router.config import ClarificationConfig


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
    def test_from_dict_uses_defaults(self):
        """from_dict should use default values when keys are missing."""
        config = ClarificationConfig.from_dict({})
        assert config.confidence_threshold == 0.7
        assert config.high_confidence_bypass == 0.9

    @pytest.mark.unit
    def test_from_dict_overrides_defaults(self):
        """from_dict should override defaults with provided values."""
        config = ClarificationConfig.from_dict({
            "confidence_threshold": 0.6,
            "high_confidence_bypass": 0.85,
        })
        assert config.confidence_threshold == 0.6
        assert config.high_confidence_bypass == 0.85

    @pytest.mark.unit
    def test_from_dict_partial_override(self):
        """from_dict should allow partial override of defaults."""
        config = ClarificationConfig.from_dict({
            "confidence_threshold": 0.5,
        })
        assert config.confidence_threshold == 0.5
        assert config.high_confidence_bypass == 0.9  # default



class TestDeprecatedImport:
    """Tests for deprecated import from scrappy.config.schema."""

    @pytest.mark.unit
    def test_deprecated_import_emits_warning(self):
        """Importing from scrappy.config.schema should emit deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Import from deprecated location
            from scrappy.config.schema import ClarificationConfig as DeprecatedConfig
            # Check warning was issued
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "scrappy.task_router.config" in str(w[0].message)

    @pytest.mark.unit
    def test_deprecated_import_returns_same_class(self):
        """Deprecated import should return the same class."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from scrappy.config.schema import ClarificationConfig as DeprecatedConfig
        from scrappy.task_router.config import ClarificationConfig

        # Should be the exact same class
        assert DeprecatedConfig is ClarificationConfig
