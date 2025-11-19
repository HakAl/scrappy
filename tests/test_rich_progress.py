"""
Tests for Rich progress bar and streaming functionality.

Following TDD: these tests define the expected behavior of RichIO progress features
for Phase 6 of Rich integration.

Test coverage:
- Progress bar creation and updates
- Spinner for indeterminate operations
- Streaming output handling
- Context manager patterns
- Multiple concurrent progress operations
- Edge cases and error handling
"""

import pytest
from io import StringIO
from typing import List
import time


class TestRichIOProgressBarBasics:
    """Tests for basic progress bar functionality."""

    @pytest.mark.unit
    def test_richio_has_progress_method(self):
        """Test that RichIO has progress context manager method."""
        from src.cli.rich_output import RichIO
        io = RichIO()
        assert hasattr(io, 'progress')
        assert callable(io.progress)

    @pytest.mark.unit
    def test_progress_context_manager_basic(self):
        """Test progress bar works as context manager."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=10, description="Processing") as progress:
            assert progress is not None
            for i in range(10):
                progress.advance(1)

        # Should complete without error
        result = output.getvalue()
        assert "Processing" in result

    @pytest.mark.unit
    def test_progress_returns_tracker(self):
        """Test that progress context returns a progress tracker."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=5, description="Test") as progress:
            # Should have advance method
            assert hasattr(progress, 'advance')
            assert callable(progress.advance)

    @pytest.mark.unit
    def test_progress_advance_updates_progress(self):
        """Test that advance() increments progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=10, description="Loading") as progress:
            progress.advance(5)
            progress.advance(5)

        # Should have completed
        result = output.getvalue()
        assert len(result) > 0

    @pytest.mark.unit
    def test_progress_with_label(self):
        """Test progress bar shows description label."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=3, description="Scanning files") as progress:
            progress.advance(3)

        result = output.getvalue()
        assert "Scanning files" in result


class TestRichIOProgressBarAdvanced:
    """Tests for advanced progress bar functionality."""

    @pytest.mark.unit
    def test_progress_update_with_custom_amount(self):
        """Test advancing by custom amounts."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=100, description="Progress") as progress:
            progress.advance(25)
            progress.advance(25)
            progress.advance(50)

        # Should complete
        result = output.getvalue()
        assert len(result) > 0

    @pytest.mark.unit
    def test_progress_tracker_has_update_description(self):
        """Test progress tracker can update description mid-progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=10, description="Step 1") as progress:
            progress.advance(5)
            progress.update_description("Step 2")
            progress.advance(5)

        result = output.getvalue()
        # Should show both descriptions at some point
        assert "Step 1" in result or "Step 2" in result

    @pytest.mark.unit
    def test_progress_auto_completes_on_exit(self):
        """Test progress bar cleans up on context exit."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=5, description="Auto") as progress:
            progress.advance(3)
            # Exit without completing all 5

        # Should exit cleanly without hanging
        result = output.getvalue()
        assert len(result) > 0

    @pytest.mark.unit
    def test_progress_with_zero_total(self):
        """Test progress bar handles zero total gracefully."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        # Should not raise
        with io.progress(total=0, description="Empty") as progress:
            pass

        result = output.getvalue()
        assert len(result) >= 0


