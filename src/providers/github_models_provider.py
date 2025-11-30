"""
GitHub Models LLM Provider implementation.

GitHub Models provides access to premium models via GitHub PAT:
- GPT-4o: 10,000 requests/day, 10M tokens/day
- GPT-4o-mini: 20,000 requests/day, 2M tokens/day
- DeepSeek R1, Grok-3, Llama 4, Phi-4, and more
"""

import logging
import os
import time
from typing import Optional

from .base import LLMProviderBase, LLMResponse, ProviderLimits, SpeedRank, QualityRank
from ..utils.imports import safe_import
from ..utils.errors import raise_package_not_installed, raise_env_var_not_found, raise_model_not_supported

logger = logging.getLogger(__name__)

# Safe imports for optional dependencies
_openai_module, OPENAI_AVAILABLE = safe_import('openai')
OpenAI = getattr(_openai_module, 'OpenAI', None) if _openai_module else None

httpx, HTTPX_AVAILABLE = safe_import('httpx')


class GitHubModelsProvider(LLMProviderBase):
    """
    GitHub Models provider for premium LLM access.

    Environment variable required: GITHUB_API_KEY (Personal Access Token with `models` scope)

    Free tier limits (as of 2025-11):
    - GPT-4o: 10,000 requests/day, 10M tokens/day
    - GPT-4o-mini: 20,000 requests/day, 2M tokens/day
    - Other models: Limits not exposed in headers
    """

    # Model configurations
    MODELS = {
        'gpt-4o': {
            'rpd': 10000, 'tpd': 10000000,
            'context': 128000, 'speed': SpeedRank.MODERATE, 'quality': QualityRank.EXCELLENT
        },
        'gpt-4o-mini': {
            'rpd': 20000, 'tpd': 2000000,
            'context': 128000, 'speed': SpeedRank.FAST, 'quality': QualityRank.VERY_GOOD
        },
        'deepseek-r1': {
            'rpd': None, 'tpd': None,  # Unknown - no headers returned
            'context': 64000, 'speed': SpeedRank.MODERATE, 'quality': QualityRank.EXCELLENT,
            'reasoning': True
        },
        'grok-3-mini': {
            'rpd': None, 'tpd': None,
            'context': 131072, 'speed': SpeedRank.FAST, 'quality': QualityRank.VERY_GOOD
        },
        'meta-llama-3.1-8b-instruct': {
            'rpd': None, 'tpd': None,
            'context': 128000, 'speed': SpeedRank.VERY_FAST, 'quality': QualityRank.GOOD
        },
        'llama-4-scout-17b-16e-instruct': {
            'rpd': None, 'tpd': None,
            'context': 10000000, 'speed': SpeedRank.FAST, 'quality': QualityRank.VERY_GOOD
        },
        'phi-4': {
            'rpd': None, 'tpd': None,
            'context': 16384, 'speed': SpeedRank.VERY_FAST, 'quality': QualityRank.GOOD
        },
        'mistral-small-2503': {
            'rpd': None, 'tpd': None,
            'context': 32768, 'speed': SpeedRank.FAST, 'quality': QualityRank.GOOD
        },
        'cohere-command-a': {
            'rpd': None, 'tpd': None,
            'context': 256000, 'speed': SpeedRank.MODERATE, 'quality': QualityRank.VERY_GOOD
        },
    }

    BASE_URL = "https://models.github.ai/inference"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional["OpenAI"] = None,
        initial_limits: Optional[ProviderLimits] = None
    ):
        """
        Initialize GitHub Models provider.

        Args:
            api_key: GitHub PAT with models scope (defaults to GITHUB_API_KEY env var)
            client: Optional OpenAI client instance
            initial_limits: Optional initial provider limits
        """
        if not OPENAI_AVAILABLE:
            raise_package_not_installed('openai')

        self._api_key = api_key or os.environ.get('GITHUB_API_KEY')
        if not self._api_key and client is None:
            raise_env_var_not_found('GITHUB_API_KEY')

        self._client = client or self._create_default_client()
        self._last_limits = initial_limits or self._create_default_limits()

    def _create_default_client(self) -> "OpenAI":
        """Create default OpenAI client."""
        return OpenAI(
            api_key=self._api_key,
            base_url=self.BASE_URL
        )

    def _create_default_limits(self) -> ProviderLimits:
        """Create default provider limits."""
        return ProviderLimits()

    @property
    def name(self) -> str:
        return 'github'

    @property
    def available_models(self) -> list[str]:
        return list(self.MODELS.keys())

    @property
    def default_model(self) -> str:
        return 'gpt-4o'

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion to GitHub Models.

        GitHub Models uses OpenAI-compatible API format.
        """
        model = model or self.default_model

        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        start_time = time.time()

        # Use with_raw_response to get headers for rate limit info
        raw_response = self._client.chat.completions.with_raw_response.create(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        latency_ms = (time.time() - start_time) * 1000
        response = raw_response.parse()

        # Extract usage info
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Extract rate limit info from headers
        headers = raw_response.headers
        remaining_requests = headers.get('x-ratelimit-remaining-requests')
        remaining_tokens = headers.get('x-ratelimit-remaining-tokens')
        limit_requests = headers.get('x-ratelimit-limit-requests')
        limit_tokens = headers.get('x-ratelimit-limit-tokens')

        # Update cached limits
        if remaining_requests is not None:
            self._last_limits = ProviderLimits(
                requests_per_day=int(limit_requests) if limit_requests else None,
                tokens_per_day=int(limit_tokens) if limit_tokens else None,
                remaining_requests=int(remaining_requests),
                remaining_tokens=int(remaining_tokens) if remaining_tokens else None,
            )

        metadata = {
            'finish_reason': response.choices[0].finish_reason,
            'model_config': self.MODELS.get(model, {}),
            'rate_limits': {
                'remaining_requests': remaining_requests,
                'remaining_tokens': remaining_tokens,
                'limit_requests': limit_requests,
                'limit_tokens': limit_tokens,
            },
            'region': headers.get('x-ms-region', 'unknown'),
        }

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=response,
            metadata=metadata
        )

    def get_limits(self) -> ProviderLimits:
        """
        Get rate limit info.

        GitHub Models provides limits in response headers:
        - x-ratelimit-limit-requests
        - x-ratelimit-remaining-requests
        - x-ratelimit-limit-tokens
        - x-ratelimit-remaining-tokens
        """
        # Return cached limits if available, otherwise use model defaults
        if self._last_limits.remaining_requests is not None:
            return self._last_limits

        model_limits = self.MODELS.get(self.default_model, {})
        return ProviderLimits(
            requests_per_day=model_limits.get('rpd'),
            tokens_per_day=model_limits.get('tpd'),
        )

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        max_retries: int = 3,
        **kwargs
    ) -> LLMResponse:
        """
        Async version using httpx for true non-blocking HTTP calls.

        Includes automatic retry with exponential backoff for rate limits.
        """
        if not HTTPX_AVAILABLE:
            # Fallback to default executor-based async
            return await super().chat_async(messages, model, max_tokens, temperature, **kwargs)

        model = model or self.default_model

        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        # Build request payload
        payload = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        # Remove max_retries from kwargs if present
        kwargs.pop('max_retries', None)
        payload.update(kwargs)

        headers = {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }

        import asyncio
        last_error = None

        for attempt in range(max_retries):
            start_time = time.time()

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.BASE_URL}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=120.0  # Longer timeout for complex models
                    )

                    if response.status_code == 429:
                        # Rate limited - wait and retry
                        wait_time = 2 ** attempt
                        logger.warning(f"[GitHub Models] Rate limited, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        last_error = Exception(f"Rate limit (429) on attempt {attempt+1}")
                        continue

                    response.raise_for_status()
                    data = response.json()

                latency_ms = (time.time() - start_time) * 1000

                # Extract usage info
                usage = data.get('usage', {})
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)

                # Extract content
                content = data['choices'][0]['message']['content']
                finish_reason = data['choices'][0].get('finish_reason', 'unknown')

                # Extract rate limit info from headers
                remaining_requests = response.headers.get('x-ratelimit-remaining-requests')
                remaining_tokens = response.headers.get('x-ratelimit-remaining-tokens')
                limit_requests = response.headers.get('x-ratelimit-limit-requests')
                limit_tokens = response.headers.get('x-ratelimit-limit-tokens')

                # Update cached limits
                if remaining_requests is not None:
                    self._last_limits = ProviderLimits(
                        requests_per_day=int(limit_requests) if limit_requests else None,
                        tokens_per_day=int(limit_tokens) if limit_tokens else None,
                        remaining_requests=int(remaining_requests),
                        remaining_tokens=int(remaining_tokens) if remaining_tokens else None,
                    )

                metadata = {
                    'finish_reason': finish_reason,
                    'model_config': self.MODELS.get(model, {}),
                    'async': True,
                    'retry_attempts': attempt,
                    'rate_limits': {
                        'remaining_requests': remaining_requests,
                        'remaining_tokens': remaining_tokens,
                        'limit_requests': limit_requests,
                        'limit_tokens': limit_tokens,
                    },
                    'region': response.headers.get('x-ms-region', 'unknown'),
                }

                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.name,
                    tokens_used=input_tokens + output_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    raw_response=data,
                    metadata=metadata
                )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"[GitHub Models] Rate limited, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    last_error = e
                    continue
                raise

        # All retries exhausted
        raise last_error or Exception("Max retries exhausted")

    def is_available(self) -> bool:
        """Check if GitHub Models is properly configured."""
        return bool(self._api_key and OPENAI_AVAILABLE)
