# Platform Detection Consolidation Plan

## Problem

Multiple platform detection systems exist across the codebase when everything should use `src/platform/`.

## Current State

### Canonical System (KEEP)
- `src/platform/` - Well-architected protocol-based platform module
  - `detection.py` - `SystemPlatformDetector` implementation
  - `protocols/detection.py` - `PlatformDetectorProtocol` interface
  - `translation.py` - Command translation (Unix to Windows)
  - `validation.py` - Command validation
  - `orchestrator.py` - Coordinates all components
  - `factory.py` - Factory functions for creating instances

### Files to Delete
| File | Reason |
|------|--------|
| `src/platform_utils.py` | Facade layer - inline usages directly to `src/platform` |
| `src/agent/platform_adapter.py` | Bridge layer - migrate callers to use orchestrator directly |
| `src/agent_tools/components/platform_sanitizer.py` | Redundant - use `SmartCommandTranslator` instead |

### Files with Direct `sys.platform` / `os.name` Checks (Must Fix)

| File | Line(s) | Current | Migration |
|------|---------|---------|-----------|
| `scrappy.py` | 19 | `sys.platform == 'win32'` | Inject detector, use `is_windows()` |
| `src/agent/audit.py` | 101, 117 | `sys.platform` checks | Inject detector |
| `src/cli/validators/path.py` | 187 | `os.name == 'nt'` | Inject detector |
| `src/agent_tools/tools/command_tool.py` | 32-33 | `os.name == 'nt'` fallback | Remove fallback, always use injected detector |
| `src/task_router/classifier.py` | 11 | imports `is_windows` | Inject `PlatformDetectorProtocol` |
| `src/agent_config.py` | 11, 58, 60 | imports from `platform_utils` | Import from `src/platform` instead |

### Test Files (Lower Priority)
| File | Line(s) | Issue |
|------|---------|-------|
| `tests/test_unicode_encoding.py` | 22, 76 | `sys.platform == 'win32'` - use pytest markers |
| `tests/agent_tools/test_agent_tools.py` | 284, 362 | `sys.platform == 'win32'` - use pytest markers |
| `tests/classifier/test_classifier_comprehensive.py` | 551 | imports `_reset_orchestrator` from `platform_utils` |
| `tests/agent/test_agent_path_escaping.py` | 18, 193 | imports from `platform_utils` |
| `tests/helpers.py` | 32 | Hardcoded `/tmp/test` - use `tempfile.gettempdir()` |

### Documentation to Update
| File | Issue |
|------|-------|
| `docs/behavior/CONTEXT.md` | Documents old `sys.platform` method |

---

## Implementation Plan

### Phase 1: Core Migration (Critical Path)

#### 1.1 Fix `scrappy.py` Entry Point
**File:** `scrappy.py:19`
**Current:**
```python
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
```
**Action:**
- Replace with:
```python
from src.platform import configure_console_encoding
configure_console_encoding()
```
- Remove `import sys` if no longer needed
- Function implementation added in Phase 0

#### 1.2 Fix `src/agent/audit.py` Signal Handling
**File:** `src/agent/audit.py:101-121`
**Current:**
```python
if sys.platform != 'win32':
    signal.signal(signal.SIGTERM, self._signal_handler)
```
**Action:**
- Inject `PlatformDetectorProtocol` via constructor
- Replace `sys.platform` checks with `detector.is_windows()` / `detector.is_unix()`

#### 1.3 Fix `src/cli/validators/path.py` Path Handling
**File:** `src/cli/validators/path.py:187`
**Current:**
```python
if os.name == 'nt':
    final_path = path
```
**Action:**
- Inject `PlatformDetectorProtocol` via constructor
- Replace `os.name == 'nt'` with `detector.is_windows()`

#### 1.4 Fix `src/agent_tools/tools/command_tool.py`
**File:** `src/agent_tools/tools/command_tool.py:32-33`
**Current:**
```python
def is_windows():
    return os.name == 'nt'
```
**Action:**
- Remove the local `is_windows()` fallback function
- Ensure detector is always injected (no fallback needed)

#### 1.5 Fix `src/task_router/classifier.py`
**File:** `src/task_router/classifier.py:11`
**Current:** Imports `is_windows` from `platform_utils`
**Action:**
- Change to inject `PlatformDetectorProtocol` in constructor
- Use `detector.is_windows()` instead of calling imported function

#### 1.6 Fix `src/agent_config.py`
**File:** `src/agent_config.py:11, 58, 60`
**Current:**
```python
from .platform_utils import get_dangerous_commands, get_interactive_commands
```
**Action:**
- Change import to:
```python
from src.platform import get_dangerous_commands, get_interactive_commands
```
- No other changes needed (functions exported in Phase 0)

### Phase 2: Delete Redundant Files

#### 2.1 Delete `src/agent_tools/components/platform_sanitizer.py`
**Action:**
- Find all usages of `WindowsSanitizer` and `UnixSanitizer`:
  - `src/agent_tools/tools/command_tool.py:78-79, 86, 153-154, 169`
  - `src/agent_tools/components/__init__.py:12, 19-20`
- Replace with `SmartCommandTranslator.translate_command()` from `src/platform`
- Remove exports from `src/agent_tools/components/__init__.py`
- Delete the file

#### 2.2 Delete `src/platform_utils.py`
**Prerequisites:** All callers migrated to use `src/platform` directly
**Action:**
- Search for all imports from `platform_utils`
- Replace with direct imports from `src/platform.factory` or `src/platform`
- Delete the file

