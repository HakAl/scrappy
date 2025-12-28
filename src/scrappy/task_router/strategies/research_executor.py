"""
Fast research and information gathering with tool support.
"""

import time
from pathlib import Path
from typing import Optional, AsyncIterator

from ..classifier import ClassifiedTask, TaskType
from .base import ExecutionResult, ProviderAwareStrategy, OrchestratorLike
from ...orchestrator.types import StreamChunk
from ...protocols.output import StreamingOutputProtocol
from .research_protocols import (
    PathResolverProtocol,
    ToolBundleProtocol,
    ResponseCleanerProtocol,
    ResearchLoopProtocol,
    ResearchSubclassifierProtocol
)
from .path_resolver import PathResolver
from .tool_bundle import ToolBundle
from .response_cleaner import ResponseCleaner
from .research_loop import ResearchLoop
from .research_subclassifier import ResearchSubclassifier
from .research_subtype import ResearchSubtype
from scrappy.prompts import (
    PromptFactory,
    PromptFactoryProtocol,
    ResearchPromptConfig,
    ResearchSubtype as PromptResearchSubtype
)


class ResearchExecutor(ProviderAwareStrategy):
    """
    Fast research and information gathering with tool support.

    Best for:
    - Explaining code
    - Answering questions
    - Code analysis
    - Architecture overview
    - Fetching external documentation
    - Package/dependency research

    Features:
    - Uses fastest available provider (Cerebras)
    - No file modifications (read-only tools)
    - Context-aware responses
    - Tool access: web_fetch, web_search, read_file, search_code, git tools
    - Dynamic provider selection per task
    - Automatic tool calling for information gathering
    """

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        preferred_provider: str = "cerebras",
        project_root: Optional[Path] = None,
        max_tool_iterations: int = 3,
        path_resolver: Optional[PathResolverProtocol] = None,
        prompt_factory: Optional[PromptFactoryProtocol] = None,
        tool_bundle: Optional[ToolBundleProtocol] = None,
        response_cleaner: Optional[ResponseCleanerProtocol] = None,
        research_loop: Optional[ResearchLoopProtocol] = None,
        subclassifier: Optional[ResearchSubclassifierProtocol] = None
    ):
        """
        Initialize research executor.

        All dependencies are injected for testability and flexibility.
        Default implementations are created via factory methods if not provided.

        Args:
            orchestrator: Orchestrator for LLM delegation
            preferred_provider: Preferred provider name (default: cerebras)
            project_root: Project root directory
            max_tool_iterations: Maximum tool calling iterations
            path_resolver: File path resolver
            prompt_factory: Stateless prompt factory
            tool_bundle: Tool bundle for execution
            response_cleaner: Response cleaner
            research_loop: Research iteration loop
            subclassifier: Research subtype classifier
        """
        super().__init__(orchestrator)
        self.preferred_provider = preferred_provider
        self.project_root = project_root or Path.cwd()
        self.max_tool_iterations = max_tool_iterations

        # Inject dependencies or create defaults
        self._path_resolver = path_resolver or self._create_default_path_resolver()
        self._tool_bundle = tool_bundle or self._create_default_tool_bundle()
        self._prompt_factory = prompt_factory or PromptFactory()
        self._response_cleaner = response_cleaner or self._create_default_response_cleaner()
        self._research_loop = research_loop or self._create_default_research_loop()
        self._subclassifier = subclassifier or self._create_default_subclassifier()

    def _create_default_path_resolver(self) -> PathResolverProtocol:
        """Create default path resolver."""
        return PathResolver(self.orchestrator)

    def _create_default_tool_bundle(self) -> ToolBundleProtocol:
        """Create default tool bundle."""
        return ToolBundle.create_with_orchestrator(
            orchestrator=self.orchestrator,
            project_root=self.project_root
        )

    def _create_default_response_cleaner(self) -> ResponseCleanerProtocol:
        """Create default response cleaner."""
        return ResponseCleaner()

    def _create_default_research_loop(self) -> ResearchLoopProtocol:
        """Create default research loop."""
        return ResearchLoop(
            orchestrator=self.orchestrator,
            tool_bundle=self._tool_bundle,
            response_cleaner=self._response_cleaner
        )

    def _create_default_subclassifier(self) -> ResearchSubclassifierProtocol:
        """Create default research subclassifier."""
        return ResearchSubclassifier()

    @property
    def name(self) -> str:
        return "ResearchExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.RESEARCH

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """
        Execute research task with fast provider and tool support.

        This method orchestrates the research execution by delegating to
        specialized components for each responsibility.
        """
        start_time = time.time()

        try:
            # Step 0: Subclassify research type and get matched files
            file_index = self._get_file_index()
            classification_result = self._subclassifier.classify_with_matches(
                task.original_input,
                file_index
            )
            research_subtype = classification_result.subtype
            matched_files = classification_result.matched_files

            # Get context summary for execution
            context_summary = self._get_context_summary()

            # Route to appropriate execution path
            if research_subtype == ResearchSubtype.GENERAL:
                return self._execute_general_research(task, context_summary, start_time)
            else:
                return self._execute_codebase_research(
                    task, context_summary, start_time, matched_files
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Research execution failed: {str(e)}",
                execution_time=time.time() - start_time,
                metadata={"tool_calls": []}
            )

    def _execute_general_research(
        self,
        task: ClassifiedTask,
        context_summary: Optional[str],
        start_time: float
    ) -> ExecutionResult:
        """
        Execute general knowledge research without codebase tools.

        Uses only web tools if available, otherwise falls back to direct LLM.
        """
        provider_to_use = self._resolve_and_validate_provider(self.preferred_provider)

        # Build config and prompts - only mention web tools if available
        if self._tool_bundle.has_web_tools():
            config = ResearchPromptConfig(
                subtype=PromptResearchSubtype.GENERAL,
                tool_descriptions=self._tool_bundle.get_web_tool_descriptions(),
                context_summary=context_summary
            )
            system_prompt = self._prompt_factory.create_research_system_prompt(config)
            initial_prompt = self._prompt_factory.create_research_user_prompt(task.original_input, config)

            # Run with web tools only via research loop
            # The loop will reject non-web tool calls
            final_response, tool_calls_made, total_tokens = self._research_loop.run(
                provider=provider_to_use,
                initial_prompt=initial_prompt,
                system_prompt=system_prompt,
                task=task,
                max_iterations=self.max_tool_iterations,
                allowed_tools=self._tool_bundle.WEB_ONLY_TOOLS
            )
        else:
            # No tools - direct LLM call
            config = ResearchPromptConfig(
                subtype=PromptResearchSubtype.GENERAL,
                tool_descriptions=None
            )
            system_prompt = self._prompt_factory.create_research_system_prompt(config)

            response = self.orchestrator.delegate(
                provider_to_use,
                task.original_input,
                system_prompt=system_prompt
            )
            final_response = response.content if hasattr(response, 'content') else str(response)
            tool_calls_made = []
            total_tokens = getattr(response, 'tokens_used', 0)

        execution_time = time.time() - start_time

        return ExecutionResult(
            success=True,
            output=final_response,
            execution_time=execution_time,
            tokens_used=total_tokens,
            provider_used=provider_to_use,
            metadata={
                "task_type": "research",
                "research_subtype": "general",
                "complexity": task.complexity_score,
                "tool_calls": tool_calls_made,
                "iterations": len(tool_calls_made) + 1
            }
        )

    def _execute_codebase_research(
        self,
        task: ClassifiedTask,
        context_summary: Optional[str],
        start_time: float,
        matched_files: tuple = ()
    ) -> ExecutionResult:
        """
        Execute codebase research with full tool access.

        This is the original research execution path.

        Args:
            task: The classified task
            context_summary: Optional project summary
            start_time: Execution start time for timing
            matched_files: Project files matching query terms from file_index
        """
        # Step 1: Auto-explore codebase if needed
        self._path_resolver.auto_explore_if_needed(task)

        # Step 2: Load matched file contents (passive RAG to prevent hallucination)
        matched_file_contents = self._load_file_snippets(matched_files)

        # Step 3: Select provider
        provider_to_use = self._resolve_and_validate_provider(self.preferred_provider)

        # Step 4: Build config and prompts
        config = ResearchPromptConfig(
            subtype=PromptResearchSubtype.CODEBASE,
            tool_descriptions=self._tool_bundle.get_tool_descriptions() if self._tool_bundle.has_tools() else None,
            context_summary=context_summary,
            extracted_files=tuple(task.extracted_files or []),
            extracted_directories=tuple(task.extracted_directories or []),
            matched_project_files=matched_files,
            matched_file_contents=matched_file_contents,
            semantic_available=self._is_semantic_ready()
        )
        system_prompt = self._prompt_factory.create_research_system_prompt(config)
        initial_prompt = self._prompt_factory.create_research_user_prompt(task.original_input, config)

        # Step 5: Run research loop
        final_response, tool_calls_made, total_tokens = self._research_loop.run(
            provider=provider_to_use,
            initial_prompt=initial_prompt,
            system_prompt=system_prompt,
            task=task,
            max_iterations=self.max_tool_iterations
        )

        execution_time = time.time() - start_time

        # Step 6: Return result
        return ExecutionResult(
            success=True,
            output=final_response,
            execution_time=execution_time,
            tokens_used=total_tokens,
            provider_used=provider_to_use,
            metadata={
                "task_type": "research",
                "research_subtype": "codebase",
                "complexity": task.complexity_score,
                "tool_calls": tool_calls_made,
                "iterations": len(tool_calls_made) + 1
            }
        )

    def _get_context_summary(self) -> Optional[str]:
        """Get project context summary if available."""
        try:
            context = self.orchestrator.context
            if context and hasattr(context, 'get_summary') and context.is_explored():
                return context.get_summary()
        except Exception:
            pass
        return None

    def _get_file_index(self) -> Optional[dict]:
        """Get cached file_index from orchestrator context (never blocks).

        Uses cached data to avoid blocking on staleness checks during requests.
        See docs/TODO/IDEAL_UX.md for future optimization strategy.
        """
        try:
            context = self.orchestrator.context
            if context and hasattr(context, 'get_cached_file_index'):
                return context.get_cached_file_index()
            # Fallback: direct attribute access
            if context and hasattr(context, 'file_index'):
                return context.file_index or None
        except Exception:
            pass
        return None

    def _is_semantic_ready(self) -> bool:
        """Check if semantic search is ready for use.

        Returns:
            True if semantic search is initialized and ready, False otherwise.
        """
        try:
            context = self.orchestrator.context
            if context and hasattr(context, 'is_semantic_search_ready'):
                return context.is_semantic_search_ready()
        except Exception:
            pass
        return False

    def _load_file_snippets(
        self,
        file_paths: tuple,
        max_files: int = 5,
        max_lines_per_file: int = 100
    ) -> tuple[tuple[str, str], ...]:
        """Load content snippets from matched files for passive RAG.

        Prevents hallucination by injecting actual file content into the prompt
        instead of just listing file names.

        Args:
            file_paths: Tuple of file paths to load
            max_files: Maximum number of files to load (to avoid prompt bloat)
            max_lines_per_file: Maximum lines to include per file

        Returns:
            Tuple of (filepath, content_snippet) pairs
        """
        if not file_paths:
            return ()

        snippets = []
        for filepath in file_paths[:max_files]:
            try:
                full_path = self.project_root / filepath
                if not full_path.exists() or not full_path.is_file():
                    continue

                content = full_path.read_text(encoding='utf-8', errors='replace')
                lines = content.splitlines()

                if len(lines) > max_lines_per_file:
                    truncated_lines = lines[:max_lines_per_file]
                    truncated_lines.append(f"... ({len(lines) - max_lines_per_file} more lines)")
                    content = "\n".join(truncated_lines)

                snippets.append((filepath, content))
            except Exception:
                # Skip files that can't be read
                continue

        return tuple(snippets)

    async def execute_streaming(
        self,
        task: ClassifiedTask,
        output: StreamingOutputProtocol
    ) -> ExecutionResult:
        """
        Execute research task with streaming output.

        This method mirrors execute() but streams responses in real-time
        through the provided output protocol.

        Args:
            task: The classified research task
            output: StreamingOutputProtocol for real-time token output

        Returns:
            ExecutionResult with final response and metadata
        """
        start_time = time.time()

        try:
            # Step 0: Subclassify research type and get matched files
            file_index = self._get_file_index()
            classification_result = self._subclassifier.classify_with_matches(
                task.original_input,
                file_index
            )
            research_subtype = classification_result.subtype
            matched_files = classification_result.matched_files

            # Get context summary for execution
            context_summary = self._get_context_summary()

            # Route to appropriate execution path
            if research_subtype == ResearchSubtype.GENERAL:
                return await self._execute_general_research_streaming(
                    task, context_summary, start_time, output
                )
            else:
                return await self._execute_codebase_research_streaming(
                    task, context_summary, start_time, matched_files, output
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Research streaming execution failed: {str(e)}",
                execution_time=time.time() - start_time,
                metadata={"tool_calls": []}
            )

    async def _execute_general_research_streaming(
        self,
        task: ClassifiedTask,
        context_summary: Optional[str],
        start_time: float,
        output: StreamingOutputProtocol
    ) -> ExecutionResult:
        """
        Execute general knowledge research with streaming output.

        For general research without tools, we can stream the direct LLM response.
        """
        provider_to_use = self._resolve_and_validate_provider(self.preferred_provider)

        # Build config and prompts - general research doesn't use codebase tools
        config = ResearchPromptConfig(
            subtype=PromptResearchSubtype.GENERAL,
            tool_descriptions=None,
            context_summary=context_summary
        )
        system_prompt = self._prompt_factory.create_research_system_prompt(config)

        # Check if orchestrator supports streaming
        if not hasattr(self.orchestrator, 'stream_delegate'):
            # Fallback to non-streaming execution
            return self._execute_general_research(task, context_summary, start_time)

        # Stream the response
        full_content = ""
        total_tokens = 0

        await output.stream_start(metadata={"provider": provider_to_use, "task_type": "research"})

        # Estimate tokens for context-aware model selection
        prompt_chars = len(task.original_input) + len(system_prompt or "")
        estimated_tokens = (prompt_chars // 4) + 2000  # Buffer for response

        try:
            async for chunk in self.orchestrator.stream_delegate(
                provider_name=provider_to_use,
                prompt=task.original_input,
                system_prompt=system_prompt,
                max_tokens=2000,
                temperature=0.3,
                min_context=estimated_tokens if estimated_tokens and estimated_tokens > 30000 else 0,
            ):
                if chunk.content:
                    full_content += chunk.content
                    await output.stream_token(chunk.content)

                # Update metadata from final chunk
                if chunk.finish_reason:
                    total_tokens = chunk.metadata.get("tokens_used", 0)

        finally:
            await output.stream_end(metadata={"tokens": total_tokens})

        execution_time = time.time() - start_time

        return ExecutionResult(
            success=True,
            output=full_content,
            execution_time=execution_time,
            tokens_used=total_tokens,
            provider_used=provider_to_use,
            metadata={
                "task_type": "research",
                "research_subtype": "general",
                "complexity": task.complexity_score,
                "tool_calls": [],
                "iterations": 1,
                "streaming": True
            }
        )

    async def _execute_codebase_research_streaming(
        self,
        task: ClassifiedTask,
        context_summary: Optional[str],
        start_time: float,
        matched_files: tuple,
        output: StreamingOutputProtocol
    ) -> ExecutionResult:
        """
        Execute codebase research with streaming output.

        NOTE: Tool-based research with streaming is complex because:
        - We need to make multiple LLM calls (for tool iterations)
        - Each iteration may invoke tools
        - Only the final response should be streamed to the user

        For now, we fallback to non-streaming execution when tools are involved.
        Future enhancement: Stream final response after tool calls complete.
        """
        # For codebase research with tools, fallback to non-streaming
        # This is acceptable because:
        # 1. Tool execution takes time anyway
        # 2. Users want accuracy over speed for codebase queries
        # 3. Proper streaming with tools requires refactoring ResearchLoop
        return self._execute_codebase_research(task, context_summary, start_time, matched_files)
