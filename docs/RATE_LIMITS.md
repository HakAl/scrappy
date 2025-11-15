# Free Tier Rate Limits Reference

Last updated: 2025-11-15

## Active Providers

### Cerebras (RECOMMENDED - Best free tier)
- **API Key**: CEREBRAS_API_KEY
- **Dashboard**: https://cloud.cerebras.ai
- **Docs**: https://inference-docs.cerebras.ai

| Model | RPD | TPM | Notes |
|-------|-----|-----|-------|
| llama3.1-8b | 14,400 | 60,000 | Primary workhorse |
| llama3.1-70b | TBD | TBD | Larger model available |

**Best for**: High-volume tasks, extremely fast inference (specialized hardware)

### Groq (Secondary)
- **API Key**: GROQ_API_KEY
- **Dashboard**: https://console.groq.com

| Model | RPM | RPD | TPM | TPD |
|-------|-----|-----|-----|-----|
| llama-3.1-8b-instant | 30 | 7,000 | 20K | 200K |
| llama-3.3-70b-versatile | 30 | 1,000 | 12K | 100K |
| llama-3.1-70b-versatile | 30 | 1,000 | 12K | 100K |
| mixtral-8x7b-32768 | 30 | 14,400 | 5K | - |
| gemma2-9b-it | 30 | 14,400 | 15K | - |

**Best for**: Backup to Cerebras, model variety

### Gemini (Auto-fallback)
- **API Key**: GEMINI_API_KEY
- **Dashboard**: https://aistudio.google.com
- **Special feature**: Auto-fallback between models on rate limits

| Model | RPM | RPD | TPD | Notes |
|-------|-----|-----|-----|-------|
| gemini-2.5-flash-lite | 15 | 1,000 | 250K | Highest quota (default) |
| gemini-2.0-flash-lite | 30 | 200 | 1M | Very fast |
| gemini-2.0-flash | 15 | 200 | 1M | Good quality |
| gemini-2.5-flash | 10 | 250 | 250K | Best quality |

**Best for**: Additional capacity, auto-fallback when other providers limited

### Cohere (USE SPARINGLY)
- **API Key**: COHERE_API_KEY
- **Dashboard**: https://dashboard.cohere.com

| Endpoint | Trial RPM | Production RPM | Monthly Limit |
|----------|-----------|----------------|---------------|
| Chat | 20 | 500 | **1,000 total** |
| Embed | 100 | 2,000 | **1,000 total** |
| Rerank | 10 | 1,000 | **1,000 total** |

**CRITICAL**: Trial key is limited to **1,000 API calls PER MONTH** across ALL endpoints!

**Best for**: Embeddings (if you have prod key), one-off reasoning tasks

---

## Providers to Investigate

### OpenRouter ⚠️ UNRELIABLE
- **URL**: https://openrouter.ai
- **Free models**: 45+ models marked as free
- **Issue**: Free models frequently rate-limited upstream or have data policy restrictions
- **Verdict**: Not reliable for production use. Skip for now.

### HuggingFace Inference API ❌ NOT VIABLE
- **URL**: https://huggingface.co/inference-api
- **Free tier**: $0.10/month credits only (~100-1000 requests)
- **Models**: Llama-3.2-3B, Qwen2.5-72B, Gemma-2-2b work
- **Verdict**: Too limited for multi-agent use. Skip.

### Together AI
- **URL**: https://together.ai
- **Free credits**: $25 on signup (not truly free tier)
- **Models**: Llama, Mistral, others
- **Potential**: Good quality, but credits run out

### Fireworks AI
- **URL**: https://fireworks.ai
- **Free credits**: $1 on signup
- **Speed**: Very fast inference
- **Potential**: Good for latency-sensitive tasks

### SambaNova ❌ NOT VIABLE
- **URL**: https://sambanova.ai
- **Free tier**: **40 requests/day** only
- **Models**: Meta-Llama-3.1-8B-Instruct works
- **Verdict**: Too limited. Skip.

---

## Usage Strategy

### Daily Budget (with current providers)

**Cerebras** (primary workhorse):
- 14,400 requests/day with llama3.1-8b
- 60,000 tokens/minute
- Use for: High-volume tasks, fast inference needs

**Groq** (secondary):
- 7,000 requests/day with llama-3.1-8b-instant
- Use for: Backup when Cerebras limits hit, model variety
- Reserve llama-3.3-70b (1000/day) for quality-critical tasks

**Cohere** (emergency only):
- 1,000 requests/month = ~33/day
- Use for: Embeddings only (if needed)
- Avoid using for chat - too expensive

