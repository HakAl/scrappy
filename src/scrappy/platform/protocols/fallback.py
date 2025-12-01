"""
Python command fallback protocol.

Defines the interface for Python implementations of Unix commands.
"""

from typing import Protocol, Dict, Any, List, runtime_checkable
from pathlib import Path


@runtime_checkable
class PythonCommandFallbackProtocol(Protocol):
    """
    Protocol for Python implementations of shell commands.

    Used when native command execution fails on Windows.
    Each method returns a dict with 'output', 'returncode', 'used_fallback'.

    Example:
        def run_ls(fallback: PythonCommandFallbackProtocol, args: List[str]):
            result = fallback.ls(args, Path.cwd())
            if result['returncode'] == 0:
                print(result['output'])
    """

    def ls(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of ls command.

        Args:
            args: Command arguments (e.g., ['-la', '/tmp'])
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def cat(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of cat command.

        Args:
            args: Command arguments (file paths)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def grep(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of grep command.

        Args:
            args: Command arguments (pattern, files, flags)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def find(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of find command.

        Args:
            args: Command arguments (path, conditions)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def wc(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of wc command.

        Args:
            args: Command arguments (files, flags)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def head(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of head command.

        Args:
            args: Command arguments (files, line count)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def tail(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of tail command.

        Args:
            args: Command arguments (files, line count)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def touch(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of touch command.

        Args:
            args: File paths to create/update
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def mkdir_p(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of mkdir -p command.

        Args:
            args: Directory paths to create
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def rm(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of rm command.

        Args:
            args: Command arguments (files, flags like -rf)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def cp(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of cp command.

        Args:
            args: Command arguments (source, dest, flags)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def mv(self, args: List[str], cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of mv command.

        Args:
            args: Command arguments (source, dest)
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def which(self, args: List[str]) -> Dict[str, Any]:
        """
        Python implementation of which command.

        Args:
            args: Command names to locate

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...

    def pwd(self, cwd: Path) -> Dict[str, Any]:
        """
        Python implementation of pwd command.

        Args:
            cwd: Working directory

        Returns:
            Dict with 'output', 'returncode', 'used_fallback'
        """
        ...
