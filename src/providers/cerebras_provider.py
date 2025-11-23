"""
Cerebras LLM Provider implementation.

Cerebras provides extremely fast inference on specialized hardware with excellent free tier:
- 14,400 requests/day
- 60,000 tokens/minute
- Models: Llama 3.1 (8B, 70B)
"""

import logging
import os
import time
import json
from typing import Optional

from .base import LLMProvider, LLMResponse, ProviderLimits, ModelInfo, ToolCall
from ..utils.imports import safe_import
from ..utils.errors import raise_package_not_installed, raise_env_var_not_found, raise_model_not_supported

logger = logging.getLogger(__name__)

# Safe imports for optional dependencies
_openai_module, OPENAI_AVAILABLE = safe_import('openai')
OpenAI = getattr(_openai_module, 'OpenAI', None) if _openai_module else None

httpx, HTTPX_AVAILABLE = safe_import('httpx')


class CerebrasProvider(LLMProvider):
    """
    Cerebras provider for ultra-fast LLM inference.

    Environment variable required: CEREBRAS_API_KEY

    Free tier limits (as of 2025-11):
    - 14,400 requests/day (all models)
    - 60,000 tokens/minute
    - Models: llama3.1-8b, llama3.1-70b
    """

    # Model configurations
    MODELS = {
        'llama3.1-8b': {
            'rpd': 14400, 'tpm': 60000,
            'context': 8192, 'speed': 'ultra_fast', 'quality': 'good'
        },
        'llama-3.3-70b': {
            'rpd': 14400, 'tpm': 60000,
            'context': 8192, 'speed': 'very_fast', 'quality': 'excellent'
        },
        'qwen-3-32b': {
            'rpd': 14400, 'tpm': 60000,
            'context': 8192, 'speed': 'very_fast', 'quality': 'very_good'
        },
        # New instruction-tuned model (added 2025-11) - excellent JSON compliance
        'qwen-3-235b-a22b-instruct-2507': {
            'rpd': 14400, 'tpm': 60000,
            'context': 8192, 'speed': 'fast', 'quality': 'excellent'
        },
    }

    BASE_URL = "https://api.cerebras.ai/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional["OpenAI"] = None,
        initial_limits: Optional[ProviderLimits] = None
    ):
        """
        Initialize Cerebras provider.

        Args:
            api_key: Cerebras API key (defaults to CEREBRAS_API_KEY env var)
            client: Optional OpenAI client instance
            initial_limits: Optional initial provider limits
        """
        if not OPENAI_AVAILABLE:
            raise_package_not_installed('openai')

        self._api_key = api_key or os.environ.get('CEREBRAS_API_KEY')
        if not self._api_key and client is None:
            raise_env_var_not_found('CEREBRAS_API_KEY')

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
        return 'cerebras'

    @property
    def available_models(self) -> list[str]:
        return list(self.MODELS.keys())

    @property
    def default_model(self) -> str:
        return 'llama3.1-8b'

    @property
    def supports_tool_calling(self) -> bool:
        """Cerebras supports native tool calling via OpenAI-compatible API."""
        return True

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion to Cerebras.

        Cerebras uses OpenAI-compatible API format.
        """
        model = model or self.default_model

        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        start_time = time.time()

        response = self._client.chat.completions.create(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        latency_ms = (time.time() - start_time) * 1000

        # Extract usage info
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Cerebras includes performance metrics in usage
        metadata = {
            'finish_reason': response.choices[0].finish_reason,
            'model_config': self.MODELS.get(model, {}),
        }

        # Add Cerebras-specific performance metrics if available
        if hasattr(usage, 'completion_tokens_per_sec'):
            metadata['tokens_per_sec'] = getattr(usage, 'completion_tokens_per_sec', None)
        if hasattr(usage, 'total_latency'):
            metadata['cerebras_latency'] = getattr(usage, 'total_latency', None)

        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=response,
            metadata=metadata
        )

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str = "auto",
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion with native tool calling to Cerebras.

        Args:
            messages: List of message dicts
            tools: OpenAI-compatible tool schemas
            tool_choice: How model should choose tools ("auto", "none", etc.)
            model: Model to use (defaults to default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            LLMResponse with tool_calls populated if model called tools
        """
        model = model or self.default_model

        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        start_time = time.time()

        response = self._client.chat.completions.create(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        latency_ms = (time.time() - start_time) * 1000

        # Extract usage info
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Build metadata
        metadata = {
            'finish_reason': response.choices[0].finish_reason,
            'model_config': self.MODELS.get(model, {}),
        }

        # Add Cerebras-specific performance metrics if available
        if hasattr(usage, 'completion_tokens_per_sec'):
            metadata['tokens_per_sec'] = getattr(usage, 'completion_tokens_per_sec', None)
        if hasattr(usage, 'total_latency'):
            metadata['cerebras_latency'] = getattr(usage, 'total_latency', None)

        # Extract tool calls if present
        tool_calls = None
        message = response.choices[0].message
        if hasattr(message, 'tool_calls') and message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))

        return LLMResponse(
            content=message.content or "",
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=response,
            metadata=metadata,
            tool_calls=tool_calls
        )

    def get_limits(self) -> ProviderLimits:
        """
        Get rate limit info.

        Cerebras provides limits in response headers:
        - x-ratelimit-limit-requests-day
        - x-ratelimit-limit-tokens-minute
        - x-ratelimit-remaining-requests-day
        - x-ratelimit-remaining-tokens-minute
        """
        model_limits = self.MODELS.get(self.default_model, {})
        return ProviderLimits(
            requests_per_day=model_limits.get('rpd'),
            tokens_per_minute=model_limits.get('tpm'),
        )

    def get_model_for_task(self, task_type: str) -> str:
        """
        Recommend a model based on task type.

        Args:
            task_type: 'fast' for quick responses, 'quality' for best results

        Returns:
            Recommended model name
        """
        if task_type == 'fast' or task_type == 'high_volume':
            return 'llama3.1-8b'
        elif task_type == 'quality':
            return 'llama-3.3-70b'
        else:
            return self.default_model

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
                        timeout=60.0
                    )

                    if response.status_code == 429:
                        # Rate limited - wait and retry
                        wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                        logger.warning(f"[Cerebras] Rate limited, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
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

                metadata = {
                    'finish_reason': finish_reason,
                    'model_config': self.MODELS.get(model, {}),
                    'async': True,
                    'retry_attempts': attempt,
                }

                # Add Cerebras-specific performance metrics if available
                if 'completion_tokens_per_sec' in usage:
                    metadata['tokens_per_sec'] = usage.get('completion_tokens_per_sec')
                if 'total_latency' in usage:
                    metadata['cerebras_latency'] = usage.get('total_latency')

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
                    logger.warning(f"[Cerebras] Rate limited, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    last_error = e
                    continue
                raise

        # All retries exhausted
        raise last_error or Exception("Max retries exhausted")

    def is_available(self) -> bool:
        """Check if Cerebras is properly configured."""
        return bool(self._api_key and OPENAI_AVAILABLE)

    def get_model_info(self, model_id: str) -> ModelInfo:
        """
        Get detailed information about a specific model.

        Uses the MODELS configuration dictionary to provide accurate info.

        Args:
            model_id: Model identifier

        Returns:
            ModelInfo with model metadata
        """
        if model_id in self.MODELS:
            return ModelInfo.from_config(model_id, self.MODELS[model_id])
        else:
            # Fall back to auto-detection for unknown models
            return super().get_model_info(model_id)
