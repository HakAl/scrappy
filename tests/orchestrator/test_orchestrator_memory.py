"""
Tests for WorkingMemory - session-scoped memory management.
"""
import pytest
from datetime import datetime
from scrappy.orchestrator.memory import WorkingMemory


class TestWorkingMemoryBasics:
    """Basic working memory operations."""

    @pytest.fixture
    def memory(self):
        """Create a fresh WorkingMemory instance."""
        return WorkingMemory()

    @pytest.mark.unit
    def test_initial_state(self, memory):
        """Test that memory starts empty."""
        assert len(memory.file_reads) == 0
        assert len(memory.search_results) == 0
        assert len(memory.git_operations) == 0
        assert len(memory.discoveries) == 0

    @pytest.mark.unit
    def test_remember_file_read(self, memory):
        """Test storing a file read."""
        memory.remember_file_read("src/main.py", "print('hello')", lines=1)

        assert "src/main.py" in memory.file_reads
        assert memory.file_reads["src/main.py"]["content"] == "print('hello')"
        assert memory.file_reads["src/main.py"]["lines"] == 1
        assert isinstance(memory.file_reads["src/main.py"]["timestamp"], datetime)

    @pytest.mark.unit
    def test_remember_search(self, memory):
        """Test storing a search result."""
        results = ["file1.py", "file2.py"]
        memory.remember_search("TODO", results)

        assert len(memory.search_results) == 1
        assert memory.search_results[0]["query"] == "TODO"
        assert memory.search_results[0]["results"] == results

    @pytest.mark.unit
    def test_remember_git_operation(self, memory):
        """Test storing a git operation."""
        memory.remember_git_operation("git status", "On branch main")

        assert len(memory.git_operations) == 1
        assert memory.git_operations[0]["operation"] == "git status"
        assert memory.git_operations[0]["output"] == "On branch main"

    @pytest.mark.unit
    def test_add_discovery(self, memory):
        """Test adding a discovery."""
        memory.add_discovery("Found unused import", "src/utils.py:10")

        assert len(memory.discoveries) == 1
        assert memory.discoveries[0]["finding"] == "Found unused import"
        assert memory.discoveries[0]["location"] == "src/utils.py:10"


class TestWorkingMemoryLRUCache:
    """Test LRU cache behavior for file reads."""

    @pytest.mark.unit
    def test_file_cache_lru_eviction(self):
        """Test that oldest files are evicted when cache is full."""
        memory = WorkingMemory(max_file_cache=3)

        # Fill cache
        memory.remember_file_read("file1.py", "content1", lines=10)
        memory.remember_file_read("file2.py", "content2", lines=20)
        memory.remember_file_read("file3.py", "content3", lines=30)

        # Add one more to trigger eviction
        memory.remember_file_read("file4.py", "content4", lines=40)

        assert len(memory.file_reads) == 3
        assert "file1.py" not in memory.file_reads  # Oldest evicted
        assert "file4.py" in memory.file_reads

    @pytest.mark.unit
    def test_search_results_limited(self):
        """Test that search results are limited to max size."""
        memory = WorkingMemory(max_searches=2)

        memory.remember_search("query1", ["result1"])
        memory.remember_search("query2", ["result2"])
        memory.remember_search("query3", ["result3"])

        assert len(memory.search_results) == 2
        assert memory.search_results[0]["query"] == "query2"
        assert memory.search_results[1]["query"] == "query3"

    @pytest.mark.unit
    def test_git_operations_limited(self):
        """Test that git operations are limited to max size."""
        memory = WorkingMemory(max_git_ops=2)

        memory.remember_git_operation("git status", "status1")
        memory.remember_git_operation("git diff", "diff1")
        memory.remember_git_operation("git log", "log1")

        assert len(memory.git_operations) == 2
        assert memory.git_operations[0]["operation"] == "git diff"
        assert memory.git_operations[1]["operation"] == "git log"


