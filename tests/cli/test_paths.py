"""
Tests for CLI paths configuration module.

TDD: Tests written first for the paths.py module which centralizes
skip directories, session files, and path-related constants used
throughout the CLI.
"""


class TestSkipDirectories:
    """Tests for directories to skip during scanning."""


    def test_skip_dirs_contains_git(self):
        """SKIP_DIRS should contain .git."""
        from scrappy.cli.config.paths import SKIP_DIRS
        assert '.git' in SKIP_DIRS

    def test_skip_dirs_contains_pycache(self):
        """SKIP_DIRS should contain __pycache__."""
        from scrappy.cli.config.paths import SKIP_DIRS
        assert '__pycache__' in SKIP_DIRS

    def test_skip_dirs_contains_node_modules(self):
        """SKIP_DIRS should contain node_modules."""
        from scrappy.cli.config.paths import SKIP_DIRS
        assert 'node_modules' in SKIP_DIRS

    def test_skip_dirs_contains_venv_variants(self):
        """SKIP_DIRS should contain virtual environment directories."""
        from scrappy.cli.config.paths import SKIP_DIRS
        venv_dirs = {'.venv', 'venv', 'env', '.env'}
        for vdir in venv_dirs:
            assert vdir in SKIP_DIRS, f"Missing {vdir}"

    def test_skip_dirs_contains_build_dirs(self):
        """SKIP_DIRS should contain build output directories."""
        from scrappy.cli.config.paths import SKIP_DIRS
        build_dirs = {'dist', 'build'}
        for bdir in build_dirs:
            assert bdir in SKIP_DIRS, f"Missing {bdir}"


class TestSkipDirsMinimal:
    """Tests for minimal skip directories set."""


    def test_skip_dirs_minimal_contains_essentials(self):
        """SKIP_DIRS_MINIMAL should contain the most critical dirs to skip."""
        from scrappy.cli.config.paths import SKIP_DIRS_MINIMAL
        essentials = {'__pycache__', 'node_modules', 'venv', '.venv'}
        for dir in essentials:
            assert dir in SKIP_DIRS_MINIMAL, f"Missing {dir}"

    def test_skip_dirs_minimal_subset_of_full(self):
        """SKIP_DIRS_MINIMAL should be a subset of SKIP_DIRS."""
        from scrappy.cli.config.paths import SKIP_DIRS, SKIP_DIRS_MINIMAL
        for dir in SKIP_DIRS_MINIMAL:
            assert dir in SKIP_DIRS, f"{dir} in minimal but not in full"


class TestSessionFiles:
    """Tests for session and tracking file names."""


    def test_session_file_value(self):
        """SESSION_FILE should be .scrappy/session.json."""
        from scrappy.cli.config.paths import SESSION_FILE
        assert SESSION_FILE == '.scrappy/session.json'


class TestProjectIndicatorFiles:
    """Tests for files that indicate project root or structure."""


    def test_project_indicators_python(self):
        """PROJECT_INDICATORS should contain Python project indicators."""
        from scrappy.cli.config.paths import PROJECT_INDICATORS
        python_indicators = {'requirements.txt', 'pyproject.toml', 'setup.py'}
        for indicator in python_indicators:
            assert indicator in PROJECT_INDICATORS, f"Missing {indicator}"

    def test_project_indicators_javascript(self):
        """PROJECT_INDICATORS should contain JavaScript project indicator."""
        from scrappy.cli.config.paths import PROJECT_INDICATORS
        assert 'package.json' in PROJECT_INDICATORS

    def test_project_indicators_git(self):
        """PROJECT_INDICATORS should contain .git."""
        from scrappy.cli.config.paths import PROJECT_INDICATORS
        assert '.git' in PROJECT_INDICATORS


class TestHelperFunctions:
    """Tests for helper functions in paths module."""









