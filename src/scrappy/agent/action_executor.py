"""
Action executor coordinator.

Orchestrates the flow: Safety check -> Duplicate check -> Tool execution -> Result.
"""

import difflib
from pathlib import Path
from typing import Optional, List, Tuple

from .types import AgentAction, ActionResult, ConversationState
from .protocols import (
    SafetyCheckerProtocol,
    DuplicateDetectorProtocol,
    ToolRunnerProtocol,
    AgentUIProtocol,
)
from .cancellation import CancellationTokenProtocol


class ActionExecutor:
    """
    Action execution coordinator.

    Implements ActionExecutorProtocol with full execution flow.

    Single Responsibility: Coordinate execution flow
    Dependencies: SafetyChecker, DuplicateDetector, ToolRunner, AgentUI (injected)
    """

    def __init__(
        self,
        safety_checker: SafetyCheckerProtocol,
        duplicate_detector: DuplicateDetectorProtocol,
        tool_runner: ToolRunnerProtocol,
        ui: AgentUIProtocol,
        cancellation_token: Optional[CancellationTokenProtocol] = None,
    ):
        """
        Initialize action executor.

        Args:
            safety_checker: Safety validation component
            duplicate_detector: Duplicate detection component
            tool_runner: Tool execution component
            ui: User interface component
            cancellation_token: Optional token for cancellation signaling
        """
        self.safety = safety_checker
        self.duplicate_detector = duplicate_detector
        self.tool_runner = tool_runner
        self.ui = ui
        self._cancellation_token = cancellation_token

    def execute(
        self,
        action: AgentAction,
        state: ConversationState,
        dry_run: bool = False
    ) -> ActionResult:
        """
        Orchestrate action execution flow.

        Flow:
        1. Display thinking
        2. Handle special cases (complete, retry_parse, unknown)
        3. Check safety and get confirmation if needed
        4. Check for duplicates/retry patterns
        5. Execute tool (unless dry-run)
        6. Display and return result

        Args:
            action: AgentAction to execute
            state: ConversationState with history
            dry_run: If True, simulate execution without running tools

        Returns:
            ActionResult with execution details
        """
        # Check for force cancellation before starting
        if self._is_force_cancelled():
            return self._make_cancelled_result(action)

        # Display thinking
        self.ui.show_thinking(action.thought)

        # Handle parse failure
        if action.action == 'retry_parse':
            return self._handle_parse_failure(action)

        # Handle unknown tool
        if action.action not in self.tool_runner.tools:
            return self._handle_unknown_tool(action)

        # Validate required parameters before showing to user
        missing = self._get_missing_required_params(action)
        if missing:
            return self._handle_missing_params(action, missing)

        # Check for cancellation before asking for user approval
        # This prevents the prompt from appearing after user pressed Escape
        if self._is_cancelled():
            return self._make_cancelled_result(action)

        # 1. Safety & Confirmation
        if not self._check_safety_and_get_approval(action, state):
            # Check if this denial was due to cancellation
            if self._is_cancelled():
                return self._make_cancelled_result(action)
            return ActionResult(
                success=False,
                output="Action denied by user",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # 2. Duplicate Detection
        is_duplicate, warning = self.duplicate_detector.check_duplicate(action, state)
        if is_duplicate:
            self.ui.show_warning(warning)
            return ActionResult(
                success=False,
                output=warning,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # 3. Dry Run Check
        if dry_run:
            self.ui.show_progress(f"[DRY RUN] Would execute: {action.action}")
            return ActionResult(
                success=True,
                output="[DRY RUN] Not executed",
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # Check for force cancellation before execution
        if self._is_force_cancelled():
            return self._make_cancelled_result(action)

        # 4. Execution
        self.ui.show_progress(f"Executing: {action.action}")

        # Show command for run_command
        if action.action == 'run_command':
            cmd = action.parameters.get('command', '')
            if cmd:
                self.ui.show_command(cmd)

        try:
            tool_result = self.tool_runner.run_tool(action.action, action.parameters)

            # Display the result
            output_str = str(tool_result)
            self.ui.show_result(output_str, is_error=not tool_result.success)

            # Notify UI if tasks were updated
            if tool_result.metadata.get("tasks_changed"):
                tasks = tool_result.metadata.get("tasks", [])
                self.ui.notify_tasks_updated(tasks)

            return ActionResult(
                success=tool_result.success,
                output=output_str,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=True,
                metadata=tool_result.metadata
            )

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.ui.show_error(error_msg)
            return ActionResult(
                success=False,
                output=error_msg,
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=True
            )

    def _check_safety_and_get_approval(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> bool:
        """
        Check safety and get user approval if needed.

        Returns:
            True if action is approved for execution, False otherwise
        """
        # Safe actions are auto-approved
        if self.safety.is_safe_action(action):
            self.ui.show_tool_request(action.action, action.parameters)
            self.ui.show_progress("Auto-approved (safe operation)")
            return True

        # Check if confirmation required
        # allow_all_enabled is set at safety checkpoint when user chooses 'a'
        skip_confirm = state.auto_confirm or getattr(state, 'allow_all_enabled', False)
        if not self.safety.requires_confirmation(action, skip_confirm):
            return True

        # Ask user
        self.ui.show_tool_request(action.action, action.parameters)

        # Show diff preview for write_file actions
        if action.action == 'write_file':
            diff_lines = self._generate_diff_preview(action)
            path = action.parameters.get('path', '')
            self.ui.show_diff_preview(path, diff_lines)

        return self.ui.prompt_confirm("Allow this action?", default=False)

    def _generate_diff_preview(self, action: AgentAction) -> List[str]:
        """
        Generate unified diff for write_file action.

        Args:
            action: AgentAction with write_file parameters

        Returns:
            List of diff lines (empty for new files)
        """
        path = action.parameters.get('path', '')
        new_content = action.parameters.get('content', '')

        if not path:
            return []

        # Get project root from tool_runner's context
        project_root = self._get_project_root()
        if not project_root:
            return []

        file_path = project_root / path
        if not file_path.exists():
            # New file - no diff to show
            return []

        try:
            existing_content = file_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            # Can't read existing file
            return []

        # Generate unified diff
        existing_lines = existing_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            existing_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=''
        )

        return list(diff)

    def _get_project_root(self) -> Optional[Path]:
        """Get project root from tool_runner's context if available."""
        if hasattr(self.tool_runner, 'tool_context'):
            ctx = self.tool_runner.tool_context
            if hasattr(ctx, 'project_root'):
                return ctx.project_root
        return None

    def _handle_parse_failure(self, action: AgentAction) -> ActionResult:
        """Handle response parsing failure."""
        raw_response = action.parameters.get('raw_response', 'No response captured')
        self.ui.show_error(f"Response parsing failed. LLM returned:\n{raw_response[:300]}...")

        error_msg = (
            "Your previous response could not be parsed as JSON. "
            "You MUST respond with ONLY a valid JSON object (no other text). "
            "Use this exact format:\n"
            '{\n'
            '  "thought": "Your reasoning here",\n'
            '  "action": "tool_name",\n'
            '  "parameters": {"param": "value"},\n'
            '  "is_complete": false\n'
            '}\n'
            "Make sure all strings are properly quoted with double quotes."
        )

        return ActionResult(
            success=False,
            output=error_msg,
            action=action.action,
            parameters=action.parameters,
            approved=False,
            executed=False
        )

    def _handle_unknown_tool(self, action: AgentAction) -> ActionResult:
        """Handle unknown tool name."""
        available_tools = ', '.join(self.tool_runner.tools.keys())
        error_msg = f"Unknown action '{action.action}'. Available tools: {available_tools}"

        self.ui.show_error(error_msg)

        return ActionResult(
            success=False,
            output=error_msg,
            action=action.action,
            parameters=action.parameters,
            approved=False,
            executed=False
        )

    def _get_missing_required_params(self, action: AgentAction) -> list[str]:
        """
        Check if action has all required parameters.

        Returns:
            List of missing required parameter names (empty if all present)
        """
        # Check if tool_registry is available (may not be in tests)
        if not hasattr(self.tool_runner, 'tool_registry'):
            return []

        tool = self.tool_runner.tool_registry.get(action.action)
        if not tool:
            return []  # Unknown tool handled elsewhere

        missing = []
        for param in tool.parameters:
            if param.required and param.name not in action.parameters:
                missing.append(param.name)

        return missing

    def _handle_missing_params(self, action: AgentAction, missing: list[str]) -> ActionResult:
        """Handle action with missing required parameters."""
        missing_str = ', '.join(missing)
        error_msg = (
            f"Action '{action.action}' is missing required parameters: {missing_str}. "
            f"You must provide all required parameters."
        )

        self.ui.show_warning(f"Malformed action: missing {missing_str}")

        return ActionResult(
            success=False,
            output=error_msg,
            action=action.action,
            parameters=action.parameters,
            approved=False,
            executed=False
        )

    def _is_force_cancelled(self) -> bool:
        """Check if force cancellation was requested."""
        if not self._cancellation_token:
            return False
        if hasattr(self._cancellation_token, 'is_force_cancelled'):
            return self._cancellation_token.is_force_cancelled()
        return False

    def _is_cancelled(self) -> bool:
        """Check if any cancellation (graceful or force) was requested."""
        if not self._cancellation_token:
            return False
        return self._cancellation_token.is_cancelled()

    def _make_cancelled_result(self, action: AgentAction) -> ActionResult:
        """Create a result indicating the action was cancelled."""
        return ActionResult(
            success=False,
            output="Action cancelled by user",
            action=action.action,
            parameters=action.parameters,
            approved=False,
            executed=False,
            metadata={"cancelled": True}
        )

    def confirm_batch(
        self,
        actions: List[AgentAction],
        state: ConversationState
    ) -> Tuple[bool, List[AgentAction], List[AgentAction]]:
        """
        Get batch confirmation for multiple actions.

        Separates safe (auto-approved) from unsafe actions and prompts
        user once for all unsafe actions.

        Args:
            actions: List of actions to confirm
            state: Current conversation state

        Returns:
            Tuple of (approved, safe_actions, unsafe_actions):
            - approved: True if batch is approved (or only safe actions)
            - safe_actions: Actions that are auto-approved
            - unsafe_actions: Actions that required user confirmation
        """
        # Separate safe vs unsafe actions
        safe_actions = []
        unsafe_actions = []
        for action in actions:
            if self.safety.is_safe_action(action):
                safe_actions.append(action)
            else:
                unsafe_actions.append(action)

        # If no unsafe actions, all approved
        if not unsafe_actions:
            return True, safe_actions, unsafe_actions

        # Check if auto-confirm or allow-all mode
        skip_confirm = state.auto_confirm or getattr(state, 'allow_all_enabled', False)
        if skip_confirm:
            return True, safe_actions, unsafe_actions

        # Check for cancellation before prompting
        if self._is_cancelled():
            return False, safe_actions, unsafe_actions

        # Build list of (tool_name, params) for UI
        action_tuples = [(a.action, a.parameters) for a in unsafe_actions]

        # Prompt user for batch approval
        approved = self.ui.confirm_batch(action_tuples)

        return approved, safe_actions, unsafe_actions

    def execute_batch(
        self,
        actions: List[AgentAction],
        state: ConversationState,
        dry_run: bool = False
    ) -> List[ActionResult]:
        """
        Execute multiple actions with batch confirmation.

        First confirms all unsafe actions with a single prompt,
        then executes all actions sequentially. Uses fail-fast:
        stops on first error.

        Args:
            actions: List of actions to execute
            state: Current conversation state
            dry_run: If True, simulate execution without running tools

        Returns:
            List of ActionResult, one per action executed.
            If batch is denied, returns single denied result.
            If error occurs, returns results up to and including the error.
        """
        if not actions:
            return []

        # Get batch confirmation
        approved, safe_actions, unsafe_actions = self.confirm_batch(actions, state)

        if not approved:
            # Return single denied result for first action
            return [ActionResult(
                success=False,
                output="Batch denied by user",
                action=actions[0].action,
                parameters=actions[0].parameters,
                approved=False,
                executed=False
            )]

        # Execute all actions sequentially
        results = []
        for action in actions:
            # Execute with confirmation already handled
            # We pass a modified state with auto_confirm=True since batch was approved
            batch_state = ConversationState(
                messages=state.messages,
                system_prompt=state.system_prompt,
                iteration=state.iteration,
                max_iterations=state.max_iterations,
                checkpoint_interval=state.checkpoint_interval,
                tools_executed=state.tools_executed,
                auto_confirm=True,  # Batch was approved
                allow_all_enabled=True,  # Skip individual confirmations
                last_checkpoint_hash=state.last_checkpoint_hash,
                failed_commands=state.failed_commands,
                retry_warnings=state.retry_warnings,
                action_history=state.action_history,
                last_action=state.last_action,
                recent_outcomes=state.recent_outcomes,
            )

            result = self.execute(action, batch_state, dry_run)
            results.append(result)

            # Fail-fast: stop on first error
            if not result.success:
                break

        return results
