"""
Codebase context management for the LLM Agent Team.

Provides automatic project exploration and context augmentation for prompts.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .file_scanner import FileScanner

logger = logging.getLogger(__name__)
from .cache import ContextCache
from .platform import PlatformDetector
from .git_history import GitHistoryReader
from .project_detector import ProjectDetector
from .config_loader import get_truncation_defaults, get_extensions_config, get_paths_config


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

        # Validate path
        self._path_valid = True
        if not self.project_path.exists():
            logger.warning(f"Project path does not exist: {self.project_path}")
            self._path_valid = False
        elif not self.project_path.is_dir():
            logger.warning(f"Project path is not a directory: {self.project_path}")
            self._path_valid = False

        self.summary: Optional[str] = None
        self.structure: dict = {}
        self.key_files: dict = {}
        self.file_index: dict = {}
        self.git_history: dict = {}  # Git history info
        self.explored_at: Optional[datetime] = None
        self.cache_file = self.project_path / ".llm_team_context.json"

        # Component instances
        self._file_scanner = FileScanner()
        self._cache = ContextCache()
        self._platform_detector = PlatformDetector()
        self._git_history_reader = GitHistoryReader()
        self._project_detector = ProjectDetector(self.project_path)

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
        defaults = get_truncation_defaults()
        truncate_limit = defaults['research_large']
        for filename, content in list(self.key_files.items())[:5]:
            # Truncate to avoid token explosion
            truncated = content[:truncate_limit] if len(content) > truncate_limit else content
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
                defaults = get_truncation_defaults()
                deps = self.key_files['requirements.txt'][:defaults['error_message']]
                relevant_parts.append(f"Dependencies:\n{deps}")

        # Check for architecture queries
        if any(word in query_lower for word in ['architecture', 'structure', 'organize', 'pattern']):
            dirs = self.structure.get('directories', [])
            if dirs:
                relevant_parts.append(f"Project directories: {', '.join(dirs)}")

        return "\n\n".join(relevant_parts)

    def _scan_files(self) -> dict:
        """Scan project for source files."""
        return self._file_scanner.scan_files(self.project_path)

    def _analyze_structure(self) -> dict:
        """Analyze project structure using file_index data."""
        # Update project detector with current file index
        self._project_detector.set_file_index(self.file_index)

        # Get markers from project detector
        markers = self._project_detector.detect_markers()

        structure = {
            'total_files': sum(len(f) for f in self.file_index.values()),
            'by_type': {k: len(v) for k, v in self.file_index.items()},
            'directories': [],
        }

        # Merge markers into structure
        structure.update(markers)

        # Get directories (only if path is valid)
        if self._path_valid and self.project_path.exists() and self.project_path.is_dir():
            skip_dirs = get_paths_config()
            for item in self.project_path.iterdir():
                if item.is_dir() and not item.name.startswith('.') and item.name not in skip_dirs:
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
        _, entry_point_files = get_extensions_config()
        defaults = get_truncation_defaults()
        truncate_priority = defaults['priority_file']

        for entry in entry_point_files:
            for f in py_files:
                if f.endswith(entry) or f == entry:
                    file_path = self.project_path / f
                    if file_path.exists():
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                            if len(content) > truncate_priority:
                                content = content[:truncate_priority] + "\n... (truncated)"
                            key_contents[f] = content
                        except Exception:
                            pass
                    break

        return key_contents

    def _get_git_history(self) -> dict:
        """Get git history information."""
        return self._git_history_reader.get_history(self.project_path)

    def _save_cache(self):
        """Save context to disk cache."""
        cache_data = {
            'explored_at': self.explored_at,
            'summary': self.summary,
            'structure': self.structure,
            'file_index': self.file_index,
            'git_history': self.git_history,
            # Don't cache key_files content - too large
        }
        self._cache.save(self.cache_file, cache_data)

    def _load_cache(self):
        """Load context from disk cache."""
        cache_data = self._cache.load(self.cache_file)
        if cache_data is None:
            return

        self.explored_at = cache_data.get('explored_at')
        self.summary = cache_data.get('summary')
        self.structure = cache_data.get('structure', {})
        self.file_index = cache_data.get('file_index', {})
        self.git_history = cache_data.get('git_history', {})

        # Re-read key files if we have structure
        if self.structure:
            self.key_files = self._read_key_files()

    def clear_cache(self):
        """Clear the cached context."""
        self._cache.clear(self.cache_file)

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

        # Ensure project detector has current file index
        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_project_type()

    def get_platform(self) -> str:
        """
        Get the current platform (cached).

        Returns:
            Platform identifier: 'windows', 'darwin', 'linux', or 'unix'
        """
        return self._platform_detector.get_platform()

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a command-line tool is available (cached).

        Args:
            tool_name: Name of the tool/command to check

        Returns:
            True if tool is available, False otherwise
        """
        return self._platform_detector.has_tool(tool_name)

    def get_languages(self) -> list:
        """
        Get list of programming languages used in the codebase.

        Returns:
            List of language names based on file extensions found
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_languages()

    def get_language_stats(self) -> dict:
        """
        Get count of files per programming language.

        Returns:
            Dict mapping language name to file count
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_language_stats()

    def get_primary_language(self) -> str:
        """
        Determine primary language based on file count.

        Returns:
            Language with most files, or 'unknown' if no code files
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_primary_language()

    def find_project_markers(self) -> list:
        """
        Find all project marker files (package.json, requirements.txt, etc.) anywhere in tree.

        Returns:
            List of relative paths to project marker files
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.find_project_markers()

    def get_marker_locations(self) -> dict:
        """
        Map directories to their project marker files.

        Returns:
            Dict mapping directory path to marker filename
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_marker_locations()

    def get_sub_projects(self) -> dict:
        """
        Detect project types in subdirectories (for monorepos).

        Returns:
            Dict mapping subdirectory name to project type
        """
        if not self.file_index:
            self.explore()

        self._project_detector.set_file_index(self.file_index)
        return self._project_detector.get_sub_projects()
