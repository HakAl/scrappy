"""
Persistent rate limit tracking for LLM providers.

Tracks usage across sessions and provides quota monitoring.
"""

from typing import Optional, TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import json

if TYPE_CHECKING:
    from ..providers import ProviderLimits


class RateLimitTracker:
    """
    Persistent rate limit tracking for LLM providers.

    Features:
    - Tracks requests and tokens per provider/model
    - Persists to disk for tracking across sessions
    - Automatic reset for daily/monthly limits
    - Proactive quota monitoring
    """

    def __init__(self, tracker_file: Optional[str] = None):
        """
        Initialize rate limit tracker.

        Args:
            tracker_file: Path to persistent tracker file (optional)
        """
        self._usage: dict = {}
        self.tracker_file = Path(tracker_file) if tracker_file else None

        # Load existing data if available
        if self.tracker_file and self.tracker_file.exists():
            self._load_tracker()
        else:
            self._initialize_empty()

    def _initialize_empty(self):
        """Initialize empty tracking structure."""
        self._usage = {
            'providers': {},  # provider -> model -> usage data
            'last_reset': {
                'daily': datetime.now().date().isoformat(),
                'monthly': datetime.now().strftime('%Y-%m')
            },
            'created_at': datetime.now().isoformat()
        }

    def _load_tracker(self):
        """Load tracker data from disk."""
        try:
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                self._usage = json.load(f)

            # Check for resets needed
            self._check_and_reset()
        except Exception:
            self._initialize_empty()

    def _save_tracker(self):
        """Save tracker data to disk."""
        if not self.tracker_file:
            return

        try:
            with open(self.tracker_file, 'w', encoding='utf-8') as f:
                json.dump(self._usage, f, indent=2)
        except Exception:
            pass  # Silently fail on write errors

    def _check_and_reset(self):
        """Check if daily or monthly resets are needed."""
        current_date = datetime.now().date().isoformat()
        current_month = datetime.now().strftime('%Y-%m')

        needs_save = False

        # Check daily reset
        if self._usage.get('last_reset', {}).get('daily') != current_date:
            self._reset_daily_limits()
            self._usage['last_reset']['daily'] = current_date
            needs_save = True

        # Check monthly reset
        if self._usage.get('last_reset', {}).get('monthly') != current_month:
            self._reset_monthly_limits()
            self._usage['last_reset']['monthly'] = current_month
            needs_save = True

        if needs_save:
            self._save_tracker()

    def _reset_daily_limits(self):
        """Reset daily request and token counters."""
        for provider_data in self._usage.get('providers', {}).values():
            for model_data in provider_data.values():
                model_data['requests_today'] = 0
                model_data['tokens_today'] = 0
                model_data['input_tokens_today'] = 0
                model_data['output_tokens_today'] = 0

    def _reset_monthly_limits(self):
        """Reset monthly request counters."""
        for provider_data in self._usage.get('providers', {}).values():
            for model_data in provider_data.values():
                model_data['requests_this_month'] = 0
                model_data['tokens_this_month'] = 0

    def _ensure_provider_model(self, provider: str, model: str):
        """Ensure tracking structure exists for provider/model."""
        if 'providers' not in self._usage:
            self._usage['providers'] = {}

        if provider not in self._usage['providers']:
            self._usage['providers'][provider] = {}

        if model not in self._usage['providers'][provider]:
            self._usage['providers'][provider][model] = {
                'requests_today': 0,
                'requests_this_month': 0,
                'tokens_today': 0,
                'tokens_this_month': 0,
                'input_tokens_today': 0,
                'output_tokens_today': 0,
                'total_requests': 0,
                'total_tokens': 0,
                'last_request': None,
                'errors': []
            }

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        Record a completed API request.

        Args:
            provider: Provider name
            model: Model used
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            success: Whether request succeeded
            error_message: Error message if failed
        """
        # Check for resets first
        self._check_and_reset()

        self._ensure_provider_model(provider, model)
        model_data = self._usage['providers'][provider][model]

        total_tokens = input_tokens + output_tokens

        # Update counters
        model_data['requests_today'] += 1
        model_data['requests_this_month'] += 1
        model_data['total_requests'] += 1

        model_data['tokens_today'] += total_tokens
        model_data['tokens_this_month'] += total_tokens
        model_data['total_tokens'] += total_tokens

        model_data['input_tokens_today'] += input_tokens
        model_data['output_tokens_today'] += output_tokens

        model_data['last_request'] = datetime.now().isoformat()

        # Track errors
        if not success and error_message:
            model_data['errors'].append({
                'timestamp': datetime.now().isoformat(),
                'message': error_message[:200]  # Truncate long errors
            })
            # Keep only last 10 errors
            model_data['errors'] = model_data['errors'][-10:]

        self._save_tracker()

    def get_usage(self, provider: str, model: Optional[str] = None) -> dict:
        """
        Get current usage for a provider/model.

        Args:
            provider: Provider name
            model: Specific model (optional, returns all models if not specified)

        Returns:
            Usage statistics dict
        """
        self._check_and_reset()

        if provider not in self._usage.get('providers', {}):
            return {}

        if model:
            return self._usage['providers'][provider].get(model, {})

        return self._usage['providers'][provider]

    def get_remaining_quota(self, provider: str, model: str, limits: 'ProviderLimits') -> dict:
        """
        Calculate remaining quota for a provider/model.

        Args:
            provider: Provider name
            model: Model name
            limits: ProviderLimits from provider

        Returns:
            Dict with remaining requests and tokens
        """
        self._check_and_reset()
        self._ensure_provider_model(provider, model)

        usage = self._usage['providers'][provider][model]

        remaining = {
            'requests_remaining_today': None,
            'requests_remaining_month': None,
            'tokens_remaining_today': None,
            'tokens_remaining_minute': None,
            'usage_today': usage['requests_today'],
            'tokens_today': usage['tokens_today'],
            'usage_this_month': usage['requests_this_month']
        }

        # Calculate remaining based on limits
        if limits.requests_per_day:
            remaining['requests_remaining_today'] = max(0, limits.requests_per_day - usage['requests_today'])

        if limits.requests_per_month:
            remaining['requests_remaining_month'] = max(0, limits.requests_per_month - usage['requests_this_month'])

        if limits.tokens_per_day:
            remaining['tokens_remaining_today'] = max(0, limits.tokens_per_day - usage['tokens_today'])

        if limits.tokens_per_minute:
            remaining['tokens_remaining_minute'] = limits.tokens_per_minute  # Can't track minute-level precisely

        return remaining

    def is_limit_approaching(self, provider: str, model: str, limits: 'ProviderLimits', threshold: float = 0.1) -> dict:
        """
        Check if approaching rate limits (within threshold of limit).

        Args:
            provider: Provider name
            model: Model name
            limits: ProviderLimits from provider
            threshold: Warning threshold (0.1 = warn at 90% usage)

        Returns:
            Dict with warning flags
        """
        remaining = self.get_remaining_quota(provider, model, limits)
        warnings = {
            'approaching_daily_request_limit': False,
            'approaching_monthly_request_limit': False,
            'approaching_daily_token_limit': False,
            'message': None
        }

        messages = []

        if limits.requests_per_day and remaining['requests_remaining_today'] is not None:
            if remaining['requests_remaining_today'] <= limits.requests_per_day * threshold:
                warnings['approaching_daily_request_limit'] = True
                messages.append(f"Only {remaining['requests_remaining_today']} requests remaining today")

        if limits.requests_per_month and remaining['requests_remaining_month'] is not None:
            if remaining['requests_remaining_month'] <= limits.requests_per_month * threshold:
                warnings['approaching_monthly_request_limit'] = True
                messages.append(f"Only {remaining['requests_remaining_month']} requests remaining this month")

        if limits.tokens_per_day and remaining['tokens_remaining_today'] is not None:
            if remaining['tokens_remaining_today'] <= limits.tokens_per_day * threshold:
                warnings['approaching_daily_token_limit'] = True
                messages.append(f"Only {remaining['tokens_remaining_today']} tokens remaining today")

        if messages:
            warnings['message'] = f"{provider}/{model}: " + ", ".join(messages)

        return warnings

    def get_all_usage_summary(self) -> dict:
        """Get summary of all provider usage."""
        self._check_and_reset()

        summary = {
            'last_reset': self._usage.get('last_reset', {}),
            'providers': {}
        }

        for provider, models in self._usage.get('providers', {}).items():
            summary['providers'][provider] = {
                'total_requests_today': sum(m.get('requests_today', 0) for m in models.values()),
                'total_tokens_today': sum(m.get('tokens_today', 0) for m in models.values()),
                'total_requests_month': sum(m.get('requests_this_month', 0) for m in models.values()),
                'models': list(models.keys()),
                'by_model': {
                    model: {
                        'requests_today': data.get('requests_today', 0),
                        'tokens_today': data.get('tokens_today', 0),
                        'last_request': data.get('last_request')
                    }
                    for model, data in models.items()
                }
            }

        return summary

    def clear(self):
        """Clear all tracking data."""
        self._initialize_empty()
        if self.tracker_file and self.tracker_file.exists():
            self.tracker_file.unlink()

    def reset_provider(self, provider: str):
        """Reset usage for a specific provider."""
        if provider in self._usage.get('providers', {}):
            del self._usage['providers'][provider]
            self._save_tracker()
