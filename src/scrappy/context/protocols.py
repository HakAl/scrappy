"""
Context layer protocols.

Defines abstract interfaces for codebase context awareness, project detection,
file scanning, and git history operations.
"""

from typing import Protocol, Dict, Any, List, Optional, Set, runtime_checkable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


@runtime_checkable
class FilePrioritizerProtocol(Protocol):
    """
    Protocol for file prioritization during indexing.

    Assigns priority to files to ensure most important files
    (README, source code) are indexed before less important ones
    (tests, docs, config).

    Implementations:
    - DefaultFilePrioritizer: README > Source > Docs > Tests > Other
    - MockPrioritizer: Fixed priorities for testing

    Example:
        def index_files(prioritizer: FilePrioritizerProtocol, files: List[Path]) -> None:
            prioritized = prioritizer.sort_by_priority(files)
            for file in prioritized:
                index(file)
    """

    def get_priority(self, file_path: Path) -> int:
        """
        Assign priority to a file (lower = higher priority).

        Args:
            file_path: Path to the file

        Returns:
            Priority value (0 = highest priority)
        """
        ...

    def sort_by_priority(self, files: List[Path]) -> List[Path]:
        """
        Sort files by priority (highest priority first).

        Args:
            files: List of file paths to sort

        Returns:
            Sorted list of file paths
        """
        ...


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

    def get_search_provider(self) -> Optional['SemanticSearchProtocol']:
        """
        Get the semantic search provider if available.

        Returns:
            SemanticSearchProtocol instance or None if not available
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
    """
    Represents a chunk of code with line range.

    Attributes:
        start_line: 1-indexed start line number
        end_line: 1-indexed end line number (inclusive)
        file_path: Path to the source file
        chunk_type: Type of chunk (e.g., "function", "class", "preamble", "block")
        name: Qualified name (e.g., "MyClass.my_method", "helper_func")
    """
    start_line: int
    end_line: int
    file_path: Optional[str] = None
    chunk_type: Optional[str] = None
    name: Optional[str] = None


@dataclass
class SearchResult:
    """Result from semantic search."""
    chunks: List[Dict[str, Any]]  # [{path, lines: (start, end), content, score}]
    tokens_used: int
    limit_hit: Optional[str] = None  # 'token_limit' | None


@dataclass
class ScoredChunk:
    """
    A code chunk with detailed scoring breakdown.

    Used by ResultRankerProtocol to enable transparent and
    configurable result ranking.
    """
    file_path: str
    start_line: int
    end_line: int
    content: str
    vector_score: float = 0.0     # Semantic similarity (0-1, higher is better)
    fts_score: float = 0.0        # Full-text keyword match score (0+)
    final_score: float = 0.0      # Combined/weighted score
    match_details: Dict[str, Any] = None  # type: ignore

    def __post_init__(self):
        if self.match_details is None:
            self.match_details = {}


@dataclass
class RankingConfig:
    """
    Configuration for search result ranking.

    Controls how vector similarity and keyword scores are combined,
    plus additional boost factors for exact matches and path matches.
    """
    vector_weight: float = 0.6       # Weight for semantic similarity
    fts_weight: float = 0.3          # Weight for keyword matches
    exact_match_boost: float = 0.5   # Boost for exact query substring in content
    path_match_boost: float = 0.2    # Boost if query terms appear in file path
    # Future: recency_weight for recently modified files


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
class ChunkingStrategyProtocol(Protocol):
    """
    Protocol for language-specific chunking strategies.

    Enables AST-aware chunking for supported languages while
    falling back to line-based chunking for unsupported ones.

    Implementations:
    - PythonASTChunker: Python AST-based chunking
    - CompositeCodeChunker: Routes to language-specific strategies

    Example:
        def chunk_python(strategy: ChunkingStrategyProtocol, code: str) -> List[CodeChunk]:
            if ".py" in strategy.supported_extensions:
                return strategy.chunk(code, "example.py")
    """

    @property
    def supported_extensions(self) -> Set[str]:
        """
        File extensions this strategy handles.

        Returns:
            Set of extensions (e.g., {".py", ".pyi"})
        """
        ...

    def chunk(self, content: str, file_path: str) -> List[CodeChunk]:
        """
        Chunk content using language-aware boundaries.

        Args:
            content: File content to chunk
            file_path: Path to the file (for context)

        Returns:
            List of CodeChunk objects with line ranges and metadata
        """
        ...


@runtime_checkable
class ResultRankerProtocol(Protocol):
    """
    Protocol for ranking search results.

    Enables customizable scoring and ranking of search results
    based on multiple signals (vector similarity, keyword matches,
    exact matches, path matches).

    Implementations:
    - DefaultResultRanker: Weighted combination of signals
    - MockResultRanker: Returns candidates unchanged for testing

    Example:
        def rank_results(
            ranker: ResultRankerProtocol,
            query: str,
            candidates: List[ScoredChunk]
        ) -> List[ScoredChunk]:
            return ranker.rank(query, candidates)
    """

    def rank(
        self,
        query: str,
        candidates: List[ScoredChunk],
        config: Optional[RankingConfig] = None,
    ) -> List[ScoredChunk]:
        """
        Re-rank candidates based on multiple signals.

        Args:
            query: Original search query
            candidates: Raw results from search backend
            config: Optional ranking configuration

        Returns:
            Re-ranked list of chunks (highest score first)
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

    def cleanup_deleted_files(self, current_files: Set[str]) -> int:
        """
        Remove index entries for files that no longer exist.

        Should be called AFTER batched indexing completes with the full
        set of currently-existing file paths.

        Args:
            current_files: Set of normalized POSIX file paths that currently exist

        Returns:
            Number of stale entries removed
        """
        ...

    def remove_files(self, files: Set[str]) -> int:
        """
        Remove specific files from the index.

        More efficient than cleanup_deleted_files when you already know
        which files were deleted (e.g., from staleness detection).

        Args:
            files: Set of file paths to remove from index

        Returns:
            Number of entries removed
        """
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
    - File size limits to prevent OOM
    - Binary file detection
    - Batched streaming to prevent memory spikes
    - Testing with mock file sets

    Implementations:
    - SemanticFileCollector: Collects files with size limits and batching
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


