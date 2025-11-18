# UX Issues Report: Spring Boot + Vite React Agent Test

**Date**: 2025-11-16
**Task**: Create Spring Boot REST API + Vite React Frontend
**Investigator**: Claude Code (acting as human-in-the-loop)
**Test Duration**: ~35 seconds before crash

---

## Executive Summary

Ran the agent to create a full-stack web application with Java Spring backend and React frontend. The agent crashed after 7 iterations due to a **Windows Unicode encoding error**.

**Discovered 12 UX issues** including:
- **6 out of 7 iterations failed** (86% failure rate)
- **0 write_file operations** - agent wasted all iterations on scaffolding tools
- **LLM not platform-aware** - tried curl and Unix-style paths on Windows
- Startup latency, confusing error messages, no audit logging on crash

**Result**: Agent crashed with `'charmap' codec can't encode characters` error. Only empty directories created. **No actual code generated.**

---

## Test Configuration

**Command Used**:
```bash
python llm_team.py agent "Create a new directory called 'website/' with: 1. A Spring Boot REST API (Java) with user registration and login endpoints using JWT. Include basic User entity and H2 database. 2. A Vite + React frontend with landing page, login page, and register page. Use React Router and Axios." --auto-confirm --max-iterations 30 --no-checkpoint
```

**Models Used**:
- **Brain**: Cerebras
- **Planner**: Gemini (gemini-2.5-flash-lite with auto-fallback)

**Platform**: Windows 10/11

---

## Critical Issues Found

### Issue #1: Windows Unicode Encoding Crash (CRITICAL)

**File**: Unknown (crash occurs in stdout handling)

**Error Message**:
```
Agent error: 'charmap' codec can't encode characters in position 0-1: character maps to <undefined>
```

**Impact**: Complete agent crash after 7 iterations. No recovery, no graceful handling.

**Root Cause**: Windows console uses cp1252 encoding by default, which cannot encode certain Unicode characters (likely emojis or special symbols from npm create output).

**Recommendation**:
1. Force UTF-8 encoding for stdout/stderr in `cli_main.py`
2. Add error handling for encoding issues in command output
3. Strip or replace non-ASCII characters in command output before printing

---

### Issue #2: No Startup Progress Feedback (HIGH)

**Observed Behavior**: 30+ seconds of complete silence during initialization.

**What the User Sees**:
```
Initializing LLM Agent Team...
[OK] GitHub Models provider registered (GPT-4o: 10K RPD, 10M TPD)
[OK] Cerebras provider registered (14,400 RPD)
[OK] Groq provider registered (7,000 RPD)
[OK] Gemini provider registered (auto-fallback enabled)
[OK] Cohere provider registered (1,000/month - use sparingly)
[BRAIN] Using cerebras as orchestrator brain
Brain: cerebras
Available providers: github, cerebras, groq, gemini, cohere
Context: Not explored (use /context to explore)
...

(LONG SILENCE - 10+ seconds)

[Agent] Create a new directory...
Working...
```

**Impact**: Users may think the program is frozen or crashed.

**Recommendation**:
1. Add "Preparing agent..." or spinner during setup
2. Show progress for API key validation
3. Reduce initialization overhead

---

### Issue #3: Confusing ALTS Credentials Warning (MEDIUM)

**Error Message**:
```
WARNING: All log messages before absl::InitializeLog() is called are written to STDERR
E0000 00:00:1763342057.885421   15512 alts_credentials.cc:93] ALTS creds ignored. Not running on GCP and untrusted ALTS is not enabled.
```

**Impact**: Frightening error message that provides no useful information to the user.

**Root Cause**: Google's abseil library warning about Application Layer Transport Security credentials.

**Recommendation**:
1. Suppress this warning by initializing abseil logging properly
2. Filter out GCP-specific warnings when not on GCP
3. Set environment variable: `GRPC_ENABLE_FORK_SUPPORT=0`

---

### Issue #4: Spring Initializr Network Failures (HIGH)

**Failed Attempts**:
1. **curl command** - Returned truncated/malformed response
2. **PowerShell DownloadFile** - HTTP 400 Bad Request

