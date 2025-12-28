"""
Comprehensive tests for src/agent/checkpoint.py

Tests git checkpoint creation and rollback functionality with mocked subprocess calls.
Includes security tests for command injection prevention.
"""

import subprocess
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import pytest

from scrappy.agent.checkpoint import (
    create_git_checkpoint,
    rollback_to_checkpoint,
    _is_valid_commit_hash,
)


class TestCommitHashValidation:
    """Test suite for commit hash validation (security feature)."""

    def test_valid_7_char_hash(self):
        """Test valid 7-character short hash."""
        assert _is_valid_commit_hash("abc1234") is True

    def test_valid_40_char_hash(self):
        """Test valid 40-character full hash."""
        assert _is_valid_commit_hash("abc123def456abc123def456abc123def456abc1") is True

    def test_invalid_hash_with_uppercase(self):
        """Test that uppercase letters fail (git uses lowercase)."""
        assert _is_valid_commit_hash("ABC1234") is False

    def test_invalid_hash_too_short(self):
        """Test that hash shorter than 7 chars fails."""
        assert _is_valid_commit_hash("abc123") is False

    def test_invalid_hash_too_long(self):
        """Test that hash longer than 40 chars fails."""
        assert _is_valid_commit_hash("a" * 41) is False

    def test_invalid_hash_with_special_chars(self):
        """Test that special characters fail."""
        assert _is_valid_commit_hash("abc123; rm -rf /") is False
        assert _is_valid_commit_hash("abc123`echo foo`") is False
        assert _is_valid_commit_hash("abc123$(whoami)") is False

    def test_invalid_hash_with_spaces(self):
        """Test that spaces fail."""
        assert _is_valid_commit_hash("abc123 def456") is False

    def test_invalid_hash_with_newlines(self):
        """Test that newlines fail."""
        assert _is_valid_commit_hash("abc123\ndef456") is False

    def test_invalid_empty_string(self):
        """Test that empty string fails."""
        assert _is_valid_commit_hash("") is False

    def test_invalid_non_hex_chars(self):
        """Test that non-hex chars fail."""
        assert _is_valid_commit_hash("ghijklm") is False


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

            # Verify the calls were made with argument lists (no shell=True)
            for call in mock_run.call_args_list:
                # All calls should use shell=False (secure)
                assert call[1]["shell"] is False
                # All calls should pass args as a list
                assert isinstance(call[0][0], list)

    def test_create_checkpoint_not_git_repo(self):
        """Test checkpoint creation when not in a git repository."""
        with patch('subprocess.run') as mock_run:
            # First call: git rev-parse --is-inside-work-tree (failure)
            mock_run.return_value = Mock(returncode=1)

            result = create_git_checkpoint()

            assert result is None
            assert mock_run.call_count == 1
            mock_run.assert_called_with(
                ["git", "rev-parse", "--is-inside-work-tree"],
                shell=False,
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
                ["git", "reset", "--hard", commit_hash],
                shell=False,
                cwd=".",
                capture_output=True,
                text=True
            )

    def test_rollback_custom_path(self):
        """Test rollback with custom project path."""
        commit_hash = "def456abc789def1"  # Valid hex hash
        custom_path = "/custom/project/path"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            result = rollback_to_checkpoint(commit_hash, custom_path)

            assert result is True
            mock_run.assert_called_once_with(
                ["git", "reset", "--hard", "def456abc789def1"],
                shell=False,
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

    def test_rollback_invalid_commit_hash_raises_valueerror(self):
        """Test rollback with invalid commit hash raises ValueError."""
        invalid_hash = "invalid-hash-format"

        # Should raise ValueError before even calling subprocess
        with pytest.raises(ValueError, match="Invalid commit hash"):
            rollback_to_checkpoint(invalid_hash)

    def test_rollback_command_injection_prevented(self):
        """Test that command injection via commit hash is prevented."""
        malicious_hashes = [
            "abc123; rm -rf /",  # Shell command chaining
            "abc123`whoami`",  # Backtick command substitution
            "abc123$(cat /etc/passwd)",  # Dollar command substitution
            "abc123 --help",  # Argument injection
            "abc123\n--help",  # Newline injection
        ]

        for malicious_hash in malicious_hashes:
            with pytest.raises(ValueError, match="Invalid commit hash"):
                rollback_to_checkpoint(malicious_hash)


class TestCheckpointIntegration:
    """Integration tests for checkpoint operations."""

    def test_full_checkpoint_lifecycle(self):
        """Test complete checkpoint creation and rollback workflow."""
        mock_commit_hash = "abc123def456abc1"  # Valid 16-char hex hash

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
        mock_commit_hash = "abc123def456abc1"  # Valid hex hash

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
        valid_hash = "abc123def456abc1"  # Valid hex hash

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = exception_type

            result = rollback_to_checkpoint(valid_hash)

            assert result is False

    def test_empty_commit_hash(self):
        """Test behavior with empty commit hash raises ValueError."""
        # Empty hash should raise ValueError (security validation)
        with pytest.raises(ValueError, match="Invalid commit hash"):
            rollback_to_checkpoint("")

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
    """Tests to validate git command construction (security: no shell=True)."""

    def test_checkpoint_command_structure(self):
        """Test that git commands are properly structured as lists."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),  # git rev-parse --is-inside-work-tree
                Mock(returncode=0),  # git add -A
                Mock(returncode=0),  # git commit
                Mock(returncode=0, stdout="abc123def456abc1\n")  # git rev-parse HEAD
            ]

            create_git_checkpoint()

            # Verify command structure
            calls = mock_run.call_args_list

            # First call should be git repository check - as a list
            assert calls[0][0][0] == ["git", "rev-parse", "--is-inside-work-tree"]

            # Second call should be git add - as a list
            assert calls[1][0][0] == ["git", "add", "-A"]

            # Third call should be git commit with message - as a list
            commit_args = calls[2][0][0]
            assert commit_args[0] == "git"
            assert commit_args[1] == "commit"
            assert commit_args[2] == "-m"
            assert commit_args[3].startswith("Agent checkpoint")
            assert commit_args[4] == "--allow-empty"

            # Fourth call should get commit hash - as a list
            assert calls[3][0][0] == ["git", "rev-parse", "HEAD"]

    def test_no_shell_in_any_command(self):
        """Test that all subprocess calls use shell=False."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="true\n"),
                Mock(returncode=0),
                Mock(returncode=0),
                Mock(returncode=0, stdout="abc123def456abc1\n")
            ]

            create_git_checkpoint()

            for call in mock_run.call_args_list:
                assert call[1]["shell"] is False, "All calls must use shell=False"



# Performance and edge case tests
class TestCheckpointPerformance:
    """Tests for performance and edge cases."""

    def test_multiple_checkpoints_same_session(self):
        """Test creating multiple checkpoints in same session."""
        # Use valid hex hashes (only a-f0-9)
        commit_hashes = ["abc1234def5678", "bcd2345efa6789", "cde3456fab7890"]

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
        # Use valid hex hash
        commit_hash = "abc123def456abc1"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Rollback multiple times
            results = []
            for _ in range(3):
                result = rollback_to_checkpoint(commit_hash)
                results.append(result)

            assert all(results)  # All rollbacks should succeed
            assert mock_run.call_count == 3