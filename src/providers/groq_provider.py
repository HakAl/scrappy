"""
Groq LLM Provider implementation.

Groq provides fast inference for open-source models with generous free tier:
- 30 RPM, 1000-7000 RPD depending on model
- 12K-20K TPM, 100K-200K TPD
- Models: Llama 3.x, Mixtral, Gemma
"""

import os
import time
import json
from typing import Optional

from .base import LLMProvider, LLMResponse, ProviderLimits, ModelInfo, ToolCall
from ..utils.imports import safe_import
from ..utils.errors import raise_package_not_installed, raise_env_var_not_found, raise_model_not_supported

# Safe imports for optional dependencies
_groq_module, GROQ_AVAILABLE = safe_import('groq')
Groq = getattr(_groq_module, 'Groq', None) if _groq_module else None

httpx, HTTPX_AVAILABLE = safe_import('httpx')


class GroqProvider(LLMProvider):
    """
    Groq provider for fast LLM inference.

    Environment variable required: GROQ_API_KEY

    Free tier limits (as of 2025):
    - llama-3.1-8b-instant: 30 RPM, 7000 RPD, 20K TPM, 200K TPD
    - llama-3.3-70b-versatile: 30 RPM, 1000 RPD, 12K TPM, 100K TPD
    - mixtral-8x7b-32768: 30 RPM, 14400 RPD, 5K TPM
    """

    # Model configurations with relative costs/speeds
    MODELS = {
        'llama-3.1-8b-instant': {
            'rpm': 30, 'rpd': 7000, 'tpm': 20000, 'tpd': 200000,
            'context': 131072, 'speed': 'very_fast', 'quality': 'good'
        },
        'llama-3.3-70b-versatile': {
            'rpm': 30, 'rpd': 1000, 'tpm': 12000, 'tpd': 100000,
            'context': 32768, 'speed': 'fast', 'quality': 'excellent'
        },
        'llama-3.1-70b-versatile': {
            'rpm': 30, 'rpd': 1000, 'tpm': 12000, 'tpd': 100000,
            'context': 32768, 'speed': 'fast', 'quality': 'excellent'
        },
        'mixtral-8x7b-32768': {
            'rpm': 30, 'rpd': 14400, 'tpm': 5000, 'tpd': None,
            'context': 32768, 'speed': 'fast', 'quality': 'very_good'
        },
        # gemma2-9b-it removed - decommissioned by Groq as of 2025-11
        # New instruction-tuned models (added 2025-11)
        'meta-llama/llama-4-scout-17b-16e-instruct': {
            'rpm': 30, 'rpd': 7000, 'tpm': 20000, 'tpd': 200000,
            'context': 16384, 'speed': 'ultra_fast', 'quality': 'excellent'
        },
        'moonshotai/kimi-k2-instruct': {
            'rpm': 30, 'rpd': 7000, 'tpm': 20000, 'tpd': 200000,
            'context': 131072, 'speed': 'ultra_fast', 'quality': 'excellent'
        },
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Groq provider.

        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
        """
        if not GROQ_AVAILABLE:
            raise_package_not_installed('groq')

        self._api_key = api_key or os.environ.get('GROQ_API_KEY')
        if not self._api_key:
            raise_env_var_not_found('GROQ_API_KEY')

        self._client = Groq(api_key=self._api_key)
        self._last_limits = ProviderLimits()

    @property
    def name(self) -> str:
        return 'groq'

    @property
    def available_models(self) -> list[str]:
        return list(self.MODELS.keys())

    @property
    def default_model(self) -> str:
        # Default to fast, high-quota model
        return 'llama-3.1-8b-instant'

    @property
    def supports_tool_calling(self) -> bool:
        """Groq supports native tool calling via OpenAI-compatible API."""
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
        Send chat completion to Groq.

        Groq uses OpenAI-compatible message format:
        [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}]
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

        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=response,
            metadata={
                'finish_reason': response.choices[0].finish_reason,
                'model_config': self.MODELS.get(model, {}),
            }
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
        Send chat completion with native tool calling to Groq.

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
            metadata={
                'finish_reason': response.choices[0].finish_reason,
                'model_config': self.MODELS.get(model, {}),
            },
            tool_calls=tool_calls
        )

    def get_limits(self) -> ProviderLimits:
        """
        Get rate limit info.

        Note: Groq includes rate limit headers in responses, but we return
        configured limits. For real-time limits, check response headers.
        """
        # Return limits for default model
        model_limits = self.MODELS.get(self.default_model, {})
        return ProviderLimits(
            requests_per_minute=model_limits.get('rpm'),
            requests_per_day=model_limits.get('rpd'),
            tokens_per_minute=model_limits.get('tpm'),
            tokens_per_day=model_limits.get('tpd'),
        )

    def get_model_for_task(self, task_type: str) -> str:
        """
        Recommend a model based on task type.

        Args:
            task_type: 'fast' for quick responses, 'quality' for best results,
                      'high_volume' for many requests

        Returns:
            Recommended model name
        """
        if task_type == 'fast':
            return 'llama-3.1-8b-instant'
        elif task_type == 'quality':
            return 'llama-3.3-70b-versatile'
        elif task_type == 'high_volume':
            return 'mixtral-8x7b-32768'  # Highest RPD
        else:
            return self.default_model

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Async version using httpx for true non-blocking HTTP calls.
        """
        if not HTTPX_AVAILABLE:
            # Fallback to default executor-based async
            return await super().chat_async(messages, model, max_tokens, temperature, **kwargs)

        model = model or self.default_model

        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        start_time = time.time()

        # Build request payload
        payload = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            **kwargs
        }

        headers = {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0
            )
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

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=data,
            metadata={
                'finish_reason': finish_reason,
                'model_config': self.MODELS.get(model, {}),
                'async': True,
            }
        )

    def is_available(self) -> bool:
        """Check if Groq is properly configured."""
        return bool(self._api_key and GROQ_AVAILABLE)

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
