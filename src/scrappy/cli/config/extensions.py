"""
CLI file extensions configuration module.

Centralizes file extension categories and file type patterns used
throughout the CLI for file classification and filtering.
"""

from typing import List

# Programming language extensions
PYTHON_EXTENSIONS: List[str] = ['.py', '.pyw', '.pyi']

JAVASCRIPT_EXTENSIONS: List[str] = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs']

WEB_EXTENSIONS: List[str] = ['.html', '.htm', '.css', '.scss', '.sass', '.less']

# Configuration file extensions
CONFIG_EXTENSIONS: List[str] = ['.json', '.yaml', '.yml', '.toml', '.ini', '.cfg']

# Documentation extensions
DOCS_EXTENSIONS: List[str] = ['.md', '.rst', '.txt']

# Extensions organized by category
EXTENSIONS_BY_CATEGORY = {
    'python': PYTHON_EXTENSIONS,
    'javascript': JAVASCRIPT_EXTENSIONS,
    'web': WEB_EXTENSIONS,
    'config': CONFIG_EXTENSIONS,
    'docs': DOCS_EXTENSIONS,
    'other': [],
}

# All code file extensions combined
ALL_CODE_EXTENSIONS: List[str] = (
    PYTHON_EXTENSIONS +
    JAVASCRIPT_EXTENSIONS +
    WEB_EXTENSIONS
)

# Entry point file names (common application entry points)
ENTRY_POINT_FILES: List[str] = [
    'main.py',
    '__main__.py',
    'app.py',
    'cli.py',
    'setup.py',
    'index.js',
    'index.ts',
    'main.js',
    'main.ts',
]

# Priority files (important project files to read first)
PRIORITY_FILES: List[str] = [
    'README.md',
    'README',
    'README.rst',
    'README.txt',
    'setup.py',
    'pyproject.toml',
    'package.json',
    'requirements.txt',
    'Cargo.toml',
    'go.mod',
    'Makefile',
    'Dockerfile',
]

# Dependency/manifest files
DEPENDENCY_FILES: List[str] = [
    'requirements.txt',
    'setup.py',
    'pyproject.toml',
    'package.json',
    'package-lock.json',
    'yarn.lock',
    'Cargo.toml',
    'Cargo.lock',
    'go.mod',
    'go.sum',
    'Pipfile',
    'Pipfile.lock',
]

# Configuration file names
CONFIGURATION_FILES: List[str] = [
    'config.py',
    'settings.py',
    'config.json',
    'config.yaml',
    'config.yml',
    '.env.example',
    '.env.sample',
    'setup.cfg',
]


def get_category_for_extension(ext: str) -> str:
    """
    Get the category for a given file extension.

    Args:
        ext: File extension (e.g., '.py', '.js')

    Returns:
        Category name ('python', 'javascript', 'web', 'config', 'docs', 'other')
    """
    for category, extensions in EXTENSIONS_BY_CATEGORY.items():
        if ext in extensions:
            return category
    return 'other'


def is_code_file(ext: str) -> bool:
    """
    Check if a file extension represents a code file.

    Args:
        ext: File extension (e.g., '.py', '.js')

    Returns:
        True if the extension is for a code file
    """
    return ext in ALL_CODE_EXTENSIONS


def is_config_file(ext: str) -> bool:
    """
    Check if a file extension represents a config file.

    Args:
        ext: File extension (e.g., '.json', '.yaml')

    Returns:
        True if the extension is for a config file
    """
    return ext in CONFIG_EXTENSIONS


def is_docs_file(ext: str) -> bool:
    """
    Check if a file extension represents a documentation file.

    Args:
        ext: File extension (e.g., '.md', '.rst')

    Returns:
        True if the extension is for a docs file
    """
    return ext in DOCS_EXTENSIONS
