"""
Web/HTTP client tools for the code agent.

Provides capabilities for fetching external documentation,
API responses, and web content.
"""

import json
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from .base import Tool, ToolParameter, ToolResult, ToolContext


class WebFetchTool(Tool):
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
                    except:
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


class WebSearchTool(Tool):
    """Search documentation and package registries."""

    # Pre-configured search endpoints
    SEARCH_ENDPOINTS = {
        "pypi": "https://pypi.org/pypi/{package}/json",
        "npm": "https://registry.npmjs.org/{package}",
        "github": "https://api.github.com/repos/{owner}/{repo}",
    }

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search package registries (PyPI, npm) or GitHub repos"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("registry", str, "Registry to search: pypi, npm, github", required=True),
            ToolParameter("query", str, "Package name or owner/repo for GitHub", required=True),
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        registry = kwargs["registry"].lower()
        query = kwargs["query"]

        if registry not in self.SEARCH_ENDPOINTS:
            return ToolResult(
                False,
                "",
                f"Unknown registry: {registry}. Available: {', '.join(self.SEARCH_ENDPOINTS.keys())}"
            )

        # Build URL
        if registry == "github":
            if '/' not in query:
                return ToolResult(False, "", "GitHub query must be in format: owner/repo")
            parts = query.split('/', 1)
            url = self.SEARCH_ENDPOINTS[registry].format(owner=parts[0], repo=parts[1])
        else:
            url = self.SEARCH_ENDPOINTS[registry].format(package=query)

        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                response = client.get(url, headers={
                    'User-Agent': WebFetchTool.DEFAULT_USER_AGENT,
                    'Accept': 'application/json'
                })

                if response.status_code == 404:
                    return ToolResult(False, "", f"{registry}: Package/repo '{query}' not found")

                if response.status_code != 200:
                    return ToolResult(False, "", f"{registry}: HTTP {response.status_code}")

                data = response.json()

                # Format based on registry
                if registry == "pypi":
                    info = data.get("info", {})
                    output = self._format_pypi(info)
                elif registry == "npm":
                    output = self._format_npm(data)
                elif registry == "github":
                    output = self._format_github(data)
                else:
                    output = json.dumps(data, indent=2)

                return ToolResult(
                    True,
                    output,
                    metadata={"registry": registry, "query": query}
                )

        except Exception as e:
            return ToolResult(False, "", f"Search failed: {str(e)}")

    def _format_pypi(self, info: dict) -> str:
        """Format PyPI package info."""
        lines = [
            f"Package: {info.get('name', 'N/A')}",
            f"Version: {info.get('version', 'N/A')}",
            f"Summary: {info.get('summary', 'N/A')}",
            f"Author: {info.get('author', 'N/A')}",
            f"License: {info.get('license', 'N/A')}",
            f"Python: {info.get('requires_python', 'N/A')}",
            f"Home: {info.get('home_page', 'N/A')}",
            f"PyPI: https://pypi.org/project/{info.get('name', '')}/",
        ]

        # Add dependencies if available
        requires = info.get('requires_dist', [])
        if requires:
            lines.append(f"\nDependencies ({len(requires)}):")
            for dep in requires[:20]:  # Limit to 20
                lines.append(f"  - {dep}")
            if len(requires) > 20:
                lines.append(f"  ... and {len(requires) - 20} more")

        return '\n'.join(lines)

    def _format_npm(self, data: dict) -> str:
        """Format npm package info."""
        latest = data.get('dist-tags', {}).get('latest', 'N/A')
        version_info = data.get('versions', {}).get(latest, {})

        lines = [
            f"Package: {data.get('name', 'N/A')}",
            f"Version: {latest}",
            f"Description: {data.get('description', 'N/A')}",
            f"License: {version_info.get('license', 'N/A')}",
            f"Homepage: {data.get('homepage', 'N/A')}",
            f"Repository: {data.get('repository', {}).get('url', 'N/A')}",
            f"npm: https://www.npmjs.com/package/{data.get('name', '')}",
        ]

        # Add dependencies
        deps = version_info.get('dependencies', {})
        if deps:
            lines.append(f"\nDependencies ({len(deps)}):")
            for name, version in list(deps.items())[:20]:
                lines.append(f"  - {name}: {version}")
            if len(deps) > 20:
                lines.append(f"  ... and {len(deps) - 20} more")

        return '\n'.join(lines)

    def _format_github(self, data: dict) -> str:
        """Format GitHub repo info."""
        lines = [
            f"Repository: {data.get('full_name', 'N/A')}",
            f"Description: {data.get('description', 'N/A')}",
            f"Stars: {data.get('stargazers_count', 0):,}",
            f"Forks: {data.get('forks_count', 0):,}",
            f"Open Issues: {data.get('open_issues_count', 0):,}",
            f"Language: {data.get('language', 'N/A')}",
            f"License: {data.get('license', {}).get('name', 'N/A') if data.get('license') else 'N/A'}",
            f"Created: {data.get('created_at', 'N/A')}",
            f"Updated: {data.get('updated_at', 'N/A')}",
            f"Default Branch: {data.get('default_branch', 'N/A')}",
            f"URL: {data.get('html_url', 'N/A')}",
            f"Clone: {data.get('clone_url', 'N/A')}",
        ]

        # Topics/tags
        topics = data.get('topics', [])
        if topics:
            lines.append(f"\nTopics: {', '.join(topics)}")

        return '\n'.join(lines)
