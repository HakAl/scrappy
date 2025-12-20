---
# Config Scopes: User vs Project

## Status: IMPLEMENTED

Rate limits now stored in `~/.scrappy/rate_limits.json` (user-level).
Migration: existing project-level files are auto-migrated on first use.

See `src/scrappy/infrastructure/paths.py` for implementation.

---

## Problem (Original)
Rate limits should be per-user (API keys are user-level), not per-project.

## Proposed Scope

| USER (~/.scrappy/)  | PROJECT (.scrappy/) |
|---------------------|---------------------|
| rate_limits.json    | command_history     |
| config/             | lancedb/            |
|  - api keys         | conversations.db    |
|  - disclaimer       | audit.json          |
|                     | config.json         |
|                     | debug.log           |
|                     | fingerprints.json   |
|                     | response_cache.json |
|                     | session.json        |

## Implementation Plan

**Scope: Minor (~25-30 lines)**

### 1. Update protocols.py (~5 lines)
Add to PathProviderProtocol:
```python
def user_data_dir(self) -> Path:
    """Get user-level data directory (~/.scrappy/)."""
    ...
```

### 2. Update paths.py (~15 lines)

ScrappyPathProvider changes:
```python
def __init__(self, project_root: Path):
    self._project_root = project_root
    self._data_dir = project_root / ".scrappy"
    self._user_dir = Path.home() / ".scrappy"  # NEW

def user_data_dir(self) -> Path:  # NEW
    return self._user_dir

def ensure_user_dir(self) -> None:  # NEW
    self._user_dir.mkdir(parents=True, exist_ok=True)

def rate_limits_file(self) -> Path:
    return self._user_dir / "rate_limits.json"  # CHANGED from _data_dir
```

### 3. Update TempPathProvider (~5 lines)
Mirror new methods for test isolation.

### 4. Migration (optional, ~10 lines)
In factory.py when creating rate tracker:
- Check if project-level rate_limits.json exists
- If user-level doesn't exist, copy project-level to user-level
- Log migration message

## Callers
`rate_limits_file()` signature unchanged - factory.py works as-is.

## Platform Note
`Path.home() / ".scrappy"` works cross-platform.
Could use `platformdirs` for proper %APPDATA% on Windows if desired.
---

