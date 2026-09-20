"""
Tests for PathProvider implementations.

Tests user-level vs project-level paths and rate limits migration.
Uses platformdirs for cross-platform XDG-compliant paths.
"""

import json
from pathlib import Path

import pytest
from platformdirs import user_data_dir

import scrappy.infrastructure.paths as paths_module
from scrappy.infrastructure.paths import (
    ScrappyPathProvider,
    TempPathProvider,
    UserPaths,
    create_default_path_provider,
)


def disposable_user_paths(root: Path) -> UserPaths:
    """Build user paths under a disposable root.

    The legacy source is included here, so a test can never pair disposable
    destinations with the developer's real ~/.scrappy. The directories are
    NOT created; tests that need them on disk create them explicitly.
    """
    return UserPaths(
        user_data_dir=root / "fake_user_data",
        user_config_dir=root / "fake_config",
        user_cache_dir=root / "fake_cache",
        legacy_user_dir=root / "fake_legacy",
    )


class TestScrappyPathProviderUserDir:
    """Tests for user-level directory support."""

    def test_user_data_dir_uses_platformdirs(self, tmp_path: Path):
        """User data dir should use platformdirs for cross-platform paths."""
        provider = create_default_path_provider(tmp_path)
        expected = Path(user_data_dir("scrappy"))
        assert provider.user_data_dir() == expected

    def test_data_dir_is_project_scrappy(self, tmp_path: Path):
        """Data dir should be project/.scrappy/."""
        provider = create_default_path_provider(tmp_path)
        assert provider.data_dir() == tmp_path / ".scrappy"

    def test_rate_limits_file_is_user_level(self, tmp_path: Path):
        """Rate limits file should be in user dir, not project dir."""
        provider = create_default_path_provider(tmp_path)
        rate_limits = provider.rate_limits_file()

        assert rate_limits == provider.user_data_dir() / "rate_limits.json"
        assert rate_limits.parent == provider.user_data_dir()

    def test_session_file_is_project_level(self, tmp_path: Path):
        """Session file should remain in project dir."""
        provider = create_default_path_provider(tmp_path)
        session = provider.session_file()

        assert session == tmp_path / ".scrappy" / "session.json"
        assert session.parent == provider.data_dir()

    def test_user_config_dir_uses_platformdirs(self, tmp_path: Path):
        """User config dir should use platformdirs."""
        from platformdirs import user_config_dir as pd_user_config_dir
        provider = create_default_path_provider(tmp_path)
        expected = Path(pd_user_config_dir("scrappy"))
        assert provider.user_config_dir() == expected

    def test_user_cache_dir_uses_platformdirs(self, tmp_path: Path):
        """User cache dir should use platformdirs."""
        from platformdirs import user_cache_dir as pd_user_cache_dir
        provider = create_default_path_provider(tmp_path)
        expected = Path(pd_user_cache_dir("scrappy"))
        assert provider.user_cache_dir() == expected

    def test_user_paths_is_required_and_keyword_only(self, tmp_path: Path):
        """Omitting user_paths must be a TypeError, never a silent real profile."""
        import pytest

        with pytest.raises(TypeError):
            ScrappyPathProvider(tmp_path)  # type: ignore[call-arg]

        with pytest.raises(TypeError):
            ScrappyPathProvider(tmp_path, disposable_user_paths(tmp_path))  # type: ignore[misc]

    def test_injected_user_paths_determine_user_members(self, tmp_path: Path):
        """The three user directories come from the injected value object."""
        user_paths = disposable_user_paths(tmp_path)
        provider = ScrappyPathProvider(tmp_path, user_paths=user_paths)

        assert provider.user_data_dir() == user_paths.user_data_dir
        assert provider.user_config_dir() == user_paths.user_config_dir
        assert provider.user_cache_dir() == user_paths.user_cache_dir
        assert provider.rate_limits_file() == user_paths.user_data_dir / "rate_limits.json"


