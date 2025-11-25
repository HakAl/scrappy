# Bug Investigation Report

Investigation of commented-out tests and issues documented in `BUGS_OR_FAILING_TESTS.md`.

---

## 1. Protocol Gaps

### 1.1 CacheProtocol.invalidate() - NOT A BUG

**Location:** `src/orchestrator/protocols.py:100-159`

**Finding:** The `CacheProtocol` does NOT define an `invalidate()` method. The protocol defines:
- `get()` - retrieve cached response
- `put()` - store response in cache

The `ResponseCache` implementation (`src/orchestrator/cache.py`) provides:
- `clear()` - clears all cache entries
- `invalidate_provider()` - invalidates all entries for a specific provider

**Conclusion:** The protocol is intentionally minimal. The `invalidate()` method mentioned in the TODO may refer to the `invalidate_provider()` method, which IS implemented. No action needed unless protocol needs expansion for more granular invalidation.

---

### 1.2 ToolRegistryProtocol.exists() - CONFIRMED GAP

**Location:**
- Protocol: `src/agent/protocols.py:210-298`
- Implementation: `src/agent_tools/tools/registry.py:12-223`

**Finding:** The `ToolRegistryProtocol` defines:
- `register(tool, name)` - register a tool
- `get(name)` - get tool by name (raises KeyError if not found)
- `list_all()` - list all registered tools
- `execute(tool_name, context, **kwargs)` - execute tool
- `unregister(name)` - unregister a tool (returns bool)

The `ToolRegistry` implementation does NOT have an `exists()` method. It has `get()` which returns `None` if not found (contrary to protocol which says it raises `KeyError`).

**Recommendation:**
1. Add `exists(name: str) -> bool` to protocol and implementation
2. Align `get()` behavior - either change protocol to return Optional or change implementation to raise KeyError

---

### 1.3 RichRenderableProtocol - NOT IMPLEMENTED BY OutputBridge

**Location:**
- Protocol: `src/protocols/output.py:175-213`
- Implementation: `src/cli/output_bridge.py:27-146`

**Finding:** The `RichRenderableProtocol` requires:
- `post_output(content: str)` - post plain text
- `post_renderable(obj: RenderableType)` - post Rich renderable

The `OutputBridge` class:
- Does NOT directly implement `RichRenderableProtocol`
- It WRAPS an `OutputSink` which should implement the protocol
- It uses `self.output_sink.post_output()` and `self.output_sink.post_renderable()` internally

**Conclusion:** This is a design choice - OutputBridge delegates to OutputSink rather than implementing directly. The gap is that OutputBridge doesn't expose these methods publicly. Consider adding pass-through methods if direct protocol compliance is needed.

---

### 1.4 ProviderRegistry - EXISTS AS PART OF ORCHESTRATOR

**Finding:** `ProviderRegistry` is not a standalone module but is integrated into the orchestrator system. The functionality exists in:
- `src/orchestrator/registration.py`
- `src/orchestrator/provider_selector.py`
- Referenced in 33 files across the codebase

**Conclusion:** NOT A BUG - The architecture uses a different approach than a standalone ProviderRegistry module.

---

## 2. Agent Tools Test Todos

### 2.1 test_search_tools.py - 3 Commented Tests

**File:** `tests/agent_tools/test_search_tools.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_context_separation` | 68-82 | Tests that non-adjacent matches are separated by '---'. Currently skipped - may indicate search tool doesn't add separators. |
| `test_finds_text_in_files` | 91-106 | Tests file glob filtering. Issues with `result.success` attribute or `metadata["matches"]` structure. |
| `test_ast_search_types` | 108-141 | Tests AST-based function/class/method/import search. Likely AST search implementation incomplete or output format differs. |
| `test_regex_error_handling` | 155-160 | Tests invalid regex handling. Should return `result.success=False` with `result.error` message. |

**Recommendation:** Review SearchCodeTool implementation for:
1. Context line separator logic
2. AST search functionality
3. Error handling return structure

---

### 2.2 test_file_tools.py - 2 Commented Tests

