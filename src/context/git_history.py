"""
Git history extraction for codebase context.

Provides git repository history information including commits,
branches, contributors, and recently changed files.
"""

import subprocess
from pathlib import Path
from typing import Union


class GitHistoryReader:
    """
    Reads git history information from a repository.

    Extracts useful context about repository history including
    recent commits, branches, contributors, and changed files.

    Usage:
        reader = GitHistoryReader()
        history = reader.get_history('/path/to/repo')

        if history.get('current_branch'):
            print(f"On branch: {history['current_branch']}")
    """

    def __init__(self, timeout: int = 10):
        """
        Initialize the git history reader.

        Args:
            timeout: Timeout in seconds for git commands (default 10)
        """
        self._timeout = timeout

    def get_history(self, project_path: Union[str, Path]) -> dict:
        """
        Get git history information for a project.

        Args:
            project_path: Path to the project directory

        Returns:
            Dict with git history information, or empty dict on failure
        """
        project_path = Path(project_path)
        git_info = {}

        try:
            # Get recent commits
            result = subprocess.run(
                ['git', 'log', '--oneline', '-20', '--decorate'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                git_info['recent_commits'] = result.stdout.strip().split('\n')[:20]

            # Get active branches
            result = subprocess.run(
                ['git', 'branch', '-a', '--no-color'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                branches = [b.strip().lstrip('* ') for b in result.stdout.strip().split('\n')]
                git_info['branches'] = branches[:10]

            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                git_info['current_branch'] = result.stdout.strip()

            # Get contributors (top 5)
            result = subprocess.run(
                ['git', 'shortlog', '-sn', '--no-merges', 'HEAD'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                contributors = []
                for line in result.stdout.strip().split('\n')[:5]:
                    line = line.strip()
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            try:
                                contributors.append({
                                    'commits': int(parts[0].strip()),
                                    'name': parts[1].strip()
                                })
                            except ValueError:
                                # Skip malformed lines
                                pass
                if contributors:
                    git_info['top_contributors'] = contributors

            # Get files changed in last 10 commits
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD~10..HEAD'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                changed = list(set(result.stdout.strip().split('\n')))
                git_info['recently_changed_files'] = changed[:20]

            # Get repository age (first commit date)
            result = subprocess.run(
                ['git', 'log', '--reverse', '--format=%ci', '-1'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                git_info['first_commit_date'] = result.stdout.strip()

        except (subprocess.TimeoutExpired, Exception):
            pass  # Git info is optional

        return git_info
