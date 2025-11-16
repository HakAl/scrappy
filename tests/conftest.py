"""
Pytest configuration and shared fixtures.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Mock LLM Response for testing without API calls
@dataclass
class MockLLMResponse:
    """Mock LLM response for testing."""
    content: str
    tokens_used: int = 100
    model: str = "mock-model"
    provider: str = "mock"
    cached: bool = False


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


@pytest.fixture
def sample_codebase_context(temp_project_dir):
    """Create a sample codebase context."""
    from src.context import CodebaseContext
    return CodebaseContext(project_root=temp_project_dir)


@pytest.fixture
def isolated_orchestrator(mock_registry, temp_project_dir):
    """Create an isolated orchestrator for testing without real API calls."""
    from src.orchestrator.core import AgentOrchestrator

    with patch('src.orchestrator.core.ProviderRegistry', return_value=mock_registry):
        with patch('src.orchestrator.core.CodebaseContext'):
            orch = AgentOrchestrator.__new__(AgentOrchestrator)
            orch.registry = mock_registry
            orch._brain = mock_registry.get("mock")
            orch._brain_name = "mock"
            orch.task_history = []
            orch.codebase_context = None
            orch.verbose = False
            orch.working_memory = Mock()
            orch.session_manager = Mock()
            orch.cache = Mock()
            orch.cache.get.return_value = None
            orch.rate_tracker = Mock()
            orch.rate_tracker.can_call.return_value = True
            orch.provider_selector = Mock()
            orch.task_executor = Mock()
            return orch


# Markers for conditional test execution
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_api: Tests requiring API keys")
