import pytest
import json
import httpx
from unittest.mock import MagicMock, Mock, patch
from scrappy.agent_tools.tools.web_tools import WebFetchTool, WebSearchTool
from scrappy.agent_tools.tools.base import ToolContext


# --- Fixtures ---

@pytest.fixture
def mock_context():
    context = MagicMock(spec=ToolContext)
    context.config = Mock()
    context.orchestrator = Mock()
    return context


@pytest.fixture
def mock_response():
    """Helper to create a mock httpx response."""
    resp = Mock(spec=httpx.Response)
    resp.status_code = 200
    resp.headers = {'content-type': 'text/plain'}
    resp.text = "default text"
    resp.json.return_value = {}
    return resp


@pytest.fixture
def mock_client(mock_response):
    """Patches httpx.Client to return a mock."""
    with patch("httpx.Client") as mock_cls:
        client_instance = mock_cls.return_value.__enter__.return_value
        client_instance.get.return_value = mock_response
        client_instance.post.return_value = mock_response
        yield client_instance


# --- WebFetchTool Tests ---

class TestWebFetchSafety:
    """Tests for URL safety and blocking logic."""

    @pytest.mark.parametrize("url,reason", [
        ("http://localhost:8000", "Blocked domain"),
        ("http://127.0.0.1/api", "Blocked domain"),
        ("http://192.168.1.5", "Blocked domain"),
        ("http://0.0.0.0", "Blocked domain"),
        ("ftp://example.com", "Invalid scheme"),
        ("file:///etc/passwd", "Invalid scheme"),
        ("https://", "No host"),
    ])
    def test_blocks_unsafe_urls(self, mock_context, url, reason):
        tool = WebFetchTool()
        result = tool.execute(mock_context, url=url)

        assert not result.success
        assert reason in result.error or "Unsafe URL" in result.error

    def test_allows_safe_url(self, mock_context, mock_client):
        tool = WebFetchTool()
        result = tool.execute(mock_context, url="https://api.example.com/data")

        assert result.success
        mock_client.get.assert_called()


class TestWebFetchExecution:
    """Tests for HTTP execution and content handling."""

    def test_fetch_json_pretty_print(self, mock_context, mock_client, mock_response):
        """Should format JSON responses nicely."""
        tool = WebFetchTool()

        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {"key": "value", "list": [1, 2]}
        mock_response.text = '{"key": "value", "list": [1, 2]}'

        result = tool.execute(mock_context, url="https://api.com")

        assert result.success
        assert '"key": "value"' in result.output
        assert "Content-Type: application/json" in result.output
        assert result.metadata["content_format"] == "json"

    def test_fetch_html_text_extraction(self, mock_context, mock_client, mock_response):
        """Should extract text from HTML and strip tags/scripts."""
        tool = WebFetchTool()

        html = """
        <html>
            <head><style>body { color: red; }</style></head>
            <body>
                <h1>Title</h1>
                <script>console.log('bad');</script>
                <p>Content goes here.</p>
            </body>
        </html>
        """
        mock_response.headers = {'content-type': 'text/html; charset=utf-8'}
        mock_response.text = html

        result = tool.execute(mock_context, url="https://site.com", extract_text=True)

        assert result.success
        assert "Title" in result.output
        assert "Content goes here" in result.output
        assert "console.log" not in result.output  # Script removed
        assert "color: red" not in result.output  # Style removed

    def test_html_extraction_fallback_regex(self, mock_context, mock_client, mock_response):
        """Should fall back to regex if BeautifulSoup is missing."""
        tool = WebFetchTool()
        html = "<h1>Regex Test</h1><br><p>It works</p>"
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.text = html

        # Simulate ImportError for bs4
        with patch.dict('sys.modules', {'bs4': None}):
            result = tool.execute(mock_context, url="https://site.com")

        assert result.success
        assert "Regex Test" in result.output
        assert "It works" in result.output
        assert "<h1>" not in result.output

    def test_post_method_handling(self, mock_context, mock_client):
        """Should handle POST requests with JSON body."""
        tool = WebFetchTool()
        body = '{"foo": "bar"}'

        tool.execute(mock_context, url="https://api.com", method="POST", body=body)

        mock_client.post.assert_called_once()
        # Check that json arg was parsed
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs['json'] == {"foo": "bar"}

    def test_timeout_handling(self, mock_context, mock_client):
        """Should return failure on timeout."""
        tool = WebFetchTool()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        result = tool.execute(mock_context, url="https://slow.com", timeout=5)

        assert not result.success
        assert "timed out" in result.error

    def test_http_error_status(self, mock_context, mock_client, mock_response):
        """Should return failure (but with content) for 4xx/5xx."""
        tool = WebFetchTool()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        result = tool.execute(mock_context, url="https://oops.com")

        # Tool returns success=False for >= 400, but still includes output
        assert result.success is False
        assert "HTTP 404" in result.error
        assert "Not Found" in result.output
        assert result.metadata["status_code"] == 404

    def test_truncation(self, mock_context, mock_client, mock_response):
        """Should truncate extremely large responses."""
        tool = WebFetchTool()
        # Limit in code is 50KB
        huge_text = "A" * (60 * 1024)
        mock_response.text = huge_text

        result = tool.execute(mock_context, url="https://big.com")

        assert result.success
        assert len(result.output) < len(huge_text)
        assert "truncated" in result.output
        assert result.metadata["truncated"] is True


