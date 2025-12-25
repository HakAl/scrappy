"""
Behavior tests for CLI codebase exploration functionality.

Tests actual behavior of codebase scanning, analysis, and summarization.
Focuses on:
- Path validation and error handling
- File scanning and categorization
- Structure analysis
- Summary generation
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from scrappy.cli.codebase import CLICodebaseAnalysis
from tests.helpers import MockIO


class TestExploreCodebasePathValidation:
    """Test path validation and error handling."""

    def test_rejects_nonexistent_path(self):
        """Should display error when path doesn't exist."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        analyzer.explore_codebase("/nonexistent/path/that/does/not/exist")

        output = io.get_output()
        assert "does not exist" in output.lower()



class TestFindSourceFiles:
    """Test source file scanning and categorization."""

    @patch('os.walk')
    def test_categorizes_files_by_extension(self, mock_walk):
        """Should categorize files by their extensions."""
        mock_walk.return_value = [
            ('/test', [], ['main.py', 'app.js', 'config.json', 'README.md', 'other.xyz'])
        ]

        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        files = analyzer._find_source_files(Path('/test'))

        # Check categorization
        assert any('main.py' in f for f in files['python'])
        assert any('app.js' in f for f in files['javascript'])
        assert any('config.json' in f for f in files['config'])
        assert any('README.md' in f for f in files['docs'])
        assert any('other.xyz' in f for f in files['other'])

    @patch('os.walk')
    def test_skips_hidden_files(self, mock_walk):
        """Should skip files starting with dot."""
        mock_walk.return_value = [
            ('/test', [], ['.hidden.py', 'visible.py'])
        ]

        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        files = analyzer._find_source_files(Path('/test'))

        all_files = [f for category in files.values() for f in category]
        assert not any('.hidden.py' in f for f in all_files)
        assert any('visible.py' in f for f in all_files)



class TestAnalyzeStructure:
    """Test project structure analysis."""

    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.iterdir', return_value=[])
    def test_detects_readme_presence(self, mock_iterdir, mock_exists):
        """Should detect README.md or README file."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        with patch.object(Path, 'exists', return_value=True):
            structure = analyzer._analyze_structure(Path('/test'), {'python': []})

        assert structure['has_readme'] is True

    @patch('pathlib.Path.exists', side_effect=lambda: True)
    @patch('pathlib.Path.iterdir', return_value=[])
    def test_detects_python_project_indicators(self, mock_iterdir, mock_exists):
        """Should detect requirements.txt and pyproject.toml."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        def exists_side_effect(self):
            filename = str(self).split('\\')[-1].split('/')[-1]
            return filename in ['requirements.txt', 'pyproject.toml']

        with patch.object(Path, 'exists', exists_side_effect):
            structure = analyzer._analyze_structure(Path('/test'), {'python': []})

        assert structure['has_requirements'] is True
        assert structure['has_pyproject'] is True

    @patch('pathlib.Path.iterdir')
    @patch('pathlib.Path.exists', return_value=False)
    def test_lists_top_level_directories(self, mock_exists, mock_iterdir):
        """Should list non-hidden top-level directories."""
        mock_dir1 = MagicMock()
        mock_dir1.is_dir.return_value = True
        mock_dir1.name = 'src'

        mock_dir2 = MagicMock()
        mock_dir2.is_dir.return_value = True
        mock_dir2.name = 'tests'

        mock_hidden = MagicMock()
        mock_hidden.is_dir.return_value = True
        mock_hidden.name = '.hidden'

        mock_iterdir.return_value = [mock_dir1, mock_dir2, mock_hidden]

        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = analyzer._analyze_structure(Path('/test'), {})

        assert "src" in structure['directories']
        assert "tests" in structure['directories']
        assert ".hidden" not in structure['directories']


class TestGenerateCodebaseSummary:
    """Test LLM summary generation."""

    def test_generates_summary_via_llm(self):
        """Should call orchestrator.delegate to generate summary."""
        orchestrator = MagicMock()
        orchestrator.delegate.return_value = Mock(content="Generated summary text")

        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {
            'total_files': 10,
            'by_type': {'python': 5, 'config': 2},
            'directories': ['src', 'tests'],
            'has_readme': True,
            'has_requirements': True,
            'has_package_json': False,
            'has_pyproject': False,
            'has_git': True
        }

        contents = {'README.md': '# Test'}

        summary = analyzer._generate_codebase_summary(Path('/test'), structure, contents)

        # Should have called delegate
        orchestrator.delegate.assert_called_once()
        call_args = orchestrator.delegate.call_args
        # Check that prompt includes structure info
        prompt = call_args[0][1]
        assert "10" in prompt  # Total files
        assert "README.md" in prompt  # File content
        assert "Generated summary text" == summary

    def test_handles_llm_error_gracefully(self):
        """Should return error message when LLM fails."""
        orchestrator = MagicMock()
        orchestrator.delegate.side_effect = Exception("API error")

        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {
            'total_files': 5,
            'by_type': {},
            'directories': [],
            'has_readme': False,
            'has_requirements': False,
            'has_package_json': False,
            'has_pyproject': False,
            'has_git': False
        }
        contents = {}

        summary = analyzer._generate_codebase_summary(Path('/test'), structure, contents)

        # Should include error message and basic structure
        assert "Error generating summary" in summary
        assert "API error" in summary
        assert "Basic structure" in summary


