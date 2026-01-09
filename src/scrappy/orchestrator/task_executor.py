"""
Task execution and orchestration logic.

Provides planning, reasoning, and synthesis capabilities using LLM providers.
"""

from typing import Optional, Callable, TYPE_CHECKING
import json

try:
    from ..providers import LLMResponse
except ImportError:
    from providers import LLMResponse

if TYPE_CHECKING:
    from .protocols import LLMServiceProtocol


class TaskExecutor:
    """
    Handles task planning, reasoning, and synthesis operations.

    Uses LLMService for LLM calls (replaces old brain provider pattern).
    """

    def __init__(
        self,
        llm_service: "LLMServiceProtocol",
        record_task: Callable,
        # Legacy parameters for backward compatibility
        get_brain_provider: Optional[Callable] = None,
        get_brain_name: Optional[Callable] = None,
    ):
        """
        Initialize task executor.

        Args:
            llm_service: LLM service for making completion calls
            record_task: Callable to record task history
            get_brain_provider: DEPRECATED - ignored
            get_brain_name: DEPRECATED - ignored
        """
        self._llm_service = llm_service
        self._record_task = record_task

    def _is_simple_task(self, task: str) -> bool:
        """
        Determine if a task is simple enough to skip planning.

        A task is considered simple if:
        - It's short (under 50 chars or under 10 words)
        - Contains single action verbs without complex conjunctions
        - Has no enumeration or multi-step indicators

        Returns:
            True if task is simple and planning should be skipped
        """
        # Length-based checks
        word_count = len(task.split())
        if word_count <= 8 and len(task) < 50:
            # Check for multi-step indicators
            multi_step_indicators = [
                ' and ', ' then ', ' after ', ' before ', ' next ',
                '1.', '2.', '3.', 'first', 'second', 'third',
                'step 1', 'step 2', 'steps:', 'multiple', 'several'
            ]
            task_lower = task.lower()
            if not any(indicator in task_lower for indicator in multi_step_indicators):
                return True

        return False

    def plan(
        self,
        task: str,
        context: Optional[str] = None,
        max_steps: int = 10,
        complexity_score: Optional[int] = None
    ) -> list[dict]:
        """
        Break down a complex task into steps.

        Args:
            task: The complex task to plan
            context: Optional context about the codebase/project
            max_steps: Maximum number of steps to generate
            complexity_score: Optional complexity score (1-10). If <= 3, planning is skipped.

        Returns:
            List of step dicts with 'step', 'description', 'provider_type' keys

        Example:
            steps = executor.plan("Implement user authentication with JWT")
            for step in steps:
                result = orch.delegate(step['provider_type'], step['description'])
        """
        # Only skip planning if explicitly marked as simple via complexity_score
        # Never skip when user explicitly requests planning via /plan command
        if complexity_score is not None and complexity_score <= 3:
            return [{
                'step': 'execute_task',
                'description': task,
                'provider_type': 'fast'
            }]

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

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        response, task_record = self._llm_service.completion_sync(
            model="quality",  # Planning uses quality tier
            messages=messages,
            max_tokens=2000,
            temperature=0.3  # Lower temp for structured output
        )

        # Track this as an orchestration task
        task_record['task_type'] = 'planning'
        self._record_task(task_record)

        # Parse the response
        try:
            # Extract JSON from response (handle markdown code blocks and embedded JSON)
            # Handle None content from some providers
            content = (response.content or "").strip()

            # Try to extract JSON array from content
            json_content = None

            # Method 1: Check for markdown code blocks
            if '```' in content:
                # Find code block content
                import re
                code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
                if code_block_match:
                    json_content = code_block_match.group(1).strip()

            # Method 2: Find JSON array anywhere in the content
            if json_content is None:
                # Look for [ ... ] pattern (JSON array)
                start_idx = content.find('[')
                if start_idx != -1:
                    # Find matching closing bracket
                    bracket_count = 0
                    end_idx = start_idx
                    for i in range(start_idx, len(content)):
                        if content[i] == '[':
                            bracket_count += 1
                        elif content[i] == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end_idx = i + 1
                                break
                    if end_idx > start_idx:
                        json_content = content[start_idx:end_idx]

            # Method 3: Try entire content as JSON
            if json_content is None:
                json_content = content

            steps = json.loads(json_content)
            # Validate return type - must be list of dicts
            if not isinstance(steps, list):
                steps = [steps]
            # Ensure each item is a dict
            validated_steps = []
            for step in steps:
                if isinstance(step, dict):
                    validated_steps.append(step)
                else:
                    validated_steps.append({
                        'step': 'execute_task',
                        'description': str(step),
                        'provider_type': 'quality'
                    })
            return validated_steps
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
    ) -> dict:
        """
        Perform complex reasoning on a question or problem.

        Args:
            question: The question or problem to reason about
            context: Optional context information
            evidence: Optional list of evidence/facts to consider

        Returns:
            Dict with 'question', 'analysis', 'conclusion', 'confidence' keys

        Example:
            answer = executor.reason(
                "Should we use JWT or session-based auth?",
                context="Building a REST API for mobile app",
                evidence=["App needs offline support", "Multiple devices per user"]
            )
        """
        system_prompt = """You are a reasoning assistant. Analyze the question carefully, consider all evidence, and provide a well-reasoned response.

You MUST respond in this exact JSON format:
{
  "question": "the question being analyzed",
  "analysis": "detailed analysis of the considerations and factors",
  "conclusion": "your final recommendation or answer",
  "confidence": "high|medium|low"
}

Be thorough but concise. Do not repeat yourself. Provide unique insights in each section."""

        user_prompt = question
        if context:
            user_prompt = f"Context: {context}\n\nQuestion: {question}"
        if evidence:
            evidence_str = "\n".join(f"- {e}" for e in evidence)
            user_prompt += f"\n\nEvidence to consider:\n{evidence_str}"

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        response, task_record = self._llm_service.completion_sync(
            model="quality",  # Reasoning uses quality tier
            messages=messages,
            max_tokens=1500,
            temperature=0.3  # Lower temperature for structured output
        )

        # Track
        task_record['task_type'] = 'reasoning'
        self._record_task(task_record)

        # Parse JSON response
        try:
            # Handle None content from some providers
            content = (response.content or "").strip()
            # Handle markdown code blocks
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])
            result = json.loads(content)
            # Ensure result is a dict before calling .get()
            if not isinstance(result, dict):
                raise ValueError("Expected JSON object, got: " + type(result).__name__)
            # Ensure all expected keys exist
            return {
                'question': result.get('question', question),
                'analysis': result.get('analysis', ''),
                'conclusion': result.get('conclusion', ''),
                'confidence': result.get('confidence', 'unknown')
            }
        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: return raw content as analysis
            return {
                'question': question,
                'analysis': response.content,
                'conclusion': 'See analysis above',
                'confidence': 'unknown'
            }

    def synthesize(
        self,
        results: list[LLMResponse],
        synthesis_prompt: str = "Synthesize these results into a coherent summary:"
    ) -> str:
        """
        Synthesize multiple agent results into a coherent summary.

        Args:
            results: List of LLMResponse objects from various agents
            synthesis_prompt: Prompt for how to synthesize

        Returns:
            Synthesized summary string
        """
        # Build context from results
        results_text = []
        for i, result in enumerate(results, 1):
            results_text.append(f"Result {i} (from {result.provider}/{result.model}):\n{result.content}")

        combined = "\n\n---\n\n".join(results_text)

        messages = [
            {'role': 'system', 'content': 'You are a synthesis assistant. Combine multiple perspectives into a coherent whole.'},
            {'role': 'user', 'content': f"{synthesis_prompt}\n\n{combined}"}
        ]

        response, task_record = self._llm_service.completion_sync(
            model="quality",  # Synthesis uses quality tier
            messages=messages,
            max_tokens=2000,
            temperature=0.4
        )

        task_record['task_type'] = 'synthesis'
        self._record_task(task_record)

        return response.content

    def generate_context_summary(self, context_data: str) -> str:
        """
        Generate a summary of codebase context.

        Args:
            context_data: Raw context data to summarize

        Returns:
            Summary string
        """
        messages = [
            {'role': 'system', 'content': 'You are a code analyst. Provide concise technical summaries.'},
            {'role': 'user', 'content': context_data}
        ]

        response, task_record = self._llm_service.completion_sync(
            model="quality",  # Context analysis uses quality tier
            messages=messages,
            max_tokens=500,
            temperature=0.3
        )

        task_record['task_type'] = 'context_analysis'
        self._record_task(task_record)

        return response.content
