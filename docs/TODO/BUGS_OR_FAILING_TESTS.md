help me assess these tests? some are bad, useless, call actual functions or apis not mocks.
sort through them to remove bad tests and keep good ones. please list functions to remove, or the whole file, or nothing.



[//]: # (CRITICAL)


  🔥 TEST ISOLATION FAILURES

  1. Integration Tests Run by Default = Real API Calls

  - ❌ pytest.ini doesn't exclude @pytest.mark.integration
  - ❌ All 5 API keys are set in your environment
  - ❌ Running pytest makes 457+ real API calls and costs real money
  - ❌ Integration tests hit rate limits (30 errors in the file)

  2. Tests Write to Project Root

  - ❌ .llm_rate_limits.json created in project root (should use tmp)
  - ❌ .llm_response_cache.json created in project root (should use tmp)
  - ❌ These files pollute the repository

  3. Tests Create Source Files

  - ❌ App.js created in src/ -- tests/test_agent_loop_prevention.py??
  - ❌ Tests should ONLY write to tmp_path fixtures

  The Fixes Needed

  1. Update pytest.ini to exclude integration tests by default
  2. Mock RateLimitTracker to use temp paths, not project root
  3. Mock ResponseCache to use temp paths, not project root
  4. Add .gitignore entries for these files
  5. Audit all tests to ensure they use tmp_path/temp_project_dir
  6. Document how to run integration tests explicitly

---

<!-- MEDIUM PRIORITY - TEST NEEDED / INVESTIGATION / REPAIR: -->

src\cli\smart_query.py

src\cli\research_handlers\testing.py
src\cli\research_handlers\dependency_info.py
src\cli\research_handlers\architecture.py 
src\cli\research_handlers\configuration.py
src\cli\research_handlers\documentation.py

[//]: # (agent_tools)
3 failing tests in: test_search_tools.py
2 failing tests in: test_file_tools.py
1 failing test in: test_web_tools.py
1 failing test in: test_python_tools.py

---

3 failing tests in: tests/test_agent_checkpoint.py

---

todos in: tests/providers/test_github_models_provider.py
todos in: tests/providers/test_cohere_provider.py
todos in: tests/providers/test_cerebras_provider.py

---

MANY likely bugs: tests/test_import_utils.py

---

todos in: tests/agent_tools/test_output_formatter.py

---

too big?
src/agent/core.py
src/agent_tools/tools/command_tool.py
src/cli/exceptions.py
src/cli/output.py
src/cli/rich_output.py
src/context/codebase_context.py
src/orchestrator/core.py
src/orchestrator/cache.py
src/orchestrator/rate_limiting/tracker.py
src/platform/fallback.py
src/platform/translation.py
src/task_router/router.py

---

cerebras not defaulted to instruct model

---


