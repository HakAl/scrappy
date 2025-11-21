"""
Edge case tests that expose limitations of regex-based classification.

These tests demonstrate scenarios where the current regex approach struggles:
1. Pattern maintainability - hard to update/extend
2. Context-dependent classification - same words, different meanings
3. Semantic understanding - understanding intent vs pattern matching
4. Complex priority resolution - when multiple patterns conflict
"""

import pytest
from src.task_router.classifier import TaskClassifier, TaskType


class TestContextDependentClassification:
    """Test cases where context changes classification."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_list_as_verb_vs_noun_create(self, classifier):
        """'list' as verb (show) vs in 'list structure' (create)."""
        # List as verb - should be RESEARCH
        result1 = classifier.classify("list all functions")
        assert result1.task_type == TaskType.RESEARCH

        # List as noun in creation context - should be CODE_GENERATION
        result2 = classifier.classify("create a list of users")
        assert result2.task_type == TaskType.CODE_GENERATION

    def test_make_command_vs_make_build_tool(self, classifier):
        """'make' as create verb vs 'make' build tool."""
        # 'make' as create - should be CODE_GENERATION
        result1 = classifier.classify("make a function")
        assert result1.task_type == TaskType.CODE_GENERATION

        # 'make' as build tool - should be DIRECT_COMMAND
        result2 = classifier.classify("make build")
        assert result2.task_type == TaskType.DIRECT_COMMAND

    def test_test_as_noun_vs_pytest_command(self, classifier):
        """'test' in context of writing tests vs running pytest."""
        # Writing tests - should be CODE_GENERATION
        result1 = classifier.classify("write tests for the login function")
        assert result1.task_type == TaskType.CODE_GENERATION

        # Running tests - should be DIRECT_COMMAND
        result2 = classifier.classify("pytest tests/")
        assert result2.task_type == TaskType.DIRECT_COMMAND


class TestSemanticIntent:
    """Test cases requiring semantic understanding of intent."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_rhetorical_question_vs_real_question(self, classifier):
        """Rhetorical questions in code comments vs real questions."""
        # Real question - should be RESEARCH
        result1 = classifier.classify("what does this function do?")
        assert result1.task_type == TaskType.RESEARCH

    def test_imperative_vs_conditional(self, classifier):
        """Imperative commands vs conditional questions."""
        # Imperative - should be CODE_GENERATION
        result1 = classifier.classify("create the database schema")
        assert result1.task_type == TaskType.CODE_GENERATION


class TestPatternOverlap:
    """Test cases where multiple patterns overlap."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_explain_how_to_create(self, classifier):
        """Both 'explain' (RESEARCH) and 'create' (CODE_GENERATION) present."""
        result = classifier.classify("explain how to create a REST API")
        # RESEARCH should win due to higher weight for 'explain'
        assert result.task_type == TaskType.RESEARCH
        # But confidence should reflect the ambiguity
        assert 0.7 <= result.confidence <= 1.0

    def test_find_and_fix(self, classifier):
        """Both 'find' (RESEARCH) and 'fix' (CODE_GENERATION) present."""
        result = classifier.classify("find and fix the authentication bug")
        # CODE_GENERATION should likely win since fixing requires code changes
        assert result.task_type == TaskType.CODE_GENERATION

    def test_create_then_list(self, classifier):
        """Multi-step with both CODE_GENERATION and RESEARCH verbs."""
        result = classifier.classify("create a function then list all its uses")
        # CODE_GENERATION should win (primary action)
        assert result.task_type == TaskType.CODE_GENERATION
        # Should recognize multi-step complexity
        assert result.complexity_score >= 5


class TestMaintenanceChallenges:
    """Test cases that demonstrate maintenance difficulties."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_pattern_weight_tuning_fragility(self, classifier):
        """Small weight changes can break classification."""
        # These should have similar confidence since they're similar tasks
        result1 = classifier.classify("create a function")
        result2 = classifier.classify("write a function")
        result3 = classifier.classify("implement a function")

        # All should be CODE_GENERATION with similar confidence
        assert result1.task_type == TaskType.CODE_GENERATION
        assert result2.task_type == TaskType.CODE_GENERATION
        assert result3.task_type == TaskType.CODE_GENERATION

        # Confidence should be similar (within 0.2)
        confidences = [result1.confidence, result2.confidence, result3.confidence]
        assert max(confidences) - min(confidences) <= 0.2

    def test_ordering_independence(self, classifier):
        """Classification should be independent of word order (mostly)."""
        result1 = classifier.classify("fix the bug in user authentication")
        result2 = classifier.classify("in user authentication fix the bug")

        # Both should classify the same way
        assert result1.task_type == result2.task_type
        # Though confidence might differ slightly
        assert result1.task_type == TaskType.CODE_GENERATION


