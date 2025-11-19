# LLM Team CLI Agent Command Test Report

**Date**: 2025-11-16
**Task**: Create Spring REST API + Vite React Frontend
**Method**: CLI `/agent` command (not Python API)
**Test File**: `tests/test_agent_spring_vite_integration.py`

---

## Test Configuration

**Command Executed**:
```bash
python llm_team.py agent "task..." --auto-confirm --max-iterations 50 --no-checkpoint
```

**Provider Configuration**:
- **Brain/Orchestrator**: Cerebras (default)
- **Planner**: GitHub Models (GPT-4o) - auto-selected
- **Executor**: Cerebras

**Pre-Test Cleanup**:
```bash
rm -f .llm_team_context.json
rm -f .llm_response_cache.json
rm -f .llm_rate_limits.json
rm -f .llm_agent_audit.json
rm -rf website/
```

---

## Test Runs

### Run 1: Unicode Crash

**Duration**: 67.54s
**Exit Code**: 1
**Iterations**: ~12 (crashed before reporting)

**Outcome**: Unicode encoding error when printing agent output

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2502' in position 5199
```

**Root Cause**: Test script didn't wrap stdout for UTF-8 on Windows.

**Fix Applied**: Added UTF-8 wrapper to test script:
```python
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

---

### Run 2: Rate Limit Crash

**Duration**: 37.33s
**Exit Code**: 1
**Iterations**: 10

**Agent Output**:
```
Initializing LLM Agent Team...
[OK] GitHub Models provider registered (GPT-4o: 10K RPD, 10M TPD)
[OK] Cerebras provider registered (14,400 RPD)
[OK] Groq provider registered (7,000 RPD)
[OK] Gemini provider registered (auto-fallback enabled)
[OK] Cohere provider registered (1,000/month - use sparingly)
[BRAIN] Using cerebras as orchestrator brain

Agent Configuration:
  Planner (smart tasks): github
  Executor (fast tasks): cerebras
  Project root: C:\Users\anyth\MINE\dev\scrappy
  Max iterations: 50
  WARNING: Auto-confirm enabled - no approval prompts
```

**Agent Actions** (10 iterations):

1. `run_command` - Create directories (FAILED - wrong syntax)
2. `run_command` - PowerShell New-Item (FAILED - not recognized)
3. `run_command` - Python os.makedirs (SUCCESS)
4. `write_file` - pom.xml (SUCCESS)
5. `write_file` - BackendApplication.java (SUCCESS)
6. `write_file` - User.java (SUCCESS)
7. `write_file` - UserRepository.java (SUCCESS)
8. `write_file` - AuthService.java (SUCCESS)
9. `write_file` - [attempted] (FAILED - rate limit)

**Error**:
```
Agent error: Too many requests. For more on scraping GitHub and how it may
affect your rights, please review our Terms of Service
(https://docs.github.com/en/site-policy/github-terms/github-terms-of-service).
```

---

## Files Created

**Backend** (5 files):
```
website/backend/
├── pom.xml
└── src/main/java/com/example/backend/
    ├── BackendApplication.java
    ├── entity/User.java
    ├── repository/UserRepository.java
    └── service/AuthService.java
```

**Frontend** (0 files):
```
website/frontend/
└── (empty - agent crashed before reaching frontend)
```

---

## Key Observations

### 1. GitHub Models as Default Planner

When GitHub API key is present, it becomes the default planner instead of Gemini. This is unexpected behavior:

```
Planner (smart tasks): github  # Not gemini!
```

### 2. Aggressive Rate Limiting

GitHub Models advertises "10K RPD" (requests per day) but:
- Hit rate limit after only **10 LLM calls**
- No burst tolerance
- No automatic retry or backoff
- No fallback to other providers
- Agent crashes immediately

### 3. Windows Command Issues

Agent struggles with Windows:

```
Thought: I will start by creating the directory structure...
Executing: run_command
Result: The syntax of the command is incorrect.

Thought: I will use PowerShell syntax...
Executing: run_command
Result: 'New-Item' is not recognized...

Thought: I will use Python's os module...
Executing: run_command
Result: (no output)  # Finally works!
```

Agent adapted and found a working solution, but wasted 3 iterations.

### 4. Different Package Structure

GitHub Models (GPT-4o) created different structure than Gemini:
- `com.example.backend` (GitHub Models)
- `com.example.llmagentbackend` (Gemini)

Different models have different coding conventions.

---

## UX Issues Identified

### Critical

1. **No Rate Limit Recovery**
   - Agent crashes with no fallback
   - User loses all progress
   - No automatic retry with different provider

### High

2. **GitHub Models Misleading Quota**
   - Advertises 10K RPD
   - Actually ~10-20 requests before burst limit
   - Per-minute limits not documented

3. **Provider Auto-Selection Unpredictable**
   - Having API key makes it default
   - User may not realize which provider is being used
   - No way to see provider selection logic

### Medium

4. **Windows Command Compatibility**
   - Linux commands fail
   - PowerShell not recognized
   - Falls back to Python (works but inefficient)

5. **No Progress Persistence**
   - When rate limited, work is lost
   - No checkpoint of agent state
   - Must restart from scratch

---

## Comparison: GitHub Models vs Gemini

| Aspect | GitHub Models (CLI Test) | Gemini (API Test) |
|--------|--------------------------|-------------------|
| Iterations completed | 10 | 35 |
| Duration | 37s | 96s |
| Backend files | 5 | 17 |
| Frontend files | 0 | 6 |
| Rate limit hit | YES (crash) | YES (fallback) |
| Recovery | None | Auto-fallback to alternate model |
| Package naming | `com.example.backend` | `com.example.llmagentbackend` |

---

## Test Script Issues Found

1. **Variable name mismatch** - `expected_backend_files` vs `expected_backend_patterns`
2. **Hardcoded package paths** - Didn't account for different LLM conventions
3. **No retry logic** - Should retry with different provider on rate limit

---

## Recommendations

### Immediate Fixes

1. **Add provider fallback on rate limit**
   ```python
   except RateLimitError:
       self.planner = self._get_next_available_provider()
       # Retry current action
   ```

2. **Add rate limit pre-check**
   - Check remaining quota before starting task
   - Warn user if insufficient

3. **Save agent state on failure**
   - Checkpoint conversation history
   - Allow resume with `--resume` flag

### Configuration Improvements

4. **Make provider selection explicit**
   ```bash
   llm-team agent "task" --planner gemini --executor cerebras
   ```

5. **Show rate limit status in UI**
   ```
   [Iteration 8/50] [GitHub: 2/10 remaining] [Gemini: 150/1650]
   ```

6. **Windows-aware command generation**
   - Detect platform in agent context
   - Use appropriate syntax (cmd, PowerShell, bash)

---

## Conclusion

The CLI agent command works but has critical reliability issues:

1. **GitHub Models is unusable for complex tasks** - Rate limits too aggressive
2. **No failover mechanism** - Single provider failure = total failure
3. **Different LLMs = different outputs** - Test expectations need flexibility
4. **Windows support needs work** - Many command failures

The /agent command UX is reasonable when it works, but the rate limiting issue makes it unreliable for production use. Users need to manually specify `--brain gemini` or `--brain groq` to avoid GitHub Models rate limits.

**Bottom Line**: Don't use GitHub Models for the planner role in complex tasks. Stick with Gemini (has auto-fallback) or Cerebras (higher limits).
