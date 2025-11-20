"""
BatchScheduler - Handles parallel batch execution of LLM requests.

Follows SOLID principles:
- Single Responsibility: Manages parallel execution of multiple requests
- Open/Closed: Extensible via protocol implementations
- Dependency Inversion: Depends on protocols, not concretions
"""

import asyncio
from typing import Any

try:
    from ..protocols.delegation import (
        BatchSchedulerProtocol,
        RetryOrchestratorProtocol,
        LLMRequest,
        OutputInterfaceProtocol,
    )
    from ..config import (
        DEFAULT_MAX_CONCURRENT,
        DEFAULT_MAX_RETRIES,
    )
except ImportError:
    from protocols.delegation import (
        BatchSchedulerProtocol,
        RetryOrchestratorProtocol,
        LLMRequest,
        OutputInterfaceProtocol,
    )
    from config import (
        DEFAULT_MAX_CONCURRENT,
        DEFAULT_MAX_RETRIES,
    )


class BatchScheduler:
    """
    Schedules and executes parallel batch requests.

    Follows SOLID principles:
    - Single Responsibility: Manages parallel execution only
    - Dependency Inversion: Depends on RetryOrchestratorProtocol for execution

    Responsibilities:
    - Execute multiple requests in parallel with concurrency control
    - Coordinate multi-provider queries
    - Preserve request order in results
    - Handle execution errors gracefully

    Does NOT:
    - Implement retry logic (delegates to RetryOrchestrator)
    - Cache responses (delegates to Cache)
    - Augment prompts (delegates to PromptAugmenter)
    - Select providers (delegates to ProviderSelector)
    """

    def __init__(
        self,
        *,
        retry_orchestrator: RetryOrchestratorProtocol,
        output: OutputInterfaceProtocol,
    ):
        """
        Initialize BatchScheduler.

        All dependencies are injected - NO instantiation inside constructor.

        Args:
            retry_orchestrator: Handles execution of individual requests with retries
            output: Output interface for logging messages
        """
        self._retry_orchestrator = retry_orchestrator
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
                    response, metadata = await self._retry_orchestrator.execute_with_retry(
                        request=request,
                        excluded_providers=set(),
                        max_retries=DEFAULT_MAX_RETRIES,
                    )
                    return response, metadata
                except Exception as e:
                    # Log error but don't fail entire batch
                    self._output.print_error(
                        f"Request failed for provider {request.provider}: {e}"
                    )
                    # Return None to indicate failure but preserve order
                    return None, {"error": str(e), "provider": request.provider}

        # Execute all requests in parallel and preserve order
        results = await asyncio.gather(
            *[execute_single(req) for req in requests],
            return_exceptions=False  # Don't wrap exceptions
        )

        return list(results)

    async def execute_multi_provider(
        self,
        request: LLMRequest,
        providers: list[str],
    ) -> dict[str, tuple[Any, dict]]:
        """
        Execute same request across multiple providers in parallel.

        Useful for comparing outputs or getting different perspectives.

        Args:
            request: The LLM request to execute
            providers: List of provider names to query

        Returns:
            Dict mapping provider name to (LLMResponse, task_record) tuple.
            Failed providers are excluded from results.

        Raises:
            ValueError: If providers list is empty
        """
        if not providers:
            raise ValueError("Cannot execute multi-provider with empty providers list")

        async def execute_for_provider(provider_name: str) -> tuple[str, tuple[Any, dict] | None]:
            """Execute request for a specific provider."""
            try:
                # Create new request with specific provider
                provider_request = LLMRequest(
                    prompt=request.prompt,
                    provider=provider_name,
                    model=request.model,
                    system_prompt=request.system_prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    use_context=request.use_context,
                    use_cache=request.use_cache,
                    intent_classification=request.intent_classification,
                    auto_fallback=False,  # Don't fallback in multi-provider mode
                    kwargs=request.kwargs,
                )

                response, metadata = await self._retry_orchestrator.execute_with_retry(
                    request=provider_request,
                    excluded_providers=set(),
                    max_retries=DEFAULT_MAX_RETRIES,
                )
                return provider_name, (response, metadata)
            except Exception as e:
                self._output.print_error(f"Provider {provider_name} failed: {e}")
                return provider_name, None

        # Execute all providers in parallel
        results = await asyncio.gather(
            *[execute_for_provider(p) for p in providers],
            return_exceptions=False
        )

        # Filter out failed providers and return as dict
        return {
            name: response
            for name, response in results
            if response is not None
        }
