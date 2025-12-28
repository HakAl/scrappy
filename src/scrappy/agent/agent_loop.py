"""
Agent Loop - Coordinates the think-plan-execute-evaluate cycle.

This module extracts the core agent loop logic from CodeAgent into
a focused class following Single Responsibility Principle.

Single Responsibility: Run the agent loop, nothing else.

Extended in Phase 4 to support high-level plan-execute-verify loop
via the solve() method, integrating Planner and Verifier components.
"""

import time
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from ..orchestrator.model_selection import ModelSelectionType, AllModelsRateLimitedError
from .types import (
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState,
    DenialHandlerResult,
    AgentContext,
    OutcomeRecord,
    smart_truncate,
)
from .protocols import (
    AgentUIProtocol,
    ActionExecutorProtocol,
    ResponseParserProtocol,
    ToolRegistryProtocol,
    ProviderSelectionStrategyProtocol,
    DenialHandlerProtocol,
    AgentContextFactoryProtocol,
    PlannerProtocol,
    VerifierProtocol,
)
from .models import (
    Plan,
    Step,
    StepStatus,
    PlanExecutionState,
    VerificationResult,
    VerificationPolicy,
    ApprovalPolicy,
)
from .exceptions import (
    PlanRejectedError,
    StepExecutionError,
)
from .cancellation import CancellationTokenProtocol
from .stop_condition import AgentStopCondition, StopReason
from .completion_validator import (
    CompletionValidator,
    CompletionValidatorProtocol,
)
from scrappy.undo import create_undo_point, undo as undo_to_point, UndoError

if TYPE_CHECKING:
    from ..orchestrator_adapter import OrchestratorAdapter
    from ..agent_config import AgentConfig


