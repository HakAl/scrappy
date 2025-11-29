"""
Google Gemini LLM Provider with automatic model fallback.

Key feature: When a model hits rate limits, automatically falls back to other models.

Current quotas (as of 2025-11-15):
- gemini-2.0-flash-lite: 200 RPD, 1M TPD
- gemini-2.0-flash: 200 RPD, 1M TPD
- gemini-2.5-flash: 250 RPD, 250K TPD
- gemini-2.5-flash-lite: 1000 RPD, 250K TPD (highest quota!)
- gemini-2.0-flash-exp: 50 RPD
"""

import logging
import os
import time
from typing import Optional

from .base import LLMProviderBase, LLMResponse, ProviderLimits, ModelInfo, SpeedRank, QualityRank
from ..utils.imports import safe_import

logger = logging.getLogger(__name__)
from ..utils.errors import (
    raise_package_not_installed, raise_env_var_not_found,
    raise_model_not_supported, ErrorFormatter
)

# Safe imports for optional dependencies
genai, GEMINI_AVAILABLE = safe_import('google.generativeai')
if GEMINI_AVAILABLE:
    try:
        from google.api_core import exceptions as google_exceptions
    except ImportError:
        google_exceptions = None
else:
    google_exceptions = None

httpx, HTTPX_AVAILABLE = safe_import('httpx')


