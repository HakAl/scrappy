"""
Action executor coordinator.

Orchestrates the flow: Safety check -> Duplicate check -> Tool execution -> Result.
"""

from typing import Optional

from .types import AgentAction, ActionResult, ConversationState
from .protocols import (
    ActionExecutorProtocol,
    SafetyCheckerProtocol,
    DuplicateDetectorProtocol,
    ToolRunnerProtocol,
    AgentUIProtocol,
)


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
    ):
        """
        Initialize action executor.

        Args:
            safety_checker: Safety validation component
            duplicate_detector: Duplicate detection component
            tool_runner: Tool execution component
            ui: User interface component
        """
        self.safety = safety_checker
        self.duplicate_detector = duplicate_detector
        self.tool_runner = tool_runner
        self.ui = ui

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

        # 1. Safety & Confirmation
        if not self._check_safety_and_get_approval(action, state):
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
        if not self.safety.requires_confirmation(action, state.auto_confirm):
            return True

        # Ask user
        self.ui.show_tool_request(action.action, action.parameters)
        return self.ui.prompt_confirm("Allow this action?", default=False)

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
