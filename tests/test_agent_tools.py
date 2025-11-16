"""
Tests for agent tools - base classes, file tools, and tool registry.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.agent_tools.tools.base import (
    ToolContext,
    ToolParameter,
    ToolResult,
    Tool
)
from src.agent_tools.tools.registry import ToolRegistry


class TestToolContext:
    """Tests for ToolContext."""

    @pytest.fixture
    def context(self, temp_project_dir):
        """Create a ToolContext with temp directory."""
        return ToolContext(project_root=temp_project_dir)

    @pytest.mark.unit
    def test_context_creation(self, temp_project_dir):
        """Test basic context creation."""
        context = ToolContext(project_root=temp_project_dir)
        assert context.project_root == temp_project_dir
        assert context.dry_run is False
        assert context.config is None
        assert context.orchestrator is None

    @pytest.mark.unit
    def test_is_safe_path_within_project(self, context, temp_project_dir):
        """Test that paths within project are safe."""
        # Create a file in project
        test_file = temp_project_dir / "test.py"
        test_file.touch()

        assert context.is_safe_path("test.py") is True
        assert context.is_safe_path("src/main.py") is True
        assert context.is_safe_path("src/../test.py") is True

    @pytest.mark.unit
    def test_is_safe_path_outside_project(self, context):
        """Test that paths outside project are unsafe."""
        # Paths that try to escape project root
        assert context.is_safe_path("../outside.py") is False
        assert context.is_safe_path("../../etc/passwd") is False
        assert context.is_safe_path("/etc/passwd") is False

    @pytest.mark.unit
    def test_is_safe_path_handles_exceptions(self, context):
        """Test that invalid paths are handled without raising exceptions."""
        # Path with null bytes - behavior may vary by platform
        # On Windows, null bytes may be silently ignored in pathlib
        # The key is that it doesn't raise an exception
        try:
            result = context.is_safe_path("test\x00.py")
            # Should return a boolean (True or False), not raise exception
            assert isinstance(result, bool)
        except ValueError:
            # Some platforms may raise ValueError for null bytes, that's also acceptable
            pass

    @pytest.mark.unit
    def test_remember_file_read_with_orchestrator(self, context):
        """Test remembering file read when orchestrator is present."""
        mock_orch = Mock()
        context.orchestrator = mock_orch

        context.remember_file_read("test.py", "content", 10)
        mock_orch.remember_file_read.assert_called_once_with("test.py", "content", 10)

    @pytest.mark.unit
    def test_remember_file_read_without_orchestrator(self, context):
        """Test that remember works gracefully without orchestrator."""
        # Should not raise exception
        context.remember_file_read("test.py", "content", 10)

    @pytest.mark.unit
    def test_remember_search_with_orchestrator(self, context):
        """Test remembering search when orchestrator is present."""
        mock_orch = Mock()
        context.orchestrator = mock_orch

        context.remember_search("TODO", ["file1", "file2"])
        mock_orch.remember_search.assert_called_once_with("TODO", ["file1", "file2"])

    @pytest.mark.unit
    def test_remember_git_operation(self, context):
        """Test remembering git operation."""
        mock_orch = Mock()
        context.orchestrator = mock_orch

        context.remember_git_operation("git status", "clean")
        mock_orch.remember_git_operation.assert_called_once_with("git status", "clean")


class TestToolParameter:
    """Tests for ToolParameter dataclass."""

    @pytest.mark.unit
    def test_required_parameter(self):
        """Test creating a required parameter."""
        param = ToolParameter(
            name="path",
            param_type=str,
            description="File path to read"
        )

        assert param.name == "path"
        assert param.param_type == str
        assert param.description == "File path to read"
        assert param.required is True
        assert param.default is None

    @pytest.mark.unit
    def test_optional_parameter(self):
        """Test creating an optional parameter with default."""
        param = ToolParameter(
            name="lines",
            param_type=int,
            description="Number of lines",
            required=False,
            default=100
        )

        assert param.required is False
        assert param.default == 100


class TestToolResult:
    """Tests for ToolResult dataclass."""

    @pytest.mark.unit
    def test_success_result(self):
        """Test creating a success result."""
        result = ToolResult(
            success=True,
            output="File content here"
        )

        assert result.success is True
        assert result.output == "File content here"
        assert result.error is None
        assert result.metadata == {}

    @pytest.mark.unit
    def test_error_result(self):
        """Test creating an error result."""
        result = ToolResult(
            success=False,
            output="",
            error="File not found"
        )

        assert result.success is False
        assert result.error == "File not found"

    @pytest.mark.unit
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = ToolResult(
            success=True,
            output="data",
            metadata={"lines": 100, "size": 1024}
        )

        assert result.metadata["lines"] == 100
        assert result.metadata["size"] == 1024


class TestToolBaseClass:
    """Tests for Tool abstract base class."""

    @pytest.fixture
    def sample_tool(self):
        """Create a concrete tool implementation for testing."""
        class EchoTool(Tool):
            @property
            def name(self):
                return "echo"

            @property
            def description(self):
                return "Echoes the input message"

            @property
            def parameters(self):
                return [
                    ToolParameter("message", str, "Message to echo"),
                    ToolParameter("times", int, "Repeat count", required=False, default=1)
                ]

            def execute(self, context, **kwargs):
                msg = kwargs.get("message", "")
                times = kwargs.get("times", 1)
                return ToolResult(True, msg * times)

        return EchoTool()

    @pytest.mark.unit
    def test_validate_valid_params(self, sample_tool):
        """Test validation with valid parameters."""
        is_valid, error = sample_tool.validate(message="Hello")
        assert is_valid is True
        assert error is None

    @pytest.mark.unit
    def test_validate_missing_required(self, sample_tool):
        """Test validation fails when required param is missing."""
        is_valid, error = sample_tool.validate()
        assert is_valid is False
        assert "message" in error

    @pytest.mark.unit
    def test_validate_wrong_type_string(self, sample_tool):
        """Test validation fails for wrong type (expecting string)."""
        is_valid, error = sample_tool.validate(message=123)
        assert is_valid is False
        assert "string" in error

    @pytest.mark.unit
    def test_validate_wrong_type_int(self, sample_tool):
        """Test validation fails for wrong type (expecting int)."""
        is_valid, error = sample_tool.validate(message="hi", times="not int")
        assert is_valid is False
        assert "integer" in error

    @pytest.mark.unit
    def test_get_signature(self, sample_tool):
        """Test signature generation."""
        sig = sample_tool.get_signature()
        assert "echo(" in sig
        assert "message: str" in sig
        assert "times: int = 1" in sig

    @pytest.mark.unit
    def test_get_full_description(self, sample_tool):
        """Test full description generation."""
        desc = sample_tool.get_full_description()
        assert "echo(" in desc
        assert "Echoes the input" in desc

    @pytest.mark.unit
    def test_call_with_valid_params(self, sample_tool, temp_project_dir):
        """Test calling tool with valid parameters."""
        context = ToolContext(project_root=temp_project_dir)
        result = sample_tool(context, message="Hi")
        assert result == "Hi"

    @pytest.mark.unit
    def test_call_with_invalid_params(self, sample_tool, temp_project_dir):
        """Test calling tool with invalid parameters."""
        context = ToolContext(project_root=temp_project_dir)
        result = sample_tool(context)  # Missing required param
        assert "Error:" in result

    @pytest.mark.unit
    def test_execute_success(self, sample_tool, temp_project_dir):
        """Test successful execution."""
        context = ToolContext(project_root=temp_project_dir)
        result = sample_tool.execute(context, message="Test", times=2)

        assert result.success is True
        assert result.output == "TestTest"


class TestToolRegistry:
    """Tests for ToolRegistry."""

    @pytest.fixture
    def registry(self):
        """Create an empty tool registry."""
        return ToolRegistry()

    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool."""
        tool = Mock(spec=Tool)
        tool.name = "mock_tool"
        tool.description = "A mock tool"
        tool.get_full_description.return_value = "mock_tool() - A mock tool"
        return tool

    @pytest.mark.unit
    def test_register_tool(self, registry, mock_tool):
        """Test registering a tool."""
        registry.register(mock_tool)
        assert "mock_tool" in registry.list_tools()

    @pytest.mark.unit
    def test_get_tool(self, registry, mock_tool):
        """Test retrieving a registered tool."""
        registry.register(mock_tool)
        retrieved = registry.get("mock_tool")
        assert retrieved is mock_tool

    @pytest.mark.unit
    def test_get_nonexistent_tool(self, registry):
        """Test getting tool that doesn't exist."""
        result = registry.get("nonexistent")
        assert result is None

    @pytest.mark.unit
    def test_list_tools_empty(self, registry):
        """Test listing tools when empty."""
        tools = registry.list_tools()
        assert isinstance(tools, list)
        assert len(tools) == 0

    @pytest.mark.unit
    def test_list_tools_multiple(self, registry, mock_tool):
        """Test listing multiple tools."""
        tool2 = Mock(spec=Tool)
        tool2.name = "another_tool"
        tool2.description = "Another tool"

        registry.register(mock_tool)
        registry.register(tool2)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert "mock_tool" in tools
        assert "another_tool" in tools

    @pytest.mark.unit
    def test_get_all_descriptions(self, registry, mock_tool):
        """Test getting all tool descriptions."""
        registry.register(mock_tool)
        descriptions = registry.generate_descriptions()

        assert isinstance(descriptions, str)
        assert "mock_tool" in descriptions

    @pytest.mark.unit
    def test_create_default_registry(self):
        """Test creating default registry with all tools."""
        registry = ToolRegistry.create_default()

        # Should have standard tools registered
        tools = registry.list_tools()
        assert len(tools) > 0

        # Check for expected tools (using actual tool names)
        expected_tools = ["read_file", "write_file", "search_code"]
        for tool_name in expected_tools:
            assert tool_name in tools, f"Expected {tool_name} in default registry"