@runtime_checkable
class SemanticSearchManagerProtocol(Protocol):
    """
    Protocol for managing semantic search lifecycle.

    Coordinates semantic search initialization, indexing, and search operations.
    Separates the complexity of background initialization, event handling,
    and progress reporting from CodebaseContext.

    Single Responsibility: Coordinate semantic search lifecycle.

    Implementations:
    - SemanticSearchManager: Full lifecycle management with background init
    - MockSemanticSearchManager: Preset results for testing
    - NullSemanticSearchManager: No-op for when semantic search unavailable

    Example:
        def setup_search(manager: SemanticSearchManagerProtocol) -> None:
            manager.start_background_init()
            # Do other work...
            if manager.is_ready():
                result = manager.search("error handling")
    """

    def start_background_init(self) -> None:
        """
        Start background initialization of semantic search dependencies.

        Non-blocking - returns immediately. Use is_ready() or
        process_events() to check completion status.
        """
        ...

    def is_ready(self) -> bool:
        """
        Check if semantic search is ready to use.

        Returns:
            True if initialized and indexed, False otherwise
        """
        ...

    def get_status(self) -> Optional[str]:
        """
        Get human-readable initialization status.

        Returns:
            Status string (e.g., "Loading model...", "Ready", "Failed")
            None if no initializer configured
        """
        ...

    def search(self, query: str, max_tokens: int = 4000) -> Optional['SearchResult']:
        """
        Search indexed codebase semantically.

        Args:
            query: Search query
            max_tokens: Maximum tokens in results

        Returns:
            SearchResult if available, None if not ready
        """
        ...

    def index_files(self, file_collector: 'FileCollectorProtocol') -> None:
        """
        Index files for semantic search.

        Args:
            file_collector: Collector providing files to index
        """
        ...

    def refresh_files(self, changed: Set[str]) -> None:
        """
        Incrementally re-index specific changed files.

        Enables efficient staleness-driven re-indexing by only processing
        files that have been added or modified since the last index.

        Args:
            changed: Set of file paths (relative to project root) that need re-indexing

        Raises:
            ValueError: If changed is empty
        """
        ...

    def remove_deleted_files(self, deleted: Set[str]) -> int:
        """
        Remove deleted files from the semantic search index.

        Enables efficient staleness-driven cleanup by removing specific
        files that have been deleted since the last index.

        Args:
            deleted: Set of file paths (relative to project root) to remove

        Returns:
            Number of entries removed from the index
        """
        ...

    def process_events(self) -> int:
        """
        Process pending background events.

        Should be called periodically from main thread.

        Returns:
            Number of events processed
        """
        ...

    def set_progress_callback(self, callback) -> None:
        """
        Set callback for progress updates during indexing.

        Args:
            callback: Function taking a string message
        """
        ...

    def set_file_collector_callback(
        self,
        callback  # Optional[Callable[[], Optional['FileCollectorProtocol']]]
    ) -> None:
        """
        Set callback for getting file collector during auto-indexing.

        When INIT_COMPLETE event is received, this callback will be invoked
        to get a file collector for auto-indexing.

        Args:
            callback: Function returning FileCollectorProtocol or None
        """
        ...

    def shutdown(self) -> None:
        """Signal background tasks to stop and clean up resources."""
        ...


