#!/usr/bin/env python3
"""
Auto-fix orphaned code in test files.
Specifically handles:
1. Missing `})` closures for MagicMock(return_value={...
2. Orphaned dict literals that need to be wrapped
"""
import re
import sys


def fix_orphaned_code(content):
    """Fix common orphaned code patterns."""
    lines = content.split('\n')
    fixed = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Pattern: Line has only `}` after a dict, should be `})`
        if i > 0 and line.strip() == '}':
            # Check if previous non-empty line is a dict entry or has MagicMock(return_value={
            prev_idx = i - 1
            while prev_idx >= 0 and not lines[prev_idx].strip():
                prev_idx -= 1
            if prev_idx >= 0:
                # Look back for MagicMock(return_value={
                for j in range(max(0, prev_idx - 20), prev_idx + 1):
                    if 'MagicMock(return_value={' in lines[j]:
                        # Change `}` to `})`
                        fixed.append(line.replace('}', '})'))
                        i += 1
                        continue

        fixed.append(line)
        i += 1

    return '\n'.join(fixed)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python auto_fix_orphaned.py <file>")
        sys.exit(1)

    filepath = sys.argv[1]

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    fixed_content = fix_orphaned_code(content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fixed_content)

    print(f"Fixed: {filepath}")
