# Coding Agent Guidelines

**CRITICAL: Never use emojis or special characters.**

---

This project uses **br** (beads rust) for issue tracking. Run `br info` or `br --help` to get started.

## Quick Reference

```bash
br info               # Show active .beads workspace and issue count
br ready              # Find available work
br show <id>          # View issue details
br update <id> --status in_progress  # Claim work
br close <id>         # Complete work
br sync               # Sync with git
```

---

## DOCUMENTATION LOCATIONS

Two distinct trees with different purposes. Pick the right one:

**`docs/`** - versioned, ships with the repo
- User-facing docs (QUICKSTART, BEGINNERS, CUSTOMIZATION)
- Architecture overviews (ARCHITECTURE.md)
- Behavior of existing systems (`docs/behavior/`)
- Anything a future contributor or user needs to read

**`.docs/`** - gitignored, local-only working space
- Plans, drafts, in-progress thinking (`.docs/plans/`)
- Notes and scratchpads
- Anything that's a working artifact rather than a shipping artifact
- Plans live here because committed plan docs make the repo bloat over time and rot once the work lands

When in doubt: if it describes "what we have" it goes in `docs/`; if it describes "what we want to build" it goes in `.docs/`.

NEVER commit anything under `.docs/`. The directory is gitignored on purpose.

---

## STAY IN SCOPE

When the user asks for X, deliver X. Do not build X plus adjacent infrastructure that might be useful later.

- Asked to plan an epic? Write the plan. Do not start building it.
- Asked to fix bug Y? Fix bug Y. Do not refactor surrounding code unless the fix requires it.
- Found untracked artifacts in the worktree? Treat them as suspicious. Do not ship them unless they are clearly part of the task.
- When in doubt about whether something is in scope, ask before building.

---

## PLAN BEFORE BUILDING

For any work bigger than a focused bug fix, write a plan first in `.docs/plans/`. The plan describes what exists, what is missing, the design decisions, and the proposed PR sequence.

Plans should be reviewed before implementation begins. A second reviewer, whether the user or another coding agent, catches structural issues that feel right to the original author.

If a plan keeps making the same wrong-layer mistake across revisions, name the rule explicitly and pin it at the top of the plan.

---

## CROSS-AGENT REVIEW

Use independent review for architectural decisions, plan revisions, and choices with multiple defensible answers. The author of an artifact has confirmation bias on their own work.

When another agent or reviewer gives findings, address the root issue in the artifact. Do not just patch the wording that was criticized.

---

## QUALITY GATE (BEFORE CLAIMING DONE)

A change is not done until:

- `ruff check` passes on the changed surface. Prefer the focused path first; run broader checks when the change touches shared behavior.
- `mypy` passes on touched source files or packages when source code changed.
- The relevant test surface passes, including edge cases for the behavior changed.
- Any skipped or impossible checks are called out explicitly with the reason.
- For user-facing or environment-dependent behavior, do not claim it works in the user's environment until the user confirms. If the user has not confirmed yet, say exactly what was verified locally and what remains unconfirmed.

---

## ENGINEERING OPERATING RULES

- Delete more than you add when cleanup is safe and in scope.
- Leave touched code better than you found it without expanding the task.
- Fix root causes. Do not defend a workaround when the underlying design is wrong.
- Prefer the smallest change that proves the behavior and preserves existing contracts.
- If pre-existing debt blocks the right fix, document it with `br create` instead of silently working around it.

---

## ISSUE DISCOVERY (MANDATORY)

While coding, you MUST document any issues you encounter using `br create`. This includes:

**Code Quality Issues:**
- SOLID principle violations (god classes, missing infrastructure protocols, hard-coded dependencies)
- Missing dependency injection
- New swappable infrastructure classes without protocols
- Tests that violate guidelines (over-mocked, structure-only, no behavior testing)
- Missing edge case handling

**Bugs and Problems:**
- Runtime errors or unexpected behavior
- Logic errors discovered during implementation
- Integration issues between components
- Performance problems

**Technical Debt:**
- TODO/FIXME comments in code
- Incomplete implementations
- Missing tests for existing functionality
- Documentation gaps

---

## ARCHITECTURAL PRINCIPLES (READ THIS FIRST)

### You Are an Architect, Not a Code Monkey

Before writing ANY code, you must:
1. **Design the abstraction** - What protocol/interface is needed?
2. **Consider SOLID principles** - Is this following Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion?
3. **Plan dependency injection** - How will this be tested? What needs to be injected?
4. **Think about edge cases** - What can go wrong? What are the boundaries?
5. **Design before coding** - No coding until the design is clear

