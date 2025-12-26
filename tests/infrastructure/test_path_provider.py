"""
Tests for PathProvider implementations.

Tests user-level vs project-level paths and rate limits migration.
Uses platformdirs for cross-platform XDG-compliant paths.
"""

import json
from pathlib import Path

from platformdirs import user_data_dir

from scrappy.infrastructure.paths import ScrappyPathProvider, TempPathProvider


class TestScrappyPathProviderUserDir:
    """Tests for user-level directory support."""

    def test_user_data_dir_uses_platformdirs(self, tmp_path: Path):
        """User data dir should use platformdirs for cross-platform paths."""
        provider = ScrappyPathProvider(tmp_path)
        expected = Path(user_data_dir("scrappy"))
        assert provider.user_data_dir() == expected

    def test_data_dir_is_project_scrappy(self, tmp_path: Path):
        """Data dir should be project/.scrappy/."""
        provider = ScrappyPathProvider(tmp_path)
        assert provider.data_dir() == tmp_path / ".scrappy"

    def test_rate_limits_file_is_user_level(self, tmp_path: Path):
        """Rate limits file should be in user dir, not project dir."""
        provider = ScrappyPathProvider(tmp_path)
        rate_limits = provider.rate_limits_file()

        assert rate_limits == provider.user_data_dir() / "rate_limits.json"
        assert rate_limits.parent == provider.user_data_dir()

    def test_session_file_is_project_level(self, tmp_path: Path):
        """Session file should remain in project dir."""
        provider = ScrappyPathProvider(tmp_path)
        session = provider.session_file()

        assert session == tmp_path / ".scrappy" / "session.json"
        assert session.parent == provider.data_dir()

    def test_user_config_dir_uses_platformdirs(self, tmp_path: Path):
        """User config dir should use platformdirs."""
        from platformdirs import user_config_dir as pd_user_config_dir
        provider = ScrappyPathProvider(tmp_path)
        expected = Path(pd_user_config_dir("scrappy"))
        assert provider.user_config_dir() == expected

    def test_user_cache_dir_uses_platformdirs(self, tmp_path: Path):
        """User cache dir should use platformdirs."""
        from platformdirs import user_cache_dir as pd_user_cache_dir
        provider = ScrappyPathProvider(tmp_path)
        expected = Path(pd_user_cache_dir("scrappy"))
        assert provider.user_cache_dir() == expected


