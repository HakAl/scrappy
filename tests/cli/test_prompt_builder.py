"""
Tests for PromptBuilder used by smart_query.
"""

import pytest
from src.intent_classifier import QueryIntent, ClassificationResult, IntentMatch


class TestPromptBuilder:
    """Tests for the PromptBuilder class."""

    def test_builds_prompt_with_research_results(self):
        """PromptBuilder includes research results in prompt."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="Where is the CodeAgent class?",
            primary_intent=IntentMatch(
                intent=QueryIntent.CODE_SEARCH,
                confidence=0.9
            ),
            entities={'class_name': ['CodeAgent']},
            keywords=['CodeAgent']
        )

        research_results = [
            "Directory Structure:\nsrc/\n  agent.py",
            "Class 'CodeAgent':\nsrc/agent.py:10: class CodeAgent:"
        ]

        builder = PromptBuilder()
        prompt = builder.build(
            query="Where is the CodeAgent class?",
            classification=classification,
            research_results=research_results
        )

        assert "CodeAgent" in prompt
        assert "Research Results" in prompt
        assert "src/agent.py" in prompt

    def test_builds_prompt_without_research_results(self):
        """PromptBuilder handles empty research results."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="What is this project?",
            primary_intent=IntentMatch(
                intent=QueryIntent.ARCHITECTURE,
                confidence=0.7
            ),
            entities={},
            keywords=['project']
        )

        builder = PromptBuilder()
        prompt = builder.build(
            query="What is this project?",
            classification=classification,
            research_results=[]
        )

        assert "What is this project?" in prompt
        # Should not contain "Research Results" section
        assert "Research Results" not in prompt or "provide a helpful answer" in prompt.lower()

    def test_includes_classification_context(self):
        """PromptBuilder includes classification metadata."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="Find authentication code",
            primary_intent=IntentMatch(
                intent=QueryIntent.CODE_SEARCH,
                confidence=0.85
            ),
            entities={'function_name': ['authenticate']},
            keywords=['authentication', 'code']
        )

        builder = PromptBuilder()
        prompt = builder.build(
            query="Find authentication code",
            classification=classification,
            research_results=["Search result: auth.py"]
        )

        # Should include intent info
        assert "CODE_SEARCH" in prompt or "code_search" in prompt
        assert "0.85" in prompt or "85" in prompt
        # Should include entities
        assert "authenticate" in prompt
        # Should include keywords
        assert "authentication" in prompt

    def test_includes_project_summary_when_provided(self):
        """PromptBuilder includes project summary at the start."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="How does auth work?",
            primary_intent=IntentMatch(
                intent=QueryIntent.CODE_EXPLANATION,
                confidence=0.9
            ),
            entities={},
            keywords=['auth']
        )

        builder = PromptBuilder()
        prompt = builder.build(
            query="How does auth work?",
            classification=classification,
            research_results=["Code snippet here"],
            project_summary="This is a Python CLI tool for code analysis."
        )

        assert "Python CLI tool" in prompt

    def test_separates_multiple_research_results(self):
        """PromptBuilder properly separates multiple results."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="Show me tests",
            primary_intent=IntentMatch(
                intent=QueryIntent.TESTING,
                confidence=0.9
            ),
            entities={},
            keywords=['tests']
        )

        research_results = [
            "Test files:\ntests/test_agent.py",
            "Test patterns:\ndef test_something():",
            "Coverage report:\n80% coverage"
        ]

        builder = PromptBuilder()
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
        """PromptBuilder provides appropriate system prompt."""
        from src.cli.prompt_builder import PromptBuilder

        builder = PromptBuilder()
        system_prompt = builder.get_system_prompt()

        assert "AI assistant" in system_prompt
        assert "codebase" in system_prompt.lower() or "research" in system_prompt.lower()

    def test_handles_empty_entities(self):
        """PromptBuilder handles classification with no entities."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="What is this?",
            primary_intent=IntentMatch(
                intent=QueryIntent.ARCHITECTURE,
                confidence=0.6
            ),
            entities={},
            keywords=[]
        )

        builder = PromptBuilder()
        # Should not raise
        prompt = builder.build(
            query="What is this?",
            classification=classification,
            research_results=[]
        )

        assert "What is this?" in prompt


class TestPromptBuilderEdgeCases:
    """Edge case tests for PromptBuilder."""

    def test_handles_very_long_research_results(self):
        """PromptBuilder handles large research results without issues."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="Show everything",
            primary_intent=IntentMatch(
                intent=QueryIntent.FILE_STRUCTURE,
                confidence=0.9
            ),
            entities={},
            keywords=[]
        )

        # Create a large result
        large_result = "line\n" * 1000

        builder = PromptBuilder()
        prompt = builder.build(
            query="Show everything",
            classification=classification,
            research_results=[large_result]
        )

        # Should include the content (may be truncated)
        assert len(prompt) > 100
        assert "Show everything" in prompt

    def test_handles_special_characters_in_query(self):
        """PromptBuilder handles queries with special characters."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query='Search for "error" in *.py files',
            primary_intent=IntentMatch(
                intent=QueryIntent.CODE_SEARCH,
                confidence=0.9
            ),
            entities={},
            keywords=['error']
        )

        builder = PromptBuilder()
        prompt = builder.build(
            query='Search for "error" in *.py files',
            classification=classification,
            research_results=[]
        )

        assert '"error"' in prompt or 'error' in prompt

    def test_multiple_secondary_intents(self):
        """PromptBuilder handles classification with secondary intents."""
        from src.cli.prompt_builder import PromptBuilder

        classification = ClassificationResult(
            query="How does the auth system work and where is it tested?",
            primary_intent=IntentMatch(
                intent=QueryIntent.CODE_EXPLANATION,
                confidence=0.8
            ),
            secondary_intents=[
                IntentMatch(intent=QueryIntent.TESTING, confidence=0.6),
                IntentMatch(intent=QueryIntent.SECURITY, confidence=0.4)
            ],
            entities={'function_name': ['auth']},
            keywords=['auth', 'system', 'tested']
        )

        builder = PromptBuilder()
        prompt = builder.build(
            query="How does the auth system work and where is it tested?",
            classification=classification,
            research_results=["Auth code here"]
        )

        # Primary intent should be included
        assert "CODE_EXPLANATION" in prompt or "code_explanation" in prompt
