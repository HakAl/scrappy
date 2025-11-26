
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