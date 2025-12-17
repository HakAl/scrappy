"""
LiteLLM Router configuration and model metadata.

This module provides:
- Model metadata for status display
- Router factory for creating LiteLLM Router with model groups
- Model group definitions ("fast" and "quality")

Architecture:
- MODEL_METADATA: Static metadata for status display (not used for routing)
- create_litellm_router(): Factory that creates Router with model groups
- Model groups are defined by model_name in router config

Model Groups:
- "fast": 8B models, speed priority, any context OK
- "quality": 70B+ models, quality priority, >= 32k context required
"""

from dataclasses import dataclass
from typing import Optional

from ..providers.base import SpeedRank, QualityRank
from ..infrastructure.config.api_keys import ApiKeyConfigServiceProtocol


class ConfigurationError(Exception):
    """Raised when LiteLLM router configuration is invalid."""
    pass


@dataclass(frozen=True)
class ModelMetadata:
    """
    Metadata for status display. NOT used for routing.

    This is for /status and /limits commands - the actual routing
    is handled by LiteLLM Router based on model groups.
    """
    model_id: str
    provider: str
    group: str  # "fast" or "quality"
    context_length: int
    speed: SpeedRank
    quality: QualityRank
    rpd: int  # Requests per day
    tpm: int  # Tokens per minute


# Static metadata for display purposes
# Keys are LiteLLM model format: "provider/model"
#
# JSON Compliance Testing (2025-12):
# - Cerebras & Groq: 110/100 (perfect JSON)
# - Gemini: 80/100 (adds markdown code fences - causes parse failures)
#
# Priority: Cerebras (highest RPD 14,400) > Groq (fast 0.4s) > SambaNova (low RPD)
MODEL_METADATA: dict[str, ModelMetadata] = {
    # --- Fast tier (8B class, speed priority) ---
    "groq/llama-3.1-8b-instant": ModelMetadata(
        model_id="groq/llama-3.1-8b-instant",
        provider="groq",
        group="fast",
        context_length=131072,
        speed=SpeedRank.VERY_FAST,
        quality=QualityRank.GOOD,
        rpd=7000,
        tpm=20000,
    ),
    "cerebras/llama3.1-8b": ModelMetadata(
        model_id="cerebras/llama3.1-8b",
        provider="cerebras",
        group="fast",
        context_length=8192,
        speed=SpeedRank.ULTRA_FAST,
        quality=QualityRank.GOOD,
        rpd=14400,
        tpm=60000,
    ),

    # --- Quality tier ---

    # Cerebras
    "cerebras/llama-3.3-70b": ModelMetadata(
        model_id="cerebras/llama-3.3-70b",
        provider="cerebras",
        group="quality",
        context_length=8192,
        speed=SpeedRank.ULTRA_FAST,  # 2100 tok/s
        quality=QualityRank.EXCELLENT,
        rpd=14400,
        tpm=60000,
    ),
    "cerebras/qwen-3-235b-a22b-instruct-2507": ModelMetadata(
        model_id="cerebras/qwen-3-235b-a22b-instruct-2507",
        provider="cerebras",
        group="quality",
        context_length=8192,
        speed=SpeedRank.FAST,  # 1.3s latency (235B size)
        quality=QualityRank.EXCELLENT,  # Instruction-tuned
        rpd=14400,
        tpm=60000,
    ),

    # Groq
    "groq/meta-llama/llama-4-scout-17b-16e-instruct": ModelMetadata(
        model_id="groq/meta-llama/llama-4-scout-17b-16e-instruct",
        provider="groq",
        group="quality",
        context_length=131072,  # 128k
        speed=SpeedRank.ULTRA_FAST,  # 0.4s
        quality=QualityRank.VERY_GOOD,
        rpd=7000,
        tpm=20000,
    ),
    "groq/moonshotai/kimi-k2-instruct": ModelMetadata(
        model_id="groq/moonshotai/kimi-k2-instruct",
        provider="groq",
        group="quality",
        context_length=131072,  # 128k
        speed=SpeedRank.ULTRA_FAST,  # 0.4s
        quality=QualityRank.VERY_GOOD,
        rpd=7000,
        tpm=20000,
    ),
    "groq/llama-3.3-70b-versatile": ModelMetadata(
        model_id="groq/llama-3.3-70b-versatile",
        provider="groq",
        group="quality",
        context_length=32768,
        speed=SpeedRank.FAST,  # 1.0s
        quality=QualityRank.EXCELLENT,
        rpd=1000,
        tpm=12000,
    ),

    # Gemini
    "gemini/gemini-2.5-flash": ModelMetadata(
        model_id="gemini/gemini-2.5-flash",
        provider="gemini",
        group="quality",
        context_length=1000000,  # 1M context
        speed=SpeedRank.MODERATE,
        quality=QualityRank.VERY_GOOD,
        rpd=250,
        tpm=250000,
    ),

    # SambaNova
    "sambanova/Meta-Llama-3.1-8B-Instruct": ModelMetadata(
        model_id="sambanova/Meta-Llama-3.1-8B-Instruct",
        provider="sambanova",
        group="fast",
        context_length=16384,
        speed=SpeedRank.FAST,
        quality=QualityRank.GOOD,
        rpd=40,
        tpm=100000,
    ),
    "sambanova/Meta-Llama-3.3-70B-Instruct": ModelMetadata(
        model_id="sambanova/Meta-Llama-3.3-70B-Instruct",
        provider="sambanova",
        group="quality",
        context_length=131072,  # 128k
        speed=SpeedRank.ULTRA_FAST,  # 0.26s latency
        quality=QualityRank.EXCELLENT,
        rpd=40,
        tpm=100000,
    ),
}


