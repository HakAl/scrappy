"""
Tests for ProviderStatusReporter.

Tests presentation logic for provider status display and information retrieval.
"""

import pytest
from unittest.mock import Mock

from scrappy.orchestrator.output import CapturingOutput
from scrappy.orchestrator.status_reporter import ProviderStatusReporter

class TestPrintStatus:
    """Test print_status() presentation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output = CapturingOutput()
        self.registry = Mock()
        self.selector = Mock()

    def _make_reporter(self, brain_name='cerebras', verbose=False):
        """Create a reporter with configured mocks."""
        return ProviderStatusReporter(
            registry=self.registry,
            provider_selector=self.selector,
            output=self.output,
            brain_name=brain_name,
            verbose_selection=verbose
        )

    def test_shows_available_provider_with_ok_status(self):
        """print_status() should show [OK] for available providers."""
        self.registry.list_available.return_value = ['cerebras', 'groq']
        self.selector._get_brain_selection_reason.return_value = 'fastest'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert '[OK] cerebras' in output_text
        assert '[OK] groq' in output_text

    def test_shows_unavailable_provider_with_dash_status(self):
        """print_status() should show [--] for unavailable providers."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'fastest'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert '[--] groq' in output_text
        assert 'NOT AVAILABLE' in output_text

    def test_shows_selection_reason_for_available_provider(self):
        """print_status() should show selection reason for available providers."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'fastest inference'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'fastest inference' in output_text

    def test_shows_selected_brain(self):
        """print_status() should show the selected brain name."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter(brain_name='groq')
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'Selected Brain: groq' in output_text

    def test_shows_selection_reason_for_brain(self):
        """print_status() should show why the brain was selected."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'high priority'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter(brain_name='cerebras')
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'Selection Reason: high priority' in output_text

    def test_shows_selection_priority(self):
        """print_status() should show the selection priority order."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'Selection Priority:' in output_text
        assert 'cerebras' in output_text
        assert 'Recommended for agent work: Cerebras first, Groq second.' in output_text
        assert 'Gemini is overflow' in output_text

    def test_shows_override_hint(self):
        """print_status() should show how to override selection."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert '--brain' in output_text

    def test_verbose_shows_selection_log(self):
        """print_status() should show selection log when verbose is True."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = [
            'Checking cerebras: available',
            'Selected cerebras'
        ]

        reporter = self._make_reporter(verbose=True)
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'Selection Log:' in output_text
        assert 'Checking cerebras: available' in output_text
        assert 'Selected cerebras' in output_text

    def test_non_verbose_hides_selection_log(self):
        """print_status() should not show selection log when verbose is False."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = [
            'Checking cerebras: available'
        ]

        reporter = self._make_reporter(verbose=False)
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'Selection Log:' not in output_text

    def test_empty_selection_log_not_shown(self):
        """print_status() should not show selection log section when empty."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter(verbose=True)
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        assert 'Selection Log:' not in output_text

    def test_all_known_providers_listed(self):
        """print_status() should list all known providers."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        # All known providers should appear
        assert 'cerebras' in output_text
        assert 'groq' in output_text
        assert 'gemini' in output_text
        assert 'sambanova' in output_text

    def test_no_brain_selected_shows_none(self):
        """print_status() should handle case when no brain is selected."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter(brain_name=None)
        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        # Should show Selected Brain with None or empty
        assert 'Selected Brain:' in output_text


class TestGetSelectionInfo:
    """Test get_selection_info() data retrieval."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output = CapturingOutput()
        self.registry = Mock()
        self.selector = Mock()

    def _make_reporter(self, brain_name='cerebras', verbose=False):
        """Create a reporter with configured mocks."""
        return ProviderStatusReporter(
            registry=self.registry,
            provider_selector=self.selector,
            output=self.output,
            brain_name=brain_name,
            verbose_selection=verbose
        )

    def test_returns_available_providers(self):
        """get_selection_info() should return list of available providers."""
        self.registry.list_available.return_value = ['cerebras', 'groq']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        assert info['available_providers'] == ['cerebras', 'groq']

    def test_returns_all_known_providers(self):
        """get_selection_info() should return list of all known providers."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        # Check all expected providers are present (order depends on PROVIDERS dict)
        expected_providers = {'cerebras', 'groq', 'gemini', 'sambanova'}
        assert set(info['all_known_providers']) == expected_providers

    def test_returns_selected_brain(self):
        """get_selection_info() should return the selected brain name."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter(brain_name='gemini')
        info = reporter.get_selection_info()

        assert info['selected_brain'] == 'gemini'

    def test_returns_selection_priority(self):
        """get_selection_info() should return selection priority list."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        assert info['selection_priority'] == ['cerebras', 'groq', 'gemini', 'sambanova']

    def test_returns_provider_details_for_available(self):
        """get_selection_info() should return details for available providers."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'fastest'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        cerebras_info = info['provider_details']['cerebras']
        assert cerebras_info['available'] is True
        assert cerebras_info['reason'] == 'fastest'

    def test_returns_provider_details_for_unavailable(self):
        """get_selection_info() should return details for unavailable providers."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        groq_info = info['provider_details']['groq']
        assert groq_info['available'] is False
        assert groq_info['reason'] == 'not available'

    def test_returns_selection_log(self):
        """get_selection_info() should return the selection log."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = ['entry1', 'entry2']

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        assert info['selection_log'] == ['entry1', 'entry2']

    def test_returns_correct_structure(self):
        """get_selection_info() should return dict with all expected keys."""
        self.registry.list_available.return_value = ['cerebras']
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter()
        info = reporter.get_selection_info()

        expected_keys = {
            'available_providers',
            'all_known_providers',
            'selected_brain',
            'selection_priority',
            'provider_details',
            'selection_log'
        }
        assert set(info.keys()) == expected_keys

    def test_provider_details_contains_all_known(self):
        """get_selection_info() should have details for all known providers."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

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
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = self._make_reporter(brain_name=None)
        info = reporter.get_selection_info()

        assert info['selected_brain'] is None


class TestProviderStatusReporterEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output = CapturingOutput()
        self.registry = Mock()
        self.selector = Mock()

    def test_empty_available_providers(self):
        """Should handle case with no available providers."""
        self.registry.list_available.return_value = []
        self.selector._get_brain_selection_reason.return_value = 'test'
        self.selector.get_selection_log.return_value = []

        reporter = ProviderStatusReporter(
            registry=self.registry,
            provider_selector=self.selector,
            output=self.output,
            brain_name=None,
            verbose_selection=False
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
        self.selector._get_brain_selection_reason.return_value = 'test reason'
        self.selector.get_selection_log.return_value = []

        reporter = ProviderStatusReporter(
            registry=self.registry,
            provider_selector=self.selector,
            output=self.output,
            brain_name='cerebras',
            verbose_selection=False
        )

        reporter.print_status()

        messages = self.output.get_by_level('info')
        output_text = '\n'.join(messages)

        # All listed providers should show as OK
        for provider in all_providers:
            assert f'[OK] {provider}' in output_text
