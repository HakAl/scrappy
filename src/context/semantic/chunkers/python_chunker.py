"""
Python AST-based code chunker.

Chunks Python code at natural boundaries (functions, classes, methods)
using the AST module for accurate parsing.
"""

import ast
import logging
from dataclasses import dataclass
from typing import List, Optional, Set

from ...protocols import CodeChunk

logger = logging.getLogger(__name__)


@dataclass
class PythonChunkerConfig:
    """Configuration for Python AST chunker."""
    max_chunk_lines: int = 100
    min_chunk_lines: int = 3  # Lowered to include small preambles/class headers
    include_preamble: bool = True
    max_preamble_lines: int = 50


class PythonASTChunker:
    """
    Chunks Python code using AST boundaries.

    Strategy:
    1. Parse AST to find top-level definitions (functions, classes)
    2. Each function/method becomes a chunk (if under max_lines)
    3. Large functions are split at logical points
    4. Imports and module docstring become a "preamble" chunk
    5. Fall back to line-based for unparseable code

    Implements ChunkingStrategyProtocol.
    """

    def __init__(self, config: Optional[PythonChunkerConfig] = None):
        """
        Initialize Python AST chunker.

        Args:
            config: Chunker configuration (uses defaults if None)
        """
        self._config = config or PythonChunkerConfig()

    @property
    def supported_extensions(self) -> Set[str]:
        """File extensions this chunker handles."""
        return {".py", ".pyi"}

    def chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        """
        Chunk Python content using AST boundaries.

        Args:
            content: Python source code
            file_path: Path to the file (for metadata)

        Returns:
            List of CodeChunk objects with line ranges and metadata
        """
        if not content.strip():
            return []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}, falling back to line-based: {e}")
            return self._fallback_chunk(content, file_path)

        chunks = []
        lines = content.splitlines()
        total_lines = len(lines)

        # Extract preamble (imports, module docstring)
        if self._config.include_preamble:
            preamble_chunk = self._extract_preamble(tree, file_path, total_lines)
            if preamble_chunk:
                chunks.append(preamble_chunk)

        # Process top-level definitions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.extend(self._chunk_function(node, file_path, lines))
            elif isinstance(node, ast.ClassDef):
                chunks.extend(self._chunk_class(node, file_path, lines))

        # If no chunks were created (e.g., file with only imports or constants),
        # fall back to line-based chunking
        if not chunks:
            return self._fallback_chunk(content, file_path)

        return chunks

    def _extract_preamble(
        self,
        tree: ast.Module,
        file_path: str,
        total_lines: int,
    ) -> Optional[CodeChunk]:
        """
        Extract preamble chunk (imports, module docstring).

        Args:
            tree: Parsed AST
            file_path: Path to the file
            total_lines: Total lines in the file

        Returns:
            CodeChunk for preamble or None if no preamble
        """
        preamble_end = 0

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                preamble_end = node.end_lineno or node.lineno
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                # Module docstring (string constant at module level)
                if isinstance(node.value.value, str):
                    preamble_end = node.end_lineno or node.lineno
            else:
                # Stop at first non-import, non-docstring node
                break

        if preamble_end == 0:
            return None

        # Cap preamble size
        preamble_end = min(preamble_end, self._config.max_preamble_lines)

        # Don't create preamble if it's too small
        if preamble_end < self._config.min_chunk_lines:
            return None

        return CodeChunk(
            start_line=1,
            end_line=preamble_end,
            file_path=file_path,
            chunk_type="preamble",
            name="imports",
        )

    def _chunk_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        lines: List[str],
    ) -> List[CodeChunk]:
        """
        Chunk a function definition.

        Args:
            node: Function AST node
            file_path: Path to the file
            lines: Source lines

        Returns:
            List of chunks (usually 1, more if function is large)
        """
        # Include decorators in the function chunk
        start = self._get_definition_start(node)
        end = node.end_lineno or node.lineno
        func_lines = end - start + 1

        # If function fits in max_lines, keep as single chunk
        if func_lines <= self._config.max_chunk_lines:
            return [CodeChunk(
                start_line=start,
                end_line=end,
                file_path=file_path,
                chunk_type="function",
                name=node.name,
            )]

        # Large function: split into multiple chunks
        return self._split_large_block(
            start, end, file_path, "function", node.name
        )

    def _get_definition_start(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> int:
        """
        Get the starting line of a definition, including decorators.

        Args:
            node: Function or class AST node

        Returns:
            Line number of first decorator or definition
        """
        if node.decorator_list:
            return node.decorator_list[0].lineno
        return node.lineno

    def _chunk_class(
        self,
        node: ast.ClassDef,
        file_path: str,
        lines: List[str],
    ) -> List[CodeChunk]:
        """
        Chunk a class definition - each method becomes a chunk.

        Args:
            node: Class AST node
            file_path: Path to the file
            lines: Source lines

        Returns:
            List of chunks (header + methods)
        """
        chunks = []
        # Include decorators in class start
        class_start = self._get_definition_start(node)
        class_end = node.end_lineno or node.lineno

        # Find first method (considering decorators)
        first_method = None
        first_method_start = None
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                first_method = child
                first_method_start = self._get_definition_start(child)
                break

        # Class header + docstring + class-level attributes
        if first_method and first_method_start:
            header_end = first_method_start - 1
        else:
            header_end = class_end

        # Always create a class header chunk (even if small, to preserve class signature)
        header_lines = header_end - class_start + 1
        if header_lines >= 1:  # Always include class header
            # Cap header size
            header_end = min(header_end, class_start + self._config.max_chunk_lines - 1)
            chunks.append(CodeChunk(
                start_line=class_start,
                end_line=header_end,
                file_path=file_path,
                chunk_type="class",
                name=node.name,
            ))

        # Each method as separate chunk
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_chunks = self._chunk_function(child, file_path, lines)
                # Qualify method names with class name
                for mc in method_chunks:
                    mc.name = f"{node.name}.{mc.name}"
                chunks.extend(method_chunks)

        return chunks

    def _split_large_block(
        self,
        start: int,
        end: int,
        file_path: str,
        chunk_type: str,
        name: str,
    ) -> List[CodeChunk]:
        """
        Split a large block into multiple chunks.

        Args:
            start: Start line
            end: End line
            file_path: Path to the file
            chunk_type: Type of chunk
            name: Name of the definition

        Returns:
            List of chunks
        """
        chunks = []
        max_lines = self._config.max_chunk_lines
        overlap = max(5, max_lines // 10)  # 10% overlap for context

        current = start
        part = 1

        while current <= end:
            chunk_end = min(current + max_lines - 1, end)

            chunk_name = f"{name}_part{part}" if current > start else name
            chunks.append(CodeChunk(
                start_line=current,
                end_line=chunk_end,
                file_path=file_path,
                chunk_type=chunk_type,
                name=chunk_name,
            ))

            # Move forward with overlap
            current = chunk_end - overlap + 1
            part += 1

            # Prevent infinite loop
            if current <= chunks[-1].start_line:
                break

        return chunks

    def _fallback_chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        """
        Line-based fallback for unparseable code.

        Args:
            content: File content
            file_path: Path to the file

        Returns:
            List of line-based chunks
        """
        from ...code_chunker import SemanticCodeChunker

        fallback = SemanticCodeChunker(chunk_size=60, overlap=15)
        chunks = fallback.chunk(file_path, content)

        # Add metadata to fallback chunks
        for chunk in chunks:
            chunk.chunk_type = "block"

        return chunks
