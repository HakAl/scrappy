# Code Duplication and Architectural Issues

> Last Updated: 2025-11-20
> Status: Comprehensive analysis completed

---

## Executive Summary

This codebase has **significant architectural debt** that violates SOLID principles outlined in CLAUDE.md. The good news: excellent protocol definitions exist in `src/orchestrator/protocols.py`, `src/cli/protocols.py`, and `src/agent/protocols.py`. They just need to be consistently applied, and duplicated infrastructure needs consolidation.

**Key Findings:**
- Multiple god classes (AgentOrchestrator: 875 lines, CodeAgent: 1,336 lines)
- CLI and Orchestrator share infrastructure with different implementations
- Name collisions (PromptBuilder, ContextManager exist in multiple places)
- Missing shared infrastructure (logging, config, persistence)
- Protocols defined but not consistently used as type hints

---

## 1. CRITICAL NAME COLLISIONS

### 1.1 PromptBuilder (TWO COMPLETELY DIFFERENT CLASSES)

**Problem:** Same class name, zero overlap in functionality

| Class | Location | Purpose | Lines |
|-------|----------|---------|-------|
| PromptBuilder | `src/cli/prompt_builder.py` | Smart query classification context + research results | 121 |
| PromptBuilder | `src/agent/prompt_builder.py` | Agent system prompts with platform/project detection | 374 |

**Impact:** Confusing imports, unclear responsibilities

**Solution:**
```python
# Rename immediately
src/cli/prompt_builder.py → src/cli/research_prompt_builder.py (ResearchPromptBuilder)
src/agent/prompt_builder.py → src/agent/system_prompt_builder.py (SystemPromptBuilder)
```

**Priority:** P0 - CRITICAL (causes import confusion)

---

### 1.2 ContextManager (TWO DIFFERENT RESPONSIBILITIES)

**Problem:** Name collision with different concerns

| Class | Location | Purpose | Lines |
|-------|----------|---------|-------|
| ContextManager | `src/cli/context_manager.py` | UI wrapper for context commands (explore, refresh, clear, etc.) | 153 |
| ContextManager | `src/orchestrator/context_manager.py` | Coordinates CodebaseContext with orchestrator components | 175 |

**Issues:**
- CLI version delegates everything to orchestrator (lines 73-142)
- Orchestrator version adds auto-exploration, summary generation
- Both manage different concerns but share name

**Solution:**
```python
# Rename for clarity
src/cli/context_manager.py → src/cli/context_commands.py (CLIContextCommands)
src/orchestrator/context_manager.py → src/orchestrator/context_coordinator.py (ContextCoordinator)
```

**Priority:** P0 - CRITICAL

---

## 2. SHARED INFRASTRUCTURE DUPLICATION

### 2.1 Rate Limiting (MAJOR DUPLICATION)

**Files:**
- `src/cli/rate_limiter.py` (256 lines) - UI wrapper + display formatting
- `src/orchestrator/rate_limiter.py` (636 lines) - Actual tracking logic

**Duplication:**
- CLI calls `orchestrator.get_rate_limit_status()`, `orchestrator.reset_rate_tracking()`
- **Zero unique business logic in CLI** - pure wrapper
- Display formatting (CLI lines 164-255) should be extracted

**What's Different:**
- CLI adds: timestamp formatting, color-coded quota display, user confirmation prompts
- Orchestrator has: tracking logic, file I/O, usage calculation, provider limits

**Solution:**
```python
# Extract to shared infrastructure
infrastructure/formatters/rate_limit_formatter.py:
  class RateLimitFormatter:
    def format_status(self, status: dict) -> str: ...
    def format_quota_line(self, used: int, limit: int) -> str: ...
    def extract_time_from_timestamp(self, ts: str) -> str: ...
```

**Priority:** P1 - HIGH

---

### 2.2 Response Caching (MODERATE DUPLICATION)

**Files:**
- `src/cli/cache_manager.py` (103 lines) - Pure wrapper
- `src/orchestrator/cache.py` (557 lines) - Actual implementation

**Duplication:**
- CLI calls `orchestrator.get_cache_stats()`, `orchestrator.clear_cache()`, `orchestrator.toggle_cache()`
- **Zero business logic in CLI**
- Display logic (CLI lines 77-102) duplicates rate_limiter pattern

**What's Unique:**
- Orchestrator: TTL management, intent-based caching, async operations, normalization
- CLI: Formatting for display only

**Solution:**
- CLI handlers should be thin presenters
- Extract display formatting to `CacheStatsFormatter`
- Orchestrator cache is single source of truth

**Priority:** P1 - HIGH

---

### 2.3 File I/O Patterns (DUPLICATED ACROSS MULTIPLE FILES)

**Evidence:**
Both `orchestrator/cache.py` and `orchestrator/rate_limiter.py` duplicate:

