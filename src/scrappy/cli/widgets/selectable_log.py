"""Model-backed transcript widget with mouse text selection."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable, Optional

from rich.console import RenderableType
from rich.segment import Segment
from rich.style import Style
from textual._cells import cell_len
from textual import events
from textual.events import MouseDown, MouseMove, MouseUp
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from .transcript_model import EntryId, TranscriptModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RenderedLine:
    """One terminal-width rendered row for a transcript entry."""

    entry_id: EntryId
    strip: Strip
    is_placeholder: bool = False


class SelectableLog(ScrollView, can_focus=True):
    """Transcript view with model-backed rendering and text selection."""

    _VIEWPORT_RENDER_BUFFER = 8
    _BOTTOM_TOLERANCE_ROWS = 2

    def __init__(
        self,
        max_lines: Optional[int] = None,
        **kwargs,
    ):
        """Initialize SelectableLog.

        Args:
            max_lines: Maximum retained rendered rows, trimmed by whole entries.
        """
        self._following: bool = True
        self._programmatic_scroll: bool = False
        super().__init__(**kwargs)
        self._model = TranscriptModel()
        self._render_width: int | None = None
        self._rendered_lines: list[_RenderedLine] = []
        self._rendered_entry_count = 0
        self._entry_line_ranges: dict[EntryId, tuple[int, int]] = {}
        self._selection_start: Optional[tuple[int, int]] = None
        self._selection_end: Optional[tuple[int, int]] = None
        self._is_selecting = False
        self._max_lines = max_lines
        self._widest_line_width = 0

    @property
    def selection_text(self) -> str:
        """Return the selected transcript text."""
        return self._get_selected_text()

    @property
    def is_following(self) -> bool:
        """Return whether the transcript is pinned to live output."""
        return self._following

    @property
    def is_at_bottom(self) -> bool:
        """Return whether the viewport is within bottom tolerance."""
        max_scroll_y = self._max_scroll_y()
        current_y = float(self.scroll_offset.y)
        return current_y >= max_scroll_y - self._BOTTOM_TOLERANCE_ROWS

    @property
    def transcript_model(self) -> TranscriptModel:
        """Return the runtime transcript model."""
        return self._model

    def write(self, renderable: RenderableType) -> None:
        """Add a Rich renderable to the log."""
        self._sync_render_width()
        should_follow = self._following and self.is_at_bottom
        reviewing_y = float(self.scroll_offset.y)

        self._model.append(renderable)
        self._render_new_entries_if_cache_complete()
        self._apply_max_lines()
        self._update_virtual_size()

        if should_follow:
            self.scroll_to_bottom()
        else:
            self._following = False
            self._scroll_to_y(reviewing_y)

    def clear(self) -> None:
        """Clear all content from the log."""
        self._model.clear()
        self._clear_render_cache()
        self._clear_selection()
        self.virtual_size = Size(0, 0)
        self._following = True
        self.refresh()

    def set_following(self, following: bool) -> None:
        """Set follow/review mode for transcript output."""
        self._following = following
        if following:
            self.scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        """Scroll to the live bottom and enter following mode."""
        self._following = True
        self._with_programmatic_scroll(
            lambda: self.scroll_end(
                animate=False,
                x_axis=False,
                y_axis=True,
            )
        )

    def follow_latest(self) -> None:
        """Return to live transcript output."""
        self.scroll_to_bottom()

    def action_scroll_up(self) -> None:
        """Scroll up and enter review mode."""
        self._following = False
        self.scroll_up(animate=False, immediate=True)

    def action_scroll_down(self) -> None:
        """Scroll down and follow again when the bottom is reached."""
        self.scroll_down(animate=False, immediate=True)
        self._update_following_after_user_scroll()

    def action_page_up(self) -> None:
        """Page up and enter review mode."""
        self._following = False
        self.scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        """Page down and follow again when the bottom is reached."""
        self.scroll_page_down(animate=False)
        self._update_following_after_user_scroll()

    def action_scroll_home(self) -> None:
        """Scroll to transcript start and enter review mode."""
        self._following = False
        self.scroll_home(animate=False, immediate=True, x_axis=False, y_axis=True)

    def action_scroll_end(self) -> None:
        """Scroll to transcript end and follow live output."""
        self.scroll_to_bottom()

    def render_line(self, y: int) -> Strip:
        """Render a single visible line with selection highlighting."""
        self._sync_render_width()

        scroll_x, scroll_y = self.scroll_offset
        line_index = int(scroll_y) + y
        width = self.scrollable_content_region.width
        self._ensure_rendered_through_line(
            line_index + self._VIEWPORT_RENDER_BUFFER
        )

        strip = self._line_strip(line_index)
        if strip is None:
            return Strip.blank(width, self.rich_style)
        selection = self._get_normalized_selection()
        if selection:
            strip = self._apply_selection_to_line(strip, line_index, selection)

        strip = strip.crop_extend(int(scroll_x), int(scroll_x) + width, self.rich_style)
        return strip.apply_style(self.rich_style)

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """Keep follow/review mode in sync with manual scroll movement."""
        super().watch_scroll_y(old_value, new_value)
        if self._programmatic_scroll:
            return
        if new_value < old_value:
            self._following = False
            return
        self._update_following_after_user_scroll()

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        """Mouse wheel up enters review mode."""
        self._following = False
        super()._on_mouse_scroll_up(event)

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        """Mouse wheel down follows again when the bottom is reached."""
        super()._on_mouse_scroll_down(event)
        self._update_following_after_user_scroll()

    def _max_scroll_y(self) -> float:
        """Return the current maximum vertical scroll offset."""
        return max(0.0, float(getattr(self, "max_scroll_y", 0.0) or 0.0))

    def _update_following_after_user_scroll(self) -> None:
        """Update state after user-driven scrolling."""
        if self.is_at_bottom:
            self._following = True
            max_scroll_y = self._max_scroll_y()
            if float(self.scroll_offset.y) < max_scroll_y:
                self._scroll_to_y(max_scroll_y)
        else:
            self._following = False

    def _scroll_to_y(self, y: float) -> None:
        """Scroll vertically without changing follow/review state."""
        self._with_programmatic_scroll(
            lambda: self.scroll_to(
                y=y,
                animate=False,
                immediate=True,
            )
        )

    def _with_programmatic_scroll(self, operation: Callable[[], None]) -> None:
        """Run a scroll operation without treating it as user navigation."""
        previous = self._programmatic_scroll
        self._programmatic_scroll = True
        try:
            operation()
        finally:
            self._programmatic_scroll = previous

    def _current_render_width(self) -> int:
        """Return the width used to render transcript entries."""
        console_width = self.app.console.width
        return self.scrollable_content_region.width or console_width

    def _sync_render_width(self) -> None:
        """Invalidate rendered rows when terminal wrapping width changes."""
        width = self._current_render_width()
        if self._render_width == width:
            return

        if self._render_width is not None:
            self._clear_selection()
        self._render_width = width
        self._clear_render_cache()
        self._update_virtual_size()

    def _clear_render_cache(self) -> None:
        """Clear rendered rows while preserving transcript entries."""
        self._rendered_lines.clear()
        self._rendered_entry_count = 0
        self._entry_line_ranges.clear()
        self._widest_line_width = 0

    def _render_entry(self, entry_id: EntryId, renderable: RenderableType) -> list[Strip]:
        """Render one transcript entry for the current width."""
        width = self._render_width or self._current_render_width()
        render_options = self.app.console.options.update_width(width)
        segments = list(self.app.console.render(renderable, render_options))
        lines = list(Segment.split_lines(segments))
        if not lines:
            return [Strip.blank(0)]
        strips = Strip.from_lines(lines)
        if not strips:
            return [Strip.blank(0)]
        return strips

    def _render_new_entries_if_cache_complete(self) -> None:
        """Render appended entries when the current cache is already complete."""
        if self._rendered_entry_count < len(self._model) - 1:
            return
        self._render_entries_until_count(len(self._model))

    def _ensure_rendered_through_line(self, line_index: int) -> None:
        """Render entries until line_index is available or entries are exhausted."""
        while (
            len(self._rendered_lines) <= line_index
            and self._rendered_entry_count < len(self._model)
        ):
            gap = line_index - len(self._rendered_lines)
            if gap > self._VIEWPORT_RENDER_BUFFER:
                self._append_placeholder_entries_until_line(line_index)
            else:
                self._render_entries_until_count(self._rendered_entry_count + 1)
        self._update_virtual_size()

    def _render_entries_until_count(self, entry_count: int) -> None:
        """Render retained entries up to entry_count."""
        entries = self._model.entries()
        while self._rendered_entry_count < min(entry_count, len(entries)):
            entry = entries[self._rendered_entry_count]
            start = len(self._rendered_lines)
            strips = self._render_entry(entry.id, entry.renderable)
            for strip in strips:
                self._rendered_lines.append(_RenderedLine(entry.id, strip))
                self._widest_line_width = max(
                    self._widest_line_width,
                    strip.cell_length,
                )
            end = len(self._rendered_lines)
            self._entry_line_ranges[entry.id] = (start, end)
            self._rendered_entry_count += 1

    def _append_placeholder_entries_until_line(self, line_index: int) -> None:
        """Skip non-visible entries with cheap one-row placeholders."""
        entries = self._model.entries()
        target_count = min(line_index + 1, len(entries))
        while self._rendered_entry_count < target_count:
            entry = entries[self._rendered_entry_count]
            row = len(self._rendered_lines)
            self._rendered_lines.append(
                _RenderedLine(entry.id, Strip.blank(0), is_placeholder=True)
            )
            self._entry_line_ranges[entry.id] = (row, row + 1)
            self._rendered_entry_count += 1

    def _materialize_placeholder_at(self, row: int) -> None:
        """Render a placeholder row on demand."""
        if row < 0 or row >= len(self._rendered_lines):
            return
        line = self._rendered_lines[row]
        if not line.is_placeholder:
            return

        entry = self._model.get(line.entry_id)
        if entry is None:
            return

        rendered = [
            _RenderedLine(line.entry_id, strip)
            for strip in self._render_entry(entry.id, entry.renderable)
        ]
        self._rendered_lines[row: row + 1] = rendered
        for rendered_line in rendered:
            self._widest_line_width = max(
                self._widest_line_width,
                rendered_line.strip.cell_length,
            )
        self._rebuild_entry_line_ranges()

    def _update_virtual_size(self) -> None:
        """Update ScrollView's virtual size from known rendered rows."""
        if self._rendered_entry_count == len(self._model):
            height = len(self._rendered_lines)
        else:
            height = max(len(self._rendered_lines), len(self._model))
        self.virtual_size = Size(self._widest_line_width, height)

    def _apply_max_lines(self) -> None:
        """Trim old entries when rendered rows exceed max_lines."""
        if not self._max_lines:
            return
        entry_overflow = len(self._model) - self._max_lines
        if entry_overflow > 0:
            last_overflow_id = self._model.entry_ids()[entry_overflow - 1]
            self._trim_model_through(last_overflow_id)

        if self._rendered_entry_count != len(self._model):
            return

        last_removed_id: EntryId | None = None
        while len(self._rendered_lines) > self._max_lines and self._rendered_lines:
            last_removed_id = self._rendered_lines[0].entry_id
            self._drop_rendered_entry(last_removed_id)

        if last_removed_id is not None:
            self._trim_model_through(last_removed_id)

    def _trim_model_through(self, entry_id: EntryId) -> None:
        """Trim model and rendered rows through entry_id."""
        removed_ids = set(self._model.trim_through(entry_id))
        if not removed_ids:
            return

        self._rendered_lines = [
            line for line in self._rendered_lines if line.entry_id not in removed_ids
        ]
        self._rendered_entry_count = max(
            0,
            self._rendered_entry_count - len(removed_ids),
        )
        self._clear_selection()
        self._rebuild_entry_line_ranges()
        self._recompute_widest_line_width()

    def _drop_rendered_entry(self, entry_id: EntryId) -> None:
        """Drop rendered rows for an entry already selected for trimming."""
        self._rendered_lines = [
            line for line in self._rendered_lines if line.entry_id != entry_id
        ]

    def _rebuild_entry_line_ranges(self) -> None:
        """Rebuild line ranges after rendered rows are trimmed."""
        ranges: dict[EntryId, list[int]] = {}
        for index, line in enumerate(self._rendered_lines):
            if line.entry_id not in ranges:
                ranges[line.entry_id] = [index, index + 1]
            else:
                ranges[line.entry_id][1] = index + 1
        self._entry_line_ranges = {
            entry_id: (bounds[0], bounds[1])
            for entry_id, bounds in ranges.items()
        }

    def _recompute_widest_line_width(self) -> None:
        """Recompute widest known rendered line after trimming."""
        self._widest_line_width = max(
            (line.strip.cell_length for line in self._rendered_lines),
            default=0,
        )

    def _apply_selection_to_line(
        self,
        strip: Strip,
        line_index: int,
        selection: tuple[tuple[int, int], tuple[int, int]],
    ) -> Strip:
        """Apply selection style to one rendered line."""
        start, end = selection
        start_row, start_col = start
        end_row, end_col = end

        if not start_row <= line_index <= end_row:
            return strip

        if line_index == start_row and line_index == end_row:
            highlight_start = start_col
            highlight_end = end_col
        elif line_index == start_row:
            highlight_start = start_col
            highlight_end = strip.cell_length
        elif line_index == end_row:
            highlight_start = 0
            highlight_end = end_col
        else:
            highlight_start = 0
            highlight_end = strip.cell_length

        if highlight_start >= highlight_end:
            return strip
        return self._highlight_strip(strip, highlight_start, highlight_end)

    def _highlight_strip(self, strip: Strip, start: int, end: int) -> Strip:
        """Apply reverse style to selected cells in a strip."""
        rev = Style(reverse=True)
        length = strip.cell_length

        if start >= end or start >= length or length == 0:
            return strip
        end = min(end, length)

        if start == 0 and end >= length:
            return strip.apply_style(rev)
        if start == 0:
            parts = list(strip.divide([end, length]))
            if parts:
                parts[0] = parts[0].apply_style(rev)
            return Strip.join(parts)
        if end >= length:
            parts = list(strip.divide([start, length]))
            if len(parts) >= 2:
                parts[1] = parts[1].apply_style(rev)
            return Strip.join(parts)

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

    def _clear_selection(self) -> None:
        """Clear selection and release any active drag capture."""
        was_selecting = self._is_selecting
        self._selection_start = None
        self._selection_end = None
        self._is_selecting = False
        if was_selecting:
            try:
                self.release_mouse()
            except Exception as exc:
                logger.debug("Failed to release mouse while clearing selection: %s", exc)

    def _mouse_to_scroll_coords(self, event) -> tuple[int, int]:
        """Convert widget-space mouse coords to scroll-space row/col cells."""
        row = event.y + int(self.scroll_offset.y)
        col = self._x_to_cell_position(event.x + int(self.scroll_offset.x), row)
        return (row, col)

    def _line_strip(self, row: int) -> Strip | None:
        """Return a rendered line by row, rendering lazily if needed."""
        self._ensure_rendered_through_line(row)
        if row < 0 or row >= len(self._rendered_lines):
            return None
        self._materialize_placeholder_at(row)
        if row >= len(self._rendered_lines):
            return None
        return self._rendered_lines[row].strip

    def _x_to_cell_position(self, x: int, row: int) -> int:
        """Convert x position to a cell position in a rendered row."""
        strip = self._line_strip(row)
        if strip is None:
            return x
        if strip.cell_length == 0:
            return 0

        cell_position = 0
        for segment in strip:
            for char in segment.text:
                char_width = cell_len(char)
                if cell_position + char_width > x:
                    return cell_position
                cell_position += char_width

        return cell_position

    def on_mouse_down(self, event: MouseDown) -> None:
        """Start selection on mouse down."""
        self._sync_render_width()
        self._selection_start = self._mouse_to_scroll_coords(event)
        self._selection_end = None
        self._is_selecting = True
        self.capture_mouse()
        self.refresh()

    def on_mouse_move(self, event: MouseMove) -> None:
        """Update selection on mouse drag."""
        if self._is_selecting:
            new_end = self._mouse_to_scroll_coords(event)
            if new_end != self._selection_end:
                self._selection_end = new_end
                self.refresh()

    def on_mouse_up(self, event: MouseUp) -> None:
        """End selection on mouse up."""
        self._is_selecting = False
        self.release_mouse()

    def _get_selected_text(self) -> str:
        """Extract plain text from selected rendered rows."""
        selection = self._get_normalized_selection()
        if not selection:
            return ""

        start, end = selection
        start_row, start_col = start
        end_row, end_col = end

        lines = []
        for row in range(start_row, end_row + 1):
            strip = self._line_strip(row)
            if strip is None:
                break

            if row == start_row and row == end_row:
                cropped = strip.crop(start_col, end_col)
            elif row == start_row:
                cropped = strip.crop(start_col, strip.cell_length)
            elif row == end_row:
                cropped = strip.crop(0, end_col)
            else:
                cropped = strip

            lines.append(cropped.text)

        return "\n".join(lines)

    def action_copy_selection(self) -> None:
        """Copy selected text to clipboard."""
        text = self.selection_text
        if text:
            self.app.copy_to_clipboard(text)
            self.notify("Copied to clipboard")
