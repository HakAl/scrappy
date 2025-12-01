"""
Python-specific tools for the code agent.

Provides dependency analysis, import extraction, and requirements management.
"""

import re
import subprocess
from pathlib import Path
from typing import Set, Dict, List, Any

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


# Python standard library modules (comprehensive list)
STDLIB_MODULES = {
    # Built-in modules
    'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore',
    'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect',
    'builtins', 'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd',
    'code', 'codecs', 'codeop', 'collections', 'colorsys', 'compileall',
    'concurrent', 'configparser', 'contextlib', 'contextvars', 'copy', 'copyreg',
    'cProfile', 'crypt', 'csv', 'ctypes', 'curses', 'dataclasses', 'datetime',
    'dbm', 'decimal', 'difflib', 'dis', 'distutils', 'doctest', 'email',
    'encodings', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput',
    'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt',
    'getpass', 'gettext', 'glob', 'graphlib', 'grp', 'gzip', 'hashlib', 'heapq',
    'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr', 'imp', 'importlib',
    'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3',
    'linecache', 'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal',
    'math', 'mimetypes', 'mmap', 'modulefinder', 'multiprocessing', 'netrc',
    'nis', 'nntplib', 'numbers', 'operator', 'optparse', 'os', 'ossaudiodev',
    'parser', 'pathlib', 'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil',
    'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint', 'profile',
    'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc', 'queue', 'quopri',
    'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter', 'runpy',
    'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil',
    'signal', 'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver',
    'spwd', 'sqlite3', 'ssl', 'stat', 'statistics', 'string', 'stringprep',
    'struct', 'subprocess', 'sunau', 'symbol', 'symtable', 'sys', 'sysconfig',
    'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile', 'termios', 'test',
    'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token', 'tokenize',
    'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types',
    'typing', 'typing_extensions', 'unicodedata', 'unittest', 'urllib', 'uu',
    'uuid', 'venv', 'warnings', 'wave', 'weakref', 'webbrowser', 'winreg',
    'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile',
    'zipimport', 'zlib', 'zoneinfo',
}

# Common PyPI package name mappings (import name -> PyPI name)
IMPORT_TO_PYPI = {
    'PIL': 'Pillow',
    'cv2': 'opencv-python',
    'sklearn': 'scikit-learn',
    'yaml': 'PyYAML',
    'bs4': 'beautifulsoup4',
    'dotenv': 'python-dotenv',
    'jwt': 'PyJWT',
    'google': 'google-api-python-client',
    'googleapiclient': 'google-api-python-client',
    'openai': 'openai',
    'anthropic': 'anthropic',
    'langchain': 'langchain',
    'llama_index': 'llama-index',
    'transformers': 'transformers',
    'torch': 'torch',
    'tensorflow': 'tensorflow',
    'keras': 'keras',
    'numpy': 'numpy',
    'pandas': 'pandas',
    'matplotlib': 'matplotlib',
    'scipy': 'scipy',
    'requests': 'requests',
    'flask': 'Flask',
    'django': 'Django',
    'fastapi': 'fastapi',
    'uvicorn': 'uvicorn',
    'pydantic': 'pydantic',
    'sqlalchemy': 'SQLAlchemy',
    'celery': 'celery',
    'redis': 'redis',
    'pymongo': 'pymongo',
    'psycopg2': 'psycopg2-binary',
    'mysqlclient': 'mysqlclient',
    'boto3': 'boto3',
    'botocore': 'botocore',
    'azure': 'azure-core',
    'google.cloud': 'google-cloud-core',
    'httpx': 'httpx',
    'aiohttp': 'aiohttp',
    'websockets': 'websockets',
    'pytest': 'pytest',
    'nose': 'nose',
    'mock': 'mock',
    'tqdm': 'tqdm',
    'rich': 'rich',
    'click': 'click',
    'typer': 'typer',
    'colorama': 'colorama',
    'toml': 'toml',
    'tomllib': 'tomli',  # backport for <3.11
    'lxml': 'lxml',
    'markdown': 'Markdown',
    'jinja2': 'Jinja2',
    'Crypto': 'pycryptodome',
    'cryptography': 'cryptography',
    'paramiko': 'paramiko',
    'fabric': 'fabric',
    'invoke': 'invoke',
    'numpy': 'numpy',
    'dateutil': 'python-dateutil',
    'pytz': 'pytz',
    'arrow': 'arrow',
    'pendulum': 'pendulum',
    'attr': 'attrs',
    'attrs': 'attrs',
    'marshmallow': 'marshmallow',
    'cerberus': 'Cerberus',
    'voluptuous': 'voluptuous',
}


