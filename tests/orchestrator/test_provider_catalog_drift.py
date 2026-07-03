"""
Drift tests: pin every live copy of provider/model facts to the catalog.

Each test derives the expected view from ProviderCatalog and asserts
equality against one existing copy. When a follow-up PR rewires a copy
to derive from the catalog, its drift test keeps holding (copy IS
catalog); until then, any divergence between a copy and the catalog
fails here instead of surfacing as routing/setup misbehavior.

Known drift between the copies is pinned exactly in TestKnownDrift;
changing those facts is a declared change, not a silent one.
"""

from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

from scrappy.orchestrator.provider_catalog import (
    ProviderCatalog,
    build_default_catalog,
)

from tests.helpers import MockApiKeyService


CATALOG = build_default_catalog()

ALL_KEYS = {
    "CEREBRAS_API_KEY": "key-cerebras",
    "GROQ_API_KEY": "key-groq",
    "GEMINI_API_KEY": "key-gemini",
    "SAMBANOVA_API_KEY": "key-sambanova",
}


class RecordingApiKeyService:
    """Api key test double that records which key names were requested."""

    def __init__(self, keys: Dict[str, str]):
        self._keys = keys
        self.requested: List[str] = []

    def get_key(self, name: str) -> Optional[str]:
        self.requested.append(name)
        return self._keys.get(name)


class TestProviderFactsDrift:
    """Catalog vs provider_definitions, api_keys, and CLI copies."""

    def test_provider_facts_match_provider_definitions(self):
        from scrappy.orchestrator.provider_definitions import PROVIDERS

        assert set(CATALOG.provider_names()) == set(PROVIDERS.keys())
        for name, definition in PROVIDERS.items():
            facts = CATALOG.provider_facts(name)
            assert facts is not None
            assert facts.env_var == definition.env_var
            assert facts.console_url == definition.console_url
            assert facts.quota == definition.quota
            assert facts.description == definition.description
            assert facts.setup_priority == definition.priority
            assert facts.supports_brain == definition.supports_brain
            assert list(facts.task_types) == definition.task_types

    def test_setup_priority_order_matches_provider_definitions(self):
        from scrappy.orchestrator.provider_definitions import get_provider_priority

        assert [
            p.name for p in CATALOG.providers_by_setup_priority()
        ] == get_provider_priority()

    def test_known_env_vars_match_api_keys_module(self):
        from scrappy.infrastructure.config.api_keys import PROVIDER_ENV_VARS

        assert list(CATALOG.known_provider_env_vars()) == PROVIDER_ENV_VARS

    def test_cli_allowlist_matches_provider_validator(self):
        from scrappy.cli.validators.provider import VALID_PROVIDERS

        assert CATALOG.cli_provider_allowlist() == VALID_PROVIDERS

    def test_validation_models_match_setup_wizard(self):
        from scrappy.cli.setup_wizard import PROVIDER_TO_MODEL

        assert {
            provider: CATALOG.validation_model_for(provider)
            for provider in CATALOG.validation_providers()
        } == PROVIDER_TO_MODEL


class TestModelFactsDrift:
    """Catalog vs MODEL_METADATA and the model_selection constants."""

    def test_model_facts_match_model_metadata(self):
        from scrappy.orchestrator.litellm_config import MODEL_METADATA

        assert set(CATALOG.model_ids()) == set(MODEL_METADATA.keys())
        for model_id, metadata in MODEL_METADATA.items():
            facts = CATALOG.model_facts(model_id)
            assert facts is not None
            assert facts.provider == metadata.provider
            assert facts.group == metadata.group
            assert facts.context_length == metadata.context_length
            assert facts.speed == metadata.speed
            assert facts.quality == metadata.quality
            assert facts.rpd == metadata.rpd
            assert facts.tpm == metadata.tpm

    def test_priorities_match_model_selection(self):
        from scrappy.orchestrator.model_selection import (
            MODEL_PRIORITIES,
            ModelSelectionType,
        )

        assert set(CATALOG.selection_types()) == {
            t.value for t in ModelSelectionType
        }
        for selection_type, model_ids in MODEL_PRIORITIES.items():
            assert (
                list(CATALOG.priority_model_ids(selection_type.value)) == model_ids
            )

    def test_selection_type_groups_match_model_selection(self):
        from scrappy.orchestrator.model_selection import SELECTION_TYPE_TO_GROUP

        assert {
            selection_type: CATALOG.group_for_selection_type(selection_type)
            for selection_type in CATALOG.selection_types()
        } == {t.value: group for t, group in SELECTION_TYPE_TO_GROUP.items()}

    def test_router_groups_match_model_selection(self):
        from scrappy.orchestrator.model_selection import MODEL_GROUPS

        assert CATALOG.router_groups() == MODEL_GROUPS


