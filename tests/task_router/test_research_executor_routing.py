"""
Tests for ResearchExecutor subtype routing.

Verifies that the subclassifier result is correctly used to route
queries to codebase vs general research execution paths.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from scrappy.task_router.classifier import ClassifiedTask, TaskType
from scrappy.task_router.strategies.research_executor import ResearchExecutor
from scrappy.task_router.strategies.research_subtype import ResearchSubtype
from scrappy.task_router.strategies.research_subclassifier import ResearchSubclassifier


class TestResearchExecutorSubtypeRouting:
    """Tests that ResearchExecutor respects subclassifier results."""

    def _create_mock_orchestrator(self):
        """Create a mock orchestrator for testing."""
        orchestrator = Mock()
        orchestrator.context = None

        # Mock providers
        providers = Mock()
        providers.list_available.return_value = ['cerebras']
        providers.get_provider.return_value = Mock()
        orchestrator.providers = providers

        # Mock delegate to return a response
        response = Mock()
        response.content = "Test response"
        response.tokens_used = 100
        orchestrator.delegate.return_value = response

        return orchestrator

    def _create_research_task(self, query: str) -> ClassifiedTask:
        """Create a ClassifiedTask for testing."""
        return ClassifiedTask(
            original_input=query,
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Test task",
            complexity_score=2,
        )

    def test_codebase_query_uses_codebase_execution_path(self):
        """
        Verify 'this codebase' queries use codebase execution path.

        This is a regression test for the reported bug where
        'how would we add rag to this codebase?' hit GENERAL instead of CODEBASE.
        """
        orchestrator = self._create_mock_orchestrator()

        # Track which execution path was taken
        execution_path = []

        # Create executor with mocked subclassifier that we can verify
        executor = ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
        )

        # Patch the execution methods to track which one is called
        original_codebase = executor._execute_codebase_research
        original_general = executor._execute_general_research

        def track_codebase(*args, **kwargs):
            execution_path.append("CODEBASE")
            return original_codebase(*args, **kwargs)

        def track_general(*args, **kwargs):
            execution_path.append("GENERAL")
            return original_general(*args, **kwargs)

        executor._execute_codebase_research = track_codebase
        executor._execute_general_research = track_general

        # Execute the problematic query
        task = self._create_research_task("how would we add rag to this codebase?")
        executor.execute(task)

        # Verify CODEBASE path was taken
        assert "CODEBASE" in execution_path, (
            f"Expected CODEBASE execution path, but got: {execution_path}"
        )
        assert "GENERAL" not in execution_path, (
            f"GENERAL path should not have been taken: {execution_path}"
        )

    def test_general_query_uses_general_execution_path(self):
        """Verify general knowledge queries use general execution path."""
        orchestrator = self._create_mock_orchestrator()

        execution_path = []

        executor = ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
        )

        original_codebase = executor._execute_codebase_research
        original_general = executor._execute_general_research

        def track_codebase(*args, **kwargs):
            execution_path.append("CODEBASE")
            return original_codebase(*args, **kwargs)

        def track_general(*args, **kwargs):
            execution_path.append("GENERAL")
            return original_general(*args, **kwargs)

        executor._execute_codebase_research = track_codebase
        executor._execute_general_research = track_general

        # Execute a general knowledge query
        task = self._create_research_task("who invented Python?")
        executor.execute(task)

        # Verify GENERAL path was taken
        assert "GENERAL" in execution_path, (
            f"Expected GENERAL execution path, but got: {execution_path}"
        )

    def test_subclassifier_receives_original_input(self):
        """Verify the subclassifier receives the unmodified original_input."""
        orchestrator = self._create_mock_orchestrator()

        # Create a mock subclassifier to capture the input
        mock_subclassifier = Mock()
        mock_subclassifier.classify.return_value = ResearchSubtype.CODEBASE

        executor = ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
            subclassifier=mock_subclassifier,
        )

        query = "how would we add rag to this codebase?"
        task = self._create_research_task(query)
        executor.execute(task)

        # Verify subclassifier was called with the exact original input
        mock_subclassifier.classify.assert_called_once()
        call_args = mock_subclassifier.classify.call_args
        assert call_args[0][0] == query, (
            f"Expected query '{query}', got '{call_args[0][0]}'"
        )

    def test_subclassifier_result_determines_execution_path(self):
        """Verify the subclassifier result is used to determine execution path."""
        orchestrator = self._create_mock_orchestrator()

        # Test with subclassifier returning CODEBASE
        mock_subclassifier = Mock()
        mock_subclassifier.classify.return_value = ResearchSubtype.CODEBASE

        executor = ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
            subclassifier=mock_subclassifier,
        )

        execution_path = []
        original_codebase = executor._execute_codebase_research

        def track_codebase(*args, **kwargs):
            execution_path.append("CODEBASE")
            return original_codebase(*args, **kwargs)

        executor._execute_codebase_research = track_codebase

        task = self._create_research_task("any query")
        executor.execute(task)

        assert "CODEBASE" in execution_path

    def test_metadata_contains_correct_subtype(self):
        """Verify execution result metadata contains the correct research_subtype."""
        orchestrator = self._create_mock_orchestrator()

        executor = ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
        )

        # Codebase query
        task = self._create_research_task("how would we add rag to this codebase?")
        result = executor.execute(task)

        assert result.metadata.get("research_subtype") == "codebase", (
            f"Expected 'codebase', got '{result.metadata.get('research_subtype')}'"
        )

        # General query
        task = self._create_research_task("who invented Python?")
        result = executor.execute(task)

        assert result.metadata.get("research_subtype") == "general", (
            f"Expected 'general', got '{result.metadata.get('research_subtype')}'"
        )


class TestResearchExecutorEdgeCases:
    """Edge case tests for research executor routing."""

    def _create_mock_orchestrator(self):
        """Create a mock orchestrator for testing."""
        orchestrator = Mock()
        orchestrator.context = None

        providers = Mock()
        providers.list_available.return_value = ['cerebras']
        providers.get_provider.return_value = Mock()
        orchestrator.providers = providers

        response = Mock()
        response.content = "Test response"
        response.tokens_used = 100
        orchestrator.delegate.return_value = response

        return orchestrator

    def _create_research_task(self, query: str) -> ClassifiedTask:
        """Create a ClassifiedTask for testing."""
        return ClassifiedTask(
            original_input=query,
            task_type=TaskType.RESEARCH,
            confidence=0.9,
            reasoning="Test task",
            complexity_score=2,
        )

    def test_subclassifier_exception_does_not_crash(self):
        """Verify executor handles subclassifier exceptions gracefully."""
        orchestrator = self._create_mock_orchestrator()

        mock_subclassifier = Mock()
        mock_subclassifier.classify.side_effect = Exception("Subclassifier error")

        executor = ResearchExecutor(
            orchestrator=orchestrator,
            preferred_provider="cerebras",
            subclassifier=mock_subclassifier,
        )

        task = self._create_research_task("test query")
        result = executor.execute(task)

        # Should not crash, should return error result
        assert result.success is False
        assert "Subclassifier error" in result.error or "failed" in result.error.lower()
