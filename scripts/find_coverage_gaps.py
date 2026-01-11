#!/usr/bin/env python3
"""
Coverage gap finder.
Analyzes pytest coverage JSON to identify untested code and prioritize gaps.

Usage:
    python -m pytest tests/ --cov=src --cov-report=json -q
    python scripts/find_coverage_gaps.py coverage.json
    python scripts/find_coverage_gaps.py coverage.json --json > gaps.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_coverage_json(path: str) -> dict[str, Any]:
    """Parse coverage.json file."""
    with open(path) as f:
        return json.load(f)


def analyze_file(filepath: str, file_data: dict[str, Any]) -> dict[str, Any]:
    """Analyze coverage data for a single file."""
    summary = file_data.get("summary", {})
    missing_lines = file_data.get("missing_lines", [])
    excluded_lines = file_data.get("excluded_lines", [])

    # Calculate coverage percentage
    covered = summary.get("covered_lines", 0)
    total = summary.get("num_statements", 0)
    coverage_pct = (covered / total * 100) if total > 0 else 0

    # Find missing line ranges (contiguous blocks are likely functions)
    missing_ranges = []
    if missing_lines:
        start = missing_lines[0]
        end = start
        for line in missing_lines[1:]:
            if line == end + 1:
                end = line
            else:
                missing_ranges.append((start, end))
                start = line
                end = line
        missing_ranges.append((start, end))

    return {
        "file": filepath,
        "coverage_pct": round(coverage_pct, 1),
        "covered_lines": covered,
        "total_lines": total,
        "missing_lines": missing_lines,
        "missing_ranges": missing_ranges,
        "excluded_lines": excluded_lines,
    }


def prioritize_gaps(analysis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Prioritize coverage gaps by importance.

    Priority factors:
    1. Core modules (orchestrator, graph, agent) over utils
    2. Lower coverage = higher priority
    3. More missing lines = higher priority
    """
    priority_patterns = [
        ("orchestrator", 10),
        ("graph", 9),
        ("agent", 8),
        ("core", 8),
        ("cli", 7),
        ("tools", 6),
        ("infrastructure", 5),
        ("utils", 3),
        ("helpers", 2),
    ]

    for item in analysis:
        filepath = item["file"].lower()

        # Base priority from module type
        base_priority = 4
        for pattern, priority in priority_patterns:
            if pattern in filepath:
                base_priority = priority
                break

        # Boost priority for low coverage
        coverage = item["coverage_pct"]
        if coverage == 0:
            coverage_boost = 5
        elif coverage < 25:
            coverage_boost = 4
        elif coverage < 50:
            coverage_boost = 3
        elif coverage < 75:
            coverage_boost = 2
        else:
            coverage_boost = 0

        # Boost for many missing lines
        missing = len(item["missing_lines"])
        if missing > 50:
            size_boost = 3
        elif missing > 20:
            size_boost = 2
        elif missing > 10:
            size_boost = 1
        else:
            size_boost = 0

        item["priority_score"] = base_priority + coverage_boost + size_boost
        item["priority_reason"] = []

        if coverage == 0:
            item["priority_reason"].append("zero coverage")
        elif coverage < 50:
            item["priority_reason"].append(f"low coverage ({coverage}%)")

        if missing > 20:
            item["priority_reason"].append(f"{missing} missing lines")

        for pattern, _ in priority_patterns[:4]:
            if pattern in filepath:
                item["priority_reason"].append(f"core module ({pattern})")
                break

    # Sort by priority score descending
    return sorted(analysis, key=lambda x: x["priority_score"], reverse=True)


