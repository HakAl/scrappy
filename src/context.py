"""
Codebase context management for the LLM Agent Team.

Provides automatic project exploration and context augmentation for prompts.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _get_config_defaults():
    """Lazy import of config defaults to avoid circular imports."""
    try:
        from src.cli.config.defaults import (
            TRUNCATE_RESEARCH_LARGE,
            TRUNCATE_ERROR_MESSAGE,
            TRUNCATE_PRIORITY_FILE,
        )
    except ImportError:
        try:
            from cli.config.defaults import (
                TRUNCATE_RESEARCH_LARGE,
                TRUNCATE_ERROR_MESSAGE,
                TRUNCATE_PRIORITY_FILE,
            )
        except ImportError:
            # Fallback values if imports fail
            TRUNCATE_RESEARCH_LARGE = 1500
            TRUNCATE_ERROR_MESSAGE = 500
            TRUNCATE_PRIORITY_FILE = 3000
    return TRUNCATE_RESEARCH_LARGE, TRUNCATE_ERROR_MESSAGE, TRUNCATE_PRIORITY_FILE


def _get_config_extensions():
    """Lazy import of config extensions to avoid circular imports."""
    try:
        from src.cli.config.extensions import EXTENSIONS_BY_CATEGORY, ENTRY_POINT_FILES
    except ImportError:
        try:
            from cli.config.extensions import EXTENSIONS_BY_CATEGORY, ENTRY_POINT_FILES
        except ImportError:
            # Fallback values if imports fail
            EXTENSIONS_BY_CATEGORY = {
                'python': ['.py'],
                'javascript': ['.js', '.jsx', '.ts', '.tsx'],
                'web': ['.html', '.css', '.scss'],
                'config': ['.json', '.yaml', '.yml', '.toml', '.ini'],
                'docs': ['.md', '.rst', '.txt'],
                'other': []
            }
            ENTRY_POINT_FILES = ['main.py', '__main__.py', 'app.py', 'cli.py', 'setup.py']
    return EXTENSIONS_BY_CATEGORY, ENTRY_POINT_FILES


def _get_config_paths():
    """Lazy import of config paths to avoid circular imports."""
    try:
        from src.cli.config.paths import SKIP_DIRS
    except ImportError:
        try:
            from cli.config.paths import SKIP_DIRS
        except ImportError:
            # Fallback values if imports fail
            SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', '.env', 'dist', 'build'}
    return SKIP_DIRS


class CodebaseContext:
    """
    Manages codebase knowledge and context for intelligent prompt augmentation.

    Usage:
        context = CodebaseContext("/path/to/project")
        context.explore()  # Scan and analyze the codebase

        # Get context for prompts
        augmented_prompt = context.augment_prompt("Fix the bug in auth")
    """

    def __init__(self, project_path: Optional[str] = None):
        """
        Initialize codebase context.

        Args:
            project_path: Path to project root. Defaults to current directory.
        """
        self.project_path = Path(project_path or ".").resolve()
        self.summary: Optional[str] = None
        self.structure: dict = {}
        self.key_files: dict = {}
        self.file_index: dict = {}
        self.git_history: dict = {}  # Git history info
        self.explored_at: Optional[datetime] = None
        self.cache_file = self.project_path / ".llm_team_context.json"

        # Cached platform and tool detection
        self._platform: Optional[str] = None
        self._tool_cache: dict = {}

        # Try to load cached context
        self._load_cache()

    def is_explored(self) -> bool:
        """Check if the codebase has been explored."""
        return self.explored_at is not None

    def explore(self, force: bool = False) -> dict:
        """
        Explore the codebase and build context.

        Args:
            force: Force re-exploration even if cache exists

        Returns:
            Dict with exploration results
        """
        if self.is_explored() and not force:
            return {
                'status': 'cached',
                'explored_at': self.explored_at.isoformat(),
                'summary': self.summary
            }

        # Scan for source files
        self.file_index = self._scan_files()

        # Analyze structure
        self.structure = self._analyze_structure()

        # Read key files
        self.key_files = self._read_key_files()

        # Get git history if available
        if self.structure.get('has_git'):
            self.git_history = self._get_git_history()

        # Mark exploration time (summary will be generated when needed)
        self.explored_at = datetime.now()

        # Save to cache
        self._save_cache()

        return {
            'status': 'explored',
            'explored_at': self.explored_at.isoformat(),
            'total_files': self.structure.get('total_files', 0),
            'file_types': self.structure.get('by_type', {}),
            'directories': self.structure.get('directories', []),
            'has_git_history': bool(self.git_history)
        }

    def generate_summary(self, llm_func) -> str:
        """
        Generate a natural language summary using an LLM.

        Args:
            llm_func: Function that takes a prompt and returns response text

        Returns:
            Generated summary string
        """
        if not self.is_explored():
            self.explore()

        # Build context for LLM
        context_parts = [
            f"Project: {self.project_path.name}",
            f"Total files: {self.structure.get('total_files', 0)}",
            f"File types: {', '.join(f'{k}={v}' for k, v in self.structure.get('by_type', {}).items() if v > 0)}",
            f"Directories: {', '.join(self.structure.get('directories', []))}",
        ]

        # Add project indicators
        if self.structure.get('has_readme'):
            context_parts.append("Has README")
        if self.structure.get('has_requirements'):
            context_parts.append("Python project (requirements.txt)")
        if self.structure.get('has_package_json'):
            context_parts.append("Node.js project")
        if self.structure.get('has_pyproject'):
            context_parts.append("Modern Python (pyproject.toml)")
        if self.structure.get('has_git'):
            context_parts.append("Version controlled with Git")

        # Add git history info
        git_context = ""
        if self.git_history:
            git_parts = []
            if self.git_history.get('current_branch'):
                git_parts.append(f"Current branch: {self.git_history['current_branch']}")
            if self.git_history.get('recent_commits'):
                commits = self.git_history['recent_commits'][:5]
                git_parts.append("Recent commits:\n" + "\n".join(f"  {c}" for c in commits))
            if self.git_history.get('top_contributors'):
                contribs = [f"{c['name']} ({c['commits']} commits)" for c in self.git_history['top_contributors'][:3]]
                git_parts.append(f"Top contributors: {', '.join(contribs)}")
            if git_parts:
                git_context = "\n\nGit History:\n" + "\n".join(git_parts)

        # Build file contents section (limited)
        file_contents = ""
        TRUNCATE_RESEARCH_LARGE, _, _ = _get_config_defaults()
        for filename, content in list(self.key_files.items())[:5]:
            # Truncate to avoid token explosion
            truncated = content[:TRUNCATE_RESEARCH_LARGE] if len(content) > TRUNCATE_RESEARCH_LARGE else content
            file_contents += f"\n--- {filename} ---\n{truncated}\n"

        prompt = f"""Analyze this codebase and provide a concise technical summary.

