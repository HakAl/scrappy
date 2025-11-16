"""
Code Agent with human-in-the-loop safety.

Uses Gemini for planning/code generation (smart tasks)
and Cerebras for quick operations (fast tasks).
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from .agent_config import AgentConfig
from .agent_tools.tools import ToolRegistry, ToolContext
from .agent_tools.tools.file_tools import (
    ReadFileTool,
    WriteFileTool,
    ListFilesTool,
    ListDirectoryTool
)
from .agent_tools.tools.git_tools import (
    GitLogTool,
    GitDiffTool,
    GitBlameTool,
    GitShowTool,
    GitRecentChangesTool
)
from .agent_tools.tools.search_tools import SearchCodeTool


class CodeAgent:
    """
    AI-powered code agent with tool use and safety features.

    Key features:
    - Human-in-the-loop confirmation for all file operations
    - Sandboxed to project directory
    - Audit logging of all actions
    - Hybrid model approach (Gemini for reasoning, Cerebras for speed)
    - Injectable tool system with registry
    """

    def __init__(
        self,
        orchestrator,
        project_path: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """
        Initialize the code agent.

        Args:
            orchestrator: AgentOrchestrator instance
            project_path: Root directory to sandbox operations (default: cwd)
            config: AgentConfig instance (uses defaults if not provided)
            tool_registry: ToolRegistry instance (creates default if not provided)
        """
        self.orch = orchestrator
        self.project_root = Path(project_path or ".").resolve()
        self.config = config or AgentConfig()
        self.audit_log = []
        self.dry_run = False

        # Create tool context
        self.tool_context = ToolContext(
            project_root=self.project_root,
            dry_run=self.dry_run,
            config=self.config,
            orchestrator=self.orch
        )

        # Setup tool registry
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            self.tool_registry = self._create_default_registry()

        # Build tools mapping for backward compatibility
        self.tools = {
            tool.name: lambda ctx=self.tool_context, t=tool, **kw: t(ctx, **kw)
            for tool in self.tool_registry.list_all()
        }

        # Add run_command tool (kept inline for security reasons)
        self.tools['run_command'] = self._tool_run_command

        # Hybrid approach: Use configured provider preferences
        available = orchestrator.registry.list_available()

        # Select planner based on preferences
        self.planner = None
        for pref in self.config.planner_preferences:
            if pref in available:
                self.planner = pref
                break
        if self.planner is None:
            self.planner = available[0] if available else None

        # Select executor based on preferences
        self.executor = None
        for pref in self.config.executor_preferences:
            if pref in available:
                self.executor = pref
                break
        if self.executor is None:
            self.executor = self.planner

    def _create_default_registry(self) -> ToolRegistry:
        """Create and populate the default tool registry."""
        registry = ToolRegistry()

        # Register file tools
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        registry.register(ListFilesTool())
        registry.register(ListDirectoryTool())

        # Register git tools
        registry.register(GitLogTool())
        registry.register(GitDiffTool())
        registry.register(GitBlameTool())
        registry.register(GitShowTool())
        registry.register(GitRecentChangesTool())

        # Register search tools
        registry.register(SearchCodeTool())

        return registry

    def _get_tool_descriptions(self) -> str:
        """Generate tool descriptions including run_command."""
        # Get descriptions from registry
        registry_desc = self.tool_registry.generate_descriptions(numbered=True)

        # Add run_command (not in registry for security)
        lines = registry_desc.split('\n')
        tool_count = len(self.tool_registry.list_tools())
        lines.insert(-1, f"{tool_count + 1}. run_command(command: str) - Run a shell command")

        # Add response format
        result = '\n'.join(lines)
        result += self.tool_registry.get_response_format()

        return result

    def _log_action(self, action: str, params: dict, result: str, approved: bool):
        """Log an action to the audit trail."""
        max_len = self.config.audit_log_result_truncation
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'parameters': params,
            'result': result[:max_len] if len(result) > max_len else result,
            'approved': approved
        }
        self.audit_log.append(entry)

    def _tool_run_command(self, command: str) -> str:
        """Run a shell command."""
        # Security: Block dangerous commands
        for d in self.config.dangerous_commands:
            if d in command.lower():
                return f"Error: Command contains dangerous pattern '{d}'"

        if self.dry_run:
            return f"[DRY RUN] Would run: {command}"

        try:
            timeout = self.config.command_timeout
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"

            max_output = self.config.max_command_output
            if len(output) > max_output:
                output = output[:max_output] + "\n... [truncated]"

            return output if output else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out ({self.config.command_timeout}s limit)"
        except Exception as e:
            return f"Error running command: {str(e)}"

    def _get_user_confirmation(self, action: str, params: dict) -> bool:
        """Ask user for confirmation before executing action."""
        print(f"\nAgent wants to: {action}")
        print(f"Parameters: {json.dumps(params, indent=2)}")

        # Show preview for write operations
        if action == 'write_file' and 'content' in params:
            content = params['content']
            max_preview = self.config.write_preview_truncation
            preview = content[:max_preview] + "..." if len(content) > max_preview else content
            print(f"\nContent preview:\n{preview}")

        response = input("Allow? [y/N]: ").strip().lower()
        return response in ('y', 'yes')

    def _parse_agent_response(self, response_text: str) -> dict:
        """Parse the agent's JSON response."""
        # Try to extract JSON from response
        text = response_text.strip()

        # Handle markdown code blocks
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            text = text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except:
                    pass

            # Return error response
            return {
                'thought': 'Failed to parse response',
                'action': 'error',
                'parameters': {},
                'is_complete': True,
                'result': f'Parse error: {response_text[:200]}'
            }

    def run(self, task: str, max_iterations: int = 10, auto_confirm: bool = False) -> dict:
        """
        Run the agent on a task.

        Args:
            task: The task to accomplish
            max_iterations: Maximum number of tool uses
            auto_confirm: Skip user confirmation (use with caution)

        Returns:
            dict with 'success', 'result', 'audit_log'
        """
        # Update tool context dry_run state
        self.tool_context.dry_run = self.dry_run

        print(f"\n{'='*60}")
        print(f"Code Agent - Task: {task}")
        print(f"{'='*60}")
        print(f"Planner: {self.planner} | Executor: {self.executor}")
        print(f"Project: {self.project_root}")
        if self.dry_run:
            print("[DRY RUN MODE - No actual changes will be made]")
        print(f"{'='*60}\n")

        # Build initial context
        context_info = ""
        if self.orch.context.is_explored():
            context_info = f"\nProject Context:\n{self.orch.context.get_summary()}\n"

        # System prompt for agent
        tool_descriptions = self._get_tool_descriptions()
        system_prompt = f"""You are a code agent that helps with programming tasks.
You have access to tools to read, write, and analyze code.

{tool_descriptions}

{context_info}

Important:
- Always explain your reasoning in the "thought" field
- Use read_file to understand existing code before modifying
- Make incremental changes, not massive rewrites
- Test your changes when possible
- Be careful with file paths (relative to project root)

Current task: {task}
"""

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f"Please complete this task: {task}"}
        ]

        iteration = 0
        tools_executed = []  # Track which tools were actually executed
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration}/{max_iterations} ---")

            # Get agent's next action (use Gemini for reasoning)
            print(f"[{self.planner}] Thinking...")

            # Build the prompt with conversation history for multi-turn
            if len(messages) == 2:
                # First iteration: just use the task
                user_prompt = messages[-1]['content']
            else:
                # Subsequent iterations: include conversation history
                history_parts = []
                for msg in messages[2:]:  # Skip system prompt and initial task
                    role = msg['role'].upper()
                    history_parts.append(f"{role}: {msg['content']}")
                history_text = "\n\n".join(history_parts)
                user_prompt = f"Previous conversation:\n{history_text}\n\nBased on the above, continue with the task. Remember to respond with valid JSON."

            response = self.orch.delegate(
                self.planner,
                user_prompt,
                system_prompt=system_prompt,  # Always include system prompt
                max_tokens=self.config.default_max_tokens,
                temperature=self.config.default_temperature,
                use_context=False  # Context already in system prompt
            )

            # Parse response
            action_data = self._parse_agent_response(response.content)

            thought = action_data.get('thought', 'No thought provided')
            action = action_data.get('action', 'error')
            params = action_data.get('parameters', {})
            is_complete = action_data.get('is_complete', False)

            print(f"\nThought: {thought}")

            # Execute tool FIRST (even if is_complete is set, we may have an action to execute)
            action_executed = False
            if action in self.tools and action != 'complete':
                # Get user confirmation (unless auto_confirm)
                if auto_confirm:
                    approved = True
                else:
                    approved = self._get_user_confirmation(action, params)

                if approved:
                    print(f"Executing: {action}")
                    tool_result = self.tools[action](**params)
                    max_display = self.config.result_display_truncation
                    print(f"Result: {tool_result[:max_display]}..." if len(tool_result) > max_display else f"Result: {tool_result}")
                    self._log_action(action, params, tool_result, True)
                    tools_executed.append(action)  # Track successful execution
                    action_executed = True

                    # Add result to conversation
                    messages.append({
                        'role': 'assistant',
                        'content': response.content
                    })
                    messages.append({
                        'role': 'user',
                        'content': f"Tool result for {action}:\n{tool_result}\n\nContinue with the task or mark as complete if done."
                    })
                else:
                    print("Action denied by user")
                    self._log_action(action, params, "Denied by user", False)

                    # Let agent know action was denied
                    messages.append({
                        'role': 'assistant',
                        'content': response.content
                    })
                    messages.append({
                        'role': 'user',
                        'content': f"User denied the {action} action. Please try a different approach or explain why this action is necessary."
                    })
            elif action not in self.tools and action != 'complete' and action != 'error':
                print(f"Unknown action: {action}")
                messages.append({
                    'role': 'assistant',
                    'content': response.content
                })
                messages.append({
                    'role': 'user',
                    'content': f"Unknown action '{action}'. Available tools: {', '.join(self.tools.keys())}"
                })

            # Check if task is complete (AFTER executing any actions)
            if is_complete or action == 'complete':
                # Verify that at least one meaningful action was performed
                meaningful_actions = [t for t in tools_executed if t in self.config.meaningful_actions]
                if not meaningful_actions and not self.dry_run:
                    print(f"\nWarning: Agent declared completion without performing any file operations.")
                    print("Requesting agent to actually execute the task...")
                    if not action_executed:
                        messages.append({
                            'role': 'assistant',
                            'content': response.content
                        })
                        messages.append({
                            'role': 'user',
                            'content': "You declared the task complete but haven't actually created or modified any files. Please respond with a JSON object containing an action to execute. Use the write_file tool to actually create the requested code. Example format:\n{\n  \"thought\": \"your reasoning\",\n  \"action\": \"write_file\",\n  \"parameters\": {\"path\": \"filename\", \"content\": \"code here\"}\n}"
                        })
                    continue

                result = action_data.get('result', 'Task completed')
                print(f"\nResult: {result}")
                self._log_action('complete', {}, result, True)

                return {
                    'success': True,
                    'result': result,
                    'iterations': iteration,
                    'audit_log': self.audit_log
                }

        # Max iterations reached
        return {
            'success': False,
            'result': f'Max iterations ({max_iterations}) reached',
            'iterations': iteration,
            'audit_log': self.audit_log
        }

    def get_audit_log(self) -> list:
        """Get the audit log of all actions."""
        return self.audit_log

    def save_audit_log(self, path: str = ".agent_audit.json"):
        """Save audit log to file."""
        log_path = self.project_root / path
        with open(log_path, 'w') as f:
            json.dump(self.audit_log, f, indent=2)
        return str(log_path)


def create_git_checkpoint(project_path: str = ".") -> Optional[str]:
    """Create a git checkpoint before agent operations."""
    try:
        result = subprocess.run(
            "git rev-parse --is-inside-work-tree",
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return None

        # Create checkpoint commit
        subprocess.run(
            "git add -A",
            shell=True,
            cwd=project_path,
            capture_output=True
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = subprocess.run(
            f'git commit -m "Agent checkpoint {timestamp}" --allow-empty',
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        # Get commit hash
        result = subprocess.run(
            "git rev-parse HEAD",
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()
    except Exception:
        return None


def rollback_to_checkpoint(commit_hash: str, project_path: str = ".") -> bool:
    """Rollback to a git checkpoint."""
    try:
        result = subprocess.run(
            f"git reset --hard {commit_hash}",
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False
