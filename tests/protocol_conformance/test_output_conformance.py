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

    def test_console_output_implements_protocol(self):
        """ConsoleOutput should implement BaseOutputProtocol."""
        from scrappy.orchestrator.output import ConsoleOutput

        assert_implements_protocol(ConsoleOutput, BaseOutputProtocol)

    def test_console_output_isinstance(self):
        """ConsoleOutput instance should pass isinstance check."""
        from scrappy.orchestrator.output import ConsoleOutput

        instance = ConsoleOutput()
        assert_isinstance_protocol(instance, BaseOutputProtocol)

    def test_null_output_implements_protocol(self):
        """NullOutput should implement BaseOutputProtocol."""
        from scrappy.orchestrator.output import NullOutput

        assert_implements_protocol(NullOutput, BaseOutputProtocol)

    def test_null_output_isinstance(self):
        """NullOutput instance should pass isinstance check."""
        from scrappy.orchestrator.output import NullOutput

        instance = NullOutput()
        assert_isinstance_protocol(instance, BaseOutputProtocol)

    def test_capturing_output_implements_protocol(self):
        """CapturingOutput should implement BaseOutputProtocol."""
        from scrappy.orchestrator.output import CapturingOutput

        assert_implements_protocol(CapturingOutput, BaseOutputProtocol)

    def test_capturing_output_isinstance(self):
        """CapturingOutput instance should pass isinstance check."""
        from scrappy.orchestrator.output import CapturingOutput

        instance = CapturingOutput()
        assert_isinstance_protocol(instance, BaseOutputProtocol)


# OperationalOutputProtocol was a backward compatibility alias that has been removed
# All code now uses BaseOutputProtocol directly


class TestFormattedOutputProtocolConformance:
    """Tests for FormattedOutputProtocol implementations."""

    def test_test_output_implements_protocol(self):
        """TestOutput should implement FormattedOutputProtocol."""
        from scrappy.cli.output import TestOutput

        assert_implements_protocol(TestOutput, FormattedOutputProtocol)

    def test_test_output_isinstance(self):
        """TestOutput instance should pass isinstance check."""
        from scrappy.cli.output import TestOutput

        instance = TestOutput()
        assert_isinstance_protocol(instance, FormattedOutputProtocol)

    def test_rich_output_implements_protocol(self):
        """RichOutput should implement FormattedOutputProtocol."""
        pytest.importorskip("rich")
        from scrappy.cli.output import RichOutput

        assert_implements_protocol(RichOutput, FormattedOutputProtocol)

    def test_rich_output_isinstance(self):
        """RichOutput instance should pass isinstance check."""
        pytest.importorskip("rich")
        from scrappy.cli.output import RichOutput

        instance = RichOutput()
        assert_isinstance_protocol(instance, FormattedOutputProtocol)

    def test_click_output_implements_protocol(self):
        """ClickOutput should implement FormattedOutputProtocol."""
        pytest.importorskip("click")
        from scrappy.cli.output import ClickOutput

        assert_implements_protocol(ClickOutput, FormattedOutputProtocol)

    def test_click_output_isinstance(self):
        """ClickOutput instance should pass isinstance check."""
        pytest.importorskip("click")
        from scrappy.cli.output import ClickOutput

        instance = ClickOutput()
        assert_isinstance_protocol(instance, FormattedOutputProtocol)

    def test_output_factory_implements_protocol(self):
        """Output (factory delegator) should implement FormattedOutputProtocol."""
        from scrappy.cli.output import Output

        assert_implements_protocol(Output, FormattedOutputProtocol)


class TestFormattedOutputAlsoImplementsBase:
    """Tests that FormattedOutputProtocol implementations also implement BaseOutputProtocol."""

    def test_test_output_implements_base(self):
        """TestOutput should also implement BaseOutputProtocol (via inheritance)."""
        from scrappy.cli.output import TestOutput

        instance = TestOutput()
        # FormattedOutputProtocol extends BaseOutputProtocol
        assert_isinstance_protocol(instance, BaseOutputProtocol)

    def test_rich_output_implements_base(self):
        """RichOutput should also implement BaseOutputProtocol."""
        pytest.importorskip("rich")
        from scrappy.cli.output import RichOutput

        instance = RichOutput()
        assert_isinstance_protocol(instance, BaseOutputProtocol)


class TestRichRenderableProtocolConformance:
    """Tests for RichRenderableProtocol implementations."""

    @pytest.mark.skip(reason="OutputBridge implements BaseOutputProtocol, not RichRenderableProtocol")
    def test_output_bridge_implements_protocol(self):
        """OutputBridge should implement RichRenderableProtocol."""
        from scrappy.cli.output_bridge import OutputBridge

        assert_implements_protocol(OutputBridge, RichRenderableProtocol)

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

    def test_null_output_discards_all(self):
        """NullOutput should not raise errors when called."""
        from scrappy.orchestrator.output import NullOutput

        output = NullOutput()

        # Should not raise
        output.info("info message")
        output.warn("warn message")
        output.error("error message")
        output.success("success message")

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
