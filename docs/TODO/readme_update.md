
---

### ⚠️ Critical Gaps (Must Fix/Add)

#### 1. The "Visual Proof" (Missing GIF/Screenshot)
Text is abstract. Users need to see what the CLI looks like.
*   **Action:** Add an ASCII cinema recording (using a tool like `asciinema` or `vhs`) or a high-quality GIF right after the "Quick Start" header. Show the tool answering a question or performing a simple refactor.
Here is a structured, technical, and transparent "Models & Providers" section. It breaks down the "Why" for each provider and transparently lists the models, limits, and specific constraints you mentioned (GitHub/Cohere).

Add this section after **"Key Features"** or replace the existing **"Requirements"** section with a broader **"Providers & Architecture"** section.

***

## Supported Models & Architecture

Scrappy uses a "Mixture of Providers" strategy. Instead of relying on one expensive model, it dynamically routes tasks to the best free-tier model for the job.

### 1. The Heavy Lifters (High Volume & Speed)
These providers power the core of Scrappy, handling the bulk of agent loops, refactoring, and general chat.

| Provider | Key Models | Why we use it |
| :--- | :--- | :--- |
| **Cerebras** | **Llama 3.3 70B**, **Qwen 3 32B**, **Llama 3.1 8B**<br>*(Plus Qwen-3-235B Instruct)* | **Incredible Speed.** With ~14,400 requests/day and ultra-fast inference, this is the default engine for the "Agent" loop, allowing it to iterate on code rapidly without hitting limits. |
| **Groq** | **Llama 3.3 70B**, **Mixtral 8x7B**, **Llama 4 Scout**<br>*(Plus Kimi-k2-instruct)* | **Low Latency.** Groq provides near-instant responses. We use the 70B Versatile models for complex reasoning tasks that require more intelligence than the 8B models can provide. |
| **Google** | **Gemini 2.5 Flash**, **Gemini 2.0 Flash-Exp** | **Huge Context.** When you need to analyze multiple files or large documentation, Scrappy routes to Gemini. It handles large context windows better than Llama-based models. |

### 2. The Specialists (High Intelligence / Specific Tasks)
Scrappy also integrates specialized providers for hard reasoning problems or "second opinions."

*   **GitHub Models:** Includes access to **GPT-4o**, **DeepSeek-R1** (Reasoning), and **Phi-4**.
    *   *Limitation:* These are strictly for **Chat/Query** mode. Due to strict Rate Limits (TPM/RPM), they cannot be used for the autonomous `agent` loop.
*   **Cohere:** Integrated but currently inactive by default due to low free-tier quotas.

### 3. Model Routing Logic
You don't need to manually switch models (though you can). Scrappy classifies your intent:

1.  **"Fix this function"** $\rightarrow$ **Cerebras (Llama 3.1 8B)**
    *   *Reason:* Fast, cheap, and capable enough for small logic changes.
2.  **"Plan a new architecture for my app"** $\rightarrow$ **Groq (Llama 3.3 70B)** or **Gemini 2.5**
    *   *Reason:* Requires high-level reasoning and instruction following.
3.  **"Explain how this entire module works"** $\rightarrow$ **Gemini 2.0 Flash**
    *   *Reason:* Needs a massive context window to read all the files.
4.  **"Why is this logic failing?" (Hard Logic)** $\rightarrow$ **DeepSeek-R1 (via GitHub)**
    *   *Reason:* Specialized reasoning model required.

---

### Integration Tips regarding specific models:

If you want to highlight the **"New/Exotic"** models you have (like Llama 4 Scout or Qwen 3 235B), you can add a small "Bleeding Edge" badge or note:

> **🧪 Bleeding Edge Access**
> Scrappy stays up to date. We support the latest experimental endpoints including **Llama 4 Scout (17B)** and **Qwen 3 (235B Instruct)**, giving you access to state-of-the-art weights the moment they hit the API providers.

### How to phrase the GitHub Limitation in the CLI/Docs:
*   **Draft:** "Note: GitHub Models (GPT-4o, DeepSeek) are powerful but rate-limited. They are available for `/ask` and `/query` commands but are disabled for `/agent` tasks to prevent immediate lockout."
#### 3. Privacy Wording Nuance
In the FAQ, you say: *"Your code never leaves your machine."*
Immediately followed by: *"Only the prompts... are sent to the AI providers."*
*   **Critique:** Technically, if the prompt contains code, the code *is* leaving the machine.
*   **Fix:** Be precise to avoid backlash.
    *   *Better:* "Your code is not stored on Scrappy servers. However, necessary code snippets are sent to the third-party LLM providers (Groq/Google) to generate answers. Check their privacy policies regarding data training."