class TestComplexRealWorldScenarios:
    """Real-world scenarios that stress the classifier."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_multi_sentence_mixed_intent(self, classifier):
        """Multiple sentences with different intents."""
        result = classifier.classify(
            "What is the current API structure? "
            "Then create a new endpoint for user profiles."
        )
        # Primary action is creation (CODE_GENERATION)
        # But starts with question (RESEARCH)
        # Should classify based on dominant/final action
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.complexity_score >= 5


class TestFallbackBehaviorEdgeCases:
    """Test edge cases in fallback logic."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_numbers_only(self, classifier):
        """Input with only numbers."""
        result = classifier.classify("12345")
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.5

    def test_symbols_only(self, classifier):
        """Input with only symbols."""
        result = classifier.classify("!@#$%^&*()")
        assert result.task_type == TaskType.RESEARCH
        assert result.confidence == 0.5

    def test_single_word_ambiguous(self, classifier):
        """Single ambiguous word."""
        result = classifier.classify("refactor")
        # Just "refactor" alone - what should this be?
        # Likely CODE_GENERATION but confidence should be lower
        assert result.task_type == TaskType.CODE_GENERATION


class TestPriorityEdgeCases:
    """Test priority resolution in complex scenarios."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_equal_weight_patterns(self, classifier):
        """When patterns have equal weight, tie-breaking should be consistent."""
        # Construct input that matches patterns with similar weights
        result = classifier.classify("explain and create")
        # Should have deterministic result, not random
        assert result.task_type in [TaskType.RESEARCH, TaskType.CODE_GENERATION]
        # Run again to ensure consistency
        result2 = classifier.classify("explain and create")
        assert result.task_type == result2.task_type

    def test_many_weak_vs_one_strong(self, classifier):
        """Many weak patterns vs one strong pattern."""
        # Many weak patterns for CODE_GENERATION
        result1 = classifier.classify("add modify update change")
        assert result1.task_type == TaskType.CODE_GENERATION

        # One strong pattern for RESEARCH
        result2 = classifier.classify("explain")
        assert result2.task_type == TaskType.RESEARCH

        # Strong should beat multiple weak (if weights are right)
        result3 = classifier.classify("explain after you add modify update")
        # RESEARCH 'explain' has weight 1.0, should win
        assert result3.task_type == TaskType.RESEARCH


class TestMetadataExtractionEdgeCases:
    """Test edge cases in metadata extraction."""

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_relative_vs_absolute_paths(self, classifier):
        """Should normalize path separators."""
        result1 = classifier.classify("edit src/utils.py")
        result2 = classifier.classify("edit src\\utils.py")
        # Both should extract same normalized path
        assert "src/utils.py" in result1.extracted_files
        assert "src/utils.py" in result2.extracted_files

    def test_hidden_files(self, classifier):
        """Hidden files starting with dot."""
        result = classifier.classify("create .gitignore")
        # Should extract .gitignore
        assert ".gitignore" in result.extracted_files or "gitignore" in result.reasoning.lower()


class TestStrategyPatternMotivation:
    """
    Tests that motivate the strategy pattern refactor.
    """

    @pytest.fixture
    def classifier(self):
        return TaskClassifier()

    def test_would_benefit_from_chain_of_responsibility(self, classifier):
        """Some inputs need multiple strategy evaluations."""
        result = classifier.classify(
            "first, explain the current architecture, "
            "then create a new module, "
            "and finally write tests"
        )
        # This has three distinct actions of different types
        # Current: picks highest scoring type
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.complexity_score >= 7

    def test_would_benefit_from_priority_chain(self, classifier):
        """Some patterns should short-circuit others."""
        # Direct commands should short-circuit other analysis
        result = classifier.classify("pip install requests")
        assert result.task_type == TaskType.DIRECT_COMMAND
        # No need to check other patterns after direct command match