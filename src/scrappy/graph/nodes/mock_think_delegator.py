"""
Mock think delegator for testing.

Provides a test double that returns scripted responses, enabling
unit tests for think.py without real LLM calls.
"""

from typing import Callable, Iterator, Optional

from scrappy.graph.protocols import ThinkResult
from scrappy.graph.run_context import AgentRunContextProtocol


class MockThinkDelegator:
    """
    Test double for ThinkDelegatorProtocol.

    Returns scripted responses in order, enabling deterministic testing
    of think node behavior without real LLM calls.

    Example:
        delegator = MockThinkDelegator([
            ThinkResult(content="I'll search for that.", tool_calls=[...]),
            ThinkResult(content="Found the answer: 42."),
        ])

        # First call returns tool call response
        result1 = delegator.complete(messages, tools, run_context, "instruct")
        assert result1.has_tool_calls

        # Second call returns final response
        result2 = delegator.complete(messages, tools, run_context, "instruct")
        assert result2.is_done
    """

    def __init__(
        self,
        responses: Optional[list[ThinkResult]] = None,
        default_response: Optional[ThinkResult] = None,
    ):
        """
        Initialize mock with scripted responses.

        Args:
            responses: List of ThinkResult to return in order.
                       Raises StopIteration if exhausted.
            default_response: Response to return after responses exhausted,
                            or if responses is None.
        """
        self._responses: Iterator[ThinkResult] = iter(responses or [])
        self._default = default_response or ThinkResult(
            content="Mock response",
            model_display="mock: test-model",
        )
        self._call_count = 0
        self._last_messages: Optional[list[dict]] = None
        self._last_tools: Optional[list[dict]] = None
        self._last_run_context: Optional[AgentRunContextProtocol] = None
        self._last_tier: Optional[str] = None

    @property
    def call_count(self) -> int:
        """Number of times complete/complete_streaming was called."""
        return self._call_count

    @property
    def last_messages(self) -> Optional[list[dict]]:
        """Messages from the last call."""
        return self._last_messages

    @property
    def last_tools(self) -> Optional[list[dict]]:
        """Tools from the last call."""
        return self._last_tools

    @property
    def last_run_context(self) -> Optional[AgentRunContextProtocol]:
        """Run context from the last call."""
        return self._last_run_context

    @property
    def last_tier(self) -> Optional[str]:
        """Tier from the last call."""
        return self._last_tier

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
    ) -> ThinkResult:
        """Return next scripted response."""
        self._record_call(messages, tools, run_context, current_tier)

        try:
            return next(self._responses)
        except StopIteration:
            return self._default

    async def complete_streaming(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ThinkResult:
        """Return next scripted response, simulating streaming via on_chunk."""
        self._record_call(messages, tools, run_context, current_tier)

        try:
            result = next(self._responses)
        except StopIteration:
            result = self._default

        # Simulate streaming by calling on_chunk with content
        if on_chunk and result.content:
            # Simulate chunked delivery
            words = result.content.split()
            for i, word in enumerate(words):
                chunk = word if i == len(words) - 1 else word + " "
                on_chunk(chunk)

        return result

    def _record_call(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        run_context: Optional[AgentRunContextProtocol],
        current_tier: str,
    ) -> None:
        """Record call details for assertions."""
        self._call_count += 1
        self._last_messages = messages
        self._last_tools = tools
        self._last_run_context = run_context
        self._last_tier = current_tier


class FailingThinkDelegator:
    """
    Test double that always raises an exception.

    Useful for testing error handling paths.
    """

    def __init__(self, error: Exception):
        """
        Initialize with exception to raise.

        Args:
            error: Exception to raise on every call
        """
        self._error = error
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Number of times complete was called before failing."""
        return self._call_count

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
    ) -> ThinkResult:
        """Raise configured exception."""
        self._call_count += 1
        raise self._error

    async def complete_streaming(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ThinkResult:
        """Raise configured exception."""
        self._call_count += 1
        raise self._error


class SequenceThinkDelegator:
    """
    Test double that returns different responses based on call patterns.

    More flexible than MockThinkDelegator for complex test scenarios.
    """

    def __init__(self):
        """Initialize with empty response map."""
        self._responses_by_content: dict[str, ThinkResult] = {}
        self._default = ThinkResult(content="Default response")
        self._call_history: list[dict] = []

    def when_messages_contain(self, text: str, response: ThinkResult) -> "SequenceThinkDelegator":
        """
        Configure response when messages contain specific text.

        Args:
            text: Text to match in message content
            response: ThinkResult to return when matched

        Returns:
            Self for method chaining
        """
        self._responses_by_content[text] = response
        return self

    def set_default(self, response: ThinkResult) -> "SequenceThinkDelegator":
        """Set default response when no patterns match."""
        self._default = response
        return self

    @property
    def call_history(self) -> list[dict]:
        """List of all calls made to this delegator."""
        return self._call_history

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
    ) -> ThinkResult:
        """Return response based on message content."""
        self._call_history.append({
            "messages": messages,
            "tools": tools,
            "tier": current_tier,
        })

        # Search for matching pattern
        all_content = " ".join(
            str(m.get("content", "")) for m in messages
        )

        for pattern, response in self._responses_by_content.items():
            if pattern in all_content:
                return response

        return self._default

    async def complete_streaming(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        run_context: Optional[AgentRunContextProtocol] = None,
        current_tier: str = "instruct",
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> ThinkResult:
        """Return response based on message content."""
        result = self.complete(messages, tools, run_context, current_tier)

        if on_chunk and result.content:
            on_chunk(result.content)

        return result
