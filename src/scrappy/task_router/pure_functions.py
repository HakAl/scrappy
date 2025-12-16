"""
Pure functions for task routing logic.

This module contains pure calculation and decision functions extracted from
the TaskRouter class. These functions:
- Take inputs and return outputs
- Have no side effects (no I/O, no state mutation, no external calls)
- Are easy to test without mocking

Benefits:
- Testable without mocking
- Reusable across different contexts
- Clear separation of concerns
- Easier to reason about
"""

import json
import re
from dataclasses import replace
from typing import Optional, Union

from .classifier import ClassifiedTask, TaskType
from .protocols import ClarificationConfigProtocol


# Action indicators used for detecting action intent
ACTION_INDICATORS = [
    'create', 'write', 'make', 'add', 'build', 'generate',
    'implement', 'fix', 'update', 'modify', 'delete', 'remove'
]

# Explanation words that indicate research/learning intent
EXPLANATION_WORDS = [
    'explain', 'describe', 'tell me', 'what is', 'how does', 'how to'
]


def has_action_indicators(text: str) -> bool:
    """
    Check if text contains action indicator words.

    Args:
        text: The text to check

    Returns:
        True if text contains action words like create, write, build, etc.
    """
    if not text:
        return False

    text_lower = text.lower()
    return any(word in text_lower for word in ACTION_INDICATORS)


def has_conflicting_signals(text: str, task_type: TaskType) -> bool:
    """
    Check if text has conflicting signals for the given task type.

    Conflicting signals occur when:
    - Text has both explanation and action words
    - Task is RESEARCH but has strong action indicators
    - Text has question mark but also action verb

    Args:
        text: The user input text
        task_type: The classified task type

    Returns:
        True if there are conflicting signals
    """
    if not text:
        return False

    text_lower = text.lower()

    # Check for explanation words
    has_explanation = any(word in text_lower for word in EXPLANATION_WORDS)

    # Check for action words
    has_action = has_action_indicators(text)

    # Conflicting signals: has BOTH explanation AND action keywords
    if has_explanation and has_action:
        return True

    # If classified as RESEARCH but has strong action indicators
    if task_type == TaskType.RESEARCH:
        # Strong action verbs that suggest code generation
        strong_action_verbs = ['create', 'write', 'make', 'add', 'build', 'generate', 'implement']
        has_strong_action = any(
            f' {verb} ' in f' {text_lower} ' or text_lower.startswith(verb)
            for verb in strong_action_verbs
        )
        if has_strong_action:
            return True

    # Question mark with action verb
    has_question = '?' in text
    if has_question and has_action:
        return True

    return False


def should_escalate_confidence(task: ClassifiedTask, threshold: float = 0.7) -> bool:
    """
    Determine if a task should be escalated based on confidence and indicators.

    Escalation occurs when:
    - Task is RESEARCH type
    - Confidence is below threshold
    - Task has action indicators

    Args:
        task: The classified task
        threshold: Confidence threshold (default 0.7)

    Returns:
        True if task should be escalated to CODE_GENERATION
    """
    # Only escalate RESEARCH tasks
    if task.task_type != TaskType.RESEARCH:
        return False

    # Check confidence
    if task.confidence >= threshold:
        return False

    # Check for action indicators
    if not has_action_indicators(task.original_input):
        return False

    return True


def create_escalated_task(task: ClassifiedTask) -> ClassifiedTask:
    """
    Create a new task escalated to CODE_GENERATION.

    This is a pure transformation that creates a new ClassifiedTask
    with updated type and reasoning, preserving other fields.

    Args:
        task: The original task to escalate

    Returns:
        New ClassifiedTask with type=CODE_GENERATION and updated reasoning
    """
    original_type = task.task_type.value
    new_reasoning = (
        f"Escalated from {original_type} due to low confidence "
        f"({task.confidence:.2f}) with action indicators"
    )

    return replace(
        task,
        task_type=TaskType.CODE_GENERATION,
        reasoning=new_reasoning
    )


