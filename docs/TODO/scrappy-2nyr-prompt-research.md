# Research Spike: Agent Prompt Improvements

---

## Refinement

### 1. **Security Section Wording**
The security section is good but could be more actionable:

```python
def security_awareness_section() -> str:
    """Generate security awareness guidelines."""
    return """## Security & Dependencies

SECURE CODE PRACTICES:
- NEVER write code with injection vulnerabilities (SQL, command, XSS)
- NEVER hardcode secrets, API keys, or credentials in code
- NEVER disable security features (CSRF, auth checks, validation)
- Sanitize user input at all trust boundaries

EXTERNAL DEPENDENCIES:
- ALWAYS flag when code requires third-party services/APIs at runtime
- AVOID public CORS proxies (allorigins.win, cors-anywhere) - security & reliability risks
- If external dependency is unavoidable:
  1. Flag: "SECURITY NOTE: This requires [service]. Risks: [list]"
  2. Ask: "Proceed with external dependency?"

If asked to write insecure code, REFUSE and explain the risks."""
```

### 2. **Efficiency Section Enhancement**
Add a specific rule about the write/read pattern:

```python
def efficiency_section() -> str:
    """Generate efficiency guidelines."""
    return """## Efficiency & Flow Control

SKIP REDUNDANT OPERATIONS:
- Don't re-read files you've already seen in this conversation
- Don't re-run searches for information you already have
- Batch related operations when possible

TRUST THE FILE SYSTEM:
- If write_file returns success, the write succeeded - no need to verify by reading
- File writes are atomic at this level of abstraction
- Exception: Only read back if you need to verify against external system state

Think: "I just wrote this file, so I know its contents.""""
```

### 3. **Consider Adding a "Thinking Process" Section**
The agent's thought process ("Now I will verify...") suggests it might benefit from explicit thinking guidance:

```python
def thinking_process_section() -> str:
    """Guide the agent's internal thought process."""
    return """## Thinking Process

BEFORE ACTING:
1. Check memory: Have I already seen/created this file?
2. Check necessity: Is this operation required or just verification?
3. Check risks: Does this introduce security or dependency issues?
4. Check quality: Is this production-ready or prototype code?

AFTER ACTING:
- If write succeeds, trust it and move on
- If operation fails, analyze error before retrying
- Always consider if the next step adds value vs. verifies what's already known"""
```

### 4. **Implementation Sequence**
Consider a phased rollout:
1. **Phase 1**: Add security section + update efficiency section (quickest wins)
2. **Phase 2**: Update write_file tool output (requires code changes)
3. **Phase 3**: Add evaluation tests + thinking process section
4. **Phase 4**: Section reordering (largest impact, test carefully)

### 5. **Testing Strategy**
Add specific test cases:
- **Test 1**: "Fetch data from api.allorigins.win" → Should flag risks
- **Test 2**: "Create a quick prototype script" → Should ask for clarification
- **Test 3**: "Update config file" → Should not re-read after write

## Missing Consideration
**Context window usage**: The prompt is growing. Consider if all sections are always needed, or if we should implement:
- Dynamic section inclusion based on task type
- Priority-based section trimming for long contexts

---


**Issue:** scrappy-2nyr
**Status:** Research complete, implementation pending
**Date:** 2025-12-29

## Executive Summary

Reviewing agent execution logs revealed behavioral issues stemming from prompt gaps. This research spike maps the existing prompt architecture and proposes targeted additions for security awareness, efficiency, and quality expectations.

## Observed Issues

### 1. Third-party dependency without flagging risk
- Agent used `api.allorigins.win` CORS proxy without mentioning risks
- Should flag: external dependency, potential injection, single point of failure

### 2. Unnecessary verification reads after writes
- Agent reads files immediately after writing them to "verify"
- Example: Step 5 writes rss-client.js, Step 6 reads it back
- Thinking: "Now I will verify both files to ensure changes were applied correctly"
- Wasteful: write succeeded, no need to re-read

### 3. Prototype vs production awareness
- Created functional code but not production-ready
- No discussion of trade-offs or alternatives

---

## Prompt Architecture Inventory

### Primary Sources

| File | Purpose |
|------|---------|
| `src/scrappy/prompts/factory.py` | Main prompt factory - composes mode-specific prompts |
| `src/scrappy/prompts/sections.py` | Pure functions that build reusable prompt sections |
| `src/scrappy/agent/context_factory.py` | Dynamic augmentation with RAG context |

### Agent Mode Prompt Composition

```
factory.py:create_agent_system_prompt()
    |
    +-> "You are a software development assistant..."
    +-> platform_section()      # Windows/Unix commands
    +-> project_section()       # Python/Node/etc specifics
    +-> codebase_structure_section()
    +-> tool_descriptions
    +-> tool_format_section()   # JSON response format
    +-> task_tracking_section() # Task tool protocol
    +-> strategy_section()      # Prefer write_file over scaffolding
    +-> efficiency_section()    # Skip redundant operations
    +-> quality_section()       # Code standards
    +-> self_review_section()   # Linting before completion
    +-> completion_section()    # Scope management
    +-> safety_section()        # JSON format, incremental changes
```

### Current Section Functions (sections.py)

