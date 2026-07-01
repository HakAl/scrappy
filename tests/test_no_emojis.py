"""Test to ensure no emoji characters exist in source code."""
import ast
import re
from pathlib import Path


def contains_emoji(text: str) -> bool:
    """Check if text contains emoji characters."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Misc Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols
        "\U0001FA00-\U0001FAFF"  # Extended-A
        "\U00002600-\U000026FF"  # Misc Symbols
        "\U00002700-\U000027BF"  # Dingbats
        "]"
    )
    return bool(emoji_pattern.search(text))


def extract_strings_from_file(filepath: Path) -> list[tuple[int, str]]:
    """Extract all string literals with line numbers from a Python file."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    strings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append((node.lineno, node.value))
    return strings


def test_no_emojis_in_source_code():
    """Ensure no emoji characters exist in source code string literals."""
    src_dir = Path(__file__).parent.parent / "src"

    violations = []

    for py_file in src_dir.rglob("*.py"):
        for lineno, string in extract_strings_from_file(py_file):
            if contains_emoji(string):
                rel_path = py_file.relative_to(src_dir.parent)
                violations.append(f"{rel_path}:{lineno}: {repr(string)}")

    assert not violations, (
        "Found emoji characters in source code:\n" + "\n".join(violations)
    )