#### 2.3 Delete `src/agent/platform_adapter.py`
**Analysis:**
- `RealPlatformUtils` is only used in `src/agent/core.py:293-294`
- `core.py` stores `_platform_utils` but NEVER uses it (dead code)
- `PlatformUtilsProtocol` in `src/agent/protocols.py` is unused outside adapter

**Action:**
- Delete `src/agent/platform_adapter.py`
- Remove from `src/agent/core.py`:
  - Line 90: Remove `platform_utils` parameter
  - Line 118: Remove docstring reference
  - Line 140: Remove `self._platform_utils = ...`
  - Lines 291-294: Remove `_create_default_platform_utils()` method
- Remove from `src/agent/protocols.py`:
  - Lines 405-430: Delete `PlatformUtilsProtocol` class
- Remove from `src/agent/__init__.py`:
  - Line 25: Remove `PlatformUtilsProtocol` import
  - Line 28: Remove `RealPlatformUtils, MockPlatformUtils` import
  - Lines 54, 59-60: Remove from `__all__`
- Move `MockPlatformUtils` to `src/platform/testing.py` for test use

### Phase 3: Update Tests

#### 3.1 Fix `tests/test_unicode_encoding.py`
**Action:**
- Replace `sys.platform == 'win32'` with pytest markers:
```python
import pytest
from src.platform import create_platform_detector

detector = create_platform_detector()

@pytest.mark.skipif(not detector.is_windows(), reason="Windows-only test")
def test_windows_unicode():
    ...
```

#### 3.2 Fix `tests/helpers.py`
**Action:**
- Replace hardcoded `/tmp/test` with `os.path.join(tempfile.gettempdir(), 'test')`

### Phase 4: Documentation

#### 4.1 Update `docs/behavior/CONTEXT.md`
**Action:**
- Update platform detection reference from `sys.platform` to `src/platform`
- Document the canonical pattern:
```python
from src.platform import create_platform_detector
detector = create_platform_detector()
if detector.is_windows():
    ...
```

---

## Required Extensions to `src/platform`

Add to `src/platform/__init__.py`:

1. **Console encoding setup** (for `scrappy.py`):
```python
def configure_console_encoding() -> None:
    """Configure UTF-8 encoding for console output on Windows."""
    detector = create_platform_detector()
    if detector.is_windows():
        import sys
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
```

2. **Command list functions** (for `agent_config.py`):
```python
_cached_validator = None

def get_dangerous_commands() -> List[str]:
    """Get platform-specific dangerous command patterns."""
    global _cached_validator
    if _cached_validator is None:
        _cached_validator = create_command_validator()
    return _cached_validator.get_dangerous_commands()

def get_interactive_commands() -> List[str]:
    """Get platform-specific interactive command patterns."""
    global _cached_validator
    if _cached_validator is None:
        _cached_validator = create_command_validator()
    return _cached_validator.get_interactive_commands()
```

3. **Mock detector for testing** (move from `platform_adapter.py`):
   - Create `src/platform/testing.py` with `MockPlatformDetector` class

---

## Migration Checklist

### Phase 0: Extend `src/platform`
- [ ] Add `configure_console_encoding()` to `src/platform/__init__.py`
- [ ] Add `get_dangerous_commands()` to `src/platform/__init__.py`
- [ ] Add `get_interactive_commands()` to `src/platform/__init__.py`
- [ ] Create `src/platform/testing.py` with `MockPlatformDetector`

### Phase 1: Core Source Files
- [ ] `scrappy.py` - use `configure_console_encoding()`
- [ ] `src/agent/audit.py` - inject detector, replace `sys.platform` checks
- [ ] `src/cli/validators/path.py` - inject detector, replace `os.name` check
- [ ] `src/agent_tools/tools/command_tool.py` - remove fallback, replace sanitizers with translator
- [ ] `src/task_router/classifier.py` - inject detector
- [ ] `src/agent_config.py` - change import to `from src.platform import ...`

### Phase 2: Delete Redundant Files
- [ ] Delete `src/agent_tools/components/platform_sanitizer.py`
- [ ] Update `src/agent_tools/components/__init__.py` - remove sanitizer exports
- [ ] Delete `src/platform_utils.py`
- [ ] Delete `src/agent/platform_adapter.py`
- [ ] Clean up `src/agent/core.py` - remove dead `platform_utils` code
- [ ] Clean up `src/agent/protocols.py` - remove `PlatformUtilsProtocol`
- [ ] Clean up `src/agent/__init__.py` - remove platform adapter exports

### Phase 3: Test Files
- [ ] Fix `tests/test_unicode_encoding.py` - use pytest markers
- [ ] Fix `tests/agent_tools/test_agent_tools.py` - use pytest markers
- [ ] Fix `tests/classifier/test_classifier_comprehensive.py` - update imports
- [ ] Fix `tests/agent/test_agent_path_escaping.py` - update imports
- [ ] Fix `tests/helpers.py` - use `tempfile.gettempdir()`

### Phase 4: Documentation & Verification
- [ ] Update `docs/behavior/CONTEXT.md`
- [ ] Run full test suite
- [ ] Verify: `grep -rn "sys.platform\|os.name.*nt\|platform.system" src/ --include="*.py"` only shows `src/platform/`

---

## Verification Command

After migration, verify no stray platform checks remain:

```bash
# Should only show hits in src/platform/
grep -rn "sys.platform\|os.name.*nt\|platform.system" src/ --include="*.py"
```