**Error Messages**:
```
Exception calling "DownloadFile" with "2" argument(s): "The remote server returned an error: (400) Bad Request."
```

**Impact**: Agent cannot create Spring Boot project using standard tools. Falls back to manual creation which is inefficient.

**Root Cause**: URL encoding issues with Spring Initializr API parameters.

**Recommendation**:
1. Pre-validate Spring Initializr URLs before execution
2. Provide fallback template files for common project types
3. Better error recovery - suggest manual project creation

---

### Issue #5: Platform Command Syntax Errors (MEDIUM)

**Failed Command**:
```bash
mkdir website/frontend
```

**Error**:
```
The syntax of the command is incorrect.
```

**Impact**: Basic file operations fail unexpectedly. Agent had to retry with PowerShell cmdlet.

**Root Cause**: Windows cmd.exe doesn't accept forward slashes in mkdir paths.

**Recommendation**:
1. Auto-translate paths for platform: `website/frontend` -> `website\frontend`
2. Use PowerShell by default on Windows for better compatibility
3. Add path translation to `platform_utils.py`

---

### Issue #6: No Audit Log Saved on Crash (HIGH)

**Observed**: `.llm_agent_audit.json` file not created.

**Impact**: No record of what the agent attempted. Cannot debug or retry from last known state.

**Recommendation**:
1. Save audit log incrementally (after each action)
2. Add crash handler to save partial audit log
3. Save state even on error for post-mortem analysis

---

### Issue #7: Incomplete Error Recovery (MEDIUM)

**Behavior**: Agent attempted 4 different methods for Spring Initializr, all failed:
1. curl with complex URL
2. curl with simplified URL
3. PowerShell Invoke-WebRequest
4. Gave up on backend, switched to frontend

**Impact**: Agent doesn't have good fallback strategies. Wasted 4 iterations on failed attempts.

**Recommendation**:
1. Add template-based project generation (no network needed)
2. Better error classification - network vs syntax vs permission
3. Provide user with choices when automated approach fails

---

### Issue #8: LLM Not Platform-Aware (CRITICAL)

**Observed Behavior**: Agent (Gemini) tried Unix-style approaches on Windows:

**Iteration Timeline**:
```
1. mkdir website                  -> OK (universal)
2. curl https://start.spring...   -> FAILED (URL encoding issues)
3. curl (retry)                   -> FAILED (same issue)
4. PowerShell DownloadFile        -> FAILED (400 Bad Request)
5. mkdir website/frontend         -> FAILED (forward slash syntax)
6. PowerShell New-Item            -> OK (finally!)
7. npm create vite                -> CRASHED (Unicode output)
```

**Problems**:
1. **curl on Windows** - While curl exists on Windows 10+, the agent didn't properly escape/encode the Spring Initializr URL
2. **mkdir with forward slashes** - Classic Unix syntax that fails on Windows cmd.exe
3. **No learning from failures** - Tried curl twice before switching strategies
4. **npm create with Unicode** - Didn't anticipate Unicode spinner output

**Root Cause**: The LLM (Gemini) isn't trained with Windows-specific knowledge. The system prompt mentions "Windows" but the LLM still defaults to Unix-style approaches.

**Impact**:
- **6 out of 7 iterations were failures or workarounds**
- Agent spent entire session trying to scaffold, never wrote actual code
- User sees confusing errors and no progress

**Recommendation**:
1. **Enhance platform guidance in system prompt** - Provide concrete examples:
   ```
   BAD: mkdir website/frontend
   GOOD: mkdir website\frontend OR New-Item -ItemType Directory -Path website\frontend
   ```
2. **Add tool-specific validation** - Before run_command, validate command syntax for platform
3. **Provide templates instead of downloads** - Don't rely on Spring Initializr network calls
4. **Limit retry attempts** - After 2 failures with same approach, force different strategy
5. **Pre-validate commands** - Check if curl/wget are available and working before using them

---

### Issue #9: No Write Operations Attempted (CRITICAL)