class TestRouterDerivationDrift:
    """Catalog vs build_model_list, env-var maps, and context fallbacks."""

    @staticmethod
    def _expected_model_list(keys: Dict[str, str]) -> List[dict]:
        expected = []
        for entry in CATALOG.router_entries():
            provider = entry.model_id.split("/")[0]
            env_var = CATALOG.env_var_for(provider)
            assert env_var is not None
            api_key = keys.get(env_var)
            if not api_key:
                continue
            expected.append({
                "model_name": entry.group,
                "litellm_params": {
                    "model": entry.model_id,
                    "api_key": api_key,
                },
                "tpm": entry.tpm,
                "rpm": entry.rpm,
            })
        return expected

    def test_build_model_list_all_keys_matches_catalog(self):
        from scrappy.orchestrator.litellm_config import build_model_list

        model_list = build_model_list(MockApiKeyService(keys=dict(ALL_KEYS)))

        assert model_list == self._expected_model_list(ALL_KEYS)

    def test_build_model_list_no_keys_is_empty(self):
        from scrappy.orchestrator.litellm_config import build_model_list

        assert build_model_list(MockApiKeyService(keys={})) == []

    def test_build_model_list_single_provider_filters_catalog_entries(self):
        from scrappy.orchestrator.litellm_config import build_model_list

        keys = {"CEREBRAS_API_KEY": "key-cerebras"}
        model_list = build_model_list(MockApiKeyService(keys=dict(keys)))

        assert model_list == self._expected_model_list(keys)

    def test_context_fallbacks_match_catalog(self):
        from scrappy.orchestrator.litellm_config import create_litellm_router

        with patch("litellm.Router") as mock_router_class:
            create_litellm_router()
        call_kwargs = mock_router_class.call_args[1]

        assert call_kwargs["context_window_fallbacks"] == [
            {fallback.primary: list(fallback.fallbacks)}
            for fallback in CATALOG.context_fallbacks()
        ]

    def test_litellm_config_env_map_matches_catalog(self):
        """get_configured_models' internal provider->key map, behaviorally."""
        from scrappy.orchestrator.litellm_config import get_configured_models

        service = RecordingApiKeyService(dict(ALL_KEYS))
        configured = get_configured_models(service)

        assert {m.model_id for m in configured} == set(CATALOG.model_ids())
        assert set(service.requested) == set(CATALOG.known_provider_env_vars())

    def test_factory_env_map_matches_catalog(self):
        """_get_configured_models' internal provider->key map, behaviorally."""
        from scrappy.orchestrator.factory import OrchestratorFactory

        factory = OrchestratorFactory(path_provider=MagicMock())
        service = RecordingApiKeyService(dict(ALL_KEYS))
        configured = factory._get_configured_models(service)

        expected = {
            model_id
            for selection_type in CATALOG.selection_types()
            for model_id in CATALOG.priority_model_ids(selection_type)
        }
        assert configured == expected
        assert set(service.requested) == set(CATALOG.known_provider_env_vars())


class TestKnownDrift:
    """Pin the documented divergence between the copies, exactly."""

    def test_metadata_only_models_pinned(self):
        assert CATALOG.metadata_only_model_ids() == {
            "sambanova/Meta-Llama-3.3-70B-Instruct",
        }

    def test_unrouted_priority_models_pinned(self):
        assert CATALOG.unrouted_priority_model_ids() == {
            "cerebras/llama-3.3-70b",
            "groq/llama-3.3-70b-versatile",
        }

    def test_selection_router_disagreements_pinned(self):
        disagreements = CATALOG.selection_router_disagreements()

        assert set(disagreements.keys()) == {"chat", "embed"}
        assert disagreements["chat"] == (
            ("cerebras/llama-3.3-70b", "groq/llama-3.3-70b-versatile"),
            ("gemini/gemini-2.5-flash", "groq/moonshotai/kimi-k2-instruct"),
        )
        assert disagreements["embed"] == (
            ("groq/llama-3.1-8b-instant", "cerebras/llama3.1-8b"),
            (
                "groq/llama-3.1-8b-instant",
                "cerebras/llama3.1-8b",
                "sambanova/Meta-Llama-3.1-8B-Instruct",
            ),
        )


class TestCatalogLookupBehavior:
    """Behavior of catalog lookups on unknown and boundary inputs."""

    def test_unknown_provider_returns_none(self):
        assert CATALOG.provider_facts("nope") is None
        assert CATALOG.env_var_for("nope") is None
        assert CATALOG.validation_model_for("nope") is None

    def test_unknown_model_returns_none(self):
        assert CATALOG.model_facts("nope/nothing") is None

    def test_unknown_selection_type_returns_empty(self):
        assert CATALOG.priority_model_ids("nope") == ()
        assert CATALOG.group_for_selection_type("nope") is None

    def test_unknown_group_returns_empty(self):
        assert CATALOG.models_in_group("nope") == ()

    def test_empty_catalog_reports_no_facts_and_no_drift(self):
        empty = ProviderCatalog(
            providers=(),
            models=(),
            priorities={},
            selection_type_to_group={},
            router_groups=(),
            router_entries=(),
            context_fallbacks=(),
            validation_models={},
        )
        assert empty.provider_names() == ()
        assert empty.model_ids() == ()
        assert empty.known_provider_env_vars() == ()
        assert empty.metadata_only_model_ids() == frozenset()
        assert empty.selection_router_disagreements() == {}