### MANDATORY: Protocol-First Infrastructure

**NEVER write a concrete infrastructure class without defining its protocol first.**

This rule applies to classes that perform I/O, wrap external systems, coordinate services, hold external resources, or are injected as dependencies. It does not apply to simple dataclasses, enums, exceptions, typed value objects, or local helpers with no reasonable alternate implementation.

```python
# WRONG - Concrete infrastructure class first
class ResponseCache:
    def get(self, key: str) -> Optional[str]:
        return self._cache.get(key)

# RIGHT - Protocol first, then implementation
class CacheProtocol(Protocol):
    """Defines the contract for caching behavior."""
    def get(self, key: str) -> Optional[str]: ...
    def put(self, key: str, value: str) -> None: ...
    def clear(self) -> None: ...

class ResponseCache:  # Implements CacheProtocol
    def get(self, key: str) -> Optional[str]:
        return self._cache.get(key)
```

**Why?** Protocols enable:
- Testing with test doubles
- Swapping implementations
- Dependency inversion
- Clear contracts

---

## SOLID PRINCIPLES (NON-NEGOTIABLE)

### Single Responsibility Principle
**Each class should have ONE reason to change.**

**BAD - God Class:**
```python
class AgentOrchestrator:
    def __init__(self):
        self.cache = ResponseCache()
        self.rate_tracker = RateLimitTracker()
        self.session_manager = SessionManager()
        # ... does caching, rate limiting, sessions, delegation, context, etc.
```

**GOOD - Focused Classes:**
```python
class Orchestrator:
    def __init__(
        self,
        cache: CacheProtocol,
        rate_tracker: RateLimitProtocol,
        session: SessionProtocol,
        delegator: DelegationProtocol,
    ):
        # Each dependency is a focused, single-purpose component
```

### Open/Closed Principle
**Open for extension, closed for modification.**

Use strategy pattern, not if/else chains.

 **BAD:**
```python
def execute(self, task_type: str):
    if task_type == "research":
        # research logic
    elif task_type == "coding":
        # coding logic
    # Adding new type = modifying this function
```

**GOOD:**
```python
class ExecutionStrategy(Protocol):
    def execute(self, task: Task) -> Result: ...

# Add new strategies without modifying existing code
strategies = {
    TaskType.RESEARCH: ResearchStrategy(),
    TaskType.CODING: CodingStrategy(),
}
```

### Liskov Substitution Principle
**Subtypes must be substitutable for their base types.**

If you inherit from a class or implement a protocol, you must honor the contract completely.

### Interface Segregation Principle
**Don't force clients to depend on interfaces they don't use.**

**BAD - Fat Interface:**
```python
class ProviderProtocol(Protocol):
    def chat(self) -> Response: ...
    def stream(self) -> Iterator[str]: ...
    def embed(self) -> List[float]: ...
    # Providers forced to implement everything even if not supported
```

**GOOD - Focused Interfaces:**
```python
class ChatProvider(Protocol):
    def chat(self) -> Response: ...

class StreamingProvider(Protocol):
    def stream(self) -> Iterator[str]: ...

# Providers implement only what they support
```

### Dependency Inversion Principle
**Depend on abstractions, not concretions.**

**BAD:**
```python
class CodeAgent:
    def __init__(self):
        self.cache = ResponseCache()  # Depends on concrete class
        self.file_ops = Path()  # Depends on stdlib directly
```

**GOOD:**
```python
class CodeAgent:
    def __init__(
        self,
        cache: CacheProtocol,  # Depends on abstraction
        file_system: FileSystemProtocol,  # Depends on abstraction
    ):
```

---

## DEPENDENCY INJECTION (MANDATORY)

### The Rule: ALL Dependencies MUST Be Injected

**NO direct instantiation of dependencies in class bodies.**

**FORBIDDEN PATTERNS:**
```python
class MyClass:
    def __init__(self):
        self.cache = ResponseCache()  # NO! Direct instantiation
        self.db = sqlite3.connect("db.sqlite")  # NO! Hard-coded dependency
        self.config = load_config()  # NO! Side effect in constructor
        Path("file.txt").write_text("data")  # NO! Direct file access

    def process(self):
        result = requests.get("http://api.com")  # NO! Direct HTTP call
```

**REQUIRED PATTERN:**
```python
class MyClass:
    def __init__(
        self,
        cache: CacheProtocol,
        db: DatabaseProtocol,
        config: Config,
        file_system: FileSystemProtocol,
        http_client: HTTPClientProtocol,
    ):
        self.cache = cache
        self.db = db
        self.config = config
        self.file_system = file_system
        self.http_client = http_client
```

