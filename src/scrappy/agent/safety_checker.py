"""
Safety checker for agent actions.

Determines which actions are safe to auto-execute vs require user confirmation.
"""

from typing import Set

from .types import AgentAction


class SafetyChecker:
    """
    Action safety validator.

    Implements SafetyCheckerProtocol with default safety rules.

    Single Responsibility: Determine action safety
    Dependencies: None (pure logic)
    """

    # Actions that are read-only and safe to execute without confirmation
    SAFE_ACTIONS: Set[str] = {
        'read_file',
        'list_files',
        'list_directory',
        'search_code',
        'codebase_search',  # Semantic search - read-only
        'git_status',
        'git_diff',
        'git_log',
        'git_blame',
        'get_context',
    }

    def is_safe_action(self, action: AgentAction) -> bool:
        """
        Check if action is safe to auto-execute.

        Safe actions are read-only operations that cannot modify state.

        Args:
            action: AgentAction to check

        Returns:
            True if action is safe, False otherwise
        """
        return action.action in self.SAFE_ACTIONS

    def requires_confirmation(self, action: AgentAction, auto_confirm: bool) -> bool:
        """
        Check if action requires user confirmation.

        Args:
            action: AgentAction to check
            auto_confirm: Whether auto-confirm mode is enabled

        Returns:
            True if confirmation required, False otherwise
        """
        # Auto-confirm mode disables all confirmations
        if auto_confirm:
            return False

        # 'complete' action never requires confirmation
        if action.action == 'complete':
            return False

        # Unsafe actions require confirmation
        return not self.is_safe_action(action)
