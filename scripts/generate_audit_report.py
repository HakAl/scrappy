#!/usr/bin/env python
"""Generate markdown report from test audit JSON."""

import json
import sys
from pathlib import Path


def main():
    audit_dir = Path(".audit")
    input_file = audit_dir / "score_6_plus.json"
    output_file = audit_dir / "test_audit_report.md"

    with open(input_file) as f:
        tests = json.load(f)

    # Group by file
    by_file: dict[str, list] = {}
    for t in tests:
        f = t["file"].replace("\\", "/")
        if f not in by_file:
            by_file[f] = []
        by_file[f].append(t)

    # Build markdown
    lines = [
        "# Test Audit Report: Score >= 6",
        "",
        f"**Total: {len(tests)} tests across {len(by_file)} files**",
        "",
    ]

    # Summary by score
    by_score: dict[int, int] = {}
    for t in tests:
        s = t["score"]
        by_score[s] = by_score.get(s, 0) + 1

    lines.append("## Summary by Score")
    lines.append("")
    lines.append("| Score | Count | Action |")
    lines.append("|-------|-------|--------|")
    for s in sorted(by_score.keys(), reverse=True):
        action = "DELETE" if s >= 9 else "REFACTOR" if s >= 7 else "REVIEW"
        lines.append(f"| {s}/10 | {by_score[s]} | {action} |")
    lines.append("")

    lines.append("## Tests by File")
    lines.append("")

    for f in sorted(by_file.keys()):
        file_tests = sorted(by_file[f], key=lambda x: -x["score"])
        lines.append(f"### {f}")
        lines.append("")
        for t in file_tests:
            # Build reasons from details
            d = t["details"]
            reasons = []
            if d.get("no_op"):
                reasons.append("no-op body")
            if d.get("only_new"):
                reasons.append("only instantiation")
            if d.get("tautologies"):
                reasons.append(f"{d['tautologies']} tautologies")
            if d.get("over_mocked"):
                reasons.append("over-mocked")
            if d.get("swallow"):
                reasons.append("swallows exceptions")
            if d.get("dead_assert"):
                reasons.append("dead assertions")
            if d.get("bare_try_pass"):
                reasons.append("bare try/pass")
            if not d.get("asserts") and not d.get("weak_asserts"):
                reasons.append("no assertions")
            elif not d.get("asserts") and d.get("weak_asserts"):
                reasons.append(f"{d['weak_asserts']} weak assertions only")
            if d.get("mocks", 0) >= 4:
                reasons.append(f"{d['mocks']} mocks")
            reason_str = ", ".join(reasons) if reasons else "low quality"
            lines.append(f"- **[{t['score']}/10]** `{t['test']}` - {reason_str}")
        lines.append("")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"Report written to {output_file}")
    print(f"Total: {len(tests)} tests")


if __name__ == "__main__":
    main()
