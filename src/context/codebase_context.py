"""
Codebase context management for the LLM Agent Team.

Provides automatic project exploration and context augmentation for prompts.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .file_scanner import FileScanner

logger = logging.getLogger(__name__)
from .cache import ContextCache
from .platform import PlatformDetector
from .git_history import GitHistoryReader
from .project_detector import ProjectDetector
from .config_loader import get_truncation_defaults, get_extensions_config, get_paths_config
from ..infrastructure.protocols import PathProviderProtocol, BackgroundInitializerProtocol
from ..infrastructure.paths import ScrappyPathProvider


class CodebaseContext:
    """
    Manages codebase knowledge and context for intelligent prompt augmentation.

    Usage:
        context = CodebaseContext("/path/to/project")
        context.explore()  # Scan and analyze the codebase

        # Get context for prompts
        augmented_prompt = context.augment_prompt("Fix the bug in auth")
    """

    def __init__(
        self,
        project_path: Optional[str] = None,
        file_scanner: Optional[FileScanner] = None,
        cache: Optional[ContextCache] = None,
        platform_detector: Optional[PlatformDetector] = None,
        git_history_reader: Optional[GitHistoryReader] = None,
        project_detector: Optional[ProjectDetector] = None,
        auto_load_cache: bool = False,
        semantic_initializer: Optional[BackgroundInitializerProtocol] = None,
        path_provider: Optional[PathProviderProtocol] = None,
        file_collector: Optional['FileCollectorProtocol'] = None,
    ):
        """
        Initialize codebase context (dependencies only - NO file I/O by default).

        Call restore_from_cache() after construction to load cached context from disk.

        Args:
            project_path: Path to project root. Defaults to current directory.
            file_scanner: Injectable file scanner (default: creates new FileScanner)
            cache: Injectable context cache (default: creates new ContextCache)
            platform_detector: Injectable platform detector (default: creates new PlatformDetector)
            git_history_reader: Injectable git history reader (default: creates new GitHistoryReader)
            project_detector: Injectable project detector (default: creates from project_path)
            auto_load_cache: If True, automatically load cache in constructor (for backwards compatibility)
            semantic_initializer: Background initializer for semantic search.
            path_provider: Path provider for data files (auto-creates if None)
            file_collector: Injectable file collector for semantic search (default: creates SemanticFileCollector)
        """
        # Store config for factory methods
        self._initial_project_path = project_path

        self.project_path = Path(project_path or ".").resolve()

        # Validate path (path checks are minimal side effects, needed for safety)
        self._path_valid = True
        if not self.project_path.exists():
            logger.warning(f"Project path does not exist: {self.project_path}")
            self._path_valid = False
        elif not self.project_path.is_dir():
            logger.warning(f"Project path is not a directory: {self.project_path}")
            self._path_valid = False

        self.summary: Optional[str] = None
        self.structure: dict = {}
        self.key_files: dict = {}
        self.file_index: dict = {}
        self.git_history: dict = {}  # Git history info
        self.explored_at: Optional[datetime] = None

        # Path provider for data files
        self._path_provider = path_provider or ScrappyPathProvider(self.project_path)

        # Component instances using factory methods
        self._file_scanner = file_scanner or self._create_default_file_scanner()
        self._cache = cache or self._create_default_cache()
        self._platform_detector = platform_detector or self._create_default_platform_detector()
        self._git_history_reader = git_history_reader or self._create_default_git_history_reader()
        self._project_detector = project_detector or self._create_default_project_detector()

        # Semantic search - uses background initializer pattern
        self._semantic_search = None  # Cached result from semantic_initializer
        self._semantic_initializer = semantic_initializer  # Background initializer
        self._semantic_search_attempted = False  # Track if we tried to create it
        self._file_collector = file_collector  # Injected file collector for semantic search
        self._indexing_progress_callback = None  # Callback for indexing progress updates

        # Auto-load cache if requested (for backwards compatibility)
        if auto_load_cache:
            self._load_cache()

    @property
    def cache_file(self) -> Path:
        """Get path to context cache file."""
        return self._path_provider.context_file()

    def restore_from_cache(self):
        """
        Restore context from cached file on disk.

        Call this after construction to load previously cached context data.

        Returns:
            self (for method chaining)
        """
        self._load_cache()
        return self

    # Factory methods for default dependencies

    def _create_default_file_scanner(self) -> FileScanner:
        """Create default file scanner."""
        return FileScanner()

    def _create_default_cache(self) -> ContextCache:
        """Create default context cache."""
        return ContextCache()

    def _create_default_platform_detector(self) -> PlatformDetector:
        """Create default platform detector."""
        return PlatformDetector()

    def _create_default_git_history_reader(self) -> GitHistoryReader:
        """Create default git history reader."""
        return GitHistoryReader()

    def _create_default_project_detector(self) -> ProjectDetector:
        """Create default project detector."""
        return ProjectDetector(self.project_path)

    def _create_default_file_collector(self) -> 'FileCollectorProtocol':
        """
        Create default file collector for semantic search.

        Returns:
            SemanticFileCollector with default configuration
        """
        try:
            from .semantic import SemanticFileCollector
            return SemanticFileCollector(self.project_path)
        except ImportError:
            # If semantic search dependencies not available, return a dummy collector
            logger.debug("Semantic search dependencies not available")
            return None

    def _create_default_semantic_initializer(self) -> Optional[BackgroundInitializerProtocol]:
        """
        Create default semantic search initializer.

        Returns:
            SemanticSearchInitializer if dependencies available, NullInitializer otherwise
        """
        try:
            from .semantic.initializer import SemanticSearchInitializer
            logger.debug("Creating SemanticSearchInitializer")
            return SemanticSearchInitializer(self.project_path)
        except ImportError as e:
            logger.debug(f"Semantic search dependencies not available: {e}")
            from .semantic.initializer import NullInitializer
            return NullInitializer()

    def set_indexing_progress_callback(self, callback) -> None:
        """
        Set callback for indexing progress updates.

        The callback will be called with status messages during file indexing.

        Args:
            callback: Function that takes a string message parameter
        """
        self._indexing_progress_callback = callback

    def _notify_indexing_progress(self, message: str) -> None:
        """
        Notify registered callback of indexing progress.

        Args:
            message: Progress message
        """
        if self._indexing_progress_callback:
            try:
                self._indexing_progress_callback(message)
            except Exception as e:
                logger.debug(f"Error in indexing progress callback: {e}")

    def start_background_initialization(self) -> None:
        """
        Start background initialization tasks (semantic search model loading, etc.).

        This is non-blocking and returns immediately. The actual work happens
        in background threads.

        Call this early in application startup to pre-load heavy dependencies.
        """
        if self._semantic_initializer:
            logger.debug("Starting background semantic search initialization")
            self._semantic_initializer.start()

            # Register callback to auto-index when initialization completes
            self._semantic_initializer.wait_with_callback(
                self._on_semantic_search_ready
            )
        else:
            logger.debug("No semantic initializer configured")

    def get_semantic_initialization_status(self) -> Optional[str]:
        """
        Get human-readable status of semantic search initialization.

        Returns:
            Status string if initializer exists, None otherwise
        """
        if self._semantic_initializer:
            return self._semantic_initializer.get_status()
        return None

    def is_semantic_search_ready(self) -> bool:
        """
        Check if semantic search is ready to use.

        Returns:
            True if semantic search is available and ready
        """
        if self._semantic_search:
            return True  # Already initialized and cached
        if self._semantic_initializer:
            return self._semantic_initializer.is_complete() and \
                   self._semantic_initializer.get_error() is None
        return False

    def _ensure_semantic_search(self) -> Optional['SemanticSearchProtocol']:
        """
        Return semantic search provider if available.

        Checks cached result from background initializer.

        Returns:
            SemanticSearchProtocol instance or None if not available
        """
        # Check if already cached
        if self._semantic_search:
            return self._semantic_search

        # Check if background initializer has completed
        if self._semantic_initializer and self._semantic_initializer.is_complete():
            result = self._semantic_initializer.get_result()
            if result:
                # Cache the result for future calls
                self._semantic_search = result
                return result
            else:
                error = self._semantic_initializer.get_error()
                logger.debug(f"Semantic search initialization failed: {error}")
                return None

        return None

    def is_explored(self) -> bool:
        """Check if the codebase has been explored."""
        return self.explored_at is not None

    def explore(self, force: bool = False) -> dict:
        """
        Explore the codebase and build context.

        Args:
            force: Force re-exploration even if cache exists

        Returns:
            Dict with exploration results
        """
        if self.is_explored() and not force:
            return {
                'status': 'cached',
                'explored_at': self.explored_at.isoformat(),
                'summary': self.summary
            }

        # Scan for source files
        self.file_index = self._scan_files()

        # Analyze structure
        self.structure = self._analyze_structure()

        # Read key files
        self.key_files = self._read_key_files()

        # Get git history if available
        if self.structure.get('has_git'):
            self.git_history = self._get_git_history()

        # Note: Semantic search indexing happens automatically after model loads
        # (triggered by background initialization callback, not during explore)

        # Mark exploration time (summary will be generated when needed)
        self.explored_at = datetime.now()

        # Save to cache
        self._save_cache()

        return {
            'status': 'explored',
            'explored_at': self.explored_at.isoformat(),
            'total_files': self.structure.get('total_files', 0),
            'file_types': self.structure.get('by_type', {}),
            'directories': self.structure.get('directories', []),
            'has_git_history': bool(self.git_history),
            'semantic_search_enabled': self._semantic_search is not None,
        }

    def generate_summary(self, llm_func) -> str:
        """
        Generate a natural language summary using an LLM.

        Args:
            llm_func: Function that takes a prompt and returns response text

        Returns:
            Generated summary string
        """
        if not self.is_explored():
            self.explore()

        # Build context for LLM
        context_parts = [
            f"Project: {self.project_path.name}",
            f"Total files: {self.structure.get('total_files', 0)}",
            f"File types: {', '.join(f'{k}={v}' for k, v in self.structure.get('by_type', {}).items() if v > 0)}",
            f"Directories: {', '.join(self.structure.get('directories', []))}",
        ]

        # Add project indicators
        if self.structure.get('has_readme'):
            context_parts.append("Has README")
        if self.structure.get('has_requirements'):
            context_parts.append("Python project (requirements.txt)")
        if self.structure.get('has_package_json'):
            context_parts.append("Node.js project")
        if self.structure.get('has_pyproject'):
            context_parts.append("Modern Python (pyproject.toml)")
        if self.structure.get('has_git'):
            context_parts.append("Version controlled with Git")

        # Add git history info
        git_context = ""
        if self.git_history:
            git_parts = []
            if self.git_history.get('current_branch'):
                git_parts.append(f"Current branch: {self.git_history['current_branch']}")
            if self.git_history.get('recent_commits'):
                commits = self.git_history['recent_commits'][:5]
                git_parts.append("Recent commits:\n" + "\n".join(f"  {c}" for c in commits))
            if self.git_history.get('top_contributors'):
                contribs = [f"{c['name']} ({c['commits']} commits)" for c in self.git_history['top_contributors'][:3]]
                git_parts.append(f"Top contributors: {', '.join(contribs)}")
            if git_parts:
                git_context = "\n\nGit History:\n" + "\n".join(git_parts)

        # Build file contents section (limited)
        file_contents = ""
        defaults = get_truncation_defaults()
        truncate_limit = defaults['research_large']
        for filename, content in list(self.key_files.items())[:5]:
            # Truncate to avoid token explosion
            truncated = content[:truncate_limit] if len(content) > truncate_limit else content
            file_contents += f"\n--- {filename} ---\n{truncated}\n"

        prompt = f"""Analyze this codebase and provide a concise technical summary.

