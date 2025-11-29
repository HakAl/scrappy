# Prompt Factory

`src/prompt/`

```
                    +------------------+
                    | PromptFactory    |  <-- Stateless, takes PromptConfig
                    +------------------+
                           |
         +-----------------+-----------------+
         |                 |                 |
    AGENT mode       RESEARCH mode      CHAT mode
         |                 |                 |
   (absorbs from    (absorbs from      (new, simple)
   SystemPromptBuilder)  PromptBuilder)
         |                 |
         v                 v
   +------------+    +------------+
   | Sections:  |    | Sections:  |
   | - platform |    | - tools    |
   | - project  |    | - hints    |
   | - tools    |    +------------+
   | - strategy |
   +------------+
```

### Dependencies

- src/agent
- src/cli
- src/orchestrator
- src/task_router

### Mode-Specific Behavior

| Mode | System Prompt | User Prompt | Tool Instructions |
|------|--------------|-------------|-------------------|
| CHAT | "You are a helpful assistant" | Just the query | None |
| AGENT | Platform + project + tools + strategy | Task + context | Full JSON format |
| RESEARCH (codebase) | Codebase tools + hints | Query + file hints | Yes - focused |
| RESEARCH (general) | Simple or web-only | Just the query | Minimal or none |