# --- WebSearchTool Tests ---

class TestWebSearchTool:

    def test_unknown_registry(self, mock_context):
        """Should reject unknown registries."""
        tool = WebSearchTool()
        result = tool.execute(mock_context, registry="fake", query="something")

        assert not result.success
        assert "Unknown registry" in result.error

    def test_github_query_validation(self, mock_context):
        """Should require owner/repo format for GitHub."""
        tool = WebSearchTool()
        result = tool.execute(mock_context, registry="github", query="just-repo")

        assert not result.success
        assert "owner/repo" in result.error

# todo
    # def test_pypi_search_format(self, mock_context, mock_client, mock_response):
    #     """Should format PyPI JSON into readable text."""
    #     tool = WebSearchTool()
    #     pypi_data = {
    #         "info": {
    #             "name": "requests",
    #             "version": "2.31.0",
    #             "summary": "HTTP for Humans",
    #             "author": "Kenneth Reitz",
    #             "license": "Apache 2.0",
    #             "requires_python": ">=3.7"
    #         },
    #         "requires_dist": ["urllib3", "certifi"]
    #     }
    #     mock_response.json.return_value = pypi_data
    #
    #     result = tool.execute(mock_context, registry="pypi", query="requests")
    #
    #     assert result.success
    #     # Verify URL construction
    #     url_called = mock_client.get.call_args[0][0]
    #     assert "pypi.org/pypi/requests/json" in url_called
    #
    #     # Verify Output formatting
    #     assert "Package: requests" in result.output
    #     assert "Version: 2.31.0" in result.output
    #     assert "Dependencies" in result.output
    #     assert "- urllib3" in result.output

    def test_npm_search_format(self, mock_context, mock_client, mock_response):
        """Should format npm JSON into readable text."""
        tool = WebSearchTool()
        npm_data = {
            "name": "react",
            "dist-tags": {"latest": "18.2.0"},
            "versions": {
                "18.2.0": {
                    "license": "MIT",
                    "dependencies": {"loose-envify": "^1.1.0"}
                }
            }
        }
        mock_response.json.return_value = npm_data

        result = tool.execute(mock_context, registry="npm", query="react")

        assert result.success
        assert "registry.npmjs.org/react" in mock_client.get.call_args[0][0]
        assert "Version: 18.2.0" in result.output
        assert "loose-envify" in result.output

    def test_search_not_found(self, mock_context, mock_client, mock_response):
        """Should handle 404 from registries gracefully."""
        tool = WebSearchTool()
        mock_response.status_code = 404

        result = tool.execute(mock_context, registry="pypi", query="nonexistent-pkg")

        assert not result.success
        assert "not found" in result.error