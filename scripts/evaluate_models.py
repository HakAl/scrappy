#!/usr/bin/env python3
"""
Model Evaluation for JSON Tool-Calling Compliance.

Tests each available model's ability to:
1. Respond ONLY with valid JSON (no preamble, no explanation)
2. Follow the exact schema required for agent tool calls
3. Maintain consistency across multiple runs

Usage:
    python scripts/evaluate_models.py
    python scripts/evaluate_models.py --quick  # Test only fast models
    python scripts/evaluate_models.py --provider groq  # Test specific provider
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Optional
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.providers.cerebras_provider import CerebrasProvider
from src.providers.groq_provider import GroqProvider
from src.providers.gemini_provider import GeminiProvider


# Test scenarios for JSON compliance
TEST_PROMPTS = [
    {
        "name": "simple_file_read",
        "system": """You are a coding assistant. You MUST respond with ONLY valid JSON.

Response format:
{
    "thought": "your reasoning",
    "action": "tool_name",
    "parameters": {"param": "value"},
    "is_complete": false
}

Available tools: read_file, write_file, run_command
Do NOT include any text outside the JSON object.""",
        "user": "Read the file package.json to check dependencies",
        "expected_action": "read_file",
    },
    {
        "name": "install_package",
        "system": """You are a coding assistant. Respond with ONLY valid JSON, no other text.

Format:
{
    "thought": "reasoning here",
    "action": "tool_name",
    "parameters": {"command": "shell command"},
    "is_complete": false
}

Available tools: read_file, write_file, run_command""",
        "user": "Install react-router-dom using npm",
        "expected_action": "run_command",
    },
    {
        "name": "write_file",
        "system": """Respond ONLY with JSON. No explanation before or after.

{
    "thought": "your reasoning",
    "action": "tool_name",
    "parameters": {},
    "is_complete": false
}

Tools: read_file, write_file, run_command""",
        "user": "Create a file called hello.py with a simple hello world function",
        "expected_action": "write_file",
    },
    {
        "name": "task_complete",
        "system": """You are a coding assistant. Respond with ONLY JSON.

