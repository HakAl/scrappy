# File System Duplication Analysis

**STATUS: COMPLETED**

Migration completed successfully. The agent file system has been consolidated into infrastructure.

## Problem Summary

There are **two separate file system implementations** in the codebase:

1. `src/agent/file_system.py` + `src/agent/protocols.py::FileSystemProtocol`
2. `src/infrastructure/file_system.py` + `src/infrastructure/protocols.py::FileSystemProtocol`

Both define protocols and implementations (`RealFileSystem` and `InMemoryFileSystem`) that serve the same purpose but with different capabilities and method signatures.

## Detailed Analysis

### Protocol Differences

#### `src/agent/protocols.py::FileSystemProtocol` (lines 497-619)
Methods:
- `read_file(path: str) -> str` (text only)
- `write_file(path: str, content: str) -> None` (text only)
- `exists(path: str) -> bool`
- `is_file(path: str) -> bool`
- `is_dir(path: str) -> bool`
- `mkdir(path: str, parents: bool, exist_ok: bool) -> None`
- `resolve(path: str) -> Path` (returns Path object)
- `join_path(*parts: str) -> str`

#### `src/infrastructure/protocols.py::FileSystemProtocol` (lines 12-212)
Methods:
- `read_text(path: str, encoding: str) -> str`
- `write_text(path: str, content: str, encoding: str) -> None`
- `read_bytes(path: str) -> bytes`
- `write_bytes(path: str, content: bytes) -> None`
- `exists(path: str) -> bool`
- `is_file(path: str) -> bool`
- `is_dir(path: str) -> bool`
- `mkdir(path: str, parents: bool, exist_ok: bool) -> None`
- `list_dir(path: str) -> List[str]`
- `glob(pattern: str) -> List[str]`
- `delete(path: str) -> None`
- `delete_tree(path: str) -> None`
- `resolve(path: str) -> str` (returns string)

**Infrastructure protocol is MORE COMPLETE:**
- Supports both text and binary operations
- Has directory listing and glob support
- Has file/directory deletion
- More explicit with encoding parameter

**Agent protocol is INCOMPLETE:**
- Text operations only (no binary)
- No directory listing
- No glob support
- No deletion operations
- Has `join_path` utility (which infrastructure lacks)

### Implementation Differences

#### `RealFileSystem` Implementations

**Agent version** (`src/agent/file_system.py`, lines 14-128):
- Basic pathlib wrapper
- Text operations only
- Manual `join_path` implementation
- Returns `Path` object from `resolve`
- Simple, minimal implementation

**Infrastructure version** (`src/infrastructure/file_system.py`, lines 14-110):
- More robust pathlib wrapper
- Text AND binary operations
- Auto-creates parent directories on write
- Has `list_dir`, `glob`, `delete`, `delete_tree`
- Returns `str` from `resolve`
- Production-ready implementation

#### `InMemoryFileSystem` Implementations

**Agent version** (`src/agent/file_system.py`, lines 130-273):
- Basic in-memory storage: `_files: dict[str, str]`, `_dirs: set[str]`
- Simple path normalization via `Path()`
- Text operations only
- No glob support
- No deletion operations
- Minimal implementation for basic testing

**Infrastructure version** (`src/infrastructure/file_system.py`, lines 112-380):
- Robust in-memory storage: `_files: Dict[str, bytes]`, `_directories: set`
- Advanced path normalization (handles `/`, `..`, `.`, etc.)
- Text AND binary operations (stores as bytes internally)
- Glob support with fnmatch
- Full deletion support (`delete`, `delete_tree`)
- Comprehensive implementation for thorough testing
- Has `clear()` method for test cleanup

### Current Usage

**Agent module uses agent version:**
- `src/agent/core.py:248` - imports `RealFileSystem` from `src/agent/file_system`
- `src/agent/__init__.py` - exports `RealFileSystem` and `InMemoryFileSystem`

**Tests use infrastructure version:**
- `tests/helpers.py` - imports from `src/infrastructure`
- `tests/infrastructure/test_file_system.py` - tests infrastructure implementations
- `tests/test_agent_dependency_injection.py` - uses `InMemoryFileSystem` from infrastructure

**Mixed usage creates confusion:**
- Which version should new code use?
- Inconsistent capabilities across the codebase
- Duplicated maintenance burden

## Migration Plan

### Goal

Standardize on **`src/infrastructure`** version because:
1. More complete feature set (binary, glob, delete, list_dir)
2. Better implementation (auto-create dirs, robust path normalization)
3. Already used by tests
4. Better documented and more production-ready

### Migration Steps

#### Phase 1: Audit Current Usage

**Task 1.1:** Find all imports of agent file_system
```bash
grep -r "from.*agent.*file_system import" src/
grep -r "from.*agent import.*FileSystem" src/
```

**Task 1.2:** Identify protocol mismatches
- Document which code uses `read_file/write_file` vs `read_text/write_text`
- Document which code uses `resolve()` expecting `Path` vs `str`

#### Phase 2: Update Agent Protocol Reference

**Task 2.1:** Update `src/agent/protocols.py`
- Change `FileSystemProtocol` to import from infrastructure:
  ```python
  from src.infrastructure.protocols import FileSystemProtocol
  ```
