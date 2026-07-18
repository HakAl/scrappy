"""Tests for ScrappyApp mouse policy routing."""

from unittest.mock import Mock, patch

import pytest

from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.textual.mouse_policy import TextualMouseReportingPolicy


class FakeMousePolicy:
    def __init__(self) -> None:
        self.selection_mode = False
        self.enable_calls = 0
        self.disable_calls = 0
        self.restore_calls = 0

    def enable(self) -> None:
        self.enable_calls += 1

    def disable_for_selection(self) -> None:
        self.selection_mode = True
        self.disable_calls += 1

    def restore(self) -> None:
        self.selection_mode = False
        self.restore_calls += 1


class FakeDriver:
    def __init__(self) -> None:
        self.enable_calls = 0
        self.disable_calls = 0

    def _enable_mouse_support(self) -> None:
        self.enable_calls += 1

    def _disable_mouse_support(self) -> None:
        self.disable_calls += 1


@pytest.mark.asyncio
async def test_restore_mouse_support_delegates_to_policy_enable() -> None:
    policy = FakeMousePolicy()
    app = ScrappyApp(cli_factory=lambda: Mock(), mouse_policy=policy)

    with (
        patch.object(app, "_check_and_migrate_providers", return_value=(True, 0)),
        patch.object(app, "_show_main_screen"),
        patch("scrappy.cli.textual.app.create_api_key_service") as api_keys,
        patch("scrappy.orchestrator.mock_llm_service.is_mock_mode_enabled", return_value=True),
    ):
        api_keys.return_value.is_disclaimer_acknowledged.return_value = True
        async with app.run_test():
            app.restore_mouse_support()

    assert policy.enable_calls == 1


def test_restore_mouse_support_does_not_reenable_real_policy_in_selection_mode() -> None:
    driver = FakeDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)
    app = ScrappyApp(cli_factory=lambda: Mock(), mouse_policy=policy)

    policy.disable_for_selection()
    app.restore_mouse_support()

    assert policy.selection_mode is True
    assert driver.disable_calls == 1
    assert driver.enable_calls == 0


def test_on_unmount_restores_mouse_policy_before_resource_cleanup() -> None:
    policy = FakeMousePolicy()
    app = ScrappyApp(cli_factory=lambda: Mock(), mouse_policy=policy)
    policy.disable_for_selection()

    with patch.object(app, "_cleanup_runtime_resources") as cleanup:
        app.on_unmount()

    assert policy.selection_mode is False
    assert policy.restore_calls == 1
    cleanup.assert_called_once_with()
