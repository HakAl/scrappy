"""
Core Code Agent implementation.

The main CodeAgent class with tool use and safety features.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional, Union

from ..agent_config import AgentConfig
from ..agent_tools.tools import ToolRegistry, ToolContext
from ..agent_tools.tools.command_tool import ShellCommandExecutor


def safe_print(*args, **kwargs):
    """
    Print function that safely handles Unicode encoding errors on Windows.

    Replaces unencodable characters instead of crashing with 'charmap' codec error.
    """
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Fallback: encode with 'replace' error handling
        text = ' '.join(str(arg) for arg in args)
        # Replace problematic characters with '?'
        safe_text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        # Try to print the safe version
        try:
            print(safe_text, **kwargs)
        except Exception:
            # Last resort: strip all non-ASCII
            ascii_text = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(ascii_text, **kwargs)
    except Exception as e:
        # Catch-all for any other print errors
        try:
            print(f"[Output encoding error: {type(e).__name__}]", **kwargs)
        except Exception:
            pass  # Give up silently if we can't print at all
from ..orchestrator_adapter import (
    OrchestratorAdapter,
    AgentOrchestratorAdapter,
)
from ..agent_tools.registry_factory import create_default_registry
from ..platform_utils import get_platform_name, is_windows, validate_command_for_platform

from .types import (
    AgentThought,
    AgentAction,
    ActionResult,
    EvaluationResult,
    ConversationState
)
from .audit import AuditLogger
from .response_parser import ResponseParser, JSONResponseParser, ParseResult


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
        self.dry_run = False

        # Initialize audit logger
        self._audit_logger = AuditLogger(
            max_result_length=self.config.audit_log_result_truncation
        )

        # Initialize response parser (defaults to JSON parsing)
        self._response_parser: ResponseParser = JSONResponseParser()

        # Create tool context
        safe_print("Preparing agent tools...")
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
            self.tool_registry = create_default_registry()

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

        # Create command executor (extracted from inline implementation)
        self._command_executor = ShellCommandExecutor(self.config)

        # Use orchestrator's intelligent provider selection
        safe_print("Selecting AI providers...")
        available = self.adapter.list_providers()

        # Store orchestrator reference for dynamic provider selection
        self._orchestrator = orchestrator

        # Check if orchestrator supports smart provider selection
        self._use_dynamic_selection = hasattr(orchestrator, 'get_recommended_provider')

        if self._use_dynamic_selection:
            # Let orchestrator decide provider based on task type and rate limits
            # Get initial recommendation for display purposes
            if hasattr(orchestrator, 'get_recommended_provider'):
                self.planner = orchestrator.get_recommended_provider('planning')
                self.executor = orchestrator.get_recommended_provider('execution')
            else:
                self.planner = available[0] if available else None
                self.executor = self.planner
        else:
            # Fallback to legacy static selection if orchestrator doesn't support it
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

    @property
    def audit_log(self):
        """Get the audit log (backward compatibility)."""
        return self._audit_logger.get_log()

    def _log_action(self, action: str, params: dict, result: str, approved: bool):
        """Log an action to the audit trail."""
        self._audit_logger.log_action(action, params, result, approved)

    def _tool_run_command(self, command: str) -> str:
        """Run a shell command using the extracted command executor."""
        # Check for interactive commands BEFORE delegating to executor
        # This is agent-specific behavior that requires user prompting
        cmd_lower = command.lower()
        for pattern in self.config.interactive_commands:
            if pattern in cmd_lower:
                safe_print(f"Warning: '{pattern}' may require interactive input")
                # Suggest workarounds for common cases
                if 'npx' in cmd_lower:
                    safe_print("   Tip: Add '-y' flag to skip prompts: npx -y create-react-app ...")
                # Ask if user wants interactive mode
                try:
                    use_interactive = input("   Run in interactive mode (you can respond to prompts)? [Y/n]: ").strip().lower()
                    if use_interactive != 'n':
                        return self._run_command_interactive(command)
                except (KeyboardInterrupt, EOFError):
                    safe_print("\n   Skipping interactive mode, running with captured output...")
                break

        # Delegate to the command executor for all other processing
        # This includes: security checks, platform fixes, retries, output parsing
        return self._command_executor.run(command, self.project_root, dry_run=self.dry_run)

    def _run_command_interactive(self, command: str) -> str:
        """
        Run a command in interactive mode - passes I/O directly to terminal.
        User can respond to prompts directly.
        """
        safe_print(f"\n{'='*60}")
        safe_print(f"Running in INTERACTIVE MODE")
        safe_print(f"Command: {command}")
        safe_print(f"You can respond to any prompts. Output goes directly to terminal.")
        safe_print(f"{'='*60}\n")

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

            safe_print(f"\n{'='*60}")
            safe_print(f"Command finished with exit code: {result.returncode}")
            safe_print(f"{'='*60}\n")

            if result.returncode == 0:
                return f"Command completed successfully (exit code 0). Output was displayed directly to terminal."
            else:
                return f"Command finished with exit code {result.returncode}. Check terminal output for details."

        except KeyboardInterrupt:
            safe_print(f"\n{'='*60}")
            safe_print(f"Command stopped by user (Ctrl+C)")
            safe_print(f"{'='*60}\n")

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

    def _categorize_command_approach(self, command: str) -> str:
        """
        Categorize a command into an approach type for retry tracking.

        This helps detect when the LLM is retrying the same failing approach.
        Delegates to the command executor's implementation.

        Args:
            command: The shell command

        Returns:
            String describing the approach type
        """
        return self._command_executor._categorize_command_approach(command)

    def _check_retry_pattern(self, command: str, failed_commands: list) -> str:
        """
        Check if a command follows a pattern that has already failed.

        Delegates to the command executor's implementation.

        Args:
            command: The command about to be executed
            failed_commands: List of previously failed commands with their approaches

        Returns:
            Warning message if retry pattern detected, empty string otherwise
        """
        return self._command_executor._check_retry_pattern(command, failed_commands)

    def _get_user_confirmation(self, action: str, params: dict) -> bool:
        """Ask user for confirmation before executing action."""
        # Auto-approve safe read-only operations
        safe_actions = ['read_file', 'list_files', 'list_directory', 'search_files', 'search_code', 'git_status', 'git_log', 'git_diff']
        if action in safe_actions:
            safe_print(f"Agent wants to: {action}")
            safe_print(f"Parameters: {json.dumps(params, indent=2)}")
            safe_print("Auto-approved (safe operation)")
            return True

        safe_print(f"\nAgent wants to: {action}")
        safe_print(f"Parameters: {json.dumps(params, indent=2)}")

        # Show preview for write operations
        if action == 'write_file' and 'content' in params:
            content = params['content']
            max_preview = self.config.write_preview_truncation
            preview = content[:max_preview] + "..." if len(content) > max_preview else content
            safe_print(f"\nContent preview:\n{preview}")

        try:
            response = input("Allow? [y/N]: ").strip().lower()
            return response in ('y', 'yes')
        except (KeyboardInterrupt, EOFError):
            safe_print("\nAction cancelled.")
            raise  # Re-raise to stop the agent loop

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
        import sys
        import time

        # Get current recommended provider (may change between calls due to rate limits)
        if self._use_dynamic_selection and hasattr(self._orchestrator, 'get_recommended_provider'):
            current_provider = self._orchestrator.get_recommended_provider('planning')
            # Update cached value for display
            self.planner = current_provider
        else:
            current_provider = self.planner

        # Show progress indicator during API call
        if state.iteration == 1:
            safe_print(f"[{current_provider}] Analyzing task (this may take a moment)...")
        else:
            safe_print(f"[{current_provider}] Thinking...")

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

        # Track API call time for first iteration
        start_time = time.time()

        # Delegate with task_type so orchestrator can make intelligent decisions
        # If orchestrator supports auto-selection, let it choose; otherwise specify provider
        if self._use_dynamic_selection:
            response = self.orch.delegate(
                provider_name=None,  # Let orchestrator decide
                prompt=user_prompt,
                system_prompt=state.system_prompt,
                max_tokens=self.config.default_max_tokens,
                temperature=self.config.default_temperature,
                use_context=False,  # Context already in system prompt
                task_type='planning'  # Inform orchestrator this is a planning task
            )
            # Update planner to reflect what was actually used
            actual_provider = response.provider
        else:
            response = self.orch.delegate(
                current_provider,
                user_prompt,
                system_prompt=state.system_prompt,
                max_tokens=self.config.default_max_tokens,
                temperature=self.config.default_temperature,
                use_context=False  # Context already in system prompt
            )
            actual_provider = current_provider

        # Report latency on first call (helps user understand wait times)
        if state.iteration == 1:
            elapsed = time.time() - start_time
            safe_print(f"[{actual_provider}] Response received ({elapsed:.1f}s)")

        return AgentThought(
            raw_response=response.content,
            provider=actual_provider,
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
        # Use the injected response parser (JSON by default, native tool calls in future)
        parse_result = self._response_parser.parse(thought.raw_response)

        return AgentAction(
            thought=parse_result.thought,
            action=parse_result.action,
            parameters=parse_result.parameters,
            is_complete=parse_result.is_complete,
            result_text=parse_result.result_text
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
        safe_print(f"\nThought: {action.thought}")

        # Handle parse failure - provide feedback to LLM to retry with valid JSON
        if action.action == 'retry_parse':
            # Show what the LLM actually returned for debugging
            raw_response = action.parameters.get('raw_response', 'No response captured')
            safe_print(f"Response parsing failed. LLM returned:\n{raw_response[:300]}...")
            safe_print("Requesting JSON format retry...")
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
            safe_print(f"Unknown action: {action.action}")
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
            safe_print("Action denied by user")
            self._log_action(action.action, action.parameters, "Denied by user", False)
            return ActionResult(
                success=False,
                output="Denied by user",
                action=action.action,
                parameters=action.parameters,
                approved=False,
                executed=False
            )

        # Check for retry patterns - detect if same approach is being repeated
        if action.action == 'run_command' and state.failed_commands:
            command = action.parameters.get('command', '')
            retry_warning = self._check_retry_pattern(command, state.failed_commands)
            if retry_warning:
                safe_print(f"[Retry Warning] {retry_warning}")
                # Add warning to state for next iteration
                state.retry_warnings.append(retry_warning)

        # Execute the tool
        safe_print(f"Executing: {action.action}")
        tool_result = self.tools[action.action](**action.parameters)

        # Track failed commands for retry detection
        if action.action == 'run_command':
            command = action.parameters.get('command', '')
            if 'Error' in tool_result or 'failed' in tool_result.lower():
                # Categorize the approach for better tracking
                approach = self._categorize_command_approach(command)
                state.failed_commands.append({
                    'command': command,
                    'error': tool_result[:200],  # Truncate error
                    'approach': approach,
                    'iteration': state.iteration
                })
                safe_print(f"   [Tracked] Failed '{approach}' approach - will suggest alternatives")

                # Check if this is a scaffolding approach
                scaffolding_approaches = [
                    'spring_initializr_download', 'curl_download',
                    'powershell_download', 'npm_create_project'
                ]

                # If ANY scaffolding approach failed, inject strong write_file suggestion
                if approach in scaffolding_approaches:
                    scaffolding_failures = sum(
                        1 for f in state.failed_commands
                        if f['approach'] in scaffolding_approaches
                    )
                    if scaffolding_failures >= 1:
                        warning = (
                            f"MANDATORY STRATEGY CHANGE: Scaffolding/download approaches have failed {scaffolding_failures} time(s). "
                            f"You MUST now use write_file tool to create project files directly. "
                            f"Do NOT attempt any more curl, npm create, or spring initializr commands. "
                            f"For Spring Boot: write_file to create pom.xml, Application.java, etc. "
                            f"For React: write_file to create package.json, App.jsx, etc."
                        )
                        state.retry_warnings.append(warning)
                        safe_print(f"   [MANDATORY] Switching to write_file strategy after scaffolding failure")

                # If same approach failed twice, inject strong warning
                approach_failures = sum(1 for f in state.failed_commands if f['approach'] == approach)
                if approach_failures >= 2:
                    warning = (
                        f"CRITICAL: The '{approach}' approach has failed {approach_failures} times. "
                        f"You MUST try a completely different strategy. "
                        f"If using shell commands, switch to write_file tool instead."
                    )
                    state.retry_warnings.append(warning)

        max_display = self.config.result_display_truncation
        if len(tool_result) > max_display:
            safe_print(f"Result: {tool_result[:max_display]}...")
        else:
            safe_print(f"Result: {tool_result}")

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
                safe_print(f"\nWarning: Agent declared completion without performing any file operations.")
                safe_print("Requesting agent to actually execute the task...")
                return EvaluationResult(
                    is_complete=False,
                    should_continue=True,
                    reason="No meaningful actions performed yet"
                )

            final_result = action.result_text or 'Task completed'
            safe_print(f"\nResult: {final_result}")
            self._log_action('complete', {}, final_result, True)

            return EvaluationResult(
                is_complete=True,
                should_continue=False,
                reason="Task marked as complete",
                final_result=final_result
            )

        # Smart completion: DISABLED - rely on explicit agent completion signals
        # The heuristic approach was too aggressive, stopping after simple write operations
        # even when the task had multiple components. Let the LLM decide when it's done.
        #
        # Previous logic checked for write_file operations and declared "done" prematurely.
        # This caused issues with complex multi-part tasks (e.g., backend + frontend).
        #
        # Now the agent must explicitly call action='complete' or set is_complete=True.
        # This gives the LLM control over task completion semantics.
        pass  # Intentionally disabled heuristic completion

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

            # Build user message with tool result and any retry warnings
            user_message = f"Tool result for {result.action}:\n{result.output}\n"

            # Inject retry warnings if any failures were tracked
            if state.retry_warnings:
                user_message += "\n--- IMPORTANT WARNINGS ---\n"
                for warning in state.retry_warnings:
                    user_message += f"- {warning}\n"
                user_message += "--- END WARNINGS ---\n"
                # Clear warnings after injecting
                state.retry_warnings.clear()

            user_message += "\nContinue with the task or mark as complete if done."

            state.messages.append({
                'role': 'user',
                'content': user_message
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

        # Enable auto-save for crash safety
        self._audit_logger.enable_auto_save(self.project_root, ".llm_agent_audit.json")
        self._audit_logger.set_task_info(task, max_iterations, auto_confirm)

        # Concise header
        task_preview = task[:80] + "..." if len(task) > 80 else task
        safe_print(f"\n[Agent] {task_preview}")
        if self.dry_run:
            safe_print("[DRY RUN MODE]")

        # Build initial context
        safe_print("Building context...")

        # System prompt for agent - use PromptBuilder for context-aware construction
        safe_print("Preparing system prompt...")
        from src.agent.prompt_builder import PromptBuilder

        # Create PromptBuilder with tool registry for unified prompt generation
        prompt_builder = PromptBuilder(
            context=self.orch.context,
            tool_registry=self.tool_registry
        )

        # Build the complete system prompt with task context
        # PromptBuilder now includes all operational guidance (strategy, efficiency,
        # completion semantics, safety rules) as proper sections
        system_prompt = prompt_builder.build(task=task)

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

        # Main agent loop - decoupled stages with crash safety
        safe_print("Starting agent loop...")
        try:
            while state.iteration < state.max_iterations:
                state.iteration += 1
                # Minimal iteration indicator (only show on first iteration)
                if state.iteration == 1:
                    safe_print(f"Working...")

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
                    self._audit_logger.mark_complete(True, evaluation.final_result)
                    return {
                        'success': True,
                        'result': evaluation.final_result,
                        'iterations': state.iteration,
                        'audit_log': self.audit_log
                    }

                if not evaluation.should_continue:
                    # Max iterations or other stopping condition
                    self._audit_logger.mark_complete(False, evaluation.reason)
                    return {
                        'success': False,
                        'result': evaluation.reason,
                        'iterations': state.iteration,
                        'audit_log': self.audit_log
                    }

            # Max iterations reached (shouldn't get here but safety check)
            self._audit_logger.mark_complete(False, f'Max iterations ({max_iterations}) reached')
            return {
                'success': False,
                'result': f'Max iterations ({max_iterations}) reached',
                'iterations': state.iteration,
                'audit_log': self.audit_log
            }
        except KeyboardInterrupt:
            # User cancelled - save partial state
            safe_print("\nAgent interrupted by user. Saving audit log...")
            self._audit_logger.mark_complete(False, "Interrupted by user (KeyboardInterrupt)")
            raise  # Re-raise to let caller handle
        except Exception as e:
            # Unexpected error - save partial state for debugging
            safe_print(f"\nAgent error: {str(e)}. Saving audit log...")
            self._audit_logger.mark_complete(False, f"Error: {str(e)}")
            raise  # Re-raise to let caller handle

    def get_audit_log(self) -> list:
        """Get the audit log of all actions."""
        return self.audit_log

    def save_audit_log(self, path: str = ".agent_audit.json"):
        """Save audit log to file."""
        return self._audit_logger.save(self.project_root, path)
