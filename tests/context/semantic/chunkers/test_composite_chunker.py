"""
Tests for CompositeCodeChunker.

Tests routing to language-specific chunkers and fallback behavior.
"""

import pytest
from typing import List, Set
from unittest.mock import Mock

from src.context.protocols import CodeChunk, ChunkingStrategyProtocol
from src.context.semantic.chunkers.composite_chunker import CompositeCodeChunker
from src.context.semantic.chunkers.python_chunker import PythonASTChunker


class MockChunkingStrategy:
    """Mock chunking strategy for testing."""

    def __init__(self, extensions: Set[str], chunks: List[CodeChunk]):
        self._extensions = extensions
        self._chunks = chunks
        self.chunk_called = False
        self.last_content = None
        self.last_file_path = None

    @property
    def supported_extensions(self) -> Set[str]:
        return self._extensions

    def chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        self.chunk_called = True
        self.last_content = content
        self.last_file_path = file_path
        return self._chunks


class TestCompositeCodeChunkerBasics:
    """Basic functionality tests."""

    def test_empty_content_returns_empty_list(self):
        """Empty content should return no chunks."""
        chunker = CompositeCodeChunker()
        result = chunker.chunk("test.py", "")
        assert result == []

    def test_whitespace_only_returns_empty_list(self):
        """Whitespace-only content should return no chunks."""
        chunker = CompositeCodeChunker()
        result = chunker.chunk("test.py", "   \n\t\n   ")
        assert result == []

    def test_default_strategies_include_python(self):
        """Default strategies should include Python."""
        chunker = CompositeCodeChunker()
        assert chunker.supports_language(".py")
        assert chunker.supports_language(".pyi")

    def test_get_supported_extensions(self):
        """Should return all supported extensions."""
        chunker = CompositeCodeChunker()
        extensions = chunker.get_supported_extensions()
        assert ".py" in extensions
        assert ".pyi" in extensions


class TestCompositeCodeChunkerRouting:
    """Tests for routing to correct strategy."""

    def test_routes_python_to_python_chunker(self):
        """Python files should be routed to PythonASTChunker."""
        mock_chunks = [CodeChunk(start_line=1, end_line=10, chunk_type="function")]
        mock_strategy = MockChunkingStrategy({".py", ".pyi"}, mock_chunks)

        chunker = CompositeCodeChunker(strategies={"python": mock_strategy})
        result = chunker.chunk("test.py", "def func(): pass")

        assert mock_strategy.chunk_called
        assert mock_strategy.last_file_path == "test.py"
        assert result == mock_chunks

    def test_routes_pyi_to_python_chunker(self):
        """Python stub files should be routed to Python chunker."""
        mock_chunks = [CodeChunk(start_line=1, end_line=5, chunk_type="function")]
        mock_strategy = MockChunkingStrategy({".py", ".pyi"}, mock_chunks)

        chunker = CompositeCodeChunker(strategies={"python": mock_strategy})
        result = chunker.chunk("module.pyi", "def func() -> int: ...")

        assert mock_strategy.chunk_called
        assert mock_strategy.last_file_path == "module.pyi"

    def test_extension_case_insensitive(self):
        """Extension matching should be case-insensitive."""
        mock_chunks = [CodeChunk(start_line=1, end_line=10)]
        mock_strategy = MockChunkingStrategy({".py"}, mock_chunks)

        chunker = CompositeCodeChunker(strategies={"python": mock_strategy})

        # Test various cases
        chunker.chunk("test.PY", "code")
        assert mock_strategy.chunk_called

        mock_strategy.chunk_called = False
        chunker.chunk("test.Py", "code")
        assert mock_strategy.chunk_called

    def test_unsupported_extension_uses_fallback(self):
        """Unsupported extensions should use fallback chunker."""
        chunker = CompositeCodeChunker()
        code = "\n".join([f"line {i}" for i in range(100)])

        result = chunker.chunk("test.xyz", code)

        # Should produce chunks via fallback
        assert len(result) > 0
        # Fallback chunks should have type "block"
        assert all(c.chunk_type == "block" for c in result)

    def test_javascript_uses_fallback(self):
        """JavaScript files should use fallback (not yet supported)."""
        chunker = CompositeCodeChunker()
        code = '''
function hello() {
    console.log("Hello");
}
'''
        result = chunker.chunk("app.js", code.strip())

        # Should use fallback
        assert len(result) > 0
        assert not chunker.supports_language(".js")