class TestRichIOSpinner:
    """Tests for spinner (indeterminate progress) functionality."""

    @pytest.mark.unit
    def test_richio_has_spinner_method(self):
        """Test that RichIO has spinner context manager method."""
        from src.cli.rich_output import RichIO
        io = RichIO()
        assert hasattr(io, 'spinner')
        assert callable(io.spinner)

    @pytest.mark.unit
    def test_spinner_context_manager_basic(self):
        """Test spinner works as context manager."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.spinner(text="Loading..."):
            # Simulate some work
            pass

        result = output.getvalue()
        assert "Loading" in result

    @pytest.mark.unit
    def test_spinner_with_message(self):
        """Test spinner displays message."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.spinner(text="Analyzing codebase"):
            pass

        result = output.getvalue()
        assert "Analyzing" in result

    @pytest.mark.unit
    def test_spinner_with_style(self):
        """Test spinner with custom style."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        # Should not raise
        with io.spinner(text="Working", spinner_style="dots"):
            pass

        result = output.getvalue()
        assert len(result) > 0

    @pytest.mark.unit
    def test_spinner_cleans_up_on_exit(self):
        """Test spinner cleans up properly on context exit."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.spinner(text="Brief task"):
            pass

        # Additional output after spinner should work
        io.echo("After spinner")

        result = output.getvalue()
        assert "After spinner" in result

    @pytest.mark.unit
    def test_spinner_handles_exception(self):
        """Test spinner cleans up even on exception."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with pytest.raises(ValueError):
            with io.spinner(text="Will fail"):
                raise ValueError("Test error")

        # Console should still be usable after
        io.echo("After error")
        result = output.getvalue()
        assert "After error" in result


class TestRichIOStreaming:
    """Tests for streaming output functionality."""

    @pytest.mark.unit
    def test_richio_has_stream_method(self):
        """Test that RichIO has stream context manager."""
        from src.cli.rich_output import RichIO
        io = RichIO()
        assert hasattr(io, 'stream')
        assert callable(io.stream)

    @pytest.mark.unit
    def test_stream_write_outputs_immediately(self):
        """Test stream writes output without buffering."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            stream.write("chunk1")
            stream.write("chunk2")

        result = output.getvalue()
        assert "chunk1" in result
        assert "chunk2" in result

    @pytest.mark.unit
    def test_stream_write_no_newline_by_default(self):
        """Test stream writes don't add newlines."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            stream.write("a")
            stream.write("b")
            stream.write("c")

        result = output.getvalue()
        # Should be able to find abc contiguous
        assert "abc" in result.replace('\n', '')

    @pytest.mark.unit
    def test_stream_write_with_style(self):
        """Test stream can write styled text."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        io = RichIO(console=console)

        with io.stream() as stream:
            stream.write("styled", style="green")

        result = output.getvalue()
        assert "styled" in result

    @pytest.mark.unit
    def test_stream_writeline_adds_newline(self):
        """Test stream writeline adds newline."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            stream.writeline("line1")
            stream.writeline("line2")

        result = output.getvalue()
        lines = result.strip().split('\n')
        assert len(lines) >= 2

    @pytest.mark.unit
    def test_stream_flushes_on_exit(self):
        """Test stream flushes any remaining content on exit."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            stream.write("final content")

        result = output.getvalue()
        assert "final content" in result


class TestRichIOProgressWithStreaming:
    """Tests for combining progress with streaming output."""

    @pytest.mark.unit
    def test_progress_with_stream_output(self):
        """Test progress bar with streamed log output."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=3, description="Processing") as progress:
            progress.advance(1)
            io.echo("Log: Step 1 complete")
            progress.advance(1)
            io.echo("Log: Step 2 complete")
            progress.advance(1)

        result = output.getvalue()
        assert "Processing" in result
        assert "Log: Step 1" in result


class TestRichIOMultipleProgress:
    """Tests for multiple concurrent progress operations."""

    @pytest.mark.unit
    def test_richio_has_multi_progress_method(self):
        """Test RichIO has method for multiple progress bars."""
        from src.cli.rich_output import RichIO
        io = RichIO()
        assert hasattr(io, 'multi_progress')
        assert callable(io.multi_progress)

    @pytest.mark.unit
    def test_multi_progress_creates_multiple_bars(self):
        """Test creating multiple progress bars."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            task1 = mp.add_task("Downloads", total=5)
            task2 = mp.add_task("Processing", total=10)

            mp.advance(task1, 3)
            mp.advance(task2, 5)
            mp.advance(task1, 2)
            mp.advance(task2, 5)

        result = output.getvalue()
        assert "Downloads" in result
        assert "Processing" in result

    @pytest.mark.unit
    def test_multi_progress_add_task(self):
        """Test adding tasks to multi-progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            task_id = mp.add_task("Task 1", total=10)
            assert task_id is not None

    @pytest.mark.unit
    def test_multi_progress_advance_by_id(self):
        """Test advancing specific task by ID."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            t1 = mp.add_task("First", total=5)
            t2 = mp.add_task("Second", total=5)

            mp.advance(t1, 5)
            mp.advance(t2, 5)

        # Should complete both without error
        result = output.getvalue()
        assert len(result) > 0


class TestRichIOProgressEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_progress_advance_beyond_total(self):
        """Test advancing beyond total doesn't crash."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=5, description="Overflow") as progress:
            progress.advance(10)  # More than total

        # Should handle gracefully
        result = output.getvalue()
        assert len(result) > 0

    @pytest.mark.unit
    def test_progress_negative_advance(self):
        """Test negative advance is handled."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        # Should not crash
        with io.progress(total=10, description="Negative") as progress:
            progress.advance(5)
            progress.advance(-2)  # Go back (may be clamped to 0)

        result = output.getvalue()
        assert len(result) > 0

    @pytest.mark.unit
    def test_progress_with_very_long_description(self):
        """Test progress with very long description."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False, width=80)
        io = RichIO(console=console)

        long_desc = "A" * 200
        with io.progress(total=1, description=long_desc) as progress:
            progress.advance(1)

        # Should handle truncation gracefully
        result = output.getvalue()
        assert "A" in result

    @pytest.mark.unit
    def test_progress_with_special_characters(self):
        """Test progress with special characters in description."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=1, description="Test [brackets]") as progress:
            progress.advance(1)

        result = output.getvalue()
        # Rich markup uses brackets, so they need escaping
        assert "Test" in result

    @pytest.mark.unit
    def test_spinner_with_empty_text(self):
        """Test spinner with empty text."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        # Should not crash
        with io.spinner(text=""):
            pass

        result = output.getvalue()
        assert len(result) >= 0

    @pytest.mark.unit
    def test_nested_progress_contexts(self):
        """Test nested progress contexts."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=2, description="Outer") as outer:
            outer.advance(1)
            with io.progress(total=3, description="Inner") as inner:
                inner.advance(3)
            outer.advance(1)

        result = output.getvalue()
        assert "Outer" in result


