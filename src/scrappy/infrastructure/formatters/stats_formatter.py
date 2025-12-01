"""
Base stats formatter implementation.

Provides reusable formatting utilities for statistics displays.
"""

from typing import Any
from .types import FormatterOutputProtocol


class StatsFormatter:
    """Base formatter for statistics displays.

    Provides formatting utilities for headers, key-value pairs,
    percentages, and numbers with color coding.

    Args:
        io: FormatterOutputProtocol instance for styled output
    """

    def __init__(self, io: FormatterOutputProtocol):
        """Initialize formatter with FormatterOutputProtocol.

        Args:
            io: FormatterOutputProtocol instance (contains theme and styling methods)
        """
        self._io = io

    def format_header(self, title: str, width: int = 60) -> str:
        """Format a header with title and separator.

        Args:
            title: The header title text
            width: Total width of the header (default: 60)

        Returns:
            Formatted header string with Rich markup
        """
        header = self._io.style(f"\n{title}", fg=self._io.theme.primary, bold=True)
        separator = self._io.style("-" * width, fg=self._io.theme.primary)
        return f"{header}\n{separator}"

    def format_key_value(self, key: str, value: Any, indent: int = 0) -> str:
        """Format a key-value pair for display.

        Args:
            key: The key/label text
            value: The value to display
            indent: Number of spaces to indent (default: 0)

        Returns:
            Formatted string like "  Key: value"
        """
        spaces = " " * indent
        return f"{spaces}{key}: {value}"

    def format_percentage(
        self,
        value: float,
        total: float,
        label: str = "",
        show_numbers: bool = True
    ) -> str:
        """Format a percentage with color coding.

        Args:
            value: Current value
            total: Total/maximum value
            label: Optional label prefix
            show_numbers: Whether to show numbers (e.g., "10/100 (10%)")

        Returns:
            Formatted string with color based on percentage (if use_color is True)
            Colors: green < 75%, yellow < 90%, red >= 90%
        """
        if total == 0:
            percentage = 0.0
        else:
            percentage = (value / total) * 100

        # Determine color based on percentage
        color = self._get_percentage_color(percentage)

        # Build the display string
        if show_numbers:
            text = f"{value:,}/{total:,} ({percentage:.1f}%)"
        else:
            text = f"{percentage:.1f}%"

        # Apply color styling
        styled_text = self._io.style(text, fg=color)

        # Add label if provided
        if label:
            return f"{label}: {styled_text}"
        else:
            return styled_text

    def format_number(self, value: int, with_commas: bool = True) -> str:
        """Format a number for display.

        Args:
            value: The numeric value
            with_commas: Whether to add thousand separators

        Returns:
            Formatted number string (e.g., "1,234,567")
        """
        if with_commas:
            return f"{value:,}"
        else:
            return str(value)

    def _get_percentage_color(self, percentage: float) -> str:
        """Determine color based on percentage.

        Args:
            percentage: The percentage value (0-100)

        Returns:
            Color from theme: success (< 75%), warning (< 90%), error (>= 90%)
        """
        if percentage < 75:
            return self._io.theme.success
        elif percentage < 90:
            return self._io.theme.warning
        else:
            return self._io.theme.error

    def format_boolean_status(
        self,
        value: bool,
        true_label: str = "Enabled",
        false_label: str = "Disabled"
    ) -> str:
        """Format a boolean status with color coding.

        Args:
            value: The boolean value
            true_label: Label for True (default: "Enabled")
            false_label: Label for False (default: "Disabled")

        Returns:
            Colored status string with Rich markup
        """
        label = true_label if value else false_label
        color = self._io.theme.success if value else self._io.theme.error
        return self._io.style(label, fg=color)
