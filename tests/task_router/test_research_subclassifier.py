"""
Tests for ResearchSubclassifier.

Tests verify that queries are correctly classified as codebase or general research.
"""

import pytest
from src.task_router.strategies.research_subclassifier import ResearchSubclassifier
from src.task_router.strategies.research_subtype import ResearchSubtype


class TestResearchSubclassifierGeneral:
    """Tests for general knowledge query classification."""

    def test_classifies_person_comparison_as_general(self):
        """Famous programmer comparison is general knowledge."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who is the best coder, Dijkstra or Turing?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_invention_question_as_general(self):
        """Questions about who invented something are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who invented Python?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_historical_question_as_general(self):
        """Historical questions are general knowledge."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("when was the first compiler written?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_famous_person_question_as_general(self):
        """Questions about famous programmers are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is Dijkstra famous for?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_concept_question_as_general(self):
        """Abstract concept questions are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is a binary search algorithm?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_algorithm_comparison_as_general(self):
        """Algorithm comparisons are general knowledge."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("which is better, quicksort vs mergesort?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_language_creation_question_as_general(self):
        """Language history questions are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who created JavaScript?")
        assert result == ResearchSubtype.GENERAL

    def test_classifies_greatest_programmer_as_general(self):
        """Greatest programmer questions are general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who is the greatest programmer of all time?")
        assert result == ResearchSubtype.GENERAL


class TestResearchSubclassifierCodebase:
    """Tests for codebase query classification."""

    def test_classifies_file_question_as_codebase(self):
        """Questions about specific files are codebase queries."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what does src/auth.py do?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_this_project_as_codebase(self):
        """References to 'this project' indicate codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("how does this project handle authentication?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_function_question_as_codebase(self):
        """Questions about functions in code are codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("explain the login function")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_class_question_as_codebase(self):
        """Questions about classes are codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what does the UserService class do?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_directory_question_as_codebase(self):
        """Questions about directories are codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is in the src/components/ folder?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_our_code_as_codebase(self):
        """References to 'our code' indicate codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("how is error handling done in our code?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_method_question_as_codebase(self):
        """Questions about methods are codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what parameters does the save method accept?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_implementation_question_as_codebase(self):
        """Questions about implementation details are codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("where is the caching logic implemented?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_js_file_reference_as_codebase(self):
        """JavaScript file references are codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what does App.tsx export?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_what_does_this_as_codebase(self):
        """'What does this' questions are typically about current code."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what does this function return?")
        assert result == ResearchSubtype.CODEBASE

    def test_classifies_how_does_this_as_codebase(self):
        """'How does this' questions about the current project."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("how does this module work?")
        assert result == ResearchSubtype.CODEBASE


class TestResearchSubclassifierContext:
    """Tests for context-aware classification."""

    def test_context_terms_boost_codebase_score(self):
        """Project-specific terms from context increase codebase score."""
        classifier = ResearchSubclassifier()
        context = "This project uses AgentOrchestrator and TaskRouter classes"
        result = classifier.classify(
            "how does the TaskRouter work?",
            context_summary=context
        )
        assert result == ResearchSubtype.CODEBASE

    def test_context_with_file_names_helps_classification(self):
        """File names in context help with classification."""
        classifier = ResearchSubclassifier()
        context = "Main files: router.py, classifier.py, executor.py"
        result = classifier.classify(
            "explain the classifier module",
            context_summary=context
        )
        assert result == ResearchSubtype.CODEBASE

    def test_general_query_stays_general_despite_context(self):
        """General queries remain general even with project context."""
        classifier = ResearchSubclassifier()
        context = "This is a Python project with AgentOrchestrator"
        result = classifier.classify(
            "who invented the actor model?",
            context_summary=context
        )
        assert result == ResearchSubtype.GENERAL


class TestResearchSubclassifierReportedBugs:
    """Tests for specific bug reports from PROMPT_REFINEMENT.md."""

    def test_add_rag_to_this_codebase_is_codebase(self):
        """
        Regression test for reported bug: 'this codebase' should route to CODEBASE.

        Query: "how would we add rag to this codebase?"
        Expected: CODEBASE (contains 'this codebase')
        Reported: Was hitting GENERAL flow
        """
        classifier = ResearchSubclassifier()
        result = classifier.classify("how would we add rag to this codebase?")
        assert result == ResearchSubtype.CODEBASE

    def test_add_feature_to_this_codebase_variations(self):
        """Test various 'add X to this codebase' patterns."""
        classifier = ResearchSubclassifier()

        queries = [
            "how would we add rag to this codebase?",
            "how can we add authentication to this codebase?",
            "how do I add logging to this codebase?",
            "what's the best way to add caching to this codebase?",
        ]

        for query in queries:
            result = classifier.classify(query)
            assert result == ResearchSubtype.CODEBASE, f"Failed for: {query}"

    def test_this_codebase_pattern_matches(self):
        """Verify 'this codebase' pattern matches correctly."""
        classifier = ResearchSubclassifier()

        # Direct pattern test - these all contain 'this codebase'
        queries = [
            "explain this codebase",
            "what does this codebase do?",
            "how is this codebase structured?",
            "analyze this codebase",
        ]

        for query in queries:
            result = classifier.classify(query)
            assert result == ResearchSubtype.CODEBASE, f"Failed for: {query}"

    def test_scores_for_reported_bug_query(self):
        """Verify scores are computed correctly for the reported bug query."""
        classifier = ResearchSubclassifier()
        query = "how would we add rag to this codebase?"

        codebase_score = classifier._score_codebase_indicators(query)
        general_score = classifier._score_general_indicators(query)

        # 'this codebase' should match pattern 0
        assert codebase_score >= 1, f"Expected codebase_score >= 1, got {codebase_score}"
        # No general patterns should match
        assert general_score == 0, f"Expected general_score == 0, got {general_score}"


class TestResearchSubclassifierEdgeCases:
    """Tests for edge cases and ambiguous queries."""

    def test_empty_query_defaults_to_general(self):
        """Empty queries default to general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("")
        assert result == ResearchSubtype.GENERAL

    def test_ambiguous_query_defaults_to_general(self):
        """Ambiguous queries default to general."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("tell me about sorting")
        assert result == ResearchSubtype.GENERAL

    def test_mixed_signals_codebase_wins_with_file_reference(self):
        """When mixed, file references tip toward codebase."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("who wrote the main.py file?")
        assert result == ResearchSubtype.CODEBASE

    def test_case_insensitive_pattern_matching(self):
        """Pattern matching is case insensitive."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("What does THIS PROJECT do?")
        assert result == ResearchSubtype.CODEBASE

    def test_urls_not_confused_with_file_paths(self):
        """URLs should not trigger codebase classification."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("what is at https://example.com/page")
        assert result == ResearchSubtype.GENERAL


class TestResearchSubclassifierProtocol:
    """Tests verifying protocol compliance."""

    def test_implements_required_method(self):
        """Classifier implements the classify method."""
        classifier = ResearchSubclassifier()
        assert hasattr(classifier, 'classify')
        assert callable(classifier.classify)

    def test_returns_research_subtype_enum(self):
        """classify() returns ResearchSubtype enum values."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("any query")
        assert isinstance(result, ResearchSubtype)

    def test_accepts_optional_context(self):
        """classify() accepts optional context_summary parameter."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("query", context_summary="context")
        assert isinstance(result, ResearchSubtype)

    def test_accepts_none_context(self):
        """classify() works with context_summary=None."""
        classifier = ResearchSubclassifier()
        result = classifier.classify("query", context_summary=None)
        assert isinstance(result, ResearchSubtype)