def get_models_for_group(group: str) -> list[ModelMetadata]:
    """
    Get all models in a group (for status display).

    Args:
        group: Model group name ("fast" or "quality")

    Returns:
        List of ModelMetadata for models in the group
    """
    return [m for m in MODEL_METADATA.values() if m.group == group]


def get_configured_models(api_key_service: ApiKeyConfigServiceProtocol) -> list[ModelMetadata]:
    """
    Get models that have API keys configured.

    Args:
        api_key_service: Service for checking API key configuration

    Returns:
        List of ModelMetadata for models with configured API keys
    """
    # Map provider names to their API key environment variable names
    provider_to_key = {
        "groq": "GROQ_API_KEY",
        "cerebras": "CEREBRAS_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "sambanova": "SAMBANOVA_API_KEY",
    }

    configured = []
    for model in MODEL_METADATA.values():
        key_name = provider_to_key.get(model.provider)
        if key_name and api_key_service.get_key(key_name):
            configured.append(model)
    return configured


def get_available_groups(api_key_service: ApiKeyConfigServiceProtocol) -> set[str]:
    """
    Get model groups that have at least one configured provider.

    Args:
        api_key_service: Service for checking API key configuration

    Returns:
        Set of available group names
    """
    configured = get_configured_models(api_key_service)
    return {m.group for m in configured}


# NOTE: SELECTION_TYPE_TO_GROUP is defined in model_selection.py
# Import from there: from .model_selection import SELECTION_TYPE_TO_GROUP


def build_model_list(api_key_service: ApiKeyConfigServiceProtocol) -> list[dict]:
    """
    Build model list from configured API keys.

    Model Groups:
    - "fast": 8B models, speed priority
    - "quality": Large models, quality priority, perfect JSON compliance

    Priority within groups determined by order (first = primary).
    Based on JSON compliance testing (2025-12):
    - Cerebras/Groq: 110/100 (perfect)
    - Gemini: 80/100 (JSON issues - deprioritized)

    Args:
        api_key_service: Service for getting API keys

    Returns:
        List of model configurations for LiteLLM Router.
        Empty list if no API keys configured.
    """
    model_list = []

    groq_key = api_key_service.get_key("GROQ_API_KEY")
    cerebras_key = api_key_service.get_key("CEREBRAS_API_KEY")
    gemini_key = api_key_service.get_key("GEMINI_API_KEY")
    sambanova_key = api_key_service.get_key("SAMBANOVA_API_KEY")

    # --- Fast Models (8B class, speed priority) ---
    # Priority: Groq (128k) > Cerebras (8k) > SambaNova (low RPD)

    if groq_key:
        model_list.append({
            "model_name": "fast",
            "litellm_params": {
                "model": "groq/llama-3.1-8b-instant",
                "api_key": groq_key,
            },
            "tpm": 20000,
            "rpm": 30,
        })

    if cerebras_key:
        model_list.append({
            "model_name": "fast",
            "litellm_params": {
                "model": "cerebras/llama3.1-8b",
                "api_key": cerebras_key,
            },
            "tpm": 60000,
            "rpm": 30,
        })

    if sambanova_key:
        model_list.append({
            "model_name": "fast",
            "litellm_params": {
                "model": "sambanova/Meta-Llama-3.1-8B-Instruct",
                "api_key": sambanova_key,
            },
            "tpm": 100000,
            "rpm": 1,  # ~40 RPD = very low RPM
        })

    # --- Quality Models (tool-use + instruction-following priority) ---
    # Priority:
    # 1. Cerebras Qwen 235B - instruction-tuned, massive model
    # 2. Groq Llama 4 - fast, good tool use
    # 3. Groq Kimi K2 - fast, 128k context
    # 4. Gemini - fallback (JSON issues but huge context)

    # Cerebras Qwen 235B - instruction-tuned for tool use
    if cerebras_key:
        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "cerebras/qwen-3-235b-a22b-instruct-2507",
                "api_key": cerebras_key,
            },
            "tpm": 60000,
            "rpm": 30,
        })

    # Groq - fast inference, good tool use
    if groq_key:
        # Llama 4 - latest architecture, 0.4s latency
        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "groq/meta-llama/llama-4-scout-17b-16e-instruct",
                "api_key": groq_key,
            },
            "tpm": 20000,
            "rpm": 30,
        })
        # Kimi K2 - fast, 128k context
        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "groq/moonshotai/kimi-k2-instruct",
                "api_key": groq_key,
            },
            "tpm": 20000,
            "rpm": 30,
        })

    # Gemini - deprioritized (JSON issues) but useful for huge context
    if gemini_key:
        model_list.append({
            "model_name": "quality",
            "litellm_params": {
                "model": "gemini/gemini-2.5-flash",
                "api_key": gemini_key,
            },
            "tpm": 250000,
            "rpm": 10,
        })

    return model_list


def create_litellm_router(callbacks: list = None):
    """
    Create empty LiteLLM Router.

    Router starts empty and is configured via set_model_list() when API keys
    become available. This allows the service to be fully constructed at
    startup even before keys are configured.

    Args:
        callbacks: Optional list of LiteLLM callbacks for rate tracking

    Returns:
        Empty litellm.Router instance ready to be configured
    """
    import litellm

    # Set callbacks globally for litellm (Router doesn't accept callbacks param)
    if callbacks:
        litellm.callbacks = callbacks

    return litellm.Router(
        model_list=[],  # Empty - configured via set_model_list() later
        routing_strategy="simple-shuffle",
        num_retries=3,
        timeout=60,
        retry_after=5,
    )