{chr(10).join(context_parts)}
{git_context}

Key Files:
{file_contents}

Provide a brief summary (3-5 sentences) covering:
1. What this project does
2. Main technologies/frameworks
3. Code organization pattern
4. Development activity (if git history available)

Be concise and technical. No fluff."""

        self.summary = llm_func(prompt)
        self._save_cache()

        return self.summary

    def augment_prompt(self, user_prompt: str, include_files: bool = False) -> str:
        """
        Augment a user prompt with relevant codebase context.

        Args:
            user_prompt: The original user prompt
            include_files: Whether to include file listings

        Returns:
            Augmented prompt with context
        """
        if not self.is_explored():
            return user_prompt

        context_parts = []

        # Add project summary if available
        if self.summary:
            context_parts.append(f"Project Context:\n{self.summary}")

        # Add structure info
        if self.structure:
            structure_info = [
                f"Project: {self.project_path.name}",
                f"Files: {self.structure.get('total_files', 0)} total",
                f"Languages: {', '.join(k for k, v in self.structure.get('by_type', {}).items() if v > 0 and k != 'other')}",
            ]
            context_parts.append("Structure:\n" + "\n".join(structure_info))

        # Add git history info
        if self.git_history:
            git_info = []
            if self.git_history.get('current_branch'):
                git_info.append(f"Branch: {self.git_history['current_branch']}")
            if self.git_history.get('recent_commits'):
                commits = self.git_history['recent_commits'][:5]
                git_info.append(f"Recent commits:\n" + "\n".join(f"  {c}" for c in commits))
            if self.git_history.get('recently_changed_files'):
                changed = self.git_history['recently_changed_files'][:10]
                git_info.append(f"Recently changed: {', '.join(changed)}")
            if git_info:
                context_parts.append("Git History:\n" + "\n".join(git_info))

        # Optionally include relevant file listings
        if include_files and self.file_index:
            # Include Python files as they're most relevant
            py_files = self.file_index.get('python', [])[:20]
            if py_files:
                context_parts.append(f"Python files:\n" + "\n".join(f"  - {f}" for f in py_files))

        if context_parts:
            context_block = "\n\n".join(context_parts)
            return f"""[Codebase Context]
{context_block}

