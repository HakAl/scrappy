"""
Tests for PythonASTChunker.

Tests AST-aware chunking of Python code at function/class boundaries.
"""

import pytest
from scrappy.context.protocols import CodeChunk
from scrappy.context.semantic.chunkers.python_chunker import (
    PythonASTChunker,
    PythonChunkerConfig,
)


class TestPythonASTChunkerBasics:
    """Basic functionality tests."""

    def test_empty_content_returns_empty_list(self):
        """Empty content should return no chunks."""
        chunker = PythonASTChunker()
        result = chunker.chunk("", "test.py")
        assert result == []

    def test_whitespace_only_returns_empty_list(self):
        """Whitespace-only content should return no chunks."""
        chunker = PythonASTChunker()
        result = chunker.chunk("   \n\t\n   ", "test.py")
        assert result == []

    def test_supported_extensions(self):
        """Verify supported file extensions."""
        chunker = PythonASTChunker()
        assert ".py" in chunker.supported_extensions
        assert ".pyi" in chunker.supported_extensions
        assert len(chunker.supported_extensions) == 2

    def test_custom_config(self):
        """Custom config should be respected."""
        config = PythonChunkerConfig(
            max_chunk_lines=50,
            min_chunk_lines=3,
            include_preamble=False,
        )
        chunker = PythonASTChunker(config=config)
        assert chunker._config.max_chunk_lines == 50
        assert chunker._config.min_chunk_lines == 3
        assert chunker._config.include_preamble is False


class TestPythonASTChunkerFunctions:
    """Tests for function chunking."""

    def test_single_function_becomes_single_chunk(self):
        """A single function should become one chunk."""
        code = '''def hello():
    """Say hello."""
    print("Hello, World!")'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code, "test.py")

        # Should have function chunk (preamble skipped - too small)
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "hello"
        assert func_chunks[0].start_line == 1
        assert func_chunks[0].end_line == 3

    def test_multiple_functions_become_separate_chunks(self):
        """Multiple functions should each become separate chunks."""
        code = '''
def func_a():
    """First function."""
    return 1

def func_b():
    """Second function."""
    return 2

def func_c():
    """Third function."""
    return 3
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 3

        names = [c.name for c in func_chunks]
        assert "func_a" in names
        assert "func_b" in names
        assert "func_c" in names

    def test_async_function_chunked_correctly(self):
        """Async functions should be chunked like regular functions."""
        code = '''
async def fetch_data():
    """Fetch data asynchronously."""
    await some_api()
    return data
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "fetch_data"

    def test_large_function_split_into_parts(self):
        """Large functions should be split into multiple chunks."""
        # Create a function with 150 lines (exceeds default max of 100)
        lines = ["def big_function():"]
        lines.append('    """A very big function."""')
        for i in range(148):
            lines.append(f"    x_{i} = {i}")
        code = "\n".join(lines)

        config = PythonChunkerConfig(max_chunk_lines=50)
        chunker = PythonASTChunker(config=config)
        chunks = chunker.chunk(code, "test.py")

        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) > 1

        # First chunk should have the original name
        assert func_chunks[0].name == "big_function"

        # Subsequent chunks should have _part suffix
        for chunk in func_chunks[1:]:
            assert "_part" in chunk.name


class TestPythonASTChunkerClasses:
    """Tests for class chunking."""

    def test_class_with_methods_chunked_separately(self):
        """Class methods should become separate chunks."""
        code = '''
class Calculator:
    """A simple calculator."""

    def __init__(self):
        self.value = 0

    def add(self, x):
        """Add x to value."""
        self.value += x
        return self.value

    def subtract(self, x):
        """Subtract x from value."""
        self.value -= x
        return self.value
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        # Should have class header + methods
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        func_chunks = [c for c in chunks if c.chunk_type == "function"]

        # Class header
        assert len(class_chunks) == 1
        assert class_chunks[0].name == "Calculator"

        # Methods (qualified with class name)
        assert len(func_chunks) == 3
        method_names = [c.name for c in func_chunks]
        assert "Calculator.__init__" in method_names
        assert "Calculator.add" in method_names
        assert "Calculator.subtract" in method_names

    def test_class_without_methods(self):
        """Class with only attributes should still be chunked."""
        code = '''
class Config:
    """Configuration class."""
    DEBUG = True
    VERSION = "1.0.0"
    MAX_ITEMS = 100
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        # Should have at least one chunk for the class
        assert len(chunks) >= 1
        class_chunk = next((c for c in chunks if c.chunk_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.name == "Config"

    def test_nested_class_methods(self):
        """Methods in nested classes should be properly named."""
        code = '''
class Outer:
    """Outer class."""

    def outer_method(self):
        pass

    class Inner:
        """Inner class."""

        def inner_method(self):
            pass
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        # Should have Outer class and its method
        method_names = [c.name for c in chunks if c.chunk_type == "function"]
        assert "Outer.outer_method" in method_names


