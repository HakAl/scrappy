"""
System reminder manager to prevent context drift in long sessions.

LLMs have recency bias - recent tokens are weighted more heavily than earlier ones.
In long conversations, this causes "context drift" away from original instructions.
System reminders periodically re-anchor the model to key constraints.

Based on Claude Code's approach of sprinkling 'system-reminders' in tool results.
See: https://github.com/Piebald-AI/claude-code-system-prompts

Usage:
    manager = ReminderManager(project_rules="Use pytest for tests.\nFollow PEP8.")
    reminder = manager.get_reminder()
    # Returns: "<system-reminder>Project rules: Use pytest for tests.</system-reminder>"
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class ReminderManagerProtocol(Protocol):
    """Protocol for reminder management."""

    def get_reminder(self) -> Optional[str]:
        """Get a system reminder to append to tool results.

        Returns:
            Formatted reminder string with XML tags, or None if no reminders
        """
        ...

    def set_project_rules(self, rules: str) -> None:
        """Set project rules to extract reminders from.

        Args:
            rules: Project rules content (from AGENTS.md or similar)
        """
        ...


# Maximum characters for extracted key rules
MAX_REMINDER_CHARS = 200

# Patterns that indicate actionable rules
RULE_PATTERNS = [
    r"^\s*[-*]\s+",  # Bullet points
    r"^\s*\d+\.\s+",  # Numbered lists
    r"\b(use|always|never|must|should|prefer|avoid)\b",  # Imperative words
]


def _extract_key_rules(content: str, max_chars: int = MAX_REMINDER_CHARS) -> str:
    """
    Extract key actionable rules from project rules content.

    Prioritizes bullet points and lines with imperative language.

    Args:
        content: Full project rules content
        max_chars: Maximum characters to return

    Returns:
        Extracted key rules, truncated to max_chars
    """
    if not content:
        return ""

    lines = content.strip().split("\n")
    actionable_lines: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip headers (lines starting with #)
        if line.startswith("#"):
            continue

        # Check if line matches actionable patterns
        is_actionable = any(
            re.search(pattern, line, re.IGNORECASE)
            for pattern in RULE_PATTERNS
        )

        if is_actionable:
            # Clean up bullet/number prefix for compact display
            cleaned = re.sub(r"^\s*[-*]\s+", "", line)
            cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned)
            actionable_lines.append(cleaned)

    if not actionable_lines:
        # Fallback: take first non-header, non-empty line
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                actionable_lines.append(line)
                break

    # Join and truncate
    result = " | ".join(actionable_lines)
    if len(result) > max_chars:
        result = result[: max_chars - 3] + "..."

    return result


def format_reminder(content: str) -> str:
    """
    Format content as a system reminder with XML tags.

    Args:
        content: Reminder content

    Returns:
        Formatted reminder string
    """
    return f"\n\n<system-reminder>\nProject rules: {content}\n</system-reminder>"


@dataclass
class ReminderManager:
    """
    Manages system reminders to prevent context drift.

    Extracts key actionable rules from project rules (AGENTS.md) and
    formats them as system reminders to inject into tool results.

    Features:
    - Extracts bullet points and imperative statements
    - Caches extracted rules for performance
    - Provides formatted reminders with XML tags
    """

    _project_rules: Optional[str] = None
    _reminder_cache: Optional[str] = field(default=None, repr=False)

    def get_reminder(self) -> Optional[str]:
        """
        Get a system reminder to append to tool results.

        Returns:
            Formatted reminder string with XML tags, or None if no rules
        """
        if not self._project_rules:
            return None

        if self._reminder_cache is None:
            key_rules = _extract_key_rules(self._project_rules)
            if key_rules:
                self._reminder_cache = format_reminder(key_rules)
            else:
                self._reminder_cache = ""

        return self._reminder_cache if self._reminder_cache else None

    def set_project_rules(self, rules: str) -> None:
        """
        Set project rules to extract reminders from.

        Clears the reminder cache so next get_reminder() extracts fresh.

        Args:
            rules: Project rules content (from AGENTS.md or similar)
        """
        self._project_rules = rules
        self._reminder_cache = None  # Clear cache


class NullReminderManager:
    """No-op reminder manager for when reminders are disabled."""

    def get_reminder(self) -> None:
        """Returns None - no reminders."""
        return None

    def set_project_rules(self, rules: str) -> None:
        """No-op - ignores rules."""
        pass
