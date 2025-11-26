
### 1. Dependencies

```toml
[tool.poetry.dependencies]
# ... existing
pydantic = "^2.0"
# groq = "^0.x"  <-- Ensure you have the standard Groq client installed
```

---

### 2. New File: `self_heal/magistrate.py` (The Judge)
*Updated with **Regex parsing** to handle DeepSeek R1's `<think>` blocks, preventing JSON parsing crashes.*

```python
# self_heal/magistrate.py
import json
import re
from pydantic import BaseModel, Field
from .router import route

class Judgment(BaseModel):
    is_valid: bool = Field(description="True only if patch is complete, non-lazy, and safe")
    critique: str = Field(description="Short, ruthless feedback if invalid")

def judge_patch(original_code: str, proposed_code: str, task: str) -> Judgment:
    prompt = f"""You are an extremely strict Senior Code Reviewer (a Magistrate).
Your job: reject lazy, incomplete, or dangerous code.

Task the code must fulfill:
{task}

STRICT RULES - REJECT IF:
- Uses placeholders like "# ...", "rest of code", "<snip>", ellipsis in code
- Deletes or comments out large chunks without replacement
- Truncates functions/classes
- Indentation would cause SyntaxError
- Missing imports that were previously present
- Output is not complete, standalone, runnable Python

Original code context (first 1200 chars):
{original_code[:1200]}

Proposed full implementation:
```python
{proposed_code}
```

Respond EXACTLY in JSON format:
{{"is_valid": true|false, "critique": "brief reason or 'clean'"}}"""

    raw = route(prompt + "\n\nJSON:", model="judge")
    
    try:
        # 1. Strip DeepSeek's <think> blocks if present
        clean_raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        
        # 2. Extract the JSON object using Regex (ignores markdown wrappers)
        json_match = re.search(r'\{.*\}', clean_raw, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in response")
            
        data = json.loads(json_match.group())
        return Judgment(**data)
    except Exception as e:
        # Fallback: Logic check if JSON fails
        print(f"Magistrate Parsing Error: {e}. Raw output: {raw[:50]}...")
        valid = "true" in raw.lower() and "false" not in raw.lower()
        critique = "clean" if valid else "Parser: Judge failed to give clean JSON, treating as rejected."
        return Judgment(is_valid=valid, critique=critique)
```

---

### 3. Tiny Router Update
*Ensures the correct model ID for Groq is used.*

```python
# self_heal/router.py
# ... existing imports ...

# DeepSeek-R1 via Groq
JUDGE_MODEL_ID = "deepseek-r1-distill-qwen-7b" # OR "deepseek-r1-distill-llama-70b" if available

def route(prompt: str, model: str = "fast") -> str:
    if model == "fast":
        m = "llama3-8b-8192"
    elif model == "smart":
        # Assuming Gemini setup exists here
        return gem.GenerativeModel("gemini-1.5-pro").generate_content(
            prompt, generation_config={"temperature": 0.1}
        ).text
    elif model == "judge":
        m = JUDGE_MODEL_ID
    else:
        m = model

    if model != "smart":
        return groq_client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, # Low temp crucial for Judge reasoning
            max_tokens=1024,
        ).choices[0].message.content
```

---

### 4. Updated Agent Core
*Added `last_critique` initialization to prevent `UnboundLocalError`.*