class TestProgressTrackerInterface:
    """Tests for the ProgressTracker returned by progress()."""

    @pytest.mark.unit
    def test_tracker_has_completed_property(self):
        """Test tracker has a way to check if completed."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=5, description="Check") as progress:
            assert hasattr(progress, 'completed')
            progress.advance(5)

    @pytest.mark.unit
    def test_tracker_has_total_property(self):
        """Test tracker exposes total."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=42, description="Total") as progress:
            assert hasattr(progress, 'total')
            assert progress.total == 42

    @pytest.mark.unit
    def test_tracker_has_current_property(self):
        """Test tracker exposes current progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.progress(total=10, description="Current") as progress:
            assert hasattr(progress, 'current')
            assert progress.current == 0
            progress.advance(5)
            assert progress.current == 5


class TestStreamWriterInterface:
    """Tests for the StreamWriter returned by stream()."""

    @pytest.mark.unit
    def test_stream_has_write_method(self):
        """Test stream writer has write method."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            assert hasattr(stream, 'write')
            assert callable(stream.write)

    @pytest.mark.unit
    def test_stream_has_writeline_method(self):
        """Test stream writer has writeline method."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            assert hasattr(stream, 'writeline')
            assert callable(stream.writeline)

    @pytest.mark.unit
    def test_stream_has_flush_method(self):
        """Test stream writer has flush method."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.stream() as stream:
            assert hasattr(stream, 'flush')
            assert callable(stream.flush)


class TestMultiProgressInterface:
    """Tests for the MultiProgress manager returned by multi_progress()."""

    @pytest.mark.unit
    def test_multi_progress_has_add_task(self):
        """Test multi-progress has add_task method."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            assert hasattr(mp, 'add_task')
            assert callable(mp.add_task)

    @pytest.mark.unit
    def test_multi_progress_has_advance(self):
        """Test multi-progress has advance method."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            assert hasattr(mp, 'advance')
            assert callable(mp.advance)

    @pytest.mark.unit
    def test_multi_progress_has_update(self):
        """Test multi-progress has update method for setting values."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            assert hasattr(mp, 'update')
            assert callable(mp.update)
            task = mp.add_task("Test", total=10)
            mp.update(task, completed=5)


class TestRichIOProgressIntegration:
    """Integration tests for progress features with real use cases."""

    @pytest.mark.unit
    def test_file_scanning_progress_simulation(self):
        """Test simulating file scanning with progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        files = ["file1.py", "file2.py", "file3.py"]

        with io.progress(total=len(files), description="Scanning files") as progress:
            for f in files:
                # Simulate processing
                progress.advance(1)

        result = output.getvalue()
        assert "Scanning files" in result

    @pytest.mark.unit
    def test_multi_step_operation_simulation(self):
        """Test multi-step operation with spinner and progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        # Step 1: Indeterminate (spinner)
        with io.spinner(text="Initializing"):
            pass

        # Step 2: Determinate (progress)
        with io.progress(total=5, description="Processing") as progress:
            for i in range(5):
                progress.advance(1)

        result = output.getvalue()
        assert "Initializing" in result
        assert "Processing" in result

    @pytest.mark.unit
    def test_streaming_llm_response_simulation(self):
        """Test simulating streaming LLM response output."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        chunks = ["Hello", " ", "world", "!"]

        with io.stream() as stream:
            for chunk in chunks:
                stream.write(chunk)

        result = output.getvalue()
        assert "Hello" in result
        assert "world" in result

    @pytest.mark.unit
    def test_context_building_with_file_progress(self):
        """Test simulating context building with file processing progress."""
        from src.cli.rich_output import RichIO
        from rich.console import Console

        output = StringIO()
        console = Console(file=output, force_terminal=False)
        io = RichIO(console=console)

        with io.multi_progress() as mp:
            scan_task = mp.add_task("Scanning", total=10)
            read_task = mp.add_task("Reading", total=5)

            # Simulate scanning
            for _ in range(10):
                mp.advance(scan_task, 1)

            # Simulate reading key files
            for _ in range(5):
                mp.advance(read_task, 1)

        result = output.getvalue()
        assert "Scanning" in result
        assert "Reading" in result
