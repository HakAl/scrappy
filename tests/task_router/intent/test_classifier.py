"""
Tests for RegexIntentClassifier.

Tests behavior, not implementation details. Focuses on proving that
classification works correctly for various query types.
"""

import pytest
from scrappy.task_router.intent.classifier import RegexIntentClassifier
from scrappy.task_router.protocols import QueryIntent


def test_classifier_identifies_file_structure_query():
    """Test classifier correctly identifies file structure queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("show me the directory structure")

    assert result.intent == QueryIntent.FILE_STRUCTURE
    assert result.confidence > 0.0


def test_classifier_identifies_code_explanation_query():
    """Test classifier correctly identifies code explanation queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("explain how the authentication works")

    assert result.intent == QueryIntent.CODE_EXPLANATION
    assert result.confidence > 0.0


def test_classifier_identifies_git_history_query():
    """Test classifier correctly identifies git history queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("show me recent commits")

    assert result.intent == QueryIntent.GIT_HISTORY
    assert result.confidence > 0.0


def test_classifier_identifies_dependency_info_query():
    """Test classifier correctly identifies dependency queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("what packages does this project use")

    assert result.intent == QueryIntent.DEPENDENCY_INFO
    assert result.confidence > 0.0


def test_classifier_identifies_architecture_query():
    """Test classifier correctly identifies architecture queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("what is the architecture of this system")

    assert result.intent == QueryIntent.ARCHITECTURE
    assert result.confidence > 0.0


def test_classifier_identifies_bug_investigation_query():
    """Test classifier correctly identifies bug investigation queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("why is this crashing with a ValueError")

    assert result.intent == QueryIntent.BUG_INVESTIGATION
    assert result.confidence > 0.0


def test_classifier_identifies_testing_query():
    """Test classifier correctly identifies testing queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("show me the test coverage")

    assert result.intent == QueryIntent.TESTING
    assert result.confidence > 0.0


def test_classifier_identifies_performance_query():
    """Test classifier correctly identifies performance queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("why is this function so slow")

    assert result.intent == QueryIntent.PERFORMANCE
    assert result.confidence > 0.0


def test_classifier_identifies_documentation_query():
    """Test classifier correctly identifies documentation queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("where is the API documentation")

    assert result.intent == QueryIntent.DOCUMENTATION
    assert result.confidence > 0.0


def test_classifier_identifies_refactoring_query():
    """Test classifier correctly identifies refactoring queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("this code needs refactoring")

    assert result.intent == QueryIntent.REFACTORING
    assert result.confidence > 0.0


def test_classifier_identifies_security_query():
    """Test classifier correctly identifies security queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("how is authentication secured")

    assert result.intent == QueryIntent.SECURITY
    assert result.confidence > 0.0


def test_classifier_identifies_configuration_query():
    """Test classifier correctly identifies configuration queries."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("how do I configure the settings")

    assert result.intent == QueryIntent.CONFIGURATION
    assert result.confidence > 0.0


def test_classifier_handles_empty_query():
    """Test classifier handles empty input gracefully."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("")

    assert result.intent == QueryIntent.GENERAL
    assert result.confidence >= 0.0


def test_classifier_returns_general_for_unclear_query():
    """Test classifier returns GENERAL for queries that don't match patterns."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("asdfghjkl")

    assert result.intent == QueryIntent.GENERAL
    assert result.confidence >= 0.0


def test_classifier_case_insensitive():
    """Test classifier works with different cases."""
    classifier = RegexIntentClassifier()

    result1 = classifier.classify("SHOW ME THE FILE STRUCTURE")
    result2 = classifier.classify("show me the file structure")
    result3 = classifier.classify("Show Me The File Structure")

    assert result1.intent == QueryIntent.FILE_STRUCTURE
    assert result2.intent == QueryIntent.FILE_STRUCTURE
    assert result3.intent == QueryIntent.FILE_STRUCTURE


def test_classifier_returns_metadata_with_matched_patterns():
    """Test classifier includes matched patterns in metadata."""
    classifier = RegexIntentClassifier()

    result = classifier.classify("show me the file structure")

    assert 'matched_patterns' in result.metadata
    assert isinstance(result.metadata['matched_patterns'], list)
    assert len(result.metadata['matched_patterns']) > 0


def test_classifier_confidence_increases_with_multiple_matches():
    """Test classifier confidence is higher when multiple patterns match."""
    classifier = RegexIntentClassifier()

    result_single = classifier.classify("file")
    result_multiple = classifier.classify("show me the file directory structure tree")

    assert result_multiple.confidence >= result_single.confidence


def test_classifier_accepts_custom_patterns():
    """Test classifier can be initialized with custom patterns."""
    from scrappy.task_router.protocols import QueryIntent

    custom_patterns = {
        QueryIntent.GENERAL: [
            (r'test pattern', 1.0),
        ]
    }

    classifier = RegexIntentClassifier(patterns=custom_patterns)
    result = classifier.classify("test pattern")

    assert result.intent == QueryIntent.GENERAL
    assert result.confidence > 0.5
