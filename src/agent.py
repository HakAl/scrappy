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

try:
    import click
    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False


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
            'list_directory': self._tool_list_directory,
            'run_command': self._tool_run_command,
            'search_code': self._tool_search_code,
            'git_log': self._tool_git_log,
            'git_diff': self._tool_git_diff,
            'git_blame': self._tool_git_blame,
            'git_show': self._tool_git_show,
            'git_recent_changes': self._tool_git_recent_changes,
        }

        # Tool descriptions for LLM
        self.tool_descriptions = """
Available tools:
1. read_file(path: str) - Read contents of a file
2. write_file(path: str, content: str) - Write content to a file
3. list_files(directory: str, pattern: str = "*") - List files matching pattern recursively
4. list_directory(path: str, depth: int = 2) - Show directory tree structure with files and subdirs
5. run_command(command: str) - Run a shell command
6. search_code(pattern: str, file_pattern: str = "*.py") - Search for pattern in code
7. git_log(n: int = 10, file: str = None) - View recent commits (optionally for specific file)
8. git_diff(ref: str = None, file: str = None) - Show changes (unstaged, or vs ref like HEAD~1)
9. git_blame(file: str, lines: str = None) - Show who changed each line (e.g., lines="10,20")
10. git_show(commit: str) - Show details of a specific commit
11. git_recent_changes(n: int = 3) - Show content of last N commits with full diffs

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

    def _colorize_git_output(self, output: str, output_type: str = "log") -> str:
        """Add colors to git output for better readability."""
        if not HAS_CLICK:
            return output

        lines = output.split('\n')
        colored_lines = []

        for line in lines:
            if output_type == "log":
                # Color commit hashes and decorations
                if line and len(line) > 7 and line[:7].replace(' ', '').isalnum():
                    parts = line.split(' ', 1)
                    if len(parts) >= 1:
                        # Commit hash in yellow
                        colored = click.style(parts[0], fg='yellow')
                        if len(parts) > 1:
                            colored += ' ' + parts[1]
                        colored_lines.append(colored)
                    else:
                        colored_lines.append(line)
                else:
                    colored_lines.append(line)

            elif output_type == "diff":
                # Color diff lines
                if line.startswith('+++') or line.startswith('---'):
                    colored_lines.append(click.style(line, fg='cyan', bold=True))
                elif line.startswith('+'):
                    colored_lines.append(click.style(line, fg='green'))
                elif line.startswith('-'):
                    colored_lines.append(click.style(line, fg='red'))
                elif line.startswith('@@'):
                    colored_lines.append(click.style(line, fg='cyan'))
                elif line.startswith('diff --git'):
                    colored_lines.append(click.style(line, fg='bright_white', bold=True))
                else:
                    colored_lines.append(line)

            elif output_type == "blame":
                # Color blame output (hash at start)
                if line and '^' in line or (len(line) > 8 and line[:8].replace(' ', '').isalnum()):
                    parts = line.split(' ', 1)
                    if len(parts) >= 1:
                        colored = click.style(parts[0], fg='yellow')
                        if len(parts) > 1:
                            colored += ' ' + parts[1]
                        colored_lines.append(colored)
                    else:
                        colored_lines.append(line)
                else:
                    colored_lines.append(line)

            elif output_type == "show":
                # Color commit show output
                if line.startswith('commit '):
                    colored_lines.append(click.style(line, fg='yellow', bold=True))
                elif line.startswith('Author:'):
                    colored_lines.append(click.style(line, fg='cyan'))
                elif line.startswith('Date:'):
                    colored_lines.append(click.style(line, fg='cyan'))
                elif line.startswith('=== COMMIT'):
                    colored_lines.append(click.style(line, fg='yellow', bold=True))
                elif line.startswith('Message:'):
                    colored_lines.append(click.style(line, fg='bright_white', bold=True))
                elif '|' in line and ('+' in line or '-' in line):
                    # File stat lines
                    colored_lines.append(click.style(line, fg='cyan'))
                elif line.startswith('+'):
                    colored_lines.append(click.style(line, fg='green'))
                elif line.startswith('-'):
                    colored_lines.append(click.style(line, fg='red'))
                else:
                    colored_lines.append(line)
            else:
                colored_lines.append(line)

        return '\n'.join(colored_lines)

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

    def _tool_list_directory(self, path: str = ".", depth: int = 2) -> str:
        """Show directory tree structure."""
        if not self._is_safe_path(path):
            return f"Error: Path '{path}' is outside project directory"

        target = self.project_root / path
        if not target.exists():
            return f"Error: Path '{path}' does not exist"
        if not target.is_dir():
            return f"Error: '{path}' is not a directory"

        try:
            lines = []
            skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', '.tox', '.pytest_cache'}

            def build_tree(dir_path: Path, prefix: str = "", current_depth: int = 0):
                if current_depth > depth:
                    return

                try:
                    items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                except PermissionError:
                    lines.append(f"{prefix}[Permission Denied]")
                    return

                # Filter out hidden and skip directories
                items = [i for i in items if not i.name.startswith('.') or i.name in ['.env', '.gitignore']]
                items = [i for i in items if i.name not in skip_dirs]

                for i, item in enumerate(items):
                    is_last = i == len(items) - 1
                    connector = "`-- " if is_last else "|-- "

                    if item.is_dir():
                        # Directory - show in cyan
                        if HAS_CLICK:
                            dir_name = click.style(f"{item.name}/", fg='cyan', bold=True)
                        else:
                            dir_name = f"{item.name}/"
                        lines.append(f"{prefix}{connector}{dir_name}")

                        # Recurse into subdirectory
                        if current_depth < depth:
                            extension = "    " if is_last else "|   "
                            build_tree(item, prefix + extension, current_depth + 1)
                    else:
                        # File - show with size
                        try:
                            size = item.stat().st_size
                            if size < 1024:
                                size_str = f"{size}B"
                            elif size < 1024 * 1024:
                                size_str = f"{size/1024:.1f}KB"
                            else:
                                size_str = f"{size/(1024*1024):.1f}MB"
                        except:
                            size_str = "?"

                        # Color by file type
                        if HAS_CLICK:
                            if item.suffix in ['.py']:
                                file_name = click.style(item.name, fg='green')
                            elif item.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                                file_name = click.style(item.name, fg='yellow')
                            elif item.suffix in ['.md', '.txt', '.rst']:
                                file_name = click.style(item.name, fg='white')
                            elif item.suffix in ['.json', '.yaml', '.yml', '.toml']:
                                file_name = click.style(item.name, fg='magenta')
                            else:
                                file_name = item.name
                            size_display = click.style(f"({size_str})", fg='bright_black')
                        else:
                            file_name = item.name
                            size_display = f"({size_str})"

                        lines.append(f"{prefix}{connector}{file_name} {size_display}")

            # Start with the directory name
            if HAS_CLICK:
                root_name = click.style(str(target.relative_to(self.project_root)), fg='cyan', bold=True)
            else:
                root_name = str(target.relative_to(self.project_root))
            lines.append(f"{root_name}/")

            build_tree(target)

            if len(lines) > 200:
                lines = lines[:200]
                lines.append("... [truncated to 200 items]")

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

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

    def _tool_git_log(self, n: int = 10, file: str = None) -> str:
        """View recent git commits."""
        try:
            cmd = ['git', 'log', f'-{n}', '--oneline', '--decorate']
            if file:
                if not self._is_safe_path(file):
                    return f"Error: Path '{file}' is outside project directory"
                cmd.extend(['--', file])

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return f"Git error: {result.stderr.strip()}"

            output = result.stdout.strip()
            if not output:
                return "No commits found"
            return self._colorize_git_output(output, "log")
        except subprocess.TimeoutExpired:
            return "Error: git log timed out"
        except Exception as e:
            return f"Error running git log: {str(e)}"

    def _tool_git_diff(self, ref: str = None, file: str = None) -> str:
        """Show git diff (unstaged changes, or vs a ref like HEAD~1)."""
        try:
            cmd = ['git', 'diff']
            if ref:
                cmd.append(ref)
            if file:
                if not self._is_safe_path(file):
                    return f"Error: Path '{file}' is outside project directory"
                cmd.extend(['--', file])

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return f"Git error: {result.stderr.strip()}"

            output = result.stdout.strip()
            if not output:
                return "No changes found"

            # Truncate if too long
            if len(output) > 5000:
                output = output[:5000] + "\n... [truncated]"
            return self._colorize_git_output(output, "diff")
        except subprocess.TimeoutExpired:
            return "Error: git diff timed out"
        except Exception as e:
            return f"Error running git diff: {str(e)}"

    def _tool_git_blame(self, file: str, lines: str = None) -> str:
        """Show git blame for a file (who changed each line)."""
        if not self._is_safe_path(file):
            return f"Error: Path '{file}' is outside project directory"

        try:
            cmd = ['git', 'blame', '--date=short']

            # Add line range if specified (e.g., "10,20" for lines 10-20)
            if lines:
                cmd.extend(['-L', lines])

            cmd.append(file)

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return f"Git error: {result.stderr.strip()}"

            output = result.stdout.strip()
            if not output:
                return "No blame information found"

            # Truncate if too long
            if len(output) > 5000:
                output = output[:5000] + "\n... [truncated]"
            return self._colorize_git_output(output, "blame")
        except subprocess.TimeoutExpired:
            return "Error: git blame timed out"
        except Exception as e:
            return f"Error running git blame: {str(e)}"

    def _tool_git_show(self, commit: str) -> str:
        """Show details of a specific commit."""
        try:
            # Validate commit hash format (basic check)
            if not commit.replace('-', '').replace('^', '').replace('~', '').replace('HEAD', '').isalnum():
                if commit not in ['HEAD', 'HEAD~1', 'HEAD~2', 'HEAD^']:
                    return f"Error: Invalid commit reference '{commit}'"

            result = subprocess.run(
                ['git', 'show', '--stat', commit],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return f"Git error: {result.stderr.strip()}"

            output = result.stdout.strip()
            if not output:
                return "No commit information found"

            # Truncate if too long
            if len(output) > 5000:
                output = output[:5000] + "\n... [truncated]"
            return self._colorize_git_output(output, "show")
        except subprocess.TimeoutExpired:
            return "Error: git show timed out"
        except Exception as e:
            return f"Error running git show: {str(e)}"

    def _tool_git_recent_changes(self, n: int = 3) -> str:
        """Show content of last N commits with full diffs."""
        try:
            # Limit to reasonable number
            n = min(n, 10)

            result = subprocess.run(
                ['git', 'log', f'-{n}', '--patch', '--stat', '--pretty=format:=== COMMIT %h ===\nAuthor: %an\nDate: %ad\nMessage: %s\n'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30  # Longer timeout for diffs
            )

            if result.returncode != 0:
                return f"Git error: {result.stderr.strip()}"

            output = result.stdout.strip()
            if not output:
                return "No recent changes found"

            # Truncate if too long (diffs can be very large)
            if len(output) > 15000:
                output = output[:15000] + "\n\n... [truncated - showing first 15000 chars]"
            return self._colorize_git_output(output, "show")
        except subprocess.TimeoutExpired:
            return "Error: git recent changes timed out (diffs too large)"
        except Exception as e:
            return f"Error getting recent changes: {str(e)}"

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
