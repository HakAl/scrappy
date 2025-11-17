#!/usr/bin/env python3
"""
List all available models from each provider API.

This queries the actual APIs to find models we might not have configured,
particularly looking for instruction-tuned variants that excel at structured output.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def list_cerebras_models():
    """List models available from Cerebras API."""
    print("\n=== CEREBRAS MODELS ===")

    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("  CEREBRAS_API_KEY not set")
        return

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.cerebras.ai/v1"
        )

        # Cerebras uses OpenAI-compatible API
        models = client.models.list()

        print("  Available models:")
        for model in models.data:
            print(f"    - {model.id}")
            # Check for instruction-tuned indicators
            if "instruct" in model.id.lower() or "chat" in model.id.lower():
                print(f"      ^ INSTRUCTION-TUNED")

    except Exception as e:
        print(f"  Error: {e}")


def list_groq_models():
    """List models available from Groq API."""
    print("\n=== GROQ MODELS ===")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("  GROQ_API_KEY not set")
        return

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        models = client.models.list()

        print("  Available models:")
        for model in models.data:
            model_id = model.id
            print(f"    - {model_id}")

            # Check for instruction-tuned indicators
            indicators = ["instruct", "chat", "it", "versatile"]
            for indicator in indicators:
                if indicator in model_id.lower():
                    print(f"      ^ Has '{indicator}' - likely instruction-tuned")
                    break

    except Exception as e:
        print(f"  Error: {e}")


def list_gemini_models():
    """List models available from Gemini API."""
    print("\n=== GEMINI MODELS ===")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  GEMINI_API_KEY not set")
        return

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        models = genai.list_models()

        print("  Available models (with generateContent support):")
        for model in models:
            # Only show models that support text generation
            if "generateContent" in model.supported_generation_methods:
                name = model.name.replace("models/", "")
                print(f"    - {name}")

                # Check for instruction-tuned indicators
                if "instruct" in name.lower() or "it" in name.lower():
                    print(f"      ^ INSTRUCTION-TUNED")

                # Show rate limits if available
                if hasattr(model, "input_token_limit"):
                    print(f"      Input limit: {model.input_token_limit} tokens")

    except Exception as e:
        print(f"  Error: {e}")


def main():
    print("Discovering Available Models from Provider APIs")
    print("=" * 50)
    print("Looking for instruction-tuned variants that might excel at structured output...")

    list_cerebras_models()
    list_groq_models()
    list_gemini_models()

    print("\n" + "=" * 50)
    print("Recommendation:")
    print("  Look for models with: instruct, chat, it, versatile in name")
    print("  These are typically fine-tuned for following instructions")
    print("  and are more likely to respect JSON output format requirements.")


if __name__ == "__main__":
    main()
