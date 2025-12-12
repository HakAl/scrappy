"""
Test helper classes and utilities.

Provides mock adapters and utilities for testing the orchestrator and agent.
"""

from typing import List, Optional, Dict, Any
from unittest.mock import Mock
from pathlib import Path
import tempfile

from scrappy.providers.base import LLMResponse
from scrappy.orchestrator_adapter import NullContext, ContextProvider
from scrappy.infrastructure import InMemoryFileSystem, FileSystemProtocol
from scrappy.infrastructure.protocols import PathProviderProtocol
from scrappy.cli.session_context import SessionContext


class TestPathProvider:
    """
    Mock path provider for testing.

    Returns in-memory or temporary paths to prevent test pollution.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize mock path provider.

        Args:
            base_dir: Base directory for all paths (defaults to in-memory)
        """
        self._base_dir = base_dir or Path(tempfile.gettempdir()) / "test"
        self._data_dir = self._base_dir / ".scrappy"

    def data_dir(self) -> Path:
        """Get test data directory."""
        return self._data_dir

    def session_file(self) -> Path:
        """Get test session file path."""
        return self._data_dir / "session.json"

    def rate_limits_file(self) -> Path:
        """Get test rate limits file path."""
        return self._data_dir / "rate_limits.json"

    def audit_file(self) -> Path:
        """Get test audit file path."""
        return self._data_dir / "audit.json"

    def response_cache_file(self) -> Path:
        """Get test response cache file path."""
        return self._data_dir / "response_cache.json"

    def context_file(self) -> Path:
        """Get test context file path."""
        return self._data_dir / "context.json"

    def ensure_data_dir(self) -> None:
        """No-op for mock - don't create real directories."""
        pass


class MockWorkingMemory:
    """Mock working memory for testing."""

    def __init__(self):
        self._data = {
            'files': {},
            'searches': [],
            'git_ops': [],
            'discoveries': []
        }

    def remember_file_read(self, path: str, content: str, lines: int = 0):
        """Store file read in memory."""
        self._data['files'][path] = {'content': content, 'lines': lines}

    def remember_search(self, query: str, results: list):
        """Store search results in memory."""
        self._data['searches'].append({'query': query, 'results': results})

    def remember_git_operation(self, operation: str, output: str):
        """Store git operation in memory."""
        self._data['git_ops'].append({'operation': operation, 'output': output})

    def add_discovery(self, finding: str, location: str = ""):
        """Add a discovery to memory."""
        self._data['discoveries'].append({'content': finding, 'source': location})

    def get_summary(self) -> dict:
        """Get summary of working memory."""
        return {
            'files_cached': len(self._data['files']),
            'cached_files': list(self._data['files'].keys()),
            'recent_searches': len(self._data['searches']),
            'git_operations': len(self._data['git_ops']),
            'discoveries': len(self._data['discoveries'])
        }

    def get_context_string(self) -> str:
        """Get context string for LLM augmentation."""
        return ""

    def clear(self):
        """Clear all working memory."""
        self._data = {
            'files': {},
            'searches': [],
            'git_ops': [],
            'discoveries': []
        }


def make_response(
    content: str = '{"thought": "test", "action": "complete", "is_complete": true}',
    provider: str = "mock",
    model: str = "",
    tokens_used: int = 0
) -> LLMResponse:
    """
    Factory function to create LLMResponse with sensible defaults.

    Isolates tests from LLMResponse constructor signature changes.

    Args:
        content: Response content (default: completion JSON)
        provider: Provider name
        model: Model name (default: empty)
        tokens_used: Token count

    Returns:
        LLMResponse instance
    """
    return LLMResponse(
        content=content,
        model=model,
        provider=provider,
        tokens_used=tokens_used
    )


class ConfigurableTestOrchestrator:
    """
    Flexible test orchestrator that can be configured for various test scenarios.

    Supports:
    - Provider recommendation with configurable logic
    - Call tracking for assertions
    - Rate limit simulation
    - Provider rotation
    - Auto-selection when provider is None

    Usage:
        # Simple tracking
        orch = ConfigurableTestOrchestrator()

        # With specific provider recommendation
        orch = ConfigurableTestOrchestrator(recommended_provider='cerebras')

        # With rate limiting
        orch = ConfigurableTestOrchestrator(rate_limited={'gemini'})

        # With rotation
        orch = ConfigurableTestOrchestrator(rotation=['cerebras', 'groq', 'gemini'])

        # With custom response
        orch = ConfigurableTestOrchestrator(
            response_content='{"thought": "test", "action": "read_file", ...}'
        )
    """

    def __init__(
        self,
        available_providers: Optional[List[str]] = None,
        recommended_provider: str = 'cerebras',
        rate_limited: Optional[set] = None,
        rotation: Optional[List[str]] = None,
        response_content: str = '{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}',
        response_tokens: int = 100,
        context_explored: bool = False
    ):
        """
        Initialize test orchestrator with configurable behavior.

        Args:
            available_providers: List of available provider names
            recommended_provider: Default provider to recommend
            rate_limited: Set of provider names that are rate limited
            rotation: List of providers to rotate through (if set, overrides recommended_provider)
            response_content: JSON content to return from delegate()
            response_tokens: Token count for responses
            context_explored: Whether context.is_explored() returns True
        """
        self.available_providers = available_providers or ['cerebras', 'groq', 'gemini']
        self._recommended_provider = recommended_provider
        self.rate_limited_providers = rate_limited or set()
        self.rotation = rotation
        self.response_content = response_content
        self.response_tokens = response_tokens

        # Tracking
        self.delegate_calls: List[Dict[str, Any]] = []
        self.call_count = 0
        self.providers_used: List[str] = []

        # Required interfaces
        self.registry = self
        self.context = Mock()
        self.context.is_explored.return_value = context_explored
        self.context.get_summary.return_value = "" if not context_explored else "Test codebase summary"
        self.context.project_path = Path("/test/project")
        self.context.file_index = {
            "dummy": ["src/dummy.py"]  # Dummy file_index for classification tests
        }
        self.context.ensure_file_index.return_value = self.context.file_index
        self.context.ensure_file_index_with_timeout.return_value = self.context.file_index

        # Additional attributes for CLI handlers
        self.brain = recommended_provider
        self.context_aware = True
        self.caching_enabled = True
        self.providers = self  # self implements list_available
        self.session_manager = Mock()
        self.session_manager.get_session_info.return_value = {'exists': False}

        # Storage for discoveries
        self._discoveries = []
        self.working_memory = MockWorkingMemory()
        # Keep _working_memory as reference for backwards compatibility in tests
        self._working_memory = self.working_memory._data

    def list_available(self) -> List[str]:
        """Return available providers."""
        return self.available_providers

    def list_providers(self) -> List[str]:
        """Return available providers (Protocol method)."""
        return self.available_providers

    def is_rate_limited(self, provider: str) -> bool:
        """Check if provider is rate limited."""
        return provider in self.rate_limited_providers

    def get_recommended_provider(self, task_type: str = 'general') -> str:
        """
        Get recommended provider based on configuration.

        If rotation is configured, returns next in rotation.
        Otherwise returns recommended_provider, skipping rate-limited ones.
        """
        if self.rotation:
            # Rotate through providers
            provider = self.rotation[self.call_count % len(self.rotation)]
            return provider

        # Skip rate-limited providers
        if self._recommended_provider in self.rate_limited_providers:
            for prov in self.available_providers:
                if prov not in self.rate_limited_providers:
                    return prov

        return self._recommended_provider

    def delegate(
        self,
        provider_name: Optional[str] = None,
        prompt: str = "",
        **kwargs
    ) -> LLMResponse:
        """
        Delegate to mock provider with tracking.

        If provider_name is None, auto-selects based on task_type.
        """
        # Auto-select if not specified
        if provider_name is None:
            task_type = kwargs.get('task_type', 'general')
            provider_name = self.get_recommended_provider(task_type)

        # Check rate limits
        if self.is_rate_limited(provider_name):
            raise Exception(f"{provider_name} is rate limited")

        # Track the call
        self.delegate_calls.append({
            'provider': provider_name,
            'prompt': prompt,
            'task_type': kwargs.get('task_type'),
            'kwargs': kwargs
        })
        self.providers_used.append(provider_name)
        self.call_count += 1

        # Return configured response
        return make_response(
            content=self.response_content,
            provider=provider_name,
            tokens_used=self.response_tokens
        )

    async def delegate_async(
        self,
        provider_name: str,
        prompt: str = "",
        **kwargs
    ) -> LLMResponse:
        """
        Async delegate - wraps sync delegate for Protocol compliance.
        """
        return self.delegate(provider_name=provider_name, prompt=prompt, **kwargs)

    def add_discovery(self, content: str, source: str = "") -> None:
        """Add a discovery to working memory."""
        self._discoveries.append({'content': content, 'source': source})
        self.working_memory.add_discovery(content, source)

    def explore_project(self, force: bool = False) -> dict:
        """Explore the project."""
        return {'status': 'cached' if not force else 'explored', 'total_files': 10}

    def get_working_memory_summary(self) -> dict:
        """Get summary of working memory (deprecated, use working_memory.get_summary())."""
        return self.working_memory.get_summary()

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            'exact_cache_entries': 10,
            'intent_cache_entries': 5,
            'exact_hits': 20,
            'intent_hits': 10,
            'exact_misses': 30,
            'saves': 15,
            'exact_hit_rate': '40.0%',
            'intent_hit_rate': '25.0%',
            'cache_file': '/test/.cache'
        }

    def toggle_cache(self) -> bool:
        """Toggle caching on/off."""
        self.caching_enabled = not self.caching_enabled
        return self.caching_enabled

    def clear_cache(self) -> None:
        """Clear the response cache."""
        pass

    def status(self) -> dict:
        """Get orchestrator status."""
        return {
            'brain': self.brain,
            'orchestrator_brain': self.brain,
            'available_providers': self.available_providers,
            'tasks_executed': self.call_count
        }

    def get_usage_report(self) -> dict:
        """Get usage report."""
        return {
            'total_tasks': self.call_count,
            'session_duration': '0:00:00',
            'cached_hits': 0,
            'api_calls': self.call_count,
            'by_provider': {
                provider: {
                    'count': self.providers_used.count(provider),
                    'total_tokens': 100 * self.providers_used.count(provider),
                    'avg_tokens': 100,
                    'total_latency_ms': 50 * self.providers_used.count(provider),
                    'cached_hits': 0
                }
                for provider in set(self.providers_used)
            },
            'cache_stats': {
                'exact_hit_rate': '0%',
                'intent_hit_rate': '0%',
                'exact_cache_entries': 0,
                'intent_cache_entries': 0
            }
        }

    def save_session(self, conversation_history: list = None) -> str:
        """Save the current session."""
        return '/test/session.json'

    def load_session(self) -> dict:
        """Load a saved session."""
        return {
            'status': 'loaded',
            'saved_at': '2024-01-01',
            'files_restored': 5,
            'searches_restored': 3,
            'git_ops_restored': 2,
            'discoveries_restored': 1,
            'conversation_history': []
        }