class TestSkipDirsProperties:
    """Tests for properties of skip directories."""

    def test_skip_dirs_no_duplicates(self):
        """SKIP_DIRS should not contain duplicates."""
        from scrappy.cli.config.paths import SKIP_DIRS
        # Convert to list to check for duplicates
        skip_list = list(SKIP_DIRS)
        assert len(skip_list) == len(set(skip_list)), "SKIP_DIRS contains duplicates"


    def test_skip_dirs_no_slashes(self):
        """Skip directory names should not contain slashes."""
        from scrappy.cli.config.paths import SKIP_DIRS
        for dir_name in SKIP_DIRS:
            assert '/' not in dir_name, f"Entry {dir_name} contains /"
            assert '\\' not in dir_name, f"Entry {dir_name} contains \\"


class TestCacheDirectories:
    """Tests for cache directory patterns."""


    def test_cache_dirs_contains_common_caches(self):
        """CACHE_DIRS should contain common cache directories."""
        from scrappy.cli.config.paths import CACHE_DIRS
        common_caches = {'__pycache__', '.cache', '.pytest_cache'}
        for cache in common_caches:
            assert cache in CACHE_DIRS, f"Missing {cache}"


class TestTestDirectoryPatterns:
    """Tests for test directory patterns."""


    def test_test_dirs_contains_common_patterns(self):
        """TEST_DIRS should contain common test directory names."""
        from scrappy.cli.config.paths import TEST_DIRS
        common_tests = {'tests', 'test', '__tests__', 'spec'}
        for test_dir in common_tests:
            assert test_dir in TEST_DIRS, f"Missing {test_dir}"


class TestBuildOutputDirectories:
    """Tests for build output directory patterns."""


    def test_build_dirs_contains_common_patterns(self):
        """BUILD_DIRS should contain common build output directories."""
        from scrappy.cli.config.paths import BUILD_DIRS
        common_builds = {'dist', 'build', 'out', 'target'}
        for build_dir in common_builds:
            assert build_dir in BUILD_DIRS, f"Missing {build_dir}"


class TestVendorDirectories:
    """Tests for vendor/dependency directory patterns."""


    def test_vendor_dirs_contains_common_patterns(self):
        """VENDOR_DIRS should contain common vendor directories."""
        from scrappy.cli.config.paths import VENDOR_DIRS
        common_vendors = {'node_modules', 'vendor', 'third_party'}
        for vendor_dir in common_vendors:
            assert vendor_dir in VENDOR_DIRS, f"Missing {vendor_dir}"


class TestVirtualEnvDirectories:
    """Tests for virtual environment directory patterns."""


    def test_venv_dirs_contains_common_patterns(self):
        """VENV_DIRS should contain common virtual env directory names."""
        from scrappy.cli.config.paths import VENV_DIRS
        common_venvs = {'.venv', 'venv', 'env', '.env'}
        for venv_dir in common_venvs:
            assert venv_dir in VENV_DIRS, f"Missing {venv_dir}"


class TestAllHiddenDirectories:
    """Tests for combined hidden directories."""


    def test_all_hidden_dirs_contains_dot_dirs(self):
        """ALL_HIDDEN_DIRS should contain directories starting with dot."""
        from scrappy.cli.config.paths import ALL_HIDDEN_DIRS
        dot_dirs = {'.git', '.venv', '.env', '.cache'}
        for dot_dir in dot_dirs:
            assert dot_dir in ALL_HIDDEN_DIRS, f"Missing {dot_dir}"


class TestPathsEdgeCases:
    """Tests for edge cases in paths module."""
  # Implementation will define this

        # Implementation should decide on case sensitivity


class TestPathsDocumentation:
    """Tests to verify paths have proper documentation."""


    def test_all_skip_dirs_documented(self):
        """Each skip directory should have documentation."""
        from scrappy.cli.config.paths import SKIP_DIRS, SKIP_DIRS_DESCRIPTIONS
        for dir_name in SKIP_DIRS:
            assert dir_name in SKIP_DIRS_DESCRIPTIONS, (
                f"Directory {dir_name} should be documented"
            )
