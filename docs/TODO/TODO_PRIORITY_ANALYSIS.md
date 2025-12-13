# Feature Priority Analysis

## Executive Summary

After reviewing all TODO documents, here is my analysis organized by **impact vs effort** and **dependencies**.

---

### 2. New Tools (NEW_TOOLS.md)

**Why High Priority:** Immediate user-facing value. Tools are the "hands" of your agent.

**Prioritized Tool List:**

| Tool | Value | Effort | Do It? |
|------|-------|--------|--------|
| Test Runner Tool | Very High | Low | YES - core loop needs this |
| TODO Tool | High | Low | YES - task tracking essential |
| Parallel tool execution | High | Medium | YES - perf multiplier |
| Semantic Code Search | Medium | High | MAYBE - nice but not blocking |
| Database Query Tool | Medium | Medium | DEFER - niche use case |
| Dependency Analysis | Low | Medium | DEFER - can use CLI tools |

**Start with:** Test Runner + TODO Tool. These directly enable the TDD Loop feature.

**Effort:** Low-Medium per tool
**Impact:** High (directly improves UX)

---

## Tier 2: Medium Priority (After Foundation)

### 3. Judge/Magistrate Pattern (JUDGE.md)

**Why Medium:** Valuable for quality, but needs clean orchestrator first.

**The idea is sound:** Use a cheap reasoning model (DeepSeek R1 Distill / Qwen 2.5 Coder 7B) as a strict reviewer to catch "lazy coding" before it hits disk.

**Dependencies:**
- Requires clean orchestrator to wire in inspection step
- Needs LiteLLM integration for easy model switching

**Recommendation:** Implement AFTER god class refactor and LiteLLM integration. The architecture in JUDGE.md is well-defined and ready to implement.

**Effort:** Medium
**Impact:** Medium-High (quality improvement, cost savings)

---

### 4. LiteLLM Integration (LITELLM.md)

**Why Medium:** Infrastructure improvement, not user-facing.

**The doc is correct:** Your router is the "brain" (cognitive routing), LiteLLM is the "muscle" (connectivity, retries, fallbacks).

**What to do:**
- Keep your routing logic
- Replace raw API calls with LiteLLM `completion()` calls
- Gain: automatic retries, fallbacks, unified interface

**Dependencies:**
- Cleaner if orchestrator is refactored first
- Enables easier Judge implementation

**Effort:** Medium
**Impact:** Medium (reliability improvement)

---

### 5. TDD Loop (TDD_LOOP.md)

**Why Medium:** Powerful self-healing capability, but complex.

**The architecture is solid:**
1. Generate test first (smart model)
2. Generate implementation (cheap model)
3. Run tests, capture stderr
4. Feed errors back to model (reflexion)
5. Escalate to smart model after N failures

**Dependencies:**
- Needs Test Runner Tool (Tier 1)
- Needs Judge pattern for lazy-code detection
- Needs clean orchestrator to wire the loop

**Recommendation:** This is a "capstone" feature. Do it after:
1. God class refactor
2. Test Runner Tool
3. Judge/Magistrate

**Effort:** High
**Impact:** Very High (autonomous coding capability)

---

## Tier 3: Lower Priority (Nice to Have)

### 6. Seamless Escalation (SEAMLESS_ESCALATION.md)

**Why Lower:** UX polish, not core capability.

**The idea:** Auto-detect complex tasks and trigger planning mode without user having to type `/agent`.

**Assessment:**
- Nice UX improvement
- Not blocking any other features
- Can be added incrementally

**Recommendation:** Defer. Keep `/agent` as manual override. Add auto-escalation later when core features are solid.

**Effort:** Medium
**Impact:** Low-Medium (UX polish)

---

### 7. Gym / Model-Based Evaluation (GYM.md)

**Why Lower:** Meta-tooling, not product feature.

**The idea is fun:** Use AI to simulate users (personas like "Junior Dev", "Micromanager", "Chaos Monkey") and benchmark your agent.

**Assessment:**
- Great for validation and bragging rights
- Not necessary for core functionality
- "Dogfooding loop" (Scrappy fixing itself) is aspirational

**Recommendation:** Defer to "polish" phase. Focus on making Scrappy work well before measuring how well it works.

**Effort:** High
**Impact:** Low (testing infra, not user value)

---

## Recommended Implementation Order

```
Phase 1: Foundation
  [1] God Class Refactor (orchestrator, agent core)
  [2] Test Runner Tool
  [3] TODO Tool

Phase 2: Infrastructure
  [4] LiteLLM Integration
  [5] Parallel Tool Execution

Phase 3: Quality Loop
  [6] Judge/Magistrate Pattern
  [7] TDD Loop (Self-Healing)

Phase 4: Polish
  [8] Seamless Escalation
  [9] Semantic Code Search
  [10] Gym / Benchmarks
```

---

## Summary Table

| Feature | Priority | Effort | Impact | Dependencies |
|---------|----------|--------|--------|--------------|
| Test Runner Tool | 1 | Low | High | None |
| TODO Tool | 1 | Low | High | None |
| LiteLLM Integration | 2 | Medium | Medium | Refactor |
| Parallel Execution | 2 | Medium | High | Refactor |
| Judge Pattern | 2 | Medium | Med-High | LiteLLM |
| TDD Loop | 2 | High | Very High | Judge, Test Runner |
| Seamless Escalation | 3 | Medium | Low-Med | TODO Tool |
| Semantic Search | 3 | High | Medium | None |
| Gym/Benchmarks | 3 | High | Low | TDD Loop |

---

## Final Thoughts

The Judge/TDD Loop is the most exciting feature but needs foundation work first. LiteLLM is good infrastructure but not urgent.

Start with:
- Build Test Runner Tool
- Build TODO Tool

These three unlock everything else.
