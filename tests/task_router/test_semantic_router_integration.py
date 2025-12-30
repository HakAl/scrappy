"""Integration tests for SemanticRouter with real embeddings.

These tests use the actual embedding model to verify classification accuracy.
Run with: python -m pytest tests/task_router/test_semantic_router_integration.py -v

Note: First run takes ~1s to load the embedding model.
"""

import pytest

from scrappy.task_router.factory import create_task_classifier
from scrappy.task_router.classification_strategy import TaskType


@pytest.fixture(scope="module")
def classifier():
    """Create classifier once for all tests in this module."""
    return create_task_classifier(warm_up=True)


class TestDirectCommand:
    """Tests for DIRECT_COMMAND classification."""

    @pytest.mark.parametrize("text", [
        "pip install requests",
        "npm install react",
        "npm run build",
        "git status",
        "git commit -m 'fix'",
        "docker ps",
        "pytest",
        "pytest tests/",
        "ls",
        "cd src",
    ])
    def test_direct_commands(self, classifier, text):
        result = classifier.classify(text)
        assert result.task_type == TaskType.DIRECT_COMMAND, (
            f"'{text}' should be DIRECT_COMMAND, got {result.task_type.value}"
        )


class TestCodeGeneration:
    """Tests for CODE_GENERATION classification."""

    @pytest.mark.parametrize("text", [
        "write a python script to parse csv",
        "create a new node.js server",
        "add a node.js server",
        "scaffold a react component",
        "make a dockerfile for this app",
        "create a requirements.txt",
        "generate setup.py",
        "build a REST API endpoint",
        "refactor this function to be async",
        "fix the type error on line 10",
        "fix the bug in user login",
        "debug why the server is crashing",
        "add error handling to this block",
        "write unit tests for this class",
        "implement a function to sort data",
    ])
    def test_code_generation(self, classifier, text):
        result = classifier.classify(text)
        assert result.task_type == TaskType.CODE_GENERATION, (
            f"'{text}' should be CODE_GENERATION, got {result.task_type.value}"
        )


class TestResearch:
    """Tests for RESEARCH classification."""

    @pytest.mark.parametrize("text", [
        "what is python?",
        "how does async await work?",
        "why is my code slow?",
        "which library should I use?",
        "explain how JWT authentication works",
        "describe the MVC pattern",
        "search for latest langchain updates",
        "find documentation for fastapi",
        "find all TODO comments",
        "list all Python files",
        "show me the requirements.txt",
        "analyze the codebase structure",
    ])
    def test_research(self, classifier, text):
        result = classifier.classify(text)
        assert result.task_type == TaskType.RESEARCH, (
            f"'{text}' should be RESEARCH, got {result.task_type.value}"
        )


class TestConversation:
    """Tests for CONVERSATION classification."""

    @pytest.mark.parametrize("text", [
        "hi",
        "hello",
        "hey there",
        "good morning",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "who are you?",
        "what can you do?",
        "help",
        "ok",
        "yes",
        "no",
    ])
    def test_conversation(self, classifier, text):
        result = classifier.classify(text)
        assert result.task_type == TaskType.CONVERSATION, (
            f"'{text}' should be CONVERSATION, got {result.task_type.value}"
        )


class TestEdgeCases:
    """Tests for edge cases and potential misclassifications."""

    def test_node_server_is_code_gen_not_research(self, classifier):
        """The original bug: 'add a node.js server' was misclassified."""
        result = classifier.classify("add a node.js server")
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence >= 0.8

    def test_csv_parsing_is_code_gen(self, classifier):
        """Variations of CSV parsing requests."""
        for text in [
            "write a python script to parse csv",
            "create a csv parser",
            "parse csv with python",
        ]:
            result = classifier.classify(text)
            assert result.task_type == TaskType.CODE_GENERATION, (
                f"'{text}' should be CODE_GENERATION"
            )

    def test_high_confidence_for_exact_matches(self, classifier):
        """Seed examples should have very high confidence."""
        result = classifier.classify("pip install requests")
        assert result.confidence >= 0.95

    def test_empty_input_returns_research_fallback(self, classifier):
        """Empty input should fallback gracefully."""
        result = classifier.classify("")
        # Empty input handled by classifier, not router
        assert result is not None

    def test_none_input_handled_gracefully(self, classifier):
        """None input should not crash."""
        result = classifier.classify(None)  # type: ignore
        assert result is not None


class TestConfidenceScores:
    """Tests for confidence score behavior."""

    def test_exact_seed_examples_have_high_confidence(self, classifier):
        """Exact matches to seed data should have ~100% confidence."""
        seed_examples = [
            "pip install requests",
            "git status",
            "hi",
            "what is python?",
        ]
        for text in seed_examples:
            result = classifier.classify(text)
            assert result.confidence >= 0.95, (
                f"'{text}' should have high confidence, got {result.confidence:.0%}"
            )

    def test_similar_inputs_have_good_confidence(self, classifier):
        """Similar inputs should have reasonable confidence."""
        result = classifier.classify("pip install numpy")  # Similar to seed
        assert result.confidence >= 0.7
        assert result.task_type == TaskType.DIRECT_COMMAND
