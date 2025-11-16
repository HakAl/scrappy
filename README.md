# LLM Team - Free AI Coding Assistant

> **A coding assistant for everyone** - students, developers in any region, anyone who can't afford paid AI subscriptions.

> "For Users Without Claude Subscription: Yes, Useful"

Get AI-powered coding help with **23,000+ free requests per day**. No credit card needed. No geographic restrictions.

---

## Why This Exists

Paid AI tools like ChatGPT Plus ($20/month) and Claude Pro ($20/month) are out of reach for many:
- **Students** learning to code
- **Developers in regions** where payments are blocked or $20/month is significant money  
- **Anyone** who wants to learn but is locked out by paywalls

**LLM Team makes AI coding assistance accessible to everyone** by combining multiple free-tier AI providers into one powerful tool.

---

## What You Get

✅ **23,000+ free AI requests per day** - enough for serious development work  
✅ **No payment required** - completely free, just need free API keys  
✅ **AI code writing** - writes code for you with your approval  
✅ **Smart about your project** - automatically understands your codebase  
✅ **Multiple AI models** - uses the best free model for each task  
✅ **Works offline-first** - caches responses to save your quota  

---

## Quick Start (5 Minutes)

### 1. Install
```bash
git clone https://github.com/HakAl/llm_agent_team
cd llm_agent_team
pip install -e .
```

### 2. Get Free API Keys

**You need at least ONE of these** (all are free, no credit card):

