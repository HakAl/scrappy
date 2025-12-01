"""
Codebase exploration and analysis functionality.
Handles scanning, analyzing, and summarizing codebases.
"""

import os
from pathlib import Path
from datetime import datetime

from .io_interface import CLIIOProtocol
from .config.defaults import (
    MAX_TOKENS_SUMMARY,
    TEMPERATURE_LOW,
    TRUNCATE_PRIORITY_FILE,
    TRUNCATE_FILE_CONTENT,
)
from .config.extensions import (
    EXTENSIONS_BY_CATEGORY,
    PRIORITY_FILES,
    ENTRY_POINT_FILES,
)
from .config.paths import SKIP_DIRS


class CLICodebaseAnalysis:
    """Handles codebase exploration and analysis operations."""

    def __init__(self, orchestrator, io: CLIIOProtocol):
        """Initialize codebase analyzer.

        Args:
            orchestrator: The AgentOrchestrator instance
            io: I/O interface for output
        """
        self.orchestrator = orchestrator
        self.io = io

    def explore_codebase(self, path: str = ""):
        """Explore and generate a comprehensive summary of a codebase.

        Scans the directory structure, reads key files, and uses LLM to generate
        a summary including project type, purpose, technologies, and architecture.

        For the current project directory, uses context-aware exploration with
        persistence. For external directories, performs standalone exploration.

        Args:
            path: Directory path to explore. If empty, prompts user for input.

        State Changes:
            - Adds discovery to orchestrator working memory
            - For current project: Updates orchestrator.context with exploration data

        Side Effects:
            - Reads files from disk to analyze codebase
            - Makes LLM API call to generate summary
            - Writes progress and summary to stdout via self.io
            - May write CODEBASE_SUMMARY.md file if user confirms

        Returns:
            None
        """
        if not path:
            path = "."

        path = Path(path).resolve()
        if not path.exists():
            self.io.secho(f"Path does not exist: {path}", fg=self.io.theme.error)
            return

        if not path.is_dir():
            self.io.secho(f"Not a directory: {path}", fg=self.io.theme.error)
            return

        self.io.secho(f"\nExploring: {path}", bold=True)
        self.io.echo("-" * 50)

        # Check if exploring current project or different directory
        is_current_project = path == self.orchestrator.context.project_path

        if is_current_project:
            # Use orchestrator's context system for proper persistence
            self.io.echo("Using context-aware exploration...")
            with self.io.progress(total=2, description="Scanning codebase") as progress:
                # Step 1: Explore and scan files
                result = self.orchestrator.context.explore(force=True)
                progress.advance(1)

                # Step 2: Generate summary with LLM (this saves to context)
                def llm_summary(prompt):
                    response = self.orchestrator.delegate(
                        self.orchestrator.brain,
                        prompt,
                        system_prompt="You are a code analysis expert. Analyze codebases and provide clear, actionable summaries. Be concise but thorough.",
                        max_tokens=MAX_TOKENS_SUMMARY,
                        temperature=TEMPERATURE_LOW
                    )
                    return response.content

                summary = self.orchestrator.context.generate_summary(llm_summary)
                progress.advance(1)

            # Add discovery to working memory
            self.orchestrator.working_memory.add_discovery(
                f"Explored codebase: {result.get('total_files', 0)} files, {', '.join(result.get('directories', [])[:5])}",
                str(path)
            )
        else:
            # For external directories, use standalone exploration (legacy behavior)
            self.io.echo("Exploring external directory (not persisted to context)...")
            with self.io.progress(total=4, description="Scanning codebase") as progress:
                source_files = self._find_source_files(path)
                progress.advance(1)
                structure = self._analyze_structure(path, source_files)
                progress.advance(1)
                key_contents = self._read_key_files(path, source_files)
                progress.advance(1)
                summary = self._generate_codebase_summary(path, structure, key_contents)
                progress.advance(1)

            # Still add to working memory as a discovery
            self.orchestrator.working_memory.add_discovery(
                f"Explored external codebase: {structure.get('total_files', 0)} files",
                str(path)
            )

        self.io.echo()
        self.io.secho("Codebase Summary:", bold=True)
        self.io.echo("-" * 50)
        self.io.echo(summary)

        if is_current_project:
            self.io.secho("\nContext saved! Use /context to view status.", fg=self.io.theme.success)

        # Offer to save summary
        if self.io.confirm("\nSave summary to file?", default=False):
            summary_file = path / "CODEBASE_SUMMARY.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"# Codebase Summary\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n")
                f.write(summary)
            self.io.secho(f"Saved to: {summary_file}", fg=self.io.theme.success)

    def _find_source_files(self, path: Path) -> dict:
        """Find all source files organized by type/category.

        Walks the directory tree, skipping common non-source directories,
        and categorizes files by extension (python, javascript, config, etc.).

        Args:
            path: Root directory path to scan.

        Returns:
            dict: Mapping of category names to lists of relative file paths.
                Categories include: python, javascript, config, docs, other.
        """
        files = {k: [] for k in EXTENSIONS_BY_CATEGORY}

        for root, dirs, filenames in os.walk(path):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

            rel_root = Path(root).relative_to(path)

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                file_path = rel_root / filename
                ext = Path(filename).suffix.lower()

                categorized = False
                for category, exts in EXTENSIONS_BY_CATEGORY.items():
                    if ext in exts:
                        files[category].append(str(file_path))
                        categorized = True
                        break

                if not categorized and ext:
                    files['other'].append(str(file_path))

        return files

    def _analyze_structure(self, path: Path, files: dict) -> dict:
        """Analyze the project structure and detect project type indicators.

        Examines the root directory for common project indicators like
        README, requirements.txt, package.json, pyproject.toml, and .git.

        Args:
            path: Root directory path to analyze.
            files: Pre-scanned files dict from _find_source_files.

        Returns:
            dict: Structure information containing:
                - total_files: Total count of all files
                - by_type: Counts by file category
                - has_readme, has_requirements, etc.: Boolean indicators
                - directories: List of top-level directory names
        """
        structure = {
            'total_files': sum(len(f) for f in files.values()),
            'by_type': {k: len(v) for k, v in files.items()},
            'has_readme': (path / 'README.md').exists() or (path / 'README').exists(),
            'has_requirements': (path / 'requirements.txt').exists(),
            'has_package_json': (path / 'package.json').exists(),
            'has_pyproject': (path / 'pyproject.toml').exists(),
            'has_git': (path / '.git').exists(),
            'directories': [],
        }

        # Get top-level directories
        for item in path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name not in SKIP_DIRS:
                structure['directories'].append(item.name)

        return structure

    def _read_key_files(self, path: Path, files: dict) -> dict:
        """Read contents of key files for LLM analysis.

        Reads priority files (README, requirements.txt, etc.) and a selection
        of main Python files to provide context for the LLM summary.

        Args:
            path: Root directory path.
            files: Pre-scanned files dict from _find_source_files.

        Returns:
            dict: Mapping of filename to file content (truncated if too large).

        Side Effects:
            - Reads multiple files from disk
        """
        key_contents = {}

        for filename in PRIORITY_FILES:
            file_path = path / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    # Limit content size
                    if len(content) > TRUNCATE_PRIORITY_FILE:
                        content = content[:TRUNCATE_PRIORITY_FILE] + "\n... (truncated)"
                    key_contents[filename] = content
                except Exception:
                    pass

        # Read a few Python files to understand the codebase
        python_files = files.get('python', [])
        if python_files:
            # Prioritize main entry points
            selected = []

            for p in ENTRY_POINT_FILES:
                for f in python_files:
                    if f.endswith(p) or f == p:
                        selected.append(f)
                        break

            # Add first few Python files if not enough
            for f in python_files[:5]:
                if f not in selected:
                    selected.append(f)
                if len(selected) >= 3:
                    break

            for filename in selected[:3]:
                file_path = path / filename
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        if len(content) > TRUNCATE_FILE_CONTENT:
                            content = content[:TRUNCATE_FILE_CONTENT] + "\n... (truncated)"
                        key_contents[filename] = content
                    except Exception:
                        pass

        return key_contents

    def _generate_codebase_summary(self, path: Path, structure: dict, contents: dict) -> str:
        """Use LLM to generate a comprehensive codebase summary.

        Builds a prompt from structure analysis and file contents, then
        delegates to the orchestrator's brain to generate a summary covering
        project type, purpose, technologies, architecture, and potential issues.

        Args:
            path: Root directory path.
            structure: Structure analysis from _analyze_structure.
            contents: Key file contents from _read_key_files.

        Returns:
            str: LLM-generated summary text, or error message if generation fails.

        Side Effects:
            - Makes LLM API call via orchestrator.delegate
        """
        # Build context
        context_parts = [
            f"Project directory: {path.name}",
            f"Total files: {structure['total_files']}",
            f"File types: {', '.join(f'{k}={v}' for k, v in structure['by_type'].items() if v > 0)}",
            f"Top-level directories: {', '.join(structure['directories'])}",
        ]

        if structure['has_readme']:
            context_parts.append("Has README: Yes")
        if structure['has_requirements']:
            context_parts.append("Python project (requirements.txt)")
        if structure['has_package_json']:
            context_parts.append("Node.js project (package.json)")
        if structure['has_pyproject']:
            context_parts.append("Modern Python project (pyproject.toml)")
        if structure['has_git']:
            context_parts.append("Git repository: Yes")

        context = "\n".join(context_parts)

        # Build file contents section
        file_contents = ""
        for filename, content in contents.items():
            file_contents += f"\n\n--- {filename} ---\n{content}"

        prompt = f"""Analyze this codebase and provide a comprehensive summary.

Project Structure:
{context}

Key File Contents:
{file_contents}

Provide a summary that includes:
1. **Project Type**: What kind of project is this? (library, CLI tool, web app, etc.)
2. **Main Purpose**: What does this project do?
3. **Key Technologies**: Languages, frameworks, libraries used
4. **Architecture**: How is the code organized?
5. **Entry Points**: Main files/functions
6. **Dependencies**: Key external dependencies
7. **Potential Issues**: Any obvious problems or areas for improvement

Be concise but thorough. Focus on actionable insights."""

        try:
            response = self.orchestrator.delegate(
                self.orchestrator.brain,
                prompt,
                system_prompt="You are a code analysis expert. Analyze codebases and provide clear, actionable summaries. Do not repeat yourself.",
                max_tokens=MAX_TOKENS_SUMMARY,
                temperature=TEMPERATURE_LOW
            )
            return response.content
        except Exception as e:
            return f"Error generating summary: {e}\n\nBasic structure:\n{context}"
