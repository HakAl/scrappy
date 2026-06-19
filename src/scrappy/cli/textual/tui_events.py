"""Typed TUI events and Textual boundary message."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any, Optional, TypeAlias

from textual.message import Message

from ..protocols import ActivityState

logger = logging.getLogger(__name__)


class TuiEventTarget(Enum):
    """Logical target for a TUI event."""

    MAIN_TRANSCRIPT = "main_transcript"
    WIZARD_TRANSCRIPT = "wizard_transcript"
    APP_STATUS = "app_status"
    LIFECYCLE = "lifecycle"


@dataclass(frozen=True)
class TranscriptAppendText:
    """Append text to a transcript surface."""

    content: str
    target: TuiEventTarget = TuiEventTarget.MAIN_TRANSCRIPT


@dataclass(frozen=True)
class TranscriptAppendRenderable:
    """Append a renderable to a transcript surface."""

    renderable: Any
    target: TuiEventTarget = TuiEventTarget.MAIN_TRANSCRIPT


@dataclass(frozen=True)
class TranscriptClear:
    """Clear a transcript surface."""

    target: TuiEventTarget = TuiEventTarget.MAIN_TRANSCRIPT


@dataclass(frozen=True)
class ActivityChanged:
    """Update the active work indicator."""

    state: ActivityState
    message: str = ""
    elapsed_ms: int = 0


@dataclass(frozen=True)
class TasksUpdated:
    """Replace the visible task list."""

    tasks: list[Any]


@dataclass(frozen=True)
class PromptRequested:
    """Request inline input capture."""

    prompt_id: str
    message: str
    input_type: str
    default: str = ""


@dataclass(frozen=True)
class MetricsUpdated:
    """Update status-bar metrics."""

    provider_display: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    session_total: Optional[int]
    context_percent: Optional[int] = None


@dataclass(frozen=True)
class IndexingProgressChanged:
    """Update semantic indexing progress."""

    message: str
    progress: int = 0
    total: int = 0
    complete: bool = False


@dataclass(frozen=True)
class FlushRequested:
    """Acknowledge all previously posted events in the same sequence."""

    flush_id: str


@dataclass(frozen=True)
class ShutdownRequested:
    """Signal shutdown to event consumers."""


@dataclass(frozen=True)
class CliReadyChanged:
    """Signal deferred CLI initialization completion."""

    cli: Any = None
    error: Optional[str] = None


@dataclass(frozen=True)
class CancelStateChanged:
    """Signal cancellation-related UI state."""

    active: bool


TuiEvent: TypeAlias = (
    TranscriptAppendText
    | TranscriptAppendRenderable
    | TranscriptClear
    | ActivityChanged
    | TasksUpdated
    | PromptRequested
    | MetricsUpdated
    | IndexingProgressChanged
    | FlushRequested
    | ShutdownRequested
    | CliReadyChanged
    | CancelStateChanged
)


def tui_event_from_legacy_output_message(
    message: tuple[str, Any],
) -> TuiEvent | None:
    """Convert tuple-adapter output messages to typed TUI events."""
    msg_type, content = message
    if msg_type == "output":
        return TranscriptAppendText(content=content)
    if msg_type == "renderable":
        return TranscriptAppendRenderable(renderable=content)
    if msg_type == "tasks":
        return TasksUpdated(content)
    if msg_type == "activity":
        state, msg, elapsed_ms = content
        return ActivityChanged(state=state, message=msg, elapsed_ms=elapsed_ms)
    if msg_type == "flush":
        return FlushRequested(flush_id=content)
    logger.warning("Unrecognized tuple-adapter tag: %s", msg_type)
    return None


class TuiEventMessage(Message):
    """Single Textual boundary wrapper for typed TUI events."""

    def __init__(self, event: TuiEvent) -> None:
        super().__init__()
        self.event = event
