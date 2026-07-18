"""
Production composition for the API key configuration service.

Hosts the single production factory wiring infrastructure (JSONPersistence
at the platform user config path) to provider domain facts (the catalog's
known provider env vars). Composition lives here, above infrastructure, so
infrastructure modules never import provider facts or app wiring.
"""

from pathlib import Path
from typing import Optional, Tuple

from scrappy.infrastructure import paths
from scrappy.infrastructure.config.api_keys import ApiKeyConfigService
from scrappy.infrastructure.persistence.json_persistence import JSONPersistence

from .provider_catalog import build_default_catalog

# Provider env vars are process constants: pure frozen-dataclass
# construction, no I/O. The user-config PATH is deliberately not bound
# here: the factory dereferences paths.USER_CONFIG_FILE at call time so
# a patch at its source module reaches the factory.
_KNOWN_PROVIDER_ENV_VARS: Tuple[str, ...] = (
    build_default_catalog().known_provider_env_vars()
)


def create_api_key_service(
    config_file: Optional[Path] = None,
) -> ApiKeyConfigService:
    """
    Create the production ApiKeyConfigService.

    Args:
        config_file: Override for the persisted config path (test seam).
            Defaults to paths.USER_CONFIG_FILE, resolved at call time.

    Returns:
        ApiKeyConfigService backed by JSONPersistence, migrating the
        catalog's known provider env vars.
    """
    resolved = config_file if config_file is not None else paths.USER_CONFIG_FILE
    persistence = JSONPersistence(str(resolved))
    return ApiKeyConfigService(persistence, _KNOWN_PROVIDER_ENV_VARS)
