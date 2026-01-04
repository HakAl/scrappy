"""
Command security validation component.

Implements CommandSecurityProtocol to validate commands against
security policies and block dangerous operations.
"""

import re
from typing import List, Optional


class CommandSecurity:
    """
    Validates command safety by checking against dangerous patterns.

    This class implements a single responsibility: security validation.
    It does NOT execute commands or handle platform-specific logic.
    """

    # Destructive command patterns
    DESTRUCTIVE_PATTERNS = [
        r'rm\s+-rf\s+/',
        r'rm\s+-rf\s+\*',
        r'format\s+[A-Za-z]:',
        r'mkfs\.',
        r'dd\s+if=',
        r':\(\)\s*\{.*\}',  # Fork bomb
        r'sudo\s+rm',
    ]

    # Command injection patterns - block shell metacharacters used for injection
    INJECTION_PATTERNS = [
        r'\$\(',           # $(command) substitution
        r'`[^`]+`',        # `command` backtick substitution
        r'\$\{[^}]+\}',    # ${var} expansion with commands
        r';\s*\w',         # ; followed by command (chaining)
        r'\n',             # Newline injection
        r'\|\s*(nc|netcat|bash|sh|curl\s+-o|wget\s+-O)',  # Pipe to dangerous commands
        r'>\s*/etc/',      # Redirect to /etc/
        r'>\s*/dev/',      # Redirect to /dev/
        r'>\s*~/',         # Redirect to home dir
        r'2>&1\s*\|\s*(nc|netcat)',  # Stderr redirect to netcat
        r'eval\s+',        # eval command
        r'exec\s+',        # exec command
    ]

    DEFAULT_DANGEROUS_PATTERNS = DESTRUCTIVE_PATTERNS + INJECTION_PATTERNS

    def __init__(self, dangerous_patterns: Optional[List[str]] = None):
        """
        Initialize command security validator.

        Args:
            dangerous_patterns: List of regex patterns for dangerous commands.
                               If None, uses DEFAULT_DANGEROUS_PATTERNS.
                               If provided, replaces defaults entirely.
        """
        if dangerous_patterns is not None:
            self._patterns = dangerous_patterns
        else:
            self._patterns = self.DEFAULT_DANGEROUS_PATTERNS

    def validate(self, command: str) -> None:
        """
        Validate command safety.

        Args:
            command: The command string to validate

        Raises:
            ValueError: If command violates security policy
        """
        for pattern in self._patterns:
            if re.search(pattern, command, re.IGNORECASE):
                raise ValueError(
                    f"Command matches dangerous pattern '{pattern}' and is blocked for security reasons"
                )
