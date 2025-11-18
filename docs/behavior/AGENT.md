
<!-- EXISITING ISSUE -->
- 2 audit logs created: 
  - .agent_audit.json
  - .llm_agent_audit.json
- Premature Task Completion: Agent stops after 4 iterations (7 seconds), completing ~5% of the task and declaring success
  - Naive Completion Detection: Any write_file operation triggers "task complete"
- No Task Decomposition: Doesn't break complex tasks into tracked subtasks
- Complex Import Structure: Relative imports fail when using programmatically

<!-- todo -->
- Agent composition - Chain multiple specialized agents


## Architecture

### Path escaping/construction.

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

### Native Tool Calling Integration

**Key Integration Points**
  - Providers: src\providers\cohere_provider.py, src\providers\groq_provider.py
    - chat_with_tools()
  - Orchestrator: src\orchestrator_adapter.py
    - delegate_with_tools()
  - PromptBuilder: src\agent\prompt_builder.py
    - skip JSON when using native tools
  - ResponseParser: src\agent\response_parser.py
    - UnifiedResponseParser, NativeToolCallParser
  - Agent: src\agent\core.py
    - AgentThought, _think(), _plan_action()



