"""
Tests for SemanticFileCollector and IndexFilterConfig.

Tests cover:
- Path filtering (avoiding substring bug)
- File size limits
- Binary file detection
- Git integration
- Fallback behavior
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.context.semantic.file_collector import (
    IndexFilterConfig,
    SemanticFileCollector,
)


class TestIndexFilterConfig:
    """Test IndexFilterConfig filtering logic."""

    def test_default_ignore_names_includes_common_directories(self):
        """Should include common directories like node_modules, dist, build."""
        config = IndexFilterConfig()

        assert 'node_modules' in config.ignore_names
        assert 'dist' in config.ignore_names
        assert 'build' in config.ignore_names
        assert '__pycache__' in config.ignore_names
        assert '.git' in config.ignore_names
        assert '.scrappy' in config.ignore_names
        assert '.lancedb' in config.ignore_names

    def test_should_skip_by_path_checks_path_parts_not_substrings(self):
        """Should skip 'dist' directory but NOT 'distributed_systems.py'."""
        config = IndexFilterConfig()
        root = Path('/project')

        # Should skip files IN dist directory
        dist_file = Path('/project/dist/bundle.js')
        assert config.should_skip_by_path(dist_file, root) is True

        # Should NOT skip files with 'dist' in name
        distributed = Path('/project/src/distributed_systems.py')
        assert config.should_skip_by_path(distributed, root) is False

        # Should skip files IN build directory
        build_file = Path('/project/build/output.js')
        assert config.should_skip_by_path(build_file, root) is True

        # Should NOT skip files with 'build' in name
        builder = Path('/project/src/builders.py')
        assert config.should_skip_by_path(builder, root) is False

    def test_should_skip_by_path_handles_nested_ignored_directories(self):
        """Should skip files in nested ignored directories."""
        config = IndexFilterConfig()
        root = Path('/project')

        # Nested node_modules
        nested = Path('/project/src/lib/node_modules/package/index.js')
        assert config.should_skip_by_path(nested, root) is True

        # Nested __pycache__
        pycache = Path('/project/src/utils/__pycache__/module.pyc')
        assert config.should_skip_by_path(pycache, root) is True

    def test_should_skip_by_path_skips_paths_outside_root(self):
        """Should skip paths outside project root."""
        config = IndexFilterConfig()
        root = Path('/project')

        outside = Path('/other/path/file.py')
        assert config.should_skip_by_path(outside, root) is True

    def test_should_skip_by_path_checks_file_extensions(self):
        """Should skip files matching extension patterns."""
        config = IndexFilterConfig()
        root = Path('/project')

        # Should skip bytecode
        assert config.should_skip_by_path(Path('/project/module.pyc'), root) is True
        assert config.should_skip_by_path(Path('/project/module.pyo'), root) is True

        # Should skip images
        assert config.should_skip_by_path(Path('/project/logo.png'), root) is True
        assert config.should_skip_by_path(Path('/project/photo.jpg'), root) is True

        # Should skip minified files
        assert config.should_skip_by_path(Path('/project/app.min.js'), root) is True
        assert config.should_skip_by_path(Path('/project/style.min.css'), root) is True

        # Should skip lock files
        assert config.should_skip_by_path(Path('/project/package-lock.json'), root) is True
        assert config.should_skip_by_path(Path('/project/yarn.lock'), root) is True

        # Should NOT skip normal source files
        assert config.should_skip_by_path(Path('/project/main.py'), root) is False
        assert config.should_skip_by_path(Path('/project/app.js'), root) is False

    def test_should_skip_by_size_enforces_max_size(self):
        """Should skip files exceeding max size."""
        config = IndexFilterConfig(max_file_size_bytes=1024)  # 1KB

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Small file - should not skip
            small_file = tmpdir / 'small.txt'
            small_file.write_text('x' * 512)  # 512 bytes
            assert config.should_skip_by_size(small_file) is False

            # Large file - should skip
            large_file = tmpdir / 'large.txt'
            large_file.write_text('x' * 2048)  # 2KB
            assert config.should_skip_by_size(large_file) is True

    def test_should_skip_by_size_handles_missing_files(self):
        """Should skip files that don't exist or can't be stat'd."""
        config = IndexFilterConfig()

        nonexistent = Path('/nonexistent/file.txt')
        assert config.should_skip_by_size(nonexistent) is True

    def test_is_binary_detects_binary_files(self):
        """Should detect binary files by null bytes."""
        config = IndexFilterConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Text file - not binary
            text_file = tmpdir / 'text.txt'
            text_file.write_text('Hello world')
            assert config.is_binary(text_file) is False

            # Binary file - contains null bytes
            binary_file = tmpdir / 'binary.bin'
            binary_file.write_bytes(b'Hello\x00World\x00')
            assert config.is_binary(binary_file) is True

    def test_is_binary_handles_read_errors(self):
        """Should treat unreadable files as binary."""
        config = IndexFilterConfig()

        nonexistent = Path('/nonexistent/file.txt')
        assert config.is_binary(nonexistent) is True


