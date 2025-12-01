"""
Git checkpoint operations for the Code Agent.

Provides functionality to create and rollback to git checkpoints
for safe agent operations.
"""

import subprocess
from datetime import datetime
from typing import Optional


def create_git_checkpoint(project_path: str = ".") -> Optional[str]:
    """
    Create a git checkpoint before agent operations.

    Args:
        project_path: Path to the project directory

    Returns:
        Commit hash of the checkpoint, or None if not in a git repo
    """
    try:
        result = subprocess.run(
            "git rev-parse --is-inside-work-tree",
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return None

        # Create checkpoint commit
        subprocess.run(
            "git add -A",
            shell=True,
            cwd=project_path,
            capture_output=True
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subprocess.run(
            f'git commit -m "Agent checkpoint {timestamp}" --allow-empty',
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        # Get commit hash
        result = subprocess.run(
            "git rev-parse HEAD",
            shell=True,
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
    """
    try:
        result = subprocess.run(
            f"git reset --hard {commit_hash}",
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False