class TestLazySummaryGeneration:
    """Test lazy summary generation behavior.

    LLM calls should only be made when user explicitly requests a summary,
    not during initial exploration.
    """

    def test_explore_displays_structure_without_llm_call(self, tmp_path):
        """Should display basic structure without making LLM call."""
        # Create test project structure
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "README.md").write_text("# Test Project")

        orchestrator = MagicMock()
        orchestrator.context.project_path = tmp_path
        orchestrator.context.explore.return_value = {
            'status': 'explored',
            'total_files': 2,
            'file_types': {'python': 1, 'docs': 1},
            'directories': ['src', 'tests'],
            'has_readme': True,
            'has_git': False,
        }

        io = MockIO(confirmations=[False])  # User declines summary generation

        analyzer = CLICodebaseAnalysis(orchestrator, io)
        analyzer.explore_codebase(str(tmp_path))

        # Should call explore() but NOT generate_summary()
        orchestrator.context.explore.assert_called_once()
        orchestrator.context.generate_summary.assert_not_called()
        orchestrator.delegate.assert_not_called()

        # Should show structure info
        output = io.get_output()
        assert "Codebase Structure" in output
        assert "Total files" in output

    def test_llm_called_only_when_user_confirms_summary(self, tmp_path):
        """Should call LLM only when user confirms summary generation."""
        (tmp_path / "main.py").write_text("# main")

        orchestrator = MagicMock()
        orchestrator.context.project_path = tmp_path
        orchestrator.context.explore.return_value = {
            'status': 'explored',
            'total_files': 1,
            'file_types': {'python': 1},
            'directories': [],
        }
        orchestrator.context.generate_summary.return_value = "Generated summary"

        io = MockIO(confirmations=[True, False])  # Yes to summary, No to save

        analyzer = CLICodebaseAnalysis(orchestrator, io)
        analyzer.explore_codebase(str(tmp_path))

        # Should call generate_summary when user confirms
        orchestrator.context.generate_summary.assert_called_once()

        # Should display the summary
        output = io.get_output()
        assert "Generated summary" in output

    def test_save_option_not_shown_when_summary_declined(self, tmp_path):
        """Should not offer save option when user declines summary."""
        (tmp_path / "main.py").write_text("# main")

        orchestrator = MagicMock()
        orchestrator.context.project_path = tmp_path
        orchestrator.context.explore.return_value = {
            'status': 'explored',
            'total_files': 1,
            'file_types': {'python': 1},
            'directories': [],
        }

        io = MockIO(confirmations=[False])  # Decline summary generation

        analyzer = CLICodebaseAnalysis(orchestrator, io)
        analyzer.explore_codebase(str(tmp_path))

        # Should only ask one question (summary generation)
        # confirm_index tracks how many confirms were processed
        assert io._confirm_index == 1

    def test_external_directory_lazy_summary(self, tmp_path):
        """Should use lazy summary for external directories too."""
        external_path = tmp_path / "external"
        external_path.mkdir()
        (external_path / "app.py").write_text("# app")

        orchestrator = MagicMock()
        orchestrator.context.project_path = tmp_path  # Different from external_path

        io = MockIO(confirmations=[False])  # Decline summary

        analyzer = CLICodebaseAnalysis(orchestrator, io)
        analyzer.explore_codebase(str(external_path))

        # Should NOT call _generate_codebase_summary (LLM)
        orchestrator.delegate.assert_not_called()

        # Should show structure
        output = io.get_output()
        assert "Codebase Structure" in output


class TestDisplayBasicStructure:
    """Test the basic structure display helper."""

    def test_displays_total_files(self):
        """Should display total file count."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {'total_files': 42, 'directories': []}
        analyzer._display_basic_structure(structure, Path('/test'))

        output = io.get_output()
        assert "42" in output

    def test_displays_file_types(self):
        """Should display file type breakdown."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {
            'total_files': 10,
            'by_type': {'python': 5, 'javascript': 3, 'config': 2},
            'directories': [],
        }
        analyzer._display_basic_structure(structure, Path('/test'))

        output = io.get_output()
        assert "python" in output.lower()
        assert "5" in output

    def test_displays_directories(self):
        """Should display top-level directories."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {
            'total_files': 10,
            'directories': ['src', 'tests', 'docs'],
        }
        analyzer._display_basic_structure(structure, Path('/test'))

        output = io.get_output()
        assert "src" in output
        assert "tests" in output

    def test_displays_project_markers(self):
        """Should display detected project markers."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {
            'total_files': 10,
            'directories': [],
            'has_readme': True,
            'has_pyproject': True,
            'has_git': True,
        }
        analyzer._display_basic_structure(structure, Path('/test'))

        output = io.get_output()
        assert "README" in output
        assert "pyproject.toml" in output
        assert "git" in output.lower()

    def test_handles_many_directories(self):
        """Should truncate directory list when too many."""
        orchestrator = MagicMock()
        io = MockIO()
        analyzer = CLICodebaseAnalysis(orchestrator, io)

        structure = {
            'total_files': 100,
            'directories': [f'dir{i}' for i in range(15)],
        }
        analyzer._display_basic_structure(structure, Path('/test'))

        output = io.get_output()
        assert "dir0" in output
        assert "dir9" in output
        assert "5 more" in output  # Should indicate truncation
