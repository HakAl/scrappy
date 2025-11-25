# Phase 2 Follow-up Plan

## Status: COMPLETED

Implementation completed on 2025-11-25. All acceptance criteria met.

These issues were discovered while implementing the clarification config changes in Phase 2. This document now serves as the implementation plan with architectural guidance.

---

## Issue 1: Import Path Inconsistency

**Location:** `src/task_router/router.py`

**Problem:** Mixed absolute and relative imports in the same file:

```python
# Absolute import (inconsistent)
from src.config.schema import ClarificationConfig

# Relative imports (standard for this file)
from .protocols import ClarificationConfigProtocol, DefaultConsoleInput, ...
```

**Risk:** Could cause import errors if package is installed or run from different contexts.

### Implementation Plan

1. Audit all files in `src/task_router/` for import consistency
2. Standardize on relative imports within the package
3. For cross-package imports, use absolute imports from the package root (e.g., `from src.config...`)

**Note:** This issue is superseded by Issue 6 - the import will be removed entirely when `ClarificationConfig` moves to the domain layer.

---

## Issue 2: Config Loading Not Implemented

**Problem:** `ClarificationConfig` values are not loaded from `.scrappy.yaml` / `.scrappy.json` files. The config infrastructure exists but there's no loader that:

1. Reads the `clarification` section from config files
2. Constructs a `ClarificationConfig` instance
3. Passes it to `TaskRouter`

**Current behavior:** Always uses defaults (0.7 / 0.9 thresholds).

### Implementation Plan

#### Step 1: Define ConfigLoaderProtocol

Config loading is I/O - it must be injectable for testing.

```python
# src/config/protocols.py
from typing import Protocol, Any

class ConfigLoaderProtocol(Protocol):
    """Abstract interface for loading configuration from external sources."""

    def load(self) -> dict[str, Any]:
        """Load and return configuration dictionary.

        Returns:
            Configuration data as a dictionary.

        Raises:
            ConfigLoadError: If the config file cannot be read or parsed.
        """
        ...
```

#### Step 2: Add Validation to ClarificationConfig

```python
# src/task_router/config.py (new location per Issue 6)
from dataclasses import dataclass

@dataclass(frozen=True)
class ClarificationConfig:
    confidence_threshold: float = 0.7
    high_confidence_bypass: float = 0.9

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                f"confidence_threshold must be between 0.0 and 1.0, "
                f"got {self.confidence_threshold}"
            )
        if not 0.0 <= self.high_confidence_bypass <= 1.0:
            raise ValueError(
                f"high_confidence_bypass must be between 0.0 and 1.0, "
                f"got {self.high_confidence_bypass}"
            )
        if self.confidence_threshold >= self.high_confidence_bypass:
            raise ValueError(
                f"confidence_threshold ({self.confidence_threshold}) must be less than "
                f"high_confidence_bypass ({self.high_confidence_bypass})"
            )

    @classmethod
    def from_dict(cls, data: dict) -> "ClarificationConfig":
        """Factory method for creating config from dictionary.

        Args:
            data: Dictionary with optional 'confidence_threshold' and
                  'high_confidence_bypass' keys.

        Returns:
            Validated ClarificationConfig instance.
        """
        return cls(
            confidence_threshold=data.get('confidence_threshold', 0.7),
            high_confidence_bypass=data.get('high_confidence_bypass', 0.9),
        )
```

#### Step 3: Implement FileConfigLoader

```python
# src/config/loaders.py
from pathlib import Path
from typing import Any
import json
import yaml  # if using YAML support

class FileConfigLoader:
    """Loads configuration from .scrappy.yaml or .scrappy.json files."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def load(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return {}

        content = self._config_path.read_text()

        if self._config_path.suffix in ('.yaml', '.yml'):
            return yaml.safe_load(content) or {}
        elif self._config_path.suffix == '.json':
            return json.loads(content)
        else:
            raise ConfigLoadError(f"Unsupported config format: {self._config_path.suffix}")
```

#### Step 4: Wire Up in Bootstrap