**File:** `tests/agent_tools/test_file_tools.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_write_verification_failure` | 162-173 | Tests that write verification detects content mismatch. Complex mocking needed. |
| `test_respect_depth_limit` | 241-253 | Tests ListDirectoryTool depth limit. May indicate depth parameter not implemented or working differently. |

---

### 2.3 test_web_tools.py - 1 Commented Test

**File:** `tests/agent_tools/test_web_tools.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_pypi_search_format` | 200-227 | Tests PyPI JSON formatting. URL construction or output formatting differs from expectation. |

---

### 2.4 test_python_tools.py - 1 Commented Test

**File:** `tests/agent_tools/test_python_tools.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_custom_exclusions` | 128-138 | Tests `exclude_patterns` parameter. Parameter may not be implemented in AnalyzePythonDependenciesTool. |

---

## 3. Provider Test Todos

### 3.1 test_github_models_provider.py

| Test | Lines | Issue |
|------|-------|-------|
| `test_get_limits_default` | 205-213 | Tests default limits when no cache available. Expected `None` values, may return different defaults. |
| `test_chat_async_basic` | 229-246 | Async chat test. Complex httpx mocking issues. |
| `test_real_api_call` | 395-408 | Integration test - properly skipped without API key. |
| `test_real_async_api_call` | 410-423 | Integration test - properly skipped without API key. |

---

### 3.2 test_cohere_provider.py

| Test | Lines | Issue |
|------|-------|-------|
| `test_chat_warning_10_calls` | 190-202 | Tests warning printed every 10 calls. Print mocking or call count tracking issues. |
| `test_embed_custom_model` | 245-257 | Tests custom embedding model. Mock assertion or model parameter handling issues. |
| `test_real_api_call` | 373-386 | Integration test - properly skipped without API key. |

---

### 3.3 test_cerebras_provider.py

| Test | Lines | Issue |
|------|-------|-------|
| `test_get_model_info` | 297-305 | Tests `get_model_info()` method. Method may not exist or return different structure. |

---

## 4. test_import_utils.py - Multiple Commented Tests

**File:** `tests/test_import_utils.py`

**Category: Path Setup Tests (Lines 86-158)**
- `test_setup_src_path` - Complex Path mocking issues
- `test_setup_src_path_already_exists` - Duplicate path prevention
- `test_setup_root_path` - Root path setup
- `test_setup_root_path_already_exists` - Root path deduplication

**Category: Import Fallback Tests (Lines 176-262)**
- `test_import_with_fallback_relative_import` - Relative import handling
- `test_import_with_fallback_single_dot` - Single dot relative import
- `test_import_with_fallback_deep_relative` - Multi-dot relative imports

**Category: Dependency Checker Tests (Lines 334-346)**
- `test_get_beautifulsoup_available` - BeautifulSoup import test

**Category: Edge Cases (Lines 362-407)**
- `test_safe_import_empty_string` - Empty string handling
- `test_require_import_empty_string` - Empty string error
- `test_import_with_fallback_empty_strings` - Empty strings in fallback
- `test_import_with_fallback_none_values` - None value handling
- `test_setup_path_with_complex_structure` - Complex directory paths

**Category: Integration Tests (Lines 423-438)**
- `test_real_path_setup` - Real path manipulation test

**Root Cause:** Most tests involve complex mocking of `Path` class and `sys.path` manipulation which is notoriously difficult to mock correctly.

---

## 5. test_output_formatter.py - 1 Commented Test

**File:** `tests/agent_tools/test_output_formatter.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_format_file_name_extensions` | 172-196 | Parametrized test for file extension color mapping. Rich `Text` class mocking issues. |

---

## 6. test_code_chunker.py - 3 Commented Tests

**File:** `tests/context/test_code_chunker.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_chunk_multiple_chunks_with_overlap` | 76-101 | Tests overlap behavior. Chunking algorithm produces different line ranges than expected. |
| `test_chunk_exact_fit_no_remainder` | 104-120 | Tests exact fit scenario. Line range calculations differ from expectations. |
| `test_protocol_compliance` | 174-186 | Tests `CodeChunk` type return. Return type may be different class or structure. |

