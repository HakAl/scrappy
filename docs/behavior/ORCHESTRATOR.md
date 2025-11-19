# Orchestrator

Allows any registered provider to act as the orchestrator brain. The orchestrator can automatically learns about your codebase and injects relevant context into prompts.

## The Good

  1. test_rate_limiter.py - 1,387 lines of excellent behavior-testing
  2. tests/helpers.py - Well-designed ConfigurableTestOrchestrator, MockIO
  3. Type hints throughout
  4. Good JSON recovery in task_executor.py
  5. Composition pattern - orchestrator delegates to specialists

## Issues

<!-- todo -->

- Add skip logic in task_executor.py
eg:   if complexity_score <= 3:
      return [{"step": "execute", "description": task, "provider_type": "fast"}]
- Update planning prompt to include: "For simple tasks, return 1-2 steps maximum. Minimize unnecessary steps."


Critical Issues

  1. Poor Testability - Interactive I/O ❌ HIGH

  40+ direct print() calls throughout the codebase:

  # core.py:118-148 - Provider registration
  print("[OK] GitHub Models provider registered (GPT-4o: 10K RPD, 10M TPD)")
  print(f"[X] GitHub Models provider unavailable: {e}")

  # core.py:561,646,668 - Runtime status
  print(f"[WARN] {current_provider_name} has exhausted daily quota...")
  print(f"[ERROR] All providers rate limited. Attempted: {attempted_providers}")

  Impact: Cannot test without capturing stdout; violates SRP.

  ---
  2. Massive Files - SRP Violation ❌ CRITICAL

  core.py at 1,276 lines - AgentOrchestrator handles 15+ responsibilities:
  - Provider registration (113-148)
  - Context management (268-284)
  - Delegation with retry/fallback (443-673)
  - Async delegation (749-976)
  - Batch processing (978-1016)
  - Background task management (1123-1211)
  - ...and more

  Impact: Untestable, incomprehensible, unmaintainable.

  ---
  3. Fragile Pattern Matching ⚠️ MEDIUM

  task_executor.py:142-203 - JSON extraction uses multiple regex fallbacks:
  # Attempts: code blocks → raw JSON → array search → single object
  Good error recovery exists, but callers may not know they got fallback response.

  ---
  4. Duplicated Code ❌ MEDIUM

  Provider priority lists duplicated in 3+ locations:

  # core.py:221,250
  all_known = ['cerebras', 'groq', 'gemini', 'cohere']

  # core.py:389-392
  task_preferences = {
      'planning': ['cerebras', 'groq', 'gemini'],
      'execution': ['cerebras', 'groq', 'gemini'],
      ...
  }

  # provider_selector.py:211,254
  priority = ['cerebras', 'groq', 'gemini']

  ---
  5. Complex JSON Parsing ✅ Handled

  task_executor.py has graceful degradation - returns raw response as single step on failure. This is actually a
  good pattern.

  ---
  6. Mixed Concerns & God Objects ❌ CRITICAL

  AgentOrchestrator is a textbook God Object. Also:

  # core.py:113-148 - _auto_register_providers()
  def _auto_register_providers(self):
      try:
          self.registry.register(GitHubModelsProvider())
          print("[OK] GitHub Models provider registered...")  # Business + presentation
      except Exception as e:
          print(f"[X] GitHub Models provider unavailable: {e}")

  Business logic mixed with I/O throughout.

  ---
  7. Shallow Tests ❌ CRITICAL

  No test file for core.py - the largest (1,276 lines) component.

  Missing coverage:
  - delegate() method (250+ lines) - untested
  - delegate_async() method - untested
  - Background task management - untested

  Existing tests are good quality (test_rate_limiter.py is excellent at 1,387 lines), but critical paths are
  missing.

  ---
  Code Quality Issues

  8. Side Effects Everywhere ❌ HIGH

  Silent except Exception: pass patterns throughout:

  # cache.py:371-372, 389-390
  except Exception:
      pass  # Silently fail on write errors

  # core.py:565-566, 1233-1234, 1258-1259
  except Exception:
      pass

  # rate_limiter.py:80-81, 95-96
  except Exception:
      pass

  Impact: Errors vanish; impossible to debug production issues.

  ---
  9. No Validation ❌ LOW

  # core.py:445-460
  def delegate(
      self,
      prompt: str = "",
      max_tokens: Optional[int] = None,
      temperature: float = 0.7,
      ...
  ):

  No validation that:
  - prompt is not empty when required
  - max_tokens is positive
  - temperature is in valid range

  ---
  10. Tight Coupling ❌ MEDIUM

  core.py:66-107 - Creates all dependencies directly:

  def __init__(self, ...):
      self.cache = ResponseCache(...)           # Hardcoded
      self.rate_tracker = RateLimitTracker(...) # Hardcoded
      self.working_memory = WorkingMemory()     # Hardcoded
      self.session_manager = SessionManager(...) # Hardcoded
      self.provider_selector = ProviderSelector(...) # Hardcoded

  Impact: Cannot inject test doubles.

  ---
  Test Quality Issues

  11. Tests Don't Follow TDD ⚠️ LIKELY

  Evidence: Core functionality (delegate, delegate_async) has no tests. If TDD was followed, these would be the
  first tests written.

  ---
  12. Over-reliance on Mocks ⚠️ PARTIAL

  test_task_executor.py:106-118:
  def test_low_complexity_score_skips_planning(self, executor, mock_brain):
      result = executor.plan("Open file", complexity_score=2)
      mock_brain.chat.assert_not_called()  # Only checks mock wasn't called

  Tests what ISN'T called, not what happens when it IS called.

  Positive: test_rate_limiter.py tests actual behavior excellently:
  def test_get_remaining_quota_with_all_limits(self):
      tracker.record_request('groq', 'model', 1000, 500)
      remaining = tracker.get_remaining_quota('groq', 'model', limits)
      assert remaining['requests_remaining_today'] == 98  # Actual calculation

  ---
  13. Skipped Tests ❌ YES

  # tests\benchmark\test_agent_spring_vite_integration.py:74
  @pytest.mark.skip(reason="Echo command triggers interactive prompts")

  Confirms Issue #1 - interactive I/O makes testing impossible.

  ---
  Architecture Issues

  14. No Clear Abstractions ⚠️ PARTIAL

  Some protocols exist (ContextProvider, OrchestratorAdapter), but AgentOrchestrator doesn't implement any - can't
  substitute with test double.

  ---
  15. Configuration Scattered ❌ YES

  # provider_selector.py:229-237
  reasons = {
      'cerebras': '14,400 RPD - highest daily quota',
      'groq': '7,000 RPD - fast and reliable',
      ...
  }

  # core.py:118-148
  print("[OK] Cerebras provider registered (14,400 RPD)")

  Same information hardcoded in multiple places.


  ---
  Priority Recommendations

  | Priority | Issue               | Action                                              |
  |----------|---------------------|-----------------------------------------------------|
  | CRITICAL | No core.py tests    | Write tests for delegate(), delegate_async()        |
  | CRITICAL | God Object          | Extract to DelegationManager, BackgroundTaskManager |
  | HIGH     | Direct print()      | Inject OutputInterface protocol                     |
  | HIGH     | Silent except: pass | Log errors, return Result types                     |
  | MEDIUM   | Tight coupling      | Accept deps via constructor (DI)                    |
  | MEDIUM   | Duplicated config   | Create PROVIDER_PRIORITIES constant                 |

