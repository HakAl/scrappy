## Issues 

---
shift selection is messed up, can't 'unselect' once a point is selected.
---

===

Unconfirmed / Mixed Behavior / Potential New Features
===

---
textual dev console
https://github.com/Textualize/textual/#dev-console

How do you debug an app in the terminal that is also running in the terminal?

The textual-dev package supplies a dev console that connects to your application from another terminal. 
In addition to system messages and events, your logged messages and print statements will appear in the dev console.
---
---
textual command palette
https://github.com/Textualize/textual/?tab=readme-ov-file#command-palette

Textual apps have a fuzzy search command palette. Hit ctrl+p to open the command palette.

It is easy to extend the command palette with custom commands for your application.
---

---
Memory Beads
https://github.com/steveyegge/beads
Beads acts as long-term memory: It is a graph-based issue tracker that lives inside the git repo (in a hidden .beads folder).[1]
It’s machine-readable first: Unlike Jira or GitHub Issues, Beads is designed to be read and written by LLMs via a CLI, not a web UI.
Context Efficiency: Instead of dumping the whole project history into the context window, 
your agent can just run bd ready --json to see exactly what tasks are unblocked and waiting.
---