class TestScrappyPathProviderMigration:
    """Tests for rate limits migration from project to user level."""

    def test_migration_copies_project_to_user(self, tmp_path: Path, monkeypatch):
        """Migration should copy project-level rate_limits.json to user level."""
        # Set up fake directories for platformdirs
        fake_user_dir = tmp_path / "fake_user_data"
        fake_config_dir = tmp_path / "fake_config"
        fake_cache_dir = tmp_path / "fake_cache"
        fake_legacy_dir = tmp_path / "fake_legacy"  # Non-existent legacy dir

        import scrappy.infrastructure.paths as paths_module
        monkeypatch.setattr(paths_module, "user_data_dir", lambda app: str(fake_user_dir))
        monkeypatch.setattr(paths_module, "user_config_dir", lambda app: str(fake_config_dir))
        monkeypatch.setattr(paths_module, "user_cache_dir", lambda app: str(fake_cache_dir))
        monkeypatch.setattr(paths_module, "LEGACY_USER_DIR", fake_legacy_dir)

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
        user_rate_limits = fake_user_dir / "rate_limits.json"
        assert user_rate_limits.exists()
        assert json.loads(user_rate_limits.read_text()) == rate_data

    def test_migration_deletes_project_level(self, tmp_path: Path, monkeypatch):
        """Migration should delete project-level file after copying."""
        fake_user_dir = tmp_path / "fake_user_data"
        fake_config_dir = tmp_path / "fake_config"
        fake_cache_dir = tmp_path / "fake_cache"
        fake_legacy_dir = tmp_path / "fake_legacy"

        import scrappy.infrastructure.paths as paths_module
        monkeypatch.setattr(paths_module, "user_data_dir", lambda app: str(fake_user_dir))
        monkeypatch.setattr(paths_module, "user_config_dir", lambda app: str(fake_config_dir))
        monkeypatch.setattr(paths_module, "user_cache_dir", lambda app: str(fake_cache_dir))
        monkeypatch.setattr(paths_module, "LEGACY_USER_DIR", fake_legacy_dir)

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
        fake_user_dir = tmp_path / "fake_user_data"
        fake_config_dir = tmp_path / "fake_config"
        fake_cache_dir = tmp_path / "fake_cache"
        fake_legacy_dir = tmp_path / "fake_legacy"
        fake_user_dir.mkdir()

        import scrappy.infrastructure.paths as paths_module
        monkeypatch.setattr(paths_module, "user_data_dir", lambda app: str(fake_user_dir))
        monkeypatch.setattr(paths_module, "user_config_dir", lambda app: str(fake_config_dir))
        monkeypatch.setattr(paths_module, "user_cache_dir", lambda app: str(fake_cache_dir))
        monkeypatch.setattr(paths_module, "LEGACY_USER_DIR", fake_legacy_dir)

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_scrappy = project_root / ".scrappy"
        project_scrappy.mkdir()

        # Create project-level rate limits with old data
        project_rate_limits = project_scrappy / "rate_limits.json"
        project_rate_limits.write_text('{"old": "data"}')

        # Create user-level rate limits with newer data
        user_rate_limits = fake_user_dir / "rate_limits.json"
        user_rate_limits.write_text('{"new": "data"}')

        provider = ScrappyPathProvider(project_root)
        provider.ensure_user_dir()

        # User-level should be unchanged
        assert json.loads(user_rate_limits.read_text()) == {"new": "data"}
        # Project-level should still exist (not migrated)
        assert project_rate_limits.exists()

    def test_migration_skips_if_no_project_file(self, tmp_path: Path, monkeypatch):
        """Migration should do nothing if no project-level file exists."""
        fake_user_dir = tmp_path / "fake_user_data"
        fake_config_dir = tmp_path / "fake_config"
        fake_cache_dir = tmp_path / "fake_cache"
        fake_legacy_dir = tmp_path / "fake_legacy"

        import scrappy.infrastructure.paths as paths_module
        monkeypatch.setattr(paths_module, "user_data_dir", lambda app: str(fake_user_dir))
        monkeypatch.setattr(paths_module, "user_config_dir", lambda app: str(fake_config_dir))
        monkeypatch.setattr(paths_module, "user_cache_dir", lambda app: str(fake_cache_dir))
        monkeypatch.setattr(paths_module, "LEGACY_USER_DIR", fake_legacy_dir)

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_scrappy = project_root / ".scrappy"
        project_scrappy.mkdir()
        # No rate_limits.json created

        provider = ScrappyPathProvider(project_root)
        provider.ensure_user_dir()

        # User dir should exist but no rate limits file
        assert fake_user_dir.exists()
        assert not (fake_user_dir / "rate_limits.json").exists()


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

    def test_user_config_dir_is_isolated(self, tmp_path: Path):
        """User config dir should be separate temp directory."""
        provider = TempPathProvider(tmp_path)
        assert provider.user_config_dir() == tmp_path / ".scrappy_config"

    def test_user_cache_dir_is_isolated(self, tmp_path: Path):
        """User cache dir should be separate temp directory."""
        provider = TempPathProvider(tmp_path)
        assert provider.user_cache_dir() == tmp_path / ".scrappy_cache"

    def test_ensure_user_dir_creates_all_directories(self, tmp_path: Path):
        """ensure_user_dir should create all user directories."""
        provider = TempPathProvider(tmp_path)

        provider.ensure_user_dir()

        assert provider.user_data_dir().exists()
        assert provider.user_config_dir().exists()
        assert provider.user_cache_dir().exists()


class TestScrappyPathProviderWorkspace:
    """Tests for workspace_display() method."""

    def test_project_root_returns_project_path(self, tmp_path: Path):
        """project_root() should return the project root path."""
        provider = ScrappyPathProvider(tmp_path)
        assert provider.project_root() == tmp_path

    def test_workspace_display_uses_forward_slashes(self, tmp_path: Path):
        """workspace_display() should use forward slashes on all platforms."""
        provider = ScrappyPathProvider(tmp_path)
        display = provider.workspace_display()
        assert "\\" not in display

    def test_workspace_display_substitutes_home(self, tmp_path: Path, monkeypatch):
        """workspace_display() should substitute ~ for home directory."""
        # Create a fake home directory structure
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        project = fake_home / "projects" / "myapp"
        project.mkdir(parents=True)

        # Monkeypatch Path.home() to return our fake home
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        provider = ScrappyPathProvider(project)
        display = provider.workspace_display()

        assert display == "~/projects/myapp"

    def test_workspace_display_handles_path_outside_home(self, tmp_path: Path, monkeypatch):
        """workspace_display() should return full path when outside home."""
        # Create a fake home directory that doesn't contain the project
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        project = tmp_path / "other_location" / "myapp"
        project.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        provider = ScrappyPathProvider(project)
        display = provider.workspace_display()

        # Should not start with ~ since it's outside home
        assert not display.startswith("~")
        assert "myapp" in display


class TestTempPathProviderWorkspace:
    """Tests for TempPathProvider workspace methods."""

    def test_project_root_returns_temp_dir(self, tmp_path: Path):
        """project_root() should return the temp directory."""
        provider = TempPathProvider(tmp_path)
        assert provider.project_root() == tmp_path

    def test_workspace_display_uses_forward_slashes(self, tmp_path: Path):
        """workspace_display() should use forward slashes."""
        provider = TempPathProvider(tmp_path)
        display = provider.workspace_display()
        assert "\\" not in display
