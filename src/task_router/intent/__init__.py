"""
Intent classification package.

Provides intent classification, entity extraction, and action resolution
for user queries.
"""

from .classifier import RegexIntentClassifier
from .entities import RegexEntityExtractor
from .actions import DefaultActionResolver
from .service import IntentService

__all__ = [
    'RegexIntentClassifier',
    'RegexEntityExtractor',
    'DefaultActionResolver',
    'IntentService',
]
