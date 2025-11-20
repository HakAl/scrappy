"""
Tests for IntentService.

Tests integration of classifier, extractor, and resolver.
"""

import pytest
from src.task_router.intent.service import IntentService
from src.task_router.intent.classifier import RegexIntentClassifier
from src.task_router.intent.entities import RegexEntityExtractor
from src.task_router.intent.actions import DefaultActionResolver
from tests.helpers import (
    StubIntentClassifier,
    StubEntityExtractor,
    StubActionResolver,
)
from src.task_router.protocols import QueryIntent, IntentResult, Action


def test_service_end_to_end_with_real_components():
    """Test the full pipeline with real components."""
    service = IntentService(
        classifier=RegexIntentClassifier(),
        extractor=RegexEntityExtractor(),
        resolver=DefaultActionResolver()
    )

    action = service.process_query("show me the file structure")

    assert action.tool == 'FileSystem'
    assert action.func == 'list_directory'


def test_service_coordinates_components_correctly():
    """Test that service calls components in correct order."""
    classifier = StubIntentClassifier(QueryIntent.FILE_STRUCTURE, confidence=0.8)
    extractor = StubEntityExtractor({'file_path': ['test.py']})
    resolver = DefaultActionResolver()

    service = IntentService(classifier, extractor, resolver)
    action = service.process_query("any query")

    assert action.tool == 'FileSystem'


def test_service_handles_missing_entities():
    """Test service handles gracefully when no entities extracted."""
    classifier = StubIntentClassifier(QueryIntent.CODE_SEARCH)
    extractor = StubEntityExtractor({})
    resolver = DefaultActionResolver()

    service = IntentService(classifier, extractor, resolver)
    action = service.process_query("search for something")

    assert action.tool == 'CodeSearch'
    assert action.func == 'search'


def test_service_uses_default_components_when_none_provided():
    """Test service creates default components when none injected."""
    service = IntentService()

    action = service.process_query("show me the documentation")

    assert isinstance(action, Action)
    assert action.tool is not None
    assert action.func is not None


def test_service_handles_empty_query():
    """Test service handles empty query gracefully."""
    service = IntentService()

    action = service.process_query("")

    assert isinstance(action, Action)


def test_service_processes_complex_query():
    """Test service handles complex query with multiple entities."""
    service = IntentService()

    action = service.process_query("why is UserManager in src/auth.py crashing")

    assert isinstance(action, Action)
    assert action.tool is not None
