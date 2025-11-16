"""
Execution strategies for different task types.
Each strategy optimizes for its specific use case.
"""

import json
import re
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from pathlib import Path

from .classifier import ClassifiedTask, TaskType


@dataclass
class ExecutionResult:
    """Result from task execution."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    provider_used: Optional[str] = None


class OrchestratorLike(Protocol):
    """Protocol for orchestrator dependency."""

    def delegate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1500,
        temperature: float = 0.3,
        use_context: bool = False
    ) -> Any:
        """Delegate prompt to a provider."""
        ...

    @property
    def context(self) -> Any:
        """Get codebase context."""
        ...

    @property
    def brain(self) -> str:
        """Get the brain provider name."""
        ...

    @property
    def providers(self) -> Any:
        """Get provider registry."""
        ...


class ExecutionStrategy(ABC):
    """Abstract base for execution strategies."""

    @abstractmethod
    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute the classified task."""
        pass

    @abstractmethod
    def can_handle(self, task: ClassifiedTask) -> bool:
        """Check if this strategy can handle the task."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging."""
        pass


class DirectExecutor(ExecutionStrategy):
    """
    Direct command execution without agent loop.

    Best for:
    - pip install, npm install
    - git status, git log
    - Simple filesystem operations
    - Build commands (make, pytest)

    Features:
    - No LLM involvement
    - Immediate execution
    - Timeout protection
    - Safety checks
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 60,
        require_confirmation: bool = True
    ):
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self.require_confirmation = require_confirmation

    @property
    def name(self) -> str:
        return "DirectExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return (
            task.task_type == TaskType.DIRECT_COMMAND
            and task.extracted_command is not None
        )

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute direct command in shell."""
        if not task.extracted_command:
            return ExecutionResult(
                success=False,
                output="",
                error="No command extracted from task"
            )

        command = task.extracted_command

        # Safety check
        from .classifier import TaskClassifier
        classifier = TaskClassifier()
        if not classifier.is_safe_command(command):
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command blocked for safety: {command}"
            )

        start_time = time.time()

        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    error=result.stderr if result.stderr else None,
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "return_code": result.returncode,
                        "working_dir": str(self.working_dir)
                    }
                )
            else:
                return ExecutionResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr or f"Command failed with code {result.returncode}",
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "return_code": result.returncode
                    }
                )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command timed out after {self.timeout}s",
                execution_time=self.timeout,
                metadata={"command": command}
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                metadata={"command": command}
            )


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

    def _parse_tool_call(self, response: str) -> Optional[Dict[str, Any]]:
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

    def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
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
                    conversation_history.append("\nPlease continue your research with this information. If you have enough information, provide your final answer without any tool calls.")
                else:
                    # No tool call or max iterations reached - this is the final response
                    # Remove any tool call syntax from final response
                    final_response = re.sub(r'```json\s*\n?\s*\{[^`]+\}\s*\n?```', '', response_text)
                    final_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
                    final_response = re.sub(r'TOOL_CALL:\s*\{.+?\}', '', final_response, flags=re.DOTALL)
                    final_response = final_response.strip()
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
When you need external information (package versions, documentation, web content), respond ONLY with:
```json
{{"tool": "tool_name", "parameters": {{"param1": "value1"}}}}
```

EXAMPLES:
- User asks about Django version → Use: {{"tool": "web_search", "parameters": {{"registry": "pypi", "query": "django"}}}}
- User asks about React package → Use: {{"tool": "web_search", "parameters": {{"registry": "npm", "query": "react"}}}}
- User asks to fetch from URL → Use: {{"tool": "web_fetch", "parameters": {{"url": "https://..."}}}}
- User asks about scikit-learn docs → Use: {{"tool": "web_fetch", "parameters": {{"url": "https://scikit-learn.org/stable/api/index.html"}}}}

CRITICAL RULES:
1. If the user asks to FETCH, CHECK, or LOOK UP external info, you MUST use a tool first
2. Do NOT give generic advice - USE THE TOOLS to get real data
3. After receiving tool results, provide a helpful summary
4. Only give your final answer (without tool calls) after you have the information"""
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
            # Detect if this likely needs web tools
            lower_input = task.original_input.lower()
            needs_web = any(kw in lower_input for kw in [
                'fetch', 'check', 'look up', 'latest', 'version', 'pypi', 'npm',
                'github', 'docs', 'documentation', 'website', 'url'
            ])

            if needs_web:
                tool_hint = "\n\nIMPORTANT: This request requires fetching external information. You MUST use a tool (web_fetch or web_search) to get real data. Respond with a JSON tool call first."
            else:
                tool_hint = "\n\nYou have tools available if you need to fetch external information."

        return f"""User Request:
{task.original_input}
{context_info}{tool_hint}

