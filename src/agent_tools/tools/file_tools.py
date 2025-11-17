"""
File operation tools for the code agent.

Provides read, write, list, and directory tree operations.
"""

from pathlib import Path
from typing import Any

try:
    import click
    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False

from .base import Tool, ToolParameter, ToolResult, ToolContext


class ReadFileTool(Tool):
    """Read contents of a file."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read contents of a file"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("path", str, "Path to file relative to project root", required=True)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        path = kwargs["path"]

        if not context.is_safe_path(path):
            return ToolResult(False, "", f"Path '{path}' is outside project directory")

        target = context.project_root / path
        if not target.exists():
            return ToolResult(False, "", f"File '{path}' does not exist")

        try:
            content = target.read_text(encoding='utf-8')
            lines = content.count('\n') + 1

            # Truncate if too long
            max_size = context.config.max_file_read_size if context.config else 50000
            if len(content) > max_size:
                content = content[:max_size] + "\n... [truncated]"

            # Store in working memory
            context.remember_file_read(path, content, lines)

            return ToolResult(True, content, metadata={"lines": lines, "path": path})
        except Exception as e:
            return ToolResult(False, "", f"Error reading file: {str(e)}")


class WriteFileTool(Tool):
    """Write content to a file."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("path", str, "Path to file relative to project root", required=True),
            ToolParameter("content", str, "Content to write to file", required=True)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        path = kwargs["path"]
        content = kwargs["content"]

        # Explicitly reject absolute paths (Unix/Mac style starting with /)
        # This prevents bypassing is_safe_path on Windows where / is treated as relative
        if path.startswith('/'):
            return ToolResult(False, "", f"Absolute path '{path}' not allowed. Use relative paths only.")

        if not context.is_safe_path(path):
            return ToolResult(False, "", f"Path '{path}' is outside project directory")

        # Validate content is not empty (common LLM failure)
        if not content or content.strip() == "":
            return ToolResult(
                False,
                "",
                f"Cannot write empty content to {path}. Content must not be empty."
            )

        # Warn if content is suspiciously short for certain file types
        suspicious_extensions = ['.py', '.js', '.ts', '.java', '.cpp', '.go', '.rs']
        if any(path.endswith(ext) for ext in suspicious_extensions):
            if len(content.strip()) < 10:
                return ToolResult(
                    False,
                    "",
                    f"Content too short ({len(content)} chars) for {path}. Expected meaningful code content."
                )

        # Special validation for requirements.txt
        if path.endswith('requirements.txt'):
            stdlib_modules = {
                'json', 'os', 'sys', 're', 'datetime', 'pathlib', 'typing',
                'subprocess', 'collections', 'itertools', 'functools', 'math',
                'random', 'time', 'logging', 'argparse', 'abc', 'io', 'enum',
                'dataclasses', 'contextlib', 'shutil', 'tempfile', 'unittest',
                'copy', 'pickle', 'hashlib', 'base64', 'urllib', 'http', 'socket',
                'threading', 'multiprocessing', 'asyncio', 'concurrent', 'queue'
            }
            found_stdlib = []
            for line in content.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (before ==, >=, etc.)
                    pkg_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                    if pkg_name.lower() in stdlib_modules:
                        found_stdlib.append(pkg_name)

            if found_stdlib:
                return ToolResult(
                    False,
                    "",
                    f"Error: requirements.txt contains standard library modules which should NOT be included: {', '.join(found_stdlib)}. "
                    f"Standard library modules are built into Python and don't need to be installed."
                )

        if context.dry_run:
            return ToolResult(
                True,
                f"[DRY RUN] Would write {len(content)} chars to {path}",
                metadata={"dry_run": True, "chars": len(content)}
            )

        target = context.project_root / path
        try:
            # Create parent directories if needed
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')

            # Verify the write succeeded
            if not target.exists():
                return ToolResult(False, "", f"File {path} was not created after write")

            # Verify content matches (read back and compare)
            # Note: Don't use byte size comparison because Windows converts \n to \r\n
            written_content = target.read_text(encoding='utf-8')
            if written_content != content:
                # Check if it's just a newline difference (Windows \r\n vs Unix \n)
                normalized_written = written_content.replace('\r\n', '\n')
                normalized_content = content.replace('\r\n', '\n')
                if normalized_written != normalized_content:
                    return ToolResult(
                        False,
                        "",
                        f"Write verification failed: content mismatch after writing to {path}"
                    )

            return ToolResult(
                True,
                f"Successfully wrote {len(content)} characters to {path}",
                metadata={"chars": len(content), "path": path, "verified": True}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error writing file: {str(e)}")


class ListFilesTool(Tool):
    """List files matching a pattern."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "List files matching pattern recursively"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("directory", str, "Directory to search", required=False, default="."),
            ToolParameter("pattern", str, "Glob pattern to match", required=False, default="*")
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        directory = kwargs.get("directory", ".")
        pattern = kwargs.get("pattern", "*")

        if not context.is_safe_path(directory):
            return ToolResult(False, "", f"Path '{directory}' is outside project directory")

        target = context.project_root / directory
        if not target.exists():
            return ToolResult(False, "", f"Directory '{directory}' does not exist")

        try:
            files = list(target.glob(pattern))
            max_files = context.config.max_file_listing if context.config else 100
            truncated = len(files) > max_files
            if truncated:
                files = files[:max_files]

            result = []
            for f in sorted(files):
                rel_path = f.relative_to(context.project_root)
                if f.is_dir():
                    result.append(f"{rel_path}/")
                else:
                    result.append(str(rel_path))

            output = "\n".join(result)
            if truncated:
                output += f"\n... [truncated to {max_files} items]"

            return ToolResult(
                True,
                output,
                metadata={"count": len(result), "truncated": truncated}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error listing files: {str(e)}")


class ListDirectoryTool(Tool):
    """Show directory tree structure."""

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "Show directory tree structure with files and subdirs"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("path", str, "Directory path", required=False, default="."),
            ToolParameter("depth", int, "Maximum depth to traverse", required=False, default=2)
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        path = kwargs.get("path", ".")
        depth = kwargs.get("depth", 2)

        if not context.is_safe_path(path):
            return ToolResult(False, "", f"Path '{path}' is outside project directory")

        target = context.project_root / path
        if not target.exists():
            return ToolResult(False, "", f"Path '{path}' does not exist")
        if not target.is_dir():
            return ToolResult(False, "", f"'{path}' is not a directory")

        try:
            lines = []
            skip_dirs = context.config.skip_directories if context.config else ['node_modules', '__pycache__', '.git', 'venv', '.venv']
            allowed_hidden = context.config.allowed_hidden_files if context.config else ['.gitignore', '.env.example']

            def build_tree(dir_path: Path, prefix: str = "", current_depth: int = 0):
                if current_depth > depth:
                    return

                try:
                    items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                except PermissionError:
                    lines.append(f"{prefix}[Permission Denied]")
                    return

                # Filter out hidden and skip directories
                items = [i for i in items if not i.name.startswith('.') or i.name in allowed_hidden]
                items = [i for i in items if i.name not in skip_dirs]

                for i, item in enumerate(items):
                    is_last = i == len(items) - 1
                    connector = "`-- " if is_last else "|-- "

                    if item.is_dir():
                        # Directory - show in cyan
                        if HAS_CLICK:
                            dir_name = click.style(f"{item.name}/", fg='cyan', bold=True)
                        else:
                            dir_name = f"{item.name}/"
                        lines.append(f"{prefix}{connector}{dir_name}")

                        # Recurse into subdirectory
                        if current_depth < depth:
                            extension = "    " if is_last else "|   "
                            build_tree(item, prefix + extension, current_depth + 1)
                    else:
                        # File - show with size
                        try:
                            size = item.stat().st_size
                            if size < 1024:
                                size_str = f"{size}B"
                            elif size < 1024 * 1024:
                                size_str = f"{size/1024:.1f}KB"
                            else:
                                size_str = f"{size/(1024*1024):.1f}MB"
                        except:
                            size_str = "?"

                        # Color by file type
                        if HAS_CLICK:
                            if item.suffix in ['.py']:
                                file_name = click.style(item.name, fg='green')
                            elif item.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                                file_name = click.style(item.name, fg='yellow')
                            elif item.suffix in ['.md', '.txt', '.rst']:
                                file_name = click.style(item.name, fg='white')
                            elif item.suffix in ['.json', '.yaml', '.yml', '.toml']:
                                file_name = click.style(item.name, fg='magenta')
                            else:
                                file_name = item.name
                            size_display = click.style(f"({size_str})", fg='bright_black')
                        else:
                            file_name = item.name
                            size_display = f"({size_str})"

                        lines.append(f"{prefix}{connector}{file_name} {size_display}")

            # Start with the directory name
            if HAS_CLICK:
                root_name = click.style(str(target.relative_to(context.project_root)), fg='cyan', bold=True)
            else:
                root_name = str(target.relative_to(context.project_root))
            lines.append(f"{root_name}/")

            build_tree(target)

            max_lines = context.config.max_directory_tree_lines if context.config else 200
            truncated = len(lines) > max_lines
            if truncated:
                lines = lines[:max_lines]
                lines.append(f"... [truncated to {max_lines} items]")

            return ToolResult(
                True,
                "\n".join(lines),
                metadata={"line_count": len(lines), "truncated": truncated}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error listing directory: {str(e)}")