```python
# orchestrator/cache.py lines 393-404
def _save_cache(self):
    try:
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        self.output.error(f"Cache write failed: {e}")

# orchestrator/rate_limiter.py lines 104-113 - IDENTICAL PATTERN
def _save_tracker(self):
    try:
        with open(self.tracker_file, 'w', encoding='utf-8') as f:
            json.dump(self._usage, f, indent=2)
    except Exception as e:
        self.output.error(f"Rate tracker write failed: {e}")
```

**Async versions also duplicated:**
- `_save_cache_async()` / `_save_tracker_async()`
- `_load_cache()` / `_load_tracker()`

**Solution:**
```python
# Create shared persistence layer
infrastructure/persistence/
  ├── protocols.py (PersistenceProtocol)
  ├── json_store.py (JSONPersistence)
  ├── async_json_store.py (AsyncJSONPersistence)
  └── file_utils.py (safe read/write with error handling)
```

**Priority:** P0 - CRITICAL (DRY violation)

---

## 3. COMMON PATTERNS WITHOUT ABSTRACTIONS

### 3.1 Logging (FRAGMENTED)

**Current State:**
- `src/cli/logging.py` (480 lines) - **Excellent structured logging** with:
  - SafeJSONEncoder, LoggerRegistry, CLILogger
  - Context binding, file rotation
  - **BUT: Only used in CLI layer!**
- Orchestrator uses simple print/console output
- Agent uses `safe_print` with Unicode handling
- No unified logging across layers

**Missing:**
1. Shared logging infrastructure for orchestrator and agent
2. Log aggregation across components
3. Consistent log levels across modules
4. Trace IDs for request correlation

**Solution:**
```python
# Promote CLI logging to shared infrastructure
infrastructure/logging/
  ├── logger.py (CLILogger → StructuredLogger)
  ├── formatters.py (SafeJSONEncoder, log formatters)
  ├── handlers.py (File, console, rotation handlers)
  └── registry.py (LoggerRegistry as singleton)

# All modules use shared logger
orchestrator: logger = get_logger("orchestrator.delegation")
agent: logger = get_logger("agent.core")
cli: logger = get_logger("cli.commands")
```

**Priority:** P1 - HIGH

---

### 3.2 Error Handling (SCATTERED)

**Current State:**
- `src/cli/exceptions.py` - CLI-specific exceptions
- `src/exceptions/delegation.py` - Delegation exceptions
- `src/utils/errors.py` - Utility error helpers
- `src/cli/error_recovery/` - Circuit breaker, retry, fallback patterns
- `src/cli/utils/error_handler.py` - Error categorization and severity

**Issues:**
1. Error recovery patterns duplicated across modules
2. No centralized error taxonomy
3. Retry logic appears in both `cli/error_recovery/` and `orchestrator/retry_orchestrator.py`
4. Rate limit error handling duplicated between providers and orchestrator

**Solution:**
```python
infrastructure/error_recovery/
  ├── base.py (ErrorRecoveryStrategy protocol)
  ├── retry.py (RetryStrategy)
  ├── circuit_breaker.py (CircuitBreakerStrategy)
  └── fallback.py (FallbackStrategy)

infrastructure/exceptions/
  ├── base.py (BaseError with categorization)
  ├── provider_errors.py (RateLimitError, ProviderNotFoundError)
  ├── cli_errors.py (CLIError, SessionError, TaskExecutionError)
  └── delegation_errors.py (DelegationError)
```

**Priority:** P1 - HIGH

---

### 3.3 Configuration Loading (IMPLICIT)

**Current State:**
- No explicit configuration module found
- `AgentConfig` defined in `src/agent_config.py`
- Orchestrator config scattered across `__init__` parameters
- CLI config in multiple files (`src/cli/config/`)

**Issues:**
1. Configuration mixed with code (constructor parameters everywhere)
2. No environment-based config (dev/test/prod)
3. Hardcoded paths (`.llm_rate_limits.json`, `.llm_response_cache.json`)
4. No validation of configuration values

**Solution:**
```python
infrastructure/config/
  ├── base.py (ConfigProtocol, BaseConfig)
  ├── loader.py (from env, from file, from dict)
  ├── validator.py (pydantic-based validation)
  └── defaults.py (default configurations)

# Config for each layer
orchestrator/config.py (OrchestratorConfig extends BaseConfig)
agent/config.py (AgentConfig extends BaseConfig)
cli/config.py (CLIConfig extends BaseConfig)
```

**Priority:** P2 - MEDIUM

---

### 3.4 Display Formatting (DUPLICATED PATTERN)

**Locations:**
- `src/cli/rate_limiter.py:164-255` (92 lines of display formatting)
- `src/cli/cache_manager.py:36-102` (similar pattern: stats display, color coding)

