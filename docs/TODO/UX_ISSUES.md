# UX Issues

Problem:
/explore command fails. 
 Error: CLICodebaseAnalysis.explore_codebase() got an unexpected keyword argument 'io'

Solution:
Investigate and repair

---

Problem:
ansi artifacts in /cache command output.
/cache:
 [36m[1m
 Cache Statistics:[0m
 [36m--------------------------------------------------[0m
 Total Entries: 0
 Exact Cache Hits: 0
 Intent Cache Hits: 0
 Cache Misses: 0
 Cache Saves: 0
 Exact Hit Rate: [33m0.0%[0m
 Intent Hit Rate: [33m0.0%[0m
 Cache File: .scrappy\response_cache.json
 Caching: [32mEnabled[0m

Solution:
find why / where this occurs and plan to fix.

---

Problem:
/usage command output is 3 tables with different styles. 
 ╭────────────────────────────── Usage Summary ───────────────────────────────╮
 │ Total Tasks: 1                                                             │
 │ Cache Hits: 0                                                              │
 │ API Calls: 1                                                               │
 │ Session Duration: 0:04:13.394599                                           │
 ╰────────────────────────────────────────────────────────────────────────────╯
                       By Provider
 ┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━┓
 ┃ Provider ┃ Requests ┃ Tokens ┃ Avg Tokens ┃ Latency ┃
 ┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━┩
 │ cerebras │ 1        │ 623    │ 623.0      │ 1016ms  │
 └──────────┴──────────┴────────┴────────────┴─────────┘
 ╭───────────────────────────── Cache Statistics ─────────────────────────────╮
 │ Exact Hit Rate: 0.0%                                                       │
 │ Intent Hit Rate: 0.0%                                                      │
 │ Total Entries: 1                                                           │
 ╰────────────────────────────────────────────────────────────────────────────╯

Solution:
Combine to one cohesive display.

---

Problem:
You>  /explore
Directory to explore [.]

Solution:
Don't prompt, just explore the current directory or the passed directory.

---

Problem:
agent broken if user answers no, keeps trying to apply changes

Solution:
Research agent routing to understand problem. Steps to reproduce and added context needed.

---

Problem:
Using coding assistant for research query.
BAD ROUTING -- EG:
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

"Both Edsger Dijkstra and Alan Turing are renowned computer scientists who made significant contributions to the field."

Solution:
Research routing to understand why code assistant is used for research task.

----

Problem:
Not using correct provider models. We should default to instruct models because they're better with tools.
Cerebras not defaulted to instruct model. Currently defaults to llama3.1-8b.

Solution:
Discuss pros / cons of models and if this is configured correctly or should change.

---

Problem:
There are 2 very similar (or identical) explore commands: /context explore, /explore -- why??

Solution:
Research code execution to understand the distinction and if further action is required.

---

Problem:
Unneeded, extra prompt after invoking /agent: Start agent? [y/n] (y): y

Solution:
Discuss, and remove if not needed.

---

Problem:
duplicated commands in /help list:
│ System               │                             │
│   /quit              │ Exit the CLI                │
│   /exit              │ Exit the CLI    

Solution:
|  /quit or /exit      | Exist the CLI  