class TestSemanticFileCollector:
    """Test SemanticFileCollector file collection."""

    def test_collect_files_uses_git_when_available(self, tmp_path):
        """Should use git ls-files when in a git repository."""
        # Create a git repo
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)

        # Create some files
        (tmp_path / 'tracked.py').write_text('print("tracked")')
        (tmp_path / 'untracked.py').write_text('print("untracked")')

        # Track only one file
        subprocess.run(['git', 'add', 'tracked.py'], cwd=tmp_path, capture_output=True)

        # Collect files
        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        # Should only get tracked file
        assert 'tracked.py' in files
        assert 'untracked.py' not in files

    def test_collect_files_respects_gitignore(self, tmp_path):
        """Should respect .gitignore when using git ls-files."""
        # Create a git repo
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)

        # Create .gitignore
        (tmp_path / '.gitignore').write_text('ignored.py\n')

        # Create files
        (tmp_path / 'tracked.py').write_text('print("tracked")')
        (tmp_path / 'ignored.py').write_text('print("ignored")')

        # Track files (git respects .gitignore during add)
        subprocess.run(['git', 'add', '.'], cwd=tmp_path, capture_output=True)

        # Collect files
        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        # Should only get tracked file
        assert 'tracked.py' in files
        assert 'ignored.py' not in files

    def test_collect_files_includes_untracked_when_configured(self, tmp_path):
        """Should include untracked files when include_untracked=True."""
        # Create a git repo
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)

        # Create files
        (tmp_path / 'tracked.py').write_text('print("tracked")')
        (tmp_path / 'untracked.py').write_text('print("untracked")')

        # Track only one file
        subprocess.run(['git', 'add', 'tracked.py'], cwd=tmp_path, capture_output=True)

        # Collect with include_untracked
        config = IndexFilterConfig(include_untracked=True)
        collector = SemanticFileCollector(tmp_path, filter_config=config)
        files = collector.collect_files()

        # Should get both files
        assert 'tracked.py' in files
        assert 'untracked.py' in files

    def test_collect_files_falls_back_to_plain_scan_when_not_git_repo(self, tmp_path):
        """Should use plain filesystem scan when not a git repository."""
        # Create files (no git init)
        (tmp_path / 'file1.py').write_text('print("file1")')
        (tmp_path / 'file2.py').write_text('print("file2")')

        # Collect files
        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        # Should get all files
        assert 'file1.py' in files
        assert 'file2.py' in files

    def test_collect_files_skips_large_files(self, tmp_path):
        """Should skip files exceeding size limit."""
        # Create files
        (tmp_path / 'small.py').write_text('x' * 100)
        (tmp_path / 'large.py').write_text('x' * 10000)

        # Collect with small size limit
        config = IndexFilterConfig(max_file_size_bytes=500)
        collector = SemanticFileCollector(tmp_path, filter_config=config)
        files = collector.collect_files()

        # Should only get small file
        assert 'small.py' in files
        assert 'large.py' not in files

    def test_collect_files_skips_binary_files(self, tmp_path):
        """Should skip binary files."""
        # Create files
        (tmp_path / 'text.py').write_text('print("hello")')
        (tmp_path / 'binary.bin').write_bytes(b'Hello\x00World\x00')

        # Collect files
        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        # Should only get text file
        assert 'text.py' in files
        assert 'binary.bin' not in files

    def test_collect_files_skips_ignored_directories(self, tmp_path):
        """Should skip files in ignored directories."""
        # Create directory structure
        (tmp_path / 'src').mkdir()
        (tmp_path / 'node_modules').mkdir()
        (tmp_path / 'dist').mkdir()

        (tmp_path / 'src' / 'main.py').write_text('print("main")')
        (tmp_path / 'node_modules' / 'package.js').write_text('console.log("package")')
        (tmp_path / 'dist' / 'bundle.js').write_text('console.log("bundle")')

        # Collect files
        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        # Should only get src file
        assert 'src/main.py' in files or 'src\\main.py' in files  # Handle Windows paths
        assert not any('node_modules' in f for f in files)
        assert not any('dist' in f for f in files)

    def test_collect_files_returns_empty_dict_when_git_fails_in_git_repo(self, tmp_path):
        """Should return empty dict (not fallback) when git fails in a git repo."""
        # Create a git repo
        (tmp_path / '.git').mkdir()  # Fake git repo
        (tmp_path / 'file.py').write_text('print("file")')

        # Mock git ls-files to fail
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = 'git error'
            mock_run.return_value = mock_result

            collector = SemanticFileCollector(tmp_path)
            files = collector.collect_files()

            # Should return empty (security: don't bypass .gitignore)
            assert len(files) == 0

    def test_collect_files_handles_git_timeout(self, tmp_path):
        """Should handle git ls-files timeout gracefully."""
        # Create a git repo
        (tmp_path / '.git').mkdir()

        # Mock git to timeout
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('git', 30)):
            collector = SemanticFileCollector(tmp_path)
            files = collector.collect_files()

            # Should return empty
            assert len(files) == 0

    def test_collect_files_handles_git_not_found(self, tmp_path):
        """Should handle git command not found."""
        # Create a git repo
        (tmp_path / '.git').mkdir()

        # Mock git not found
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            collector = SemanticFileCollector(tmp_path)
            files = collector.collect_files()

            # Should return empty
            assert len(files) == 0

    def test_collect_files_plain_scan_filters_by_path(self, tmp_path):
        """Plain scan should apply path filtering."""
        # Create directory structure
        (tmp_path / 'src').mkdir()
        (tmp_path / 'dist').mkdir()

        (tmp_path / 'src' / 'main.py').write_text('print("main")')
        (tmp_path / 'src' / 'distributed.py').write_text('print("distributed")')  # Should NOT be filtered
        (tmp_path / 'dist' / 'bundle.js').write_text('console.log("bundle")')  # Should be filtered

        # Collect with respect_gitignore=False to force plain scan
        config = IndexFilterConfig(respect_gitignore=False)
        collector = SemanticFileCollector(tmp_path, filter_config=config)
        files = collector.collect_files()

        # Should get src files but not dist
        assert 'src/main.py' in files or 'src\\main.py' in files
        assert 'src/distributed.py' in files or 'src\\distributed.py' in files  # Not filtered (no substring match)
        assert not any('dist' in f and 'bundle' in f for f in files)  # dist/bundle.js filtered

    def test_collect_files_reads_file_content(self, tmp_path):
        """Should return dict with file content."""
        content = 'def hello():\n    print("Hello")'
        (tmp_path / 'test.py').write_text(content)

        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        assert files['test.py'] == content

    def test_collect_files_handles_read_errors_gracefully(self, tmp_path):
        """Should skip files that can't be read."""
        (tmp_path / 'good.py').write_text('print("good")')

        collector = SemanticFileCollector(tmp_path)

        # Mock read_text to fail for specific file
        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            if 'bad' in str(self):
                raise PermissionError("No permission")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, 'read_text', mock_read_text):
            files = collector.collect_files()

            # Should get good file, skip bad
            assert 'good.py' in files


