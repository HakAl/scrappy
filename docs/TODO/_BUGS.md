## Issues

---
create a plan for semantic search UX
Current status: shows some numbers, progress doesn't move, timer remains at 0, isn't hidden when task completes.
Shown every time on load -- need a paradigm created so we show status bar on initial / large scans. not each app launch
---

---
too much agent output? toggle with agent verbose mode?
---

---
why python tools? what's the purpose?? generalize to dependencies tool? is that useful?
---

---
is max steps 10 for agent good? are existing safeguards good enough? 
---

---
automatically explore?
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


---
shift selection is messed up, can't 'unselect' once a point is selected.
can't use mouse scroll during selection.  shift + scrolling
---

---
code search tool is completely useless (command tool has grep)-- more logical as a hybrid with grep/rg + semantic search?
---

===

Unconfirmed / Mixed Behavior
----