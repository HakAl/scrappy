"""
Pytest configuration and shared fixtures.
"""
import contextlib
import os
import pytest
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock
from dataclasses import dataclass


_DEFAULT_TEST_SESSION_ID = f"run-{uuid.uuid4().hex[:8]}"


def _get_session_temp_root(root_path: Path) -> Path:
    """Resolve the root temp directory for the test session."""
    override = os.environ.get("SCRAPPY_TEST_TEMP")
    session_id = os.environ.get("SCRAPPY_TEST_SESSION_ID", _DEFAULT_TEST_SESSION_ID)
    base_root = Path(override).expanduser() if override else root_path / ".pytest_tmp"
    return base_root / session_id


def _configure_test_temp_dirs(root_path: Path) -> tuple[Path, Path]:
    """Configure repo-local temp directories for pytest and tempfile users."""
    session_root = _get_session_temp_root(root_path).resolve()
    pytest_temp = session_root / "pytest"
    system_temp = session_root / "system"

    pytest_temp.mkdir(parents=True, exist_ok=True)
    system_temp.mkdir(parents=True, exist_ok=True)

    os.environ["TMPDIR"] = str(system_temp)
    os.environ["TEMP"] = str(system_temp)
    os.environ["TMP"] = str(system_temp)
    tempfile.tempdir = str(system_temp)

    return pytest_temp, system_temp


def pytest_configure(config):
    """Configure pytest and tempfile to use repo-local temp directories."""
    config.addinivalue_line(
        "markers",
        "no_contained_config_seed: opt OUT of the seeded global CLI configuration "
        "(layer 2 only). Layer 1 containment of the configuration SOURCE still "
        "applies, so an opted-out test never reads developer configuration; it "
        "drives its own seeding/reset lifecycle with controlled inputs. For "
        "discovery, direct-parser and cache/reload tests.",
    )
    pytest_temp, _ = _configure_test_temp_dirs(Path(config.rootpath))

    if not config.option.basetemp:
        config.option.basetemp = pytest_temp


# ---------------------------------------------------------------------------
# Containment DISCLOSURE banner (scrappy-i2jo PR-1, plan 3e).
#
# This is DISCLOSURE, NOT CONTAINMENT. It does not redirect anything. A bare
# `pytest` invocation still writes to the developer's REAL user profile until the
# later routing PRs land; this banner only tells the developer so, and names the
# launcher that does contain the run. The operator declined an in-process HOME
# backstop (open decision O-1), so none is added here: an in-process assignment
# cannot be ordered before the import-bound constants it would need to beat.
# ---------------------------------------------------------------------------

_TRUTHY = {"1", "true", "t", "yes", "y"}

# Profile paths still expected to escape at PR-1, with the PR that routes each. This
# is the current expected-escape list the banner discloses; it shrinks as PRs land.
_EXPECTED_ESCAPES = (
    "~/.scrappy/command_history (routed in PR-2)",
    "~/.scrappy/model_cooldowns.json (routed in PR-2)",
    "<user config>/scrappy/config.json (routed through injection in PR-3; still "
    "reached by tests that construct CLI, ScrappyApp or AgentOrchestrator bare)",
    "<user data>/scrappy user directory CREATION and <legacy>/.scrappy reads "
    "(the rate_limits.json write and the legacy migration copy are routed by "
    "PR-4a injection and PR-4b forwarding, and the contained measurement now "
    "records ZERO file operations; a mkdir and a read leave no file behind, so "
    "the measurement cannot speak for them while bare constructions remain)",
    "~/.cache/huggingface population (unattributed; measured by PR-1)",
)


def _containment_active() -> bool:
    """True when the run is inside scripts/contained-pytest.sh's environment.

    The launcher roots HOME under a `.pytest_profile` region and sets the dotenv
    switch; both together are the signal. Disclosure fires only when absent.
    """
    home = os.environ.get("HOME", "")
    home_contained = ".pytest_profile" in Path(home).parts
    dotenv_disabled = os.environ.get("PYTHON_DOTENV_DISABLED", "").casefold() in _TRUTHY
    return home_contained and dotenv_disabled


def pytest_report_header(config):
    """Emit the disclosure banner in the session header when NOT contained."""
    if _containment_active():
        return None
    lines = [
        "containment DISCLOSURE (scrappy-i2jo PR-1): this run is NOT contained.",
        "  A bare pytest writes to your REAL user profile. Run the suite through",
        "  scripts/contained-pytest.sh to redirect it into a disposable profile.",
        "  This message is disclosure, not containment; it does not redirect anything.",
        "  Profile paths still expected to escape at this point in the sequence:",
    ]
    lines.extend(f"    - {escape}" for escape in _EXPECTED_ESCAPES)
    return lines

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


