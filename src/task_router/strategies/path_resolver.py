"""
PathResolver - Handles file path resolution and automatic codebase exploration.

Responsibilities:
- Detect when a task needs codebase exploration
- Trigger exploration automatically for file-related queries
- Resolve partial file references to full paths using file index
"""

from typing import Optional, Any
from ..classifier import ClassifiedTask


class PathResolver:
    """
    Resolves file paths and manages automatic codebase exploration.

    This class is responsible for:
    1. Detecting when a task involves file/codebase operations
    2. Triggering automatic exploration when needed
    3. Resolving partial file names to full paths using the file index

    All dependencies are injected, no side effects in constructor.
    """

    def __init__(self, context_provider: Any):
        """
        Initialize PathResolver with injected dependencies.

        Args:
            context_provider: Object that provides access to codebase context
                            (typically an orchestrator with a .context attribute)
        """
        self._context_provider = context_provider

    def auto_explore_if_needed(self, task: ClassifiedTask) -> None:
        """
        Automatically trigger codebase exploration if the task needs it.

        Detection logic:
        - Task has extracted files or directories
        - Task query contains file-related keywords

        If exploration is needed:
        - Checks if context is already explored
        - Triggers exploration with force=True if not explored or file index is empty
        - Automatically resolves file paths after exploration

        Args:
            task: The classified task to check
        """
        # Check if exploration is needed
        needs_exploration = self._should_explore(task)

        if not needs_exploration:
            return

        # Try to get context and trigger exploration
        try:
            context = self._get_context()
            if not context:
                return

            # Check if we need to explore
            should_force_explore = (
                not context.is_explored() or
                not self._has_file_index(context)
            )

            if should_force_explore:
                context.explore(force=True)

            # After exploration, resolve file paths if we have extracted files
            if task.extracted_files and self._has_file_index(context):
                self._resolve_paths(task, context)

        except Exception:
            # Silently handle exploration failures
            # The task can continue without exploration
            pass

    def resolve_file_paths(self, task: ClassifiedTask) -> None:
        """
        Resolve extracted file names to full paths.

        Uses the file index to find full paths for partial file references.
        Modifies task.extracted_files in place with resolved paths.

        Resolution strategy:
        - Match by exact basename (case-insensitive)
        - Match by partial path (case-insensitive)
        - Deduplicate results

        Args:
            task: The classified task with extracted file references
        """
        try:
            context = self._get_context()
            if not context:
                return

            if not self._has_file_index(context):
                return

            self._resolve_paths(task, context)

        except Exception:
            # Silently handle resolution failures
            pass

    def _should_explore(self, task: ClassifiedTask) -> bool:
        """
        Determine if the task needs codebase exploration.

        Args:
            task: The classified task

        Returns:
            True if exploration is needed, False otherwise
        """
        # Check if task has extracted files or directories
        if task.extracted_files or task.extracted_directories:
            return True

        # Check if query contains file-related keywords
        lower_input = task.original_input.lower()
        file_keywords = [
            'file', 'code', 'function', 'class', 'component',
            'directory', 'folder'
        ]

        return any(keyword in lower_input for keyword in file_keywords)

    def _get_context(self) -> Optional[Any]:
        """
        Get the codebase context from the provider.

        Returns:
            Context object or None if not available
        """
        if not self._context_provider:
            return None

        if not hasattr(self._context_provider, 'context'):
            return None

        return self._context_provider.context

    def _has_file_index(self, context: Any) -> bool:
        """
        Check if context has a populated file index.

        Args:
            context: The codebase context

        Returns:
            True if file index exists and is not empty
        """
        if not hasattr(context, 'file_index'):
            return False

        if context.file_index is None:
            return False

        if not context.file_index:  # Empty dict
            return False

        return True

    def _resolve_paths(self, task: ClassifiedTask, context: Any) -> None:
        """
        Resolve file paths using the context's file index.

        Modifies task.extracted_files in place.

        Args:
            task: The task with file references to resolve
            context: The codebase context with file index
        """
        if not task.extracted_files:
            return

        if not self._has_file_index(context):
            return

        resolved_paths = []

        for file_ref in task.extracted_files:
            # Normalize the file reference for case-insensitive matching
            file_ref_lower = file_ref.lower()
            file_basename = file_ref.split('/')[-1].lower()

            # Search in all indexed files across all file types
            for file_type, files in context.file_index.items():
                for indexed_file in files:
                    indexed_lower = indexed_file.lower()
                    indexed_basename = indexed_file.split('/')[-1].lower()

                    # Match by basename (case-insensitive)
                    if indexed_basename == file_basename:
                        resolved_paths.append(indexed_file)
                    # Match by partial path (case-insensitive)
                    elif file_ref_lower in indexed_lower:
                        resolved_paths.append(indexed_file)

        # Update task with resolved paths (deduplicated)
        if resolved_paths:
            # Use object.__setattr__ to bypass frozen dataclass restriction
            # Convert to sorted tuple for deterministic ordering
            object.__setattr__(
                task,
                'extracted_files',
                tuple(sorted(set(resolved_paths)))
            )