class AnalyzePythonDependenciesTool(ToolBase):
    """Analyze Python imports to generate requirements.txt content."""

    @property
    def name(self) -> str:
        return "analyze_python_dependencies"

    @property
    def description(self) -> str:
        return "Analyze Python files to extract third-party dependencies for requirements.txt"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("directory", str, "Directory to scan for .py files", required=False, default="."),
            ToolParameter("include_versions", bool, "Try to detect installed versions", required=False, default=True),
            ToolParameter("exclude_patterns", str, "Comma-separated patterns to exclude (e.g., 'test,example')", required=False, default="")
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        directory = kwargs.get("directory", ".")
        include_versions = kwargs.get("include_versions", True)
        exclude_patterns = kwargs.get("exclude_patterns", "")

        if not context.is_safe_path(directory):
            return ToolResult(False, "", f"Path '{directory}' is outside project directory")

        target = context.project_root / directory
        if not target.exists():
            return ToolResult(False, "", f"Directory '{directory}' does not exist")

        try:
            # Parse exclude patterns
            excludes = [p.strip() for p in exclude_patterns.split(',') if p.strip()]

            # Find all Python files
            py_files = list(target.rglob("*.py"))

            # Filter out common non-source directories
            skip_dirs = {'node_modules', '__pycache__', '.git', 'venv', '.venv', 'env', '.tox', '.pytest_cache', 'build', 'dist', '.eggs'}
            py_files = [
                f for f in py_files
                if not any(skip in f.parts for skip in skip_dirs)
            ]

            # Apply custom excludes
            if excludes:
                py_files = [
                    f for f in py_files
                    if not any(exc in str(f) for exc in excludes)
                ]

            if not py_files:
                return ToolResult(False, "", f"No Python files found in '{directory}'")

            # Extract all imports
            all_imports: Set[str] = set()
            import_pattern = re.compile(
                r'^(?:from\s+([\w.]+)|import\s+([\w.]+(?:\s*,\s*[\w.]+)*))',
                re.MULTILINE
            )

            for py_file in py_files:
                try:
                    content = py_file.read_text(encoding='utf-8', errors='ignore')
                    matches = import_pattern.findall(content)
                    for match in matches:
                        if match[0]:  # from X import ...
                            module = match[0].split('.')[0]  # Get top-level module
                            all_imports.add(module)
                        if match[1]:  # import X, Y, Z
                            for mod in match[1].split(','):
                                module = mod.strip().split('.')[0]
                                if module:
                                    all_imports.add(module)
                except Exception:
                    continue

            # Filter out standard library and local imports
            third_party = set()
            local_modules = set()

            # Detect local modules (modules that exist as .py files in project)
            for py_file in py_files:
                rel_path = py_file.relative_to(context.project_root)
                # Module name from file path
                if rel_path.name == '__init__.py':
                    local_modules.add(rel_path.parent.name)
                else:
                    local_modules.add(rel_path.stem)

            for imp in all_imports:
                if imp in STDLIB_MODULES:
                    continue
                if imp in local_modules:
                    continue
                if imp.startswith('_'):
                    continue
                third_party.add(imp)

            if not third_party:
                return ToolResult(
                    True,
                    "No third-party dependencies found. Project uses only standard library modules.",
                    metadata={"files_scanned": len(py_files), "imports_found": len(all_imports)}
                )

            # Map import names to PyPI package names
            packages: Dict[str, str] = {}  # pypi_name -> version
            unmapped = []

            for imp in sorted(third_party):
                if imp in IMPORT_TO_PYPI:
                    pypi_name = IMPORT_TO_PYPI[imp]
                else:
                    # Assume import name matches package name (common case)
                    pypi_name = imp.replace('_', '-')

                packages[pypi_name] = ""

            # Try to get versions if requested
            if include_versions:
                try:
                    # Use pip show to get versions (more reliable than pip freeze)
                    for pkg_name in list(packages.keys()):
                        result = subprocess.run(
                            ["pip", "show", pkg_name],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            cwd=str(context.project_root)
                        )
                        if result.returncode == 0:
                            for line in result.stdout.split('\n'):
                                if line.startswith('Version:'):
                                    version = line.split(':', 1)[1].strip()
                                    packages[pkg_name] = f"=={version}"
                                    break
                except Exception:
                    pass  # Version detection failed, continue without versions

            # Generate requirements.txt content
            lines = []
            for pkg_name in sorted(packages.keys(), key=str.lower):
                version = packages[pkg_name]
                lines.append(f"{pkg_name}{version}")

            requirements_content = "\n".join(lines)

            # Generate summary
            summary = f"""# Requirements Analysis Summary
# Files scanned: {len(py_files)}
# Total imports found: {len(all_imports)}
# Third-party packages: {len(packages)}
# Standard library modules filtered out

{requirements_content}
"""

            return ToolResult(
                True,
                summary,
                metadata={
                    "files_scanned": len(py_files),
                    "imports_found": len(all_imports),
                    "third_party_packages": len(packages),
                    "packages": list(packages.keys()),
                    "requirements_content": requirements_content
                }
            )

        except Exception as e:
            return ToolResult(False, "", f"Error analyzing dependencies: {str(e)}")
