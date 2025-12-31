# Plan: LLM-First Classification System

**Status**: SUPERSEDED
**Superseded By**: classification-semantic-router.md
**Reason**: Semantic Router approach is faster (20-50ms vs 2000ms), free, offline, and uses existing stack.

---

## User Feedback

We have a **fantastic stack**. lancedb, fastembed, BGE -- Everything you need to build a **Semantic Router**.

This approach is better than the "LLM-First" plan because:
1.  **Latency**: It runs in **~20-50ms** (vs 2000ms+ for an LLM).
2.  **Privacy/Offline**: No data leaves your machine.
3.  **Cost**: Free.
4.  **Reliability**: It's deterministic.

### The Concept: K-Nearest Neighbors (KNN)
We aren't asking a model to "think." We are simply calculating geometry.
1.  We place "canonical examples" (anchors) in vector space.
2.  We place the `user_input` in that same space.
3.  We look at who the `user_input` is standing next to.

If the user says "Help me build an API," and that vector lands right next to "Write a python script" (which is labeled `CODE_GENERATION`), then the user wants `CODE_GENERATION`.

---

### The Implementation
Here is how you implement `SemanticClassifier` using `lancedb` + `fastembed` with `bge-small`.

#### 1. Define Your "Anchors" (The Training Data)
You need a list of clear examples for each intent.

```python
# src/scrappy/task_router/semantic_data.py

ROUTER_EXAMPLES = [
    # CODE_GENERATION Examples
    {"text": "write a python script", "label": "CODE_GENERATION"},
    {"text": "create a node.js server", "label": "CODE_GENERATION"},
    {"text": "debug this error", "label": "CODE_GENERATION"},
    {"text": "refactor this function", "label": "CODE_GENERATION"},
    {"text": "add a unit test", "label": "CODE_GENERATION"},
    
    # CONVERSATION Examples
    {"text": "hi there", "label": "CONVERSATION"},
    {"text": "who are you?", "label": "CONVERSATION"},
    {"text": "how does this work?", "label": "CONVERSATION"},
    {"text": "thanks", "label": "CONVERSATION"},
    
    # RESEARCH Examples
    {"text": "search the web for react patterns", "label": "RESEARCH"},
    {"text": "who is the ceo of google", "label": "RESEARCH"},
    {"text": "find documentation for lancedb", "label": "RESEARCH"},
]
```

#### 2. Build the Classifier Class
This replaces your Regex or LLM logic. It initializes the DB once, then queries it.


### Integration into your Architecture

You modify your `Proposed Architecture` to use this `SemanticRouter` first.


### Why this works:
1.  **FastEmbed** runs quantized models. BGE-Small is tiny (~130MB) and loads instantly.
2.  **LanceDB** is built for this. It doesn't need a separate server process (unlike Postgres/pgvector or Qdrant server). It's just a file on disk.
3.  **BGE-Small** is "Dense". It understands that "node" and "js" and "server" are conceptually close to "coding", even if the user types "make me a backend in javascript".

### Action Items
2.  **Create** `semantic_data.py` with about 10-15 examples per category.
3.  **Implement** the class above.
4.  **Wire it up**: This replaces the complexity of the "LLM-First" plan with a "Vector-First" plan, which is technically superior for this specific problem.

---


**Original Status**: Draft - Ready for Review
**Author**: Planning Peter
**Date**: 2024-12-30
**Related Bead**: scrappy-w5yn
**Note**: See classification-semantic-router.md for the approved approach

---

## Problem Statement

The classification system has reliability and UX issues:

1. **Regex has gaps**: "add a node.js server" gets 50% confidence instead of high CODE_GENERATION
2. **Ugly clarification UX**: When uncertain, shows numbered menu that interrupts chat flow
3. **User feedback**: "classification doesn't really work" and "always prompts"

## Current Architecture

```
User Input
    |
    v
[Regex Classifier] -----> Classification (with confidence)
    |
    v
[Confidence < 0.7?] --yes--> [LLM Fallback] ---> Updated Classification
    |                              |
    no                             v
    |                    [Still uncertain?] --yes--> [InteractiveClarifier]
    v                              |                    (ugly numbered menu)
    |                              no
    v                              |
[Execute Strategy] <---------------+
```

### Key Files

