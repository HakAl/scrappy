#!/usr/bin/env python3
"""
Test helper consolidation analyzer.
Finds duplicate mocks, scattered fixtures, and patterns that should be centralized.

Usage:
    python scripts/consolidate_helpers.py tests/
    python scripts/consolidate_helpers.py tests/ --json > consolidation.json
"""

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


class HelperVisitor(ast.NodeVisitor):
    """AST visitor to find mocks, fixtures, and helper patterns."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.mocks: list[dict[str, Any]] = []
        self.fixtures: list[dict[str, Any]] = []
        self.patches: list[dict[str, Any]] = []
        self.factory_calls: list[dict[str, Any]] = []
        self.test_doubles: list[dict[str, Any]] = []
        self.current_function: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Find test double classes (Mock*, Fake*, Stub*)."""
        name = node.name
        if any(name.startswith(prefix) for prefix in ("Mock", "Fake", "Stub", "Dummy", "Spy")):
            self.test_doubles.append({
                "name": name,
                "file": self.filepath,
                "line": node.lineno,
                "type": "class",
            })
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Find fixtures and factory functions."""
        self.current_function = node.name

        # Check for pytest.fixture decorator
        for decorator in node.decorator_list:
            dec_name = self._get_decorator_name(decorator)
            if "fixture" in dec_name:
                self.fixtures.append({
                    "name": node.name,
                    "file": self.filepath,
                    "line": node.lineno,
                    "decorator": dec_name,
                })

        # Check for factory function patterns
        if node.name.startswith(("make_", "create_", "build_", "get_test_")):
            self.factory_calls.append({
                "name": node.name,
                "file": self.filepath,
                "line": node.lineno,
                "type": "factory",
            })

        self.generic_visit(node)
        self.current_function = None

    def visit_Call(self, node: ast.Call) -> None:
        """Find Mock(), MagicMock(), patch() calls."""
        func_name = self._get_call_name(node)

        if func_name in ("Mock", "MagicMock", "AsyncMock", "PropertyMock"):
            # Extract spec if provided
            spec = None
            for kw in node.keywords:
                if kw.arg == "spec":
                    spec = self._get_node_repr(kw.value)

            self.mocks.append({
                "type": func_name,
                "spec": spec,
                "file": self.filepath,
                "line": node.lineno,
                "in_function": self.current_function,
            })

        elif "patch" in func_name:
            # Extract patch target
            target = None
            if node.args:
                target = self._get_node_repr(node.args[0])

            self.patches.append({
                "target": target,
                "file": self.filepath,
                "line": node.lineno,
                "in_function": self.current_function,
            })

        self.generic_visit(node)

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Extract decorator name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return ""

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract function name from Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _get_node_repr(self, node: ast.expr) -> str:
        """Get string representation of AST node."""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_node_repr(node.value)}.{node.attr}"
        return "<complex>"


def scan_file(filepath: str) -> dict[str, Any]:
    """Scan a single Python file for helper patterns."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError):
        return {}

    visitor = HelperVisitor(filepath)
    visitor.visit(tree)

    return {
        "file": filepath,
        "mocks": visitor.mocks,
        "fixtures": visitor.fixtures,
        "patches": visitor.patches,
        "factories": visitor.factory_calls,
        "test_doubles": visitor.test_doubles,
    }


