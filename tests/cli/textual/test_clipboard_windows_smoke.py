"""Windows smoke tests for real clipboard integration."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import uuid

import pytest
from textual.widgets import TextArea

os.environ["SCRAPPY_MOCK_LLM"] = "1"

from scrappy.cli.textual.app import ScrappyApp
from scrappy.cli.widgets.selectable_log import SelectableLog


def create_mock_cli():
    """Create a mock CLI for app startup."""
    from unittest.mock import MagicMock

    mock_cli = MagicMock()
    mock_cli.interactive_mode = MagicMock()
    mock_cli.interactive_mode.command_router = MagicMock()
    mock_cli.interactive_mode.command_router.set_setup_wizard_callback = MagicMock()
    mock_cli.interactive_mode._process_input = MagicMock(return_value=True)
    return mock_cli


def create_test_app() -> ScrappyApp:
    """Create a ScrappyApp instance using the production clipboard path."""
    return ScrappyApp(cli_factory=create_mock_cli)


def _run_powershell(script: str) -> str:
    """Run a PowerShell command and return stdout."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        raise RuntimeError(stderr or stdout or "PowerShell clipboard command failed")
    return result.stdout


def _set_system_clipboard(text: str) -> None:
    """Write text to the Windows clipboard via PowerShell."""
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("ascii")
    _run_powershell(
        "$value = [Text.Encoding]::UTF8.GetString("
        f"[Convert]::FromBase64String('{encoded_text}')); "
        "Set-Clipboard -Value $value"
    )


def _get_system_clipboard() -> str:
    """Read text from the Windows clipboard via PowerShell."""
    return _run_powershell(
        "$value = Get-Clipboard -Raw; "
        "if ($null -ne $value) { [Console]::Out.Write($value) }"
    )


def _require_system_clipboard() -> None:
    """Skip when the current Windows session does not expose a clipboard."""
    probe = f"scrappy-clipboard-probe-{uuid.uuid4()}"
    original_text = ""
    current_text = ""
    try:
        original_text = _get_system_clipboard()
        _set_system_clipboard(probe)
        current_text = _get_system_clipboard()
    except RuntimeError as exc:
        pytest.skip(f"System clipboard unavailable in this session: {exc}")
    finally:
        try:
            _set_system_clipboard(original_text)
        except Exception:
            pass

    if current_text != probe:
        pytest.skip("System clipboard did not preserve test content")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="Windows clipboard smoke test")
async def test_ctrl_v_reads_real_windows_clipboard():
    """Ctrl+V should paste the current Windows clipboard into the input."""
    _require_system_clipboard()
    original_text = _get_system_clipboard()
    clipboard_text = f"scrappy paste smoke {uuid.uuid4()}"

    try:
        _set_system_clipboard(clipboard_text)

        app = create_test_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            input_widget = app.screen.query_one(TextArea)
            await pilot.press("ctrl+v")
            await pilot.pause()

            assert input_widget.text == clipboard_text
    finally:
        _set_system_clipboard(original_text)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="Windows clipboard smoke test")
async def test_ctrl_c_writes_real_windows_clipboard():
    """Ctrl+C should write the selected log text to the Windows clipboard."""
    _require_system_clipboard()
    original_text = _get_system_clipboard()
    copied_text = f"scrappy copy smoke {uuid.uuid4()}"

    try:
        app = create_test_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            log = app.screen.query_one(SelectableLog)
            log.clear()
            log.write(copied_text)
            await pilot.pause()

            log._selection_start = (0, 0)
            log._selection_end = (0, len(copied_text))

            await pilot.press("ctrl+c")
            await pilot.pause()

        assert _get_system_clipboard() == copied_text
    finally:
        _set_system_clipboard(original_text)
