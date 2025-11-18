"""
Fast research and information gathering with tool support.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, Optional

from ..classifier import ClassifiedTask, TaskType
from .base import ExecutionResult, ExecutionStrategy, OrchestratorLike


class ResearchExecutor(ExecutionStrategy):
    """
    Fast research and information gathering with tool support.

    Best for:
    - Explaining code
    - Answering questions
    - Code analysis
    - Architecture overview
    - Fetching external documentation
    - Package/dependency research

    Features:
    - Uses fastest available provider (Cerebras)
    - No file modifications (read-only tools)
    - Context-aware responses
    - Tool access: web_fetch, web_search, read_file, search_code, git tools
    - Dynamic provider selection per task
    - Automatic tool calling for information gathering
    """

    # Read-only tools available for research
    RESEARCH_TOOLS = [
        'web_fetch',
        'web_search',
        'read_file',
        'list_files',
        'list_directory',
        'search_code',
        'git_log',
        'git_diff',
        'git_blame',
        'git_show',
        'git_recent_changes',
    ]

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        preferred_provider: str = "cerebras",
        project_root: Optional[Path] = None,
        max_tool_iterations: int = 3
    ):
        self.orchestrator = orchestrator
        self.preferred_provider = preferred_provider
        self.project_root = project_root or Path.cwd()
        self.max_tool_iterations = max_tool_iterations
        self._resolved_provider: Optional[str] = None
        self._resolved_model: Optional[str] = None
        self._tool_registry = None
        self._tool_context = None

    def _setup_tools(self):
        """Initialize tool registry with read-only tools."""
        if self._tool_registry is not None:
            return

        try:
            from ..agent_tools.tools import (
                ToolRegistry,
                ToolContext,
                ReadFileTool,
                ListFilesTool,
                ListDirectoryTool,
                SearchCodeTool,
                GitLogTool,
                GitDiffTool,
                GitBlameTool,
                GitShowTool,
                GitRecentChangesTool,
            )
            from ..agent_tools.tools.web_tools import WebFetchTool, WebSearchTool

            self._tool_registry = ToolRegistry()
            self._tool_registry.register(ReadFileTool())
            self._tool_registry.register(ListFilesTool())
            self._tool_registry.register(ListDirectoryTool())
            self._tool_registry.register(SearchCodeTool())
            self._tool_registry.register(GitLogTool())
            self._tool_registry.register(GitDiffTool())
            self._tool_registry.register(GitBlameTool())
            self._tool_registry.register(GitShowTool())
            self._tool_registry.register(GitRecentChangesTool())
            self._tool_registry.register(WebFetchTool())
            self._tool_registry.register(WebSearchTool())

            self._tool_context = ToolContext(
                project_root=self.project_root,
                dry_run=False,
                orchestrator=self.orchestrator if hasattr(self.orchestrator, 'remember_file_read') else None
            )
        except ImportError as e:
            # Tools not available, proceed without them
            self._tool_registry = None
            self._tool_context = None

    def _auto_explore_if_needed(self, task: ClassifiedTask):
        """Auto-trigger codebase exploration for file-related queries."""
        # Check if this task involves file/codebase queries
        needs_exploration = (
            task.extracted_files or
            task.extracted_directories or
            any(kw in task.original_input.lower() for kw in [
                'file', 'code', 'function', 'class', 'component', 'directory', 'folder'
            ])
        )

        if not needs_exploration:
            return

        # Check if context is already explored
        try:
            context = self.orchestrator.context
            if context:
                if not context.is_explored():
                    # Trigger exploration
                    print("Auto-exploring codebase for better file resolution...")
                    context.explore(force=True)  # Force fresh scan
                elif not context.file_index:
                    # Cache exists but file_index is empty, reload
                    print("Reloading codebase file index...")
                    context.explore(force=True)

                # If we have extracted files, try to resolve their exact paths
                if task.extracted_files and context.file_index:
                    self._resolve_file_paths(task, context)

        except Exception as e:
            # If exploration fails, continue without it
            print(f"Auto-explore failed: {e}")
            pass

    def _resolve_file_paths(self, task: ClassifiedTask, context):
        """Resolve extracted file names to full paths using the file index."""
        if not hasattr(context, 'file_index') or not context.file_index:
            return

        resolved_paths = []

        for file_ref in task.extracted_files:
            # Normalize the file reference
            file_ref_lower = file_ref.lower()
            file_basename = file_ref.split('/')[-1].lower()

            # Search in all indexed files
            for file_type, files in context.file_index.items():
                for indexed_file in files:
                    indexed_lower = indexed_file.lower()
                    indexed_basename = indexed_file.split('/')[-1].lower()

                    # Match by basename (case-insensitive)
                    if indexed_basename == file_basename:
                        resolved_paths.append(indexed_file)
                    # Match by partial path
                    elif file_ref_lower in indexed_lower:
                        resolved_paths.append(indexed_file)

        # Store resolved paths in task for use in prompt building
        if resolved_paths:
            task.extracted_files = list(set(resolved_paths))  # Deduplicate

    def _generate_fallback_response(self, task: ClassifiedTask, tool_calls_made: list, conversation_history: list) -> str:
        """Generate a fallback response when LLM doesn't provide one."""
        # Extract tool results from conversation history
        results_summary = []

        for item in conversation_history:
            if item.startswith("\nTool Result:"):
                result_text = item.replace("\nTool Result:\n", "").strip()
                if result_text and len(result_text) > 10:
                    # Truncate long results
                    if len(result_text) > 500:
                        result_text = result_text[:500] + "..."
                    results_summary.append(result_text)

        if results_summary:
            # Provide a summary of what was found
            response = f"Based on the research conducted ({len(tool_calls_made)} tool calls made):\n\n"
            for i, result in enumerate(results_summary[:3], 1):
                response += f"Result {i}:\n{result}\n\n"
            return response.strip()
        else:
            # No results found
            tools_used = [tc.get('tool', 'unknown') for tc in tool_calls_made]
            return f"Research completed using {tools_used}, but no relevant information was found. The files may not exist or may not contain the requested information."

    def _get_tool_descriptions(self) -> str:
        """Generate tool descriptions for the LLM."""
        if not self._tool_registry:
            return ""

        descriptions = []
        for tool_name in self.RESEARCH_TOOLS:
            tool = self._tool_registry.get(tool_name)
            if tool:
                descriptions.append(f"- {tool.get_full_description()}")

        return "\n".join(descriptions)

    def _parse_tool_call(self, response: str) -> Optional[Dict[str, object]]:
        """Parse tool call from LLM response."""

        def fix_json_string(s: str) -> str:
            """Fix common JSON issues from LLM output."""
            # Replace Python booleans with JSON booleans
            s = re.sub(r'\bTrue\b', 'true', s)
            s = re.sub(r'\bFalse\b', 'false', s)
            s = re.sub(r'\bNone\b', 'null', s)
            # Single to double quotes (careful with apostrophes)
            s = s.replace("'", '"')
            return s

        # Look for JSON tool call pattern
        patterns = [
            r'```json\s*\n?\s*(\{[\s\S]*?\})\s*\n?```',
            r'```\s*\n?\s*(\{[\s\S]*?"tool"[\s\S]*?\})\s*\n?```',
            r'<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>',
            r'TOOL_CALL:\s*(\{[^\n]+\})',
        ]

        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    json_str = fix_json_string(match.group(1).strip())
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

        # Try to find bare JSON object with "tool" key (no code blocks)
        # This handles LLM output like: {"tool": "...", "parameters": {...}}
        try:
            # Find the start of a JSON object containing "tool"
            tool_match = re.search(r'\{\s*"tool"\s*:', response)
            if tool_match:
                start = tool_match.start()
                # Extract from { to matching }
                brace_count = 0
                end = start
                for i in range(start, len(response)):
                    if response[i] == '{':
                        brace_count += 1
                    elif response[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break

                json_str = fix_json_string(response[start:end])
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        except:
            pass

        return None

    def _execute_tool(self, tool_call: Dict[str, object]) -> str:
        """Execute a tool call and return the result."""
        tool_name = tool_call.get('tool')
        params = tool_call.get('parameters', {})

        if not tool_name:
            return "Error: No tool name specified"

        if tool_name not in self.RESEARCH_TOOLS:
            return f"Error: Tool '{tool_name}' is not available for research tasks"

        tool = self._tool_registry.get(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found"

        try:
            result = tool(self._tool_context, **params)
            # Truncate long results
            if len(result) > 10000:
                result = result[:10000] + "\n... [truncated]"
            return result
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def set_provider(self, provider_name: Optional[str], model_name: Optional[str] = None):
        """
        Set the provider to use for the next execution.

        Called by TaskRouter with resolved provider from classifier hints.
        """
        self._resolved_provider = provider_name
        self._resolved_model = model_name

    @property
    def name(self) -> str:
        return "ResearchExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.RESEARCH

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute research task with fast provider and tool support."""
        start_time = time.time()
        total_tokens = 0
        tool_calls_made = []

        # Setup tools
        self._setup_tools()

        # Auto-explore codebase if needed for file-related queries
        self._auto_explore_if_needed(task)

        try:
            # Get the provider to use (priority: resolved > preferred > brain)
            if self._resolved_provider:
                provider_to_use = self._resolved_provider
            else:
                provider_to_use = self.preferred_provider

            # Validate provider is available
            try:
                available = self.orchestrator.providers.list_available()
                if provider_to_use not in available:
                    provider_to_use = self.orchestrator.brain
            except Exception:
                provider_to_use = self.orchestrator.brain

            # Build initial research prompt with tools
            system_prompt = self._build_system_prompt()
            prompt = self._build_research_prompt(task)

            # Tool-calling loop
            conversation_history = []
            final_response = ""

            for iteration in range(self.max_tool_iterations + 1):
                # Build full prompt with history
                if conversation_history:
                    full_prompt = prompt + "\n\n" + "\n".join(conversation_history)
                else:
                    full_prompt = prompt

                # Delegate to provider
                response = self.orchestrator.delegate(
                    provider_to_use,
                    full_prompt,
                    system_prompt=system_prompt,
                    max_tokens=2000,
                    temperature=0.3,
                    use_context=True
                )

                # Extract response
                if hasattr(response, 'content'):
                    response_text = response.content
                    total_tokens += getattr(response, 'tokens_used', 0)
                else:
                    response_text = str(response)

                # Check for tool call
                tool_call = self._parse_tool_call(response_text) if self._tool_registry else None

                if tool_call and iteration < self.max_tool_iterations:
                    # Execute tool
                    tool_result = self._execute_tool(tool_call)
                    tool_calls_made.append({
                        'tool': tool_call.get('tool'),
                        'parameters': tool_call.get('parameters', {}),
                        'result_length': len(tool_result)
                    })

                    # Add to conversation history
                    conversation_history.append(f"\nTool Call: {json.dumps(tool_call)}")
                    conversation_history.append(f"\nTool Result:\n{tool_result}")

                    # Adjust continuation prompt based on remaining iterations
                    remaining = self.max_tool_iterations - iteration - 1
                    if remaining > 0:
                        conversation_history.append(f"\nYou have {remaining} tool call(s) remaining. If you have enough information to answer the user's question, provide your FINAL ANSWER now (no JSON, just plain text). Otherwise, make another tool call.")
                    else:
                        conversation_history.append("\nThis is your LAST tool call. You MUST now provide your FINAL ANSWER in plain text (no JSON, no tool calls). Summarize what you found from the tool results above.")
                else:
                    # No tool call or max iterations reached - this is the final response
                    # Remove any tool call syntax from final response
                    final_response = re.sub(r'```json\s*\n?\s*\{[^`]+\}\s*\n?```', '', response_text)
                    final_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
                    final_response = re.sub(r'TOOL_CALL:\s*\{.+?\}', '', final_response, flags=re.DOTALL)
                    # Remove role-played tool calls (LLM describing what it would do)
                    final_response = re.sub(r'Tool Call:\s*\{[^}]+\}.*?(?=\n\n|\Z)', '', final_response, flags=re.DOTALL)
                    # Remove bare JSON tool calls (LLM outputting raw JSON in final response)
                    # Handle nested braces by matching lines that look like tool calls
                    lines = final_response.split('\n')
                    cleaned_lines = []
                    for line in lines:
                        # Skip lines that are just JSON tool calls
                        if line.strip().startswith('{"tool"'):
                            continue
                        cleaned_lines.append(line)
                    final_response = '\n'.join(cleaned_lines)
                    final_response = re.sub(r'Please wait for the result\.\.\.', '', final_response)
                    final_response = re.sub(r'Tool Result:\s*\n*', '', final_response)
                    final_response = re.sub(r'\n{3,}', '\n\n', final_response)  # Clean up excessive newlines
                    final_response = final_response.strip()

                    # If response is empty after cleanup but we have tool results, generate a summary
                    if not final_response and tool_calls_made:
                        final_response = self._generate_fallback_response(task, tool_calls_made, conversation_history)

                    break

            # Clear resolved provider after use
            self._resolved_provider = None
            self._resolved_model = None

            execution_time = time.time() - start_time

            return ExecutionResult(
                success=True,
                output=final_response,
                execution_time=execution_time,
                tokens_used=total_tokens,
                provider_used=provider_to_use,
                metadata={
                    "task_type": "research",
                    "complexity": task.complexity_score,
                    "tool_calls": tool_calls_made,
                    "iterations": len(tool_calls_made) + 1
                }
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Research execution failed: {str(e)}",
                execution_time=time.time() - start_time,
                metadata={"tool_calls": tool_calls_made}
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt with tool instructions."""
        base_prompt = "You are a helpful research assistant. Provide concise, accurate information."

        if self._tool_registry:
            tool_desc = self._get_tool_descriptions()
            return f"""{base_prompt}

IMPORTANT: You have access to tools for fetching real information. USE THEM when asked to fetch, check, or look up external data.

Available tools:
{tool_desc}

HOW TO USE TOOLS:
When you need information (package versions, documentation, web content, or codebase details), respond ONLY with:
```json
{{"tool": "tool_name", "parameters": {{"param1": "value1"}}}}
```

EXAMPLES FOR WEB/EXTERNAL INFO:
- User asks about Django version -> Use: {{"tool": "web_search", "parameters": {{"registry": "pypi", "query": "django"}}}}
- User asks about React package -> Use: {{"tool": "web_search", "parameters": {{"registry": "npm", "query": "react"}}}}
- User asks to fetch from URL -> Use: {{"tool": "web_fetch", "parameters": {{"url": "https://..."}}}}
- User asks about scikit-learn docs -> Use: {{"tool": "web_fetch", "parameters": {{"url": "https://scikit-learn.org/stable/api/index.html"}}}}

EXAMPLES FOR CODEBASE SEARCHES:
- User asks about "frontend/App.js" -> Use: {{"tool": "search_code", "parameters": {{"pattern": "register", "file_pattern": "**/App.js"}}}}
- User asks "does app.js have X" -> Use: {{"tool": "search_code", "parameters": {{"pattern": "X", "file_pattern": "**/*.js"}}}}
- User asks about a class -> Use: {{"tool": "search_code", "parameters": {{"pattern": "ClassName", "search_type": "class", "file_pattern": "**/*.py"}}}}
- User mentions specific file -> Use: {{"tool": "read_file", "parameters": {{"file_path": "frontend/src/App.js"}}}}
- User asks about directory -> Use: {{"tool": "list_directory", "parameters": {{"path": "frontend", "depth": 3}}}}

IMPORTANT FOR FILE SEARCHES:
- Use "**/" prefix for RECURSIVE search (e.g., "**/App.js" finds frontend/src/App.js)
- File patterns are CASE-SENSITIVE, so use "**/[Aa]pp.js" or "**/*.js" if unsure
- When user mentions a directory path like "frontend/", check that directory first with list_directory
- If searching for text in a specific file, use search_code with that exact file pattern

CRITICAL RULES:
1. If the user asks to FETCH, CHECK, or LOOK UP external info, you MUST use a tool first
2. If the user asks about FILES, CODE, or DIRECTORIES in the project, use search_code, read_file, or list_directory
3. Do NOT give generic advice - USE THE TOOLS to get real data
4. After receiving tool results, provide a helpful summary
5. Only give your final answer (without tool calls) after you have the information"""
        else:
            return base_prompt

    def _build_research_prompt(self, task: ClassifiedTask) -> str:
        """Build optimized prompt for research tasks."""
        # Get context if available
        context_info = ""
        try:
            context = self.orchestrator.context
            if context and hasattr(context, 'get_summary') and context.is_explored():
                summary = context.get_summary()
                if summary:
                    context_info = f"\n\nProject Context:\n{summary}\n"
        except Exception:
            pass

        tool_hint = ""
        if self._tool_registry:
            # Detect if this likely needs web tools or codebase tools
            lower_input = task.original_input.lower()
            original_input = task.original_input

            needs_web = any(kw in lower_input for kw in [
                'fetch', 'look up', 'latest', 'version', 'pypi', 'npm',
                'github.com', 'documentation', 'website', 'url', 'http'
            ])

            # Detect codebase/file queries
            needs_codebase = any([
                # File extension mentions
                any(ext in lower_input for ext in ['.js', '.py', '.ts', '.tsx', '.jsx', '.java', '.cpp', '.rs', '.go', '.rb', '.php', '.css', '.html', '.json', '.yaml', '.yml', '.md']),
                # File path patterns
                '/' in original_input and not 'http' in lower_input,
                # Keywords indicating file/code queries
                any(kw in lower_input for kw in [
                    'file', 'directory', 'folder', 'codebase', 'source', 'frontend', 'backend', 'src/',
                    'does the', 'is there', 'where is', 'find the', 'show me', 'check if', 'contain',
                    'have a', 'has a', 'include', 'import'
                ])
            ])

            if needs_web:
                tool_hint = "\n\nIMPORTANT: This request requires fetching external information. You MUST use a tool (web_fetch or web_search) to get real data. Respond with a JSON tool call first."
            elif needs_codebase:
                # Use extracted file references from task classification
                file_hints = []

                if task.extracted_files:
                    file_hints.append(f"Detected file reference(s): {', '.join(task.extracted_files)}")
                    # Suggest search patterns
                    for f in task.extracted_files[:2]:
                        basename = f.split('/')[-1]
                        file_hints.append(f"  -> To search in {basename}, use file_pattern: \"**/{basename}\"")

                if task.extracted_directories:
                    file_hints.append(f"Detected directory reference(s): {', '.join(task.extracted_directories)}")
                    for d in task.extracted_directories[:2]:
                        file_hints.append(f"  -> To explore {d}/, use: list_directory with path=\"{d}\"")

                hint_text = "\n".join(file_hints) if file_hints else ""
                if hint_text:
                    hint_text = f"\n{hint_text}"

                tool_hint = f"""\n\nIMPORTANT: This request is about the LOCAL CODEBASE. You MUST use file/search tools to answer:
- Use search_code to find text patterns (with file_pattern like "**/*.js" for recursive search)
- Use read_file to read specific files
- Use list_directory to explore directories
{hint_text}
Respond with a JSON tool call FIRST, do not guess or make assumptions about file contents."""
            else:
                tool_hint = "\n\nYou have tools available if you need to fetch external information or search the codebase."

        return f"""User Request:
{task.original_input}
{context_info}{tool_hint}

Respond appropriately. If information is needed, use a tool first."""
