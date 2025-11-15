#!/usr/bin/env python3
"""
Orchestrator demo with swappable brain.

This demonstrates:
1. Swappable orchestrator brain (Cerebras/Groq/Gemini)
2. Task planning using brain
3. Complex reasoning
4. Multi-agent synthesis
5. Smart delegation
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Handle relative import issue by importing directly
from providers import (
    CerebrasProvider, GroqProvider, GeminiProvider, CohereProvider,
    ProviderRegistry, LLMResponse
)
from datetime import datetime
from typing import Optional
import json


class DemoOrchestrator:
    """
    Demo orchestrator with swappable brain.

    This is a simplified version that avoids import issues.
    See src/orchestrator.py for full implementation.
    """

    def __init__(self, orchestrator_provider: Optional[str] = None):
        self.registry = ProviderRegistry()
        self.task_history = []
        self._brain = None
        self._brain_name = None

        self._register_providers()
        self._setup_brain(orchestrator_provider)

    def _register_providers(self):
        """Auto-register available providers."""
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
                print(f"[X] {name}: {str(e)[:50]}")

    def _setup_brain(self, preferred: Optional[str] = None):
        """Set up orchestrator brain."""
        available = self.registry.list_available()

        if not available:
            print("[WARN] No providers available for brain")
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
            print(f"[BRAIN] {self._brain_name} selected as orchestrator brain")

    @property
    def brain(self):
        if not self._brain:
            raise RuntimeError("No brain configured")
        return self._brain

    def status(self):
        return {
            'brain': self._brain_name,
            'available': self.registry.list_available(),
            'tasks': len(self.task_history)
        }

    def plan(self, task: str, max_steps: int = 5):
        """Use brain to plan a complex task."""
        print(f"\n[Planning] Breaking down: {task}")

        system_prompt = f"""Break down this task into {max_steps} or fewer steps.
