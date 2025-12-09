"""Output protocol conformance tests.

Tests that output implementations correctly conform to their protocols:
- BaseOutputProtocol
- FormattedOutputProtocol
- OutputSink / RichRenderableProtocol
"""

import pytest

from tests.protocol_conformance.conftest import (
    assert_implements_protocol,
    assert_isinstance_protocol,
)

# Import protocols
from scrappy.protocols.output import (
    BaseOutputProtocol,
    FormattedOutputProtocol,
    RichRenderableProtocol,
)
from scrappy.cli.protocols import OutputSink


class TestBaseOutputProtocolConformance:
    """Tests for BaseOutputProtocol implementations."""








# OperationalOutputProtocol was a backward compatibility alias that has been removed
# All code now uses BaseOutputProtocol directly


class TestFormattedOutputProtocolConformance:
    """Tests for FormattedOutputProtocol implementations."""









class TestFormattedOutputAlsoImplementsBase:
    """Tests that FormattedOutputProtocol implementations also implement BaseOutputProtocol."""




class TestRichRenderableProtocolConformance:
    """Tests for RichRenderableProtocol implementations."""


    def test_output_sink_protocol_matches_rich_renderable(self):
        """OutputSink protocol should have same methods as RichRenderableProtocol."""
        # Both protocols should define post_output and post_renderable
        from tests.protocol_conformance.conftest import get_protocol_methods

        sink_methods = set(get_protocol_methods(OutputSink))
        renderable_methods = set(get_protocol_methods(RichRenderableProtocol))

        # OutputSink should have at least the same methods as RichRenderableProtocol
        assert renderable_methods.issubset(sink_methods), (
            f"OutputSink missing methods from RichRenderableProtocol: "
            f"{renderable_methods - sink_methods}"
        )


class TestOutputBehavior:
    """Tests that verify actual behavior matches protocol contracts."""

    def test_capturing_output_captures_all_levels(self):
        """CapturingOutput should capture info, warn, error, and success."""
        from scrappy.orchestrator.output import CapturingOutput

        output = CapturingOutput()

        output.info("info message")
        output.warn("warn message")
        output.error("error message")
        output.success("success message")

        assert output.get_by_level('info') == ["info message"]
        assert output.get_by_level('warn') == ["warn message"]
        assert output.get_by_level('error') == ["error message"]
        assert output.get_by_level('success') == ["success message"]


    def test_test_output_captures_print(self):
        """TestOutput should capture printed text."""
        from scrappy.cli.output import TestOutput

        output = TestOutput()
        output.print("hello", color="green", bold=True)

        assert "hello" in output.get_output()
        styled_calls = output.get_styled_calls()
        assert len(styled_calls) == 1
        assert styled_calls[0]['color'] == 'green'
        assert styled_calls[0]['bold'] is True

    def test_test_output_returns_preset_inputs(self):
        """TestOutput should return preset input values."""
        from scrappy.cli.output import TestOutput

        output = TestOutput(inputs=["first", "second"])

        assert output.prompt("prompt1") == "first"
        assert output.prompt("prompt2") == "second"
        assert output.prompt("prompt3", default="default") == "default"

    def test_test_output_returns_preset_confirmations(self):
        """TestOutput should return preset confirmation values."""
        from scrappy.cli.output import TestOutput

        output = TestOutput(confirmations=[True, False])

        assert output.confirm("confirm1") is True
        assert output.confirm("confirm2") is False
        assert output.confirm("confirm3", default=True) is True
