#!/usr/bin/env python3
"""
Entry point for LLM Agent Team CLI.
"""

import sys
import os

# Suppress gRPC/abseil ALTS warnings BEFORE any imports
# These warnings occur when using Google APIs (Gemini) outside of GCP
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

# Fix Windows Unicode encoding issues BEFORE any other imports
# This prevents 'charmap' codec errors when printing Unicode characters (emojis, etc.)
if sys.platform == 'win32':
    # Set UTF-8 mode for Python (Python 3.7+)
    if hasattr(sys, 'set_int_max_str_digits'):
        # Python 3.11+ - use UTF-8 mode
        pass

    # Force UTF-8 encoding for stdout/stderr
    if hasattr(sys.stdout, 'reconfigure'):
        # Python 3.7+ - reconfigure streams to use UTF-8
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass  # Fallback if reconfigure fails
    else:
        # Older Python - wrap streams
        import io
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

    # Set environment variable for child processes
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8:replace'

from src.cli import main

if __name__ == "__main__":
    main()
