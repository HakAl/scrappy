"""
Code Agent with human-in-the-loop safety.

Uses Gemini for planning/code generation (smart tasks)
and Cerebras for quick operations (fast tasks).
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Union

from .agent_config import AgentConfig
from .agent_tools.tools import ToolRegistry, ToolContext
from .orchestrator_adapter import (
    OrchestratorAdapter,
    AgentOrchestratorAdapter,
    ContextProvider,
    NullContext
)
from .agent_tools.tools.file_tools import (
    ReadFileTool,
    WriteFileTool,
    ListFilesTool,
    ListDirectoryTool
)
from .agent_tools.tools.git_tools import (
    GitLogTool,
    GitStatusTool,
    GitDiffTool,
    GitBlameTool,
    GitShowTool,
    GitRecentChangesTool
)
from .agent_tools.tools.search_tools import SearchCodeTool
from .agent_tools.tools.web_tools import WebFetchTool, WebSearchTool
from .agent_tools.tools.python_tools import AnalyzePythonDependenciesTool
from .platform_utils import get_platform_name, is_windows, validate_command_for_platform


@dataclass
class AgentThought:
    """Result from the thinking stage (LLM response)."""
    raw_response: str
    provider: str
    iteration: int


@dataclass
class AgentAction:
    """Parsed action from the planning stage."""
    thought: str
    action: str
    parameters: Dict[str, object]
    is_complete: bool
    result_text: str = ""  # For completion results


@dataclass
class ActionResult:
    """Result from executing an action."""
    success: bool
    output: str
    action: str
    parameters: Dict[str, object]
    approved: bool
    executed: bool = False


@dataclass
class EvaluationResult:
    """Result from evaluating whether task is complete."""
    is_complete: bool
    should_continue: bool
    reason: str
    final_result: Optional[str] = None


@dataclass
class ConversationState:
    """Encapsulates the conversation state for the agent loop."""
    messages: List[Dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    iteration: int = 0
    max_iterations: int = 10
    tools_executed: List[str] = field(default_factory=list)
    auto_confirm: bool = False


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
        orchestrator: Union[OrchestratorAdapter, object],
        project_path: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """
        Initialize the code agent.

        Args:
            orchestrator: OrchestratorAdapter instance or AgentOrchestrator
                         (will be wrapped in adapter if not already)
            project_path: Root directory to sandbox operations (default: cwd)
            config: AgentConfig instance (uses defaults if not provided)
            tool_registry: ToolRegistry instance (creates default if not provided)
        """
        # Wrap orchestrator in adapter if needed
        if isinstance(orchestrator, OrchestratorAdapter):
            self.adapter = orchestrator
        else:
            # Assume it's a full AgentOrchestrator, wrap it
            self.adapter = AgentOrchestratorAdapter(orchestrator)

        # Keep orch as alias for backward compatibility
        self.orch = self.adapter

        self.project_root = Path(project_path or ".").resolve()
        self.config = config or AgentConfig()
        self.audit_log = []
        self.dry_run = False

        # Create tool context
        self.tool_context = ToolContext(
            project_root=self.project_root,
            dry_run=self.dry_run,
            config=self.config,
            orchestrator=orchestrator  # Pass original for tool context
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

        # Build tool name mapping for dynamic _tool_* method resolution
        self._tool_name_map = {
            tool.name: tool.name for tool in self.tool_registry.list_all()
        }
        # Add common aliases for convenience
        self._tool_name_map.update({
            'list_directory': 'list_directory',
            'search_code': 'search_code',
            'read_file': 'read_file',
            'write_file': 'write_file',
            'git_log': 'git_log',
            'git_status': 'git_status',
            'git_diff': 'git_diff',
            'git_blame': 'git_blame',
        })

        # Hybrid approach: Use configured provider preferences
        available = self.adapter.list_providers()

        # Check if adapter has a preferred provider override (from task routing)
        preferred_provider = None
        if hasattr(self.adapter, 'get_preferred_provider'):
            pref_provider, pref_model = self.adapter.get_preferred_provider()
            if pref_provider and pref_provider in available:
                preferred_provider = pref_provider

        # Select planner based on preferences (prefer adapter override)
        self.planner = None
        if preferred_provider:
            self.planner = preferred_provider
        else:
            for pref in self.config.planner_preferences:
                if pref in available:
                    self.planner = pref
                    break
        if self.planner is None:
            self.planner = available[0] if available else None

        # Select executor based on preferences (prefer adapter override)
        self.executor = None
        if preferred_provider:
            self.executor = preferred_provider
        else:
            for pref in self.config.executor_preferences:
                if pref in available:
                    self.executor = pref
                    break
        if self.executor is None:
            self.executor = self.planner

    def __getattr__(self, name: str):
        """Dynamic attribute resolution for _tool_* methods.

        Allows calling agent._tool_search_code(...) which routes to self.tools['search_code'](...)
        This bridges the gap between smart_query.py expectations and the tool registry pattern.
        """
        if name.startswith('_tool_'):
            tool_name = name[6:]  # Remove '_tool_' prefix

            # Check if this is a registered tool
            if hasattr(self, '_tool_name_map') and tool_name in self._tool_name_map:
                actual_tool_name = self._tool_name_map[tool_name]

                # Define parameter mappings for common tools (positional to keyword)
                param_maps = {
                    'search_code': ['pattern', 'file_pattern'],
                    'read_file': ['file_path', 'max_lines'],
                    'write_file': ['file_path', 'content'],
                    'list_directory': ['path', 'depth'],
                    'git_log': ['n'],
                    'git_diff': ['ref1', 'ref2'],
                    'git_blame': ['file_path'],
                    'git_show': ['ref'],
                }

                # Return a wrapper function that calls the tool
                def tool_wrapper(*args, **kwargs):
                    if hasattr(self, 'tools') and actual_tool_name in self.tools:
                        # Convert positional args to keyword args
                        if args and actual_tool_name in param_maps:
                            param_names = param_maps[actual_tool_name]
                            for i, arg in enumerate(args):
                                if i < len(param_names):
                                    kwargs[param_names[i]] = arg

                        try:
                            result = self.tools[actual_tool_name](**kwargs)
                            # Return the output string for backward compatibility
                            if hasattr(result, 'output'):
                                if result.success:
                                    return result.output
                                else:
                                    return f"Error: {result.error}" if result.error else "Error: Tool execution failed"
                            return str(result)
                        except Exception as e:
                            return f"Error: {str(e)}"
                    raise AttributeError(f"Tool '{actual_tool_name}' not found in tools registry")

                return tool_wrapper

        # Default behavior - raise AttributeError for unknown attributes
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

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
        registry.register(GitStatusTool())
        registry.register(GitDiffTool())
        registry.register(GitBlameTool())
        registry.register(GitShowTool())
        registry.register(GitRecentChangesTool())

        # Register search tools
        registry.register(SearchCodeTool())

        # Register web tools
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())

        # Register Python tools
        registry.register(AnalyzePythonDependenciesTool())

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

        # Validate command for current platform
        is_valid, warning = validate_command_for_platform(command)
        if not is_valid:
            return f"Error: {warning}. Use platform-appropriate tools instead (read_file, search_code, list_files, etc.)"

        if self.dry_run:
            return f"[DRY RUN] Would run: {command}"

        # Check for interactive commands
        cmd_lower = command.lower()
        interactive_warning = False
        for pattern in self.config.interactive_commands:
            if pattern in cmd_lower:
                interactive_warning = True
                print(f"⚠️  Warning: '{pattern}' may require interactive input")
                # Suggest workarounds for common cases
                if 'npx' in cmd_lower:
                    print("   💡 Tip: Add '-y' flag to skip prompts: npx -y create-react-app ...")
                # Ask if user wants interactive mode
                try:
                    use_interactive = input("   Run in interactive mode (you can respond to prompts)? [Y/n]: ").strip().lower()
                    if use_interactive != 'n':
                        return self._run_command_interactive(command)
                except (KeyboardInterrupt, EOFError):
                    print("\n   Skipping interactive mode, running with captured output...")
                break

        # Check for long-running commands
        is_long_running = False
        for pattern in self.config.long_running_commands:
            if pattern in cmd_lower:
                is_long_running = True
                print(f"⏳ Long-running command detected: '{pattern}'")
                print(f"   Timeout: {self.config.command_timeout}s | Streaming output enabled")
                break

        try:
            timeout = self.config.command_timeout

            # Use streaming output for ALL commands (not just long-running)
            # This provides real-time feedback and better monitoring
            if is_long_running:
                return self._run_command_with_retry(command, timeout, show_progress=True)
            else:
                # Stream all commands but with quieter progress reporting
                return self._run_command_with_retry(command, timeout, show_progress=False)

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out ({self.config.command_timeout}s limit)"
        except Exception as e:
            return f"Error running command: {str(e)}"

    def _run_command_interactive(self, command: str) -> str:
        """
        Run a command in interactive mode - passes I/O directly to terminal.
        User can respond to prompts directly.
        """
        import os

        print(f"\n{'='*60}")
        print(f"Running in INTERACTIVE MODE")
        print(f"Command: {command}")
        print(f"You can respond to any prompts. Output goes directly to terminal.")
        print(f"{'='*60}\n")

        try:
            # Run command with direct terminal I/O (no capture)
            # This allows the user to see output and respond to prompts
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.project_root),
                # Don't capture - let it go directly to terminal
                # This allows interactive prompts to work
            )

            print(f"\n{'='*60}")
            print(f"Command finished with exit code: {result.returncode}")
            print(f"{'='*60}\n")

            if result.returncode == 0:
                return f"Command completed successfully (exit code 0). Output was displayed directly to terminal."
            else:
                return f"Command finished with exit code {result.returncode}. Check terminal output for details."

        except KeyboardInterrupt:
            print(f"\n{'='*60}")
            print(f"Command stopped by user (Ctrl+C)")
            print(f"{'='*60}\n")

            # Provide context-aware message based on command type
            cmd_lower = command.lower()

            # Check if this was likely a successful setup followed by a dev server
            if any(pattern in cmd_lower for pattern in ['create', 'init', 'new', 'vite', 'next', 'nuxt']):
                return (
                    "Command was stopped by user (Ctrl+C). This is normal if a dev server was started. "
                    "The project setup likely completed successfully before the server started. "
                    "Check the terminal output above to confirm files were created, then use 'list_files' "
                    "to verify the project structure. Do NOT re-run the create/init command."
                )
            elif any(pattern in cmd_lower for pattern in ['dev', 'start', 'serve', 'watch']):
                return (
                    "Dev server was stopped by user (Ctrl+C). This is expected behavior - "
                    "the server was running successfully until stopped. No need to re-run."
                )
            else:
                return (
                    "Command was stopped by user (Ctrl+C). Check terminal output above to see "
                    "what was accomplished before the interrupt. The command may have partially "
                    "or fully completed its main task."
                )
        except Exception as e:
            return f"Error running interactive command: {str(e)}"

    def _run_command_with_retry(self, command: str, timeout: int, show_progress: bool = True, max_retries: int = 3) -> str:
        """
        Run a command with streaming output and automatic retry logic.

        Args:
            command: The shell command to execute
            timeout: Maximum time in seconds before timeout
            show_progress: Whether to show detailed progress indicators
            max_retries: Maximum number of retry attempts for recoverable errors

        Returns:
            Command output with optional format parsing metadata
        """
        import time

        last_error = None
        retry_count = 0

        # Define recoverable error patterns
        recoverable_patterns = [
            'connection reset',
            'connection refused',
            'network is unreachable',
            'temporary failure',
            'timed out',
            'ECONNRESET',
            'ETIMEDOUT',
            'ENOTFOUND',
            'socket hang up',
            'certificate has expired',
            'unable to get local issuer certificate',
        ]

        for attempt in range(max_retries):
            if attempt > 0:
                # Exponential backoff: 2, 4, 8 seconds
                wait_time = 2 ** attempt
                print(f"   ⚠️  Retry attempt {attempt + 1}/{max_retries} after {wait_time}s delay...")
                time.sleep(wait_time)
                retry_count = attempt

            output = self._run_command_streaming(command, timeout, show_progress)

            # Check if output contains recoverable errors
            is_recoverable_error = False
            output_lower = output.lower()

            for pattern in recoverable_patterns:
                if pattern in output_lower and 'error' in output_lower:
                    is_recoverable_error = True
                    last_error = output
                    print(f"   ⚠️  Recoverable error detected: {pattern}")
                    break

            if not is_recoverable_error:
                # Success or non-recoverable error - parse output and return
                parsed_output = self._parse_command_output(output)
                if retry_count > 0:
                    parsed_output = f"[Succeeded after {retry_count} retries]\n{parsed_output}"
                return parsed_output

        # All retries exhausted
        return f"Error: Command failed after {max_retries} attempts.\nLast error:\n{last_error}"

    def _parse_command_output(self, output: str) -> str:
        """
        Parse command output and auto-detect format (JSON/YAML).

        Adds metadata about detected format and validates structure.
        """
        import json

        if not output or output == "(no output)":
            return output

        stripped = output.strip()

        # Try JSON detection
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                parsed = json.loads(stripped)
                # Valid JSON detected
                format_info = "[Auto-detected: JSON output]\n"
                if isinstance(parsed, dict):
                    format_info += f"[Structure: Object with {len(parsed)} keys]\n"
                elif isinstance(parsed, list):
                    format_info += f"[Structure: Array with {len(parsed)} items]\n"
                return format_info + output
            except json.JSONDecodeError:
                pass  # Not valid JSON, continue

        # Try YAML detection
        try:
            import yaml
            # Only attempt if it looks like YAML (has colons, indentation patterns)
            if ':' in stripped and not stripped.startswith('Error'):
                # Check for YAML-like patterns
                lines = stripped.split('\n')
                yaml_indicators = 0
                for line in lines[:10]:  # Check first 10 lines
                    if line.strip() and ':' in line:
                        # Key: value pattern
                        if line.strip().endswith(':') or ': ' in line:
                            yaml_indicators += 1
                    if line.startswith('  ') or line.startswith('- '):
                        yaml_indicators += 1

                if yaml_indicators >= 3:  # Likely YAML
                    try:
                        parsed = yaml.safe_load(stripped)
                        if isinstance(parsed, (dict, list)):
                            format_info = "[Auto-detected: YAML output]\n"
                            if isinstance(parsed, dict):
                                format_info += f"[Structure: Object with {len(parsed)} keys]\n"
                            elif isinstance(parsed, list):
                                format_info += f"[Structure: Array with {len(parsed)} items]\n"
                            return format_info + output
                    except Exception:
                        pass  # Not valid YAML
        except ImportError:
            pass  # PyYAML not available

        # Return original output if no format detected
        return output

    def _run_command_streaming(self, command: str, timeout: int, show_progress: bool = True) -> str:
        """Run a command with streaming output (for all commands)."""
        import threading
        import time
        import os

        output_lines = []
        process = None

        try:
            # Set environment to force unbuffered output
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['NODE_ENV'] = 'development'
            # Force npm/npx to be non-interactive
            env['CI'] = 'true'  # Many tools check this to skip prompts
            env['npm_config_yes'] = 'true'  # Skip npm prompts

            # Start the process with pipes
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                env=env
            )

            # Read output with timeout
            start_time = time.time()
            last_output_time = start_time

            def read_output():
                nonlocal last_output_time
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            output_lines.append(line.rstrip())
                            last_output_time = time.time()
                            # Print progress indicator (only for long-running commands)
                            if show_progress and len(output_lines) % 10 == 0:
                                print(f"   ... {len(output_lines)} lines processed")
                except Exception:
                    pass  # Handle closed pipe

            reader_thread = threading.Thread(target=read_output)
            reader_thread.daemon = True
            reader_thread.start()

            # Wait for process with timeout
            stall_warning_shown = False
            while process.poll() is None:
                elapsed = time.time() - start_time
                stall_time = time.time() - last_output_time

                if elapsed > timeout:
                    process.kill()
                    return f"Error: Command timed out after {timeout}s\nPartial output ({len(output_lines)} lines):\n" + "\n".join(output_lines[-50:])

                # Warn if no output for 30 seconds (might be waiting for input)
                if stall_time > 30 and not stall_warning_shown and show_progress:
                    print(f"   ⚠️  No output for 30s - command may be waiting for input")
                    print(f"   Press Ctrl+C to interrupt if stuck")
                    stall_warning_shown = True

                time.sleep(0.5)

            # Wait for reader to finish
            reader_thread.join(timeout=5)

            # Combine output
            output = "\n".join(output_lines)
            max_output = self.config.max_command_output

            if len(output) > max_output:
                # Show last part for long outputs
                output = "... [truncated, showing last portion]\n" + output[-max_output:]

            if show_progress:
                print(f"   ✓ Command completed ({len(output_lines)} lines)")
            return output if output else "(no output)"

        except Exception as e:
            if process:
                process.kill()
            return f"Error running command: {str(e)}"

    def _get_user_confirmation(self, action: str, params: dict) -> bool:
        """Ask user for confirmation before executing action."""
        # Auto-approve safe read-only operations
        safe_actions = ['read_file', 'list_files', 'search_files', 'search_code', 'git_status', 'git_log', 'git_diff']
        if action in safe_actions:
            print(f"Agent wants to: {action}")
            print(f"Parameters: {json.dumps(params, indent=2)}")
            print("Auto-approved (safe operation)")
            return True

        print(f"\nAgent wants to: {action}")
        print(f"Parameters: {json.dumps(params, indent=2)}")

        # Show preview for write operations
        if action == 'write_file' and 'content' in params:
            content = params['content']
            max_preview = self.config.write_preview_truncation
            preview = content[:max_preview] + "..." if len(content) > max_preview else content
            print(f"\nContent preview:\n{preview}")

        try:
            response = input("Allow? [y/N]: ").strip().lower()
            return response in ('y', 'yes')
        except (KeyboardInterrupt, EOFError):
            print("\nAction cancelled.")
            raise  # Re-raise to stop the agent loop

    def _parse_agent_response(self, response_text: str) -> dict:
        """Parse the agent's JSON response with robust error handling."""
        # Try to extract JSON from response
        text = response_text.strip()

        def fix_json_string(s: str) -> str:
            """Fix common JSON issues from LLM output."""
            # Replace Python booleans with JSON booleans
            s = re.sub(r'\bTrue\b', 'true', s)
            s = re.sub(r'\bFalse\b', 'false', s)
            s = re.sub(r'\bNone\b', 'null', s)
            return s

        # Handle markdown code blocks
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            if end > start:
                text = text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            if end > start:
                text = text[start:end].strip()

        # Try to parse as-is first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try fixing Python-style booleans
        try:
            fixed_text = fix_json_string(text)
            return json.loads(fixed_text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object with proper brace matching
        try:
            start = text.find('{')
            if start != -1:
                brace_count = 0
                end = start
                for i in range(start, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break

                if end > start:
                    json_str = fix_json_string(text[start:end])
                    return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            pass

        # Try to extract key fields using regex as last resort
        thought_match = re.search(r'"thought"\s*:\s*"([^"]+)"', text)
        action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)

        if thought_match and action_match:
            # Found at least thought and action, try to reconstruct
            result = {
                'thought': thought_match.group(1),
                'action': action_match.group(1),
                'parameters': {},
                'is_complete': False
            }

            # Try to extract parameters
            params_match = re.search(r'"parameters"\s*:\s*(\{[^}]+\})', text)
            if params_match:
                try:
                    result['parameters'] = json.loads(fix_json_string(params_match.group(1)))
                except:
                    pass

            # Check for is_complete
            if re.search(r'"is_complete"\s*:\s*true', text, re.IGNORECASE):
                result['is_complete'] = True

            return result

        # Return error response - but don't mark as complete so agent retries
        return {
            'thought': 'Failed to parse LLM response as JSON',
            'action': 'retry_parse',  # Special action indicating parse failure
            'parameters': {'raw_response': response_text[:500]},
            'is_complete': False,  # Don't complete on parse error - allow retry
            'result': f'Parse error: {response_text[:200]}'
        }

    # ========== Decoupled Agent Loop Methods ==========

    def _think(self, state: ConversationState) -> AgentThought:
        """
        Generate the next thought/action from the LLM.

        This is the reasoning stage where the agent decides what to do next.

        Args:
            state: Current conversation state

        Returns:
            AgentThought containing raw LLM response
        """
        print(f"[{self.planner}] Thinking...")

        # Build the prompt with conversation history for multi-turn
        if len(state.messages) == 2:
            # First iteration: just use the task
            user_prompt = state.messages[-1]['content']
        else:
            # Subsequent iterations: include conversation history
            history_parts = []
            for msg in state.messages[2:]:  # Skip system prompt and initial task
                role = msg['role'].upper()
                history_parts.append(f"{role}: {msg['content']}")
            history_text = "\n\n".join(history_parts)
            user_prompt = f"Previous conversation:\n{history_text}\n\nBased on the above, continue with the task. Remember to respond with valid JSON."

        response = self.orch.delegate(
            self.planner,
            user_prompt,
            system_prompt=state.system_prompt,
            max_tokens=self.config.default_max_tokens,
            temperature=self.config.default_temperature,
            use_context=False  # Context already in system prompt
        )

        return AgentThought(
            raw_response=response.content,
            provider=self.planner,
            iteration=state.iteration
        )

    def _plan_action(self, thought: AgentThought) -> AgentAction:
        """
        Parse the LLM response into a structured action.

        This is the planning stage where we extract the action to take.

        Args:
            thought: Raw thought from _think()

        Returns:
            AgentAction with parsed action details
        """
        action_data = self._parse_agent_response(thought.raw_response)

        return AgentAction(
            thought=action_data.get('thought', 'No thought provided'),
            action=action_data.get('action', 'error'),
            parameters=action_data.get('parameters', {}),
            is_complete=action_data.get('is_complete', False),
            result_text=action_data.get('result', '')
        )

    def _execute(self, action: AgentAction, state: ConversationState) -> ActionResult:
        """
        Execute the planned action (tool call).

        This is the execution stage where the tool is actually run.

        Args:
            action: Parsed action from _plan_action()
            state: Current conversation state (for auto_confirm)

        Returns:
            ActionResult with execution details
        """
        print(f"\nThought: {action.thought}")

        # Handle parse failure - provide feedback to LLM to retry with valid JSON
        if action.action == 'retry_parse':
            # Show what the LLM actually returned for debugging
            raw_response = action.parameters.get('raw_response', 'No response captured')
            print(f"⚠️ Response parsing failed. LLM returned:\n{raw_response[:300]}...")
            print("Requesting JSON format retry...")
            error_msg = (
                "Your previous response could not be parsed as JSON. "
                "You MUST respond with ONLY a valid JSON object (no other text). "
                "Use this exact format:\n"
                '{\n'
                '  "thought": "Your reasoning here",\n'
                '  "action": "tool_name",\n'
                '  "parameters": {"param": "value"},\n'
                '  "is_complete": false\n'
                '}\n'
                "Available tools: read_file, write_file, list_files, list_directory, search_code, run_command\n"
                "Make sure all strings are properly quoted with double quotes. Do not include any text outside the JSON object."
            )
            return ActionResult(
                success=False,
                output=error_msg,
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Check if this is a valid tool action
        if action.action not in self.tools or action.action == 'complete':
            return ActionResult(
                success=True,  # Not a failure, just no execution
                output="",
                action=action.action,
                parameters=action.parameters,
                approved=True,
                executed=False
            )

        # Handle unknown actions
        if action.action not in self.tools and action.action != 'complete' and action.action != 'error':
            print(f"Unknown action: {action.action}")
            return ActionResult(
                success=False,
                output=f"Unknown action '{action.action}'. Available tools: {', '.join(self.tools.keys())}",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Get user confirmation (unless auto_confirm)
        if state.auto_confirm:
            approved = True
        else:
            approved = self._get_user_confirmation(action.action, action.parameters)

        if not approved:
            print("Action denied by user")
            self._log_action(action.action, action.parameters, "Denied by user", False)
            return ActionResult(
                success=False,
                output="Denied by user",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Execute the tool
        print(f"Executing: {action.action}")
        tool_result = self.tools[action.action](**action.parameters)

        max_display = self.config.result_display_truncation
        if len(tool_result) > max_display:
            print(f"Result: {tool_result[:max_display]}...")
        else:
            print(f"Result: {tool_result}")

        self._log_action(action.action, action.parameters, tool_result, True)

        return ActionResult(
            success=True,
            output=tool_result,
            action=action.action,
            parameters=action.parameters,
            approved=True,
            executed=True
        )

    def _evaluate(
        self,
        action: AgentAction,
        result: ActionResult,
        state: ConversationState
    ) -> EvaluationResult:
        """
        Evaluate whether the task is complete and if we should continue.

        This is the evaluation stage where we check completion criteria.

        Args:
            action: The action that was planned
            result: The result of executing the action
            state: Current conversation state

        Returns:
            EvaluationResult indicating whether to continue or complete
        """
        # Check if task is complete (AFTER executing any actions)
        if action.is_complete or action.action == 'complete':
            # Verify that at least one meaningful action was performed
            meaningful_actions = [
                t for t in state.tools_executed
                if t in self.config.meaningful_actions
            ]

            if not meaningful_actions and not self.dry_run:
                print(f"\nWarning: Agent declared completion without performing any file operations.")
                print("Requesting agent to actually execute the task...")
                return EvaluationResult(
                    is_complete=False,
                    should_continue=True,
                    reason="No meaningful actions performed yet"
                )

            final_result = action.result_text or 'Task completed'
            print(f"\nResult: {final_result}")
            self._log_action('complete', {}, final_result, True)

            return EvaluationResult(
                is_complete=True,
                should_continue=False,
                reason="Task marked as complete",
                final_result=final_result
            )

        # Smart completion: Check if primary goal was achieved
        if result.executed and result.action in ['write_file', 'run_command']:
            if 'Successfully wrote' in result.output or 'successfully' in result.output.lower():
                # Check if this was likely the main task
                write_actions = [t for t in state.tools_executed if t == 'write_file']
                if len(write_actions) >= 1 and state.iteration >= 2:
                    # File was written successfully - likely complete
                    print(f"\nTask goal achieved. Stopping execution.")
                    return EvaluationResult(
                        is_complete=True,
                        should_continue=False,
                        reason="Primary goal achieved (file written successfully)",
                        final_result=result.output
                    )

        # Check max iterations
        if state.iteration >= state.max_iterations:
            return EvaluationResult(
                is_complete=False,
                should_continue=False,
                reason=f"Max iterations ({state.max_iterations}) reached"
            )

        # Continue with more iterations
        return EvaluationResult(
            is_complete=False,
            should_continue=True,
            reason="Task not yet complete"
        )

    def _update_conversation(
        self,
        state: ConversationState,
        thought: AgentThought,
        action: AgentAction,
        result: ActionResult
    ) -> None:
        """
        Update the conversation history based on the action and result.

        Args:
            state: Conversation state to update
            thought: The raw thought from LLM
            action: The parsed action
            result: The execution result
        """
        if result.executed:
            # Tool was executed successfully
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': f"Tool result for {result.action}:\n{result.output}\n\nContinue with the task or mark as complete if done."
            })
            state.tools_executed.append(result.action)
        elif not result.approved and result.action in self.tools:
            # Tool was denied by user
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': f"User denied the {result.action} action. Please try a different approach or explain why this action is necessary."
            })
        elif action.action == 'retry_parse':
            # Parse failure - provide detailed JSON format instructions
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': result.output  # Contains the detailed JSON format instructions
            })
        elif action.action not in self.tools and action.action != 'complete' and action.action != 'error':
            # Unknown action
            state.messages.append({
                'role': 'assistant',
                'content': thought.raw_response
            })
            state.messages.append({
                'role': 'user',
                'content': f"Unknown action '{action.action}'. Available tools: {', '.join(self.tools.keys())}"
            })
        elif action.is_complete and not result.executed:
            # Agent wants to complete but no action executed and no meaningful work done
            meaningful_actions = [t for t in state.tools_executed if t in self.config.meaningful_actions]
            if not meaningful_actions and not self.dry_run:
                state.messages.append({
                    'role': 'assistant',
                    'content': thought.raw_response
                })
                state.messages.append({
                    'role': 'user',
                    'content': "You declared the task complete but haven't actually created or modified any files. Please respond with a JSON object containing an action to execute. Use the write_file tool to actually create the requested code. Example format:\n{\n  \"thought\": \"your reasoning\",\n  \"action\": \"write_file\",\n  \"parameters\": {\"path\": \"filename\", \"content\": \"code here\"}\n}"
                })

    def run(self, task: str, max_iterations: int = 10, auto_confirm: bool = False) -> dict:
        """
        Run the agent on a task using decoupled stages.

        The agent loop follows clear stages:
        1. Think - LLM generates next thought/action
        2. Plan - Parse response into structured action
        3. Execute - Run the tool
        4. Evaluate - Check if task is complete

        Args:
            task: The task to accomplish
            max_iterations: Maximum number of tool uses
            auto_confirm: Skip user confirmation (use with caution)

        Returns:
            dict with 'success', 'result', 'audit_log'
        """
        # Update tool context dry_run state
        self.tool_context.dry_run = self.dry_run

        # Concise header
        task_preview = task[:80] + "..." if len(task) > 80 else task
        print(f"\n🤖 Agent: {task_preview}")
        if self.dry_run:
            print("[DRY RUN MODE]")

        # Build initial context
        context_info = ""
        if self.orch.context.is_explored():
            context_info = f"\nProject Context:\n{self.orch.context.get_summary()}\n"

        # System prompt for agent
        tool_descriptions = self._get_tool_descriptions()
        platform_name = get_platform_name()
        platform_guidance = ""
        if is_windows():
            platform_guidance = """
IMPORTANT - Platform: Windows
- Do NOT use Unix commands (grep, cat, sed, awk, find, xargs, etc.)
- Use Python code or PowerShell equivalents instead
- For searching files, use the search_code tool (not grep)
- For reading files, use the read_file tool (not cat)
- For listing files, use the list_files tool (not ls or find)
- When running shell commands, use Windows commands (dir, type, etc.)
"""
        else:
            platform_guidance = f"""
Platform: {platform_name}
- Unix commands (grep, cat, sed, etc.) are available
"""

        system_prompt = f"""You are a code agent that helps with programming tasks.
You have access to tools to read, write, and analyze code.

{tool_descriptions}

{context_info}
{platform_guidance}

Important:
- Always explain your reasoning in the "thought" field
- RESPOND WITH VALID JSON ONLY - use lowercase true/false/null, not Python's True/False/None
- Use read_file to understand existing code before modifying
- Make incremental changes, not massive rewrites
- Test your changes when possible
- Be careful with file paths (relative to project root)
- For requirements.txt: Analyze actual import statements in *.py files, NOT pip freeze (which gives ALL installed packages)

CRITICAL - write_file usage:
- NEVER call write_file with empty content - this WILL fail
- Always include the COMPLETE file content in one write_file call
- Do NOT create empty files then fill them later
- Plan your file content fully before calling write_file

Current task: {task}
"""

        # Initialize conversation state
        state = ConversationState(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Please complete this task: {task}"}
            ],
            system_prompt=system_prompt,
            iteration=0,
            max_iterations=max_iterations,
            tools_executed=[],
            auto_confirm=auto_confirm
        )

        # Main agent loop - decoupled stages
        while state.iteration < state.max_iterations:
            state.iteration += 1
            # Minimal iteration indicator (only show on first iteration)
            if state.iteration == 1:
                print(f"Working...")

            # Stage 1: Think - LLM generates next thought/action
            thought = self._think(state)

            # Stage 2: Plan - Parse response into structured action
            action = self._plan_action(thought)

            # Stage 3: Execute - Run the tool
            result = self._execute(action, state)

            # Stage 4: Evaluate - Check if task is complete
            evaluation = self._evaluate(action, result, state)

            # Update conversation history
            self._update_conversation(state, thought, action, result)

            # Check evaluation result
            if evaluation.is_complete:
                return {
                    'success': True,
                    'result': evaluation.final_result,
                    'iterations': state.iteration,
                    'audit_log': self.audit_log
                }

            if not evaluation.should_continue:
                # Max iterations or other stopping condition
                return {
                    'success': False,
                    'result': evaluation.reason,
                    'iterations': state.iteration,
                    'audit_log': self.audit_log
                }

        # Max iterations reached (shouldn't get here but safety check)
        return {
            'success': False,
            'result': f'Max iterations ({max_iterations}) reached',
            'iterations': state.iteration,
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
