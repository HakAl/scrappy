import pytest
import json
import httpx
from unittest.mock import MagicMock, Mock, patch
from scrappy.agent_tools.tools.web_tools import WebFetchTool
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
