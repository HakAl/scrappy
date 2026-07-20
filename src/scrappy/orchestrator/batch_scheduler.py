"""
BatchScheduler - Handles parallel batch execution of LLM requests.

Follows SOLID principles:
- Single Responsibility: Manages parallel execution of multiple requests
- Open/Closed: Extensible via protocol implementations
- Dependency Inversion: Depends on protocols, not concretions

After LiteLLM integration (Phase 3):
- Uses LLMServiceProtocol instead of RetryOrchestratorProtocol
- LiteLLM Router handles retry/fallback internally
"""

import asyncio
from typing import Any

from .protocols import (
    LLMRequest,
    LLMServiceProtocol,
)
from ..cli.protocols import BaseOutputProtocol as OutputInterfaceProtocol
from .model_selection import MODEL_GROUPS
from .constants import (
    DEFAULT_MAX_CONCURRENT,
)


# Map legacy provider names to model groups
PROVIDER_TO_GROUP = {
    "groq": "fast",
    "cerebras": "fast",
    "gemini": "instruct",
    "auto": "fast",
}


def _resolve_model_group(provider_name: str) -> str:
    """Resolve a provider name to a model group for LiteLLM Router."""
    if provider_name in MODEL_GROUPS:
        return provider_name
    if provider_name in PROVIDER_TO_GROUP:
        return PROVIDER_TO_GROUP[provider_name]
    return "fast"


def _request_to_messages(request: LLMRequest) -> list[dict]:
    """Convert an LLMRequest to LiteLLM messages format."""
    messages = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.append({"role": "user", "content": request.prompt})
    return messages


class BatchScheduler:
    """
    Schedules and executes parallel batch requests.

    Follows SOLID principles:
    - Single Responsibility: Manages parallel execution only
    - Dependency Inversion: Depends on LLMServiceProtocol for execution

    Responsibilities:
    - Execute multiple requests in parallel with concurrency control
    - Coordinate multi-provider queries
    - Preserve request order in results
    - Handle execution errors gracefully

    Does NOT:
    - Implement retry logic (handled by LiteLLM Router via LLMService)
    - Cache responses (delegates to Cache)
    - Augment prompts (delegates to PromptAugmenter)
    - Select providers (handled by LiteLLM Router)
    """

    def __init__(
        self,
        *,
        llm_service: LLMServiceProtocol,
        output: OutputInterfaceProtocol,
    ):
        """
        Initialize BatchScheduler.

        All dependencies are injected - NO instantiation inside constructor.

        Args:
            llm_service: LLM service for making completion calls (uses LiteLLM Router)
            output: Output interface for logging messages
        """
        self._llm_service = llm_service
        self._output = output

    async def execute_batch(
        self,
        requests: list[LLMRequest],
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> list[tuple[Any, dict]]:
        """
        Execute multiple requests in parallel with concurrency control.

        Uses asyncio.Semaphore to limit concurrent executions and preserve
        request order in results.

        Args:
            requests: List of LLM requests to execute
            max_concurrent: Maximum number of concurrent executions

        Returns:
            List of (LLMResponse, task_record) tuples in same order as requests

        Raises:
            ValueError: If requests list is empty
        """
        if not requests:
            raise ValueError("Cannot execute batch with empty requests list")

        if max_concurrent < 1:
            raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_single(request: LLMRequest) -> tuple[Any, dict]:
            """Execute a single request with concurrency control."""
            async with semaphore:
                try:
                    model_group = _resolve_model_group(request.provider or "fast")
                    messages = _request_to_messages(request)

                    response, metadata = await self._llm_service.completion(
                        model=model_group,
                        messages=messages,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        **(request.kwargs or {}),
                    )
                    return response, metadata
                except Exception as e:
                    # Log error but don't fail entire batch
                    self._output.error(
                        f"Request failed for model group {request.provider}: {e}"
                    )
                    # Return None to indicate failure but preserve order
                    return None, {"error": str(e), "model_group": request.provider}

        # Execute all requests in parallel and preserve order
        results = await asyncio.gather(
            *[execute_single(req) for req in requests],
            return_exceptions=False  # Don't wrap exceptions
        )

        return list(results)
