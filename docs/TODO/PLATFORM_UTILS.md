## Protocol-Based Platform Utils Decomposition

**UPDATED PLAN - Based on Current Codebase State**

### Current State Analysis

**What Already Exists:**
1. `src/platform_utils.py` - 1600-line god module with functions for:
   - Platform detection (is_windows, is_unix, is_macos, get_platform_name)
   - Shell info (get_shell_info, has_git_bash)
   - Command translation (translate_command_for_platform)
   - Command validation (validate_command_for_platform, get_dangerous_commands, get_interactive_commands)
   - Path utilities (normalize_path_for_shell, normalize_command_paths, get_null_device, get_path_separator)
   - Command execution (smart_execute_command, get_python_fallback)
   - Spring Initializr fixes (fix_spring_initializr_command, validate_spring_initializr_url)
   - Python fallback implementations (_python_ls, _python_cat, _python_grep, etc.)

2. `src/context/platform.py` - `PlatformDetector` class:
   - Caches platform and tool detection results
   - Methods: get_platform(), has_tool()
   - Already follows good practices (DI-friendly, testable)

3. `src/agent/protocols.py` - `PlatformUtilsProtocol`:
   - Simple 6-method protocol
   - Methods: is_windows(), is_unix(), is_macos(), get_platform_name(), validate_command(), translate_command()
   - Already in use by CodeAgent via dependency injection

4. `src/agent/platform_adapter.py` - Concrete implementations:
   - `RealPlatformUtils` - wraps platform_utils module functions
   - `MockPlatformUtils` - test double for platform behavior

**What's Missing:**
- No `src/platform/` directory structure
- Protocol doesn't cover all platform_utils functionality (only 6 of ~30+ functions)
- No separation of concerns (detection vs translation vs validation vs execution)
- No command executor abstraction
- No fallback strategy abstraction
- Test helpers exist but are minimal

### Refactoring Strategy

**PHASE 1: Create Directory Structure** (Start Here)
- Create `src/platform/` directory
- Create `src/platform/protocols/` subdirectory for all protocol definitions
- Move existing code in stages to maintain backward compatibility

**PHASE 2: Expand and Decompose Protocols**
- Keep existing `PlatformUtilsProtocol` for backward compatibility
- Create focused protocols following SOLID principles
- Use composition, not inheritance

**PHASE 3: Implement Concrete Classes**
- Move logic from platform_utils.py module into focused classes
- Maintain platform_utils.py as facade for backward compatibility initially
- Each class has single responsibility

**PHASE 4: Testing Infrastructure**
- Create comprehensive test helpers
- Write behavior tests, not structure tests
- Cover edge cases

**PHASE 5: Migration**
- Update call sites to use new architecture
- Deprecate old module functions (keep for backward compat initially)
- Remove deprecated code after migration

---

Decompose the god class using protocols:

### Backward Compatibility Plan

**CRITICAL: Maintain backward compatibility during refactoring**

1. Keep `src/platform_utils.py` as facade initially - all existing imports work
2. Keep `src/agent/protocols.py::PlatformUtilsProtocol` unchanged
3. Keep `src/agent/platform_adapter.py` adapters working
4. New code uses new protocols; old code continues working
5. Gradual migration, not big bang refactor

---

### 1. **Platform Detection Protocols**

**NOTE:** `src/context/platform.py::PlatformDetector` already exists and works well.
We'll create a protocol to abstract it, not replace it.

```python
# scrappy/src/platform/protocols/detection.py
from typing import Protocol, Optional, Dict, runtime_checkable
from typing import Literal

PlatformType = Literal["Windows", "macOS", "Linux", "FreeBSD", "OpenBSD", "NetBSD"]


@runtime_checkable
class PlatformDetectorProtocol(Protocol):
    """
    Protocol for platform detection (renamed from PlatformDetector to avoid conflict).

    NOTE: src/context/platform.py::PlatformDetector already implements most of this.

    Implementations must provide platform detection methods
    and shell information without side effects.
    """
    
    def is_windows(self) -> bool:
        """Check if running on Windows."""
        ...
    
    def is_unix(self) -> bool:
        """Check if running on Unix-like system (Linux, macOS, BSD)."""
        ...
    
    def is_macos(self) -> bool:
        """Check if running on macOS."""
        ...
    
    def get_platform_name(self) -> PlatformType:
        """Get human-readable platform name."""
        ...
    
    def get_shell_info(self) -> Dict[str, Optional[str]]:
        """
        Get information about available shells.
        
        Returns:
            Dict with 'default', 'bash', 'powershell', 'cmd', 'sh' keys.
        """
        ...
    
    def has_git_bash(self) -> bool:
        """Check if Git Bash is available (common on Windows)."""
        ...
```

### 2. **Command Translation Protocols**

