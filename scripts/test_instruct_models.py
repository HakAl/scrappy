#!/usr/bin/env python3
"""
Test instruction-tuned models for JSON tool-calling compliance.

Focuses on models with 'instruct' or 'it' in name that should be better
at following structured output format requirements.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# Instruction-tuned models to test
INSTRUCT_MODELS = {
    "cerebras": [
        "qwen-3-235b-a22b-instruct-2507",  # 235B instruction-tuned!
        "llama-3.3-70b",  # For comparison
    ],
    "groq": [
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "moonshotai/kimi-k2-instruct",
        "llama-3.3-70b-versatile",  # For comparison
        "qwen/qwen3-32b",
    ],
    "gemini": [
        "gemma-3-27b-it",  # 27B instruction-tuned
        "gemma-3-12b-it",  # 12B instruction-tuned (faster)
        "gemini-2.5-flash",  # For comparison
    ],
}


# Single comprehensive test prompt
TEST_PROMPT = {
    "system": """You are a coding assistant with access to tools.

CRITICAL: You MUST respond with ONLY a valid JSON object. No text before or after.
No explanations. No markdown. Just the JSON object.

Response format (choose ONE action):
{
    "thought": "Your reasoning about what to do",
    "action": "tool_name",
    "parameters": {"param1": "value1"},
    "is_complete": false
}

Available tools:
- read_file: Read a file. Parameters: {"path": "filename"}
- write_file: Write a file. Parameters: {"path": "filename", "content": "file content"}
- run_command: Run shell command. Parameters: {"command": "shell command"}

Use lowercase true/false for booleans (JSON standard), not True/False (Python).

