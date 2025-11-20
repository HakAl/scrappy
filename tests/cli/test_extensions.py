"""
Tests for CLI extensions configuration module.

TDD: Tests written first for the extensions.py module which centralizes
file extension categories and file type patterns used throughout the CLI.
"""

import pytest


class TestLanguageExtensions:
    """Tests for programming language file extensions."""


    def test_python_extensions_contains_py(self):
        """PYTHON_EXTENSIONS should contain .py."""
        from src.cli.config.extensions import PYTHON_EXTENSIONS
        assert '.py' in PYTHON_EXTENSIONS


    def test_javascript_extensions_values(self):
        """JAVASCRIPT_EXTENSIONS should contain js, jsx, ts, tsx."""
        from src.cli.config.extensions import JAVASCRIPT_EXTENSIONS
        expected = {'.js', '.jsx', '.ts', '.tsx'}
        for ext in expected:
            assert ext in JAVASCRIPT_EXTENSIONS, f"Missing {ext}"


    def test_web_extensions_values(self):
        """WEB_EXTENSIONS should contain html, css, scss."""
        from src.cli.config.extensions import WEB_EXTENSIONS
        expected = {'.html', '.css', '.scss'}
        for ext in expected:
            assert ext in WEB_EXTENSIONS, f"Missing {ext}"


class TestConfigExtensions:
    """Tests for configuration file extensions."""


    def test_config_extensions_values(self):
        """CONFIG_EXTENSIONS should contain common config formats."""
        from src.cli.config.extensions import CONFIG_EXTENSIONS
        expected = {'.json', '.yaml', '.yml', '.toml', '.ini'}
        for ext in expected:
            assert ext in CONFIG_EXTENSIONS, f"Missing {ext}"


class TestDocExtensions:
    """Tests for documentation file extensions."""


    def test_docs_extensions_values(self):
        """DOCS_EXTENSIONS should contain md, rst, txt."""
        from src.cli.config.extensions import DOCS_EXTENSIONS
        expected = {'.md', '.rst', '.txt'}
        for ext in expected:
            assert ext in DOCS_EXTENSIONS, f"Missing {ext}"


class TestExtensionsCategoryMapping:
    """Tests for the complete extensions category mapping."""


    def test_extensions_by_category_keys(self):
        """EXTENSIONS_BY_CATEGORY should have all category keys."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        expected_keys = {'python', 'javascript', 'web', 'config', 'docs', 'other'}
        for key in expected_keys:
            assert key in EXTENSIONS_BY_CATEGORY, f"Missing category: {key}"

    def test_python_category_value(self):
        """Python category should contain .py."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        assert '.py' in EXTENSIONS_BY_CATEGORY['python']

    def test_javascript_category_values(self):
        """JavaScript category should contain expected extensions."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        expected = {'.js', '.jsx', '.ts', '.tsx'}
        for ext in expected:
            assert ext in EXTENSIONS_BY_CATEGORY['javascript'], f"Missing {ext}"

    def test_config_category_values(self):
        """Config category should contain expected extensions."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        expected = {'.json', '.yaml', '.yml', '.toml', '.ini'}
        for ext in expected:
            assert ext in EXTENSIONS_BY_CATEGORY['config'], f"Missing {ext}"

    def test_other_category_empty(self):
        """Other category should be an empty list."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        assert EXTENSIONS_BY_CATEGORY['other'] == []


class TestEntryPointFiles:
    """Tests for entry point file names."""


    def test_entry_point_files_values(self):
        """ENTRY_POINT_FILES should contain common entry points."""
        from src.cli.config.extensions import ENTRY_POINT_FILES
        expected = {'main.py', '__main__.py', 'app.py', 'cli.py', 'setup.py'}
        for file in expected:
            assert file in ENTRY_POINT_FILES, f"Missing {file}"


class TestPriorityFiles:
    """Tests for priority file names."""


    def test_priority_files_contains_readme(self):
        """PRIORITY_FILES should contain README variants."""
        from src.cli.config.extensions import PRIORITY_FILES
        readme_variants = {'README.md', 'README', 'README.rst'}
        for readme in readme_variants:
            assert readme in PRIORITY_FILES, f"Missing {readme}"

    def test_priority_files_contains_package_configs(self):
        """PRIORITY_FILES should contain package configuration files."""
        from src.cli.config.extensions import PRIORITY_FILES
        package_configs = {
            'setup.py', 'pyproject.toml', 'package.json',
            'requirements.txt', 'Cargo.toml', 'go.mod'
        }
        for config in package_configs:
            assert config in PRIORITY_FILES, f"Missing {config}"


class TestDependencyFiles:
    """Tests for dependency file names."""


    def test_dependency_files_python(self):
        """DEPENDENCY_FILES should contain Python dependency files."""
        from src.cli.config.extensions import DEPENDENCY_FILES
        python_deps = {'requirements.txt', 'setup.py', 'pyproject.toml'}
        for dep in python_deps:
            assert dep in DEPENDENCY_FILES, f"Missing {dep}"

    def test_dependency_files_javascript(self):
        """DEPENDENCY_FILES should contain JavaScript dependency file."""
        from src.cli.config.extensions import DEPENDENCY_FILES
        assert 'package.json' in DEPENDENCY_FILES

    def test_dependency_files_other_languages(self):
        """DEPENDENCY_FILES should contain other language dependency files."""
        from src.cli.config.extensions import DEPENDENCY_FILES
        other_deps = {'Cargo.toml', 'go.mod'}
        for dep in other_deps:
            assert dep in DEPENDENCY_FILES, f"Missing {dep}"


class TestConfigurationFiles:
    """Tests for configuration file names."""


    def test_configuration_files_values(self):
        """CONFIGURATION_FILES should contain common config file names."""
        from src.cli.config.extensions import CONFIGURATION_FILES
        expected = {
            'config.py', 'settings.py', '.env.example',
            'config.json', 'config.yaml'
        }
        for config in expected:
            assert config in CONFIGURATION_FILES, f"Missing {config}"


class TestAllCodeExtensions:
    """Tests for combined code extensions."""


    def test_all_code_extensions_includes_python(self):
        """ALL_CODE_EXTENSIONS should include Python."""
        from src.cli.config.extensions import ALL_CODE_EXTENSIONS
        assert '.py' in ALL_CODE_EXTENSIONS

    def test_all_code_extensions_includes_javascript(self):
        """ALL_CODE_EXTENSIONS should include JavaScript/TypeScript."""
        from src.cli.config.extensions import ALL_CODE_EXTENSIONS
        for ext in ['.js', '.jsx', '.ts', '.tsx']:
            assert ext in ALL_CODE_EXTENSIONS, f"Missing {ext}"


class TestHelperFunctions:
    """Tests for helper functions in extensions module."""















class TestExtensionsEdgeCases:
    """Tests for edge cases in extensions module."""


    def test_case_sensitivity(self):
        """Extensions should be lowercase for consistency."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        for category, exts in EXTENSIONS_BY_CATEGORY.items():
            for ext in exts:
                assert ext == ext.lower(), f"Extension {ext} should be lowercase"

    def test_extensions_start_with_dot(self):
        """File extensions should start with a dot."""
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY
        for category, exts in EXTENSIONS_BY_CATEGORY.items():
            if category == 'other':
                continue  # other is empty
            for ext in exts:
                assert ext.startswith('.'), f"Extension {ext} should start with dot"