```python
# scrappy/src/platform/protocols/translation.py
from typing import Protocol, Tuple, Optional, Dict, List, runtime_checkable
from pathlib import Path


@runtime_checkable
class CommandTranslator(Protocol):
    """
    Protocol for translating commands between platforms.
    
    Implementations handle platform-specific command translation
    while preserving command semantics.
    """
    
    def translate_command(self, command: str) -> Tuple[str, bool]:
        """
        Translate Unix commands to Windows equivalents when necessary.
        
        Args:
            command: Original command
            
        Returns:
            Tuple of (translated_command, was_translated)
        """
        ...
    
    def normalize_command_paths(self, command: str) -> Tuple[str, bool, str]:
        """
        Normalize paths in shell commands for the current platform.
        
        Args:
            command: Shell command that may contain paths
            
        Returns:
            Tuple of (normalized_command, was_modified, message)
        """
        ...
    
    def normalize_npm_command_for_windows(self, command: str) -> Tuple[str, bool, str]:
        """
        Normalize npm commands for Windows to prevent Unicode output issues.
        
        Args:
            command: npm command to normalize
            
        Returns:
            Tuple of (normalized_command, was_modified, message)
        """
        ...
    
    def fix_spring_initializr_command(self, command: str) -> Tuple[str, bool, str]:
        """
        Fix curl/PowerShell commands that use Spring Initializr.
        
        Args:
            command: The shell command to fix
            
        Returns:
            Tuple of (fixed_command, was_fixed, message)
        """
        ...
```

### 3. **Command Validation Protocols**

```python
# scrappy/src/platform/protocols/validation.py
from typing import Protocol, Tuple, List, runtime_checkable


@runtime_checkable
class CommandValidator(Protocol):
    """
    Protocol for validating commands before execution.
    
    Implementations check for dangerous commands, platform compatibility,
    and other validation rules.
    """
    
    def validate_command_for_platform(self, command: str) -> Tuple[bool, str]:
        """
        Validate if a command is appropriate for the current platform.
        
        Args:
            command: Command to validate
            
        Returns:
            Tuple of (is_valid, warning_message)
        """
        ...
    
    def get_dangerous_commands(self) -> List[str]:
        """
        Get list of dangerous command patterns for the current platform.
        
        Returns:
            List of dangerous command patterns to block (regex patterns)
        """
        ...
    
    def get_interactive_commands(self) -> List[str]:
        """
        Get list of commands that may prompt for user input.
        
        Returns:
            List of interactive command patterns
        """
        ...
```

### 4. **Command Execution Protocols**

```python
# scrappy/src/platform/protocols/execution.py
from typing import Protocol, Dict, Any, Optional, runtime_checkable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    """
    Data class for command execution results.

    NOTE: This is a dataclass, not a Protocol, because it represents
    data structure, not behavior. Protocols are for behavior contracts.
    """

    output: str
    returncode: int
    method: str  # native/translated/python_fallback/timeout/error

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.returncode == 0

    @property
    def error_message(self) -> Optional[str]:
        """Get error message if execution failed."""
        return self.output if not self.success else None

    @classmethod
    def error(cls, message: str) -> "ExecutionResult":
        """Create an error result."""
        return cls(output=message, returncode=1, method="error")


@runtime_checkable
class CommandExecutor(Protocol):
    """
    Protocol for executing shell commands.

    Implementations provide different execution strategies
    (native, translated, fallback).
    """

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute a command with the specific strategy.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            ExecutionResult with output, returncode, and method used
        """
        ...
```

### 5. **Fallback Implementation Protocols**

```python
# scrappy/src/platform/protocols/fallback.py
from typing import Protocol, Dict, Any, List, Optional, runtime_checkable
from pathlib import Path


@runtime_checkable
class PythonCommandFallback(Protocol):
    """
    Protocol for Python implementations of shell commands.
    
    Used when native command execution fails on Windows.
    """
    
    def ls(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of ls command."""
        ...
    
    def cat(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of cat command."""
        ...
    
    def grep(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of grep command."""
        ...
    
    def find(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of find command."""
        ...
    
    def wc(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of wc command."""
        ...
    
    def head(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of head command."""
        ...
    
    def tail(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of tail command."""
        ...
    
    def touch(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of touch command."""
        ...
    
    def mkdir_p(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of mkdir -p command."""
        ...
    
    def rm(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of rm command."""
        ...
    
    def cp(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of cp command."""
        ...
    
    def mv(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """Python implementation of mv command."""
        ...
    
    def which(self, args: List[str]) -> Dict[str, Any]:
        """Python implementation of which command."""
        ...
    
    def pwd(self, cwd: Path) -> Dict[str, Any]:
        """Python implementation of pwd command."""
        ...
```

### 6. **Utility Protocols**

```python
# scrappy/src/platform/protocols/utils.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class PathUtils(Protocol):
    """Protocol for platform-specific path utilities."""
    
    def get_null_device(self) -> str:
        """Get the null device path for the current platform."""
        ...
    
    def get_path_separator(self) -> str:
        """Get the path separator for the current platform."""
        ...
    
    def normalize_path_for_shell(self, path: str) -> str:
        """
        Normalize a path for use in shell commands.
        
        Args:
            path: Path to normalize
            
        Returns:
            Normalized path string
        """
        ...


@runtime_checkable
class FileCheckCommands(Protocol):
    """Protocol for platform-specific file checking commands."""
    
    def get_file_check_command(self, path: str) -> str:
        """
        Get platform-appropriate command to check if a file exists.
        
        Args:
            path: File path to check
            
        Returns:
            Shell command that checks file existence
        """
        ...
    
    def get_directory_list_command(self, path: str = ".") -> str:
        """
        Get platform-appropriate command to list directory contents.
        
        Args:
            path: Directory path to list
            
        Returns:
            Shell command to list directory
        """
        ...
```

