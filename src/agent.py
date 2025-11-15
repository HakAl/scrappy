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


class CodeAgent:
    """
    AI-powered code agent with tool use and safety features.

    Key features:
    - Human-in-the-loop confirmation for all file operations
    - Sandboxed to project directory
    - Audit logging of all actions
    - Hybrid model approach (Gemini for reasoning, Cerebras for speed)
    """

    def __init__(self, orchestrator, project_path: Optional[str] = None):
        """
        Initialize the code agent.

        Args:
            orchestrator: AgentOrchestrator instance
            project_path: Root directory to sandbox operations (default: cwd)
        """
        self.orch = orchestrator
        self.project_root = Path(project_path or ".").resolve()
        self.audit_log = []
        self.dry_run = False

        # Hybrid approach: Gemini for smart tasks, Cerebras for fast tasks
        available = orchestrator.registry.list_available()

        # Prefer Gemini for planning/code gen (best reasoning)
        if 'gemini' in available:
            self.planner = 'gemini'
        elif 'groq' in available:
            self.planner = 'groq'
        else:
            self.planner = available[0] if available else None

        # Prefer Cerebras for fast operations
        if 'cerebras' in available:
            self.executor = 'cerebras'
        else:
            self.executor = self.planner

        # Define available tools
        self.tools = {
            'read_file': self._tool_read_file,
            'write_file': self._tool_write_file,
            'list_files': self._tool_list_files,
            'run_command': self._tool_run_command,
            'search_code': self._tool_search_code,
        }

        # Tool descriptions for LLM
        self.tool_descriptions = """
Available tools:
1. read_file(path: str) - Read contents of a file
2. write_file(path: str, content: str) - Write content to a file
3. list_files(directory: str, pattern: str = "*") - List files in directory
4. run_command(command: str) - Run a shell command
5. search_code(pattern: str, file_pattern: str = "*.py") - Search for pattern in code

Response format (JSON):
{
    "thought": "What I'm thinking about the task",
    "action": "tool_name",
    "parameters": {"param1": "value1"},
    "is_complete": false
}

When task is complete:
{
    "thought": "Task completed successfully",
    "action": "complete",
    "result": "Summary of what was done",
    "is_complete": true
}
"""

    def _log_action(self, action: str, params: dict, result: str, approved: bool):
        """Log an action to the audit trail."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'parameters': params,
            'result': result[:500] if len(result) > 500 else result,
            'approved': approved
        }
        self.audit_log.append(entry)

    def _is_safe_path(self, path: str) -> bool:
        """Check if path is within project sandbox."""
        try:
            target = (self.project_root / path).resolve()
            return str(target).startswith(str(self.project_root))
        except Exception:
            return False

    def _tool_read_file(self, path: str) -> str:
        """Read a file from the project."""
        if not self._is_safe_path(path):
            return f"Error: Path '{path}' is outside project directory"

        target = self.project_root / path
        if not target.exists():
            return f"Error: File '{path}' does not exist"

        try:
            content = target.read_text(encoding='utf-8')
            # Truncate if too long
            if len(content) > 10000:
                content = content[:10000] + "\n... [truncated]"
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def _tool_write_file(self, path: str, content: str) -> str:
        """Write content to a file."""
        if not self._is_safe_path(path):
            return f"Error: Path '{path}' is outside project directory"

        if self.dry_run:
            return f"[DRY RUN] Would write {len(content)} chars to {path}"

        target = self.project_root / path
        try:
            # Create parent directories if needed
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    def _tool_list_files(self, directory: str = ".", pattern: str = "*") -> str:
        """List files in a directory."""
        if not self._is_safe_path(directory):
            return f"Error: Path '{directory}' is outside project directory"

        target = self.project_root / directory
        if not target.exists():
            return f"Error: Directory '{directory}' does not exist"

        try:
            files = list(target.glob(pattern))
            # Limit results
            if len(files) > 100:
                files = files[:100]
                truncated = True
            else:
                truncated = False

            result = []
            for f in sorted(files):
                rel_path = f.relative_to(self.project_root)
                if f.is_dir():
                    result.append(f"{rel_path}/")
                else:
                    result.append(str(rel_path))

            output = "\n".join(result)
            if truncated:
                output += "\n... [truncated to 100 items]"
            return output
        except Exception as e:
            return f"Error listing files: {str(e)}"

    def _tool_run_command(self, command: str) -> str:
        """Run a shell command."""
        # Security: Block dangerous commands
        dangerous = ['rm -rf', 'del /f', 'format', 'mkfs', '> /dev/', 'sudo']
        for d in dangerous:
            if d in command.lower():
                return f"Error: Command contains dangerous pattern '{d}'"

        if self.dry_run:
            return f"[DRY RUN] Would run: {command}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"

            if len(output) > 5000:
                output = output[:5000] + "\n... [truncated]"

            return output if output else "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out (30s limit)"
        except Exception as e:
            return f"Error running command: {str(e)}"

    def _tool_search_code(self, pattern: str, file_pattern: str = "*.py") -> str:
        """Search for a pattern in code files."""
        try:
            results = []
            for file_path in self.project_root.rglob(file_pattern):
                if '.git' in str(file_path) or '__pycache__' in str(file_path):
                    continue
                if not self._is_safe_path(str(file_path.relative_to(self.project_root))):
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8')
                    for i, line in enumerate(content.splitlines(), 1):
                        if pattern.lower() in line.lower():
                            rel_path = file_path.relative_to(self.project_root)
                            results.append(f"{rel_path}:{i}: {line.strip()}")
                except Exception:
                    continue

                if len(results) > 50:
                    break

            if not results:
                return f"No matches found for '{pattern}'"

            output = "\n".join(results[:50])
            if len(results) > 50:
                output += "\n... [truncated to 50 matches]"
            return output
        except Exception as e:
            return f"Error searching: {str(e)}"

    def _get_user_confirmation(self, action: str, params: dict) -> bool:
        """Ask user for confirmation before executing action."""
        print(f"\nAgent wants to: {action}")
        print(f"Parameters: {json.dumps(params, indent=2)}")

        # Show preview for write operations
        if action == 'write_file' and 'content' in params:
            content = params['content']
            preview = content[:500] + "..." if len(content) > 500 else content
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
        system_prompt = f"""You are a code agent that helps with programming tasks.
