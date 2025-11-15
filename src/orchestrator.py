"""
LLM Agent Orchestrator

This module provides the coordination layer for multi-provider LLM agent teams.

Architecture:
    Claude Code (complex reasoning) <-- Human/Orchestrator
           |
           v
    Orchestrator (this module)
           |
    +------+------+------+
    |      |      |      |
    v      v      v      v
   Groq  Cohere  [Future providers...]
  (fast) (embed) (OpenRouter, HuggingFace, etc.)

The orchestrator:
1. Maintains a registry of available providers
2. Routes tasks to appropriate providers based on task type
3. Tracks usage and rate limits across providers
4. Provides fallback strategies when limits are hit
"""

from typing import Optional
from datetime import datetime

from .providers import ProviderRegistry, GroqProvider, CohereProvider, GeminiProvider, CerebrasProvider, LLMResponse


class AgentOrchestrator:
    """
    Central coordinator for multi-provider LLM agent team.

    Usage with Claude Code as reasoning layer:
        # In Claude Code session:
        orch = AgentOrchestrator()

        # Delegate simple task to Groq
        result = orch.delegate('groq', 'Summarize this text: ...')

        # Use Cohere for embeddings
        embeddings = orch.providers.get('cohere').embed(['text1', 'text2'])

        # Claude (you) handles complex reasoning, then delegates sub-tasks
    """

    def __init__(self, auto_register: bool = True, orchestrator_provider: Optional[str] = None):
        """
        Initialize orchestrator.

        Args:
            auto_register: Automatically register available providers
            orchestrator_provider: Provider to use as the "brain" for planning/reasoning
                                  (default: 'cerebras' if available, else first available)
        """
        self.registry = ProviderRegistry()
        self.task_history: list[dict] = []
        self.created_at = datetime.now()
        self._brain = None
        self._brain_name = orchestrator_provider

        if auto_register:
            self._auto_register_providers()
            self._setup_brain(orchestrator_provider)

    def _auto_register_providers(self):
        """Attempt to register all known providers."""
        # Try Cerebras (primary - highest quota)
        try:
            self.registry.register(CerebrasProvider())
            print("[OK] Cerebras provider registered (14,400 RPD)")
        except Exception as e:
            print(f"[X] Cerebras provider unavailable: {e}")

        # Try Groq (secondary)
        try:
            self.registry.register(GroqProvider())
            print("[OK] Groq provider registered (7,000 RPD)")
        except Exception as e:
            print(f"[X] Groq provider unavailable: {e}")

        # Try Gemini (with auto-fallback)
        try:
            self.registry.register(GeminiProvider())
            print("[OK] Gemini provider registered (auto-fallback enabled)")
        except Exception as e:
            print(f"[X] Gemini provider unavailable: {e}")

        # Try Cohere (limited - embeddings only)
        try:
            self.registry.register(CohereProvider())
            print("[OK] Cohere provider registered (1,000/month - use sparingly)")
        except Exception as e:
            print(f"[X] Cohere provider unavailable: {e}")

    def _setup_brain(self, preferred_provider: Optional[str] = None):
        """
        Set up the orchestrator's reasoning brain.

        Priority: specified > cerebras > groq > gemini > any available
        """
        available = self.registry.list_available()

        if not available:
            print("[WARN] No providers available for orchestrator brain")
            return

        # Use specified provider if available
        if preferred_provider and preferred_provider in available:
            self._brain = self.registry.get(preferred_provider)
            self._brain_name = preferred_provider
            print(f"[BRAIN] Using {preferred_provider} as orchestrator brain")
            return

        # Default priority: cerebras > groq > gemini
        priority = ['cerebras', 'groq', 'gemini']
        for provider in priority:
            if provider in available:
                self._brain = self.registry.get(provider)
                self._brain_name = provider
                print(f"[BRAIN] Using {provider} as orchestrator brain")
                return

        # Fallback to first available
        self._brain_name = available[0]
        self._brain = self.registry.get(self._brain_name)
        print(f"[BRAIN] Using {self._brain_name} as orchestrator brain (fallback)")

    @property
    def providers(self) -> ProviderRegistry:
        """Access the provider registry."""
        return self.registry

    def status(self) -> dict:
        """
        Get current status of all providers.

        Returns:
            Dict with provider availability and limits
        """
        return {
            'available_providers': self.registry.list_available(),
            'all_providers': self.registry.list_all(),
            'provider_details': self.registry.get_provider_info(),
            'orchestrator_brain': self._brain_name,
            'tasks_executed': len(self.task_history),
            'session_start': self.created_at.isoformat(),
        }

    @property
    def brain(self):
        """Access the orchestrator's reasoning brain."""
        if not self._brain:
            raise RuntimeError("No orchestrator brain configured. No providers available?")
        return self._brain

    def plan(
        self,
        task: str,
        context: Optional[str] = None,
        max_steps: int = 10
    ) -> list[dict]:
        """
        Use the orchestrator brain to break down a complex task into steps.

        Args:
            task: The complex task to plan
            context: Optional context about the codebase/project
            max_steps: Maximum number of steps to generate

        Returns:
            List of step dicts with 'step', 'description', 'provider' keys

        Example:
            steps = orch.plan("Implement user authentication with JWT")
            for step in steps:
                result = orch.delegate(step['provider'], step['description'])
        """
        system_prompt = f"""You are a task planning assistant. Break down the given task into concrete, actionable steps.

For each step, specify:
1. A brief step name
2. A detailed description of what to do
3. Which provider type to use: 'fast' (simple tasks), 'quality' (complex reasoning), or 'high_volume' (many similar tasks)

Respond in this exact JSON format:
[
  {{"step": "step_name", "description": "what to do", "provider_type": "fast|quality|high_volume"}}
]

Maximum {max_steps} steps. Be specific and actionable."""

        user_prompt = task
        if context:
            user_prompt = f"Context:\n{context}\n\nTask:\n{task}"

        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            max_tokens=2000,
            temperature=0.3  # Lower temp for structured output
        )

        # Track this as an orchestration task
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': self._brain_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'task_type': 'planning',
        })

        # Parse the response
        try:
            import json
            # Extract JSON from response (handle markdown code blocks)
            content = response.content.strip()
            if content.startswith('```'):
                # Remove markdown code block
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])
            steps = json.loads(content)
            return steps
        except json.JSONDecodeError:
            # If parsing fails, return raw response as single step
            return [{
                'step': 'execute_task',
                'description': response.content,
                'provider_type': 'quality'
            }]

    def reason(
        self,
        question: str,
        context: Optional[str] = None,
        evidence: Optional[list[str]] = None
    ) -> str:
        """
        Use the orchestrator brain for complex reasoning.

        Args:
            question: The question or problem to reason about
            context: Optional context information
            evidence: Optional list of evidence/facts to consider

        Returns:
            Reasoned response as string

        Example:
            answer = orch.reason(
                "Should we use JWT or session-based auth?",
                context="Building a REST API for mobile app",
                evidence=["App needs offline support", "Multiple devices per user"]
            )
        """
        system_prompt = """You are a reasoning assistant. Analyze the question carefully, consider all evidence, and provide a well-reasoned response.

Structure your response:
1. Key considerations
2. Analysis of options/factors
3. Conclusion with reasoning"""

        user_prompt = question
        if context:
            user_prompt = f"Context: {context}\n\nQuestion: {question}"
        if evidence:
            evidence_str = "\n".join(f"- {e}" for e in evidence)
            user_prompt += f"\n\nEvidence to consider:\n{evidence_str}"

        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            max_tokens=1500,
            temperature=0.5
        )

        # Track
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': self._brain_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'task_type': 'reasoning',
        })

        return response.content

    def synthesize(
        self,
        results: list[LLMResponse],
        synthesis_prompt: str = "Synthesize these results into a coherent summary:"
    ) -> str:
        """
        Use the brain to synthesize multiple agent results.

        Args:
            results: List of LLMResponse objects from various agents
            synthesis_prompt: Prompt for how to synthesize

        Returns:
            Synthesized summary
        """
        # Build context from results
        results_text = []
        for i, result in enumerate(results, 1):
            results_text.append(f"Result {i} (from {result.provider}/{result.model}):\n{result.content}")

        combined = "\n\n---\n\n".join(results_text)

        response = self.brain.chat(
            messages=[
                {'role': 'system', 'content': 'You are a synthesis assistant. Combine multiple perspectives into a coherent whole.'},
                {'role': 'user', 'content': f"{synthesis_prompt}\n\n{combined}"}
            ],
            max_tokens=2000,
            temperature=0.4
        )

        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': self._brain_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
            'task_type': 'synthesis',
        })

        return response.content

    def delegate(
        self,
        provider_name: str,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """
        Delegate a task to a specific provider.

        Args:
            provider_name: Name of provider ('groq', 'cohere', etc.)
            prompt: The user prompt/task
            model: Specific model to use (optional)
            system_prompt: System prompt for context (optional)
            max_tokens: Max response tokens
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with result

        Example:
            # Simple delegation
            result = orch.delegate('groq', 'What is 2+2?')

            # With system prompt
            result = orch.delegate(
                'groq',
                'Review this code for bugs',
                system_prompt='You are a code reviewer. Be concise.'
            )
        """
        provider = self.registry.get(provider_name)

        # Build messages
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        # Execute
        response = provider.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        # Track
        self.task_history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': provider_name,
            'model': response.model,
            'tokens_used': response.tokens_used,
            'latency_ms': response.latency_ms,
        })

        return response

    def delegate_smart(
        self,
        prompt: str,
        task_type: str = 'general',
        **kwargs
    ) -> LLMResponse:
        """
        Automatically select best provider for task type.

        Args:
            prompt: The task/prompt
            task_type: Type of task
                - 'fast': Quick response needed (uses Cerebras > Groq)
                - 'quality': Best quality needed (uses Cerebras 70b > Groq 70b)
                - 'reasoning': Complex reasoning (use orchestrator brain)
                - 'high_volume': Many requests expected (uses Cerebras > Groq)
                - 'embed': Embedding task (uses Cohere - expensive!)
                - 'general': General task (uses Cerebras > Groq)
            **kwargs: Additional parameters

        Returns:
            LLMResponse with result
        """
        available = self.registry.list_available()

        if not available:
            raise RuntimeError("No providers available!")

        # Routing logic - Cerebras is now primary
        if task_type in ['fast', 'high_volume', 'general']:
            # Prefer Cerebras (14,400 RPD), then Groq (7,000 RPD)
            if 'cerebras' in available:
                provider = self.registry.get('cerebras')
                model = provider.get_model_for_task(task_type)
                return self.delegate('cerebras', prompt, model=model, **kwargs)
            elif 'groq' in available:
                provider = self.registry.get('groq')
                model = provider.get_model_for_task(task_type)
                return self.delegate('groq', prompt, model=model, **kwargs)

        elif task_type == 'reasoning':
            # Use the orchestrator brain for reasoning
            return LLMResponse(
                content=self.reason(prompt),
                model=self.brain.default_model,
                provider=self._brain_name,
                metadata={'task_type': 'reasoning', 'via': 'orchestrator_brain'}
            )

        elif task_type == 'quality':
            # Use best available large model
            if 'cerebras' in available:
                return self.delegate(
                    'cerebras',
                    prompt,
                    model='llama-3.3-70b',
                    **kwargs
                )
            elif 'groq' in available:
                return self.delegate(
                    'groq',
                    prompt,
                    model='llama-3.3-70b-versatile',
                    **kwargs
                )

        elif task_type == 'embed' and 'cohere' in available:
            print("WARNING: Using Cohere. This counts toward 1,000/month limit!")
            return self.delegate('cohere', prompt, **kwargs)

        # Fallback: use first available provider
        provider_name = available[0]
        return self.delegate(provider_name, prompt, **kwargs)

    def batch_delegate(
        self,
        tasks: list[dict],
        provider_name: str = 'groq'
    ) -> list[LLMResponse]:
        """
        Process multiple tasks with same provider.

        Args:
            tasks: List of task dicts with 'prompt' and optional 'system_prompt'
            provider_name: Provider to use for all tasks

        Returns:
            List of LLMResponse objects

        Example:
            tasks = [
                {'prompt': 'Summarize: ...'},
                {'prompt': 'Translate: ...'},
                {'prompt': 'Classify: ...'},
            ]
            results = orch.batch_delegate(tasks)
        """
        results = []
        for task in tasks:
            result = self.delegate(
                provider_name,
                task['prompt'],
                system_prompt=task.get('system_prompt'),
                **task.get('kwargs', {})
            )
            results.append(result)
        return results

    def get_usage_report(self) -> dict:
        """
        Get usage statistics for current session.

        Returns:
            Dict with usage metrics by provider
        """
        if not self.task_history:
            return {'message': 'No tasks executed yet'}

        # Aggregate by provider
        by_provider = {}
        for task in self.task_history:
            provider = task['provider']
            if provider not in by_provider:
                by_provider[provider] = {
                    'count': 0,
                    'total_tokens': 0,
                    'total_latency_ms': 0,
                }
            by_provider[provider]['count'] += 1
            by_provider[provider]['total_tokens'] += task['tokens_used']
            by_provider[provider]['total_latency_ms'] += task['latency_ms']

        # Calculate averages
        for provider, stats in by_provider.items():
            stats['avg_tokens'] = stats['total_tokens'] / stats['count']
            stats['avg_latency_ms'] = stats['total_latency_ms'] / stats['count']

        return {
            'total_tasks': len(self.task_history),
            'by_provider': by_provider,
            'session_duration': str(datetime.now() - self.created_at),
        }

    def recommend_provider(self, requirements: dict) -> str:
        """
        Recommend best provider based on requirements.

        Args:
            requirements: Dict with keys like:
                - 'speed': 'fast' | 'moderate' | 'slow'
                - 'quality': 'moderate' | 'good' | 'excellent'
                - 'budget_sensitive': bool
                - 'task_count': int (how many similar tasks)

        Returns:
            Recommended provider name
        """
        available = self.registry.list_available()

        if not available:
            raise RuntimeError("No providers available!")

        # Budget sensitive -> prefer Groq (more quota)
        if requirements.get('budget_sensitive', True):
            if 'groq' in available:
                return 'groq'

        # High volume -> Groq
        if requirements.get('task_count', 1) > 10:
            if 'groq' in available:
                return 'groq'

        # Speed priority -> Groq
        if requirements.get('speed') == 'fast':
            if 'groq' in available:
                return 'groq'

        # Quality priority and willing to use quota -> Cohere
        if requirements.get('quality') == 'excellent':
            if 'cohere' in available and not requirements.get('budget_sensitive', True):
                return 'cohere'

        # Default to Groq if available
        return available[0]


def create_orchestrator() -> AgentOrchestrator:
    """
    Factory function to create an orchestrator.

    Returns:
        Configured AgentOrchestrator instance
    """
    return AgentOrchestrator(auto_register=True)