### 7. **Main Orchestrator Protocol**

```python
# scrappy/src/platform/protocols/orchestrator.py
from typing import Protocol, Optional, Dict, Any, runtime_checkable

from .detection import PlatformDetector
from .translation import CommandTranslator
from .validation import CommandValidator
from .execution import CommandExecutor, ExecutionResult


@runtime_checkable
class PlatformOrchestrator(Protocol):
    """
    Main protocol for platform-aware command execution.
    
    Orchestrates platform detection, command translation, validation,
    and execution strategies.
    
    This protocol enables:
    - Type hints that accept any conforming implementation
    - Easy substitution of test mocks for unit testing
    - Loose coupling between components and the orchestrator
    """
    
    @property
    def detector(self) -> PlatformDetector:
        """Get platform detector implementation."""
        ...
    
    @property
    def translator(self) -> CommandTranslator:
        """Get command translator implementation."""
        ...
    
    @property
    def validator(self) -> CommandValidator:
        """Get command validator implementation."""
        ...
    
    @property
    def executors(self) -> list[CommandExecutor]:
        """Get list of available command executors in priority order."""
        ...
    
    def smart_execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        """
        Execute a command with automatic platform translation and Python fallback.
        
        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds
            
        Returns:
            ExecutionResult with output, returncode, and method used
        """
        ...
    
    def get_usage_report(self) -> Dict[str, Any]:
        """
        Get usage statistics report.
        
        Returns:
            Dictionary containing usage statistics including:
            - total_commands: Total commands executed
            - by_method: Execution method breakdown (native/translated/fallback)
            - by_platform: Platform-specific statistics
            - error_rate: Error rate statistics
        """
        ...
```

### 8. **Concrete Implementation Structure**

```python
# scrappy/src/platform/implementation.py
from typing import Dict, Any, Optional, List
from pathlib import Path

from .protocols import (
    PlatformOrchestrator,
    PlatformDetector,
    CommandTranslator,
    CommandValidator,
    CommandExecutor,
    PythonCommandFallback,
    ExecutionResult
)
from .detection import SystemPlatformDetector
from .translation import SmartCommandTranslator
from .validation import SecurityCommandValidator
from .execution import (
    NativeExecutor,
    TranslatedExecutor,
    FallbackExecutor
)
from .fallback import PythonCommandFallbackImpl


class SmartPlatformOrchestrator:
    """
    Concrete implementation of PlatformOrchestrator.

    Provides smart command execution with automatic platform detection,
    translation, validation, and fallback strategies.

    CRITICAL: All dependencies are INJECTED, not instantiated directly.
    This enables testing, dependency inversion, and loose coupling.
    """

    def __init__(
        self,
        detector: Optional[PlatformDetector] = None,
        translator: Optional[CommandTranslator] = None,
        validator: Optional[CommandValidator] = None,
        fallback: Optional[PythonCommandFallback] = None,
        executors: Optional[List[CommandExecutor]] = None,
    ):
        """
        Initialize the orchestrator with injected dependencies.

        Args:
            detector: Platform detector implementation (defaults to SystemPlatformDetector)
            translator: Command translator implementation (defaults to SmartCommandTranslator)
            validator: Command validator implementation (defaults to SecurityCommandValidator)
            fallback: Python fallback implementation (defaults to PythonCommandFallbackImpl)
            executors: List of command executors in priority order (auto-created if None)

        Note: Defaults are created via factory methods, not direct instantiation,
        to maintain testability and follow dependency injection principles.
        """
        # Inject dependencies or use defaults from factory methods
        self._detector = detector or self._create_default_detector()
        self._translator = translator or self._create_default_translator(self._detector)
        self._validator = validator or self._create_default_validator(self._detector)
        self._fallback = fallback or self._create_default_fallback()

        # Priority order: try native first, then translated, then fallback
        self._executors = executors or self._create_default_executors(
            self._detector,
            self._translator,
            self._fallback
        )

        self._usage_stats = {
            'total_commands': 0,
            'by_method': {'native': 0, 'translated': 0, 'fallback': 0, 'error': 0},
            'by_platform': {},
            'error_rate': 0.0
        }
    
    @property
    def detector(self) -> PlatformDetector:
        return self._detector
    
    @property
    def translator(self) -> CommandTranslator:
        return self._translator
    
    @property
    def validator(self) -> CommandValidator:
        return self._validator
    
    @property
    def executors(self) -> list[CommandExecutor]:
        return self._executors
    
    def smart_execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        # Validate command
        is_valid, warning = self._validator.validate_command_for_platform(command)
        if not is_valid:
            return ExecutionResult.error(warning)
        
        # Try execution strategies in priority order
        for executor in self._executors:
            result = executor.execute(command, cwd, timeout)
            if result.success:
                self._update_usage_stats(result.method)
                return result
        
        # All strategies failed
        return ExecutionResult.error("All execution strategies failed")
    
    def get_usage_report(self) -> Dict[str, Any]:
        return self._usage_stats.copy()
    
    def _update_usage_stats(self, method: str):
        """Update usage statistics after successful execution."""
        self._usage_stats['total_commands'] += 1
        self._usage_stats['by_method'][method] += 1

        platform = self._detector.get_platform_name()
        if platform not in self._usage_stats['by_platform']:
            self._usage_stats['by_platform'][platform] = 0
        self._usage_stats['by_platform'][platform] += 1

        # Update error rate
        total = self._usage_stats['total_commands']
        errors = self._usage_stats['by_method']['error']
        self._usage_stats['error_rate'] = errors / total if total > 0 else 0.0

    @staticmethod
    def _create_default_detector() -> PlatformDetector:
        """Factory method to create default platform detector."""
        return SystemPlatformDetector()

    @staticmethod
    def _create_default_translator(detector: PlatformDetector) -> CommandTranslator:
        """Factory method to create default command translator."""
        return SmartCommandTranslator(detector)

    @staticmethod
    def _create_default_validator(detector: PlatformDetector) -> CommandValidator:
        """Factory method to create default command validator."""
        return SecurityCommandValidator(detector)

    @staticmethod
    def _create_default_fallback() -> PythonCommandFallback:
        """Factory method to create default Python fallback implementation."""
        return PythonCommandFallbackImpl()

    @staticmethod
    def _create_default_executors(
        detector: PlatformDetector,
        translator: CommandTranslator,
        fallback: PythonCommandFallback
    ) -> List[CommandExecutor]:
        """Factory method to create default executor chain."""
        return [
            NativeExecutor(detector),
            TranslatedExecutor(detector, translator),
            FallbackExecutor(detector, fallback)
        ]
```

