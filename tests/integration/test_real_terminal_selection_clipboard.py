"""Cross-platform entry point for isolated real-terminal clipboard verification."""

from __future__ import annotations

from pathlib import Path

import pytest

from .platform_terminal_harness import create_platform_terminal_harness
from .real_terminal_scenario import (
    build_session_spec,
    execute_help_selection_clipboard_scenario,
    require_real_terminal_opt_in,
)


pytestmark = pytest.mark.integration


def test_help_output_can_be_selected_and_copied_in_real_terminal(tmp_path: Path):
    """Run the shared /help selection scenario against the current platform harness."""
    require_real_terminal_opt_in()

    repo_root = Path(__file__).resolve().parents[2]
    session = build_session_spec(tmp_path=tmp_path, repo_root=repo_root)
    harness = create_platform_terminal_harness()

    execute_help_selection_clipboard_scenario(harness=harness, session=session)
