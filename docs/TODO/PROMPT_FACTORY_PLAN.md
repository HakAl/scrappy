# Stateless Prompt Factory Plan

## Problem Statement

Current prompt generation is:
- **Scattered**: 3+ prompt builders with overlapping concerns
- **Stateful**: Builders hold context, tool registries, file system dependencies
- **Mode-blind**: Same aggressive tool-calling prompts used for agent AND chat scenarios
- **Hard to test**: Requires mocking context, tool registries, file system

## Goal

Create a **stateless prompt factory** that:
1. Takes all required data as input (no internal state)
2. Returns appropriate prompts based on mode and context
3. Follows SOLID principles and protocol-first design
4. Is trivially testable with pure function calls

---

## Existing Prompt Builders Analysis

### 1. `src/task_router/strategies/prompt_builder.py` (PromptBuilder)

**Used by**: `ResearchExecutor`

**State**: `_tool_descriptions_provider` (callable)

**Methods**:
- `build_system_prompt(has_tools)` - Research system prompt with tool instructions
- `build_research_prompt(task, context_summary)` - User prompt with tool hints

**Problem**: Always includes aggressive tool-calling instructions when `has_tools=True`, even for simple questions that don't need tools.

**Maps to**: `PromptMode.RESEARCH` with `ResearchSubtype.CODEBASE` or `GENERAL`

---

### 2. `src/cli/research_prompt_builder.py` (ResearchPromptBuilder)

**Used by**: CLI smart query functionality (`smart_query.py`)

**State**: None (already nearly stateless)

**Methods**:
- `build(query, classification, research_results, project_summary)` - User prompt with research context
- `get_system_prompt()` - Simple system prompt

**Maps to**: Could be a specialized user prompt builder, or merged into factory

---

### 3. `src/agent/system_prompt_builder.py` (SystemPromptBuilder)

**Used by**: `AgentExecutor`, `CodeAgent`

**State**: `context`, `tool_registry`, `_custom_sections`, `_section_overrides`

**Methods**:
- `build(task, use_native_tools)` - Full agent system prompt

**Sections built**:
- Core identity
- Platform (Windows cmd.exe vs Unix)
- Project type (Python, Java, Node.js, etc.)
- Codebase structure
- Tools (from registry)
- Strategy, Efficiency, Completion, Safety rules

**Maps to**: `PromptMode.AGENT` - most complex, needs section extraction

---

## Full Scope Summary

### Files to CREATE

| File | Purpose |
|------|---------|
| `src/prompts/__init__.py` | Package exports |
| `src/prompts/protocols.py` | `Platform`, `ResearchSubtype`, `*PromptConfig`, `PromptFactoryProtocol` |
| `src/prompts/factory.py` | `PromptFactory` implementation |
| `src/prompts/sections.py` | Pure functions for prompt sections |
| `tests/prompts/test_prompt_factory.py` | Factory unit tests |
| `tests/prompts/test_sections.py` | Section function tests |

### Files to DELETE

| File | Reason |
|------|--------|
| `src/task_router/strategies/prompt_builder.py` | Replaced by `PromptFactory` |
| `src/agent/system_prompt_builder.py` | Replaced by `PromptFactory` |

### Files to MODIFY

| File | Changes |
|------|---------|
| `src/task_router/strategies/research_executor.py` | Inject `PromptFactory`, remove `PromptBuilder` import |
| `src/task_router/strategies/research_protocols.py` | Remove `PromptBuilderProtocol`, add `PromptFactoryProtocol` import |
| `src/agent/core.py` | Replace `SystemPromptBuilder` with `PromptFactory` |
| `src/agent/protocols.py` | Remove unused `PromptBuilderProtocol` |
| `src/agent/__init__.py` | Remove `PromptBuilderProtocol` export |

### Test Files to DELETE

| File | Reason |
|------|--------|
| `tests/task_router/test_prompt_builder.py` | Tests deleted `PromptBuilder` |
| `tests/test_prompt_builder.py` | Tests deleted `SystemPromptBuilder` |

