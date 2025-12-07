"""
Tests for SemanticSearchManager - semantic search lifecycle management.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

from scrappy.context.semantic_manager import SemanticSearchManager, NullSemanticSearchManager
from scrappy.infrastructure.threading import (
    EventQueueProtocol,
    ThreadSafeEventQueue,
    BackgroundEvent,
    EventType,
)
from scrappy.infrastructure.progress import NullProgressReporter


@pytest.fixture
def test_path():
    """Create a test path that exists."""
    # Use the project root as a test path that definitely exists
    return Path(__file__).parent.parent.parent


class MockInitializer:
    """Mock background initializer for testing."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self._started = False
        self._complete = False
        self._status = "Not started"

    def start(self):
        self._started = True
        self._status = "Running"

    def is_complete(self):
        return self._complete

    def is_running(self):
        return self._started and not self._complete

    def get_result(self):
        return self._result

    def get_error(self):
        return self._error

    def get_status(self):
        return self._status

    def wait_for_completion(self, timeout=None):
        return self._complete

    def complete(self, result=None, error=None):
        """Simulate completion for testing."""
        self._complete = True
        if result is not None:
            self._result = result
        if error is not None:
            self._error = error
        self._status = "Complete" if error is None else f"Failed: {error}"


class MockSearchProvider:
    """Mock semantic search provider for testing."""

    def __init__(self, indexed=False, search_results=None):
        self._indexed = indexed
        self._search_results = search_results or Mock()
        self._files_indexed = {}
        self.index_files = Mock(side_effect=self._index_files_impl)
        self.save_index_state = Mock()

    def is_indexed(self):
        return self._indexed

    def search(self, query, max_results=25, max_tokens=4000):
        return self._search_results

    def _index_files_impl(self, files, is_batch=False):
        """Internal implementation for index_files."""
        self._files_indexed.update(files)
        self._indexed = True

    def set_progress_reporter(self, reporter):
        pass


class MockFileCollector:
    """Mock file collector for testing."""

    def __init__(self, files=None):
        self._files = files or {"test.py": "print('hello')"}

    def collect_files(self):
        return self._files

    def collect_files_batched(self, batch_size=50):
        # Yield all files in one batch for simplicity
        yield self._files

    def collect_file_paths(self):
        """Return list of file paths (for metrics)."""
        return [Path(p) for p in self._files.keys()]

    def get_file_hashes(self, files):
        """Return dict mapping paths to hashes."""
        return {str(f): "mock_hash_123" for f in files}

    def get_file_sizes(self, files):
        """Return dict mapping paths to sizes."""
        return {str(f): 100 for f in files}


class MockIndexStateManager:
    """Mock index state manager for testing."""

    def __init__(self):
        self._state = None

    def load(self):
        return self._state

    def save(self, state):
        self._state = state

    def clear(self):
        self._state = None


class MockDecisionMaker:
    """Mock indexing decision maker for testing."""

    def __init__(self, decision=None, show_progress=False):
        # Import here to avoid circular dependency
        from scrappy.context.protocols import IndexingDecision

        # Default to FULL_INDEX if no decision provided
        if decision is None:
            self._decision = IndexingDecision.FULL_INDEX
        elif isinstance(decision, str):
            # Convert string to enum for backward compatibility
            decision_map = {
                "full": IndexingDecision.FULL_INDEX,
                "incremental": IndexingDecision.INCREMENTAL_UPDATE,
                "skip": IndexingDecision.SKIP,
            }
            self._decision = decision_map.get(decision, IndexingDecision.FULL_INDEX)
        else:
            self._decision = decision
        self._show_progress = show_progress

    def decide(self, saved_state, current_metrics):
        return self._decision

    def should_show_progress(self, metrics):
        return self._show_progress


class MockConfig:
    """Mock semantic index config for testing."""

    def __init__(self):
        self.db_dir_name = ".scrappy_index"
        self.table_name = "code_chunks"
        self.avg_chunk_bytes = 400
        self.show_progress_chunks = 20


