"""
Audit logging functionality for the Code Agent.

Provides logging and persistence of agent actions for traceability.
"""

import atexit
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional


class AuditLogger:
    """Handles audit logging for agent actions with crash-safe persistence."""

    def __init__(self, max_result_length: int = 1000):
        """
        Initialize the audit logger.

        Args:
            max_result_length: Maximum length for result truncation in logs
        """
        self.log: List[dict] = []
        self.max_result_length = max_result_length
        self._save_path: Optional[Path] = None
        self._filename: str = ".llm_agent_audit.json"
        self._auto_save: bool = False
        self._crash_handlers_registered: bool = False
        self._task_info: dict = {}

    def enable_auto_save(self, path: Path, filename: str = ".llm_agent_audit.json") -> None:
        """
        Enable automatic incremental saving after each action.
        Also registers crash handlers to save on unexpected exit.

        Args:
            path: Directory to save the log file
            filename: Name of the audit log file
        """
        self._save_path = path
        self._filename = filename
        self._auto_save = True
        self._register_crash_handlers()

    def set_task_info(self, task: str, max_iterations: int, auto_confirm: bool) -> None:
        """
        Store task metadata for crash recovery.

        Args:
            task: The task being executed
            max_iterations: Maximum iterations allowed
            auto_confirm: Whether auto-confirm is enabled
        """
        self._task_info = {
            'task': task,
            'max_iterations': max_iterations,
            'auto_confirm': auto_confirm,
            'started_at': datetime.now().isoformat()
        }
        # Save immediately to capture task info even if crash happens early
        if self._auto_save:
            self._save_incremental()

    def _register_crash_handlers(self) -> None:
        """Register handlers to save audit log on crash or unexpected exit."""
        if self._crash_handlers_registered:
            return

        # Register atexit handler for normal exit
        atexit.register(self._on_exit)

        # Register signal handlers for crashes (only on non-Windows or with care)
        if sys.platform != 'win32':
            # Unix-specific signals
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGHUP, self._signal_handler)
        else:
            # Windows signals
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

        self._crash_handlers_registered = True

    def _signal_handler(self, signum, frame):
        """Handle signals by saving audit log before exit."""
        self._on_exit()
        # Re-raise the signal for proper cleanup
        signal.signal(signum, signal.SIG_DFL)
        if sys.platform == 'win32':
            sys.exit(1)
        else:
            import os
            os.kill(os.getpid(), signum)

    def _on_exit(self) -> None:
        """Save audit log on exit (normal or crash)."""
        if self._save_path and self.log:
            try:
                self._save_incremental()
            except Exception:
                # Last resort: try to write to current directory
                try:
                    with open(self._filename, 'w') as f:
                        json.dump(self._build_save_data(), f, indent=2)
                except Exception:
                    pass  # Give up silently if we can't save

    def _build_save_data(self) -> dict:
        """Build the complete data structure for saving."""
        return {
            'task_info': self._task_info,
            'actions': self.log,
            'saved_at': datetime.now().isoformat(),
            'total_actions': len(self.log),
            'status': 'in_progress' if not self._task_info.get('completed') else 'completed'
        }

    def _save_incremental(self) -> None:
        """Save the current state of the audit log."""
        if not self._save_path:
            return

        try:
            log_path = self._save_path / self._filename
            with open(log_path, 'w') as f:
                json.dump(self._build_save_data(), f, indent=2)
        except Exception:
            pass  # Don't let save errors interrupt agent execution

    def log_action(self, action: str, params: dict, result: str, approved: bool) -> None:
        """
        Log an action to the audit trail and save incrementally.

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

        # Auto-save after each action for crash safety
        if self._auto_save:
            self._save_incremental()

    def mark_complete(self, success: bool, result: str) -> None:
        """
        Mark the task as complete and save final state.

        Args:
            success: Whether the task completed successfully
            result: Final result message
        """
        self._task_info['completed'] = True
        self._task_info['success'] = success
        self._task_info['final_result'] = result
        self._task_info['completed_at'] = datetime.now().isoformat()

        if self._auto_save:
            self._save_incremental()

    def get_log(self) -> List[dict]:
        """Get the complete audit log."""
        return self.log

    def clear_log(self) -> None:
        """Clear the audit log."""
        self.log = []
        self._task_info = {}

    def save(self, path: Path, filename: str = ".llm_agent_audit.json") -> str:
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
            json.dump(self._build_save_data(), f, indent=2)
        return str(log_path)