### Test Files to MODIFY

| File | Changes |
|------|---------|
| `tests/protocol_conformance/test_agent_conformance.py` | Remove `PromptBuilderProtocol` tests |

### Test Files to KEEP (unchanged)

| File | Notes |
|------|-------|
| `tests/cli/test_prompt_builder.py` | Tests `ResearchPromptBuilder` (kept) |
| `tests/cli/test_prompt_display.py` | Unrelated to prompt building |
| `tests/orchestrator/test_prompt_augmenter.py` | Different concern |

### Files to KEEP (no changes)

| File | Reason |
|------|--------|
| `src/cli/research_prompt_builder.py` | Different concern (result formatting) |
| `src/cli/smart_query.py` | Uses `ResearchPromptBuilder` (kept) |

### Consumers Summary

| Consumer | Current Dependency | New Dependency |
|----------|-------------------|----------------|
| `ResearchExecutor` | `PromptBuilder` + `PromptBuilderProtocol` | `PromptFactory` + `PromptFactoryProtocol` |
| `CodeAgent.run()` | `SystemPromptBuilder` | `PromptFactory` |
| `smart_query.py` | `ResearchPromptBuilder` | `ResearchPromptBuilder` (unchanged) |

---

## Consolidation Strategy

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

**Reusable sections** (pure functions):
- `platform_section(Platform)` - from SystemPromptBuilder
- `project_section(project_type)` - from SystemPromptBuilder
- `tool_format_section(tools, use_json)` - from both
- `codebase_hint_section(files, dirs)` - from PromptBuilder

---

## Architecture

### Core Types

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

class Platform(Enum):
    WINDOWS = "windows"
    UNIX = "unix"

class ResearchSubtype(Enum):
    CODEBASE = "codebase"
    GENERAL = "general"

@dataclass(frozen=True)
class ChatPromptConfig:
    """Minimal config for chat mode - no tools, direct answers."""
    pass

@dataclass(frozen=True)
class AgentPromptConfig:
    """Config for agent mode with full tool access."""
    platform: Platform
    tool_descriptions: str
    use_native_tools: bool = False
    project_type: Optional[str] = None
    codebase_structure: Optional[str] = None

@dataclass(frozen=True)
class ResearchPromptConfig:
    """Config for research mode - tools depend on subtype."""
    subtype: ResearchSubtype
    tool_descriptions: Optional[str] = None
    context_summary: Optional[str] = None
    extracted_files: tuple[str, ...] = ()
    extracted_directories: tuple[str, ...] = ()
```

### Factory Protocol

```python
class PromptFactoryProtocol(Protocol):
    """Stateless prompt generation with mode-specific methods."""

    # Chat mode - simplest, no tools
    def create_chat_system_prompt(self) -> str: ...
    def create_chat_user_prompt(self, query: str) -> str: ...

    # Agent mode - full tools, iterative
    def create_agent_system_prompt(self, config: AgentPromptConfig) -> str: ...
    def create_agent_user_prompt(self, task: str, config: AgentPromptConfig) -> str: ...

    # Research mode - tools depend on subtype
    def create_research_system_prompt(self, config: ResearchPromptConfig) -> str: ...
    def create_research_user_prompt(self, query: str, config: ResearchPromptConfig) -> str: ...