class MockIO:
    """
    Mock I/O implementation for testing CLI code.

    Captures all output and provides preset inputs for deterministic testing.
    This is equivalent to TestIO in src/cli/io_interface.py but located
    in the test helpers for convenience.

    Usage:
        io = MockIO(
            inputs=["user response", "another input"],
            confirmations=[True, False]
        )

        # Run code that uses io
        my_cli_function(io)

        # Verify output
        assert "expected text" in io.get_output()
        assert io.get_styled_outputs()[0]['fg'] == 'green'
    """

    def __init__(
        self,
        inputs: Optional[List[str]] = None,
        confirmations: Optional[List[bool]] = None
    ):
        """
        Initialize MockIO with preset inputs and confirmations.

        Args:
            inputs: List of input strings to return from prompt/input_line
            confirmations: List of boolean values to return from confirm
        """
        self._inputs: List[str] = list(inputs) if inputs else []
        self._confirmations: List[bool] = list(confirmations) if confirmations else []
        self._output_buffer: List[str] = []
        self._styled_outputs: List[Dict[str, Any]] = []
        self._input_index = 0
        self._confirm_index = 0

        # Add theme mock for color theming support (match ScrappyTheme defaults)
        self.theme = Mock()
        self.theme.primary = "#00ffff"
        self.theme.success = "#00ff00"
        self.theme.warning = "#ffff00"
        self.theme.error = "#ff0000"
        self.theme.info = "#0000ff"
        self.theme.accent = "#ff9900"

        # Enable color by default
        self.use_color = True

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Capture output to internal buffer."""
        if nl:
            self._output_buffer.append(message + "\n")
        else:
            self._output_buffer.append(message)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Capture styled output and record styling info."""
        self._styled_outputs.append({
            'text': message,
            'fg': fg,
            'bold': bold,
            'nl': nl
        })

        if nl:
            self._output_buffer.append(message + "\n")
        else:
            self._output_buffer.append(message)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return text unchanged (no actual styling in tests) or with ANSI codes if use_color=True."""
        if not self.use_color:
            return text
        # Add ANSI codes when color is enabled to simulate styled output
        if fg or bold:
            return f"\x1b[1m{text}\x1b[0m" if bold else f"\x1b[32m{text}\x1b[0m"
        return text

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Return preset input or default."""
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return default

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Return preset confirmation or default."""
        # Capture the prompt text to output buffer for verification
        self._output_buffer.append(text)
        if self._confirm_index < len(self._confirmations):
            result = self._confirmations[self._confirm_index]
            self._confirm_index += 1
            return result
        return default

    def input_line(self) -> str:
        """Return preset input or empty string."""
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return ""

    def progress(self, total: int, description: str = "Progress"):
        """Return a mock progress context manager.

        Returns a context manager that provides a mock progress tracker
        compatible with UnifiedIO.progress().

        Args:
            total: Total number of steps
            description: Description text for the progress bar

        Returns:
            Context manager that yields a mock progress tracker
        """
        from contextlib import contextmanager

        @contextmanager
        def _progress_context():
            # Create a simple mock progress tracker
            class MockProgressTracker:
                def __init__(self):
                    self.current = 0

                def advance(self, amount: int = 1):
                    self.current += amount

                def update_description(self, description: str):
                    pass

            yield MockProgressTracker()

        return _progress_context()

    def get_output(self) -> str:
        """Get all captured output as a single string."""
        return "".join(self._output_buffer)

    def get_output_lines(self) -> List[str]:
        """Get captured output as list of lines."""
        full_output = self.get_output()
        return full_output.split("\n") if full_output else []

    def get_styled_outputs(self) -> List[Dict[str, Any]]:
        """Get list of all styled output records.

        Returns:
            List of dicts with 'text', 'fg', 'bold', 'nl' keys
        """
        return self._styled_outputs

    def clear_output(self) -> None:
        """Clear all captured output."""
        self._output_buffer = []
        self._styled_outputs = []

    def add_input(self, value: str) -> None:
        """Add an input value to the queue."""
        self._inputs.append(value)

    def add_confirmation(self, value: bool) -> None:
        """Add a confirmation value to the queue."""
        self._confirmations.append(value)

    def confirmations_used(self) -> int:
        """Get the number of confirmations that have been used.

        Returns:
            Number of confirm() calls made
        """
        return self._confirm_index

    def reset(self) -> None:
        """Reset all state for reuse between tests."""
        self._output_buffer = []
        self._styled_outputs = []
        self._input_index = 0
        self._confirm_index = 0

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Capture table output as formatted text."""
        if title:
            self._output_buffer.append(title + "\n")
        # Format as simple table
        self._output_buffer.append(" | ".join(headers) + "\n")
        self._output_buffer.append("-" * 40 + "\n")
        for row in rows:
            self._output_buffer.append(" | ".join(str(cell) for cell in row) + "\n")

    def supports_color(self) -> bool:
        """Return True for mock (allows color-based formatting in tests)."""
        return True