# ---------------------------------------------------------------------------
# Contained CLI configuration (PR-7, brief S4a). Implements i2jo D4(iii):
# fallback consumers must see CONTAINED configuration across the suite, not
# whatever discovery finds on the developer's machine.
# ---------------------------------------------------------------------------

# Known values, deliberately distinct from any plausible real configuration so
# a test that accidentally reads the developer's file fails loudly rather than
# passing on a coincidence.
CONTAINED_CONFIG_SEED = {
    "temperature_default": 0.123,
    "max_tokens_query": 4321,
}


def _selector_is_repository_owned(selector, repo_root) -> bool:
    """True ONLY for a selector inside the repository-owned disposable profile.

    A SESSION LABEL IS NOT PROVENANCE. scripts/contained-pytest.sh:72-78
    explicitly READS AND ADOPTS an inherited SCRAPPY_TEST_SESSION_ID, so its
    presence proves nothing about who assigned the selector. Membership of HOME
    proves nothing either, because a direct pytest run has an ordinary HOME.

    The launcher's real provenance is its repository-derived layout:
    PROFILE_ROOT="${REPO_ROOT}/.pytest_profile/${SESSION_ID}" and
    HOME_DIR="${PROFILE_ROOT}/home" (:88-89). This binds to that layout and
    nothing else.

    Both sides are RESOLVED before comparison, so a selector that sits inside
    the profile directory but symlinks out of it resolves outside the anchor
    and is rejected.
    """
    if selector is None or repo_root is None:
        return False
    anchor = Path(repo_root) / ".pytest_profile"
    try:
        return Path(selector).resolve().is_relative_to(anchor.resolve())
    except (OSError, ValueError, RuntimeError, TypeError):
        return False


@contextlib.contextmanager
def contained_cli_config_scope(disposable_dir, seed: bool = True, repo_root=None):
    """The fixture's ENTIRE lifecycle, as one directly testable unit.

    Extracted from the fixture so restoration can be observed IMMEDIATELY after
    the scope exits, rather than inferred from a later test whose own setup
    would mask a failure.
    """
    import json as _json

    from scrappy.cli import config_factory as _cf

    disposable_dir = Path(disposable_dir)
    disposable_dir.mkdir(parents=True, exist_ok=True)

    # reset_config() clears the module global AND _factory._cached_config, so
    # both must be saved or teardown clears rather than restores.
    saved_global = _cf._global_config
    saved_factory_cache = getattr(_cf._factory, "_cached_config", None)
    saved_env = os.environ.get("CLI_CONFIG_PATH")
    env_replaced = False

    try:
        # LAYER 1: own the configuration SOURCE unless it is anchored to the
        # repository-owned disposable profile. A genuine launcher assignment is
        # kept; absent, inherited and hostile selectors are all replaced with a
        # disposable non-existent path, which config_factory skips gracefully at
        # its exists() gate while still displacing any CWD scan.
        # CLI_CONFIG_PATH is never removed globally.
        if not _selector_is_repository_owned(saved_env, repo_root):
            os.environ["CLI_CONFIG_PATH"] = str(disposable_dir / "contained-absent.json")
            env_replaced = True

        _cf.reset_config()

        # LAYER 2: seed known values for the fallback consumers.
        # set_config with an explicitly parsed object, NOT get_config(..., reload=True):
        # CLIConfigFactory.create() merges environment AFTER the file and overwrites
        # explicit file values with environment defaults (measured: 0.7 with
        # use_env=True versus 0.123 with use_env=False for the same file). That is
        # pre-existing production behaviour, tracked separately as scrappy-bj58 and
        # deliberately NOT changed here; seeding simply must not depend on it.
        if seed:
            seed_file = disposable_dir / ".scrappy.json"
            seed_file.write_text(_json.dumps(CONTAINED_CONFIG_SEED))
            _cf.set_config(_cf.CLIConfigFactory().create_from_file(str(seed_file)))

        yield
    finally:
        # Restore global, factory cache and any selector THIS scope replaced.
        _cf.reset_config()
        _cf._global_config = saved_global
        _cf._factory._cached_config = saved_factory_cache
        if env_replaced:
            if saved_env is None:
                os.environ.pop("CLI_CONFIG_PATH", None)
            else:
                os.environ["CLI_CONFIG_PATH"] = saved_env


@pytest.fixture(autouse=True)
def contained_cli_config(request, tmp_path_factory):
    """Thin wrapper: all behaviour lives in contained_cli_config_scope."""
    seed = request.node.get_closest_marker("no_contained_config_seed") is None
    with contained_cli_config_scope(
        tmp_path_factory.mktemp("contained-cli-config"),
        seed=seed,
        repo_root=request.config.rootpath,
    ):
        yield
