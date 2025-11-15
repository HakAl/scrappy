# 5-Minute Quickstart

Get running with LLM Team in 5 minutes. No fluff.

## 1. Get Free API Keys (2 min)

Pick at least one:
- **Cerebras** (recommended): https://cloud.cerebras.ai → 14,400 requests/day
- **Groq**: https://console.groq.com → 7,000 requests/day

## 2. Install (1 min)

```bash
cd llm_agent_team
pip install -e .
```

## 3. Set Keys (30 sec)

**Windows PowerShell:**
```powershell
$env:CEREBRAS_API_KEY = "your-key-here"
$env:GROQ_API_KEY = "your-key-here"
```

**Mac/Linux:**
```bash
export CEREBRAS_API_KEY="your-key-here"
export GROQ_API_KEY="your-key-here"
```

## 4. Use It (30 sec)

```bash
# Go to any project
cd ~/my-project

# Start (learns your codebase automatically)
llm-team --auto-explore
```

That's it. You're in.

---

## Essential Commands

**Ask anything:**
```
You: How does the auth system work?
You: What's the best way to add caching here?
```

**Plan a task:**
```
You: /plan Add user authentication
```

**Let AI write code (with your approval):**
```
You: /agent Fix the login bug
```

**Exit:**
```
You: /quit
```

---

## One-Liners (No Interactive Mode)

```bash
# Quick question
llm-team query "What is Docker?"

# Question about your code
llm-team query "How should I fix the auth bug?" --with-context

# Plan something
llm-team plan "Build REST API"

# AI writes code
llm-team agent "Add input validation"
```

---

## What Just Happened?

- `--auto-explore` scanned your project and learned about it
- All your questions now include that context automatically
- The AI knows your tech stack, file structure, and patterns
- Responses are cached to save API quota

---

## Next Steps

- Type `/help` to see all commands
- Read [CLI.md](CLI.md) for full documentation
- Check [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system

---

## Troubleshooting

**"Provider not available"**
→ API key not set. Check step 3.

**"No module named..."**
→ Run `pip install -e .` from the llm_agent_team directory.

**Command not found: llm-team**
→ Run `pip install -e .` again, or use `python llm_team.py` instead.
