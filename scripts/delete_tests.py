#!/usr/bin/env python3

# Delete tests listed in the JSON report.
# Requires: pip install asttokens
# Usage: python .\scripts\delete_tests.py --report .\tests.json

import argparse
import json
import os
import ast
import asttokens


def fix_empty_classes(original_source, broken_source, deleted_test_names):
    """
    When deleting tests leaves a class empty, insert 'pass' to make it valid.
    """
    # Parse original to find classes and their methods
    try:
        original_tree = ast.parse(original_source)
    except SyntaxError:
        return broken_source

    class_info = {}  # {class_name: [(method_name, indent_level)]}

    for node in ast.walk(original_tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(item.name)
            class_info[node.name] = methods

    # Find classes where ALL methods were deleted
    lines = broken_source.split('\n')
    for class_name, methods in class_info.items():
        if all(m in deleted_test_names for m in methods):
            # Find the class definition line and insert 'pass' after it
            for i, line in enumerate(lines):
                if f'class {class_name}' in line and line.strip().startswith('class'):
                    # Find indentation of class
                    indent = len(line) - len(line.lstrip())
                    # Insert pass statement after class definition
                    if i + 1 < len(lines):
                        lines.insert(i + 1, ' ' * (indent + 4) + 'pass')
                    break

    return '\n'.join(lines)


def kill_tests_in_file(path, test_names, dry):
    """
    Deletes specified functions from a file.
    Returns True if file was modified.
    """
    # 1. Normalize Path (Handle Windows/Linux slashes)
    path = os.path.normpath(path)

    if not os.path.exists(path):
        print(f"MISSING: {path}")
        return False

    with open(path, encoding="utf-8") as f:
        source = f.read()

    atok = asttokens.ASTTokens(source, parse=True)
    kill_ranges = []

    # Track classes to check if we empty them out
    classes_touched = {}  # {class_node: [deleted_method_names]}

    # First pass: find all functions to delete
    for node in ast.walk(atok.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in test_names:
            # Get range including decorators
            start, end = atok.get_text_range(node)

            # WHITESPACE CLEANUP:
            # Consume preceding blank lines to avoid "Swiss Cheese" files
            while start > 0 and source[start - 1] in '\n\r':
                start -= 1
                # Also consume any whitespace-only lines
                line_start = source.rfind('\n', 0, start)
                if line_start >= 0:
                    line_content = source[line_start + 1:start + 1]
                    if line_content.strip() == '':
                        start = line_start
                    else:
                        start += 1  # Undo the last decrement
                        break
                else:
                    break

            kill_ranges.append((start, end))

    # Second pass: find orphan type annotations for deleted functions
    # e.g., `my_func: Callable[..., str]` before `def my_func(): ...`
    for node in ast.walk(atok.tree):
        if isinstance(node, ast.AnnAssign):
            # Check if this is an annotation for a function we're deleting
            if isinstance(node.target, ast.Name) and node.target.id in test_names:
                start, end = atok.get_text_range(node)
                # Consume preceding newline
                while start > 0 and source[start - 1] in '\n\r':
                    start -= 1
                kill_ranges.append((start, end))

    if not kill_ranges:
        return False

    # Sort reverse to keep offsets valid
    kill_ranges.sort(key=lambda x: x[0], reverse=True)

    new_source = source
    for s, e in kill_ranges:
        new_source = new_source[:s] + new_source[e:]

    # SAFETY CHECK 1: Syntax Validation
    try:
        ast.parse(new_source, filename=path)
    except SyntaxError:
        # SAFETY CHECK 2: The "Empty Class" Rescue
        # If deletion caused a syntax error, it's usually because a class became empty.
        # Find empty classes and insert 'pass' statements
        print(f"WARN: Deletion in {path} caused SyntaxError (likely empty class). Attempting fix...")
        new_source = fix_empty_classes(source, new_source, test_names)
        try:
            ast.parse(new_source, filename=path)
            print(f"     Fixed empty class(es) by inserting 'pass'")
        except SyntaxError:
            print(f"     Could not fix automatically. Skipping file.")
            return False

    if dry:
        print(f"[DRY-RUN] Would remove {len(kill_ranges)} tests from {path}")
        return False

    # Write Atomic
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new_source)

    # Windows atomic replace fix
    try:
        os.replace(tmp, path)
    except OSError:
        os.remove(path)
        os.rename(tmp, path)

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="JSON from audit script")
    parser.add_argument("--dry-run", action="store_true", help="Don't touch files")
    args = parser.parse_args()

    # --- FIX START: Robust Encoding Handling ---
    try:
        # First try standard UTF-8
        with open(args.report, encoding="utf-8") as f:
            data = json.load(f)
    except UnicodeDecodeError:
        # If that fails, it's likely a PowerShell UTF-16 file (0xff 0xfe)
        print(f"NOTICE: Detected PowerShell encoding (UTF-16) in {args.report}. parsing...")
        with open(args.report, encoding="utf-16") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON. File might be empty or mixed content.\n{e}")
        return
    # --- FIX END ---

    by_file = {}
    for row in data:
        by_file.setdefault(row["file"], set()).add(row["test"])

    changed_files = 0
    total_deleted = 0

    for path, tests in by_file.items():
        if kill_tests_in_file(path, tests, args.dry_run):
            changed_files += 1
            total_deleted += len(tests)
            print(f"MODIFIED: {path} (-{len(tests)} tests)")

    print(f"{'='*40}")
    print(f"Total: Removed {total_deleted} tests across {changed_files} files.")


if __name__ == "__main__":
    main()