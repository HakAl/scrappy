"""Characterization pins for ProviderStatusReporter (PR-5, bead scrappy-86pi).

ProviderStatusReporter calls self._selector._get_brain_selection_reason, a
method that exists nowhere in production. The bug pins below construct the
reporter with a REAL ProviderSelector and pin the resulting AttributeError;
commit 3 flips them. The copy pins ground the exact authored strings in
status_reporter.py, stubbing only the missing reason seam where the code
path requires it.
"""

import pytest

from scrappy.orchestrator.provider_definitions import AGENT_PROVIDER_GUIDANCE
from scrappy.orchestrator.provider_selector import ProviderSelector
from scrappy.orchestrator.status_reporter import ProviderStatusReporter


class RecordingOutput:
    """Output stub that records info lines verbatim."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, message: str) -> None:
        self.lines.append(message)


class GeneralUseOnlyProvider:
    """Provider that does not support the agent/brain role."""

    supports_agent_role = False


class AgentCapableProvider:
    """Provider without the supports_agent_role attribute (agent-capable path)."""


class FakeRegistry:
    """Minimal registry over an in-memory provider mapping."""

    def __init__(self, providers: dict) -> None:
        self._providers = dict(providers)

    def list_available(self) -> list[str]:
        return list(self._providers)

    def get(self, name: str):
        return self._providers[name]


class SelectorWithAvailableReason(ProviderSelector):
    """Real selector plus the reason seam the reporter expects.

    Production ProviderSelector lacks _get_brain_selection_reason entirely
    (scrappy-86pi); this subclass supplies the minimal seam so the authored
    copy around it can be pinned.
    """

    def _get_brain_selection_reason(self, provider_name: str) -> str:
        return "available"


def make_reporter(
    registry: FakeRegistry,
    selector: ProviderSelector,
    output: RecordingOutput,
    brain_name=None,
    quality_mode: bool = True,
) -> ProviderStatusReporter:
    """Build a reporter with real objects and the given selector."""
    return ProviderStatusReporter(
        registry=registry,
        provider_selector=selector,
        output=output,
        brain_name=brain_name,
        verbose_selection=False,
        quality_mode=quality_mode,
    )


class TestRealSelectorContractBug86pi:
    """BUG PINS (scrappy-86pi): real selector lacks the reason method."""

    def test_print_status_with_real_selector_raises_attributeerror_bug_86pi(self):
        """print_status raises the moment any provider is available."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        reporter = make_reporter(registry, ProviderSelector(), RecordingOutput())

        with pytest.raises(AttributeError, match="_get_brain_selection_reason"):
            reporter.print_status()

    def test_get_selection_info_with_real_selector_raises_attributeerror_bug_86pi(self):
        """get_selection_info raises the moment any provider is available."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        reporter = make_reporter(registry, ProviderSelector(), RecordingOutput())

        with pytest.raises(AttributeError, match="_get_brain_selection_reason"):
            reporter.get_selection_info()


class TestPrintStatusCopyPins:
    """Copy pins for the strings authored in status_reporter.py."""

    def test_available_provider_line_copy(self):
        """Available agent-capable provider line has no suffix."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        output = RecordingOutput()
        reporter = make_reporter(registry, SelectorWithAvailableReason(), output)

        reporter.print_status()

        assert "  [OK] groq            - available" in output.lines

    def test_available_provider_general_use_only_suffix(self):
        """Provider that cannot act as agent gets the general-use-only suffix."""
        registry = FakeRegistry({"groq": GeneralUseOnlyProvider()})
        output = RecordingOutput()
        reporter = make_reporter(registry, SelectorWithAvailableReason(), output)

        reporter.print_status()

        assert "  [OK] groq            - available (general use only)" in output.lines

    def test_unavailable_provider_line_copy_real_selector(self):
        """With nothing available, every known provider gets the [--] line."""
        output = RecordingOutput()
        reporter = make_reporter(FakeRegistry({}), ProviderSelector(), output)

        reporter.print_status()

        assert (
            "  [--] cerebras        - NOT AVAILABLE (missing API key or package)"
            in output.lines
        )
        assert (
            "  [--] groq            - NOT AVAILABLE (missing API key or package)"
            in output.lines
        )
        assert (
            "  [--] gemini          - NOT AVAILABLE (missing API key or package)"
            in output.lines
        )
        assert (
            "  [--] sambanova       - NOT AVAILABLE (missing API key or package)"
            in output.lines
        )

    def test_selected_brain_and_reason_copy(self):
        """Selected brain line shows the name and its selection reason."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        output = RecordingOutput()
        reporter = make_reporter(
            registry, SelectorWithAvailableReason(), output, brain_name="groq"
        )

        reporter.print_status()

        assert "\nSelected Brain: groq" in output.lines
        assert "Selection Reason: available" in output.lines

    def test_mode_priority_guidance_copy_real_selector(self):
        """Header, brain-none, mode, priority, and guidance copy pins."""
        output = RecordingOutput()
        reporter = make_reporter(
            FakeRegistry({}), ProviderSelector(), output, quality_mode=True
        )

        reporter.print_status()

        assert "PROVIDER CONFIGURATION SUMMARY" in output.lines
        assert "\nSelected Brain: None" in output.lines
        assert "\nModel Selection Mode: CHAT" in output.lines
        assert "  Use /model fast or /model chat to change mode" in output.lines
        assert (
            "\nSelection Priority: cerebras > groq > gemini > sambanova"
            in output.lines
        )
        assert AGENT_PROVIDER_GUIDANCE in output.lines
        assert "Use --brain <provider> to override auto-selection" in output.lines

    def test_mode_line_fast_when_quality_mode_false(self):
        """quality_mode=False renders the FAST mode line."""
        output = RecordingOutput()
        reporter = make_reporter(
            FakeRegistry({}), ProviderSelector(), output, quality_mode=False
        )

        reporter.print_status()

        assert "\nModel Selection Mode: FAST" in output.lines
