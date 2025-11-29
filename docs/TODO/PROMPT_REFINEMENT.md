# Prompt Refinement

## Problem 1: Subclassifier Misrouting

Query "how would we add rag to this codebase?" contains "this codebase" but hit GENERAL flow instead of CODEBASE.

The regex `\b(this|our|the)\s+(project|codebase|code|repo)\b` DOES match "this codebase" (verified), so the bug is elsewhere in the routing logic.

**TODO**: Investigate why codebase match isn't being respected.

## Problem 2: Agent vs Chat Mode Confusion

Current system uses the same prompts and model configs for both:
- **Agent scenarios**: Tool calling appropriate, JSON responses expected
- **Chat scenarios**: Direct answers expected, no tool overhead needed

The aggressive tool-calling prompts cause small models (llama3.1-8b) to output ONLY JSON, which then gets stripped by response_cleaner, resulting in empty responses.

**Need**:
- Separate prompt templates for agent mode vs chat mode
- Different model selection logic based on interaction type
- Chat mode should NOT include tool-calling instructions for simple Q&A
