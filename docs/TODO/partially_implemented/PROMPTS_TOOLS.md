# Agent Tools Inventory

## Issues

  Tool Issues:

  4. No "think" or "scratchpad" tool - The agent has complete to end, but no explicit tool to pause and reason without
  taking action. Some agent frameworks include this.
  5. Research mode tool gating - CODEBASE research gets file tools, GENERAL gets web tools. If classification is wrong,
  the agent is stuck without the tools it needs.

## Architecture

- **Location:** `src/scrappy/agent_tools/tools/`
- **Base Protocol:** `ToolProtocol` in `tools/base.py`
- **Base Class:** `ToolBase` in `tools/base.py`
- **Registry:** `ToolRegistry` in `tools/registry.py`
- **Factory:** `create_default_registry()` in `registry_factory.py`

---

## Tools (17 Total)

### File Operations (4)
| Tool | Description | Parameters |
|------|-------------|------------|
| `read_file` | Read file contents | `path` |
| `write_file` | Write content to file | `path`, `content` |
| `list_files` | List files matching pattern | `directory?`, `pattern?` |
| `list_directory` | Show directory tree structure | `path?`, `depth?` |

### Git Operations (6)
| Tool | Description | Parameters |
|------|-------------|------------|
| `git_log` | View recent commits | `n?`, `file?` |
| `git_status` | Show repo status | `short?` |
| `git_diff` | Show changes | `ref?`, `file?` |
| `git_blame` | Show who changed each line | `file`, `lines?` |
| `git_show` | Show commit details | `commit` |
| `git_recent_changes` | Show last N commits with diffs | `n?` |

### Search (2)
| Tool | Description | Parameters |
|------|-------------|------------|
| `find_exact_text` | Exact text/pattern search (ripgrep/grep/findstr) | `pattern`, `file_pattern?`, `use_regex?`, `case_sensitive?`, `context_lines?` |
| `codebase_search` | Semantic code search by meaning | `query`, `max_tokens?` |

### Web (2)
| Tool | Description | Parameters |
|------|-------------|------------|
| `web_fetch` | Fetch content from URLs | `url`, `method?`, `headers?`, `body?`, `extract_text?`, `timeout?` |
| `web_search` | Search package registries (PyPI, npm, GitHub) | `registry`, `query` |

### Command Execution (1)
| Tool | Description | Parameters |
|------|-------------|------------|
| `run_command` | Execute shell command with security checks | `command` |

### Control (1)
| Tool | Description | Parameters |
|------|-------------|------------|
| `complete` | Signal task completion | `result` |

### Task Management (1)
| Tool | Description | Parameters |
|------|-------------|------------|
| `task` | Persistent task tracking via markdown | (various) |

---

## Core Data Structures

### ToolProtocol
```python
name: str                           # Unique identifier
description: str                    # Human-readable description
parameters: list[ToolParameter]     # Parameter definitions
execute(context, **kwargs) -> ToolResult
```

### ToolParameter
```python
name: str           # Parameter name
param_type: type    # Parameter type
description: str    # Parameter description
required: bool      # Whether required
default: object     # Default value
```

### ToolResult
```python
success: bool           # Success status
output: str             # Output string
error: Optional[str]    # Error message
metadata: dict          # Additional metadata
```

### ToolContext
```python
project_root: Path                          # Project root directory
dry_run: bool                               # Dry run mode
config: Optional[AgentConfig]               # Agent configuration
orchestrator: Optional[MemoryProvider]      # Memory access
semantic_search: Optional[SemanticSearchProtocol]
```

---

## Registry Factory Functions

| Function | Description |
|----------|-------------|
| `create_default_registry()` | Full registry with all 18 tools |
| `create_minimal_registry()` | Minimal registry with file tools only |

---

## File Locations

```
src/scrappy/agent_tools/
  tools/
    base.py              # ToolProtocol, ToolBase, ToolParameter, ToolResult
    registry.py          # ToolRegistry
    file_tools.py        # ReadFile, WriteFile, ListFiles, ListDirectory
    git_tools.py         # GitLog, GitStatus, GitDiff, GitBlame, GitShow, GitRecentChanges
    search_tools.py      # FindExactText
    semantic_search_tool.py  # SemanticSearch (codebase_search)
    web_tools.py         # WebFetch, WebSearch
    python_tools.py      # AnalyzePythonDependencies
    command_tool.py      # CommandTool (run_command)
    control_tools.py     # Complete
    task_tools.py        # Task
  protocols/
    __init__.py          # CommandSecurityProtocol, OutputParserProtocol, etc.
  registry_factory.py    # create_default_registry, create_minimal_registry
```

---

# Prompt Construction

## Overview

Prompts are built through a layered composition system:

