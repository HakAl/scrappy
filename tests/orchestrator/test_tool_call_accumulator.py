"""
Unit tests for ToolCallAccumulator.

Tests tool call fragment accumulation including:
- Single fragment completion
- Multi-fragment accumulation
- JSON argument parsing
- Multiple parallel tool calls
- Edge cases (empty args, invalid JSON, incomplete fragments)
- State management (get_completed, get_pending, reset, force_complete)
"""

import json

from scrappy.orchestrator.streaming_util import ToolCallAccumulator
from scrappy.orchestrator.types import ToolCallFragment


# =============================================================================
# Helper Functions
# =============================================================================

def make_fragment(
    id: str = "call_123",
    type: str = "function",
    name: str = "test_function",
    arguments: str = "",
    index: int = 0,
    complete: bool = False,
) -> ToolCallFragment:
    """Create a tool call fragment for testing."""
    return ToolCallFragment(
        id=id,
        type=type,
        name=name,
        arguments=arguments,
        index=index,
        complete=complete,
    )


# =============================================================================
# Single Fragment Tests
# =============================================================================

def test_single_complete_fragment():
    """Test adding a single complete fragment with valid JSON arguments."""
    accumulator = ToolCallAccumulator()

    fragment = make_fragment(
        id="call_1",
        name="get_weather",
        arguments='{"location": "NYC"}',
        index=0,
        complete=True,
    )

    result = accumulator.add_fragment(fragment)

    assert result is not None
    assert result.id == "call_1"
    assert result.name == "get_weather"
    assert result.arguments == {"location": "NYC"}
    assert result.index == 0
    assert result.type == "function"


def test_single_incomplete_fragment():
    """Test adding a single incomplete fragment returns None."""
    accumulator = ToolCallAccumulator()

    fragment = make_fragment(
        id="call_1",
        name="get_weather",
        arguments='{"location":',
        index=0,
        complete=False,
    )

    result = accumulator.add_fragment(fragment)

    assert result is None
    assert accumulator.has_pending()
    pending = accumulator.get_pending()
    assert len(pending) == 1
    assert pending[0].index == 0


def test_empty_arguments():
    """Test completing a tool call with empty arguments."""
    accumulator = ToolCallAccumulator()

    fragment = make_fragment(
        id="call_1",
        name="no_args_function",
        arguments="",
        index=0,
        complete=True,
    )

    result = accumulator.add_fragment(fragment)

    assert result is not None
    assert result.arguments == {}




# =============================================================================
# Multi-Fragment Accumulation Tests
# =============================================================================

def test_accumulate_arguments_across_chunks():
    """Test accumulating JSON arguments across multiple chunks."""
    accumulator = ToolCallAccumulator()

    # First chunk: id and start of arguments
    fragment1 = make_fragment(
        id="call_1",
        name="get_weather",
        arguments='{"location":',
        index=0,
        complete=False,
    )
    result1 = accumulator.add_fragment(fragment1)
    assert result1 is None

    # Second chunk: more arguments
    fragment2 = make_fragment(
        id="",
        name="",
        arguments=' "NYC",',
        index=0,
        complete=False,
    )
    result2 = accumulator.add_fragment(fragment2)
    assert result2 is None

    # Third chunk: complete arguments
    fragment3 = make_fragment(
        id="",
        name="",
        arguments=' "units": "metric"}',
        index=0,
        complete=True,
    )
    result3 = accumulator.add_fragment(fragment3)

    assert result3 is not None
    assert result3.id == "call_1"
    assert result3.name == "get_weather"
    assert result3.arguments == {"location": "NYC", "units": "metric"}


def test_accumulate_name_across_chunks():
    """Test that later non-empty name values overwrite earlier ones."""
    accumulator = ToolCallAccumulator()

    # First chunk: partial name
    fragment1 = make_fragment(
        id="call_1",
        name="get_wea",
        arguments="",
        index=0,
        complete=False,
    )
    accumulator.add_fragment(fragment1)

    # Second chunk: updated name (overwrites) and arguments
    fragment2 = make_fragment(
        id="",
        name="get_weather",
        arguments='{"location": "NYC"}',
        index=0,
        complete=True,
    )
    result = accumulator.add_fragment(fragment2)

    assert result is not None
    assert result.name == "get_weather"


