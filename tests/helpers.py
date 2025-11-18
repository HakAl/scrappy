"""
Test helper classes and utilities.

Provides mock adapters and utilities for testing the orchestrator and agent.
"""

from typing import List, Optional, Dict, Any, Callable
from unittest.mock import Mock

from src.providers.base import LLMResponse
from src.orchestrator_adapter import NullContext, ContextProvider


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

    def list_available(self) -> List[str]:
        """Return available providers."""
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

    def reset_tracking(self) -> None:
        """Reset call tracking (useful between test phases)."""
        self.delegate_calls = []
        self.call_count = 0
        self.providers_used = []


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

    def reset(self) -> None:
        """Reset all state for reuse between tests."""
        self._output_buffer = []
        self._styled_outputs = []
        self._input_index = 0
        self._confirm_index = 0