You have access to tools to read, write, and analyze code.

{self.tool_descriptions}

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
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration}/{max_iterations} ---")

            # Get agent's next action (use Gemini for reasoning)
            print(f"[{self.planner}] Thinking...")
            response = self.orch.delegate(
                self.planner,
                messages[-1]['content'] if len(messages) == 2 else "Continue with the task based on the previous result.",
                system_prompt=system_prompt if len(messages) == 2 else None,
                max_tokens=1500,
                temperature=0.3,
                use_context=False  # Context already in system prompt
            )

            # Parse response
            action_data = self._parse_agent_response(response.content)

            thought = action_data.get('thought', 'No thought provided')
            action = action_data.get('action', 'error')
            params = action_data.get('parameters', {})
            is_complete = action_data.get('is_complete', False)

            print(f"\nThought: {thought}")

            # Check if task is complete
            if is_complete or action == 'complete':
                result = action_data.get('result', 'Task completed')
                print(f"\nResult: {result}")
                self._log_action('complete', {}, result, True)

                return {
                    'success': True,
                    'result': result,
                    'iterations': iteration,
                    'audit_log': self.audit_log
                }

            # Execute tool
            if action in self.tools:
                # Get user confirmation (unless auto_confirm)
                if auto_confirm:
                    approved = True
                else:
                    approved = self._get_user_confirmation(action, params)

                if approved:
                    print(f"Executing: {action}")
                    tool_result = self.tools[action](**params)
                    print(f"Result: {tool_result[:300]}..." if len(tool_result) > 300 else f"Result: {tool_result}")
                    self._log_action(action, params, tool_result, True)

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
            else:
                print(f"Unknown action: {action}")
                messages.append({
                    'role': 'assistant',
                    'content': response.content
                })
                messages.append({
                    'role': 'user',
                    'content': f"Unknown action '{action}'. Available tools: {', '.join(self.tools.keys())}"
                })

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