def test_accumulate_id_across_chunks():
    """Test that later non-empty id values overwrite earlier ones."""
    accumulator = ToolCallAccumulator()

    # First chunk: partial ID
    fragment1 = make_fragment(
        id="call_",
        name="test_func",
        arguments="",
        index=0,
        complete=False,
    )
    accumulator.add_fragment(fragment1)

    # Second chunk: updated ID (overwrites) and arguments
    fragment2 = make_fragment(
        id="call_abc123",
        name="",
        arguments='{}',
        index=0,
        complete=True,
    )
    result = accumulator.add_fragment(fragment2)

    assert result is not None
    assert result.id == "call_abc123"


def test_fragment_marked_complete_before_all_data():
    """Test completing only when fragment has id, name, and complete flag."""
    accumulator = ToolCallAccumulator()

    # Fragment marked complete but missing name
    fragment1 = make_fragment(
        id="call_1",
        name="",
        arguments='{}',
        index=0,
        complete=True,
    )
    result1 = accumulator.add_fragment(fragment1)
    assert result1 is None

    # Add name
    fragment2 = make_fragment(
        id="",
        name="test_func",
        arguments="",
        index=0,
        complete=False,
    )
    result2 = accumulator.add_fragment(fragment2)

    # Now should be complete since we have id, name, and complete flag
    assert result2 is not None
    assert result2.name == "test_func"


# =============================================================================
# Multiple Parallel Tool Calls Tests
# =============================================================================

def test_multiple_parallel_tool_calls():
    """Test accumulating multiple tool calls in parallel."""
    accumulator = ToolCallAccumulator()

    # First tool call (index 0)
    fragment1 = make_fragment(
        id="call_1",
        name="get_weather",
        arguments='{"location": "NYC"}',
        index=0,
        complete=True,
    )
    result1 = accumulator.add_fragment(fragment1)
    assert result1 is not None
    assert result1.index == 0

    # Second tool call (index 1)
    fragment2 = make_fragment(
        id="call_2",
        name="get_time",
        arguments='{"timezone": "EST"}',
        index=1,
        complete=True,
    )
    result2 = accumulator.add_fragment(fragment2)
    assert result2 is not None
    assert result2.index == 1

    # Verify completed list
    completed = accumulator.get_completed()
    assert len(completed) == 2
    assert completed[0].index == 0
    assert completed[1].index == 1


def test_interleaved_fragments():
    """Test fragments from different tool calls arriving interleaved."""
    accumulator = ToolCallAccumulator()

    # Start first tool call
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="func1",
        arguments='{"a":',
        index=0,
        complete=False,
    ))

    # Start second tool call
    accumulator.add_fragment(make_fragment(
        id="call_2",
        name="func2",
        arguments='{"b":',
        index=1,
        complete=False,
    ))

    # Continue first tool call
    accumulator.add_fragment(make_fragment(
        id="",
        name="",
        arguments=' 1}',
        index=0,
        complete=True,
    ))

    # Continue second tool call
    accumulator.add_fragment(make_fragment(
        id="",
        name="",
        arguments=' 2}',
        index=1,
        complete=True,
    ))

    completed = accumulator.get_completed()
    assert len(completed) == 2
    assert completed[0].arguments == {"a": 1}
    assert completed[1].arguments == {"b": 2}


def test_out_of_order_completion():
    """Test tool calls completing out of index order."""
    accumulator = ToolCallAccumulator()

    # Add index 1 first
    accumulator.add_fragment(make_fragment(
        id="call_2",
        name="second",
        arguments='{"x": 2}',
        index=1,
        complete=True,
    ))

    # Add index 0 second
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="first",
        arguments='{"x": 1}',
        index=0,
        complete=True,
    ))

    # Completed list should be sorted by index
    completed = accumulator.get_completed()
    assert len(completed) == 2
    assert completed[0].index == 0
    assert completed[0].name == "first"
    assert completed[1].index == 1
    assert completed[1].name == "second"


# =============================================================================
# JSON Parsing and Error Handling Tests
# =============================================================================





