#!/usr/bin/env python3
"""
Fix orphaned code from incomplete test deletions.
Removes lines that start with unexpected indentation.
"""
import ast
import sys


def fix_file(filepath):
    """Try to compile and report issues."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        return None  # No error
    except (SyntaxError, IndentationError) as e:
        return (e.lineno, str(e))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_orphaned_code.py <test_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    error = fix_file(filepath)

    if error:
        lineno, msg = error
        print(f"{filepath}:{lineno}: {msg}")
        sys.exit(1)
    else:
        print(f"{filepath}: OK")
