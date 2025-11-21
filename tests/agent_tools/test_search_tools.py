import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock

from src.agent_tools.tools.search_tools import SearchCodeTool
from src.agent_tools.tools.base import ToolContext

# --- Fixtures ---

@pytest.fixture
def mock_context(tmp_path):
    """
    Create a tool context backed by a real temporary directory.
    This allows us to test file discovery and I/O.
    """
    context = MagicMock(spec=ToolContext)
    context.project_root = tmp_path
    # Allow all paths within the temp dir
    context.is_safe_path = Mock(return_value=True)
    context.remember_search = Mock()
    context.config = Mock()
    context.config.max_search_results = 10
    return context

@pytest.fixture
def tool():
    return SearchCodeTool()

# --- Unit Tests: Logic & Properties ---

class TestToolProperties:
    def test_metadata(self, tool):
        assert tool.name == "search_code"
        assert "search" in tool.description.lower()
        assert any(p.name == "pattern" for p in tool.parameters)

class TestInternalTextLogic:
    """Detailed unit tests for _search_text logic, specifically context handling."""

    def test_context_merging_overlapping(self, tool):
        """
        If matches are close enough, context lines should merge 
        without duplicating lines or inserting separators.
        """
        # Lines: 0, 1, 2(match), 3, 4(match), 5, 6
        # Context=1.
        # Match 1 (line 2) wants: 1, 2, 3
        # Match 2 (line 4) wants: 3, 4, 5
        # Result should be: 1, 2, 3, 4, 5 (no '---' separator)
        content = "0\n1\n2-match\n3\n4-match\n5\n6"
        
        results = tool._search_text(
            content, "match", use_regex=False, case_sensitive=False, 
            context_lines=1, rel_path=Path("test.py")
        )
        
        text_output = "\n".join(results)
        
        assert "test.py:2: " in text_output  # Line 1
        assert "test.py:3:>" in text_output  # Line 2 (match)
        assert "test.py:4: " in text_output  # Line 3 (shared context)
        assert "test.py:5:>" in text_output  # Line 4 (match)
        assert "test.py:6: " in text_output  # Line 5
        assert "---" not in text_output
        assert text_output.count("test.py:4: ") == 1  # Ensure line 3 appears once

# todo?
#     def test_context_separation(self, tool):
#         """If matches are far apart, they should be separated by '---'."""
#         # Lines: 0(match), 1, 2, 3, 4(match)
#         # Context=0.
#         content = "match1\n1\n2\n3\nmatch2"
#
#         results = tool._search_text(
#             content, "match", use_regex=False, case_sensitive=False,
#             context_lines=0, rel_path=Path("test.py")
#         )
#
#         assert len(results) == 3
#         assert "match1" in results[0]
#         assert results[1] == "---"
#         assert "match2" in results[2]



# --- Integration Tests: File System Execution ---

class TestSearchExecution:
    """Tests the full 'execute' flow with real files."""

# todo?
#     def test_finds_text_in_files(self, tool, mock_context):
#         """Should find patterns in multiple files respecting file glob."""
#         # Setup
#         (mock_context.project_root / "src").mkdir()
#         (mock_context.project_root / "src/main.py").write_text("def hello():\n    print('Hello World')")
#         (mock_context.project_root / "README.md").write_text("Hello World")
#         (mock_context.project_root / "other.txt").write_text("Hello World")
#
#         # Execute: Search for "World" in .py files only
#         result = tool.execute(mock_context, pattern="World", file_pattern="*.py")
#
#         assert result.success
#         assert "src/main.py" in result.output
#         assert "README.md" not in result.output
#         assert "matches" in result.metadata
#
#     def test_ast_search_types(self, tool, mock_context):
#         """Test various AST search types on a complex file."""
#         code = """
# import os
# from sys import path as sys_path
#
# class MyClass:
#     def my_method(self):
#         pass
#
# def my_func():
#     pass
# """
#         (mock_context.project_root / "test.py").write_text(code)
#
#         # 1. Test Function search
#         res_func = tool.execute(mock_context, pattern="my_func", search_type="function")
#         assert "[function] my_func" in res_func.output
#
#         # 2. Test Class search
#         res_class = tool.execute(mock_context, pattern="MyClass", search_type="class")
#         assert "[class] MyClass" in res_class.output
#
#         # 3. Test Method search
#         res_method = tool.execute(mock_context, pattern="my_method", search_type="method")
#         assert "[method] MyClass.my_method" in res_method.output
#
#         # 4. Test Import search (Standard)
#         res_imp = tool.execute(mock_context, pattern="os", search_type="import")
#         assert "[import] os" in res_imp.output
#
#         # 5. Test Import search (From/As)
#         res_imp_from = tool.execute(mock_context, pattern="path", search_type="import")
#         assert "sys_path" in res_imp_from.output or "path" in res_imp_from.output

    def test_ignore_directories(self, tool, mock_context):
        """Should ignore .git and __pycache__."""
        git_dir = mock_context.project_root / ".git"
        git_dir.mkdir()
        (git_dir / "dirty.py").write_text("secret = 'password'")

        result = tool.execute(mock_context, pattern="secret")
        
        assert result.success
        assert "No matches found" in result.output

# todo?
    # def test_regex_error_handling(self, tool, mock_context):
    #     """Should return a failed ToolResult if regex is invalid."""
    #     result = tool.execute(mock_context, pattern="[unclosed", use_regex=True)
    #
    #     assert not result.success
    #     assert "Invalid regex pattern" in result.error

    def test_result_truncation(self, tool, mock_context):
        """Should truncate results exceeding config.max_search_results."""
        # Create a file with 20 matches, limit is 10 (set in fixture)
        content = "\n".join([f"match {i}" for i in range(20)])
        (mock_context.project_root / "large.py").write_text(content)

        result = tool.execute(mock_context, pattern="match")
        
        assert result.success
        assert result.metadata["matches"] == 10
        assert "truncated" in result.metadata
        assert result.metadata["truncated"] is True
        assert "... [truncated" in result.output

    def test_context_lines_in_execution(self, tool, mock_context):
        """Verify context lines are rendered in the final output."""
        (mock_context.project_root / "ctx.py").write_text("A\nB\nTARGET\nC\nD")
        
        result = tool.execute(mock_context, pattern="TARGET", context_lines=1)
        
        assert "ctx.py:2:  B" in result.output # Context before
        assert "ctx.py:3:> TARGET" in result.output # Match
        assert "ctx.py:4:  C" in result.output # Context after

    def test_syntax_error_in_file(self, tool, mock_context):
        """AST search should gracefully skip files with syntax errors."""
        (mock_context.project_root / "broken.py").write_text("def broken(params") # Missing parenthesis
        
        # Should not raise exception
        result = tool.execute(mock_context, pattern="broken", search_type="function")
        
        assert result.success
        assert "No matches found" in result.output