def test_complex_nested_json():
    """Test parsing complex nested JSON arguments."""
    accumulator = ToolCallAccumulator()

    complex_args = json.dumps({
        "location": {"city": "NYC", "country": "USA"},
        "options": ["temp", "humidity"],
        "settings": {"units": "metric", "lang": "en"}
    })

    fragment = make_fragment(
        id="call_1",
        name="complex_function",
        arguments=complex_args,
        index=0,
        complete=True,
    )

    result = accumulator.add_fragment(fragment)

    assert result is not None
    assert result.arguments["location"]["city"] == "NYC"
    assert len(result.arguments["options"]) == 2
    assert result.arguments["settings"]["units"] == "metric"


def test_json_with_special_characters():
    """Test JSON arguments containing special characters."""
    accumulator = ToolCallAccumulator()

    args = json.dumps({
        "message": "Hello \"world\"!\nNew line\tTab",
        "unicode": "emoji: \U0001F4A1",
    })

    fragment = make_fragment(
        id="call_1",
        name="special_chars",
        arguments=args,
        index=0,
        complete=True,
    )

    result = accumulator.add_fragment(fragment)

    assert result is not None
    assert "Hello \"world\"!" in result.arguments["message"]
    assert "\U0001F4A1" in result.arguments["unicode"]


# =============================================================================
# State Management Tests
# =============================================================================

def test_get_completed_empty():
    """Test get_completed returns empty list when no completions."""
    accumulator = ToolCallAccumulator()
    assert accumulator.get_completed() == []


def test_get_pending_empty():
    """Test get_pending returns empty list when no pending fragments."""
    accumulator = ToolCallAccumulator()
    assert accumulator.get_pending() == []
    assert not accumulator.has_pending()


def test_get_pending_returns_sorted():
    """Test get_pending returns fragments sorted by index."""
    accumulator = ToolCallAccumulator()

    # Add out of order
    accumulator.add_fragment(make_fragment(index=2, complete=False))
    accumulator.add_fragment(make_fragment(index=0, complete=False))
    accumulator.add_fragment(make_fragment(index=1, complete=False))

    pending = accumulator.get_pending()
    assert len(pending) == 3
    assert pending[0].index == 0
    assert pending[1].index == 1
    assert pending[2].index == 2


def test_has_pending():
    """Test has_pending correctly tracks pending state."""
    accumulator = ToolCallAccumulator()

    assert not accumulator.has_pending()

    accumulator.add_fragment(make_fragment(complete=False))
    assert accumulator.has_pending()

    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="func",
        arguments='{}',
        complete=True,
    ))
    assert not accumulator.has_pending()


def test_reset_clears_state():
    """Test reset clears all fragments and completed calls."""
    accumulator = ToolCallAccumulator()

    # Add completed and pending
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="complete",
        arguments='{}',
        index=0,
        complete=True,
    ))
    accumulator.add_fragment(make_fragment(
        index=1,
        complete=False,
    ))

    assert len(accumulator.get_completed()) == 1
    assert accumulator.has_pending()

    accumulator.reset()

    assert len(accumulator.get_completed()) == 0
    assert not accumulator.has_pending()


def test_fragment_removed_after_completion():
    """Test fragment is removed from pending after completion."""
    accumulator = ToolCallAccumulator()

    # Add incomplete fragment
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="test",
        arguments='{"x":',
        index=0,
        complete=False,
    ))

    assert accumulator.has_pending()

    # Complete it
    accumulator.add_fragment(make_fragment(
        arguments=' 1}',
        index=0,
        complete=True,
    ))

    assert not accumulator.has_pending()
    assert len(accumulator.get_completed()) == 1


# =============================================================================
# Force Complete Pending Tests
# =============================================================================

def test_force_complete_pending_with_valid_fragments():
    """Test force completing pending fragments with valid data."""
    accumulator = ToolCallAccumulator()

    # Add incomplete but valid fragments
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="func1",
        arguments='{"a": 1}',
        index=0,
        complete=False,
    ))
    accumulator.add_fragment(make_fragment(
        id="call_2",
        name="func2",
        arguments='{"b": 2}',
        index=1,
        complete=False,
    ))

    forced = accumulator.force_complete_pending()

    assert len(forced) == 2
    assert forced[0].arguments == {"a": 1}
    assert forced[1].arguments == {"b": 2}
    assert not accumulator.has_pending()
    assert len(accumulator.get_completed()) == 2


