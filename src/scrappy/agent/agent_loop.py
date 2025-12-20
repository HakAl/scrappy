"""
Agent Loop - Coordinates the think-plan-execute-evaluate cycle.

This module extracts the core agent loop logic from CodeAgent into
a focused class following Single Responsibility Principle.

Single Responsibility: Run the agent loop, nothing else.
"""

import time
from typing import Optional, Dict, Any, TYPE_CHECKING

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
)
from .cancellation import CancellationTokenProtocol
from .stop_condition import AgentStopCondition, StopReason
from .completion_validator import (
    CompletionValidator,
    CompletionValidatorProtocol,
)

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
        """
        self._orchestrator = orchestrator
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

    def think(self, state: ConversationState, context: AgentContext) -> AgentThought:
        """
        Generate the next thought/action from the LLM.

        This is the reasoning stage where the agent decides what to do next.

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

        # Use native tool calling if both adapter and provider support it
        if has_delegate_with_tools and provider_supports_tools:
            response = self._delegate_with_tools(
                current_provider, user_prompt, context.system_prompt,
                messages=messages_to_send
            )
            actual_provider = response.provider
        else:
            # Fall back to regular delegate with JSON parsing
            if self._provider_strategy.supports_dynamic_selection():
                response = self._orchestrator.delegate(
                    provider_name=None,  # Let orchestrator decide
                    prompt=user_prompt,
                    system_prompt=context.system_prompt,
                    max_tokens=self._config.default_max_tokens,
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
                    max_tokens=self._config.default_max_tokens,
                    temperature=self._config.default_temperature,
                    use_context=False,  # Context already in system prompt
                    selection_type=ModelSelectionType.INSTRUCT,
                    messages=messages_to_send,
                )
                actual_provider = current_provider

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
        messages: Optional[list[dict]] = None
    ) -> Any:
        """Delegate to orchestrator with native tool calling."""
        # Get tool schemas from registry (single source of truth)
        tools = self._tool_registry.to_openai_schema()

        return self._orchestrator.delegate_with_tools(
            provider_name=provider,
            prompt=prompt,
            tools=tools,
            system_prompt=system_prompt,
            max_tokens=self._config.default_max_tokens,
            temperature=self._config.default_temperature,
            tool_choice="auto",
            selection_type=ModelSelectionType.INSTRUCT,
            messages=messages,
        )

    def plan(self, thought: AgentThought) -> AgentAction:
        """
        Parse the LLM response into a structured action.

        This is the planning stage where we extract the action to take.

        Args:
            thought: Raw thought from think()

        Returns:
            AgentAction with parsed action details
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

        return AgentAction(
            thought=parse_result.thought,
            action=parse_result.action,
            parameters=parse_result.parameters,
            is_complete=parse_result.is_complete,
            result_text=parse_result.result_text,
        )

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
                complete_attempts=complete_attempts - 1,  # -1 because current attempt counted
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

            # Stage 2: Plan - Parse response into structured action
            action = self.plan(thought)

            # Track parse failures
            if action.action == 'retry_parse':
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

            # Stage 3: Execute - Run the tool
            result = self.execute(action, state)

            # Check if action was cancelled (force cancel detected in ActionExecutor)
            if result.metadata.get("cancelled"):
                return self._make_stop_result(StopReason.USER_CANCELLED, state)

            # Check stop condition after execute (tools can take a long time)
            should_stop, reason = self._stop_condition.should_stop()
            if should_stop:
                return self._make_stop_result(reason, state)

            # Stage 4: Evaluate - Check if task is complete
            evaluation = self.evaluate(action, result, state)

            # Update conversation history and check for denial
            denial_result = self.update_conversation(state, thought, action, result)

            # Handle denial result (denial already recorded in _handle_denied_action)
            if denial_result:
                if denial_result.should_stop:
                    return self._make_stop_result(StopReason.REPEATED_DENIALS, state)
            elif result.approved:
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

            # Soft checkpoint - ask user to continue every N iterations
            if (state.checkpoint_interval > 0 and
                state.iteration % state.checkpoint_interval == 0 and
                not state.auto_confirm):
                should_continue = self._checkpoint_prompt(state)
                if not should_continue:
                    return {
                        'success': False,
                        'result': f'Stopped at checkpoint (iteration {state.iteration})',
                        'iterations': state.iteration,
                        'stop_reason': StopReason.USER_CANCELLED.value,
                    }

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

    def _checkpoint_prompt(self, state: ConversationState) -> bool:
        """
        Prompt user at checkpoint to decide whether to continue.

        Returns:
            True to continue, False to stop
        """
        self._ui.show_info(
            f"Checkpoint: {state.iteration} iterations completed. "
            f"{len(state.tools_executed)} tools executed."
        )
        return self._ui.confirm("Continue agent execution?")
