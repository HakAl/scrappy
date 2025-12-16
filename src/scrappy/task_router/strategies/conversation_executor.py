"""
Simple conversation handling with LLM-generated responses.
"""

import time
from typing import Optional

from ..classifier import ClassifiedTask, TaskType
from .base import ExecutionResult, ProviderAwareStrategy, OrchestratorLike
from ...protocols.output import StreamingOutputProtocol


CONVERSATION_SYSTEM_PROMPT = """You are a helpful coding assistant having a natural conversation.

Keep responses:
- Concise and friendly
- Focused on helping with coding tasks
- Natural and conversational

You can help with:
- Direct commands (pip install, git status, etc.)
- Code generation, refactoring, and bug fixes
- Research and code explanation
- Architecture analysis

Respond naturally to greetings, thanks, and general conversation.
Do not use emojis."""


class ConversationExecutor(ProviderAwareStrategy):
    """
    Conversation handling with LLM-generated responses.

    Best for:
    - Greetings
    - Acknowledgments
    - Help requests
    - Simple Q&A
    - General conversation

    Uses fast provider (cerebras) for snappy responses.
    """

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        preferred_provider: str = "cerebras"
    ):
        super().__init__(orchestrator)
        self.preferred_provider = preferred_provider

    @property
    def name(self) -> str:
        return "ConversationExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.CONVERSATION

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Handle conversation with LLM-generated response."""
        start_time = time.time()

        try:
            provider_to_use = self._resolve_and_validate_provider(self.preferred_provider)

            response = self.orchestrator.delegate(
                provider_to_use,
                task.original_input,
                system_prompt=CONVERSATION_SYSTEM_PROMPT,
                max_tokens=500,
                temperature=0.7
            )

            content = response.content if hasattr(response, 'content') else str(response)
            tokens_used = getattr(response, 'tokens_used', 0)

            return ExecutionResult(
                success=True,
                output=content,
                execution_time=time.time() - start_time,
                tokens_used=tokens_used,
                provider_used=provider_to_use,
                metadata={
                    "task_type": "conversation",
                    "matched_patterns": list(task.matched_patterns)
                }
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Conversation failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    async def execute_streaming(
        self,
        task: ClassifiedTask,
        output: StreamingOutputProtocol
    ) -> ExecutionResult:
        """Handle conversation with streaming LLM response."""
        start_time = time.time()

        try:
            provider_to_use = self._resolve_and_validate_provider(self.preferred_provider)

            # Check if orchestrator supports streaming
            if not hasattr(self.orchestrator, 'stream_delegate'):
                return self.execute(task)

            full_content = ""
            total_tokens = 0

            await output.stream_start(metadata={
                "provider": provider_to_use,
                "task_type": "conversation"
            })

            try:
                async for chunk in self.orchestrator.stream_delegate(
                    provider_name=provider_to_use,
                    prompt=task.original_input,
                    system_prompt=CONVERSATION_SYSTEM_PROMPT,
                    max_tokens=500,
                    temperature=0.7
                ):
                    if chunk.content:
                        full_content += chunk.content
                        await output.stream_token(chunk.content)

                    if chunk.finish_reason:
                        total_tokens = chunk.metadata.get("tokens_used", 0)

            finally:
                await output.stream_end(metadata={"tokens": total_tokens})

            return ExecutionResult(
                success=True,
                output=full_content,
                execution_time=time.time() - start_time,
                tokens_used=total_tokens,
                provider_used=provider_to_use,
                metadata={
                    "task_type": "conversation",
                    "matched_patterns": list(task.matched_patterns),
                    "streaming": True
                }
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Conversation streaming failed: {str(e)}",
                execution_time=time.time() - start_time
            )