class TestCompositeCodeChunkerFallback:
    """Tests for fallback behavior."""

    def test_fallback_chunk_size_configurable(self):
        """Fallback chunk size should be configurable."""
        chunker = CompositeCodeChunker(
            fallback_chunk_size=10,
            fallback_overlap=2,
        )

        # Create content longer than chunk size
        code = "\n".join([f"line {i}" for i in range(50)])
        result = chunker.chunk("test.txt", code)

        # Should create multiple chunks with ~10 lines each
        assert len(result) > 1

    def test_fallback_adds_block_type(self):
        """Fallback chunks should have chunk_type='block'."""
        chunker = CompositeCodeChunker()
        code = "\n".join([f"line {i}" for i in range(20)])

        result = chunker.chunk("test.txt", code)

        for chunk in result:
            assert chunk.chunk_type == "block"


class TestCompositeCodeChunkerCustomStrategies:
    """Tests for custom strategy configuration."""

    def test_custom_strategy_injection(self):
        """Custom strategies can be injected."""
        mock_chunks = [CodeChunk(start_line=1, end_line=5, chunk_type="custom")]
        mock_strategy = MockChunkingStrategy({".custom"}, mock_chunks)

        chunker = CompositeCodeChunker(strategies={"custom": mock_strategy})

        assert chunker.supports_language(".custom")
        result = chunker.chunk("test.custom", "content")
        assert result == mock_chunks

    def test_add_strategy_runtime(self):
        """Strategies can be added at runtime."""
        chunker = CompositeCodeChunker()
        assert not chunker.supports_language(".newlang")

        mock_chunks = [CodeChunk(start_line=1, end_line=10)]
        mock_strategy = MockChunkingStrategy({".newlang"}, mock_chunks)

        chunker.add_strategy("newlang", mock_strategy)

        assert chunker.supports_language(".newlang")
        result = chunker.chunk("test.newlang", "content")
        assert result == mock_chunks

    def test_replace_existing_strategy(self):
        """Existing strategies can be replaced."""
        old_chunks = [CodeChunk(start_line=1, end_line=5)]
        old_strategy = MockChunkingStrategy({".py"}, old_chunks)

        new_chunks = [CodeChunk(start_line=1, end_line=10)]
        new_strategy = MockChunkingStrategy({".py"}, new_chunks)

        chunker = CompositeCodeChunker(strategies={"python": old_strategy})
        chunker.add_strategy("python_v2", new_strategy)

        result = chunker.chunk("test.py", "code")
        assert result == new_chunks


class TestCompositeCodeChunkerIntegration:
    """Integration tests with real PythonASTChunker."""

    def test_real_python_chunking(self):
        """Test with real Python code through composite chunker."""
        chunker = CompositeCodeChunker()
        code = '''
def hello():
    """Say hello."""
    print("Hello!")

class Greeter:
    def greet(self, name):
        print(f"Hello, {name}!")
'''
        result = chunker.chunk("greeting.py", code.strip())

        # Should have function and class chunks
        chunk_types = [c.chunk_type for c in result]
        assert "function" in chunk_types
        assert "class" in chunk_types

    def test_mixed_files_in_sequence(self):
        """Test chunking different file types in sequence."""
        chunker = CompositeCodeChunker()

        # Python file
        py_result = chunker.chunk("main.py", "def main(): pass")
        assert any(c.chunk_type == "function" for c in py_result)

        # Unknown file type
        txt_result = chunker.chunk("readme.txt", "This is a readme.\nLine 2.")
        assert any(c.chunk_type == "block" for c in txt_result)

        # Python stub file
        pyi_result = chunker.chunk("types.pyi", "def typed_func() -> int: ...")
        assert any(c.chunk_type == "function" for c in pyi_result)


class TestCompositeCodeChunkerProtocolCompliance:
    """Tests for CodeChunkerProtocol compliance."""

    def test_implements_chunk_method(self):
        """Should implement chunk method from protocol."""
        chunker = CompositeCodeChunker()
        assert hasattr(chunker, "chunk")
        assert callable(chunker.chunk)

    def test_chunk_returns_list_of_code_chunks(self):
        """chunk() should return List[CodeChunk]."""
        chunker = CompositeCodeChunker()
        result = chunker.chunk("test.py", "x = 1")

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, CodeChunk)

    def test_chunk_method_signature(self):
        """chunk() should accept (file_path, content) arguments."""
        chunker = CompositeCodeChunker()

        # Should work with positional args
        result1 = chunker.chunk("test.py", "x = 1")

        # Should work with keyword args
        result2 = chunker.chunk(file_path="test.py", content="x = 1")

        assert isinstance(result1, list)
        assert isinstance(result2, list)