class TestDefaultPathProviderComposition:
    """T2. Production defaults, under a setup that separates the two timings."""

    def test_discovery_at_creation_and_legacy_captured_from_import(
        self, tmp_path: Path, monkeypatch
    ):
        """Platform dirs resolve when the provider is created; legacy is captured.

        The two timings are made OBSERVABLY DIFFERENT first: the discovery
        functions return values they never returned at import, and Path.home()
        moves away from the home LEGACY_USER_DIR was built from. Without that
        setup this test would pass even if the legacy source were recomputed,
        because in an unchanged process the two coincide.

        Asserts on resolved VALUES only. Touches no filesystem.
        """
        # The stubs keep the app name in the result they return, so the
        # discovered locations stay pinned to APP_NAME rather than merely to
        # "whatever the stub returned".
        new_data = tmp_path / "new_data" / "scrappy"
        new_config = tmp_path / "new_config" / "scrappy"
        new_cache = tmp_path / "new_cache" / "scrappy"
        patched_home = tmp_path / "patched_home"

        monkeypatch.setattr(
            paths_module, "user_data_dir", lambda app: str(tmp_path / "new_data" / app)
        )
        monkeypatch.setattr(
            paths_module, "user_config_dir", lambda app: str(tmp_path / "new_config" / app)
        )
        monkeypatch.setattr(
            paths_module, "user_cache_dir", lambda app: str(tmp_path / "new_cache" / app)
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: patched_home))

        retained_legacy = paths_module.LEGACY_USER_DIR
        assert retained_legacy != patched_home / ".scrappy", (
            "setup failed to separate the retained constant from a fresh home"
        )

        provider = create_default_path_provider(tmp_path / "project")

        # Discovery ran now, not at import.
        assert provider.user_data_dir() == new_data
        assert provider.user_config_dir() == new_config
        assert provider.user_cache_dir() == new_cache

        # The import-bound legacy default was captured, not recomputed.
        assert provider._user_paths.legacy_user_dir == retained_legacy
        assert provider._user_paths.legacy_user_dir != patched_home / ".scrappy"


