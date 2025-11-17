# Available LLM Models by Provider

Last updated: 2025-11-17

This document lists all models discovered from provider APIs, with emphasis on instruction-tuned variants that are better suited for structured JSON output (critical for agent tool-calling).

## Summary

| Provider | Total Models | Instruction-Tuned | Currently Configured |
|----------|-------------|-------------------|---------------------|
| Cerebras | 6 | 1 | 3 |
| Groq | 19+ | 5 | 5 |
| Gemini | 40+ | 12+ | 5 |

## Cerebras Models

**API Endpoint:** `https://api.cerebras.ai/v1`
**Env Variable:** `CEREBRAS_API_KEY`
**Free Tier:** 14,400 RPD, 60,000 TPM

### All Available Models

| Model ID | Type | Notes |
|----------|------|-------|
| `qwen-3-235b-a22b-instruct-2507` | **INSTRUCTION-TUNED** | 235B parameters, likely best for tool-calling |
| `llama3.1-8b` | Base/Chat | Fast, good quality |
| `llama-3.3-70b` | Base/Chat | Higher quality, slower |
| `qwen-3-32b` | Base/Chat | Good balance |
| `gpt-oss-120b` | Unknown | 120B parameters |
| `zai-glm-4.6` | Unknown | GLM architecture |

### Recommended for Agent

**Primary:** `qwen-3-235b-a22b-instruct-2507`
- Instruction-tuned specifically for following instructions
- Massive 235B parameters for complex reasoning
- Should excel at structured JSON output

**Fallback:** `llama-3.3-70b`
- Well-tested, reliable
- Good instruction-following

---

## Groq Models

**API Endpoint:** `https://api.groq.com/openai/v1`
**Env Variable:** `GROQ_API_KEY`
**Free Tier:** 30 RPM, varies by model (1000-14400 RPD)

### Instruction-Tuned Models (Prioritize These)

| Model ID | Parameters | RPD | Context | Notes |
|----------|-----------|-----|---------|-------|
| `meta-llama/llama-4-maverick-17b-128e-instruct` | 17B | ? | 128K | **NEW** Llama 4, latest arch |
| `meta-llama/llama-4-scout-17b-16e-instruct` | 17B | ? | 16K | **NEW** Llama 4, smaller context |
| `moonshotai/kimi-k2-instruct` | ? | ? | ? | Instruction-tuned |
| `moonshotai/kimi-k2-instruct-0905` | ? | ? | ? | Specific version |
| `qwen/qwen3-32b` | 32B | ? | ? | May be chat-tuned |

### Currently Configured Models

| Model ID | RPD | TPM | Context | Quality |
|----------|-----|-----|---------|---------|
| `llama-3.1-8b-instant` | 7000 | 20K | 131K | Good, fast |
| `llama-3.3-70b-versatile` | 1000 | 12K | 32K | Excellent |
| `llama-3.1-70b-versatile` | 1000 | 12K | 32K | Excellent |
| `mixtral-8x7b-32768` | 14400 | 5K | 32K | Very good, high quota |
| `gemma2-9b-it` | 14400 | 15K | 8K | Good, instruction-tuned |

### Other Available Models

| Model ID | Type | Notes |
|----------|------|-------|
| `allam-2-7b` | Unknown | Arabic? |
| `openai/gpt-oss-safeguard-20b` | Safety | Content moderation |
| `openai/gpt-oss-120b` | Base | Large model |
| `openai/gpt-oss-20b` | Base | Smaller variant |
| `groq/compound` | Compound | Multi-model? |
| `groq/compound-mini` | Compound | Smaller variant |
| `meta-llama/llama-guard-4-12b` | Safety | Content moderation |
| `meta-llama/llama-prompt-guard-2-86m` | Safety | Prompt injection detection |
| `meta-llama/llama-prompt-guard-2-22m` | Safety | Smaller variant |
| `playai-tts` | TTS | Text-to-speech |
| `playai-tts-arabic` | TTS | Arabic TTS |
| `whisper-large-v3` | STT | Speech-to-text |
| `whisper-large-v3-turbo` | STT | Faster STT |

### Recommended for Agent

**Primary:** `meta-llama/llama-4-maverick-17b-128e-instruct`
- Latest Llama 4 architecture
- Explicitly instruction-tuned
- Large 128K context window

