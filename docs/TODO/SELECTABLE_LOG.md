# SelectableLog Widget Plan

## Problem
Users can't copy text from RichLog in Textual.

## Solution
Build a SelectableLog widget using Textual's Strip API (~150 lines).

---

## Architecture

```python
class SelectableLog(Widget):
    """RichLog replacement with mouse text selection."""

    can_focus = True

    # Storage: list of Strip objects (colored lines)
    _strips: list[Strip]

    # Selection state
    _selection_start: tuple[int, int] | None  # (row, col) in scroll space
    _selection_end: tuple[int, int] | None

    # Performance: cache highlighted strips while selection is stable
    _cached_selection_range: tuple[tuple[int, int], tuple[int, int]] | None
    _cached_highlighted_strips: dict[int, Strip]  # row -> highlighted strip
```

---

## Critical Implementation Notes

### 1. Performance: Cache Highlighted Strips

`render_line()` is called for every visible line on every frame. `Strip.crop()` is cheap but not zero-cost - cropping 200 colored segments 60x/s adds up.

**Solution:** Cache the highlighted version while selection is stable. Invalidate only when `_selection_end` moves.

```python
def _invalidate_highlight_cache(self) -> None:
    """Clear cache when selection changes."""
    self._cached_highlighted_strips.clear()
    self._cached_selection_range = None
```

### 2. Coordinate Systems: Widget Space vs Scroll Space

Mouse coordinates are in widget space; strips are in scroll space.

- `event.y` is relative to visible viewport - add `self.scroll_offset.y` before indexing into `self._strips`
- `event.x` vs `strip.cell_length` - double-width emoji will mis-align if you use raw `event.x`

```python
def _mouse_to_scroll_coords(self, event) -> tuple[int, int]:
    """Convert widget-space mouse coords to scroll-space row/col."""
    row = event.y + self.scroll_offset.y
    # For col: need to account for cell width (emoji, CJK)
    col = self._x_to_cell_offset(event.x, row)
    return (row, col)
```

### 3. Use Strip.apply_style() for Highlighting

Don't manually crop+reverse. `Strip.apply_style()` keeps original segments untouched and only overlays the reverse attribute - no new allocations for un-selected parts.

```python
from rich.style import Style

def _highlight_strip(self, strip: Strip, start: int, end: int) -> Strip:
    """Apply reverse style to selected portion."""
    rev = Style(reverse=True)
    return strip.apply_style(rev, start=start, end=end)
```

### 4. Empty Lines Must Be Preserved

RichLog collapses consecutive `\n`. If you want identical behavior (and correct copy), use:

```python
options = self._console.options.update(height=None)
segments = list(self._console.render(renderable, options))
```

This makes Rich insert `Segment("\n")` for every hard break, so you get one `Strip([])` per blank line. Otherwise copying selected text loses empty lines and cursor position drifts.

### 5. Virtual Size Management

Inheriting from Widget gives scrollbars, but only if you update virtual size. After appending strips:

```python
def write(self, renderable):
    # ... append strips ...

    # CRITICAL: Update virtual size so scrollbars appear
    self.virtual_size = Size(
        max(self.virtual_size.width, max((s.cell_length for s in self._strips), default=0)),
        len(self._strips)
    )
```

### 6. Selection Direction (Drag Up)

Users often click and drag upwards. Must normalize the range:

```python
def _get_normalized_selection(self) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return (start, end) with start always before end."""
    start = self._selection_start
    end = self._selection_end
    if start is None or end is None:
        return None
    if start > end:
        start, end = end, start
    return (start, end)
```

### 7. Memory Management (max_lines)

Without max_lines, memory grows indefinitely. Implement like RichLog:

```python
def write(self, renderable):
    # ... append strips ...

    if self.max_lines and len(self._strips) > self.max_lines:
        overflow = len(self._strips) - self.max_lines
        self._strips = self._strips[overflow:]
        # Adjust selection indices if now invalid
        if self._selection_start:
            row, col = self._selection_start
            self._selection_start = (max(0, row - overflow), col)
        if self._selection_end:
            row, col = self._selection_end
            self._selection_end = (max(0, row - overflow), col)
        self._invalidate_highlight_cache()
```