class AgentLoop:
    """
    Coordinates the agent's think-plan-execute-evaluate cycle.

    Single Responsibility: Run the agent loop, nothing else.

    The loop follows clear stages:
    1. Think - LLM generates next thought/action
    2. Plan - Parse response into structured action
    3. Execute - Run the tool
    4. Evaluate - Check if task is complete
    5. Update - Update conversation history

    All dependencies are injected, making this class testable in isolation.
    """

    def __init__(
        self,
        orchestrator: "OrchestratorAdapter",
        action_executor: ActionExecutorProtocol,
        response_parser: ResponseParserProtocol,
        ui: AgentUIProtocol,
        tool_registry: ToolRegistryProtocol,
        provider_strategy: ProviderSelectionStrategyProtocol,
        config: "AgentConfig",
        context_factory: AgentContextFactoryProtocol,
        audit_logger: Any = None,  # AuditLoggerProtocol
        tools: Optional[Dict[str, Any]] = None,
        denial_handler: Optional[DenialHandlerProtocol] = None,
        cancellation_token: Optional[CancellationTokenProtocol] = None,
        stop_condition: Optional[AgentStopCondition] = None,
        tool_context: Optional[Any] = None,  # ToolContext for HUD turn tracking
        completion_validator: Optional[CompletionValidatorProtocol] = None,
        project_root: Optional[str] = None,  # For git checkpoints
        # Phase 4: Planner and Verifier integration
        planner: Optional[PlannerProtocol] = None,
        verifier: Optional[VerifierProtocol] = None,
        verification_policy: Optional[VerificationPolicy] = None,
        approval_policy: Optional[ApprovalPolicy] = None,
    ):
        """
        Initialize AgentLoop with injected dependencies.

        Args:
            orchestrator: OrchestratorAdapter for LLM calls
            action_executor: ActionExecutor for tool execution
            response_parser: ResponseParser for parsing LLM output
            ui: AgentUI for user interaction
            tool_registry: ToolRegistry for tool schemas
            provider_strategy: Strategy for selecting providers
            config: AgentConfig with settings
            context_factory: Factory for building AgentContext per iteration
            audit_logger: Optional audit logger
            tools: Optional tools dict for backward compat
            denial_handler: Optional handler for user denials
            cancellation_token: Optional token for cancellation signaling
            stop_condition: Unified stop condition tracker (created if not provided)
            tool_context: Optional ToolContext for HUD turn tracking
            completion_validator: Validator for task completion (created if not provided)
            project_root: Project root path for git checkpoints
            planner: Optional Planner for creating execution plans
            verifier: Optional Verifier for running pytest/ruff/mypy
            verification_policy: Policy controlling verification strictness
            approval_policy: Policy controlling plan/step approval
        """
        self._orchestrator = orchestrator
        self._project_root = project_root or "."
        self._action_executor = action_executor
        self._response_parser = response_parser
        self._ui = ui
        self._tool_registry = tool_registry
        self._provider_strategy = provider_strategy
        self._config = config
        self._context_factory = context_factory
        self._audit_logger = audit_logger
        self._tools = tools or {}
        self._denial_handler = denial_handler
        self._cancellation_token = cancellation_token
        self._tool_context = tool_context  # For HUD turn tracking

        # Unified stop condition - single source of truth for termination
        self._stop_condition = stop_condition or AgentStopCondition(
            cancellation_token=cancellation_token,
            max_iterations=config.max_iterations if hasattr(config, 'max_iterations') else 50,
        )

        # Completion validator - checks for meaningful work before allowing completion
        self._completion_validator = completion_validator or CompletionValidator(
            meaningful_actions=set(config.meaningful_actions)
        )

        # Track current dry_run state
        self._dry_run = False

        # Phase 4: Planner and Verifier for plan-execute-verify loop
        self._planner = planner
        self._verifier = verifier
        self._verification_policy = verification_policy or VerificationPolicy()
        self._approval_policy = approval_policy or ApprovalPolicy()

    def think(self, state: ConversationState, context: AgentContext) -> AgentThought:
        """
        Generate the next thought/action from the LLM.

        This is the reasoning stage where the agent decides what to do next.
        Includes retry logic for truncated responses (finish_reason == 'length').

        Args:
            state: Current conversation state
            context: Agent context with system prompt and RAG data

        Returns:
            AgentThought containing raw LLM response
        """
        # Get current recommended provider
        current_provider = self._provider_strategy.get_planner()

        # Show progress indicator during API call
        if state.iteration == 1:
            self._ui.show_provider_status(
                current_provider, "Analyzing task (this may take a moment)..."
            )
        else:
            self._ui.show_provider_status(current_provider, "Thinking...")

        # Determine prompt and messages for multi-turn conversation
        # First iteration: use prompt string
        # Subsequent iterations: pass full messages array to preserve role separation
        if len(state.messages) == 2:
            # First iteration: just use the task as prompt
            user_prompt = state.messages[-1]['content']
            messages_to_send = None
        else:
            # Multi-turn: pass full messages array (don't flatten to string)
            user_prompt = ""  # Not used when messages provided
            messages_to_send = state.messages

        # Track API call time for first iteration
        start_time = time.time()

        # Check if orchestrator adapter has delegate_with_tools
        # and if provider supports native tool calling
        has_delegate_with_tools = hasattr(self._orchestrator, 'delegate_with_tools')
        provider_supports_tools = self._check_provider_supports_tools(current_provider)

        # Retry logic for truncated responses
        # Start with default, double on each retry up to max
        max_tokens = self._config.default_max_tokens
        max_retries = 2  # Allow 2 retries with higher limits
        max_token_limit = 8000  # Cap to prevent excessive token usage

        for attempt in range(max_retries + 1):
            # Use native tool calling if both adapter and provider support it
            if has_delegate_with_tools and provider_supports_tools:
                response = self._delegate_with_tools(
                    current_provider, user_prompt, context.system_prompt,
                    messages=messages_to_send,
                    max_tokens=max_tokens,
                )
                actual_provider = response.provider
            else:
                # Fall back to regular delegate with JSON parsing
                if self._provider_strategy.supports_dynamic_selection():
                    response = self._orchestrator.delegate(
                        provider_name=None,  # Let orchestrator decide
                        prompt=user_prompt,
                        system_prompt=context.system_prompt,
                        max_tokens=max_tokens,
                        temperature=self._config.default_temperature,
                        use_context=False,  # Context already in system prompt
                        selection_type=ModelSelectionType.INSTRUCT,
                        messages=messages_to_send,
                    )
                    actual_provider = response.provider
                else:
                    response = self._orchestrator.delegate(
                        current_provider,
                        user_prompt,
                        system_prompt=context.system_prompt,
                        max_tokens=max_tokens,
                        temperature=self._config.default_temperature,
                        use_context=False,  # Context already in system prompt
                        selection_type=ModelSelectionType.INSTRUCT,
                        messages=messages_to_send,
                    )
                    actual_provider = current_provider

            # Check for truncation and retry with higher limit if needed
            if self._is_truncated(response) and attempt < max_retries:
                new_max_tokens = min(max_tokens * 2, max_token_limit)
                if new_max_tokens > max_tokens:
                    self._ui.show_warning(
                        f"Response truncated, retrying with higher limit "
                        f"({max_tokens} -> {new_max_tokens} tokens)"
                    )
                    max_tokens = new_max_tokens
                    continue
            break

        # Report latency on first call
        if state.iteration == 1:
            elapsed = time.time() - start_time
            self._ui.show_provider_status(
                actual_provider, f"Response received ({elapsed:.1f}s)", color="green"
            )

        return AgentThought(
            raw_response=response.content,
            provider=actual_provider,
            iteration=state.iteration,
            llm_response=response,  # Store full response for native tool calls
        )

    def _check_provider_supports_tools(self, provider_name: str) -> bool:
        """Check if provider supports native tool calling."""
        # Access orchestrator's registry to check provider capabilities
        orchestrator = self._orchestrator
        # Handle adapter wrapping
        if hasattr(orchestrator, '_orchestrator'):
            orchestrator = orchestrator._orchestrator
        if hasattr(orchestrator, '_registry'):
            provider_obj = orchestrator._registry.get(provider_name)
            if provider_obj and hasattr(provider_obj, 'supports_tool_calling'):
                return provider_obj.supports_tool_calling
        return False

    def _delegate_with_tools(
        self, provider: str, prompt: str, system_prompt: str,
        messages: Optional[list[dict]] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Delegate to orchestrator with native tool calling."""
        # Get tool schemas from registry (single source of truth)
        tools = self._tool_registry.to_openai_schema()

        return self._orchestrator.delegate_with_tools(
            provider_name=provider,
            prompt=prompt,
            tools=tools,
            system_prompt=system_prompt,
            max_tokens=max_tokens or self._config.default_max_tokens,
            temperature=self._config.default_temperature,
            tool_choice="auto",
            selection_type=ModelSelectionType.INSTRUCT,
            messages=messages,
        )

    def _is_truncated(self, response: Any) -> bool:
        """
        Check if response was truncated due to max_tokens limit.

        Args:
            response: LLMResponse object

        Returns:
            True if response was truncated (finish_reason == 'length')
        """
        if not hasattr(response, 'metadata'):
            return False
        finish_reason = response.metadata.get('finish_reason')
        return finish_reason == 'length'

    def plan(self, thought: AgentThought) -> List[AgentAction]:
        """
        Parse the LLM response into structured actions.

        This is the planning stage where we extract the actions to take.
        Supports multiple tool calls from a single LLM response.

        Args:
            thought: Raw thought from think()

        Returns:
            List of AgentAction with parsed action details.
            First action is the primary action, additional ones follow.
        """
        # Check if we have a full LLMResponse with actual tool_calls
        if (
            thought.llm_response
            and thought.llm_response.tool_calls is not None
            and len(thought.llm_response.tool_calls) > 0
        ):
            # Use the response parser to handle LLMResponse objects
            parse_result = self._response_parser.parse(thought.llm_response)
        else:
            # Fall back to parsing raw text response (JSON format)
            parse_result = self._response_parser.parse(thought.raw_response)

        # Build list of actions starting with primary
        actions = [AgentAction(
            thought=parse_result.thought,
            action=parse_result.action,
            parameters=parse_result.parameters,
            is_complete=parse_result.is_complete,
            result_text=parse_result.result_text,
        )]

        # Add additional actions from multi-tool-call responses
        for additional in parse_result.additional_actions:
            actions.append(AgentAction(
                thought="",  # Only first action has the thought
                action=additional.action,
                parameters=additional.parameters,
                is_complete=additional.is_complete,
                result_text=additional.result_text,
            ))

        return actions

    def execute(self, action: AgentAction, state: ConversationState) -> ActionResult:
        """
        Execute the planned action (tool call).

        This is the execution stage where the tool is actually run.
        Delegates to ActionExecutor for all execution logic.

        Args:
            action: Parsed action from plan()
            state: Current conversation state

        Returns:
            ActionResult with execution details
        """
        result = self._action_executor.execute(action, state, dry_run=self._dry_run)

        # Log action for audit trail (including blocked actions for transparency)
        if self._audit_logger:
            # Log both executed and blocked actions
            is_blocked = not result.executed and result.approved  # Approved but not executed = blocked
            if result.executed or is_blocked:
                self._audit_logger.log_action(
                    action.action,
                    action.parameters,
                    result.output,
                    result.approved,
                    thinking=action.thought,
                    blocked=is_blocked,
                )

        return result

    def execute_batch(
        self,
        actions: List[AgentAction],
        state: ConversationState
    ) -> List[ActionResult]:
        """
        Execute multiple actions with batch confirmation.

        Uses ActionExecutor.execute_batch() for batch confirmation and
        sequential execution with fail-fast behavior.

        Args:
            actions: List of parsed actions from plan()
            state: Current conversation state

        Returns:
            List of ActionResult, one per action executed
        """
        results = self._action_executor.execute_batch(
            actions, state, dry_run=self._dry_run
        )

        # Log each action for audit trail
        if self._audit_logger:
            for action, result in zip(actions, results):
                is_blocked = not result.executed and result.approved
                if result.executed or is_blocked:
                    self._audit_logger.log_action(
                        action.action,
                        action.parameters,
                        result.output,
                        result.approved,
                        thinking=action.thought,
                        blocked=is_blocked,
                    )

        return results

    def evaluate(
        self,
        action: AgentAction,
        result: ActionResult,
        state: ConversationState,
    ) -> EvaluationResult:
        """
        Evaluate whether the task is complete and if we should continue.

        This is the evaluation stage where we check completion criteria.

        Args:
            action: The action that was planned
            result: The result of executing the action
            state: Current conversation state

        Returns:
            EvaluationResult indicating whether to continue or complete
        """
        # Check if task is complete via metadata (from CompleteTool execution)
        if result.metadata.get("stop_loop", False):
            # Validate completion - checks for meaningful work
            complete_attempts = state.tools_executed.count('complete')
            validation = self._completion_validator.validate(
                tools_executed=state.tools_executed,
                task_description="",  # Not used for current checks
                result_text=action.result_text,
                complete_attempts=complete_attempts,  # Count of previous attempts (current not yet recorded)
            )

            if not validation.allow_completion:
                self._ui.show_warning(f"Completion blocked: {validation.reason}")
                if validation.suggestions:
                    for suggestion in validation.suggestions:
                        self._ui.show_info(f"  - {suggestion}")
                return EvaluationResult(
                    is_complete=False,
                    should_continue=True,
                    reason=validation.reason,
                )

            final_result = action.result_text or 'Task completed'
            # Use show_completion if available (compact mode aware)
            if hasattr(self._ui, 'show_completion'):
                self._ui.show_completion(final_result, success=True)
            else:
                self._ui.show_rule("Task Complete")
                self._ui.show_result(final_result, title="Final Result")

            # Note: 'complete' action already logged in execute() stage
            # Don't log again here to avoid duplicate audit entries

            return EvaluationResult(
                is_complete=True,
                should_continue=False,
                reason="Task marked as complete",
                final_result=final_result,
            )

        # Check max iterations
        if state.iteration >= state.max_iterations:
            return EvaluationResult(
                is_complete=False,
                should_continue=False,
                reason=f"Max iterations ({state.max_iterations}) reached",
            )

        # Continue with more iterations
        return EvaluationResult(
            is_complete=False,
            should_continue=True,
            reason="Task not yet complete",
        )

    def update_conversation(
        self,
        state: ConversationState,
        thought: AgentThought,
        action: AgentAction,
        result: ActionResult,
    ) -> Optional[DenialHandlerResult]:
        """
        Update the conversation history based on the action and result.

        Args:
            state: Conversation state to update
            thought: The raw thought from LLM
            action: The parsed action
            result: The execution result

        Returns:
            DenialHandlerResult if action was denied, None otherwise
        """
        if result.executed:
            self._handle_executed_action(state, thought, action, result)
            return None
        elif not result.approved and action.action in self._tools:
            return self._handle_denied_action(state, thought, result)
        elif result.approved and not result.executed and action.action in self._tools:
            self._handle_blocked_action(state, thought, result)
            return None
        elif action.action == 'retry_parse':
            self._handle_parse_failure(state, thought, result)
            return None
        elif action.action not in self._tools and action.action != 'complete' and action.action != 'error':
            self._handle_unknown_action(state, thought, action)
            return None
        elif action.is_complete and not result.executed:
            self._handle_premature_completion(state, thought)
            return None
        return None

    def _handle_executed_action(
        self,
        state: ConversationState,
        thought: AgentThought,
        action: AgentAction,
        result: ActionResult,
    ) -> None:
        """Handle successfully executed action."""
        state.messages.append({
            'role': 'assistant',
            'content': thought.raw_response,
        })

        # Track action in history for duplicate detection
        action_record = {
            "action": result.action,
            "parameters": result.parameters,
        }
        state.action_history.append(action_record)
        state.last_action = action_record

        # Track failed commands for retry detection
        if action.action == 'run_command' and not result.success:
            command = action.parameters.get('command', '')
            if command:
                approach = self._categorize_command_approach(command)
                state.failed_commands.append({
                    'command': command,
                    'error': result.output[:200],
                    'approach': approach,
                    'iteration': state.iteration,
                })

        # Build user message with tool result and any retry warnings
        user_message = f"Tool result for {result.action}:\n{result.output}\n"

        # Inject retry warnings if any failures were tracked
        if state.retry_warnings:
            user_message += "\n--- IMPORTANT WARNINGS ---\n"
            for warning in state.retry_warnings:
                user_message += f"- {warning}\n"
            user_message += "--- END WARNINGS ---\n"
            state.retry_warnings.clear()

        # For write_file operations, encourage verification
        if result.action == 'write_file':
            file_path = result.parameters.get('path', 'the file')
            user_message += (
                f"\nSuggestion: Consider reading {file_path} "
                "to verify the content is correct.\n"
            )

        user_message += "\nContinue with the task or mark as complete if done."

        state.messages.append({
            'role': 'user',
            'content': user_message,
        })
        state.tools_executed.append(result.action)

        # Record outcome for HUD display
        outcome = OutcomeRecord(
            turn=state.iteration,
            tool=result.action,
            success=result.success,
            summary=smart_truncate(result.output, result.success),
        )
        state.recent_outcomes.append(outcome)

        # Keep only last 3 outcomes
        if len(state.recent_outcomes) > 3:
            state.recent_outcomes = state.recent_outcomes[-3:]

    def _handle_denied_action(
        self,
        state: ConversationState,
        thought: AgentThought,
        result: ActionResult,
    ) -> DenialHandlerResult:
        """
        Handle action denied by user.

        Args:
            state: Conversation state to update
            thought: The raw thought from LLM
            result: The action result

        Returns:
            DenialHandlerResult with should_stop flag and message
        """
        # Record denial in stop condition (tracks consecutive denials)
        self._stop_condition.record_denial()
        denial_count = self._stop_condition.consecutive_denials

        # Use denial handler if available
        if self._denial_handler:
            denial_result = self._denial_handler.handle_denial(
                action=result.action,
                denial_count=denial_count,
            )
        else:
            # Default behavior: continue with message
            denial_result = DenialHandlerResult(
                should_stop=False,
                message=(
                    f"User denied the {result.action} action. "
                    "Please try a different approach or explain why this action is necessary."
                ),
            )

        # Update conversation with denial message
        state.messages.append({
            'role': 'assistant',
            'content': thought.raw_response,
        })
        state.messages.append({
            'role': 'user',
            'content': denial_result.message,
        })

        return denial_result

    def _handle_blocked_action(
        self,
        state: ConversationState,
        thought: AgentThought,
        result: ActionResult,
    ) -> None:
        """Handle action blocked (e.g., duplicate detected)."""
        state.messages.append({
            'role': 'assistant',
            'content': thought.raw_response,
        })
        state.messages.append({
            'role': 'user',
            'content': result.output,  # Contains warning message
        })

    def _handle_parse_failure(
        self,
        state: ConversationState,
        thought: AgentThought,
        result: ActionResult,
    ) -> None:
        """Handle parse failure - provide format instructions."""
        state.messages.append({
            'role': 'assistant',
            'content': thought.raw_response,
        })
        state.messages.append({
            'role': 'user',
            'content': result.output,  # Contains JSON format instructions
        })

    def _handle_unknown_action(
        self,
        state: ConversationState,
        thought: AgentThought,
        action: AgentAction,
    ) -> None:
        """Handle unknown action."""
        state.messages.append({
            'role': 'assistant',
            'content': thought.raw_response,
        })
        state.messages.append({
            'role': 'user',
            'content': (
                f"Unknown action '{action.action}'. "
                f"Available tools: {', '.join(self._tools.keys())}"
            ),
        })

    def _handle_premature_completion(
        self,
        state: ConversationState,
        thought: AgentThought,
    ) -> None:
        """Handle premature completion without meaningful work."""
        complete_attempts = state.tools_executed.count('complete')
        validation = self._completion_validator.validate(
            tools_executed=state.tools_executed,
            task_description="",
            result_text=None,
            complete_attempts=complete_attempts,
        )

        # Only push back if validation fails
        if not validation.allow_completion:
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response,
            })
            state.messages.append({
                'role': 'user',
                'content': (
                    "You declared the task complete but haven't actually created "
                    "or modified any files. Please respond with a JSON object "
                    "containing an action to execute. Use the write_file tool to "
                    "actually create the requested code. Example format:\n"
                    "{\n"
                    '  "thought": "your reasoning",\n'
                    '  "action": "write_file",\n'
                    '  "parameters": {"path": "filename", "content": "code here"}\n'
                    "}"
                ),
            })

    def _categorize_command_approach(self, command: str) -> str:
        """
        Categorize a command into an approach type for retry tracking.

        Args:
            command: The shell command

        Returns:
            String describing the approach type
        """
        cmd_lower = command.lower()

        # Package managers
        if 'npm' in cmd_lower or 'npx' in cmd_lower:
            return 'npm'
        if 'yarn' in cmd_lower:
            return 'yarn'
        if 'pip' in cmd_lower:
            return 'pip'

        # Build tools
        if 'make' in cmd_lower:
            return 'make'
        if 'cargo' in cmd_lower:
            return 'cargo'
        if 'go build' in cmd_lower or 'go run' in cmd_lower:
            return 'go'

        # Generic categorization
        parts = command.split()
        if parts:
            return parts[0]
        return 'unknown'

    def run(
        self,
        task: str,
        state: ConversationState,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the complete agent loop until completion or max iterations.

        Args:
            task: Task description (for context building)
            state: ConversationState to track progress
            dry_run: If True, simulate execution

        Returns:
            Dict with 'success', 'result', 'iterations', 'stop_reason'
        """
        self._dry_run = dry_run

        # Reset stop condition and step counter for new task
        self._stop_condition.reset()
        if hasattr(self._ui, 'reset_step_counter'):
            self._ui.reset_step_counter()

        self._ui.show_progress("Starting agent loop...")

        while True:
            # Unified stop check at start of each iteration
            should_stop, reason = self._stop_condition.should_stop()
            if should_stop:
                return self._make_stop_result(reason, state)

            self._stop_condition.increment_iteration()
            state.iteration = self._stop_condition.current_iteration

            # Increment HUD turn counter (for working set tracking)
            if self._tool_context is not None:
                self._tool_context.turn = state.iteration

            # Stage 1: Think - LLM generates next thought/action
            try:
                context = self._context_factory.build_context(task, state.system_prompt)

                # Inject HUD message for recency bias (temporary, removed after think)
                hud_message = self._context_factory.build_hud_message(state)
                if hud_message:
                    state.messages.append(hud_message)

                thought = self.think(state, context)

                # Remove HUD message to avoid permanent accumulation in history
                if hud_message and state.messages and state.messages[-1] == hud_message:
                    state.messages.pop()

                self._stop_condition.clear_network_errors()
            except AllModelsRateLimitedError as e:
                self._stop_condition.mark_rate_limited()
                self._ui.show_error(str(e))
                return self._make_stop_result(StopReason.RATE_LIMITED, state)
            except ValueError as e:
                # Configuration errors (e.g., no models configured for selection type)
                self._ui.show_error(f"Configuration error: {e}")
                return {
                    'success': False,
                    'result': f"Configuration error: {e}",
                    'iterations': state.iteration,
                    'stop_reason': 'configuration_error',
                }
            except Exception as e:
                # Network/API errors
                if self._is_network_error(e):
                    self._stop_condition.record_network_error()
                    self._ui.show_warning(f"Network error: {e}")
                    should_stop, reason = self._stop_condition.should_stop()
                    if should_stop:
                        return self._make_stop_result(reason, state)
                    continue  # Retry
                raise

            # Check stop condition after LLM call (can be slow)
            should_stop, reason = self._stop_condition.should_stop()
            if should_stop:
                return self._make_stop_result(reason, state)

            # Stage 2: Plan - Parse response into structured actions
            # (supports multiple tool calls from a single LLM response)
            actions = self.plan(thought)

            # Track parse failures (check first action)
            if actions[0].action == 'retry_parse':
                self._stop_condition.record_parse_failure()
                should_stop, reason = self._stop_condition.should_stop()
                if should_stop:
                    return self._make_stop_result(reason, state)
            else:
                self._stop_condition.clear_parse_failures()

            # Check stop condition before execute
            should_stop, reason = self._stop_condition.should_stop()
            if should_stop:
                return self._make_stop_result(reason, state)

            # Stage 3: Execute - Run the tool(s)
            # Use batch execution for multiple actions, single for one
            if len(actions) == 1:
                results = [self.execute(actions[0], state)]
            else:
                results = self.execute_batch(actions, state)

            # Check if any action was cancelled
            if any(r.metadata.get("cancelled") for r in results):
                return self._make_stop_result(StopReason.USER_CANCELLED, state)

            # Check stop condition after execute (tools can take a long time)
            should_stop, reason = self._stop_condition.should_stop()
            if should_stop:
                return self._make_stop_result(reason, state)

            # Stage 4: Evaluate - Check if task is complete
            # Use last action/result for evaluation (completion is typically last)
            last_action = actions[-1] if len(results) == len(actions) else actions[len(results) - 1]
            last_result = results[-1]
            evaluation = self.evaluate(last_action, last_result, state)

            # Update conversation history for all actions/results
            denial_result = None
            any_approved = False
            for action, result in zip(actions, results):
                denial_result = self.update_conversation(state, thought, action, result)
                if result.approved:
                    any_approved = True
                # Only process first action's thought (others have empty thought)
                thought = AgentThought(
                    raw_response="",
                    provider=thought.provider,
                    iteration=thought.iteration,
                    llm_response=None
                )

            # Handle denial result (denial already recorded in _handle_denied_action)
            if denial_result:
                if denial_result.should_stop:
                    return self._make_stop_result(StopReason.REPEATED_DENIALS, state)
            elif any_approved:
                self._stop_condition.clear_denials()

            # Check evaluation result
            if evaluation.is_complete:
                self._stop_condition.mark_completed()
                return {
                    'success': True,
                    'result': evaluation.final_result,
                    'iterations': state.iteration,
                    'stop_reason': StopReason.COMPLETED.value,
                }

            if not evaluation.should_continue:
                return {
                    'success': False,
                    'result': evaluation.reason,
                    'iterations': state.iteration,
                    'stop_reason': StopReason.MAX_ITERATIONS.value,
                }

            # Safety checkpoint - ask user to continue every N iterations
            # Works even in auto_confirm mode as a safety net
            if (state.checkpoint_interval > 0 and
                state.iteration % state.checkpoint_interval == 0):
                result = self._handle_safety_checkpoint(state)
                if result is not None:
                    return result

    def _make_stop_result(self, reason: StopReason, state: ConversationState) -> Dict[str, Any]:
        """Create a standardized stop result dictionary."""
        message = self._stop_condition.get_stop_message(reason)

        # Log cancellation
        if reason == StopReason.USER_CANCELLED and self._audit_logger:
            self._audit_logger.log_action('cancelled', {}, message, True)

        # Show appropriate UI message
        if reason == StopReason.USER_CANCELLED:
            self._ui.show_warning(message)
        elif reason in (StopReason.RATE_LIMITED, StopReason.NETWORK_ERROR):
            self._ui.show_error(message)
        elif reason == StopReason.PARSE_FAILURES:
            self._ui.show_error(message)
        elif reason == StopReason.REPEATED_DENIALS:
            self._ui.show_warning(message)

        return {
            'success': reason == StopReason.COMPLETED,
            'result': message,
            'iterations': state.iteration,
            'stop_reason': reason.value,
        }

    def _is_network_error(self, error: Exception) -> bool:
        """Check if an exception is a network-related error."""
        error_str = str(error).lower()
        network_indicators = [
            'connection', 'timeout', 'network', 'socket',
            'refused', 'reset', 'unreachable', 'dns',
        ]
        return any(indicator in error_str for indicator in network_indicators)

    def _handle_safety_checkpoint(
        self, state: ConversationState
    ) -> Optional[Dict[str, Any]]:
        """
        Handle safety checkpoint with multi-option prompt.

        Prompts user with options to continue, create undo point,
        enable allow-all mode, or stop. Works even in auto_confirm mode.

        Args:
            state: Current conversation state

        Returns:
            None to continue, or a result dict to stop the agent
        """
        tools_count = len(state.tools_executed)
        choice = self._ui.prompt_checkpoint(state.iteration, tools_count)

        if choice == 'c':
            # Continue
            self._ui.show_progress("Continuing...")
            return None

        elif choice == 'g':
            # Create undo point then continue
            self._ui.show_progress("Creating undo point...")
            try:
                undo_state = create_undo_point()
                state.last_checkpoint_hash = undo_state.ref
                self._ui.show_info(f"Undo point created: {undo_state.ref.split('/')[-1]}")
            except UndoError as e:
                self._ui.show_warning(f"Could not create undo point: {e}")
            return None

        elif choice == 'a':
            # Enable allow-all mode
            state.allow_all_enabled = True
            self._ui.show_progress("Allow-all mode enabled for remaining actions")
            return None

        else:  # choice == 's'
            # Stop
            return {
                'success': False,
                'result': f'Stopped at checkpoint (iteration {state.iteration})',
                'iterations': state.iteration,
                'stop_reason': StopReason.USER_CANCELLED.value,
            }

    # =========================================================================
    # Phase 4: Plan-Execute-Verify Loop (solve method)
    # =========================================================================

    async def solve(
        self,
        user_input: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        High-level plan-execute-verify loop.

        This is the main entry point for structured task execution with
        planning, user approval, step execution, and verification.

        Flow:
        1. Create plan via Planner
        2. Get user approval (ALWAYS required)
        3. For each step:
           a. Show progress: "[Step 2/5] Writing login endpoint..."
           b. Git checkpoint if modifying step
           c. Execute step
           d. Verify step if modifying
           e. On failure: retry up to 3x
           f. On max retries: escape hatch prompt
        4. Final plan verification
        5. Return results

        Args:
            user_input: The user's request or goal
            context: Optional additional context (e.g., file contents, errors)

        Returns:
            Dict with:
                - success: bool
                - plan: Plan object
                - completed_steps: list of completed step IDs
                - failed_steps: list of failed step IDs
                - verification_result: final verification result if any
                - stop_reason: why execution stopped

        Raises:
            ValueError: If planner is not configured
            PlanRejectedError: If user rejects the plan

        Note:
            This is an async method. Callers must run it within an async context
            (e.g., via asyncio.run() or from another async function). A synchronous
            solve_sync() wrapper may be added in a future release.
        """
        if self._planner is None:
            raise ValueError("Planner is required for solve(). Pass planner to AgentLoop.__init__.")

        # Step 1: Create plan
        self._ui.show_progress("Creating execution plan...")
        plan = await self._planner.create_plan(user_input, context)

        # Step 2: Get user approval (ALWAYS required)
        approved = await self._get_plan_approval(plan)
        if not approved:
            raise PlanRejectedError(plan_id=plan.id, reason="User declined to execute plan")

        # Mark plan as approved
        from datetime import datetime, timezone
        plan.approved_at = datetime.now(timezone.utc)

        # Initialize execution state
        execution_state = PlanExecutionState(
            plan=plan,
            current_step_index=0,
            checkpoint_hash=None,
            step_checkpoints={},
            started_at=datetime.now(timezone.utc),
        )

        # Create initial checkpoint before execution starts
        initial_checkpoint = await self._checkpoint_if_needed(
            Step(id="initial", description="Initial checkpoint", is_read_only=False)
        )
        if initial_checkpoint:
            execution_state.checkpoint_hash = initial_checkpoint

        completed_steps: List[str] = []
        failed_steps: List[str] = []

        # Step 3: Execute each step
        for i, step in enumerate(plan.steps):
            # Show progress
            self._show_step_progress(plan, step)

            # Track files that may be changed by this step
            changed_files: List[str] = []

            # Create checkpoint for modifying steps
            step_checkpoint = None
            if not step.is_read_only:
                step_checkpoint = await self._checkpoint_if_needed(step)
                if step_checkpoint:
                    execution_state.step_checkpoints[step.id] = step_checkpoint

            # Execute with retry logic
            max_retries = self._verification_policy.max_fix_attempts
            retry_count = 0
            step_success = False

            while retry_count < max_retries:
                try:
                    # Mark step as in progress
                    step.mark_started()

                    # Execute the step
                    result = await self._execute_step(step)
                    step.execution_result = result

                    # Track changed files (extract from step parameters or result)
                    changed_files = self._extract_changed_files(step, result)

                    # Verify if needed
                    if not step.is_read_only and self._verifier is not None:
                        verification = await self._verify_step(step, changed_files)
                        step.verification_result = verification

                        if not verification.success:
                            retry_count += 1
                            step.retry_count = retry_count

                            if retry_count >= max_retries:
                                # Max retries exceeded - escape hatch
                                choice = await self._handle_step_failure(
                                    step, verification.message
                                )

                                if choice == "edit":
                                    # Future: allow plan editing
                                    self._ui.show_warning("Plan editing not yet implemented. Aborting.")
                                    step.mark_failed("User requested plan edit")
                                    failed_steps.append(step.id)
                                    return self._make_solve_result(
                                        success=False,
                                        plan=plan,
                                        completed_steps=completed_steps,
                                        failed_steps=failed_steps,
                                        stop_reason="edit_requested",
                                    )

                                elif choice == "skip":
                                    step.status = StepStatus.SKIPPED
                                    self._ui.show_info(f"Skipping step: {step.description}")
                                    break  # Exit retry loop

                                elif choice == "rollback":
                                    if step_checkpoint:
                                        await self._rollback_to_checkpoint(step_checkpoint)
                                        self._ui.show_info(f"Rolled back to checkpoint: {step_checkpoint[:8]}")
                                    else:
                                        self._ui.show_warning("No checkpoint available for rollback")
                                    step.mark_failed("Rolled back after failures")
                                    failed_steps.append(step.id)
                                    return self._make_solve_result(
                                        success=False,
                                        plan=plan,
                                        completed_steps=completed_steps,
                                        failed_steps=failed_steps,
                                        stop_reason="rollback",
                                    )

                                else:  # abort
                                    step.mark_failed("User aborted after failures")
                                    failed_steps.append(step.id)
                                    return self._make_solve_result(
                                        success=False,
                                        plan=plan,
                                        completed_steps=completed_steps,
                                        failed_steps=failed_steps,
                                        stop_reason="abort",
                                    )

                            else:
                                # Retry - show message and continue loop
                                self._ui.show_warning(
                                    f"Step verification failed (attempt {retry_count}/{max_retries}): "
                                    f"{verification.message}"
                                )
                                continue

                    # Step completed successfully
                    step.mark_completed(result)
                    completed_steps.append(step.id)
                    step_success = True
                    break

                except StepExecutionError as e:
                    retry_count += 1
                    step.retry_count = retry_count

                    if retry_count > max_retries:
                        choice = await self._handle_step_failure(step, str(e))

                        if choice == "skip":
                            step.status = StepStatus.SKIPPED
                            break
                        elif choice == "rollback" and step_checkpoint:
                            await self._rollback_to_checkpoint(step_checkpoint)
                            step.mark_failed(f"Rolled back: {e}")
                            failed_steps.append(step.id)
                            return self._make_solve_result(
                                success=False,
                                plan=plan,
                                completed_steps=completed_steps,
                                failed_steps=failed_steps,
                                stop_reason="rollback",
                            )
                        else:
                            step.mark_failed(str(e))
                            failed_steps.append(step.id)
                            return self._make_solve_result(
                                success=False,
                                plan=plan,
                                completed_steps=completed_steps,
                                failed_steps=failed_steps,
                                stop_reason="abort",
                            )
                    else:
                        self._ui.show_warning(
                            f"Step execution failed (attempt {retry_count}/{max_retries}): {e}"
                        )
                        continue

            # If step was neither completed nor skipped, it failed
            if not step_success and step.status != StepStatus.SKIPPED:
                step.mark_failed("Max retries exceeded")
                failed_steps.append(step.id)

        # Step 4: Final plan verification
        final_verification = None
        if self._verifier is not None and completed_steps:
            self._ui.show_progress("Running final verification...")
            final_verification = await self._verifier.verify_plan(plan)

            if not final_verification.success:
                self._ui.show_warning(f"Plan verification failed: {final_verification.message}")
                return self._make_solve_result(
                    success=False,
                    plan=plan,
                    completed_steps=completed_steps,
                    failed_steps=failed_steps,
                    verification_result=final_verification,
                    stop_reason="verification_failed",
                )

        # Step 5: Return results
        execution_state.completed_at = datetime.now(timezone.utc)
        all_success = len(failed_steps) == 0 and len(completed_steps) == len(plan.steps)

        return self._make_solve_result(
            success=all_success,
            plan=plan,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            verification_result=final_verification,
            stop_reason="completed" if all_success else "partial_success",
        )

    async def _get_plan_approval(self, plan: Plan) -> bool:
        """
        Show plan and get user approval. Returns True if approved.

        Displays the plan with all steps and prompts the user with:
        "Execute this plan? [Y]es / [N]o / [E]dit"

        Args:
            plan: The plan to display and get approval for

        Returns:
            True if user approved, False otherwise
        """
        # Display the plan
        self._ui.show_rule("Execution Plan")
        self._ui.show_info(f"Goal: {plan.goal}")
        self._ui.show_info("")

        for i, step in enumerate(plan.steps, 1):
            tool_info = f" [{step.tool}]" if step.tool else ""
            read_only_marker = " (read-only)" if step.is_read_only else ""
            self._ui.show_info(f"  {i}. {step.description}{tool_info}{read_only_marker}")

        self._ui.show_info("")

        # Prompt for approval
        # Use confirm method which handles Y/N responses
        response = self._ui.confirm(
            "Execute this plan? (Y=yes, N=no, E=edit - edit not yet supported)",
            default=True
        )

        return response

    def _validate_step_parameters(self, step: Step) -> None:
        """
        Validate step parameters before execution.

        Security: Validates LLM-generated parameters to prevent:
        - Path traversal attacks in file paths
        - Shell metacharacters in filenames
        - Dangerous commands that bypassed plan approval

        Args:
            step: The step to validate

        Raises:
            StepExecutionError: If validation fails
        """
        from pathlib import Path
        import re

        # Validate file paths for write_file and edit_file
        if step.tool in ("write_file", "edit_file", "read_file"):
            path = step.parameters.get("path", "")
            if not isinstance(path, str):
                raise StepExecutionError(
                    message=f"Invalid path parameter type: {type(path)}",
                    step_id=step.id,
                    tool_name=step.tool,
                )

            # Check for path traversal
            if ".." in path:
                raise StepExecutionError(
                    message=f"Path traversal detected in path: {path}",
                    step_id=step.id,
                    tool_name=step.tool,
                )

            # Check for shell metacharacters in filename
            # (Could be used to break out of quoted paths)
            dangerous_chars = re.compile(r'[;&|`$(){}[\]<>\'\"\\]')
            filename = Path(path).name
            if dangerous_chars.search(filename):
                raise StepExecutionError(
                    message=f"Dangerous characters in filename: {filename}",
                    step_id=step.id,
                    tool_name=step.tool,
                )

        # Validate commands for run_command
        if step.tool == "run_command":
            command = step.parameters.get("command", "")
            if not isinstance(command, str):
                raise StepExecutionError(
                    message=f"Invalid command parameter type: {type(command)}",
                    step_id=step.id,
                    tool_name=step.tool,
                )
            # Note: Dangerous command check is done in _execute_step
            # where we can prompt the user for confirmation

    async def _execute_step(self, step: Step) -> str:
        """
        Execute a single step and return the result.

        Uses the existing agent loop's run() method for single-tool execution,
        or directly executes if tool is simple.

        Args:
            step: The step to execute

        Returns:
            String result from execution

        Raises:
            StepExecutionError: If step execution fails
        """
        if step.tool is None:
            # Think step or no-op - just return description
            return f"Completed: {step.description}"

        # Security: Validate step parameters before execution
        self._validate_step_parameters(step)

        try:
            # Build a minimal task for the step
            # This uses the existing action executor infrastructure
            action = AgentAction(
                thought=f"Executing step: {step.description}",
                action=step.tool,
                parameters=step.parameters,
                is_complete=False,
            )

            # Security: Even after plan approval, dangerous commands need confirmation
            # (Issue scrappy-cbu3)
            auto_confirm = True
            if step.tool == "run_command":
                command = step.parameters.get("command", "")
                if self._approval_policy.is_dangerous(command):
                    # Prompt user for dangerous commands even in approved plans
                    if not self._ui.confirm(f"Execute dangerous command: {command}?"):
                        raise StepExecutionError(
                            message="User declined dangerous command",
                            step_id=step.id,
                            tool_name=step.tool,
                        )

            # Create minimal state for execution
            state = ConversationState(
                messages=[],
                system_prompt="",
                iteration=1,
                auto_confirm=auto_confirm,  # Steps in approved plan are auto-confirmed
            )

            result = self.execute(action, state)

            if not result.success:
                raise StepExecutionError(
                    message=f"Step execution failed: {result.output}",
                    step_id=step.id,
                    tool_name=step.tool,
                )

            return result.output

        except Exception as e:
            if isinstance(e, StepExecutionError):
                raise
            raise StepExecutionError(
                message=str(e),
                step_id=step.id,
                tool_name=step.tool,
                original_error=e,
            ) from e

    async def _verify_step(
        self,
        step: Step,
        changed_files: List[str],
    ) -> VerificationResult:
        """
        Run verification on step if needed.

        Args:
            step: The completed step to verify
            changed_files: List of files that were modified

        Returns:
            VerificationResult with success status and any errors
        """
        if self._verifier is None:
            return VerificationResult(
                success=True,
                message="Verification skipped (no verifier configured)",
                files_checked=changed_files,
            )

        return await self._verifier.verify_step(step, changed_files)

    async def _handle_step_failure(self, step: Step, error: str) -> str:
        """
        Escape hatch when step fails after max retries.

        Prompts the user with options:
        "[E]dit plan, [S]kip step, [R]ollback, [A]bort?"

        Args:
            step: The step that failed
            error: Error message from the failure

        Returns:
            User choice: "edit", "skip", "rollback", or "abort"
        """
        self._ui.show_rule("Step Failed")
        self._ui.show_error(f"Step '{step.description}' failed after {step.retry_count} attempts.")
        self._ui.show_error(f"Error: {error}")
        self._ui.show_info("")
        self._ui.show_info("[E]dit plan  [S]kip step  [R]ollback  [A]bort")

        # Use Python's built-in input() with try/except wrapper
        # This avoids duck-typing the UI protocol
        while True:
            try:
                choice = input("> ").strip().lower()

                if choice in ('e', 'edit'):
                    return "edit"
                elif choice in ('s', 'skip'):
                    return "skip"
                elif choice in ('r', 'rollback'):
                    return "rollback"
                elif choice in ('a', 'abort', ''):
                    return "abort"
                else:
                    self._ui.show_warning("Invalid choice. Please enter E, S, R, or A.")
            except (EOFError, KeyboardInterrupt):
                return "abort"

    def _show_step_progress(self, plan: Plan, step: Step) -> None:
        """
        Display step progress: "[Step 2/5] Writing login endpoint..."

        Args:
            plan: The plan containing the step
            step: The current step being executed
        """
        try:
            step_index = plan.steps.index(step) + 1
        except ValueError:
            step_index = 1
        total_steps = len(plan.steps)

        self._ui.show_progress(f"[Step {step_index}/{total_steps}] {step.description}")

    async def _checkpoint_if_needed(self, step: Step) -> Optional[str]:
        """
        Create undo point before modifying steps.

        Only creates checkpoint for non-read-only steps.

        Args:
            step: The step about to be executed

        Returns:
            Undo ref of the checkpoint, or None if not needed/failed
        """
        if step.is_read_only:
            return None

        try:
            undo_state = create_undo_point()
            self._ui.show_info(f"Undo point: {undo_state.ref.split('/')[-1]}")
            return undo_state.ref
        except UndoError as e:
            self._ui.show_warning(f"Could not create undo point: {e}")
            return None

    async def _rollback_to_checkpoint(self, undo_ref: str) -> None:
        """
        Restore to undo point.

        Note: This uses the undo system which provides safer rollback.

        Args:
            undo_ref: The undo ref to roll back to (refs/scrappy/undo/...)
        """
        try:
            # Use undo(1) to restore to the most recent undo point
            # In the context of Phase 4 solve(), we've just created an undo point
            undo_to_point(n=1, force=True)
            short_ref = undo_ref.split('/')[-1] if '/' in undo_ref else undo_ref[:8]
            self._ui.show_info(f"Rolled back to: {short_ref}")
        except UndoError as e:
            self._ui.show_error(f"Failed to rollback: {e}")

    def _extract_changed_files(self, step: Step, result: str) -> List[str]:
        """
        Extract list of changed files from step parameters or result.

        Args:
            step: The executed step
            result: The execution result string

        Returns:
            List of file paths that were potentially modified
        """
        changed_files: List[str] = []

        # Check step parameters for file paths
        if step.tool in ("write_file", "edit_file"):
            path = step.parameters.get("path")
            if path and isinstance(path, str):
                changed_files.append(path)

        # For run_command, we can't easily know what files changed
        # The result might contain file paths, but parsing is unreliable

        return changed_files

    def _make_solve_result(
        self,
        success: bool,
        plan: Plan,
        completed_steps: List[str],
        failed_steps: List[str],
        verification_result: Optional[VerificationResult] = None,
        stop_reason: str = "completed",
    ) -> Dict[str, Any]:
        """
        Create a standardized result dictionary for solve().

        Args:
            success: Whether the overall operation succeeded
            plan: The execution plan
            completed_steps: List of completed step IDs
            failed_steps: List of failed step IDs
            verification_result: Final verification result if any
            stop_reason: Why execution stopped

        Returns:
            Dict with solve results
        """
        result: Dict[str, Any] = {
            "success": success,
            "plan": plan,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "stop_reason": stop_reason,
        }

        if verification_result is not None:
            result["verification_result"] = verification_result

        # Add summary
        total = len(plan.steps)
        completed = len(completed_steps)
        failed = len(failed_steps)
        skipped = total - completed - failed

        if success:
            result["summary"] = f"Plan completed successfully ({completed}/{total} steps)"
        else:
            result["summary"] = (
                f"Plan execution stopped: {stop_reason} "
                f"({completed} completed, {failed} failed, {skipped} skipped)"
            )

        return result
