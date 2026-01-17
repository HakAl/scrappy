#!/usr/bin/env python3
"""
Query Langfuse traces for debugging agent interactions.

Usage:
    python scripts/langfuse_query.py <trace_id>
    python scripts/langfuse_query.py --list  # List recent traces
    python scripts/langfuse_query.py --search "find_exact_text"  # Search traces

Requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")


def get_auth():
    """Get HTTP Basic Auth tuple."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("Error: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY required in .env")
        sys.exit(1)
    return (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)


def fetch_trace(trace_id: str) -> dict:
    """Fetch a single trace by ID."""
    url = f"{LANGFUSE_HOST}/api/public/traces/{trace_id}"
    resp = requests.get(url, auth=get_auth(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_observations(trace_id: str) -> list:
    """Fetch all observations (spans/generations) for a trace."""
    url = f"{LANGFUSE_HOST}/api/public/observations"
    params = {"traceId": trace_id, "limit": 100}
    resp = requests.get(url, params=params, auth=get_auth(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", [])


def list_traces(limit: int = 20) -> list:
    """List recent traces."""
    url = f"{LANGFUSE_HOST}/api/public/traces"
    params = {"limit": limit, "orderBy": "timestamp.desc"}
    resp = requests.get(url, params=params, auth=get_auth(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", [])


def search_generations(query: str, limit: int = 50) -> list:
    """Search generations by name or content."""
    url = f"{LANGFUSE_HOST}/api/public/generations"
    params = {"limit": limit, "orderBy": "startTime.desc"}
    resp = requests.get(url, params=params, auth=get_auth(), timeout=10)
    resp.raise_for_status()

    results = []
    for gen in resp.json().get("data", []):
        # Search in name, input, output
        searchable = json.dumps(gen, default=str).lower()
        if query.lower() in searchable:
            results.append(gen)
    return results


def format_trace(trace: dict) -> str:
    """Format trace for display."""
    lines = [
        f"Trace: {trace.get('id')}",
        f"Name: {trace.get('name')}",
        f"Time: {trace.get('timestamp')}",
        f"Session: {trace.get('sessionId')}",
        f"Tags: {trace.get('tags', [])}",
        "",
        "Input:",
        json.dumps(trace.get("input"), indent=2, default=str)[:2000],
        "",
        "Output:",
        json.dumps(trace.get("output"), indent=2, default=str)[:2000],
    ]
    return "\n".join(lines)


def format_observation(obs: dict) -> str:
    """Format observation for display."""
    obs_type = obs.get("type", "unknown")
    lines = [
        f"\n{'='*60}",
        f"[{obs_type.upper()}] {obs.get('name')}",
        f"ID: {obs.get('id')}",
        f"Time: {obs.get('startTime')} -> {obs.get('endTime')}",
        f"Model: {obs.get('model')}",
    ]

    if obs.get("input"):
        input_str = json.dumps(obs["input"], indent=2, default=str)
        if len(input_str) > 3000:
            input_str = input_str[:3000] + "\n... (truncated)"
        lines.extend(["", "Input:", input_str])

    if obs.get("output"):
        output_str = json.dumps(obs["output"], indent=2, default=str)
        if len(output_str) > 3000:
            output_str = output_str[:3000] + "\n... (truncated)"
        lines.extend(["", "Output:", output_str])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query Langfuse traces")
    parser.add_argument("trace_id", nargs="?", help="Trace ID to fetch")
    parser.add_argument("--list", action="store_true", help="List recent traces")
    parser.add_argument("--search", help="Search generations for text")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        if args.list:
            traces = list_traces(args.limit)
            if args.json:
                print(json.dumps(traces, indent=2, default=str))
            else:
                for t in traces:
                    print(f"{t.get('timestamp', '')[:19]}  {t.get('id')}  {t.get('name', '')[:40]}")

        elif args.search:
            results = search_generations(args.search, args.limit)
            if args.json:
                print(json.dumps(results, indent=2, default=str))
            else:
                print(f"Found {len(results)} generations matching '{args.search}':\n")
                for gen in results:
                    print(f"{gen.get('startTime', '')[:19]}  {gen.get('traceId')}  {gen.get('name', '')[:40]}")

        elif args.trace_id:
            trace = fetch_trace(args.trace_id)
            observations = fetch_observations(args.trace_id)

            if args.json:
                print(json.dumps({"trace": trace, "observations": observations}, indent=2, default=str))
            else:
                print(format_trace(trace))
                print(f"\n\nObservations ({len(observations)}):")
                for obs in sorted(observations, key=lambda x: x.get("startTime", "")):
                    print(format_observation(obs))

        else:
            parser.print_help()

    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to Langfuse at {LANGFUSE_HOST}")
        print("Make sure Langfuse is running: docker-compose up -d")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
