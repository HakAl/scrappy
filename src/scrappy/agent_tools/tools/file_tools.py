"""
File operation tools for the code agent.

Provides read, write, list, and directory tree operations.
"""

from pathlib import Path

from scrappy.infrastructure.theme import DEFAULT_THEME, SYNTAX_COLORS

from .base import ToolBase, ToolParameter, ToolResult, ToolContext


class ReadFileTool(ToolBase):
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
            max_size = context.config.max_file_read_size
            if len(content) > max_size:
                content = content[:max_size] + "\n... [truncated]"

            # Store in working memory
            context.remember_file_read(path, content, lines)

            # Record in HUD working set (whole file read, no line range)
            if context.working_set:
                context.working_set.record_read(path, context.turn)

            return ToolResult(True, content, metadata={"lines": lines, "path": path})
        except Exception as e:
            return ToolResult(False, "", f"Error reading file: {str(e)}")


class ReadFilesTool(ToolBase):
    """Read contents of multiple files in a single operation."""

    @property
    def name(self) -> str:
        return "read_files"

    @property
    def description(self) -> str:
        return "Read contents of multiple files at once. More efficient than multiple read_file calls."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "paths",
                list,
                "List of file paths relative to project root",
                required=True
            )
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        paths = kwargs.get("paths", [])

        if not paths:
            return ToolResult(False, "", "No paths provided")

        if not isinstance(paths, list):
            return ToolResult(False, "", "paths must be a list of file paths")

        results = []
        total_size = 0
        max_total_size = context.config.max_file_read_size * 3  # Allow 3x single file limit for batch
        files_read = 0
        files_failed = 0
        truncated = False

        for path in paths:
            # Check if we've hit size limit
            if total_size >= max_total_size:
                truncated = True
                results.append(f"\n{'='*60}\n[TRUNCATED] Remaining files skipped due to size limit\n{'='*60}")
                break

            # Validate path
            if not isinstance(path, str):
                results.append(f"\n{'='*60}\nFILE: {path}\n{'='*60}\n[ERROR] Invalid path type")
                files_failed += 1
                continue

            if not context.is_safe_path(path):
                results.append(f"\n{'='*60}\nFILE: {path}\n{'='*60}\n[ERROR] Path is outside project directory")
                files_failed += 1
                continue

            target = context.project_root / path
            if not target.exists():
                results.append(f"\n{'='*60}\nFILE: {path}\n{'='*60}\n[ERROR] File does not exist")
                files_failed += 1
                continue

            try:
                content = target.read_text(encoding='utf-8')
                lines = content.count('\n') + 1

                # Check remaining budget
                remaining_budget = max_total_size - total_size
                if len(content) > remaining_budget:
                    content = content[:remaining_budget] + "\n... [truncated]"
                    truncated = True

                total_size += len(content)

                # Store in working memory
                context.remember_file_read(path, content, lines)

                # Record in HUD working set
                if context.working_set:
                    context.working_set.record_read(path, context.turn)

                results.append(f"\n{'='*60}\nFILE: {path} ({lines} lines)\n{'='*60}\n{content}")
                files_read += 1

            except Exception as e:
                results.append(f"\n{'='*60}\nFILE: {path}\n{'='*60}\n[ERROR] {str(e)}")
                files_failed += 1

        if not results:
            return ToolResult(False, "", "No files could be read")

        output = "".join(results)
        summary = f"Read {files_read} file(s)"
        if files_failed > 0:
            summary += f", {files_failed} failed"
        if truncated:
            summary += " (output truncated)"

        return ToolResult(
            True,
            output,
            metadata={
                "files_read": files_read,
                "files_failed": files_failed,
                "total_size": total_size,
                "truncated": truncated
            }
        )


