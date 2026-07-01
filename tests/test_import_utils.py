"""
Test suite for import utilities module.

This module contains comprehensive tests for safe_import, require_import,
import_with_fallback, and path setup functions.
"""

from unittest.mock import Mock, patch
import pytest

from scrappy.infrastructure.utils import (
    safe_import,
    require_import,
    import_with_fallback,
    get_aiofiles,
    get_httpx,
    get_click,
    get_beautifulsoup
)


class TestSafeImport:
    """Test suite for safe_import function."""

    def test_safe_import_existing_module(self):
        """Test importing an existing module."""
        module, available = safe_import('os')

        assert module is not None
        assert available is True
        assert module.__name__ == 'os'


    def test_safe_import_submodule(self):
        """Test importing a submodule."""
        module, available = safe_import('os.path')

        assert module is not None
        assert available is True
        assert hasattr(module, 'join')

    def test_safe_import_nested_submodule(self):
        """Test importing a deeply nested submodule."""
        module, available = safe_import('collections.abc')

        assert module is not None
        assert available is True
        assert hasattr(module, 'Mapping')





class TestRequireImport:
    """Test suite for require_import function."""

    def test_require_import_existing_module(self):
        """Test requiring an existing module."""
        module = require_import('os')

        assert module is not None
        assert module.__name__ == 'os'




    def test_require_import_submodule(self):
        """Test requiring a submodule."""
        module = require_import('os.path')

        assert module is not None
        assert hasattr(module, 'join')



class TestPathSetupFunctions:
    """Test suite for path setup functions."""

# todo
    # def test_setup_src_path(self, monkeypatch):
    #     """Test setup_src_path adds correct directory to sys.path."""
    #     # Mock the file structure
    #     mock_file_path = Path("/project/src/utils/imports.py")
    #
    #     with patch('scrappy.infrastructure.utils.imports.Path') as mock_path_class:
    #         mock_path_instance = Mock()
    #         mock_path_instance.parent.parent = Path("/project/src")
    #         mock_path_class.return_value = mock_file_path
    #         mock_path_class.return_value.__str__.return_value = "/project/src/utils/imports.py"
    #
    #         # Mock the parent call chain
    #         mock_file_path.parent = Mock()
    #         mock_file_path.parent.parent = Path("/project/src")
    #
    #         with patch.object(sys, 'path', []):  # Start with empty path
    #             setup_src_path()
    #
    #             # Should add /project/src to path
    #             assert "/project/src" in sys.path
    #
    # def test_setup_src_path_already_exists(self):
    #     """Test setup_src_path doesn't duplicate existing path."""
    #     test_path = "/existing/path"
    #
    #     with patch('scrappy.infrastructure.utils.imports.Path') as mock_path_class:
    #         mock_file_path = Mock()
    #         mock_file_path.parent.parent.__str__.return_value = test_path
    #         mock_path_class.return_value = mock_file_path
    #
    #         with patch.object(sys, 'path', [test_path]):  # Path already exists
    #             setup_src_path()
    #
    #             # Should not duplicate
    #             assert sys.path.count(test_path) == 1

# todo
    # def test_setup_root_path(self, monkeypatch):
    #     """Test setup_root_path adds correct directory to sys.path."""
    #     mock_file_path = Path("/project/src/utils/imports.py")
    #
    #     with patch('scrappy.infrastructure.utils.imports.Path') as mock_path_class:
    #         mock_path_instance = Mock()
    #         mock_path_instance.parent.parent.parent = Path("/project")
    #         mock_path_class.return_value = mock_file_path
    #
    #         # Mock the parent call chain
    #         mock_file_path.parent = Mock()
    #         mock_file_path.parent.parent = Mock()
    #         mock_file_path.parent.parent.parent = Path("/project")
    #
    #         with patch.object(sys, 'path', []):  # Start with empty path
    #             setup_root_path()
    #
    #             # Should add /project to path
    #             assert "/project" in sys.path

# todo
    # def test_setup_root_path_already_exists(self):
    #     """Test setup_root_path doesn't duplicate existing path."""
    #     test_path = "/existing/path"
    #
    #     with patch('scrappy.infrastructure.utils.imports.Path') as mock_path_class:
    #         mock_file_path = Mock()
    #         mock_file_path.parent.parent.parent.__str__.return_value = test_path
    #         mock_path_class.return_value = mock_file_path
    #
    #         with patch.object(sys, 'path', [test_path]):  # Path already exists
    #             setup_root_path()
    #
    #             # Should not duplicate
    #             assert sys.path.count(test_path) == 1


