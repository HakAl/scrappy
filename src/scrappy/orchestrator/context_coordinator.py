"""
Context coordinator for orchestrator.

Coordinates codebase context operations with orchestrator components
like logging and task execution.
"""

from typing import Dict, Any, Optional, Callable

try:
    from ..context.protocols import CodebaseContextProtocol
except ImportError:
    from context.protocols import CodebaseContextProtocol

from .output import BaseOutputProtocol, ConsoleOutput


class ContextCoordinator:
    """
    Coordinates codebase context operations with orchestrator components.

    This class adds orchestration concerns (logging, task executor integration,
    lifecycle policies) on top of CodebaseContext. It does NOT duplicate
    CodebaseContext functionality - instead it coordinates context operations
    with other orchestrator components.

    Responsibilities:
    - Auto-exploration on startup
    - Manual exploration triggering
    - Coordination with OutputInterface for logging
    - Integration with TaskExecutor for summary generation

    Does NOT handle (delegated to CodebaseContext):
    - File scanning
    - Context building
    - Prompt augmentation
    - Cache management
    """

    def __init__(
        self,
        context: CodebaseContextProtocol,
        output: Optional[BaseOutputProtocol] = None,
        generate_summary_func: Optional[Callable[[str], str]] = None,
    ):
        """
        Initialize context coordinator.

        Args:
            context: Underlying codebase context
            output: Output interface for logging (default: ConsoleOutput)
            generate_summary_func: Optional function to generate context summaries
                                  Should match TaskExecutor.generate_context_summary signature
        """
        self._context = context
        self.output = output or ConsoleOutput()
        self._generate_summary_func = generate_summary_func

    @property
    def context(self) -> CodebaseContextProtocol:
        """
        Access underlying codebase context.

        Direct context operations should use this property:
        - context.augment_prompt(prompt)
        - context.get_file_count()
        - context.add_files(files)
        - context.is_explored()
        - context.get_status()

        Returns:
            The underlying CodebaseContext instance
        """
        return self._context

    def auto_explore(self) -> Dict[str, Any]:
        """
        Orchestrator-level auto-exploration on startup.

        Coordinates:
        - Check if context is cached (via context.is_explored())
        - Log status via OutputInterface
        - Trigger exploration if needed (via context.explore())
        - Generate summary via TaskExecutor if exploration occurred
        - Log results

        Returns:
            Dictionary containing:
            - status: 'cached' | 'explored' | 'skipped'
            - total_files: Number of files found (if explored)
            - cache_used: Whether cached data was used
        """
        # Check if already explored (cached)
        if self._context.is_explored():
            project_name = getattr(self._context.project_path, 'name', 'project')
            self.output.info(f"[CONTEXT] Loaded cached context for {project_name}")
            status = self._context.get_status()
            return {
                'status': 'cached',
                'cache_used': True,
                'total_files': status.get('total_files', 0),
            }

        # Trigger exploration
        project_path = getattr(self._context, 'project_path', 'unknown')
        self.output.info(f"[CONTEXT] Exploring codebase: {project_path}")

        result = self._context.explore()

        if result['status'] == 'explored':
            self.output.info(f"[CONTEXT] Found {result['total_files']} files")

            # Generate summary if function provided
            if self._generate_summary_func:
                self._context.generate_summary(self._generate_summary_func)
                self.output.info("[CONTEXT] Generated project summary")

            return {
                'status': 'explored',
                'total_files': result['total_files'],
                'cache_used': False,
            }

        return {
            'status': 'skipped',
            'cache_used': False,
            'total_files': 0,
        }

    def explore_project(self, force: bool = False) -> Dict[str, Any]:
        """
        Orchestrator-level manual exploration trigger.

        Coordinates:
        - Clear cache if force=True (via context.clear_cache())
        - Trigger exploration (via context.explore())
        - Generate summary via TaskExecutor if exploration occurred
        - Log results via OutputInterface

        Args:
            force: Force re-exploration even if cached

        Returns:
            Dictionary containing:
            - status: 'explored' | 'cached' | 'failed'
            - total_files: Number of files found
            - error: Error message if status is 'failed'
        """
        try:
            # Clear cache if force requested
            if force:
                self._context.clear_cache()

            # Trigger exploration
            result = self._context.explore(force=force)

            # Generate summary if explored (or forced)
            if result['status'] == 'explored' or force:
                if self._generate_summary_func:
                    self._context.generate_summary(self._generate_summary_func)
                    self.output.info("[CONTEXT] Generated project summary")

            return result

        except Exception as e:
            self.output.error(f"[CONTEXT] Exploration failed: {e}")
            return {
                'status': 'failed',
                'total_files': 0,
                'error': str(e),
            }
