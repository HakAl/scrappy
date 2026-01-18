"""Tests for ReminderManager (system reminders to prevent context drift)."""

from scrappy.context.reminder_manager import (
    ReminderManager,
    NullReminderManager,
    ReminderManagerProtocol,
    _extract_key_rules,
    format_reminder,
    MAX_REMINDER_CHARS,
)


class TestReminderManager:
    """Tests for ReminderManager."""

    def test_protocol_compliance(self):
        """ReminderManager implements protocol."""
        manager = ReminderManager()
        assert isinstance(manager, ReminderManagerProtocol)

    def test_null_manager_protocol_compliance(self):
        """NullReminderManager implements protocol."""
        manager = NullReminderManager()
        assert isinstance(manager, ReminderManagerProtocol)

    def test_returns_none_without_rules(self):
        """Returns None when no project rules set."""
        manager = ReminderManager()
        assert manager.get_reminder() is None

    def test_returns_reminder_with_rules(self):
        """Returns formatted reminder when rules are set."""
        manager = ReminderManager()
        manager.set_project_rules("- Use pytest for tests\n- Follow PEP8")

        reminder = manager.get_reminder()

        assert reminder is not None
        assert "<system-reminder>" in reminder
        assert "</system-reminder>" in reminder
        assert "Project rules:" in reminder

    def test_extracts_bullet_points(self):
        """Extracts bullet points from project rules."""
        manager = ReminderManager()
        manager.set_project_rules("""
# Project Guidelines

- Use pytest for testing
- Always type hint functions
- Never use print for logging
""")

        reminder = manager.get_reminder()

        assert reminder is not None
        assert "pytest" in reminder
        assert "type hint" in reminder

    def test_extracts_numbered_lists(self):
        """Extracts numbered lists from project rules."""
        manager = ReminderManager()
        manager.set_project_rules("""
1. Use dependency injection
2. Prefer protocols over ABCs
""")

        reminder = manager.get_reminder()

        assert reminder is not None
        assert "dependency injection" in reminder
        assert "protocols" in reminder

    def test_caches_reminder(self):
        """Caches extracted reminder for performance."""
        manager = ReminderManager()
        manager.set_project_rules("- Use pytest")

        reminder1 = manager.get_reminder()
        reminder2 = manager.get_reminder()

        assert reminder1 is reminder2  # Same object (cached)

    def test_clears_cache_on_new_rules(self):
        """Clears cache when new rules are set."""
        manager = ReminderManager()
        manager.set_project_rules("- Use pytest")
        reminder1 = manager.get_reminder()

        manager.set_project_rules("- Use unittest")
        reminder2 = manager.get_reminder()

        assert "pytest" in reminder1
        assert "unittest" in reminder2

    def test_null_manager_returns_none(self):
        """NullReminderManager always returns None."""
        manager = NullReminderManager()
        manager.set_project_rules("- Some rules")

        assert manager.get_reminder() is None


class TestExtractKeyRules:
    """Tests for _extract_key_rules helper."""

    def test_extracts_bullet_points(self):
        """Extracts lines starting with - or *."""
        content = """
# Header
- First rule
* Second rule
Some other text
"""
        result = _extract_key_rules(content)

        assert "First rule" in result
        assert "Second rule" in result
        assert "Header" not in result

    def test_extracts_numbered_items(self):
        """Extracts numbered list items."""
        content = """
1. First item
2. Second item
"""
        result = _extract_key_rules(content)

        assert "First item" in result
        assert "Second item" in result

    def test_extracts_imperative_lines(self):
        """Extracts lines with imperative words."""
        content = """
You should use pytest
Always follow conventions
Never commit secrets
Must run linting
"""
        result = _extract_key_rules(content)

        assert "pytest" in result or "should" in result.lower()
        assert "conventions" in result or "always" in result.lower()

    def test_truncates_to_max_chars(self):
        """Truncates result to MAX_REMINDER_CHARS."""
        # Create content with many bullet points
        content = "\n".join([f"- Rule number {i} is very important" for i in range(100)])

        result = _extract_key_rules(content)

        assert len(result) <= MAX_REMINDER_CHARS

    def test_adds_ellipsis_when_truncated(self):
        """Adds ... when content is truncated."""
        content = "\n".join([f"- Very long rule description number {i}" for i in range(100)])

        result = _extract_key_rules(content)

        if len(result) == MAX_REMINDER_CHARS:
            assert result.endswith("...")

    def test_skips_headers(self):
        """Skips lines starting with #."""
        content = """
# Main Header
## Sub Header
- Actual rule
"""
        result = _extract_key_rules(content)

        assert "Main Header" not in result
        assert "Sub Header" not in result
        assert "Actual rule" in result

    def test_fallback_for_no_actionable(self):
        """Falls back to first non-header line if no actionable rules."""
        content = """
# Header
Just some plain text
"""
        result = _extract_key_rules(content)

        assert "Just some plain text" in result

    def test_handles_empty_content(self):
        """Returns empty string for empty content."""
        assert _extract_key_rules("") == ""
        assert _extract_key_rules("   ") == ""

    def test_joins_with_separator(self):
        """Joins multiple rules with | separator."""
        content = """
- First rule
- Second rule
"""
        result = _extract_key_rules(content)

        assert " | " in result


class TestFormatReminder:
    """Tests for format_reminder helper."""

    def test_wraps_in_xml_tags(self):
        """Wraps content in system-reminder XML tags."""
        result = format_reminder("Use pytest")

        assert result.startswith("\n\n<system-reminder>")
        assert result.endswith("</system-reminder>")

    def test_includes_project_rules_prefix(self):
        """Includes 'Project rules:' prefix."""
        result = format_reminder("Use pytest")

        assert "Project rules: Use pytest" in result