**Common Pattern:**
1. Subcommand validation
2. Stats retrieval from orchestrator
3. Color-coded table formatting
4. User confirmation prompts

**Solution:**
```python
infrastructure/formatters/
  ├── stats_formatter.py (StatsFormatter)
  ├── table_formatter.py (TableFormatter with color support)
  └── prompt_formatter.py (Confirmation prompts)
```

**Priority:** P1 - HIGH

---

## 4. MISSING PROTOCOLS/INTERFACES

### 4.1 Protocols Defined But Not Consistently Used

**Excellent Protocol Definitions Exist:**
- `src/orchestrator/protocols.py` (810 lines):
  - Orchestrator, CacheProtocol, RateLimitTrackerProtocol
  - SessionManagerProtocol, ProviderSelectorProtocol
  - WorkingMemoryProtocol, OutputInterface

- `src/cli/protocols.py` (633 lines):
  - CLIHandlerProtocol, DisplayFormatterProtocol
  - InputValidatorProtocol, DashboardProtocol

- `src/agent/protocols.py` (579 lines):
  - AuditLoggerProtocol, ResponseParserProtocol
  - PromptBuilderProtocol, ToolRegistryProtocol

**Problem: Not consistently used as type hints!**

**Examples:**
```python
# orchestrator/core.py line 62 - should use protocol
registry: Optional[ProviderRegistry]  # BAD
registry: Optional[ProviderRegistryProtocol]  # GOOD

# agent/core.py line 82 - should use protocol
tool_registry: Optional[ToolRegistry]  # BAD
tool_registry: Optional[ToolRegistryProtocol]  # GOOD
```

**Priority:** P1 - HIGH (enforces dependency inversion)

---

### 4.2 Protocols That Don't Exist Yet

**Missing:**

1. **FileSystemProtocol** - Abstract Path operations
   - Found import in `agent/protocols.py:13` referencing `infrastructure/protocols.py`
   - But no consistent abstraction found

2. **HTTPClientProtocol** - Abstract requests/HTTP calls
   - No abstraction for API calls
   - Direct use of `requests` library

3. **ProviderAdapterProtocol** - Standardize provider interface
   - Each provider implements similar interface
   - No shared protocol

4. **SerializerProtocol** - Abstract JSON/YAML/pickle
   - JSON operations scattered throughout

5. **MetricsCollectorProtocol** - Observability abstraction
   - Ad-hoc counters in various places

**Recommendation:**
```python
infrastructure/protocols.py:
  - FileSystemProtocol (abstract Path operations)
  - HTTPClientProtocol (abstract requests)
  - SerializerProtocol (abstract JSON/YAML/etc)
  - CryptoProtocol (abstract encryption/hashing)

providers/protocols.py:
  - ProviderAdapterProtocol (standardize provider interface)
  - StreamingProtocol (for streaming responses)
  - EmbeddingProtocol (for embedding providers)

observability/protocols.py:
  - MetricsCollectorProtocol
  - TracerProtocol
  - HealthCheckProtocol
```

**Priority:** P2 - MEDIUM

---


### 5.2 Tight Coupling

#### Direct File System Access

```python
# orchestrator/cache.py line 214
cache_file = str(codebase_context.project_path / ".llm_response_cache.json")

# orchestrator/rate_limiter.py line 221
tracker_file = str(codebase_context.project_path / ".llm_rate_limits.json")
```

**Issue:** Should use FileSystemProtocol for testability

---

#### Hard-Coded Tool Implementations

```python
# agent/core.py lines 161-167
self.tools = {
    tool.name: lambda ctx=self.tool_context, t=tool, **kw: t(ctx, **kw)
    for tool in self.tool_registry.list_all()
}
self.tools['run_command'] = self._tool_run_command  # Inline coupling!
```

**Issue:** Tight coupling to specific tool implementation

---

#### Concrete Dependencies

```python
# orchestrator/core.py line 109
self.registry = registry or self._create_default_registry()
# Returns ProviderRegistry, not ProviderRegistryProtocol
```

**Issue:** Depends on concrete class instead of protocol

**Priority:** P1 - HIGH

---

## 6. INFRASTRUCTURE GAPS

### 6.1 Logging Infrastructure

**Current:**
- CLI has excellent structured logging (`src/cli/logging.py`)
- Orchestrator and Agent use print/console
- No trace correlation across components

**Missing:**
- Centralized logging configuration
- Log aggregation
- Request tracing
- Performance logging
- Audit trail integration

**Priority:** P1 - HIGH

---

### 6.2 Metrics/Observability

**Current:**
- `UsageReporter` tracks API usage
- `RateLimitTracker` tracks rate limits
- Ad-hoc counters in various places

**Missing:**
- MetricsCollectorProtocol
- Prometheus/OpenTelemetry integration
- Performance metrics (latency, throughput)
- Error rate tracking
- Health checks

