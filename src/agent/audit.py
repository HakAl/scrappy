"""
Audit logging functionality for the Code Agent.

Provides logging and persistence of agent actions for traceability.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List


class AuditLogger:
    """Handles audit logging for agent actions."""

    def __init__(self, max_result_length: int = 1000):
        """
        Initialize the audit logger.

        Args:
            max_result_length: Maximum length for result truncation in logs
        """
        self.log: List[dict] = []
        self.max_result_length = max_result_length

    def log_action(self, action: str, params: dict, result: str, approved: bool) -> None:
        """
        Log an action to the audit trail.

        Args:
            action: The action/tool that was executed
            params: Parameters passed to the action
            result: The result of the action
            approved: Whether the action was approved by user
        """
        truncated_result = (
            result[:self.max_result_length]
            if len(result) > self.max_result_length
            else result
        )

        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'parameters': params,
            'result': truncated_result,
            'approved': approved
        }
        self.log.append(entry)

    def get_log(self) -> List[dict]:
        """Get the complete audit log."""
        return self.log

    def clear_log(self) -> None:
        """Clear the audit log."""
        self.log = []

    def save(self, path: Path, filename: str = ".agent_audit.json") -> str:
        """
        Save audit log to file.

        Args:
            path: Directory to save the log file
            filename: Name of the audit log file

        Returns:
            Path to the saved file
        """
        log_path = path / filename
        with open(log_path, 'w') as f:
            json.dump(self.log, f, indent=2)
        return str(log_path)