# =============================================================================
# Factory Functions for Common Test Setups
# =============================================================================

def make_handler_test_setup(
    inputs: Optional[List[str]] = None,
    confirmations: Optional[List[bool]] = None,
    providers: Optional[List[str]] = None,
    brain: str = 'cerebras',
    context_explored: bool = False,
    response_content: str = '{"thought": "test", "action": "complete", "is_complete": true, "result": "done"}'
) -> tuple:
    """
    Create a common test setup with MockIO and ConfigurableTestOrchestrator.

    Factory function to reduce boilerplate in CLI handler tests.

    Args:
        inputs: List of input strings for MockIO
        confirmations: List of boolean confirmations for MockIO
        providers: List of available providers for orchestrator
        brain: Default brain/provider for orchestrator
        context_explored: Whether context should report as explored
        response_content: JSON content for delegate responses

    Returns:
        Tuple of (MockIO, ConfigurableTestOrchestrator)

    Usage:
        io, orch = make_handler_test_setup(
            inputs=["user input"],
            confirmations=[True, False],
            brain='anthropic'
        )

        handler = MyHandler(orch)
        handler.do_something(io=io)

        assert "expected" in io.get_output()
    """
    io = MockIO(inputs=inputs, confirmations=confirmations)

    orch = ConfigurableTestOrchestrator(
        available_providers=providers or ['cerebras', 'groq', 'gemini'],
        recommended_provider=brain,
        context_explored=context_explored,
        response_content=response_content
    )
    orch.brain = brain

    return io, orch


