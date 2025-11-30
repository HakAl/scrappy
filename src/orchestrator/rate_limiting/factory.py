"""Factory for creating rate limit tracker with default dependencies."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from .tracker import RateLimitTracker
from .storage import RateLimitStorage, FileSystemAdapter
from .policy import RateLimitPolicy
from .calculator import RateLimitCalculator
from .recommender import RateLimitRecommender
from ..config import OrchestratorConfig


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
    # Convert to Path if string
    path = Path(tracker_file) if tracker_file else None

    # Create dependencies
    file_system = FileSystemAdapter()
    storage = RateLimitStorage(path, file_system)
    policy = RateLimitPolicy()
    calculator = RateLimitCalculator()

    # Create tracker first (needed by recommender)
    tracker = RateLimitTracker(
        storage=storage,
        policy=policy,
        calculator=calculator,
        recommender=None,  # type: ignore - will be set next
        auto_load=False,  # Load after recommender is set
        config=config,
    )

    # Create recommender with tracker as usage query
    recommender = RateLimitRecommender(tracker)

    # Inject recommender
    tracker._recommender = recommender

    # Now load if requested
    if auto_load:
        tracker.restore_from_disk()

    return tracker