[User Request]
{user_prompt}"""

        return user_prompt

    def get_relevant_context(self, query: str, max_tokens: int = 4000) -> str:
        """
        Get context relevant to a specific query.

        Now uses semantic search if available, with fallback to keyword matching.

        Args:
            query: The query to find relevant context for
            max_tokens: Maximum tokens to return (for semantic search)

        Returns:
            Relevant context string
        """
        if not self.is_explored():
            return ""

        # Try semantic search first (lazy indexing on first use)
        semantic_search = self._ensure_semantic_search()
        if semantic_search:
            # Lazy index on first use (if not already indexed)
            if not semantic_search.is_indexed() and self.is_explored():
                logger.info("Indexing files for semantic search (first use)...")
                try:
                    self._index_for_semantic_search()
                except Exception as e:
                    logger.warning(f"Semantic indexing failed: {e}")
                    semantic_search = None

            # Search if indexed
            if semantic_search and semantic_search.is_indexed():
                try:
                    result = semantic_search.search(query, max_tokens=max_tokens)
                    if result.chunks:
                        logger.debug(f"Using semantic search ({len(result.chunks)} chunks)")
                        return self._format_search_result(result)
                except Exception as e:
                    logger.warning(f"Semantic search failed, falling back to keyword: {e}")

        # Fall back to keyword matching (existing logic)
        logger.debug("Using keyword-based context")
        return self._get_keyword_context(query)

    def _scan_files(self) -> dict:
        """Scan project for source files."""
        return self._file_scanner.scan_files(self.project_path)

    def _analyze_structure(self) -> dict:
        """Analyze project structure using file_index data."""
        # Update project detector with current file index
        self._project_detector.set_file_index(self.file_index)

        # Get markers from project detector
        markers = self._project_detector.detect_markers()

        structure = {
            'total_files': sum(len(f) for f in self.file_index.values()),
            'by_type': {k: len(v) for k, v in self.file_index.items()},
            'directories': [],
        }

        # Merge markers into structure
        structure.update(markers)

        # Get directories (only if path is valid)
        if self._path_valid and self.project_path.exists() and self.project_path.is_dir():
            skip_dirs = get_paths_config()
            for item in self.project_path.iterdir():
                if item.is_dir() and not item.name.startswith('.') and item.name not in skip_dirs:
                    structure['directories'].append(item.name)

        return structure

    def _read_key_files(self) -> dict:
        """Read important project files."""
        key_contents = {}

        # Priority files
        priority_files = [
            'README.md', 'README', 'setup.py', 'pyproject.toml',
            'package.json', 'requirements.txt', 'Cargo.toml', 'go.mod'
        ]

        for filename in priority_files:
            file_path = self.project_path / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if len(content) > 5000:
                        content = content[:5000] + "\n... (truncated)"
                    key_contents[filename] = content
                except Exception:
                    pass

        # Read main Python entry points
        py_files = self.file_index.get('python', [])
        _, entry_point_files = get_extensions_config()
        defaults = get_truncation_defaults()
        truncate_priority = defaults['priority_file']

        for entry in entry_point_files:
            for f in py_files:
                if f.endswith(entry) or f == entry:
                    file_path = self.project_path / f
                    if file_path.exists():
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                            if len(content) > truncate_priority:
                                content = content[:truncate_priority] + "\n... (truncated)"
                            key_contents[f] = content
                        except Exception:
                            pass
                    break

        return key_contents

    def _get_git_history(self) -> dict:
        """Get git history information."""
        return self._git_history_reader.get_history(self.project_path)

    def _on_semantic_search_ready(self, success: bool, result, error) -> None:
        """
        Callback when semantic search initialization completes.

        Automatically triggers file indexing when the model is ready.

        Args:
            success: True if initialization succeeded
            result: The initialized semantic search provider (or None)
            error: Exception if initialization failed (or None)
        """
        logger.info(f"Callback triggered: success={success}, result={result}, error={error}")
        if success and result:
            logger.info("Semantic search model ready, starting auto-indexing...")
            self._notify_indexing_progress("Semantic search ready, starting indexing...")

            # Cache the result for use
            self._semantic_search = result

            # Trigger auto-indexing
            logger.info("Calling _index_for_semantic_search()...")
            self._index_for_semantic_search()
            logger.info("_index_for_semantic_search() completed")
        elif error:
            logger.warning(f"Semantic search initialization failed: {error}")
            self._notify_indexing_progress(f"Semantic search initialization failed: {error}")

    def _index_for_semantic_search(self):
        """
        Index files for semantic search with Rich progress display.

        Uses batched file collection to prevent memory spikes:
        - Processes files in batches of 20
        - Respects .gitignore via git ls-files
        - Enforces file size limits (5MB per file)
        - Skips binary files
        - Gracefully handles errors
        - Displays progress using Rich (transient, disappears when done)

        Progress updates are sent via the registered callback (if any).

        Gracefully degrades - semantic search becomes unavailable on failure.
        """
        # Create Rich progress reporter for this indexing session
        from ..infrastructure.progress import RichProgressReporter, NullProgressReporter
        progress = RichProgressReporter()
        progress_started = False

        try:
            logger.info("Starting semantic search indexing (batched)...")
            logger.debug(f"Semantic search provider: {self._semantic_search}")

            # Get or create file collector
            self._notify_indexing_progress("Preparing file collector...")
            logger.info(f"File collector before creation: {self._file_collector}")
            file_collector = self._file_collector
            if file_collector is None:
                logger.info("Creating default file collector...")
                file_collector = self._create_default_file_collector()
                logger.info(f"File collector after creation: {file_collector}")
                if file_collector is None:
                    logger.warning("No file collector available - skipping semantic indexing")
                    self._notify_indexing_progress("No file collector available")
                    return

            # Set progress reporter on the provider
            self._semantic_search.set_progress_reporter(progress)

            # Index files in batches to prevent memory spikes
            self._notify_indexing_progress("Collecting and indexing files in batches...")

            total_indexed = 0
            batch_count = 0

            # Start progress with indeterminate total (we don't know how many files yet)
            progress.start("Indexing files for semantic search")
            progress_started = True

            logger.info("Starting batch collection...")
            for batch in file_collector.collect_files_batched(batch_size=20):
                batch_count += 1
                batch_size = len(batch)
                total_indexed += batch_size
                logger.info(f"Received batch {batch_count} with {batch_size} files")
                logger.debug(f"Sample files: {list(batch.keys())[:3]}")

                # Update progress with cumulative totals
                progress_msg = f"Indexing files: batch {batch_count} ({total_indexed} files total)"
                progress.update(description=progress_msg)

                self._notify_indexing_progress(
                    f"Indexing batch {batch_count} ({batch_size} files, "
                    f"{total_indexed} total)..."
                )

                logger.debug(f"Indexing batch {batch_count} with {batch_size} files")
                self._semantic_search.index_files(batch, is_batch=True)

            if total_indexed == 0:
                logger.warning("No files collected for semantic search indexing")
                self._notify_indexing_progress("No files to index")
                return

            logger.info(f"Semantic search indexing complete ({total_indexed} files in {batch_count} batches)")
            self._notify_indexing_progress(f"Indexing complete ({total_indexed} files)")

        except Exception as e:
            logger.error(f"Semantic indexing failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())

            self._notify_indexing_progress(f"Indexing failed: {e}")
            if progress_started:
                progress.error(str(e))

            # Gracefully degrade - disable semantic search
            self._semantic_search = None

        finally:
            # Always complete progress if it was started
            if progress_started:
                progress.complete("Indexing complete")

            # Reset progress reporter to null to avoid affecting future operations
            if self._semantic_search:
                self._semantic_search.set_progress_reporter(NullProgressReporter())

    def _format_search_result(self, result: 'SearchResult') -> str:
        """
        Format search result into context string.

        Args:
            result: SearchResult from semantic search

        Returns:
            Formatted context string
        """
        if not result.chunks:
            return ""

        parts = []
        for chunk in result.chunks:
            header = f"--- {chunk['path']} (lines {chunk['lines'][0]}-{chunk['lines'][1]}) ---"
            parts.append(f"{header}\n{chunk['content']}\n")

        return "\n".join(parts)

    def _get_keyword_context(self, query: str) -> str:
        """
        Get context using keyword matching (existing behavior).

        This is the ORIGINAL get_relevant_context logic, extracted
        for clarity and to enable fallback.

        Args:
            query: Search query

        Returns:
            Context string based on keyword matching
        """
        # Simple keyword-based relevance (existing logic)
        query_lower = query.lower()
        relevant_parts = []

        # Always include summary
        if self.summary:
            relevant_parts.append(f"Project: {self.summary}")

        # Check for file-specific keywords
        if any(word in query_lower for word in ['file', 'module', 'class', 'function', 'import']):
            py_files = self.file_index.get('python', [])[:10]
            if py_files:
                relevant_parts.append("Key Python files:\n" + "\n".join(f"  {f}" for f in py_files))

        # Check for config-related queries
        if any(word in query_lower for word in ['config', 'setup', 'install', 'dependency', 'require']):
            if 'requirements.txt' in self.key_files:
                defaults = get_truncation_defaults()
                deps = self.key_files['requirements.txt'][:defaults['error_message']]
                relevant_parts.append(f"Dependencies:\n{deps}")

        # Check for architecture queries
        if any(word in query_lower for word in ['architecture', 'structure', 'organize', 'pattern']):
            dirs = self.structure.get('directories', [])
            if dirs:
                relevant_parts.append(f"Project directories: {', '.join(dirs)}")

        return "\n\n".join(relevant_parts)

    def _save_cache(self):
        """Save context to disk cache."""
        cache_data = {
            'explored_at': self.explored_at,
            'summary': self.summary,
            'structure': self.structure,
            'file_index': self.file_index,
            'git_history': self.git_history,
            # Don't cache key_files content - too large
        }
        self._cache.save(self.cache_file, cache_data)

    def _load_cache(self):
        """Load context from disk cache."""
        cache_data = self._cache.load(self.cache_file)
        if cache_data is None:
            return

        self.explored_at = cache_data.get('explored_at')
        self.summary = cache_data.get('summary')
        self.structure = cache_data.get('structure', {})
        self.file_index = cache_data.get('file_index', {})
        self.git_history = cache_data.get('git_history', {})

        # Re-read key files if we have structure
        if self.structure:
            self.key_files = self._read_key_files()

    def clear_cache(self):
        """Clear the cached context."""
        self._cache.clear(self.cache_file)

        self.summary = None
        self.structure = {}
        self.key_files = {}
        self.file_index = {}
        self.git_history = {}
        self.explored_at = None

    def get_status(self) -> dict:
        """Get current context status."""
        status = {
            'project_path': str(self.project_path),
            'is_explored': self.is_explored(),
            'has_summary': self.summary is not None,
            'explored_at': self.explored_at.isoformat() if self.explored_at else None,
            'total_files': self.structure.get('total_files', 0),
            'cache_file': str(self.cache_file),
            'cache_exists': self.cache_file.exists(),
            'has_git_history': bool(self.git_history),
        }

        # Add git history summary
        if self.git_history:
            status['git_branch'] = self.git_history.get('current_branch', 'unknown')
            status['git_commits'] = len(self.git_history.get('recent_commits', []))
            status['git_recently_changed'] = len(self.git_history.get('recently_changed_files', []))

        return status

    def get_summary(self) -> str:
        """Get the project summary text."""
        if self.summary:
            return self.summary

        # If no summary, return basic info
        if self.is_explored():
            return f"Project: {self.project_path.name}, {self.structure.get('total_files', 0)} files"

        return "Project not explored yet"

    def get_project_type(self) -> str:
        """
        Determine the primary project type based on detected markers.

        Returns:
            String identifier for project type (e.g., 'python', 'java', 'nodejs')
        """
        if not self.structure:
            self.explore()

        # Ensure project detector has current file index
        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_project_type()

    def get_platform(self) -> str:
        """
        Get the current platform (cached).

        Returns:
            Platform identifier: 'windows', 'darwin', 'linux', or 'unix'
        """
        return self._platform_detector.get_platform()

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a command-line tool is available (cached).

        Args:
            tool_name: Name of the tool/command to check

        Returns:
            True if tool is available, False otherwise
        """
        return self._platform_detector.has_tool(tool_name)

    def get_languages(self) -> list:
        """
        Get list of programming languages used in the codebase.

        Returns:
            List of language names based on file extensions found
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_languages()

    def get_language_stats(self) -> dict:
        """
        Get count of files per programming language.

        Returns:
            Dict mapping language name to file count
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_language_stats()

    def get_primary_language(self) -> str:
        """
        Determine primary language based on file count.

        Returns:
            Language with most files, or 'unknown' if no code files
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_primary_language()

    def find_project_markers(self) -> list:
        """
        Find all project marker files (package.json, requirements.txt, etc.) anywhere in tree.

        Returns:
            List of relative paths to project marker files
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.find_project_markers()

    def get_marker_locations(self) -> dict:
        """
        Map directories to their project marker files.

        Returns:
            Dict mapping directory path to marker filename
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_marker_locations()

    def get_sub_projects(self) -> dict:
        """
        Detect project types in subdirectories (for monorepos).

        Returns:
            Dict mapping subdirectory name to project type
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_sub_projects()