def test_force_complete_skips_incomplete_data():
    """Test force complete skips fragments without required fields."""
    accumulator = ToolCallAccumulator()

    # Fragment missing name
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="",
        arguments='{}',
        index=0,
        complete=False,
    ))

    # Fragment missing arguments
    accumulator.add_fragment(make_fragment(
        id="call_2",
        name="func",
        arguments="",
        index=1,
        complete=False,
    ))

    forced = accumulator.force_complete_pending()

    # No fragments should be completed
    assert len(forced) == 0
    assert accumulator.has_pending()




def test_force_complete_empty_accumulator():
    """Test force complete on empty accumulator returns empty list."""
    accumulator = ToolCallAccumulator()

    forced = accumulator.force_complete_pending()

    assert forced == []


def test_force_complete_with_mixed_fragments():
    """Test force complete processes only valid fragments."""
    accumulator = ToolCallAccumulator()

    # Valid fragment
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="valid",
        arguments='{"x": 1}',
        index=0,
        complete=False,
    ))

    # Invalid fragment (missing name)
    accumulator.add_fragment(make_fragment(
        id="call_2",
        name="",
        arguments='{"y": 2}',
        index=1,
        complete=False,
    ))

    # Valid fragment
    accumulator.add_fragment(make_fragment(
        id="call_3",
        name="also_valid",
        arguments='{"z": 3}',
        index=2,
        complete=False,
    ))

    forced = accumulator.force_complete_pending()

    # Only 2 valid fragments should be completed
    assert len(forced) == 2
    assert forced[0].name == "valid"
    assert forced[1].name == "also_valid"

    # One invalid fragment should remain pending
    assert accumulator.has_pending()
    pending = accumulator.get_pending()
    assert len(pending) == 1
    assert pending[0].index == 1


# =============================================================================
# Edge Cases
# =============================================================================

def test_same_index_updates_merge():
    """Test multiple fragments with same index merge correctly."""
    accumulator = ToolCallAccumulator()

    # First fragment at index 0
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="func",
        arguments='{"a":',
        index=0,
        complete=False,
    ))

    # Another fragment at same index
    accumulator.add_fragment(make_fragment(
        id="",
        name="",
        arguments=' 1}',
        index=0,
        complete=True,
    ))

    # Should have merged and completed
    assert not accumulator.has_pending()
    completed = accumulator.get_completed()
    assert len(completed) == 1
    assert completed[0].arguments == {"a": 1}


def test_empty_string_fields_dont_overwrite():
    """Test that empty string fields in fragments don't overwrite existing values."""
    accumulator = ToolCallAccumulator()

    # First fragment with id and name
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="original_name",
        arguments='{"x":',
        index=0,
        complete=False,
    ))

    # Second fragment with empty id and name (should not overwrite)
    accumulator.add_fragment(make_fragment(
        id="",
        name="",
        arguments=' 1}',
        index=0,
        complete=True,
    ))

    completed = accumulator.get_completed()
    assert len(completed) == 1
    assert completed[0].id == "call_1"
    assert completed[0].name == "original_name"


def test_complete_flag_persists():
    """Test complete flag persists once set to True."""
    accumulator = ToolCallAccumulator()

    # Add incomplete fragment
    accumulator.add_fragment(make_fragment(
        id="call_1",
        name="func",
        arguments='{}',
        index=0,
        complete=False,
    ))

    # Mark as complete
    accumulator.add_fragment(make_fragment(
        index=0,
        complete=True,
    ))

    # Should be completed now
    assert not accumulator.has_pending()
    assert len(accumulator.get_completed()) == 1


def test_type_preserved():
    """Test tool call type is preserved from fragments."""
    accumulator = ToolCallAccumulator()

    fragment = make_fragment(
        id="call_1",
        type="custom_type",
        name="func",
        arguments='{}',
        index=0,
        complete=True,
    )

    result = accumulator.add_fragment(fragment)

    assert result is not None
    assert result.type == "custom_type"