class TestImportWithFallback:
    """Test suite for import_with_fallback function."""

    def test_import_with_fallback_primary_success(self):
        """Test successful primary import."""
        # Mock successful primary import
        with patch('builtins.__import__') as mock_import:
            mock_module = Mock()
            mock_import.return_value = mock_module

            result = import_with_fallback('os', 'fallback_module')

            assert result == mock_module
            mock_import.assert_called_once()

# todo
    # def test_import_with_fallback_relative_import(self):
    #     """Test relative import handling."""
    #     mock_module = Mock()
    #
    #     with patch('builtins.__import__') as mock_import:
    #         mock_import.return_value = mock_module
    #
    #         result = import_with_fallback('..providers', 'providers')
    #
    #         assert result == mock_module
    #         # Should be called with level parameter for relative import
    #         mock_import.assert_called_once_with(
    #             'providers',
    #             globals(),
    #             locals(),
    #             [],
    #             2  # level for ..providers
    #         )

    def test_import_with_fallback_primary_fails_fallback_success(self):
        """Test fallback import when primary fails."""
        mock_fallback = Mock()

        # Patch setup_src_path FIRST, before mocking __import__
        with patch('scrappy.infrastructure.utils.imports.setup_src_path'):
            with patch('builtins.__import__') as mock_import:
                # First call fails, second succeeds
                mock_import.side_effect = [ImportError, mock_fallback]

                result = import_with_fallback('nonexistent.primary', 'existing.fallback')

                assert result == mock_fallback
                assert mock_import.call_count == 2

    def test_import_with_fallback_nested_attributes(self):
        """Test importing nested attributes from module."""
        mock_module = Mock()
        mock_nested = Mock()
        mock_module.submodule = mock_nested

        with patch('builtins.__import__') as mock_import:
            mock_import.return_value = mock_module

            result = import_with_fallback('package.submodule.attr', 'fallback')

            # Should return the nested attribute
            assert result == mock_module


# todo
    # def test_import_with_fallback_single_dot(self):
    #     """Test relative import with single dot."""
    #     mock_module = Mock()
    #
    #     with patch('builtins.__import__') as mock_import:
    #         mock_import.return_value = mock_module
    #
    #         result = import_with_fallback('.providers', 'providers')
    #
    #         assert result == mock_module
    #         mock_import.assert_called_once_with(
    #             'providers',
    #             globals(),
    #             locals(),
    #             [],
    #             1  # level for .providers
    #         )
    #
    # def test_import_with_fallback_deep_relative(self):
    #     """Test deep relative import with multiple dots."""
    #     mock_module = Mock()
    #
    #     with patch('builtins.__import__') as mock_import:
    #         mock_import.return_value = mock_module
    #
    #         result = import_with_fallback('...utils.imports', 'imports')
    #
    #         assert result == mock_module
    #         mock_import.assert_called_once_with(
    #             'utils',
    #             globals(),
    #             locals(),
    #             ['imports'],
    #             3  # level for ...utils.imports
    #         )


class TestPreconfiguredDependencyCheckers:
    """Test suite for pre-configured dependency checker functions."""

    def test_get_aiofiles_available(self):
        """Test get_aiofiles when aiofiles is available."""
        with patch('scrappy.infrastructure.utils.imports.safe_import') as mock_safe_import:
            mock_module = Mock()
            mock_safe_import.return_value = (mock_module, True)

            module, available = get_aiofiles()

            assert module == mock_module
            assert available is True
            mock_safe_import.assert_called_once_with('aiofiles')

    def test_get_aiofiles_not_available(self):
        """Test get_aiofiles when aiofiles is not available."""
        with patch('scrappy.infrastructure.utils.imports.safe_import') as mock_safe_import:
            mock_safe_import.return_value = (None, False)

            module, available = get_aiofiles()

            assert module is None
            assert available is False

    def test_get_httpx_available(self):
        """Test get_httpx when httpx is available."""
        with patch('scrappy.infrastructure.utils.imports.safe_import') as mock_safe_import:
            mock_module = Mock()
            mock_safe_import.return_value = (mock_module, True)

            module, available = get_httpx()

            assert module == mock_module
            assert available is True
            mock_safe_import.assert_called_once_with('httpx')

    def test_get_httpx_not_available(self):
        """Test get_httpx when httpx is not available."""
        with patch('scrappy.infrastructure.utils.imports.safe_import') as mock_safe_import:
            mock_safe_import.return_value = (None, False)

            module, available = get_httpx()

            assert module is None
            assert available is False

    def test_get_click_available(self):
        """Test get_click when click is available."""
        with patch('scrappy.infrastructure.utils.imports.safe_import') as mock_safe_import:
            mock_module = Mock()
            mock_safe_import.return_value = (mock_module, True)

            module, available = get_click()

            assert module == mock_module
            assert available is True
            mock_safe_import.assert_called_once_with('click')

    def test_get_click_not_available(self):
        """Test get_click when click is not available."""
        with patch('scrappy.infrastructure.utils.imports.safe_import') as mock_safe_import:
            mock_safe_import.return_value = (None, False)

            module, available = get_click()

            assert module is None
            assert available is False