def find_duplicates(all_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Find duplicate patterns across files."""
    # Group mocks by spec
    mocks_by_spec: dict[str, list] = defaultdict(list)
    for data in all_data:
        for mock in data.get("mocks", []):
            if mock.get("spec"):
                mocks_by_spec[mock["spec"]].append(mock)

    # Group patches by target
    patches_by_target: dict[str, list] = defaultdict(list)
    for data in all_data:
        for patch in data.get("patches", []):
            if patch.get("target"):
                patches_by_target[patch["target"]].append(patch)

    # Find fixtures defined in non-conftest files
    scattered_fixtures = []
    for data in all_data:
        if "conftest" not in data["file"]:
            scattered_fixtures.extend(data.get("fixtures", []))

    # Find duplicate test double class names
    doubles_by_name: dict[str, list] = defaultdict(list)
    for data in all_data:
        for double in data.get("test_doubles", []):
            doubles_by_name[double["name"]].append(double)

    # Filter to actual duplicates (appearing in multiple files)
    duplicate_mocks = {k: v for k, v in mocks_by_spec.items() if len(set(m["file"] for m in v)) > 1}
    duplicate_patches = {k: v for k, v in patches_by_target.items() if len(set(p["file"] for p in v)) > 1}
    duplicate_doubles = {k: v for k, v in doubles_by_name.items() if len(set(d["file"] for d in v)) > 1}

    return {
        "duplicate_mocks": duplicate_mocks,
        "duplicate_patches": duplicate_patches,
        "duplicate_test_doubles": duplicate_doubles,
        "scattered_fixtures": scattered_fixtures,
    }


def find_consolidation_opportunities(duplicates: dict[str, Any]) -> list[dict[str, Any]]:
    """Identify specific consolidation opportunities."""
    opportunities = []

    # Duplicate mocks -> move to helpers.py
    for spec, mocks in duplicates.get("duplicate_mocks", {}).items():
        files = list(set(m["file"] for m in mocks))
        opportunities.append({
            "type": "duplicate_mock",
            "description": f"Mock(spec={spec}) used in {len(files)} files",
            "files": files,
            "recommendation": f"Create a factory function in tests/helpers.py: make_mock_{spec.lower().replace('.', '_')}()",
            "priority": "high" if len(files) > 2 else "medium",
        })

    # Duplicate patches -> consider a fixture
    for target, patches in duplicates.get("duplicate_patches", {}).items():
        files = list(set(p["file"] for p in patches))
        if len(files) > 2:
            opportunities.append({
                "type": "duplicate_patch",
                "description": f"patch({target}) used in {len(files)} files",
                "files": files,
                "recommendation": f"Create a fixture in conftest.py that patches {target}",
                "priority": "medium",
            })

    # Duplicate test doubles -> keep one, import it
    for name, doubles in duplicates.get("duplicate_test_doubles", {}).items():
        files = list(set(d["file"] for d in doubles))
        opportunities.append({
            "type": "duplicate_test_double",
            "description": f"Class {name} defined in {len(files)} files",
            "files": files,
            "recommendation": f"Keep {name} only in tests/helpers.py, import elsewhere",
            "priority": "high",
        })

    # Scattered fixtures -> move to conftest
    scattered = duplicates.get("scattered_fixtures", [])
    if scattered:
        by_file: dict[str, list] = defaultdict(list)
        for fix in scattered:
            by_file[fix["file"]].append(fix["name"])

        for file, fixtures in by_file.items():
            opportunities.append({
                "type": "scattered_fixture",
                "description": f"{len(fixtures)} fixtures in {file}",
                "fixtures": fixtures,
                "recommendation": "Move fixtures to tests/conftest.py for sharing",
                "priority": "low" if len(fixtures) == 1 else "medium",
            })

    return sorted(opportunities, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])


def generate_report(all_data: list[dict[str, Any]], output_json: bool = False) -> None:
    """Generate consolidation report."""
    duplicates = find_duplicates(all_data)
    opportunities = find_consolidation_opportunities(duplicates)

    if output_json:
        print(json.dumps({
            "duplicates": duplicates,
            "opportunities": opportunities,
            "file_details": all_data,
        }, indent=2, default=str))
        return

    print("\n" + "=" * 70)
    print("HELPER CONSOLIDATION REPORT")
    print("=" * 70)

    # Summary
    total_mocks = sum(len(d.get("mocks", [])) for d in all_data)
    total_patches = sum(len(d.get("patches", [])) for d in all_data)
    total_fixtures = sum(len(d.get("fixtures", [])) for d in all_data)
    total_doubles = sum(len(d.get("test_doubles", [])) for d in all_data)

    print(f"\nSCANNED:")
    print(f"  Files: {len(all_data)}")
    print(f"  Mock calls: {total_mocks}")
    print(f"  Patch calls: {total_patches}")
    print(f"  Fixtures: {total_fixtures}")
    print(f"  Test doubles: {total_doubles}")

    # Duplicates found
    dup_mocks = len(duplicates.get("duplicate_mocks", {}))
    dup_patches = len(duplicates.get("duplicate_patches", {}))
    dup_doubles = len(duplicates.get("duplicate_test_doubles", {}))
    scattered = len(duplicates.get("scattered_fixtures", []))

    print(f"\nISSUES FOUND:")
    print(f"  Duplicate mock specs: {dup_mocks}")
    print(f"  Duplicate patch targets: {dup_patches}")
    print(f"  Duplicate test double classes: {dup_doubles}")
    print(f"  Scattered fixtures: {scattered}")

    if not opportunities:
        print("\nNo consolidation opportunities found!")
        return

    # Opportunities
    print("\n" + "-" * 70)
    print("CONSOLIDATION OPPORTUNITIES")
    print("-" * 70)

    high_priority = [o for o in opportunities if o["priority"] == "high"]
    medium_priority = [o for o in opportunities if o["priority"] == "medium"]
    low_priority = [o for o in opportunities if o["priority"] == "low"]

    if high_priority:
        print("\nHIGH PRIORITY:")
        for opp in high_priority:
            print(f"\n  [{opp['type']}] {opp['description']}")
            if opp.get("files"):
                for f in opp["files"][:3]:
                    print(f"    - {f}")
                if len(opp.get("files", [])) > 3:
                    print(f"    ... and {len(opp['files']) - 3} more")
            print(f"  Recommendation: {opp['recommendation']}")

    if medium_priority:
        print("\nMEDIUM PRIORITY:")
        for opp in medium_priority[:5]:
            print(f"\n  [{opp['type']}] {opp['description']}")
            print(f"  Recommendation: {opp['recommendation']}")

    if low_priority and len(opportunities) < 10:
        print("\nLOW PRIORITY:")
        for opp in low_priority[:3]:
            print(f"  - {opp['description']}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Find helper consolidation opportunities in tests")
    parser.add_argument("target", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not Path(args.target).exists():
        print(f"Error: Directory not found: {args.target}")
        sys.exit(1)

    all_data = []
    files_scanned = 0

    for root, _, files in os.walk(args.target):
        for f in files:
            if f.endswith(".py"):
                files_scanned += 1
                path = os.path.join(root, f)
                data = scan_file(path)
                if data:
                    all_data.append(data)

    if not all_data:
        print("No Python files found to analyze")
        sys.exit(1)

    generate_report(all_data, output_json=args.json)


if __name__ == "__main__":
    main()
