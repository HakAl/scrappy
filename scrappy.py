#!/usr/bin/env python3
"""
Entry point for Scrappy CLI.
"""

import sys
import os

# Suppress gRPC/abseil ALTS warnings BEFORE any imports
# These warnings occur when using Google APIs (Gemini) outside of GCP
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'
# TODO TESTING
# Limit ONNX Runtime to physical cores to prevent async blocking
os.environ["OMP_NUM_THREADS"] = "4"

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

# Configure logging to file for debugging (before other imports)
import atexit
import logging
from pathlib import Path

log_file = Path.cwd() / ".scrappy" / "debug.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

# Create handler explicitly so we can close it on exit
file_handler = logging.FileHandler(log_file, mode='w')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler, logging.StreamHandler()]
)

# Register cleanup to prevent ResourceWarning about unclosed file
atexit.register(file_handler.close)

from src.cli import main

if __name__ == "__main__":
    main()
