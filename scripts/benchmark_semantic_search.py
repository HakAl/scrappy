#!/usr/bin/env python3
"""
Parse semantic search debug logs and extract performance metrics.

Usage:
    python scripts/benchmark_semantic_search.py
    python scripts/benchmark_semantic_search.py --log .scrappy/debug.log
    python scripts/benchmark_semantic_search.py --compare before.log after.log
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class BenchmarkMetrics:
    """Performance metrics extracted from logs."""
    embedding_time: float = 0.0
    indexing_time: float = 0.0
    total_time: float = 0.0
    total_chunks: int = 0
    files_processed: int = 0
    batch_count: int = 0
    skipped_chunks: int = 0

    @property
    def avg_chunks_per_file(self) -> float:
        return self.total_chunks / self.files_processed if self.files_processed > 0 else 0.0

    @property
    def throughput_chunks_per_sec(self) -> float:
        return self.total_chunks / self.total_time if self.total_time > 0 else 0.0


def parse_log(log_path: Path) -> BenchmarkMetrics:
    """Parse debug log and extract semantic search metrics."""
    metrics = BenchmarkMetrics()

    if not log_path.exists():
        print(f"Error: Log file not found: {log_path}")
        sys.exit(1)

    content = log_path.read_text(encoding='utf-8', errors='ignore')

    # Extract embedding generation times
    embedding_times = re.findall(r'Embedding generation took ([\d.]+)s', content)
    metrics.embedding_time = sum(float(t) for t in embedding_times)

    # Extract table.add() times
    indexing_times = re.findall(r'table\.add\(\) took ([\d.]+)s', content)
    metrics.indexing_time = sum(float(t) for t in indexing_times)

    # Extract total chunks added
    chunks_match = re.search(r'Added (\d+) chunks total \(skipped (\d+) small chunks\)', content)
    if chunks_match:
        metrics.total_chunks = int(chunks_match.group(1))
        metrics.skipped_chunks = int(chunks_match.group(2))

    # Count batches processed
    batch_matches = re.findall(r'Successfully added (?:batch|final batch) of (\d+) chunks', content)
    metrics.batch_count = len(batch_matches)

    # Count files processed (from "Indexed <filename>:" lines)
    file_matches = re.findall(r'Indexed [^:]+: \d+ chunks', content)
    metrics.files_processed = len(file_matches)

    # Calculate total time
    metrics.total_time = metrics.embedding_time + metrics.indexing_time

    return metrics


def format_metrics(metrics: BenchmarkMetrics, title: str = "Semantic Search Benchmark") -> str:
    """Format metrics as a readable report."""
    lines = [
        f"\n{'=' * 60}",
        f"{title:^60}",
        f"{'=' * 60}",
        f"Embedding Generation:  {metrics.embedding_time:>8.2f}s",
        f"Indexing Operations:   {metrics.indexing_time:>8.2f}s",
        f"Total Time:            {metrics.total_time:>8.2f}s",
        f"{'-' * 60}",
        f"Files Processed:       {metrics.files_processed:>8}",
        f"Total Chunks:          {metrics.total_chunks:>8}",
        f"Skipped Chunks:        {metrics.skipped_chunks:>8}",
        f"Batches:               {metrics.batch_count:>8}",
        f"{'-' * 60}",
        f"Avg Chunks/File:       {metrics.avg_chunks_per_file:>8.2f}",
        f"Throughput:            {metrics.throughput_chunks_per_sec:>8.2f} chunks/sec",
        f"{'=' * 60}\n",
    ]
    return '\n'.join(lines)


def compare_metrics(before: BenchmarkMetrics, after: BenchmarkMetrics) -> str:
    """Generate a comparison report showing before/after changes."""

    def percent_change(old: float, new: float) -> str:
        if old == 0:
            return "N/A"
        change = ((new - old) / old) * 100
        symbol = "⬆" if change > 0 else "⬇" if change < 0 else "="
        return f"{change:+6.1f}% {symbol}"

    def absolute_change(old: float, new: float) -> str:
        change = new - old
        return f"{change:+.2f}s"

    lines = [
        f"\n{'=' * 70}",
        f"{'Comparison: Before → After':^70}",
        f"{'=' * 70}",
        f"{'Metric':<30} {'Before':>12} {'After':>12} {'Change':>12}",
        f"{'-' * 70}",
        f"{'Embedding Time':<30} {before.embedding_time:>10.2f}s {after.embedding_time:>10.2f}s {absolute_change(before.embedding_time, after.embedding_time):>12}",
        f"{'Indexing Time':<30} {before.indexing_time:>10.2f}s {after.indexing_time:>10.2f}s {absolute_change(before.indexing_time, after.indexing_time):>12}",
        f"{'Total Time':<30} {before.total_time:>10.2f}s {after.total_time:>10.2f}s {absolute_change(before.total_time, after.total_time):>12}",
        f"{'-' * 70}",
        f"{'Files Processed':<30} {before.files_processed:>12} {after.files_processed:>12} {after.files_processed - before.files_processed:>+12}",
        f"{'Total Chunks':<30} {before.total_chunks:>12} {after.total_chunks:>12} {after.total_chunks - before.total_chunks:>+12}",
        f"{'-' * 70}",
        f"{'Throughput (chunks/s)':<30} {before.throughput_chunks_per_sec:>12.2f} {after.throughput_chunks_per_sec:>12.2f} {percent_change(before.throughput_chunks_per_sec, after.throughput_chunks_per_sec):>12}",
        f"{'=' * 70}\n",
    ]
    return '\n'.join(lines)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Parse semantic search logs and extract performance metrics'
    )
    parser.add_argument(
        '--log',
        type=Path,
        default=Path('.scrappy/debug.log'),
        help='Path to debug log file (default: .scrappy/debug.log)'
    )
    parser.add_argument(
        '--compare',
        nargs=2,
        metavar=('BEFORE', 'AFTER'),
        type=Path,
        help='Compare two log files (before and after)'
    )

    args = parser.parse_args()

    if args.compare:
        # Comparison mode
        before_metrics = parse_log(args.compare[0])
        after_metrics = parse_log(args.compare[1])

        print(format_metrics(before_metrics, "BEFORE"))
        print(format_metrics(after_metrics, "AFTER"))
        print(compare_metrics(before_metrics, after_metrics))
    else:
        # Single log analysis
        metrics = parse_log(args.log)
        print(format_metrics(metrics))


if __name__ == '__main__':
    main()
