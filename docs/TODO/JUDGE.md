
**Judge or Magistrate Pattern**

You don't need a *smart* coder; you need a *strict* reviewer.
And for that, you don't need Gemini 3.0. You need a model that excels at **Logic & Instruction Following**, not necessarily creative generation.

Here is your "Token-Poor" Judge architecture using open-weight models that punch way above their weight class.

### 1. The Hardware: "DeepSeek R1 Distill"
The biggest breakthrough for you isn't Gemini 3; it's **DeepSeek R1 Distill**.
*   **The Tech:** They took their massive reasoning model (R1) and "distilled" its reasoning patterns into smaller architectures (Llama and Qwen).
*   **The Win:** You get "Reasoning Traces" (Chain of Thought) in a **7B or 8B parameter model**.
*   **Recommendation:** Use **`DeepSeek-R1-Distill-Qwen-7B`** (or the Llama 8B variant).
    *   It is tiny (runs on Groq/Cerebras or a local Macbook Air).
    *   It is *specifically* trained to reason before answering.
    *   It is ruthlessly logical, making it a perfect Judge.

### 2. The Implementation: The "Inspector" Agent
Don't ask your Judge to "fix" code. Ask it to **Pass/Fail** the code based on specific criteria (like "Laziness").

**The Workflow:**
1.  **Coder Agent (Fast/Cheap):** Generates the patch.
2.  **Inspector Agent (Reasoning/Strict):** Reads the patch + original file.
3.  **Action:** If `FAIL`, reject the patch and send the *Inspector's critique* back to the Coder.

#### The Code
Here is how you implement the `Inspector` using a structured output schema (or strict parsing).

```python
# inspector.py
from pydantic import BaseModel, Field

class InspectionResult(BaseModel):
    is_valid: bool = Field(description="Set to False if the code is lazy, truncated, or breaks syntax.")
    critique: str = Field(description="Brief explanation of why it failed. Be ruthless.")
    lazy_score: int = Field(description="0-100 score of how 'lazy' the code is (e.g. uses comments instead of code).")

def inspect_code(original_code: str, proposed_patch: str) -> InspectionResult:
    prompt = f"""
    You are a Senior Code Reviewer. Your ONLY job is to catch "Lazy Coding" and hallucinations.
    
    TASK:
    Review this patch for the following file.
    
    STRICT RULES:
    1. REJECT any code that uses placeholders like `# ... rest of code ...` or `// existing logic`.
    2. REJECT any code that deletes functions without explicit instruction.
    3. REJECT if the indentation implies a syntax error (Python).
    
    Original File Snippet:
    {original_code[:1000]}...
    
    Proposed Patch:
    {proposed_patch}
    """
    
    # Use DeepSeek-R1-Distill or Qwen-2.5-Coder-7B here
    # Force JSON output (many providers support this natively now)
    response = llm_provider.generate(
        model="deepseek-r1-distill-qwen-7b", 
        prompt=prompt,
        response_format=InspectionResult
    )
    
    return response
```

### 3. The "Refusal Loop"
Now, wire this into your orchestration. This is where you save money: **You catch the lazy code before it hits the disk.**

```python
# orchestrator.py

def execute_task_with_judge(task):
    max_retries = 3
    for attempt in range(max_retries):
        # 1. Generate Code
        patch = coder_agent.generate(task)
        
        # 2. Inspect Code (The "Magistrate" Step)
        result = inspector.inspect_code(original_file, patch)
        
        if result.is_valid:
            apply_patch(patch)
            return "Success"
        
        # 3. Rejection Feedback
        print(f"⚠️ Inspector Rejected (Score {result.lazy_score}): {result.critique}")
        
        # 4. Feed the critique back to the Coder
        # This is the "Self-Healing" moment!
        task += f"\n\nPREVIOUS ATTEMPT REJECTED: {result.critique}\nDO NOT use lazy placeholders."

    return "Failed to generate valid code."
```

### 4. Why Qwen 2.5 Coder (7B) is a Valid Backup
If you can't access the DeepSeek distilled models easily, **Qwen 2.5 Coder 7B Instruct** is your next best bet.
*   It is widely considered the current "King of 7B Coding Models."
*   It beats GPT-3.5-Turbo and approaches GPT-4 on some benchmarks.
*   It is exceptionally good at following strict formatting instructions (like "Don't delete my code").

**Summary:** You are right to avoid relying on Gemini 3.0 for production features. Use **DeepSeek R1 Distill** or **Qwen 2.5 Coder 7B** as your "Sheriff." They are cheap, run anywhere, and are smart enough to slap the wrist of a lazy coding model.