```

### Mode-Specific Behavior

| Mode | System Prompt | User Prompt | Tool Instructions |
|------|--------------|-------------|-------------------|
| CHAT | "You are a helpful assistant" | Just the query | None |
| AGENT | Platform + project + tools + strategy | Task + context | Full JSON format |
| RESEARCH (codebase) | Codebase tools + hints | Query + file hints | Yes - focused |
| RESEARCH (general) | Simple or web-only | Just the query | Minimal or none |

---

## Implementation Plan

### Step 1: Define Types and Protocol

**File**: `src/prompts/protocols.py`

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

class Platform(Enum):
    WINDOWS = "windows"
    UNIX = "unix"

class ResearchSubtype(Enum):
    CODEBASE = "codebase"
    GENERAL = "general"

@dataclass(frozen=True)
class ChatPromptConfig:
    """Config for chat mode - no fields needed."""
    pass

@dataclass(frozen=True)
class AgentPromptConfig:
    """Config for agent mode with tools."""
    platform: Platform
    tool_descriptions: str
    use_native_tools: bool = False
    project_type: Optional[str] = None
    codebase_structure: Optional[str] = None

@dataclass(frozen=True)
class ResearchPromptConfig:
    """Config for research mode."""
    subtype: ResearchSubtype
    tool_descriptions: Optional[str] = None
    context_summary: Optional[str] = None
    extracted_files: tuple[str, ...] = ()
    extracted_directories: tuple[str, ...] = ()

class PromptFactoryProtocol(Protocol):
    """Stateless prompt generation."""

    def create_chat_system_prompt(self) -> str: ...
    def create_chat_user_prompt(self, query: str) -> str: ...

    def create_agent_system_prompt(self, config: AgentPromptConfig) -> str: ...
    def create_agent_user_prompt(self, task: str, config: AgentPromptConfig) -> str: ...

    def create_research_system_prompt(self, config: ResearchPromptConfig) -> str: ...
    def create_research_user_prompt(self, query: str, config: ResearchPromptConfig) -> str: ...
```

### Step 2: Implement Stateless Factory

**File**: `src/prompts/factory.py`

```python
from .protocols import (
    AgentPromptConfig,
    ResearchPromptConfig,
    ResearchSubtype,
)
from .sections import (
    platform_section,
    project_section,
    codebase_structure_section,
    tool_format_section,
    strategy_section,
    efficiency_section,
    completion_section,
    safety_section,
    codebase_hint_section,
)

class PromptFactory:
    """Stateless prompt factory - all data passed via config."""

    # === Chat Mode ===

    def create_chat_system_prompt(self) -> str:
        """Simple chat - NO tool instructions."""
        return "You are a helpful assistant. Answer questions directly and concisely."

    def create_chat_user_prompt(self, query: str) -> str:
        """Chat user prompt - just the query."""
        return query

    # === Agent Mode ===

    def create_agent_system_prompt(self, config: AgentPromptConfig) -> str:
        """Full agent with tools and behavioral guidelines."""
        sections = [
            "You are a software development assistant with access to file system tools.",
            platform_section(config.platform),
            project_section(config.project_type),
            codebase_structure_section(config.codebase_structure),
            f"## Available Tools\n\n{config.tool_descriptions}",
            tool_format_section(use_json=not config.use_native_tools),
            strategy_section(),
            efficiency_section(),
            completion_section(),
            safety_section(),
        ]
        return "\n\n".join(filter(None, sections))

    def create_agent_user_prompt(self, task: str, config: AgentPromptConfig) -> str:
        """Agent user prompt - task with context."""
        return f"Please complete this task: {task}"

    # === Research Mode ===

    def create_research_system_prompt(self, config: ResearchPromptConfig) -> str:
        """Research prompt - tools depend on subtype."""
        if config.subtype == ResearchSubtype.GENERAL:
            if not config.tool_descriptions:
                return "You are a helpful assistant. Answer the question directly."
            return self._general_research_prompt(config)
        else:
            return self._codebase_research_prompt(config)

    def create_research_user_prompt(self, query: str, config: ResearchPromptConfig) -> str:
        """Research user prompt - query with hints."""
        parts = [f"User Request:\n{query}"]

        if config.context_summary:
            parts.append(f"\nProject Context:\n{config.context_summary}")

        if config.subtype == ResearchSubtype.CODEBASE:
            hint = codebase_hint_section(config.extracted_files, config.extracted_directories)
            if hint:
                parts.append(hint)

        parts.append("\nRespond appropriately. If information is needed, use a tool first.")
        return "\n".join(parts)

    def _general_research_prompt(self, config: ResearchPromptConfig) -> str:
        """General research with optional web tools."""
        return f"""You are a helpful research assistant.

{config.tool_descriptions}

{tool_format_section()}"""

    def _codebase_research_prompt(self, config: ResearchPromptConfig) -> str:
        """Codebase research with file/search tools."""
        return f"""You are a helpful research assistant with access to codebase tools.

{config.tool_descriptions}

{tool_format_section()}

Use search_code, read_file, or list_directory to find information in the codebase."""
```

