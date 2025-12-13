# Phase 5: Degraded Mode Awareness

**Goal:** Agent acknowledges when operating without full semantic search.

**Approach:** Track indexing state, inject awareness into prompts.

---

## Current State

- `CodebaseContext.is_semantic_search_ready()` already exists (line 401)
- `SemanticSearchManager.is_ready()` returns True when model loaded and indexed
- ResearchExecutor does NOT check this status currently

---

## Changes Required

### 1. Add `semantic_available` to ResearchPromptConfig

**File:** `src/scrappy/prompts/protocols.py`

```python
@dataclass(frozen=True)
class ResearchPromptConfig:
    """Configuration for research mode - tools depend on subtype."""

    subtype: ResearchSubtype
    tool_descriptions: Optional[str] = None
    context_summary: Optional[str] = None
    extracted_files: tuple[str, ...] = ()
    extracted_directories: tuple[str, ...] = ()
    matched_project_files: tuple[str, ...] = ()
    matched_file_contents: tuple[tuple[str, str], ...] = ()
    semantic_available: bool = True  # NEW: False during indexing gap
```

### 2. Inject degraded mode caveat in prompt factory

**File:** `src/scrappy/prompts/factory.py`

In `create_research_system_prompt()` or `create_research_user_prompt()`:

```python
def create_research_system_prompt(self, config: ResearchPromptConfig) -> str:
    sections = [...]

    # Add degraded mode warning if semantic search unavailable
    if not config.semantic_available:
        sections.append(DEGRADED_MODE_SECTION)

    return "\n\n".join(sections)
```

### 3. Add degraded mode prompt section

**File:** `src/scrappy/prompts/sections.py`

```python
DEGRADED_MODE_SECTION = """
## Limited Search Mode

Semantic search is still initializing. Your search results are based on:
- Filename matching only
- No content-based similarity

If the user's question requires deep code understanding, acknowledge this limitation:
"I'm still indexing the codebase. Here's what I found based on filenames - I may have better results in a moment."
"""
```

### 4. Check semantic status in ResearchExecutor

**File:** `src/scrappy/task_router/strategies/research_executor.py`

```python
def _execute_codebase_research(self, task, context_summary, start_time, matched_files):
    # Check if semantic search is available
    semantic_available = self._is_semantic_ready()

    config = ResearchPromptConfig(
        subtype=PromptResearchSubtype.CODEBASE,
        tool_descriptions=self._tool_bundle.get_tool_descriptions(),
        context_summary=context_summary,
        matched_project_files=matched_files,
        semantic_available=semantic_available,  # NEW
    )
    # ...

def _is_semantic_ready(self) -> bool:
    """Check if semantic search is available."""
    try:
        context = self.orchestrator.context
        if context and hasattr(context, 'is_semantic_search_ready'):
            return context.is_semantic_search_ready()
    except Exception:
        pass
    return False
```

---

## Files to Modify

| File | Change |
|------|--------|
| `src/scrappy/prompts/protocols.py` | Add `semantic_available` field |
| `src/scrappy/prompts/sections.py` | Add `DEGRADED_MODE_SECTION` |
| `src/scrappy/prompts/factory.py` | Inject section when degraded |
| `src/scrappy/task_router/strategies/research_executor.py` | Check status, pass to config |

---

## Tests

```python
def test_degraded_mode_detected_during_indexing():
    """Config has semantic_available=False when not ready."""
    context = Mock()
    context.is_semantic_search_ready.return_value = False
    # ... verify config.semantic_available == False

def test_prompt_includes_degraded_caveat():
    """System prompt includes limitation warning when degraded."""
    config = ResearchPromptConfig(
        subtype=ResearchSubtype.CODEBASE,
        semantic_available=False
    )
    prompt = factory.create_research_system_prompt(config)
    assert "still indexing" in prompt.lower()

def test_no_caveat_when_semantic_ready():
    """No warning when semantic search is ready."""
    config = ResearchPromptConfig(
        subtype=ResearchSubtype.CODEBASE,
        semantic_available=True
    )
    prompt = factory.create_research_system_prompt(config)
    assert "still indexing" not in prompt.lower()
```

---

## Success Criteria

- [ ] Agent knows when semantic search unavailable
- [ ] Codebase research prompts include caveat during indexing gap
- [ ] General research unaffected (doesn't need semantic search)
- [ ] No caveat once indexing complete

---

## Optional Future Enhancement

Re-offer to search after indexing completes:
- Track queries made during degraded mode
- When indexing completes, notify: "Indexing complete. Want me to search again?"
- Requires conversation state tracking (out of scope for Phase 5)
