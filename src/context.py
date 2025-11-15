"""
Codebase context management for the LLM Agent Team.

Provides automatic project exploration and context augmentation for prompts.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


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
        self.explored_at: Optional[datetime] = None
        self.cache_file = self.project_path / ".llm_team_context.json"

        # Try to load cached context
        self._load_cache()

    def is_explored(self) -> bool:
        """Check if the codebase has been explored."""
        return self.summary is not None and self.explored_at is not None

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

        # Mark exploration time (summary will be generated when needed)
        self.explored_at = datetime.now()

        # Save to cache
        self._save_cache()

        return {
            'status': 'explored',
            'explored_at': self.explored_at.isoformat(),
            'total_files': self.structure.get('total_files', 0),
            'file_types': self.structure.get('by_type', {}),
            'directories': self.structure.get('directories', [])
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

        # Build file contents section (limited)
        file_contents = ""
        for filename, content in list(self.key_files.items())[:5]:
            # Truncate to avoid token explosion
            truncated = content[:1500] if len(content) > 1500 else content
            file_contents += f"\n--- {filename} ---\n{truncated}\n"

        prompt = f"""Analyze this codebase and provide a concise technical summary.

{chr(10).join(context_parts)}

Key Files:
{file_contents}

Provide a brief summary (3-5 sentences) covering:
1. What this project does
2. Main technologies/frameworks
3. Code organization pattern

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
                deps = self.key_files['requirements.txt'][:500]
                relevant_parts.append(f"Dependencies:\n{deps}")

        # Check for architecture queries
        if any(word in query_lower for word in ['architecture', 'structure', 'organize', 'pattern']):
            dirs = self.structure.get('directories', [])
            if dirs:
                relevant_parts.append(f"Project directories: {', '.join(dirs)}")

        return "\n\n".join(relevant_parts)

    def _scan_files(self) -> dict:
        """Scan project for source files."""
        extensions = {
            'python': ['.py'],
            'javascript': ['.js', '.jsx', '.ts', '.tsx'],
            'web': ['.html', '.css', '.scss'],
            'config': ['.json', '.yaml', '.yml', '.toml', '.ini'],
            'docs': ['.md', '.rst', '.txt'],
            'other': []
        }

        files = {k: [] for k in extensions}
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'dist', 'build', '.tox', '.pytest_cache'}

        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]

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
                for category, exts in extensions.items():
                    if ext in exts:
                        files[category].append(file_path)
                        categorized = True
                        break

                if not categorized and ext:
                    files['other'].append(file_path)

        return files

    def _analyze_structure(self) -> dict:
        """Analyze project structure."""
        structure = {
            'total_files': sum(len(f) for f in self.file_index.values()),
            'by_type': {k: len(v) for k, v in self.file_index.items()},
            'has_readme': (self.project_path / 'README.md').exists() or (self.project_path / 'README').exists(),
            'has_requirements': (self.project_path / 'requirements.txt').exists(),
            'has_package_json': (self.project_path / 'package.json').exists(),
            'has_pyproject': (self.project_path / 'pyproject.toml').exists(),
            'has_git': (self.project_path / '.git').exists(),
            'directories': [],
        }

        for item in self.project_path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name not in {'__pycache__', 'node_modules', 'venv', '.venv'}:
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
        entry_points = ['main.py', '__main__.py', 'app.py', 'cli.py']

        for entry in entry_points:
            for f in py_files:
                if f.endswith(entry) or f == entry:
                    file_path = self.project_path / f
                    if file_path.exists():
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                            if len(content) > 3000:
                                content = content[:3000] + "\n... (truncated)"
                            key_contents[f] = content
                        except Exception:
                            pass
                    break

        return key_contents

    def _save_cache(self):
        """Save context to disk cache."""
        try:
            cache_data = {
                'explored_at': self.explored_at.isoformat() if self.explored_at else None,
                'summary': self.summary,
                'structure': self.structure,
                'file_index': self.file_index,
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
        self.explored_at = None

    def get_status(self) -> dict:
        """Get current context status."""
        return {
            'project_path': str(self.project_path),
            'is_explored': self.is_explored(),
            'has_summary': self.summary is not None,
            'explored_at': self.explored_at.isoformat() if self.explored_at else None,
            'total_files': self.structure.get('total_files', 0),
            'cache_file': str(self.cache_file),
            'cache_exists': self.cache_file.exists()
        }
