"""
Tests for FileScanner - file discovery and categorization.
"""
import pytest
from pathlib import Path

from scrappy.context.file_scanner import FileScanner


class TestFileScannerBasics:
    """Basic file scanning functionality."""

    @pytest.mark.unit
    def test_scan_empty_directory(self, tmp_path):
        """Scanning empty directory returns empty categories."""
        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        # Should have category keys but empty lists
        assert all(isinstance(v, list) for v in result.values())
        assert sum(len(v) for v in result.values()) == 0


class TestFileCategorization:
    """Tests for categorizing files by extension."""

    @pytest.fixture
    def project_with_files(self, tmp_path):
        """Create a project with various file types."""
        # Python files
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        # JavaScript files
        (tmp_path / "app.js").write_text("console.log('hi')")
        (tmp_path / "component.tsx").write_text("export const App = () => {}")

        # Config files
        (tmp_path / "config.json").write_text("{}")
        (tmp_path / "settings.yaml").write_text("key: value")

        # Docs
        (tmp_path / "README.md").write_text("# Project")

        return tmp_path

    @pytest.mark.unit
    def test_categorizes_python_files(self, project_with_files):
        """Python files are categorized correctly."""
        scanner = FileScanner()
        result = scanner.scan_files(project_with_files)

        python_files = result.get('python', [])
        assert len(python_files) == 2
        assert any('main.py' in f for f in python_files)
        assert any('utils.py' in f for f in python_files)

    @pytest.mark.unit
    def test_categorizes_javascript_files(self, project_with_files):
        """JavaScript/TypeScript files are categorized correctly."""
        scanner = FileScanner()
        result = scanner.scan_files(project_with_files)

        js_files = result.get('javascript', [])
        assert len(js_files) == 2
        assert any('app.js' in f for f in js_files)
        assert any('component.tsx' in f for f in js_files)

    @pytest.mark.unit
    def test_categorizes_config_files(self, project_with_files):
        """Config files are categorized correctly."""
        scanner = FileScanner()
        result = scanner.scan_files(project_with_files)

        config_files = result.get('config', [])
        assert len(config_files) == 2
        assert any('config.json' in f for f in config_files)
        assert any('settings.yaml' in f for f in config_files)

    @pytest.mark.unit
    def test_categorizes_docs_files(self, project_with_files):
        """Documentation files are categorized correctly."""
        scanner = FileScanner()
        result = scanner.scan_files(project_with_files)

        docs_files = result.get('docs', [])
        assert len(docs_files) == 1
        assert any('README.md' in f for f in docs_files)

    @pytest.mark.unit
    def test_uncategorized_files_go_to_other(self, tmp_path):
        """Files with unknown extensions go to 'other' category."""
        (tmp_path / "data.xyz").write_text("unknown format")
        (tmp_path / "binary.bin").write_text("binary data")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        other_files = result.get('other', [])
        assert len(other_files) == 2