class WriteFilesTool(ToolBase):
    """Write content to multiple files in a single operation."""

    # Maximum files per batch to prevent abuse
    MAX_FILES_PER_BATCH = 20

    # Extensions that require content validation
    SUSPICIOUS_EXTENSIONS = [
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.go', '.rs',
        '.html', '.css', '.scss', '.vue', '.svelte', '.rb', '.php', '.swift',
        '.kt', '.scala', '.c', '.h', '.hpp', '.cs', '.sh', '.bash', '.zsh'
    ]

    @property
    def name(self) -> str:
        return "write_files"

    @property
    def description(self) -> str:
        return "Write content to multiple files at once. More efficient than multiple write_file calls."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                "files",
                list,
                "List of {path, content} objects to write",
                required=True
            )
        ]

    def _is_absolute_path_any_platform(self, path: str) -> bool:
        """Check if path looks like an absolute path on ANY platform."""
        if path.startswith('/'):
            return True
        if len(path) >= 2 and path[1] == ':' and path[0].isalpha():
            return True
        if path.startswith('\\\\'):
            return True
        return False

    def _validate_file_spec(self, file_spec: dict, context: 'ToolContext') -> tuple[bool, str]:
        """
        Validate a single file specification.

        Returns:
            (is_valid, error_message) - error_message is empty if valid
        """
        if not isinstance(file_spec, dict):
            return False, "File spec must be a dict with 'path' and 'content'"

        path = file_spec.get('path')
        content = file_spec.get('content')

        if not path:
            return False, "Missing 'path' in file spec"
        if not isinstance(path, str):
            return False, f"Path must be a string, got {type(path).__name__}"
        if content is None:
            return False, f"Missing 'content' for {path}"
        if not isinstance(content, str):
            return False, f"Content must be a string for {path}"

        # Security: reject absolute paths
        if self._is_absolute_path_any_platform(path):
            return False, f"Absolute path '{path}' not allowed"

        # Security: check path is within project
        if not context.is_safe_path(path):
            return False, f"Path '{path}' is outside project directory"

        # Validate content is not empty
        if not content or content.strip() == "":
            return False, f"Empty content not allowed for {path}"

        # Validate code files have meaningful content
        if any(path.endswith(ext) for ext in self.SUSPICIOUS_EXTENSIONS):
            if len(content.strip()) < 10:
                return False, f"Content too short ({len(content)} chars) for {path}"

        return True, ""

    def execute(self, context: 'ToolContext', **kwargs) -> ToolResult:
        files = kwargs.get("files", [])

        if not files:
            return ToolResult(False, "", "No files provided")

        if not isinstance(files, list):
            return ToolResult(False, "", "files must be a list of {path, content} objects")

        if len(files) > self.MAX_FILES_PER_BATCH:
            return ToolResult(
                False, "",
                f"Too many files ({len(files)}). Maximum is {self.MAX_FILES_PER_BATCH} per batch."
            )

        # Phase 1: Validate all files first (fail-fast)
        validation_errors = []
        for i, file_spec in enumerate(files):
            is_valid, error = self._validate_file_spec(file_spec, context)
            if not is_valid:
                validation_errors.append(f"File {i+1}: {error}")

        if validation_errors:
            return ToolResult(
                False, "",
                "Validation failed:\n" + "\n".join(validation_errors)
            )

        # Phase 2: Dry run check
        if context.dry_run:
            paths = [f['path'] for f in files]
            total_chars = sum(len(f['content']) for f in files)
            return ToolResult(
                True,
                f"[DRY RUN] Would write {len(files)} files ({total_chars} chars total):\n" +
                "\n".join(f"  - {p}" for p in paths),
                metadata={"dry_run": True, "file_count": len(files)}
            )

        # Phase 3: Write all files
        results = []
        files_written = 0
        files_failed = 0
        total_chars = 0

        for file_spec in files:
            path = file_spec['path']
            content = file_spec['content']
            target = context.project_root / path

            try:
                # Create parent directories if needed
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')

                # Verify write succeeded
                if not target.exists():
                    results.append(f"[FAIL] {path}: File was not created")
                    files_failed += 1
                    continue

                # Verify content matches
                written = target.read_text(encoding='utf-8')
                normalized_written = written.replace('\r\n', '\n')
                normalized_content = content.replace('\r\n', '\n')

                if normalized_written != normalized_content:
                    results.append(f"[FAIL] {path}: Content verification failed")
                    files_failed += 1
                    continue

                # Record in HUD working set
                if context.working_set:
                    context.working_set.record_write(path, context.turn)

                results.append(f"[OK] {path} ({len(content)} chars)")
                files_written += 1
                total_chars += len(content)

            except Exception as e:
                results.append(f"[FAIL] {path}: {str(e)}")
                files_failed += 1

        # Build summary
        if files_failed == 0:
            summary = f"Successfully wrote {files_written} file(s) ({total_chars} chars total)"
        else:
            summary = f"Wrote {files_written} file(s), {files_failed} failed"

        output = summary + "\n\n" + "\n".join(results)

        return ToolResult(
            success=(files_failed == 0),
            output=output,
            error="" if files_failed == 0 else f"{files_failed} file(s) failed to write",
            metadata={
                "files_written": files_written,
                "files_failed": files_failed,
                "total_chars": total_chars
            }
        )