### Step 3: Create Pure Section Functions

**File**: `src/prompts/sections.py`

```python
"""Pure functions for building prompt sections."""
from typing import Optional, Tuple
from .protocols import Platform

def platform_section(platform: Platform) -> str:
    """Generate platform-specific instructions."""
    if platform == Platform.WINDOWS:
        return """## Platform: Windows (cmd.exe)

- Use cmd.exe commands: mkdir, copy, del, dir
- Do NOT use PowerShell cmdlets
- Paths use backslashes"""
    return """## Platform: Unix/Linux

- Use standard Unix commands: mkdir -p, cp, rm, ls"""

def project_section(project_type: Optional[str]) -> str:
    """Generate project-type-specific instructions."""
    if not project_type:
        return ""
    sections = {
        "python": "## Project: Python\n\nUse pip, pytest, venv",
        "nodejs": "## Project: Node.js\n\nUse npm, package.json",
        "java": "## Project: Java\n\nUse Maven/Gradle",
        "go": "## Project: Go\n\nUse go mod, go test",
        "rust": "## Project: Rust\n\nUse Cargo",
    }
    return sections.get(project_type, "")

def codebase_structure_section(structure: Optional[str]) -> str:
    """Generate codebase structure section."""
    if not structure:
        return ""
    return f"## Codebase Structure\n\n{structure}"

def tool_format_section(use_json: bool = True) -> str:
    """Generate tool calling format instructions."""
    if not use_json:
        return ""
    return '''## Tool Format

To use a tool, respond with:
```json
{"tool": "tool_name", "parameters": {"param": "value"}}
```'''

def strategy_section() -> str:
    return """## Strategy

Prefer write_file over scaffolding tools (curl, npm create).
Direct file creation is more reliable and predictable."""

def efficiency_section() -> str:
    return """## Efficiency

Skip redundant operations. Reuse information already gathered.
Don't re-read files you've already seen in this conversation."""

def completion_section() -> str:
    return """## Completion

Mark task complete when primary goal is done.
Don't add optional extras unless explicitly requested."""

def safety_section() -> str:
    return """## Safety

Use JSON with lowercase true/false (not Python True/False).
Never write empty files. Make incremental, careful changes."""

def codebase_hint_section(
    extracted_files: Tuple[str, ...],
    extracted_directories: Tuple[str, ...]
) -> str:
    """Generate hints for codebase queries."""
    hints = []

    if extracted_files:
        hints.append(f"Detected file reference(s): {', '.join(extracted_files)}")

    if extracted_directories:
        hints.append(f"Detected directory reference(s): {', '.join(extracted_directories)}")

    if not hints:
        return ""

    return "\n" + "\n".join(hints)
```

---

## Migration Plan

### Phase 1: Add New Module (Non-Breaking)

1. Create `src/prompts/` package with:
   - `protocols.py` - Types and protocols
   - `factory.py` - PromptFactory implementation
   - `sections.py` - Pure helper functions (extracted from existing builders)
   - `config_builder.py` - Convenience builders

2. Add comprehensive tests in `tests/prompts/`:
   - `test_prompt_factory.py` - Unit tests for each mode
   - `test_sections.py` - Tests for pure functions
   - `test_config_builder.py` - Tests for builders

