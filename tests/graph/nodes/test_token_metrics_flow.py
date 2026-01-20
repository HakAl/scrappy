"""
Tests for token metrics data flow.

TDD tests to verify token counts flow from LLM API response through to AgentState.

The data flow should be:
    LLM API -> StreamChunk (with usage) -> ThinkResult -> AgentState

Currently broken: estimates are used instead of actual API values.

Issue: scrappy-zz5z
"""

import pytest

from scrappy.graph.nodes.think_delegator import LiteLLMThinkDelegator
from scrappy.graph.protocols import ThinkResult
from scrappy.graph.state import AgentState
from scrappy.graph.nodes.think import _apply_think_result
from scrappy.orchestrator.types import StreamChunk


# =============================================================================
# Test Fixtures
# =============================================================================


class MockOrchestratorWithUsage:
    """Mock orchestrator that returns chunks with usage data in final chunk."""

    def __init__(
        self,
        chunks: list[StreamChunk],
        final_input_tokens: int = 0,
        final_output_tokens: int = 0,
    ):
        self._chunks = chunks
        self._final_input_tokens = final_input_tokens
        self._final_output_tokens = final_output_tokens
        self.call_count = 0

    def stream_completion_with_fallback(self, messages, model=None, selection_type=None, **kwargs):
        self.call_count += 1
        for chunk in self._chunks:
            yield chunk
        # Final chunk with usage data (like OpenAI stream_options=include_usage)
        # Token counts are passed via input_tokens/output_tokens fields
        yield StreamChunk(
            content="",
            model="test/model",
            provider="test",
            finish_reason="stop",
            input_tokens=self._final_input_tokens,
            output_tokens=self._final_output_tokens,
        )


def make_chunk(content="", model="", provider="", finish_reason=None):
    """Create a StreamChunk for testing."""
    return StreamChunk(
        content=content,
        model=model,
        provider=provider,
        finish_reason=finish_reason,
    )


def make_minimal_state() -> AgentState:
    """Create minimal AgentState for testing."""
    return AgentState(
        input="test input",
        original_task="test task",
        working_dir="/tmp",
        messages=[],
        iteration=0,
    )


# =============================================================================
# Core Data Flow Tests
# =============================================================================


class TestStreamChunkTokenFields:
    """Test that StreamChunk can carry token usage data."""

    def test_streamchunk_has_token_fields(self):
        """StreamChunk should have input_tokens and output_tokens fields.

        These fields carry actual token counts from the LLM API response,
        typically available in the final chunk when streaming with usage enabled.
        """
        # This test will fail until we add the fields to StreamChunk
        chunk = StreamChunk(
            content="test",
            input_tokens=100,
            output_tokens=50,
        )
        assert chunk.input_tokens == 100
        assert chunk.output_tokens == 50

    def test_streamchunk_token_fields_default_to_none(self):
        """Token fields should default to None when not provided."""
        chunk = StreamChunk(content="test")
        assert chunk.input_tokens is None
        assert chunk.output_tokens is None


class TestThinkResultTokenFields:
    """Test that ThinkResult can carry token usage data."""

    def test_thinkresult_has_token_fields(self):
        """ThinkResult should have input_tokens and output_tokens fields.

        These fields carry actual token counts from the LLM API,
        passed through from StreamChunk at the end of streaming.
        """
        # This test will fail until we add the fields to ThinkResult
        result = ThinkResult(
            content="test response",
            input_tokens=100,
            output_tokens=50,
        )
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_thinkresult_token_fields_default_to_none(self):
        """Token fields should default to None when not provided."""
        result = ThinkResult(content="test")
        assert result.input_tokens is None
        assert result.output_tokens is None


