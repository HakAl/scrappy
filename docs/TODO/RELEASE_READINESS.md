# Release Readiness Assessment

## Current State: Released

---

### Tier 4: High Value Post-RC

| Feature | Priority | Effort | Source | Rationale |
|---------|----------|--------|--------|-----------|
| **Todo Tool** | High | Medium | TODO_TOOL | Agent forgets progress on complex tasks |
| **Test Runner Tool** | High | Medium | TEST_RUNNER_TOOL | Closes the TDD verification loop |
| **Proactive rate limiting** | High | High | RATE_LIMITING | Stop wasting API calls on exhausted providers |
| **Smart staleness detection** | Medium | Medium | IDEAL_UX | JIT reindex only referenced files |
| **Provider performance tracking** | Medium | Medium | HIGH_VALUE_FEATURES | Score-based intelligent routing |

### Tier 5: Nice to Have (v1.1+)

| Feature | Priority | Effort | Source | Rationale |
|---------|----------|--------|--------|-----------|
| Episodic Memory (Phase 2) | Medium | High | _WIP | Long conversation recall |
| Parallel tool execution | Medium | Medium | PARALLEL_TOOL | Speed up multi-file operations |
| platformdirs (XDG paths) | Low | Low | HIGH_VALUE_FEATURES | Cross-platform config |
| Offline/local mode | Low | Medium | OFFLINE_MODE | Graceful degradation when no API |
| Local model support (Ollama) | Low | High | OFFLINE_MODE | Privacy-conscious users |
| Structured output validation | Low | Medium | RESEARCHED_FEATURES | Pydantic schemas for LLM responses |

---

## Release Checklist

### Post-RC (v1.0 Road)
- [ ] Todo Tool for agent planning
- [ ] Test Runner Tool for verification
- [ ] Proactive rate limiting

### Post-Release (v1.1+)
- [ ] Episodic Memory (Phase 2)
- [ ] Provider performance tracking
- [ ] Smart staleness detection
- [ ] Parallel tool execution

---

**Post-RC (v1.0):**
12. Todo Tool
13. Test Runner
14. Streaming responses

**Post-Release (v1.1+):**
15. Episodic Memory
16. Proactive rate limiting