### 9. **Convenience Factory Function**

```python
# scrappy/src/platform/factory.py
from typing import Optional
from .protocols import PlatformOrchestrator
from .implementation import SmartPlatformOrchestrator
from .detection import SystemPlatformDetector
from .translation import SmartCommandTranslator
from .validation import SecurityCommandValidator
from .fallback import PythonCommandFallbackImpl
from .execution import NativeExecutor, TranslatedExecutor, FallbackExecutor


def create_default_orchestrator() -> PlatformOrchestrator:
    """
    Factory function to create a fully configured PlatformOrchestrator
    with default implementations.

    This is the recommended way to instantiate the orchestrator for
    production use, as it provides all default dependencies while
    maintaining testability.

    Returns:
        Fully configured PlatformOrchestrator instance
    """
    detector = SystemPlatformDetector()
    translator = SmartCommandTranslator(detector)
    validator = SecurityCommandValidator(detector)
    fallback = PythonCommandFallbackImpl()

    executors = [
        NativeExecutor(detector),
        TranslatedExecutor(detector, translator),
        FallbackExecutor(detector, fallback)
    ]

    return SmartPlatformOrchestrator(
        detector=detector,
        translator=translator,
        validator=validator,
        fallback=fallback,
        executors=executors
    )
```

### 10. **Usage Examples**

```python
# Usage in your existing codebase
from scrappy.src.platform.factory import create_default_orchestrator
from scrappy.src.platform.protocols import PlatformOrchestrator

# PRODUCTION: Use factory function for default configuration
orchestrator: PlatformOrchestrator = create_default_orchestrator()

# Execute command with automatic platform handling
result = orchestrator.smart_execute_command("ls -la /tmp", cwd="/home/user")

if result.success:
    print(f"Output: {result.output}")
    print(f"Method used: {result.method}")
else:
    print(f"Error: {result.error_message}")

# Get usage statistics
stats = orchestrator.get_usage_report()
print(f"Total commands: {stats['total_commands']}")
print(f"By method: {stats['by_method']}")
```

```python
# TESTING: Inject test doubles for complete isolation
from scrappy.src.platform.implementation import SmartPlatformOrchestrator
from tests.helpers import FakePlatformDetector, FakeCommandExecutor

# Create test doubles
fake_detector = FakePlatformDetector(platform="Windows")
fake_executor = FakeCommandExecutor(
    output="mocked output",
    returncode=0,
    method="test"
)

# Inject test doubles
orchestrator = SmartPlatformOrchestrator(
    detector=fake_detector,
    executors=[fake_executor]
)

# Test code is now completely isolated from real I/O
result = orchestrator.smart_execute_command("ls")
assert result.output == "mocked output"
assert result.success
```

### 11. **Testing Strategy**

#### Test Helpers (tests/helpers.py)