**Fallback:** `llama-3.3-70b-versatile`
- Proven reliability
- "Versatile" implies good instruction-following

---

## Gemini Models

**API Endpoint:** `https://generativelanguage.googleapis.com/v1beta`
**Env Variable:** `GEMINI_API_KEY`
**Free Tier:** Varies widely (50-1000 RPD)

### Instruction-Tuned Models (Gemma Series)

| Model ID | Parameters | Context | Notes |
|----------|-----------|---------|-------|
| `gemma-3-27b-it` | 27B | 131K | **Best Gemma for quality** |
| `gemma-3-12b-it` | 12B | 32K | Good balance |
| `gemma-3-4b-it` | 4B | 32K | Fast, smaller |
| `gemma-3-1b-it` | 1B | 32K | Very fast, basic |
| `gemma-3n-e4b-it` | 4B | 8K | Efficient variant |
| `gemma-3n-e2b-it` | 2B | 8K | Most efficient |

### Gemini Flash Models (Currently Configured)

| Model ID | RPD | TPD | Quality | Speed |
|----------|-----|-----|---------|-------|
| `gemini-2.5-flash-lite` | 1000 | 250K | Good | Fast |
| `gemini-2.0-flash-lite` | 200 | 1M | Moderate | Very fast |
| `gemini-2.0-flash` | 200 | 1M | Good | Fast |
| `gemini-2.5-flash` | 250 | 250K | Very good | Moderate |
| `gemini-2.0-flash-exp` | 50 | ? | Experimental | Fast |

### Premium Models (Higher Quality)

| Model ID | Context | Notes |
|----------|---------|-------|
| `gemini-2.5-pro` | 1M | Best quality |
| `gemini-2.5-pro-preview-06-05` | 1M | Latest preview |
| `gemini-2.0-pro-exp` | 1M | Experimental pro |

### Special Purpose Models

| Model ID | Purpose | Notes |
|----------|---------|-------|
| `gemini-2.0-flash-thinking-exp` | Reasoning | Chain-of-thought |
| `gemini-2.5-computer-use-preview-10-2025` | Automation | Computer control |
| `learnlm-2.0-flash-experimental` | Education | Learning assistant |
| `gemini-robotics-er-1.5-preview` | Robotics | Embodied reasoning |

### Recommended for Agent

**Primary:** `gemma-3-27b-it`
- Explicitly instruction-tuned
- Open weights (more consistent behavior)
- Large enough for complex reasoning

**Fallback:** `gemini-2.5-flash`
- Highest quality of configured models
- Good balance of speed and capability

---

## Recommendations for Agent Tool-Calling

### Best Candidates (Untested)

1. **Cerebras `qwen-3-235b-a22b-instruct-2507`**
   - Massive model specifically tuned for instructions
   - Should excel at JSON format compliance
   - Worth testing despite potential latency

2. **Groq `meta-llama/llama-4-maverick-17b-128e-instruct`**
   - Latest architecture (Llama 4)
   - Explicitly instruction-tuned
   - Fast inference on Groq

3. **Gemini `gemma-3-27b-it`**
   - Instruction-tuned open model
   - Consistent behavior
   - Google's training quality

### Known Issues with Current Setup

Based on the agent interaction analysis:

1. **Gemini models** tend to add conversational preamble
   - "I will now..." instead of pure JSON
   - This causes JSON parse failures

2. **Non-instruction-tuned models** may not respect JSON-only format
   - They explain rather than execute
   - Need stronger prompt engineering OR instruction-tuned variants

### Testing Priority

1. Test instruction-tuned models first (see `scripts/test_instruct_models.py`)
2. Measure:
   - JSON compliance (starts with `{`, no preamble)
   - Schema adherence (thought, action, parameters)
   - Correct boolean format (lowercase true/false)
   - Action selection accuracy
3. Update provider configurations based on results

### Provider Configuration Updates Needed

To use discovered models, update:

- `src/providers/cerebras_provider.py` - Add `qwen-3-235b-a22b-instruct-2507`
- `src/providers/groq_provider.py` - Add Llama 4 and Kimi K2 models
- `src/providers/gemini_provider.py` - Add Gemma instruction-tuned models

---

## Scripts for Model Evaluation

