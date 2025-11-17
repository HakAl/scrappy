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