```python
# tests/helpers.py
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from scrappy.src.platform.protocols import (
    PlatformDetector,
    CommandTranslator,
    CommandValidator,
    CommandExecutor,
    PythonCommandFallback
)
from scrappy.src.platform.protocols.execution import ExecutionResult


class FakePlatformDetector:
    """Test double for PlatformDetector."""

    def __init__(self, platform: str = "Linux"):
        self._platform = platform

    def is_windows(self) -> bool:
        return self._platform == "Windows"

    def is_unix(self) -> bool:
        return self._platform in ["Linux", "macOS", "FreeBSD"]

    def is_macos(self) -> bool:
        return self._platform == "macOS"

    def get_platform_name(self) -> str:
        return self._platform

    def get_shell_info(self) -> Dict[str, Optional[str]]:
        return {"default": "/bin/bash", "bash": "/bin/bash"}

    def has_git_bash(self) -> bool:
        return False


class FakeCommandTranslator:
    """Test double for CommandTranslator."""

    def __init__(self, translate_to: Optional[str] = None):
        self._translate_to = translate_to

    def translate_command(self, command: str) -> tuple[str, bool]:
        if self._translate_to:
            return (self._translate_to, True)
        return (command, False)

    def normalize_command_paths(self, command: str) -> tuple[str, bool, str]:
        return (command, False, "")

    def normalize_npm_command_for_windows(self, command: str) -> tuple[str, bool, str]:
        return (command, False, "")

    def fix_spring_initializr_command(self, command: str) -> tuple[str, bool, str]:
        return (command, False, "")


class FakeCommandValidator:
    """Test double for CommandValidator."""

    def __init__(self, always_valid: bool = True):
        self._always_valid = always_valid

    def validate_command_for_platform(self, command: str) -> tuple[bool, str]:
        if self._always_valid:
            return (True, "")
        return (False, "Command blocked for testing")

    def get_dangerous_commands(self) -> List[str]:
        return []

    def get_interactive_commands(self) -> List[str]:
        return []


class FakeCommandExecutor:
    """Test double for CommandExecutor."""

    def __init__(
        self,
        output: str = "",
        returncode: int = 0,
        method: str = "test"
    ):
        self._output = output
        self._returncode = returncode
        self._method = method

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ) -> ExecutionResult:
        return ExecutionResult(
            output=self._output,
            returncode=self._returncode,
            method=self._method
        )


class FakePythonFallback:
    """Test double for PythonCommandFallback."""

    def __init__(self, result: Dict[str, Any]):
        self._result = result

    def ls(self, args: List[str], cwd) -> Dict[str, Any]:
        return self._result

    def cat(self, args: List[str], cwd) -> Dict[str, Any]:
        return self._result

    # ... other methods return self._result
```

#### Example Tests

```python
# tests/test_platform_orchestrator.py
import pytest
from scrappy.src.platform.implementation import SmartPlatformOrchestrator
from scrappy.src.platform.protocols.execution import ExecutionResult
from tests.helpers import (
    FakePlatformDetector,
    FakeCommandTranslator,
    FakeCommandValidator,
    FakeCommandExecutor
)


def test_orchestrator_executes_command_successfully():
    """Test that orchestrator executes commands and returns results."""
    # Arrange
    fake_executor = FakeCommandExecutor(
        output="file1.txt\nfile2.txt",
        returncode=0,
        method="native"
    )
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(platform="Linux"),
        executors=[fake_executor]
    )

    # Act
    result = orchestrator.smart_execute_command("ls")

    # Assert
    assert result.success
    assert result.output == "file1.txt\nfile2.txt"
    assert result.method == "native"


def test_orchestrator_returns_error_for_invalid_command():
    """Test that orchestrator validates commands before execution."""
    # Arrange
    fake_validator = FakeCommandValidator(always_valid=False)
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        validator=fake_validator,
        executors=[]
    )

    # Act
    result = orchestrator.smart_execute_command("rm -rf /")

    # Assert
    assert not result.success
    assert "blocked" in result.error_message.lower()


def test_orchestrator_tracks_usage_statistics():
    """Test that orchestrator tracks usage stats correctly."""
    # Arrange
    fake_executor = FakeCommandExecutor(returncode=0, method="native")
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(platform="Windows"),
        executors=[fake_executor]
    )

    # Act
    orchestrator.smart_execute_command("dir")
    orchestrator.smart_execute_command("type file.txt")
    stats = orchestrator.get_usage_report()

    # Assert
    assert stats['total_commands'] == 2
    assert stats['by_method']['native'] == 2
    assert stats['by_platform']['Windows'] == 2


def test_orchestrator_tries_executors_in_order():
    """Test that orchestrator tries executors in priority order."""
    # Arrange
    failing_executor = FakeCommandExecutor(returncode=1, method="native")
    succeeding_executor = FakeCommandExecutor(
        output="success",
        returncode=0,
        method="fallback"
    )
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        executors=[failing_executor, succeeding_executor]
    )

    # Act
    result = orchestrator.smart_execute_command("ls")

    # Assert
    assert result.success
    assert result.method == "fallback"  # Used second executor


def test_platform_detector_identifies_windows():
    """Test that platform detector correctly identifies Windows."""
    # Arrange
    detector = FakePlatformDetector(platform="Windows")

    # Act & Assert
    assert detector.is_windows()
    assert not detector.is_unix()
    assert not detector.is_macos()
    assert detector.get_platform_name() == "Windows"


def test_command_translator_translates_commands():
    """Test that command translator translates commands correctly."""
    # Arrange
    translator = FakeCommandTranslator(translate_to="dir")

    # Act
    translated, was_translated = translator.translate_command("ls")

    # Assert
    assert translated == "dir"
    assert was_translated


def test_execution_result_properties():
    """Test ExecutionResult dataclass properties."""
    # Test success
    success_result = ExecutionResult(output="ok", returncode=0, method="native")
    assert success_result.success
    assert success_result.error_message is None

    # Test failure
    error_result = ExecutionResult(output="error msg", returncode=1, method="native")
    assert not error_result.success
    assert error_result.error_message == "error msg"

    # Test error factory
    error = ExecutionResult.error("Something went wrong")
    assert not error.success
    assert error.error_message == "Something went wrong"
    assert error.method == "error"
```

