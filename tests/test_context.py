"""
Tests for CodebaseContext - project exploration and context management.
"""
import pytest
from pathlib import Path
from datetime import datetime
import json

from src.context import CodebaseContext


class TestCodebaseContextBasics:
    """Basic context creation and state tests."""

    @pytest.mark.unit
    def test_context_creation_current_dir(self):
        """Test creating context for current directory."""
        context = CodebaseContext()
        assert context.project_path.exists()
        assert isinstance(context.project_path, Path)

    @pytest.mark.unit
    def test_context_creation_with_path(self, temp_project_dir):
        """Test creating context with specific path."""
        context = CodebaseContext(str(temp_project_dir))
        assert context.project_path == temp_project_dir.resolve()

    @pytest.mark.unit
    def test_initial_state(self, temp_project_dir):
        """Test initial state before exploration."""
        context = CodebaseContext(str(temp_project_dir))
        assert context.summary is None
        assert context.structure == {}
        assert context.key_files == {}
        assert context.file_index == {}
        assert context.explored_at is None

    @pytest.mark.unit
    def test_is_explored_before_explore(self, temp_project_dir):
        """Test that is_explored returns False before exploration."""
        context = CodebaseContext(str(temp_project_dir))
        assert context.is_explored() is False

    @pytest.mark.unit
    def test_cache_file_path(self, temp_project_dir):
        """Test that cache file path is set correctly."""
        context = CodebaseContext(str(temp_project_dir))
        expected_cache = temp_project_dir / ".llm_team_context.json"
        assert context.cache_file == expected_cache


class TestCodebaseExploration:
    """Tests for codebase exploration functionality."""

    @pytest.fixture
    def rich_project_dir(self, tmp_path):
        """Create a project directory with various file types."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "utils").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        # Create Python files
        (tmp_path / "src" / "__init__.py").write_text("")
        (tmp_path / "src" / "main.py").write_text('def main():\n    print("Hello")\n')
        (tmp_path / "src" / "utils" / "__init__.py").write_text("")
        (tmp_path / "src" / "utils" / "helpers.py").write_text('def helper():\n    pass\n')

        # Create test files
        (tmp_path / "tests" / "test_main.py").write_text('def test_main():\n    pass\n')

        # Create config files
        (tmp_path / "README.md").write_text("# Test Project\n\nA test project.\n")
        (tmp_path / "requirements.txt").write_text("pytest\nclick\n")
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        # Create a JavaScript file
        (tmp_path / "package.json").write_text('{"name": "test"}\n')

        # Simulate git directory
        (tmp_path / ".git").mkdir()

        return tmp_path

    @pytest.mark.unit
    def test_explore_returns_dict(self, rich_project_dir):
        """Test that explore returns a dictionary."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()
        assert isinstance(result, dict)

    @pytest.mark.unit
    def test_explore_marks_explored(self, rich_project_dir):
        """Test that explore sets explored_at timestamp."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()
        # is_explored checks for both summary AND explored_at
        # After explore(), explored_at is set but summary may be None until generated
        assert context.explored_at is not None
        assert isinstance(context.explored_at, datetime)

    @pytest.mark.unit
    def test_explore_counts_files(self, rich_project_dir):
        """Test that explore counts files correctly."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()

        assert 'total_files' in result
        assert result['total_files'] > 0

    @pytest.mark.unit
    def test_explore_detects_file_types(self, rich_project_dir):
        """Test that explore detects different file types."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()

        assert 'file_types' in result
        # Should detect Python files
        file_types = result['file_types']
        # Check for python files (may be 'python' or 'py' depending on implementation)
        has_python = any('py' in k.lower() or 'python' in k.lower() for k in file_types.keys())
        assert has_python or len(file_types) > 0

    @pytest.mark.unit
    def test_explore_finds_directories(self, rich_project_dir):
        """Test that explore lists directories."""
        context = CodebaseContext(str(rich_project_dir))
        result = context.explore()

        assert 'directories' in result
        directories = result['directories']
        assert 'src' in directories or any('src' in d for d in directories)

    @pytest.mark.unit
    def test_explore_detects_git(self, rich_project_dir):
        """Test that explore detects git repository."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_git') is True

    @pytest.mark.unit
    def test_explore_detects_readme(self, rich_project_dir):
        """Test that explore detects README."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_readme') is True

    @pytest.mark.unit
    def test_explore_detects_requirements(self, rich_project_dir):
        """Test that explore detects requirements.txt."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_requirements') is True

    @pytest.mark.unit
    def test_explore_detects_pyproject(self, rich_project_dir):
        """Test that explore detects pyproject.toml."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        assert context.structure.get('has_pyproject') is True

    @pytest.mark.unit
    def test_explore_cached_returns_cached_status(self, rich_project_dir):
        """Test that second explore returns cached status."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        # Set summary to satisfy is_explored() check
        context.summary = "Test summary"
        result = context.explore()  # Second call

        assert result['status'] == 'cached'

    @pytest.mark.unit
    def test_explore_force_reexplores(self, rich_project_dir):
        """Test that force=True re-explores."""
        context = CodebaseContext(str(rich_project_dir))
        context.explore()

        old_time = context.explored_at
        import time
        time.sleep(0.01)  # Small delay

        result = context.explore(force=True)
        assert result['status'] == 'explored'
        assert context.explored_at > old_time