**Gemini** (additional capacity):
- ~1,650 requests/day across models (with fallback)
- Use for: Extra capacity when Cerebras/Groq hit limits
- Auto-fallback handles rate limits automatically

**Orchestrator Brain** (Cerebras/Groq/Gemini):
- Complex reasoning, planning, synthesis
- Orchestrating the team
- Can run autonomously without Claude Code

**Combined capacity**: ~23,000 requests/day (Cerebras + Groq + Gemini)

### Example Daily Workflow

Morning (light usage):
- 50 Cerebras calls for routine tasks
- 20 Groq calls for variety
- 0 Cohere calls

Afternoon (heavy development):
- 200 Cerebras calls for code generation
- 50 Groq calls for different models
- 30 Gemini calls for overflow

Evening (wrap-up):
- 50 Cerebras calls for summaries
- 10 Groq calls for final checks

**Total**: 300 Cerebras, 80 Groq, 30 Gemini
**Remaining**: 14,100 Cerebras, 6,920 Groq, 1,620 Gemini

### Heavy Usage Day (Intensive Development)

- 2,000 Cerebras calls (14% of daily limit)
- 500 Groq calls (7% of daily limit)
- 200 Gemini calls (12% of daily limit)

**Still have**: 12,400 Cerebras, 6,500 Groq, 1,450 Gemini remaining

---

## Monitoring Usage

### Persistent Rate Limit Tracking (NEW)

The orchestrator now includes **persistent rate limit tracking** that survives restarts:

**CLI Commands:**
```bash
# View all rate limit usage
/limits

# View specific provider
/limits cerebras

# Reset tracking data
/limits reset
```

**Programmatic Access:**
```python
from src.orchestrator import AgentOrchestrator

orch = AgentOrchestrator()

# Get comprehensive rate limit status
status = orch.get_rate_limit_status()
# Returns: providers, usage today/month, remaining quotas, limits

# Check remaining quota for specific provider
remaining = orch.get_remaining_quota('cerebras')
# Returns: requests_remaining_today, tokens_remaining_today, etc.

# Get warnings for approaching limits
warnings = orch.check_rate_limit_warnings()
# Returns: List of warning messages when >90% of limit used

# Reset tracking
orch.reset_rate_tracking()  # Reset all
orch.reset_rate_tracking('groq')  # Reset specific provider
```

**Features:**
- Tracks requests and tokens per provider/model
- Persists to `.llm_rate_limits.json`
- Auto-resets daily limits at midnight
- Auto-resets monthly limits on month change
- Warns when approaching rate limits (90% threshold)
- Color-coded usage display in CLI

**Tracking File:**
```json
{
  "providers": {
    "cerebras": {
      "llama3.1-8b": {
        "requests_today": 150,
        "tokens_today": 45000,
        "requests_this_month": 2500,
        "total_requests": 10000,
        "last_request": "2025-11-15T14:30:00"
      }
    }
  },
  "last_reset": {
    "daily": "2025-11-15",
    "monthly": "2025-11"
  }
}
```

### Provider-Specific Headers

**Cerebras:**
- `x-ratelimit-remaining-requests-day`
- `x-ratelimit-remaining-tokens-minute`

**Groq:**
- `x-ratelimit-remaining-requests`
- `x-ratelimit-remaining-tokens`

**Gemini:**
Auto-tracked internally:
- `provider.get_usage_summary()` - shows model usage and limited models

**Cohere:**
- `x-endpoint-monthly-call-limit`
- `x-trial-endpoint-call-remaining`

### Legacy Monitoring

Monitor in code:
```python
from src.orchestrator import AgentOrchestrator

orch = AgentOrchestrator()
print(orch.status())          # Shows brain, available providers
print(orch.get_usage_report()) # Shows session usage by provider
```

---

## When You Hit Limits

1. **Cerebras daily limit**: Switch to Groq (7,000 RPD remaining)
2. **Groq daily limit**: Switch to Gemini (auto-fallback)
3. **Gemini limit**: Auto-fallback tries other Gemini models
4. **All limits hit**: Wait for midnight reset (rare with 23K combined)
5. **Cohere monthly limit**: Stop using Cohere entirely

---

## Getting More Resources

**Current capacity (23K RPD) is sufficient for most use cases.**

If you need more:
1. **Cerebras paid tier** - Contact for enterprise pricing
2. **Groq Developer tier** - $20/month for 500x limits
3. **Cohere production key** - Apply with use case
4. **Add more providers** - Fireworks ($1 credit), Together ($25 credit)
5. **Response caching** - Reduce duplicate calls (TODO: implement)