- `scripts/list_available_models.py` - Discover all models from APIs
- `scripts/test_instruct_models.py` - Test JSON compliance of instruction-tuned models
- `scripts/evaluate_models.py` - Comprehensive evaluation across all models

Run discovery:
```bash
python scripts/list_available_models.py
```

Test instruction-tuned models:
```bash
python scripts/test_instruct_models.py
```


 Best Models for Agent Tool-Calling (Considering Rate Limits)

## JSON Compliance Test Results (2025-11-17)

Tested models for structured JSON output (critical for agent tool-calling):

### Top Performers (110/100 - Perfect JSON)

| Provider | Model | Latency | RPD | Status |
|----------|-------|---------|-----|--------|
| Cerebras | `llama-3.3-70b` | 0.6s | 14,400 | **RECOMMENDED** |
| Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | 0.4s | 7,000 | **NEW - Fastest** |
| Groq | `moonshotai/kimi-k2-instruct` | 0.4s | 7,000 | **NEW** |
| Groq | `llama-3.3-70b-versatile` | 1.0s | 1,000 | Reliable |
| Cerebras | `qwen-3-235b-a22b-instruct-2507` | 1.3s | 14,400 | **NEW - Largest** |

### Problem Models (80/100 - JSON Issues)

| Provider | Model | Issue |
|----------|-------|-------|
| Gemini | `gemma-3-27b-it` | Adds markdown code fences (```json) |
| Gemini | `gemma-3-12b-it` | Adds markdown code fences |
| Groq | `qwen/qwen3-32b` | Adds `<think>` tags before JSON |

### Deprecated Models

| Model | Provider | Status |
|-------|----------|--------|
| `gemma2-9b-it` | Groq | **DECOMMISSIONED** (removed 2025-11) |

---

## Best Models for Agent Planning

### Tier 1: Primary Planner (High RPD + Perfect JSON)

**Cerebras `llama-3.3-70b`** - RECOMMENDED
- RPD: 14,400 (highest quota)
- JSON Score: 110/100 (perfect)
- Latency: 0.6s (fast)
- Already configured

**Cerebras `qwen-3-235b-a22b-instruct-2507`** - NEW
- RPD: 14,400
- JSON Score: 110/100 (perfect)
- Latency: 1.3s (slower due to size)
- Instruction-tuned, massive model

### Tier 2: Secondary Planner (Fast + Perfect JSON)

**Groq `meta-llama/llama-4-scout-17b-16e-instruct`** - NEW, FASTEST
- RPD: 7,000
- JSON Score: 110/100 (perfect)
- Latency: 0.4s (ultra-fast)
- Latest Llama 4 architecture

**Groq `moonshotai/kimi-k2-instruct`** - NEW
- RPD: 7,000
- JSON Score: 110/100 (perfect)
- Latency: 0.4s (ultra-fast)
- 131K context window

**Groq `llama-3.3-70b-versatile`**
- RPD: 1,000 (limited)
- JSON Score: 110/100 (perfect)
- Latency: 1.0s
- Already configured, reliable

### NOT RECOMMENDED for Agent Planning

**Gemini models** - JSON compliance issues
- Add markdown code fences around JSON
- Causes parse failures in agent loop
- Use for other tasks, not planning

---

## Updated Recommendation

```python
# Primary planner (best overall)
planner = "cerebras"
planner_model = "llama-3.3-70b"  # 14,400 RPD, 110/100 JSON, 0.6s

# Fast alternative (when speed matters most)
planner = "groq"
planner_model = "meta-llama/llama-4-scout-17b-16e-instruct"  # 7,000 RPD, 0.4s

# Executor (fast, high volume)
executor = "cerebras"
executor_model = "llama3.1-8b"  # 14,400 RPD, ultra-fast
```

Combined capacity: 21,400+ RPD for agent workflows

---

## Key Findings

1. **Cerebras and Groq models excel at JSON compliance** - All tested models scored 110/100
2. **Gemini models have JSON formatting issues** - They add markdown code fences
3. **Groq `gemma2-9b-it` is deprecated** - Removed from config
4. **New instruction-tuned models are available** - Llama 4, Kimi K2 added
5. **Speed vs RPD trade-off** - Groq fastest (0.4s) but lower RPD; Cerebras has highest RPD (14,400)