### 8. Resizing & Wrapping

**The "Fixed Strip" Problem:** Strips have fixed width based on console width at creation time. Terminal resize won't reflow text.

**Decision:** For a log widget, horizontal scrolling is acceptable. Text won't wrap on resize - user scrolls horizontally. This matches RichLog behavior.

### 9. Use Textual's cell_len

Don't use `wcwidth` directly. Use Textual's helper to match rendering:

```python
from textual._cells import cell_len

# In _x_to_cell_offset:
char_width = cell_len(char)
```

### 10. CSS for Scrolling

Widget handles scrolling if `virtual_size > size` and overflow is set:

```python
DEFAULT_CSS = """
SelectableLog {
    overflow: auto;
}
"""
```

---

## Implementation Steps

### Step 1: Basic Widget Structure

```python
from textual.widget import Widget
from textual.strip import Strip
from rich.console import Console, RenderableType
from rich.segment import Segment

class SelectableLog(Widget):
    """Log widget with text selection support."""

    can_focus = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._strips: list[Strip] = []
        self._selection_start: tuple[int, int] | None = None
        self._selection_end: tuple[int, int] | None = None
        self._console = Console(force_terminal=True, no_color=False)

    def write(self, renderable: RenderableType) -> None:
        """Add a Rich renderable to the log."""
        # Render to segments, convert to Strips
        # Append to self._strips
        # self.refresh()
        pass

    def render_line(self, y: int) -> Strip:
        """Render a single line with selection highlighting."""
        pass
```

### Step 2: Rich Renderable to Strips Conversion

```python
def write(self, renderable: RenderableType) -> None:
    """Convert Rich renderable to Strips and append."""
    # Render with height=None to preserve empty lines (don't collapse \n)
    options = self._console.options.update(height=None)
    segments = list(self._console.render(renderable, options))

    # Split into lines - empty lines become Strip([])
    current_line: list[Segment] = []
    for segment in segments:
        if '\n' in segment.text:
            parts = segment.text.split('\n')
            for i, part in enumerate(parts):
                if i > 0:
                    # New line - save current and start new
                    self._strips.append(Strip(current_line))
                    current_line = []
                if part:
                    current_line.append(Segment(part, segment.style))
        else:
            current_line.append(segment)

    if current_line:
        self._strips.append(Strip(current_line))

    self.refresh()

    # Only auto-scroll if user is already at bottom (don't yank them down)
    if self._is_at_bottom():
        self.scroll_end()

def _is_at_bottom(self) -> bool:
    """Check if viewport is scrolled to bottom."""
    return self.scroll_offset.y >= max(0, len(self._strips) - self.size.height)

def on_scroll(self, event) -> None:
    """Track scroll position to manage auto-scroll behavior."""
    # Auto-scroll stops as soon as user scrolls up
    pass  # _is_at_bottom() handles this dynamically
```

### Step 3: Mouse Selection (with coordinate conversion)

```python
def on_mouse_down(self, event: MouseDown) -> None:
    """Start selection on mouse down."""
    self._selection_start = self._mouse_to_scroll_coords(event)
    self._selection_end = None
    self._invalidate_highlight_cache()
    self.capture_mouse()

def on_mouse_move(self, event: MouseMove) -> None:
    """Update selection on mouse drag."""
    if self._selection_start is not None:
        new_end = self._mouse_to_scroll_coords(event)
        if new_end != self._selection_end:
            self._selection_end = new_end
            self._invalidate_highlight_cache()
            self.refresh()

def on_mouse_up(self, event: MouseUp) -> None:
    """End selection on mouse up."""
    self.release_mouse()

def _mouse_to_scroll_coords(self, event) -> tuple[int, int]:
    """Convert widget-space mouse coords to scroll-space row/col."""
    row = event.y + self.scroll_offset.y
    col = self._x_to_cell_offset(event.x, row)
    return (row, col)

def _x_to_cell_offset(self, x: int, row: int) -> int:
    """Convert x position to cell offset, handling double-width chars."""
    from textual._cells import cell_len

    if row >= len(self._strips):
        return x
    strip = self._strips[row]
    # Walk segments, accumulating cell widths until we reach x
    cell_offset = 0
    visual_offset = 0
    for segment in strip._segments:
        for char in segment.text:
            char_width = cell_len(char)
            if visual_offset + char_width > x:
                return cell_offset
            visual_offset += char_width
            cell_offset += 1
    return cell_offset
```