```
User Input
    |
    v
Task Router (classify: AGENT, RESEARCH, CHAT)
    |
    +--[AGENT]-----> PromptFactory.create_agent_system_prompt()
    |                    |
    |                    v
    |                AgentContextFactory.build_context()
    |                    |
    |                    v
    |                PromptAugmenter.augment()
    |                    |
    |                    v
    |                Build messages: [system, user]
    |                    |
    |                    v
    |                LiteLLMService.completion_sync()
    |
    +--[RESEARCH]--> ResearchExecutor + ResearchLoop
    |
    +--[CHAT]------> Simple system prompt + user message
```

---

## System Prompts by Mode

### CHAT Mode
Simple Q&A without tools.
```
You are Scrappy, an intelligent coding assistant.
Guidelines:
- Answer questions directly and concisely
- When explaining code, use clear examples
- If you're unsure, say so rather than guessing
- For complex topics, break down your explanation into steps
- Use markdown formatting for code blocks
```

### AGENT Mode
Full tool-calling agent. System prompt composed from sections:

| Section | Content |
|---------|---------|
| Base role | Agent identity and capabilities |
| Platform | Windows cmd.exe vs Unix shell specifics |
| Project type | Python/Node/Java/Go/Rust package managers, testing |
| Codebase structure | Project layout info |
| Tools | Available tools and descriptions |
| Tool format | JSON response format (if not native tool calling) |
| Strategy | Prefer write_file over scaffolding |
| Efficiency | Skip redundant operations |
| Completion | Don't over-engineer |
| Safety | JSON lowercase true/false, test changes |
| Quality | Code standards |

### RESEARCH Mode
Two subtypes with different tool sets:
- **CODEBASE**: File system tools (read_file, search_code, git tools)
- **GENERAL**: Web tools (web_fetch, web_search)

---

## Prompt Section Builders

**Location:** `src/scrappy/prompts/sections.py`

| Function | Purpose |
|----------|---------|
| `platform_section(platform)` | Windows/Unix specific commands |
| `project_section(project_type)` | Language-specific instructions |
| `codebase_structure_section(structure)` | Project layout |
| `tool_format_section(use_json)` | JSON format for tool responses |
| `strategy_section()` | File creation preferences |
| `efficiency_section()` | Redundancy avoidance |
| `completion_section()` | Scope management |
| `safety_section()` | Error prevention |
| `quality_section()` | Code standards |
| `codebase_hint_section()` | Matched files/content hints |

---

## Context Augmentation

### AgentContextFactory
**Location:** `src/scrappy/agent/context_factory.py`

1. Filter tools based on semantic search readiness
2. Build passive RAG context (semantic search results)
3. Build search strategy section
4. Assemble: `base_prompt + search_strategy + passive_rag_context`

### PromptAugmenter
**Location:** `src/scrappy/orchestrator/prompt_augmenter.py`

Two-stage augmentation:
1. Augment with codebase context (if explored)
2. Prepend working memory (recent interactions)

**Order:** Working memory FIRST, then main prompt (recency = priority)

### Passive RAG
Semantic search results injected into system prompt:
- Code chunks with filepath, line numbers, content
- Token budget computed based on:
  - File references in task
  - Identifiers (CamelCase, snake_case)
  - Exploration keywords (how, where, what, why, explain)

---

## Tool Descriptions to LLM

**Location:** `src/scrappy/agent_tools/tools/registry.py`

### Human-readable format
```python
registry.generate_descriptions(numbered=True)
# Output:
# Available tools:
# 1. tool_name: Description with parameters
# 2. ...
```

### OpenAI-compatible schema
```python
registry.to_openai_schema()
# Output:
# [{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}]
```

### Expected response format
```python
registry.get_response_format()
# Output:
# {"thought": "reasoning", "action": "tool_name", "parameters": {...}, "is_complete": false}
```

---

## Message Construction

**Location:** `src/scrappy/orchestrator/delegation.py`

```python
messages = []
if system_prompt:
    messages.append({"role": "system", "content": system_prompt})
messages.append({"role": "user", "content": final_prompt})

# Sent to LiteLLMService.completion_sync(model, messages, max_tokens, temperature, tools?)
```

---

## Multi-Turn Conversation

**Location:** `src/scrappy/agent/agent_loop.py`

`state.messages` maintains full history:
```python
[
    {"role": "system", "content": "..."},
    {"role": "user", "content": "task"},
    {"role": "assistant", "content": "response1"},
    {"role": "user", "content": "..."},
    ...
]
```

On continuation, history reconstructed as:
```
Previous conversation:
ASSISTANT: response1
USER: ...
...

Based on the above, continue with the task...
```

---

## File Locations

```
src/scrappy/prompts/
  factory.py              # Main prompt generation
  protocols.py            # Protocol definitions, config dataclasses
  sections.py             # Individual section builders

src/scrappy/agent/
  agent_loop.py           # Agent loop with prompt handling
  context_factory.py      # Dynamic context building

src/scrappy/orchestrator/
  prompt_augmenter.py     # Augmentation logic
  delegation.py           # Message formatting and LLM delegation
  litellm_service.py      # Final provider communication

src/scrappy/cli/
  research_prompt_builder.py  # Smart query prompts

src/scrappy/agent_tools/tools/
  registry.py             # Tool description generation
```