### Phase 2: Migrate PromptBuilder (Research)

**Target**: `src/task_router/strategies/prompt_builder.py`

1. Update `ResearchExecutor` to inject `PromptFactory`:
   ```python
   def __init__(
       self,
       ...
       prompt_factory: Optional[PromptFactoryProtocol] = None,
   ):
       self._prompt_factory = prompt_factory or PromptFactory()
   ```

2. Replace `PromptBuilder` usage:
   ```python
   def execute(self, task):
       subtype = self._subclassifier.classify(task.original_input, ...)

       config = PromptConfig(
           mode=PromptMode.RESEARCH,
           research_subtype=subtype,
           tools_available=tuple(self._tool_bundle.get_tool_names()),
           tool_descriptions=self._tool_bundle.get_tool_descriptions(),
           context_summary=self._get_context_summary(),
       )

       system_prompt = self._prompt_factory.create_system_prompt(config)
       user_prompt = self._prompt_factory.create_user_prompt(task.original_input, config)
   ```

3. Delete `src/task_router/strategies/prompt_builder.py` (not deprecate - per CLAUDE.md)

### Phase 3: Migrate SystemPromptBuilder (Agent)

**Target**: `src/agent/system_prompt_builder.py`

1. Extract pure section functions to `src/prompts/sections.py`:
   - `_build_platform_section()` -> `platform_section(Platform)`
   - `_build_project_section()` -> `project_section(project_type)`
   - `_build_codebase_structure_section()` -> `codebase_structure_section(file_index)`

2. Update `AgentExecutor` to use `PromptFactory`:
   ```python
   config = PromptConfig(
       mode=PromptMode.AGENT,
       platform=Platform.WINDOWS if is_windows() else Platform.UNIX,
       project_type=context.get_project_type(),
       tools_available=tuple(tool_registry.list_tools()),
       tool_descriptions=tool_registry.generate_descriptions(),
       codebase_structure=context.get_structure_summary(),
   )
   system_prompt = self._prompt_factory.create_system_prompt(config)
   ```

3. Delete `src/agent/system_prompt_builder.py`

### Phase 4: Keep ResearchPromptBuilder (CLI)

**Target**: `src/cli/research_prompt_builder.py`

**Decision**: Keep this builder - it handles **result formatting**, not prompt generation.

1. No changes needed - different responsibility than PromptFactory
2. `smart_query.py` continues using it for formatting research results

### Phase 5: Update Protocol Definitions and Exports

**Existing protocols to update/remove**:

1. `src/task_router/strategies/research_protocols.py:15` - `PromptBuilderProtocol`
   - Replace with import from `src/prompts/protocols.py`
   - Or inline the new `PromptFactoryProtocol` usage

2. `src/agent/protocols.py:140` - `PromptBuilderProtocol`
   - This is a DIFFERENT protocol (has `build(task, system_prompt)`)
   - Evaluate: is this used anywhere? If not, remove it
   - If used, update to use new factory or keep separate

3. `src/agent/__init__.py:21` - Exports `PromptBuilderProtocol`
   - Update export to new protocol or remove

**Protocol conformance tests to update**:

- `tests/protocol_conformance/test_agent_conformance.py`
  - Tests for `PromptBuilderProtocol.build`, `add_context`, `clear_context`
  - Update to test new `PromptFactoryProtocol`

### Final State

```
BEFORE                              AFTER
------                              -----
prompt_builder.py          -->      (deleted)
system_prompt_builder.py   -->      (deleted)
research_prompt_builder.py -->      (kept - different concern)

research_protocols.py:
  PromptBuilderProtocol    -->      (import from src/prompts or inline)

agent/protocols.py:
  PromptBuilderProtocol    -->      (evaluate usage, likely remove)

agent/__init__.py:
  PromptBuilderProtocol    -->      (update or remove export)

                                    src/prompts/
                                      __init__.py
                                      protocols.py
                                      factory.py
                                      sections.py
```

