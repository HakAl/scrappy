# Command Tools Refactoring Plan -- src/agent_tools/tools/command_tool.py

This document outlines the refactoring of `ShellCommandExecutor` to follow SOLID principles and architectural best practices.

## Table of Contents
1. [Problem Diagnosis](#1-problem-diagnosis)
2. [Architectural Violations](#2-architectural-violations)
3. [Protocol-First Design](#3-protocol-first-design)
4. [Dependency Injection Strategy](#4-dependency-injection-strategy)
5. [Testing Strategy](#5-testing-strategy)
6. [Implementation Phases](#6-implementation-phases)

---

## 1. Problem Diagnosis

### Current Responsibilities (SRP Violations)

The `ShellCommandExecutor` class has at least **6 distinct responsibilities**:

1. **Low-level Execution:** Managing `subprocess`, threads, and streaming (`_run_command_streaming`)
2. **Security Policy:** Defining and checking regexes for dangerous commands (`_check_dangerous_command`)
3. **Platform Abstraction:** Patching paths and npm commands for Windows (`_apply_platform_fixes`)
4. **Domain Knowledge:** Hardcoded knowledge of Spring Boot, Maven, and specific CLI tool behaviors (`intercept_spring_initializr_download`)
5. **Output Processing:** Heuristic detection of JSON vs. YAML vs. Error messages (`_parse_command_output`)
6. **Agent Strategy:** Analyzing "approaches" to detect if the LLM is looping on a failed strategy (`_categorize_command_approach`, `_check_retry_pattern`)

### Code Smells

- **Hardcoded Framework Logic:** Generic `CommandTool` shouldn't know about `spring-boot-starter-web`
- **Mixed Abstraction Levels:** High-level logic (`_check_retry_pattern`) mixed with low-level OS logic (`subprocess.Popen`)
- **Platform Utils Redundancy:** Massive glue code instead of self-sufficient utilities
- **God Class:** 850+ lines with multiple reasons to change

---

## 2. Architectural Violations

### Open/Closed Principle (OCP) Violation
Adding support for new frameworks (Rust/Cargo) or output formats (XML) requires modifying the core `ShellCommandExecutor` class, risking breaking existing execution logic.

### Dependency Inversion Principle (DIP) Violation
Direct instantiation of dependencies instead of depending on abstractions.

---

## 3. Protocol-First Design

**CRITICAL:** Define protocols BEFORE implementing any concrete classes.

### 3.1 CommandSecurityProtocol

```python
from typing import Protocol

class CommandSecurityProtocol(Protocol):
    """Contract for validating command safety.

    Implementations must check commands against security policies
    and raise exceptions for dangerous operations.
    """

    def validate(self, command: str) -> None:
        """Validate command safety.

        Args:
            command: The command string to validate

        Raises:
            SecurityError: If command violates security policy
        """
        ...
```

### 3.2 OutputParserProtocol

```python
class OutputParserProtocol(Protocol):
    """Contract for parsing and formatting command output.

    Implementations handle truncation, format detection (JSON/YAML),
    and consistent output formatting.
    """

    def parse(self, raw_output: str, max_length: int = 30000) -> str:
        """Parse and format raw command output.

        Args:
            raw_output: Raw output from command execution
            max_length: Maximum output length before truncation

        Returns:
            Formatted output string
        """
        ...

    def detect_format(self, output: str) -> str:
        """Detect output format (json, yaml, text, error).

        Args:
            output: Command output to analyze

        Returns:
            Format type identifier
        """
        ...
```

### 3.3 CommandAdvisorProtocol

```python
from typing import Optional

class CommandAdvisorProtocol(Protocol):
    """Contract for providing command advice and context.

    Implementations provide framework-specific guidance and
    enrich error messages with helpful context.
    """

    def analyze_command(self, command: str) -> Optional[str]:
        """Analyze command and provide pre-execution advice.

        Args:
            command: Command to analyze

        Returns:
            Advisory message if applicable, None otherwise
        """
        ...

    def enrich_output(self, output: str, command: str) -> str:
        """Enrich output with contextual information.

        Args:
            output: Raw command output
            command: Original command that was executed

        Returns:
            Enriched output with additional context
        """
        ...
```

### 3.4 PlatformSanitizerProtocol

```python
class PlatformSanitizerProtocol(Protocol):
    """Contract for platform-specific command sanitization.

    Implementations handle OS-specific command adjustments,
    path normalization, and command translation.
    """

    def sanitize(self, command: str) -> str:
        """Apply platform-specific command fixes.

        Args:
            command: Original command string

        Returns:
            Sanitized command appropriate for current platform
        """
        ...

    def normalize_path(self, path: str) -> str:
        """Normalize path for current platform.

        Args:
            path: Path to normalize

        Returns:
            Platform-appropriate path
        """
        ...
```

### 3.5 SubprocessRunnerProtocol

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExecutionResult:
    """Result of command execution."""
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float

class SubprocessRunnerProtocol(Protocol):
    """Contract for executing subprocesses.

    Implementations handle the low-level mechanics of process
    execution, streaming, timeout handling, and signal management.
    """

    def execute(
        self,
        command: str,
        cwd: str,
        timeout: Optional[float] = None,
        stream_output: bool = False,
    ) -> ExecutionResult:
        """Execute command in subprocess.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Optional timeout in seconds
            stream_output: Whether to stream output in real-time

        Returns:
            ExecutionResult with stdout, stderr, and exit code

        Raises:
            TimeoutError: If execution exceeds timeout
            ExecutionError: If execution fails
        """
        ...
```

---

## 4. Dependency Injection Strategy

### 4.1 Refactored ShellCommandExecutor

```python
class ShellCommandExecutor:
    """Coordinates command execution through injected dependencies.

    This class follows the Single Responsibility Principle by
    delegating specific concerns to injected protocol implementations.
    """

    def __init__(
        self,
        security: CommandSecurityProtocol,
        sanitizer: PlatformSanitizerProtocol,
        advisor: CommandAdvisorProtocol,
        runner: SubprocessRunnerProtocol,
        parser: OutputParserProtocol,
    ):
        """Initialize with dependency injection.

        Args:
            security: Command security validator
            sanitizer: Platform-specific command sanitizer
            advisor: Command advisor for framework-specific guidance
            runner: Subprocess execution engine
            parser: Output parser and formatter
        """
        self._security = security
        self._sanitizer = sanitizer
        self._advisor = advisor
        self._runner = runner
        self._parser = parser

    def execute(self, command: str, cwd: str) -> str:
        """Execute command with full pipeline.

        Args:
            command: Command to execute
            cwd: Working directory

        Returns:
            Formatted and enriched output
        """
        # 1. Security validation
        self._security.validate(command)

        # 2. Platform sanitization
        sanitized_command = self._sanitizer.sanitize(command)

        # 3. Pre-execution advice
        advice = self._advisor.analyze_command(sanitized_command)
        if advice:
            print(f"[ADVICE] {advice}")

        # 4. Execute
        result = self._runner.execute(sanitized_command, cwd)

        # 5. Parse output
        parsed = self._parser.parse(result.stdout)

        # 6. Enrich with context
        return self._advisor.enrich_output(parsed, command)
```

### 4.2 Factory Function for Default Wiring

```python
def create_shell_executor(config: Config) -> ShellCommandExecutor:
    """Factory function for creating ShellCommandExecutor with defaults.

    Args:
        config: Application configuration

    Returns:
        Fully wired ShellCommandExecutor instance
    """
    return ShellCommandExecutor(
        security=CommandSecurity(config),
        sanitizer=WindowsSanitizer() if os.name == 'nt' else UnixSanitizer(),
        advisor=FrameworkAdvisor(),
        runner=SubprocessRunner(),
        parser=OutputParser(),
    )
```

---

## 5. Testing Strategy

### 5.1 Test Each Component in Isolation

**CommandSecurity Tests:**
```python
def test_command_security_blocks_rm_rf():
    security = CommandSecurity(config)
    with pytest.raises(SecurityError):
        security.validate("rm -rf /")

def test_command_security_allows_safe_commands():
    security = CommandSecurity(config)
    security.validate("ls -la")  # Should not raise
```

**OutputParser Tests:**
```python
def test_output_parser_detects_json():
    parser = OutputParser()
    result = parser.parse('{"status": "ok"}')
    assert '"status": "ok"' in result

def test_output_parser_truncates_long_output():
    parser = OutputParser()
    long_output = "x" * 50000
    result = parser.parse(long_output, max_length=1000)
    assert len(result) < 1500  # Includes truncation message
```

**CommandAdvisor Tests:**
```python
def test_advisor_suggests_npm_init_flag():
    advisor = FrameworkAdvisor()
    advice = advisor.analyze_command("npm init")
    assert "-y" in advice or "interactive" in advice

def test_advisor_enriches_spring_error():
    advisor = FrameworkAdvisor()
    output = "Error downloading spring-boot-starter-web"
    enriched = advisor.enrich_output(output, "spring init")
    assert "Spring Initializr" in enriched
```

### 5.2 Test ShellCommandExecutor with Test Doubles

```python
def test_executor_full_pipeline():
    # Arrange: Create test doubles
    security = MockCommandSecurity()
    sanitizer = MockPlatformSanitizer()
    advisor = MockCommandAdvisor()
    runner = MockSubprocessRunner(
        result=ExecutionResult(stdout="test output", stderr="", exit_code=0, execution_time=0.1)
    )
    parser = MockOutputParser()

    executor = ShellCommandExecutor(security, sanitizer, advisor, runner, parser)

    # Act
    result = executor.execute("test command", "/tmp")

    # Assert
    assert security.validate_called
    assert sanitizer.sanitize_called
    assert runner.execute_called
    assert parser.parse_called
```

### 5.3 Integration Tests

```python
def test_executor_end_to_end():
    # Use REAL implementations
    executor = create_shell_executor(test_config)
    result = executor.execute("echo hello", os.getcwd())
    assert "hello" in result
```

---

## 6. Implementation Phases

### Phase 1: Protocol Definition (CRITICAL - DO THIS FIRST)

- [ ] Create `src/agent_tools/protocols/__init__.py`
- [ ] Define `CommandSecurityProtocol`
- [ ] Define `OutputParserProtocol`
- [ ] Define `CommandAdvisorProtocol`
- [ ] Define `PlatformSanitizerProtocol`
- [ ] Define `SubprocessRunnerProtocol`
- [ ] Define `ExecutionResult` dataclass
- [ ] Review protocols with team - GET AGREEMENT ON INTERFACES

### Phase 2: Test Preparation

- [ ] Create test doubles in `tests/helpers.py`:
  - `MockCommandSecurity`
  - `MockOutputParser`
  - `MockCommandAdvisor`
  - `MockPlatformSanitizer`
  - `MockSubprocessRunner`
- [ ] Write test suite structure (empty tests with TODOs)

### Phase 3: Implementation (TDD - Red/Green/Refactor)

**3.1 CommandSecurity**
- [ ] Write failing tests for dangerous command detection
- [ ] Implement `CommandSecurity` class
- [ ] Test edge cases: escaped commands, chained commands, etc.

**3.2 OutputParser**
- [ ] Write failing tests for JSON/YAML detection
- [ ] Write failing tests for truncation
- [ ] Implement `OutputParser` class
- [ ] Test edge cases: malformed JSON, mixed formats

**3.3 CommandAdvisor**
- [ ] Write failing tests for framework detection
- [ ] Write failing tests for output enrichment
- [ ] Implement `FrameworkAdvisor` class
- [ ] Test Spring, npm, Maven, Gradle scenarios

**3.4 PlatformSanitizer**
- [ ] Write failing tests for Windows path handling
- [ ] Write failing tests for command translation
- [ ] Implement `WindowsSanitizer` and `UnixSanitizer`
- [ ] Test cross-platform scenarios

**3.5 SubprocessRunner**
- [ ] Write failing tests for basic execution
- [ ] Write failing tests for timeout handling
- [ ] Write failing tests for streaming output
- [ ] Implement `SubprocessRunner` class
- [ ] Test signal handling, process cleanup

### Phase 4: Integration

**4.1 Refactor ShellCommandExecutor**
- [ ] Update `__init__` to use dependency injection
- [ ] Update `execute` method to use protocol implementations
- [ ] Remove all duplicated logic (now in components)
- [ ] Write integration tests with real components

**4.2 Create Factory**
- [ ] Implement `create_shell_executor` factory function
- [ ] Add configuration-based component selection
- [ ] Test factory with different configs

**4.3 Update Callers**
- [ ] Find all places that instantiate `ShellCommandExecutor`
- [ ] Update to use factory function
- [ ] Verify existing behavior preserved

### Phase 5: Cleanup

- [ ] Remove old implementation from `ShellCommandExecutor`
- [ ] Delete unused helper methods
- [ ] Move framework-specific code to appropriate locations
- [ ] Update documentation
- [ ] Verify file size reduction (target: ~200 lines for `ShellCommandExecutor`)

### Phase 6: Verification

- [ ] All tests pass
- [ ] Code coverage maintained or improved
- [ ] No regression in existing functionality
- [ ] Performance benchmarks within acceptable range
- [ ] Code review completed
- [ ] Documentation updated

---

## Success Criteria

- [ ] `ShellCommandExecutor` reduced to < 200 lines
- [ ] Each component has single responsibility
- [ ] All dependencies injected via protocols
- [ ] 100% test coverage on new components
- [ ] All existing tests still pass
- [ ] No direct instantiation of dependencies
- [ ] Can swap implementations without changing `ShellCommandExecutor`
- [ ] Can test all components in isolation
- [ ] Framework-specific code isolated in `CommandAdvisor`

---

## Notes

- **DO NOT** start implementing concrete classes until protocols are reviewed and approved
- **DO NOT** skip writing tests - TDD is mandatory
- **DO NOT** directly instantiate dependencies - use injection
- **DO NOT** mock business logic - only external dependencies
- **REMEMBER:** Protocol → Test → Implement → Integrate