---

**RED**

we're working to improve src\orchestrator the next task is: 
Consolidate and Clean - Remaining task:

  - Update type hints throughout codebase - Optional refactoring to replace AgentOrchestrator type hints with
  Orchestrator Protocol where appropriate for looser coupling.

Usage:

  from src.orchestrator import Orchestrator

  def use_orchestrator(orch: Orchestrator) -> Dict:
      return orch.get_usage_report()
  Todos
  ☒ Write tests for Orchestrator Protocol
  ☒ Create src/orchestrator/protocols.py with Orchestrator Protocol
  ☒ Verify AgentOrchestrator implements Protocol
  ☒ Run full test suite to verify no regressions
  ☐ Update type hints throughout codebase to use Protocol
can you research the task and start with tests? are new tests needed? 

**GREEN**

we completed the red phase of the task: 

**REFACTOR**

we created:
they're fully tested and ready for integration in src/. can you complete the refactor phase of TDD?


  ---
  Phase 4: Consolidate and Clean

  ---
  4.3 Add Protocol for Orchestrator

  1. Create src/orchestrator/protocols.py:

  from typing import Protocol

  class Orchestrator(Protocol):
      """Protocol for orchestrator implementations"""

      def delegate(self, prompt: str, ...) -> LLMResponse: ...
      async def delegate_async(self, prompt: str, ...) -> LLMResponse: ...
      def get_usage_report(self) -> Dict: ...

  2. Have AgentOrchestrator implement it
  3. Use protocol in type hints throughout codebase

  ---
  Phase 5: Verify and Document

  5.1 Run Full Test Suite

  python -m pytest tests/ -v --cov=src/orchestrator --cov-report=term-missing

  Targets:
  - core.py: 80%+ coverage
  - delegation.py: 90%+ coverage
  - task_executor.py: 85%+ coverage
  - All other orchestrator files: 80%+

  ---
  5.2 Remove Skipped Tests

  Fixes: Issue #13 (Skipped Tests)

  After Phase 1 completes (testable I/O), revisit:
  - tests/benchmark/test_agent_spring_vite_integration.py:74

  Use MockIO from helpers to enable the test.

  ---
  5.3 Update Documentation

  1. Add docstrings to all new classes
  2. Update any architecture docs
  3. Document the DI pattern for future contributors