class WriteFileTool(ToolBase):
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

    def _is_absolute_path_any_platform(self, path: str) -> bool:
        """Check if path looks like an absolute path on ANY platform.

        Security measure: Reject paths that are absolute in either Unix or Windows
        format, regardless of the current platform. This prevents:
        - Unix absolute paths like /etc/passwd
        - Windows drive paths like C:\\Windows or D:/Users
        - Windows UNC paths like \\\\server\\share
        """
        # Unix/Mac absolute path
        if path.startswith('/'):
            return True

        # Windows drive letter (C:, D:, etc.) - check for letter followed by colon
        if len(path) >= 2 and path[1] == ':' and path[0].isalpha():
            return True

        # Windows UNC path (\\server\share)
        if path.startswith('\\\\'):
            return True

        return False

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        path = kwargs["path"]
        content = kwargs["content"]

        # Explicitly reject absolute paths in ANY format (Unix OR Windows)
        # This is critical security validation - must reject paths that look
        # absolute on ANY platform, not just the current one
        if self._is_absolute_path_any_platform(path):
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
        suspicious_extensions = [
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.go', '.rs',
            '.html', '.css', '.scss', '.vue', '.svelte', '.rb', '.php', '.swift',
            '.kt', '.scala', '.c', '.h', '.hpp', '.cs', '.sh', '.bash', '.zsh'
        ]
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

        # Check if file exists and content is identical (loop prevention)
        if target.exists():
            try:
                existing_content = target.read_text(encoding='utf-8')
                existing_len = len(existing_content)
                new_len = len(content)

                # Normalize line endings for comparison
                normalized_existing = existing_content.replace('\r\n', '\n')
                normalized_new = content.replace('\r\n', '\n')

                if normalized_existing == normalized_new:
                    return ToolResult(
                        True,
                        "Warning: File content unchanged. No modifications needed.",
                        metadata={"chars": len(content), "path": path, "unchanged": True}
                    )

                # Detect significant shrinkage (potential corruption loop)
                # If new content is less than 50% of existing and existing was substantial,
                # this is likely a truncation error, not an intentional reduction
                if existing_len > 100 and new_len < existing_len * 0.5:
                    return ToolResult(
                        False,
                        "",
                        f"Content shrinkage detected: new content ({new_len} chars) is less than "
                        f"50% of existing ({existing_len} chars). This may indicate truncation. "
                        f"If intentional, delete the file first then write new content."
                    )
            except Exception:
                # If we can't read the existing file, proceed with write
                pass

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

            # Record in HUD working set
            if context.working_set:
                context.working_set.record_write(path, context.turn)

            return ToolResult(
                True,
                f"Successfully wrote {len(content)} characters to {path}",
                metadata={"chars": len(content), "path": path, "verified": True}
            )
        except Exception as e:
            return ToolResult(False, "", f"Error writing file: {str(e)}")


