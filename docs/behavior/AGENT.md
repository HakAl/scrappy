Path escaping/construction.
- tests\test_agent_path_escaping.py

  The agent will now receive a clear error message instead of a cryptic "not recognized" failure.

## System Prompt

tests\test_prompt_builder.py

### PromptBuilder Service

The PromptBuilder should consume CodebaseContext rather than duplicate detection logic. 

  src/agent/prompt_builder.py
  ├── PlatformSection      # Windows cmd.exe, Unix shells
  ├── ProjectTypeSection   # Python, Java, Node.js specific
  ├── ToolCapabilities     # What tools can actually do
  ├── SafetyRules          # Platform-specific gotchas
  └── TaskContext          # Current task requirements


### Context Detection Pipeline


```DetectPlatform → DetectProjectType → DetectInstalledTools → BuildPrompt```

  PromptBuilder service with context-aware sections:

  1. Move prompt construction out of core.py entirely
  2. Create src/agent/prompt_builder.py with composable sections
  3. Detect context at agent startup (platform, project type from package.json/pom.xml/requirements.txt)
  4. Only include relevant guidance


src\agent\core.py
  refactor out: parse, plan, retry

  insanity: _tool_run_command --> hardcoded to catch spring dls exactly? npm?




  
● Integration Complete

  PromptBuilder is now integrated into src/agent/core.py:

  Changes:
  1. Replaced hardcoded platform guidance (94 lines) with PromptBuilder
  2. System prompt now dynamically includes:
    - Platform-specific commands (Windows cmd.exe vs Unix)
    - Project-type-specific guidance (Python, Java, Node.js, etc.)
    - Custom tool descriptions section
    - Operational guidelines (task completion, write_file rules)
    - Task context

  Benefits:
  - Removed ~100 lines of hardcoded Spring Boot examples
  - Platform guidance is now succinct and accurate for the current environment
  - Project type detection happens automatically via CodebaseContext
  - No more irrelevant framework examples (e.g., no Spring Boot advice for Python projects)
  - Prompt size reduced from ~2000 chars to context-appropriate size

  Code Flow:
  prompt_builder = PromptBuilder(context=self.orch.context)
  prompt_builder.add_section('tools', tool_descriptions)
  prompt_builder.add_section('operational_guidelines', operational_guidance)
  system_prompt = prompt_builder.build(task=task)