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

### Native Tool Calling Integration

  Key Integration Points in core.py

  1. AgentThought (types.py:12)
  - Only stores raw_response: str
  - Needs to also store the full LLMResponse object for native tool calls

  2. _think() method (core.py:865)
  - Returns AgentThought(raw_response=response.content, ...)
  - Only passes text content, discards tool_calls
  - Needs to detect if provider supports native tools and call chat_with_tools()

  3. _plan_action() method (core.py:946)
  - Uses self._response_parser.parse(thought.raw_response) - text only
  - Needs to check if response has tool_calls and use NativeToolCallParser.parse_response()

  4. OrchestratorAdapter (orchestrator_adapter.py:37)
  - delegate() returns simplified LLMResponse without tool_calls
  - No delegate_with_tools() method
  - Creates its own LLMResponse that strips native tool info

  5. System prompt (core.py:1335)
  - Includes JSON response format instructions
  - Native tool calling doesn't need those instructions





  1. Extend AgentThought - Add llm_response: Optional[LLMResponse] = None
  2. Add adapter method - Implement delegate_with_tools() in OrchestratorAdapter that passes through to provider's
  chat_with_tools()
  3. Modify _think() - Check provider capability, call appropriate method, store full response
  4. Modify _plan_action() - Detect native tool response, use appropriate parser
  5. Update system prompt - Skip JSON format instructions when using native tools
  6. Handle run_command - Not in registry, needs manual schema addition

  The complexity arises from:
  
  - Need to maintain backward compatibility with providers that don't support native tools



src\agent\core.py
  refactor out: plan, retry

  insanity: _tool_run_command --> hardcoded to catch spring dls exactly? npm?
