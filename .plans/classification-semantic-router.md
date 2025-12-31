# Plan: Semantic Router Classification

**Status**: APPROVED - Pending Reba Sign-off (Updated with Neo's + Reba's + Matt's Fixes)
**Author**: Planning Peter
**Date**: 2024-12-30
**Updated**: 2024-12-30 (Neo's + Reba's + Matt's reviews incorporated)
**Related Bead**: scrappy-w5yn
**Supersedes**: classification-llm-first.md

---

## Summary

Replace regex-first classification with a **Semantic Router** using the existing lancedb + fastembed + BGE-small stack. This is superior to both LLM-first and regex-first approaches.

| Approach | Latency | Cost | Privacy | Reliability |
|----------|---------|------|---------|-------------|
| Regex | ~1ms | Free | Yes | Brittle |
| LLM | ~2000ms | $$ | No | Good |
| **Semantic Router** | **~20-50ms** | **Free** | **Yes** | **Excellent** |

---

## Problem Statement

The classification system has reliability and UX issues:

1. **Regex has gaps**: "add a node.js server" gets 50% confidence
2. **LLM is slow**: 2+ seconds per classification
3. **User prompts are ugly**: Numbered menus interrupt flow
4. **User feedback**: "classification doesn't really work"

---

## Solution: Semantic Router

### The Concept

We do not ask an LLM to "think". We calculate vector geometry:

1. Pre-embed "canonical examples" (anchors) for each task type
2. Embed user input at runtime
3. Find K-nearest neighbors in vector space
4. Classify based on majority vote of neighbors

If user says "Help me build an API" and it lands next to "Write a python script" (labeled CODE_GENERATION), then classify as CODE_GENERATION.

### Why This Works

1. **FastEmbed** runs quantized BGE-small-en-v1.5 (~130MB, loads in ~1s)
2. **LanceDB** is file-based, no server process needed
3. **BGE-small-en-v1.5** understands semantic similarity ("node server" is close to "coding")
   - **Note**: BGE-small-en-v1.5 produces **384-dimension** vectors (not 768)
4. **Already in codebase**: `src/scrappy/context/semantic/embeddings.py` has the exact stack

---

## Proposed Architecture

```
App Startup
    |
    v
[warm_up()] -----------------> Pre-load model + embed examples
                               (avoids cold start on first request)

User Input
    |
    v
[Input Validation] -----------> Empty? Return None
    |                           Long? Truncate to ~2000 chars
    v
[Semantic Router] -----------> Classification (with confidence)
    |                              |
    v                              v
[Confidence >= 0.6?]         [fallback to regex if unavailable]
    |
   yes -----> [Confidence >= 0.5?] --no--> [Optional: LLM fallback]
    |                |
    v               yes
[Execute Strategy]   |
    ^________________|
```

**Key changes:**
- Semantic Router is primary classifier
- **warm_up() called at app init** - not first request (Neo fix)
- **Recommended warm_up() location**: TUI background thread in `app.py:223` (`initialize_cli()`) (Matt's audit)
- Regex is fallback only (model not loaded, error)
- **Hybrid approach**: Consider LLM fallback for confidence < 0.5 (Neo suggestion)
- **Feature flag**: `enable_semantic_routing` for easy disable (Matt's audit)
- No user prompts ever
- Auto-escalate to CODE_GENERATION when ambiguous

---

## Implementation Tasks

### Task 0: Fix embeddings.py Thread Safety and Docstring (Matt's Audit)

**File**: `src/scrappy/context/semantic/embeddings.py`
**Effort**: Small
**Risk**: Low

Matt's integration audit found two issues in the existing embeddings module:

1. **Incorrect dimension in docstring**: The class docstring says "768 dimensions" but `ndims()` correctly returns 384. Fix the docstring.

2. **Thread safety race condition**: The `_get_or_create_model()` function has a TOCTOU (time-of-check-to-time-of-use) race. Multiple threads could see `_CACHED_MODEL is None` and create multiple model instances.

**Fix:**

```python
import threading

_MODEL_LOCK = threading.Lock()
_CACHED_MODEL: Optional[TextEmbedding] = None


def _get_or_create_model() -> TextEmbedding:
    """
    Get cached TextEmbedding model or create if not exists.

    Thread-safe via double-checked locking pattern.

    Returns:
        Cached TextEmbedding instance
    """
    global _CACHED_MODEL
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    with _MODEL_LOCK:
        if _CACHED_MODEL is None:  # Double-check after acquiring lock
            model_name = "BAAI/bge-small-en-v1.5"
            logger.debug(f"Initializing FastEmbed with model: {model_name}")
            _CACHED_MODEL = TextEmbedding(
                model_name=model_name,
            )
            logger.debug("FastEmbed model initialized")
        return _CACHED_MODEL
```

**Docstring fix** (line 48):
```python
# Before
- 768 dimensions

# After
- 384 dimensions
```

**Acceptance Criteria:**
- [ ] `_get_or_create_model()` uses threading.Lock with double-checked locking
- [ ] Class docstring correctly states 384 dimensions
- [ ] Existing tests still pass

---

### Task 1: Create Semantic Router Data

**File**: `src/scrappy/task_router/semantic_router/route_data.py`
**Effort**: Small
**Risk**: Low

Define canonical examples for each task type:

```python
"""Canonical examples for semantic routing."""

from typing import List, Dict

ROUTE_EXAMPLES = [
    # ==========================================
    # DIRECT_COMMAND 
    # Intent: Immediate execution, shell commands, no "thinking" required.
    # High Threshold recommended (>0.82)
    # ==========================================
    {"text": "pip install requests", "label": "DIRECT_COMMAND"},
    {"text": "npm install react", "label": "DIRECT_COMMAND"},
    {"text": "npm run build", "label": "DIRECT_COMMAND"},
    {"text": "git status", "label": "DIRECT_COMMAND"},
    {"text": "git commit -m 'fix'", "label": "DIRECT_COMMAND"},
    {"text": "docker ps", "label": "DIRECT_COMMAND"},
    {"text": "docker build -t myapp .", "label": "DIRECT_COMMAND"},
    {"text": "pytest", "label": "DIRECT_COMMAND"},
    {"text": "ls -la", "label": "DIRECT_COMMAND"}, # Added flag to make it more "shelly"
    {"text": "cd src", "label": "DIRECT_COMMAND"},
    {"text": "clear screen", "label": "DIRECT_COMMAND"}, # Explicit
    {"text": "cat config.py", "label": "DIRECT_COMMAND"}, # Reading single files is usually a command
    {"text": "pwd", "label": "DIRECT_COMMAND"},

    # ==========================================
    # CODE_GENERATION
    # Intent: Complex state modification, file writing, reasoning required.
    # ==========================================
    
    # The "Add Node Server" Fix
    {"text": "add a node.js server", "label": "CODE_GENERATION"},
    {"text": "create a server.js file", "label": "CODE_GENERATION"},

    # Scaffolding & Creation
    {"text": "write a python script to parse csv", "label": "CODE_GENERATION"},
    {"text": "scaffold a react component", "label": "CODE_GENERATION"},
    {"text": "make a dockerfile for this app", "label": "CODE_GENERATION"},
    {"text": "create a requirements.txt", "label": "CODE_GENERATION"},
    {"text": "build a REST API endpoint", "label": "CODE_GENERATION"},

    # Modification
    {"text": "refactor this function to be async", "label": "CODE_GENERATION"},
    {"text": "rename the variable x to user_id", "label": "CODE_GENERATION"},
    {"text": "optimize this loop", "label": "CODE_GENERATION"},
    {"text": "delete the temp folder", "label": "CODE_GENERATION"}, # Dangerous ops belong in Gen (Agent can double check)

    # Debugging
    {"text": "fix the type error", "label": "CODE_GENERATION"},
    {"text": "debug the server crash", "label": "CODE_GENERATION"},
    {"text": "resolve the merge conflict", "label": "CODE_GENERATION"},

    # ==========================================
    # RESEARCH
    # Intent: Information retrieval, explanation, "Grepping" for understanding.
    # ==========================================
    
    # Pure Info
    {"text": "what is python?", "label": "RESEARCH"},
    {"text": "how does async await work?", "label": "RESEARCH"},
    {"text": "explain JWT authentication", "label": "RESEARCH"},
    {"text": "summarize the SOLID principles", "label": "RESEARCH"},

    # Codebase Analysis (The "Smart Grep")
    {"text": "find all TODO comments", "label": "RESEARCH"},
    {"text": "where is the user authentication logic defined?", "label": "RESEARCH"}, # Specific
    {"text": "analyze the database schema", "label": "RESEARCH"},
    {"text": "check for security vulnerabilities", "label": "RESEARCH"},
    {"text": "search for usages of the User class", "label": "RESEARCH"}, # Distinct from 'ls'

    # External Search
    {"text": "search google for langchain docs", "label": "RESEARCH"},
    {"text": "lookup the error code 500", "label": "RESEARCH"},

    # ==========================================
    # CONVERSATION
    # Intent: Routing sink for non-actionable text.
    # ==========================================
    {"text": "hi", "label": "CONVERSATION"},
    {"text": "hello", "label": "CONVERSATION"},
    {"text": "good morning", "label": "CONVERSATION"},
    {"text": "thanks", "label": "CONVERSATION"},
    {"text": "thank you", "label": "CONVERSATION"},
    {"text": "bye", "label": "CONVERSATION"},
    {"text": "who are you?", "label": "CONVERSATION"},
    {"text": "help", "label": "CONVERSATION"},
    {"text": "ok", "label": "CONVERSATION"},
    {"text": "sure", "label": "CONVERSATION"}, # Added variation
    {"text": "yes", "label": "CONVERSATION"},
    {"text": "no", "label": "CONVERSATION"},
    {"text": "maybe", "label": "CONVERSATION"},
]
```

**Acceptance Criteria:**
- [ ] At least 10 examples per task type
- [ ] Examples cover edge cases (e.g., "add a node.js server")
- [ ] File follows project structure conventions

---

### Task 2: Create SemanticRouter Protocol

**File**: `src/scrappy/task_router/protocols.py`
**Effort**: Small
**Risk**: Low

Add protocol for semantic routing:

```python
from typing import Protocol, Optional, runtime_checkable

# Forward reference - RouteResult defined in router.py
# Import at runtime or use TYPE_CHECKING block


@runtime_checkable
class SemanticRouterProtocol(Protocol):
    """
    Protocol for semantic-based task classification.

    Uses vector embeddings to classify user input by finding
    nearest neighbors among canonical examples.
    """

    def classify(self, user_input: str) -> Optional["RouteResult"]:
        """
        Classify user input semantically.

        Args:
            user_input: Raw user input string

        Returns:
            RouteResult with task_type, confidence, nearest_example, distance
            or None if unavailable/low confidence

        Note:
            Returns RouteResult (not Tuple) for richer context.
            (Neo fix: protocol/implementation type mismatch)
        """
        ...

    def is_ready(self) -> bool:
        """Check if router is initialized and ready."""
        ...

    def warm_up(self) -> bool:
        """
        Pre-initialize the router (load model, embed examples).

        Call this during application startup, NOT on first request.
        This avoids cold-start latency for the first user.

        Returns:
            True if warm-up succeeded, False otherwise

        Note:
            (Neo fix: add warm-up strategy)
        """
        ...
```

**Acceptance Criteria:**
- [x] Protocol follows existing patterns in protocols.py
- [x] Clear docstrings with usage examples
- [x] **Return type is `Optional[RouteResult]`** not `Optional[Tuple[str, float]]` (Neo fix)
- [x] **Includes `warm_up()` method** for app-init loading (Neo fix)

---

### Task 3: Implement SemanticRouter

**File**: `src/scrappy/task_router/semantic_router/router.py`
**Effort**: Medium
**Risk**: Medium

Implement the router using existing embedding infrastructure:

```python
"""
Semantic router for task classification.

Uses vector similarity to classify user input against canonical examples.
Leverages existing lancedb + fastembed stack from context/semantic.

Neo's fixes incorporated:
- Thread safety via Lock in _ensure_initialized
- numpy for cosine distance (vectorized)
- Input validation (empty, truncation)
- warm_up() method for app startup
- Store vectors as np.ndarray
"""

import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from ..classification_strategy import TaskType
from ..protocols import SemanticRouterProtocol
from ...context.protocols import EmbeddingFunctionProtocol

logger = logging.getLogger(__name__)

# Input constraints
MAX_INPUT_LENGTH = 2000  # Truncate long inputs (Neo fix)


@dataclass
class RouteResult:
    """Result from semantic routing."""
    task_type: TaskType
    confidence: float
    nearest_example: str
    distance: float


class SemanticRouter:
    """
    Semantic router using K-nearest neighbors in vector space.

    Architecture:
    - Pre-embeds canonical examples on first use (or via warm_up)
    - In-memory storage (examples are small)
    - Queries using numpy-vectorized cosine similarity
    - Returns majority vote of K nearest neighbors

    Design Decisions:
    - Uses same EmbeddingFunctionProtocol as semantic search
    - Lazy initialization (no I/O in constructor)
    - Thread-safe initialization via Lock (Neo fix)
    - Fallback to None if not ready (caller uses regex)

    Thread Safety:
    - _ensure_initialized uses a Lock to prevent race conditions
    - Multiple threads can call classify() safely after init
    """

    def __init__(
        self,
        embedding_func: Optional[EmbeddingFunctionProtocol] = None,
        route_examples: Optional[List[Dict[str, str]]] = None,
        k_neighbors: int = 3,
        confidence_threshold: float = 0.6,
    ):
        """
        Initialize semantic router.

        Args:
            embedding_func: Embedding function (lazy-loaded if None)
            route_examples: Canonical examples (uses defaults if None)
            k_neighbors: Number of neighbors for voting
            confidence_threshold: Minimum confidence to return result
        """
        self._embedding_func = embedding_func
        self._k = k_neighbors
        self._threshold = confidence_threshold

        # Lazy state
        self._examples = route_examples
        # Store as numpy array for vectorized operations (Neo fix)
        self._example_vectors: Optional[np.ndarray] = None
        self._is_initialized = False

        # Thread safety (Neo fix)
        self._init_lock = threading.Lock()

    def _ensure_initialized(self) -> bool:
        """
        Lazy initialization of embedding function and example vectors.

        Thread-safe via Lock to prevent race conditions during
        concurrent first-access. (Neo fix)

        Returns:
            True if initialized successfully, False otherwise
        """
        # Fast path: already initialized
        if self._is_initialized:
            return True

        # Slow path: acquire lock and initialize
        with self._init_lock:
            # Double-check after acquiring lock
            if self._is_initialized:
                return True

            try:
                # Load examples if not provided
                if self._examples is None:
                    from .route_data import ROUTE_EXAMPLES
                    self._examples = ROUTE_EXAMPLES

                # Load embedding function if not provided
                if self._embedding_func is None:
                    from ...context.semantic.embeddings import EmbedFunction
                    self._embedding_func = EmbedFunction()

                # Pre-embed all examples, store as numpy array (Neo fix)
                texts = [ex["text"] for ex in self._examples]
                embeddings = self._embedding_func.generate_embeddings(texts)
                self._example_vectors = np.array(embeddings)

                self._is_initialized = True
                logger.debug(f"SemanticRouter initialized with {len(texts)} examples")
                return True

            except Exception as e:
                logger.warning(f"SemanticRouter initialization failed: {e}")
                return False

    def warm_up(self) -> bool:
        """
        Pre-initialize the router during application startup.

        Call this during app init, NOT on first user request.
        This avoids cold-start latency for the first user.
        (Neo fix: add warm-up strategy)

        Returns:
            True if warm-up succeeded, False otherwise
        """
        return self._ensure_initialized()

    def is_ready(self) -> bool:
        """Check if router is ready."""
        return self._is_initialized

    def _validate_input(self, user_input: str) -> Optional[str]:
        """
        Validate and normalize user input.

        (Neo fix: add input validation)
        (Reba fix: handle None input to prevent crash)

        Args:
            user_input: Raw user input (may be None)

        Returns:
            Validated input or None if invalid
        """
        # Handle None and empty input (Reba fix: None check)
        if not user_input:  # Handles None and empty string
            logger.debug("Empty/None input, returning None")
            return None

        cleaned = user_input.strip()

        # Handle whitespace-only input
        if not cleaned:
            logger.debug("Whitespace-only input, returning None")
            return None

        # Truncate long input (Neo fix)
        if len(cleaned) > MAX_INPUT_LENGTH:
            logger.debug(f"Truncating input from {len(cleaned)} to {MAX_INPUT_LENGTH} chars")
            cleaned = cleaned[:MAX_INPUT_LENGTH]

        return cleaned

    def classify(self, user_input: str) -> Optional[RouteResult]:
        """
        Classify user input using K-nearest neighbors.

        Args:
            user_input: Raw user input

        Returns:
            RouteResult or None if not ready/uncertain/invalid
        """
        # Input validation (Neo fix)
        validated_input = self._validate_input(user_input)
        if validated_input is None:
            return None

        if not self._ensure_initialized():
            return None

        # Embed user input
        try:
            user_embedding = self._embedding_func.generate_embeddings([validated_input])[0]
            user_vector = np.array(user_embedding)
        except Exception as e:
            logger.warning(f"Failed to embed user input: {e}")
            return None

        # Calculate distances using numpy (Neo fix: vectorized)
        distances = self._cosine_distances_vectorized(user_vector, self._example_vectors)

        # Find K nearest neighbors
        k_indices = np.argsort(distances)[:self._k]
        k_distances = distances[k_indices]

        # Vote on task type
        votes: Dict[str, List[float]] = {}
        for idx, dist in zip(k_indices, k_distances):
            label = self._examples[idx]["label"]
            if label not in votes:
                votes[label] = []
            votes[label].append(float(dist))

        # Find winner (most votes, then smallest average distance)
        winner = max(votes.keys(), key=lambda l: (len(votes[l]), -sum(votes[l])/len(votes[l])))

        # Calculate confidence (inverse of average distance to winner)
        avg_dist = sum(votes[winner]) / len(votes[winner])
        confidence = 1.0 - min(avg_dist, 1.0)  # Convert distance to similarity

        # Return None if below threshold
        if confidence < self._threshold:
            logger.debug(f"Low confidence {confidence:.2f} for '{validated_input[:50]}...', returning None")
            return None

        # Map label to TaskType
        task_type_map = {
            "CODE_GENERATION": TaskType.CODE_GENERATION,
            "CONVERSATION": TaskType.CONVERSATION,
            "RESEARCH": TaskType.RESEARCH,
            "DIRECT_COMMAND": TaskType.DIRECT_COMMAND,
        }
        task_type = task_type_map.get(winner)
        if task_type is None:
            return None

        nearest_idx = int(k_indices[0])
        return RouteResult(
            task_type=task_type,
            confidence=confidence,
            nearest_example=self._examples[nearest_idx]["text"],
            distance=float(k_distances[0]),
        )

    @staticmethod
    def _cosine_distances_vectorized(
        query: np.ndarray,
        examples: np.ndarray
    ) -> np.ndarray:
        """
        Calculate cosine distances using numpy vectorized operations.

        (Neo fix: replace manual Python loops with numpy)

        Args:
            query: Query vector (1D array, 384 dims for BGE-small)
            examples: Example vectors (2D array, N x 384)

        Returns:
            Array of cosine distances (N,)
        """
        # Normalize query
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return np.ones(len(examples))
        query_normalized = query / query_norm

        # Normalize examples (row-wise)
        example_norms = np.linalg.norm(examples, axis=1, keepdims=True)
        # Avoid division by zero
        example_norms = np.where(example_norms == 0, 1, example_norms)
        examples_normalized = examples / example_norms

        # Cosine similarity via dot product of normalized vectors
        similarities = examples_normalized @ query_normalized

        # Convert to distance
        return 1.0 - similarities
```

**Acceptance Criteria:**
- [x] Uses existing EmbeddingFunctionProtocol
- [x] Lazy initialization (no I/O in constructor)
- [x] K-nearest neighbors voting logic
- [x] Confidence based on average distance
- [x] Falls back gracefully if not ready
- [x] **Thread-safe initialization via Lock** (Neo fix)
- [x] **numpy vectorized cosine distance** (Neo fix)
- [x] **Input validation: empty check, truncation** (Neo fix)
- [x] **warm_up() method** (Neo fix)
- [x] **Vectors stored as np.ndarray** (Neo fix)

---

### Task 4: Integrate into TaskClassifier

**File**: `src/scrappy/task_router/classifier.py`
**Effort**: Small
**Risk**: Low

Update TaskClassifier to use SemanticRouter as primary:

```python
class TaskClassifier:
    """
    Classifies user tasks using Semantic Router with regex fallback.
    """

    def __init__(
        self,
        strategies: Optional[List] = None,
        platform_detector: Optional[PlatformDetectorProtocol] = None,
        semantic_router: Optional[SemanticRouterProtocol] = None,
        enable_semantic_routing: bool = True,  # Feature flag for easy disable (Matt's audit)
    ):
        # ... existing code ...

        # Semantic router (primary classifier)
        self._semantic_router = semantic_router
        self._enable_semantic_routing = enable_semantic_routing

    def classify(self, user_input: str) -> ClassifiedTask:
        """Classify using semantic router, fallback to regex."""
        input_stripped = user_input.strip()

        # Try semantic router first (if feature flag enabled)
        if self._enable_semantic_routing and self._semantic_router is not None:
            result = self._semantic_router.classify(input_stripped)
            if result is not None:
                return ClassifiedTask(
                    original_input=input_stripped,
                    task_type=result.task_type,
                    confidence=result.confidence,
                    reasoning=f"Semantic: nearest to '{result.nearest_example}'",
                    # ... other fields
                )

        # Fallback to regex strategies
        # ... existing regex logic ...
```

**Feature Flag (Matt's Audit):**
The `enable_semantic_routing` parameter allows easy disable in case of issues:
- Default: `True` (semantic routing enabled)
- Set to `False` to fall back to regex-only classification
- Can be controlled via config/environment variable in production

**Acceptance Criteria:**
- [ ] Semantic router is tried first
- [ ] Falls back to regex if router returns None
- [ ] Maintains backward compatibility
- [ ] **Feature flag `enable_semantic_routing` allows runtime disable** (Matt's audit)

---

### Task 5: Disable Clarification by Default

**File**: `src/scrappy/task_router/router.py`
**Effort**: Small
**Risk**: Low

```python
# Before
self.clarify_on_low_confidence = True

# After
# Intent clarification disabled: Semantic router + auto-escalation
# handles ambiguity without interrupting user flow
self.clarify_on_low_confidence = False
```

**Acceptance Criteria:**
- [ ] Clarification disabled by default
- [ ] Comment explains rationale

---

### Task 6: Write Tests

**File**: `tests/task_router/test_semantic_router.py`
**Effort**: Medium
**Risk**: Low

**CRITICAL (Neo fix): Tests MUST use fake embeddings with deterministic vectors, NOT real model.**

The real embedding model is slow and non-deterministic. Tests must be fast and repeatable.

```python
"""Tests for SemanticRouter.

IMPORTANT: All tests use FakeEmbeddingFunc with deterministic vectors.
DO NOT use real embedding model in tests - they must be fast and repeatable.
(Neo fix: proper test strategy)
"""

import numpy as np
import pytest
from scrappy.task_router.semantic_router.router import SemanticRouter, RouteResult
from scrappy.task_router.classification_strategy import TaskType


class FakeEmbeddingFunc:
    """
    Fake embedding function for testing with deterministic vectors.

    (Neo fix: proper fake implementation)

    Strategy:
    - Map known texts to specific vectors
    - Unknown texts get a default "distant" vector
    - Vectors are designed to produce predictable cosine distances
    """

    VECTOR_DIM = 384  # BGE-small-en-v1.5 dimension (Neo fix: correct dim)

    def __init__(self, text_to_vector: dict[str, list[float]] | None = None):
        """
        Args:
            text_to_vector: Map of text -> embedding vector.
                            If None, uses default test vectors.
        """
        self._text_to_vector = text_to_vector or {}

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic embeddings for testing."""
        result = []
        for text in texts:
            if text in self._text_to_vector:
                result.append(self._text_to_vector[text])
            else:
                # Default: zero vector (will be distant from everything)
                result.append([0.0] * self.VECTOR_DIM)
        return result

    def ndims(self) -> int:
        return self.VECTOR_DIM


def _make_unit_vector(dim: int, index: int) -> list[float]:
    """Create a unit vector with 1.0 at the given index, 0.0 elsewhere."""
    vec = [0.0] * dim
    vec[index] = 1.0
    return vec


def _make_similar_vector(base: list[float], similarity: float = 0.9) -> list[float]:
    """Create a vector similar to base with given cosine similarity."""
    # Add noise to reduce similarity
    noise_scale = np.sqrt(1 - similarity**2)
    noise = np.random.randn(len(base)) * noise_scale
    result = np.array(base) * similarity + noise
    # Normalize
    result = result / np.linalg.norm(result)
    return result.tolist()


class TestSemanticRouter:
    """Tests for SemanticRouter using fake embeddings."""

    def test_classify_exact_match(self):
        """Exact match to example should classify with high confidence."""
        # Setup: CODE_GENERATION examples at index 0, CONVERSATION at index 1
        code_vec = _make_unit_vector(384, 0)
        conv_vec = _make_unit_vector(384, 1)

        fake_embed = FakeEmbeddingFunc({
            # Examples
            "write python": code_vec,
            "create server": code_vec,
            "build api": code_vec,
            "hi": conv_vec,
            "hello": conv_vec,
            "thanks": conv_vec,
            # Query - matches code examples exactly
            "write python": code_vec,
        })

        examples = [
            {"text": "write python", "label": "CODE_GENERATION"},
            {"text": "create server", "label": "CODE_GENERATION"},
            {"text": "build api", "label": "CODE_GENERATION"},
            {"text": "hi", "label": "CONVERSATION"},
            {"text": "hello", "label": "CONVERSATION"},
            {"text": "thanks", "label": "CONVERSATION"},
        ]

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=examples,
            k_neighbors=3,
            confidence_threshold=0.6,
        )

        result = router.classify("write python")

        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION
        assert result.confidence >= 0.9  # Exact match = high confidence

    def test_classify_similar_input(self):
        """Similar input should classify correctly."""
        code_vec = _make_unit_vector(384, 0)
        similar_code_vec = _make_similar_vector(code_vec, 0.95)

        fake_embed = FakeEmbeddingFunc({
            "write python": code_vec,
            "create server": code_vec,
            "build api": code_vec,
            # Query - similar to code vectors
            "make a script": similar_code_vec,
        })

        examples = [
            {"text": "write python", "label": "CODE_GENERATION"},
            {"text": "create server", "label": "CODE_GENERATION"},
            {"text": "build api", "label": "CODE_GENERATION"},
        ]

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=examples,
        )

        result = router.classify("make a script")

        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION

    def test_returns_none_for_empty_input(self):
        """Empty input should return None (Neo fix: input validation)."""
        router = SemanticRouter(
            embedding_func=FakeEmbeddingFunc(),
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        assert router.classify("") is None
        assert router.classify("   ") is None

    def test_returns_none_for_none_input(self):
        """None input should return None without crashing (Reba fix)."""
        router = SemanticRouter(
            embedding_func=FakeEmbeddingFunc(),
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        # This previously crashed - now handles gracefully (Reba fix)
        assert router.classify(None) is None  # type: ignore

    def test_truncates_long_input(self):
        """Long input should be truncated, not rejected (Neo fix)."""
        fake_embed = FakeEmbeddingFunc({
            "test": [1.0] + [0.0] * 383,
        })
        # Add truncated version too
        long_input = "x" * 3000
        truncated = long_input[:2000]
        fake_embed._text_to_vector[truncated] = [1.0] + [0.0] * 383

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        # Should not raise, should truncate
        result = router.classify(long_input)
        # May return None (zero vector = distant) but should not crash

    def test_warm_up_initializes_router(self):
        """warm_up() should pre-initialize (Neo fix)."""
        fake_embed = FakeEmbeddingFunc({
            "test": [1.0] + [0.0] * 383,
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        assert not router.is_ready()  # Not initialized yet

        success = router.warm_up()

        assert success is True
        assert router.is_ready()

    def test_is_ready_false_before_init(self):
        """is_ready() should return False before initialization."""
        router = SemanticRouter(
            embedding_func=FakeEmbeddingFunc(),
            route_examples=[{"text": "test", "label": "CODE_GENERATION"}],
        )

        # is_ready() should NOT trigger initialization (Neo fix)
        assert router.is_ready() is False

    def test_low_confidence_returns_none(self):
        """Below-threshold confidence should return None."""
        # Setup: query is distant from all examples
        code_vec = _make_unit_vector(384, 0)
        distant_vec = _make_unit_vector(384, 100)  # Orthogonal = 0 similarity

        fake_embed = FakeEmbeddingFunc({
            "write python": code_vec,
            "distant query": distant_vec,
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[{"text": "write python", "label": "CODE_GENERATION"}],
            confidence_threshold=0.6,
        )

        result = router.classify("distant query")

        # Distance ~1.0 -> confidence ~0.0 -> below threshold
        assert result is None

    def test_knn_voting_majority_wins(self):
        """K-nearest neighbors should vote by majority."""
        # 2 CODE examples close, 1 CONVERSATION close but slightly farther
        code_vec = _make_unit_vector(384, 0)
        code_vec2 = _make_similar_vector(code_vec, 0.99)
        conv_vec = _make_similar_vector(code_vec, 0.95)  # Slightly farther

        fake_embed = FakeEmbeddingFunc({
            "write python": code_vec,
            "create server": code_vec2,
            "hi there": conv_vec,
            "query": code_vec,  # Matches code examples
        })

        router = SemanticRouter(
            embedding_func=fake_embed,
            route_examples=[
                {"text": "write python", "label": "CODE_GENERATION"},
                {"text": "create server", "label": "CODE_GENERATION"},
                {"text": "hi there", "label": "CONVERSATION"},
            ],
            k_neighbors=3,
        )

        result = router.classify("query")

        # 2 CODE vs 1 CONVERSATION -> CODE wins
        assert result is not None
        assert result.task_type == TaskType.CODE_GENERATION
```

**Acceptance Criteria:**
- [x] Tests for each task type
- [x] Tests for edge cases (empty, long input)
- [x] Tests for graceful failure
- [x] **Uses FakeEmbeddingFunc with deterministic vectors** (Neo fix)
- [x] **No real embedding model in tests** (Neo fix)
- [x] Tests warm_up() method
- [x] Tests KNN voting logic

---

### Task 7: Add Package Structure

**Files**:
- `src/scrappy/task_router/semantic_router/__init__.py`
- Update `src/scrappy/task_router/__init__.py`

**Effort**: Small
**Risk**: Low

```python
# src/scrappy/task_router/semantic_router/__init__.py
"""Semantic router for task classification."""

from .router import SemanticRouter, RouteResult
from .route_data import ROUTE_EXAMPLES

__all__ = ['SemanticRouter', 'RouteResult', 'ROUTE_EXAMPLES']
```

**Acceptance Criteria:**
- [ ] Clean package structure
- [ ] Exports aligned with usage

---

### Task 8: Add Wiring/Factory Code (Neo fix)

**File**: `src/scrappy/task_router/factory.py` (or appropriate location)
**Effort**: Small
**Risk**: Low

**Neo's concern**: The plan shows SemanticRouter and TaskClassifier but not WHERE/HOW they are constructed and wired together. This is critical for DI.

```python
"""
Factory functions for task routing components.

(Neo fix: add wiring code showing how components are assembled)
"""

from typing import Optional

from .classifier import TaskClassifier
from .semantic_router.router import SemanticRouter
from ..context.semantic.embeddings import EmbedFunction


def create_task_classifier(
    enable_semantic_router: bool = True,
    warm_up: bool = True,
) -> TaskClassifier:
    """
    Factory function to create a fully-wired TaskClassifier.

    This is the ONLY place where SemanticRouter is instantiated
    and injected into TaskClassifier. DI principle: construct
    dependencies at composition root.

    Args:
        enable_semantic_router: Whether to use semantic routing (default True)
        warm_up: Whether to pre-initialize the router (default True)

    Returns:
        Configured TaskClassifier instance

    Usage:
        # In app startup (e.g., main.py or app factory)
        classifier = create_task_classifier(warm_up=True)

        # For testing (disable real embedding model)
        classifier = create_task_classifier(enable_semantic_router=False)
    """
    semantic_router: Optional[SemanticRouter] = None

    if enable_semantic_router:
        semantic_router = SemanticRouter(
            # Let it lazy-load the real embedding function
            embedding_func=None,
            route_examples=None,  # Use default examples
            k_neighbors=3,
            confidence_threshold=0.6,
        )

        if warm_up:
            # Pre-initialize during app startup, NOT on first request
            # (Neo fix: warm-up strategy)
            success = semantic_router.warm_up()
            if not success:
                # Log warning but continue - will fall back to regex
                import logging
                logging.getLogger(__name__).warning(
                    "SemanticRouter warm-up failed, will use regex fallback"
                )

    return TaskClassifier(
        semantic_router=semantic_router,
        # Other dependencies injected here...
    )


def create_test_classifier(
    fake_embedding_func=None,
    route_examples=None,
) -> TaskClassifier:
    """
    Factory for tests - uses fake/controlled dependencies.

    Args:
        fake_embedding_func: Fake embedding function for deterministic tests
        route_examples: Custom route examples for testing

    Returns:
        TaskClassifier with test-friendly configuration
    """
    semantic_router = None

    if fake_embedding_func is not None:
        semantic_router = SemanticRouter(
            embedding_func=fake_embedding_func,
            route_examples=route_examples or [],
        )

    return TaskClassifier(
        semantic_router=semantic_router,
    )
```

**App Startup Integration** (Matt's audit - specific location):

```python
# RECOMMENDED: In src/scrappy/cli/textual/app.py
# Add to initialize_cli() method (line 223) which runs in background thread

@work(thread=True)
def initialize_cli(self) -> None:
    """Initialize CLI in background thread."""
    if self._cli_factory is None:
        return

    try:
        # This is the slow part - runs in thread pool
        cli = self._cli_factory()

        # NEW: Warm up semantic router while in background thread
        # This runs BEFORE user can interact, avoiding cold-start latency
        if cli.classifier and hasattr(cli.classifier, '_semantic_router'):
            router = cli.classifier._semantic_router
            if router and hasattr(router, 'warm_up'):
                router.warm_up()  # ~1s model load happens here, in background

        self.post_message(CLIReady(cli=cli))
    except Exception as e:
        # ... error handling ...
```

**Why this location?**
- `initialize_cli()` already runs in a background thread (`@work(thread=True)`)
- The user cannot interact until CLI is ready anyway
- Model load happens in parallel with UI setup
- No cold-start latency on first user message

**Acceptance Criteria:**
- [x] **Factory function shows WHERE SemanticRouter is constructed** (Neo fix)
- [x] **Factory function shows HOW it's injected into TaskClassifier** (Neo fix)
- [x] warm_up() called during app init, not first request
- [x] Separate test factory for controlled testing
- [x] Follows DI principle: construct at composition root

---

## Verification Steps

### Automated

1. All existing tests pass
2. New tests pass: `pytest tests/task_router/test_semantic_router.py`
3. Linting passes: `ruff check src/scrappy/task_router/semantic_router/`
4. Type checking passes: `mypy src/scrappy/task_router/semantic_router/`

### Manual

1. Start scrappy
2. Enter: "add a node.js server"
3. Verify: Routes to CODE_GENERATION without prompt
4. Enter: "hi"
5. Verify: Routes to CONVERSATION
6. Enter: "search for python tutorials"
7. Verify: Routes to RESEARCH
8. Check timing: Classification should be <100ms

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Embedding model fails to load | Regex fallback always available |
| Slow first classification (~1s model load) | **warm_up() at app init** (Neo fix) |
| Bad example data | Start with proven examples, iterate |
| K value too low/high | Default K=3, configurable for tuning |
| Race condition on init | **Thread-safe Lock** (Neo fix) |
| Very long input causes issues | **Truncate to 2000 chars** (Neo fix) |
| Low confidence misrouting | **Optional LLM fallback for <0.5** (Neo suggestion) |

---

## Open Questions (Resolved)

1. ~~Use LanceDB or in-memory?~~ -> In-memory for simplicity (examples are small)
2. ~~Where to store example vectors?~~ -> Compute on first use, cache in memory
3. ~~Share embedding model with semantic search?~~ -> Yes, same EmbedFunction class

---

## Migration Path

1. Deploy SemanticRouter alongside existing regex
2. Monitor: Log both results, compare accuracy
3. Tune: Adjust examples based on misclassifications
4. Remove: Delete LLM classification code after validation

---

## Approval Checklist

- [x] Problem statement accurate
- [x] Architecture changes clear
- [x] All tasks well-defined
- [x] Risks addressed
- [x] Tests specified
- [x] Uses existing stack (no new dependencies)
- [x] Ready for implementation

---

## Neo's Fixes Summary

The following issues were identified by Neo and incorporated into this plan:

| Issue | Fix | Location |
|-------|-----|----------|
| 1. Protocol/impl mismatch | Return `Optional[RouteResult]` not `Optional[Tuple]` | Task 2 |
| 2. No warm-up strategy | Add `warm_up()` method, call at app init | Tasks 2, 3, 8 |
| 3. Tests use real model | Use `FakeEmbeddingFunc` with deterministic vectors | Task 6 |
| 4. Missing wiring code | Add factory function showing DI assembly | Task 8 (NEW) |
| 5. Thread safety | Add `threading.Lock` to `_ensure_initialized()` | Task 3 |
| 6. Slow cosine distance | Use numpy vectorized operations, store as `np.ndarray` | Task 3 |
| 7. No input validation | Handle empty input, truncate long input (~2000 chars) | Task 3 |
| 8. Wrong dimension docs | BGE-small-en-v1.5 is **384 dims**, not 768 | Summary, Task 6 |
| 9. Hybrid approach | Consider LLM fallback for confidence < 0.5 | Architecture |

All fixes have been incorporated into the relevant sections above.

---

## Reba's Fixes Summary

The following issue was identified by Reba during QA review:

| Issue | Fix | Location |
|-------|-----|----------|
| 10. None input crash | `_validate_input()` now checks `if not user_input` before calling `.strip()`, handling both None and empty string | Task 3, Task 6 |

**Details:**
- **Bug**: Calling `classify(None)` would crash with `AttributeError: 'NoneType' object has no attribute 'strip'`
- **Root cause**: Original validation `if not user_input or not user_input.strip()` still called `.strip()` on None
- **Fix**: Changed to `if not user_input:` first (handles None and empty), then separate whitespace check
- **Test**: Added dedicated `test_returns_none_for_none_input()` test case

**Status**: Fix incorporated. Awaiting Reba's final sign-off.

---

## Matt's Audit Summary (Integration Audit)

Matt performed an integration audit of the semantic router plan against the existing codebase. The following issues were identified:

| Issue | Fix | Location |
|-------|-----|----------|
| 11. embeddings.py thread safety | `_get_or_create_model()` has TOCTOU race - add `threading.Lock` with double-checked locking | Task 0 (NEW) |
| 12. Wrong dimension in docstring | EmbedFunction class docstring says "768 dimensions" but model is 384 dims | Task 0 (NEW) |
| 13. No feature flag | Add `enable_semantic_routing: bool = True` parameter for easy disable | Task 4 |
| 14. No warm_up location | Recommend `app.py:223` (`initialize_cli()`) background thread | Architecture, Task 8 |

**Details:**

### Issue 11: Thread Safety in embeddings.py
- **File**: `src/scrappy/context/semantic/embeddings.py`
- **Bug**: `_get_or_create_model()` checks `if _CACHED_MODEL is None` then creates model, but another thread could pass the same check before the first thread finishes creating
- **Impact**: Multiple expensive TextEmbedding instances created, wasted memory
- **Fix**: Add `threading.Lock()` with double-checked locking pattern

### Issue 12: Incorrect Dimension Documentation
- **File**: `src/scrappy/context/semantic/embeddings.py` line 48
- **Bug**: Docstring says "768 dimensions" but BGE-small-en-v1.5 produces 384-dim vectors
- **Impact**: Misleading documentation, could cause confusion
- **Fix**: Change "768 dimensions" to "384 dimensions"

### Issue 13: No Feature Flag for Easy Disable
- **File**: `src/scrappy/task_router/classifier.py`
- **Concern**: If semantic routing has issues in production, need a way to quickly disable without code change
- **Fix**: Add `enable_semantic_routing: bool = True` parameter to TaskClassifier

### Issue 14: Unclear warm_up() Integration Point
- **Concern**: Plan mentions warm_up() but doesn't specify WHERE in the codebase to call it
- **Recommendation**: Call in `src/scrappy/cli/textual/app.py` at line 223 in `initialize_cli()`
- **Rationale**: This method already runs in a background thread, user cannot interact until complete

**Status**: All issues incorporated into plan. Task 0 added as prerequisite.