class GeminiProvider(LLMProviderBase):
    """
    Google Gemini provider with automatic model fallback.

    Environment variable required: GEMINI_API_KEY

    Special feature: If a model hits rate limits, automatically tries the next model.
    """

    # Models ordered by preference (quality) with their limits
    # Format: rpm_limit, rpd_limit, tpm_limit, tpd_limit
    MODELS = {
        'gemini-2.5-flash-lite': {
            'rpm': 15, 'rpd': 1000, 'tpd': 250000,
            'quality': QualityRank.GOOD, 'speed': SpeedRank.FAST, 'priority': 1
        },
        'gemini-2.0-flash-lite': {
            'rpm': 30, 'rpd': 200, 'tpd': 1000000,
            'quality': QualityRank.MODERATE, 'speed': SpeedRank.VERY_FAST, 'priority': 2
        },
        'gemini-2.0-flash': {
            'rpm': 15, 'rpd': 200, 'tpd': 1000000,
            'quality': QualityRank.GOOD, 'speed': SpeedRank.FAST, 'priority': 3
        },
        'gemini-2.5-flash': {
            'rpm': 10, 'rpd': 250, 'tpd': 250000,
            'quality': QualityRank.VERY_GOOD, 'speed': SpeedRank.MODERATE, 'priority': 4
        },
        'gemini-2.0-flash-exp': {
            'rpm': 10, 'rpd': 50, 'tpd': None,
            'quality': 'experimental', 'speed': SpeedRank.FAST, 'priority': 5
        },
    }

    # Fallback order: try models with most remaining quota first
    FALLBACK_ORDER = [
        'gemini-2.5-flash-lite',  # 1000 RPD - highest quota
        'gemini-2.0-flash-lite',  # 200 RPD, very fast
        'gemini-2.0-flash',       # 200 RPD, good quality
        'gemini-2.5-flash',       # 250 RPD, best quality
        'gemini-2.0-flash-exp',   # 50 RPD, experimental
    ]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        if not GEMINI_AVAILABLE:
            raise_package_not_installed('google-generativeai')

        self._api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self._api_key:
            raise_env_var_not_found('GEMINI_API_KEY')

        genai.configure(api_key=self._api_key)

        # Track which models have hit limits (reset periodically)
        self._limited_models: set[str] = set()
        self._model_usage: dict[str, int] = {model: 0 for model in self.MODELS}

    @property
    def name(self) -> str:
        return 'gemini'

    @property
    def available_models(self) -> list[str]:
        return list(self.MODELS.keys())

    @property
    def default_model(self) -> str:
        # Use highest quota model by default
        return 'gemini-2.5-flash-lite'

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        auto_fallback: bool = True,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion to Gemini with automatic fallback.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use (defaults to highest quota model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            auto_fallback: If True, try other models on rate limit errors
            **kwargs: Additional parameters

        Returns:
            LLMResponse with result and metadata about which model was used
        """
        model = model or self.default_model

        if auto_fallback:
            return self._chat_with_fallback(messages, model, max_tokens, temperature, **kwargs)
        else:
            return self._single_model_chat(messages, model, max_tokens, temperature, **kwargs)

    def _single_model_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> LLMResponse:
        """Execute chat with a single model (no fallback)."""
        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        # Convert messages to Gemini format
        gemini_messages = self._convert_messages(messages)

        start_time = time.time()

        # Create model instance
        generation_config = {
            'max_output_tokens': max_tokens,
            'temperature': temperature,
        }

        gemini_model = genai.GenerativeModel(
            model_name=model,
            generation_config=generation_config
        )

        # Send request
        response = gemini_model.generate_content(gemini_messages)

        latency_ms = (time.time() - start_time) * 1000

        # Track usage
        self._model_usage[model] = self._model_usage.get(model, 0) + 1

        # Extract token counts if available
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)

        return LLMResponse(
            content=response.text,
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=response,
            metadata={
                'model_config': self.MODELS.get(model, {}),
                'session_usage': self._model_usage.copy(),
                'fallback_used': False,
            }
        )

    def _chat_with_fallback(
        self,
        messages: list[dict[str, str]],
        preferred_model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> LLMResponse:
        """
        Try preferred model first, then fallback to others on rate limit.

        This is the key feature - automatically finds a working model.
        """
        # Build fallback list: preferred model first, then others
        models_to_try = [preferred_model]
        for model in self.FALLBACK_ORDER:
            if model != preferred_model and model not in self._limited_models:
                models_to_try.append(model)

        last_error = None
        attempted_models = []

        for model in models_to_try:
            attempted_models.append(model)
            try:
                response = self._single_model_chat(messages, model, max_tokens, temperature, **kwargs)

                # Success! Update metadata to show fallback path
                response.metadata['fallback_used'] = (model != preferred_model)
                response.metadata['attempted_models'] = attempted_models
                response.metadata['original_model'] = preferred_model

                if model != preferred_model:
                    logger.info(f"[Gemini] Fallback: {preferred_model} -> {model}")

                return response

            except Exception as e:
                error_str = str(e).lower()

                # Check if this is a rate limit error
                if 'quota' in error_str or 'rate' in error_str or '429' in error_str or 'resource' in error_str:
                    logger.warning(f"[Gemini] {model} rate limited, trying next...")
                    self._limited_models.add(model)
                    last_error = e
                    continue
                else:
                    # Not a rate limit error, don't try other models
                    raise

        # All models failed
        if last_error:
            raise RuntimeError(
                f"{ErrorFormatter.all_providers_rate_limited(attempted_models)}. "
                f"Last error: {last_error}"
            )
        else:
            raise RuntimeError(ErrorFormatter.no_providers_available())

    def _convert_messages(self, messages: list[dict[str, str]]) -> list:
        """
        Convert standard message format to Gemini format.

        Gemini expects a different format than OpenAI/Anthropic.
        """
        gemini_messages = []

        for msg in messages:
            role = msg['role']
            content = msg['content']

            # Map roles
            if role == 'system':
                # Gemini doesn't have system role, prepend to first user message
                # or add as a "user" message
                gemini_messages.append({
                    'role': 'user',
                    'parts': [f"System instruction: {content}"]
                })
                # Add a model acknowledgment
                gemini_messages.append({
                    'role': 'model',
                    'parts': ['Understood. I will follow these instructions.']
                })
            elif role == 'user':
                gemini_messages.append({
                    'role': 'user',
                    'parts': [content]
                })
            elif role == 'assistant':
                gemini_messages.append({
                    'role': 'model',
                    'parts': [content]
                })

        # If only one message and it's user, just return the content
        if len(gemini_messages) == 1 and gemini_messages[0]['role'] == 'user':
            return gemini_messages[0]['parts'][0]

        return gemini_messages

    def get_limits(self) -> ProviderLimits:
        """Get rate limit info for default model."""
        model_limits = self.MODELS.get(self.default_model, {})
        return ProviderLimits(
            requests_per_minute=model_limits.get('rpm'),
            requests_per_day=model_limits.get('rpd'),
            tokens_per_day=model_limits.get('tpd'),
        )

    def is_available(self) -> bool:
        """Check if Gemini is properly configured."""
        return bool(self._api_key and GEMINI_AVAILABLE)

    def reset_limited_models(self):
        """
        Reset the list of rate-limited models.

        Call this at the start of a new day or when you know limits have reset.
        """
        self._limited_models.clear()
        logger.info("[Gemini] Rate limit tracking reset")

    def get_usage_summary(self) -> dict:
        """Get summary of model usage in this session."""
        return {
            'model_usage': self._model_usage.copy(),
            'limited_models': list(self._limited_models),
            'available_models': [m for m in self.MODELS if m not in self._limited_models],
        }

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        auto_fallback: bool = True,
        **kwargs
    ) -> LLMResponse:
        """
        Async version using httpx for true non-blocking HTTP calls.
        """
        if not HTTPX_AVAILABLE:
            # Fallback to default executor-based async
            return await super().chat_async(messages, model, max_tokens, temperature, **kwargs)

        model = model or self.default_model

        if auto_fallback:
            return await self._chat_with_fallback_async(messages, model, max_tokens, temperature, **kwargs)
        else:
            return await self._single_model_chat_async(messages, model, max_tokens, temperature, **kwargs)

    async def _single_model_chat_async(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> LLMResponse:
        """Execute async chat with a single model (no fallback)."""
        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        start_time = time.time()

        # Convert messages to Gemini REST API format
        contents = self._convert_messages_for_rest(messages)

        # Build request payload
        payload = {
            'contents': contents,
            'generationConfig': {
                'maxOutputTokens': max_tokens,
                'temperature': temperature,
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self._api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                timeout=60.0
            )

            # Check for rate limit errors
            if response.status_code == 429:
                raise Exception(f"Rate limit exceeded (429) for {model}")

            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000

        # Track usage
        self._model_usage[model] = self._model_usage.get(model, 0) + 1

        # Extract content from response
        if 'candidates' not in data or not data['candidates']:
            raise ValueError(f"No response candidates from Gemini: {data}")

        content = data['candidates'][0]['content']['parts'][0]['text']

        # Extract token counts if available
        input_tokens = 0
        output_tokens = 0
        if 'usageMetadata' in data:
            input_tokens = data['usageMetadata'].get('promptTokenCount', 0)
            output_tokens = data['usageMetadata'].get('candidatesTokenCount', 0)

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
                'model_config': self.MODELS.get(model, {}),
                'session_usage': self._model_usage.copy(),
                'fallback_used': False,
                'async': True,
            }
        )

    async def _chat_with_fallback_async(
        self,
        messages: list[dict[str, str]],
        preferred_model: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> LLMResponse:
        """
        Async version: Try preferred model first, then fallback to others on rate limit.
        """
        # Build fallback list: preferred model first, then others
        models_to_try = [preferred_model]
        for model in self.FALLBACK_ORDER:
            if model != preferred_model and model not in self._limited_models:
                models_to_try.append(model)

        last_error = None
        attempted_models = []

        for model in models_to_try:
            attempted_models.append(model)
            try:
                response = await self._single_model_chat_async(messages, model, max_tokens, temperature, **kwargs)

                # Success! Update metadata to show fallback path
                response.metadata['fallback_used'] = (model != preferred_model)
                response.metadata['attempted_models'] = attempted_models
                response.metadata['original_model'] = preferred_model

                if model != preferred_model:
                    logger.info(f"[Gemini] Fallback: {preferred_model} -> {model}")

                return response

            except Exception as e:
                error_str = str(e).lower()

                # Check if this is a rate limit error
                if 'quota' in error_str or 'rate' in error_str or '429' in error_str or 'resource' in error_str:
                    logger.warning(f"[Gemini] {model} rate limited, trying next...")
                    self._limited_models.add(model)
                    last_error = e
                    continue
                else:
                    # Not a rate limit error, don't try other models
                    raise

        # All models failed
        if last_error:
            raise RuntimeError(
                f"{ErrorFormatter.all_providers_rate_limited(attempted_models)}. "
                f"Last error: {last_error}"
            )
        else:
            raise RuntimeError(ErrorFormatter.no_providers_available())

    def _convert_messages_for_rest(self, messages: list[dict[str, str]]) -> list:
        """
        Convert standard message format to Gemini REST API format.
        """
        contents = []

        for msg in messages:
            role = msg['role']
            content = msg['content']

            # Map roles
            if role == 'system':
                # Gemini doesn't have system role, prepend to first user message
                contents.append({
                    'role': 'user',
                    'parts': [{'text': f"System instruction: {content}"}]
                })
                # Add a model acknowledgment
                contents.append({
                    'role': 'model',
                    'parts': [{'text': 'Understood. I will follow these instructions.'}]
                })
            elif role == 'user':
                contents.append({
                    'role': 'user',
                    'parts': [{'text': content}]
                })
            elif role == 'assistant':
                contents.append({
                    'role': 'model',
                    'parts': [{'text': content}]
                })

        return contents

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
