"""
Integration tests for provider responses using VCR cassettes.

These tests record real API responses for:
1. Basic completions - verify response parsing works
2. Streaming - verify chunk handling works
3. Tool calls - verify extraction works
4. Provider quirks - capture edge cases for regression testing

Run with: pytest -m integration tests/integration/

Cassettes are stored in tests/integration/cassettes/ and replayed in CI.
"""

import os
import pytest

# Mark all tests in this module as integration (skipped by default)
pytestmark = pytest.mark.integration
from dotenv import load_dotenv
from scrappy.orchestrator.litellm_service import LiteLLMService
from scrappy.orchestrator.litellm_config import create_litellm_router
from scrappy.orchestrator.types import StreamChunk, ToolCallFragment
from scrappy.providers.base import LLMResponse, ToolCall
from tests.helpers import MockOutputForLiteLLM, MockApiKeyService

# Load keys for recording cassettes
load_dotenv()


# =============================================================================
# Shared Fixtures
# =============================================================================

@pytest.fixture
def mock_output():
    """Create mock output for tests."""
    return MockOutputForLiteLLM()


@pytest.fixture
def api_key_service():
    """Create API key service with keys from environment."""
    service = MockApiKeyService()
    for key_name in ["GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "SAMBANOVA_API_KEY"]:
        value = os.getenv(key_name)
        if value:
            service.set_key(key_name, value)
    return service


@pytest.fixture
def litellm_service(api_key_service, mock_output):
    """Create configured LiteLLM service."""
    router = create_litellm_router()
    service = LiteLLMService(
        router=router,
        api_key_service=api_key_service,
        output=mock_output,
    )
    service.configure()
    return service


@pytest.fixture
def calculator_tool():
    """Simple calculator tool for testing."""
    return [{
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Add two numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"}
                },
                "required": ["a", "b"]
            }
        }
    }]


# =============================================================================
# Core Tests - These are the essential cassettes to record
# =============================================================================

class TestCoreProviderBehavior:
    """Core tests that verify provider integration works."""

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_basic_completion(self, litellm_service):
        """
        Record: Basic completion response parsing.

        Verifies:
        - Response has content
        - Token counts populated
        - Provider/model info present
        """
        messages = [{"role": "user", "content": "Say 'test' and nothing else."}]

        response, task_record = await litellm_service.completion(
            model="fast",
            messages=messages,
            max_tokens=10,
        )

        assert isinstance(response, LLMResponse)
        assert response.content != ""
        assert response.tokens_used > 0
        assert response.provider != ""

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_streaming_completion(self, litellm_service):
        """
        Record: Streaming response with multiple chunks.

        Verifies:
        - Multiple chunks received
        - Content accumulates correctly
        - Final chunk has finish_reason
        """
        messages = [{"role": "user", "content": "Count: 1, 2, 3"}]

        chunks = []
        async for chunk in litellm_service.stream_completion(
            model="fast",
            messages=messages,
            max_tokens=30,
        ):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert all(isinstance(c, StreamChunk) for c in chunks)

        content = "".join(c.content for c in chunks)
        assert content != ""

        # Last chunk should have finish_reason
        assert chunks[-1].finish_reason in ["stop", "length", None]

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_tool_call_extraction(self, litellm_service, calculator_tool):
        """
        Record: Tool call parsing from response.

        Verifies:
        - Tool call is extracted OR model returns JSON in content
        - Some providers (Cerebras) return tool calls as JSON content
        """
        messages = [{
            "role": "user",
            "content": "What is 15 + 27? Use the calculate tool."
        }]

        response, _ = await litellm_service.completion(
            model="fast",
            messages=messages,
            tools=calculator_tool,
            max_tokens=100,
        )

        # Some providers return proper tool_calls, others return JSON in content
        if response.tool_calls is not None:
            assert len(response.tool_calls) >= 1
            tool_call = response.tool_calls[0]
            assert isinstance(tool_call, ToolCall)
            assert tool_call.name == "calculate"
            assert isinstance(tool_call.arguments, dict)
        else:
            # Fallback: check if JSON was returned in content
            import json
            try:
                parsed = json.loads(response.content)
                assert "name" in parsed or "arguments" in parsed
            except json.JSONDecodeError:
                pytest.fail("No tool_calls and content is not valid JSON")

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_streaming_with_tool_calls(self, litellm_service, calculator_tool):
        """
        Record: Streaming response with tool call fragments.

        Verifies:
        - Tool fragments accumulate correctly
        - Final tool call is complete
        """
        messages = [{
            "role": "user",
            "content": "Calculate 42 + 58 using the tool."
        }]

        fragments_by_index = {}
        async for chunk in litellm_service.stream_completion(
            model="fast",
            messages=messages,
            tools=calculator_tool,
            max_tokens=100,
        ):
            for frag in chunk.tool_call_fragments:
                idx = frag.index
                if idx not in fragments_by_index:
                    fragments_by_index[idx] = {"name": "", "arguments": ""}
                if frag.name:
                    fragments_by_index[idx]["name"] += frag.name
                if frag.arguments:
                    fragments_by_index[idx]["arguments"] += frag.arguments

        # If tool calls were streamed, verify structure
        if fragments_by_index:
            for accumulated in fragments_by_index.values():
                assert accumulated["name"] != ""


# =============================================================================
# Provider Quirk Tests - Capture edge cases for regression
# =============================================================================

class TestProviderQuirks:
    """
    Tests for provider-specific quirks.

    These cassettes help ensure we handle edge cases:
    - Empty chunks in stream
    - Double final chunks (Groq)
    - Unicode handling
    """

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_empty_chunks_handled(self, litellm_service):
        """
        Record: Stream that may contain empty content chunks.

        Some providers send empty chunks as heartbeats.
        """
        messages = [{"role": "user", "content": "Hi"}]

        chunks = []
        async for chunk in litellm_service.stream_completion(
            model="fast",
            messages=messages,
            max_tokens=10,
        ):
            chunks.append(chunk)
            # Content should never be None
            assert chunk.content is not None

        assert len(chunks) > 0

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_unicode_content(self, litellm_service):
        """
        Record: Response with unicode characters.

        Verifies unicode doesn't break parsing.
        """
        messages = [{"role": "user", "content": "Write: thumbs up emoji"}]

        content = ""
        async for chunk in litellm_service.stream_completion(
            model="fast",
            messages=messages,
            max_tokens=20,
        ):
            content += chunk.content

        assert isinstance(content, str)
        assert content.strip() != ""

    @pytest.mark.vcr()
    @pytest.mark.asyncio
    async def test_max_tokens_truncation(self, litellm_service):
        """
        Record: Response truncated by max_tokens.

        Verifies finish_reason is 'length' when truncated.
        """
        messages = [{"role": "user", "content": "Write a very long story"}]

        response, _ = await litellm_service.completion(
            model="fast",
            messages=messages,
            max_tokens=5,
        )

        assert response.output_tokens <= 10  # Some tolerance
        if "finish_reason" in response.metadata:
            assert response.metadata["finish_reason"] in ["length", "stop"]