class TestSemanticSearchManagerCreation:
    """Tests for SemanticSearchManager creation."""

    @pytest.mark.unit
    def test_creation_with_defaults(self, test_path):
        """Test creating manager with default parameters."""
        manager = SemanticSearchManager(project_path=test_path)
        assert manager is not None
        assert manager.event_queue is not None

    @pytest.mark.unit
    def test_creation_with_custom_event_queue(self, test_path):
        """Test creating manager with custom event queue."""
        queue = ThreadSafeEventQueue()
        manager = SemanticSearchManager(
            project_path=test_path,
            event_queue=queue,
        )
        assert manager.event_queue is queue

    @pytest.mark.unit
    def test_creation_with_initializer(self, test_path):
        """Test creating manager with custom initializer."""
        initializer = MockInitializer()
        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        # Verify initializer is set
        manager.start_background_init()
        assert initializer._started

    @pytest.mark.unit
    def test_creation_with_config(self, test_path):
        """Test creating manager with custom config."""
        config = MockConfig()
        manager = SemanticSearchManager(
            project_path=test_path,
            config=config,
        )
        assert manager is not None

    @pytest.mark.unit
    def test_creation_with_state_manager(self, test_path):
        """Test creating manager with custom state manager."""
        state_manager = MockIndexStateManager()
        manager = SemanticSearchManager(
            project_path=test_path,
            state_manager=state_manager,
        )
        assert manager is not None

    @pytest.mark.unit
    def test_creation_with_decision_maker(self, test_path):
        """Test creating manager with custom decision maker."""
        decision_maker = MockDecisionMaker()
        manager = SemanticSearchManager(
            project_path=test_path,
            decision_maker=decision_maker,
        )
        assert manager is not None


class TestSemanticSearchManagerLifecycle:
    """Tests for semantic search initialization lifecycle."""

    @pytest.mark.unit
    def test_start_background_init_starts_initializer(self, test_path):
        """Test that start_background_init starts the initializer."""
        initializer = MockInitializer()
        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        manager.start_background_init()
        assert initializer._started

    @pytest.mark.unit
    def test_is_ready_false_before_init(self, test_path):
        """Test that is_ready returns False before initialization."""
        initializer = MockInitializer()
        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        assert manager.is_ready() is False

    @pytest.mark.unit
    def test_is_ready_true_after_successful_init(self, test_path):
        """Test that is_ready returns True after successful initialization."""
        provider = MockSearchProvider()
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        assert manager.is_ready() is True

    @pytest.mark.unit
    def test_is_ready_false_after_failed_init(self, test_path):
        """Test that is_ready returns False after failed initialization."""
        initializer = MockInitializer()
        initializer.complete(error=Exception("Init failed"))

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        assert manager.is_ready() is False

    @pytest.mark.unit
    def test_get_status_returns_initializer_status(self, test_path):
        """Test that get_status delegates to initializer."""
        initializer = MockInitializer()
        initializer._status = "Loading model..."

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        assert manager.get_status() == "Loading model..."


class TestSemanticSearchManagerSearch:
    """Tests for semantic search functionality."""

    @pytest.mark.unit
    def test_search_returns_none_when_not_ready(self, test_path):
        """Test that search returns None when not ready."""
        initializer = MockInitializer()
        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        result = manager.search("test query")
        assert result is None

    @pytest.mark.unit
    def test_search_delegates_to_provider(self, test_path):
        """Test that search delegates to the search provider."""
        mock_result = Mock()
        mock_result.chunks = [{"path": "test.py", "content": "test"}]

        provider = MockSearchProvider(indexed=True, search_results=mock_result)
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        result = manager.search("test query")
        assert result is mock_result

    @pytest.mark.unit
    def test_search_returns_none_when_provider_not_indexed(self, test_path):
        """Test that search returns None when provider not indexed."""
        provider = MockSearchProvider(indexed=False)
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        result = manager.search("test query")
        assert result is None

    @pytest.mark.unit
    def test_get_search_provider_returns_provider(self, test_path):
        """Test that get_search_provider returns the provider."""
        provider = MockSearchProvider()
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        assert manager.get_search_provider() is provider