```python
# self_heal/agent.py
from .magistrate import judge_patch, Judgment

class ReflexionAgent:
    # ... __init__ unchanged ...

    def run(self, task: str) -> str:
        # PHASE 1 – write test (smart model once)
        test_code = route(f"Write a pytest that verifies: {task}\nOutput ONLY code.", "smart")
        self.test_file.write_text(test_code)
        
        # Initialize critique to avoid UnboundLocalError
        last_critique = ""

        for attempt in range(1, self.max_retries + 1):
            # 1. Generate candidate
            impl_prompt = f"Write complete Python code for: {task}"
            if last_critique:
                impl_prompt += f"\n\nPrevious feedback: {last_critique}"
                
            candidate = route(impl_prompt, model="fast")

            # 2. Linter short-circuit (free & fast)
            lint_err = lint(candidate)
            if lint_err:
                candidate = route(
                    f"Fix these ruff errors (output ONLY fixed code):\n{lint_err}\n\n{candidate}",
                    model="fast",
                )

            # 3. MAGISTRATE JUDGMENT
            # Read previous file if exists, else empty string
            original = (self.work / "implementation.py").read_text() if (self.work / "implementation.py").exists() else ""
            
            judgment: Judgment = judge_patch(original, candidate, task)

            if not judgment.is_valid:
                print(f"Judge REJECTED attempt {attempt}: {judgment.critique}")
                last_critique = judgment.critique
                continue  # Loop restarts, coder gets the critique

            # 4. If judge approves → write & test
            self.impl_file.write_text(candidate)
            rc, stderr = run_tests(self.test_file)

            if rc == 0:
                return "SUCCESS – passed tests + judge approved."

            last_critique = f"Tests failed:\n{stderr}\nFix the bug."

            # Optional escalation after 2 fails (Smart Rescue)
            if attempt == 2:
                print("Escalating to Smart Model...")
                candidate = route(impl_prompt + "\nBe extremely careful.", model="smart")
                self.impl_file.write_text(candidate)
                if run_tests(self.test_file)[0] == 0:
                    return "SUCCESS (smart model rescue)"

        return "FAILED – max retries exhausted."
```



This is the "Agentic Loop" pattern, and it is the difference between a chatbot and an autonomous engineer.

Since you are intrigued by the "self-healing" concept, here is how you implement a **Token-Poor Reflexion Loop** without burning through your API limits.

### The Architecture: "The TDD Loop"
Instead of just "Generate Code," your agent follows a strict **Test-Driven Development (TDD)** cycle. This is safer because the LLM isn't guessing if it's right—the Python interpreter is telling it.

#### Phase 1: The Setup (The "Spec")
Before writing a single line of implementation code, force the agent to write a **verification script**.

1.  **User Prompt:** "Create a function that parses this CSV and calculates the mean."
2.  **Agent Action 1 (The Architect):** writes `tests/test_task.py` first.
    *   It defines the inputs and the *expected* outputs.
    *   *Model Strategy:* Use a "Smart" model (Gemini Pro/Llama-3-70b) here. If the test is wrong, the whole loop fails.

#### Phase 2: The Loop (The "Coder")
Now, you enter the `while` loop.

1.  **Agent Action 2 (The Builder):** Writes `src/task.py`.
    *   *Model Strategy:* Use a "Fast/Cheap" model (Groq/Llama-3-8b). Speed matters more than perfection here because we have a safety net.
2.  **System Action:** Runs `pytest tests/test_task.py`.
3.  **Decision Point:**
    *   **Pass:** ✅ Save file, exit loop, notify user.
    *   **Fail:** ❌ Capture the **STDERR** (the error message).

#### Phase 3: The Reflexion (The "Fixer")
This is where the magic happens. You don't just say "Try again." You feed the error back into the prompt.

*   **Prompt:**
    > "You wrote this code [insert code].
    > It failed with this error: [insert stderr].
    > The test expected [A] but got [B].
    > Analyze the error, explain why it happened, and rewrite the code to fix it."

*   **Model Strategy:** Switch back to a "Smart" model if the "Fast" model fails twice. This is "Dynamic Escalation."

*   **Circuit Breaker** The "3-strike" rule is industry standard. You might also want to add a "Temperature Decaying" strategy:
    *   Attempt 1: Temp 0.0 (Precise)
    *   Attempt 2: Temp 0.2 (Little creativity)
    *   Attempt 3: Temp 0.5 (Try something different)

### Implementation Blueprint

Here is how I would structure this `ReflexionAgent` class in your project:

```python
def run_reflexion_loop(task_description, max_retries=3):
    # Step 1: Generate the Test (The "Contract")
    test_code = router.route(
        f"Write a pytest for: {task_description}. Output ONLY code.", 
        model="smart"
    )
    save_file("temp_test.py", test_code)

    # Step 2: The Loop
    current_code = ""
    error_log = ""
    
    for attempt in range(max_retries):
        # Construct prompt with history if we failed previously
        prompt = f"Write python code for: {task_description}."
        if error_log:
            prompt += f"\n\nYour previous attempt failed:\n{error_log}\nFix it."

        # Generate implementation
        current_code = router.route(prompt, model="fast")
        save_file("implementation.py", current_code)

        # Run the test
        result = subprocess.run(["pytest", "temp_test.py"], capture_output=True, text=True)

        if result.returncode == 0:
            return "Success! ✅"  # Break the loop
        
        # Capture error for the next iteration
        error_log = result.stderr[-2000:] # Keep it short for context window
        print(f"Attempt {attempt+1} failed. Retrying...")

    return "Failed after 3 attempts. ❌"
```

### Why This Fits Your "Token-Poor" Ethos
1.  **Cheap Tries:** You use the cheap model for the heavy lifting (writing the code). You only pay for the expensive model when you need "Architecture" (writing the test) or "Debugging" (fixing hard errors).
2.  **Early Bailout:** If the agent writes a bad test, the loop explodes immediately. You don't waste tokens iterating on code that will never pass.
3.  **Deterministic Success:** When the agent says "I'm done," you *know* it works (at least according to the test).

### A "Pro" Tip for Self-Correction
LLMs are often blind to their own syntax errors.
*   **Add a Linter Step:** Before even running the test, run `flake8` or `ruff` on the generated code.
*   If `ruff` fails, don't even count it as a "retry." Just auto-feed the syntax error back to the cheap model. It fixes syntax instantly. This saves your "Smart Model" budget for logic errors, not missing colons.


Since you are about to implement this "Self-Healing" loop, I have one **critical warning** that will save you days of debugging and prevents your users from getting angry.

### The Trap: The "Lazy Coder" & The File Wipe
When you ask an LLM (especially smaller/cheaper ones) to "fix the code," it often returns this:

```python
# src/main.py
def important_function():
    # ... existing code ...
    new_logic_here()
```

If your agent blindly writes this string to `src/main.py`, **it deletes the user's entire file** and replaces it with comments. This is the #1 way coding agents lose user trust.

### The Solution: "Search and Replace" Blocks
Since you are optimizing for **Token Poverty**, you should rarely ask the model to rewrite the *whole* file. It wastes tokens and increases latency.

Instead, force the "Fixer" agent to output **Search/Replace blocks**.

#### 1. The Prompt Strategy
Tell the agent: *"Do not output the whole file. Only output the code block that needs to change, formatted like this:"*

```text
<<<<<<< SEARCH
def calculate_total(items):
    return sum(items)
=======
def calculate_total(items):
    # Fix: Handle empty lists to prevent errors
    if not items:
        return 0
    return sum(items)
>>>>>>> REPLACE
```

#### 2. The Python Patcher (The "Applier")
You need a robust function to apply these blocks. LLMs are sometimes slightly off with whitespace, so a "fuzzy" match helps.

Here is a starter implementation for your `utils.py`:

```python
def apply_diff(file_path, search_block, replace_block):
    with open(file_path, 'r') as f:
        content = f.read()
    
    # exact match check
    if search_block in content:
        new_content = content.replace(search_block, replace_block)
        with open(file_path, 'w') as f:
            f.write(new_content)
        return True
        
    # Fallback: If exact match fails (common with whitespace hallucinations),
    # you can implement a "fuzzy" match here or just return False 
    # and ask the LLM to try again.
    return False
```

### Why this fits `scrappy`:
1.  **Saves Tokens:** You aren't streaming back 500 lines of unchanged code. You stream back 5 lines.
2.  **Safety:** If the `SEARCH` block isn't found, the agent **does nothing**. It doesn't accidentally overwrite the file with garbage. It fails safe.
3.  **Speed:** Smaller output = faster inference = snappier "Daily Standup" or "Quick Fix" feel.



---

