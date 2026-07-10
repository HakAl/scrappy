"""
Shared retry-after extraction from provider exceptions.

Single parser for server-reported cooldown hints, used by:
- litellm_service exception mapping (attaches retry_after to ProviderError,
  which drives model cooldowns via mark_unhealthy)
- litellm_callbacks failure logging (records provider-scoped retry_at in the
  rate limit tracker for /rate-limits display and the legacy recommender)

Values returned here are raw (unbounded). The selection-path consumer clamps
at mark_unhealthy; any future consumer that turns these into cooldowns must
bound them too.
"""

from email.utils import parsedate_to_datetime
import re
import time
from typing import Callable, Optional


def extract_retry_after(
    error: Exception,
    now: Callable[[], float] = time.time,
) -> Optional[float]:
    """Extract retry-after time from a provider exception.

    Checks multiple sources:
    1. response headers (Retry-After, x-ratelimit-reset-requests)
    2. error body for retry_after field
    3. error message for time patterns

    Args:
        error: A litellm exception (usually RateLimitError)
        now: Clock returning epoch seconds (for HTTP-date headers)

    Returns:
        Retry-after time in seconds, or None if not available
    """
    # Try response headers first
    response = getattr(error, 'response', None)
    if response:
        headers = getattr(response, 'headers', {})
        if headers:
            # Standard Retry-After header (seconds or HTTP date)
            retry_after = headers.get('Retry-After') or headers.get('retry-after')
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    parsed_delta = _parse_retry_after_http_date(retry_after, now)
                    if parsed_delta is not None:
                        return parsed_delta

            # OpenAI/Anthropic rate limit headers
            reset_requests = headers.get('x-ratelimit-reset-requests')
            reset_tokens = headers.get('x-ratelimit-reset-tokens')
            if reset_requests:
                # Parse time like "1s", "1m30s", "1h"
                return _parse_time_string(reset_requests)
            if reset_tokens:
                return _parse_time_string(reset_tokens)

    # Try error body
    body = getattr(error, 'body', None)
    if body and isinstance(body, dict):
        retry = body.get('retry_after') or body.get('retryAfter')
        if retry:
            try:
                return float(retry)
            except (ValueError, TypeError):
                pass

    # Try parsing from error message (e.g., "retry after 45 seconds").
    # The duration must be adjacent to a retry/wait phrase: a message where
    # 'retry' or 'wait' merely co-occurs with an unrelated duration (latency
    # reports, context windows) must not extract.
    message = str(error).lower()
    time_match = re.search(
        r'(?:retry(?:ing)?\s+(?:in|after)|try again in|available (?:again )?in'
        r'|wait(?:ing)?(?:\s+for)?)'
        r'\s*:?\s*(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|secs?|mins?|s|m|h)\b',
        message,
    )
    if time_match:
        value = float(time_match.group(1))
        unit = time_match.group(2)
        if unit.startswith('m'):
            value *= 60
        elif unit.startswith('h'):
            value *= 3600
        return value

    return None


def _parse_retry_after_http_date(
    retry_after: str,
    now: Callable[[], float],
) -> Optional[float]:
    """Parse Retry-After HTTP-date header into seconds from now."""
    try:
        parsed = parsedate_to_datetime(retry_after)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None

    if parsed.tzinfo is None:
        from datetime import timezone
        parsed = parsed.replace(tzinfo=timezone.utc)

    return max(0.0, parsed.timestamp() - now())


def _parse_time_string(time_str: str) -> Optional[float]:
    """Parse time strings like '1s', '1m30s', '1h2m3s' into seconds."""
    total_seconds = 0.0
    time_str = time_str.lower().strip()

    # Match hours, minutes, seconds patterns
    hours = re.search(r'(\d+(?:\.\d+)?)\s*h', time_str)
    minutes = re.search(r'(\d+(?:\.\d+)?)\s*m(?!s)', time_str)  # m but not ms
    seconds = re.search(r'(\d+(?:\.\d+)?)\s*s', time_str)

    if hours:
        total_seconds += float(hours.group(1)) * 3600
    if minutes:
        total_seconds += float(minutes.group(1)) * 60
    if seconds:
        total_seconds += float(seconds.group(1))

    # If no time units found, try parsing as plain number
    if total_seconds == 0.0 and time_str:
        try:
            total_seconds = float(time_str)
        except ValueError:
            return None

    return total_seconds if total_seconds > 0 else None
