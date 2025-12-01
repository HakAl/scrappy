#!/usr/bin/env python3
"""
Entry point for Scrappy CLI.
"""

import sys
import os

# Suppress gRPC/abseil ALTS warnings BEFORE any imports
# These warnings occur when using Google APIs (Gemini) outside of GCP
os.environ['GRPC_VERBOSITY'] = 'NONE'
os.environ['GRPC_TRACE'] = ''
os.environ['GLOG_minloglevel'] = '2'
os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'
# Suppress absl logging (used by Google libraries)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
# TODO TESTING
# Limit ONNX Runtime to physical cores to prevent async blocking
os.environ["OMP_NUM_THREADS"] = "4"

# Fix Windows Unicode encoding issues BEFORE any other imports
# This prevents 'charmap' codec errors when printing Unicode characters (emojis, etc.)
from scrappy.platform import configure_console_encoding
configure_console_encoding()

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

from scrappy.cli import main

if __name__ == "__main__":
    main()
