"""
Full agent loop with planning and tool use.
"""

import time
from pathlib import Path
from typing import Optional

from ..classifier import ClassifiedTask, TaskType
from .base import ExecutionResult, ExecutionStrategy, OrchestratorLike


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
                project_path=str(self.project_root)
            )
            # Configure agent settings
            agent.config.max_iterations = self.max_iterations
            agent.require_approval = self.require_approval

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

            # Add task-specific guidance
            guidance = self._get_task_specific_guidance(task)
            if guidance:
                task_with_guidance = f"{task_with_plan}\n{guidance}"
            else:
                task_with_guidance = task_with_plan

            # Execute with agent loop
            run_result = agent.run(task_with_guidance)

            execution_time = time.time() - start_time

            # run_result is a dict with 'success', 'result', 'iterations', 'audit_log'
            if isinstance(run_result, dict):
                success = run_result.get('success', False)
                result_text = run_result.get('result', 'No result')
                iterations = run_result.get('iterations', 0)
                audit_log = run_result.get('audit_log', [])

                # Format output
                output_parts = [f"Agent completed in {iterations} iterations"]
                output_parts.append(f"Result: {result_text}")

                # Include audit log summary
                if audit_log:
                    output_parts.append(f"\nActions taken: {len(audit_log)}")
                    for entry in audit_log[-3:]:  # Show last 3 actions
                        action_name = entry.get('action', 'unknown')
                        output_parts.append(f"  - {action_name}")

                return ExecutionResult(
                    success=success,
                    output="\n".join(output_parts),
                    execution_time=execution_time,
                    tokens_used=0,
                    provider_used="agent_loop",
                    metadata={
                        "iterations": iterations,
                        "audit_log_size": len(audit_log),
                        "final_result": result_text
                    }
                )
            else:
                # Fallback for unexpected return type
                return ExecutionResult(
                    success=False,
                    output=str(run_result),
                    error="Unexpected return type from agent.run()",
                    execution_time=execution_time
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

    def _get_task_specific_guidance(self, task: ClassifiedTask) -> str:
        """
        Generate task-specific guidance to improve agent behavior.

        This adds context and instructions based on the type of task,
        helping the agent make better decisions.
        """
        input_lower = task.original_input.lower()
        guidance_parts = []

        # Requirements.txt creation
        if 'requirements' in input_lower and ('create' in input_lower or 'generate' in input_lower):
            guidance_parts.append("""
CRITICAL GUIDANCE for requirements.txt:
1. FIRST: Search ALL Python imports using: search_code with pattern="^import |^from " and file_pattern="**/*.py"
2. THEN: Identify which packages are THIRD-PARTY (not standard library)
   - STANDARD LIBRARY (DO NOT include): json, os, sys, re, datetime, pathlib, typing, subprocess, etc.
   - THIRD-PARTY (DO include): requests, numpy, pandas, flask, django, etc.
3. FINALLY: Write requirements.txt with ONLY third-party packages

IMPORTANT:
- Do NOT write an empty file first - gather all dependencies BEFORE writing
- Use modern package names: beautifulsoup4 (not bs4), scikit-learn (not sklearn)
- Include version specifiers if known, otherwise just package names
- The 'json' module is STANDARD LIBRARY - do NOT include it

Example format:
requests>=2.28.0
beautifulsoup4>=4.11.0
numpy>=1.24.0
""")

        # Config file creation
        if any(f in input_lower for f in ['config', '.env', 'settings', 'configuration']):
            guidance_parts.append("""
IMPORTANT GUIDANCE for config files:
- First examine existing config patterns in the project
- Use read_file to check for existing config files
- Follow the project's existing configuration style
- Don't include sensitive values, use placeholders
""")

        # Code modification/refactoring
        if any(word in input_lower for word in ['refactor', 'modify', 'update', 'change']):
            guidance_parts.append("""
IMPORTANT GUIDANCE for code modification:
- ALWAYS read the existing file first using read_file
- Understand the current implementation before changing
- Make incremental, targeted changes
- Preserve existing functionality unless asked to remove it
- Test if possible after changes
""")

        # File creation
        if 'create' in input_lower or 'write' in input_lower:
            guidance_parts.append("""
IMPORTANT GUIDANCE for file creation:
- NEVER write an empty file first then fill it later - always include FULL content in one write_file call
- Check if the file already exists first using list_files or read_file
- Follow existing patterns in the project
- Use consistent coding style with the rest of the codebase
- When using write_file, the "content" parameter MUST contain the complete file content
""")

        # Dockerfile creation
        if 'dockerfile' in input_lower:
            guidance_parts.append("""
IMPORTANT GUIDANCE for Dockerfile:
- Analyze the project structure first
- Check for requirements.txt, package.json, or other dependency files
- Use appropriate base image for the project's language
- Follow Docker best practices (multi-stage builds, minimal layers)
""")

        if guidance_parts:
            return "\n".join(guidance_parts)
        return ""

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