class TestSemanticSearchManagerIndexing:
    """Tests for semantic search indexing."""

    @pytest.mark.unit
    def test_index_files_when_not_ready(self, test_path):
        """Test that index_files handles not-ready state gracefully."""
        initializer = MockInitializer()
        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        collector = MockFileCollector()
        progress_reporter = NullProgressReporter()
        # Should not raise, just log warning
        manager.index_files(collector, progress_reporter=progress_reporter)

    @pytest.mark.unit
    def test_index_files_delegates_to_provider(self, test_path):
        """Test that index_files indexes via the provider."""
        provider = MockSearchProvider()
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        collector = MockFileCollector({"main.py": "print('main')"})
        progress_reporter = NullProgressReporter()
        manager.index_files(collector, progress_reporter=progress_reporter)

        assert provider._indexed
        assert "main.py" in provider._files_indexed

    @pytest.mark.unit
    def test_index_files_uses_null_reporter_by_default(self, test_path):
        """Test that index_files defaults to NullProgressReporter when none provided."""
        provider = MockSearchProvider()
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
        )
        collector = MockFileCollector({"main.py": "print('main')"})
        # Don't pass progress_reporter parameter
        manager.index_files(collector)

        assert provider._indexed
        assert "main.py" in provider._files_indexed

    @pytest.mark.unit
    def test_index_files_skips_when_no_changes(self, test_path):
        """index_files skips indexing when decision is SKIP."""
        from scrappy.context.protocols import IndexingDecision, IndexState
        from datetime import datetime

        # Create a mock saved state
        mock_saved_state = IndexState(
            last_indexed=datetime.now(),
            total_chunks=100,
            total_files=5,
            index_version="1.0",
            file_hashes={"test.py": "hash123"}
        )

        # Set up decision maker to return SKIP
        decision_maker = MockDecisionMaker(decision=IndexingDecision.SKIP)
        state_manager = MockIndexStateManager()
        state_manager._state = mock_saved_state

        provider = MockSearchProvider()
        initializer = MockInitializer(result=provider)
        initializer.complete(result=provider)

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
            state_manager=state_manager,
            decision_maker=decision_maker,
        )

        collector = MockFileCollector({"test.py": "print('hello')"})
        manager.index_files(collector)

        # Provider.index_files should NOT be called
        provider.index_files.assert_not_called()


class TestSemanticSearchManagerEvents:
    """Tests for event handling."""

    @pytest.mark.unit
    def test_process_events_processes_queue(self, test_path):
        """Test that process_events processes pending events."""
        queue = ThreadSafeEventQueue()
        manager = SemanticSearchManager(
            project_path=test_path,
            event_queue=queue,
        )

        # Initially no events
        count = manager.process_events()
        assert count == 0

    @pytest.mark.unit
    def test_handles_init_complete_event(self, test_path):
        """Test that INIT_COMPLETE event updates state."""
        queue = ThreadSafeEventQueue()
        initializer = MockInitializer()

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
            event_queue=queue,
        )
        manager.start_background_init()

        # Simulate init complete event
        provider = MockSearchProvider()
        event = BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data=provider,
        )
        queue.put(event)

        # Process the event
        manager.process_events()

        # Provider should now be available
        assert manager.get_search_provider() is provider


class TestSemanticSearchManagerCallbacks:
    """Tests for progress callbacks."""

    @pytest.mark.unit
    def test_set_progress_callback(self, test_path):
        """Test that progress callback can be set."""
        manager = SemanticSearchManager(project_path=test_path)
        callback = Mock()
        manager.set_progress_callback(callback)
        # Callback is stored (no public way to verify except through behavior)


class TestSemanticSearchManagerDecisionMaker:
    """Tests for decision maker integration."""

    @pytest.mark.unit
    def test_decision_maker_is_stored(self, test_path):
        """Test that decision maker is stored when provided."""
        decision_maker = MockDecisionMaker()
        manager = SemanticSearchManager(
            project_path=test_path,
            decision_maker=decision_maker,
        )
        # Decision maker is stored (accessible via _decision_maker for testing)
        assert manager._decision_maker is decision_maker

    @pytest.mark.unit
    def test_decision_maker_defaults_to_none(self, test_path):
        """Test that decision maker defaults to None when not provided."""
        manager = SemanticSearchManager(
            project_path=test_path,
        )
        # Default factory returns None
        assert manager._decision_maker is None

    @pytest.mark.unit
    def test_state_manager_is_stored(self, test_path):
        """Test that state manager is stored when provided."""
        state_manager = MockIndexStateManager()
        manager = SemanticSearchManager(
            project_path=test_path,
            state_manager=state_manager,
        )
        # State manager is stored (accessible via _state_manager for testing)
        assert manager._state_manager is state_manager

    @pytest.mark.unit
    def test_state_manager_defaults_to_none(self, test_path):
        """Test that state manager defaults to None when not provided."""
        manager = SemanticSearchManager(
            project_path=test_path,
        )
        # Default factory returns None
        assert manager._state_manager is None