def _project_with_scrappy(tmp_path: Path) -> Path:
    """Create an empty project root with its .scrappy/ directory."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".scrappy").mkdir()
    return project_root


class TestScrappyPathProviderMigration:
    """Rate limits migration from project to user level, on injected paths.

    T1/T3/T4. These four were monkeypatch-based; under injection the patches
    would no longer reach the provider, so converting them is required rather
    than cosmetic. The legacy directory is deliberately NOT created here, so
    these cover _migrate_rate_limits only, exactly as they did before.
    """

    def test_migration_copies_project_to_user(self, tmp_path: Path):
        """Migration should copy project-level rate_limits.json to user level."""
        user_paths = disposable_user_paths(tmp_path)
        project_root = _project_with_scrappy(tmp_path)

        # Create project-level rate limits
        project_rate_limits = project_root / ".scrappy" / "rate_limits.json"
        rate_data = {"gemini-2.0-flash": {"rpm_limit": 100}}
        project_rate_limits.write_text(json.dumps(rate_data))

        # Create provider and trigger migration
        provider = ScrappyPathProvider(project_root, user_paths=user_paths)
        provider.ensure_user_dir()

        # Check user-level file was created
        user_rate_limits = user_paths.user_data_dir / "rate_limits.json"
        assert user_rate_limits.exists()
        assert json.loads(user_rate_limits.read_text()) == rate_data

    def test_migration_deletes_project_level(self, tmp_path: Path):
        """T3. Migration should delete project-level file after copying.

        The delete is the one behaviour whose regression is silent and
        destructive, so it is pinned on both sides: copied up AND removed.
        """
        user_paths = disposable_user_paths(tmp_path)
        project_root = _project_with_scrappy(tmp_path)

        # Create project-level rate limits
        project_rate_limits = project_root / ".scrappy" / "rate_limits.json"
        project_rate_limits.write_text("{}")

        provider = ScrappyPathProvider(project_root, user_paths=user_paths)
        provider.ensure_user_dir()

        # Copied to the injected user level ...
        assert (user_paths.user_data_dir / "rate_limits.json").exists()
        # ... and the project-level file should be deleted
        assert not project_rate_limits.exists()

    def test_migration_skips_if_user_exists(self, tmp_path: Path):
        """Migration should not overwrite existing user-level file."""
        user_paths = disposable_user_paths(tmp_path)
        user_paths.user_data_dir.mkdir()
        project_root = _project_with_scrappy(tmp_path)

        # Create project-level rate limits with old data
        project_rate_limits = project_root / ".scrappy" / "rate_limits.json"
        project_rate_limits.write_text('{"old": "data"}')

        # Create user-level rate limits with newer data
        user_rate_limits = user_paths.user_data_dir / "rate_limits.json"
        user_rate_limits.write_text('{"new": "data"}')

        provider = ScrappyPathProvider(project_root, user_paths=user_paths)
        provider.ensure_user_dir()

        # User-level should be unchanged
        assert json.loads(user_rate_limits.read_text()) == {"new": "data"}
        # Project-level should still exist (not migrated)
        assert project_rate_limits.exists()

    def test_migration_skips_if_no_project_file(self, tmp_path: Path):
        """Migration should do nothing if no project-level file exists."""
        user_paths = disposable_user_paths(tmp_path)
        project_root = _project_with_scrappy(tmp_path)
        # No rate_limits.json created

        provider = ScrappyPathProvider(project_root, user_paths=user_paths)
        provider.ensure_user_dir()

        # User dir should exist but no rate limits file
        assert user_paths.user_data_dir.exists()
        assert not (user_paths.user_data_dir / "rate_limits.json").exists()


class TestLegacyMigration:
    """T7-T10. The real _migrate_from_legacy, against injected disposable paths.

    Everything past the legacy-missing early return was previously unreachable
    in tests, because every existing test pointed at a legacy directory that
    was never created. These seed the legacy directory on disk and run the
    real ensure_user_dir helper.
    """

    def test_legacy_files_are_copied(self, tmp_path: Path):
        """T7. Files in the legacy directory are copied to user data."""
        user_paths = disposable_user_paths(tmp_path)
        user_paths.legacy_user_dir.mkdir()
        (user_paths.legacy_user_dir / "config.json").write_text('{"k": "v"}')
        (user_paths.legacy_user_dir / "notes.txt").write_text("hello")

        provider = ScrappyPathProvider(
            _project_with_scrappy(tmp_path), user_paths=user_paths
        )
        provider.ensure_user_dir()

        assert (user_paths.user_data_dir / "config.json").read_text() == '{"k": "v"}'
        assert (user_paths.user_data_dir / "notes.txt").read_text() == "hello"

    def test_legacy_subdirectories_are_ignored(self, tmp_path: Path):
        """T8. The files-only filter skips directories."""
        user_paths = disposable_user_paths(tmp_path)
        user_paths.legacy_user_dir.mkdir()
        (user_paths.legacy_user_dir / "keep.txt").write_text("file")
        nested = user_paths.legacy_user_dir / "subdir"
        nested.mkdir()
        (nested / "inner.txt").write_text("inner")

        provider = ScrappyPathProvider(
            _project_with_scrappy(tmp_path), user_paths=user_paths
        )
        provider.ensure_user_dir()

        assert (user_paths.user_data_dir / "keep.txt").exists()
        assert not (user_paths.user_data_dir / "subdir").exists()

    def test_existing_destination_file_is_not_overwritten(self, tmp_path: Path):
        """T9. The no-overwrite guard protects an existing destination file.

        This is the guard whose failure would silently destroy user data.
        """
        user_paths = disposable_user_paths(tmp_path)
        user_paths.legacy_user_dir.mkdir()
        (user_paths.legacy_user_dir / "config.json").write_text("legacy content")

        user_paths.user_data_dir.mkdir()
        existing = user_paths.user_data_dir / "config.json"
        existing.write_text("newer content")

        provider = ScrappyPathProvider(
            _project_with_scrappy(tmp_path), user_paths=user_paths
        )
        provider.ensure_user_dir()

        # The existing destination survived untouched. Nothing more is asserted
        # here: a test that also required the copy would fail when the migration
        # is skipped entirely, which is T7's job to detect, not this one's.
        assert existing.read_text() == "newer content"

    def test_already_migrated_early_return(self, tmp_path: Path):
        """T10. A populated user rate_limits.json stops the legacy copy."""
        user_paths = disposable_user_paths(tmp_path)
        user_paths.legacy_user_dir.mkdir()
        (user_paths.legacy_user_dir / "config.json").write_text("legacy content")

        user_paths.user_data_dir.mkdir()
        (user_paths.user_data_dir / "rate_limits.json").write_text("{}")

        provider = ScrappyPathProvider(
            _project_with_scrappy(tmp_path), user_paths=user_paths
        )
        provider.ensure_user_dir()

        # Nothing was copied: the early return fired.
        assert not (user_paths.user_data_dir / "config.json").exists()


class PathEscape(Exception):
    """Raised by the T5 guard when an operation targets a path outside the root."""


class TestMigrationFilesystemBoundary:
    """T5. In-suite guard at the boundaries this code actually uses.

    PR-3's tripwire guards JSONPersistence load/save and paths.USER_CONFIG_FILE,
    which this provider never goes through. That guard is untouched and still
    covers its own seam; this one sits alongside it at the boundaries the
    migration actually calls. Makes no claim about the recorded escape set.

    Every wrapper DECIDES BEFORE IT DELEGATES. A target outside the allowed
    disposable root raises and the real mkdir/unlink/copy/exists/iterdir is
    never reached, so an escape is prevented rather than reported after the
    write has already landed.
    """

    def test_migration_writes_only_under_injected_paths(self, tmp_path: Path, monkeypatch):
        allowed_root = tmp_path / "allowed"
        allowed_root.mkdir()

        # A disposable region the guard treats as forbidden. "Forbidden" here
        # means only "outside the allowed root", which is the same rule that
        # would reject a real user location; no real location is ever named.
        forbidden_root = tmp_path / "forbidden"
        forbidden_root.mkdir()
        sentinel = forbidden_root / "sentinel.txt"
        sentinel_bytes = "untouched sentinel"
        sentinel.write_text(sentinel_bytes)

        made_dirs: list[Path] = []
        copied: list[tuple[Path, Path]] = []
        unlinked: list[Path] = []
        checked: list[Path] = []
        listed: list[Path] = []

        real_mkdir = Path.mkdir
        real_unlink = Path.unlink
        real_exists = Path.exists
        real_iterdir = Path.iterdir
        real_copy = paths_module.shutil.copy

        def allow_or_reject(*targets) -> None:
            for target in targets:
                if not Path(target).is_relative_to(allowed_root):
                    raise PathEscape(
                        f"migration reached outside {allowed_root}: {Path(target)}"
                    )

        def guarded_mkdir(self, *args, **kwargs):
            allow_or_reject(self)
            made_dirs.append(Path(self))
            return real_mkdir(self, *args, **kwargs)

        def guarded_unlink(self, *args, **kwargs):
            allow_or_reject(self)
            unlinked.append(Path(self))
            return real_unlink(self, *args, **kwargs)

        def guarded_copy(src, dst, *args, **kwargs):
            allow_or_reject(src, dst)
            copied.append((Path(src), Path(dst)))
            return real_copy(src, dst, *args, **kwargs)

        def guarded_exists(self, *args, **kwargs):
            allow_or_reject(self)
            checked.append(Path(self))
            return real_exists(self, *args, **kwargs)

        def guarded_iterdir(self, *args, **kwargs):
            allow_or_reject(self)
            listed.append(Path(self))
            return real_iterdir(self, *args, **kwargs)

        user_paths = disposable_user_paths(allowed_root)
        user_paths.legacy_user_dir.mkdir()
        (user_paths.legacy_user_dir / "legacy.txt").write_text("legacy")

        project_root = _project_with_scrappy(allowed_root)
        project_rate_limits = project_root / ".scrappy" / "rate_limits.json"
        project_rate_limits.write_text("{}")

        provider = ScrappyPathProvider(project_root, user_paths=user_paths)

        # The guard covers the migration call only, so an unrelated read
        # elsewhere in the test process is never the thing being judged.
        with monkeypatch.context() as patched:
            patched.setattr(Path, "mkdir", guarded_mkdir)
            patched.setattr(Path, "unlink", guarded_unlink)
            patched.setattr(Path, "exists", guarded_exists)
            patched.setattr(Path, "iterdir", guarded_iterdir)
            patched.setattr(paths_module.shutil, "copy", guarded_copy)
            provider.ensure_user_dir()

        # POSITIVE: it ran where it was told, not merely nowhere. A guard that
        # passes because nothing happened at all would be worthless.
        assert user_paths.user_data_dir in made_dirs
        assert user_paths.user_config_dir in made_dirs
        assert user_paths.user_cache_dir in made_dirs
        assert (
            user_paths.legacy_user_dir / "legacy.txt",
            user_paths.user_data_dir / "legacy.txt",
        ) in copied
        assert project_rate_limits in unlinked

        # The read boundary was exercised, not merely declared.
        assert user_paths.legacy_user_dir in listed
        assert user_paths.user_data_dir / "rate_limits.json" in checked

        # The forbidden region is byte-for-byte what it was before the run.
        assert sentinel.read_text() == sentinel_bytes
        assert [p.name for p in forbidden_root.iterdir()] == ["sentinel.txt"]

        # The rejection bites: driven directly, the guard raises INSTEAD of
        # performing the operation, and the sentinel survives each attempt.
        with pytest.raises(PathEscape):
            guarded_unlink(sentinel)
        with pytest.raises(PathEscape):
            guarded_mkdir(forbidden_root / "new_dir")
        with pytest.raises(PathEscape):
            guarded_copy(user_paths.legacy_user_dir / "legacy.txt", sentinel)
        with pytest.raises(PathEscape):
            guarded_iterdir(forbidden_root)

        assert sentinel.read_text() == sentinel_bytes
        assert [p.name for p in forbidden_root.iterdir()] == ["sentinel.txt"]
        assert sentinel not in unlinked
        assert forbidden_root / "new_dir" not in made_dirs


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
        provider = ScrappyPathProvider(tmp_path, user_paths=disposable_user_paths(tmp_path))
        assert provider.project_root() == tmp_path

    def test_workspace_display_uses_forward_slashes(self, tmp_path: Path):
        """workspace_display() should use forward slashes on all platforms."""
        provider = ScrappyPathProvider(tmp_path, user_paths=disposable_user_paths(tmp_path))
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

        provider = ScrappyPathProvider(project, user_paths=disposable_user_paths(tmp_path))
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

        provider = ScrappyPathProvider(project, user_paths=disposable_user_paths(tmp_path))
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
