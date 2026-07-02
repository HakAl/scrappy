"""Factory for creating rate limit tracker with default dependencies."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from .tracker import RateLimitTracker
from .storage import RateLimitStorage, FileSystemAdapter
from .policy import RateLimitPolicy
from .calculator import RateLimitCalculator
from .recommender import RateLimitRecommender
from .scorer import QuotaScorer
from .enforcement import RateLimitEnforcementPolicy
from .notifier import RateLimitNotifier, NullNotifier
from .protocols import (
    EnforcementPolicyProtocol,
    QuotaScorerProtocol,
    UserNotifierProtocol,
)
from ..config import OrchestratorConfig


class OutputProtocol(Protocol):
    """Minimal output interface for notifications."""

    def print(self, message: str) -> None:
        """Print informational message."""
        ...

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        ...

    def print_error(self, message: str) -> None:
        """Print error message."""
        ...


@dataclass
class RateLimitComponents:
    """Container for all rate limit components.

    Allows access to individual components for advanced use cases
    while keeping the simple create_rate_limit_tracker API.
    """

    tracker: RateLimitTracker
    scorer: QuotaScorerProtocol
    enforcement: EnforcementPolicyProtocol
    notifier: UserNotifierProtocol


@dataclass
class EnforcementComponents:
    """Container for enforcement components that use an existing tracker.

    Use when tracker is already created and wired to callbacks
    (e.g., via RateTrackingCallback in LiteLLM).
    """

    scorer: QuotaScorerProtocol
    enforcement: EnforcementPolicyProtocol
    notifier: UserNotifierProtocol


def create_rate_limit_tracker(
    tracker_file: Optional[str | Path] = None,
    auto_load: bool = False,
    config: Optional[OrchestratorConfig] = None,
) -> RateLimitTracker:
    """
    Create rate limit tracker with default dependencies.

    This is the primary way to create a tracker for production use.
    For testing, instantiate RateLimitTracker directly with test doubles.

    Args:
        tracker_file: Path to tracker file (None = no persistence)
        auto_load: If True, load data from storage on init
        config: OrchestratorConfig instance (creates default if None)

    Returns:
        Configured RateLimitTracker instance
    """
    components = create_rate_limit_components(
        tracker_file=tracker_file,
        auto_load=auto_load,
        config=config,
        output=None,  # No notifier output - just tracker
    )
    return components.tracker


def create_rate_limit_components(
    tracker_file: Optional[str | Path] = None,
    auto_load: bool = False,
    config: Optional[OrchestratorConfig] = None,
    output: Optional[OutputProtocol] = None,
    quiet_mode: bool = False,
) -> RateLimitComponents:
    """
    Create all rate limit components with enforcement support.

    This is the full-featured factory that creates tracker, scorer,
    enforcement policy, and notifier. Use this when you need
    pre-request enforcement checks.

    Args:
        tracker_file: Path to tracker file (None = no persistence)
        auto_load: If True, load data from storage on init
        config: OrchestratorConfig instance (creates default if None)
        output: Output interface for notifications (None = NullNotifier)
        quiet_mode: If True, suppress non-critical notifications

    Returns:
        RateLimitComponents with all components
    """
    # Use default config if not provided
    if config is None:
        config = OrchestratorConfig()

    # Convert to Path if string
    path = Path(tracker_file) if tracker_file else None

    # Create storage dependencies
    file_system = FileSystemAdapter()
    storage = RateLimitStorage(path, file_system)
    policy = RateLimitPolicy()
    calculator = RateLimitCalculator()

    # Create tracker first (needed by scorer and recommender)
    tracker = RateLimitTracker(
        storage=storage,
        policy=policy,
        calculator=calculator,
        recommender=None,  # type: ignore[arg-type]  # circular wiring: recommender is set right after creation
        auto_load=False,  # Load after all wiring is complete
        config=config,
    )

    # Create scorer with tracker as usage query
    scorer = QuotaScorer(
        usage_query=tracker,
        warn_threshold=config.enforcement_warn_threshold,
    )

    # Create recommender with tracker and scorer
    recommender = RateLimitRecommender(
        usage_query=tracker,
        scorer=scorer,
    )

    # Inject recommender into tracker
    tracker._recommender = recommender

    # Create enforcement policy
    enforcement = RateLimitEnforcementPolicy(
        usage_query=tracker,
        scorer=scorer,
        warn_threshold=config.enforcement_warn_threshold,
        block_threshold=config.enforcement_block_threshold,
    )

    # Create notifier (NullNotifier if no output provided)
    notifier: UserNotifierProtocol
    if output is not None:
        notifier = RateLimitNotifier(
            output=output,
            quiet_mode=quiet_mode,
            notification_cooldown=config.notification_cooldown,
        )
    else:
        notifier = NullNotifier()

    # Now load if requested
    if auto_load:
        tracker.restore_from_disk()

    return RateLimitComponents(
        tracker=tracker,
        scorer=scorer,
        enforcement=enforcement,
        notifier=notifier,
    )


def create_enforcement_components(
    tracker: RateLimitTracker,
    config: Optional[OrchestratorConfig] = None,
    output: Optional[OutputProtocol] = None,
    quiet_mode: bool = False,
) -> EnforcementComponents:
    """
    Create enforcement components using an existing tracker.

    Use this when the tracker is already created and wired to callbacks
    (e.g., via RateTrackingCallback). This avoids creating a duplicate
    tracker that wouldn't receive usage updates.

    Args:
        tracker: Existing RateLimitTracker instance
        config: OrchestratorConfig instance (creates default if None)
        output: Output interface for notifications (None = NullNotifier)
        quiet_mode: If True, suppress non-critical notifications

    Returns:
        EnforcementComponents with scorer, enforcement policy, and notifier
    """
    if config is None:
        config = OrchestratorConfig()

    # Create scorer with existing tracker as usage query
    scorer = QuotaScorer(
        usage_query=tracker,
        warn_threshold=config.enforcement_warn_threshold,
    )

    # Create enforcement policy
    enforcement = RateLimitEnforcementPolicy(
        usage_query=tracker,
        scorer=scorer,
        warn_threshold=config.enforcement_warn_threshold,
        block_threshold=config.enforcement_block_threshold,
    )

    # Create notifier (NullNotifier if no output provided)
    notifier: UserNotifierProtocol
    if output is not None:
        notifier = RateLimitNotifier(
            output=output,
            quiet_mode=quiet_mode,
            notification_cooldown=config.notification_cooldown,
        )
    else:
        notifier = NullNotifier()

    return EnforcementComponents(
        scorer=scorer,
        enforcement=enforcement,
        notifier=notifier,
    )
