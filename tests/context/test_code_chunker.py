import pytest

# Import actual protocol classes
from scrappy.context.code_chunker import SemanticCodeChunker


class TestSemanticCodeChunker:
    """Test suite for SemanticCodeChunker class."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        chunker = SemanticCodeChunker()
        assert chunker._chunk_size == 250
        assert chunker._overlap == 30

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        chunker = SemanticCodeChunker(chunk_size=100, overlap=15)
        assert chunker._chunk_size == 100
        assert chunker._overlap == 15


    def test_chunk_empty_content(self):
        """Test chunking empty or whitespace-only content."""
        chunker = SemanticCodeChunker(chunk_size=10, overlap=2)

        # Empty string
        result = chunker.chunk("test.py", "")
        assert result == []

        # Whitespace only
        result = chunker.chunk("test.py", "   \n  \t  \n  ")
        assert result == []

    def test_chunk_single_chunk(self):
        """Test chunking content smaller than chunk_size."""
        chunker = SemanticCodeChunker(chunk_size=10, overlap=2)
        content = "line1\nline2\nline3"  # 3 lines

        result = chunker.chunk("test.py", content)

        assert len(result) == 1
        assert result[0].start_line == 1
        assert result[0].end_line == 3
        assert result[0].file_path == "test.py"

    def test_chunk_multiple_chunks_with_overlap(self):
        """Test chunking with multiple chunks and overlap."""
        chunker = SemanticCodeChunker(chunk_size=5, overlap=2)
        content = "\n".join([f"line{i}" for i in range(1, 13)])  # 12 lines

        result = chunker.chunk("test.py", content)

        # Algorithm: step = chunk_size - overlap = 5 - 2 = 3
        # i=0: start=1, end=5, i+=3 -> i=3
        # i=3: start=4, end=8, i+=3 -> i=6
        # i=6: start=7, end=11, i+=3 -> i=9
        # i=9: start=10, end=12, i+=3 -> i=12 (exit)
        # Creates 4 chunks with the trailing partial chunk

        assert len(result) == 4

        # First chunk
        assert result[0].start_line == 1
        assert result[0].end_line == 5

        # Second chunk (overlaps lines 4-5 with chunk 1)
        assert result[1].start_line == 4
        assert result[1].end_line == 8

        # Third chunk (overlaps lines 7-8 with chunk 2)
        assert result[2].start_line == 7
        assert result[2].end_line == 11

        # Fourth chunk (trailing partial, overlaps lines 10-11 with chunk 3)
        assert result[3].start_line == 10
        assert result[3].end_line == 12

    def test_chunk_exact_fit_no_remainder(self):
        """Test chunking when content fits exactly into chunks."""
        chunker = SemanticCodeChunker(chunk_size=4, overlap=1)
        content = "\n".join([f"line{i}" for i in range(1, 9)])  # 8 lines

        result = chunker.chunk("test.py", content)

        # Algorithm: step = chunk_size - overlap = 4 - 1 = 3
        # i=0: start=1, end=4, i+=3 -> i=3
        # i=3: start=4, end=7, i+=3 -> i=6
        # i=6: start=7, end=8, i+=3 -> i=9 (exit)
        # Creates 3 chunks

        assert len(result) == 3
        assert result[0].start_line == 1
        assert result[0].end_line == 4
        assert result[1].start_line == 4
        assert result[1].end_line == 7
        assert result[2].start_line == 7
        assert result[2].end_line == 8

    def test_chunk_large_content(self):
        """Test chunking large content with default settings."""
        chunker = SemanticCodeChunker(chunk_size=250, overlap=30)
        # Create content with 1000 lines
        content = "\n".join([f"line{i}" for i in range(1, 1001)])

        result = chunker.chunk("large_file.py", content)

        # Should create multiple chunks
        assert len(result) > 1

        # Verify first chunk
        assert result[0].start_line == 1
        assert result[0].end_line == 250

        # Verify last chunk includes remaining lines
        assert result[-1].end_line == 1000

        # Verify overlap is working
        for i in range(1, len(result)):
            prev_chunk_end = result[i - 1].end_line
            curr_chunk_start = result[i].start_line
            overlap_size = prev_chunk_end - curr_chunk_start + 1
            assert overlap_size == 30

    def test_chunk_different_file_paths(self):
        """Test that file_path is correctly set in chunks."""
        chunker = SemanticCodeChunker(chunk_size=5, overlap=1)
        content = "\n".join([f"line{i}" for i in range(1, 8)])

        result1 = chunker.chunk("path/to/file1.py", content)
        result2 = chunker.chunk("path/to/file2.js", content)

        assert all(chunk.file_path == "path/to/file1.py" for chunk in result1)
        assert all(chunk.file_path == "path/to/file2.js" for chunk in result2)

    def test_chunk_content_with_empty_lines(self):
        """Test chunking content with empty lines."""
        chunker = SemanticCodeChunker(chunk_size=5, overlap=1)
        content = "line1\n\nline3\n\nline5\nline6\n\nline8"

        result = chunker.chunk("test.py", content)

        # Empty lines should be counted as lines
        assert len(result) >= 1
        assert result[0].start_line == 1

        # Verify content is preserved in line count
        expected_lines = len(content.splitlines())
        assert result[-1].end_line == expected_lines


    def test_edge_case_zero_overlap(self):
        """Test chunking with zero overlap."""
        chunker = SemanticCodeChunker(chunk_size=3, overlap=0)
        content = "\n".join([f"line{i}" for i in range(1, 8)])  # 7 lines

        result = chunker.chunk("test.py", content)

        # Should create 3 chunks with no overlap
        assert len(result) == 3
        assert result[0].start_line == 1
        assert result[0].end_line == 3
        assert result[1].start_line == 4  # No overlap
        assert result[1].end_line == 6
        assert result[2].start_line == 7  # No overlap
        assert result[2].end_line == 7

    def test_chunk_single_line_content(self):
        """Test chunking single line content."""
        chunker = SemanticCodeChunker(chunk_size=10, overlap=2)
        content = "single line"

        result = chunker.chunk("test.py", content)

        assert len(result) == 1
        assert result[0].start_line == 1
        assert result[0].end_line == 1

    def test_chunk_performance_large_file(self):
        """Test performance with a very large file."""
        chunker = SemanticCodeChunker(chunk_size=100, overlap=20)
        # Create content with 10,000 lines
        content = "\n".join([f"def function_{i}():\n    return {i}" for i in range(5000)])

        import time
        start_time = time.time()
        result = chunker.chunk("large_file.py", content)
        end_time = time.time()

        # Should complete reasonably quickly (under 1 second for 10k lines)
        assert end_time - start_time < 1.0
        assert len(result) > 0
        assert result[-1].end_line == len(content.splitlines())


class TestSemanticCodeChunkerIntegration:
    """Integration tests for SemanticCodeChunker with realistic code content."""

    def test_chunk_python_code(self):
        """Test chunking actual Python code content."""
        chunker = SemanticCodeChunker(chunk_size=10, overlap=2)

        python_code = '''
def hello_world():
    """A simple hello world function."""
    print("Hello, World!")

class Calculator:
    """A simple calculator class."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def subtract(self, a, b):
        """Subtract two numbers."""
        return a - b

if __name__ == "__main__":
    calc = Calculator()
    result = calc.add(5, 3)
    print(f"5 + 3 = {result}")
'''

        result = chunker.chunk("calculator.py", python_code.strip())

        # Should create multiple chunks for this code
        assert len(result) >= 2

        # Verify all chunks have valid line ranges
        for chunk in result:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.file_path == "calculator.py"

    def test_chunk_javascript_code(self):
        """Test chunking JavaScript code content."""
        chunker = SemanticCodeChunker(chunk_size=8, overlap=2)

        js_code = '''
function greet(name) {
    console.log(`Hello, ${name}!`);
}

class Person {
    constructor(name, age) {
        this.name = name;
        this.age = age;
    }

    introduce() {
        console.log(`Hi, I'm ${this.name} and I'm ${this.age} years old.`);
    }
}

const person = new Person("Alice", 30);
person.introduce();
'''

        result = chunker.chunk("app.js", js_code.strip())

        assert len(result) >= 2
        for chunk in result:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.file_path == "app.js"


if __name__ == "__main__":
    pytest.main([__file__])
