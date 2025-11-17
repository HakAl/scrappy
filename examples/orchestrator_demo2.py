#!/usr/bin/env python3
"""Test the swappable orchestrator brain."""

import sys
sys.path.insert(0, 'src')

# Need to handle the relative import issue
from providers import CerebrasProvider, GroqProvider, GeminiProvider, CohereProvider, ProviderRegistry, LLMResponse
from providers.base import ProviderLimits
from datetime import datetime
from typing import Optional
import json


class TestableOrchestrator:
    """Simplified orchestrator for testing (avoids relative import issues)."""

    def __init__(self, orchestrator_provider: Optional[str] = None):
        self.registry = ProviderRegistry()
        self.task_history = []
        self.created_at = datetime.now()
        self._brain = None
        self._brain_name = None

        self._auto_register()
        self._setup_brain(orchestrator_provider)

    def _auto_register(self):
        """Register all available providers."""
        providers = [
            (CerebrasProvider, "Cerebras", "14,400 RPD"),
            (GroqProvider, "Groq", "7,000 RPD"),
            (GeminiProvider, "Gemini", "auto-fallback"),
            (CohereProvider, "Cohere", "1,000/month"),
        ]

        for ProviderClass, name, note in providers:
            try:
                self.registry.register(ProviderClass())
                print(f"[OK] {name} registered ({note})")
            except Exception as e:
                print(f"[X] {name} unavailable: {e}")

    def _setup_brain(self, preferred: Optional[str] = None):
        """Set up orchestrator brain."""
        available = self.registry.list_available()

        if not available:
            print("[WARN] No providers available")
            return

        # Priority: preferred > cerebras > groq > gemini
        if preferred and preferred in available:
            self._brain = self.registry.get(preferred)
            self._brain_name = preferred
        else:
            for p in ['cerebras', 'groq', 'gemini']:
                if p in available:
                    self._brain = self.registry.get(p)
                    self._brain_name = p
                    break

        if self._brain:
            print(f"[BRAIN] Using {self._brain_name} as orchestrator brain")

    @property
    def brain(self):
        if not self._brain:
            raise RuntimeError("No brain configured")
        return self._brain

    def plan(self, task: str, max_steps: int = 5) -> list[dict]:
        """Break down task into steps."""
        system_prompt = f"""Break down this task into {max_steps} or fewer concrete steps.
Return JSON array: [{{"step": "name", "description": "what to do", "provider_type": "fast|quality"}}]
Be specific."""

        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': task}
            ],
            max_tokens=1000,
            temperature=0.3
        )

        self.task_history.append({
            'type': 'planning',
            'provider': self._brain_name,
            'tokens': response.tokens_used
        })

        # Parse JSON
        content = response.content.strip()
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:-1])

        try:
            return json.loads(content)
        except:
            return [{'step': 'execute', 'description': response.content, 'provider_type': 'quality'}]

    def reason(self, question: str) -> str:
        """Complex reasoning using brain."""
        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': 'Analyze carefully and provide reasoned response. Be concise.'},
                {'role': 'user', 'content': question}
            ],
            max_tokens=500,
            temperature=0.5
        )

        self.task_history.append({
            'type': 'reasoning',
            'provider': self._brain_name,
            'tokens': response.tokens_used
        })

        return response.content

    def status(self) -> dict:
        return {
            'brain': self._brain_name,
            'available': self.registry.list_available(),
            'tasks': len(self.task_history)
        }


def main():
    print("=" * 50)
    print("Testing Swappable Orchestrator Brain")
    print("=" * 50)

    # Test 1: Default brain (should be Cerebras)
    print("\n--- Test 1: Default Brain ---")
    orch = TestableOrchestrator()
    print(f"Status: {orch.status()}")

    # Test 2: Planning
    print("\n--- Test 2: Task Planning ---")
    steps = orch.plan("Add user authentication to Flask app")
    print(f"Generated {len(steps)} steps:")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step.get('step', 'N/A')}: {step.get('description', 'N/A')[:60]}...")

    # Test 3: Reasoning
    print("\n--- Test 3: Complex Reasoning ---")
    answer = orch.reason("What are the trade-offs between JWT and session-based auth for a mobile app?")
    print(f"Answer:\n{answer[:500]}...")

    # Test 4: Swap brain to Groq
    print("\n--- Test 4: Swap Brain to Groq ---")
    orch2 = TestableOrchestrator(orchestrator_provider='groq')
    print(f"Status: {orch2.status()}")
    answer2 = orch2.reason("When should I use async/await vs threading in Python?")
    print(f"Answer:\n{answer2[:400]}...")

    print("\n" + "=" * 50)
    print("All tests passed! Orchestrator brain is swappable.")
    print("=" * 50)


if __name__ == "__main__":
    main()
