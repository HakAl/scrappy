"""
Tests for RegexEntityExtractor.

Tests behavior of entity extraction from user queries.
"""

import pytest
from scrappy.task_router.intent.entities import RegexEntityExtractor


def test_extractor_finds_file_paths():
    """Test extractor finds file paths in queries."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("check src/main.py")

    assert 'file_path' in entities
    assert any('main.py' in path for path in entities['file_path'])


def test_extractor_finds_multiple_file_paths():
    """Test extractor finds multiple file paths."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("compare src/main.py and test/test_main.py")

    assert 'file_path' in entities
    assert len(entities['file_path']) >= 2


def test_extractor_finds_class_names():
    """Test extractor finds class names in queries."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("where is UserManager class defined")

    assert 'class_name' in entities
    assert 'UserManager' in entities['class_name']


def test_extractor_finds_function_names():
    """Test extractor finds function names in queries."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("find function process_request")

    assert 'function_name' in entities
    assert 'process_request' in entities['function_name']


def test_extractor_finds_error_types():
    """Test extractor finds error types in queries."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("why is this raising a ValueError")

    assert 'error_type' in entities
    assert 'ValueError' in entities['error_type']


def test_extractor_handles_empty_query():
    """Test extractor handles empty input gracefully."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("")

    assert entities == {}


def test_extractor_handles_no_entities():
    """Test extractor handles queries with no extractable entities."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("hello world")

    assert len(entities) == 0 or all(len(v) == 0 for v in entities.values())


def test_extractor_deduplicates_matches():
    """Test extractor deduplicates repeated entities."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("check test.py and test.py again")

    assert 'file_path' in entities
    file_paths = entities['file_path']
    assert file_paths.count('test.py') == 1


def test_extractor_filters_common_words_from_class_names():
    """Test extractor filters common English words from class names."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("The User is here")

    if 'class_name' in entities:
        assert 'The' not in entities['class_name']
        assert 'User' in entities['class_name']


def test_extractor_filters_common_words_from_function_names():
    """Test extractor filters common English words from function names."""
    extractor = RegexEntityExtractor()

    entities = extractor.extract("find the get function")

    if 'function_name' in entities:
        assert 'find' not in entities['function_name']
        assert 'the' not in entities['function_name']


def test_extractor_accepts_custom_patterns():
    """Test extractor can be initialized with custom patterns."""
    custom_patterns = {
        'custom_type': [r'custom_(\w+)']
    }

    extractor = RegexEntityExtractor(patterns=custom_patterns)
    entities = extractor.extract("find custom_value here")

    assert 'custom_type' in entities
    assert 'value' in entities['custom_type']
