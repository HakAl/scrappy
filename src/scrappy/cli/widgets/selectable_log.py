"""SelectableLog widget - RichLog replacement with mouse text selection."""

from typing import Optional

from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.geometry import Size
from textual.events import MouseDown, MouseMove, MouseUp
from textual._cells import cell_len
from rich.console import RenderableType
from rich.segment import Segment
from rich.style import Style


class SelectableLog(ScrollView, can_focus=True):
    """Log widget with text selection support.

    A drop-in replacement for RichLog that allows users to select
    and copy text using mouse drag and Ctrl+C.

    Features:
    - Rich renderable support (Panel, Table, Text, Syntax, etc.)
    - Mouse click-and-drag text selection
    - Ctrl+C to copy selected text
    - Auto-scroll to bottom on new content
    - Memory management via max_lines
    - Proper handling of double-width characters (emoji, CJK)
    """

    def __init__(
        self,
        max_lines: Optional[int] = None,
        auto_scroll: bool = True,
        wrap: bool = False,
        highlight: bool = False,
        markup: bool = False,
        **kwargs
    ):
        """Initialize SelectableLog.

        Args:
            max_lines: Maximum lines to keep (None = unlimited)
            auto_scroll: Auto-scroll to bottom on new content
            wrap: Ignored (kept for RichLog API compatibility)
            highlight: Ignored (kept for RichLog API compatibility)
            markup: Ignored (kept for RichLog API compatibility)
        """
        super().__init__(**kwargs)
        self._strips: list[Strip] = []
        self._selection_start: Optional[tuple[int, int]] = None
        self._selection_end: Optional[tuple[int, int]] = None
        self._is_selecting = False
        self._max_lines = max_lines
        self._auto_scroll = auto_scroll
        self._widest_line_width = 0

    def write(self, renderable: RenderableType) -> None:
        """Add a Rich renderable to the log.

        Args:
            renderable: Any Rich renderable (Text, Panel, Table, str, etc.)
        """
        console = self.app.console
        # Use widget's actual width for proper text wrapping on resize
        # Fall back to console width if widget not yet sized
        widget_width = self.scrollable_content_region.width or console.width
        render_options = console.options.update_width(widget_width)

        # Render the content
        segments = list(console.render(renderable, render_options))

        # Convert segments to strips, splitting on newlines
        lines = list(Segment.split_lines(segments))

        if not lines:
            self._strips.append(Strip.blank(0))
        else:
            strips = Strip.from_lines(lines)
            self._strips.extend(strips)

            # Track widest line
            for strip in strips:
                self._widest_line_width = max(
                    self._widest_line_width, strip.cell_length
                )

        # Apply max_lines limit
        if self._max_lines and len(self._strips) > self._max_lines:
            overflow = len(self._strips) - self._max_lines
            self._strips = self._strips[overflow:]
            # Adjust selection indices - clamp to 0 instead of nullifying
            if self._selection_start:
                row, col = self._selection_start
                new_row = row - overflow
                self._selection_start = (max(0, new_row), col)
            if self._selection_end:
                row, col = self._selection_end
                new_row = row - overflow
                self._selection_end = (max(0, new_row), col)

        # Update virtual size for scrollbars
        self.virtual_size = Size(self._widest_line_width, len(self._strips))

        # Auto-scroll if enabled
        if self._auto_scroll:
            self.scroll_end(animate=False)

    def clear(self) -> None:
        """Clear all content from the log."""
        self._strips.clear()
        self._selection_start = None
        self._selection_end = None
        self._widest_line_width = 0
        self.virtual_size = Size(0, 0)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a single line with selection highlighting.

        This implements the Line API contract expected by ScrollView.
        """
        scroll_x, scroll_y = self.scroll_offset
        line_index = int(scroll_y) + y
        width = self.scrollable_content_region.width

        if line_index >= len(self._strips):
            return Strip.blank(width, self.rich_style)

        strip = self._strips[line_index]

        # Apply selection highlight if this line is in selection range
        selection = self._get_normalized_selection()
        if selection:
            start, end = selection
            start_row, start_col = start
            end_row, end_col = end

            if start_row <= line_index <= end_row:
                # Determine columns to highlight on this line
                if line_index == start_row and line_index == end_row:
                    # Single line selection
                    highlight_start = start_col
                    highlight_end = end_col
                elif line_index == start_row:
                    # First line of multi-line selection
                    highlight_start = start_col
                    highlight_end = strip.cell_length
                elif line_index == end_row:
                    # Last line of multi-line selection
                    highlight_start = 0
                    highlight_end = end_col
                else:
                    # Middle line - full highlight
                    highlight_start = 0
                    highlight_end = strip.cell_length

                if highlight_start < highlight_end:
                    strip = self._highlight_strip(strip, highlight_start, highlight_end)

        # Crop/extend to handle horizontal scrolling and width
        strip = strip.crop_extend(int(scroll_x), int(scroll_x) + width, self.rich_style)

        # Apply widget style
        strip = strip.apply_style(self.rich_style)

        return strip

    def _highlight_strip(self, strip: Strip, start: int, end: int) -> Strip:
        """Apply reverse style to selected portion.

        Uses divide/join to apply style to a specific range within the strip.
        Args use cell positions (not character indices).
        """
        rev = Style(reverse=True)
        length = strip.cell_length

        # Handle edge cases
        if start >= end or start >= length or length == 0:
            return strip
        end = min(end, length)

        # Entire strip selected
        if start == 0 and end >= length:
            return strip.apply_style(rev)

        # Build cuts list - must include length to get all parts
        if start == 0:
            # [0-end, end-length] -> style parts[0]
            parts = list(strip.divide([end, length]))
            if parts:
                parts[0] = parts[0].apply_style(rev)
        elif end >= length:
            # [0-start, start-length] -> style parts[1]
            parts = list(strip.divide([start, length]))
            if len(parts) >= 2:
                parts[1] = parts[1].apply_style(rev)
        else:
            # [0-start, start-end, end-length] -> style parts[1]
            parts = list(strip.divide([start, end, length]))
            if len(parts) >= 2:
                parts[1] = parts[1].apply_style(rev)

        return Strip.join(parts)

    def _get_normalized_selection(self) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
        """Return (start, end) with start always before end."""
        if self._selection_start is None or self._selection_end is None:
            return None
        start = self._selection_start
        end = self._selection_end
        if start > end:
            start, end = end, start
        return (start, end)

    def _mouse_to_scroll_coords(self, event) -> tuple[int, int]:
        """Convert widget-space mouse coords to scroll-space row/col (in cells)."""
        row = event.y + int(self.scroll_offset.y)
        col = self._x_to_cell_position(event.x + int(self.scroll_offset.x), row)
        return (row, col)

    def _x_to_cell_position(self, x: int, row: int) -> int:
        """Convert x position to cell position, handling double-width chars.

        Returns cell position (visual column), not character index.
        This is important for emoji/CJK which take 2 cells per character.
        """
        if row < 0 or row >= len(self._strips):
            return x

        strip = self._strips[row]

        # Early return for empty strips
        if strip.cell_length == 0:
            return 0

        cell_position = 0
        for segment in strip:  # Uses Strip's public __iter__
            for char in segment.text:
                char_width = cell_len(char)
                if cell_position + char_width > x:
                    return cell_position
                cell_position += char_width

        return cell_position

    def on_mouse_down(self, event: MouseDown) -> None:
        """Start selection on mouse down."""
        self._selection_start = self._mouse_to_scroll_coords(event)
        self._selection_end = None
        self._is_selecting = True
        self.capture_mouse()
        self.refresh()

    def on_mouse_move(self, event: MouseMove) -> None:
        """Update selection on mouse drag."""
        # Only update selection while actively dragging (button held)
        if self._is_selecting and event.button != 0:
            new_end = self._mouse_to_scroll_coords(event)
            if new_end != self._selection_end:
                self._selection_end = new_end
                self.refresh()

    def on_mouse_up(self, event: MouseUp) -> None:
        """End selection on mouse up."""
        self._is_selecting = False
        self.release_mouse()

    def _has_selection(self) -> bool:
        """Check if there is an active selection."""
        return self._selection_start is not None and self._selection_end is not None

    def _get_selected_text(self) -> str:
        """Extract plain text from selected strips.

        Uses strip.crop() to handle cell-to-text conversion properly,
        which correctly handles double-width character boundaries.
        """
        selection = self._get_normalized_selection()
        if not selection:
            return ""

        start, end = selection
        start_row, start_col = start
        end_row, end_col = end

        lines = []
        for row in range(start_row, end_row + 1):
            if row >= len(self._strips):
                break

            strip = self._strips[row]

            if row == start_row and row == end_row:
                # Single line - crop both ends
                cropped = strip.crop(start_col, end_col)
            elif row == start_row:
                # First line - crop from start
                cropped = strip.crop(start_col, strip.cell_length)
            elif row == end_row:
                # Last line - crop to end
                cropped = strip.crop(0, end_col)
            else:
                # Middle lines - full text
                cropped = strip

            lines.append(cropped.text)

        return "\n".join(lines)

    def action_copy_selection(self) -> None:
        """Copy selected text to clipboard (bound to Ctrl+C)."""
        if self._has_selection():
            text = self._get_selected_text()
            if text:
                self.app.copy_to_clipboard(text)
                self.notify("Copied to clipboard")