---

## Testing Strategy

### Unit Tests (Pure Functions)

```python
from src.prompts.factory import PromptFactory
from src.prompts.protocols import (
    AgentPromptConfig,
    ResearchPromptConfig,
    Platform,
    ResearchSubtype,
)

class TestChatMode:
    def test_chat_system_prompt_has_no_tool_instructions(self):
        factory = PromptFactory()
        prompt = factory.create_chat_system_prompt()

        assert "tool" not in prompt.lower()
        assert "json" not in prompt.lower()

    def test_chat_user_prompt_is_just_query(self):
        factory = PromptFactory()
        prompt = factory.create_chat_user_prompt("What is Python?")

        assert prompt == "What is Python?"


class TestAgentMode:
    def test_agent_system_prompt_has_tool_instructions(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_descriptions="read_file: Read a file",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "read_file" in prompt
        assert "json" in prompt.lower()

    def test_agent_system_prompt_includes_platform(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.WINDOWS,
            tool_descriptions="tools here",
        )
        prompt = factory.create_agent_system_prompt(config)

        assert "Windows" in prompt
        assert "cmd.exe" in prompt

    def test_agent_native_tools_skips_json_format(self):
        factory = PromptFactory()
        config = AgentPromptConfig(
            platform=Platform.UNIX,
            tool_descriptions="tools here",
            use_native_tools=True,
        )
        prompt = factory.create_agent_system_prompt(config)

        assert '{"tool":' not in prompt


class TestResearchMode:
    def test_research_general_without_tools_is_simple(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.GENERAL,
            tool_descriptions=None,
        )
        prompt = factory.create_research_system_prompt(config)

        assert "tool" not in prompt.lower()
        assert "helpful assistant" in prompt.lower()

    def test_research_codebase_has_tool_instructions(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            tool_descriptions="search_code: Search in codebase",
        )
        prompt = factory.create_research_system_prompt(config)

        assert "search_code" in prompt
        assert "json" in prompt.lower()

    def test_research_user_prompt_includes_file_hints(self):
        factory = PromptFactory()
        config = ResearchPromptConfig(
            subtype=ResearchSubtype.CODEBASE,
            extracted_files=("src/main.py", "tests/test_main.py"),
        )
        prompt = factory.create_research_user_prompt("explain main.py", config)

        assert "src/main.py" in prompt
        assert "tests/test_main.py" in prompt


class TestSections:
    """Tests for pure section functions."""

    def test_platform_section_windows(self):
        from src.prompts.sections import platform_section
        result = platform_section(Platform.WINDOWS)
        assert "cmd.exe" in result
        assert "PowerShell" in result

    def test_project_section_python(self):
        from src.prompts.sections import project_section
        result = project_section("python")
        assert "pip" in result
        assert "pytest" in result

    def test_project_section_unknown_returns_empty(self):
        from src.prompts.sections import project_section
        result = project_section("unknown_lang")
        assert result == ""
```

---

## Design Decisions (Resolved)

### D1: Mode-Specific Config Types (was Q7)

**Decision**: Use separate config types per mode instead of one generic config.

```python
@dataclass(frozen=True)
class ChatPromptConfig:
    """Minimal config for chat mode."""
    pass  # No fields needed

@dataclass(frozen=True)
class AgentPromptConfig:
    """Config for agent mode with tools."""
    platform: Platform
    tool_descriptions: str
    use_native_tools: bool = False
    project_type: Optional[str] = None
    codebase_structure: Optional[str] = None

@dataclass(frozen=True)
class ResearchPromptConfig:
    """Config for research mode."""
    subtype: ResearchSubtype
    tool_descriptions: Optional[str] = None  # None if no tools
    context_summary: Optional[str] = None
    extracted_files: tuple[str, ...] = ()
    extracted_directories: tuple[str, ...] = ()
```