{chr(10).join(context_parts)}
{git_context}

Key Files:
{file_contents}

Provide a brief summary (3-5 sentences) covering:
1. What this project does
2. Main technologies/frameworks
3. Code organization pattern
4. Development activity (if git history available)

Be concise and technical. No fluff."""

        self.summary = llm_func(prompt)
        self._save_cache()

        return self.summary

    def augment_prompt(self, user_prompt: str, include_files: bool = False) -> str:
        """
        Augment a user prompt with relevant codebase context.

        Args:
            user_prompt: The original user prompt
            include_files: Whether to include file listings

        Returns:
            Augmented prompt with context
        """
        if not self.is_explored():
            return user_prompt

        context_parts = []

        # Add project summary if available
        if self.summary:
            context_parts.append(f"Project Context:\n{self.summary}")

        # Add structure info
        if self.structure:
            structure_info = [
                f"Project: {self.project_path.name}",
                f"Files: {self.structure.get('total_files', 0)} total",
                f"Languages: {', '.join(k for k, v in self.structure.get('by_type', {}).items() if v > 0 and k != 'other')}",
            ]
            context_parts.append("Structure:\n" + "\n".join(structure_info))

        # Add git history info
        if self.git_history:
            git_info = []
            if self.git_history.get('current_branch'):
                git_info.append(f"Branch: {self.git_history['current_branch']}")
            if self.git_history.get('recent_commits'):
                commits = self.git_history['recent_commits'][:5]
                git_info.append(f"Recent commits:\n" + "\n".join(f"  {c}" for c in commits))
            if self.git_history.get('recently_changed_files'):
                changed = self.git_history['recently_changed_files'][:10]
                git_info.append(f"Recently changed: {', '.join(changed)}")
            if git_info:
                context_parts.append("Git History:\n" + "\n".join(git_info))

        # Optionally include relevant file listings
        if include_files and self.file_index:
            # Include Python files as they're most relevant
            py_files = self.file_index.get('python', [])[:20]
            if py_files:
                context_parts.append(f"Python files:\n" + "\n".join(f"  - {f}" for f in py_files))

        if context_parts:
            context_block = "\n\n".join(context_parts)
            return f"""[Codebase Context]
{context_block}

