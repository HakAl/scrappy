"""
Test helper classes and utilities.

Provides mock adapters and utilities for testing the orchestrator and agent.
"""

from typing import List, Optional, Dict, Any
from unittest.mock import Mock
from pathlib import Path

from src.providers.base import LLMResponse
from src.orchestrator_adapter import NullContext, ContextProvider


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

    def reset_tracking(self) -> None:
        """Reset call tracking (useful between test phases)."""
        self.delegate_calls = []
        self.call_count = 0
        self.providers_used = []

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

    def get_context_status(self) -> dict:
        """Get context status."""
        return {
            'project_path': self.context.project_path,
            'is_explored': self.context.is_explored(),
            'has_summary': bool(self.context.get_summary()),
            'explored_at': None,
            'total_files': 10,
            'cache_file': '/test/.cache',
            'cache_exists': False
        }

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

    def get_rate_limit_status(self) -> dict:
        """Get rate limit status."""
        return {
            'last_reset': {'daily': 'N/A', 'monthly': 'N/A'},
            'providers': {}
        }

    def check_rate_limit_warnings(self) -> list:
        """Check for rate limit warnings."""
        return []

    def reset_rate_tracking(self, provider: str = None) -> None:
        """Reset rate limit tracking."""
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

    def clear_session(self) -> None:
        """Clear the saved session."""
        pass

    def clear_working_memory(self) -> None:
        """Clear working memory (deprecated, use working_memory.clear())."""
        self.working_memory.clear()
        # Update reference
        self._working_memory = self.working_memory._data


class SimpleLLMAdapter:
    """
    Simple adapter for testing or single-provider scenarios.

    This adapter allows using the agent with just a single LLM function,
    without needing the full orchestrator infrastructure.
    """

    def __init__(
        self,
        llm_func,
        provider_name: str = "default",
        context_provider: Optional[ContextProvider] = None
    ):
        """
        Initialize with a simple LLM function.

        Args:
            llm_func: Function that takes (prompt, system_prompt, max_tokens, temperature)
                      and returns a string response
            provider_name: Name to identify this provider
            context_provider: Optional context provider
        """
        self._llm_func = llm_func
        self._provider_name = provider_name
        self._context = context_provider or NullContext()

    @property
    def context(self) -> ContextProvider:
        """Get the context provider."""
        return self._context

    def list_providers(self) -> List[str]:
        """Return single provider."""
        return [self._provider_name]

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponse:
        """Call the LLM function."""
        # Ignore provider name, use our single function
        content = self._llm_func(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

        return LLMResponse(
            content=content,
            model="",
            provider=self._provider_name
        )


class MockOrchestratorAdapter:
    """
    Mock adapter for testing purposes.

    Allows setting up predetermined responses for testing agent behavior.
    """

    def __init__(self, responses: Optional[List[str]] = None):
        """
        Initialize with optional list of responses.

        Args:
            responses: List of responses to return in order
        """
        self._responses = responses or []
        self._call_index = 0
        self._context = NullContext()
        self._calls = []  # Track all calls for assertions

    @property
    def context(self) -> ContextProvider:
        """Get the context provider."""
        return self._context

    def list_providers(self) -> List[str]:
        """Return mock provider."""
        return ["mock"]

    def add_response(self, response: str) -> None:
        """Add a response to the queue."""
        self._responses.append(response)

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> LLMResponse:
        """Return next mock response."""
        # Track the call
        self._calls.append({
            'provider': provider,
            'prompt': prompt,
            'system_prompt': system_prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'use_context': use_context
        })

        if self._call_index >= len(self._responses):
            # Default completion response if no more responses
            content = '{"thought": "No more responses", "action": "complete", "is_complete": true, "result": "Mock completed"}'
        else:
            content = self._responses[self._call_index]
            self._call_index += 1

        return LLMResponse(
            content=content,
            model="",
            provider="mock"
        )

    def get_calls(self) -> List[dict]:
        """Get all calls made to delegate()."""
        return self._calls

    def reset(self) -> None:
        """Reset the adapter state."""
        self._call_index = 0
        self._calls = []


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

    def styled_echo(
        self,
        message: str,
        fg: Optional[str] = None,
        bold: bool = False,
        nl: bool = True
    ) -> None:
        """Alias for secho() for backwards compatibility."""
        self.secho(message, fg=fg, bold=bold, nl=nl)

    def style(
        self,
        text: str,
        fg: Optional[str] = None,
        bold: bool = False
    ) -> str:
        """Return text unchanged (no actual styling in tests)."""
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
        compatible with RichIO.progress().

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


# =============================================================================
# Factory Functions for Common Test Setups
# =============================================================================

def make_injectable_orchestrator(
    tmp_path,
    cache: Optional[Any] = None,
    rate_tracker: Optional[Any] = None,
    working_memory: Optional[Any] = None,
    session_manager: Optional[Any] = None,
    provider_selector: Optional[Any] = None,
    auto_register: bool = False
):
    """
    Create a real AgentOrchestrator with injectable mock dependencies.

    This factory enables unit testing the orchestrator with full control
    over its dependencies while using the actual implementation.

    Args:
        tmp_path: Temporary directory path for the project
        cache: Mock cache or None for default
        rate_tracker: Mock rate tracker or None for default
        working_memory: Mock working memory or None for default
        session_manager: Mock session manager or None for default
        provider_selector: Mock provider selector or None for default
        auto_register: Whether to auto-register providers (default False for tests)

    Returns:
        AgentOrchestrator instance with injected dependencies

    Usage:
        def test_something(tmp_path):
            mock_cache = Mock(spec=ResponseCache)
            mock_cache.get.return_value = None

            orch = make_injectable_orchestrator(
                tmp_path,
                cache=mock_cache
            )

            # Test with real orchestrator but mocked cache
            orch.delegate(...)
            mock_cache.get.assert_called()
    """
    from src.orchestrator.core import AgentOrchestrator
    from src.orchestrator.output import NullOutput

    return AgentOrchestrator(
        auto_register=auto_register,
        project_path=str(tmp_path),
        cache=cache,
        rate_tracker=rate_tracker,
        working_memory=working_memory,
        session_manager=session_manager,
        provider_selector=provider_selector,
        output=NullOutput()
    )


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
        'context': orch.context
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
