"""
Pytest configuration and shared fixtures.
"""
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock
from dataclasses import dataclass


def pytest_configure(config):
    """Configure pytest to use system temp directory instead of project root."""
    # Use system temp directory to avoid permission issues and keep project clean
    if not config.option.basetemp:
        config.option.basetemp = Path(tempfile.gettempdir()) / "pytest-scrappy"

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# Add tests directory for test helper imports
sys.path.insert(0, str(Path(__file__).parent))


# Mock LLM Response for testing without API calls
@dataclass
class MockLLMResponse:
    """Mock LLM response for testing."""
    content: str
    tokens_used: int = 100
    model: str = "mock-model"
    provider: str = "mock"


@pytest.fixture
def mock_llm_response():
    """Factory fixture for creating mock LLM responses."""
    def _create(content: str = "Mock response", tokens: int = 100):
        return MockLLMResponse(content=content, tokens_used=tokens)
    return _create


@pytest.fixture
def mock_provider(mock_llm_response):
    """Create a mock LLM provider."""
    provider = Mock()
    provider.name = "mock"
    provider.chat.return_value = mock_llm_response("Test response")
    provider.get_limits.return_value = Mock(
        requests_per_minute=100,
        requests_per_day=10000,
        tokens_per_minute=100000
    )
    provider.is_available.return_value = True
    return provider


@pytest.fixture
def mock_registry(mock_provider):
    """Create a mock provider registry."""
    registry = Mock()
    registry.list_available.return_value = ["mock", "cerebras", "groq"]
    registry.get.return_value = mock_provider
    return registry


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory for testing."""
    # Create basic project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "main.py").write_text('print("Hello")\n')
    (tmp_path / "README.md").write_text("# Test Project\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / ".git").mkdir()

    return tmp_path


@pytest.fixture(autouse=True)
def prevent_real_api_calls(monkeypatch):
    """
    CRITICAL: Prevent ALL tests from making real API calls.

    This fixture runs automatically for EVERY test.
    Removes all API keys from environment so tests MUST use mocks.
    """
    # Block ALL real provider API calls by removing API keys from environment
    # Tests that need providers MUST use mocks
    api_keys_to_block = [
        'GROQ_API_KEY',
        'CEREBRAS_API_KEY',
        'GEMINI_API_KEY',
        'COHERE_API_KEY',
        'GITHUB_API_KEY',
        'GITHUB_TOKEN',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        # Langfuse tracing - prevent polluting observability data in tests
        'LANGFUSE_PUBLIC_KEY',
        'LANGFUSE_SECRET_KEY',
        'LANGFUSE_HOST',
    ]

    for key in api_keys_to_block:
        monkeypatch.delenv(key, raising=False)

    # Reset Langfuse tracer singleton to ensure tests don't use cached real tracer
    try:
        from scrappy.graph.tracing import set_tracer, NoOpTracer
        set_tracer(NoOpTracer())
    except ImportError:
        pass  # Tracing module not available


def pytest_deselected(items):
    if not items:
        return
    config = items[0].session.config
    reporter = config.pluginmanager.getplugin("terminalreporter")
    reporter.ensure_newline()
    for item in items:
        reporter.line(f"deselected: {item.nodeid}", yellow=True, bold=True)


@pytest.fixture
def mock_semantic_search():
    """
    Mock semantic search provider for testing.

    Returns a configured mock that implements SemanticSearchProtocol
    without loading real FastEmbed models or LanceDB.
    """
    mock = Mock()
    mock.index_files = Mock()
    mock.search = Mock(return_value={'chunks': [], 'tokens_used': 0})
    mock.is_indexed = Mock(return_value=False)
    mock.clear_index = Mock()
    return mock


@pytest.fixture
def mock_semantic_initializer():
    """
    Mock semantic search initializer for testing.

    Returns a configured mock that implements BackgroundInitializerProtocol
    without actually starting background threads.
    """
    mock = Mock()
    mock.start = Mock()
    mock.is_complete = Mock(return_value=True)
    mock.is_running = Mock(return_value=False)
    mock.wait_for_completion = Mock(return_value=True)
    mock.get_result = Mock(return_value=None)
    mock.get_error = Mock(return_value=None)
    mock.get_status = Mock(return_value="Complete")
    return mock


@pytest.fixture
def mock_codebase_context(temp_project_dir):
    """
    Create a mock CodebaseContext with semantic search disabled.

    Returns a context that won't load real databases or models in tests.
    """
    from scrappy.context import CodebaseContext

    context = CodebaseContext(
        project_path=str(temp_project_dir)
    )
    return context


@pytest.fixture
def mock_tool_registry():
    """
    Create a mock ToolRegistry for testing.

    Returns a mock registry that implements the required methods
    without registering real tools.
    """
    mock = Mock()
    mock.generate_descriptions.return_value = "Mock tool descriptions"
    # Mock should include common tool names that tests expect to find
    mock.get_full_prompt_section.return_value = (
        "Available tools:\n"
        "- read_file: Read file contents\n"
        "- write_file: Write content to file\n"
        "- run_command: Execute shell command\n"
        "- list_files: List files in directory\n"
        "- search_code: Search for code patterns\n"
        "\n"
        "Response format: {\"thought\": \"...\", \"action\": \"...\", \"parameters\": {...}, \"is_complete\": true/false}"
    )
    return mock