```python
# Application entry point
from src.config.loaders import FileConfigLoader
from src.task_router.config import ClarificationConfig

config_loader = FileConfigLoader(Path(".scrappy.yaml"))
config_data = config_loader.load()

clarification_config = ClarificationConfig.from_dict(
    config_data.get('clarification', {})
)

router = TaskRouter(..., clarification_config=clarification_config)
```

### Tests Required

1. `test_clarification_config_validation_rejects_negative_threshold`
2. `test_clarification_config_validation_rejects_threshold_above_one`
3. `test_clarification_config_validation_rejects_threshold_gte_bypass`
4. `test_clarification_config_from_dict_uses_defaults`
5. `test_clarification_config_from_dict_overrides_defaults`
6. `test_file_config_loader_returns_empty_dict_when_file_missing`
7. `test_file_config_loader_parses_yaml`
8. `test_file_config_loader_parses_json`

---

## Issue 3: Default Threshold Changed (Breaking Change)

**Problem:** Confidence threshold default changed from 0.65 to 0.7.

| Location | Old Value | New Value |
|----------|-----------|-----------|
| `TaskRouter.__init__` | 0.65 | 0.7 (via ClarificationConfig) |

**Impact:** Tasks with confidence between 0.65-0.69 that previously triggered clarification will now skip it.

### Implementation Plan

Add deprecation warning when using implicit defaults:

```python
# src/task_router/router.py
import warnings

class TaskRouter:
    def __init__(
        self,
        ...,
        clarification_config: ClarificationConfigProtocol | None = None,
    ) -> None:
        if clarification_config is None:
            warnings.warn(
                "Default confidence_threshold changed from 0.65 to 0.7 in v2.0. "
                "Pass explicit ClarificationConfig to suppress this warning.",
                DeprecationWarning,
                stacklevel=2,
            )
            clarification_config = ClarificationConfig()

        self._clarification_config = clarification_config
```

### Decision Required

Choose one:
- **Option A:** Keep 0.7 default (aligns with plan document) + deprecation warning
- **Option B:** Revert to 0.65 for backwards compatibility

**Recommendation:** Option A - the warning gives users visibility and the ability to explicitly set their preferred threshold.

---

## Issue 4: Missing `__init__.py` Export

**Location:** `src/config/__init__.py`

**Problem:** `ClarificationConfig` not exported from config module.

### Implementation Plan

**Note:** This issue becomes moot if Issue 6 is implemented first - `ClarificationConfig` will move to `src/task_router/config.py`.

If keeping in `src/config/`:

```python
# In src/config/__init__.py
from .schema import ClarificationConfig

__all__ = [
    # ... existing exports ...
    'ClarificationConfig',
]
```

---

## Issue 5: Protocol vs ABC Duplication

**Problem:** Two abstractions for intent clarification exist:

| File | Name | Type |
|------|------|------|
| `protocols.py` | `IntentClarifierProtocol` | Protocol (structural typing) |
| `intent_clarifier.py` | `IntentClarifierInterface` | ABC (nominal typing) |

**Impact:** Confusing for developers, unclear which to use for type hints.

### Implementation Plan

#### Step 1: Audit Usages

Search for all usages of `IntentClarifierInterface`:
- Type hints
- `isinstance()` checks
- Inheritance (`class Foo(IntentClarifierInterface)`)
- Test assertions

#### Step 2: Migration

For each usage:

| Usage Type | Migration |
|------------|-----------|
| Type hint | Replace with `IntentClarifierProtocol` |
| `isinstance()` check | Replace with `hasattr()` or duck typing |
| Inheritance | Remove, ensure class satisfies protocol |
| Test mock | Use protocol-based test double |

#### Step 3: Deprecation Period

```python
# src/task_router/intent_clarifier.py
import warnings
from abc import ABC, abstractmethod

class IntentClarifierInterface(ABC):
    """DEPRECATED: Use IntentClarifierProtocol instead."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} inherits from IntentClarifierInterface which is deprecated. "
            "Implement IntentClarifierProtocol instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    @abstractmethod
    def clarify(self, query: str) -> ClarifiedIntent:
        ...
```

#### Step 4: Removal

After deprecation period, remove `IntentClarifierInterface` entirely.

### Tests Required

