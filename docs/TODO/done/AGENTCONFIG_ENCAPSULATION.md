# AgentConfig Encapsulation Refactor

## Problem

`AgentConfig` is a `@dataclass` with **public mutable fields** that violates encapsulation principles:

```python
@dataclass
class AgentConfig(BaseConfig):
    max_file_read_size: int = 10000  # PUBLIC - can be modified without validation
    command_timeout: int = 300       # PUBLIC - can be modified without validation
    # ... 20+ more public fields
```

### Issues with Current Design

1. **No validation on write** - Can set invalid values:
   ```python
   config.command_timeout = -100  # Allowed! No error until validate() called
   ```

2. **Validation is optional** - `validate()` must be explicitly called:
   ```python
   config = AgentConfig()
   config.max_file_read_size = -50  # Invalid but no error
   # ... code runs with invalid config ...
   config.validate()  # Only NOW does it error
   ```

3. **Magic numbers duplicated** - Defaults are hardcoded in AgentConfig:
   ```python
   # AgentConfig has:
   command_timeout: int = 300

   # CommandTool has:
   timeout: int = 30  # DIFFERENT VALUE!
   ```

4. **Violates encapsulation** - Internal representation exposed

5. **Blocks architectural improvements** - Can't refactor without breaking all clients

## Why This Blocks Agent Loop Cleanup

The agent loop cleanup requires:
```python
def create_default_registry(
    command_timeout: int = ???,
    max_command_output: int = ???,
    dangerous_commands: list[str] = ???
) -> ToolRegistry:
```

We need to get these values from `AgentConfig`, but:
- We can't pass the whole config (circular import)
- We can't use constants only (config must be customizable)
- We can't access public fields (violates encapsulation)

**Therefore: We must add getters first.**

## Solution

### Step 1: Add Constants (DONE)

Created `src/agent_tools/constants.py` with all defaults:
```python
DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_MAX_COMMAND_OUTPUT = 10000
# ... etc
```

### Step 2: Refactor AgentConfig to Use Getters/Setters

```python
@dataclass
class AgentConfig(BaseConfig):
    # Private fields with constants as defaults
    _max_file_read_size: int = field(default=DEFAULT_MAX_FILE_READ_SIZE, init=False, repr=False)
    _command_timeout: int = field(default=DEFAULT_COMMAND_TIMEOUT, init=False, repr=False)
    # ... all other fields as private

    # Getters
    def get_max_file_read_size(self) -> int:
        return self._max_file_read_size

    def get_command_timeout(self) -> int:
        return self._command_timeout

    # Setters with validation
    def set_max_file_read_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"max_file_read_size must be positive, got {value}")
        self._max_file_read_size = value

    def set_command_timeout(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"command_timeout must be positive, got {value}")
        self._command_timeout = value

    # ... getters/setters for all 26 fields
```

**Benefits:**
- Validation happens immediately on write
- Can't forget to validate
- Encapsulation - can change internals without breaking clients
- Single responsibility - each setter validates one concern

### Step 3: Update All Code to Use Getters/Setters

**Production code: 26 occurrences across 7 files**
- `src/agent/agent_loop.py` - 8 occurrences
- `src/agent_tools/tools/git_tools.py` - 7 occurrences
- `src/agent_tools/tools/file_tools.py` - 5 occurrences
- `src/agent/core.py` - 2 occurrences
- `src/agent/provider_strategy.py` - 2 occurrences
- `src/agent_tools/tools/search_tools.py` - 1 occurrence
- `src/context/config_loader.py` - 1 occurrence

**Test code: 36 occurrences across 8 files**
- `tests/cli/test_phase6_theme_integration.py` - 9 occurrences
- `tests/agent_tools/test_git_tools.py` - 8 occurrences
- `tests/agent/test_provider_strategy.py` - 6 occurrences
- `tests/agent_tools/test_file_tools.py` - 5 occurrences
- `tests/agent/test_agent_loop.py` - 3 occurrences
- `tests/test_command_tool.py` - 2 occurrences
- `tests/agent_tools/test_search_tools.py` - 2 occurrences
- `tests/agent/test_agent.py` - 1 occurrence

**Total: 62 occurrences to update**

Changes needed:
```python
# BEFORE
max_size = context.config.max_file_read_size

# AFTER
max_size = context.config.get_max_file_read_size()
```

```python
# BEFORE (setter)
config.command_timeout = 500

# AFTER (setter)
config.set_command_timeout(500)
```

### Step 4: Remove Standalone validate() Method

Once all fields use setters with validation, the standalone `validate()` method is redundant and should be removed.

## All Fields Requiring Getters/Setters

### File Operations (5 fields)
- `max_file_read_size` - int
- `max_file_listing` - int
- `max_directory_tree_lines` - int
- `skip_directories` - Set[str]
- `allowed_hidden_files` - Set[str]

### Command Execution (4 fields)
- `command_timeout` - int
- `max_command_output` - int
- `dangerous_commands` - List[str]
- `long_running_commands` - List[str]
- `interactive_commands` - List[str]

### Code Search (1 field)
- `max_search_results` - int