class TestDirectoryHandling:
    """Tests for directory traversal and filtering."""

    @pytest.mark.unit
    def test_scans_nested_directories(self, tmp_path):
        """Scanner finds files in nested directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "utils").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "src" / "utils" / "helpers.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert len(python_files) == 2
        # Should include relative paths
        assert any('src' in f and 'main.py' in f for f in python_files)
        assert any('utils' in f and 'helpers.py' in f for f in python_files)

    @pytest.mark.unit
    def test_skips_hidden_directories(self, tmp_path):
        """Scanner skips directories starting with dot."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "secret.py").write_text("")
        (tmp_path / "visible.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert len(python_files) == 1
        assert not any('.hidden' in f for f in python_files)

    @pytest.mark.unit
    def test_skips_hidden_files(self, tmp_path):
        """Scanner skips files starting with dot."""
        (tmp_path / ".hidden.py").write_text("")
        (tmp_path / "visible.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert len(python_files) == 1
        assert not any('.hidden' in f for f in python_files)

    @pytest.mark.unit
    def test_skips_pycache_directory(self, tmp_path):
        """Scanner skips __pycache__ directories."""
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "module.cpython-39.pyc").write_text("")
        (tmp_path / "module.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        # Should only find the .py file, not the .pyc
        all_files = [f for files in result.values() for f in files]
        assert len(all_files) == 1
        assert not any('__pycache__' in f for f in all_files)

    @pytest.mark.unit
    def test_skips_node_modules(self, tmp_path):
        """Scanner skips node_modules directories."""
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package").mkdir()
        (tmp_path / "node_modules" / "package" / "index.js").write_text("")
        (tmp_path / "app.js").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        js_files = result.get('javascript', [])
        assert len(js_files) == 1
        assert not any('node_modules' in f for f in js_files)

    @pytest.mark.unit
    def test_skips_venv_directory(self, tmp_path):
        """Scanner skips virtual environment directories."""
        for venv_name in ['venv', '.venv', 'env']:
            venv_dir = tmp_path / venv_name
            venv_dir.mkdir()
            (venv_dir / "lib").mkdir()
            (venv_dir / "lib" / "site.py").write_text("")

        (tmp_path / "main.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert len(python_files) == 1
        assert all('venv' not in f and 'env' not in f for f in python_files)

    @pytest.mark.unit
    def test_skips_git_directory(self, tmp_path):
        """Scanner skips .git directories."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("")
        (tmp_path / "main.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        all_files = [f for files in result.values() for f in files]
        assert not any('.git' in f for f in all_files)

    @pytest.mark.unit
    def test_skips_build_directories(self, tmp_path):
        """Scanner skips dist and build directories."""
        for dir_name in ['dist', 'build']:
            build_dir = tmp_path / dir_name
            build_dir.mkdir()
            (build_dir / "output.js").write_text("")

        (tmp_path / "scrappy.js").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        js_files = result.get('javascript', [])
        assert len(js_files) == 1


class TestCustomConfiguration:
    """Tests for custom extension and skip directory configuration."""

    @pytest.mark.unit
    def test_accepts_custom_extensions(self, tmp_path):
        """Scanner can use custom extension categories."""
        (tmp_path / "file.custom").write_text("")

        custom_extensions = {
            'custom': ['.custom'],
            'other': []
        }

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path, extensions_by_category=custom_extensions)

        assert 'custom' in result
        assert len(result['custom']) == 1

    @pytest.mark.unit
    def test_accepts_custom_skip_dirs(self, tmp_path):
        """Scanner can use custom skip directories."""
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "lib.py").write_text("")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")

        custom_skip = {'vendor'}

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path, skip_dirs=custom_skip)

        python_files = result.get('python', [])
        assert len(python_files) == 1
        assert not any('vendor' in f for f in python_files)


class TestPathHandling:
    """Tests for file path handling."""

    @pytest.mark.unit
    def test_returns_relative_paths(self, tmp_path):
        """Scanner returns paths relative to project root."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        # Should be relative path like "src/main.py" or "src\\main.py"
        assert len(python_files) == 1
        file_path = python_files[0]
        assert not file_path.startswith(str(tmp_path))
        assert 'src' in file_path
        assert 'main.py' in file_path

    @pytest.mark.unit
    def test_root_files_have_simple_names(self, tmp_path):
        """Files in root directory have just their filename."""
        (tmp_path / "main.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert python_files == ['main.py']

    @pytest.mark.unit
    def test_handles_path_object_input(self, tmp_path):
        """Scanner accepts Path objects."""
        (tmp_path / "file.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(Path(tmp_path))

        assert len(result.get('python', [])) == 1

    @pytest.mark.unit
    def test_handles_string_path_input(self, tmp_path):
        """Scanner accepts string paths."""
        (tmp_path / "file.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(str(tmp_path))

        assert len(result.get('python', [])) == 1


class TestEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.unit
    def test_handles_nonexistent_path(self, tmp_path):
        """Scanner handles nonexistent paths gracefully."""
        nonexistent = tmp_path / "does_not_exist"

        scanner = FileScanner()
        result = scanner.scan_files(nonexistent)

        # Should return empty categories, not raise
        assert isinstance(result, dict)
        assert sum(len(v) for v in result.values()) == 0

    @pytest.mark.unit
    def test_handles_deeply_nested_structure(self, tmp_path):
        """Scanner handles deeply nested directories."""
        deep_path = tmp_path
        for i in range(10):
            deep_path = deep_path / f"level{i}"
            deep_path.mkdir()

        (deep_path / "deep.py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert len(python_files) == 1
        assert 'deep.py' in python_files[0]

    @pytest.mark.unit
    def test_handles_files_without_extension(self, tmp_path):
        """Scanner handles files without extensions."""
        (tmp_path / "Makefile").write_text("")
        (tmp_path / "Dockerfile").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        # Should go to 'other' category
        other_files = result.get('other', [])
        assert len(other_files) == 2

    @pytest.mark.unit
    def test_case_insensitive_extensions(self, tmp_path):
        """Scanner handles different case extensions."""
        (tmp_path / "lower.py").write_text("")
        (tmp_path / "upper.PY").write_text("")
        (tmp_path / "mixed.Py").write_text("")

        scanner = FileScanner()
        result = scanner.scan_files(tmp_path)

        python_files = result.get('python', [])
        assert len(python_files) == 3