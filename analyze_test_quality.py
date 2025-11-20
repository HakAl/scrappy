#!/usr/bin/env python3
"""
Test Quality Analyzer

Automatically scans test files and identifies quality issues.
Helps prioritize which tests to improve.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


class TestQualityAnalyzer:
    """Analyzes test files for quality issues."""

    def __init__(self, test_dir: str = "tests"):
        self.test_dir = Path(test_dir)
        self.issues = defaultdict(lambda: defaultdict(list))

    def analyze_all(self) -> Dict[str, Dict[str, List]]:
        """Analyze all test files and return issues."""
        test_files = list(self.test_dir.rglob("test_*.py"))

        print(f"Analyzing {len(test_files)} test files...")

        for test_file in test_files:
            self.analyze_file(test_file)

        return dict(self.issues)

    def analyze_file(self, file_path: Path):
        """Analyze a single test file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return

        relative_path = str(file_path.relative_to(self.test_dir.parent))

        # Check for assignment-only tests
        assignment_tests = self._find_assignment_tests(lines)
        if assignment_tests:
            self.issues[relative_path]['assignment_only'] = assignment_tests

        # Check for type-only tests
        type_tests = self._find_type_only_tests(lines)
        if type_tests:
            self.issues[relative_path]['type_only'] = type_tests

        # Check for initialization tests
        init_tests = self._find_initialization_tests(lines)
        if init_tests:
            self.issues[relative_path]['initialization'] = init_tests

        # Check for empty tests
        empty_tests = self._find_empty_tests(lines)
        if empty_tests:
            self.issues[relative_path]['empty'] = empty_tests

    def _find_assignment_tests(self, lines: List[str]) -> List[Tuple[int, str]]:
        """Find tests that only check assignment."""
        issues = []
        pattern = re.compile(r'assert\s+\w+\._\w+\s+is\s+\w+')

        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                issues.append((i, line.strip()))

        return issues

    def _find_type_only_tests(self, lines: List[str]) -> List[Tuple[int, str]]:
        """Find tests that only check isinstance."""
        issues = []
        in_test = False
        test_name = ""
        test_start = 0
        assert_count = 0
        isinstance_count = 0

        for i, line in enumerate(lines, 1):
            # Detect test function start
            if line.strip().startswith('def test_'):
                in_test = True
                test_name = line.strip()
                test_start = i
                assert_count = 0
                isinstance_count = 0

            # Detect test function end (next def or class)
            elif in_test and (line.strip().startswith('def ') or line.strip().startswith('class ')):
                # Check if test ONLY has isinstance assertions
                if isinstance_count > 0 and isinstance_count == assert_count:
                    issues.append((test_start, test_name))
                in_test = False

            # Count assertions
            elif in_test:
                if 'assert' in line:
                    assert_count += 1
                    if 'isinstance(' in line:
                        isinstance_count += 1

        return issues

    def _find_initialization_tests(self, lines: List[str]) -> List[Tuple[int, str]]:
        """Find tests that only check initialization."""
        issues = []
        pattern = re.compile(r'def test_.*init')

        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                # Check if test only checks 'is not None'
                test_content = self._get_test_content(lines, i)
                if 'is not None' in test_content and test_content.count('assert') == 1:
                    issues.append((i, line.strip()))

        return issues

    def _find_empty_tests(self, lines: List[str]) -> List[Tuple[int, str]]:
        """Find tests with no assertions."""
        issues = []
        in_test = False
        test_name = ""
        test_start = 0
        has_assert = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith('def test_'):
                in_test = True
                test_name = line.strip()
                test_start = i
                has_assert = False

            elif in_test and (line.strip().startswith('def ') or line.strip().startswith('class ')):
                if not has_assert and 'pass' not in test_name:
                    issues.append((test_start, test_name))
                in_test = False

            elif in_test and 'assert' in line:
                has_assert = True

        return issues

    def _get_test_content(self, lines: List[str], start_line: int, max_lines: int = 20) -> str:
        """Get content of a test function."""
        content = []
        for i in range(start_line, min(start_line + max_lines, len(lines))):
            line = lines[i]
            if line.strip().startswith('def ') and i != start_line:
                break
            content.append(line)
        return '\n'.join(content)

    def print_report(self):
        """Print a formatted report of all issues."""
        if not self.issues:
            print("\nNo quality issues found!")
            return

        print("\n" + "="*80)
        print("TEST QUALITY REPORT")
        print("="*80)

        # Sort files by total issue count
        files_by_severity = sorted(
            self.issues.items(),
            key=lambda x: sum(len(v) for v in x[1].values()),
            reverse=True
        )

        total_issues = 0

        for file_path, categories in files_by_severity:
            issue_count = sum(len(v) for v in categories.values())
            total_issues += issue_count

            print(f"\n{file_path} ({issue_count} issues)")
            print("-" * 80)

            for category, items in categories.items():
                print(f"\n  {category.replace('_', ' ').title()}: {len(items)} found")
                for line_num, content in items[:5]:  # Show first 5
                    print(f"    Line {line_num}: {content[:70]}")
                if len(items) > 5:
                    print(f"    ... and {len(items) - 5} more")

        print("\n" + "="*80)
        print(f"SUMMARY: {total_issues} total issues in {len(self.issues)} files")
        print("="*80)

        # Priority list
        print("\nFILES TO FIX (Priority Order):")
        for i, (file_path, categories) in enumerate(files_by_severity[:10], 1):
            issue_count = sum(len(v) for v in categories.values())
            print(f"{i}. {file_path} - {issue_count} issues")


def main():
    """Run the analyzer."""
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "tests"

    analyzer = TestQualityAnalyzer(test_dir)
    analyzer.analyze_all()
    analyzer.print_report()

    # Return exit code based on issues found
    total_issues = sum(sum(len(v) for v in cats.values()) for cats in analyzer.issues.values())
    if total_issues > 0:
        print(f"\nRun this script with -v for detailed analysis")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
