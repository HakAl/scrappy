"""The two user-level PathProviderProtocol members (scrappy-i2jo).

ScrappyPathProvider.command_history_file() and model_cooldowns_file() must
resolve from Path.home() AT CALL TIME (so a test that relocates HOME after
construction is followed), preserving today's production location. This is the
test that fails if the implementer binds the path at import or in __init__.

TempPathProvider derives both from its injected temp_dir, like every other
member; sending a temp provider's paths back to HOME would defeat the contract.
"""

from pathlib import Path

from scrappy.infrastructure.paths import ScrappyPathProvider, TempPathProvider


class TestScrappyProviderResolvesHomeAtCallTime:
    """The production provider follows HOME when it moves after construction."""

    def test_command_history_follows_moved_home(self, tmp_path, monkeypatch):
        home1 = tmp_path / "home1"
        home2 = tmp_path / "home2"
        home1.mkdir()
        home2.mkdir()

        monkeypatch.setattr(Path, "home", staticmethod(lambda: home1))
        # project_root is irrelevant to this member; it resolves from HOME.
        provider = ScrappyPathProvider(Path("."))
        assert provider.command_history_file() == home1 / ".scrappy" / "command_history"

        # MOVE HOME, then call again: the second call must follow the moved home.
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home2))
        assert provider.command_history_file() == home2 / ".scrappy" / "command_history"

    def test_model_cooldowns_follows_moved_home(self, tmp_path, monkeypatch):
        home1 = tmp_path / "home1"
        home2 = tmp_path / "home2"
        home1.mkdir()
        home2.mkdir()

        monkeypatch.setattr(Path, "home", staticmethod(lambda: home1))
        provider = ScrappyPathProvider(Path("."))
        assert provider.model_cooldowns_file() == home1 / ".scrappy" / "model_cooldowns.json"

        monkeypatch.setattr(Path, "home", staticmethod(lambda: home2))
        assert provider.model_cooldowns_file() == home2 / ".scrappy" / "model_cooldowns.json"


class TestTempProviderMembersUnderInjectedDir:
    """The temp provider keeps both new members inside its injected root."""

    def test_command_history_under_temp_dir(self, tmp_path):
        provider = TempPathProvider(tmp_path)
        assert provider.command_history_file().is_relative_to(tmp_path)

    def test_model_cooldowns_under_temp_dir(self, tmp_path):
        provider = TempPathProvider(tmp_path)
        assert provider.model_cooldowns_file().is_relative_to(tmp_path)
