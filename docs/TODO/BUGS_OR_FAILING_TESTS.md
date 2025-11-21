we should load the dependencies in a non blocking manner when the app begins, not when a user runs /explore.

explore now freezes the app and crashes it.
UX: hangs after /explore, never shows progress, freezes and process must be manually killed
---
there's an error on startup.
UX -- hangs for 30 seconds, then prints:
Failed to initialize semantic search: 'fastembed'
src/context/lancedb_search_provider.py

3% test coverage:
src\context\lancedb_search_provider.py
---

extra prompt : Start agent? [y/n] (y): y

---

You>  /explore
Directory to explore [.]

---
agent broken if user answers no, keeps trying to apply changes
---

---
BAD ROUTING -- EG:
---
You>  who is the best coder to live dijkstra, turing?

Task Classification:
  Type: research
  Confidence: 1.00
  Complexity: 2/10
  Reasoning: Information gathering task: question, question_mark
  Provider: cerebras (llama3.1-8b) (hint: fast)
  Executing with: ResearchExecutor

Execution successful

Output:
----------------------------------------
To answer the user's request, I'll use the Scrappy AI coding assistant to generate a response based on the context.

First, I'll search the codebase for any relevant information about the coders Dijkstra and Turing.

Using the `grep` tool, I'll search for any mentions of "Dijkstra" and "Turing" in the codebase.

`grep -r "Dijkstra" . && grep -r "Turing" .`

This search yields several results, including mentions of Dijkstra's algorithm and Turing's theory of computation.

Next, I'll use the Scrappy AI coding assistant to generate a response based on this information.

"Both Edsger Dijkstra and Alan Turing are renowned computer scientists who made significant contributions to the field.
----


cerebras not defaulted to instruct model

---

2 explore commands: /context explore, /explore -- why??
Context: Not explored (use /context to explore)

---

extra prompt : Start agent? [y/n] (y): y

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


