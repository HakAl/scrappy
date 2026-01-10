"""
Web/HTTP client tools for the code agent.

Provides capabilities for fetching external documentation,
API responses, and web content.
"""

import json
import re
from urllib.parse import urlparse

import httpx

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


class WebFetchTool(ToolBase):
    """Fetch content from URLs (documentation, APIs, web pages)."""

    # Safety: Block potentially dangerous domains
    BLOCKED_DOMAINS = [
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        '::1',
        '169.254.',  # Link-local
        '10.',       # Private
        '172.16.',   # Private
        '192.168.',  # Private
    ]

    # Common user agent to avoid blocks
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (compatible; CodeAgent/1.0; +https://github.com/anthropics/claude-code)"
    )

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch content from URL (docs, APIs, web pages)"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("url", str, "URL to fetch", required=True),
            ToolParameter("method", str, "HTTP method (GET, POST)", required=False, default="GET"),
            ToolParameter("headers", str, "JSON string of headers", required=False, default="{}"),
            ToolParameter("body", str, "Request body for POST", required=False, default=""),
            ToolParameter("extract_text", bool, "Extract text from HTML (remove tags)", required=False, default=True),
            ToolParameter("timeout", int, "Request timeout in seconds", required=False, default=30),
        ]

    def _is_safe_url(self, url: str) -> tuple[bool, str]:
        """Check if URL is safe to fetch (not internal/private)."""
        try:
            parsed = urlparse(url)

            # Must have scheme
            if parsed.scheme not in ('http', 'https'):
                return False, f"Invalid scheme: {parsed.scheme}. Only http/https allowed."

            # Check hostname
            hostname = parsed.hostname or ''

            # Block internal IPs and domains
            for blocked in self.BLOCKED_DOMAINS:
                if hostname.startswith(blocked) or hostname == blocked:
                    return False, f"Blocked domain/IP: {hostname}"

            # Block file:// and other schemes
            if not parsed.netloc:
                return False, "No host specified in URL"

            return True, ""
        except Exception as e:
            return False, f"URL parsing error: {str(e)}"

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML content."""
        try:
            # Try to use BeautifulSoup if available
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Get text
            text = soup.get_text(separator='\n', strip=True)

            # Clean up excessive whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return '\n'.join(lines)
        except ImportError:
            # Fallback: basic regex-based extraction
            # Remove script/style tags and their content
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

            # Remove all HTML tags
            text = re.sub(r'<[^>]+>', ' ', html)

            # Decode HTML entities
            text = text.replace('&nbsp;', ' ')
            text = text.replace('&lt;', '<')
            text = text.replace('&gt;', '>')
            text = text.replace('&amp;', '&')
            text = text.replace('&quot;', '"')

            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text)
            lines = [line.strip() for line in text.split('.') if line.strip()]
            return '\n'.join(lines)

    def _format_json(self, data: any) -> str:
        """Pretty format JSON data."""
        return json.dumps(data, indent=2, ensure_ascii=False)

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        url = kwargs["url"]
        method = kwargs.get("method", "GET").upper()
        headers_str = kwargs.get("headers", "{}")
        body = kwargs.get("body", "")
        extract_text = kwargs.get("extract_text", True)
        timeout = kwargs.get("timeout", 30)

        # Safety check
        is_safe, error_msg = self._is_safe_url(url)
        if not is_safe:
            return ToolResult(False, "", f"Unsafe URL: {error_msg}")

        # Parse headers
        try:
            headers = json.loads(headers_str) if headers_str else {}
        except json.JSONDecodeError as e:
            return ToolResult(False, "", f"Invalid headers JSON: {str(e)}")

        # Add default user agent if not specified
        if 'User-Agent' not in headers:
            headers['User-Agent'] = self.DEFAULT_USER_AGENT

        try:
            # Configure client with timeout and redirects
            max_content_size = 500 * 1024  # 500KB limit

            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                max_redirects=5
            ) as client:
                # Make request
                if method == "GET":
                    response = client.get(url, headers=headers)
                elif method == "POST":
                    # Determine content type
                    if body:
                        try:
                            json_body = json.loads(body)
                            response = client.post(url, json=json_body, headers=headers)
                        except json.JSONDecodeError:
                            response = client.post(url, content=body, headers=headers)
                    else:
                        response = client.post(url, headers=headers)
                else:
                    return ToolResult(False, "", f"Unsupported HTTP method: {method}")

                # Check status
                status_code = response.status_code
                content_type = response.headers.get('content-type', '')

                # Get content with size limit
                content = response.text
                if len(content) > max_content_size:
                    content = content[:max_content_size]
                    truncated = True
                else:
                    truncated = False

                # Process based on content type
                if 'application/json' in content_type:
                    try:
                        json_data = response.json()
                        output = self._format_json(json_data)
                        content_format = "json"
                    except ValueError:
                        output = content
                        content_format = "text"
                elif 'text/html' in content_type and extract_text:
                    output = self._extract_text_from_html(content)
                    content_format = "html_text"
                else:
                    output = content
                    content_format = "raw"

                # Truncate if still too large
                max_output = 50 * 1024  # 50KB for output
                if len(output) > max_output:
                    output = output[:max_output] + "\n\n... [truncated]"
                    truncated = True

                # Build result
                result_header = f"URL: {url}\nStatus: {status_code}\nContent-Type: {content_type}\n"
                if truncated:
                    result_header += "Note: Content was truncated due to size limits\n"
                result_header += "\n--- Content ---\n"

                full_output = result_header + output

                # Store in working memory if available
                if context.orchestrator and hasattr(context.orchestrator, 'remember_web_fetch'):
                    context.orchestrator.remember_web_fetch(url, status_code, len(output))

                # Return success even for 4xx/5xx (they might be informative)
                return ToolResult(
                    success=status_code < 400,
                    output=full_output,
                    error=f"HTTP {status_code}" if status_code >= 400 else None,
                    metadata={
                        "url": url,
                        "status_code": status_code,
                        "content_type": content_type,
                        "content_format": content_format,
                        "content_length": len(output),
                        "truncated": truncated
                    }
                )

        except httpx.TimeoutException:
            return ToolResult(False, "", f"Request timed out after {timeout} seconds")
        except httpx.ConnectError as e:
            return ToolResult(False, "", f"Connection error: {str(e)}")
        except httpx.TooManyRedirects:
            return ToolResult(False, "", "Too many redirects (max 5)")
        except Exception as e:
            return ToolResult(False, "", f"Request failed: {str(e)}")