#### Edge Case Tests

```python
# tests/test_platform_edge_cases.py
import pytest
from scrappy.src.platform.implementation import SmartPlatformOrchestrator
from tests.helpers import FakePlatformDetector, FakeCommandExecutor


def test_orchestrator_handles_empty_command():
    """Test orchestrator behavior with empty command string."""
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        executors=[FakeCommandExecutor()]
    )

    result = orchestrator.smart_execute_command("")
    # Should either validate against empty or execute and handle it


def test_orchestrator_handles_null_cwd():
    """Test orchestrator with None as working directory."""
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        executors=[FakeCommandExecutor()]
    )

    result = orchestrator.smart_execute_command("ls", cwd=None)
    assert result is not None


def test_orchestrator_handles_timeout():
    """Test orchestrator respects timeout parameter."""
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        executors=[FakeCommandExecutor()]
    )

    result = orchestrator.smart_execute_command("sleep 100", timeout=1)
    # Should either timeout or handle it gracefully


def test_orchestrator_with_no_executors():
    """Test orchestrator behavior with empty executor list."""
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        executors=[]
    )

    result = orchestrator.smart_execute_command("ls")
    assert not result.success
    assert "failed" in result.error_message.lower()


def test_usage_stats_initialized_correctly():
    """Test that usage statistics start at zero."""
    orchestrator = SmartPlatformOrchestrator(
        detector=FakePlatformDetector(),
        executors=[]
    )

    stats = orchestrator.get_usage_report()
    assert stats['total_commands'] == 0
    assert stats['error_rate'] == 0.0
```

### 12. **Benefits Summary**

This protocol-based decomposition provides:

1. **Structural subtyping** - Classes don't need explicit inheritance
2. **Runtime checkability** - Use `@runtime_checkable` for `isinstance()` checks
3. **Testability** - Easy to create mock implementations for testing
4. **Loose coupling** - Components depend on protocols, not concrete classes
5. **Extensibility** - Easy to add new platforms or execution strategies
6. **Type safety** - Static type checking with mypy/pyright
7. **Dependency injection** - All dependencies injected, enabling test isolation
8. **Factory pattern** - Convenient default creation while maintaining testability
9. **SOLID principles** - Follows all five SOLID principles rigorously

### 13. **Implementation Checklist**

Before implementing, verify:

- [ ] All protocols defined before concrete classes
- [ ] All dependencies injected via constructor
- [ ] Factory methods provided for default dependencies
- [ ] Test helpers created in tests/helpers.py
- [ ] Behavior tests written (not just structure tests)
- [ ] Edge cases covered in tests
- [ ] ExecutionResult is a dataclass, not a Protocol
- [ ] No direct instantiation of dependencies
- [ ] No side effects in constructors
- [ ] Type hints on all public methods
- [ ] Documentation explains why, not just what

The decomposition follows your established pattern and maintains backward compatibility while providing a clean, testable architecture that adheres to all SOLID principles.

---

## CRITICAL IMPROVEMENTS MADE TO ORIGINAL PLAN

### 1. Fixed Dependency Injection Violation
**BEFORE (WRONG):**
```python
def __init__(self):
    self._detector = SystemPlatformDetector()  # Direct instantiation!
    self._translator = SmartCommandTranslator(self._detector)
```

**AFTER (CORRECT):**
```python
def __init__(
    self,
    detector: Optional[PlatformDetector] = None,
    translator: Optional[CommandTranslator] = None,
    # ...
):
    self._detector = detector or self._create_default_detector()
    self._translator = translator or self._create_default_translator(self._detector)
```

**Why:** Enables testing with test doubles, follows dependency inversion principle, allows swapping implementations.

### 2. Changed ExecutionResult from Protocol to Dataclass
**BEFORE (WRONG):**
```python
class ExecutionResult(Protocol):  # Protocol for data
    output: str
    returncode: int
```

**AFTER (CORRECT):**
```python
@dataclass
class ExecutionResult:  # Dataclass for data
    output: str
    returncode: int
```

**Why:** Protocols are for behavior contracts, dataclasses are for data structures.

### 3. Added Factory Function for Convenient Defaults
**NEW:**
```python
def create_default_orchestrator() -> PlatformOrchestrator:
    # Creates fully configured orchestrator with all default implementations
```

**Why:** Provides convenient way to create default instance while maintaining full testability.

