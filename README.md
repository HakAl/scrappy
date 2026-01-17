# Scrappy

[![Tests](https://github.com/HakAl/scrappy/actions/workflows/tests.yml/badge.svg)](https://github.com/HakAl/scrappy/actions/workflows/tests.yml)
[![PyPI version](https://badge.fury.io/py/scrappy-ai.svg)](https://badge.fury.io/py/scrappy-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**23,000+ free AI coding requests per day.** No subscriptions. No credit card. No geographic restrictions.

Scrappy orchestrates free-tier LLM providers (Cerebras, Groq, Gemini) into a context-aware coding assistant that understands your entire codebase.

![Scrappy showing a diff preview before applying changes](docs/images/new_ss.png)
*Scrappy shows diffs before making changes. You approve or reject each edit.*

---

## The Mission: AI for Everyone

Paid AI tools are great, but $20/month adds up. Scrappy exists for:

*   **Students** - Learn to code with AI help, without the subscription
*   **Developers in restricted regions** - Where payments are blocked or $20 is significant
*   **Frugal folks** - Build and learn without subscriptions.

### Why Scrappy?

| Tool | Cost | Context-Aware | Agent Mode | Offline Index |
|------|------|---------------|------------|---------------|
| **Scrappy** | Free | Yes | Yes | Yes |
| ChatGPT Plus | $20/mo | No | No | No |
| Claude Pro | $20/mo | Limited | Yes | No |
| GitHub Copilot | $10/mo | Yes | No | No |
| Aider | Free* | Yes | Yes | No |
| Continue | Free* | Yes | No | No |

*\* Requires your own API keys with usage-based billing. Scrappy uses providers with generous free tiers.*

---

## What You Get

- **Context-aware chat** - Scrappy indexes your codebase locally; it knows your functions, classes, and patterns
- **Agent mode** - `/agent` executes multi-step tasks with human approval at each step
- **Diff preview** - See exactly what changes before they're applied (shown above)
- **Automatic checkpoints** - Git-based rollback if anything goes wrong
- **Provider failover** - When one API hits rate limits, Scrappy switches to another
- **Offline search** - After initial setup, semantic code search runs entirely on your machine
- **Session persistence** - Conversations auto-save; pick up where you left off

---

## Quick Start

### 1. Install

```bash
pip install scrappy-ai
```

Or with a virtual environment:
```bash
# Mac/Linux
python3 -m venv venv && source venv/bin/activate && pip install scrappy-ai

# Windows (PowerShell)
python -m venv venv; .\venv\Scripts\activate; pip install scrappy-ai
```

### 2. Get Free API Keys

You need **at least one** (all three recommended for 23K+ daily requests):

| Provider | Free Tier | Get Key |
|----------|-----------|---------|
| **Cerebras** | 14,400 req/day | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| **Groq** | 7,000+ req/day | [console.groq.com](https://console.groq.com) |
| **Gemini** | 1,650 req/day | [aistudio.google.com](https://aistudio.google.com) |

No credit card required for any of them.

### 3. Run

```bash
cd your-project
scrappy
```

First run:
1. Paste your API keys (stored locally, never sent anywhere)
2. Scrappy downloads the embedding model (~33MB, one-time)
3. Your codebase indexes in the background
4. Start chatting immediately - no need to wait for indexing

---

## Usage Examples

### Chat Mode (default)
```
You: How does the authentication flow work?
You: What files handle database connections?
You: Explain the error handling in src/api/
```

### Agent Mode
```
You: /agent add input validation to the signup form
You: /agent refactor UserService to use dependency injection
You: /agent write tests for the payment module
```

Agent mode shows you each proposed change as a diff. You approve, reject, or modify before anything is written.

### Commands
```
/agent <task>    Run the coding agent with human approval
/help            Show all commands
/clear           Clear conversation history
/quit            Exit
```

See [CLI Documentation](docs/CLI.md) for the full reference.

---

## How It Works

1. **Indexing**: BGE-small embeddings (33MB, runs locally) index your codebase into LanceDB
2. **Retrieval**: Your questions trigger semantic search to find relevant code
3. **Orchestration**: Scrappy routes requests across providers, handling rate limits automatically
4. **Response**: Context-aware answers that understand your specific codebase

For the full architecture, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## FAQ


*   **Q: Is this really free?**
    *   **A:** Yes. Cerebras, Groq, and Google offer generous free tiers. Scrappy just orchestrates them intelligently.

*   **Q: What happens when rate limits hit?**
    *   **A:** Scrappy automatically fails over to the next available provider. With all three configured, you're unlikely to hit limits in normal use.

*   **Q: Is my code private?**
    *   **A:** Scrappy has no servers. Code snippets are sent to the LLM providers (Cerebras/Groq/Google) to generate responses. Check their privacy policies. The local index never leaves your machine.

*   **Q: What languages does it support?**
    *   **A:** All of them. The semantic search and LLMs are language-agnostic.

*   **Q: Does it work offline?**
    *   **A:** Chat requires internet (to reach LLM APIs). Code indexing and search are fully offline after the initial 33MB model download.

*   **Q: What if a provider removes their free tier?**
    *   **A:** Scrappy is modular. New providers can be added easily. As long as any free tier exists, Scrappy works.

---

## Requirements

- Python 3.10+
- Git (for checkpoints)
- Windows, macOS, or Linux

---

## Troubleshooting

**"No API keys configured"**
Run `scrappy` and follow the setup wizard to add at least one key.

**"Rate limit exceeded"**
Add more providers, or wait for the limit to reset (usually hourly/daily).

**Indexing seems slow**
Large codebases take time on first run. Subsequent runs are incremental and fast.

**Model download fails**
Check your internet connection. The BGE-small model downloads from Hugging Face.

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Disclaimer

Use at your own risk. Always work from a clean git state so you can revert if needed. Scrappy creates checkpoints, but git is your ultimate safety net.

---

## License

MIT License. Use it, modify it, share it.

---

**If Scrappy helps you, star the repo so others can find it.**
