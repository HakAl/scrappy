"""
Tests for config_loader - centralized configuration loading with fallbacks.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGetTruncationDefaults:
    """Tests for get_truncation_defaults function."""

    @pytest.mark.unit
    def test_returns_dict_with_expected_keys(self):
        """Test that function returns dict with all truncation keys."""
        from scrappy.context.config_loader import get_truncation_defaults

        result = get_truncation_defaults()

        assert isinstance(result, dict)
        assert 'research_large' in result
        assert 'error_message' in result
        assert 'priority_file' in result

    @pytest.mark.unit
    def test_values_are_positive_integers(self):
        """Test that all truncation values are positive integers."""
        from scrappy.context.config_loader import get_truncation_defaults

        result = get_truncation_defaults()

        for key, value in result.items():
            assert isinstance(value, int), f"{key} should be int"
            assert value > 0, f"{key} should be positive"


    @pytest.mark.unit
    def test_fallback_values_when_import_fails(self):
        """Test that fallback values are used when config imports fail."""
        from scrappy.context import config_loader

        # Mock to simulate import failure
        with patch.dict('sys.modules', {'scrappy.cli.config.defaults': None}):
            # Force reimport
            import importlib
            importlib.reload(config_loader)

            result = config_loader.get_truncation_defaults()

            # Should return valid fallback values
            assert result['research_large'] == 1500
            assert result['error_message'] == 500
            assert result['priority_file'] == 3000

        # Reload to restore normal behavior
        importlib.reload(config_loader)


class TestGetExtensionsConfig:
    """Tests for get_extensions_config function."""

    @pytest.mark.unit
    def test_returns_tuple_with_two_elements(self):
        """Test that function returns tuple of (extensions_dict, entry_points)."""
        from scrappy.context.config_loader import get_extensions_config

        result = get_extensions_config()

        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.unit
    def test_extensions_dict_has_expected_categories(self):
        """Test that extensions dict has standard categories."""
        from scrappy.context.config_loader import get_extensions_config

        extensions, _ = get_extensions_config()

        assert isinstance(extensions, dict)
        assert 'python' in extensions
        assert 'javascript' in extensions
        assert 'web' in extensions
        assert 'config' in extensions
        assert 'docs' in extensions

    @pytest.mark.unit
    def test_entry_points_is_list_of_strings(self):
        """Test that entry points is a list of filenames."""
        from scrappy.context.config_loader import get_extensions_config

        _, entry_points = get_extensions_config()

        assert isinstance(entry_points, list)
        assert len(entry_points) > 0
        assert all(isinstance(f, str) for f in entry_points)





class TestGetPathsConfig:
    """Tests for get_paths_config function."""


    @pytest.mark.unit
    def test_includes_venv_dirs(self):
        """Test that result includes virtual environment directories."""
        from scrappy.context.config_loader import get_paths_config

        result = get_paths_config()

        # At least one venv pattern should be present
        venv_dirs = {'.venv', 'venv', 'env'}
        assert any(d in result for d in venv_dirs)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_multiple_calls_return_same_values(self):
        """Test that repeated calls return consistent values."""
        from scrappy.context.config_loader import (
            get_truncation_defaults,
            get_extensions_config,
            get_paths_config,
        )

        # Call multiple times
        defaults1 = get_truncation_defaults()
        defaults2 = get_truncation_defaults()

        ext1, entry1 = get_extensions_config()
        ext2, entry2 = get_extensions_config()

        paths1 = get_paths_config()
        paths2 = get_paths_config()

        # Should be equal
        assert defaults1 == defaults2
        assert ext1 == ext2
        assert entry1 == entry2
        assert paths1 == paths2

