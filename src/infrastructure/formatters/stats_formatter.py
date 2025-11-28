"""
Base stats formatter implementation.

Provides reusable formatting utilities for statistics displays.
"""

from typing import Any, Optional
import click

from src.infrastructure.theme import DEFAULT_THEME, ThemeProtocol


class StatsFormatter:
    """Base formatter for statistics displays.

    Provides formatting utilities for headers, key-value pairs,
    percentages, and numbers with color coding.

    Args:
        use_color: Whether to include ANSI color codes in output.
            Defaults to True. Set to False for terminals that don't
            support colors to avoid ANSI artifacts.
        theme: Theme instance for color values. Defaults to DEFAULT_THEME.
    """

    def __init__(
        self,
        use_color: bool = True,
        theme: Optional[ThemeProtocol] = None,
    ):
        """Initialize formatter with color preference and theme.

        Args:
            use_color: Whether to use ANSI color codes in output.
            theme: Theme instance for color values.
        """
        self._use_color = use_color
        self._theme = theme or DEFAULT_THEME

    def format_header(self, title: str, width: int = 60) -> str:
        """Format a header with title and separator.

        Args:
            title: The header title text
            width: Total width of the header (default: 60)

        Returns:
            Formatted header string, with ANSI codes if use_color is True
        """
        if self._use_color:
            header = click.style(f"\n{title}", fg=self._theme.primary, bold=True)
            separator = click.style("-" * width, fg=self._theme.primary)
        else:
            header = f"\n{title}"
            separator = "-" * width
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

        # Apply color only if enabled
        if self._use_color:
            styled_text = click.style(text, fg=color)
        else:
            styled_text = text

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
            return self._theme.success
        elif percentage < 90:
            return self._theme.warning
        else:
            return self._theme.error

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
            Colored status string (if use_color is True), plain text otherwise
        """
        label = true_label if value else false_label
        if not self._use_color:
            return label

        color = self._theme.success if value else self._theme.error
        return click.style(label, fg=color)