**Priority:** P2 - MEDIUM

---

### 6.3 Configuration Management

**Current:**
- Scattered across constructor parameters
- Some in `agent_config.py`
- CLI config in separate package

**Missing:**
- Centralized config loader
- Environment-based configs (dev/prod)
- Config validation
- Secrets management
- Feature flags

**Priority:** P2 - MEDIUM

---

### 6.4 Testing Utilities

**Current:**
- Protocols defined for testing (good!)
- Likely test doubles in `tests/helpers.py`

**Missing (based on protocol definitions):**
- InMemoryCache implementation
- MockOrchestrator implementation
- TestToolRegistry implementation
- NullOutput implementation
- Test fixture generators

**Priority:** P3 - LOW

---

## 7. REFACTORING ROADMAP

### Phase 0: Critical Name Fixes (IMMEDIATE)

**Goal:** Eliminate name collisions that cause confusion

**Tasks:**
1. Rename `cli/prompt_builder.py` → `cli/research_prompt_builder.py`
2. Rename `agent/prompt_builder.py` → `agent/system_prompt_builder.py`
3. Rename `cli/context_manager.py` → `cli/context_commands.py`
4. Rename `orchestrator/context_manager.py` → `orchestrator/context_coordinator.py`
5. Update all imports and references

**Estimated Effort:** 2-4 hours
**Priority:** P0 - CRITICAL

---

### Phase 1: Extract Shared Infrastructure (WEEK 1)

**Goal:** Consolidate duplicated infrastructure

**Tasks:**
1. Extract file I/O to `infrastructure/persistence/`
   - JSONPersistence, AsyncJSONPersistence
   - Update cache.py and rate_limiter.py to use

2. Extract display formatting to `infrastructure/formatters/`
   - StatsFormatter, TableFormatter
   - Update CLI handlers to use

3. Promote CLI logging to `infrastructure/logging/`
   - Make available to orchestrator and agent
   - Add trace correlation

**Estimated Effort:** 1 week
**Priority:** P1 - HIGH

---

### Phase 2: Break Up God Classes (WEEK 2-3)

**Goal:** Apply Single Responsibility Principle

God Classes have their own plans in docs/TODO/CODE_AGENT.md, docs/TODO/AGENT_ORCH.md, docs/TODO/RATE_LIMIT_TRACKER.md
**Tasks:**
1. Refactor AgentOrchestrator (875 lines → multiple focused classes)
   - Extract ContextCoordinator
   - Extract BackgroundTaskManager
   - Extract UsageReporter
   - Keep core.py for high-level coordination only

2. Refactor CodeAgent (1,336 lines → multiple focused classes)
   - Extract ToolExecutor
   - Extract ResponseHandler
   - Extract DuplicateDetector
   - Extract InteractiveHandler
   - Keep core.py for agent loop only

3. Refactor RateLimitTracker (636 lines → focused components)
   - Extract RateLimitStorage
   - Extract RateLimitCalculator
   - Extract RateLimitPolicy

**Estimated Effort:** 2 weeks
**Priority:** P0 - CRITICAL

---

### Phase 3: Enforce Protocol Usage (WEEK 4)

**Goal:** Apply Dependency Inversion Principle

**Tasks:**
1. Update all type hints to use protocols instead of concrete classes
2. Ensure factory methods return protocol types
3. Add runtime validation that dependencies implement required protocols
4. Create missing protocol definitions (FileSystemProtocol, HTTPClientProtocol, etc.)

**Estimated Effort:** 1 week
**Priority:** P1 - HIGH

---

### Phase 4: Consolidate Error Handling (WEEK 5)

**Goal:** Unified error recovery and taxonomy

**Tasks:**
1. Merge `cli/error_recovery/` and `orchestrator/retry_orchestrator.py`
2. Create `infrastructure/error_recovery/` with shared strategies
3. Create `infrastructure/exceptions/` with error taxonomy
4. Update all modules to use shared error handling

**Estimated Effort:** 1 week
**Priority:** P1 - HIGH

---

### Phase 5: Configuration Infrastructure (WEEK 6)

**Goal:** Centralized configuration management

**Tasks:**
1. Create `infrastructure/config/` with loaders and validators
2. Migrate scattered config to structured config objects
3. Add environment-based configuration support
4. Add config validation with clear error messages

**Estimated Effort:** 1 week
**Priority:** P2 - MEDIUM

---


[//]: # (RESULTS)

Phase 0: Critical Name Fixes - COMPLETE
Phase 1: Extract Shared Infrastructure - COMPLETE
Phase 2: Break Up God Classes - COMPLETE -- some classes may need more complete refactoring, but 90% better
Phase 3: Enforce Protocol Usage - Possibly complete, started. Need to investigate