@runtime_checkable
class ContextAugmenterProtocol(Protocol):
    """
    Protocol for augmenting prompts with codebase context.

    Builds context blocks for prompt augmentation from various
    sources (summary, structure, git history, semantic search).

    Single Responsibility: Format context for prompts.

    Implementations:
    - ContextAugmenter: Full context augmentation
    - MockContextAugmenter: Fixed context for testing
    - NullContextAugmenter: Returns prompts unchanged

    Example:
        def enhance_prompt(augmenter: ContextAugmenterProtocol, prompt: str) -> str:
            return augmenter.augment(prompt)
    """

    def augment(self, prompt: str, include_files: bool = False) -> str:
        """
        Augment a prompt with codebase context.

        Args:
            prompt: Original user prompt
            include_files: Whether to include file listings

        Returns:
            Augmented prompt with context blocks
        """
        ...

    def get_relevant_context(self, query: str, max_tokens: int = 4000) -> str:
        """
        Get context relevant to a specific query.

        Uses semantic search if available, falls back to keyword matching.

        Args:
            query: Query to find relevant context for
            max_tokens: Maximum tokens to return

        Returns:
            Relevant context string
        """
        ...


# --- Index State Management ---


@dataclass
class IndexState:
    """Persisted index metadata."""
    last_indexed: datetime
    total_chunks: int
    total_files: int
    index_version: str
    file_hashes: Dict[str, str]  # path -> content_hash


@dataclass
class ChangeMetrics:
    """Metrics about what changed since last index."""
    new_files: int
    modified_files: int
    deleted_files: int
    estimated_chunks: int
    total_bytes_changed: int


class IndexingDecision(Enum):
    FULL_INDEX = "full"
    INCREMENTAL_UPDATE = "incremental"
    SKIP = "skip"


@runtime_checkable
class IndexStateProtocol(Protocol):
    """Single responsibility: Persist and retrieve index state."""

    def load(self) -> Optional[IndexState]: ...
    def save(self, state: IndexState) -> None: ...
    def clear(self) -> None: ...


@runtime_checkable
class IndexingDecisionProtocol(Protocol):
    """Single responsibility: Decide what indexing action to take."""

    def decide(
        self,
        saved_state: Optional[IndexState],
        current_metrics: ChangeMetrics,
    ) -> IndexingDecision: ...

    def should_show_progress(self, metrics: ChangeMetrics) -> bool: ...


# --- Staleness Detection ---


class TimeProviderProtocol(Protocol):
    """
    Protocol for time operations.

    Abstracts time.time() to enable testing with controlled time values.

    Implementations:
    - SystemTimeProvider: Uses real system time
    - FakeTimeProvider: Controllable time for testing

    Example:
        def check_debounce(provider: TimeProviderProtocol) -> bool:
            return provider.now_ms() > last_check + debounce_ms
    """

    def now_ms(self) -> float:
        """
        Get current time in milliseconds.

        Returns:
            Current time in milliseconds since epoch
        """
        ...


