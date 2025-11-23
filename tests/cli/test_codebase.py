"""
Behavior tests for CLI codebase exploration functionality.

Tests actual behavior of codebase scanning, analysis, and summarization.
Focuses on:
- Path validation and error handling
- File scanning and categorization
- Structure analysis
- Summary generation
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open

from src.cli.codebase import CLICodebaseAnalysis
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