class TestPythonASTChunkerPreamble:
    """Tests for preamble extraction."""

    def test_imports_become_preamble(self):
        """Import statements should become preamble chunk."""
        code = '''
import os
import sys
from pathlib import Path
from typing import List, Dict

def main():
    pass
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        preamble = next((c for c in chunks if c.chunk_type == "preamble"), None)
        assert preamble is not None
        assert preamble.name == "imports"
        assert preamble.start_line == 1

    def test_module_docstring_included_in_preamble(self):
        """Module docstring should be part of preamble."""
        code = '''
"""
This is a module docstring.
It describes what the module does.
"""

import os

def main():
    pass
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        preamble = next((c for c in chunks if c.chunk_type == "preamble"), None)
        assert preamble is not None
        # Preamble should include docstring and imports
        assert preamble.end_line >= 6

    def test_no_preamble_when_disabled(self):
        """Preamble should not be created when disabled."""
        code = '''
import os
import sys

def main():
    pass
'''
        config = PythonChunkerConfig(include_preamble=False)
        chunker = PythonASTChunker(config=config)
        chunks = chunker.chunk(code.strip(), "test.py")

        preamble = next((c for c in chunks if c.chunk_type == "preamble"), None)
        assert preamble is None

    def test_small_preamble_skipped(self):
        """Very small preamble should be skipped."""
        code = '''
import os

def main():
    pass
'''
        config = PythonChunkerConfig(min_chunk_lines=5)
        chunker = PythonASTChunker(config=config)
        chunks = chunker.chunk(code.strip(), "test.py")

        # Single import is too small for preamble
        preamble = next((c for c in chunks if c.chunk_type == "preamble"), None)
        assert preamble is None


class TestPythonASTChunkerFallback:
    """Tests for fallback behavior."""

    def test_syntax_error_falls_back_to_line_chunking(self):
        """Invalid Python should fall back to line-based chunking."""
        code = '''
def broken(
    # Missing closing paren
    x = 1
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        # Should still produce chunks (via fallback)
        assert len(chunks) > 0
        # Fallback chunks have type "block"
        assert all(c.chunk_type == "block" for c in chunks)

    def test_file_with_only_constants_falls_back(self):
        """File with only constants should fall back to line-based."""
        code = '''
# Configuration constants
DEBUG = True
VERSION = "1.0.0"
MAX_ITEMS = 100
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        # Should produce chunks via fallback
        assert len(chunks) > 0


class TestPythonASTChunkerEdgeCases:
    """Edge case tests."""

    def test_decorated_function(self):
        """Decorated functions should include decorators in chunk."""
        code = '''@property
@staticmethod
def decorated_func():
    """A decorated function."""
    return 42'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code, "test.py")

        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        # Decorators should be included (start at line 1)
        assert func_chunks[0].start_line == 1
        assert func_chunks[0].end_line == 5

    def test_function_with_long_docstring(self):
        """Function with long docstring should stay as single chunk if within limits."""
        lines = ["def documented():", '    """']
        for i in range(20):
            lines.append(f"    Line {i} of documentation.")
        lines.append('    """')
        lines.append("    pass")
        code = "\n".join(lines)

        chunker = PythonASTChunker()
        chunks = chunker.chunk(code, "test.py")

        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "documented"

    def test_file_path_preserved(self):
        """File path should be preserved in all chunks."""
        code = '''
def func():
    pass

class MyClass:
    def method(self):
        pass
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "path/to/module.py")

        for chunk in chunks:
            assert chunk.file_path == "path/to/module.py"

    def test_chunks_have_valid_line_ranges(self):
        """All chunks should have valid line ranges."""
        code = '''
import os

def func_a():
    return 1

class MyClass:
    def method(self):
        return 2

def func_b():
    return 3
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "test.py")

        for chunk in chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.start_line <= len(code.strip().splitlines())
            assert chunk.end_line <= len(code.strip().splitlines())


class TestPythonASTChunkerRealWorld:
    """Real-world code examples."""

    def test_typical_module_structure(self):
        """Test a typical Python module with imports, class, and functions."""
        code = '''
"""
Example module for testing.
"""

import os
import sys
from typing import Optional

class DataProcessor:
    """Processes data."""

    def __init__(self, config: dict):
        """Initialize processor."""
        self.config = config
        self._cache = {}

    def process(self, data: list) -> list:
        """Process the data."""
        result = []
        for item in data:
            processed = self._transform(item)
            result.append(processed)
        return result

    def _transform(self, item):
        """Transform a single item."""
        return item * 2


def main():
    """Entry point."""
    processor = DataProcessor({})
    result = processor.process([1, 2, 3])
    print(result)


if __name__ == "__main__":
    main()
'''
        chunker = PythonASTChunker()
        chunks = chunker.chunk(code.strip(), "example.py")

        # Should have: preamble, class header, 3 methods, main function
        chunk_types = [c.chunk_type for c in chunks]

        assert "preamble" in chunk_types
        assert "class" in chunk_types
        assert chunk_types.count("function") >= 4  # 3 methods + main

        # Check method qualification
        method_names = [c.name for c in chunks if "DataProcessor." in (c.name or "")]
        assert "DataProcessor.__init__" in method_names
        assert "DataProcessor.process" in method_names
        assert "DataProcessor._transform" in method_names
