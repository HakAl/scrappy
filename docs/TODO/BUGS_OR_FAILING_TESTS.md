we have 29 failing tests from recent refactoring work. they may highlight errors in code, be bad/duplicate
  tests, or need updated w/ new imports / apis. can you check into them?
 There are a few test failures remaining that appear to be from incomplete refactoring:


<!-- MEDIUM PRIORITY - 30-50% Coverage: -->

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


too big?
src/platform/fallback.py
src/platform/translation.py
src/orchestrator/core.py
src/orchestrator/cache.py
src/orchestrator/rate_limiting/tracker.py
src/cli/exceptions.py
src/cli/output.py
src/cli/rich_output.py
src/context/codebase_context.py
src/task_router/router.py
src/agent/core.py