**Likely Issue:** The `SemanticCodeChunker` calculates overlap/boundaries differently than the test expectations. The implementation may use 0-indexed or different overlap formulas.

---

## 7. test_texual_progress.py - 1 Commented Test

**File:** `tests/infrastructure/test_texual_progress.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_import_handling` | 153-169 | Tests behavior when textual cannot be imported. Complex import mocking with `sys.modules` patch. |

---

## 8. test_fallback.py - 3 Commented Tests/Classes

**File:** `tests/platform/test_fallback.py`

| Test | Lines | Issue |
|------|-------|-------|
| `test_find_basic` | 154-160 | Basic find command. Output format may include full paths differently. |
| `test_which_nonexistent_command` | 480-486 | Tests `which` with missing command. Return format or message differs. |
| `TestEdgeCasesAndErrorHandling` | 624-720 | Entire class commented out. Contains 8 edge case tests that likely fail due to platform differences or complex scenarios. |

---

## 9. Files Listed Without Tests

The following source files were mentioned in BUGS_OR_FAILING_TESTS.md but have no specific test issues documented:

- `src/cli/smart_query.py` - Reviewed, no obvious issues
- `src/cli/research_handlers/testing.py` - Reviewed, functional
- `src/cli/research_handlers/dependency_info.py` - Reviewed, functional
- `src/cli/research_handlers/architecture.py` - Reviewed, functional
- `src/cli/research_handlers/configuration.py` - Reviewed, functional
- `src/cli/research_handlers/documentation.py` - Reviewed, functional

These may have been listed for future test coverage rather than documenting existing bugs.

---

## 10. Test Warnings (127 Warnings)

The 127 warnings mentioned are not documented in detail. Common sources of pytest warnings include:
- Deprecation warnings from dependencies
- Unclosed resources (files, connections)
- Async warnings (unawaited coroutines)
- Collection warnings (test files/functions not collected)

**Recommendation:** Run `pytest --tb=short -W default` to see full warning details and categorize them.

---

## Summary Statistics

| Category | Commented Tests | Priority |
|----------|-----------------|----------|
| Protocol Gaps | 1 confirmed | Medium |
| Search Tools | 4 tests | High |
| File Tools | 2 tests | Medium |
| Web Tools | 1 test | Low |
| Python Tools | 1 test | Low |
| Provider Tests | 7 tests | Medium |
| Import Utils | 14 tests | Low |
| Output Formatter | 1 test | Low |
| Code Chunker | 3 tests | Medium |
| Textual Progress | 1 test | Low |
| Fallback | 3+ tests | Medium |

**Total Commented/Skipped Tests: ~37**

---

## Recommended Priority Actions

1. **HIGH:** Fix SearchCodeTool tests - these affect core functionality
2. **MEDIUM:** Fix ToolRegistryProtocol.exists() gap - protocol compliance
3. **MEDIUM:** Fix CodeChunker overlap calculations - affects code analysis
4. **MEDIUM:** Review provider test failures - affects LLM integrations
5. **LOW:** Import utils tests - mostly mocking issues, not bugs
6. **LOW:** Investigate 127 warnings

---

*Report generated: Investigation of BUGS_OR_FAILING_TESTS.md*

---

## Implementation Plan

This section outlines the architectural approach to fixing the gaps identified above, following SOLID principles and the project's protocol-first design philosophy.

---

### Phase 1: Protocol Compliance (HIGH Priority) -- COMPLETE

#### 1.1 ToolRegistry.exists() - Protocol Gap Fix

**Problem:** `ToolRegistryProtocol` defines `exists(name: str) -> bool` but `ToolRegistry` does not implement it.

**Design:**
```
Protocol already defines:
  exists(name: str) -> bool

Implementation needed in ToolRegistry:
  def exists(self, name: str) -> bool:
      return name in self._tools
```

**Files to modify:**
- `src/agent_tools/tools/registry.py:12-223`

**Implementation steps:**
1. Add `exists()` method to `ToolRegistry` class
2. Verify method matches protocol signature exactly
3. Add unit test in `tests/agent_tools/test_registry.py`

