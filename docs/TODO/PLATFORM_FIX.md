# Platform Detection Consolidation

## Goal

Delete duplicate platform detection code. Standardize on `src/platform`.

## Current State

Two implementations exist:

1. **src/context/platform.py** - `PlatformDetector` (TO BE DELETED)
   - Returns lowercase strings: 'windows', 'darwin', 'linux', 'unix'
   - Tool availability via shutil.which
   - Used by CodebaseContext

2. **src/platform/detection.py** - `SystemPlatformDetector` (KEEP)
   - Returns PlatformType: 'Windows', 'macOS', 'Linux', etc.
   - Shell detection, Git Bash detection
   - Implements PlatformDetectorProtocol
   - Currently wraps CorePlatformDetector (the duplicate)

## Usage Points

### Production Code
- `src/context/codebase_context.py` - imports PlatformDetector, exposes get_platform()/has_tool()
- `src/agent/core.py:767` - `platform = Platform.WINDOWS if self.orch.context.get_platform() == "windows" else Platform.UNIX`

### Test Infrastructure
- `tests/helpers.py:FakePlatformDetector` - already implements PlatformDetectorProtocol (good)
- `tests/platform/test_platform_detector.py` - tests old PlatformDetector (delete)
- `tests/platform/test_detection.py` - tests SystemPlatformDetector (keep)

### Documentation
- `docs/behavior/CONTEXT.md` - shows old API examples (update)

## Migration Plan

### Step 1: Update SystemPlatformDetector
- Remove CorePlatformDetector wrapper dependency
- Implement tool caching directly (copy logic from old PlatformDetector)

### Step 2: Update CodebaseContext
- Change import from `src.context.platform.PlatformDetector` to `src.platform.detection.SystemPlatformDetector`
- Delete `get_platform()` and `has_tool()` wrapper methods
- Expose `platform: PlatformDetectorProtocol` property instead

### Step 3: Update core.py
- Change from: `self.orch.context.get_platform() == "windows"`
- Change to: `self.orch.context.platform.is_windows()`

### Step 4: Delete Files
- `src/context/platform.py`
- `tests/platform/test_platform_detector.py`

### Step 5: Consolidate Tests
- Move any valuable tests from test_platform_detector.py into test_detection.py
- Most tests overlap; the detection tests are more comprehensive

### Step 6: Update Documentation
- `docs/behavior/CONTEXT.md` - update examples to use new API

## Files Changed

| File | Action |
|------|--------|
| src/platform/detection.py | Modify - remove CorePlatformDetector, add tool caching |
| src/context/codebase_context.py | Modify - use SystemPlatformDetector, expose as property |
| src/agent/core.py | Modify - use is_windows() |
| src/context/platform.py | DELETE |
| tests/platform/test_platform_detector.py | DELETE |
| tests/platform/test_detection.py | Modify - add any missing coverage |
| docs/behavior/CONTEXT.md | Modify - update examples |

## New API

```python
# Old way (being deleted)
context.get_platform()  # returns 'windows'
context.has_tool('git')  # returns bool

# New way
context.platform.is_windows()  # returns bool
context.platform.is_unix()  # returns bool
context.platform.is_macos()  # returns bool
context.platform.get_platform_name()  # returns 'Windows', 'macOS', 'Linux', etc.
context.platform.has_tool('git')  # returns bool
context.platform.get_shell_info()  # returns dict of available shells
context.platform.has_git_bash()  # returns bool
```