class TestSemanticSearchManagerAutoIndexing:
    """Tests for auto-indexing flow triggered by INIT_COMPLETE event."""

    @pytest.mark.unit
    def test_init_complete_triggers_indexing_when_callback_set(self, test_path):
        """INIT_COMPLETE should trigger indexing if file collector callback exists."""
        queue = ThreadSafeEventQueue()
        initializer = MockInitializer()

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
            event_queue=queue,
        )

        # Set up file collector callback
        mock_collector = MockFileCollector({"test.py": "print('hello')"})
        manager.set_file_collector_callback(lambda: mock_collector)

        manager.start_background_init()

        # Simulate INIT_COMPLETE event with a provider
        provider = MockSearchProvider(indexed=False)
        event = BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data=provider,
        )
        queue.put(event)

        # Process the event
        manager.process_events()

        # Verify indexing was triggered - provider should now be indexed
        assert provider._indexed
        assert "test.py" in provider._files_indexed

    @pytest.mark.unit
    def test_init_complete_skips_indexing_when_no_callback(self, test_path):
        """INIT_COMPLETE should not fail if no file collector callback."""
        queue = ThreadSafeEventQueue()
        initializer = MockInitializer()

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
            event_queue=queue,
        )

        # No file collector callback set
        manager.start_background_init()

        # Simulate INIT_COMPLETE event
        provider = MockSearchProvider()
        event = BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data=provider,
        )
        queue.put(event)

        # Should not raise
        manager.process_events()

        # Provider should be cached but not indexed (no callback)
        assert manager.get_search_provider() is provider
        assert not provider._indexed

    @pytest.mark.unit
    def test_init_complete_handles_callback_returning_none(self, test_path):
        """INIT_COMPLETE should handle callback returning None gracefully."""
        queue = ThreadSafeEventQueue()
        initializer = MockInitializer()

        manager = SemanticSearchManager(
            project_path=test_path,
            initializer=initializer,
            event_queue=queue,
        )

        # Set callback that returns None
        manager.set_file_collector_callback(lambda: None)

        manager.start_background_init()

        # Simulate INIT_COMPLETE event
        provider = MockSearchProvider()
        event = BackgroundEvent(
            event_type=EventType.INIT_COMPLETE,
            source="semantic_search",
            data=provider,
        )
        queue.put(event)

        # Should not raise
        manager.process_events()

        # Provider should be cached but not indexed
        assert manager.get_search_provider() is provider
        assert not provider._indexed

    @pytest.mark.unit
    def test_set_file_collector_callback(self, test_path):
        """Test that file collector callback can be set."""
        manager = SemanticSearchManager(project_path=test_path)
        callback = Mock(return_value=MockFileCollector())
        manager.set_file_collector_callback(callback)
        # Callback is stored (verified through behavior in other tests)


class TestNullSemanticSearchManager:
    """Tests for NullSemanticSearchManager."""

    @pytest.mark.unit
    def test_is_ready_always_false(self):
        """Test that is_ready always returns False."""
        manager = NullSemanticSearchManager()
        assert manager.is_ready() is False

    @pytest.mark.unit
    def test_get_status_returns_none(self):
        """Test that get_status returns None."""
        manager = NullSemanticSearchManager()
        assert manager.get_status() is None

    @pytest.mark.unit
    def test_search_returns_none(self):
        """Test that search returns None."""
        manager = NullSemanticSearchManager()
        assert manager.search("query") is None

    @pytest.mark.unit
    def test_start_background_init_is_noop(self):
        """Test that start_background_init is a no-op."""
        manager = NullSemanticSearchManager()
        manager.start_background_init()  # Should not raise

    @pytest.mark.unit
    def test_process_events_returns_zero(self):
        """Test that process_events returns 0."""
        manager = NullSemanticSearchManager()
        assert manager.process_events() == 0

    @pytest.mark.unit
    def test_set_file_collector_callback_is_noop(self):
        """Test that set_file_collector_callback is a no-op."""
        manager = NullSemanticSearchManager()
        manager.set_file_collector_callback(lambda: None)  # Should not raise