- Remove the duplicate protocol definition (lines 497-619)
- Add deprecation notice if needed

**Task 2.2:** Update agent code to use infrastructure protocol
- Update `src/agent/core.py` to import from infrastructure
- Change any code using `read_file/write_file` to `read_text/write_text`
- Change any code expecting `Path` from `resolve()` to handle `str`

#### Phase 3: Add Missing Method to Infrastructure

**Task 3.1:** Add `join_path` to infrastructure protocol
- The agent protocol has `join_path(*parts: str) -> str`
- Infrastructure protocol should have this utility method
- Add to `FileSystemProtocol` in `src/infrastructure/protocols.py`
- Implement in both `RealFileSystem` and `InMemoryFileSystem`

**Task 3.2:** Consider standardizing `resolve()` return type
- Agent expects `Path`, infrastructure returns `str`
- Options:
  - Keep as `str` (simpler, consistent with protocol using strings)
  - Add `resolve_path()` method that returns `Path`
  - Update agent code to handle `str` (recommended)

#### Phase 4: Migrate Imports

**Task 4.1:** Update all imports in `src/agent/`
```python
# OLD
from .file_system import RealFileSystem, InMemoryFileSystem
from .protocols import FileSystemProtocol

# NEW
from src.infrastructure import RealFileSystem, InMemoryFileSystem
from src.infrastructure.protocols import FileSystemProtocol
```

**Task 4.2:** Update `src/agent/__init__.py` exports
- Stop exporting `RealFileSystem` and `InMemoryFileSystem` from agent
- Or re-export from infrastructure for backward compatibility:
  ```python
  from src.infrastructure import RealFileSystem, InMemoryFileSystem
  ```

#### Phase 5: Delete Duplicate Code

**Task 5.1:** Delete `src/agent/file_system.py`
- Verify all imports updated
- Verify all tests pass
- Remove the file

**Task 5.2:** Remove protocol from `src/agent/protocols.py`
- Delete lines 497-619 (FileSystemProtocol definition)
- Or replace with import/re-export

#### Phase 6: Run All Tests

**Task 6.1:** Run full test suite
```bash
python -m pytest tests/ -v
```

**Task 6.2:** Verify no regressions
- All agent tests pass
- All infrastructure tests pass
- All integration tests pass

#### Phase 7: Update Documentation

**Task 7.1:** Update CLAUDE.md if needed
- Reference infrastructure file system as the standard
- Remove any agent file system references

**Task 7.2:** Update inline documentation
- Update docstrings that reference agent file system
- Add migration notes if backward compatibility maintained

## Risk Analysis

### Low Risk
- Infrastructure implementation is well-tested
- Clear separation of concerns
- No external API changes (internal refactoring only)

### Medium Risk
- Agent code may depend on `read_file/write_file` naming
- Agent code may depend on `resolve()` returning `Path`
- Some code may expect text-only operations

### Mitigation Strategies

**Strategy 1: Backward Compatibility Layer**
Create adapter in `src/agent/file_system.py`:
```python
from src.infrastructure import RealFileSystem as _RealFileSystem
from src.infrastructure import InMemoryFileSystem as _InMemoryFileSystem

class RealFileSystem:
    """Backward compatibility wrapper."""
    def __init__(self):
        self._fs = _RealFileSystem()

    def read_file(self, path: str) -> str:
        return self._fs.read_text(path)

    def write_file(self, path: str, content: str) -> None:
        self._fs.write_text(path, content)

    # ... delegate other methods
```

**Strategy 2: Gradual Migration**
1. Add infrastructure methods to agent implementations
2. Deprecate agent-specific methods
3. Migrate code incrementally
4. Remove deprecated methods after migration

**Strategy 3: Direct Migration (Recommended)**
1. Update all code at once
2. Use find/replace for method name changes
3. Run tests to catch issues
4. Fix any breakage immediately

## Effort Estimate

**Phase 1 (Audit):** 1-2 hours
- Search for all usage
- Document dependencies

**Phase 2 (Protocol Update):** 1 hour
- Update protocol reference
- Update documentation

**Phase 3 (Add Missing Methods):** 2-3 hours
- Implement `join_path`
- Test implementation
- Verify behavior matches agent version

**Phase 4 (Migrate Imports):** 2-3 hours
- Update imports
- Update method calls (read_file -> read_text)
- Handle resolve() return type changes

**Phase 5 (Delete Duplicates):** 1 hour
- Delete files
- Verify nothing broken

**Phase 6 (Testing):** 2-4 hours
- Run all tests
- Fix any regressions
- Verify behavior

**Phase 7 (Documentation):** 1 hour
- Update docs
- Add migration notes

**Total Estimated Effort:** 10-15 hours

## Success Criteria

1. All code uses `src/infrastructure/file_system.py`
2. No duplicate `FileSystemProtocol` definitions
3. All tests pass
4. No behavioral changes (same functionality, different implementation)
5. Code is cleaner and more maintainable
6. Single source of truth for file system abstraction

## Notes

- This is a **pure refactoring** - no new features, just consolidation
- Follows SOLID principles by having single abstraction
- Reduces maintenance burden
- Improves testability by using more robust test implementation
- Sets precedent for handling other duplications in the codebase
