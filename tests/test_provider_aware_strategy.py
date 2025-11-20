"""
Tests for ProviderAwareStrategy - common provider logic extraction.

These tests drive the refactoring to remove code duplication in provider handling
across executors. The goal is a single source of truth for:
- set_provider() method
- Provider resolution and validation
- Fallback to orchestrator.brain
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Optional

from src.task_router.strategies.base import ExecutionStrategy, ExecutionResult
from src.task_router.classifier import ClassifiedTask, TaskType


class TestProviderAwareStrategyBase:
    """Tests for ProviderAwareStrategy base class existence and interface."""




