"""
Tests for ResearchPromptBuilder used by smart_query.
"""

import pytest
from src.task_router.protocols import QueryIntent, IntentResult
from src.cli.research_handlers.base import ClassificationResult


class TestResearchPromptBuilder:
    """Tests for the ResearchPromptBuilder class."""

    def test_builds_prompt_without_research_results(self):
        """ResearchPromptBuilder handles empty research results."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        classification = ClassificationResult(
            query="What is this project?",
            intent_result=IntentResult(
                intent=QueryIntent.ARCHITECTURE,
                confidence=0.7,
                metadata={}
            ),
            entities={},
            keywords=['project']
        )

        builder = ResearchPromptBuilder()
        prompt = builder.build(
            query="What is this project?",
            classification=classification,
            research_results=[]
        )

        assert "What is this project?" in prompt
        # Should not contain "Research Results" section
        assert "Research Results" not in prompt or "provide a helpful answer" in prompt.lower()

    def test_includes_project_summary_when_provided(self):
        """ResearchPromptBuilder includes project summary at the start."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        classification = ClassificationResult(
            query="How does auth work?",
            intent_result=IntentResult(
                intent=QueryIntent.CODE_EXPLANATION,
                confidence=0.9,
                metadata={}
            ),
            entities={},
            keywords=['auth']
        )

        builder = ResearchPromptBuilder()
        prompt = builder.build(
            query="How does auth work?",
            classification=classification,
            research_results=["Code snippet here"],
            project_summary="This is a Python CLI tool for code analysis."
        )

        assert "Python CLI tool" in prompt

    def test_separates_multiple_research_results(self):
        """ResearchPromptBuilder properly separates multiple results."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        classification = ClassificationResult(
            query="Show me tests",
            intent_result=IntentResult(
                intent=QueryIntent.TESTING,
                confidence=0.9,
                metadata={}
            ),
            entities={},
            keywords=['tests']
        )

        research_results = [
            "Test files:\ntests/test_agent.py",
            "Test patterns:\ndef test_something():",
            "Coverage report:\n80% coverage"
        ]

        builder = ResearchPromptBuilder()
        prompt = builder.build(
            query="Show me tests",
            classification=classification,
            research_results=research_results
        )

        # All results should be present
        assert "test_agent.py" in prompt
        assert "test_something" in prompt
        assert "80%" in prompt

    def test_get_system_prompt(self):
        """ResearchPromptBuilder provides appropriate system prompt."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        builder = ResearchPromptBuilder()
        system_prompt = builder.get_system_prompt()

        assert "AI assistant" in system_prompt
        assert "codebase" in system_prompt.lower() or "research" in system_prompt.lower()

    def test_handles_empty_entities(self):
        """ResearchPromptBuilder handles classification with no entities."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        classification = ClassificationResult(
            query="What is this?",
            intent_result=IntentResult(
                intent=QueryIntent.ARCHITECTURE,
                confidence=0.6,
                metadata={}
            ),
            entities={},
            keywords=[]
        )

        builder = ResearchPromptBuilder()
        # Should not raise
        prompt = builder.build(
            query="What is this?",
            classification=classification,
            research_results=[]
        )

        assert "What is this?" in prompt


class TestResearchPromptBuilderEdgeCases:
    """Edge case tests for ResearchPromptBuilder."""

    def test_handles_very_long_research_results(self):
        """ResearchPromptBuilder handles large research results without issues."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        classification = ClassificationResult(
            query="Show everything",
            intent_result=IntentResult(
                intent=QueryIntent.FILE_STRUCTURE,
                confidence=0.9,
                metadata={}
            ),
            entities={},
            keywords=[]
        )

        # Create a large result
        large_result = "line\n" * 1000

        builder = ResearchPromptBuilder()
        prompt = builder.build(
            query="Show everything",
            classification=classification,
            research_results=[large_result]
        )

        # Should include the content (may be truncated)
        assert len(prompt) > 100
        assert "Show everything" in prompt

    def test_multiple_secondary_intents(self):
        """ResearchPromptBuilder handles classification with secondary intents."""
        from src.cli.research_prompt_builder import ResearchPromptBuilder

        classification = ClassificationResult(
            query="How does the auth system work and where is it tested?",
            intent_result=IntentResult(
                intent=QueryIntent.CODE_EXPLANATION,
                confidence=0.8,
                metadata={'secondary_intents': ['TESTING', 'SECURITY']}
            ),
            entities={'function_name': ['auth']},
            keywords=['auth', 'system', 'tested']
        )

        builder = ResearchPromptBuilder()
        prompt = builder.build(
            query="How does the auth system work and where is it tested?",
            classification=classification,
            research_results=["Auth code here"]
        )

        # Primary intent should be included
        assert "CODE_EXPLANATION" in prompt or "code_explanation" in prompt