### Constructor Rules

1. **NO side effects** - Constructors assign dependencies only
2. **NO business logic** - Move logic to explicit methods
3. **NO I/O operations** - No file reads, no network calls
4. **NO auto-registration** - Explicit is better than implicit
5. **Provide defaults with factory pattern:**

```python
def __init__(
    self,
    cache: Optional[CacheProtocol] = None,
):
    self.cache = cache or self._create_default_cache()

def _create_default_cache(self) -> CacheProtocol:
    return ResponseCache()  # Factory method for default
```

---

## TESTS

### Test Quality Checklist

Before writing ANY test, answer these questions:

**Does this test prove a feature works?**
- If NO, do not write it

**Would this test fail if the feature breaks?**
- If NO, do not write it

**Can I refactor internals without breaking this test?**
- If NO, you are testing implementation, not behavior

**Does this test cover edge cases?**
- Empty inputs?
- Boundary values?
- Error conditions?
- Invalid data?

**Am I mocking appropriately?**
- Only external dependencies (APIs, file system, network)?
- Using real objects for business logic?
- Using test doubles from `helpers.py`?

### TEST ISOLATION (CRITICAL - READ THIS)

**NEVER MAKE REAL API CALLS IN TESTS. EVER.**
**TEST BEHAVIOR THROUGH MOCKS NOT REAL APIS YOU MANIAC**

### Tests to NEVER Write

 **Structure-only tests:**
```python
def test_returns_correct_type():
    result = do_thing()
    assert isinstance(result, MyClass)  # So what? Proves nothing!
```

 **Initialization tests:**
```python
def test_initialization():
    obj = MyClass()
    assert obj is not None  # Useless!
    assert hasattr(obj, 'field')  # Useless!
```

 **Over-mocked tests:**
```python
def test_with_all_mocks():
    mock1 = Mock()
    mock2 = Mock()
    mock3 = Mock()
    obj = MyClass(mock1, mock2, mock3)
    obj.do_thing()
    mock1.assert_called_once()  # Only proves mock was called, not that feature works!
```

### Tests to ALWAYS Write

 **Behavior tests:**
```python
def test_cache_returns_none_when_empty():
    cache = ResponseCache()
    result = cache.get("nonexistent")
    assert result is None  # Tests actual behavior

def test_cache_returns_stored_value():
    cache = ResponseCache()
    cache.put("key", "value")
    result = cache.get("key")
    assert result == "value"  # Tests actual behavior
```

 **Edge case tests:**
```python
def test_handles_empty_input():
    result = process([])
    assert result == []

def test_handles_none_input():
    result = process(None)
    assert result is None

def test_raises_on_invalid_input():
    with pytest.raises(ValueError):
        process("invalid")
```

 **Integration tests:**
```python
def test_end_to_end_flow():
    # Use real business objects around a fake external boundary.
    llm_service = FakeLLMService(response="done")
    orchestrator = create_test_orchestrator(llm_service=llm_service)
    result = orchestrator.delegate("test query")
    assert result.content == "done"
    assert llm_service.calls == ["test query"]
```

---

## COMMAND REFERENCE

Use the narrowest command that proves the changed behavior first, then broaden when the change touches shared contracts.

```bash
# Lint source and tests with ruff
ruff check src/ tests/

# Type check source with mypy
mypy src/

# Run default test suite (excludes integration, slow, and benchmark tests by pytest config)
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_<module>.py -v

# Run the full test tree explicitly when validating test infrastructure changes
python -m pytest tests/ -v --tb=short --strict-markers -o addopts=""

# Run integration tests explicitly when touching integration behavior
python -m pytest tests/integration/ -v --tb=short --strict-markers -o addopts=""

# Run with coverage (informational only)
python -m pytest tests/ --cov=src --cov-report=term-missing
```

The quality gate above defines when a change can be claimed done. If a command cannot run or is blocked by known pre-existing debt, say so explicitly.

---

## REMEMBER

**You are building a system that must:**
- Be testable without real I/O
- Support swapping implementations
- Be maintainable by others
- Follow industry best practices
- Prove it works via tests

**Think like an architect:**
1. Design interfaces first
2. Consider dependencies
3. Plan for testing
4. Follow SOLID
5. Write tests that prove it works
6. Then implement

**Never be a lazy coder:**
- Don't mock everything
- Don't write tests that prove nothing
- Don't create god classes
- Don't hard-code dependencies
- Don't skip edge cases
- Don't write code without designing first
