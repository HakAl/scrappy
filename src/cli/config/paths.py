"""
CLI paths configuration module.

Centralizes skip directories, session files, and path-related
constants used throughout the CLI for file system operations.
"""

import os
from pathlib import Path
from typing import List, Set

# User config directory (in user's home directory)
USER_CONFIG_DIR = Path.home() / '.scrappy'
USER_CONFIG_FILE = USER_CONFIG_DIR / 'config.json'

# Session and tracking files (now in .scrappy/ directory)
SESSION_FILE = '.scrappy/session.json'
RATE_LIMITS_FILE = '.scrappy/rate_limits.json'
RESPONSE_CACHE_FILE = '.scrappy/response_cache.json'
CONTEXT_FILE = '.scrappy/context.json'
AUDIT_FILE = '.scrappy/audit.json'

# Hidden files and directories (should not be shown in file listings)
HIDDEN_FILES: List[str] = [
    SESSION_FILE,
    RATE_LIMITS_FILE,
    RESPONSE_CACHE_FILE,
    CONTEXT_FILE,
    AUDIT_FILE,
]

# Hidden directories
HIDDEN_DIRS: Set[str] = {
    '.scrappy',
}

# Cache directories
CACHE_DIRS: Set[str] = {
    '__pycache__',
    '.cache',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
}

# Test directories
TEST_DIRS: Set[str] = {
    'tests',
    'test',
    '__tests__',
    'spec',
    'specs',
}

# Build output directories
BUILD_DIRS: Set[str] = {
    'dist',
    'build',
    'out',
    'target',
    'bin',
    'obj',
}

# Vendor/dependency directories
VENDOR_DIRS: Set[str] = {
    'node_modules',
    'vendor',
    'third_party',
    'external',
    'packages',
}

# Virtual environment directories
VENV_DIRS: Set[str] = {
    '.venv',
    'venv',
    'env',
    '.env',
    'virtualenv',
}

# All hidden directories (start with dot)
ALL_HIDDEN_DIRS: Set[str] = {
    '.git',
    '.svn',
    '.hg',
    '.venv',
    '.env',
    '.cache',
    '.tox',
    '.nox',
    '.coverage',
}

# Complete set of directories to skip during scanning
SKIP_DIRS: Set[str] = (
    CACHE_DIRS |
    BUILD_DIRS |
    VENDOR_DIRS |
    VENV_DIRS |
    ALL_HIDDEN_DIRS |
    HIDDEN_DIRS |
    {'.git', '.svn', '.hg', '.idea', '.vscode'}
)

# Minimal skip set for lightweight scanning
SKIP_DIRS_MINIMAL: Set[str] = {
    '__pycache__',
    'node_modules',
    'venv',
    '.venv',
    '.git',
}

# Documentation for skip directories
SKIP_DIRS_DESCRIPTIONS = {
    '.git': 'Git version control directory',
    '.svn': 'Subversion version control directory',
    '.hg': 'Mercurial version control directory',
    '__pycache__': 'Python bytecode cache',
    'node_modules': 'Node.js dependencies',
    '.venv': 'Python virtual environment',
    'venv': 'Python virtual environment',
    'env': 'Python virtual environment',
    '.env': 'Environment/virtual environment directory',
    'dist': 'Distribution/build output',
    'build': 'Build output directory',
    'out': 'Output directory',
    'target': 'Build target directory (Rust, Java)',
    'bin': 'Binary output directory',
    'obj': 'Object files directory',
    '.cache': 'Cache directory',
    '.pytest_cache': 'Pytest cache',
    '.mypy_cache': 'Mypy type checker cache',
    '.ruff_cache': 'Ruff linter cache',
    'vendor': 'Third-party dependencies',
    'third_party': 'Third-party code',
    'external': 'External dependencies',
    'packages': 'Package dependencies',
    '.idea': 'IntelliJ IDEA settings',
    '.vscode': 'VS Code settings',
    'virtualenv': 'Python virtual environment',
    '.tox': 'Tox testing directory',
    '.nox': 'Nox testing directory',
    '.coverage': 'Coverage data directory',
    '.scrappy': 'Scrappy data directory (session, cache, logs)',
}

# Project root indicator files
PROJECT_INDICATORS: List[str] = [
    '.git',
    'requirements.txt',
    'pyproject.toml',
    'setup.py',
    'package.json',
    'Cargo.toml',
    'go.mod',
    'Makefile',
    '.gitignore',
]


def should_skip_directory(dir_name: str) -> bool:
    """
    Check if a directory should be skipped during scanning.

    Args:
        dir_name: Name of the directory (not full path)

    Returns:
        True if the directory should be skipped
    """
    return dir_name in SKIP_DIRS


def is_session_file(filename: str) -> bool:
    """
    Check if a file is a session tracking file.

    Args:
        filename: Name of the file

    Returns:
        True if the file is a session file
    """
    return filename in HIDDEN_FILES


def is_project_root(path: str) -> bool:
    """
    Check if a path appears to be a project root directory.

    Args:
        path: Path to check

    Returns:
        True if the path contains project indicator files
    """
    if not os.path.isdir(path):
        return False

    for indicator in PROJECT_INDICATORS:
        indicator_path = os.path.join(path, indicator)
        if os.path.exists(indicator_path):
            return True

    return False
