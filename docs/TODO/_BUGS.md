## Issues


---
(src\scrappy\task_router\classifier.py)
  ⎿  Read 150 lines

● Search(pattern: "_extract_file_references", path: "src\scrappy\task_router\classifier.py", output_mode: "content")
  ⎿  Found 83 lines (ctrl+o to expand)

● Found the bug! Look at line 300:

  file_ext_pattern = r'\b([\w\-.\]+\.(?:js|jsx|ts|tsx|py|...md...))\b'

  The character class [\w\-.\] doesn't include /, so paths like docs/TODO/SELECTABLE_LOG.md won't match as a full path - it only extracts SELECTABLE_LOG.md (the filename part).

  When you say "review docs/TODO/SELECTABLE_LOG.md", the system:
  1. Extracts just SELECTABLE_LOG.md (missing the directory path)
  2. The file doesn't exist at the root, so it falls back to semantic search
  3. Semantic search finds "RichLog" as related content

  The fix needs to include path separators in the regex. But more importantly - if a user provides an explicit path, the system should check if that file exists and read it directly before falling back to searc
---

 ### 3. **Scalability Improvements**
 - Refactor the core agent to support distributed execution
 - Implement proper resource management for concurrent operations
 - Add configuration options for resource limits and throttling

 ### 4. **Extensibility**
 - Create a formal plugin interface for custom action executors
 - Standardize the context factory pattern across components
 - Add clear extension points in the agent loop

 ### 5. **Observability**
 - Enhance the audit module with structured logging
 - Add metrics collection for key operations and performance indicators
 - Implement distributed tracing support

 ### 6. **Configuration and Usability**
 - Create a centralized configuration system
 - Add validation for configuration parameters
 - Implement better defaults and documentation

 ### 7. **Testing and Reliability**
 - Increase test coverage, especially for edge cases
 - Add integration tests for the complete agent workflow
 - Implement property-based testing for core algorithms

---

---
why python tools? what's the purpose?? generalize to dependencies tool? is that useful?
---

---
src/agent/core.py -- _format_codebase_structure -- does this belong here?
---

---
Problem: Provider output is truncated.
EG:  Available Providers:
 --------------------------------------------------

 GITHUB
 (Active)
   Default Model: gpt-4o
   Daily Quota: 10,000 requests
   Daily Tokens: 10,000,000 TPD
   Models: gpt-4o, gpt-4o-mini, deepseek-r1
            ... and 6 more

 CEREBRAS
 (Active)
   Default Model: qwen-3-235b-a22b-instruct-2507
   Daily Quota: 14,400 requests
   Token Limit: 60,000 TPM
   Models: llama3.1-8b, llama-3.3-70b, qwen-3-32b
            ... and 1 more

 GROQ
 (Active)
   Default Model: llama-3.1-8b-instant
   Daily Quota: 7,000 requests
   Token Limit: 20,000 TPM
   Daily Tokens: 200,000 TPD
   Models: llama-3.1-8b-instant, llama-3.3-70b-versatile, llama-3.1-70b-versatile
            ... and 3 more

 GEMINI
 (Active)
   Default Model: gemini-2.5-flash-lite
   Daily Quota: 1,000 requests
   Daily Tokens: 250,000 TPD
   Models: gemini-2.5-flash-lite, gemini-2.0-flash-lite, gemini-2.0-flash
            ... and 2 more

 COHERE
 (Active)
   Default Model: command-r7b-12-2024
   Models: command-r-08-2024, command-r7b-12-2024, command-a-03-2025
            ... and 3 more
---



===

Unconfirmed / Mixed Behavior
----