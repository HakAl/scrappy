#!/usr/bin/env python3
"""
Basic usage example for the Multi-Provider LLM Agent Team.

This demonstrates:
1. Provider registration and status
2. Simple task delegation to Cerebras (primary)
3. Smart delegation with auto-routing
4. Using the orchestrator brain for planning
5. Usage reporting
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from providers import CerebrasProvider, GroqProvider, GeminiProvider, ProviderRegistry


def main():
    print("=" * 60)
    print("Multi-Provider LLM Agent Team - Basic Usage")
    print("=" * 60)

    # 1. Direct provider usage
    print("\n1. Direct Provider Usage")
    print("-" * 40)

    try:
        cerebras = CerebrasProvider()
        print(f"Cerebras available: {cerebras.is_available()}")
        print(f"Models: {cerebras.available_models}")

        result = cerebras.chat(
            messages=[{"role": "user", "content": "What is 2+2? Answer with just the number."}],
            max_tokens=10
        )
        print(f"Response: {result.content}")
        print(f"Tokens: {result.tokens_used}, Latency: {result.latency_ms:.0f}ms")
    except Exception as e:
        print(f"Cerebras not available: {e}")

    # 2. Registry pattern
    print("\n2. Provider Registry")
    print("-" * 40)

    registry = ProviderRegistry()

    # Register available providers
    providers = [
        (CerebrasProvider, "Cerebras"),
        (GroqProvider, "Groq"),
        (GeminiProvider, "Gemini"),
    ]

    for ProviderClass, name in providers:
        try:
            registry.register(ProviderClass())
            print(f"[OK] {name} registered")
        except Exception as e:
            print(f"[X] {name}: {e}")

    print(f"\nAvailable: {registry.list_available()}")

    # 3. Smart model selection
    print("\n3. Model Selection by Task Type")
    print("-" * 40)

    if 'cerebras' in registry.list_available():
        cerebras = registry.get('cerebras')
        print(f"Fast task: {cerebras.get_model_for_task('fast')}")
        print(f"Quality task: {cerebras.get_model_for_task('quality')}")
        print(f"High volume: {cerebras.get_model_for_task('high_volume')}")

    # 4. Simple chat example
    print("\n4. Simple Chat Example")
    print("-" * 40)

    if registry.list_available():
        provider = registry.get(registry.list_available()[0])
        result = provider.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Be concise."},
                {"role": "user", "content": "List 3 benefits of microservices architecture."}
            ],
            max_tokens=150,
            temperature=0.7
        )
        print(f"Provider: {provider.name}")
        print(f"Model: {result.model}")
        print(f"Response:\n{result.content}")

    # 5. Rate limit info
    print("\n5. Rate Limit Information")
    print("-" * 40)

    for name in registry.list_available():
        provider = registry.get(name)
        limits = provider.get_limits()
        print(f"{name}:")
        if limits.requests_per_day:
            print(f"  Requests/day: {limits.requests_per_day}")
        if limits.tokens_per_minute:
            print(f"  Tokens/min: {limits.tokens_per_minute}")

    print("\n" + "=" * 60)
    print("For orchestrator features (planning, reasoning, synthesis),")
    print("see examples/orchestrator_demo.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