1. `test_concrete_clarifier_satisfies_protocol` (static type check)
2. `test_deprecation_warning_on_abc_inheritance`

---

## Issue 6: Config-to-Domain Dependency Inversion (NEW)

**Problem:** `src/task_router/router.py` imports from `src/config/schema.py`. This creates a dependency from the domain layer (task_router) to infrastructure (config).

```
Current:
  task_router (domain) --> config (infrastructure)

Should be:
  config (infrastructure) --> task_router (domain)
  OR
  both depend on shared protocols
```

### Implementation Plan

#### Option A: Move Config to Domain (Recommended)

Move `ClarificationConfig` to where it's consumed:

```
src/task_router/
    config.py          <-- NEW: ClarificationConfig lives here
    protocols.py       <-- ClarificationConfigProtocol already here
    router.py          <-- imports from local config.py
```

```python
# src/task_router/config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ClarificationConfig:
    """Configuration for the clarification subsystem.

    This is a domain object - it belongs with the code that uses it.
    """
    confidence_threshold: float = 0.7
    high_confidence_bypass: float = 0.9

    # Validation and factory methods as shown in Issue 2
```

#### Option B: Shared Protocols Package

If `ClarificationConfig` is truly shared across multiple domains:

```
src/
    shared/
        protocols.py   <-- ClarificationConfigProtocol
    task_router/
        config.py      <-- ClarificationConfig implements protocol
    config/
        loaders.py     <-- FileConfigLoader uses protocol
```

**Recommendation:** Option A unless there's evidence of multi-domain usage.

### Migration Steps

1. Create `src/task_router/config.py` with `ClarificationConfig`
2. Update imports in `src/task_router/router.py` to use local config
3. Update `src/config/schema.py` to re-export for backwards compatibility (with deprecation warning)
4. Update tests
5. Remove re-export after deprecation period

---

## Implementation Order

Based on dependencies between issues:

```
Phase A (Foundation):
  Issue 6 --> Issue 4 --> Issue 1
  (Move config to domain, fixes export and import issues)

Phase B (Config Loading):
  Issue 2
  (Implement full config loading with protocols)

Phase C (Cleanup):
  Issue 5 --> Issue 3
  (Consolidate abstractions, add deprecation warnings)
```

### Detailed Sequence

1. **Issue 6** - Move `ClarificationConfig` to `src/task_router/config.py`
   - This automatically resolves Issue 1 (import inconsistency)
   - This makes Issue 4 moot (no need to export from config module)

2. **Issue 2** - Implement config loading
   - Add `ConfigLoaderProtocol`
   - Add validation to `ClarificationConfig`
   - Implement `FileConfigLoader`
   - Wire up in bootstrap

3. **Issue 5** - Consolidate Protocol/ABC
   - Audit usages
   - Add deprecation warning to ABC
   - Migrate usages to Protocol

4. **Issue 3** - Add breaking change warning
   - Add deprecation warning for implicit defaults

---

## Priority Matrix (Updated)

| Issue | Severity | Effort | Dependencies |
|-------|----------|--------|--------------|
| Issue 6: Dependency Inversion | High | Low | None |
| Issue 2: Config Loading | High | Medium | Issue 6 |
| Issue 5: Protocol/ABC Duplication | Medium | Medium | None |
| Issue 1: Import Inconsistency | Medium | Low | Resolved by Issue 6 |
| Issue 4: Missing Export | Low | Trivial | Resolved by Issue 6 |
| Issue 3: Breaking Change | Low | Trivial | Issue 2 |

---

## Acceptance Criteria

All issues are resolved when:

- [x] `ClarificationConfig` lives in `src/task_router/config.py`
- [x] `ClarificationConfig` has validation in `__post_init__`
- [x] `ConfigLoaderProtocol` exists and is used for file loading
- [x] Config values are loaded from `.scrappy.yaml` / `.scrappy.json`
- [x] `IntentClarifierInterface` ABC is deprecated with warning
- [x] All type hints use `IntentClarifierProtocol`
- [x] Deprecation warning exists for implicit config defaults
- [x] All new code has corresponding tests
- [x] No `isinstance()` checks against ABC remain
