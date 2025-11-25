"""
Configuration schema definitions.

Provides dataclasses for configuration values loaded from yaml/json/toml files.
All config classes implement their corresponding Protocol for type safety.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClarificationConfig:
    """
    Configuration for clarification behavior.

    Implements ClarificationConfigProtocol.

    This dataclass is immutable (frozen=True) to prevent accidental
    modification after loading from config file.

    Attributes:
        confidence_threshold: Confidence below this always needs clarification.
            Tasks with confidence below this value will always prompt
            for user clarification. Default: 0.7

        high_confidence_bypass: Confidence at or above this bypasses
            conflicting signal checks. When the classifier is highly
            confident, we trust it and skip additional checks.
            Default: 0.9
    """

    confidence_threshold: float = 0.7
    high_confidence_bypass: float = 0.9

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                f"confidence_threshold must be between 0.0 and 1.0, "
                f"got {self.confidence_threshold}"
            )
        if not 0.0 <= self.high_confidence_bypass <= 1.0:
            raise ValueError(
                f"high_confidence_bypass must be between 0.0 and 1.0, "
                f"got {self.high_confidence_bypass}"
            )
        if self.confidence_threshold >= self.high_confidence_bypass:
            raise ValueError(
                f"confidence_threshold ({self.confidence_threshold}) must be "
                f"less than high_confidence_bypass ({self.high_confidence_bypass})"
            )
