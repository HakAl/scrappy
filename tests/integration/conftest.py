"""
Pytest configuration for integration tests.

Integration tests use VCR cassettes to replay recorded HTTP interactions.
By default, tests replay from cassettes (no API calls needed).

To record new cassettes:
    pytest tests/integration/ --vcr-record=all

Cassettes are stored in tests/integration/cassettes/ and committed to git.
"""
import pytest
from pathlib import Path
from dotenv import load_dotenv
import litellm
import httpx

# Load .env for API keys when recording cassettes
load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def _force_httpx_transport_for_vcr():
    """
    Force LiteLLM to use httpx transport for VCR compatibility.

    LiteLLM >= 1.71 defaults to aiohttp which VCR cannot intercept.
    This fixture disables aiohttp and forces httpx transport during test runs,
    allowing VCR to record and replay HTTP interactions.
    """
    # Disable aiohttp, force httpx
    litellm.disable_aiohttp_transport = True
    litellm.use_aiohttp_transport = False

    # Set explicit httpx clients for both sync and async
    litellm.client_session = httpx.Client()
    litellm.aclient_session = httpx.AsyncClient()

    yield

    # Restore defaults
    litellm.disable_aiohttp_transport = False
    litellm.use_aiohttp_transport = True
    litellm.client_session = None
    litellm.aclient_session = None


@pytest.fixture(scope="module")
def vcr_config(request):
    """
    Configure VCR for recording and replaying HTTP interactions.

    Default mode is 'none' (replay only). Use --vcr-record=all to record.
    """
    # Check if recording mode was requested via CLI
    record_mode = request.config.getoption("--vcr-record", default="none")

    return {
        "cassette_library_dir": str(Path(__file__).parent / "cassettes"),
        "record_mode": record_mode,
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("x-api-key", "REDACTED"),
            ("api-key", "REDACTED"),
        ],
        "decode_compressed_response": True,
        "ignore_localhost": False,
        "serializer": "yaml",
    }


@pytest.fixture(autouse=True)
def restore_api_keys_for_recording(monkeypatch, request):
    """
    Restore API keys when recording cassettes.

    The global conftest.py removes all API keys to prevent accidental
    real API calls. When recording (--vcr-record=all), we need them back.
    """
    record_mode = request.config.getoption("--vcr-record", default="none")

    # Only restore keys when recording
    if record_mode == "none":
        return

    # Re-load from .env since root conftest deleted them
    from dotenv import dotenv_values
    env_values = dotenv_values()

    api_keys = [
        'GROQ_API_KEY',
        'CEREBRAS_API_KEY',
        'GEMINI_API_KEY',
        'SAMBANOVA_API_KEY',
    ]

    for key in api_keys:
        if key in env_values and env_values[key]:
            monkeypatch.setenv(key, env_values[key])
