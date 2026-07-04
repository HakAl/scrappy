"""
LiteLLM Router configuration and model metadata.

This module provides:
- Model metadata for status display
- Router factory for creating LiteLLM Router with model groups
- Model group definitions

Architecture:
- MODEL_METADATA: Static metadata for status display (not used for routing)
- create_litellm_router(): Factory that creates Router with model groups
- Model groups are defined by model_name in router config

Model Groups:
- "fast": 8B models, speed priority
- "chat": 70B models, conversation
- "instruct": Tool-capable models for agent work, with Gemini as last resort
"""

from dataclasses import dataclass
from typing import Optional

from .provider_catalog import build_default_catalog
from .provider_types import SpeedRank, QualityRank
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


_CATALOG = build_default_catalog()


def _model_metadata_from_catalog() -> dict[str, ModelMetadata]:
    """Derive display metadata from the catalog, preserving catalog order.

    A model id the catalog cannot resolve is a catalog integrity error;
    fail at import rather than leaking None into display metadata.
    """
    metadata: dict[str, ModelMetadata] = {}
    for model_id in _CATALOG.model_ids():
        facts = _CATALOG.model_facts(model_id)
        if facts is None:
            raise RuntimeError(
                f"Provider catalog has no model facts for {model_id!r}"
            )
        metadata[model_id] = ModelMetadata(
            model_id=facts.model_id,
            provider=facts.provider,
            group=facts.group,
            context_length=facts.context_length,
            speed=facts.speed,
            quality=facts.quality,
            rpd=facts.rpd,
            tpm=facts.tpm,
        )
    return metadata


# Static metadata for display purposes
# Keys are LiteLLM model format: "provider/model"
# Fact rationale (JSON compliance, priority reasoning) lives with the
# facts in provider_catalog.build_default_catalog.
MODEL_METADATA: dict[str, ModelMetadata] = _model_metadata_from_catalog()


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
        name: env_var
        for name in _CATALOG.provider_names()
        if (env_var := _CATALOG.env_var_for(name)) is not None
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

    Entries derive from the catalog's router entries: group membership,
    intra-group priority (entry order), and tpm/rpm all come from
    provider_catalog.build_default_catalog. Entries whose provider has
    no configured API key are omitted.

    Args:
        api_key_service: Service for getting API keys

    Returns:
        List of model configurations for LiteLLM Router.
        Empty list if no API keys configured.
    """
    model_list = []

    for entry in _CATALOG.router_entries():
        provider = entry.model_id.split("/")[0]
        env_var = _CATALOG.env_var_for(provider)
        if env_var is None:
            raise ConfigurationError(
                f"Provider catalog has no env var for provider {provider!r} "
                f"(router entry {entry.model_id!r})"
            )
        api_key = api_key_service.get_key(env_var)
        if not api_key:
            continue
        model_list.append({
            "model_name": entry.group,
            "litellm_params": {
                "model": entry.model_id,
                "api_key": api_key,
            },
            "tpm": entry.tpm,
            "rpm": entry.rpm,
        })

    return model_list


def create_litellm_router(callbacks: Optional[list] = None):
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
    import os
    import logging

    # === CRITICAL: Suppress LiteLLM/Langfuse output BEFORE imports ===
    # These libraries are "chatty" and can corrupt terminal escape sequences
    # used by Textual for mouse tracking. Must silence BEFORE importing.

    # 1. Disable LiteLLM telemetry (prevents network calls and output)
    os.environ["LITELLM_TELEMETRY"] = "False"

    # 2. Silence loggers BEFORE importing (they set up handlers on import)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM Router").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM Proxy").setLevel(logging.WARNING)
    logging.getLogger("langfuse").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Now safe to import
    import litellm

    # 3. Also set litellm's internal flags
    litellm.suppress_debug_info = True
    litellm.set_verbose = False

    # Set callbacks globally for litellm (Router doesn't accept callbacks param)
    if callbacks:
        litellm.callbacks = callbacks

    # Enable Langfuse for LLM call tracing if configured
    from scrappy.graph.tracing import is_tracing_enabled
    if is_tracing_enabled():
        litellm.success_callback = litellm.success_callback or []
        if "langfuse" not in litellm.success_callback:
            litellm.success_callback.append("langfuse")
        litellm.failure_callback = litellm.failure_callback or []
        if "langfuse" not in litellm.failure_callback:
            litellm.failure_callback.append("langfuse")

    # Context window fallbacks: when a model hits context limit, try larger models
    # Order: small context -> medium -> large (Gemini has 1M context)
    context_fallbacks = [
        {fallback.primary: list(fallback.fallbacks)}
        for fallback in _CATALOG.context_fallbacks()
    ]

    # NOTE: Model fallbacks for rate limiting are NOT configured here.
    # LiteLLM's global fallbacks don't distinguish between agent (needs tool-calling)
    # and chat (any model). Agent tasks require instruct models (qwen, gemini) -
    # Llama models don't properly use tools.
    #
    # Fallback logic should be handled at graph level where we know the request type.
    # See: scrappy-oikp (Integrate tier escalation into graph package)

    return litellm.Router(
        model_list=[],  # Empty - configured via set_model_list() later
        routing_strategy="simple-shuffle",
        num_retries=1,  # Reduced: let graph fallback chain handle retries deterministically
        timeout=60,
        retry_after=5,
        context_window_fallbacks=context_fallbacks,
    )