class TestThinkDelegatorPassesTokens:
    """Test that LiteLLMThinkDelegator passes token data from chunks to result."""

    def test_delegator_captures_tokens_from_final_chunk(self):
        """Delegator should capture token counts from final StreamChunk.

        When streaming completes, the final chunk may contain usage data.
        The delegator should extract this and include it in ThinkResult.
        """
        # Create chunks: content chunks + final chunk with usage
        chunks = [
            make_chunk(content="Hello ", model="test/model", provider="test"),
            make_chunk(content="world"),
        ]
        # Final chunk will have usage data (added by mock orchestrator)
        orchestrator = MockOrchestratorWithUsage(
            chunks=chunks,
            final_input_tokens=150,
            final_output_tokens=25,
        )

        delegator = LiteLLMThinkDelegator(orchestrator)
        result = delegator.complete(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            run_context=None,
            current_tier="instruct",
        )

        # Verify tokens were captured
        assert result.is_success
        assert result.content == "Hello world"
        # These assertions will fail until we implement token capture
        assert result.input_tokens == 150
        assert result.output_tokens == 25


class TestApplyThinkResultUsesActualTokens:
    """Test that _apply_think_result uses actual tokens when available."""

    def test_actual_tokens_override_estimates(self):
        """When ThinkResult has actual tokens, they should be used instead of estimates.

        The UI reads last_input_tokens and last_output_tokens from AgentState.
        These should be actual values from the API, not estimates.
        """
        state = make_minimal_state()

        # ThinkResult with actual token counts (from API)
        result = ThinkResult(
            content="The answer is 42.",
            model_display="test: model",
            input_tokens=500,  # Actual from API
            output_tokens=10,  # Actual from API
        )

        # Apply with estimates that differ from actual
        # (the function receives estimates but should use actual from result)
        new_state = _apply_think_result(
            state=state,
            result=result,
            user_message_exists=True,
            input_tokens=999,  # Estimate (should be ignored)
            output_tokens=999,  # Estimate (should be ignored)
        )

        # State should have actual values, not estimates
        assert new_state.last_input_tokens == 500
        assert new_state.last_output_tokens == 10

    def test_falls_back_to_estimates_when_no_actual(self):
        """When ThinkResult has no actual tokens, estimates should be used.

        This maintains backward compatibility - if the API doesn't provide
        usage data (some providers don't), we fall back to estimates.
        """
        state = make_minimal_state()

        # ThinkResult without actual token counts
        result = ThinkResult(
            content="The answer is 42.",
            model_display="test: model",
            # No input_tokens/output_tokens - they default to None
        )

        new_state = _apply_think_result(
            state=state,
            result=result,
            user_message_exists=True,
            input_tokens=500,  # Estimate
            output_tokens=10,  # Estimate
        )

        # State should use estimates when actual not available
        assert new_state.last_input_tokens == 500
        assert new_state.last_output_tokens == 10


# =============================================================================
# Integration Test
# =============================================================================


class TestEndToEndTokenFlow:
    """Integration test for complete token flow."""

    def test_tokens_flow_from_api_to_state(self):
        """Verify tokens flow: StreamChunk -> ThinkResult -> AgentState.

        This is the critical path that's currently broken.
        The UI reads from AgentState and shows '--' because actual tokens
        never make it through the pipeline.
        """
        # 1. Create orchestrator that provides actual token counts
        chunks = [
            StreamChunk(
                content="Response content here.",
                model="test/model",
                provider="test",
            ),
        ]
        orchestrator = MockOrchestratorWithUsage(
            chunks=chunks,
            final_input_tokens=1000,
            final_output_tokens=50,
        )

        # 2. Use delegator to get ThinkResult
        delegator = LiteLLMThinkDelegator(orchestrator)
        result = delegator.complete(
            messages=[{"role": "user", "content": "Test"}],
            tools=None,
            run_context=None,
            current_tier="instruct",
        )

        # 3. Verify ThinkResult has actual tokens
        assert result.input_tokens == 1000, "ThinkResult should have actual input tokens"
        assert result.output_tokens == 50, "ThinkResult should have actual output tokens"

        # 4. Apply to state
        state = make_minimal_state()
        new_state = _apply_think_result(
            state=state,
            result=result,
            user_message_exists=True,
            input_tokens=999,  # Bogus estimate
            output_tokens=999,  # Bogus estimate
        )

        # 5. Verify state has actual tokens (not estimates)
        assert new_state.last_input_tokens == 1000, "State should have actual input tokens"
        assert new_state.last_output_tokens == 50, "State should have actual output tokens"