Return JSON: [{{"step": "name", "description": "action", "provider_type": "fast|quality"}}]"""

        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': task}
            ],
            max_tokens=1000,
            temperature=0.3
        )

        self.task_history.append({'type': 'planning', 'provider': self._brain_name})

        # Parse JSON
        content = response.content.strip()
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:-1])

        try:
            return json.loads(content)
        except:
            return [{'step': 'execute', 'description': response.content, 'provider_type': 'quality'}]

    def reason(self, question: str, context: str = None, evidence: list = None):
        """Use brain for complex reasoning."""
        print(f"\n[Reasoning] Analyzing: {question[:50]}...")

        system_prompt = "Analyze carefully. Structure: 1) Key points, 2) Analysis, 3) Conclusion."

        user_prompt = question
        if context:
            user_prompt = f"Context: {context}\n\nQuestion: {question}"
        if evidence:
            evidence_str = "\n".join(f"- {e}" for e in evidence)
            user_prompt += f"\n\nEvidence:\n{evidence_str}"

        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            max_tokens=800,
            temperature=0.5
        )

        self.task_history.append({'type': 'reasoning', 'provider': self._brain_name})
        return response.content

    def delegate(self, provider_name: str, prompt: str, **kwargs):
        """Delegate task to specific provider."""
        provider = self.registry.get(provider_name)
        response = provider.chat(
            messages=[{'role': 'user', 'content': prompt}],
            **kwargs
        )
        self.task_history.append({'type': 'delegation', 'provider': provider_name})
        return response

    def synthesize(self, results: list, prompt: str = "Synthesize these results:"):
        """Use brain to synthesize multiple results."""
        print(f"\n[Synthesizing] Combining {len(results)} results...")

        results_text = []
        for i, result in enumerate(results, 1):
            results_text.append(f"Result {i} ({result.provider}):\n{result.content}")

        combined = "\n\n---\n\n".join(results_text)

        response = self.brain.chat(
            messages=[
                {'role': 'user', 'content': f"{prompt}\n\n{combined}"}
            ],
            max_tokens=1000,
            temperature=0.4
        )

        self.task_history.append({'type': 'synthesis', 'provider': self._brain_name})
        return response.content


def demo_swappable_brain():
    """Demo 1: Swappable orchestrator brain."""
    print("\n" + "=" * 60)
    print("DEMO 1: Swappable Orchestrator Brain")
    print("=" * 60)

    # Default brain (Cerebras)
    print("\n--- Default Brain (Cerebras) ---")
    orch1 = DemoOrchestrator()
    print(f"Status: {orch1.status()}")

    # Swap to Groq
    print("\n--- Swap to Groq Brain ---")
    orch2 = DemoOrchestrator(orchestrator_provider='groq')
    print(f"Status: {orch2.status()}")


def demo_task_planning():
    """Demo 2: Task planning with brain."""
    print("\n" + "=" * 60)
    print("DEMO 2: Task Planning")
    print("=" * 60)

    orch = DemoOrchestrator()
    steps = orch.plan("Add user authentication to a Flask API")

    print(f"\nGenerated {len(steps)} steps:")
    for i, step in enumerate(steps, 1):
        name = step.get('step', 'N/A')
        desc = step.get('description', 'N/A')[:80]
        ptype = step.get('provider_type', 'N/A')
        print(f"  {i}. [{ptype}] {name}")
        print(f"     {desc}...")


def demo_complex_reasoning():
    """Demo 3: Complex reasoning with evidence."""
    print("\n" + "=" * 60)
    print("DEMO 3: Complex Reasoning")
    print("=" * 60)

    orch = DemoOrchestrator()
    answer = orch.reason(
        question="Should we use JWT or session-based authentication?",
        context="Building a mobile app backend with REST API",
        evidence=[
            "App needs offline capability",
            "Users have multiple devices",
            "Security is critical (financial data)"
        ]
    )

    print(f"\nAnalysis:\n{answer[:600]}...")


def demo_multi_agent():
    """Demo 4: Multi-agent with synthesis."""
    print("\n" + "=" * 60)
    print("DEMO 4: Multi-Agent Synthesis")
    print("=" * 60)

    orch = DemoOrchestrator()

    if len(orch.registry.list_available()) < 2:
        print("Need at least 2 providers for this demo")
        return

    question = "What are 2 key benefits of TypeScript over JavaScript?"

    # Get perspectives from different providers
    results = []
    available = orch.registry.list_available()[:2]

    for provider in available:
        print(f"\n[Asking {provider}]")
        result = orch.delegate(provider, question, max_tokens=100)
        print(f"Response: {result.content[:150]}...")
        results.append(result)

    # Synthesize
    summary = orch.synthesize(results, "Identify common themes and unique insights:")
    print(f"\n[Synthesis]\n{summary[:400]}...")


def demo_usage_tracking():
    """Demo 5: Usage tracking."""
    print("\n" + "=" * 60)
    print("DEMO 5: Usage Tracking")
    print("=" * 60)

    orch = DemoOrchestrator()

    # Do some tasks
    orch.plan("Build a REST API")
    orch.reason("Redis vs Memcached for caching?")
    if 'groq' in orch.registry.list_available():
        orch.delegate('groq', "Hello", max_tokens=10)

    print(f"\nTask History:")
    for task in orch.task_history:
        print(f"  - {task['type']} via {task['provider']}")

    print(f"\nTotal tasks: {len(orch.task_history)}")


def main():
    print("=" * 60)
    print("Multi-Provider LLM Orchestrator - Feature Demo")
    print("=" * 60)

    # Run demos
    demo_swappable_brain()
    demo_task_planning()
    demo_complex_reasoning()
    # demo_multi_agent()  # Uncomment to test multi-agent (uses more API calls)
    demo_usage_tracking()

    print("\n" + "=" * 60)
    print("Demo complete! Key takeaways:")
    print("- Brain is swappable (Cerebras/Groq/Gemini)")
    print("- Planning, reasoning, synthesis all use brain")
    print("- No Claude Code subscription required")
    print("- 23,000+ free requests/day available")
    print("=" * 60)


if __name__ == "__main__":
    main()
