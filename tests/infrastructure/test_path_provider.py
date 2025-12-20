"""
Tests for PathProvider implementations.

Tests user-level vs project-level paths and rate limits migration.
"""

import json
import pytest
from pathlib import Path

from scrappy.infrastructure.paths import ScrappyPathProvider, TempPathProvider


class TestScrappyPathProviderUserDir:
    """Tests for user-level directory support."""

    def test_user_data_dir_is_home_scrappy(self, tmp_path: Path):
        """User data dir should be ~/.scrappy/."""
        provider = ScrappyPathProvider(tmp_path)
        assert provider.user_data_dir() == Path.home() / ".scrappy"

    def test_data_dir_is_project_scrappy(self, tmp_path: Path):
        """Data dir should be project/.scrappy/."""
        provider = ScrappyPathProvider(tmp_path)
        assert provider.data_dir() == tmp_path / ".scrappy"

    def test_rate_limits_file_is_user_level(self, tmp_path: Path):
        """Rate limits file should be in user dir, not project dir."""
        provider = ScrappyPathProvider(tmp_path)
        rate_limits = provider.rate_limits_file()

        assert rate_limits == Path.home() / ".scrappy" / "rate_limits.json"
        assert rate_limits.parent == provider.user_data_dir()

    def test_session_file_is_project_level(self, tmp_path: Path):
        """Session file should remain in project dir."""
        provider = ScrappyPathProvider(tmp_path)
        session = provider.session_file()

        assert session == tmp_path / ".scrappy" / "session.json"
        assert session.parent == provider.data_dir()


class TestScrappyPathProviderMigration:
    """Tests for rate limits migration from project to user level."""

    def test_migration_copies_project_to_user(self, tmp_path: Path, monkeypatch):
        """Migration should copy project-level rate_limits.json to user level."""
        # Set up fake home directory for isolation
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_scrappy = project_root / ".scrappy"
        project_scrappy.mkdir()

        # Create project-level rate limits
        project_rate_limits = project_scrappy / "rate_limits.json"
        rate_data = {"gemini-2.0-flash": {"rpm_limit": 100}}
        project_rate_limits.write_text(json.dumps(rate_data))

        # Create provider and trigger migration
        provider = ScrappyPathProvider(project_root)
        provider.ensure_user_dir()

        # Check user-level file was created
        user_rate_limits = fake_home / ".scrappy" / "rate_limits.json"
        assert user_rate_limits.exists()
        assert json.loads(user_rate_limits.read_text()) == rate_data

    def test_migration_deletes_project_level(self, tmp_path: Path, monkeypatch):
        """Migration should delete project-level file after copying."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_scrappy = project_root / ".scrappy"
        project_scrappy.mkdir()

        # Create project-level rate limits
        project_rate_limits = project_scrappy / "rate_limits.json"
        project_rate_limits.write_text("{}")

        provider = ScrappyPathProvider(project_root)
        provider.ensure_user_dir()

        # Project-level file should be deleted
        assert not project_rate_limits.exists()

    def test_migration_skips_if_user_exists(self, tmp_path: Path, monkeypatch):
        """Migration should not overwrite existing user-level file."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_scrappy = project_root / ".scrappy"
        project_scrappy.mkdir()

        # Create project-level rate limits with old data
        project_rate_limits = project_scrappy / "rate_limits.json"
        project_rate_limits.write_text('{"old": "data"}')

        # Create user-level rate limits with newer data
        user_scrappy = fake_home / ".scrappy"
        user_scrappy.mkdir()
        user_rate_limits = user_scrappy / "rate_limits.json"
        user_rate_limits.write_text('{"new": "data"}')

        provider = ScrappyPathProvider(project_root)
        provider.ensure_user_dir()

        # User-level should be unchanged
        assert json.loads(user_rate_limits.read_text()) == {"new": "data"}
        # Project-level should still exist (not migrated)
        assert project_rate_limits.exists()

    def test_migration_skips_if_no_project_file(self, tmp_path: Path, monkeypatch):
        """Migration should do nothing if no project-level file exists."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_scrappy = project_root / ".scrappy"
        project_scrappy.mkdir()
        # No rate_limits.json created

        provider = ScrappyPathProvider(project_root)
        provider.ensure_user_dir()

        # User dir should exist but no rate limits file
        assert (fake_home / ".scrappy").exists()
        assert not (fake_home / ".scrappy" / "rate_limits.json").exists()


class TestTempPathProviderUserDir:
    """Tests for TempPathProvider user directory support."""

    def test_user_data_dir_is_isolated(self, tmp_path: Path):
        """User data dir should be separate from project dir for isolation."""
        provider = TempPathProvider(tmp_path)

        assert provider.user_data_dir() == tmp_path / ".scrappy_user"
        assert provider.data_dir() == tmp_path / ".scrappy"
        assert provider.user_data_dir() != provider.data_dir()

    def test_rate_limits_file_uses_user_dir(self, tmp_path: Path):
        """Rate limits should be in user dir."""
        provider = TempPathProvider(tmp_path)

        rate_limits = provider.rate_limits_file()
        assert rate_limits.parent == provider.user_data_dir()

    def test_ensure_user_dir_creates_directory(self, tmp_path: Path):
        """ensure_user_dir should create the user directory."""
        provider = TempPathProvider(tmp_path)

        assert not provider.user_data_dir().exists()
        provider.ensure_user_dir()
        assert provider.user_data_dir().exists()