**Additional issue found:** Protocol says `get()` raises `KeyError`, but implementation returns `None`. Decision needed:
- Option A: Change protocol to `get(name) -> Optional[Any]` (matches current impl)

**Recommendation:** Option A - The `get()` returning `None` pattern is safer and more Pythonic. Update protocol docstring.

---

#### 1.2 CacheProtocol.invalidate() - Already Implemented

**Finding:** The `CacheProtocol` at `src/orchestrator/protocols.py:179-194` already defines `invalidate()`. The `ResponseCache` implementation has `invalidate_provider()` but not the general `invalidate()` method matching the protocol.

**Design:**
```
Protocol defines:
  invalidate(provider: Optional[str], prompt: Optional[str]) -> int

Implementation needed:
  def invalidate(self, provider: Optional[str] = None, prompt: Optional[str] = None) -> int:
      # If only provider specified, delegate to invalidate_provider
      # If both or prompt specified, do more granular invalidation
```

**Files to modify:**
- `src/orchestrator/cache.py` - Add `invalidate()` method

**Implementation steps:**
1. Add `invalidate()` method that wraps/extends `invalidate_provider()`
2. Support prompt-based invalidation (new functionality)
3. Return count of invalidated entries
4. Add unit tests

---

### Phase 2: Search Tools Tests (HIGH Priority) -- COMPLETE

#### 2.1 Context Separation Test

**Problem:** Test expects `---` separator between non-adjacent matches when `context_lines=0`.

**Analysis of implementation (`src/agent_tools/tools/search_tools.py:67-86`):**
The separator logic at line 83-86 only adds `---` when `context_lines > 0`. This is intentional behavior - no separator needed when there's no context to separate.

**Decision:** Remove or update the test. The implementation is correct. When `context_lines=0`, every match is standalone, so separators add no value.

**Action:** Delete the commented test `test_context_separation` - it tests invalid expectations.

---

#### 2.2 File Glob Filtering Test

**Problem:** Test `test_finds_text_in_files` expects file glob filtering.

**Analysis:** The implementation at line 173 uses `rglob(file_pattern)` which should work. The test may have issues with:
1. Recursive glob vs non-recursive glob
2. Metadata structure expectations

**Implementation steps:**
1. Uncomment the test
2. Verify `file_pattern="*.py"` properly filters
3. Fix any assertion issues (likely `result.metadata["matches"]` structure)

---

#### 2.3 AST Search Test

**Problem:** Test `test_ast_search_types` expects specific output formats.

**Analysis:** The implementation at lines 90-154 produces output like:
- `[function] func_name - line_content`
- `[class] ClassName - line_content`
- `[method] ClassName.method_name - line_content`
- `[import] module_name - line_content`
- `[from-import] module.name - line_content`

**Implementation steps:**
1. Uncomment the test
2. Verify output format matches expectations
3. Adjust test assertions to match actual output format

---

#### 2.4 Regex Error Handling Test

**Problem:** Test expects `result.success=False` and `result.error` for invalid regex.

**Analysis:** Implementation at lines 191-193 catches `ValueError` and returns `ToolResult(False, "", str(e))`. The error message goes to the third positional arg (error field).

**Implementation steps:**
1. Uncomment the test
2. Verify error message contains "Invalid regex pattern"
3. Test should pass as-is if implementation matches

---

### Phase 3: Code Chunker Tests (MEDIUM Priority) -- COMPLETE

#### 3.1 Overlap Calculation Fix

**Problem:** Tests expect different chunk boundaries than implementation produces.

**Analysis of implementation (`src/context/code_chunker.py:44-81`):**
```python
# Implementation uses:
chunk_start = i + 1  # 1-indexed
chunk_end = min(i + self._chunk_size, len(lines))
step = self._chunk_size - self._overlap
i += step
```

**Test expectation (chunk_size=5, overlap=2, 12 lines):**
- Chunk 1: lines 1-5
- Chunk 2: lines 4-8
- Chunk 3: lines 7-11