class TestTestNoiseExclusion:
    """Test noise exclusion patterns for test data directories and files."""

    def test_default_test_noise_patterns_includes_snapshots(self):
        """Should include common test noise directories."""
        config = IndexFilterConfig()

        assert '__snapshots__' in config.test_noise_patterns
        assert 'snapshots' in config.test_noise_patterns
        assert 'fixtures' in config.test_noise_patterns
        assert '__mocks__' in config.test_noise_patterns
        assert 'testdata' in config.test_noise_patterns

    def test_default_test_noise_extensions_includes_snap(self):
        """Should include snapshot file extensions."""
        config = IndexFilterConfig()

        assert '.snap' in config.test_noise_extensions
        assert '.snapshot' in config.test_noise_extensions

    def test_should_skip_snapshot_directories(self):
        """Should skip files in __snapshots__ directory."""
        config = IndexFilterConfig()
        root = Path('/project')

        # Files in __snapshots__ should be skipped
        snap_file = Path('/project/tests/__snapshots__/Button.test.js.snap')
        assert config.should_skip_by_path(snap_file, root) is True

        # But test code should not be skipped
        test_file = Path('/project/tests/Button.test.js')
        assert config.should_skip_by_path(test_file, root) is False

    def test_should_skip_fixture_directories(self):
        """Should skip files in fixtures directory."""
        config = IndexFilterConfig()
        root = Path('/project')

        # Files in fixtures should be skipped
        fixture_file = Path('/project/tests/fixtures/sample_data.json')
        assert config.should_skip_by_path(fixture_file, root) is True

        # Nested fixtures
        nested_fixture = Path('/project/tests/unit/fixtures/mock.json')
        assert config.should_skip_by_path(nested_fixture, root) is True

    def test_should_skip_test_data_directories(self):
        """Should skip files in test/data and tests/data directories."""
        config = IndexFilterConfig()
        root = Path('/project')

        # test/data
        test_data_file = Path('/project/test/data/sample.json')
        assert config.should_skip_by_path(test_data_file, root) is True

        # tests/data
        tests_data_file = Path('/project/tests/data/sample.json')
        assert config.should_skip_by_path(tests_data_file, root) is True

    def test_should_skip_snap_extension_files(self):
        """Should skip .snap and .snapshot files."""
        config = IndexFilterConfig()
        root = Path('/project')

        # .snap files
        snap_file = Path('/project/Component.snap')
        assert config.should_skip_by_path(snap_file, root) is True

        # .snapshot files
        snapshot_file = Path('/project/test.snapshot')
        assert config.should_skip_by_path(snapshot_file, root) is True

    def test_should_not_skip_test_code(self):
        """Should NOT skip test code files."""
        config = IndexFilterConfig()
        root = Path('/project')

        # Test files should still be included
        test_file = Path('/project/tests/test_module.py')
        assert config.should_skip_by_path(test_file, root) is False

        # Spec files
        spec_file = Path('/project/spec/my_spec.rb')
        assert config.should_skip_by_path(spec_file, root) is False

    def test_should_skip_large_json_in_tests(self):
        """Should skip large JSON files in test directories."""
        config = IndexFilterConfig(
            skip_large_json_in_tests=True,
            large_json_threshold_bytes=100  # Small threshold for testing
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tests_dir = tmpdir / 'tests'
            tests_dir.mkdir()

            # Large JSON in tests/ - should be skipped
            large_json = tests_dir / 'large_fixture.json'
            large_json.write_text('x' * 200)  # 200 bytes > 100 threshold
            assert config.should_skip_large_json_in_tests(large_json, tmpdir) is True

            # Small JSON in tests/ - should NOT be skipped
            small_json = tests_dir / 'small.json'
            small_json.write_text('{}')
            assert config.should_skip_large_json_in_tests(small_json, tmpdir) is False

            # Large JSON outside tests/ - should NOT be skipped
            src_dir = tmpdir / 'src'
            src_dir.mkdir()
            src_json = src_dir / 'config.json'
            src_json.write_text('x' * 200)
            assert config.should_skip_large_json_in_tests(src_json, tmpdir) is False

    def test_should_skip_large_json_in_spec_directory(self):
        """Should also skip large JSON in spec/ directory."""
        config = IndexFilterConfig(
            skip_large_json_in_tests=True,
            large_json_threshold_bytes=100
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            spec_dir = tmpdir / 'spec'
            spec_dir.mkdir()

            large_json = spec_dir / 'fixture.json'
            large_json.write_text('x' * 200)
            assert config.should_skip_large_json_in_tests(large_json, tmpdir) is True

    def test_skip_large_json_can_be_disabled(self):
        """Should respect skip_large_json_in_tests=False."""
        config = IndexFilterConfig(
            skip_large_json_in_tests=False,
            large_json_threshold_bytes=100
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tests_dir = tmpdir / 'tests'
            tests_dir.mkdir()

            large_json = tests_dir / 'large.json'
            large_json.write_text('x' * 200)
            assert config.should_skip_large_json_in_tests(large_json, tmpdir) is False

    def test_collect_files_skips_test_noise(self, tmp_path):
        """SemanticFileCollector should skip test noise."""
        # Create directory structure
        tests_dir = tmp_path / 'tests'
        tests_dir.mkdir()
        (tests_dir / 'test_module.py').write_text('def test_foo(): pass')

        snapshots_dir = tests_dir / '__snapshots__'
        snapshots_dir.mkdir()
        (snapshots_dir / 'test_module.snap').write_text('snapshot data')

        fixtures_dir = tests_dir / 'fixtures'
        fixtures_dir.mkdir()
        (fixtures_dir / 'data.json').write_text('{"key": "value"}')

        # Collect files
        collector = SemanticFileCollector(tmp_path)
        files = collector.collect_files()

        # Test code should be included
        assert any('test_module.py' in f for f in files)

        # Snapshots and fixtures should NOT be included
        assert not any('__snapshots__' in f for f in files)
        assert not any('.snap' in f for f in files)
        assert not any('fixtures' in f for f in files)