For completion:
{
    "thought": "summary",
    "action": "complete",
    "result": "what was accomplished",
    "is_complete": true
}""",
        "user": "The task is done. The file has been created successfully. Mark as complete.",
        "expected_action": "complete",
    },
]


def validate_json_response(response_text: str) -> dict:
    """
    Check if response is valid JSON and follows expected schema.

    Returns:
        dict with validation results
    """
    result = {
        "is_valid_json": False,
        "has_preamble": False,
        "has_postamble": False,
        "has_thought": False,
        "has_action": False,
        "has_parameters": False,
        "uses_lowercase_bool": True,
        "action_value": None,
        "errors": [],
    }

    text = response_text.strip()

    # Check for preamble (text before JSON)
    if not text.startswith("{"):
        result["has_preamble"] = True
        result["errors"].append("Response has text before JSON")

        # Try to find JSON anyway
        start = text.find("{")
        if start != -1:
            text = text[start:]
        else:
            result["errors"].append("No JSON object found")
            return result

    # Check for postamble (text after JSON)
    try:
        # Find matching closing brace
        brace_count = 0
        end_pos = 0
        for i, char in enumerate(text):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i + 1
                    break

        if end_pos < len(text) and text[end_pos:].strip():
            result["has_postamble"] = True
            result["errors"].append("Response has text after JSON")
            text = text[:end_pos]
    except Exception:
        pass

    # Check for Python booleans
    if "True" in text or "False" in text or "None" in text:
        result["uses_lowercase_bool"] = False
        result["errors"].append("Uses Python True/False/None instead of JSON true/false/null")

    # Try to parse JSON
    try:
        # Fix Python booleans if needed
        fixed_text = text.replace("True", "true").replace("False", "false").replace("None", "null")
        data = json.loads(fixed_text)
        result["is_valid_json"] = True

        # Check schema
        if "thought" in data:
            result["has_thought"] = True
        else:
            result["errors"].append("Missing 'thought' field")

        if "action" in data:
            result["has_action"] = True
            result["action_value"] = data["action"]
        else:
            result["errors"].append("Missing 'action' field")

        if "parameters" in data or data.get("action") == "complete":
            result["has_parameters"] = True
        else:
            result["errors"].append("Missing 'parameters' field")

    except json.JSONDecodeError as e:
        result["errors"].append(f"Invalid JSON: {str(e)[:100]}")

    return result


def test_model(provider, model: str, prompt_data: dict) -> dict:
    """Test a single model with a single prompt."""
    messages = [
        {"role": "system", "content": prompt_data["system"]},
        {"role": "user", "content": prompt_data["user"]},
    ]

    try:
        start = time.time()
        response = provider.chat(
            messages=messages,
            model=model,
            max_tokens=500,
            temperature=0.1,  # Low temp for consistency
        )
        latency = time.time() - start

        validation = validate_json_response(response.content)

        return {
            "success": True,
            "response": response.content[:500],
            "validation": validation,
            "latency": latency,
            "tokens": response.tokens_used,
            "correct_action": validation["action_value"] == prompt_data["expected_action"],
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)[:200],
            "validation": {"errors": [str(e)[:100]]},
            "latency": 0,
            "tokens": 0,
            "correct_action": False,
        }


def calculate_score(results: list) -> float:
    """Calculate overall compliance score (0-100)."""
    if not results:
        return 0.0

    total_points = 0
    max_points = len(results) * 100  # 100 points per test

    for result in results:
        if not result["success"]:
            continue

        v = result["validation"]
        points = 0

        # Core requirements (must have all for any points)
        if v["is_valid_json"] and v["has_thought"] and v["has_action"]:
            points = 50  # Base score for valid response

            # Bonus points
            if not v["has_preamble"]:
                points += 20  # Clean start
            if not v["has_postamble"]:
                points += 10  # Clean end
            if v["uses_lowercase_bool"]:
                points += 10  # Proper JSON booleans
            if result["correct_action"]:
                points += 10  # Chose right tool

        total_points += points

    return (total_points / max_points) * 100


def evaluate_provider(provider, provider_name: str, models: list, quick: bool = False):
    """Evaluate all models from a provider."""
    print(f"\n{'='*60}")
    print(f"Evaluating {provider_name.upper()}")
    print(f"{'='*60}")

    model_scores = {}

    for model in models:
        print(f"\n  Testing {model}...")
        results = []

        tests = TEST_PROMPTS[:2] if quick else TEST_PROMPTS

        for prompt in tests:
            print(f"    - {prompt['name']}...", end=" ", flush=True)
            result = test_model(provider, model, prompt)
            results.append(result)

            if result["success"]:
                v = result["validation"]
                if v["is_valid_json"] and not v["has_preamble"]:
                    print("PASS", end="")
                elif v["is_valid_json"]:
                    print("PARTIAL", end="")
                else:
                    print("FAIL", end="")

                if not result["correct_action"]:
                    print(f" (wrong action: {v['action_value']})", end="")
                print()
            else:
                print(f"ERROR: {result['error'][:50]}")

        score = calculate_score(results)
        model_scores[model] = {
            "score": score,
            "results": results,
        }

        print(f"    Score: {score:.1f}/100")

        # Show sample response for debugging
        if results and results[0]["success"]:
            sample = results[0]["response"][:200]
            if len(results[0]["response"]) > 200:
                sample += "..."
            print(f"    Sample: {sample}")

    return model_scores


def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM models for JSON tool-calling compliance")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    parser.add_argument("--provider", type=str, help="Test specific provider only")
    args = parser.parse_args()

    print("LLM Model JSON Compliance Evaluation")
    print("=====================================")
    print("Testing models for structured JSON output capability")
    print("(Critical for agent tool-calling reliability)")

    all_scores = {}

    # Test each provider
    providers_to_test = []

    if args.provider:
        if args.provider.lower() == "cerebras":
            providers_to_test = [("cerebras", CerebrasProvider)]
        elif args.provider.lower() == "groq":
            providers_to_test = [("groq", GroqProvider)]
        elif args.provider.lower() == "gemini":
            providers_to_test = [("gemini", GeminiProvider)]
    else:
        providers_to_test = [
            ("cerebras", CerebrasProvider),
            ("groq", GroqProvider),
            ("gemini", GeminiProvider),
        ]

    for provider_name, provider_class in providers_to_test:
        try:
            provider = provider_class()
            models = provider.available_models
            scores = evaluate_provider(provider, provider_name, models, args.quick)
            all_scores[provider_name] = scores
        except Exception as e:
            print(f"\n  {provider_name}: SKIPPED ({str(e)[:50]})")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY - Models Ranked by JSON Compliance Score")
    print("="*60)

    # Flatten and sort
    ranked = []
    for provider_name, models in all_scores.items():
        for model, data in models.items():
            ranked.append((provider_name, model, data["score"]))

    ranked.sort(key=lambda x: x[2], reverse=True)

    for i, (provider, model, score) in enumerate(ranked, 1):
        status = ""
        if score >= 90:
            status = "EXCELLENT"
        elif score >= 70:
            status = "GOOD"
        elif score >= 50:
            status = "FAIR"
        else:
            status = "POOR"

        print(f"{i:2}. {provider:10} / {model:30} : {score:5.1f} ({status})")

    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    if ranked:
        best = ranked[0]
        print(f"\nBest for Planner: {best[0]} / {best[1]} (score: {best[2]:.1f})")

        if len(ranked) > 1:
            # Find fastest among good scorers
            good_models = [(p, m, s) for p, m, s in ranked if s >= 70]
            if good_models:
                print(f"Backup options: {', '.join([f'{p}/{m}' for p, m, s in good_models[1:4]])}")

    print("\nKey Issues Found:")
    issues = set()
    for provider_name, models in all_scores.items():
        for model, data in models.items():
            for result in data["results"]:
                if result.get("validation"):
                    for error in result["validation"].get("errors", []):
                        issues.add(error)

    for issue in list(issues)[:5]:
        print(f"  - {issue}")


if __name__ == "__main__":
    main()