| File | Purpose |
|------|---------|
| `src/scrappy/task_router/classifier.py` | Regex-based TaskClassifier with pattern strategies |
| `src/scrappy/task_router/router.py` | TaskRouter with `_classify_with_llm()` fallback |
| `src/scrappy/task_router/intent_clarifier.py` | InteractiveClarifier (the ugly UX) |
| `src/scrappy/task_router/pure_functions.py` | Pure functions for escalation logic |
| `src/scrappy/task_router/config.py` | ClarificationConfig thresholds |
| `src/scrappy/llm/models.py` | TaskClassification Pydantic model for Instructor |

### Current Flow (router.py lines 367-412)

1. Regex classification via `self.classifier.classify()`
2. Confidence escalation (low confidence + action indicators -> CODE_GENERATION)
3. LLM fallback if `confidence < 0.7` and `use_llm_classification=True`
4. Intent clarification if `clarify_on_low_confidence=True` and still uncertain
5. Resolve provider and execute

---

## Proposed Architecture

```
User Input
    |
    v
[Orchestrator available?]
    |
   yes                              no
    |                                |
    v                                v
[LLM Classifier] ----------> [Regex Classifier] (fallback)
    |                                |
    v                                v
[Confidence >= 0.5?]         [Auto-escalate if uncertain]
    |                                |
   yes                              |
    |                                |
    v                                v
[Execute Strategy] <-----------------+
```

**Key changes:**
- LLM is primary when available
- Regex is fallback for offline/errors
- No user prompts ever
- Lower confidence threshold (0.5 instead of 0.7) since LLM is more reliable
- Auto-escalate to CODE_GENERATION when uncertain (safer default)

---

## Implementation Tasks

### Task 1: Disable Clarification by Default

**File**: `src/scrappy/task_router/router.py`
**Effort**: Small
**Risk**: Low

Change line 145:
```python
# Before
self.clarify_on_low_confidence = True

# After
self.clarify_on_low_confidence = False
```

Add comment explaining rationale:
```python
# Intent clarification settings
# Disabled by default: Trust LLM classification + auto-escalation instead
# of interrupting user with ugly numbered menu prompts
self.clarify_on_low_confidence = False
```

### Task 2: Implement LLM-First Classification

**File**: `src/scrappy/task_router/router.py`
**Effort**: Medium
**Risk**: Medium

#### 2a. Add new method `_classify_llm_first()`

```python
def _classify_llm_first(self, user_input: str) -> ClassifiedTask:
    """
    Classify using LLM as primary, regex as fallback.

    Called when orchestrator is available. Falls back to regex
    classification if LLM fails or times out.

    Args:
        user_input: Raw user input string

    Returns:
        ClassifiedTask with classification result
    """
    # Try LLM first
    if self.orchestrator and self.use_llm_classification:
        try:
            llm_result = self._classify_with_llm_direct(user_input)
            if llm_result and llm_result.confidence >= 0.5:
                return llm_result
        except Exception as e:
            if self.verbose:
                self.output_handler.log_info(f"LLM classification failed, using regex: {e}")

    # Fallback to regex
    return self.classifier.classify(user_input)
```

#### 2b. Add `_classify_with_llm_direct()` method

Similar to existing `_classify_with_llm()` but:
- Takes raw `user_input` string instead of `ClassifiedTask`
- Adds 2-second timeout
- Returns `ClassifiedTask` or `None` on failure

```python
def _classify_with_llm_direct(self, user_input: str) -> Optional[ClassifiedTask]:
    """
    Direct LLM classification from user input.

    Returns None on failure (caller should fallback to regex).
    """
    system_prompt = """You are a task classifier..."""  # existing prompt
    user_prompt = f'Classify this user request:\n"{user_input}"'

    try:
        result = self.orchestrator.delegate_structured(
            provider_name="fast",
            prompt=user_prompt,
            response_model=LLMTaskClassification,
            system_prompt=system_prompt,
            max_tokens=200,
            temperature=0.1,
            timeout=2000,  # 2 second timeout
        )

        # Map LLM type to router type
        new_type = self._llm_to_router_type.get(result.task_type)
        if new_type is None:
            return None

        return ClassifiedTask(
            original_input=user_input,
            task_type=new_type,
            confidence=result.confidence,
            reasoning=f"LLM classification: {result.reasoning}",
        )
    except Exception:
        return None
```