**Key Insight**: In 7 iterations, the agent **never once called write_file**.

**What the Agent Did**:
- `run_command` - 7 times (all scaffolding attempts)
- `write_file` - 0 times
- `read_file` - 0 times

**Why This Matters**: The task was to create a Spring Boot + React application. The agent could have:
1. Created `pom.xml` directly with write_file
2. Created `User.java` directly with write_file
3. Created `package.json` directly with write_file
4. Created React components directly with write_file

Instead, it tried to use automated scaffolding tools that failed repeatedly.

**Recommendation**:
1. **Bias toward write_file** - When creating projects, prefer direct file creation over scaffolding tools
2. **Detect scaffolding failures early** - After 2 failed run_command attempts, switch to write_file approach
3. **Provide project templates** - Include common project structures in the system prompt

---

## Minor Issues

### Issue #10: Result Truncation Without Notice
Command output is truncated:
```
Result:   % Total    % Received...
```
User can't see full error to understand what went wrong.

### Issue #11: No Iteration Counter
User doesn't know how many iterations have been used or how many remain.

### Issue #12: Auto-Confirm Warning Unclear
```
WARNING: Auto-confirm enabled - no approval prompts
```
Doesn't explain the security implications.

---

## What Was Actually Created

```
website/
  backend/    (empty directory)
  frontend/   (empty directory)
```

**Expected**: Full Spring Boot + React application
**Actual**: Two empty directories

---

## Comparison with Previous Test (UX_INVESTIGATION_REPORT.md)

| Metric | Previous Test | This Test |
|--------|---------------|-----------|
| Method | Python API | CLI Command |
| Crash | No | Yes (Unicode) |
| Iterations | 35 | 7 (crashed) |
| Files Created | Multiple | 0 (empty dirs) |
| Main Issue | Premature completion | Encoding crash |

---

## Recommendations Summary

### Critical (Must Fix)
1. **Fix Unicode encoding** - Force UTF-8 or handle encoding errors gracefully
2. **Enhance platform guidance** - Teach LLM Windows-specific commands with examples
3. **Bias toward write_file** - Stop wasting iterations on failed scaffolding tools
4. **Add startup progress** - Show user something is happening during 10+ second init

### High Priority
5. **Incremental audit logging** - Save progress even on crash
6. **Platform path translation** - Auto-convert `/` to `\` on Windows
7. **Network error recovery** - Better fallbacks for Spring Initializr
8. **Limit retry attempts** - Max 2 failures before forcing different approach

### Medium Priority
9. **Suppress GCP warnings** - Filter irrelevant ALTS/abseil messages
10. **Show iteration count** - User should know progress
11. **Better auto-confirm warning** - Explain security implications
12. **Pre-validate commands** - Check syntax before execution

---

## Files Modified in This Session

- None (agent crashed before creating files)

## Related Files to Fix

- `src/cli_main.py` - Add UTF-8 encoding for stdout/stderr
- `src/agent/core.py` - Add crash handler for audit log
- `src/platform_utils.py` - Add path translation for mkdir commands
- `src/cli/commands.py` - Suppress GCP-specific warnings

---

## Reproduction Steps

1. Clean environment:
```bash
rm -f .llm_team_context.json .llm_response_cache.json .llm_rate_limits.json
rm -rf website/
```

2. Run agent:
```bash
python llm_team.py agent "Create a new directory called 'website/' with Spring Boot backend and Vite React frontend" --auto-confirm --max-iterations 30
```

3. Observe crash at iteration 7 with Unicode encoding error

---

## Conclusion

The agent's CLI mode has significant UX issues on Windows, primarily related to:
1. Console encoding incompatibility (crash on Unicode output)
2. Lack of progress feedback during initialization
3. Poor error recovery when network operations fail
4. Platform-specific command syntax issues

The Unicode crash is the most critical issue as it prevents any real work from being completed. The previous test using the Python API directly didn't hit this issue because it handled output differently.

**Next Steps**: Fix the Unicode encoding issue first, as it blocks all Windows CLI usage. Then address the startup latency and error recovery issues.