class TestWorkingMemorySummary:
    """Tests for memory summary and context generation."""

    @pytest.fixture
    def populated_memory(self):
        """Create memory with some data."""
        memory = WorkingMemory()
        memory.remember_file_read("src/main.py", "code", lines=100)
        memory.remember_search("TODO", ["file1", "file2"])
        memory.remember_git_operation("git status", "clean")
        memory.add_discovery("Pattern found", "src/utils.py")
        return memory

    @pytest.mark.unit
    def test_get_summary(self, populated_memory):
        """Test getting memory summary."""
        summary = populated_memory.get_summary()

        assert summary["files_cached"] == 1
        assert "src/main.py" in summary["cached_files"]
        assert summary["recent_searches"] == 1
        assert summary["git_operations"] == 1
        assert summary["discoveries"] == 1

    @pytest.mark.unit
    def test_get_context_string(self, populated_memory):
        """Test getting context string for LLM augmentation."""
        context = populated_memory.get_context_string()

        assert "[Session Working Memory]" in context
        assert "src/main.py" in context
        assert "100 lines" in context
        assert "TODO" in context
        assert "git status" in context
        assert "Pattern found" in context

    @pytest.mark.unit
    def test_empty_context_string(self):
        """Test context string when memory is empty."""
        memory = WorkingMemory()
        context = memory.get_context_string()
        assert context == ""


class TestWorkingMemorySerialization:
    """Tests for memory serialization and deserialization."""

    @pytest.fixture
    def memory_with_data(self):
        """Create memory with various data types."""
        memory = WorkingMemory()
        memory.remember_file_read("test.py", "content", lines=50)
        memory.remember_search("error", ["error1", "error2"])
        memory.remember_git_operation("git commit", "committed")
        memory.add_discovery("Bug found", "line 42")
        return memory

    @pytest.mark.unit
    def test_to_dict(self, memory_with_data):
        """Test serialization to dictionary."""
        data = memory_with_data.to_dict()

        assert "file_reads" in data
        assert "search_results" in data
        assert "git_operations" in data
        assert "discoveries" in data

        # Check file reads serialization
        assert "test.py" in data["file_reads"]
        assert isinstance(data["file_reads"]["test.py"]["timestamp"], str)  # ISO format

        # Check lists serialization
        assert len(data["search_results"]) == 1
        assert data["search_results"][0]["query"] == "error"

    @pytest.mark.unit
    def test_from_dict(self, memory_with_data):
        """Test deserialization from dictionary."""
        original_data = memory_with_data.to_dict()
        restored = WorkingMemory.from_dict(original_data)

        # Verify restoration
        assert "test.py" in restored.file_reads
        assert restored.file_reads["test.py"]["content"] == "content"
        assert restored.file_reads["test.py"]["lines"] == 50
        assert isinstance(restored.file_reads["test.py"]["timestamp"], datetime)

        assert len(restored.search_results) == 1
        assert restored.search_results[0]["query"] == "error"

        assert len(restored.git_operations) == 1
        assert restored.git_operations[0]["operation"] == "git commit"

        assert len(restored.discoveries) == 1
        assert restored.discoveries[0]["finding"] == "Bug found"

    @pytest.mark.unit
    def test_roundtrip_serialization(self, memory_with_data):
        """Test that data survives serialization roundtrip."""
        original_summary = memory_with_data.get_summary()

        # Serialize and deserialize
        data = memory_with_data.to_dict()
        restored = WorkingMemory.from_dict(data)

        restored_summary = restored.get_summary()

        # Summaries should match
        assert original_summary["files_cached"] == restored_summary["files_cached"]
        assert original_summary["recent_searches"] == restored_summary["recent_searches"]
        assert original_summary["git_operations"] == restored_summary["git_operations"]
        assert original_summary["discoveries"] == restored_summary["discoveries"]

    @pytest.mark.unit
    def test_from_dict_empty(self):
        """Test deserialization from empty dictionary."""
        restored = WorkingMemory.from_dict({})

        assert len(restored.file_reads) == 0
        assert len(restored.search_results) == 0
        assert len(restored.git_operations) == 0
        assert len(restored.discoveries) == 0


class TestWorkingMemoryClear:
    """Tests for clearing memory."""

    @pytest.mark.unit
    def test_clear(self):
        """Test clearing all memory."""
        memory = WorkingMemory()
        memory.remember_file_read("test.py", "content", lines=10)
        memory.remember_search("query", ["result"])
        memory.remember_git_operation("git status", "output")
        memory.add_discovery("finding", "location")

        memory.clear()

        assert len(memory.file_reads) == 0
        assert len(memory.search_results) == 0
        assert len(memory.git_operations) == 0
        assert len(memory.discoveries) == 0
