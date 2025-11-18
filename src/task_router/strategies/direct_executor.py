"""
Direct command execution without agent loop.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional

from ..classifier import ClassifiedTask, TaskClassifier, TaskType
from .base import ExecutionResult, ExecutionStrategy


class DirectExecutor(ExecutionStrategy):
    """
    Direct command execution without agent loop.

    Best for:
    - pip install, npm install
    - git status, git log
    - Simple filesystem operations
    - Build commands (make, pytest)

    Features:
    - No LLM involvement
    - Immediate execution
    - Timeout protection
    - Safety checks
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 60,
        require_confirmation: bool = True
    ):
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self.require_confirmation = require_confirmation

    @property
    def name(self) -> str:
        return "DirectExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return (
            task.task_type == TaskType.DIRECT_COMMAND
            and task.extracted_command is not None
        )

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute direct command in shell."""
        if not task.extracted_command:
            return ExecutionResult(
                success=False,
                output="",
                error="No command extracted from task"
            )

        command = task.extracted_command

        # Safety check
        classifier = TaskClassifier()
        if not classifier.is_safe_command(command):
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command blocked for safety: {command}"
            )

        start_time = time.time()

        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr if result.stderr else None,
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "return_code": result.returncode,
                        "working_dir": str(self.working_dir)
                    }
                )
            else:
                return ExecutionResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr or f"Command failed with code {result.returncode}",
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "return_code": result.returncode
                    }
                )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command timed out after {self.timeout}s",
                execution_time=self.timeout,
                metadata={"command": command}
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                metadata={"command": command}
            )