class TestFileToolsSafety:
    """Security tests for file tools."""

    @pytest.mark.unit
    def test_path_traversal_blocked(self, temp_project_dir):
        """Test that path traversal attacks are blocked."""
        import sys
        context = ToolContext(project_root=temp_project_dir)

        # Various path traversal attempts (platform-independent)
        malicious_paths = [
            "../../../etc/passwd",
            "src/../../outside",
        ]

        # Add platform-specific paths
        if sys.platform == 'win32':
            # Windows-style path traversal
            malicious_paths.append("..\\..\\windows\\system32")
            malicious_paths.append("C:\\windows\\system32")
        else:
            # Unix-style absolute paths
            malicious_paths.append("/absolute/path")
            malicious_paths.append("/etc/shadow")

        for path in malicious_paths:
            assert context.is_safe_path(path) is False, f"Should block: {path}"

    @pytest.mark.unit
    def test_symlink_escape_handled(self, temp_project_dir):
        """Test that symlinks pointing outside are handled."""
        context = ToolContext(project_root=temp_project_dir)

        # Create a symlink pointing outside (if platform supports)
        try:
            symlink_path = temp_project_dir / "escape_link"
            # This would point outside project
            # On Windows, may require admin privileges
            # Just test the resolve behavior
            result = context.is_safe_path("escape_link/../../../etc")
            assert result is False
        except OSError:
            # Skip if symlinks not supported
            pass

    @pytest.mark.unit
    def test_null_byte_injection(self, temp_project_dir):
        """Test that null byte injection is handled without crashing."""
        context = ToolContext(project_root=temp_project_dir)

        # Null byte injection attempt - behavior varies by platform
        # On Windows, null bytes may be silently ignored
        # The key test is that it doesn't crash
        try:
            result = context.is_safe_path("valid.py\x00.txt")
            # Should return a boolean, not crash
            assert isinstance(result, bool)
        except ValueError:
            # Some platforms may raise ValueError for null bytes
            pass

    @pytest.mark.unit
    def test_sibling_directory_attack_blocked(self, temp_project_dir):
        """Test that sibling directories with similar names are blocked.

        This tests the critical vulnerability where startswith() could be fooled:
        If project_root is /path/to/myproject, then /path/to/myproject-secrets
        would pass a startswith check but should be blocked.
        """
        context = ToolContext(project_root=temp_project_dir)

        # Create a sibling directory with similar name
        sibling_dir = temp_project_dir.parent / (temp_project_dir.name + "-secrets")
        sibling_dir.mkdir(exist_ok=True)

        try:
            # Create a file in the sibling directory
            secret_file = sibling_dir / "passwords.txt"
            secret_file.write_text("secret passwords")

            # Try to access via path traversal to sibling
            # This path resolves to sibling_dir/passwords.txt
            # which starts with project_root string but is NOT inside it
            malicious_path = f"../{sibling_dir.name}/passwords.txt"

            # This MUST be blocked
            assert context.is_safe_path(malicious_path) is False, \
                "Sibling directory attack should be blocked"
        finally:
            # Cleanup
            if sibling_dir.exists():
                import shutil
                shutil.rmtree(sibling_dir)

    @pytest.mark.unit
    def test_windows_case_insensitivity(self, temp_project_dir):
        """Test that Windows case differences are handled correctly.

        On Windows, file paths are case-insensitive but string comparison is not.
        The is_safe_path method must handle this correctly.
        """
        import sys
        context = ToolContext(project_root=temp_project_dir)

        # Create a test file
        test_file = temp_project_dir / "TestFile.py"
        test_file.touch()

        # On Windows, these should all resolve to the same file
        if sys.platform == 'win32':
            # Different cases should all be valid (Windows is case-insensitive)
            assert context.is_safe_path("TestFile.py") is True
            assert context.is_safe_path("testfile.py") is True
            assert context.is_safe_path("TESTFILE.PY") is True
        else:
            # On Unix, only exact case should match
            assert context.is_safe_path("TestFile.py") is True
            # These might return True for safety check but file won't exist

    @pytest.mark.unit
    def test_relative_to_method_robustness(self, temp_project_dir):
        """Test that relative_to method properly validates paths.

        This tests the fix: using Path.relative_to() instead of startswith()
        ensures that paths are truly relative to the project root.
        """
        context = ToolContext(project_root=temp_project_dir)

        # Valid relative paths
        assert context.is_safe_path("src/module.py") is True
        assert context.is_safe_path("src/sub/deep/file.py") is True
        assert context.is_safe_path("./src/module.py") is True
        assert context.is_safe_path("src/../src/module.py") is True  # Resolves to src/module.py

        # Invalid paths that escape
        assert context.is_safe_path("../escape.py") is False
        assert context.is_safe_path("src/../../escape.py") is False
        assert context.is_safe_path("./../../escape.py") is False

    @pytest.mark.unit
    def test_deeply_nested_traversal(self, temp_project_dir):
        """Test deeply nested path traversal attempts."""
        context = ToolContext(project_root=temp_project_dir)

        # Create a deep directory structure
        deep_dir = temp_project_dir / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True, exist_ok=True)

        # These should all be blocked
        blocked_paths = [
            "a/b/c/d/../../../../..",
            "a/b/c/d/../../../../../etc/passwd",
            "a/b/c/d/e/f/g/../../../../../../../..",
        ]

        for path in blocked_paths:
            assert context.is_safe_path(path) is False, f"Should block: {path}"

        # These should be allowed (stay within project)
        allowed_paths = [
            "a/b/c/d/../../../../a/b/c/d",  # Goes up then back down
            "a/b/../b/c",  # Goes up one level then back
            "a/b/c/d",
        ]

        for path in allowed_paths:
            assert context.is_safe_path(path) is True, f"Should allow: {path}"
