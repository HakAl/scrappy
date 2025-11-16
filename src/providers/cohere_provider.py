"""
Cohere LLM Provider implementation.

Cohere provides chat, embedding, and reranking capabilities.

CRITICAL LIMITATIONS (Trial Key):
- 1,000 API calls per MONTH total (across all endpoints)
- 10 calls per endpoint during trial evaluation
- Chat: 20/min
- Embed: 100/min

Use sparingly! Best for:
- Embeddings (if you have production key)
- One-off complex reasoning tasks
- NOT for high-volume agent communication
"""

import os
import time
from typing import Optional

from .base import LLMProvider, LLMResponse, ProviderLimits
from ..utils.imports import safe_import
from ..utils.errors import raise_package_not_installed, raise_env_var_not_found, raise_model_not_supported

# Safe import for optional dependency
cohere, COHERE_AVAILABLE = safe_import('cohere')


class CohereProvider(LLMProvider):
    """
    Cohere provider for chat and specialized NLP tasks.

    Environment variable required: COHERE_API_KEY

    WARNING: Trial key has severe limits:
    - 1,000 calls/month TOTAL
    - 10 calls per endpoint for evaluation
    - After those 10, you must wait or upgrade
    """

    # Model configurations
    MODELS = {
        'command-r-08-2024': {
            'type': 'chat', 'quality': 'good', 'speed': 'fast',
            'context': 128000, 'description': 'Balanced performance'
        },
        'command-r7b-12-2024': {
            'type': 'chat', 'quality': 'moderate', 'speed': 'very_fast',
            'context': 128000, 'description': 'Smaller, faster model'
        },
        'command-a-03-2025': {
            'type': 'chat', 'quality': 'excellent', 'speed': 'moderate',
            'context': 256000, 'description': 'Newest command model'
        },
        'command-a-reasoning-08-2025': {
            'type': 'reasoning', 'quality': 'excellent', 'speed': 'slow',
            'context': 256000, 'description': 'Specialized reasoning model'
        },
        'c4ai-aya-expanse-8b': {
            'type': 'chat', 'quality': 'good', 'speed': 'fast',
            'context': 8192, 'description': 'Multilingual model'
        },
        'c4ai-aya-expanse-32b': {
            'type': 'chat', 'quality': 'very_good', 'speed': 'moderate',
            'context': 8192, 'description': 'Larger multilingual model'
        },
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Cohere provider.

        Args:
            api_key: Cohere API key (defaults to COHERE_API_KEY env var)
        """
        if not COHERE_AVAILABLE:
            raise_package_not_installed('cohere')

        self._api_key = api_key or os.environ.get('COHERE_API_KEY')
        if not self._api_key:
            raise_env_var_not_found('COHERE_API_KEY')

        # Use V2 client for chat
        self._client = cohere.ClientV2(api_key=self._api_key)
        # Also keep V1 client for other operations
        self._client_v1 = cohere.Client(api_key=self._api_key)

        self._calls_made = 0  # Track calls to warn about limits

    @property
    def name(self) -> str:
        return 'cohere'

    @property
    def available_models(self) -> list[str]:
        return list(self.MODELS.keys())

    @property
    def default_model(self) -> str:
        # Use smaller model by default to conserve quota
        return 'command-r7b-12-2024'

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion to Cohere.

        WARNING: Each call counts toward your 1000/month limit!

        Cohere V2 uses OpenAI-compatible message format:
        [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}]
        """
        model = model or self.default_model

        if model not in self.MODELS:
            raise_model_not_supported(model, self.available_models)

        # Warn about usage
        self._calls_made += 1
        if self._calls_made % 10 == 0:
            print(f"WARNING: Cohere calls this session: {self._calls_made}")
            print(f"Remember: Trial key has 1000 calls/month limit!")

        start_time = time.time()

        response = self._client.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        latency_ms = (time.time() - start_time) * 1000

        # Extract content
        content = ""
        if response.message and response.message.content:
            content = response.message.content[0].text

        # Extract usage if available
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'meta') and response.meta:
            if hasattr(response.meta, 'tokens'):
                tokens = response.meta.tokens
                input_tokens = getattr(tokens, 'input_tokens', 0)
                output_tokens = getattr(tokens, 'output_tokens', 0)

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            raw_response=response,
            metadata={
                'model_config': self.MODELS.get(model, {}),
                'session_calls': self._calls_made,
            }
        )

    def get_limits(self) -> ProviderLimits:
        """Get rate limit info for trial key."""
        return ProviderLimits(
            requests_per_minute=20,  # Chat endpoint
            requests_per_month=1000,  # CRITICAL LIMIT
        )

    def get_model_for_task(self, task_type: str) -> str:
        """
        Recommend a model based on task type.

        Args:
            task_type: 'fast', 'quality', 'reasoning', 'multilingual'

        Returns:
            Recommended model name
        """
        if task_type == 'fast':
            return 'command-r7b-12-2024'
        elif task_type == 'quality':
            return 'command-a-03-2025'
        elif task_type == 'reasoning':
            return 'command-a-reasoning-08-2025'
        elif task_type == 'multilingual':
            return 'c4ai-aya-expanse-32b'
        else:
            return self.default_model

    def embed(self, texts: list[str], model: str = 'embed-english-v3.0') -> list[list[float]]:
        """
        Generate embeddings for texts.

        Note: Each call counts toward monthly limit!
        Trial limit: 100/min for embed endpoint

        Args:
            texts: List of strings to embed
            model: Embedding model to use

        Returns:
            List of embedding vectors
        """
        self._calls_made += 1

        response = self._client_v1.embed(
            texts=texts,
            model=model,
            input_type='search_document'
        )

        return response.embeddings

    def is_available(self) -> bool:
        """Check if Cohere is properly configured."""
        return bool(self._api_key and COHERE_AVAILABLE)

    def get_remaining_budget(self) -> dict:
        """
        Estimate remaining API budget.

        Returns rough estimate based on session usage.
        For accurate info, check Cohere dashboard.
        """
        return {
            'session_calls': self._calls_made,
            'estimated_monthly_remaining': 1000 - self._calls_made,
            'warning': 'This is session-only tracking. Check Cohere dashboard for actual usage.'
        }
