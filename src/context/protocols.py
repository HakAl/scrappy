"""
Context layer protocols.

Defines abstract interfaces for codebase context awareness, project detection,
file scanning, and git history operations.
"""

from typing import Protocol, Dict, Any, List, Optional, Set, runtime_checkable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass


@runtime_checkable
class CodebaseContextProtocol(Protocol):
    """
    Protocol for codebase context awareness.

    Abstracts codebase exploration and context management to enable
    testing without real file system access.

    Implementations:
    - CodebaseContext: Full codebase exploration and context
    - MockContext: Preset context for testing
    - NullContext: No context awareness

    Example:
        def get_context(ctx: CodebaseContextProtocol) -> str:
            ctx.explore()
            return ctx.get_context()
    """

    def explore(
        self,
        max_files: int = 100,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> None:
        """
        Explore codebase and build context.

        Args:
            max_files: Maximum files to include
            include_patterns: File patterns to include
            exclude_patterns: File patterns to exclude
        """
        ...

    def get_context(self, max_length: Optional[int] = None) -> str:
        """
        Get codebase context as formatted string.

        Args:
            max_length: Maximum context length in characters

        Returns:
            Formatted context string
        """
        ...

    def add_files(self, files: List[str]) -> None:
        """
        Add specific files to context.

        Args:
            files: List of file paths to add
        """
        ...

    def clear(self) -> None:
        """
        Clear all context.
        """
        ...

    def get_file_count(self) -> int:
        """
        Get number of files in context.

        Returns:
            Number of files
        """
        ...

    def get_summary(self) -> Dict[str, Any]:
        """
        Get context summary.

        Returns:
            Dictionary containing:
            - file_count: Number of files
            - total_size: Total size in bytes
            - languages: Languages detected
            - structure: Project structure
        """
        ...

    def set_max_file_size(self, size: int) -> None:
        """
        Set maximum file size to include.

        Args:
            size: Maximum size in bytes
        """
        ...


@runtime_checkable
class ProjectDetectorProtocol(Protocol):
    """
    Protocol for project detection.

    Abstracts project type detection and metadata extraction to enable
    testing with controlled project configurations.

    Implementations:
    - ProjectDetector: Auto-detects project type from files
    - FixedDetector: Returns preset project type for testing
    - MultiDetector: Detects multiple project types

    Example:
        def get_project_type(detector: ProjectDetectorProtocol, path: str) -> str:
            return detector.detect_type(path)
    """

    def detect_type(self, path: str) -> Optional[str]:
        """
        Detect project type from path.

        Args:
            path: Project path to analyze

        Returns:
            Project type identifier (e.g., "python", "javascript", "rust")
            None if type cannot be determined
        """
        ...

    def find_config(self, path: str, config_name: str) -> Optional[str]:
        """
        Find configuration file in project.

        Args:
            path: Project path to search
            config_name: Configuration file name

        Returns:
            Full path to config file if found, None otherwise
        """
        ...

    def get_metadata(self, path: str) -> Dict[str, Any]:
        """
        Get project metadata.

        Args:
            path: Project path to analyze

        Returns:
            Dictionary containing:
            - type: Project type
            - name: Project name
            - version: Project version (if available)
            - dependencies: List of dependencies
            - config_files: List of config file paths
        """
        ...

    def is_project_root(self, path: str) -> bool:
        """
        Check if path is a project root.

        Args:
            path: Path to check

        Returns:
            True if path appears to be project root, False otherwise
        """
        ...

    def get_supported_types(self) -> List[str]:
        """
        Get list of supported project types.

        Returns:
            List of project type identifiers
        """
        ...


@runtime_checkable
class FileScannerProtocol(Protocol):
    """
    Protocol for file scanning.

    Abstracts file system scanning to enable testing without real
    file system access and support different scanning strategies.

    Implementations:
    - FileScanner: Full file system scanning with filters
    - TestFileScanner: Returns preset file lists for testing
    - CachedFileScanner: Caches scan results

    Example:
        def scan_project(scanner: FileScannerProtocol, path: str) -> List[str]:
            return scanner.scan(path, patterns=["**/*.py"])
    """

    def scan(
        self,
        root: str,
        patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_files: Optional[int] = None,
    ) -> List[str]:
        """
        Scan directory for files matching patterns.

        Args:
            root: Root directory to scan
            patterns: File patterns to include (glob format)
            exclude_patterns: File patterns to exclude
            max_files: Maximum files to return

        Returns:
            List of file paths matching criteria
        """
        ...

    def filter(
        self,
        files: List[str],
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Filter file list by patterns.

        Args:
            files: List of file paths to filter
            include: Patterns to include
            exclude: Patterns to exclude

        Returns:
            Filtered list of file paths
        """
        ...

    def should_ignore(self, path: str) -> bool:
        """
        Check if path should be ignored.

        Args:
            path: File path to check

        Returns:
            True if path should be ignored, False otherwise
        """
        ...

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """
        Get file information.

        Args:
            path: File path

        Returns:
            Dictionary containing:
            - size: File size in bytes
            - modified: Last modified timestamp
            - extension: File extension
            - language: Detected language (if applicable)
        """
        ...

    def set_ignore_patterns(self, patterns: List[str]) -> None:
        """
        Set patterns for files/directories to ignore.

        Args:
            patterns: List of patterns to ignore
        """
        ...


@runtime_checkable
class GitHistoryProtocol(Protocol):
    """
    Protocol for git operations.

    Abstracts git history and operations to enable testing without
    real git repository access.

    Implementations:
    - GitHistory: Real git operations
    - MockGitHistory: Preset git data for testing
    - NoGitHistory: No-op for non-git projects

    Example:
        def get_changes(git: GitHistoryProtocol) -> List[str]:
            return git.get_recent_commits(5)
    """

    def get_recent_commits(
        self,
        count: int = 10,
        branch: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent commits.

        Args:
            count: Number of commits to retrieve
            branch: Branch name (None for current branch)

        Returns:
            List of commit dictionaries containing:
            - hash: Commit hash
            - author: Author name
            - date: Commit date
            - message: Commit message
        """
        ...

    def get_diff(
        self,
        commit1: Optional[str] = None,
        commit2: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """
        Get diff between commits or working tree.

        Args:
            commit1: First commit hash (None for working tree)
            commit2: Second commit hash (None for HEAD)
            file_path: Specific file to diff (None for all files)

        Returns:
            Diff text
        """
        ...

    def get_blame(self, file_path: str) -> Dict[int, Dict[str, Any]]:
        """
        Get blame information for file.

        Args:
            file_path: File path to get blame for

        Returns:
            Dictionary mapping line numbers to blame info:
            - author: Author name
            - date: Commit date
            - hash: Commit hash
            - message: Commit message
        """
        ...

    def is_git_repo(self) -> bool:
        """
        Check if current directory is a git repository.

        Returns:
            True if in git repository, False otherwise
        """
        ...

    def get_current_branch(self) -> Optional[str]:
        """
        Get current git branch name.

        Returns:
            Branch name if in git repo, None otherwise
        """
        ...

    def get_modified_files(self) -> List[str]:
        """
        Get list of modified files in working tree.

        Returns:
            List of modified file paths
        """
        ...

    def get_file_history(
        self,
        file_path: str,
        max_commits: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get commit history for specific file.

        Args:
            file_path: File path
            max_commits: Maximum commits to retrieve

        Returns:
            List of commits that modified the file
        """
        ...


# --- Semantic Search Data Classes ---


@dataclass
class CodeChunk:
    """Represents a chunk of code with line range."""
    start_line: int
    end_line: int
    file_path: Optional[str] = None


@dataclass
class SearchResult:
    """Result from semantic search."""
    chunks: List[Dict[str, Any]]  # [{path, lines: (start, end), content, score}]
    tokens_used: int
    limit_hit: Optional[str] = None  # 'token_limit' | None


# --- Semantic Search Protocols ---


@runtime_checkable
class CodeChunkerProtocol(Protocol):
    """
    Protocol for code chunking strategies.

    Abstracts code chunking to enable different strategies
    (semantic, line-based, AST-based) without changing consumers.

    Implementations:
    - SemanticCodeChunker: Semantic chunking with overlap
    - LineBasedChunker: Simple line-count chunking (future)
    - TestChunker: Fixed chunks for testing

    Example:
        def chunk_file(chunker: CodeChunkerProtocol, content: str) -> List[CodeChunk]:
            return chunker.chunk("example.py", content)
    """

    def chunk(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk code content into retrievable segments.

        Args:
            file_path: Path to the file being chunked
            content: File content to chunk

        Returns:
            List of CodeChunk objects with line ranges
        """
        ...


@runtime_checkable
class SemanticSearchProtocol(Protocol):
    """
    Protocol for semantic code search.

    Abstracts semantic search implementation to enable:
    - Swapping search backends (LanceDB, Pinecone, Chroma)
    - Testing with mock search results
    - Graceful degradation when not available

    Implementations:
    - LanceDBSearchProvider: Vector + FTS hybrid search
    - MockSearchProvider: Preset results for testing
    - NullSearchProvider: No-op for when dependencies unavailable

    Example:
        def search_code(search: SemanticSearchProtocol, query: str) -> SearchResult:
            if search.is_indexed():
                return search.search(query)
            return SearchResult(chunks=[], tokens_used=0)
    """

    def index_files(self, files: Dict[str, str], is_batch: bool = False) -> None:
        """
        Index files for semantic search.

        Args:
            files: Dict mapping file paths to content
            is_batch: If True, skip deletion detection (for batched indexing)

        Raises:
            IndexingError: If indexing fails
        """
        ...

    def search(
        self,
        query: str,
        max_results: int = 25,
        max_tokens: int = 4000
    ) -> SearchResult:
        """
        Search indexed files semantically.

        Args:
            query: Search query
            max_results: Maximum results to return
            max_tokens: Token budget for results

        Returns:
            SearchResult with chunks and metadata
        """
        ...

    def is_indexed(self) -> bool:
        """
        Check if files have been indexed.

        Returns:
            True if index exists and is usable, False otherwise
        """
        ...

    def clear_index(self) -> None:
        """Clear the search index."""
        ...


@runtime_checkable
class EmbeddingFunctionProtocol(Protocol):
    """
    Protocol for embedding generation.

    Abstracts embedding generation to enable:
    - Testing without loading real embedding models
    - Swapping embedding backends (FastEmbed, OpenAI, etc.)
    - Dependency injection for LanceDBSearchProvider

    Implementations:
    - EmbedFunction: FastEmbed-based local embeddings
    - MockEmbeddingFunction: Fixed vectors for testing

    Example:
        def embed_texts(func: EmbeddingFunctionProtocol, texts: List[str]) -> List[List[float]]:
            return func.generate_embeddings(texts)
    """

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)
        """
        ...

    def ndims(self) -> int:
        """
        Return the dimensionality of the embeddings.

        Returns:
            Number of dimensions in embedding vectors
        """
        ...


@runtime_checkable
class FileCollectorProtocol(Protocol):
    """
    Protocol for collecting files for semantic search indexing.

    Abstracts file collection to enable:
    - Respecting .gitignore via git ls-files
    - File size limits to prevent OOM
    - Binary file detection
    - Batched streaming to prevent memory spikes
    - Testing with mock file sets

    Implementations:
    - SemanticFileCollector: Git-aware with size limits and batching
    - MockFileCollector: Fixed file set for testing

    Example:
        # Batched collection (memory efficient)
        for batch in collector.collect_files_batched(batch_size=50):
            process_batch(batch)

        # Or collect all at once (backward compatibility)
        all_files = collector.collect_files()
    """

    def collect_files(self) -> Dict[str, str]:
        """
        Collect all files for semantic search indexing.

        Note: Loads all files into memory. For large codebases,
        prefer collect_files_batched() to avoid memory spikes.

        Returns:
            Dict mapping relative file paths to content
        """
        ...

    def collect_files_batched(self, batch_size: int = 50):
        """
        Collect files in batches (generator).

        Yields batches of files to prevent loading entire codebase
        into memory at once.

        Args:
            batch_size: Number of files per batch

        Yields:
            Dict[str, str]: Batch of file paths to content
        """
        ...
