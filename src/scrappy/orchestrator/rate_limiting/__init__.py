"""Rate limiting package."""
from .tracker import RateLimitTracker
from .factory import (
    create_rate_limit_tracker,
    create_rate_limit_components,
    create_enforcement_components,
    RateLimitComponents,
    EnforcementComponents,
)
from .calculator import RateLimitCalculator
from .policy import RateLimitPolicy
from .recommender import RateLimitRecommender
from .scorer import QuotaScorer
from .enforcement import RateLimitEnforcementPolicy
from .notifier import RateLimitNotifier, NullNotifier
from .httpx_patcher import (
    install_rate_limit_hooks,
    uninstall_rate_limit_hooks,
    is_installed as is_rate_limit_hooks_installed,
)
from .protocols import (
    # Existing protocols
    StorageProtocol,
    PolicyProtocol,
    CalculatorProtocol,
    RecommenderProtocol,
    UsageQueryProtocol,
    FileSystemProtocol,
    # Enforcement protocols and types
    EnforcementAction,
    EnforcementDecision,
    EnforcementPolicyProtocol,
    QuotaScore,
    QuotaScorerProtocol,
    UserNotifierProtocol,
    NotificationLevel,
)

__all__ = [
    # Main API
    "RateLimitTracker",
    "create_rate_limit_tracker",
    "create_rate_limit_components",
    "create_enforcement_components",
    "RateLimitComponents",
    "EnforcementComponents",

    # Components (for testing)
    "RateLimitCalculator",
    "RateLimitPolicy",
    "RateLimitRecommender",

    # Enforcement components
    "QuotaScorer",
    "RateLimitEnforcementPolicy",
    "RateLimitNotifier",
    "NullNotifier",

    # HTTP header capture
    "install_rate_limit_hooks",
    "uninstall_rate_limit_hooks",
    "is_rate_limit_hooks_installed",

    # Protocols (for testing and custom implementations)
    "StorageProtocol",
    "PolicyProtocol",
    "CalculatorProtocol",
    "RecommenderProtocol",
    "UsageQueryProtocol",
    "FileSystemProtocol",

    # Enforcement protocols and types
    "EnforcementAction",
    "EnforcementDecision",
    "EnforcementPolicyProtocol",
    "QuotaScore",
    "QuotaScorerProtocol",
    "UserNotifierProtocol",
    "NotificationLevel",
]
