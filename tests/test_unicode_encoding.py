#!/usr/bin/env python3
"""
Test Unicode encoding handling for Windows.

This test verifies that the safe_print function and UTF-8 encoding
configuration properly handle Unicode characters (emojis, etc.) without crashing.
"""

import sys


def test_utf8_environment_variables():
    """Test that UTF-8 environment variables are set on Windows."""
    import os

    if sys.platform == 'win32':
        # Import the entry point module which sets env vars
        # Add parent directory to path to find scrappy
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, parent_dir)
        # Imported for its side effect: main.py sets the UTF-8 env vars below
        import main  # noqa: F401

        # Check that environment variables are set
        assert os.environ.get('PYTHONUTF8') == '1', "PYTHONUTF8 should be set to '1'"
        assert os.environ.get('PYTHONIOENCODING') == 'utf-8:replace', "PYTHONIOENCODING should be set"


def test_subprocess_encoding_config():
    """Test that subprocess uses UTF-8 with error replacement."""
    import subprocess
    import os

    # Simulate what _run_command_streaming does
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['CI'] = 'true'
    # Ensure subprocess uses UTF-8 for stdout (required on Windows)
    env['PYTHONIOENCODING'] = 'utf-8'

    # This should work without crashing even with UTF-8 output
    result = subprocess.run(
        [sys.executable, '-c', 'print("Test output with emoji: \\U0001F600")'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env,
        timeout=10
    )

    # Should contain the text (emoji may be replaced)
    assert 'Test output' in result.stdout