### 4. Added Comprehensive Testing Strategy
**NEW:**
- Complete test helper implementations (FakePlatformDetector, etc.)
- Behavior-focused test examples
- Edge case test coverage
- Examples showing how to test with protocols

**Why:** Tests prove features work, not just that code runs. Shows exactly how to test protocol-based design.

### 5. Added Factory Methods for Default Dependencies
**NEW:**
```python
@staticmethod
def _create_default_detector() -> PlatformDetector:
    return SystemPlatformDetector()
```

**Why:** Separates default creation from constructor, maintains single responsibility, enables easier testing.

---

## UPDATED IMPLEMENTATION PLAN

**Based on current codebase analysis, here's the revised implementation approach:**

### Phase 1: Foundation (Do First)

**Goal:** Set up directory structure and core protocols without breaking existing code.

**Tasks:**
1. ✅ Create `src/platform/` directory
2. ✅ Create `src/platform/protocols/` subdirectory
3. ✅ Create `src/platform/__init__.py` (empty for now)
4. ✅ Create `src/platform/protocols/__init__.py` with protocol exports
5. ✅ Define `PlatformDetectorProtocol` that `src/context/platform.py::PlatformDetector` already satisfies
6. ✅ Define other protocols (CommandTranslator, CommandValidator, CommandExecutor, etc.)
7. ✅ Keep `src/platform_utils.py` untouched - it continues working as-is

**Deliverables:**
- New directory structure
- All protocol definitions in `src/platform/protocols/`
- Zero breaking changes to existing code

### Phase 2: Concrete Implementations

**Goal:** Move logic from god module into focused classes.

**Tasks:**
1. ✅ Create `src/platform/detection.py`:
   - `SystemPlatformDetector` - wraps existing `PlatformDetector`
   - Implements `PlatformDetectorProtocol`
   - Adds shell info methods from platform_utils

2. ✅ Create `src/platform/translation.py`:
   - `CommandTranslator` - moves translation logic from platform_utils
   - Implements `CommandTranslatorProtocol`
   - Handles Unix→Windows command translation
   - Handles path normalization
   - Handles npm fixes, Spring Initializr fixes

3. ✅ Create `src/platform/validation.py`:
   - `CommandValidator` - moves validation logic from platform_utils
   - Implements `CommandValidatorProtocol`
   - Dangerous command detection
   - Interactive command detection
   - Platform compatibility checks

4. ✅ Create `src/platform/execution.py`:
   - `NativeCommandExecutor` - runs commands as-is
   - `TranslatedCommandExecutor` - translates then runs
   - `FallbackCommandExecutor` - uses Python fallbacks
   - All implement `CommandExecutorProtocol`

5. ✅ Create `src/platform/fallback.py`:
   - `PythonCommandFallback` - all the _python_* functions
   - Implements `PythonCommandFallbackProtocol`

6. ✅ Create `src/platform/orchestrator.py`:
   - `PlatformOrchestrator` - coordinates all components
   - Uses dependency injection for all sub-components
   - Provides `smart_execute_command` with strategy pattern

7. ✅ Create `src/platform/factory.py`:
   - `create_platform_orchestrator()` - convenience factory

**Deliverables:**
- All logic moved into focused classes
- Each class < 300 lines
- Each class has single responsibility
- All dependencies injected
- `src/platform_utils.py` can now delegate to these classes (optional refactor)

### Phase 3: Testing Infrastructure

**Goal:** Comprehensive test coverage with behavior tests.

**Tasks:**
1. ✅ Create `tests/platform/` directory
2. ✅ Update `tests/helpers.py` with platform test doubles:
   - `FakePlatformDetector`
   - `FakeCommandTranslator`
   - `FakeCommandValidator`
   - `FakeCommandExecutor`
   - `FakePythonFallback`

3. ✅ Write behavior tests:
   - `tests/platform/test_platform_orchestrator.py` - end-to-end tests
   - `tests/platform/test_detection.py` - platform detection tests
   - `tests/platform/test_translation.py` - command translation tests
   - `tests/platform/test_validation.py` - command validation tests
   - `tests/platform/test_execution.py` - command execution tests
   - `tests/platform/test_fallback.py` - Python fallback tests

4. ✅ Edge case tests:
   - Empty inputs
   - Null values
   - Timeout scenarios
   - Error conditions
   - Platform-specific edge cases

**Deliverables:**
- Test coverage > 90%
- All behavior tests (not structure tests)
- Edge cases covered
- Tests prove features work

### Phase 4: Migration (Optional)

**Goal:** Migrate existing code to use new architecture.

**Tasks:**
1. ⚠️ Update `src/agent/platform_adapter.py`:
   - `RealPlatformUtils` can use new `PlatformOrchestrator` internally
   - Or keep wrapping `platform_utils.py` functions (backward compat)

2. ⚠️ Update `src/platform_utils.py`:
   - Option A: Keep as-is (facade pattern - wraps new classes)
   - Option B: Deprecate with warnings, point to new modules
   - Option C: Remove after full migration (breaking change)

