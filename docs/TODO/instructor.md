 Instructor Integration Plan

 Decisions

 - Delete standalone adapters - LiteLLMService handles everything
 - Classification first - Validate approach before expanding to research loop

 Beads to Create

 1. Phase 1: Extend LiteLLMService with completion_structured (P1)
 2. Phase 2: Add Protocol + Update Pydantic Models (P1) - depends on Phase 1
 3. Phase 3: Wire into DelegationManager (P1) - depends on Phase 2
 4. Phase 4: Update Task Classification (P1) - depends on Phase 3
 5. Phase 5: Unit Tests (P1) - depends on Phase 4
 6. Phase 6: Cleanup - delete src/scrappy/llm/ (P2) - depends on Phase 5
   - REQUIRES HUMAN VERIFICATION before proceeding
 7. Phase 7: Research Loop integration (P2) - BLOCKED BY Phase 6

 Current State

 Architecture Overview

 - LiteLLMService (orchestrator/litellm_service.py) - implements LLMServiceProtocol, wraps LiteLLM Router
 - DelegationManager (orchestrator/delegation.py) - high-level delegation, uses LLMService
 - Orchestrator.delegate() - main entry point for LLM calls

 JSON Parsing Points (to be replaced)

 1. pure_functions.py:parse_llm_classification_response() - task classification
 2. research_loop.py:_parse_tool_call() - tool call extraction
 3. response_parser.py:JSONResponseParser - agent response parsing

 Problem

 The InstructorAdapter I created is standalone - it bypasses the orchestrator entirely. This loses:
 - Provider selection/fallback
 - Context augmentation
 - Rate limiting
 - Caching
 - Usage tracking

 Design Decision

 Option A: Extend LiteLLMService with structured output capability
 - Add completion_structured() method that uses Instructor
 - Instructor wraps the existing LiteLLM Router via instructor.from_litellm()
 - Keeps all orchestrator benefits (caching, rate limiting, provider fallback)

 Option B: Create parallel StructuredOutputService
 - New service specifically for structured output
 - Would duplicate some orchestrator logic

 Recommendation: Option A - cleaner, maintains single source of truth

 Implementation Plan

 Phase 1: Extend LiteLLMService

 File: src/scrappy/orchestrator/litellm_service.py

 Key insights from review:
 - Wrap at call site (in init), not globally
 - CRITICAL: Must be async throughout - delegate_structured must also be async
 - Derive mode internally - don't expose to callers, pick from model string
 - DEFAULT_INSTRUCTOR_RETRIES = 1 - class-level default, high-risk calls can override
 - Observability spans - wrap in OpenTelemetry span with retry_count, validation_errors

 from typing import Type, TypeVar, Optional, List, Dict
 import instructor
 from pydantic import BaseModel

 T = TypeVar("T", bound=BaseModel)
 DEFAULT_INSTRUCTOR_RETRIES = 1  # Class-level default

 # In __init__:
 self._instructor_client = instructor.from_litellm(self._router.acompletion)

 def _pick_mode(self, model: str) -> instructor.Mode:
     """Derive instructor mode from model string."""
     if any(x in model for x in {"gpt-4", "claude", "command-r"}):
         return instructor.Mode.TOOLS
     return instructor.Mode.JSON

 async def completion_structured(
     self,
     model: str,
     messages: List[Dict],
     response_model: Type[T],
     max_retries: Optional[int] = None,
     mode_override: Optional[instructor.Mode] = None,  # Escape hatch for edge cases
     **kwargs
 ) -> T:
     """Async structured output with validation retries."""
     retries = max_retries if max_retries is not None else DEFAULT_INSTRUCTOR_RETRIES
     mode = mode_override if mode_override else self._pick_mode(model)

     # TODO: Wrap in OpenTelemetry span with retry_count, validation_errors
     return await self._instructor_client.chat.completions.create(
         model=model,
         messages=messages,
         response_model=response_model,
         max_retries=retries,
         mode=mode,
         **kwargs
     )

 Phase 2: Add Protocol (ASYNC)

 File: src/scrappy/orchestrator/protocols.py

 class StructuredOutputProtocol(Protocol):
     async def completion_structured(
         self,
         model: str,
         messages: List[Dict],
         response_model: Type[T],
         **kwargs
     ) -> T: ...

 Phase 2b: Update Pydantic Models

 File: src/scrappy/llm/models.py

 Instructor uses field docstrings as context (NOT the full system prompt).
 Keep descriptions short/factual. Put behavioral instructions in system_prompt parameter.

 SECURITY: Never reflect user input into Field descriptions (prompt injection vector).

 class TaskClassification(BaseModel):
     """Classifies the user intent into a task category."""
     task_type: TaskType = Field(..., description="RESEARCH, CODE_GENERATION, DIRECT_COMMAND, or CONVERSATION")
     confidence: float = Field(..., description="0.0 to 1.0")
     reasoning: str = Field(..., description="Brief explanation")

 Phase 3: Wire into DelegationManager (ASYNC)

 File: src/scrappy/orchestrator/delegation.py

 Must be async to avoid blocking:
 async def delegate_structured(
     self,
     provider_name: str,
     prompt: str,
     response_model: Type[T],
     system_prompt: Optional[str] = None,
     **kwargs
 ) -> T:
     """Async delegate with structured output validation."""
     # Resolve provider_name to model string (e.g., "fast" -> "groq/llama-3.1-8b")
     model = self._resolve_model(provider_name)
     messages = self._build_messages(prompt, system_prompt)
     return await self.llm_service.completion_structured(
         model=model,
         messages=messages,
         response_model=response_model,
         **kwargs
     )

 Phase 4: Update Task Classification (ASYNC + AWAIT)

 File: src/scrappy/task_router/router.py

 Method must be async and await the result:
 # Before:
 response = self.orchestrator.delegate(...)
 result = parse_llm_classification_response(response.content)

 # After:
 from scrappy.llm.models import TaskClassification

 async def _classify_with_llm(self, task: ClassifiedTask) -> ClassifiedTask:
     result = await self.orchestrator.delegate_structured(
         provider_name="fast",
         prompt=user_prompt,
         response_model=TaskClassification,
         system_prompt=system_prompt,
     )
     # result is now a validated TaskClassification instance

 Phase 5: Unit Tests (Required)

 Mock strategy: Use MagicMock on router.acompletion to simulate bad/good JSON flow. Do NOT hit real APIs.

 Test cases:
 - Model returns valid JSON → parses under 500ms
 - Model returns malformed JSON → instructor retries exactly once (verify counter)
 - Model returns JSON that passes Pydantic but violates business rule → catch ValidationError, raise TaskRouterError
 - Asyncio event-loop is NOT created in thread-worker (would deadlock)
 - Observability: verify LiteLLM logs both calls on retry (failure + success)

 Phase 6: Cleanup

 - Delete src/scrappy/llm/ directory (adapters moved into LiteLLMService)
 - Update tests

 Phase 7 (LATER): Research Loop

 After classification works, expand to research_loop.py tool parsing.

 Files to Modify (This PR)

 1. src/scrappy/orchestrator/litellm_service.py - add completion_structured
 2. src/scrappy/orchestrator/protocols.py - add StructuredOutputProtocol
 3. src/scrappy/orchestrator/delegation.py - add delegate_structured
 4. src/scrappy/task_router/router.py - use structured output for classification
 5. src/scrappy/llm/models.py - fix TaskType enum, keep only TaskClassification model

 Files to Delete

 - src/scrappy/llm/adapters.py
 - src/scrappy/llm/testing.py
 - tests/llm/test_adapters.py
 - tests/llm/test_models.py
 - tests/llm/test_testing.py