### Step 4: Selection Highlighting in Render (with caching)

```python
def render_line(self, y: int) -> Strip:
    """Render line with selection highlight. Uses cache for performance."""
    scroll_y = y + self.scroll_offset.y

    if scroll_y >= len(self._strips):
        return Strip.blank(self.size.width)

    # Check cache first
    if scroll_y in self._cached_highlighted_strips:
        return self._cached_highlighted_strips[scroll_y]

    strip = self._strips[scroll_y]

    # Apply selection highlight if this line is in selection range
    if self._is_in_selection(scroll_y):
        start_col, end_col = self._get_selection_columns(scroll_y)
        strip = self._highlight_strip(strip, start_col, end_col)
        # Cache the result
        self._cached_highlighted_strips[scroll_y] = strip

    return strip

def _highlight_strip(self, strip: Strip, start: int, end: int) -> Strip:
    """Apply reverse style to selected portion. No new allocations for unselected."""
    rev = Style(reverse=True)
    return strip.apply_style(rev, start=start, end=end)
```

### Step 5: Copy to Clipboard

```python
def on_key(self, event: Key) -> None:
    """Handle Ctrl+C to copy selection."""
    if event.key == "ctrl+c" and self._has_selection():
        text = self._get_selected_text()
        import pyperclip
        pyperclip.copy(text)
        self.notify("Copied to clipboard")
        event.stop()

def _get_selected_text(self) -> str:
    """Extract plain text from selected strips."""
    # Get rows in selection range
    # For each row, extract text from start_col to end_col
    # Join with newlines
    pass
```

---

## Integration

Replace RichLog usage in `chat_layout.py`:

```python
# Before
from textual.widgets import RichLog

# After
from .selectable_log import SelectableLog

# Usage is the same
log = SelectableLog()
log.write(panel)  # Rich Panel
log.write(text)   # Rich Text
log.write("string")  # Plain string
```

---

## Testing Checklist

### Basic Functionality
- [ ] Rich renderables display correctly (Panel, Table, Text, Syntax)
- [ ] Click and drag selects text
- [ ] Selection highlights visually (reverse video)
- [ ] Ctrl+C copies selected text to clipboard
- [ ] Auto-scrolls to bottom on new content
- [ ] Manual scroll works
- [ ] Colors preserved in display

### Edge Cases (Critical)
- [ ] **Drag Up**: Start selection at line 10, drag to line 5 - selection works correctly
- [ ] **Resize**: Resize terminal - text doesn't disappear (horizontal scroll if needed)
- [ ] **Double-Width Chars**: Select line with emojis/CJK - cursor position is accurate
- [ ] **Style Retention**: Bold/red text stays bold/red when selected (reverse overlay)
- [ ] **Empty Lines**: `write("\n")` creates visible blank line, copies correctly
- [ ] **Max Lines**: Feed 10,000 lines - memory usage stable, old lines discarded
- [ ] **Selection After Overflow**: Selection adjusts correctly when max_lines trims content

### Performance
- [ ] Large content (1000+ lines) renders smoothly
- [ ] Selection highlight doesn't cause lag (cache working)
- [ ] Scrolling is responsive

---

## Files

| File | Action |
|------|--------|
| `cli/widgets/selectable_log.py` | Create (~150 lines) |
| `cli/screens/chat_layout.py` | Replace RichLog import |
| `tests/cli/test_selectable_log.py` | Create tests |

---

## Dependencies

- Textual >= 0.40 (Strip API)
- pyperclip (clipboard access)

---

## Estimated Time

1-2 days for polished, tested widget.