def make_cli_test_context(
    inputs: Optional[List[str]] = None,
    confirmations: Optional[List[bool]] = None,
    context_explored: bool = False,
    providers: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a full CLI test context with all commonly needed components.

    Returns a dictionary with io, orchestrator, and context for comprehensive tests.

    Args:
        inputs: List of input strings for MockIO
        confirmations: List of boolean confirmations for MockIO
        context_explored: Whether context should report as explored
        providers: List of available providers

    Returns:
        Dictionary with 'io', 'orchestrator', 'context' keys

    Usage:
        ctx = make_cli_test_context(context_explored=True)

        handler = MyHandler(ctx['orchestrator'])
        handler.process(io=ctx['io'])

        assert ctx['orchestrator'].context.is_explored()
    """
    io, orch = make_handler_test_setup(
        inputs=inputs,
        confirmations=confirmations,
        providers=providers,
        context_explored=context_explored
    )

    return {
        'io': io,
        'orchestrator': orch,
        'context': orch.context,
        'session_context': SessionContext()
    }


def make_mock_agent_result(
    success: bool = True,
    result: str = "Task completed",
    iterations: int = 1,
    audit_log: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Create a mock agent run result dictionary.

    Factory function to create properly structured agent results for testing.

    Args:
        success: Whether the agent completed successfully
        result: Result message
        iterations: Number of iterations the agent ran
        audit_log: List of audit log entries

    Returns:
        Dictionary matching agent run result structure

    Usage:
        result = make_mock_agent_result(success=True, iterations=3)

        mock_agent.run.return_value = result
    """
    return {
        'success': success,
        'result': result,
        'iterations': iterations,
        'audit_log': audit_log or []
    }


def make_delegate_response(
    content: str = '{"thought": "test", "action": "complete", "is_complete": true}',
    provider: str = "mock",
    model: str = "",
    tokens_used: int = 100
) -> LLMResponse:
    """
    Create an LLMResponse for testing delegate calls.

    Convenience wrapper around make_response with better defaults for delegate testing.

    Args:
        content: Response content
        provider: Provider name
        model: Model name
        tokens_used: Token count

    Returns:
        LLMResponse instance
    """
    return make_response(
        content=content,
        provider=provider,
        model=model,
        tokens_used=tokens_used
    )


def make_completion_response(
    result: str = "Task completed",
    provider: str = "mock",
    tokens_used: int = 100
) -> LLMResponse:
    """
    Create an LLMResponse with agent completion JSON.

    Creates a response that signals the agent has completed its task.

    Args:
        result: The result message to include
        provider: Provider name
        tokens_used: Token count

    Returns:
        LLMResponse with completion JSON content
    """
    import json
    content = json.dumps({
        "thought": "Task completed successfully",
        "action": "complete",
        "is_complete": True,
        "result": result
    })

    return make_response(
        content=content,
        provider=provider,
        tokens_used=tokens_used
    )


# =============================================================================
# Behavior Verification Helpers
# =============================================================================

def assert_output_contains(io: MockIO, text: str, msg: str = "") -> None:
    """
    Assert that MockIO output contains the specified text.

    Args:
        io: MockIO instance to check
        text: Text to search for
        msg: Optional custom message on failure

    Raises:
        AssertionError: If text is not found in output
    """
    output = io.get_output()
    if text not in output:
        default_msg = f"Text '{text}' not found in output.\nOutput was:\n{output}"
        raise AssertionError(msg or default_msg)


def assert_output_not_contains(io: MockIO, text: str, msg: str = "") -> None:
    """
    Assert that MockIO output does not contain the specified text.

    Args:
        io: MockIO instance to check
        text: Text that should not be present
        msg: Optional custom message on failure

    Raises:
        AssertionError: If text is found in output
    """
    output = io.get_output()
    if text in output:
        default_msg = f"Text '{text}' was found in output but should not be present.\nOutput was:\n{output}"
        raise AssertionError(msg or default_msg)


def assert_styled_with(
    io: MockIO,
    text: str,
    fg: Optional[str] = None,
    bold: Optional[bool] = None,
    msg: str = ""
) -> None:
    """
    Assert that styled output contains text with specified styling.

    Args:
        io: MockIO instance to check
        text: Text to search for (can be substring)
        fg: Expected foreground color (None to skip check)
        bold: Expected bold state (None to skip check)
        msg: Optional custom message on failure

    Raises:
        AssertionError: If no matching styled output is found
    """
    styled_outputs = io.get_styled_outputs()

    for styled in styled_outputs:
        if text in styled['text']:
            # Found the text, now check styling
            if fg is not None and styled.get('fg') != fg:
                default_msg = f"Text '{text}' found but has fg='{styled.get('fg')}' instead of '{fg}'"
                raise AssertionError(msg or default_msg)

            if bold is not None and styled.get('bold') != bold:
                default_msg = f"Text '{text}' found but has bold={styled.get('bold')} instead of {bold}"
                raise AssertionError(msg or default_msg)

            # All checks passed
            return

    # Text not found in any styled output
    texts = [s['text'] for s in styled_outputs]
    default_msg = f"Text '{text}' not found in styled outputs.\nStyled texts: {texts}"
    raise AssertionError(msg or default_msg)


def get_styled_by_color(io: MockIO, color: str) -> List[Dict[str, Any]]:
    """
    Get all styled outputs with a specific color.

    Args:
        io: MockIO instance
        color: Color to filter by (e.g., 'red', 'green', 'yellow')

    Returns:
        List of styled output dictionaries with the specified color
    """
    return [s for s in io.get_styled_outputs() if s.get('fg') == color]


def assert_has_error_output(io: MockIO, msg: str = "") -> None:
    """
    Assert that MockIO has error-styled output (red color).

    Args:
        io: MockIO instance to check
        msg: Optional custom message on failure

    Raises:
        AssertionError: If no red-colored output is found
    """
    red_outputs = get_styled_by_color(io, 'red')
    if not red_outputs:
        default_msg = "No error output (red) found in styled outputs"
        raise AssertionError(msg or default_msg)


def assert_has_success_output(io: MockIO, msg: str = "") -> None:
    """
    Assert that MockIO has success-styled output (green color).

    Args:
        io: MockIO instance to check
        msg: Optional custom message on failure

    Raises:
        AssertionError: If no green-colored output is found
    """
    green_outputs = get_styled_by_color(io, 'green')
    if not green_outputs:
        default_msg = "No success output (green) found in styled outputs"
        raise AssertionError(msg or default_msg)


def assert_has_warning_output(io: MockIO, msg: str = "") -> None:
    """
    Assert that MockIO has warning-styled output (yellow color).

    Args:
        io: MockIO instance to check
        msg: Optional custom message on failure

    Raises:
        AssertionError: If no yellow-colored output is found
    """
    yellow_outputs = get_styled_by_color(io, 'yellow')
    if not yellow_outputs:
        default_msg = "No warning output (yellow) found in styled outputs"
        raise AssertionError(msg or default_msg)


def assert_provider_used(
    orch: ConfigurableTestOrchestrator,
    provider: str,
    count: Optional[int] = None,
    msg: str = ""
) -> None:
    """
    Assert that a specific provider was used in delegate calls.

    Args:
        orch: ConfigurableTestOrchestrator instance
        provider: Provider name to check for
        count: Expected number of times used (None for at least once)
        msg: Optional custom message on failure

    Raises:
        AssertionError: If provider was not used (or count doesn't match)
    """
    provider_count = orch.providers_used.count(provider)

    if count is not None:
        if provider_count != count:
            default_msg = f"Provider '{provider}' was used {provider_count} times, expected {count}"
            raise AssertionError(msg or default_msg)
    elif provider_count == 0:
        default_msg = f"Provider '{provider}' was not used. Providers used: {orch.providers_used}"
        raise AssertionError(msg or default_msg)


def assert_delegate_called_with(
    orch: ConfigurableTestOrchestrator,
    prompt_contains: Optional[str] = None,
    provider: Optional[str] = None,
    msg: str = ""
) -> None:
    """
    Assert that delegate was called with specific parameters.

    Args:
        orch: ConfigurableTestOrchestrator instance
        prompt_contains: Text that should be in the prompt
        provider: Provider that should have been used
        msg: Optional custom message on failure

    Raises:
        AssertionError: If no matching call is found
    """
    for call in orch.delegate_calls:
        matches = True

        if prompt_contains is not None:
            if prompt_contains not in call.get('prompt', ''):
                matches = False

        if provider is not None:
            if call.get('provider') != provider:
                matches = False

        if matches:
            return

    # No match found
    call_summaries = [
        {'provider': c.get('provider'), 'prompt_preview': c.get('prompt', '')[:50]}
        for c in orch.delegate_calls
    ]
    default_msg = f"No delegate call matched criteria. Calls: {call_summaries}"
    raise AssertionError(msg or default_msg)


# =============================================================================
# Intent Classification Test Helpers
# =============================================================================

from scrappy.task_router.protocols import (
    IntentClassifierProtocol,
    EntityExtractorProtocol,
    ActionResolverProtocol,
    IntentResult,
    QueryIntent,
    Action,
)


class StubIntentClassifier(IntentClassifierProtocol):
    """
    Test double for intent classifier that returns predetermined intent.

    Use this when you want to control the classification result in tests
    without testing the actual classification logic.

    Example:
        classifier = StubIntentClassifier(QueryIntent.FILE_STRUCTURE, confidence=0.9)
        result = classifier.classify("any query")
        assert result.intent == QueryIntent.FILE_STRUCTURE
        assert result.confidence == 0.9
    """

    def __init__(
        self,
        intent: QueryIntent = QueryIntent.GENERAL,
        confidence: float = 0.9,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize stub with predetermined values.

        Args:
            intent: Intent to return
            confidence: Confidence score to return
            metadata: Metadata to include in result
        """
        self._intent = intent
        self._confidence = confidence
        self._metadata = metadata if metadata is not None else {"test": True}

    def classify(self, query: str) -> IntentResult:
        """Return predetermined intent result."""
        return IntentResult(
            intent=self._intent,
            confidence=self._confidence,
            metadata=self._metadata
        )


class StubEntityExtractor(EntityExtractorProtocol):
    """
    Test double for entity extractor that returns predetermined entities.

    Use this when you want to control the extracted entities in tests
    without testing the actual extraction logic.

    Example:
        extractor = StubEntityExtractor({'file_path': ['test.py']})
        entities = extractor.extract("any query")
        assert entities == {'file_path': ['test.py']}
    """

    def __init__(self, entities: Optional[Dict[str, List[str]]] = None):
        """
        Initialize stub with predetermined entities.

        Args:
            entities: Entities to return
        """
        self._entities = entities if entities is not None else {}

    def extract(self, query: str) -> Dict[str, List[str]]:
        """Return predetermined entities."""
        return self._entities


class StubActionResolver(ActionResolverProtocol):
    """
    Test double for action resolver that returns predetermined action.

    Use this when you want to control the resolved action in tests
    without testing the actual resolution logic.

    Example:
        resolver = StubActionResolver(Action('TestTool', 'test_func', {}))
        action = resolver.resolve(intent_result, entities)
        assert action.tool == 'TestTool'
    """

    def __init__(self, action: Optional[Action] = None):
        """
        Initialize stub with predetermined action.

        Args:
            action: Action to return (defaults to generic action)
        """
        self._action = action if action is not None else Action(
            tool='TestTool',
            func='test_func',
            args={}
        )

    def resolve(self, result: IntentResult, entities: Dict[str, List[str]]) -> Action:
        """Return predetermined action."""
        return self._action


class RecordingIntentClassifier(IntentClassifierProtocol):
    """
    Test double that records all classification calls.

    Use this when you need to verify that classification was called
    with specific queries.

    Example:
        classifier = RecordingIntentClassifier(QueryIntent.FILE_STRUCTURE)
        classifier.classify("query 1")
        classifier.classify("query 2")
        assert len(classifier.calls) == 2
        assert classifier.calls[0] == "query 1"
    """

    def __init__(
        self,
        intent: QueryIntent = QueryIntent.GENERAL,
        confidence: float = 0.9,
    ):
        """
        Initialize recording classifier.

        Args:
            intent: Intent to return
            confidence: Confidence to return
        """
        self._intent = intent
        self._confidence = confidence
        self.calls: List[str] = []

    def classify(self, query: str) -> IntentResult:
        """Record the call and return predetermined result."""
        self.calls.append(query)
        return IntentResult(
            intent=self._intent,
            confidence=self._confidence,
            metadata={'recorded': True}
        )


# =============================================================================
# File System Test Helpers
# =============================================================================


# =============================================================================
# Rate Limiting Test Doubles
# =============================================================================

class FakeFileSystem:
    """Test double for file system operations."""

    def __init__(self):
        self._files: Dict[Path, str] = {}
        self._dirs: set[Path] = set()

    def exists(self, path: Path) -> bool:
        return path in self._files or path in self._dirs

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        if path not in self._files:
            raise FileNotFoundError(f"No such file: {path}")
        return self._files[path]

    def write_text(self, path: Path, content: str, encoding: str = "utf-8") -> None:
        self._files[path] = content

    def mkdir(self, path: Path, parents: bool = False, exist_ok: bool = False) -> None:
        if path in self._dirs and not exist_ok:
            raise FileExistsError(f"Directory exists: {path}")
        self._dirs.add(path)
        if parents:
            current = path.parent
            while current and current != current.parent:
                self._dirs.add(current)
                current = current.parent

    def unlink(self, path: Path) -> None:
        if path in self._files:
            del self._files[path]


class FakeStorage:
    """Test double for storage."""

    def __init__(self):
        self._data: Optional[dict[str, Any]] = None
        self.load_count = 0
        self.save_count = 0

    def load(self) -> dict[str, Any]:
        self.load_count += 1
        return self._data.copy() if self._data else {}

    def save(self, data: dict[str, Any]) -> None:
        self.save_count += 1
        self._data = data.copy()

    async def load_async(self) -> dict[str, Any]:
        return self.load()

    async def save_async(self, data: dict[str, Any]) -> None:
        return self.save(data)


class FakePolicy:
    """Test double for reset policy."""

    def __init__(self, reset_flags: Optional[Dict[str, bool]] = None):
        self.reset_flags = reset_flags or {"daily": False, "monthly": False}
        self.reset_calls: List[Dict[str, bool]] = []

    def reset_needed(self, last_reset_info: Dict[str, str]) -> Dict[str, bool]:
        return self.reset_flags

    def apply_reset(self, usage: dict[str, Any], which: Dict[str, bool]) -> None:
        self.reset_calls.append(which)


class FakeCalculator:
    """Test double for calculator."""

    def __init__(self):
        self.remaining_calls = []
        self.warnings_calls = []
        self.summarise_calls = []

    def remaining(self, usage: dict[str, Any], limits: Any) -> Dict[str, Any]:
        self.remaining_calls.append((usage, limits))
        return {
            "requests_remaining_today": 100,
            "requests_remaining_month": 1000,
            "tokens_remaining_today": 10000,
            "tokens_remaining_minute": 1000,
            "usage_today": 0,
            "tokens_today": 0,
            "usage_this_month": 0,
        }

    def warnings(
        self,
        remaining: Dict[str, Any],
        limits: Any,
        threshold: float = 0.1,
    ) -> Dict[str, Any]:
        self.warnings_calls.append((remaining, limits, threshold))
        return {
            "approaching_daily_request_limit": False,
            "approaching_monthly_request_limit": False,
            "approaching_daily_token_limit": False,
            "message": None,
        }

    def summarise(self, usage: dict[str, Any]) -> Dict[str, Any]:
        self.summarise_calls.append(usage)
        return {"last_reset": {}, "providers": {}}


class FakeRecommender:
    """Test double for recommender."""

    def __init__(self, provider_to_recommend: Optional[str] = "openai"):
        self.provider = provider_to_recommend
        self.calls = []

    def recommended(
        self,
        task_type: str,
        registry: Any,
        task_preferences: dict[str, list[str]],
    ) -> Optional[str]:
        self.calls.append((task_type, registry, task_preferences))
        return self.provider


def create_test_rate_limit_tracker(
    auto_load: bool = False,
    reset_flags: Optional[Dict[str, bool]] = None,
    recommended_provider: Optional[str] = "openai"
):
    """
    Create a RateLimitTracker configured for testing.

    Factory function that creates a tracker with test doubles,
    isolating tests from file system and real persistence.

    Args:
        auto_load: Whether to auto-load from storage on init
        reset_flags: Reset flags for policy (default: no resets needed)
        recommended_provider: Provider to recommend (default: "openai")

    Returns:
        Configured RateLimitTracker using test doubles

    Usage:
        tracker = create_test_rate_limit_tracker()
        tracker.record_request('openai', 'gpt-4', 100, 50)
        assert tracker.get_remaining('openai', limits).usage_today == 1
    """
    from scrappy.orchestrator.rate_limiting import RateLimitTracker

    storage = FakeStorage()
    policy = FakePolicy(reset_flags=reset_flags)
    calculator = FakeCalculator()
    recommender = FakeRecommender(provider_to_recommend=recommended_provider)

    tracker = RateLimitTracker(
        storage=storage,
        policy=policy,
        calculator=calculator,
        recommender=recommender,
        auto_load=auto_load
    )

    return tracker


# =============================================================================
# Command Tool Protocol Test Doubles
# =============================================================================

from scrappy.agent_tools.protocols import (
    ExecutionResult,
    CommandSecurityProtocol,
    OutputParserProtocol,
    CommandAdvisorProtocol,
    PlatformSanitizerProtocol,
    SubprocessRunnerProtocol,
)


class MockCommandSecurity:
    """Test double for CommandSecurityProtocol."""

    def __init__(self, should_block: bool = False, error_message: str = ""):
        """
        Initialize mock command security.

        Args:
            should_block: If True, validate() will raise an exception
            error_message: Error message for blocked commands
        """
        self.should_block = should_block
        self.error_message = error_message or "Command blocked for security reasons"
        self.validate_called = False
        self.validated_commands: List[str] = []

    def validate(self, command: str) -> None:
        """Validate command safety (mock)."""
        self.validate_called = True
        self.validated_commands.append(command)
        if self.should_block:
            raise ValueError(self.error_message)


class MockOutputParser:
    """Test double for OutputParserProtocol."""

    def __init__(self, parsed_output: Optional[str] = None, detected_format: str = "text"):
        """
        Initialize mock output parser.

        Args:
            parsed_output: Output to return from parse() (if None, returns input)
            detected_format: Format to return from detect_format()
        """
        self.parsed_output = parsed_output
        self.detected_format = detected_format
        self.parse_called = False
        self.detect_format_called = False
        self.parsed_inputs: List[str] = []

    def parse(self, raw_output: str, max_length: int = 30000) -> str:
        """Parse and format raw command output (mock)."""
        self.parse_called = True
        self.parsed_inputs.append(raw_output)
        if self.parsed_output is not None:
            return self.parsed_output
        return raw_output[:max_length]

    def detect_format(self, output: str) -> str:
        """Detect output format (mock)."""
        self.detect_format_called = True
        return self.detected_format


class MockCommandAdvisor:
    """Test double for CommandAdvisorProtocol."""

    def __init__(
        self,
        advice: Optional[str] = None,
        enriched_output: Optional[str] = None
    ):
        """
        Initialize mock command advisor.

        Args:
            advice: Advice to return from analyze_command()
            enriched_output: Output to return from enrich_output() (if None, returns input)
        """
        self.advice = advice
        self.enriched_output = enriched_output
        self.analyze_called = False
        self.enrich_called = False
        self.analyzed_commands: List[str] = []

    def analyze_command(self, command: str) -> Optional[str]:
        """Analyze command and provide pre-execution advice (mock)."""
        self.analyze_called = True
        self.analyzed_commands.append(command)
        return self.advice

    def enrich_output(self, output: str, command: str) -> str:
        """Enrich output with contextual information (mock)."""
        self.enrich_called = True
        if self.enriched_output is not None:
            return self.enriched_output
        return output


class MockPlatformSanitizer:
    """Test double for PlatformSanitizerProtocol."""

    def __init__(
        self,
        sanitized_command: Optional[str] = None,
        normalized_path: Optional[str] = None
    ):
        """
        Initialize mock platform sanitizer.

        Args:
            sanitized_command: Command to return from sanitize() (if None, returns input)
            normalized_path: Path to return from normalize_path() (if None, returns input)
        """
        self.sanitized_command = sanitized_command
        self.normalized_path = normalized_path
        self.sanitize_called = False
        self.normalize_path_called = False
        self.sanitized_commands: List[str] = []

    def sanitize(self, command: str) -> str:
        """Apply platform-specific command fixes (mock)."""
        self.sanitize_called = True
        self.sanitized_commands.append(command)
        if self.sanitized_command is not None:
            return self.sanitized_command
        return command

    def normalize_path(self, path: str) -> str:
        """Normalize path for current platform (mock)."""
        self.normalize_path_called = True
        if self.normalized_path is not None:
            return self.normalized_path
        return path


class MockSubprocessRunner:
    """Test double for SubprocessRunnerProtocol."""

    def __init__(
        self,
        result: Optional[ExecutionResult] = None,
        should_timeout: bool = False
    ):
        """
        Initialize mock subprocess runner.

        Args:
            result: ExecutionResult to return (default: success result)
            should_timeout: If True, raises TimeoutError
        """
        self.result = result or ExecutionResult(
            stdout="test output",
            stderr="",
            exit_code=0,
            execution_time=0.1
        )
        self.should_timeout = should_timeout
        self.execute_called = False
        self.executed_commands: List[tuple[str, str]] = []

    def execute(
        self,
        command: str,
        cwd: str,
        timeout: Optional[float] = None,
        stream_output: bool = False,
    ) -> ExecutionResult:
        """Execute command in subprocess (mock)."""
        self.execute_called = True
        self.executed_commands.append((command, cwd))
        if self.should_timeout:
            raise TimeoutError(f"Command timed out after {timeout}s")
        return self.result


# =============================================================================
# Platform Test Doubles
# =============================================================================

class FakePlatformDetector:
    """Test double for PlatformDetectorProtocol."""

    def __init__(self, platform: str = "Linux", has_git_bash: bool = False):
        """
        Initialize fake platform detector.

        Args:
            platform: Platform name to report (Windows, macOS, Linux, etc.)
            has_git_bash: Whether to report Git Bash as available
        """
        self._platform = platform
        self._tools: Dict[str, bool] = {}
        self._has_git_bash = has_git_bash

    def is_windows(self) -> bool:
        """Check if platform is Windows."""
        return self._platform == "Windows"

    def is_unix(self) -> bool:
        """Check if platform is Unix-like."""
        return self._platform in ["Linux", "macOS", "FreeBSD", "OpenBSD", "NetBSD"]

    def is_macos(self) -> bool:
        """Check if platform is macOS."""
        return self._platform == "macOS"

    def get_platform_name(self) -> str:
        """Get platform name."""
        return self._platform

    def get_shell_info(self) -> Dict[str, Optional[str]]:
        """Get shell info."""
        if self._platform == "Windows":
            return {
                "default": "cmd.exe",
                "bash": None,
                "powershell": "powershell.exe",
                "cmd": "cmd.exe",
                "sh": None,
            }
        else:
            return {
                "default": "/bin/bash",
                "bash": "/bin/bash",
                "powershell": None,
                "cmd": None,
                "sh": "/bin/sh",
            }

    def has_git_bash(self) -> bool:
        """Check if Git Bash is available."""
        return self._has_git_bash

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is available.

        You can configure available tools using set_tool().
        """
        return self._tools.get(tool_name, False)

    def set_tool(self, tool_name: str, available: bool) -> None:
        """Configure tool availability for testing."""
        self._tools[tool_name] = available


class FakeCommandTranslator:
    """Test double for CommandTranslatorProtocol."""

    def __init__(self, translate_to: Optional[str] = None):
        """
        Initialize fake command translator.

        Args:
            translate_to: Command to translate to (if None, no translation)
        """
        self._translate_to = translate_to

    def translate_command(self, command: str) -> tuple[str, bool]:
        """Translate command."""
        if self._translate_to:
            return (self._translate_to, True)
        return (command, False)

    def normalize_command_paths(self, command: str) -> tuple[str, bool, str]:
        """Normalize command paths."""
        return (command, False, "")

    def normalize_npm_command_for_windows(self, command: str) -> tuple[str, bool, str]:
        """Normalize npm command."""
        return (command, False, "")

    def fix_spring_initializr_command(self, command: str) -> tuple[str, bool, str]:
        """Fix Spring Initializr command."""
        return (command, False, "")


class FakeCommandValidator:
    """Test double for CommandValidatorProtocol."""

    def __init__(self, always_valid: bool = True, warning: str = ""):
        """
        Initialize fake command validator.

        Args:
            always_valid: If True, all commands are valid
            warning: Warning message to return for invalid commands
        """
        self._always_valid = always_valid
        self._warning = warning

    def validate_command_for_platform(self, command: str) -> tuple[bool, str]:
        """Validate command."""
        if self._always_valid:
            return (True, "")
        return (False, self._warning or "Command blocked for testing")

    def get_dangerous_commands(self) -> List[str]:
        """Get dangerous commands."""
        return []

    def get_interactive_commands(self) -> List[str]:
        """Get interactive commands."""
        return []


class FakeCommandExecutor:
    """Test double for CommandExecutorProtocol."""

    def __init__(
        self,
        output: str = "",
        returncode: int = 0,
        method: str = "test"
    ):
        """
        Initialize fake command executor.

        Args:
            output: Output to return
            returncode: Return code to return
            method: Execution method to report
        """
        self._output = output
        self._returncode = returncode
        self._method = method
        self.commands_executed: List[str] = []

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30
    ):
        """Execute command (fake)."""
        from scrappy.platform.protocols.execution import ExecutionResult

        self.commands_executed.append(command)

        return ExecutionResult(
            output=self._output,
            returncode=self._returncode,
            method=self._method
        )


class FakePythonFallback:
    """Test double for PythonCommandFallbackProtocol."""

    def __init__(self, result: Optional[Dict[str, Any]] = None):
        """
        Initialize fake Python fallback.

        Args:
            result: Result dict to return for all commands
        """
        self._result = result or {'output': '', 'returncode': 0, 'used_fallback': True}

    def ls(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python ls command."""
        return self._result

    def cat(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python cat command."""
        return self._result

    def grep(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python grep command."""
        return self._result

    def find(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python find command."""
        return self._result

    def wc(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python wc command."""
        return self._result

    def head(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python head command."""
        return self._result

    def tail(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python tail command."""
        return self._result

    def touch(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python touch command."""
        return self._result

    def mkdir_p(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python mkdir -p command."""
        return self._result

    def rm(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python rm command."""
        return self._result

    def cp(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python cp command."""
        return self._result

    def mv(self, args: List[str], cwd) -> Dict[str, Any]:
        """Python mv command."""
        return self._result

    def which(self, args: List[str]) -> Dict[str, Any]:
        """Python which command."""
        return self._result

    def pwd(self, cwd) -> Dict[str, Any]:
        """Python pwd command."""
        return self._result


# =============================================================================
# Semantic Search Test Doubles
# =============================================================================

class MockSemanticSearch:
    """
    Test double for SemanticSearchProtocol.

    Provides a mock semantic search that doesn't load real models or databases.
    Use this to test code that depends on semantic search without the overhead
    of loading FastEmbed and LanceDB.

    Example:
        search = MockSemanticSearch()
        search.set_indexed(True)
        search.set_search_results([
            {'path': 'test.py', 'lines': (1, 10), 'content': 'def foo():', 'score': 0.9}
        ])

        result = search.search("find foo function")
        assert len(result['chunks']) == 1
    """

    def __init__(self):
        """Initialize mock semantic search."""
        self._indexed = False
        self._search_results: List[Dict[str, Any]] = []
        self._index_calls: List[Dict[str, str]] = []
        self._search_calls: List[str] = []

    def index_files(self, files: Dict[str, str]) -> None:
        """
        Mock index_files that records calls without actual indexing.

        Args:
            files: Dict mapping file paths to content
        """
        self._index_calls.append(files.copy())
        self._indexed = True

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        """
        Mock search that returns preset results.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget

        Returns:
            SearchResult dict with chunks and metadata
        """
        self._search_calls.append(query)
        return {
            'chunks': self._search_results[:max_results],
            'tokens_used': sum(len(r.get('content', '')) // 4 for r in self._search_results[:max_results]),
            'limit_hit': None
        }

    def is_indexed(self) -> bool:
        """Check if mock is indexed."""
        return self._indexed

    def clear_index(self) -> None:
        """Clear mock index."""
        self._indexed = False
        self._index_calls.clear()

    def set_indexed(self, indexed: bool) -> None:
        """Set indexed state for testing."""
        self._indexed = indexed

    def set_search_results(self, results: List[Dict[str, Any]]) -> None:
        """Set results to return from search()."""
        self._search_results = results

    def get_index_calls(self) -> List[Dict[str, str]]:
        """Get all index_files() calls for verification."""
        return self._index_calls

    def get_search_calls(self) -> List[str]:
        """Get all search() calls for verification."""
        return self._search_calls


class MockSemanticInitializer:
    """
    Test double for BackgroundInitializerProtocol.

    Simulates semantic search initialization without actual background threads.
    Use this to test code that depends on background initialization without
    the overhead and complexity of real threads.

    Example:
        initializer = MockSemanticInitializer()
        initializer.set_result(MockSemanticSearch())
        initializer.start()

        assert initializer.is_complete()
        search = initializer.get_result()
    """

    def __init__(
        self,
        auto_complete: bool = True,
        result: Optional[Any] = None,
        error: Optional[Exception] = None
    ):
        """
        Initialize mock initializer.

        Args:
            auto_complete: If True, is_complete() returns True immediately
            result: Result to return from get_result()
            error: Error to return from get_error()
        """
        self._auto_complete = auto_complete
        self._result = result
        self._error = error
        self._started = False
        self._complete = auto_complete
        self._status = "Complete" if auto_complete else "Not started"

    def start(self) -> None:
        """Mock start - marks as started."""
        self._started = True
        if self._auto_complete:
            self._complete = True
            self._status = "Complete"

    def is_complete(self) -> bool:
        """Check if complete."""
        return self._complete

    def is_running(self) -> bool:
        """Check if running."""
        return self._started and not self._complete

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Mock wait - returns complete status."""
        return self._complete and self._error is None

    def get_result(self) -> Optional[Any]:
        """Get mock result."""
        return self._result

    def get_error(self) -> Optional[Exception]:
        """Get mock error."""
        return self._error

    def get_status(self) -> str:
        """Get mock status."""
        return self._status

    def set_complete(self, complete: bool = True) -> None:
        """Set completion state for testing."""
        self._complete = complete
        self._status = "Complete" if complete else "Running"

    def set_result(self, result: Any) -> None:
        """Set result for testing."""
        self._result = result

    def set_error(self, error: Exception) -> None:
        """Set error for testing."""
        self._error = error
        self._status = f"Failed: {error}"

    def set_status(self, status: str) -> None:
        """Set status message for testing."""
        self._status = status


# =============================================================================
# Textual TUI Test Doubles
# =============================================================================

class MockTextualApp:
    """Mock Textual app for testing.

    Provides test doubles for Textual app components without requiring
    the full Textual framework or terminal environment.

    Usage:
        app = MockTextualApp()
        io = MockTextualIO(app)
        io.secho("Test message", fg="green")

        assert "Test message" in app.get_output()
    """

    def __init__(self):
        """Initialize mock Textual app."""
        self._output_updates: List[str] = []
        self._status_updates: List[str] = []
        self._widgets: Dict[str, Any] = {
            "#output": MockStaticWidget(),
            "#status": MockStaticWidget(),
        }
        self.exit_called = False

    def query_one(self, selector: str, widget_type=None):
        """Mock query_one to return mock widgets.

        Args:
            selector: Widget selector (e.g., "#output")
            widget_type: Widget type (ignored in mock)

        Returns:
            Mock widget matching the selector
        """
        if selector in self._widgets:
            return self._widgets[selector]
        raise LookupError(f"No widget found for selector: {selector}")

    def exit(self):
        """Mock app exit."""
        self.exit_called = True

    def get_output(self) -> str:
        """Get all output updates as a single string."""
        return "\n".join(self._output_updates)

    def get_status_updates(self) -> List[str]:
        """Get all status updates."""
        return self._status_updates.copy()


class MockStaticWidget:
    """Mock Textual Static widget for testing."""

    def __init__(self):
        """Initialize mock static widget."""
        self._content = ""
        self._updates: List[str] = []

    def update(self, content: str) -> None:
        """Mock update method.

        Args:
            content: New content for the widget
        """
        self._content = content
        self._updates.append(content)

    @property
    def renderable(self) -> str:
        """Get current renderable content."""
        return self._content

    def get_updates(self) -> List[str]:
        """Get all updates for verification."""
        return self._updates.copy()


class MockTextualIO:
    """Mock for Textual-based IO (UnifiedIO with OutputSink) for testing.

    Implements CLIIOProtocol for testing Textual-based CLI code
    without requiring a real Textual app or terminal.

    Usage:
        app = MockTextualApp()
        io = MockTextualIO(app)
        io.secho("Success!", fg="green")

        assert "Success!" in app.get_output()
        assert io.get_styled_outputs()[0]['fg'] == 'green'
    """

    def __init__(self, app: Optional[MockTextualApp] = None):
        """Initialize mock for Textual IO.

        Args:
            app: MockTextualApp instance (creates one if not provided)
        """
        self._app = app or MockTextualApp()
        self._output_buffer: List[str] = []
        self._styled_outputs: List[Dict[str, Any]] = []

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Capture output to internal buffer."""
        output = message + "\n" if nl else message
        self._output_buffer.append(output)

        # Also update app's output widget
        output_widget = self._app.query_one("#output")
        current = str(output_widget.renderable)
        new_content = f"{current}\n{message}" if current and nl else f"{current}{message}"
        output_widget.update(new_content)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Capture styled output and record styling info."""
        self._styled_outputs.append({
            'text': message,
            'fg': fg,
            'bold': bold,
            'nl': nl
        })

        # Add to buffer
        output = message + "\n" if nl else message
        self._output_buffer.append(output)

        # Update app's output widget with Rich markup
        output_widget = self._app.query_one("#output")
        current = str(output_widget.renderable)

        # Apply Rich markup
        if fg and bold:
            formatted = f"[bold {fg}]{message}[/bold {fg}]"
        elif fg:
            formatted = f"[{fg}]{message}[/{fg}]"
        elif bold:
            formatted = f"[bold]{message}[/bold]"
        else:
            formatted = message

        new_content = f"{current}\n{formatted}" if current and nl else f"{current}{formatted}"
        output_widget.update(new_content)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return text with Rich markup."""
        if fg and bold:
            return f"[bold {fg}]{text}[/bold {fg}]"
        elif fg:
            return f"[{fg}]{text}[/{fg}]"
        elif bold:
            return f"[bold]{text}[/bold]"
        else:
            return text

    def prompt(
        self,
        text: str,
        default: str = "",
        show_default: bool = True
    ) -> str:
        """Not supported in Textual mode."""
        raise NotImplementedError("prompt() not supported in Textual mode")

    def confirm(
        self,
        text: str,
        default: bool = False
    ) -> bool:
        """Not supported in Textual mode."""
        raise NotImplementedError("confirm() not supported in Textual mode")

    def input_line(self) -> str:
        """Not supported in Textual mode."""
        raise NotImplementedError("input_line() not supported in Textual mode")

    def get_output(self) -> str:
        """Get all captured output as a single string."""
        return "".join(self._output_buffer)

    def get_output_lines(self) -> List[str]:
        """Get captured output as list of lines."""
        full_output = self.get_output()
        return full_output.split("\n") if full_output else []

    def get_styled_outputs(self) -> List[Dict[str, Any]]:
        """Get list of all styled output records."""
        return self._styled_outputs

    def clear_output(self) -> None:
        """Clear all captured output."""
        self._output_buffer = []
        self._styled_outputs = []


class MockTextualProgressReporter:
    """Mock progress reporter for testing Textual apps.

    Implements ProgressReporterProtocol for testing without a real Textual app.

    Usage:
        reporter = MockTextualProgressReporter()
        reporter.start("Processing", total=10)
        reporter.update(5, "Half done")
        reporter.complete("Finished")

        assert reporter.get_status_updates()[0] == "Processing (0/10)"
        assert reporter.complete_called
    """

    def __init__(self, app: Optional[MockTextualApp] = None):
        """Initialize mock progress reporter.

        Args:
            app: MockTextualApp instance (creates one if not provided)
        """
        self._app = app or MockTextualApp()
        self._status_updates: List[str] = []
        self.start_called = False
        self.update_called = False
        self.complete_called = False
        self.error_called = False

    def start(self, description: str, total: Optional[int] = None) -> None:
        """Record start call."""
        self.start_called = True
        if total is not None:
            status = f"{description} (0/{total})"
        else:
            status = f"{description}..."
        self._status_updates.append(status)
        self._update_app_status(f"[cyan]{status}[/cyan]")

    def update(self, current: Optional[int] = None, description: Optional[str] = None) -> None:
        """Record update call."""
        self.update_called = True
        status = description or "Processing..."
        self._status_updates.append(status)
        self._update_app_status(f"[cyan]{status}[/cyan]")

    def complete(self, message: str = "Complete") -> None:
        """Record complete call."""
        self.complete_called = True
        self._status_updates.append(message)
        self._update_app_status(f"[green]{message}[/green]")

    def error(self, message: str) -> None:
        """Record error call."""
        self.error_called = True
        error_msg = f"Error: {message}"
        self._status_updates.append(error_msg)
        self._update_app_status(f"[red]{error_msg}[/red]")

    def _update_app_status(self, content: str) -> None:
        """Update the app's status widget."""
        try:
            status_widget = self._app.query_one("#status")
            status_widget.update(content)
        except LookupError:
            pass  # App doesn't have status widget

    def get_status_updates(self) -> List[str]:
        """Get all status updates for verification."""
        return self._status_updates.copy()


# =============================================================================
# Agent UI Test Doubles
# =============================================================================

class StubAgentUI:
    """
    Test double for AgentUIProtocol.

    Implements the minimum interface needed for testing denial handling.

    Example:
        ui = StubAgentUI(prompt_confirm_responses=[True, False])
        result1 = ui.prompt_confirm("Stop?")  # Returns True
        result2 = ui.prompt_confirm("Stop?")  # Returns False
    """

    def __init__(
        self,
        prompt_confirm_responses: Optional[List[bool]] = None,
    ):
        """
        Initialize stub with preset responses.

        Args:
            prompt_confirm_responses: List of booleans to return from prompt_confirm()
        """
        self._prompt_confirm_responses = list(prompt_confirm_responses) if prompt_confirm_responses else []
        self._prompt_confirm_index = 0
        self._shown_messages: List[str] = []

    def prompt_confirm(self, message: str = "Allow?", default: bool = False) -> bool:
        """Return preset confirmation or default."""
        self._shown_messages.append(message)
        if self._prompt_confirm_index < len(self._prompt_confirm_responses):
            result = self._prompt_confirm_responses[self._prompt_confirm_index]
            self._prompt_confirm_index += 1
            return result
        return default

    def show_thinking(self, text: str) -> None:
        """Record thinking message."""
        self._shown_messages.append(f"[thinking] {text}")

    def show_tool_request(self, tool_name: str, params: Dict[str, Any]) -> None:
        """Record tool request."""
        self._shown_messages.append(f"[tool] {tool_name}")

    def show_command(self, command: str) -> None:
        """Record command."""
        self._shown_messages.append(f"[command] {command}")

    def show_error(self, message: str) -> None:
        """Record error."""
        self._shown_messages.append(f"[error] {message}")

    def show_result(self, result: str, title: str = "Result", is_error: bool = False) -> None:
        """Record result."""
        self._shown_messages.append(f"[result] {result}")

    def show_warning(self, message: str) -> None:
        """Record warning."""
        self._shown_messages.append(f"[warning] {message}")

    def show_progress(self, message: str) -> None:
        """Record progress."""
        self._shown_messages.append(f"[progress] {message}")

    def show_provider_status(self, provider: str, message: str, color: str = "cyan") -> None:
        """Record provider status."""
        self._shown_messages.append(f"[provider:{provider}] {message}")

    def show_rule(self, title: Optional[str] = None) -> None:
        """Record rule."""
        self._shown_messages.append(f"[rule] {title or ''}")

    def get_shown_messages(self) -> List[str]:
        """Get all recorded messages for verification."""
        return self._shown_messages.copy()


class MockIO:
    """
    Mock IO implementation for testing CLI handlers.

    Captures all echo() and secho() calls for assertion in tests.
    Implements CLIIOProtocol without requiring Rich or Click.
    """

    def __init__(
        self,
        inputs: Optional[List[str]] = None,
        confirmations: Optional[List[bool]] = None
    ):
        """Initialize with empty message buffer."""
        self.messages: List[str] = []
        self.styled_messages: List[Dict[str, Any]] = []
        self._inputs: List[str] = list(inputs) if inputs else []
        self._confirmations: List[bool] = list(confirmations) if confirmations else []
        self._input_index = 0
        self._confirm_index = 0

        # Add theme mock for color theming support (match ScrappyTheme defaults)
        self.theme = Mock()
        self.theme.primary = "#00ffff"
        self.theme.success = "#00ff00"
        self.theme.warning = "#ffff00"
        self.theme.error = "#ff0000"
        self.theme.info = "#0000ff"
        self.theme.accent = "#ff9900"

        # Enable color by default
        self.use_color = True

    def echo(self, message: str = "", nl: bool = True) -> None:
        """Capture plain echo message."""
        self.messages.append(message)

    def secho(
        self,
        message: str,
        fg: Optional[str] = None,
        bg: Optional[str] = None,
        bold: bool = False,
        dim: bool = False,
        underline: bool = False,
        blink: bool = False,
        reverse: bool = False,
        reset: bool = True,
        nl: bool = True,
        err: bool = False
    ) -> None:
        """Capture styled echo message."""
        self.styled_messages.append({
            'message': message,
            'fg': fg,
            'bg': bg,
            'bold': bold,
            'dim': dim,
            'underline': underline,
            'blink': blink,
            'reverse': reverse,
            'reset': reset,
            'nl': nl,
            'err': err
        })
        self.messages.append(message)

    def confirm(self, prompt: str, default: bool = False) -> bool:
        """Mock confirm - returns preset confirmations or default."""
        if self._confirm_index < len(self._confirmations):
            result = self._confirmations[self._confirm_index]
            self._confirm_index += 1
            return result
        return default

    def prompt(self, text: str, default: str = "", show_default: bool = True) -> str:
        """Mock prompt - returns preset input or default."""
        if self._input_index < len(self._inputs):
            result = self._inputs[self._input_index]
            self._input_index += 1
            return result
        return default

    def clear(self) -> None:
        """Clear message buffers."""
        self.messages = []
        self.styled_messages = []

    def clear_output(self) -> None:
        """Clear all captured output (alias for clear)."""
        self.clear()

    def get_all_output(self) -> str:
        """Get all captured output as single string."""
        return "\n".join(self.messages)

    def get_output(self) -> str:
        """Get all captured output as single string (alias for get_all_output)."""
        return self.get_all_output()

    def reset(self) -> None:
        """Reset all state for reuse between tests."""
        self.clear()
        self._input_index = 0
        self._confirm_index = 0

    def style(self, text: str, fg: Optional[str] = None, bg: Optional[str] = None,
              bold: bool = False, dim: bool = False) -> str:
        """Mock style - returns text with ANSI codes if use_color=True."""
        if not self.use_color:
            return text
        # Add ANSI codes when color is enabled to simulate styled output
        if fg or bold or bg or dim:
            return f"\x1b[1m{text}\x1b[0m" if bold else f"\x1b[32m{text}\x1b[0m"
        return text

    def progress(self, total: int, description: str = "Progress"):
        """Return a mock progress context manager.

        Returns a context manager that provides a mock progress tracker
        compatible with UnifiedIO.progress().

        Args:
            total: Total number of steps
            description: Description text for the progress bar

        Returns:
            Context manager that yields a mock progress tracker
        """
        from contextlib import contextmanager

        @contextmanager
        def _progress_context():
            # Create a simple mock progress tracker
            class MockProgressTracker:
                def __init__(self):
                    self.current = 0

                def advance(self, amount: int = 1):
                    self.current += amount

                def update_description(self, description: str):
                    pass

            yield MockProgressTracker()

        return _progress_context()

    def get_styled_outputs(self) -> List[Dict[str, Any]]:
        """Get all styled messages with 'text' key for compatibility."""
        # Convert 'message' to 'text' for compatibility with tests
        return [{'text': s['message'], **{k: v for k, v in s.items() if k != 'message'}}
                for s in self.styled_messages]

    def get_output_lines(self) -> List[str]:
        """Get all captured output as list of lines."""
        return self.messages.copy()

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> None:
        """Capture table output as formatted text."""
        if title:
            self.messages.append(title)
        # Format as simple table
        self.messages.append(" | ".join(headers))
        self.messages.append("-" * 40)
        for row in rows:
            self.messages.append(" | ".join(str(cell) for cell in row))

    def supports_color(self) -> bool:
        """Return True for mock (allows color-based formatting in tests)."""
        return True
