"""
Tests for ProjectDetector - project type and language detection.

Following TDD: these tests define the expected behavior before implementation.
"""
import pytest
from pathlib import Path


class TestProjectDetectorBasics:
    """Basic initialization and interface tests."""

    @pytest.mark.unit
    def test_creation_with_project_path(self, tmp_path):
        """ProjectDetector can be created with a project path."""
        from src.context.project_detector import ProjectDetector

        detector = ProjectDetector(tmp_path)
        assert detector.project_path == tmp_path

    @pytest.mark.unit
    def test_creation_accepts_string_path(self, tmp_path):
        """ProjectDetector accepts string path and converts to Path."""
        from src.context.project_detector import ProjectDetector

        detector = ProjectDetector(str(tmp_path))
        assert detector.project_path == tmp_path
        assert isinstance(detector.project_path, Path)


class TestProjectMarkerDetection:
    """Tests for detecting project marker files."""

    @pytest.fixture
    def detector_factory(self):
        """Factory to create detector with file_index."""
        from src.context.project_detector import ProjectDetector

        def create(project_path, file_index=None):
            detector = ProjectDetector(project_path)
            if file_index:
                detector.set_file_index(file_index)
            return detector
        return create

    @pytest.mark.unit
    def test_detects_python_requirements(self, tmp_path, detector_factory):
        """Should detect Python project via requirements.txt."""
        (tmp_path / 'requirements.txt').write_text('flask\n')

        detector = detector_factory(tmp_path, {'docs': ['requirements.txt']})
        markers = detector.detect_markers()

        assert markers.get('has_requirements') is True

    @pytest.mark.unit
    def test_detects_pyproject_toml(self, tmp_path, detector_factory):
        """Should detect Python project via pyproject.toml."""
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')

        detector = detector_factory(tmp_path, {'config': ['pyproject.toml']})
        markers = detector.detect_markers()

        assert markers.get('has_pyproject') is True

    @pytest.mark.unit
    def test_detects_package_json(self, tmp_path, detector_factory):
        """Should detect Node.js project via package.json."""
        (tmp_path / 'package.json').write_text('{"name": "test"}\n')

        detector = detector_factory(tmp_path, {'config': ['package.json']})
        markers = detector.detect_markers()

        assert markers.get('has_package_json') is True

    @pytest.mark.unit
    def test_detects_pom_xml(self, tmp_path, detector_factory):
        """Should detect Java/Maven project via pom.xml."""
        (tmp_path / 'pom.xml').write_text('<project></project>\n')

        detector = detector_factory(tmp_path, {'config': ['pom.xml']})
        markers = detector.detect_markers()

        assert markers.get('has_pom_xml') is True

    @pytest.mark.unit
    def test_detects_build_gradle(self, tmp_path, detector_factory):
        """Should detect Java/Gradle project via build.gradle."""
        (tmp_path / 'build.gradle').write_text('plugins { id "java" }\n')

        detector = detector_factory(tmp_path, {'config': ['build.gradle']})
        markers = detector.detect_markers()

        assert markers.get('has_build_gradle') is True

    @pytest.mark.unit
    def test_detects_cargo_toml(self, tmp_path, detector_factory):
        """Should detect Rust project via Cargo.toml."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')

        detector = detector_factory(tmp_path, {'config': ['Cargo.toml']})
        markers = detector.detect_markers()

        assert markers.get('has_cargo_toml') is True

    @pytest.mark.unit
    def test_detects_go_mod(self, tmp_path, detector_factory):
        """Should detect Go project via go.mod."""
        (tmp_path / 'go.mod').write_text('module test\ngo 1.21\n')

        detector = detector_factory(tmp_path, {'config': ['go.mod']})
        markers = detector.detect_markers()

        assert markers.get('has_go_mod') is True

    @pytest.mark.unit
    def test_detects_gemfile(self, tmp_path, detector_factory):
        """Should detect Ruby project via Gemfile."""
        (tmp_path / 'Gemfile').write_text('source "https://rubygems.org"\n')

        detector = detector_factory(tmp_path, {'other': ['Gemfile']})
        markers = detector.detect_markers()

        assert markers.get('has_gemfile') is True

    @pytest.mark.unit
    def test_detects_csproj(self, tmp_path, detector_factory):
        """Should detect .NET project via .csproj."""
        (tmp_path / 'App.csproj').write_text('<Project></Project>\n')

        detector = detector_factory(tmp_path, {'config': ['App.csproj']})
        markers = detector.detect_markers()

        assert markers.get('has_csproj') is True

    @pytest.mark.unit
    def test_detects_sln(self, tmp_path, detector_factory):
        """Should detect .NET project via .sln."""
        (tmp_path / 'App.sln').write_text('Microsoft Visual Studio Solution\n')

        detector = detector_factory(tmp_path, {'config': ['App.sln']})
        markers = detector.detect_markers()

        assert markers.get('has_csproj') is True  # .sln counts as has_csproj

    @pytest.mark.unit
    def test_detects_git_directory(self, tmp_path, detector_factory):
        """Should detect git repository via .git directory."""
        (tmp_path / '.git').mkdir()

        detector = detector_factory(tmp_path, {})
        markers = detector.detect_markers()

        assert markers.get('has_git') is True

    @pytest.mark.unit
    def test_detects_readme(self, tmp_path, detector_factory):
        """Should detect README.md in root."""
        (tmp_path / 'README.md').write_text('# Project\n')

        detector = detector_factory(tmp_path, {'docs': ['README.md']})
        markers = detector.detect_markers()

        assert markers.get('has_readme') is True

    @pytest.mark.unit
    def test_multiple_markers_detected(self, tmp_path, detector_factory):
        """Should detect multiple project markers."""
        (tmp_path / 'requirements.txt').write_text('flask\n')
        (tmp_path / 'package.json').write_text('{"name": "test"}\n')
        (tmp_path / '.git').mkdir()

        detector = detector_factory(tmp_path, {
            'docs': ['requirements.txt'],
            'config': ['package.json']
        })
        markers = detector.detect_markers()

        assert markers.get('has_requirements') is True
        assert markers.get('has_package_json') is True
        assert markers.get('has_git') is True

    @pytest.mark.unit
    def test_no_markers_returns_all_false(self, tmp_path, detector_factory):
        """Should return all False when no markers present."""
        detector = detector_factory(tmp_path, {})
        markers = detector.detect_markers()

        assert markers.get('has_requirements') is False
        assert markers.get('has_package_json') is False
        assert markers.get('has_git') is False


class TestProjectTypeDetection:
    """Tests for determining primary project type."""

    @pytest.fixture
    def detector_factory(self):
        """Factory to create detector with markers pre-set."""
        from src.context.project_detector import ProjectDetector

        def create(project_path, file_index=None):
            detector = ProjectDetector(project_path)
            if file_index:
                detector.set_file_index(file_index)
            return detector
        return create

    @pytest.mark.unit
    def test_python_from_requirements(self, tmp_path, detector_factory):
        """Should identify Python from requirements.txt."""
        (tmp_path / 'requirements.txt').write_text('flask\n')

        detector = detector_factory(tmp_path, {'docs': ['requirements.txt']})
        project_type = detector.get_project_type()

        assert project_type == 'python'

    @pytest.mark.unit
    def test_python_from_pyproject(self, tmp_path, detector_factory):
        """Should identify Python from pyproject.toml."""
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')

        detector = detector_factory(tmp_path, {'config': ['pyproject.toml']})
        project_type = detector.get_project_type()

        assert project_type == 'python'

    @pytest.mark.unit
    def test_java_from_pom_xml(self, tmp_path, detector_factory):
        """Should identify Java from pom.xml."""
        (tmp_path / 'pom.xml').write_text('<project></project>\n')

        detector = detector_factory(tmp_path, {'config': ['pom.xml']})
        project_type = detector.get_project_type()

        assert project_type == 'java'

    @pytest.mark.unit
    def test_java_from_build_gradle(self, tmp_path, detector_factory):
        """Should identify Java from build.gradle."""
        (tmp_path / 'build.gradle').write_text('plugins { id "java" }\n')

        detector = detector_factory(tmp_path, {'config': ['build.gradle']})
        project_type = detector.get_project_type()

        assert project_type == 'java'

    @pytest.mark.unit
    def test_nodejs_from_package_json(self, tmp_path, detector_factory):
        """Should identify Node.js from package.json."""
        (tmp_path / 'package.json').write_text('{"name": "test"}\n')

        detector = detector_factory(tmp_path, {'config': ['package.json']})
        project_type = detector.get_project_type()

        assert project_type == 'nodejs'

    @pytest.mark.unit
    def test_rust_from_cargo_toml(self, tmp_path, detector_factory):
        """Should identify Rust from Cargo.toml."""
        (tmp_path / 'Cargo.toml').write_text('[package]\nname = "test"\n')

        detector = detector_factory(tmp_path, {'config': ['Cargo.toml']})
        project_type = detector.get_project_type()

        assert project_type == 'rust'

    @pytest.mark.unit
    def test_go_from_go_mod(self, tmp_path, detector_factory):
        """Should identify Go from go.mod."""
        (tmp_path / 'go.mod').write_text('module test\ngo 1.21\n')

        detector = detector_factory(tmp_path, {'config': ['go.mod']})
        project_type = detector.get_project_type()

        assert project_type == 'go'

    @pytest.mark.unit
    def test_ruby_from_gemfile(self, tmp_path, detector_factory):
        """Should identify Ruby from Gemfile."""
        (tmp_path / 'Gemfile').write_text('source "https://rubygems.org"\n')

        detector = detector_factory(tmp_path, {'other': ['Gemfile']})
        project_type = detector.get_project_type()

        assert project_type == 'ruby'

    @pytest.mark.unit
    def test_dotnet_from_csproj(self, tmp_path, detector_factory):
        """Should identify .NET from .csproj."""
        (tmp_path / 'App.csproj').write_text('<Project></Project>\n')

        detector = detector_factory(tmp_path, {'config': ['App.csproj']})
        project_type = detector.get_project_type()

        assert project_type == 'dotnet'

    @pytest.mark.unit
    def test_unknown_when_no_markers(self, tmp_path, detector_factory):
        """Should return unknown when no markers present."""
        detector = detector_factory(tmp_path, {})
        project_type = detector.get_project_type()

        assert project_type == 'unknown'

    @pytest.mark.unit
    def test_python_priority_over_nodejs(self, tmp_path, detector_factory):
        """Python markers should take priority over Node.js."""
        (tmp_path / 'requirements.txt').write_text('flask\n')
        (tmp_path / 'package.json').write_text('{"name": "test"}\n')

        detector = detector_factory(tmp_path, {
            'docs': ['requirements.txt'],
            'config': ['package.json']
        })
        project_type = detector.get_project_type()

        # Python has higher priority in the detection order
        assert project_type == 'python'


class TestLanguageDetection:
    """Tests for detecting programming languages from file extensions."""

    @pytest.fixture
    def detector_factory(self):
        """Factory to create detector with file_index."""
        from src.context.project_detector import ProjectDetector

        def create(project_path, file_index):
            detector = ProjectDetector(project_path)
            detector.set_file_index(file_index)
            return detector
        return create

    @pytest.mark.unit
    def test_detects_python_from_files(self, tmp_path, detector_factory):
        """Should detect Python from .py files."""
        detector = detector_factory(tmp_path, {
            'python': ['main.py', 'utils.py']
        })

        languages = detector.get_languages()
        assert 'python' in languages

    @pytest.mark.unit
    def test_detects_javascript_from_files(self, tmp_path, detector_factory):
        """Should detect JavaScript from .js files."""
        detector = detector_factory(tmp_path, {
            'javascript': ['app.js', 'index.js']
        })

        languages = detector.get_languages()
        assert 'javascript' in languages

    @pytest.mark.unit
    def test_detects_typescript_from_ts_files(self, tmp_path, detector_factory):
        """Should detect TypeScript from .ts/.tsx files."""
        detector = detector_factory(tmp_path, {
            'javascript': ['app.ts', 'component.tsx']
        })

        languages = detector.get_languages()
        assert 'typescript' in languages

    @pytest.mark.unit
    def test_detects_multiple_languages(self, tmp_path, detector_factory):
        """Should detect multiple languages in same project."""
        detector = detector_factory(tmp_path, {
            'python': ['main.py'],
            'javascript': ['app.js']
        })

        languages = detector.get_languages()
        assert 'python' in languages
        assert 'javascript' in languages

    @pytest.mark.unit
    def test_empty_file_index_returns_empty_list(self, tmp_path, detector_factory):
        """Should return empty list when no files indexed."""
        detector = detector_factory(tmp_path, {})

        languages = detector.get_languages()
        assert languages == []

    @pytest.mark.unit
    def test_get_language_stats(self, tmp_path, detector_factory):
        """Should return count of files per language."""
        detector = detector_factory(tmp_path, {
            'python': ['a.py', 'b.py', 'c.py'],
            'javascript': ['app.js']
        })

        stats = detector.get_language_stats()
        assert stats.get('python') == 3
        assert stats.get('javascript') == 1

    @pytest.mark.unit
    def test_get_primary_language(self, tmp_path, detector_factory):
        """Should return language with most files."""
        detector = detector_factory(tmp_path, {
            'python': ['a.py', 'b.py', 'c.py', 'd.py', 'e.py'],
            'javascript': ['app.js', 'index.js']
        })

        primary = detector.get_primary_language()
        assert primary == 'python'

    @pytest.mark.unit
    def test_primary_language_unknown_when_no_code(self, tmp_path, detector_factory):
        """Should return unknown when no code files."""
        detector = detector_factory(tmp_path, {
            'docs': ['README.md'],
            'config': ['package.json']
        })

        primary = detector.get_primary_language()
        assert primary == 'unknown'


class TestProjectMarkerLocations:
    """Tests for finding and mapping project markers in directories."""

    @pytest.fixture
    def detector_factory(self):
        """Factory to create detector with file_index."""
        from src.context.project_detector import ProjectDetector

        def create(project_path, file_index):
            detector = ProjectDetector(project_path)
            detector.set_file_index(file_index)
            return detector
        return create

    @pytest.mark.unit
    def test_finds_root_marker(self, tmp_path, detector_factory):
        """Should find marker in root directory."""
        detector = detector_factory(tmp_path, {
            'config': ['package.json']
        })

        markers = detector.find_project_markers()
        assert 'package.json' in markers

    @pytest.mark.unit
    def test_finds_nested_marker(self, tmp_path, detector_factory):
        """Should find marker in subdirectory."""
        detector = detector_factory(tmp_path, {
            'config': ['frontend/package.json']
        })

        markers = detector.find_project_markers()
        assert any('package.json' in m for m in markers)

    @pytest.mark.unit
    def test_finds_markers_in_docs_category(self, tmp_path, detector_factory):
        """Should find requirements.txt in docs category."""
        detector = detector_factory(tmp_path, {
            'docs': ['requirements.txt', 'backend/requirements.txt']
        })

        markers = detector.find_project_markers()
        assert len([m for m in markers if 'requirements.txt' in m]) >= 1

    @pytest.mark.unit
    def test_maps_marker_to_directory(self, tmp_path, detector_factory):
        """Should map marker files to their containing directories."""
        detector = detector_factory(tmp_path, {
            'config': ['frontend/package.json', 'backend/pyproject.toml']
        })

        locations = detector.get_marker_locations()
        assert locations.get('frontend') == 'package.json'
        assert locations.get('backend') == 'pyproject.toml'

    @pytest.mark.unit
    def test_root_marker_mapped_to_dot(self, tmp_path, detector_factory):
        """Root-level markers should be mapped to '.'."""
        detector = detector_factory(tmp_path, {
            'config': ['package.json']
        })

        locations = detector.get_marker_locations()
        assert locations.get('.') == 'package.json'

    @pytest.mark.unit
    def test_handles_deeply_nested_markers(self, tmp_path, detector_factory):
        """Should handle markers in deeply nested directories."""
        detector = detector_factory(tmp_path, {
            'config': ['services/auth/api/pom.xml']
        })

        locations = detector.get_marker_locations()
        # Should map the full path
        assert 'services/auth/api' in locations
        assert locations['services/auth/api'] == 'pom.xml'


class TestSubProjectDetection:
    """Tests for detecting sub-projects in monorepos."""

    @pytest.fixture
    def detector_factory(self):
        """Factory to create detector with file_index."""
        from src.context.project_detector import ProjectDetector

        def create(project_path, file_index):
            detector = ProjectDetector(project_path)
            detector.set_file_index(file_index)
            return detector
        return create

    @pytest.mark.unit
    def test_detects_nodejs_subproject(self, tmp_path, detector_factory):
        """Should detect Node.js sub-project in frontend directory."""
        detector = detector_factory(tmp_path, {
            'config': ['frontend/package.json']
        })

        sub_projects = detector.get_sub_projects()
        assert 'frontend' in sub_projects
        assert sub_projects['frontend'] == 'nodejs'

    @pytest.mark.unit
    def test_detects_python_subproject(self, tmp_path, detector_factory):
        """Should detect Python sub-project in backend directory."""
        detector = detector_factory(tmp_path, {
            'docs': ['backend/requirements.txt']
        })

        sub_projects = detector.get_sub_projects()
        assert 'backend' in sub_projects
        assert sub_projects['backend'] == 'python'

    @pytest.mark.unit
    def test_detects_java_subproject(self, tmp_path, detector_factory):
        """Should detect Java sub-project with pom.xml."""
        detector = detector_factory(tmp_path, {
            'config': ['services/api/pom.xml']
        })

        sub_projects = detector.get_sub_projects()
        # Should detect both services and full path
        assert 'services' in sub_projects or 'services/api' in sub_projects

    @pytest.mark.unit
    def test_detects_go_subproject(self, tmp_path, detector_factory):
        """Should detect Go sub-project with go.mod."""
        detector = detector_factory(tmp_path, {
            'config': ['worker/go.mod']
        })

        sub_projects = detector.get_sub_projects()
        assert 'worker' in sub_projects
        assert sub_projects['worker'] == 'go'

    @pytest.mark.unit
    def test_detects_multiple_subprojects(self, tmp_path, detector_factory):
        """Should detect multiple sub-projects in monorepo."""
        detector = detector_factory(tmp_path, {
            'config': ['frontend/package.json', 'worker/go.mod'],
            'docs': ['backend/requirements.txt']
        })

        sub_projects = detector.get_sub_projects()
        assert len(sub_projects) >= 3
        assert sub_projects.get('frontend') == 'nodejs'
        assert sub_projects.get('backend') == 'python'
        assert sub_projects.get('worker') == 'go'

    @pytest.mark.unit
    def test_excludes_root_from_subprojects(self, tmp_path, detector_factory):
        """Root directory marker should not appear in sub-projects."""
        detector = detector_factory(tmp_path, {
            'config': ['package.json', 'services/package.json']
        })

        sub_projects = detector.get_sub_projects()
        # Root ('.') should not be in sub_projects
        assert '.' not in sub_projects
        # But services should be
        assert 'services' in sub_projects

    @pytest.mark.unit
    def test_empty_when_no_subprojects(self, tmp_path, detector_factory):
        """Should return empty dict when no sub-projects."""
        detector = detector_factory(tmp_path, {
            'config': ['package.json']  # Only root marker
        })

        sub_projects = detector.get_sub_projects()
        assert sub_projects == {}


class TestEdgeCases:
    """Edge cases and error handling for ProjectDetector."""

    @pytest.mark.unit
    def test_handles_empty_file_index(self, tmp_path):
        """Should handle empty file_index gracefully."""
        from src.context.project_detector import ProjectDetector

        detector = ProjectDetector(tmp_path)
        detector.set_file_index({})

        # Should not raise errors
        markers = detector.detect_markers()
        assert isinstance(markers, dict)

        project_type = detector.get_project_type()
        assert project_type == 'unknown'

        languages = detector.get_languages()
        assert languages == []

    @pytest.mark.unit

    @pytest.mark.unit
    def test_handles_nonexistent_path(self, tmp_path):
        """Should handle nonexistent project path."""
        from src.context.project_detector import ProjectDetector

        nonexistent = tmp_path / 'does_not_exist'
        detector = ProjectDetector(nonexistent)

        # Should not raise during creation
        assert detector.project_path == nonexistent

    @pytest.mark.unit
    def test_handles_windows_backslash_paths(self, tmp_path):
        """Should handle Windows-style backslash paths in file_index."""
        from src.context.project_detector import ProjectDetector

        detector = ProjectDetector(tmp_path)
        detector.set_file_index({
            'config': ['frontend\\package.json', 'backend\\pyproject.toml']
        })

        locations = detector.get_marker_locations()
        # Should normalize paths
        assert 'frontend' in locations or 'frontend\\package.json' in str(locations)

    @pytest.mark.unit
    def test_markers_are_case_sensitive(self, tmp_path):
        """Marker detection should be case-sensitive."""
        from src.context.project_detector import ProjectDetector

        detector = ProjectDetector(tmp_path)
        detector.set_file_index({
            'config': ['PACKAGE.JSON']  # Wrong case
        })

        markers = detector.detect_markers()
        # Should not detect as package.json
        assert markers.get('has_package_json') is False

    @pytest.mark.unit
    def test_detects_gradle_kts(self, tmp_path):
        """Should detect Kotlin Gradle script as Gradle project."""
        from src.context.project_detector import ProjectDetector

        (tmp_path / 'build.gradle.kts').write_text('plugins { }\n')

        detector = ProjectDetector(tmp_path)
        detector.set_file_index({
            'config': ['build.gradle.kts']
        })

        markers = detector.detect_markers()
        assert markers.get('has_build_gradle') is True
