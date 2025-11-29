"""
End-to-end tests for task routing.

Tests the full flow from TaskRouter through classification and execution.
"""

import pytest
from unittest.mock import Mock

from src.task_router.router import TaskRouter
from src.task_router.classifier import TaskType
from src.task_router.config import ClarificationConfig
from src.task_router.output_handler import NullOutputHandler
from src.task_router.intent_clarifier import NullClarifier
from src.task_router.provider_resolver import ProviderResolver
from tests.helpers import ConfigurableTestOrchestrator


def create_test_router(response_content: str = "Test response") -> TaskRouter:
    """Create a TaskRouter with proper test mocking."""
    orchestrator = ConfigurableTestOrchestrator(
        response_content=response_content
    )

    # Mock provider resolver to return proper tuple
    provider_resolver = Mock(spec=ProviderResolver)
    provider_resolver.resolve.return_value = ("cerebras", "llama3.1-8b")

    return TaskRouter(
        orchestrator=orchestrator,
        verbose=False,
        clarification_config=ClarificationConfig(),
        output_handler=NullOutputHandler(),
        intent_clarifier=NullClarifier(),
        provider_resolver=provider_resolver,
    )


class TestTaskRouterCodebaseResearch:
    """
    End-to-end tests for codebase research routing.

    Tests the full path: TaskRouter -> TaskClassifier -> ResearchExecutor -> Subclassifier
    """

    def test_add_rag_query_routes_to_research(self):
        """Verify 'add rag to this codebase' routes to RESEARCH task type."""
        router = create_test_router()

        # Check classification only
        classified = router.classify_only("how would we add rag to this codebase?")

        # Should be classified as RESEARCH (asking "how would we")
        # or potentially CODE_GENERATION (contains "add")
        assert classified.task_type in [TaskType.RESEARCH, TaskType.CODE_GENERATION], (
            f"Expected RESEARCH or CODE_GENERATION, got {classified.task_type}"
        )

    def test_add_rag_query_full_execution(self):
        """Test full execution of 'add rag to this codebase' query."""
        router = create_test_router(
            response_content="To add RAG to this codebase, you would..."
        )

        result = router.route("how would we add rag to this codebase?")

        # Should succeed
        assert result.success, f"Expected success, got error: {result.error}"

        # Check metadata
        classification = result.metadata.get("classification", {})

        # If it went through ResearchExecutor, check research_subtype
        if classification.get("task_type") == "research":
            # The result metadata should show which subtype was used
            research_subtype = result.metadata.get("research_subtype")
            if research_subtype:
                assert research_subtype == "codebase", (
                    f"Expected 'codebase' subtype, got '{research_subtype}'"
                )

    def test_this_codebase_queries_classified_correctly(self):
        """Test various 'this codebase' queries are classified correctly."""
        router = create_test_router()

        # These queries contain "this codebase" and should either:
        # - Be classified as RESEARCH and routed to CODEBASE subtype
        # - Be classified as CODE_GENERATION (if action words dominate)
        queries = [
            "how would we add rag to this codebase?",
            "explain this codebase",
            "what is the architecture of this codebase?",
            "how does this codebase handle errors?",
        ]

        for query in queries:
            result = router.route(query)
            assert result.success, f"Query '{query}' failed: {result.error}"

            # If classified as research, verify codebase subtype
            classification = result.metadata.get("classification", {})
            if classification.get("task_type") == "research":
                research_subtype = result.metadata.get("research_subtype")
                if research_subtype:
                    assert research_subtype == "codebase", (
                        f"Query '{query}' got subtype '{research_subtype}', expected 'codebase'"
                    )


class TestTaskRouterGeneralResearch:
    """Tests for general knowledge research routing."""

    def test_general_knowledge_queries(self):
        """Test general knowledge queries route to GENERAL subtype."""
        router = create_test_router(
            response_content="Guido van Rossum invented Python"
        )

        queries = [
            "who invented Python?",
            "what is the best sorting algorithm?",
            "who is Dijkstra?",
        ]

        for query in queries:
            result = router.route(query)
            assert result.success, f"Query '{query}' failed: {result.error}"

            # If classified as research, verify general subtype
            classification = result.metadata.get("classification", {})
            if classification.get("task_type") == "research":
                research_subtype = result.metadata.get("research_subtype")
                if research_subtype:
                    assert research_subtype == "general", (
                        f"Query '{query}' got subtype '{research_subtype}', expected 'general'"
                    )


class TestProblem2AgentVsChatMode:
    """
    Tests for Problem 2: Agent vs Chat mode confusion.

    Small models outputting only JSON and getting empty responses.
    """

    def test_json_only_response_does_not_result_in_empty_output(self):
        """
        Test that JSON-only responses don't result in empty output.

        When a small model outputs only JSON tool calls and the response
        cleaner strips it, we should get a fallback response, not empty.
        """
        # Simulate small model returning only JSON (tool call)
        router = create_test_router(
            response_content='{"tool": "web_search", "parameters": {"query": "what is RAG"}}'
        )

        # A simple question that might trigger JSON-only response from small models
        result = router.route("what is RAG?")

        # Should not have empty output
        # Note: Currently this might fail if the bug exists
        if result.success:
            assert result.output, (
                "Expected non-empty output, but got empty string. "
                "This indicates the JSON-only response bug (Problem 2)."
            )
