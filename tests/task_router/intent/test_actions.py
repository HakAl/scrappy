"""
Tests for DefaultActionResolver.

Tests behavior of action resolution from intents and entities.
"""

import pytest
from src.task_router.intent.actions import DefaultActionResolver
from src.task_router.protocols import IntentResult, QueryIntent, Action


def test_resolver_creates_file_structure_action():
    """Test resolver creates correct action for file structure intent."""
    resolver = DefaultActionResolver()
    result = IntentResult(QueryIntent.FILE_STRUCTURE, 0.8, {})
    entities = {'file_path': ['src/']}

    action = resolver.resolve(result, entities)

    assert action.tool == 'FileSystem'
    assert action.func == 'list_directory'
    assert 'path' in action.args


def test_resolver_creates_git_history_action():
    """Test resolver creates correct action for git history intent."""
    resolver = DefaultActionResolver()
    result = IntentResult(QueryIntent.GIT_HISTORY, 0.8, {})
    entities = {}

    action = resolver.resolve(result, entities)

    assert action.tool == 'GitHistory'
    assert action.func == 'get_history'


def test_resolver_creates_general_action_for_unknown_intent():
    """Test resolver creates fallback action for GENERAL intent."""
    resolver = DefaultActionResolver()
    result = IntentResult(QueryIntent.GENERAL, 0.5, {})
    entities = {}

    action = resolver.resolve(result, entities)

    assert action.tool == 'GeneralAgent'
    assert action.func == 'process'


def test_resolver_uses_entities_in_action_args():
    """Test resolver includes entities in action arguments."""
    resolver = DefaultActionResolver()
    result = IntentResult(QueryIntent.FILE_STRUCTURE, 0.8, {})
    entities = {'file_path': ['src/main.py']}

    action = resolver.resolve(result, entities)

    assert 'src/main.py' in action.args['path']