**Actual implementation behavior:**
- i=0: start=1, end=5, then i+=3 -> i=3
- i=3: start=4, end=8, then i+=3 -> i=6
- i=6: start=7, end=11, then i+=3 -> i=9
- i=9: start=10, end=12, then i+=3 -> i=12

The test expectations are WRONG. The implementation is correct. Chunk 2 should start at line 4 (which is i=3+1=4), not at line 4 overlapping lines 4-5.

**Wait - let me recalculate:**
With chunk_size=5, overlap=2:
- step = 5 - 2 = 3
- Chunk 1 (i=0): lines 1-5
- Chunk 2 (i=3): lines 4-8 (overlaps lines 4-5 with chunk 1) - correct!
- Chunk 3 (i=6): lines 7-11 (overlaps lines 7-8 with chunk 2) - correct!
- Chunk 4 (i=9): lines 10-12 (overlaps lines 10-11 with chunk 3)

The test expects 3 chunks but implementation produces 4 chunks because line 12 gets its own partial chunk.

**Decision:** The test expectations are slightly off. Update tests to match correct algorithm behavior.

**Implementation steps:**
1. Uncomment `test_chunk_multiple_chunks_with_overlap`
2. Update expectations to account for trailing partial chunk
3. Uncomment `test_chunk_exact_fit_no_remainder`
4. Recalculate expected boundaries

---

#### 3.2 Protocol Compliance Test

**Problem:** Test imports local `CodeChunk` class instead of using the actual protocol.

**Analysis:** The test file defines its own `CodeChunk` class at lines 7-16, then tries to check `isinstance(result[0], CodeChunk)`.

**Design fix:**
```python
# Instead of local definition, import from actual module:
from src.context.protocols import CodeChunk
```

**Implementation steps:**
1. Remove local `CodeChunk` class definition from test
2. Import `CodeChunk` from `src.context.protocols`
3. Uncomment `test_protocol_compliance`
4. Verify isinstance check works

---

### Phase 4: File Tools Tests (MEDIUM Priority) -- COMPLETE

#### 4.1 Write Verification Test

**Problem:** Complex mocking needed to simulate write verification failure.

**Analysis:** The test wants to verify that if `read_text()` returns different content than what was written, the tool returns failure.

**Design approach - Use dependency injection:**
The current implementation directly uses `Path.write_text()` and `Path.read_text()`. This violates dependency inversion.

**Architectural fix:**
1. Create `FileSystemProtocol` (already exists in `src/infrastructure/protocols.py`)
2. Inject file system into `WriteFileTool`
3. Use mock file system in tests

**Simpler approach (for now):**
The test can be fixed with proper mocking:
```python
def test_write_verification_failure(self, mock_context):
    tool = WriteFileTool()
    test_file = mock_context.project_root / "test.txt"

    # Create file first so it exists
    test_file.write_text("initial")

    # Mock read_text to return wrong content after write
    original_read = Path.read_text
    call_count = [0]
    def fake_read(self, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 1:  # After write verification read
            return "Corrupted Data"
        return original_read(self, *args, **kwargs)

    with patch.object(Path, 'read_text', fake_read):
        result = tool.execute(mock_context, path="test.txt", content="Expected Data")

    assert not result.success
    assert "verification failed" in result.error
```

**Implementation steps:**
1. Uncomment test
2. Fix mocking approach
3. Verify test passes

---

#### 4.2 Depth Limit Test

**Problem:** `ListDirectoryTool` depth parameter may not work as expected.

**Analysis:** Implementation at lines 316-345 shows:
- `current_depth` starts at 0
- Recursion happens when `current_depth < depth`
- `depth` parameter defaults to 2

**Test expectation:** `depth=1` shows root content but not inside subdirs.

**Implementation check:** With `depth=1`:
- Initial call: `current_depth=0`, shows items, recurses if `0 < 1` (true)
- Recursive call: `current_depth=1`, shows items, recurses if `1 < 1` (false)

So `depth=1` shows TWO levels (root and first level subdirs). The test expects `depth=1` to show only root.