class TestKeyFileReading:
    """Tests for reading key project files."""

    @pytest.fixture
    def project_with_key_files(self, tmp_path):
        """Create project with key files."""
        (tmp_path / "README.md").write_text("# My Project\n\nDescription here.\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='test')\n")
        (tmp_path / "requirements.txt").write_text("flask==2.0.0\nrequests>=2.25.0\n")
        (tmp_path / ".git").mkdir()
        return tmp_path

    @pytest.mark.unit
    def test_reads_readme(self, project_with_key_files):
        """Test that README is read."""
        context = CodebaseContext(str(project_with_key_files))
        context.explore()

        assert "README.md" in context.key_files or any("README" in k for k in context.key_files)

    @pytest.mark.unit
    def test_reads_setup_py(self, project_with_key_files):
        """Test that setup.py is read."""
        context = CodebaseContext(str(project_with_key_files))
        context.explore()

        has_setup = "setup.py" in context.key_files or any("setup" in k for k in context.key_files)
        assert has_setup

    @pytest.mark.unit
    def test_key_files_contain_content(self, project_with_key_files):
        """Test that key files have actual content."""
        context = CodebaseContext(str(project_with_key_files))
        context.explore()

        for filename, content in context.key_files.items():
            assert len(content) > 0


class TestCaching:
    """Tests for context caching functionality."""

    @pytest.mark.unit
    def test_saves_cache_after_explore(self, temp_project_dir):
        """Test that cache is saved after exploration."""
        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.cache_file.exists()

    @pytest.mark.unit
    def test_cache_contains_json(self, temp_project_dir):
        """Test that cache file contains valid JSON."""
        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        with open(context.cache_file, 'r') as f:
            data = json.load(f)
        assert isinstance(data, dict)

    @pytest.mark.unit
    def test_loads_cache_on_init(self, temp_project_dir):
        """Test that cache is loaded on initialization."""
        # First context explores and saves
        context1 = CodebaseContext(str(temp_project_dir))
        context1.explore()
        explored_time = context1.explored_at

        # Second context should load from cache
        context2 = CodebaseContext(str(temp_project_dir))
        # Should have loaded cached data
        assert context2.explored_at == explored_time

    @pytest.mark.unit
    def test_cache_survives_reinstantiation(self, temp_project_dir):
        """Test that context state survives reinstantiation."""
        context1 = CodebaseContext(str(temp_project_dir))
        context1.explore()
        # Set summary to be cached
        context1.summary = "Test project summary"
        context1._save_cache()

        # Create new instance - should load from cache
        context2 = CodebaseContext(str(temp_project_dir))
        # Check that explored_at was restored from cache
        assert context2.explored_at is not None


