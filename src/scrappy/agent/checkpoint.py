"""
Git checkpoint operations for the Code Agent.

Provides functionality to create and rollback to git checkpoints
for safe agent operations.
"""

import re
import subprocess
from datetime import datetime
from typing import Optional


# Pattern for valid git commit hashes (7-40 hex characters)
_COMMIT_HASH_PATTERN = re.compile(r'^[a-f0-9]{7,40}$')


def _is_valid_commit_hash(commit_hash: str) -> bool:
    """
    Validate that a string is a valid git commit hash.

    Args:
        commit_hash: String to validate

    Returns:
        True if valid commit hash format, False otherwise
    """
    return bool(_COMMIT_HASH_PATTERN.match(commit_hash))


def create_git_checkpoint(project_path: str = ".") -> Optional[str]:
    """
    Create a git checkpoint before agent operations.

    Args:
        project_path: Path to the project directory

    Returns:
        Commit hash of the checkpoint, or None if not in a git repo
    """
    try:
        # Security: Use argument list instead of shell=True to prevent command injection
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            shell=False,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return None

        # Create checkpoint commit
        subprocess.run(
            ["git", "add", "-A"],
            shell=False,
            cwd=project_path,
            capture_output=True
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Security: Use argument list - the message is passed as a single argument
        # to git, not interpreted by a shell
        message = f"Agent checkpoint {timestamp}"
        subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty"],
            shell=False,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            shell=False,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()
    except Exception:
        return None


def rollback_to_checkpoint(commit_hash: str, project_path: str = ".") -> bool:
    """
    Rollback to a git checkpoint.

    Args:
        commit_hash: The commit hash to rollback to
        project_path: Path to the project directory

    Returns:
        True if rollback succeeded, False otherwise

    Raises:
        ValueError: If commit_hash is not a valid git commit hash format
    """
    # Security: Validate commit hash format to prevent command injection
    if not _is_valid_commit_hash(commit_hash):
        raise ValueError(f"Invalid commit hash: {commit_hash}")

    try:
        # Security: Use argument list instead of shell=True
        result = subprocess.run(
            ["git", "reset", "--hard", commit_hash],
            shell=False,
            cwd=project_path,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False
