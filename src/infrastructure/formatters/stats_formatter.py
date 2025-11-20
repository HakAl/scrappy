"""
Base stats formatter implementation.

Provides reusable formatting utilities for statistics displays.
"""

from typing import Any
import click


class StatsFormatter:
    """Base formatter for statistics displays.

    Provides formatting utilities for headers, key-value pairs,
    percentages, and numbers with color coding.
    """

    def format_header(self, title: str, width: int = 60) -> str:
        """Format a header with title and separator.

        Args:
            title: The header title text
            width: Total width of the header (default: 60)

        Returns:
            Formatted header string with ANSI color codes
        """
        header = click.style(f"\n{title}", fg="cyan", bold=True)
        separator = click.style("-" * width, fg="cyan")
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
            Formatted string with color based on percentage
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

        # Add label if provided
        if label:
            return f"{label}: {click.style(text, fg=color)}"
        else:
            return click.style(text, fg=color)

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
            Color name: 'green', 'yellow', or 'red'
        """
        if percentage < 75:
            return "green"
        elif percentage < 90:
            return "yellow"
        else:
            return "red"

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
            Colored status string
        """
        if value:
            return click.style(true_label, fg="green")
        else:
            return click.style(false_label, fg="red")