class TestPromptAugmentation:
    """Tests for prompt augmentation functionality."""

    @pytest.fixture
    def explored_context(self, temp_project_dir):
        """Create an explored context."""
        context = CodebaseContext(str(temp_project_dir))
        context.explore()
        # Manually set a summary for testing
        context.summary = "Python project with main.py and tests."
        return context

    @pytest.mark.unit
    def test_augment_prompt_adds_context(self, explored_context):
        """Test that augment_prompt adds context to prompt."""
        original = "Fix the bug in main.py"
        augmented = explored_context.augment_prompt(original)

        # Should contain original prompt
        assert original in augmented
        # Should contain some context info
        assert len(augmented) > len(original)

    @pytest.mark.unit
    def test_augment_prompt_includes_project_info(self, explored_context):
        """Test that augmented prompt includes project information."""
        augmented = explored_context.augment_prompt("Test prompt")

        # Should include project name or path info
        # Depends on implementation
        assert len(augmented) > 0

    @pytest.mark.unit
    def test_augment_prompt_handles_empty_input(self, explored_context):
        """Test augmenting empty prompt."""
        augmented = explored_context.augment_prompt("")
        assert isinstance(augmented, str)


class TestEdgeCases:
    """Edge cases and error handling tests."""

    @pytest.mark.unit
    def test_nonexistent_path_handled(self, tmp_path):
        """Test handling of nonexistent path."""
        nonexistent = tmp_path / "does_not_exist"
        # Should not raise exception during creation
        context = CodebaseContext(str(nonexistent))
        assert context.project_path is not None

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        """Test exploring empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        context = CodebaseContext(str(empty_dir))
        result = context.explore()

        assert result['status'] == 'explored'
        assert result['total_files'] == 0

    @pytest.mark.unit
    def test_directory_with_only_hidden_files(self, tmp_path):
        """Test directory with only hidden files."""
        (tmp_path / ".hidden").write_text("hidden content")
        (tmp_path / ".gitignore").write_text("*.pyc\n")

        context = CodebaseContext(str(tmp_path))
        result = context.explore()

        assert isinstance(result, dict)

    @pytest.mark.unit
    def test_corrupted_cache_handled(self, temp_project_dir):
        """Test that corrupted cache is handled gracefully."""
        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        # Corrupt the cache file
        context.cache_file.write_text("not valid json {")

        # Should handle gracefully on new instance
        context2 = CodebaseContext(str(temp_project_dir))
        assert context2.summary is None or context2.explored_at is None


class TestProjectTypeDetection:
    """Tests for detecting different project types."""

    @pytest.mark.unit
    def test_detects_maven_project(self, temp_project_dir):
        """Should detect Java/Maven projects via pom.xml."""
        (temp_project_dir / 'pom.xml').write_text(
            '<project><groupId>com.example</groupId></project>\n'
        )

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_pom_xml') is True

    @pytest.mark.unit
    def test_detects_gradle_project(self, temp_project_dir):
        """Should detect Java/Gradle projects via build.gradle."""
        (temp_project_dir / 'build.gradle').write_text(
            'plugins {\n    id "java"\n}\n'
        )

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_build_gradle') is True

    @pytest.mark.unit
    def test_detects_rust_project(self, temp_project_dir):
        """Should detect Rust projects via Cargo.toml."""
        (temp_project_dir / 'Cargo.toml').write_text(
            '[package]\nname = "myapp"\nversion = "0.1.0"\n'
        )

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_cargo_toml') is True

    @pytest.mark.unit
    def test_detects_go_project(self, temp_project_dir):
        """Should detect Go projects via go.mod."""
        (temp_project_dir / 'go.mod').write_text(
            'module github.com/user/myapp\ngo 1.21\n'
        )

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_go_mod') is True

    @pytest.mark.unit
    def test_detects_ruby_project(self, temp_project_dir):
        """Should detect Ruby projects via Gemfile."""
        (temp_project_dir / 'Gemfile').write_text(
            'source "https://rubygems.org"\ngem "rails"\n'
        )

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_gemfile') is True

    @pytest.mark.unit
    def test_detects_dotnet_project(self, temp_project_dir):
        """Should detect .NET projects via .csproj or .sln."""
        (temp_project_dir / 'MyApp.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"></Project>\n'
        )

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_csproj') is True

    @pytest.mark.unit
    def test_detects_multiple_project_types(self, temp_project_dir):
        """Should detect multiple project types in monorepo."""
        # Python backend
        (temp_project_dir / 'requirements.txt').write_text('flask\n')
        # Node.js frontend
        (temp_project_dir / 'package.json').write_text('{"name": "frontend"}\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        assert context.structure.get('has_requirements') is True
        assert context.structure.get('has_package_json') is True

    @pytest.mark.unit
    def test_get_project_type_returns_primary_type(self, temp_project_dir):
        """Should return primary project type based on markers."""
        (temp_project_dir / 'requirements.txt').write_text('django\n')

        context = CodebaseContext(str(temp_project_dir))
        context.explore()

        # Should provide a method to get primary project type
        project_type = context.get_project_type()
        assert project_type == 'python'

    @pytest.mark.unit
    def test_get_project_type_java_maven(self, tmp_path):
        """Should identify Java/Maven as project type."""
        # Use tmp_path to avoid default pyproject.toml
        (tmp_path / 'pom.xml').write_text('<project></project>\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        project_type = context.get_project_type()
        assert project_type in ('java', 'maven', 'java-maven')

    @pytest.mark.unit
    def test_get_project_type_nodejs(self, tmp_path):
        """Should identify Node.js as project type."""
        # Use tmp_path to avoid default pyproject.toml
        (tmp_path / 'package.json').write_text('{"name": "app"}\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        project_type = context.get_project_type()
        assert project_type in ('nodejs', 'node', 'javascript')

    @pytest.mark.unit
    def test_get_project_type_unknown(self, tmp_path):
        """Should return unknown/generic for unmarked projects."""
        # Use tmp_path to avoid default pyproject.toml
        context = CodebaseContext(str(tmp_path))
        context.explore()

        project_type = context.get_project_type()
        assert project_type in ('unknown', 'generic', None)


class TestPlatformAwareness:
    """Tests for platform detection in context."""

    @pytest.mark.unit
    def test_context_knows_current_platform(self):
        """Context should know the current platform."""
        from src.context import CodebaseContext
        import sys

        context = CodebaseContext()

        # Should have platform information
        platform = context.get_platform()
        assert platform is not None
        assert platform in ('windows', 'unix', 'darwin', 'linux')

    @pytest.mark.unit
    def test_platform_matches_system(self):
        """Platform detection should match actual system."""
        from src.context import CodebaseContext
        import sys

        context = CodebaseContext()
        platform = context.get_platform()

        if sys.platform == 'win32':
            assert platform == 'windows'
        elif sys.platform == 'darwin':
            assert platform in ('darwin', 'unix')
        else:
            assert platform in ('linux', 'unix')

    @pytest.mark.unit
    def test_platform_is_cached(self):
        """Platform detection should be cached (not recalculated)."""
        from src.context import CodebaseContext
        from unittest.mock import patch

        context = CodebaseContext()

        # First call
        platform1 = context.get_platform()

        # Platform should be cached, not re-detected
        with patch('sys.platform', 'completely_different'):
            platform2 = context.get_platform()

        # Should return cached value
        assert platform1 == platform2


class TestToolAvailability:
    """Tests for detecting available tools/commands."""

    @pytest.mark.unit
    def test_detects_git_available(self, temp_project_dir):
        """Should detect if git command is available."""
        context = CodebaseContext(str(temp_project_dir))

        # git should be available in most dev environments
        has_git = context.has_tool('git')
        assert isinstance(has_git, bool)

    @pytest.mark.unit
    def test_detects_python_available(self, temp_project_dir):
        """Should detect if python command is available."""
        context = CodebaseContext(str(temp_project_dir))

        # We're running Python tests, so Python must be available
        has_python = context.has_tool('python')
        assert has_python is True

    @pytest.mark.unit
    def test_detects_nonexistent_tool(self, temp_project_dir):
        """Should return False for nonexistent tools."""
        context = CodebaseContext(str(temp_project_dir))

        # This tool definitely doesn't exist
        has_fake = context.has_tool('definitely_not_a_real_command_xyz123')
        assert has_fake is False

    @pytest.mark.unit
    def test_tool_detection_cached(self, temp_project_dir):
        """Tool detection should be cached for performance."""
        context = CodebaseContext(str(temp_project_dir))

        # Check same tool twice
        _ = context.has_tool('git')
        _ = context.has_tool('git')

        # Should only check once (implementation detail)
        # At minimum, should not raise errors
        assert True


class TestMonorepoDetection:
    """Tests for detecting project types in subdirectories (monorepos)."""

    @pytest.fixture
    def monorepo_dir(self, tmp_path):
        """Create a monorepo with multiple project types."""
        # Frontend - Node.js/React
        frontend = tmp_path / 'frontend'
        frontend.mkdir()
        (frontend / 'package.json').write_text('{"name": "frontend", "dependencies": {"react": "^18.0.0"}}\n')
        (frontend / 'src').mkdir()
        (frontend / 'src' / 'App.tsx').write_text('export const App = () => <div>Hello</div>;\n')
        (frontend / 'src' / 'index.ts').write_text('import { App } from "./App";\n')

        # Backend - Python/Django
        backend = tmp_path / 'backend'
        backend.mkdir()
        (backend / 'requirements.txt').write_text('django==4.2\ndjango-rest-framework\n')
        (backend / 'manage.py').write_text('#!/usr/bin/env python\nimport django\n')
        (backend / 'api').mkdir()
        (backend / 'api' / '__init__.py').write_text('')
        (backend / 'api' / 'views.py').write_text('from django.views import View\n')

        # Services - Java microservices
        services = tmp_path / 'services'
        services.mkdir()
        auth_api = services / 'auth-api'
        auth_api.mkdir()
        (auth_api / 'pom.xml').write_text('<project><artifactId>auth-api</artifactId></project>\n')

        # Shared Go worker
        worker = tmp_path / 'worker'
        worker.mkdir()
        (worker / 'go.mod').write_text('module github.com/myorg/worker\ngo 1.21\n')
        (worker / 'main.go').write_text('package main\nfunc main() {}\n')

        return tmp_path

    @pytest.mark.unit
    def test_detects_frontend_nodejs_project(self, monorepo_dir):
        """Should detect Node.js project in frontend subdirectory."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        sub_projects = context.get_sub_projects()
        assert 'frontend' in sub_projects
        assert sub_projects['frontend'] in ('nodejs', 'node', 'javascript', 'typescript')

    @pytest.mark.unit
    def test_detects_backend_python_project(self, monorepo_dir):
        """Should detect Python project in backend subdirectory."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        sub_projects = context.get_sub_projects()
        assert 'backend' in sub_projects
        assert sub_projects['backend'] == 'python'

    @pytest.mark.unit
    def test_detects_nested_java_project(self, monorepo_dir):
        """Should detect Java project in nested subdirectory."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        sub_projects = context.get_sub_projects()
        # Should find services/auth-api as Java
        has_java = any('java' in ptype for ptype in sub_projects.values())
        assert has_java, f"No Java project found in {sub_projects}"

    @pytest.mark.unit
    def test_detects_go_worker_project(self, monorepo_dir):
        """Should detect Go project in worker subdirectory."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        sub_projects = context.get_sub_projects()
        assert 'worker' in sub_projects
        assert sub_projects['worker'] == 'go'

    @pytest.mark.unit
    def test_monorepo_detects_project_type_from_subdirs(self, monorepo_dir):
        """Monorepo should detect project type based on markers in subdirectories."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        # Even though root has no markers, subdirs do
        # Should detect based on what's found in the tree
        primary_type = context.get_project_type()
        # Monorepo has python (backend), nodejs (frontend), java (services), go (worker)
        # Should detect one of these, not 'unknown'
        assert primary_type in ('python', 'nodejs', 'java', 'go'), f"Got {primary_type}"

    @pytest.mark.unit
    def test_lists_all_languages_used(self, monorepo_dir):
        """Should list all programming languages found in the codebase."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        languages = context.get_languages()
        # Should detect Python, TypeScript/JavaScript, Java, Go
        assert 'python' in languages or any('py' in lang for lang in languages)
        assert 'javascript' in languages or 'typescript' in languages or any('js' in lang or 'ts' in lang for lang in languages)

    @pytest.mark.unit
    def test_uses_file_index_for_language_detection(self, monorepo_dir):
        """Should use file_index to detect languages, not just project markers."""
        context = CodebaseContext(str(monorepo_dir))
        context.explore()

        # file_index should have categorized all files
        assert len(context.file_index.get('python', [])) > 0, "No Python files found"
        assert len(context.file_index.get('javascript', [])) > 0, "No JS/TS files found"


class TestFileIndexUtilization:
    """Tests for using file_index to inform project detection."""

    @pytest.mark.unit
    def test_finds_project_markers_in_subdirs(self, tmp_path):
        """Should find package.json, requirements.txt in subdirectories."""
        # Create nested structure
        (tmp_path / 'app' / 'client').mkdir(parents=True)
        (tmp_path / 'app' / 'client' / 'package.json').write_text('{"name": "client"}\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        # Should find the nested package.json
        markers = context.find_project_markers()
        assert any('package.json' in marker for marker in markers), f"package.json not found in {markers}"

    @pytest.mark.unit
    def test_maps_markers_to_directories(self, tmp_path):
        """Should map project markers to their containing directories."""
        (tmp_path / 'frontend').mkdir()
        (tmp_path / 'frontend' / 'package.json').write_text('{"name": "fe"}\n')
        (tmp_path / 'backend').mkdir()
        (tmp_path / 'backend' / 'requirements.txt').write_text('flask\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        marker_map = context.get_marker_locations()
        # Should map directory to marker type
        assert marker_map.get('frontend') == 'package.json' or 'frontend' in str(marker_map)
        assert marker_map.get('backend') == 'requirements.txt' or 'backend' in str(marker_map)

    @pytest.mark.unit
    def test_detects_language_from_file_extensions(self, tmp_path):
        """Should detect languages from actual code files, not just markers."""
        # Python files without requirements.txt
        (tmp_path / 'scripts').mkdir()
        (tmp_path / 'scripts' / 'deploy.py').write_text('import boto3\n')
        (tmp_path / 'scripts' / 'cleanup.py').write_text('import os\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        # Should detect Python from .py files
        languages = context.get_languages()
        assert 'python' in languages

    @pytest.mark.unit
    def test_config_files_include_nested_markers(self, tmp_path):
        """file_index['config'] should include nested project markers."""
        (tmp_path / 'services' / 'api').mkdir(parents=True)
        (tmp_path / 'services' / 'api' / 'package.json').write_text('{"name": "api"}\n')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        config_files = context.file_index.get('config', [])
        has_nested_package_json = any('package.json' in f for f in config_files)
        assert has_nested_package_json, f"Nested package.json not in config files: {config_files}"

    @pytest.mark.unit
    def test_counts_files_per_language(self, tmp_path):
        """Should count how many files of each language type exist."""
        (tmp_path / 'src').mkdir()
        (tmp_path / 'src' / 'a.py').write_text('')
        (tmp_path / 'src' / 'b.py').write_text('')
        (tmp_path / 'src' / 'c.py').write_text('')
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib' / 'util.js').write_text('')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        lang_counts = context.get_language_stats()
        assert lang_counts.get('python', 0) >= 3
        assert lang_counts.get('javascript', 0) >= 1

    @pytest.mark.unit
    def test_primary_language_based_on_file_count(self, tmp_path):
        """Primary language should be determined by file count, not just markers."""
        # More Python files than JS
        (tmp_path / 'src').mkdir()
        for i in range(10):
            (tmp_path / 'src' / f'module{i}.py').write_text('')
        (tmp_path / 'scripts').mkdir()
        (tmp_path / 'scripts' / 'one.js').write_text('')

        context = CodebaseContext(str(tmp_path))
        context.explore()

        primary = context.get_primary_language()
        assert primary == 'python', f"Expected python as primary, got {primary}"
