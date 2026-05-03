"""
Provider config validation and health checks.

Tier 1 (no secrets): config parses, models are recognized by litellm, groups valid.
Tier 2 (with secrets): ping each provider with a minimal completion request.
"""

import os
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Tier 1: Config validation (no API keys needed)
# ---------------------------------------------------------------------------

class TestConfigParsesCorrectly:
    """Validate that provider/model config is internally consistent."""

    def test_model_metadata_has_required_fields(self):
        from scrappy.orchestrator.litellm_config import MODEL_METADATA
        for model_id, meta in MODEL_METADATA.items():
            assert meta.model_id == model_id, f"Key/id mismatch: {model_id}"
            assert meta.provider in {"cerebras", "groq", "gemini", "sambanova"}
            assert meta.group in {"fast", "chat", "instruct"}
            assert meta.context_length > 0
            assert meta.rpd > 0
            assert meta.tpm > 0

    def test_every_provider_has_definition(self):
        from scrappy.orchestrator.litellm_config import MODEL_METADATA
        from scrappy.orchestrator.provider_definitions import PROVIDERS

        providers_in_models = {m.provider for m in MODEL_METADATA.values()}
        for provider in providers_in_models:
            assert provider in PROVIDERS, f"Provider {provider} in MODEL_METADATA but not in PROVIDERS"

    def test_provider_env_vars_are_defined(self):
        from scrappy.orchestrator.provider_definitions import PROVIDERS
        for name, defn in PROVIDERS.items():
            assert defn.env_var, f"Provider {name} has no env_var"
            assert defn.env_var.endswith("_API_KEY"), f"Provider {name} env_var should end with _API_KEY"

    def test_build_model_list_with_all_keys(self):
        """build_model_list should return models for all groups when all keys present."""
        from scrappy.orchestrator.litellm_config import build_model_list

        mock_keys = MagicMock()
        mock_keys.get_key.return_value = "fake-key-for-testing"

        model_list = build_model_list(mock_keys)
        groups = {m["model_name"] for m in model_list}
        assert "fast" in groups, "No fast models configured"
        assert "chat" in groups, "No chat models configured"
        assert "instruct" in groups, "No instruct models configured"

    def test_build_model_list_empty_without_keys(self):
        """build_model_list should return empty list when no keys configured."""
        from scrappy.orchestrator.litellm_config import build_model_list

        mock_keys = MagicMock()
        mock_keys.get_key.return_value = None

        model_list = build_model_list(mock_keys)
        assert model_list == []

    def test_litellm_recognizes_model_ids(self):
        """Every model ID should be parseable by litellm (provider/model format)."""
        from scrappy.orchestrator.litellm_config import MODEL_METADATA

        for model_id in MODEL_METADATA:
            parts = model_id.split("/", 1)
            assert len(parts) == 2, f"Model ID {model_id} not in provider/model format"
            provider, model = parts
            assert len(provider) > 0
            assert len(model) > 0

    def test_each_group_has_at_least_two_providers(self):
        """Each model group should have fallback options from multiple providers."""
        from scrappy.orchestrator.litellm_config import MODEL_METADATA

        group_providers: dict[str, set[str]] = {}
        for meta in MODEL_METADATA.values():
            group_providers.setdefault(meta.group, set()).add(meta.provider)

        for group, providers in group_providers.items():
            assert len(providers) >= 2, (
                f"Group '{group}' only has providers: {providers}. "
                f"Add a fallback provider for resilience."
            )

    def test_build_model_list_all_models_in_metadata(self):
        """Every model in build_model_list must exist in MODEL_METADATA."""
        from scrappy.orchestrator.litellm_config import build_model_list, MODEL_METADATA

        mock_keys = MagicMock()
        mock_keys.get_key.return_value = "fake-key"

        model_list = build_model_list(mock_keys)
        metadata_ids = set(MODEL_METADATA.keys())

        missing = []
        for entry in model_list:
            model_id = entry["litellm_params"]["model"]
            if model_id not in metadata_ids:
                missing.append(model_id)

        assert not missing, (
            f"Models in build_model_list but missing from MODEL_METADATA: {missing}. "
            f"Add metadata or remove the model from the router config."
        )


# ---------------------------------------------------------------------------
# Tier 2: Verify every configured model actually works with its provider
# ---------------------------------------------------------------------------

# Map provider prefix to the env var that holds its key
_PROVIDER_KEY_MAP = {
    "cerebras": "CEREBRAS_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
}


def _get_key(name: str) -> str:
    """Get API key at runtime (after dotenv has loaded)."""
    key = os.environ.get(name, "")
    if not key:
        pytest.skip(f"{name} not set")
    return key


def _ping_model(model_id: str, api_key: str):
    """Send a minimal completion to verify litellm can reach this specific model."""
    import litellm

    litellm.suppress_debug_info = True
    litellm.set_verbose = False

    response = litellm.completion(
        model=model_id,
        messages=[{"role": "user", "content": "Say OK"}],
        max_tokens=5,
        api_key=api_key,
    )
    content = response.choices[0].message.content
    assert content is not None and len(content) > 0, f"Empty response from {model_id}"


def _collect_configured_models():
    """Build parametrized list of (model_id, env_var) from the real router config."""
    from scrappy.orchestrator.litellm_config import build_model_list
    mock_keys = MagicMock()
    mock_keys.get_key.return_value = "fake-key"

    seen = set()
    params = []
    for entry in build_model_list(mock_keys):
        model_id = entry["litellm_params"]["model"]
        if model_id in seen:
            continue
        seen.add(model_id)

        provider = model_id.split("/", 1)[0]
        env_var = _PROVIDER_KEY_MAP.get(provider)
        if env_var:
            params.append(pytest.param(model_id, env_var, id=model_id))

    return params


@pytest.mark.parametrize("model_id,env_var", _collect_configured_models())
def test_configured_model_responds(model_id, env_var):
    """Each model in build_model_list should return a valid response."""
    _ping_model(model_id, _get_key(env_var))