class ListFilesTool(ToolBase):
    """List files matching a pattern, with optional tree view."""

    def __init__(self, output_interface=None):
        """Initialize tool with optional output interface for styling.

        Args:
            output_interface: Output interface for styling tree view. If None, no styling.
        """
        self._output = output_interface

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files in a directory. Use pattern for glob matching, "
            "depth to control recursion, tree=true for visual tree structure."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("directory", str, "Directory to search", required=False, default="."),
            ToolParameter("pattern", str, "Glob pattern to match", required=False, default="*"),
            ToolParameter("depth", int, "Max directory depth (1=current only)", required=False, default=1),
            ToolParameter("tree", bool, "Show as visual tree structure", required=False, default=False),
        ]

    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        directory = kwargs.get("directory", ".")
        pattern = kwargs.get("pattern", "*")
        depth = kwargs.get("depth", 1)
        tree = kwargs.get("tree", False)

        if not context.is_safe_path(directory):
            return ToolResult(False, "", f"Path '{directory}' is outside project directory")

        target = context.project_root / directory
        if not target.exists():
            return ToolResult(False, "", f"Directory '{directory}' does not exist")
        if not target.is_dir():
            return ToolResult(False, "", f"'{directory}' is not a directory")

        try:
            if tree:
                return self._execute_tree(context, target, depth)
            else:
                return self._execute_flat(context, target, pattern, depth)
        except Exception as e:
            return ToolResult(False, "", f"Error listing files: {str(e)}")

    def _execute_flat(self, context: ToolContext, target: Path, pattern: str, depth: int) -> ToolResult:
        """Execute flat file listing with glob pattern."""
        # Build glob pattern with depth
        if depth == 1:
            glob_pattern = pattern
        else:
            # For depth > 1, use recursive glob
            glob_pattern = f"**/{pattern}" if depth > 1 else pattern

        files = list(target.glob(glob_pattern))

        # Filter by depth if using recursive glob
        if depth > 1:
            filtered = []
            for f in files:
                try:
                    rel = f.relative_to(target)
                    # Count path parts to determine depth
                    if len(rel.parts) <= depth:
                        filtered.append(f)
                except ValueError:
                    continue
            files = filtered

        max_files = context.config.max_file_listing
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

    def _execute_tree(self, context: ToolContext, target: Path, depth: int) -> ToolResult:
        """Execute tree-style directory listing."""
        lines = []
        skip_dirs = context.config.skip_directories
        allowed_hidden = context.config.allowed_hidden_files

        def build_tree(dir_path: Path, prefix: str = "", current_depth: int = 0):
            if current_depth >= depth:
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
                    # Directory - show with styling if available
                    if self._output:
                        dir_name = self._output.style(f"{item.name}/", color=DEFAULT_THEME.primary, bold=True)
                    else:
                        dir_name = f"{item.name}/"
                    lines.append(f"{prefix}{connector}{dir_name}")

                    # Recurse into subdirectory
                    if current_depth < depth - 1:
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
                    except OSError:
                        size_str = "?"

                    # Color by file type
                    if self._output:
                        if item.suffix in ['.py']:
                            file_name = self._output.style(item.name, color=SYNTAX_COLORS.python)
                        elif item.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                            file_name = self._output.style(item.name, color=SYNTAX_COLORS.javascript)
                        elif item.suffix in ['.md', '.txt', '.rst']:
                            file_name = self._output.style(item.name, color=SYNTAX_COLORS.docs)
                        elif item.suffix in ['.json', '.yaml', '.yml', '.toml']:
                            file_name = self._output.style(item.name, color=SYNTAX_COLORS.config)
                        else:
                            file_name = item.name
                        size_display = self._output.style(f"({size_str})", color=DEFAULT_THEME.text_muted)
                    else:
                        file_name = item.name
                        size_display = f"({size_str})"

                    lines.append(f"{prefix}{connector}{file_name} {size_display}")

        # Start with the directory name
        try:
            root_name = str(target.relative_to(context.project_root))
            if root_name == ".":
                root_name = target.name or "."
        except ValueError:
            root_name = target.name

        if self._output:
            styled_root = self._output.style(root_name, color=DEFAULT_THEME.primary, bold=True)
            lines.append(f"{styled_root}/")
        else:
            lines.append(f"{root_name}/")

        build_tree(target)

        max_lines = context.config.max_directory_tree_lines
        truncated = len(lines) > max_lines
        if truncated:
            lines = lines[:max_lines]
            lines.append(f"... [truncated to {max_lines} items]")

        return ToolResult(
            True,
            "\n".join(lines),
            metadata={"line_count": len(lines), "truncated": truncated, "tree": True}
        )


class ListDirectoryTool(ToolBase):
    """Show directory tree structure."""

    def __init__(self, output_interface=None):
        """Initialize tool with output interface.

        Args:
            output_interface: Output interface for styling. If None, no styling applied.
        """
        self._output = output_interface

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
            skip_dirs = context.config.skip_directories
            allowed_hidden = context.config.allowed_hidden_files

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
                        # Directory - show in primary color with bold
                        if self._output:
                            dir_name = self._output.style(f"{item.name}/", color=DEFAULT_THEME.primary, bold=True)
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
                        except OSError:
                            size_str = "?"

                        # Color by file type using SYNTAX_COLORS
                        if self._output:
                            if item.suffix in ['.py']:
                                file_name = self._output.style(item.name, color=SYNTAX_COLORS.python)
                            elif item.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                                file_name = self._output.style(item.name, color=SYNTAX_COLORS.javascript)
                            elif item.suffix in ['.md', '.txt', '.rst']:
                                file_name = self._output.style(item.name, color=SYNTAX_COLORS.docs)
                            elif item.suffix in ['.json', '.yaml', '.yml', '.toml']:
                                file_name = self._output.style(item.name, color=SYNTAX_COLORS.config)
                            else:
                                file_name = item.name
                            size_display = self._output.style(f"({size_str})", color=DEFAULT_THEME.text_muted)
                        else:
                            file_name = item.name
                            size_display = f"({size_str})"

                        lines.append(f"{prefix}{connector}{file_name} {size_display}")

            # Start with the directory name
            if self._output:
                root_name = self._output.style(str(target.relative_to(context.project_root)), color=DEFAULT_THEME.primary, bold=True)
                lines.append(f"{root_name}/")
            else:
                root_name = str(target.relative_to(context.project_root))
                lines.append(f"{root_name}/")

            build_tree(target)

            max_lines = context.config.max_directory_tree_lines
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
