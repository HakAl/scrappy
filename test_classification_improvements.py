#!/usr/bin/env python3
"""
Test script for classification improvements:
1. Pattern expansion - catches more file creation patterns
2. Confidence escalation - upgrades low-confidence tasks
3. Intent clarification - asks user when ambiguous
"""

import sys
sys.path.insert(0, '.')

from src.task_router.classifier import TaskClassifier
from src.task_router.router import TaskRouter

def test_pattern_expansion():
    """Test that new patterns catch file creation correctly."""
    print("=" * 60)
    print("TEST 1: Pattern Expansion")
    print("=" * 60)

    classifier = TaskClassifier()

    tests = [
        ("please create requirements.txt for the python dependencies", "code_generation"),
        ("create requirements.txt", "code_generation"),
        ("generate config.json", "code_generation"),
        ("write a README.md file", "code_generation"),
        ("what is requirements.txt", "research"),  # Should stay research
    ]

    all_passed = True
    for input_text, expected_type in tests:
        result = classifier.classify(input_text)
        passed = result.task_type.value == expected_type
        status = "PASS" if passed else "FAIL"

        print(f"[{status}] '{input_text[:50]}...'")
        print(f"   Expected: {expected_type}, Got: {result.task_type.value}")
        print(f"   Confidence: {result.confidence:.2f}, Patterns: {result.matched_patterns}")

        if not passed:
            all_passed = False
        print()

    return all_passed


def test_confidence_escalation():
    """Test that low-confidence tasks get escalated."""
    print("=" * 60)
    print("TEST 2: Confidence Escalation")
    print("=" * 60)

    # Create a router (without orchestrator for this test)
    router = TaskRouter(orchestrator=None, verbose=False)

    # Create a low-confidence research task with action words
    from src.task_router.classifier import ClassifiedTask, TaskType

    task = ClassifiedTask(
        original_input="create something for me",
        task_type=TaskType.RESEARCH,
        confidence=0.5,  # Low confidence
        reasoning="No specific patterns matched, defaulting to research"
    )

    print(f"Before escalation:")
    print(f"  Type: {task.task_type.value}")
    print(f"  Confidence: {task.confidence:.2f}")

    escalated = router._apply_confidence_escalation(task)

    print(f"\nAfter escalation:")
    print(f"  Type: {escalated.task_type.value}")
    print(f"  Reasoning: {escalated.reasoning}")

    passed = escalated.task_type == TaskType.CODE_GENERATION
    status = "PASS" if passed else "FAIL"
    print(f"\n[{status}] Task was escalated from RESEARCH to CODE_GENERATION")

    return passed


def test_intent_clarification_detection():
    """Test that ambiguous tasks are detected for clarification."""
    print("=" * 60)
    print("TEST 3: Intent Clarification Detection")
    print("=" * 60)

    router = TaskRouter(orchestrator=None, verbose=False)
    classifier = TaskClassifier()

    # Test cases: (input, should_need_clarification)
    tests = [
        ("explain how to create requirements.txt", True),  # Conflicting: explain + create
        ("create requirements.txt", False),  # Clear action
        ("what is requirements.txt", False),  # Clear research
        ("can you create a file?", True),  # Question + action
        ("tell me how to add logging", True),  # Conflicting: tell me + add
        ("add logging to main.py", False),  # Clear action
    ]

    all_passed = True
    for input_text, expected_clarify in tests:
        task = classifier.classify(input_text)
        needs_clarify = router._needs_intent_clarification(task)
        passed = needs_clarify == expected_clarify
        status = "PASS" if passed else "FAIL"

        print(f"[{status}] '{input_text}'")
        print(f"   Type: {task.task_type.value}, Confidence: {task.confidence:.2f}")
        print(f"   Needs clarification: {needs_clarify} (expected: {expected_clarify})")

        if not passed:
            all_passed = False
        print()

    return all_passed


def main():
    print("\n" + "=" * 60)
    print("TESTING CLASSIFICATION IMPROVEMENTS")
    print("=" * 60 + "\n")

    results = []

    results.append(("Pattern Expansion", test_pattern_expansion()))
    results.append(("Confidence Escalation", test_confidence_escalation()))
    results.append(("Intent Clarification Detection", test_intent_clarification_detection()))

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'All tests passed!' if all_passed else 'Some tests failed'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
