# Claude Code Guidelines

**CRITICAL: Never use emojis or special characters.**

---

## SESSION STARTUP

On session start, run `/work` to check the Beads issue tracker for current work.

**Autonomous Workflow:**
Run `/auto <bead-id>` to execute full autonomous workflow (PLAN -> IMPLEMENT -> TEST).
Or run directly: `python workflows/orchestrator.py <bead-id>`

The orchestrator uses aggressive context isolation - each step runs in a fresh agent.
State persists only in beads. No context survives between agents.

**Beads Workflow (binary at `.beads/bd.exe`):**
- `.beads/bd.exe ready --json` - See issues with no blockers (ready to work on)
- `.beads/bd.exe list --status in_progress` - See what's currently being worked on
- `.beads/bd.exe create "title" -t task -p 2` - Create new issue (types: bug, feature, task, epic, chore; priority 0-4)
- `.beads/bd.exe update <id> --status in_progress` - Start working on an issue
- `.beads/bd.exe close <id>` - Complete an issue
- `.beads/bd.exe dep add <child> <parent>` - Add dependency (child depends on parent)

When you discover new work while implementing, create an issue with `.beads/bd.exe create --discovered-from <current-issue>`.

---

## ISSUE DISCOVERY (MANDATORY)

While coding, you MUST create beads for any issues you encounter. This includes:

**Code Quality Issues:**
- SOLID principle violations (god classes, missing protocols, hard-coded dependencies)
- Missing dependency injection
- Concrete classes without protocols
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

**How to Log Issues:**
```bash
# Create a bug for code quality violation
.beads/bd.exe create "SRP violation in XyzClass - does caching AND validation" -t bug -p 2

# Create a task for missing protocol
.beads/bd.exe create "Add protocol for FooService - currently concrete only" -t task -p 3

# Create chore for tech debt
.beads/bd.exe create "Add edge case tests for bar() function" -t chore -p 3
```

**After creating the bead**, append a one-line summary to `docs/TODO/AGENT_BUGS.md`:
```
- [BEAD-ID] Brief description (discovered while working on X)
```

This creates a persistent human-readable log of agent-discovered issues.

---

## PROJECT STATUS: PRERELEASE

This is a local development project in active prerelease development. There are no external users or published APIs.

**Therefore:**
- **NO deprecation warnings** - Just remove or change code directly
- **NO backward compatibility shims** - Delete old code, don't wrap it
- **NO fallback code paths** - If something is replaced, remove the old version
- **NO legacy support** - No need to maintain old interfaces
- **NO migration code** - Just make the change

When refactoring or fixing bugs: delete the old code, write the new code. Done.

---

## ARCHITECTURAL PRINCIPLES (READ THIS FIRST)

### You Are an Architect, Not a Code Monkey

Before writing ANY code, you must:
1. **Design the abstraction** - What protocol/interface is needed?
2. **Consider SOLID principles** - Is this following Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion?
3. **Plan dependency injection** - How will this be tested? What needs to be injected?
4. **Think about edge cases** - What can go wrong? What are the boundaries?
5. **Design before coding** - No coding until the design is clear

### MANDATORY: Protocol-First Design

**NEVER write a concrete class without defining its protocol first.**

```python
# WRONG - Concrete class first
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
- If NO → Don't write it

**Would this test fail if the feature breaks?**
- If NO → Don't write it

**Can I refactor internals without breaking this test?**
- If NO → You're testing implementation, not behavior

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
    # Use real objects, not mocks
    orchestrator = create_test_orchestrator()
    result = orchestrator.delegate("test query")
    assert result.content != ""
    assert result.tokens_used > 0
```

---

## COMMANDS

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_<module>.py -v

# Run with coverage (informational only)
python -m pytest tests/ --cov=src --cov-report=term-missing
```

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