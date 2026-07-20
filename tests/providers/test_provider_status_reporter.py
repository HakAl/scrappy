"""
Tests for ProviderStatusReporter.

Tests presentation logic for provider status display and information
retrieval. The reporter is selector-free: availability is rendered
directly from the registry (the external boundary, mocked here).
"""

from unittest.mock import Mock

from scrappy.orchestrator.output import CapturingOutput
from scrappy.orchestrator.status_reporter import ProviderStatusReporter


class GeneralUseOnlyProvider:
    """Provider that does not support the agent/brain role."""

    supports_agent_role = False


class TestPrintStatus:
    """Test print_status() presentation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output = CapturingOutput()
        self.registry = Mock()

    def _make_reporter(self, brain_name='cerebras', quality_mode=True):
        """Create a reporter with the mocked registry."""
        return ProviderStatusReporter(
            registry=self.registry,
            output=self.output,
            brain_name=brain_name,
            quality_mode=quality_mode
        )

    def _output_text(self):
        """Join captured info lines for assertions."""
        return '\n'.join(self.output.get_by_level('info'))

    def test_shows_available_provider_with_ok_status(self):
        """print_status() should show [OK] for available providers."""
        self.registry.list_available.return_value = ['cerebras', 'groq']

        reporter = self._make_reporter()
        reporter.print_status()

        output_text = self._output_text()

        assert '[OK] cerebras' in output_text
        assert '[OK] groq' in output_text

    def test_shows_unavailable_provider_with_dash_status(self):
        """print_status() should show [--] for unavailable providers."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        reporter.print_status()

        output_text = self._output_text()

        assert '[--] groq' in output_text
        assert 'NOT AVAILABLE' in output_text

    def test_shows_available_text_for_available_provider(self):
        """print_status() should describe available providers as available."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        reporter.print_status()

        assert '  [OK] cerebras        - available' in self._output_text()

    def test_shows_general_use_only_suffix(self):
        """Providers without agent-role support get the general-use suffix."""
        self.registry.list_available.return_value = ['groq']
        self.registry.get.return_value = GeneralUseOnlyProvider()

        reporter = self._make_reporter()
        reporter.print_status()

        assert (
            '  [OK] groq            - available (general use only)'
            in self._output_text()
        )

    def test_shows_selected_brain(self):
        """print_status() should show the selected brain name."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter(brain_name='groq')
        reporter.print_status()

        assert 'Selected Brain: groq' in self._output_text()

    def test_shows_selection_priority(self):
        """print_status() should show the selection priority order."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        reporter.print_status()

        output_text = self._output_text()

        assert 'Selection Priority:' in output_text
        assert 'cerebras' in output_text
        assert 'Recommended for agent work: Cerebras first, Groq second.' in output_text
        assert 'Gemini is overflow' in output_text

    def test_shows_override_hint(self):
        """print_status() should show how to override selection."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        reporter.print_status()

        assert '--brain' in self._output_text()

    def test_no_selection_log_section(self):
        """print_status() has no selection log section anymore."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        reporter.print_status()

        assert 'Selection Log:' not in self._output_text()

    def test_all_known_providers_listed(self):
        """print_status() should list all known providers."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        reporter.print_status()

        output_text = self._output_text()

        # All known providers should appear
        assert 'cerebras' in output_text
        assert 'groq' in output_text
        assert 'gemini' in output_text
        assert 'sambanova' in output_text

    def test_no_brain_selected_shows_none(self):
        """print_status() should handle case when no brain is selected."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter(brain_name=None)
        reporter.print_status()

        # Should show Selected Brain with None or empty
        assert 'Selected Brain:' in self._output_text()


class TestGetSelectionInfo:
    """Test get_selection_info() data retrieval."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output = CapturingOutput()
        self.registry = Mock()

    def _make_reporter(self, brain_name='cerebras', quality_mode=True):
        """Create a reporter with the mocked registry."""
        return ProviderStatusReporter(
            registry=self.registry,
            output=self.output,
            brain_name=brain_name,
            quality_mode=quality_mode
        )

    def test_returns_available_providers(self):
        """get_selection_info() should return list of available providers."""
        self.registry.list_available.return_value = ['cerebras', 'groq']

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        assert info['available_providers'] == ['cerebras', 'groq']

    def test_returns_all_known_providers(self):
        """get_selection_info() should return list of all known providers."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        # Check all expected providers are present (order depends on PROVIDERS dict)
        expected_providers = {'cerebras', 'groq', 'gemini', 'sambanova'}
        assert set(info['all_known_providers']) == expected_providers

    def test_returns_selected_brain(self):
        """get_selection_info() should return the selected brain name."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter(brain_name='gemini')
        info = reporter.get_selection_info()

        assert info['selected_brain'] == 'gemini'

    def test_returns_selection_priority(self):
        """get_selection_info() should return selection priority list."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        assert info['selection_priority'] == ['cerebras', 'groq', 'gemini', 'sambanova']

    def test_returns_provider_details_for_available(self):
        """get_selection_info() should return details for available providers."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        cerebras_info = info['provider_details']['cerebras']
        assert cerebras_info['available'] is True
        assert cerebras_info['reason'] == 'available'

    def test_returns_provider_details_for_unavailable(self):
        """get_selection_info() should return details for unavailable providers."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        groq_info = info['provider_details']['groq']
        assert groq_info['available'] is False
        assert groq_info['reason'] == 'not available'

    def test_no_selection_log_key(self):
        """get_selection_info() no longer carries a selection log."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        assert 'selection_log' not in info

    def test_returns_correct_structure(self):
        """get_selection_info() should return dict with all expected keys."""
        self.registry.list_available.return_value = ['cerebras']

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        expected_keys = {
            'available_providers',
            'all_known_providers',
            'selected_brain',
            'selection_priority',
            'provider_details',
        }
        assert set(info.keys()) == expected_keys

    def test_provider_details_contains_all_known(self):
        """get_selection_info() should have details for all known providers."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        expected_providers = ['cerebras', 'groq', 'gemini', 'sambanova']
        for provider in expected_providers:
            assert provider in info['provider_details']
            assert 'available' in info['provider_details'][provider]
            assert 'reason' in info['provider_details'][provider]

    def test_handles_none_brain_name(self):
        """get_selection_info() should handle None brain name."""
        self.registry.list_available.return_value = []

        reporter = self._make_reporter(brain_name=None)
        info = reporter.get_selection_info()

        assert info['selected_brain'] is None


class TestProviderStatusReporterEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output = CapturingOutput()
        self.registry = Mock()

    def test_empty_available_providers(self):
        """Should handle case with no available providers."""
        self.registry.list_available.return_value = []

        reporter = ProviderStatusReporter(
            registry=self.registry,
            output=self.output,
            brain_name=None,
        )

        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        # All providers should show as unavailable
        assert '[--]' in output_text
        assert 'NOT AVAILABLE' in output_text

    def test_all_providers_available(self):
        """Should handle case with all providers available."""
        all_providers = ['cerebras', 'groq', 'gemini']  # Only test subset since mock setup is limited
        self.registry.list_available.return_value = all_providers

        reporter = ProviderStatusReporter(
            registry=self.registry,
            output=self.output,
            brain_name='cerebras',
        )

        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        # All listed providers should show as OK
        for provider in all_providers:
            assert f'[OK] {provider}' in output_text