Respond appropriately. If external information is needed, use a tool first."""


class AgentExecutor(ExecutionStrategy):
    """
    Full agent loop with planning and tool use.

    Best for:
    - Writing new code
    - Refactoring existing code
    - Multi-step implementations
    - Bug fixes

    Features:
    - Full planning phase
    - Human-in-the-loop approval
    - Tool access (file, git, search)
    - Iterative execution
    - Dynamic provider selection for complex tasks
    """

    def __init__(
        self,
        orchestrator: OrchestratorLike,
        project_root: Optional[Path] = None,
        max_iterations: int = 10,
        require_approval: bool = True
    ):
        self.orchestrator = orchestrator
        self.project_root = project_root or Path.cwd()
        self.max_iterations = max_iterations
        self.require_approval = require_approval
        self._resolved_provider: Optional[str] = None
        self._resolved_model: Optional[str] = None

    def set_provider(self, provider_name: Optional[str], model_name: Optional[str] = None):
        """
        Set the provider to use for the next execution.

        Called by TaskRouter with resolved provider from classifier hints.
        For complex tasks (complexity >= 7), this will use quality models.
        """
        self._resolved_provider = provider_name
        self._resolved_model = model_name

    @property
    def name(self) -> str:
        return "AgentExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.CODE_GENERATION

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Execute code generation task with full agent loop."""
        start_time = time.time()

        try:
            # Import CodeAgent here to avoid circular imports
            from ..agent import CodeAgent, ConversationState
            from ..orchestrator_adapter import AgentOrchestratorAdapter

            # Create adapter for CodeAgent with provider hint
            adapter = AgentOrchestratorAdapter(self.orchestrator)

            # Override adapter's provider if we have a resolved one
            if self._resolved_provider:
                adapter.set_preferred_provider(self._resolved_provider, self._resolved_model)

            # Initialize CodeAgent
            agent = CodeAgent(
                orchestrator=adapter,
                project_root=self.project_root,
                max_iterations=self.max_iterations,
                require_approval=self.require_approval
            )

            # Clear resolved provider after use
            self._resolved_provider = None
            self._resolved_model = None

            # Run planning phase if needed
            if task.requires_planning:
                plan_result = self._run_planning(task)
                if plan_result:
                    task_with_plan = f"{task.original_input}\n\nPlan:\n{plan_result}"
                else:
                    task_with_plan = task.original_input
            else:
                task_with_plan = task.original_input

            # Execute with agent loop
            results = agent.run(task_with_plan)

            execution_time = time.time() - start_time

            # Format results
            output_parts = []
            total_tokens = 0

            for i, result in enumerate(results, 1):
                output_parts.append(f"Step {i}: {result.action.action}")
                if result.output:
                    output_parts.append(f"  Output: {result.output[:500]}")
                if not result.approved:
                    output_parts.append("  [User declined]")

            return ExecutionResult(
                success=all(r.approved for r in results),
                output="\n".join(output_parts),
                execution_time=execution_time,
                tokens_used=total_tokens,
                provider_used="agent_loop",
                metadata={
                    "iterations": len(results),
                    "actions": [r.action.action for r in results],
                    "all_approved": all(r.approved for r in results)
                }
            )

        except ImportError as e:
            # Fallback if CodeAgent not available
            return self._fallback_execution(task, start_time, str(e))
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Agent execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    def _run_planning(self, task: ClassifiedTask) -> Optional[str]:
        """Run planning phase for complex tasks."""
        try:
            if hasattr(self.orchestrator, 'plan'):
                plan = self.orchestrator.plan(task.original_input)
                if isinstance(plan, list):
                    return "\n".join([f"- {step}" for step in plan])
                return str(plan)
        except Exception:
            pass
        return None

    def _fallback_execution(
        self,
        task: ClassifiedTask,
        start_time: float,
        import_error: str
    ) -> ExecutionResult:
        """
        Fallback to simple LLM generation if CodeAgent unavailable.
        """
        try:
            prompt = f"""Code Generation Task:
{task.original_input}

Please provide the code implementation. Include:
1. Clear code with comments
2. Any necessary imports
3. Brief explanation of the approach
"""
            # Use orchestrator's brain provider with correct signature
            response = self.orchestrator.delegate(
                self.orchestrator.brain,
                prompt,
                system_prompt="You are an expert programmer. Write clean, well-documented code.",
                max_tokens=2000,
                temperature=0.3,
                use_context=True
            )

            if hasattr(response, 'content'):
                output = response.content
                tokens = getattr(response, 'tokens_used', 0)
            else:
                output = str(response)
                tokens = 0

            return ExecutionResult(
                success=True,
                output=output,
                execution_time=time.time() - start_time,
                tokens_used=tokens,
                provider_used="fallback_llm",
                metadata={
                    "fallback_reason": import_error,
                    "mode": "simple_generation"
                }
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Fallback execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )


class ConversationExecutor(ExecutionStrategy):
    """
    Simple conversation handling without task execution.

    Best for:
    - Greetings
    - Acknowledgments
    - Help requests
    - Simple Q&A
    """

    def __init__(self, orchestrator: Optional[OrchestratorLike] = None):
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return "ConversationExecutor"

    def can_handle(self, task: ClassifiedTask) -> bool:
        return task.task_type == TaskType.CONVERSATION

    def execute(self, task: ClassifiedTask) -> ExecutionResult:
        """Handle simple conversation."""
        start_time = time.time()

        # Pre-defined responses for common patterns
        responses = {
            "greeting": "Hello! I'm ready to help with your tasks. What would you like to do?",
            "thanks": "You're welcome! Let me know if you need anything else.",
            "acknowledgment": "Understood. What's next?",
            "help_request": "I can help with:\n- Direct commands (pip install, git status)\n- Code generation (write, refactor, fix)\n- Research (explain code, analyze architecture)\n\nWhat would you like to do?",
            "farewell": "Goodbye! Feel free to return anytime."
        }

        # Find matching pattern
        for pattern in task.matched_patterns:
            if pattern in responses:
                return ExecutionResult(
                    success=True,
                    output=responses[pattern],
                    execution_time=time.time() - start_time,
                    metadata={"pattern": pattern}
                )

        # Default response
        return ExecutionResult(
            success=True,
            output="I understand. How can I assist you?",
            execution_time=time.time() - start_time
        )