Example valid response:
{
    "thought": "I need to read package.json to check dependencies",
    "action": "read_file",
    "parameters": {"path": "package.json"},
    "is_complete": false
}""",

    "user": "Install the react-router-dom package using npm",

    "expected_action": "run_command",
}


def validate_response(text: str) -> dict:
    """Validate JSON response structure."""
    text = text.strip()
    result = {
        "raw": text[:300] + ("..." if len(text) > 300 else ""),
        "clean_json": False,
        "valid_json": False,
        "has_thought": False,
        "has_action": False,
        "has_parameters": False,
        "correct_action": False,
        "uses_json_bools": True,
        "score": 0,
    }

    # Check for clean JSON (no preamble)
    if text.startswith("{"):
        result["clean_json"] = True
        result["score"] += 30

    # Check for Python booleans
    if "True" in text or "False" in text or "None" in text:
        result["uses_json_bools"] = False
    else:
        result["score"] += 10

    # Try to extract and parse JSON
    try:
        # Find JSON object
        start = text.find("{")
        if start == -1:
            return result

        brace_count = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                brace_count += 1
            elif text[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        json_str = text[start:end]
        # Fix Python booleans
        json_str = json_str.replace("True", "true").replace("False", "false").replace("None", "null")

        data = json.loads(json_str)
        result["valid_json"] = True
        result["score"] += 30

        if "thought" in data and data["thought"]:
            result["has_thought"] = True
            result["score"] += 10

        if "action" in data:
            result["has_action"] = True
            result["score"] += 10

            # Check if correct action
            if data["action"] == "run_command":
                result["correct_action"] = True
                result["score"] += 10

                # Check if parameters make sense
                if "parameters" in data:
                    result["has_parameters"] = True
                    params = data["parameters"]
                    if "command" in params and "npm" in str(params["command"]) and "react-router" in str(params["command"]):
                        result["score"] += 10  # Bonus for correct command

    except Exception as e:
        result["error"] = str(e)[:100]

    return result


def test_model(provider_name: str, model: str) -> dict:
    """Test a single model."""
    print(f"    Testing {model}...", end=" ", flush=True)

    # Initialize provider
    if provider_name == "cerebras":
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ.get("CEREBRAS_API_KEY"),
            base_url="https://api.cerebras.ai/v1"
        )

        try:
            start = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": TEST_PROMPT["system"]},
                    {"role": "user", "content": TEST_PROMPT["user"]},
                ],
                max_tokens=500,
                temperature=0.1,
            )
            latency = time.time() - start
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
        except Exception as e:
            print(f"ERROR: {str(e)[:50]}")
            return {"error": str(e), "score": 0}

    elif provider_name == "groq":
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

        try:
            start = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": TEST_PROMPT["system"]},
                    {"role": "user", "content": TEST_PROMPT["user"]},
                ],
                max_tokens=500,
                temperature=0.1,
            )
            latency = time.time() - start
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
        except Exception as e:
            print(f"ERROR: {str(e)[:50]}")
            return {"error": str(e), "score": 0}

    elif provider_name == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

        try:
            start = time.time()
            model_instance = genai.GenerativeModel(
                model_name=model,
                generation_config={"max_output_tokens": 500, "temperature": 0.1}
            )

            # Convert to Gemini format
            messages = [
                {"role": "user", "parts": [f"System: {TEST_PROMPT['system']}"]},
                {"role": "model", "parts": ["Understood. I will respond with only valid JSON."]},
                {"role": "user", "parts": [TEST_PROMPT["user"]]},
            ]

            response = model_instance.generate_content(messages)
            latency = time.time() - start
            content = response.text
            tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens = getattr(response.usage_metadata, "prompt_token_count", 0) + \
                        getattr(response.usage_metadata, "candidates_token_count", 0)
        except Exception as e:
            print(f"ERROR: {str(e)[:50]}")
            return {"error": str(e), "score": 0}

    else:
        return {"error": f"Unknown provider: {provider_name}", "score": 0}

    # Validate response
    result = validate_response(content)
    result["latency"] = latency
    result["tokens"] = tokens

    # Print result
    if result["score"] >= 90:
        print(f"EXCELLENT ({result['score']}/100)")
    elif result["score"] >= 70:
        print(f"GOOD ({result['score']}/100)")
    elif result["score"] >= 50:
        print(f"FAIR ({result['score']}/100)")
    else:
        print(f"POOR ({result['score']}/100)")

    return result


def main():
    print("Testing Instruction-Tuned Models for JSON Tool-Calling")
    print("=" * 60)
    print("Task: Install react-router-dom using npm")
    print("Expected: JSON with action='run_command', npm install command")
    print()

    all_results = []

    for provider_name, models in INSTRUCT_MODELS.items():
        print(f"\n{provider_name.upper()}")
        print("-" * 40)

        # Check if provider is available
        env_var = f"{provider_name.upper()}_API_KEY"
        if not os.environ.get(env_var):
            print(f"  Skipped: {env_var} not set")
            continue

        for model in models:
            result = test_model(provider_name, model)
            all_results.append({
                "provider": provider_name,
                "model": model,
                "score": result.get("score", 0),
                "latency": result.get("latency", 0),
                "raw": result.get("raw", ""),
            })

            # Show sample response for low scores
            if result.get("score", 0) < 70 and "raw" in result:
                print(f"      Response: {result['raw'][:150]}")
            elif "raw" in result:
                print(f"      Response: {result['raw'][:100]}")

    # Summary
    print("\n" + "=" * 60)
    print("RANKING BY JSON COMPLIANCE SCORE")
    print("=" * 60)

    all_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(all_results, 1):
        print(f"{i:2}. {r['provider']:10} / {r['model'][:40]:40} : {r['score']:3}/100  ({r['latency']:.1f}s)")

    # Recommendation
    if all_results and all_results[0]["score"] >= 70:
        best = all_results[0]
        print(f"\nRECOMMENDED for Planner: {best['provider']} / {best['model']}")
        print(f"  Score: {best['score']}/100, Latency: {best['latency']:.1f}s")
    else:
        print("\nWARNING: No model scored above 70. Consider:")
        print("  1. Using native tool-calling APIs instead of JSON parsing")
        print("  2. Adding stronger format enforcement in system prompt")
        print("  3. Post-processing responses to extract JSON")


if __name__ == "__main__":
    main()
