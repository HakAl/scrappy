---
COMPLETED - GitHub Models should be blocked specifically from agent/planner roles, not removed entirely.

Add to provider metadata - Mark GitHub Models as supports_agent=False and have provider selector respect it

Make it clear to users that Github has valuable models, but cannot be used with agent.
---

## Proposed Plan

### Problem
GitHub Models is completely excluded from brain/planner roles via hardcoded logic:
- `config.py:70-72` - `brain_priority` list doesn't include `github_models`
- `provider_selector.py:156-157` - Comment explaining exclusion
- Task preferences also exclude it

This makes GitHub's valuable models (GPT-4o, DeepSeek R1, Grok-3, Llama 4) unavailable for general use even though they're fine for non-agent tasks.

### Solution: Provider Capability Metadata

Add `supports_agent_role: bool` property to provider base class. This:
- Is defined on the provider itself (not hardcoded in selector)
- Can be respected by ProviderSelector when selecting for agent/brain roles
- Is reusable for future providers with similar limitations
- Allows GitHub Models to still be used for general non-agent tasks

### Implementation Steps

1. **Add `supports_agent_role` property to `LLMProviderBase`** (`src/providers/base.py`)
   - Default: `True`
   - Place after `supports_tool_calling` for consistency

2. **Override in `GitHubModelsProvider`** (`src/providers/github_models_provider.py`)
   - Set `supports_agent_role = False`

3. **Update `ProviderSelector`** (`src/orchestrator/provider_selector.py`)
   - `setup_brain()`: Filter candidates by `supports_agent_role`
   - `select_for_planning()`: Same filtering
   - Remove hardcoded comments about GitHub exclusion

4. **Update `OrchestratorConfig`** (`src/orchestrator/config.py`)
   - Add `github_models` to `brain_priority` and `task_preferences`
   - Selector will filter based on capability, not config exclusion
   - Update `provider_info` description for GitHub

5. **Add tests** (`tests/`)
   - Test that providers with `supports_agent_role=False` are excluded from brain selection
   - Test that they're still available for general provider list

### User Communication

**Scenario 1: User explicitly requests `--brain github`**
- In `setup_brain()`, check `supports_agent_role` before accepting user preference
- If False, warn user and fall back to auto-selection:
  ```
  [WARN] github does not support agent/brain roles (aggressive rate limiting)
  [WARN] Falling back to auto-selection...
  [SELECTED] Using cerebras as brain
  ```

**Scenario 2: Status display (`--verbose`)**
- In `ProviderStatusReporter.print_status()`, show capability alongside availability:
  ```
  Provider Status:
    [OK] github_models    - 10K RPD (general use only - not for agent/brain)
    [OK] cerebras         - 14,400 RPD - highest daily quota
    ...
  ```

**Scenario 3: Provider info descriptions**
- Update `provider_info` in config to clarify:
  ```python
  'github_models': ProviderInfo(
      quota='10K RPD',
      description='available for general use, not for agent/brain roles',
  )
  ```

### Files to Modify
- `src/providers/base.py` - Add property to LLMProviderBase
- `src/providers/github_models_provider.py` - Override property
- `src/orchestrator/provider_selector.py` - Respect property in selection logic, warn on explicit request
- `src/orchestrator/config.py` - Include github_models in priorities, update description
- `src/orchestrator/status_reporter.py` - Show capability in status display
- `tests/` - Add capability filtering tests