def find_untested_functions(filepath: str, missing_ranges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """
    Try to identify function names for missing line ranges.

    Reads the source file and looks for function definitions
    that fall within missing ranges.
    """
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except (FileNotFoundError, PermissionError):
        return []

    functions = []
    for start, end in missing_ranges:
        # Look for function definitions in the range
        for i in range(max(0, start - 1), min(len(lines), end)):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                # Extract function name
                if "def " in stripped:
                    name = stripped.split("def ")[1].split("(")[0]
                    functions.append({
                        "name": name,
                        "line": i + 1,
                        "range": (start, end),
                    })

    return functions


def generate_report(analysis: list[dict[str, Any]], output_json: bool = False) -> None:
    """Generate coverage gap report."""
    prioritized = prioritize_gaps(analysis)

    if output_json:
        print(json.dumps(prioritized, indent=2))
        return

    # Filter to only show files with gaps
    with_gaps = [a for a in prioritized if a["coverage_pct"] < 100]

    if not with_gaps:
        print("No coverage gaps found!")
        return

    print("\n" + "=" * 70)
    print("COVERAGE GAP REPORT")
    print("=" * 70)

    # Summary stats
    zero_coverage = [a for a in with_gaps if a["coverage_pct"] == 0]
    low_coverage = [a for a in with_gaps if 0 < a["coverage_pct"] < 50]
    medium_coverage = [a for a in with_gaps if 50 <= a["coverage_pct"] < 80]

    print(f"\nSUMMARY:")
    print(f"  Files with 0% coverage:    {len(zero_coverage)}")
    print(f"  Files with <50% coverage:  {len(low_coverage)}")
    print(f"  Files with <80% coverage:  {len(medium_coverage)}")
    print(f"  Total files with gaps:     {len(with_gaps)}")

    # Critical gaps (0% coverage)
    if zero_coverage:
        print("\n" + "-" * 70)
        print("CRITICAL: Files with NO tests")
        print("-" * 70)
        for item in zero_coverage[:10]:
            print(f"  {item['file']}")
            print(f"    Lines: {item['total_lines']}")
            if item.get("priority_reason"):
                print(f"    Priority: {', '.join(item['priority_reason'])}")

    # High priority gaps
    high_priority = [a for a in prioritized if a["priority_score"] >= 10 and a["coverage_pct"] > 0]
    if high_priority:
        print("\n" + "-" * 70)
        print("HIGH PRIORITY: Core modules with low coverage")
        print("-" * 70)
        for item in high_priority[:10]:
            print(f"  [{item['coverage_pct']}%] {item['file']}")
            print(f"    Missing: {len(item['missing_lines'])} lines")

            # Try to find function names
            functions = find_untested_functions(item["file"], item["missing_ranges"])
            if functions:
                print(f"    Untested functions:")
                for fn in functions[:5]:
                    print(f"      - {fn['name']} (line {fn['line']})")

    # Recommendations
    print("\n" + "-" * 70)
    print("RECOMMENDED ACTIONS")
    print("-" * 70)

    if zero_coverage:
        print(f"\n1. Add tests for {len(zero_coverage)} untested files")
        for item in zero_coverage[:3]:
            print(f"   - {item['file']}")

    if high_priority:
        print(f"\n2. Improve coverage for {len(high_priority)} high-priority modules")
        for item in high_priority[:3]:
            print(f"   - {item['file']} ({item['coverage_pct']}% -> target 80%)")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Analyze coverage gaps from pytest coverage JSON")
    parser.add_argument("coverage_file", help="Path to coverage.json file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--min-lines", type=int, default=5, help="Minimum lines to report (default: 5)")
    args = parser.parse_args()

    if not Path(args.coverage_file).exists():
        print(f"Error: Coverage file not found: {args.coverage_file}")
        print("\nGenerate coverage first:")
        print("  python -m pytest tests/ --cov=src --cov-report=json -q")
        sys.exit(1)

    data = parse_coverage_json(args.coverage_file)
    files = data.get("files", {})

    analysis = []
    for filepath, file_data in files.items():
        file_analysis = analyze_file(filepath, file_data)
        # Filter out files with few lines
        if file_analysis["total_lines"] >= args.min_lines:
            analysis.append(file_analysis)

    generate_report(analysis, output_json=args.json)


if __name__ == "__main__":
    main()
