"""Tests for the global selection-mode toggle."""

from unittest.mock import Mock, patch

from scrappy.cli.textual.app import ScrappyApp


class FakeMousePolicy:
    def __init__(self) -> None:
        self.selection_mode = False
        self.calls: list[str] = []

    def enable(self) -> None:
        self.calls.append("enable")

    def disable_for_selection(self) -> None:
        self.selection_mode = True
        self.calls.append("disable_for_selection")

    def restore(self) -> None:
        self.selection_mode = False
        self.calls.append("restore")


def test_action_toggle_selection_mode_flips_disable_and_restore() -> None:
    policy = FakeMousePolicy()
    app = ScrappyApp(cli_factory=lambda: Mock(), mouse_policy=policy)

    with patch.object(app, "notify") as notify:
        app.action_toggle_selection_mode()
        app.action_toggle_selection_mode()

    assert policy.selection_mode is False
    assert policy.calls == ["disable_for_selection", "restore"]
    assert notify.call_args_list[0].args == (
        "Selection mode: drag to select, Cmd+C to copy. Ctrl+T to restore.",
    )
    assert notify.call_args_list[0].kwargs == {"timeout": 4}
    assert notify.call_args_list[1].args == ("Mouse mode on (scroll/click).",)
    assert notify.call_args_list[1].kwargs == {"timeout": 2}


def test_ctrl_t_binding_is_global_selection_mode_toggle() -> None:
    actions_by_key = {binding.key: binding.action for binding in ScrappyApp.BINDINGS}
    labels_by_key = {binding.key: binding.description for binding in ScrappyApp.BINDINGS}

    assert actions_by_key["ctrl+t"] == "toggle_selection_mode"
    assert labels_by_key["ctrl+t"] == "Select mode"