def needs_clarification(
    task: ClassifiedTask,
    config: Union[ClarificationConfigProtocol, float],
) -> bool:
    """
    Determine if a task needs user clarification due to ambiguity.

    Returns True when:
    - Confidence is below confidence_threshold
    - Confidence is in medium range AND has conflicting signals (rule-based only)

    Returns False when:
    - Confidence is at or above high_confidence_bypass (trust the classifier)
    - LLM classification was used (trust LLM over keyword matching)

    Args:
        task: The classified task
        config: ClarificationConfigProtocol with threshold values, or
                a float for backwards compatibility (treated as confidence_threshold
                with high_confidence_bypass=0.9)

    Returns:
        True if task needs user clarification
    """
    # Backwards compatibility: accept float as confidence_threshold
    if isinstance(config, float):
        confidence_threshold = config
        high_confidence_bypass = 0.9
    else:
        confidence_threshold = config.confidence_threshold
        high_confidence_bypass = config.high_confidence_bypass

    # Low confidence always needs clarification
    if task.confidence < confidence_threshold:
        return True

    # High confidence means classifier is sure - trust it completely
    # Skip conflicting signal checks for high confidence classifications
    if task.confidence >= high_confidence_bypass:
        return False

    # If LLM was used for classification, trust it over keyword matching
    # LLM already considered context and semantics
    if "LLM semantic classification" in task.reasoning:
        return False

    # Medium confidence range: check for conflicting signals
    if has_conflicting_signals(task.original_input, task.task_type):
        return True

    return False


def determine_execution_action(
    task_type: TaskType,
    auto_confirm: bool,
    command: Optional[str],
    is_safe: bool
) -> str:
    """
    Determine what action to take for task execution.

    Args:
        task_type: The type of task
        auto_confirm: Whether to auto-confirm direct commands
        command: The command string (for DIRECT_COMMAND)
        is_safe: Whether the command is safe to execute

    Returns:
        "execute" - Execute without confirmation
        "confirm" - Ask for user confirmation
        "block" - Block execution
    """
    # Auto-execute safe task types
    if task_type == TaskType.CONVERSATION:
        return "execute"

    if task_type == TaskType.RESEARCH:
        return "execute"

    # Code generation has its own approval loop
    if task_type == TaskType.CODE_GENERATION:
        return "execute"

    # Direct commands need special handling
    if task_type == TaskType.DIRECT_COMMAND:
        # Block unsafe commands
        if not is_safe:
            return "block"

        # Auto-confirm if enabled
        if auto_confirm:
            return "execute"

        # Otherwise need confirmation
        return "confirm"

    # Default to execute for unknown types
    return "execute"


def parse_llm_classification_response(response_text: str) -> Optional[dict]:
    """
    Parse LLM classification response JSON.

    Extracts task_type, confidence, and reasoning from LLM response.
    Handles JSON wrapped in markdown code blocks.

    Args:
        response_text: The raw response text from LLM

    Returns:
        Dictionary with task_type, confidence, reasoning or None if parsing fails
    """
    if not response_text:
        return None

    text = response_text.strip()

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    # Try to find JSON object in text
    json_start = text.find('{')
    json_end = text.rfind('}')
    if json_start != -1 and json_end != -1:
        text = text[json_start:json_end + 1]

    try:
        result = json.loads(text)

        # Validate required fields
        if 'task_type' not in result:
            return None
        if 'confidence' not in result:
            return None
        if 'reasoning' not in result:
            return None

        # Normalize task_type to uppercase
        result['task_type'] = result['task_type'].upper()

        return result

    except json.JSONDecodeError:
        return None


def build_classification_metadata(
    task: ClassifiedTask,
    provider_name: Optional[str],
    model_name: Optional[str]
) -> dict:
    """
    Build metadata dictionary for classification result.

    Args:
        task: The classified task
        provider_name: Resolved provider name
        model_name: Resolved model name

    Returns:
        Dictionary with classification metadata
    """
    return {
        "type": task.task_type.value,
        "confidence": task.confidence,
        "complexity": task.complexity_score,
        "reasoning": task.reasoning,
        "suggested_provider": task.suggested_provider,
        "override_provider": task.override_provider,
        "resolved_provider": provider_name,
        "resolved_model": model_name,
        "used_llm_classification": "LLM semantic classification" in task.reasoning
    }
