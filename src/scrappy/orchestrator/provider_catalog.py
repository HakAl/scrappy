"""
Provider catalog: single source of provider/model facts.

Consolidates the provider and model facts currently duplicated across
provider_definitions.PROVIDERS, model_selection.MODEL_PRIORITIES,
litellm_config.MODEL_METADATA, litellm_config.build_model_list,
the context fallback chains in create_litellm_router, the provider
env-var maps, and the CLI validator/wizard copies.

PR-1b status: model_selection.py and litellm_config.py now derive their
routing-facing surfaces from this catalog (literals deleted). The CLI/
setup/env-var copies still hold their own literals until PR-1c; drift
tests (tests/orchestrator/test_provider_catalog_drift.py) pin every
copy, live or derived, to the catalog.

Facts are transcribed from what routing actually does on main today.
Known divergence between the copies is represented explicitly through
the drift-reporting methods (metadata_only_model_ids,
unrouted_priority_model_ids, selection_router_disagreements) rather
than corrected; any fact correction is a separate declared change.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Protocol, Tuple

from .provider_types import QualityRank, SpeedRank


@dataclass(frozen=True)
class ProviderFacts:
    """Static facts about one provider (setup, display, and key lookup)."""
    name: str
    env_var: str
    console_url: str
    quota: str
    description: str
    setup_priority: int
    supports_brain: bool
    task_types: Tuple[str, ...]


@dataclass(frozen=True)
class ModelFacts:
    """Static facts about one model in provider/model LiteLLM id format."""
    model_id: str
    provider: str
    group: str
    context_length: int
    speed: SpeedRank
    quality: QualityRank
    rpd: int
    tpm: int


@dataclass(frozen=True)
class RouterEntry:
    """One router model-list entry: group membership plus rate params."""
    group: str
    model_id: str
    tpm: int
    rpm: int


@dataclass(frozen=True)
class ContextFallback:
    """Context-window fallback chain for one primary model."""
    primary: str
    fallbacks: Tuple[str, ...]


class ProviderCatalogProtocol(Protocol):
    """Contract for reading consolidated provider/model facts."""

    def provider_names(self) -> Tuple[str, ...]: ...

    def provider_facts(self, name: str) -> Optional[ProviderFacts]: ...

    def providers_by_setup_priority(self) -> Tuple[ProviderFacts, ...]: ...

    def env_var_for(self, provider_name: str) -> Optional[str]: ...

    def known_provider_env_vars(self) -> Tuple[str, ...]: ...

    def model_ids(self) -> Tuple[str, ...]: ...

    def model_facts(self, model_id: str) -> Optional[ModelFacts]: ...

    def models_in_group(self, group: str) -> Tuple[ModelFacts, ...]: ...

    def selection_types(self) -> Tuple[str, ...]: ...

    def priority_model_ids(self, selection_type: str) -> Tuple[str, ...]: ...

    def group_for_selection_type(self, selection_type: str) -> Optional[str]: ...

    def router_groups(self) -> frozenset[str]: ...

    def router_entries(self) -> Tuple[RouterEntry, ...]: ...

    def context_fallbacks(self) -> Tuple[ContextFallback, ...]: ...

    def validation_model_for(self, provider_name: str) -> Optional[str]: ...

    def validation_providers(self) -> Tuple[str, ...]: ...

    def cli_provider_allowlist(self) -> frozenset[str]: ...

    def metadata_only_model_ids(self) -> frozenset[str]: ...

    def unrouted_priority_model_ids(self) -> frozenset[str]: ...

    def selection_router_disagreements(
        self,
    ) -> Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]]: ...


class ProviderCatalog:
    """Implements ProviderCatalogProtocol over injected fact data."""

    def __init__(
        self,
        providers: Iterable[ProviderFacts],
        models: Iterable[ModelFacts],
        priorities: Mapping[str, Tuple[str, ...]],
        selection_type_to_group: Mapping[str, str],
        router_groups: Iterable[str],
        router_entries: Iterable[RouterEntry],
        context_fallbacks: Iterable[ContextFallback],
        validation_models: Mapping[str, str],
    ) -> None:
        self._providers: Dict[str, ProviderFacts] = {p.name: p for p in providers}
        self._models: Dict[str, ModelFacts] = {m.model_id: m for m in models}
        self._priorities: Dict[str, Tuple[str, ...]] = dict(priorities)
        self._selection_type_to_group: Dict[str, str] = dict(selection_type_to_group)
        self._router_groups: frozenset[str] = frozenset(router_groups)
        self._router_entries: Tuple[RouterEntry, ...] = tuple(router_entries)
        self._context_fallbacks: Tuple[ContextFallback, ...] = tuple(context_fallbacks)
        self._validation_models: Dict[str, str] = dict(validation_models)

    def provider_names(self) -> Tuple[str, ...]:
        return tuple(self._providers.keys())

    def provider_facts(self, name: str) -> Optional[ProviderFacts]:
        return self._providers.get(name)

    def providers_by_setup_priority(self) -> Tuple[ProviderFacts, ...]:
        return tuple(
            sorted(self._providers.values(), key=lambda p: p.setup_priority)
        )

    def env_var_for(self, provider_name: str) -> Optional[str]:
        facts = self._providers.get(provider_name)
        return facts.env_var if facts is not None else None

    def known_provider_env_vars(self) -> Tuple[str, ...]:
        return tuple(p.env_var for p in self.providers_by_setup_priority())

    def model_ids(self) -> Tuple[str, ...]:
        return tuple(self._models.keys())

    def model_facts(self, model_id: str) -> Optional[ModelFacts]:
        return self._models.get(model_id)

    def models_in_group(self, group: str) -> Tuple[ModelFacts, ...]:
        return tuple(m for m in self._models.values() if m.group == group)

    def selection_types(self) -> Tuple[str, ...]:
        return tuple(self._selection_type_to_group.keys())

    def priority_model_ids(self, selection_type: str) -> Tuple[str, ...]:
        return self._priorities.get(selection_type, ())

    def group_for_selection_type(self, selection_type: str) -> Optional[str]:
        return self._selection_type_to_group.get(selection_type)

    def router_groups(self) -> frozenset[str]:
        return self._router_groups

    def router_entries(self) -> Tuple[RouterEntry, ...]:
        return self._router_entries

    def context_fallbacks(self) -> Tuple[ContextFallback, ...]:
        return self._context_fallbacks

    def validation_model_for(self, provider_name: str) -> Optional[str]:
        return self._validation_models.get(provider_name)

    def validation_providers(self) -> Tuple[str, ...]:
        return tuple(self._validation_models.keys())

    def cli_provider_allowlist(self) -> frozenset[str]:
        return frozenset(self._providers.keys())

    def _routed_model_ids(self) -> frozenset[str]:
        return frozenset(e.model_id for e in self._router_entries)

    def _prioritized_model_ids(self) -> frozenset[str]:
        return frozenset(
            model_id for ids in self._priorities.values() for model_id in ids
        )

    def metadata_only_model_ids(self) -> frozenset[str]:
        """Models carried in metadata but reachable by no routing path."""
        return (
            frozenset(self._models)
            - self._routed_model_ids()
            - self._prioritized_model_ids()
        )

    def unrouted_priority_model_ids(self) -> frozenset[str]:
        """Models in a priority list but absent from the router model list."""
        return self._prioritized_model_ids() - self._routed_model_ids()

    def selection_router_disagreements(
        self,
    ) -> Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]]:
        """Selection types whose priority list differs from the router group.

        Maps selection type -> (priority list, router entry order) for every
        selection type where the two are not identical.
        """
        out: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {}
        for selection_type, group in self._selection_type_to_group.items():
            prioritized = self.priority_model_ids(selection_type)
            routed = tuple(
                e.model_id for e in self._router_entries if e.group == group
            )
            if prioritized != routed:
                out[selection_type] = (prioritized, routed)
        return out


def build_default_catalog() -> ProviderCatalog:
    """Build the catalog with facts transcribed from the live copies.

    Transcription sources (deleted in follow-up PRs once callers derive
    from the catalog): provider_definitions.PROVIDERS,
    litellm_config.MODEL_METADATA, model_selection.MODEL_PRIORITIES and
    SELECTION_TYPE_TO_GROUP and MODEL_GROUPS, litellm_config.build_model_list,
    the context fallback chains in litellm_config.create_litellm_router,
    and setup_wizard.PROVIDER_TO_MODEL.
    """
    providers = (
        ProviderFacts(
            name="cerebras",
            env_var="CEREBRAS_API_KEY",
            console_url="cloud.cerebras.ai",
            quota="14,400 RPD",
            description="best default for agent work",
            setup_priority=1,
            supports_brain=True,
            task_types=("planning", "execution", "quick", "general"),
        ),
        ProviderFacts(
            name="groq",
            env_var="GROQ_API_KEY",
            console_url="console.groq.com/keys",
            quota="7,000 RPD",
            description="fast fallback for agent work",
            setup_priority=2,
            supports_brain=True,
            task_types=("planning", "execution", "quick", "general"),
        ),
        ProviderFacts(
            name="gemini",
            env_var="GEMINI_API_KEY",
            console_url="aistudio.google.com/apikey",
            quota="varies",
            description="overflow option when free-tier capacity matters",
            setup_priority=3,
            supports_brain=True,
            task_types=("planning", "execution", "quick", "general"),
        ),
        ProviderFacts(
            name="sambanova",
            env_var="SAMBANOVA_API_KEY",
            console_url="cloud.sambanova.ai",
            quota="varies",
            description="optional extra capacity",
            setup_priority=4,
            supports_brain=True,
            task_types=("planning", "execution", "quick", "general"),
        ),
    )

    models = (
        ModelFacts(
            model_id="groq/llama-3.1-8b-instant",
            provider="groq",
            group="fast",
            context_length=131072,
            speed=SpeedRank.VERY_FAST,
            quality=QualityRank.GOOD,
            rpd=7000,
            tpm=20000,
        ),
        ModelFacts(
            model_id="cerebras/llama3.1-8b",
            provider="cerebras",
            group="fast",
            context_length=8192,
            speed=SpeedRank.ULTRA_FAST,
            quality=QualityRank.GOOD,
            rpd=14400,
            tpm=60000,
        ),
        ModelFacts(
            model_id="cerebras/llama-3.3-70b",
            provider="cerebras",
            group="chat",
            context_length=8192,
            speed=SpeedRank.ULTRA_FAST,
            quality=QualityRank.EXCELLENT,
            rpd=14400,
            tpm=60000,
        ),
        ModelFacts(
            model_id="groq/llama-3.3-70b-versatile",
            provider="groq",
            group="chat",
            context_length=32768,
            speed=SpeedRank.FAST,
            quality=QualityRank.EXCELLENT,
            rpd=1000,
            tpm=12000,
        ),
        ModelFacts(
            model_id="sambanova/Meta-Llama-3.1-8B-Instruct",
            provider="sambanova",
            group="fast",
            context_length=16384,
            speed=SpeedRank.FAST,
            quality=QualityRank.GOOD,
            rpd=40,
            tpm=100000,
        ),
        ModelFacts(
            model_id="sambanova/Meta-Llama-3.3-70B-Instruct",
            provider="sambanova",
            group="chat",
            context_length=131072,
            speed=SpeedRank.ULTRA_FAST,
            quality=QualityRank.EXCELLENT,
            rpd=40,
            tpm=100000,
        ),
        ModelFacts(
            model_id="cerebras/qwen-3-235b-a22b-instruct-2507",
            provider="cerebras",
            group="instruct",
            context_length=8192,
            speed=SpeedRank.FAST,
            quality=QualityRank.EXCELLENT,
            rpd=14400,
            tpm=60000,
        ),
        ModelFacts(
            model_id="cerebras/gpt-oss-120b",
            provider="cerebras",
            group="instruct",
            context_length=131072,
            speed=SpeedRank.FAST,
            quality=QualityRank.VERY_GOOD,
            rpd=14400,
            tpm=60000,
        ),
        ModelFacts(
            model_id="cerebras/zai-glm-4.7",
            provider="cerebras",
            group="instruct",
            context_length=131072,
            speed=SpeedRank.FAST,
            quality=QualityRank.VERY_GOOD,
            rpd=14400,
            tpm=60000,
        ),
        ModelFacts(
            model_id="groq/moonshotai/kimi-k2-instruct",
            provider="groq",
            group="instruct",
            context_length=131072,
            speed=SpeedRank.ULTRA_FAST,
            quality=QualityRank.VERY_GOOD,
            rpd=7000,
            tpm=20000,
        ),
        ModelFacts(
            model_id="gemini/gemini-2.5-flash",
            provider="gemini",
            group="instruct",
            context_length=1000000,
            speed=SpeedRank.MODERATE,
            quality=QualityRank.VERY_GOOD,
            rpd=250,
            tpm=250000,
        ),
    )

    # Priority order per selection type: first is highest, tried first.
    # Based on JSON compliance testing (2025-12):
    # - Cerebras & Groq: 110/100 (perfect JSON)
    # - Gemini: 80/100 (adds markdown code fences - causes parse failures)
    # Provider priority: Cerebras (highest RPD 14,400) > Groq (fast 0.4s)
    # > SambaNova (low RPD). Instruct tier: gpt-oss-120b stable default,
    # kimi-k2 fast fallback, zai-glm preview fallback, gemini huge-context
    # last resort, qwen-235b final preview fallback.
    priorities: Dict[str, Tuple[str, ...]] = {
        "fast": (
            "groq/llama-3.1-8b-instant",
            "cerebras/llama3.1-8b",
            "sambanova/Meta-Llama-3.1-8B-Instruct",
        ),
        "chat": (
            "cerebras/llama-3.3-70b",
            "groq/llama-3.3-70b-versatile",
        ),
        "instruct": (
            "cerebras/gpt-oss-120b",
            "groq/moonshotai/kimi-k2-instruct",
            "cerebras/zai-glm-4.7",
            "gemini/gemini-2.5-flash",
            "cerebras/qwen-3-235b-a22b-instruct-2507",
        ),
        "embed": (
            "groq/llama-3.1-8b-instant",
            "cerebras/llama3.1-8b",
        ),
    }

    selection_type_to_group = {
        "fast": "fast",
        "chat": "chat",
        "instruct": "instruct",
        "embed": "fast",
    }

    # Router entry order IS build_model_list output order (intra-group
    # priority). Chat group must use models with native tool calling -
    # Llama hallucinates fake XML syntax; lower volume than agent loops,
    # so quality models carry no rate-limit risk. SambaNova fast entry
    # rpm=1 reflects its ~40 RPD quota.
    router_entries = (
        RouterEntry(group="fast", model_id="groq/llama-3.1-8b-instant", tpm=20000, rpm=30),
        RouterEntry(group="fast", model_id="cerebras/llama3.1-8b", tpm=60000, rpm=30),
        RouterEntry(group="fast", model_id="sambanova/Meta-Llama-3.1-8B-Instruct", tpm=100000, rpm=1),
        RouterEntry(group="chat", model_id="gemini/gemini-2.5-flash", tpm=250000, rpm=10),
        RouterEntry(group="chat", model_id="groq/moonshotai/kimi-k2-instruct", tpm=20000, rpm=30),
        RouterEntry(group="instruct", model_id="cerebras/gpt-oss-120b", tpm=60000, rpm=30),
        RouterEntry(group="instruct", model_id="groq/moonshotai/kimi-k2-instruct", tpm=20000, rpm=30),
        RouterEntry(group="instruct", model_id="cerebras/zai-glm-4.7", tpm=60000, rpm=10),
        RouterEntry(group="instruct", model_id="gemini/gemini-2.5-flash", tpm=250000, rpm=10),
        RouterEntry(group="instruct", model_id="cerebras/qwen-3-235b-a22b-instruct-2507", tpm=60000, rpm=30),
    )

    context_fallbacks = (
        ContextFallback(
            primary="cerebras/qwen-3-235b-a22b-instruct-2507",
            fallbacks=(
                "cerebras/gpt-oss-120b",
                "groq/moonshotai/kimi-k2-instruct",
                "cerebras/zai-glm-4.7",
                "gemini/gemini-2.5-flash",
            ),
        ),
        ContextFallback(
            primary="cerebras/gpt-oss-120b",
            fallbacks=("gemini/gemini-2.5-flash",),
        ),
        ContextFallback(
            primary="cerebras/zai-glm-4.7",
            fallbacks=("gemini/gemini-2.5-flash",),
        ),
        ContextFallback(
            primary="cerebras/llama-3.3-70b",
            fallbacks=("groq/moonshotai/kimi-k2-instruct", "gemini/gemini-2.5-flash"),
        ),
        ContextFallback(
            primary="cerebras/llama3.1-8b",
            fallbacks=("groq/llama-3.1-8b-instant", "gemini/gemini-2.5-flash"),
        ),
        ContextFallback(
            primary="groq/moonshotai/kimi-k2-instruct",
            fallbacks=("gemini/gemini-2.5-flash",),
        ),
        ContextFallback(
            primary="groq/llama-3.3-70b-versatile",
            fallbacks=("gemini/gemini-2.5-flash",),
        ),
    )

    validation_models = {
        "groq": "groq/llama-3.1-8b-instant",
        "cerebras": "cerebras/gpt-oss-120b",
        "gemini": "gemini/gemini-2.5-flash",
        "sambanova": "sambanova/Meta-Llama-3.1-8B-Instruct",
        "openrouter": "openrouter/meta-llama/llama-3.1-8b-instruct:free",
        "github_models": "azure/gpt-4o-mini",
    }

    return ProviderCatalog(
        providers=providers,
        models=models,
        priorities=priorities,
        selection_type_to_group=selection_type_to_group,
        router_groups=("fast", "chat", "instruct"),
        router_entries=router_entries,
        context_fallbacks=context_fallbacks,
        validation_models=validation_models,
    )