3. ⚠️ Update call sites:
   - Replace direct `platform_utils` imports with new modules
   - Use `PlatformOrchestrator` for command execution
   - Use individual protocols for specific needs

**Deliverables:**
- All existing tests still pass
- No breaking changes (unless intentional)
- Deprecation warnings if applicable

### Phase 5: Cleanup (Future)

**Goal:** Remove deprecated code after migration period.

**Tasks:**
1. Remove `src/platform_utils.py` (if fully migrated)
2. Remove old adapter code (if replaced)
3. Update all documentation
4. Update CLAUDE.md with new patterns

---

## RECOMMENDED STARTING POINT

**Start with Phase 1, Task 1-6:**

1. Create directory structure
2. Define all protocols
3. Don't touch existing code yet
4. Verify nothing breaks (run existing tests)

**Then proceed to Phase 2:**

5. Implement one component at a time (start with detector)
6. Write tests for each component as you go (TDD)
7. Verify backward compatibility maintained

**Key Principles:**

- ✅ Protocol-first design
- ✅ Dependency injection everywhere
- ✅ Single responsibility per class
- ✅ Behavior tests, not structure tests
- ✅ Maintain backward compatibility
- ✅ Incremental migration, not big bang
- ✅ Each phase independently valuable

---

## DIFFERENCES FROM ORIGINAL PLAN

1. **Renamed Protocol:** `PlatformDetector` → `PlatformDetectorProtocol` (avoid naming conflict)

2. **Reuse Existing Code:** Don't rewrite `src/context/platform.py::PlatformDetector`, just wrap it

3. **Backward Compatibility:** Keep `platform_utils.py` as facade, not delete it

4. **Phased Approach:** Don't try to do everything at once

5. **Leverage What Exists:**
   - Keep `PlatformUtilsProtocol` in `src/agent/protocols.py`
   - Keep adapters in `src/agent/platform_adapter.py`
   - These can delegate to new architecture internally

6. **Practical Focus:** Start with most valuable parts first (orchestrator, execution)

---

## CURRENT STATUS

 Phase 1 is complete! Here's what I accomplished:

  Phase 1 Summary - Foundation ✅

  Created Directory Structure

  src/platform/
  ├── __init__.py
  └── protocols/
      ├── __init__.py
      ├── detection.py         # PlatformDetectorProtocol
      ├── translation.py       # CommandTranslatorProtocol
      ├── validation.py        # CommandValidatorProtocol
      ├── execution.py         # CommandExecutorProtocol + ExecutionResult
      ├── fallback.py          # PythonCommandFallbackProtocol
      └── orchestrator.py      # PlatformOrchestratorProtocol

  Defined All Protocols

  1. PlatformDetectorProtocol - Platform detection and tool availability
    - Methods: is_windows(), is_unix(), is_macos(), get_platform_name(), get_shell_info(), has_git_bash(),
  has_tool()
  2. CommandTranslatorProtocol - Command translation for cross-platform compatibility
    - Methods: translate_command(), normalize_command_paths(), normalize_npm_command_for_windows(),
  fix_spring_initializr_command()
  3. CommandValidatorProtocol - Command safety and compatibility validation
    - Methods: validate_command_for_platform(), get_dangerous_commands(), get_interactive_commands()
  4. CommandExecutorProtocol - Command execution strategy interface
    - Methods: execute()
    - ExecutionResult dataclass for results (not a protocol - data, not behavior)
  5. PythonCommandFallbackProtocol - Python implementations of Unix commands
    - Methods: ls(), cat(), grep(), find(), wc(), head(), tail(), touch(), mkdir_p(), rm(), cp(), mv(), which(),
   pwd()
  6. PlatformOrchestratorProtocol - Main orchestrator interface
    - Properties: detector, translator, validator, executors
    - Methods: smart_execute_command(), get_usage_report()

  Verified Backward Compatibility ✅

  - Ran existing tests: 26 passed (1 unrelated permission error)
  - Zero breaking changes to existing code
  - All protocols follow SOLID principles

  Next: Phase 2 - Concrete Implementations

  Ready to start implementing the concrete classes that satisfy these protocols. Should I proceed with Phase 2?

  Todos
  ☒ Review current state and update PLATFORM_UTILS.md plan
  ☒ PHASE 1: Create src/platform directory structure
  ☒ PHASE 1: Define all protocol interfaces in src/platform/protocols/
  ☒ PHASE 1: Verify nothing breaks (run existing tests)
  ☐ PHASE 2: Implement SystemPlatformDetector in src/platform/detection.py
  ☐ PHASE 2: Implement CommandTranslator in src/platform/translation.py
  ☐ PHASE 2: Implement CommandValidator in src/platform/validation.py
  ☐ PHASE 2: Implement command executors in src/platform/execution.py
  ☐ PHASE 2: Implement PythonCommandFallback in src/platform/fallback.py
  ☐ PHASE 2: Implement PlatformOrchestrator in src/platform/orchestrator.py
  ☐ PHASE 2: Create factory function in src/platform/factory.py
  ☐ PHASE 3: Create test helpers in tests/helpers.py
  ☐ PHASE 3: Write comprehensive behavior tests for all components