**Factory methods**:
```python
class PromptFactory:
    def create_chat_system_prompt(self) -> str: ...
    def create_chat_user_prompt(self, query: str) -> str: ...

    def create_agent_system_prompt(self, config: AgentPromptConfig) -> str: ...
    def create_agent_user_prompt(self, task: str, config: AgentPromptConfig) -> str: ...

    def create_research_system_prompt(self, config: ResearchPromptConfig) -> str: ...
    def create_research_user_prompt(self, query: str, config: ResearchPromptConfig) -> str: ...
```

---

### D2: Missing Config Fields (was Q1)

**Decision**: Fields included in mode-specific configs above:
- `codebase_structure` -> `AgentPromptConfig.codebase_structure`
- `extracted_files` -> `ResearchPromptConfig.extracted_files`
- `extracted_directories` -> `ResearchPromptConfig.extracted_directories`

---

### D3: ResearchPromptBuilder Fate (was Q2)

**Decision**: Keep `ResearchPromptBuilder` separate.

It formats **research results** into prompts, which is a different concern than system/user prompt generation. The new factory handles system/user prompts; result formatting stays in `ResearchPromptBuilder`.

**Migration**: Phase 4 updated - keep `research_prompt_builder.py`, don't delete.

---

### D4: Native Tool Calling (was Q3)

**Decision**: Add `use_native_tools: bool` to `AgentPromptConfig`.

When `True`, skip JSON format instructions (provider handles tool calling natively).

---

### D5: Custom Sections/Overrides (was Q4)

**Decision**: Drop feature. Callers can append to generated prompt if needed.

Keep factory simple and stateless.

---

### D6: Context Exploration (was Q5)

**Decision**: Caller (agent/executor) is responsible for exploring context before building config.

**Current flow** in `CodeAgent.run()`:
```python
# SystemPromptBuilder auto-explores inside build()
prompt_builder = SystemPromptBuilder(context=self.orch.context, ...)
system_prompt = prompt_builder.build(task=task, ...)
```

**New flow** in `CodeAgent.run()`:
```python
# Agent ensures exploration BEFORE building config
context = self.orch.context
if not context.is_explored():
    context.explore()

# Build config with pre-computed data
config = AgentPromptConfig(
    platform=Platform.WINDOWS if context.get_platform() == "windows" else Platform.UNIX,
    project_type=context.get_project_type(),
    codebase_structure=self._format_codebase_structure(context.file_index),
    tool_descriptions=self.tool_registry.generate_descriptions(),
    use_native_tools=use_native_tools,
)

# Factory is pure - no I/O
system_prompt = self._prompt_factory.create_agent_system_prompt(config)
```

**Same pattern for ResearchExecutor**:
```python
# Executor ensures context is ready
context_summary = self._get_context_summary()  # Already handles exploration

config = ResearchPromptConfig(
    subtype=research_subtype,
    tool_descriptions=self._tool_bundle.get_tool_descriptions(),
    context_summary=context_summary,
    extracted_files=tuple(task.extracted_files or []),
    extracted_directories=tuple(task.extracted_directories or []),
)

system_prompt = self._prompt_factory.create_research_system_prompt(config)
```

---

### D7: Strategy/Efficiency/Completion/Safety Sections (was Q6)

**Decision**: Include in `create_agent_system_prompt()`.

These are important behavioral guidelines for agent mode. Extract as pure functions in `sections.py`:
- `strategy_section()` -> "Prefer write_file over scaffolding tools"
- `efficiency_section()` -> "Skip redundant operations"
- `completion_section()` -> "Mark task complete when primary goal is done"
- `safety_section()` -> "Use JSON with lowercase true/false"

---

## Success Criteria

1. **Problem 2 Fixed**: CHAT mode queries get simple prompts without tool instructions
2. **Testable**: All prompt logic can be tested without mocks
3. **Stateless**: PromptFactory has no instance state
4. **SOLID Compliant**: Single responsibility, open for extension
5. **Backward Compatible**: Existing code continues to work during migration