The "Lazy Coder" problem (where the model writes `// ... rest of code`) is the bane of my existence. When you are using lighter models (like Gemini Flash, Groq/Llama-3-8b, or even older 3.5 classes), they *love* to hallucinate that they are being helpful by truncating files.

Here is the **"Poor Man's Patcher"**. This is the Python logic that allows you to use cheap models safely, effectively "fixing" their lazy mistakes without needing a smarter brain.

### The Strategy: "Fuzzy Search & Replace"

Cheap models are bad at exact whitespace. If your file has 4 spaces but the model outputs a `SEARCH` block with tabs, a standard `text.replace()` fails.

You need a **Fuzzy Patcher**. It finds the "most likely" location of the code block and swaps it, even if the model messed up the indentation slightly.

#### 1. The Prompt (Strict Formatting)
First, force the format. Don't ask for "code." Ask for a **UDIFF** or a specific block format. The industry standard (used by Aider and others) is:

```text
<<<<<<< SEARCH
(original code to find)
=======
(new code to replace it with)
>>>>>>> REPLACE
```

#### 2. The Implementation (The Magic Function)
Add this to your `utils.py`. It uses Python's built-in `difflib` to handle the "dumb model" variance.

```python
import difflib

def apply_fuzzy_patch(file_path, search_block, replace_block, threshold=0.85):
    """
    Applies a patch even if the model messed up whitespace or context slightly.
    """
    with open(file_path, "r") as f:
        content = f.read()

    # 1. Try exact match first (Fastest)
    if search_block in content:
        new_content = content.replace(search_block, replace_block, 1)
        _write_file(file_path, new_content)
        return True, "Exact match applied."

    # 2. Fuzzy Match (The Safety Net)
    # We split by lines to find the best block match
    content_lines = content.splitlines()
    search_lines = search_block.splitlines()
    
    best_ratio = 0.0
    best_idx = -1
    
    # Scan the file for the block that looks most like 'search_block'
    # (This is O(N*M), so only use on files < 2000 lines or optimize)
    matcher = difflib.SequenceMatcher(None, search_lines, [])
    
    for i in range(len(content_lines) - len(search_lines) + 1):
        window = content_lines[i : i + len(search_lines)]
        matcher.set_seq2(window)
        if matcher.ratio() > best_ratio:
            best_ratio = matcher.ratio()
            best_idx = i

    # 3. Decision Logic
    if best_ratio > threshold:
        # We found the block! Replace it.
        new_lines = (
            content_lines[:best_idx] + 
            replace_block.splitlines() + 
            content_lines[best_idx + len(search_lines):]
        )
        _write_file(file_path, "\n".join(new_lines))
        return True, f"Fuzzy match applied (Confidence: {best_ratio:.2f})"
    
    return False, f"Could not locate block. Best match was only {best_ratio:.2f}"

def _write_file(path, content):
    with open(path, "w") as f:
        f.write(content)
```

### 3. The "Lazy Detection" Guardrail

Even with fuzzy matching, the model might still try to delete code. Add this simple check before you write to disk:

```python
def validate_patch(original_content, new_content):
    # Logic: If the file shrank by > 50% but the user didn't ask for a delete,
    # the model probably hallucinated a "lazy" summary.
    
    if len(new_content) < len(original_content) * 0.5:
        if "rest of code" in new_content or "..." in new_content:
            raise ValueError("Lazy Coder Detected: Model tried to truncate file.")
    
    return True
```

### How to use this in your workflow

When your cheap model (Groq/Flash) fails to apply a patch:

1.  **Do NOT** immediately switch to the "Smart" model (Gemini 3.0 Pro).
2.  **INSTEAD**, feed the failure back to the cheap model with the *actual* context lines from the file.

> **Prompt:** "Your SEARCH block failed to match. The actual code at that location looks like this:
> [Insert 10 lines of actual code from file]
> Rewrite the block using this EXACT text in the SEARCH section."

This costs pennies and usually fixes the issue on the second try.

Since you like Gemini 3.0, you can use it as the **"Judge"** in your architecture—have it verify the diffs created by the smaller models before they are applied, rather than generating the code itself. Best of both worlds!
