"""
Duplicate action detector.

Prevents the agent from repeating failed or redundant operations.
"""

from .types import AgentAction, ConversationState


class DuplicateDetector:
    """
    Duplicate and retry pattern detector.

    Implements DuplicateDetectorProtocol with state-aware detection.

    Single Responsibility: Detect duplicate/redundant actions
    Dependencies: None (pure logic)
    """

    LOOKBACK_WINDOW = 3  # Check last N actions for duplicates
    MAX_COMMAND_FAILURES = 3  # Block command after N failures

    # Actions that should never be flagged as duplicates
    # File operations are normal to repeat (read to check state, write iteratively)
    SKIP_DUPLICATE_CHECK: set[str] = {
        'read_file',
        'write_file',
        'list_files',
        'list_directory',
        'search_code',
        'find_exact_text',
        'codebase_search',
        'git_status',
        'git_diff',
        'task',
        'complete',  # Let completion validator handle this, not duplicate detector
    }

    def check_duplicate(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> tuple[bool, str]:
        """
        Check if action is duplicate or should be blocked.

        Args:
            action: AgentAction to check
            state: ConversationState with action history

        Returns:
            Tuple of (is_duplicate, warning_message).
            If is_duplicate is True, warning_message explains why.
        """
        # Skip duplicate check for file operations and other repeatable actions
        if action.action in self.SKIP_DUPLICATE_CHECK:
            return (False, "")

        # Check if this exact action was recently executed
        if self._is_recent_duplicate(action, state):
            return (
                True,
                f"Action '{action.action}' with these parameters was already attempted recently."
            )

        # Check if command has failed multiple times
        if action.action == 'run_command':
            failure_count = self._count_command_failures(action, state)
            if failure_count >= self.MAX_COMMAND_FAILURES:
                return (
                    True,
                    f"Command has failed {failure_count} times. Stopping to avoid infinite loop."
                )

        return (False, "")

    def _is_recent_duplicate(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> bool:
        """Check if action was executed in last N iterations."""
        # Check immediate duplicate (same as last action)
        if hasattr(state, 'last_action') and state.last_action:
            last = state.last_action
            if isinstance(last, dict):
                if (last.get('action') == action.action and
                    last.get('parameters') == action.parameters):
                    return True

        # Check action history
        if not hasattr(state, 'action_history'):
            return False

        recent_actions = state.action_history[-self.LOOKBACK_WINDOW:]

        for recent in recent_actions:
            # Compare action name and parameters
            if isinstance(recent, dict):
                if (recent.get('action') == action.action and
                    recent.get('parameters') == action.parameters):
                    return True
            elif hasattr(recent, 'action'):
                if (recent.action == action.action and
                    recent.parameters == action.parameters):
                    return True

        return False

    def _count_command_failures(
        self,
        action: AgentAction,
        state: ConversationState
    ) -> int:
        """Count how many times this specific command has failed."""
        if not hasattr(state, 'failed_commands'):
            return 0

        command = action.parameters.get('command', '')
        if not command:
            return 0

        # Count exact command matches in failed_commands
        count = 0
        for failure in state.failed_commands:
            if isinstance(failure, dict) and failure.get('command') == command:
                count += 1

        return count
