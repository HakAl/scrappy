"""
Tests for GitHistoryReader - git repository history extraction.

TDD: These tests define the expected behavior for the GitHistoryReader class
that will be extracted from CodebaseContext.
"""
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGitHistoryReaderBasics:
    """Basic GitHistoryReader functionality tests."""

    pass

class TestGitHistoryReaderWithMocks:
    """Tests using mocked subprocess calls for isolation."""

    @pytest.fixture
    def mock_subprocess_run(self):
        """Create a mock for subprocess.run."""
        with patch('subprocess.run') as mock_run:
            yield mock_run

    @pytest.mark.unit
    def test_gets_recent_commits(self, temp_project_dir, mock_subprocess_run):
        """Should extract recent commits from git log."""
        from src.context.git_history import GitHistoryReader

        # Mock git log output
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 Initial commit\ndef5678 Add feature\n"
        mock_subprocess_run.return_value = mock_result

        reader = GitHistoryReader()
        result = reader.get_history(temp_project_dir)

        assert 'recent_commits' in result
        assert len(result['recent_commits']) == 2
        assert 'Initial commit' in result['recent_commits'][0]

    @pytest.mark.unit
    def test_gets_current_branch(self, temp_project_dir, mock_subprocess_run):
        """Should extract current branch name."""
        from src.context.git_history import GitHistoryReader

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"
        mock_subprocess_run.return_value = mock_result

        reader = GitHistoryReader()
        result = reader.get_history(temp_project_dir)

        assert 'current_branch' in result
        assert result['current_branch'] == 'main'

    @pytest.mark.unit
    def test_gets_branches_list(self, temp_project_dir, mock_subprocess_run):
        """Should extract list of branches."""
        from src.context.git_history import GitHistoryReader

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "* main\n  feature/auth\n  develop\n"
        mock_subprocess_run.return_value = mock_result

        reader = GitHistoryReader()
        result = reader.get_history(temp_project_dir)

        assert 'branches' in result
        # Should strip asterisk and whitespace
        assert 'main' in result['branches']

    @pytest.mark.unit
    def test_gets_top_contributors(self, temp_project_dir, mock_subprocess_run):
        """Should extract top contributors."""
        from src.context.git_history import GitHistoryReader

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "    42\tJohn Doe\n    15\tJane Smith\n"
        mock_subprocess_run.return_value = mock_result

        reader = GitHistoryReader()
        result = reader.get_history(temp_project_dir)

        assert 'top_contributors' in result
        contributors = result['top_contributors']
        assert len(contributors) >= 1
        # Check structure
        assert 'name' in contributors[0]
        assert 'commits' in contributors[0]

    @pytest.mark.unit
    def test_gets_recently_changed_files(self, temp_project_dir, mock_subprocess_run):
        """Should extract recently changed files."""
        from src.context.git_history import GitHistoryReader

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/main.py\ntests/test_main.py\nREADME.md\n"
        mock_subprocess_run.return_value = mock_result

        reader = GitHistoryReader()
        result = reader.get_history(temp_project_dir)

        assert 'recently_changed_files' in result
        changed = result['recently_changed_files']
        assert 'src/main.py' in changed or any('main.py' in f for f in changed)

    @pytest.mark.unit
    def test_gets_first_commit_date(self, temp_project_dir, mock_subprocess_run):
        """Should extract first commit date (repository age)."""
        from src.context.git_history import GitHistoryReader

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "2024-01-15 10:30:00 -0500\n"
        mock_subprocess_run.return_value = mock_result

        reader = GitHistoryReader()
        result = reader.get_history(temp_project_dir)

        assert 'first_commit_date' in result
        assert '2024' in result['first_commit_date']


