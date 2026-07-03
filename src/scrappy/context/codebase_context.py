"""
Codebase context management for the LLM Agent Team.

Provides automatic project exploration and context augmentation for prompts.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .file_scanner import FileScanner
from .cache import ContextCache
from .git_history import GitHistoryReader
from ..platform.detection import SystemPlatformDetector
from ..platform.protocols.detection import PlatformDetectorProtocol
from .project_detector import ProjectDetector
from .config_loader import get_truncation_defaults, get_extensions_config, get_paths_config
from ..infrastructure.protocols import PathProviderProtocol, BackgroundInitializerProtocol
from ..infrastructure.paths import ScrappyPathProvider
from ..infrastructure.threading import (
    EventQueueProtocol,
    ThreadSafeEventQueue,
)
from .semantic_manager import SemanticSearchManager
from .augmenter import ContextAugmenter
from .protocols import (
    SemanticSearchManagerProtocol,
    ContextAugmenterProtocol,
    FileCollectorProtocol,
    StalenessCheckerProtocol,
)

if TYPE_CHECKING:
    from ..cli.protocols import CLIIOProtocol
    from .semantic.config import SemanticIndexConfig
    from .protocols import (
        IndexStateProtocol,
        IndexingDecisionProtocol,
        SemanticSearchProtocol,
        SearchResult,
    )

logger = logging.getLogger(__name__)


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
        platform_detector: Optional[PlatformDetectorProtocol] = None,
        git_history_reader: Optional[GitHistoryReader] = None,
        project_detector: Optional[ProjectDetector] = None,
        path_provider: Optional[PathProviderProtocol] = None,
        file_collector: Optional[FileCollectorProtocol] = None,
        io: Optional["CLIIOProtocol"] = None,
        event_queue: Optional[EventQueueProtocol] = None,
        semantic_manager: Optional[SemanticSearchManagerProtocol] = None,
        context_augmenter: Optional[ContextAugmenterProtocol] = None,
        staleness_checker: Optional[StalenessCheckerProtocol] = None,
    ):
        """
        Initialize codebase context (dependencies only - NO file I/O by default).

        Call restore_from_cache() after construction to load cached context from disk.

        Args:
            project_path: Path to project root. Defaults to current directory.
            file_scanner: Injectable file scanner (default: creates new FileScanner)
            cache: Injectable context cache (default: creates new ContextCache)
            platform_detector: Injectable platform detector (default: creates new SystemPlatformDetector)
            git_history_reader: Injectable git history reader (default: creates new GitHistoryReader)
            project_detector: Injectable project detector (default: creates from project_path)
            path_provider: Path provider for data files (auto-creates if None)
            file_collector: Injectable file collector for semantic search (default: creates SemanticFileCollector)
            io: Injectable IO interface for progress reporting (default: None, falls back to NullProgressReporter)
            event_queue: Event queue for main-thread-safe background notifications.
                        If None, creates a default ThreadSafeEventQueue.
            semantic_manager: Injectable semantic search manager (default: creates SemanticSearchManager)
            context_augmenter: Injectable context augmenter (default: creates ContextAugmenter)
            staleness_checker: Injectable staleness checker for detecting file changes (default: creates StalenessChecker)
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

        # IO interface for progress reporting
        self._io = io  # Injected IO interface (optional)

        # Event queue for main-thread-safe background notifications
        self._event_queue = event_queue or ThreadSafeEventQueue()

        # File collector for semantic search
        self._file_collector = file_collector

        # === Staleness Checker ===
        # Create staleness checker FIRST so it can be shared with SemanticSearchManager
        # This prevents duplicate instances that get out of sync (see AGENT_BUGS.md)
        self._staleness_checker = staleness_checker or self._create_default_staleness_checker()

        # === Semantic Search Manager (extracted) ===
        # If semantic_manager is provided, use it; otherwise create default
        # Pass shared staleness_checker to avoid duplicate fingerprinting
        if semantic_manager:
            self._semantic_manager = semantic_manager
        else:
            self._semantic_manager = SemanticSearchManager(
                project_path=self.project_path,
                event_queue=self._event_queue,
                io=self._io,
                staleness_checker=self._staleness_checker,
            )

        # Backward compatibility: expose underlying state via manager
        self._semantic_search = None  # Cached for backward compatibility
        self._indexing_progress_callback = None  # Callback for indexing progress updates

        # === Context Augmenter (extracted) ===
        # Defer augmenter creation until first use since it needs data providers
        self._context_augmenter = context_augmenter  # May be None initially


    @property
    def cache_file(self) -> Path:
        """Get path to context cache file."""
        return self._path_provider.context_file()

    @property
    def event_queue(self) -> EventQueueProtocol:
        """
        Get the event queue for processing background events.

        Returns:
            The event queue used for background-to-main-thread communication
        """
        return self._event_queue

    @property
    def platform(self) -> PlatformDetectorProtocol:
        """
        Get the platform detector.

        Returns:
            Platform detector for checking OS type and tool availability
        """
        return self._platform_detector

    @property
    def semantic_manager(self) -> Optional[SemanticSearchManagerProtocol]:
        """
        Get the semantic search manager.

        Returns:
            Semantic search manager for external use
        """
        return self._semantic_manager

    def _get_or_create_augmenter(self) -> ContextAugmenter:
        """
        Get or create the context augmenter with proper data providers.

        Lazily creates augmenter on first use since providers need self reference.
        """
        if self._context_augmenter is None:
            self._context_augmenter = ContextAugmenter(
                project_path=self.project_path,
                summary_provider=lambda: self.summary,
                structure_provider=lambda: self.structure,
                git_history_provider=lambda: self.git_history,
                file_index_provider=lambda: self.file_index,
                is_explored_provider=lambda: self.is_explored(),
                semantic_manager=self._semantic_manager,
            )
        return self._context_augmenter

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

    def _create_default_platform_detector(self) -> PlatformDetectorProtocol:
        """Create default platform detector."""
        return SystemPlatformDetector()

    def _create_default_git_history_reader(self) -> GitHistoryReader:
        """Create default git history reader."""
        return GitHistoryReader()

    def _create_default_project_detector(self) -> ProjectDetector:
        """Create default project detector."""
        return ProjectDetector(self.project_path)

    def _create_default_staleness_checker(self) -> StalenessCheckerProtocol:
        """
        Create default staleness checker for file change detection.

        Returns:
            StalenessChecker with default configuration
        """
        from .staleness import StalenessChecker
        from .semantic.config import SemanticIndexConfig

        # Use default config for staleness settings
        config = SemanticIndexConfig()

        return StalenessChecker(
            root_path=self.project_path,
            config=config,
        )

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
            logger.debug("Creating SemanticSearchInitializer with event queue")
            return SemanticSearchInitializer(
                self.project_path,
                event_queue=self._event_queue,
            )
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
        # Also set on semantic manager for delegation
        self._semantic_manager.set_progress_callback(callback)

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

    def configure_semantic_search(
        self,
        config: 'SemanticIndexConfig',
        state_manager: 'IndexStateProtocol',
        decision_maker: 'IndexingDecisionProtocol',
    ) -> None:
        """
        Configure semantic search with custom dependencies.

        This must be called BEFORE start_background_initialization() to
        inject custom configuration and managers.

        Args:
            config: Semantic index configuration with thresholds
            state_manager: Index state persistence manager
            decision_maker: Indexing decision logic
        """
        # Re-create semantic manager with new dependencies
        self._semantic_manager = SemanticSearchManager(
            project_path=self.project_path,
            event_queue=self._event_queue,
            io=self._io,
            config=config,
            state_manager=state_manager,
            decision_maker=decision_maker,
        )

        # Re-apply progress callback if it was set
        if self._indexing_progress_callback:
            self._semantic_manager.set_progress_callback(self._indexing_progress_callback)

    def start_background_initialization(self) -> None:
        """
        Start background initialization tasks (semantic search model loading, etc.).

        This is non-blocking and returns immediately. The actual work happens
        in background threads.

        Call this early in application startup to pre-load heavy dependencies.

        Use process_background_events() periodically from the main thread to
        process completion events.
        """
        # Set up file collector callback for auto-indexing
        # This allows SemanticSearchManager to trigger indexing when model is ready
        self._semantic_manager.set_file_collector_callback(
            lambda: self._file_collector or self._create_default_file_collector()
        )

        # Delegate to semantic manager
        self._semantic_manager.start_background_init()

        if self._indexing_progress_callback:
            self._semantic_manager.set_progress_callback(self._indexing_progress_callback)

    def process_background_events(self) -> int:
        """
        Process pending background events.

        Should be called periodically from the main thread to handle
        completion events from background initialization tasks.

        Returns:
            Number of events processed
        """
        # Delegate to semantic manager (which owns the event queue)
        return self._semantic_manager.process_events()

    def get_semantic_initialization_status(self) -> Optional[str]:
        """
        Get human-readable status of semantic search initialization.

        Returns:
            Status string if initializer exists, None otherwise
        """
        # Delegate to semantic manager
        return self._semantic_manager.get_status()

    def is_semantic_search_ready(self) -> bool:
        """
        Check if semantic search is ready to use.

        Returns:
            True if semantic search is available and ready
        """
        # Delegate to semantic manager
        return self._semantic_manager.is_ready()

    def get_search_provider(self) -> Optional['SemanticSearchProtocol']:
        """
        Get the semantic search provider if available.

        Returns:
            SemanticSearchProtocol instance or None if not available
        """
        return self._semantic_manager.get_search_provider()

    def is_explored(self) -> bool:
        """Check if the codebase has been explored."""
        return self.explored_at is not None

    def get_cached_file_index(self) -> dict:
        """
        Get the cached file_index without staleness checking or reindexing.

        Use this for fast lookups where stale data is acceptable (e.g., query
        classification). Never blocks on staleness checks.

        Returns:
            Cached file_index dict (may be empty if never scanned, may be stale)
        """
        if not self.file_index:
            self.file_index = self._scan_files()
        return self.file_index

    def ensure_file_index(self, force_refresh: bool = False) -> dict:
        """
        Ensure file_index is populated, using three-layer staleness detection.

        Three-layer detection strategy (fast to slow):
        1. Trust stored fingerprints - no scan if fingerprints exist
        2. Quick directory mtime check - only scan dirs, not files
        3. Full file scan - only when directories changed or forced

        Args:
            force_refresh: If True, skip quick checks and do full scan

        Returns:
            Dict mapping category names to lists of relative file paths
        """
        if not self.file_index:
            logger.debug("file_index empty, performing lazy scan")
            self.file_index = self._scan_files()

        # Layer 1: Check if we have stored fingerprints
        if not self._staleness_checker.has_fingerprints():
            logger.info("First run - establishing fingerprint baseline")
            self._staleness_checker.update_fingerprints(None)
            return self.file_index

        # Layer 2: Quick directory mtime check (skip if forcing refresh)
        if not force_refresh and not self._staleness_checker.quick_check():
            # No directory changes detected - skip full scan
            logger.debug("Quick check passed - skipping full staleness scan")
            return self.file_index

        # Layer 3: Full scan (directories changed or forced)
        logger.debug("Directory changes detected or forced - performing full scan")
        staleness_report = self._staleness_checker.check_staleness(force=force_refresh)
        if staleness_report.is_stale:
            logger.info(
                f"Detected file changes: {staleness_report.total_changes} files "
                f"(added={len(staleness_report.added)}, "
                f"modified={len(staleness_report.modified)}, "
                f"deleted={len(staleness_report.deleted)})"
            )

            # Re-scan file index to pick up new files
            logger.debug("Re-scanning file index due to staleness")
            self.file_index = self._scan_files()

            # Trigger blocking re-index of changed files in semantic search
            if self._semantic_manager and self._semantic_manager.is_ready():
                # Handle added/modified files
                changed_files = staleness_report.added | staleness_report.modified
                if changed_files:
                    logger.info(f"Re-indexing {len(changed_files)} changed files")
                    try:
                        self._semantic_manager.refresh_files(changed_files)
                        logger.info("Re-indexing complete")
                    except Exception as e:
                        logger.warning(f"Re-indexing failed: {e}")

                # Handle deleted files
                if staleness_report.deleted:
                    logger.info(f"Removing {len(staleness_report.deleted)} deleted files from index")
                    try:
                        self._semantic_manager.remove_deleted_files(staleness_report.deleted)
                    except Exception as e:
                        logger.warning(f"Failed to remove deleted files: {e}")

            # Update fingerprints after successful refresh
            self._staleness_checker.update_fingerprints(staleness_report)

        return self.file_index

    def explore(self, force: bool = False) -> dict:
        """
        Explore the codebase and build context.

        Args:
            force: Force re-exploration even if cache exists

        Returns:
            Dict with exploration results
        """
        explored_at = self.explored_at
        if explored_at is not None and not force:
            return {
                'status': 'cached',
                'explored_at': explored_at.isoformat(),
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
        # Delegate to context augmenter
        augmenter = self._get_or_create_augmenter()
        return augmenter.augment(user_prompt, include_files=include_files)

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
        # Check for file changes and refresh index if needed
        self.ensure_file_index()

        # Check for lazy indexing (for backward compatibility)
        if self.is_explored():
            semantic_search = self.get_search_provider()
            if semantic_search and not semantic_search.is_indexed():
                logger.info("Indexing files for semantic search (first use)...")
                try:
                    self._index_for_semantic_search()
                except Exception as e:
                    logger.warning(f"Semantic indexing failed: {e}")

        # Delegate to context augmenter
        augmenter = self._get_or_create_augmenter()
        return augmenter.get_relevant_context(query, max_tokens=max_tokens)

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

    def _index_for_semantic_search(self):
        """
        Index files for semantic search with Rich progress display.

        Delegates to SemanticSearchManager for the actual indexing logic.

        Uses batched file collection to prevent memory spikes:
        - Processes files in batches of 20
        - Filters via IndexFilterConfig (skips .git, node_modules, etc.)
        - Enforces file size limits (5MB per file)
        - Skips binary files
        - Gracefully handles errors

        Progress updates are sent via the registered callback (if any).
        """
        # Get or create file collector
        file_collector = self._file_collector
        if file_collector is None:
            file_collector = self._create_default_file_collector()
            if file_collector is None:
                logger.warning("No file collector available - skipping semantic indexing")
                self._notify_indexing_progress("No file collector available")
                return

        # Delegate to semantic manager
        self._semantic_manager.index_files(file_collector)

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

    def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown background tasks and clean up resources.

        Args:
            timeout: Max seconds to wait for background threads to stop.
                     Use a short timeout (e.g., 0.5) for app exit since
                     daemon threads will be killed anyway when process exits.
        """
        self._semantic_manager.shutdown(timeout=timeout)
