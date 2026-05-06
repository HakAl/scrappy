"""Behavior tests for the shared chat surface."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from textual.app import App, ComposeResult
from textual.events import MouseDown

from scrappy.cli.screens.chat_surface import (
    AppendTranscript,
    ChatSurface,
    ClearTranscript,
    SubmitResult,
    UpdatePlaceholder,
)
from scrappy.cli.widgets import SelectableLog


class SurfaceHarnessApp(App):
    """Minimal app that mounts one chat surface."""

    def compose(self) -> ComposeResult:
        yield ChatSurface(id="surface")


@dataclass
class RecordingHandler:
    """Capture submitted text through the handler protocol."""

    submitted: list[str]

    def handle_submit(self, user_input: str) -> SubmitResult:
        self.submitted.append(user_input)
        return SubmitResult(
            accepted=True,
            follow_up_actions=(
                ClearTranscript(),
                AppendTranscript(entries=("after submit",)),
                UpdatePlaceholder("next prompt"),
            ),
        )


@pytest.mark.asyncio
async def test_transcript_right_click_does_not_paste_into_composer() -> None:
    """Transcript mouse actions should not paste into the composer."""
    app = SurfaceHarnessApp()

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        surface = app.query_one(ChatSurface)
        log = app.query_one(SelectableLog)
        surface.input.text = ""
        clipboard = Mock()
        clipboard.paste_text.return_value = "pasted"
        event = MouseDown(log, 0, 0, 0, 0, 3, False, False, False)

        surface.handle_click(event, clipboard)

        assert surface.input.text == ""
        clipboard.paste_text.assert_not_called()


@pytest.mark.asyncio
async def test_right_click_outside_transcript_pastes_into_composer() -> None:
    """Right-click on the surface background should paste into the composer."""
    app = SurfaceHarnessApp()

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        surface = app.query_one(ChatSurface)
        clipboard = Mock()
        clipboard.paste_text.return_value = "pasted"
        event = MouseDown(surface, 0, 0, 0, 0, 3, False, False, False)

        surface.handle_click(event, clipboard)

        assert surface.input.text == "pasted"


@pytest.mark.asyncio
async def test_submit_clears_input_and_applies_local_follow_up_actions() -> None:
    """Submit should share input clearing and local follow-up handling."""
    app = SurfaceHarnessApp()

    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()

        surface = app.query_one(ChatSurface)
        surface.write("before submit")
        surface.input.text = "  command text  "
        handler = RecordingHandler(submitted=[])

        result = surface.submit(handler)
        unhandled = surface.apply_follow_up_actions(result.follow_up_actions)

        assert handler.submitted == ["command text"]
        assert surface.input.text == ""
        assert surface.output.selection_text == ""
        assert surface.output.transcript_model.entries()[-1].renderable == "after submit"
        assert surface.input.placeholder == "next prompt"
        assert unhandled == ()
