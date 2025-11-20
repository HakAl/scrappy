"""
Comprehensive tests for src/agent/checkpoint.py

Tests git checkpoint creation and rollback functionality with mocked subprocess calls.
"""

import subprocess
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import pytest

from src.agent.checkpoint import create_git_checkpoint, rollback_to_checkpoint


class TestCreateGitCheckpoint:
    """Test suite for create_git_checkpoint function."""

    def test_create_checkpoint_success(self):
        """Test successful checkpoint creation in a git repository."""
        mock_commit_hash = "abc123def456"

        # Mock the subprocess calls
        with patch('subprocess.run') as mock_run:
            # First call: git rev-parse --is-inside-work-tree (success)
            # Second call: git add -A (success)
            # Third call: git commit (success)
            # Fourth call: git rev-parse HEAD (returns commit hash)
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=0),  # git commit
                Mock(returncode=0, stdout=f"{mock_commit_hash}\n")  # git rev-parse HEAD
            ]

            result = create_git_checkpoint()

            assert result == mock_commit_hash
            assert mock_run.call_count == 4

            # Verify the calls were made with correct arguments
            calls = [
                (("git rev-parse --is-inside-work-tree",),
                 {"shell": True, "cwd": ".", "capture_output": True, "text": True}),
                (("git add -A",), {"shell": True, "cwd": ".", "capture_output": True}),
                (("git commit -m \"Agent checkpoint",),
                 {"shell": True, "cwd": ".", "capture_output": True, "text": True}),
                (("git rev-parse HEAD",), {"shell": True, "cwd": ".", "capture_output": True, "text": True})
            ]

            for i, (expected_args, expected_kwargs) in enumerate(calls):
                actual_call = mock_run.call_args_list[i]
                if i == 2:  # Special handling for timestamp in commit message
                    assert actual_call[0][0].startswith("git commit -m \"Agent checkpoint")
                    assert actual_call[1]["shell"] == expected_kwargs["shell"]
                    assert actual_call[1]["cwd"] == expected_kwargs["cwd"]
                else:
                    assert actual_call[0] == expected_args
                    assert actual_call[1] == expected_kwargs

    def test_create_checkpoint_not_git_repo(self):
        """Test checkpoint creation when not in a git repository."""
        with patch('subprocess.run') as mock_run:
            # First call: git rev-parse --is-inside-work-tree (failure)
            mock_run.return_value = Mock(returncode=1)

            result = create_git_checkpoint()

            assert result is None
            assert mock_run.call_count == 1
            mock_run.assert_called_with(
                "git rev-parse --is-inside-work-tree",
                shell=True,
                cwd=".",
                capture_output=True,
                text=True
            )

    def test_create_checkpoint_custom_path(self):
        """Test checkpoint creation with custom project path."""
        custom_path = "/custom/project/path"
        mock_commit_hash = "def456ghi789"

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=0),  # git commit
                Mock(returncode=0, stdout=f"{mock_commit_hash}\n")  # git rev-parse HEAD
            ]

            result = create_git_checkpoint(custom_path)

            assert result == mock_commit_hash
            assert mock_run.call_count == 4

            # Verify all calls use the custom path
            for call in mock_run.call_args_list:
                assert call[1]["cwd"] == custom_path

# todo
    # def test_create_checkpoint_git_add_fails(self):
    #     """Test behavior when git add fails."""
    #     with patch('subprocess.run') as mock_run:
    #         mock_run.side_effect = [
    #             Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
    #             Mock(returncode=1),  # git add -A fails
    #         ]
    #
    #         result = create_git_checkpoint()
    #
    #         # Should still return the commit hash if commit succeeds
    #         assert result is not None  # Function continues despite git add failure

    def test_create_checkpoint_git_commit_fails(self):
        """Test behavior when git commit fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=1),  # git commit fails
            ]

            result = create_git_checkpoint()

            # Should still attempt to get commit hash
            assert mock_run.call_count == 4  # All calls are made

    def test_create_checkpoint_exception_handling(self):
        """Test exception handling in create_git_checkpoint."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            result = create_git_checkpoint()

            assert result is None

