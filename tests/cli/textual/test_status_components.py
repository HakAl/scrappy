"""
Tests for Textual status bar components.
"""

from scrappy.cli.textual.status_components import MetricsStatus


class TestMetricsStatus:
    """Tests for MetricsStatus formatting."""

    def test_empty_state_format(self):
        """Empty state uses placeholder values."""
        metrics = MetricsStatus()
        assert metrics._format_metrics() == "provider: -- | in:-- out:-- | session:-- | ctx:--%"

    def test_format_with_values(self):
        """Formats provider and token values with separators."""
        metrics = MetricsStatus()
        metrics.update(
            provider_display="gemini: gemma",
            input_tokens=123,
            output_tokens=456,
            session_total=579,
            context_percent=42,
        )
        assert metrics._format_metrics() == "gemini: gemma | in:123 out:456 | session:579 | ctx:42%"

    def test_format_with_empty_provider_string(self):
        """Formats empty provider string as placeholder."""
        metrics = MetricsStatus()
        metrics.update(
            provider_display="",
            input_tokens=None,
            output_tokens=None,
            session_total=None,
            context_percent=None,
        )
        assert metrics._format_metrics().startswith("provider: -- |")

    def test_format_with_warning_threshold(self):
        """Formats warning threshold with yellow percent."""
        metrics = MetricsStatus()
        metrics.update(
            provider_display="gemini: gemma",
            input_tokens=100,
            output_tokens=200,
            session_total=300,
            context_percent=85,
        )
        assert metrics._format_metrics().endswith("| ctx:[yellow]85%[/yellow]")

    def test_format_with_error_threshold(self):
        """Formats error threshold with red percent."""
        metrics = MetricsStatus()
        metrics.update(
            provider_display="gemini: gemma",
            input_tokens=100,
            output_tokens=200,
            session_total=300,
            context_percent=95,
        )
        assert metrics._format_metrics().endswith("| ctx:[red]95%[/red]")
