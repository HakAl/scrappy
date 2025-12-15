#!/usr/bin/env python3
"""
Record real provider streaming responses for golden file tests.

This script captures actual streaming responses from configured providers
to create golden files that replay provider quirks (fragmentation patterns,
timing, tool call chunking, etc.) in tests without making real API calls.

Usage:
    python scripts/record_stream.py --provider groq --scenario basic
    python scripts/record_stream.py --provider cerebras --scenario tool_call
    python scripts/record_stream.py --all

Scenarios:
    basic: Simple text completion
    tool_call: Completion with tool call (function calling)
    long_response: Multi-paragraph response to test fragmentation
    unicode: Response with unicode characters
    empty: Empty/minimal response

Golden files saved to: tests/orchestrator/golden/{provider}_{scenario}.json
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, UTC

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()


@dataclass
class StreamChunkRecord:
    """Record of a single stream chunk."""
    index: int
    timestamp_ms: float
    delta_content: Optional[str]
    delta_tool_calls: Optional[list[dict[str, Any]]]
    finish_reason: Optional[str]
    raw_chunk: dict[str, Any]


@dataclass
class StreamRecording:
    """Complete recording of a stream response."""
    provider: str
    model: str
    scenario: str
    recorded_at: str
    total_chunks: int
    total_duration_ms: float
    prompt: list[dict[str, str]]
    tools: Optional[list[dict[str, Any]]]
    chunks: list[dict[str, Any]]


# Test scenarios with prompts
SCENARIOS = {
    "basic": {
        "messages": [{"role": "user", "content": "Say hello in exactly 5 words."}],
        "tools": None,
    },
    "tool_call": {
        "messages": [
            {
                "role": "user",
                "content": "What is the weather in San Francisco? Use the get_weather tool."
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather in a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "description": "Temperature unit",
                            },
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
    },
    "long_response": {
        "messages": [
            {
                "role": "user",
                "content": "Write a 3-paragraph explanation of recursion in programming. Keep it concise."
            }
        ],
        "tools": None,
    },
    "unicode": {
        "messages": [
            {
                "role": "user",
                "content": "Respond with these unicode characters: emoji, chinese, math symbols."
            }
        ],
        "tools": None,
    },
    "empty": {
        "messages": [{"role": "user", "content": "Say 'OK'"}],
        "tools": None,
    },
}


# Provider model mappings
PROVIDER_MODELS = {
    "groq": "groq/llama-3.1-8b-instant",
    "cerebras": "cerebras/llama3.1-8b",
    "gemini": "gemini/gemini-2.5-flash",
    "sambanova": "sambanova/Meta-Llama-3.1-8B-Instruct",
}

PROVIDER_API_KEYS = {
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
}


async def record_stream(
    provider: str,
    scenario: str,
    output_dir: Path,
) -> Optional[Path]:
    """
    Record a streaming response from a provider.

    Args:
        provider: Provider name (groq, cerebras, gemini, sambanova)
        scenario: Scenario name from SCENARIOS
        output_dir: Directory to save golden files

    Returns:
        Path to saved golden file, or None if failed
    """
    import litellm

    # Validate provider
    if provider not in PROVIDER_MODELS:
        print(f"ERROR: Unknown provider '{provider}'. Available: {list(PROVIDER_MODELS.keys())}")
        return None

    # Check API key
    api_key_env = PROVIDER_API_KEYS[provider]
    api_key = os.getenv(api_key_env)
    if not api_key:
        print(f"SKIP: {provider} - No API key found (set {api_key_env})")
        return None

    # Validate scenario
    if scenario not in SCENARIOS:
        print(f"ERROR: Unknown scenario '{scenario}'. Available: {list(SCENARIOS.keys())}")
        return None

    model = PROVIDER_MODELS[provider]
    scenario_config = SCENARIOS[scenario]

    print(f"Recording: {provider}/{scenario} using {model}")

    # Prepare request
    request_params = {
        "model": model,
        "api_key": api_key,
        "messages": scenario_config["messages"],
        "stream": True,
        "max_tokens": 200,
    }

    if scenario_config["tools"]:
        request_params["tools"] = scenario_config["tools"]
        request_params["tool_choice"] = "auto"

    # Record chunks
    chunks = []
    start_time = asyncio.get_event_loop().time()

    try:
        response = await litellm.acompletion(**request_params)

        chunk_index = 0
        async for chunk in response:
            chunk_time = asyncio.get_event_loop().time()
            timestamp_ms = (chunk_time - start_time) * 1000

            # Extract delta information
            delta_content = None
            delta_tool_calls = None
            finish_reason = None

            if hasattr(chunk, 'choices') and chunk.choices:
                choice = chunk.choices[0]
                finish_reason = getattr(choice, 'finish_reason', None)

                if hasattr(choice, 'delta'):
                    delta = choice.delta
                    delta_content = getattr(delta, 'content', None)

                    # Extract tool calls from delta
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        delta_tool_calls = []
                        for tc in delta.tool_calls:
                            tool_call_dict = {
                                "index": getattr(tc, 'index', None),
                                "id": getattr(tc, 'id', None),
                                "type": getattr(tc, 'type', None),
                            }
                            if hasattr(tc, 'function'):
                                tool_call_dict["function"] = {
                                    "name": getattr(tc.function, 'name', None),
                                    "arguments": getattr(tc.function, 'arguments', None),
                                }
                            delta_tool_calls.append(tool_call_dict)

            # Convert chunk to dict (store raw chunk for replay)
            # We use chunk.__dict__ or convert to dict manually
            raw_chunk = {}
            if hasattr(chunk, 'model_dump'):
                raw_chunk = chunk.model_dump()
            elif hasattr(chunk, 'dict'):
                raw_chunk = chunk.dict()
            else:
                # Fallback: manually extract fields
                raw_chunk = {
                    "id": getattr(chunk, 'id', None),
                    "object": getattr(chunk, 'object', None),
                    "created": getattr(chunk, 'created', None),
                    "model": getattr(chunk, 'model', None),
                    "choices": [],
                }
                if hasattr(chunk, 'choices') and chunk.choices:
                    for choice in chunk.choices:
                        choice_dict = {
                            "index": getattr(choice, 'index', None),
                            "finish_reason": getattr(choice, 'finish_reason', None),
                            "delta": {},
                        }
                        if hasattr(choice, 'delta'):
                            delta = choice.delta
                            choice_dict["delta"] = {
                                "content": getattr(delta, 'content', None),
                                "role": getattr(delta, 'role', None),
                            }
                            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                                choice_dict["delta"]["tool_calls"] = delta_tool_calls
                        raw_chunk["choices"].append(choice_dict)

            chunk_record = StreamChunkRecord(
                index=chunk_index,
                timestamp_ms=timestamp_ms,
                delta_content=delta_content,
                delta_tool_calls=delta_tool_calls,
                finish_reason=finish_reason,
                raw_chunk=raw_chunk,
            )

            chunks.append(asdict(chunk_record))
            chunk_index += 1

        end_time = asyncio.get_event_loop().time()
        total_duration_ms = (end_time - start_time) * 1000

        # Create recording
        recording = StreamRecording(
            provider=provider,
            model=model,
            scenario=scenario,
            recorded_at=datetime.now(UTC).isoformat(),
            total_chunks=len(chunks),
            total_duration_ms=total_duration_ms,
            prompt=scenario_config["messages"],
            tools=scenario_config["tools"],
            chunks=chunks,
        )

        # Save to file
        output_file = output_dir / f"{provider}_{scenario}.json"
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(recording), f, indent=2, ensure_ascii=False)

        print(f"  Saved: {output_file} ({len(chunks)} chunks, {total_duration_ms:.1f}ms)")
        return output_file

    except Exception as e:
        print(f"  ERROR: {provider}/{scenario} - {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="Record provider streaming responses")
    parser.add_argument(
        "--provider",
        choices=list(PROVIDER_MODELS.keys()),
        help="Provider to record from"
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        help="Scenario to record"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Record all providers and scenarios"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "tests" / "orchestrator" / "golden",
        help="Output directory for golden files"
    )

    args = parser.parse_args()

    if args.all:
        # Record all combinations
        print("Recording all provider/scenario combinations...\n")
        success_count = 0
        skip_count = 0
        error_count = 0

        for provider in PROVIDER_MODELS.keys():
            for scenario in SCENARIOS.keys():
                result = await record_stream(provider, scenario, args.output)
                if result:
                    success_count += 1
                elif result is None and provider not in os.environ.get(PROVIDER_API_KEYS[provider], ''):
                    skip_count += 1
                else:
                    error_count += 1

        print(f"\nCompleted: {success_count} recorded, {skip_count} skipped (no key), {error_count} errors")

    elif args.provider and args.scenario:
        # Record specific combination
        await record_stream(args.provider, args.scenario, args.output)

    else:
        parser.error("Either specify --provider and --scenario, or use --all")


if __name__ == "__main__":
    asyncio.run(main())