[User Request]
{user_prompt}"""

        return user_prompt

    def get_relevant_context(self, query: str) -> str:
        """
        Get context relevant to a specific query.

        Args:
            query: The query to find relevant context for

        Returns:
            Relevant context string
        """
        if not self.is_explored():
            return ""

        # Simple keyword-based relevance (could be enhanced with embeddings)
        query_lower = query.lower()
        relevant_parts = []

        # Always include summary
        if self.summary:
            relevant_parts.append(f"Project: {self.summary}")

        # Check for file-specific keywords
        if any(word in query_lower for word in ['file', 'module', 'class', 'function', 'import']):
            # Include file structure
            py_files = self.file_index.get('python', [])[:10]
            if py_files:
                relevant_parts.append("Key Python files:\n" + "\n".join(f"  {f}" for f in py_files))

        # Check for config-related queries
        if any(word in query_lower for word in ['config', 'setup', 'install', 'dependency', 'require']):
            if 'requirements.txt' in self.key_files:
                _, TRUNCATE_ERROR_MESSAGE, _ = _get_config_defaults()
                deps = self.key_files['requirements.txt'][:TRUNCATE_ERROR_MESSAGE]
                relevant_parts.append(f"Dependencies:\n{deps}")

        # Check for architecture queries
        if any(word in query_lower for word in ['architecture', 'structure', 'organize', 'pattern']):
            dirs = self.structure.get('directories', [])
            if dirs:
                relevant_parts.append(f"Project directories: {', '.join(dirs)}")

        return "\n\n".join(relevant_parts)

    def _scan_files(self) -> dict:
        """Scan project for source files."""
        EXTENSIONS_BY_CATEGORY, _ = _get_config_extensions()
        SKIP_DIRS = _get_config_paths()
        files = {k: [] for k in EXTENSIONS_BY_CATEGORY}

        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

            try:
                rel_root = Path(root).relative_to(self.project_path)
            except ValueError:
                continue

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                file_path = str(rel_root / filename) if str(rel_root) != '.' else filename
                ext = Path(filename).suffix.lower()

                categorized = False
                for category, exts in EXTENSIONS_BY_CATEGORY.items():
                    if ext in exts:
                        files[category].append(file_path)
                        categorized = True
                        break

                if not categorized:
                    files['other'].append(file_path)

        return files

    def _analyze_structure(self) -> dict:
        """Analyze project structure using file_index data."""
        # Build list of all files for marker detection
        all_files = []
        for file_list in self.file_index.values():
            all_files.extend(file_list)

        # Helper to check if marker exists anywhere in tree
        def has_marker(marker_name):
            return any(f.endswith(marker_name) or f == marker_name for f in all_files)

        # Helper to check if marker exists in root only
        def has_root_marker(marker_name):
            return marker_name in all_files

        structure = {
            'total_files': sum(len(f) for f in self.file_index.values()),
            'by_type': {k: len(v) for k, v in self.file_index.items()},
            'has_readme': has_root_marker('README.md') or has_root_marker('README'),
            # Project markers - check anywhere in tree (supports monorepos)
            'has_requirements': has_marker('requirements.txt'),
            'has_package_json': has_marker('package.json'),
            'has_pyproject': has_marker('pyproject.toml'),
            'has_git': (self.project_path / '.git').exists(),
            # Java/JVM project markers
            'has_pom_xml': has_marker('pom.xml'),
            'has_build_gradle': has_marker('build.gradle') or has_marker('build.gradle.kts'),
            # Rust project marker
            'has_cargo_toml': has_marker('Cargo.toml'),
            # Go project marker
            'has_go_mod': has_marker('go.mod'),
            # Ruby project marker
            'has_gemfile': has_marker('Gemfile'),
            # .NET project marker
            'has_csproj': any(f.endswith('.csproj') or f.endswith('.sln') for f in all_files),
            'directories': [],
        }

        SKIP_DIRS = _get_config_paths()
        for item in self.project_path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name not in SKIP_DIRS:
                structure['directories'].append(item.name)

        return structure

    def _read_key_files(self) -> dict:
        """Read important project files."""
        key_contents = {}

        # Priority files
        priority_files = [
            'README.md', 'README', 'setup.py', 'pyproject.toml',
            'package.json', 'requirements.txt', 'Cargo.toml', 'go.mod'
        ]

        for filename in priority_files:
            file_path = self.project_path / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if len(content) > 5000:
                        content = content[:5000] + "\n... (truncated)"
                    key_contents[filename] = content
                except Exception:
                    pass

        # Read main Python entry points
        py_files = self.file_index.get('python', [])
        _, ENTRY_POINT_FILES = _get_config_extensions()
        _, _, TRUNCATE_PRIORITY_FILE = _get_config_defaults()

        for entry in ENTRY_POINT_FILES:
            for f in py_files:
                if f.endswith(entry) or f == entry:
                    file_path = self.project_path / f
                    if file_path.exists():
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                            if len(content) > TRUNCATE_PRIORITY_FILE:
                                content = content[:TRUNCATE_PRIORITY_FILE] + "\n... (truncated)"
                            key_contents[f] = content
                        except Exception:
                            pass
                    break

        return key_contents

    def _get_git_history(self) -> dict:
        """Get git history information."""
        git_info = {}

        try:
            # Get recent commits
            result = subprocess.run(
                ['git', 'log', '--oneline', '-20', '--decorate'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                git_info['recent_commits'] = result.stdout.strip().split('\n')[:20]

            # Get active branches
            result = subprocess.run(
                ['git', 'branch', '-a', '--no-color'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                branches = [b.strip().lstrip('* ') for b in result.stdout.strip().split('\n')]
                git_info['branches'] = branches[:10]

            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                git_info['current_branch'] = result.stdout.strip()

            # Get contributors (top 5)
            result = subprocess.run(
                ['git', 'shortlog', '-sn', '--no-merges', 'HEAD'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                contributors = []
                for line in result.stdout.strip().split('\n')[:5]:
                    line = line.strip()
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            contributors.append({'commits': int(parts[0].strip()), 'name': parts[1].strip()})
                git_info['top_contributors'] = contributors

            # Get files changed in last 10 commits
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD~10..HEAD'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                changed = list(set(result.stdout.strip().split('\n')))
                git_info['recently_changed_files'] = changed[:20]

            # Get repository age (first commit date)
            result = subprocess.run(
                ['git', 'log', '--reverse', '--format=%ci', '-1'],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                git_info['first_commit_date'] = result.stdout.strip()

        except (subprocess.TimeoutExpired, Exception):
            pass  # Git info is optional

        return git_info

    def _save_cache(self):
        """Save context to disk cache."""
        try:
            cache_data = {
                'explored_at': self.explored_at.isoformat() if self.explored_at else None,
                'summary': self.summary,
                'structure': self.structure,
                'file_index': self.file_index,
                'git_history': self.git_history,
                # Don't cache key_files content - too large
            }

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass  # Caching is optional

    def _load_cache(self):
        """Load context from disk cache."""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            if cache_data.get('explored_at'):
                self.explored_at = datetime.fromisoformat(cache_data['explored_at'])
            self.summary = cache_data.get('summary')
            self.structure = cache_data.get('structure', {})
            self.file_index = cache_data.get('file_index', {})
            self.git_history = cache_data.get('git_history', {})

            # Re-read key files if we have structure
            if self.structure:
                self.key_files = self._read_key_files()
        except Exception:
            pass  # Cache loading is optional

    def clear_cache(self):
        """Clear the cached context."""
        if self.cache_file.exists():
            self.cache_file.unlink()

        self.summary = None
        self.structure = {}
        self.key_files = {}
        self.file_index = {}
        self.git_history = {}
        self.explored_at = None

    def get_status(self) -> dict:
        """Get current context status."""
        status = {
            'project_path': str(self.project_path),
            'is_explored': self.is_explored(),
            'has_summary': self.summary is not None,
            'explored_at': self.explored_at.isoformat() if self.explored_at else None,
            'total_files': self.structure.get('total_files', 0),
            'cache_file': str(self.cache_file),
            'cache_exists': self.cache_file.exists(),
            'has_git_history': bool(self.git_history),
        }

        # Add git history summary
        if self.git_history:
            status['git_branch'] = self.git_history.get('current_branch', 'unknown')
            status['git_commits'] = len(self.git_history.get('recent_commits', []))
            status['git_recently_changed'] = len(self.git_history.get('recently_changed_files', []))

        return status

    def get_summary(self) -> str:
        """Get the project summary text."""
        if self.summary:
            return self.summary

        # If no summary, return basic info
        if self.is_explored():
            return f"Project: {self.project_path.name}, {self.structure.get('total_files', 0)} files"

        return "Project not explored yet"

    def get_project_type(self) -> str:
        """
        Determine the primary project type based on detected markers.

        Returns:
            String identifier for project type (e.g., 'python', 'java', 'nodejs')
        """
        if not self.structure:
            self.explore()

        # Priority order for project type detection
        if self.structure.get('has_requirements') or self.structure.get('has_pyproject'):
            return 'python'
        elif self.structure.get('has_pom_xml'):
            return 'java'
        elif self.structure.get('has_build_gradle'):
            return 'java'
        elif self.structure.get('has_package_json'):
            return 'nodejs'
        elif self.structure.get('has_cargo_toml'):
            return 'rust'
        elif self.structure.get('has_go_mod'):
            return 'go'
        elif self.structure.get('has_gemfile'):
            return 'ruby'
        elif self.structure.get('has_csproj'):
            return 'dotnet'
        else:
            return 'unknown'

    def get_platform(self) -> str:
        """
        Get the current platform (cached).

        Returns:
            Platform identifier: 'windows', 'darwin', 'linux', or 'unix'
        """
        if self._platform is None:
            if sys.platform == 'win32':
                self._platform = 'windows'
            elif sys.platform == 'darwin':
                self._platform = 'darwin'
            elif sys.platform.startswith('linux'):
                self._platform = 'linux'
            else:
                self._platform = 'unix'

        return self._platform

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a command-line tool is available (cached).

        Args:
            tool_name: Name of the tool/command to check

        Returns:
            True if tool is available, False otherwise
        """
        if tool_name not in self._tool_cache:
            self._tool_cache[tool_name] = shutil.which(tool_name) is not None

        return self._tool_cache[tool_name]

    def get_languages(self) -> list:
        """
        Get list of programming languages used in the codebase.

        Returns:
            List of language names based on file extensions found
        """
        if not self.file_index:
            self.explore()

        languages = []
        if self.file_index.get('python'):
            languages.append('python')
        if self.file_index.get('javascript'):
            languages.append('javascript')
        # Note: javascript category includes .ts, .tsx files
        if any(f.endswith('.ts') or f.endswith('.tsx') for f in self.file_index.get('javascript', [])):
            if 'typescript' not in languages:
                languages.append('typescript')

        return languages

    def get_language_stats(self) -> dict:
        """
        Get count of files per programming language.

        Returns:
            Dict mapping language name to file count
        """
        if not self.file_index:
            self.explore()

        return {k: len(v) for k, v in self.file_index.items() if v}

    def get_primary_language(self) -> str:
        """
        Determine primary language based on file count.

        Returns:
            Language with most files, or 'unknown' if no code files
        """
        stats = self.get_language_stats()

        # Only consider actual code languages
        code_languages = {k: v for k, v in stats.items()
                         if k in ('python', 'javascript') and v > 0}

        if not code_languages:
            return 'unknown'

        return max(code_languages.items(), key=lambda x: x[1])[0]

    def find_project_markers(self) -> list:
        """
        Find all project marker files (package.json, requirements.txt, etc.) anywhere in tree.

        Returns:
            List of relative paths to project marker files
        """
        if not self.file_index:
            self.explore()

        marker_names = {
            'package.json', 'requirements.txt', 'pyproject.toml', 'setup.py',
            'pom.xml', 'build.gradle', 'build.gradle.kts',
            'Cargo.toml', 'go.mod', 'Gemfile', 'composer.json'
        }

        markers = []
        for file_path in self.file_index.get('config', []):
            if any(file_path.endswith(marker) for marker in marker_names):
                markers.append(file_path)

        # Also check 'other' category for markers not in config
        for file_path in self.file_index.get('other', []):
            if any(file_path.endswith(marker) for marker in marker_names):
                markers.append(file_path)

        # Also check 'docs' category (requirements.txt has .txt extension)
        for file_path in self.file_index.get('docs', []):
            if any(file_path.endswith(marker) for marker in marker_names):
                markers.append(file_path)

        return markers

    def get_marker_locations(self) -> dict:
        """
        Map directories to their project marker files.

        Returns:
            Dict mapping directory path to marker filename
        """
        markers = self.find_project_markers()
        locations = {}

        for marker_path in markers:
            # Get directory containing the marker
            if '/' in marker_path or '\\' in marker_path:
                # Normalize to forward slashes for consistency
                normalized = marker_path.replace('\\', '/')
                parts = normalized.rsplit('/', 1)
                directory = parts[0]
                marker_name = parts[1]
            else:
                # Marker in root directory
                directory = '.'
                marker_name = marker_path

            locations[directory] = marker_name

        return locations

    def get_sub_projects(self) -> dict:
        """
        Detect project types in subdirectories (for monorepos).

        Returns:
            Dict mapping subdirectory name to project type
        """
        marker_locations = self.get_marker_locations()
        sub_projects = {}

        # Map marker files to project types
        marker_to_type = {
            'package.json': 'nodejs',
            'requirements.txt': 'python',
            'pyproject.toml': 'python',
            'setup.py': 'python',
            'pom.xml': 'java',
            'build.gradle': 'java',
            'build.gradle.kts': 'java',
            'Cargo.toml': 'rust',
            'go.mod': 'go',
            'Gemfile': 'ruby',
            'composer.json': 'php',
        }

        for directory, marker in marker_locations.items():
            if directory != '.':  # Skip root
                project_type = marker_to_type.get(marker, 'unknown')
                # Use the top-level directory name as key
                top_dir = directory.split('/')[0] if '/' in directory else directory
                # If we already have this directory, keep the first one found
                if top_dir not in sub_projects:
                    sub_projects[top_dir] = project_type
                # For nested paths like services/auth-api, also track the full path
                if '/' in directory:
                    sub_projects[directory] = project_type

        return sub_projects
