# OFFLINE / LOCAL-ONLY MODE (Future)

## Vision
Users can use scrappy without LLM providers for local-only features.
Hybrid mode: some features work offline, others require providers.

---

## When This Matters

- Returning user loses API access (keys expire, rate limited, network down)
- Privacy-conscious user wants local-only for certain tasks
- Future: Local model support (ollama, llama.cpp)

---

## Feature Classification

### Works Offline
- File operations: read, write, search (grep-based)
- Git operations: status, diff, log, commit, branch
- Shell commands: any local command
- Session management: save/load
- Navigation: cd, ls, tree
- Help: /help, /commands
- Project scanning: detect project type

### Requires LLM Provider
- Chat/delegation (core interaction)
- Code generation (agent loop)
- Complex task planning
- Intent classification
- Semantic search (embeddings)

### Could Degrade Gracefully
- Task routing: fall back to heuristics
- Search: keyword instead of semantic

---

## UX Decisions (When Ready)

### Interactive Mode
Recommendation: Launch normally, LLM commands fail with helpful error

### Command Visibility
Recommendation: Show LLM commands as "unavailable" with explanation

### Error Message
```
No LLM provider configured.

Available offline:
  /help, /git, /file, /search (grep), /session

To enable LLM features: /setup
```

---

## Existing Infrastructure

Already have graceful degradation patterns:
- `src/infrastructure/error_recovery/fallback.py` - FallbackChain, graceful_degrade()
- `src/cli/error_recovery/fallback.py` - fallback_providers()
- `src/infrastructure/exceptions/provider_errors.py` - All error types

---

## Local Model Support (Future)

Potential providers:
- Ollama (local inference server)
- llama.cpp (direct inference)
- LM Studio (local GUI + API)

Would fit into ProviderInfo as another entry with local detection.

---

## Priority

**Low** - Phase 1 (new user setup) handles critical path.
Implement when:
- Local model support added
- Users request offline functionality
- Privacy/security use cases emerge
