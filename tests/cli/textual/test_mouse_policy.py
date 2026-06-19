"""Tests for Textual mouse reporting policy behavior."""

from scrappy.cli.textual.mouse_policy import TextualMouseReportingPolicy


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.writes: list[str] = []
        self.flushed = False

    def _enable_mouse_support(self) -> None:
        self.calls.append("enable")

    def _disable_mouse_support(self) -> None:
        self.calls.append("disable")

    def write(self, value: str) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        self.flushed = True


class EnableOnlyDriver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _enable_mouse_support(self) -> None:
        self.calls.append("enable")


class EscapeOnlyDriver:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.flushed = False

    def write(self, value: str) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        self.flushed = True


def test_enable_calls_driver_enable_when_not_in_selection_mode() -> None:
    driver = FakeDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)

    policy.enable()

    assert driver.calls == ["enable"]


def test_enable_is_noop_while_selection_mode_is_active() -> None:
    driver = FakeDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)

    policy.disable_for_selection()
    driver.calls.clear()
    policy.enable()

    assert policy.selection_mode is True
    assert driver.calls == []


def test_disable_for_selection_sets_mode_and_calls_driver_disable() -> None:
    driver = FakeDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)

    policy.disable_for_selection()

    assert policy.selection_mode is True
    assert driver.calls == ["disable"]


def test_restore_clears_selection_mode_and_calls_driver_enable() -> None:
    driver = FakeDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)

    policy.disable_for_selection()
    driver.calls.clear()
    policy.restore()

    assert policy.selection_mode is False
    assert driver.calls == ["enable"]


def test_disable_for_selection_falls_back_to_explicit_escape_sequences() -> None:
    driver = EscapeOnlyDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)

    policy.disable_for_selection()

    assert policy.selection_mode is True
    assert driver.writes == list(TextualMouseReportingPolicy._DISABLE_SEQS)
    assert driver.flushed is True


def test_enable_only_driver_sets_selection_mode_without_crashing() -> None:
    driver = EnableOnlyDriver()
    policy = TextualMouseReportingPolicy(lambda: driver)

    policy.disable_for_selection()

    assert policy.selection_mode is True
    assert driver.calls == []


def test_missing_driver_is_safe_for_all_policy_actions() -> None:
    policy = TextualMouseReportingPolicy(lambda: None)

    policy.enable()
    policy.disable_for_selection()
    policy.restore()

    assert policy.selection_mode is False
