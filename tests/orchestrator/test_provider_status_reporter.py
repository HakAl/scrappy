"""Characterization pins for ProviderStatusReporter (PR-5, bead scrappy-86pi).

The reporter is selector-free: it renders availability directly from the
registry, so real objects produce working output (the 86pi AttributeError
bug pins flipped here in commit 3). The copy pins ground the exact
authored strings in status_reporter.py.
"""

from scrappy.orchestrator.provider_definitions import AGENT_PROVIDER_GUIDANCE
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


def make_reporter(
    registry: FakeRegistry,
    output: RecordingOutput,
    brain_name=None,
    quality_mode: bool = True,
) -> ProviderStatusReporter:
    """Build a reporter with real objects."""
    return ProviderStatusReporter(
        registry=registry,
        output=output,
        brain_name=brain_name,
        quality_mode=quality_mode,
    )


class TestRealObjectContract86piFixed:
    """WORKING-OUTPUT PINS (scrappy-86pi fixed): real objects render status."""

    def test_print_status_with_real_objects_renders_available_line(self):
        """print_status renders the available line for a real registry entry."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        output = RecordingOutput()
        reporter = make_reporter(registry, output)

        reporter.print_status()

        assert "  [OK] groq            - available" in output.lines

    def test_get_selection_info_with_real_objects_reports_available(self):
        """get_selection_info reports availability for a real registry entry."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        reporter = make_reporter(registry, RecordingOutput())

        info = reporter.get_selection_info()

        assert info["provider_details"]["groq"] == {
            "available": True,
            "supports_agent_role": True,
            "reason": "available",
        }
        assert "selection_log" not in info


class TestPrintStatusCopyPins:
    """Copy pins for the strings authored in status_reporter.py."""

    def test_available_provider_line_copy(self):
        """Available agent-capable provider line has no suffix."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        output = RecordingOutput()
        reporter = make_reporter(registry, output)

        reporter.print_status()

        assert "  [OK] groq            - available" in output.lines

    def test_available_provider_general_use_only_suffix(self):
        """Provider that cannot act as agent gets the general-use-only suffix."""
        registry = FakeRegistry({"groq": GeneralUseOnlyProvider()})
        output = RecordingOutput()
        reporter = make_reporter(registry, output)

        reporter.print_status()

        assert "  [OK] groq            - available (general use only)" in output.lines

    def test_unavailable_provider_line_copy_real_selector(self):
        """With nothing available, every known provider gets the [--] line."""
        output = RecordingOutput()
        reporter = make_reporter(FakeRegistry({}), output)

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

    def test_selected_brain_copy(self):
        """Selected brain line shows the name."""
        registry = FakeRegistry({"groq": AgentCapableProvider()})
        output = RecordingOutput()
        reporter = make_reporter(registry, output, brain_name="groq")

        reporter.print_status()

        assert "\nSelected Brain: groq" in output.lines

    def test_mode_priority_guidance_copy_real_selector(self):
        """Header, brain-none, mode, priority, and guidance copy pins."""
        output = RecordingOutput()
        reporter = make_reporter(FakeRegistry({}), output, quality_mode=True)

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
        reporter = make_reporter(FakeRegistry({}), output, quality_mode=False)

        reporter.print_status()

        assert "\nModel Selection Mode: FAST" in output.lines
