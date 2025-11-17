"""
Base classes for LLM providers.

This module defines the abstract interface that all LLM providers must implement,
making it easy to add new providers (OpenRouter, HuggingFace, etc.) in the future.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import asyncio
import re


class ModelType(Enum):
    """Classification of model training/tuning type."""
    BASE = "base"           # Raw pretrained, no instruction tuning
    CHAT = "chat"           # Chat-tuned (conversational)
    INSTRUCT = "instruct"   # Instruction-tuned (follows structured commands)
    CODE = "code"           # Code-specialized
    REASONING = "reasoning" # Chain-of-thought / reasoning specialized
    UNKNOWN = "unknown"     # Type not determined


def detect_model_type(model_id: str) -> ModelType:
    """
    Auto-detect model type from model ID/name.

    Looks for common patterns in model names to determine type.

    Args:
        model_id: Model identifier string

    Returns:
        ModelType enum value
    """
    model_lower = model_id.lower()

    # Check for code models first (specific)
    if "code" in model_lower or "coder" in model_lower:
        return ModelType.CODE

    # Check for instruction-tuned indicators
    if "instruct" in model_lower:
        return ModelType.INSTRUCT

    # Check for -it suffix (instruction-tuned)
    if re.search(r'-it$', model_lower) or re.search(r'-it-', model_lower):
        return ModelType.INSTRUCT

    # Check for chat indicators
    if "chat" in model_lower:
        return ModelType.CHAT

    # Check for versatile (Groq's term for chat-tuned)
    if "versatile" in model_lower:
        return ModelType.CHAT

    # Check for base model indicators
    if "base" in model_lower:
        return ModelType.BASE

    # Check for reasoning/thinking models
    if "thinking" in model_lower or "reasoning" in model_lower:
        return ModelType.REASONING

    # Default to unknown
    return ModelType.UNKNOWN


@dataclass
class ModelInfo:
    """
    Metadata about a specific model.

    Provides detailed information about model capabilities, limits,
    and characteristics for intelligent model selection.
    """
    id: str
    model_type: ModelType
    context_length: int
    rpd: Optional[int] = None  # Requests per day
    tpm: Optional[int] = None  # Tokens per minute
    quality: str = "good"      # good, very_good, excellent
    speed: str = "fast"        # fast, very_fast, moderate, slow

    @property
    def is_instruction_tuned(self) -> bool:
        """Check if model is instruction-tuned (best for JSON compliance)."""
        return self.model_type == ModelType.INSTRUCT

    @classmethod
    def from_config(cls, model_id: str, config: Dict[str, Any]) -> "ModelInfo":
        """
        Create ModelInfo from provider config dictionary.

        Args:
            model_id: Model identifier
            config: Dictionary with model configuration

        Returns:
            ModelInfo instance
        """
        # Get model type from config or auto-detect from name
        if "type" in config:
            model_type = config["type"]
        else:
            model_type = detect_model_type(model_id)

        # Extract context length (may be 'context' or 'context_length')
        context_length = config.get("context", config.get("context_length", 4096))

        return cls(
            id=model_id,
            model_type=model_type,
            context_length=context_length,
            rpd=config.get("rpd"),
            tpm=config.get("tpm"),
            quality=config.get("quality", "good"),
            speed=config.get("speed", "fast")
        )


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw_response: object = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProviderLimits:
    """Rate limit information for a provider."""
    requests_per_minute: Optional[int] = None
    requests_per_day: Optional[int] = None
    requests_per_month: Optional[int] = None
    tokens_per_minute: Optional[int] = None
    tokens_per_day: Optional[int] = None
    remaining_requests: Optional[int] = None
    remaining_tokens: Optional[int] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    To add a new provider:
    1. Create a new file (e.g., openrouter_provider.py)
    2. Inherit from LLMProvider
    3. Implement all abstract methods
    4. Register in ProviderRegistry
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider."""
        pass

    @property
    @abstractmethod
    def available_models(self) -> list[str]:
        """List of model IDs available from this provider."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model to use if none specified."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
                     Example: [{'role': 'user', 'content': 'Hello'}]
            model: Model ID to use (defaults to provider's default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with standardized format
        """
        pass

    @abstractmethod
    def get_limits(self) -> ProviderLimits:
        """Get current rate limit information."""
        pass

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Async version of chat completion.

        Default implementation wraps sync chat() in executor.
        Override this method for true async HTTP calls.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model ID to use (defaults to provider's default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with standardized format
        """
        # Default: run sync version in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.chat(messages, model, max_tokens, temperature, **kwargs)
        )

    def is_available(self) -> bool:
        """Check if provider is configured and available."""
        try:
            # Default implementation - can be overridden
            return len(self.available_models) > 0
        except Exception:
            return False

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        """
        Estimate cost for a request (returns 0.0 for free tier).
        Override in paid providers.
        """
        return 0.0

    def get_model_info(self, model_id: str) -> ModelInfo:
        """
        Get detailed information about a specific model.

        Default implementation returns ModelInfo with auto-detected type.
        Override in providers with model configuration dictionaries.

        Args:
            model_id: Model identifier

        Returns:
            ModelInfo with model metadata
        """
        # Default implementation - providers should override
        return ModelInfo(
            id=model_id,
            model_type=detect_model_type(model_id),
            context_length=4096  # Conservative default
        )

    def get_instruction_tuned_models(self) -> list[str]:
        """
        Get all instruction-tuned models from this provider.

        Returns:
            List of model IDs that are instruction-tuned
        """
        return [
            model_id for model_id in self.available_models
            if self.get_model_info(model_id).is_instruction_tuned
        ]


class ProviderRegistry:
    """
    Central registry for all LLM providers.

    Usage:
        registry = ProviderRegistry()
        registry.register(GroqProvider())
        registry.register(CohereProvider())

        # Get a specific provider
        groq = registry.get('groq')

        # List all available providers
        providers = registry.list_available()
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        """Register a new provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        """Get a provider by name."""
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not registered. Available: {list(self._providers.keys())}")
        return self._providers[name]

    def list_all(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_available(self) -> list[str]:
        """List only providers that are configured and available."""
        return [name for name, provider in self._providers.items() if provider.is_available()]

    def get_provider_info(self) -> dict[str, dict]:
        """Get detailed info about all providers."""
        info = {}
        for name, provider in self._providers.items():
            info[name] = {
                'available': provider.is_available(),
                'default_model': provider.default_model if provider.is_available() else None,
                'models': provider.available_models if provider.is_available() else [],
                'limits': provider.get_limits() if provider.is_available() else None,
            }
        return info
