# Task Router 

The Task Router is an intelligent dispatch system that:

1. **Classifies** user input by task type and complexity
2. **Selects** the optimal provider based on task requirements
3. **Routes** to the appropriate execution strategy
4. **Executes** with strategy-specific optimizations

This eliminates the overhead of running every task through a full agent loop while ensuring complex tasks still receive appropriate handling.

## Issues

<!-- todo -->

- Semantic LLM classification
- Add intent clarification mechanism

---
  Recommendations

  1. Configuration consolidation - Consider a RouterConfig dataclass for all thresholds/settings
  2. Pattern weight configuration - Allow runtime/file-based pattern weight adjustment
  3. Metrics persistence - Add optional persistence for MetricsCollector

  ---
  3. Fragile Pattern Matching

  Evidence:
  - Strategy pattern with pluggable ClassificationStrategy implementations
  - LLM-augmented classification for disambiguation
  - Intent clarification for ambiguous cases
  - Confidence scoring with escalation logic

  Remaining concerns:
  - Pattern weights still hardcoded in strategy classes
  - Could benefit from configurable patterns or learned weights

  Location: classification_strategies/*.py

  ---
  15. Configuration Scattered ⚠️ IMPROVED

  Evidence:
  - Router configuration centralized in constructor
  - Behavior switches on router instance:
    - clarify_on_low_confidence
    - confidence_threshold
    - escalate_on_low_confidence
    - use_llm_classification

  Remaining concerns:
  - Some thresholds hardcoded (e.g., 0.7 in pure_functions)
  - Pattern weights in strategy classes
  - Consider centralizing to a config object
----

**LiteLLM Integration**

**`LiteLLM` is the Muscle, but your Task Router is the Brain.**

If you deleted your router today and switched to `LiteLLM`'s default router, your app would actually get *dumber*.

Here is why your custom logic is still the "secret sauce" and exactly how to combine the two.

### 1. The "Brain vs. Muscle" Distinction

*   **What `LiteLLM` does (The Muscle):**
    *   "I need to send this string to Gemini." → *It handles the HTTP request, the API key, the retry if it fails, and the fallback to Claude if Gemini is down.*
    *   It is an **Infrastructure Layer**. It ensures the message gets delivered. It generally defaults to random load balancing or latency-based routing, not "intelligence-based" routing.

*   **What YOUR Router does (The Brain):**
    *   "This is a large `git diff` (500 lines), so I shouldn't send it to Llama-3-8b because it will hallucinate. I must send it to Gemini-Pro-1.5."
    *   "The user is asking for a 'Security Review', so I need a model trained on reasoning, not a fast chat model."
    *   This is **Business Logic**. `LiteLLM` cannot do this out of the box. It doesn't know your file structure or what a "complex task" means in your specific app context.

### 2. Why Your Code is Better for *Coding Agents*
`LiteLLM`'s router is primarily designed for **Reliability** (e.g., "Model A is rate-limited, send to Model B"). It is *not* natively designed for **Cognitive Routing** (e.g., "This task is hard, send to Smart Model").

You mentioned your router uses "dynamic ad-hoc scanning" of the project to inform the decision. **`LiteLLM` can't do that.** It doesn't know you have a `tests/` folder. Your logic that checks the context *before* choosing a model is your competitive advantage.

### 3. The "Power Move": Combine Them
Don't throw away your code. **Wrap it.**

Use your Router to make the *Strategic Decision*, and use `LiteLLM` to execute the *Action*.

**Before (What you probably have):**
```python
# Your custom logic mixed with API calls
def route_task(task):
    if analyze_complexity(task) > 5:
        # You likely wrote custom code to call Gemini here
        return requests.post("https://generativelanguage.googleapis.com...", ...)
    else:
        # And custom code to call Groq here
        return requests.post("https://api.groq.com...", ...)
```

**After (The "Supercharged" Architecture):**
```python
from litellm import completion

# Your custom logic STAYS as the "Manager"
def route_task(task):
    # 1. Your Brain makes the decision
    complexity = analyze_complexity(task)
    
    target_model = ""
    if complexity > 5:
        target_model = "gemini/gemini-1.5-pro-latest"
    else:
        target_model = "groq/llama3-8b-8192"

    # 2. LiteLLM handles the "dirty work" (Connections, Retries, Errors)
    response = completion(
        model=target_model, 
        messages=[{"role": "user", "content": task}],
        fallbacks=["openai/gpt-4o-mini"] # <--- You now get this for free!
    )
    return response
```

### Summary
You built the **Strategy Layer**. `LiteLLM` is just the **Connectivity Layer**.

*   **Keep your Router:** It contains your app's intelligence.
*   **Refactor the *calls* inside it:** Swap your raw `requests` or SDK calls for `LiteLLM` calls.

This gives you the best of both worlds: **Your smart decision-making + Their battle-tested error handling.** You are exactly where you need to be.

---

## Architecture

**Strategy Pattern:**
```
TaskClassifier
  └─ strategies: List[ClassificationStrategy]
       ├─ DirectCommandStrategy
       │    └─ patterns: List[(regex, weight, name)]
       ├─ CodeGenerationStrategy
       │    └─ patterns: List[(regex, weight, name)]
       ├─ ResearchStrategy
       │    └─ patterns: List[(regex, weight, name)]
       └─ ConversationStrategy
            └─ patterns: List[(regex, weight, name)]

  classify() method:
    - Call each strategy.evaluate(input)
    - Pick strategy with highest confidence
    - Generate metadata
```

## Benefits

### 1. Separation of Concerns 
- Each strategy manages its own patterns
- Easy to understand what each strategy does
- No more giant pattern lists in one file

### 2. Testability 
- Can test strategies independently
- Can mock/stub strategies for unit testing
- Easier to add tests for new patterns

### 3. Extensibility 
- Add new strategies without modifying core classifier
- Can inject custom strategies via constructor:
  ```python
  custom_strategies = [
      DirectCommandStrategy(),
      CodeGenerationStrategy(),
      ResearchStrategy(),
      ConversationStrategy(),
      MyCustomStrategy(),  # Add custom strategy
  ]
  classifier = TaskClassifier(strategies=custom_strategies)
  ```
  