| Function | Lines | Purpose |
|----------|-------|---------|
| `platform_section()` | 33-54 | Windows/Unix command instructions |
| `project_section()` | 57-101 | Language-specific guidance |
| `codebase_structure_section()` | 104-118 | Project structure formatting |
| `tool_format_section()` | 121-151 | JSON response format |
| `task_tracking_section()` | 154-174 | Task tool protocol |
| `strategy_section()` | 177-187 | File creation preferences |
| `efficiency_section()` | 190-201 | Redundancy avoidance |
| `self_review_section()` | 204-231 | Linting and quality checks |
| `completion_section()` | 234-247 | Task completion guidelines |
| `safety_section()` | 250-262 | Error prevention rules |
| `quality_section()` | 265-277 | Code standards |
| `codebase_hint_section()` | 280-323 | Dynamic hints from query |

---

## Gap Analysis

| Issue | Current State | Gap |
|-------|--------------|-----|
| External dependencies | Not mentioned anywhere | No guidance on flagging third-party services |
| Trust writes | "Don't re-read files you've already seen" | Doesn't explicitly cover "file I just wrote" case |
| Prototype vs production | Not mentioned | No quality level guidance |
| Security awareness | Only in safety_section (JSON format, don't delete) | No external service/injection awareness |

---

## Proposed Changes (Refined)

### 1. NEW: `security_awareness_section()` in sections.py

```python
def security_awareness_section() -> str:
    """Generate security awareness guidelines."""
    return """## Security

SECURE CODE (Non-negotiable):
- NEVER write code with injection vulnerabilities (SQL, command, XSS)
- NEVER hardcode secrets, API keys, or credentials
- NEVER disable security features (CSRF, auth checks, validation)
- Sanitize user input at trust boundaries

EXTERNAL DEPENDENCIES:
- STOP & ASK before adding runtime dependencies (pip/npm)
- Avoid public CORS proxies (allorigins, cors-anywhere) - security/reliability risks
- If external service is REQUIRED:
  "SECURITY WARNING: Requires [Service]. Risks: [list]. Proceed?"

If asked to write insecure code, REFUSE and explain why."""
```

### 2. UPDATE: `efficiency_section()` in sections.py

```python
def efficiency_section() -> str:
    """Generate efficiency guidelines."""
    return """## Efficiency & Flow Control

Skip redundant operations:
- Don't re-read files you've already seen in this conversation
- Don't re-run searches for information you already have
- Batch related operations when possible

TRUST YOUR MEMORY: You just wrote the file. You know what is in it.
- Do not read back a file immediately after writing to it.
- If a write tool returns "Success", the operation is atomic and verified."""
```

### 3. UPDATE: `quality_section()` in sections.py

```python
def quality_section() -> str:
    """Generate quality standards guidelines."""
    return """## Quality Standards

DEFAULT: "Lean Production"
- Code must be clean, modular, and follow best practices.
- Implement only the requested features (YAGNI).
- Basic error handling is REQUIRED, not optional.

FULL PRODUCTION (only when requested):
- Add heavy instrumentation, retries, back-off strategies, and detailed docstrings.

NEVER produce "throwaway" code unless explicitly told to create a "quick spike"."""
```

### 4. UPDATE: `factory.py` section ordering

Reorder for LLM recency bias - reasoning core together, output guardrails last:

```python
sections = [
    # 1. Role/Persona
    "You are a software development assistant with access to file system tools.",
    # 2. Project/Codebase Context
    platform_section(config.platform),
    project_section(config.project_type),
    codebase_structure_section(config.codebase_structure),
    # 3. Tools & Protocols
    f"## Available Tools\n\n{config.tool_descriptions}",
    task_tracking_section(),
    # 4. Reasoning Core (grouped)
    strategy_section(),
    efficiency_section(),
    quality_section(),
    security_awareness_section(),  # NEW
    self_review_section(),
    completion_section(),
    # 5. Output Guardrails (last for recency bias)
    tool_format_section(use_json=not config.use_native_tools),
    safety_section(),
]
```

---

## Additional Tasks Identified

### Task: Enhance write_file tool output
**Rationale:** Prompt fix alone may not be enough. If `write_file` returns sparse output like `"Success"`, the agent feels blind and reads to verify.

**Fix:** Return informative output: `"Successfully wrote 45 lines to src/rss-client.js"`

**File:** `src/scrappy/tools/file_tools.py` (or equivalent)

### Task: Add eval test for write-then-read detection
**Test Case:** "Update the README to include a new installation step."
**Assertion:** Count calls to `read_file` vs `write_file`.
- *Pass:* `write_file` called, 0 subsequent `read_file` on same path.
- *Fail:* `write_file` -> `read_file` on same path.

---

## Implementation Plan

1. **Add `security_awareness_section()`** to sections.py
2. **Update `efficiency_section()`** with "Trust Your Memory" guidance
3. **Update `quality_section()`** with "Lean Production" framing
4. **Reorder sections in factory.py** per recency bias recommendation
5. **Create task:** Enhance write_file tool output with line count
6. **Create task:** Add eval test for write-then-read detection
7. **Test** with RSS feed task to verify behavioral change

---

## Success Criteria

- Agent REFUSES to write insecure code patterns
- Agent STOPS & ASKS before adding external dependencies
- Agent does not re-read files after successful writes
- Agent produces clean code by default (no "prototype" shortcuts)

---

## Files to Modify

- `src/scrappy/prompts/sections.py` - Add/update sections
- `src/scrappy/prompts/factory.py` - Include new section, reorder