class FingerprintScannerProtocol(Protocol):
    """
    Protocol for scanning files for fingerprinting.

    Abstracts file system access to enable testing without real file operations.
    Used by StalenessChecker to get file metadata (mtime_ns, size) for change detection.

    Note: This is distinct from FileScannerProtocol which handles pattern-based
    file discovery. This protocol focuses on metadata retrieval for fingerprinting.

    Implementations:
    - FileSystemScanner: Real file system access
    - FakeFileScanner: Controllable file state for testing
    """

    def scan_files(self, root: Path) -> Set[str]:
        """
        Scan directory for all files.

        Args:
            root: Root directory to scan

        Returns:
            Set of relative file paths (forward-slash normalized)
        """
        ...

    def scan_directory_mtimes(self, root: Path) -> Dict[str, float]:
        """
        Scan directory mtimes for quick change detection.

        Args:
            root: Root directory to scan

        Returns:
            Dict mapping directory relative path to mtime (nanoseconds)
        """
        ...

    def get_mtime_ns(self, file_path: Path) -> int:
        """
        Get file modification time in nanoseconds.

        Args:
            file_path: Absolute path to file

        Returns:
            Modification time in nanoseconds for maximum precision
        """
        ...

    def get_size(self, file_path: Path) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Absolute path to file

        Returns:
            File size in bytes
        """
        ...

    def get_fingerprint(self, file_path: Path) -> tuple:
        """
        Get file fingerprint as (mtime_ns, size) tuple.

        Args:
            file_path: Absolute path to file

        Returns:
            Tuple of (mtime_ns, size) for change detection
        """
        ...


@dataclass
class StalenessReport:
    """
    Report of file changes detected by staleness checking.

    Attributes:
        added: Set of file paths that are new since last check
        modified: Set of file paths that have changed since last check
        deleted: Set of file paths that no longer exist
    """
    added: Set[str]
    modified: Set[str]
    deleted: Set[str]

    @property
    def is_stale(self) -> bool:
        """Check if any changes were detected."""
        return bool(self.added or self.modified or self.deleted)

    @property
    def total_changes(self) -> int:
        """Get total number of changed files."""
        return len(self.added) + len(self.modified) + len(self.deleted)


@runtime_checkable
class StalenessCheckerProtocol(Protocol):
    """
    Protocol for detecting file changes via fingerprinting.

    Abstracts staleness detection to enable:
    - Testing without real file system access
    - Debounced checking to avoid rapid re-scans
    - Efficient change detection via mtime + size fingerprints

    Single Responsibility: Detect when files have changed.

    Implementations:
    - StalenessChecker: mtime + size fingerprinting with debounce
    - MockStalenessChecker: Preset staleness reports for testing
    - AlwaysFreshChecker: Always reports no changes

    Example:
        def check_and_reindex(checker: StalenessCheckerProtocol) -> None:
            report = checker.check_staleness()
            if report.is_stale:
                reindex_files(report.added | report.modified)
                checker.update_fingerprints()
    """

    def get_fingerprints(self) -> Dict[str, tuple]:
        """
        Get current stored fingerprints.

        Returns:
            Dict mapping file paths to fingerprint tuples (mtime, size)
        """
        ...

    def check_staleness(self) -> StalenessReport:
        """
        Check for file changes since last update.

        Compares current file system state against stored fingerprints.
        Respects debounce timing to avoid rapid re-checks.

        Returns:
            StalenessReport with sets of added/modified/deleted files
        """
        ...

    def update_fingerprints(self, staleness_report: Optional[StalenessReport] = None) -> None:
        """
        Update stored fingerprints to current file system state.

        Args:
            staleness_report: Optional report of changes from check_staleness().
                             If provided, only updates fingerprints for files in the report
                             (incremental update). If None, scans all files (full update).

        Should be called after successfully re-indexing changed files.
        """
        ...


# --- Re-index Operations ---


@dataclass
class ReindexResult:
    """
    Result from a blocking re-index operation.

    Attributes:
        success: Whether the re-index completed successfully
        files_processed: Number of files that were processed
        timed_out: Whether the operation timed out
        error: Error message if operation failed, None otherwise
    """
    success: bool
    files_processed: int
    timed_out: bool
    error: Optional[str] = None


@runtime_checkable
class ReindexCallbackProtocol(Protocol):
    """
    Protocol for receiving re-index progress callbacks.

    Enables UI components to track and display re-index progress
    without coupling to specific UI implementations.

    Single Responsibility: Notify about re-index lifecycle events.

    Implementations:
    - ReindexActivityCallback: Bridges to ActivityIndicator via messages
    - MockReindexCallback: No-op for testing
    - LoggingReindexCallback: Logs progress to console

    Example:
        def reindex_with_progress(callback: ReindexCallbackProtocol) -> None:
            callback.on_start()
            for i, file in enumerate(files):
                process(file)
                callback.on_progress(i + 1, len(files))
            callback.on_complete(ReindexResult(True, len(files), False))
    """

    def on_start(self) -> None:
        """Called when re-index operation starts."""
        ...

    def on_progress(self, files_processed: int, total_files: int) -> None:
        """
        Called periodically during re-index.

        Args:
            files_processed: Number of files processed so far
            total_files: Total number of files to process
        """
        ...

    def on_complete(self, result: ReindexResult) -> None:
        """
        Called when re-index operation completes.

        Args:
            result: Result of the re-index operation
        """
        ...

    def on_timeout(self) -> None:
        """Called when re-index operation times out."""
        ...
