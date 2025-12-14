  Model Grouping Analysis

  Current Requirement

  MIN_CONTEXT_FOR_BRAIN = 32768 (32k) - Quality/planner tasks require this.

  Context Length by Provider

  Cerebras (all models 8k - NONE meet 32k requirement):
  | Model                     | Context | Speed      | Quality   |
  |---------------------------|---------|------------|-----------|
  | llama3.1-8b               | 8,192   | ULTRA_FAST | GOOD      |
  | llama-3.3-70b             | 8,192   | VERY_FAST  | EXCELLENT |
  | qwen-3-32b                | 8,192   | VERY_FAST  | VERY_GOOD |
  | qwen-3-235b-a22b-instruct | 8,192   | FAST       | EXCELLENT |

  Groq (several meet 32k+):
  | Model                   | Context | Speed      | Quality   |
  |-------------------------|---------|------------|-----------|
  | llama-3.1-8b-instant    | 131,072 | VERY_FAST  | GOOD      |
  | llama-3.3-70b-versatile | 32,768  | FAST       | EXCELLENT |
  | llama-3.1-70b-versatile | 32,768  | FAST       | EXCELLENT |
  | mixtral-8x7b-32768      | 32,768  | FAST       | VERY_GOOD |
  | kimi-k2-instruct        | 131,072 | ULTRA_FAST | EXCELLENT |

  Gemini (context not in MODELS dict, but known ~1M):
  | Model            | Context | Speed    | Quality   |
  |------------------|---------|----------|-----------|
  | gemini-2.5-flash | ~1M     | MODERATE | VERY_GOOD |
  | gemini-2.0-flash | ~1M     | FAST     | GOOD      |

  ---
  Problem Found

  The plan has cerebras/llama-3.3-70b in quality tier - but it only has 8k context!

  This violates the 32k requirement for quality/planner tasks.

  ---
  Recommended Model Groups

  "fast" tier (speed priority, any context OK):
  # Priority order
  1. groq/llama-3.1-8b-instant     # 128k, VERY_FAST, GOOD - best fast option!
  2. cerebras/llama3.1-8b          # 8k, ULTRA_FAST, GOOD - fallback

  "quality" tier (quality priority, >= 32k context required):
  # Priority order
  1. gemini/gemini-2.5-flash           # ~1M context, VERY_GOOD
  2. groq/llama-3.3-70b-versatile      # 32k context, EXCELLENT
  3. groq/moonshotai/kimi-k2-instruct  # 128k context, EXCELLENT, INSTRUCT

  NOT in quality tier:
  - cerebras/llama-3.3-70b - Only 8k context despite EXCELLENT quality
  - cerebras/qwen-3-235b-a22b-instruct - Only 8k context despite EXCELLENT quality

  ---
  Decision Point

Strict 32k requirement
  - Remove all Cerebras from quality tier
  - Quality tier = Gemini + Groq 70B models only