| Provider | How to Get Key | Daily Limit |
|----------|---------------|-------------|
| **Cerebras** | [cloud.cerebras.ai](https://cloud.cerebras.ai) → Sign up → Copy key | 14,400 requests |
| **Groq** | [console.groq.com](https://console.groq.com) → Create account → API Keys | 7,000 requests |
| **Gemini** | [aistudio.google.com](https://aistudio.google.com) → Get API Key | 1,650 requests |

**Tip**: Get all three for maximum free requests!

### 3. Add Keys to Your Environment

```bash
export CEREBRAS_API_KEY=your_key_here
export GROQ_API_KEY=your_key_here
export GEMINI_API_KEY=your_key_here
```

Or create a `.env` file:
```
CEREBRAS_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

### 4. Start Coding with AI

```bash
# Navigate to your project
cd ~/my-project

# Start the assistant (it learns about your code automatically)
llm-team --auto-explore
```

Now you can:
- Ask coding questions: `How do I add authentication?`
- Get code written: `/agent Add rate limiting to my API`
- Understand codebases: `Explain how the auth module works`
- Plan features: `/plan Build a user profile page`

---

## Real Examples

### Example 1: Ask a Question
```
You: How should I structure my database models for a blog?

AI: Based on your project, I'd recommend:
- User model (id, username, email, password_hash)
- Post model (id, title, content, user_id, created_at)
- Comment model (id, content, user_id, post_id, created_at)

Would you like me to write the code for these models?
```

### Example 2: Let AI Write Code
```
You: /agent Add input validation to my signup form

Code Agent: I'll add validation for email and password. 
Allow me to modify signup.js? [y/N]: y

✓ Added email format validation
✓ Added password strength requirements  
✓ Added error message display

Task completed in 3 iterations!
```

### Example 3: Understand Existing Code
```
You: Explain how authentication works in this app

AI: [Reads your codebase automatically]
Your app uses JWT tokens stored in localStorage...
[Detailed explanation based on YOUR actual code]
```

---

## Who This Is For

### ✅ Perfect for:
- **Students** - Learn coding with AI help without paying subscriptions
- **International developers** - No payment restrictions, works anywhere
- **Beginners** - Get explanations and working code examples  
- **Budget-conscious developers** - 23K free requests/day is serious capacity
- **Learning projects** - Build without worrying about API costs

### ⚠️ Maybe not ideal for:
- **Production apps needing 24/7 uptime** - Free tiers can change
- **Enterprise teams** - Consider paid options with SLAs
- **If you already pay for Claude/GPT Plus** - Just use those directly

---

## How It Works

Instead of relying on one expensive AI:
1. **Uses multiple free AI providers** (Cerebras, Groq, Gemini)
2. **Routes tasks intelligently** - fast model for simple tasks, smart model for complex
3. **Understands your codebase** - automatically learns your project structure
4. **Caches responses** - saves your quota by not re-asking same questions
5. **Stays within free limits** - auto-switches providers when one hits limits

---

## Common Questions

**Q: Is this really free?**  
A: Yes! All the AI providers offer generous free tiers. No credit card needed.

**Q: What if free tiers disappear?**  
A: The tool is designed to easily add new providers. As long as ANY free tier exists, it works.

**Q: Can I use my own paid API keys?**  
A: Yes! You can use OpenAI, Anthropic, or any paid provider alongside the free ones.

**Q: Will my code be kept private?**  
A: Your code never leaves your machine. Only prompts are sent to AI providers (check each provider's privacy policy).

**Q: What languages/frameworks does it support?**  
A: All of them! Works with any codebase - Python, JavaScript, Java, Go, Rust, etc.

**Q: Do I need to know how to use terminal/command line?**  
A: Basic terminal knowledge helps, but the quickstart above is all you need.

---

## Available Commands

Once running, type `/help` to see all commands:

```
/agent <task>          - Let AI write code (you approve each step)
/plan <task>          - Break down a complex task into steps  
/reason <question>    - Deep analysis with evidence-based reasoning
/explore [path]       - Understand a codebase
/context             - See what the AI knows about your project
/help                - Show all commands
```

---

## Installation Details

### Requirements
- Python 3.10 or newer
- pip (Python package manager)
- At least one free API key (see Quick Start above)

### Full Installation
```bash
# Clone the repository
git clone https://github.com/HakAl/llm_agent_team
cd llm_agent_team

# Install (makes 'llm-team' command available everywhere)
pip install -e .

# Verify installation
llm-team --help
```

### Setting Up API Keys

**Option 1: Environment Variables** (recommended)
```bash
export CEREBRAS_API_KEY=your_key
export GROQ_API_KEY=your_key  
export GEMINI_API_KEY=your_key
```

**Option 2: .env File** (easier for beginners)
Create a file named `.env` in the project folder:
```
CEREBRAS_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

---

## Safety Features

When AI writes code, you stay in control:

✅ **Human approval required** - You approve EVERY file change  
✅ **Git checkpoints** - Easy rollback if something goes wrong  
✅ **Sandboxed** - AI can only modify your project folder  
✅ **Audit logging** - See exactly what changed  
✅ **Dry-run mode** - Preview changes without applying them

---

## Get Help

- **Issues?** [Open an issue on GitHub](https://github.com/HakAl/llm_agent_team/issues)
- **Questions?** Check the [documentation](https://github.com/HakAl/llm_agent_team/tree/main/docs)
- **Want to contribute?** PRs welcome!

---

## The Mission

**AI coding tools shouldn't be locked behind paywalls.**

Students in developing countries, broke college students, self-taught developers - everyone deserves access to AI-powered learning tools.

This project exists to keep AI coding assistance free and accessible while commercial tools become increasingly expensive.

As long as free AI tiers exist, we'll make them work better for people who need them most.

---

## Technical Details (For Developers)

<details>
<summary>Click to expand architecture and advanced usage</summary>

### Architecture
- Multi-provider orchestration with intelligent routing
- Task classification (direct execution, research, or full agent)
- Automatic codebase context extraction
- Response caching to minimize API calls
- Session persistence across restarts

### Provider Details
| Provider | RPD | Tokens/Min | Use Case |
|----------|-----|------------|----------|
| Cerebras | 14,400 | 60,000 | Fast execution, primary workhorse |
| Groq | 7,000+ | 20,000 | Secondary, model variety |
| Gemini | 1,650 | - | Complex reasoning, overflow |

### Extending
Add new providers by implementing the `LLMProvider` interface:
```python
class NewProvider(LLMProvider):
    def chat(self, messages, **kwargs):
        # Your implementation
        pass
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

### API Usage (Python)
```python
from src.orchestrator import AgentOrchestrator

# Initialize
orch = AgentOrchestrator(auto_explore=True)

# Plan a task
steps = orch.plan("Add user authentication")

# Delegate to specific provider  
result = orch.delegate('cerebras', 'Explain this code')

# Smart delegation (auto-selects best provider)
result = orch.delegate_smart('Complex task', task_type='quality')
```

</details>

---

## License

MIT - Use it, modify it, share it. Help others access AI.

---

## Star History

If this helps you, give it a ⭐ so others can find it!

**Built with the belief that education and tools should be accessible to all.**