#### 2c. Update `route()` method

Change classification section (around line 390) to use LLM-first:

```python
# Before
classified = self.classifier.classify(user_input)
classified = self._apply_confidence_escalation(classified)
if self.use_llm_classification and classified.confidence < self.confidence_threshold:
    classified = self._classify_with_llm(classified)

# After
classified = self._classify_llm_first(user_input)
classified = self._apply_confidence_escalation(classified)
```

#### 2d. Update `_prepare_for_execution()` similarly

Ensure both paths use the same LLM-first flow.

### Task 3: Add Auto-Escalation for Uncertain Results

**File**: `src/scrappy/task_router/pure_functions.py`
**Effort**: Small
**Risk**: Low

Add function:
```python
def auto_escalate_uncertain(task: ClassifiedTask, threshold: float = 0.5) -> ClassifiedTask:
    """
    Auto-escalate uncertain classifications to CODE_GENERATION.

    When classifier confidence is below threshold and task type is
    RESEARCH (ambiguous), escalate to CODE_GENERATION as safer default.

    Args:
        task: The classified task
        threshold: Confidence threshold (default 0.5)

    Returns:
        Task, potentially escalated to CODE_GENERATION
    """
    if task.confidence < threshold and task.task_type == TaskType.RESEARCH:
        return replace(
            task,
            task_type=TaskType.CODE_GENERATION,
            reasoning=f"Auto-escalated from RESEARCH due to low confidence ({task.confidence:.2f})"
        )
    return task
```

### Task 4: Update Tests

**File**: `tests/task_router/test_task_router.py`
**Effort**: Medium
**Risk**: Low

#### New tests to add:

```python
class TestLLMFirstClassification:
    def test_llm_first_when_orchestrator_available(self):
        """LLM is called before regex when orchestrator exists."""

    def test_regex_fallback_when_no_orchestrator(self):
        """Regex is used when orchestrator is None."""

    def test_regex_fallback_on_llm_exception(self):
        """Falls back to regex if LLM call throws."""

    def test_regex_fallback_on_llm_timeout(self):
        """Falls back to regex if LLM times out."""

    def test_conversation_not_escalated(self):
        """Greetings like 'hi' stay as CONVERSATION."""

    def test_auto_escalate_only_from_research(self):
        """Only RESEARCH with low confidence escalates to CODE_GENERATION."""

    def test_no_clarification_prompt_by_default(self):
        """Verify clarify_on_low_confidence defaults to False."""
```

#### Existing tests to update:

- Tests that expect regex-first behavior may need adjustment
- Tests that mock `_classify_with_llm` need to account for new method

### Task 5: Lower LLM Acceptance Threshold

**File**: `src/scrappy/task_router/router.py`
**Effort**: Small
**Risk**: Low

In `_classify_with_llm()` (existing method, kept for backwards compatibility):
```python
# Before
if result.confidence >= 0.7:

# After
if result.confidence >= 0.5:
```

Rationale: LLM semantic understanding is more reliable than regex pattern matching, so we can trust lower confidence scores.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| LLM unavailable (offline) | Regex fallback always available |
| LLM timeout/hang | 2-second timeout with regex fallback |
| LLM returns invalid type | Type mapping with None check, fallback to regex |
| Greetings escalated incorrectly | Only escalate from RESEARCH type |
| Breaking existing behavior | Comprehensive test coverage |
| Both route() paths diverge | Update both consistently |

---

## Verification Steps

### Automated

1. All existing tests pass
2. New tests pass
3. Coverage maintained or improved

### Manual

1. Start scrappy
2. Enter: "add a node.js server"
3. Verify: Routes to CODE_GENERATION without prompt
4. Enter: "hi"
5. Verify: Routes to CONVERSATION
6. Disconnect network, enter: "create a python file"
7. Verify: Still routes correctly (regex fallback)

---

## Open Questions

1. **Caching**: Should we cache LLM classifications for repeated queries? (Defer for now)
2. **Metrics**: Should we log classification accuracy for future tuning? (Defer for now)
3. **Timeout value**: Is 2 seconds appropriate? May need tuning.

---

## Approval Checklist

- [ ] Problem statement accurate
- [ ] Architecture changes clear
- [ ] All tasks well-defined
- [ ] Risks addressed
- [ ] Tests specified
- [ ] Ready for implementation
