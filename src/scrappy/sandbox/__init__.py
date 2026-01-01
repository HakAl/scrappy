"""
Sandbox module for safe command execution.

Provides Docker-based isolation for shell commands with:
- Persistent container reuse for performance
- Project directory mounting
- Network isolation
- Timeout enforcement
- Graceful fallback to host execution
- Git branch isolation for safe rollback
"""

from scrappy.sandbox.docker_executor import (
    CommandExecutorProtocol,
    CommandResult,
    DockerExecutor,
    HostExecutor,
    create_executor,
)
from scrappy.sandbox.git_isolation import (
    BranchInfo,
    GitError,
    GitIsolation,
    GitIsolationProtocol,
    create_git_isolation,
    generate_branch_name,
)

__all__ = [
    # Docker executor
    "CommandExecutorProtocol",
    "CommandResult",
    "DockerExecutor",
    "HostExecutor",
    "create_executor",
    # Git isolation
    "BranchInfo",
    "GitError",
    "GitIsolation",
    "GitIsolationProtocol",
    "create_git_isolation",
    "generate_branch_name",
]
