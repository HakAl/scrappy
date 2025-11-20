import pytest
from unittest.mock import MagicMock, ANY
from typing import List, Dict, Any

# ==========================================
# 1. MOCKS & STUBS (Replace external imports)
# ==========================================

# Mocking constants that would usually come from ..config.defaults
TRUNCATE_RESEARCH_LARGE = 100


# Mocking Enums/Classes that would usually come from .base or ..io_interface
class QueryIntent:
    BUG_INVESTIGATION = "BUG_INVESTIGATION"


class ClassificationResult:
    def __init__(self, entities: Dict[str, List[str]]):
        self.entities = entities


class CLIIOProtocol:
    """Mock for type hinting."""

    def echo(self, msg: str): pass


class BaseResearchHandler:
    """Mock base class with the specific method used by the child."""

    def _safe_tool_call(self, func, *args, **kwargs):
        # This default behavior is overridden by mocks in the tests
        return True, "Default Mock Result"

    @property
    def intent(self):
        raise NotImplementedError


# ==========================================
# 2. CLASS UNDER TEST
# ==========================================

# We paste the class here, but we remove the relative imports
# because we defined the dependencies above.

class BugInvestigationHandler(BaseResearchHandler):
    """Handler for BUG_INVESTIGATION intent - searches for error patterns."""

    @property
    def intent(self) -> QueryIntent:
        """The intent this handler processes."""
        return QueryIntent.BUG_INVESTIGATION

    def execute(
            self,
            agent: Any,
            classification: ClassificationResult,
            io: CLIIOProtocol
    ) -> List[str]:
        """
        Execute bug investigation research.
        """
        results = []

        # Search for error types mentioned
        for error_type in classification.entities.get('error_type', [])[:3]:
            io.echo(f"  - Searching for '{error_type}'...")
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                error_type,
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Error '{error_type}' occurrences:\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                )

        # Check for error handling patterns if no specific error type
        if not classification.entities.get('error_type'):
            io.echo("  - Searching for error handling...")
            success, result = self._safe_tool_call(
                agent._tool_search_code,
                "except|raise|Error",
                "*.py"
            )
            if success and "No matches" not in result:
                results.append(
                    f"Error handling patterns:\n{result[:TRUNCATE_RESEARCH_LARGE]}"
                )

        return results


# ==========================================
# 3. TESTS
# ==========================================

@pytest.fixture
def handler():
    """Creates an instance of the handler for each test."""
    return BugInvestigationHandler()


@pytest.fixture
def mock_agent():
    """Mocks the agent and its search tool."""
    agent = MagicMock()
    # Default behavior: return a simple string
    agent._tool_search_code = MagicMock(return_value="Default Code Match")
    return agent


@pytest.fixture
def mock_io():
    """Mocks the IO interface."""
    return MagicMock(spec=CLIIOProtocol)


class TestBugInvestigationHandler:

    def test_intent_property(self, handler):
        """Verify the handler identifies with the correct intent."""
        assert handler.intent == QueryIntent.BUG_INVESTIGATION

    def test_execute_with_specific_error_types(self, handler, mock_agent, mock_io):
        """
        Test that specific 'error_type' entities trigger specific code searches.
        """
        # Setup input with two specific errors
        classification = ClassificationResult(entities={'error_type': ['ValueError', 'KeyError']})

        # Mock _safe_tool_call to return specific successes for each call
        handler._safe_tool_call = MagicMock(side_effect=[
            (True, "Found ValueError code..."),
            (True, "Found KeyError code...")
        ])

        # Execute
        results = handler.execute(mock_agent, classification, mock_io)

        # Verification
        assert len(results) == 2
        assert "Error 'ValueError' occurrences" in results[0]
        assert "Error 'KeyError' occurrences" in results[1]

        # Verify IO feedback
        mock_io.echo.assert_any_call("  - Searching for 'ValueError'...")
        mock_io.echo.assert_any_call("  - Searching for 'KeyError'...")

        # Verify the tool was called with the correct arguments
        assert handler._safe_tool_call.call_count == 2
        # Check first call args
        handler._safe_tool_call.assert_any_call(mock_agent._tool_search_code, "ValueError", "*.py")

    def test_execute_truncates_results(self, handler, mock_agent, mock_io):
        """
        Test that long search results are truncated using the TRUNCATE_RESEARCH_LARGE constant.
        """
        classification = ClassificationResult(entities={'error_type': ['LongError']})

        # Create a result longer than our mocked limit (100 chars)
        long_output = "A" * 200
        handler._safe_tool_call = MagicMock(return_value=(True, long_output))

        results = handler.execute(mock_agent, classification, mock_io)

        assert len(results) == 1
        # Extract the content part of the result string
        content = results[0].split("\n")[1]
        assert len(content) == TRUNCATE_RESEARCH_LARGE
        assert content == "A" * TRUNCATE_RESEARCH_LARGE

    def test_execute_fallback_general_handling(self, handler, mock_agent, mock_io):
        """
        Test that if no 'error_type' is provided, it searches for general error handling patterns.
        """
        # Setup: Empty entities
        classification = ClassificationResult(entities={})

        handler._safe_tool_call = MagicMock(return_value=(True, "try: except: code"))

        # Execute
        results = handler.execute(mock_agent, classification, mock_io)

        # Verification
        assert len(results) == 1
        assert "Error handling patterns" in results[0]

        mock_io.echo.assert_called_with("  - Searching for error handling...")

        # Verify specific regex search was used
        handler._safe_tool_call.assert_called_once_with(
            mock_agent._tool_search_code,
            "except|raise|Error",
            "*.py"
        )

    def test_execute_limits_entities_to_three(self, handler, mock_agent, mock_io):
        """
        Test that the handler processes a maximum of 3 error types (performance guard).
        """
        classification = ClassificationResult(entities={
            'error_type': ['E1', 'E2', 'E3', 'E4']
        })

        handler._safe_tool_call = MagicMock(return_value=(True, "matches"))

        handler.execute(mock_agent, classification, mock_io)

        # Should only call 3 times despite 4 entities
        assert handler._safe_tool_call.call_count == 3

        # Extract the search terms from the calls to verify which ones were run
        calls = [args[0][1] for args in handler._safe_tool_call.call_args_list]
        assert calls == ['E1', 'E2', 'E3']

    def test_execute_no_matches_found(self, handler, mock_agent, mock_io):
        """
        Test that if 'No matches' is returned by the tool, nothing is added to results.
        """
        classification = ClassificationResult(entities={'error_type': ['GhostError']})

        # Tool returns success=True but content indicates no matches (grep style behavior)
        handler._safe_tool_call = MagicMock(return_value=(True, "No matches found"))

        results = handler.execute(mock_agent, classification, mock_io)

        assert len(results) == 0
        mock_io.echo.assert_called_with("  - Searching for 'GhostError'...")

    def test_execute_tool_call_failed(self, handler, mock_agent, mock_io):
        """
        Test that if _safe_tool_call returns success=False, the result is ignored.
        """
        classification = ClassificationResult(entities={})

        # Tool execution failed (e.g. syntax error in regex or tool crash)
        handler._safe_tool_call = MagicMock(return_value=(False, "Error executing tool"))

        results = handler.execute(mock_agent, classification, mock_io)

        assert len(results) == 0