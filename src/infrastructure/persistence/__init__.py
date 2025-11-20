"""
Infrastructure persistence layer.

Provides abstractions for persisting structured data with error handling.
"""

from .protocols import PersistenceProtocol, AsyncPersistenceProtocol
from .json_persistence import JSONPersistence

__all__ = [
    'PersistenceProtocol',
    'AsyncPersistenceProtocol',
    'JSONPersistence',
]