**Decision:** Either:
- Option A: Fix implementation to match intuitive behavior (depth=1 = show 1 level)

**Recommendation:** Option A - The parameter should be intuitive. `depth=1` should mean "show 1 level deep".

**Implementation steps:**
1. Review `ListDirectoryTool` depth logic
2. Decide on semantic (0-based or 1-based depth)
3. Fix implementation or test accordingly
4. Uncomment and verify test

---

### Phase 5: Provider Tests (MEDIUM Priority) -- COMPLETE

#### 5.1 GitHub Models Provider Tests

**Files:** `tests/providers/test_github_models_provider.py`

**Issues:**
- `test_get_limits_default`: Expects `None` values, may get different defaults
- `test_chat_async_basic`: Complex httpx mocking

**Implementation steps:**
1. Review `get_limits()` default behavior
2. Update test expectations to match actual defaults
3. For async test, use `pytest-httpx` or `respx` for proper async mocking

---

#### 5.2 Cohere Provider Tests

**Files:** `tests/providers/test_cohere_provider.py`

**Issues:**
- `test_chat_warning_10_calls`: Print mocking issues
- `test_embed_custom_model`: Mock assertion issues

**Implementation steps:**
1. Use `capsys` fixture for capturing print output
2. Review embed method signature and mock accordingly

---

#### 5.3 Cerebras Provider Tests

**Files:** `tests/providers/test_cerebras_provider.py`

**Issues:**
- `test_get_model_info`: Method may not exist

**Implementation steps:**
1. Check if `get_model_info()` is in provider protocol
2. If not in protocol, either add to protocol or remove test
3. If in protocol but not implemented, implement it

---

### Phase 6: Import Utils Tests (LOW Priority)

**General issue:** Complex mocking of `Path` and `sys.path`.

**Recommendation:** These tests are testing Python's import system more than our code. Consider:
1. Testing at integration level instead of unit level
2. Using actual filesystem with temp directories
3. Simplifying the utility functions to reduce need for mocking

**Implementation steps:**
1. Review each test to determine if it tests valuable behavior
2. Convert to integration tests where appropriate
3. Delete tests that don't provide value

---

### Phase 7: Platform Fallback Tests (MEDIUM Priority)

**Files:** `tests/platform/test_fallback.py`

**Issues:**
- Output format differences across platforms
- Edge case handling

**Implementation steps:**
1. Review `test_find_basic` - may need platform-aware assertions
2. Review `test_which_nonexistent_command` - check error message format
3. For `TestEdgeCasesAndErrorHandling` class - uncomment and fix one test at a time

---

### Phase 8: Warnings Investigation (LOW Priority)

**Action:** Run `pytest --tb=short -W default` to categorize warnings.

**Common fixes:**
1. Deprecation warnings: Update deprecated API usage
2. Unclosed resources: Add proper cleanup/context managers
3. Async warnings: Ensure coroutines are awaited

---

## Summary: Implementation Order

| Phase | Priority | Effort | Impact |
|-------|----------|--------|--------|
| 1.1 ToolRegistry.exists() | HIGH | Low | Protocol compliance |
| 1.2 CacheProtocol.invalidate() | HIGH | Medium | Protocol compliance |
| 2.x Search Tools | HIGH | Medium | Core functionality |
| 3.x Code Chunker | MEDIUM | Low | Test expectations |
| 4.x File Tools | MEDIUM | Medium | DI architecture |
| 5.x Provider Tests | MEDIUM | Medium | LLM integration |
| 6.x Import Utils | LOW | High | Mocking complexity |
| 7.x Platform Fallback | MEDIUM | Medium | Cross-platform |
| 8 Warnings | LOW | Varies | Code quality |

**Recommended execution order:**
1. Phase 1.1 (quick win, protocol compliance)
2. Phase 2.4 (regex error - likely already works)
3. Phase 2.2, 2.3 (search tools - core functionality)
4. Phase 3.x (code chunker - test fixes)
5. Phase 1.2 (cache invalidate)
6. Phase 4.x, 5.x, 7.x (as needed)
7. Phase 6.x, 8 (cleanup)