class TestGitHistoryReaderEdgeCases:
    """Edge cases and error handling tests."""

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit

    @pytest.mark.unit
    def test_limits_recent_commits_to_20(self, temp_project_dir):
        """Should limit recent commits to 20."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            # Generate 30 commits
            commits = "\n".join([f"hash{i} Commit {i}" for i in range(30)])
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = commits
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            result = reader.get_history(temp_project_dir)

            if 'recent_commits' in result:
                assert len(result['recent_commits']) <= 20

    @pytest.mark.unit
    def test_limits_branches_to_10(self, temp_project_dir):
        """Should limit branches to 10."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            # Generate 20 branches
            branches = "\n".join([f"  branch{i}" for i in range(20)])
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = branches
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            result = reader.get_history(temp_project_dir)

            if 'branches' in result:
                assert len(result['branches']) <= 10

    @pytest.mark.unit
    def test_limits_contributors_to_5(self, temp_project_dir):
        """Should limit contributors to top 5."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            # Generate 10 contributors
            contribs = "\n".join([f"    {i*10}\tDeveloper{i}" for i in range(10, 0, -1)])
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = contribs
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            result = reader.get_history(temp_project_dir)

            if 'top_contributors' in result:
                assert len(result['top_contributors']) <= 5

    @pytest.mark.unit
    def test_limits_changed_files_to_20(self, temp_project_dir):
        """Should limit recently changed files to 20."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            # Generate 30 files
            files = "\n".join([f"src/file{i}.py" for i in range(30)])
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = files
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            result = reader.get_history(temp_project_dir)

            if 'recently_changed_files' in result:
                assert len(result['recently_changed_files']) <= 20

    @pytest.mark.unit
    def test_deduplicates_changed_files(self, temp_project_dir):
        """Should deduplicate recently changed files."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            # Same file appears multiple times
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "src/main.py\nsrc/main.py\nsrc/main.py\n"
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            result = reader.get_history(temp_project_dir)

            if 'recently_changed_files' in result:
                # Should be deduplicated
                assert result['recently_changed_files'].count('src/main.py') == 1


class TestGitHistoryReaderIntegration:
    """Integration tests with actual git repository."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository with some history."""
        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=tmp_path, capture_output=True
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test User'],
            cwd=tmp_path, capture_output=True
        )

        # Create initial commit
        (tmp_path / 'README.md').write_text('# Test Project\n')
        subprocess.run(['git', 'add', '.'], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'Initial commit'],
            cwd=tmp_path, capture_output=True
        )

        # Create second commit
        (tmp_path / 'main.py').write_text('print("Hello")\n')
        subprocess.run(['git', 'add', '.'], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'Add main.py'],
            cwd=tmp_path, capture_output=True
        )

        return tmp_path

    @pytest.mark.integration
    def test_reads_actual_git_history(self, git_repo):
        """Should read actual git history from a real repo."""
        from src.context.git_history import GitHistoryReader

        reader = GitHistoryReader()
        result = reader.get_history(git_repo)

        # Should have commits
        assert 'recent_commits' in result
        assert len(result['recent_commits']) >= 2

    @pytest.mark.integration
    def test_finds_current_branch(self, git_repo):
        """Should find the current branch in a real repo."""
        from src.context.git_history import GitHistoryReader

        reader = GitHistoryReader()
        result = reader.get_history(git_repo)

        assert 'current_branch' in result
        # Default branch is typically 'main' or 'master'
        assert result['current_branch'] in ('main', 'master')

    @pytest.mark.integration
    def test_finds_contributors(self, git_repo):
        """Should find contributors in a real repo."""
        from src.context.git_history import GitHistoryReader

        reader = GitHistoryReader()
        result = reader.get_history(git_repo)

        assert 'top_contributors' in result
        # Should have at least our test user
        assert len(result['top_contributors']) >= 1
        assert result['top_contributors'][0]['name'] == 'Test User'

    @pytest.mark.integration
    def test_finds_changed_files(self, git_repo):
        """Should find recently changed files in a real repo."""
        from src.context.git_history import GitHistoryReader

        reader = GitHistoryReader()
        result = reader.get_history(git_repo)

        # May or may not have this depending on git version/output
        if 'recently_changed_files' in result:
            # Should include our files
            all_files = ' '.join(result['recently_changed_files'])
            assert 'main.py' in all_files or 'README' in all_files


class TestGitHistoryReaderWithCodebaseContext:
    """Tests for GitHistoryReader integration with CodebaseContext."""

    @pytest.fixture
    def git_project(self, tmp_path):
        """Create a project with git initialization."""
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=tmp_path, capture_output=True
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test User'],
            cwd=tmp_path, capture_output=True
        )

        (tmp_path / 'README.md').write_text('# Project\n')
        subprocess.run(['git', 'add', '.'], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'Initial'],
            cwd=tmp_path, capture_output=True
        )

        return tmp_path

    @pytest.mark.integration

    @pytest.mark.integration
    def test_codebase_context_git_history_has_expected_fields(self, git_project):
        """CodebaseContext git_history should have expected fields."""
        from src.context import CodebaseContext

        context = CodebaseContext(str(git_project))
        context.explore()

        # Should have at least some of these fields
        possible_fields = [
            'recent_commits', 'current_branch', 'branches',
            'top_contributors', 'recently_changed_files', 'first_commit_date'
        ]
        has_some_fields = any(
            field in context.git_history for field in possible_fields
        )
        assert has_some_fields, f"git_history has none of expected fields: {context.git_history}"


class TestGitHistoryReaderTimeouts:
    """Tests for timeout handling."""

    @pytest.mark.unit
    def test_uses_timeout_for_subprocess_calls(self, temp_project_dir):
        """Should use timeout for all subprocess calls."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "test\n"
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            _ = reader.get_history(temp_project_dir)

            # All calls should have timeout parameter
            for call in mock_run.call_args_list:
                _, kwargs = call
                assert 'timeout' in kwargs
                assert kwargs['timeout'] > 0

    @pytest.mark.unit
    def test_default_timeout_is_reasonable(self, temp_project_dir):
        """Default timeout should be reasonable (e.g., 10 seconds)."""
        from src.context.git_history import GitHistoryReader

        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "test\n"
            mock_run.return_value = mock_result

            reader = GitHistoryReader()
            _ = reader.get_history(temp_project_dir)

            # Check timeout value
            for call in mock_run.call_args_list:
                _, kwargs = call
                # Should be between 5-30 seconds
                assert 5 <= kwargs['timeout'] <= 30
