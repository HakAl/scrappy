<!-- MEDIUM PRIORITY - TEST NEEDED / INVESTIGATION / REPAIR: -->

Problem:
Many tests have been commented out and marked #todo that may expose issues in code.
Investigate and determine what is required to resolve.

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

failing tests: tests/context/test_code_chunker.py

test_chunk_multiple_chunks_with_overlap
test_chunk_exact_fit_no_remainder
test_protocol_compliance

---

tests/infrastructure/test_texual_progress.py

test_import_handling

---

tests/platform/test_fallback.py

test_find_basic
test_which_nonexistent_command
TestEdgeCasesAndErrorHandling

---


[//]: # (Low Priority)

127 warnings -- what are the warnings about?