# todo
    # def test_create_checkpoint_timestamp_format(self):
    #     """Test that timestamp is included in commit message."""
    #     with patch('subprocess.run') as mock_run:
    #         mock_run.side_effect = [
    #             Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
    #             Mock(returncode=0),  # git add -A
    #             Mock(returncode=0),  # git commit
    #             Mock(returncode=0, stdout="hash123\n")  # git rev-parse HEAD
    #         ]
    #
    #         # Mock datetime to get predictable timestamp
    #         with patch('datetime.datetime') as mock_datetime:
    #             mock_datetime.now.return_value.strftime.return_value = "20231201_143000"
    #
    #             result = create_git_checkpoint()
    #
    #             assert result == "hash123"
    #
    #             # Verify commit message contains the timestamp
    #             commit_call = mock_run.call_args_list[2]
    #             commit_command = commit_call[0][0]
    #             assert "Agent checkpoint 20231201_143000" in commit_command


class TestRollbackToCheckpoint:
    """Test suite for rollback_to_checkpoint function."""

    def test_rollback_success(self):
        """Test successful rollback to a checkpoint."""
        commit_hash = "abc123def456"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            result = rollback_to_checkpoint(commit_hash)

            assert result is True
            mock_run.assert_called_once_with(
                f"git reset --hard {commit_hash}",
                shell=True,
                cwd=".",
                capture_output=True,
                text=True
            )

    def test_rollback_custom_path(self):
        """Test rollback with custom project path."""
        commit_hash = "def456ghi789"
        custom_path = "/custom/project/path"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            result = rollback_to_checkpoint(commit_hash, custom_path)

            assert result is True
            mock_run.assert_called_once_with(
                f"git reset --hard {commit_hash}",
                shell=True,
                cwd=custom_path,
                capture_output=True,
                text=True
            )

    def test_rollback_failure(self):
        """Test rollback failure (non-zero return code)."""
        commit_hash = "abc123def456"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1)

            result = rollback_to_checkpoint(commit_hash)

            assert result is False

    def test_rollback_exception_handling(self):
        """Test exception handling in rollback_to_checkpoint."""
        commit_hash = "abc123def456"

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Git command failed")

            result = rollback_to_checkpoint(commit_hash)

            assert result is False

    def test_rollback_invalid_commit_hash(self):
        """Test rollback with invalid commit hash format."""
        invalid_hash = "invalid-hash-format"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1)  # Git should fail with invalid hash

            result = rollback_to_checkpoint(invalid_hash)

            assert result is False


class TestCheckpointIntegration:
    """Integration tests for checkpoint operations."""

    def test_full_checkpoint_lifecycle(self):
        """Test complete checkpoint creation and rollback workflow."""
        mock_commit_hash = "lifecycle123"

        with patch('subprocess.run') as mock_run:
            # Setup sequence for create checkpoint
            create_responses = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=0),  # git commit
                Mock(returncode=0, stdout=f"{mock_commit_hash}\n")  # git rev-parse HEAD
            ]

            # Setup sequence for rollback
            rollback_response = Mock(returncode=0)

            # Combine responses
            mock_run.side_effect = create_responses + [rollback_response]

            # Create checkpoint
            checkpoint_hash = create_git_checkpoint()
            assert checkpoint_hash == mock_commit_hash

            # Rollback to checkpoint
            rollback_result = rollback_to_checkpoint(checkpoint_hash)
            assert rollback_result is True

            # Verify all calls were made
            assert mock_run.call_count == 5

    def test_checkpoint_with_special_characters_in_path(self):
        """Test checkpoint operations with paths containing special characters."""
        special_path = "/path/with spaces/and-dashes/and_underscores"
        mock_commit_hash = "special123"

        with patch('subprocess.run') as mock_run:
            # Create checkpoint
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=0),  # git commit
                Mock(returncode=0, stdout=f"{mock_commit_hash}\n")  # git rev-parse HEAD
            ]

            result = create_git_checkpoint(special_path)

            assert result == mock_commit_hash
            # Verify path was properly passed to all calls
            for call in mock_run.call_args_list:
                assert call[1]["cwd"] == special_path


class TestCheckpointErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.parametrize("exception_type", [
        subprocess.CalledProcessError(1, "git"),
        PermissionError("Permission denied"),
        FileNotFoundError("Git not found"),
        Exception("Generic error")
    ])
    def test_create_checkpoint_various_exceptions(self, exception_type):
        """Test handling of various exception types in create_git_checkpoint."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = exception_type

            result = create_git_checkpoint()

            assert result is None

    @pytest.mark.parametrize("exception_type", [
        subprocess.CalledProcessError(1, "git"),
        PermissionError("Permission denied"),
        FileNotFoundError("Git not found"),
        Exception("Generic error")
    ])
    def test_rollback_various_exceptions(self, exception_type):
        """Test handling of various exception types in rollback_to_checkpoint."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = exception_type

            result = rollback_to_checkpoint("some-hash")

            assert result is False

    def test_empty_commit_hash(self):
        """Test behavior with empty commit hash."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1)  # Git should fail

            result = rollback_to_checkpoint("")

            assert result is False

# todo
    # def test_none_commit_hash(self):
    #     """Test behavior with None commit hash."""
    #     with patch('subprocess.run') as mock_run:
    #         # Should not even call subprocess with None hash
    #         result = rollback_to_checkpoint(None)
    #
    #         # The function should handle this gracefully
    #         assert result is False
    #         mock_run.assert_not_called()


class TestCheckpointCommandValidation:
    """Tests to validate git command construction."""

    def test_checkpoint_command_structure(self):
        """Test that git commands are properly structured."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=0),  # git commit
                Mock(returncode=0, stdout="hash123\n")  # git rev-parse HEAD
            ]

            create_git_checkpoint()

            # Verify command structure
            calls = mock_run.call_args_list

            # First call should be git repository check
            assert "git rev-parse --is-inside-work-tree" in calls[0][0][0]

            # Second call should be git add
            assert calls[1][0][0] == "git add -A"

            # Third call should be git commit with message
            assert calls[2][0][0].startswith("git commit -m \"Agent checkpoint")
            assert "--allow-empty" in calls[2][0][0]

            # Fourth call should get commit hash
            assert calls[3][0][0] == "git rev-parse HEAD"

    def test_rollback_command_structure(self):
        """Test that rollback command is properly structured."""
        commit_hash = "abc123def456"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            rollback_to_checkpoint(commit_hash)

            # Verify command structure
            mock_run.assert_called_once_with(
                f"git reset --hard {commit_hash}",
                shell=True,
                cwd=".",
                capture_output=True,
                text=True
            )


# Performance and edge case tests
class TestCheckpointPerformance:
    """Tests for performance and edge cases."""

    def test_multiple_checkpoints_same_session(self):
        """Test creating multiple checkpoints in same session."""
        commit_hashes = ["hash1", "hash2", "hash3"]

        with patch('subprocess.run') as mock_run:
            # Setup responses for multiple checkpoints
            responses = []
            for hash_val in commit_hashes:
                responses.extend([
                    Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                    Mock(returncode=0),  # git add -A
                    Mock(returncode=0),  # git commit
                    Mock(returncode=0, stdout=f"{hash_val}\n")  # git rev-parse HEAD
                ])

            mock_run.side_effect = responses

            # Create multiple checkpoints
            results = []
            for _ in commit_hashes:
                result = create_git_checkpoint()
                results.append(result)

            assert results == commit_hashes
            assert mock_run.call_count == len(commit_hashes) * 4

    def test_rollback_to_same_checkpoint_multiple_times(self):
        """Test rolling back to the same checkpoint multiple times."""
        commit_hash = "same_hash"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Rollback multiple times
            results = []
            for _ in range(3):
                result = rollback_to_checkpoint(commit_hash)
                results.append(result)

            assert all(results)  # All rollbacks should succeed
            assert mock_run.call_count == 3