### Git Operations (7 fields)
- `git_timeout` - int
- `git_diff_timeout` - int
- `max_git_diff_size` - int
- `max_git_blame_size` - int
- `max_git_show_size` - int
- `max_recent_changes_size` - int
- `max_recent_commits` - int

### Display/UI (3 fields)
- `audit_log_result_truncation` - int
- `result_display_truncation` - int
- `write_preview_truncation` - int

### LLM Settings (2 fields)
- `default_max_tokens` - int
- `default_temperature` - float

### Provider Preferences (2 fields)
- `planner_preferences` - List[str]
- `executor_preferences` - List[str]

### Completion Validation (1 field)
- `meaningful_actions` - List[str]

**Total: 26 fields requiring getters/setters**

## Implementation Checklist

### Phase 1: Refactor AgentConfig
- [ ] Convert all 26 public fields to private fields (`_field_name`)
- [ ] Add 26 getter methods (`get_field_name()`)
- [ ] Add 26 setter methods with validation (`set_field_name(value)`)
- [ ] Use constants from `agent_tools.constants` as defaults
- [ ] Remove standalone `validate()` method

### Phase 2: Update Production Code (26 occurrences, 7 files)
- [ ] `src/agent/agent_loop.py` - 8 reads
- [ ] `src/agent_tools/tools/git_tools.py` - 7 reads
- [ ] `src/agent_tools/tools/file_tools.py` - 5 reads
- [ ] `src/agent/core.py` - 2 reads
- [ ] `src/agent/provider_strategy.py` - 2 reads
- [ ] `src/agent_tools/tools/search_tools.py` - 1 read
- [ ] `src/context/config_loader.py` - 1 read

### Phase 3: Update Test Code (36 occurrences, 8 files)
- [ ] `tests/cli/test_phase6_theme_integration.py` - 9 uses (reads + writes)
- [ ] `tests/agent_tools/test_git_tools.py` - 8 uses
- [ ] `tests/agent/test_provider_strategy.py` - 6 uses
- [ ] `tests/agent_tools/test_file_tools.py` - 5 uses
- [ ] `tests/agent/test_agent_loop.py` - 3 uses
- [ ] `tests/test_command_tool.py` - 2 uses
- [ ] `tests/agent_tools/test_search_tools.py` - 2 uses
- [ ] `tests/agent/test_agent.py` - 1 use

### Phase 4: Find Other Setter Uses
- [ ] Search for `config\..*\s*=` pattern to find all write operations
- [ ] Update to use setter methods

### Phase 5: Run Tests
- [ ] Run full test suite
- [ ] Verify no regressions
- [ ] Verify validation is working (try setting invalid values)

## Risk Assessment

### Low Risk
- Mechanical refactor - straightforward search/replace pattern
- Type checker will catch most mistakes
- Tests will catch runtime issues

### Medium Risk
- Large number of files to update (15 files total)
- Tests might rely on direct field access
- Possible missed occurrences if grep pattern incomplete

### High Risk
- May uncover other code that mutates config in unexpected ways
- Could expose bugs where invalid values were being set silently

## Estimated Effort

- **Getters/Setters:** ~2 hours (26 fields × 3 methods each = 78 methods)
- **Update production code:** ~1 hour (26 occurrences, mostly mechanical)
- **Update test code:** ~1 hour (36 occurrences, mostly mechanical)
- **Find setter uses:** ~30 min (search and update)
- **Testing/verification:** ~1 hour

**Total: ~5-6 hours**

## After This Refactor

Once complete, we can proceed with Agent Loop Cleanup:

```python
# In registry_factory.py
def create_default_registry(
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
    max_command_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
    dangerous_commands: list[str] = None,
    ...
) -> ToolRegistry:
    # No circular import - just primitive values
    registry.register(CommandTool(
        timeout=command_timeout,
        max_output=max_command_output,
        dangerous_patterns=dangerous_commands or []
    ))
```

```python
# In core.py
def _create_default_tool_registry(self):
    return create_default_registry(
        command_timeout=self.config.get_command_timeout(),
        max_command_output=self.config.get_max_command_output(),
        dangerous_commands=self.config.get_dangerous_commands(),
    )
```

**Clean. No hacks. Proper encapsulation.**

## Alternative: Property Decorators

Instead of explicit getters/setters, we could use `@property`:

```python
@dataclass
class AgentConfig(BaseConfig):
    _command_timeout: int = field(default=DEFAULT_COMMAND_TIMEOUT, init=False, repr=False)

    @property
    def command_timeout(self) -> int:
        return self._command_timeout

    @command_timeout.setter
    def command_timeout(self, value: int) -> None:
        if value <= 0:
            raise ValueError(f"command_timeout must be positive, got {value}")
        self._command_timeout = value
```

**Pros:**
- More Pythonic
- Less code change (no need to add `()` to reads)
- Standard Python pattern

**Cons:**
- Looks like field access (hides that validation is happening)
- Slightly less explicit

**Decision: Use `@property` decorators** - more Pythonic, less code change, standard pattern.

This means only WRITE operations need updating:
```python
# Reads stay the same
max_size = context.config.max_file_read_size  # No change needed

# Writes change
config.command_timeout = 500  # Still works, but now validated
```

This reduces the scope to **just finding setter uses** - far less work!
