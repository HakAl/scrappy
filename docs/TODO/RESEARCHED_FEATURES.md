Feature Requests / Enhancements

### 4.1 User-Facing Configuration for Semantic Search
**Status:** NOT IMPLEMENTED
**Impact:** Medium - power users want control

**Problem:** Configuration is only programmatic via `SemanticIndexConfig`. No user-facing config file.

**Solution:** Add config file support (e.g., `.scrappy/config.yaml`) for semantic search settings.

---

### 4.2 Diff Preview
**Status:** NOT IMPLEMENTED
**Impact:** Medium - helpful for reviewing changes

**Solution:** Show diff preview before applying file changes.

---

### 4.3 Streaming Responses
**Status:** NOT IMPLEMENTED
**Impact:** Medium - better UX for long responses

**Problem:** Token-by-token generation would improve perceived responsiveness.

**Solution:** Implement streaming for LLM responses.

---

### 4.4 Structured Output Validation
**Status:** NOT IMPLEMENTED
**Impact:** Medium - reliability improvement

**Problem:** LLM responses not validated against schemas.

**Solution:** Add Pydantic schemas for LLM response validation.

---

### 4.5 Skip Logic for Simple Tasks
**Status:** NOT IMPLEMENTED
**Impact:** Low-Medium - performance optimization
**Location:** `src/orchestrator/task_executor.py`

**Problem:** Simple tasks go through full planning flow unnecessarily.

**Solution:**
```python
if complexity_score <= 3:
    return [{"step": "execute", "description": task, "provider_type": "fast"}]
```
Update planning prompt: "For simple tasks, return 1-2 steps maximum."

---

### 4.6 Configuration Consolidation
**Status:** NOT IMPLEMENTED
**Impact:** Low-Medium - code quality

**Problem:** Thresholds/settings scattered across codebase.

**Solution:** Create `RouterConfig` dataclass for all thresholds/settings. Allow runtime/file-based pattern weight adjustment.

---

### 4.7 Semantic LLM Classification
**Status:** NOT IMPLEMENTED
**Impact:** Low-Medium - accuracy improvement

**Problem:** Pattern matching can be fragile.

**Solution:** Add LLM-augmented classification for disambiguation, intent clarification for ambiguous cases.

---