#### 4. The "Embeddings" Trap
You mention "Semantic Code Search." This usually requires a local embedding model (like `sentence-transformers`).
*   **Question:** Does Scrappy download a 500MB model on the first run?
*   **Action:** If yes, warn the user in the "Quick Start."
    *   *Add:* "Note: The first time you run `/explore`, Scrappy will download a lightweight embedding model for search functionality."

---

### 🎨 Polishing Touches

#### 1. Windows Command Accuracy
In your Quick Start:
```bash
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```
*   **Issue:** In standard Windows `cmd.exe`, the activate script is just `venv\Scripts\activate.bat`. The command you listed is for PowerShell.
*   **Fix:** Just keep it simple or specify: `.\venv\Scripts\activate` (Works in PS, usually enough for devs).

#### 2. Installation Method
You suggest `pip install -e .`.
*   **Action:** If you are releasing, are you putting this on PyPI?
    *   *If yes:* Change to `pip install scrappy-ai`.
    *   *If no:* The current instructions are fine, but clarify that this is a "Source Install."

#### 3. The "Help" Command
In the Quick Start step 4, you show `> /explore`.
*   **Suggestion:** Change the very first command the user sees to `> /help`.
*   *Why:* It gives them immediate agency if they get stuck.

---

### 📄 Suggested Edit for the "Quick Start" Section

Here is a slightly refined version of Step 1 to make it bulletproof for different OSs:

**1. Install the Tool**
Clone the repository and install dependencies.

```bash
git clone https://github.com/HakAl/scrappy
cd scrappy

# Linux/macOS
python -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\activate

# Install in editable mode
pip install -e .
```

---


This is great news. The fact that you have a **Setup Wizard**, **background processing**, and **visual feedback (status bar)** significantly improves the user experience (UX) and addresses the "hidden download" concern I raised earlier.

Using `fastembed` and `lancedb` means the setup is likely much faster and lighter than standard torch-heavy implementations, which is a big selling point.

Here is how I would update the **Quick Start** and **Features** sections to reflect this polished workflow.

### 1. Update "Quick Start" (Step 3 & 4)

Since the Wizard handles the keys, you can merge the "Set Keys" and "Start Coding" steps into a smoother flow.

**Revised Quick Start Section:**

> **3. Run the Setup Wizard**
> Scrappy comes with an interactive setup wizard to get you started in seconds.
>
> ```bash
> scrappy
> ```
>
> The wizard will:
> 1.  Prompt you to paste your free API keys (saved securely locally).
> 2.  **Automatically download** the embedding model (BGE-Small) in the background.
> 3.  **Index your codebase** using LanceDB for ultra-fast retrieval.
>
> *Note: You'll see a progress bar at the bottom of the screen. You can start chatting immediately while Scrappy indexes your code in the background!*

---

### 2. Update "Key Features"

You should brag about the tech stack here. `Fastembed` and `lancedb` are buzzwords that signal "modern" and "fast" to developers.

**Add/Modify this bullet point:**

> *   **Local & Fast Indexing**: Uses **LanceDB** and **FastEmbed** to index your code locally. No vector databases to manage, no heavy PyTorch dependencies, and your code structure never leaves your machine.

---

### 3. Update "Common Questions" (Or "Troubleshooting")

Since it downloads a model (even a small one), it's good to cover the "what if I'm offline" scenario.

> **Q: Does Scrappy work offline?**
> *   **A:** The chat requires an internet connection to reach the LLM providers. However, the code indexing and search happen entirely **offline** on your device after the initial 20MB model download.

---

### 4. The "Visual" Opportunity

Since you mentioned a **"clear progress indicator at the bottom status bar,"** this is the **perfect** image to put at the top of your README.

**Why?**
*   It proves the tool has a robust UI (TUI), not just a basic `input()` loop.
*   It shows "liveness" and polish.

**Recommendation:**
Take a screenshot capturing the setup wizard or the main chat window with the status bar visible at the bottom showing `Indexing: [====..] 45%`.

### Summary of Changes for `README.md`

Here is a block you can copy-paste to replace the existing **Step 3 & 4** in your draft:

```markdown
**3. Run the Setup Wizard**
Scrappy includes a first-run wizard to configure your environment automatically.

```bash
# Navigate to your project folder
cd ~/my-cool-project

# Run Scrappy
scrappy
```

The wizard will ask for your API keys and store them securely.

**4. Instant Coding**
Once configured, Scrappy will immediately start **auto-exploring** your directory.
*   **Zero-Wait:** You can start chatting right away.
*   **Background Indexing:** Scrappy uses `FastEmbed` and `LanceDB` to index your code on a background thread. Watch the status bar at the bottom for real-time progress.
```