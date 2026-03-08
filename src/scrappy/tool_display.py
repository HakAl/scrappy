"""Shared formatting helpers for tool display and confirmation UX."""

from typing import Any, Mapping, Optional

FILE_PATH_ARG_NAMES = ("file_path", "path", "filepath", "file")

DEFAULT_TOOL_KEY_PARAM_MAP: dict[str, str] = {
    "write_file": "path",
    "read_file": "path",
    "read_files": "paths",
    "edit_file": "path",
    "create_file": "path",
    "patch_file": "path",
    "delete_file": "path",
    "run_command": "command",
    "list_files": "path",
    "list_directory": "path",
    "find_exact_text": "pattern",
    "codebase_search": "query",
    "search_files": "pattern",
    "complete": "result",
}


def truncate_tool_value(value: str, max_length: int = 50) -> str:
    """Truncate display values to a predictable width."""
    if max_length > 3 and len(value) > max_length:
        return value[: max_length - 3] + "..."
    return value


def extract_file_path(args: dict[str, Any]) -> Optional[str]:
    """Extract a file path from common tool argument names."""
    for key in FILE_PATH_ARG_NAMES:
        value = args.get(key)
        if value:
            return str(value)
    return None


def extract_write_files_paths(args: dict[str, Any]) -> tuple[list[str], int]:
    """Extract valid paths from a write_files argument payload."""
    files = args.get("files", [])
    if not isinstance(files, list):
        return [], 0

    paths = [
        str(file_spec.get("path"))
        for file_spec in files
        if isinstance(file_spec, dict) and file_spec.get("path")
    ]
    return paths, len(files)


def summarize_write_files(
    args: dict[str, Any],
    *,
    max_length: Optional[int] = 50,
) -> str:
    """Summarize a write_files batch using the first path and remaining count."""
    paths, total_files = extract_write_files_paths(args)
    if total_files == 0:
        return ""
    if not paths:
        value = f"{total_files} file(s)"
    elif len(paths) == 1:
        value = paths[0]
    else:
        value = f"{paths[0]} (+{len(paths) - 1} more)"

    if max_length is None:
        return value
    return truncate_tool_value(value, max_length=max_length)


def extract_tool_key_param(
    tool_name: str,
    args: dict[str, Any],
    *,
    max_length: int = 50,
    key_param_map: Mapping[str, str] | None = None,
) -> str:
    """Extract the most useful display value for a tool call."""
    if tool_name == "write_files":
        return summarize_write_files(args, max_length=max_length)

    param_name = (key_param_map or DEFAULT_TOOL_KEY_PARAM_MAP).get(tool_name)
    if not param_name or param_name not in args:
        return ""

    value = str(args[param_name])
    return truncate_tool_value(value, max_length=max_length)


def format_confirmation_prompt(tool_name: str, args: dict[str, Any]) -> str:
    """Create a human-readable confirmation prompt for destructive tools."""
    if tool_name in {"write_file", "edit_file", "create_file", "patch_file"}:
        path = extract_file_path(args) or "<unknown>"
        return f"Write to {path}"
    if tool_name == "write_files":
        paths, total_files = extract_write_files_paths(args)
        if total_files == 0:
            return "Write multiple files"
        if not paths:
            return f"Write {total_files} files"
        if len(paths) == 1:
            return f"Write to {paths[0]}"
        return f"Write {len(paths)} files ({paths[0]} +{len(paths) - 1} more)"
    if tool_name == "delete_file":
        path = extract_file_path(args) or "<unknown>"
        return f"Delete {path}"
    if tool_name == "run_command":
        command = truncate_tool_value(str(args.get("command", "<unknown>")), max_length=60)
        return f"Run: {command}"
    return f"Execute {tool_name}"