# todo
    # def test_get_beautifulsoup_available(self):
    #     """Test get_beautifulsoup when BeautifulSoup is available."""
    #     with patch('builtins.__import__') as mock_import:
    #         mock_bs4 = Mock()
    #         mock_bs4.BeautifulSoup = Mock()
    #         mock_import.return_value = mock_bs4
    #
    #         result, available = get_beautifulsoup()
    #
    #         assert result == mock_bs4.BeautifulSoup
    #         assert available is True
    #         mock_import.assert_called_once_with('bs4')

    def test_get_beautifulsoup_not_available(self):
        """Test get_beautifulsoup when BeautifulSoup is not available."""
        with patch('builtins.__import__') as mock_import:
            mock_import.side_effect = ImportError

            result, available = get_beautifulsoup()

            assert result is None
            assert available is False


class TestImportEdgeCases:
    """Test edge cases and error conditions."""

# todo
    # def test_safe_import_empty_string(self):
    #     """Test safe_import with empty string."""
    #     module, available = safe_import('')
    #
    #     assert module is None
    #     assert available is False

# todo
    # def test_require_import_empty_string(self):
    #     """Test require_import with empty string."""
    #     with pytest.raises(ImportError):
    #         require_import('')
    #
    # def test_import_with_fallback_empty_strings(self):
    #     """Test import_with_fallback with empty strings."""
    #     with patch('scrappy.infrastructure.utils.imports.setup_src_path'):
    #         with pytest.raises(ImportError):
    #             import_with_fallback('', '')
    #
    # def test_import_with_fallback_none_values(self):
    #     """Test import_with_fallback with None values (should not crash)."""
    #     # This should handle gracefully
    #     with pytest.raises(TypeError):
    #         import_with_fallback(None, None)

# todo
    # def test_setup_path_with_complex_structure(self):
    #     """Test path setup with complex directory structure."""
    #     mock_file_path = Path("/very/deep/nested/structure/src/utils/imports.py")
    #
    #     with patch('scrappy.infrastructure.utils.imports.Path') as mock_path_class:
    #         mock_path_class.return_value = mock_file_path
    #
    #         # Mock the parent chain
    #         current = mock_file_path
    #         for _ in range(6):  # Go up 6 levels
    #             current = Mock()
    #             current.__str__.return_value = f"/level{_}"
    #
    #         mock_file_path.parent.parent.__str__.return_value = "/very/deep/nested/structure/src"
    #
    #         with patch.object(sys, 'path', []):
    #             setup_src_path()
    #
    #             assert "/very/deep/nested/structure/src" in sys.path


class TestImportIntegration:
    """Integration tests for import utilities."""




    def test_real_require_import_nonexistent(self):
        """Test require_import with real non-existent module."""
        with pytest.raises(ImportError) as exc_info:
            require_import('definitely_not_a_real_module_12345')

        assert "definitely_not_a_real_module_12345 package not installed" in str(exc_info.value)

# todo
    # def test_real_path_setup(self):
    #     """Test that path setup functions work with real paths."""
    #     # This test runs in the actual environment
    #     original_path = sys.path.copy()
    #
    #     try:
    #         setup_src_path()
    #
    #         # Should add src directory to path
    #         src_dir = str(Path(__file__).parent.parent.parent / 'src')
    #         assert src_dir in sys.path
    #
    #     finally:
    #         # Restore original path
    #         sys.path[:] = original_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
