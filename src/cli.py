#!/usr/bin/env python3
"""
Command-line interface for the LLM Agent Team orchestrator.
Provides interactive and one-shot access to multi-provider LLM capabilities.
"""

import click
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from .orchestrator import AgentOrchestrator
except ImportError:
    # Allow running as script
    from orchestrator import AgentOrchestrator


class CLI:
    """Interactive CLI for the LLM Agent Team."""

    def __init__(self, brain: Optional[str] = None, auto_explore: bool = False, context_aware: bool = True):
        """Initialize CLI with orchestrator."""
        click.echo("Initializing LLM Agent Team...")
        self.orchestrator = AgentOrchestrator(
            orchestrator_provider=brain,
            auto_explore=auto_explore,
            context_aware=context_aware
        )
        self.session_start = datetime.now()
        click.echo(f"Brain: {self.orchestrator.brain}")
        click.echo(f"Available providers: {', '.join(self.orchestrator.providers.list_available())}")

        # Show context status
        if self.orchestrator.context.is_explored():
            click.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif context_aware:
            click.secho("Context: Not explored (use /context to explore)", fg="yellow")

        click.echo()

    def interactive_mode(self):
        """Run interactive chat mode."""
        click.echo("=" * 60)
        click.echo("LLM Agent Team - Interactive Mode")
        click.echo("=" * 60)
        click.echo("Commands:")
        click.echo("  /help          - Show all commands")
        click.echo("  /plan <task>   - Create a task plan")
        click.echo("  /reason <q>    - Reason about a question")
        click.echo("  /status        - Show system status")
        click.echo("  /providers     - List available providers")
        click.echo("  /brain <name>  - Switch orchestrator brain")
        click.echo("  /usage         - Show usage statistics")
        click.echo("  /quit or /exit - Exit the CLI")
        click.echo("  /context       - Manage codebase context")
        click.echo("  (any text)     - Chat with current brain")
        click.echo("=" * 60)
        click.echo()

        conversation_history = []

        while True:
            try:
                user_input = click.prompt("You", default="", show_default=False).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    if self._handle_command(user_input, conversation_history):
                        continue
                    else:
                        break

                # Regular chat
                conversation_history.append({
                    "role": "user",
                    "content": user_input
                })

                click.echo("Assistant: ", nl=False)

                response = self.orchestrator.delegate(
                    self.orchestrator.brain,
                    user_input,
                    system_prompt="You are a helpful AI assistant. Be concise and informative."
                )

                click.echo(response.content)
                click.secho(
                    f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                    fg="cyan"
                )
                click.echo()

                conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })

            except click.Abort:
                click.echo("\n\nInterrupted. Type /quit to exit.")
                continue
            except Exception as e:
                click.secho(f"\nError: {e}", fg="red")
                click.echo("Type /help for available commands.\n")

    def _handle_command(self, command: str, history: list) -> bool:
        """
        Handle slash commands. Returns True to continue loop, False to exit.
        """
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ["/quit", "/exit", "/q"]:
            self._show_usage()
            click.echo("\nGoodbye!")
            return False

        elif cmd == "/help":
            self._show_help()

        elif cmd == "/status":
            self._show_status()

        elif cmd == "/providers":
            self._list_providers()

        elif cmd == "/brain":
            self._switch_brain(args)

        elif cmd == "/usage":
            self._show_usage()

        elif cmd == "/plan":
            if not args:
                click.echo("Usage: /plan <task description>")
            else:
                self._plan_task(args)

        elif cmd == "/reason":
            if not args:
                click.echo("Usage: /reason <question>")
            else:
                self._reason(args)

        elif cmd == "/synthesize":
            self._synthesize_mode()

        elif cmd == "/delegate":
            self._delegate_mode(args)

        elif cmd == "/clear":
            history.clear()
            click.secho("Conversation history cleared.", fg="green")

        elif cmd == "/models":
            self._list_models(args)

        elif cmd == "/explore":
            self._explore_codebase(args)

        elif cmd == "/context":
            self._manage_context(args)

        else:
            click.secho(f"Unknown command: {cmd}", fg="yellow")
            click.echo("Type /help for available commands.")

        click.echo()
        return True

    def _show_help(self):
        """Display help information."""
        click.echo("\nAvailable Commands:")
        click.echo("-" * 50)
        click.secho("Chat & Conversation:", bold=True)
        click.echo("  (text)           - Send message to current brain")
        click.echo("  /clear           - Clear conversation history")
        click.echo()
        click.secho("Task Operations:", bold=True)
        click.echo("  /plan <task>     - Break down task into steps")
        click.echo("  /reason <q>      - Analyze question with reasoning")
        click.echo("  /synthesize      - Combine multiple provider responses")
        click.echo("  /delegate <p>    - Send prompt to specific provider")
        click.echo("  /explore [path]  - Explore and learn about a codebase")
        click.echo()
        click.secho("Provider Management:", bold=True)
        click.echo("  /providers       - List all available providers")
        click.echo("  /brain <name>    - Switch orchestrator brain")
        click.echo("  /models [prov]   - List models (optionally for provider)")
        click.echo("  /status          - Show current system status")
        click.echo("  /usage           - Show usage statistics")
        click.echo()
        click.secho("Context Management:", bold=True)
        click.echo("  /context         - Show context status")
        click.echo("  /context explore - Explore current project")
        click.echo("  /context clear   - Clear cached context")
        click.echo("  /context toggle  - Toggle context awareness")
        click.echo()
        click.secho("System:", bold=True)
        click.echo("  /help            - Show this help message")
        click.echo("  /quit or /exit   - Exit the CLI")

    def _show_status(self):
        """Display current system status."""
        status = self.orchestrator.status()

        click.echo("\nSystem Status:")
        click.echo("-" * 50)
        brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
        click.echo(f"Current Brain: {click.style(brain, fg='green', bold=True)}")
        click.echo(f"Total Providers: {len(status.get('available_providers', []))}")
        click.echo(f"Available: {', '.join(status['available_providers'])}")
        click.echo(f"Tasks Completed: {status.get('tasks_executed', 0)}")
        click.echo(f"Session Duration: {datetime.now() - self.session_start}")

    def _list_providers(self):
        """List all providers with their details."""
        click.echo("\nAvailable Providers:")
        click.echo("-" * 50)

        info = self.orchestrator.providers.get_provider_info()

        for name, details in info.items():
            if details['available']:
                limits = details['limits']
                click.secho(f"\n{name.upper()} ", fg="green", bold=True, nl=False)
                click.secho("(Active)", fg="green")
                click.echo(f"  Default Model: {details['default_model']}")
                click.echo(f"  Daily Quota: {limits.requests_per_day:,} requests")
                if limits.tokens_per_minute > 0:
                    click.echo(f"  Token Limit: {limits.tokens_per_minute:,} TPM")
                click.echo(f"  Models: {', '.join(details['models'][:3])}")
                if len(details['models']) > 3:
                    click.echo(f"           ... and {len(details['models']) - 3} more")
            else:
                click.secho(f"\n{name.upper()} ", fg="red", bold=True, nl=False)
                click.secho("(Not Configured)", fg="red")

    def _switch_brain(self, provider_name: str):
        """Switch the orchestrator brain to a different provider."""
        if not provider_name:
            click.echo(f"Current brain: {click.style(self.orchestrator.brain, fg='green', bold=True)}")
            click.echo(f"Available: {', '.join(self.orchestrator.providers.list_available())}")
            click.echo("Usage: /brain <provider_name>")
            return

        provider_name = provider_name.lower().strip()
        available = self.orchestrator.providers.list_available()

        if provider_name not in available:
            click.secho(f"Provider '{provider_name}' not available.", fg="red")
            click.echo(f"Available: {', '.join(available)}")
            return

        old_brain = self.orchestrator.brain
        self.orchestrator.brain = provider_name
        click.secho(f"Brain switched: {old_brain} -> {provider_name}", fg="green")

    def _show_usage(self):
        """Display usage statistics."""
        report = self.orchestrator.get_usage_report()

        click.echo("\nUsage Statistics:")
        click.echo("-" * 50)
        click.echo(f"Total Tasks: {report['total_tasks']}")
        click.echo(f"Session Duration: {report['session_duration']}")

        if report['by_provider']:
            click.echo("\nBy Provider:")
            for provider, stats in report['by_provider'].items():
                click.secho(f"  {provider}:", bold=True)
                click.echo(f"    Requests: {stats['count']}")
                click.echo(f"    Total Tokens: {stats['total_tokens']:,}")
                click.echo(f"    Avg Tokens/Request: {stats['avg_tokens']:.1f}")
                click.echo(f"    Total Latency: {stats['total_latency_ms']:.0f}ms")

    def _plan_task(self, task: str):
        """Create a task plan."""
        click.secho(f"\nPlanning: {task}", bold=True)
        click.echo("-" * 50)

        with click.progressbar(length=1, label="Generating plan") as bar:
            try:
                steps = self.orchestrator.plan(task)
                bar.update(1)
            except Exception as e:
                bar.update(1)
                click.secho(f"Error during planning: {e}", fg="red")
                return

        click.echo()
        if isinstance(steps, list):
            for i, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    click.secho(f"{i}. {step.get('step', 'Step')}", bold=True)
                    click.echo(f"   {step.get('description', '')}")
                    if 'provider_type' in step:
                        click.secho(f"   [Recommended: {step['provider_type']}]", fg="cyan")
                else:
                    click.echo(f"{i}. {step}")
                click.echo()
        else:
            click.echo(steps)

    def _reason(self, question: str):
        """Perform reasoning on a question."""
        click.secho(f"\nReasoning about: {question}", bold=True)
        click.echo("-" * 50)

        with click.progressbar(length=1, label="Analyzing") as bar:
            try:
                response = self.orchestrator.reason(question)
                bar.update(1)
            except Exception as e:
                bar.update(1)
                click.secho(f"Error during reasoning: {e}", fg="red")
                return

        click.echo()
        if isinstance(response, dict):
            click.echo(f"Question: {response.get('question', question)}")
            click.secho(f"\nAnalysis:", bold=True)
            click.echo(response.get('analysis', ''))
            click.secho(f"\nConclusion: ", bold=True, nl=False)
            click.echo(response.get('conclusion', ''))
            click.echo(f"Confidence: {response.get('confidence', 'N/A')}")
        else:
            click.echo(response)

    def _synthesize_mode(self):
        """Interactive synthesis mode - gather responses from multiple providers."""
        click.secho("\nSynthesis Mode", bold=True)
        click.echo("-" * 50)
        click.echo("This will query multiple providers and synthesize their responses.")

        prompt = click.prompt("Enter your question")
        if not prompt:
            click.echo("No question provided.")
            return

        available = self.orchestrator.providers.list_available()
        click.echo(f"\nAvailable providers: {', '.join(available)}")

        providers_input = click.prompt("Providers to query (comma-separated, or 'all')")

        if providers_input.lower() == 'all':
            providers_to_use = available
        else:
            providers_to_use = [p.strip() for p in providers_input.split(",")]
            providers_to_use = [p for p in providers_to_use if p in available]

        if len(providers_to_use) < 2:
            click.secho("Need at least 2 providers for synthesis.", fg="yellow")
            return

        click.echo(f"\nQuerying: {', '.join(providers_to_use)}")

        results = []
        for provider in providers_to_use:
            click.echo(f"  Asking {provider}...", nl=False)
            try:
                response = self.orchestrator.delegate(provider, prompt)
                results.append(response.content)
                click.secho(f" Done ({response.tokens_used} tokens)", fg="green")
            except Exception as e:
                click.secho(f" Error: {e}", fg="red")

        if len(results) < 2:
            click.secho("Not enough responses for synthesis.", fg="yellow")
            return

        click.echo("\nSynthesizing responses...")
        synthesis = self.orchestrator.synthesize(
            results,
            "Combine these perspectives into a comprehensive answer:"
        )

        click.secho(f"\nSynthesized Response:", bold=True)
        click.echo("-" * 50)
        click.echo(synthesis)

    def _delegate_mode(self, args: str):
        """Delegate a task to a specific provider."""
        if not args:
            click.echo("Usage: /delegate <provider> <prompt>")
            click.echo("   or: /delegate (for interactive mode)")

            provider = click.prompt("Provider")
            prompt = click.prompt("Prompt")
        else:
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                click.echo("Usage: /delegate <provider> <prompt>")
                return
            provider, prompt = parts

        if not provider or not prompt:
            click.secho("Both provider and prompt are required.", fg="yellow")
            return

        provider = provider.lower().strip()
        available = self.orchestrator.providers.list_available()

        if provider not in available:
            click.secho(f"Provider '{provider}' not available.", fg="red")
            click.echo(f"Available: {', '.join(available)}")
            return

        click.echo(f"\nDelegating to {provider}...")

        try:
            response = self.orchestrator.delegate(provider, prompt)
            click.secho(f"\nResponse from {provider}:", bold=True)
            click.echo("-" * 50)
            click.echo(response.content)
            click.secho(
                f"\n[{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                fg="cyan"
            )
        except Exception as e:
            click.secho(f"Error: {e}", fg="red")

    def _list_models(self, provider_name: str = ""):
        """List available models."""
        if provider_name:
            provider_name = provider_name.lower().strip()
            available = self.orchestrator.providers.list_available()

            if provider_name not in available:
                click.secho(f"Provider '{provider_name}' not available.", fg="red")
                return

            provider = self.orchestrator.providers.get(provider_name)
            click.secho(f"\n{provider_name.upper()} Models:", bold=True)
            click.echo("-" * 50)
            for model in provider.available_models:
                if model == provider.default_model:
                    click.echo(f"  - {model} ", nl=False)
                    click.secho("(default)", fg="green")
                else:
                    click.echo(f"  - {model}")
        else:
            click.secho("\nAll Available Models:", bold=True)
            click.echo("-" * 50)

            for name in self.orchestrator.providers.list_available():
                provider = self.orchestrator.providers.get(name)
                click.secho(f"\n{name.upper()}:", bold=True)
                for model in provider.available_models:
                    if model == provider.default_model:
                        click.echo(f"  - {model} ", nl=False)
                        click.secho("(default)", fg="green")
                    else:
                        click.echo(f"  - {model}")

    def _explore_codebase(self, path: str = ""):
        """Explore and learn about a codebase."""
        if not path:
            path = click.prompt("Directory to explore", default=".")

        path = Path(path).resolve()
        if not path.exists():
            click.secho(f"Path does not exist: {path}", fg="red")
            return

        if not path.is_dir():
            click.secho(f"Not a directory: {path}", fg="red")
            return

        click.secho(f"\nExploring: {path}", bold=True)
        click.echo("-" * 50)

        # Collect codebase information
        with click.progressbar(length=4, label="Scanning codebase") as bar:
            # Step 1: Find all source files
            source_files = self._find_source_files(path)
            bar.update(1)

            # Step 2: Analyze structure
            structure = self._analyze_structure(path, source_files)
            bar.update(1)

            # Step 3: Read key files
            key_contents = self._read_key_files(path, source_files)
            bar.update(1)

            # Step 4: Generate summary with LLM
            summary = self._generate_codebase_summary(path, structure, key_contents)
            bar.update(1)

        click.echo()
        click.secho("Codebase Summary:", bold=True)
        click.echo("-" * 50)
        click.echo(summary)

        # Offer to save summary
        if click.confirm("\nSave summary to file?", default=False):
            summary_file = path / "CODEBASE_SUMMARY.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"# Codebase Summary\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n")
                f.write(summary)
            click.secho(f"Saved to: {summary_file}", fg="green")

    def _find_source_files(self, path: Path) -> dict:
        """Find all source files organized by type."""
        extensions = {
            'python': ['.py'],
            'javascript': ['.js', '.jsx', '.ts', '.tsx'],
            'web': ['.html', '.css', '.scss'],
            'config': ['.json', '.yaml', '.yml', '.toml', '.ini'],
            'docs': ['.md', '.rst', '.txt'],
            'other': []
        }

        files = {k: [] for k in extensions}

        # Common directories to skip
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', '.env', 'dist', 'build'}

        for root, dirs, filenames in os.walk(path):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]

            rel_root = Path(root).relative_to(path)

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                file_path = rel_root / filename
                ext = Path(filename).suffix.lower()

                categorized = False
                for category, exts in extensions.items():
                    if ext in exts:
                        files[category].append(str(file_path))
                        categorized = True
                        break

                if not categorized and ext:
                    files['other'].append(str(file_path))

        return files

    def _analyze_structure(self, path: Path, files: dict) -> dict:
        """Analyze the project structure."""
        structure = {
            'total_files': sum(len(f) for f in files.values()),
            'by_type': {k: len(v) for k, v in files.items()},
            'has_readme': (path / 'README.md').exists() or (path / 'README').exists(),
            'has_requirements': (path / 'requirements.txt').exists(),
            'has_package_json': (path / 'package.json').exists(),
            'has_pyproject': (path / 'pyproject.toml').exists(),
            'has_git': (path / '.git').exists(),
            'directories': [],
        }

        # Get top-level directories
        for item in path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name not in {'__pycache__', 'node_modules', 'venv', '.venv'}:
                structure['directories'].append(item.name)

        return structure

    def _read_key_files(self, path: Path, files: dict) -> dict:
        """Read contents of key files for analysis."""
        key_contents = {}

        # Priority files to read
        priority_files = [
            'README.md', 'README', 'README.rst',
            'setup.py', 'pyproject.toml', 'package.json',
            'requirements.txt', 'Cargo.toml', 'go.mod',
        ]

        for filename in priority_files:
            file_path = path / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    # Limit content size
                    if len(content) > 3000:
                        content = content[:3000] + "\n... (truncated)"
                    key_contents[filename] = content
                except Exception:
                    pass

        # Read a few Python files to understand the codebase
        python_files = files.get('python', [])
        if python_files:
            # Prioritize main entry points
            priority = ['main.py', '__main__.py', 'app.py', 'cli.py', 'setup.py']
            selected = []

            for p in priority:
                for f in python_files:
                    if f.endswith(p) or f == p:
                        selected.append(f)
                        break

            # Add first few Python files if not enough
            for f in python_files[:5]:
                if f not in selected:
                    selected.append(f)
                if len(selected) >= 3:
                    break

            for filename in selected[:3]:
                file_path = path / filename
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        if len(content) > 2000:
                            content = content[:2000] + "\n... (truncated)"
                        key_contents[filename] = content
                    except Exception:
                        pass

        return key_contents

    def _generate_codebase_summary(self, path: Path, structure: dict, contents: dict) -> str:
        """Use LLM to generate a codebase summary."""
        # Build context
        context_parts = [
            f"Project directory: {path.name}",
            f"Total files: {structure['total_files']}",
            f"File types: {', '.join(f'{k}={v}' for k, v in structure['by_type'].items() if v > 0)}",
            f"Top-level directories: {', '.join(structure['directories'])}",
        ]

        if structure['has_readme']:
            context_parts.append("Has README: Yes")
        if structure['has_requirements']:
            context_parts.append("Python project (requirements.txt)")
        if structure['has_package_json']:
            context_parts.append("Node.js project (package.json)")
        if structure['has_pyproject']:
            context_parts.append("Modern Python project (pyproject.toml)")
        if structure['has_git']:
            context_parts.append("Git repository: Yes")

        context = "\n".join(context_parts)

        # Build file contents section
        file_contents = ""
        for filename, content in contents.items():
            file_contents += f"\n\n--- {filename} ---\n{content}"

        prompt = f"""Analyze this codebase and provide a comprehensive summary.

Project Structure:
{context}

Key File Contents:
{file_contents}

Provide a summary that includes:
1. **Project Type**: What kind of project is this? (library, CLI tool, web app, etc.)
2. **Main Purpose**: What does this project do?
3. **Key Technologies**: Languages, frameworks, libraries used
4. **Architecture**: How is the code organized?
5. **Entry Points**: Main files/functions
6. **Dependencies**: Key external dependencies
7. **Potential Issues**: Any obvious problems or areas for improvement

Be concise but thorough. Focus on actionable insights."""

        try:
            response = self.orchestrator.delegate(
                self.orchestrator.brain,
                prompt,
                system_prompt="You are a code analysis expert. Analyze codebases and provide clear, actionable summaries. Do not repeat yourself.",
                max_tokens=2000,
                temperature=0.3
            )
            return response.content
        except Exception as e:
            return f"Error generating summary: {e}\n\nBasic structure:\n{context}"

    def _manage_context(self, args: str = ""):
        """Manage codebase context."""
        if not args:
            # Show context status
            status = self.orchestrator.get_context_status()
            click.secho("\nContext Status:", bold=True)
            click.echo("-" * 50)
            click.echo(f"Project: {status['project_path']}")
            click.echo(f"Explored: {click.style('Yes' if status['is_explored'] else 'No', fg='green' if status['is_explored'] else 'yellow')}")
            click.echo(f"Has Summary: {'Yes' if status['has_summary'] else 'No'}")
            if status['explored_at']:
                click.echo(f"Explored At: {status['explored_at']}")
            click.echo(f"Total Files: {status['total_files']}")
            click.echo(f"Context Aware: {click.style('Enabled' if self.orchestrator.context_aware else 'Disabled', fg='green' if self.orchestrator.context_aware else 'red')}")
            click.echo(f"Cache File: {status['cache_file']}")
            click.echo(f"Cache Exists: {'Yes' if status['cache_exists'] else 'No'}")

            if status['has_summary']:
                click.secho("\nProject Summary:", bold=True)
                click.echo(self.orchestrator.context.summary)

        elif args.lower() == "explore":
            click.echo("Exploring current project...")
            result = self.orchestrator.explore_project(force=False)
            if result['status'] == 'cached':
                click.secho("Using cached exploration.", fg="cyan")
            else:
                click.secho(f"Found {result['total_files']} files.", fg="green")

            if self.orchestrator.context.summary:
                click.secho("\nGenerated Summary:", bold=True)
                click.echo(self.orchestrator.context.summary)

        elif args.lower() == "refresh":
            click.echo("Force re-exploring project...")
            result = self.orchestrator.explore_project(force=True)
            click.secho(f"Found {result['total_files']} files.", fg="green")

            if self.orchestrator.context.summary:
                click.secho("\nGenerated Summary:", bold=True)
                click.echo(self.orchestrator.context.summary)

        elif args.lower() == "clear":
            self.orchestrator.context.clear_cache()
            click.secho("Context cache cleared.", fg="green")

        elif args.lower() == "toggle":
            self.orchestrator.context_aware = not self.orchestrator.context_aware
            status = "enabled" if self.orchestrator.context_aware else "disabled"
            click.secho(f"Context awareness {status}.", fg="green" if self.orchestrator.context_aware else "yellow")

        else:
            click.echo("Usage: /context [explore|refresh|clear|toggle]")
            click.echo("  (no args)  - Show context status")
            click.echo("  explore    - Explore project (uses cache if available)")
            click.echo("  refresh    - Force re-exploration")
            click.echo("  clear      - Clear cached context")
            click.echo("  toggle     - Toggle context-aware prompts")


# Global CLI instance for commands
pass_cli = click.make_pass_decorator(CLI, ensure=True)


@click.group(invoke_without_command=True)
@click.option("--brain", "-b", default=None, help="Orchestrator brain provider (cerebras, groq, gemini)")
@click.option("--auto-explore", "-a", is_flag=True, help="Automatically explore codebase on startup")
@click.option("--no-context", is_flag=True, help="Disable context-aware prompts")
@click.pass_context
def cli(ctx, brain, auto_explore, no_context):
    """LLM Agent Team CLI - Multi-provider orchestrator interface.

    Start interactive mode by running without arguments, or use subcommands
    for one-shot operations.
    """
    ctx.ensure_object(dict)

    # Store preferences
    ctx.obj['brain'] = brain
    ctx.obj['auto_explore'] = auto_explore
    ctx.obj['context_aware'] = not no_context

    # If no subcommand, start interactive mode
    if ctx.invoked_subcommand is None:
        cli_instance = CLI(brain=brain, auto_explore=auto_explore, context_aware=not no_context)
        cli_instance.interactive_mode()


@cli.command()
@click.argument("prompt")
@click.option("--provider", "-p", default=None, help="Specific provider to use")
@click.option("--model", "-m", default=None, help="Specific model to use")
@click.option("--temperature", "-t", default=0.7, type=float, help="Temperature (0-1)")
@click.option("--max-tokens", default=1000, type=int, help="Max tokens in response")
@click.option("--with-context", "-c", is_flag=True, help="Include codebase context in prompt")
@click.pass_context
def query(ctx, prompt, provider, model, temperature, max_tokens, with_context):
    """Send a one-shot query to the orchestrator."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)

    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)

    target_provider = provider or cli_instance.orchestrator.brain
    click.echo(f"Querying {target_provider}...\n")

    try:
        response = cli_instance.orchestrator.delegate(
            target_provider,
            prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            use_context=with_context if with_context else None
        )

        click.echo(response.content)
        click.secho(
            f"\n[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
            fg="cyan"
        )
    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.argument("task")
@click.option("--max-steps", default=5, type=int, help="Maximum number of steps")
@click.pass_context
def plan(ctx, task, max_steps):
    """Create a task plan."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    click.echo(f"Planning: {task}\n")
    cli_instance._plan_task(task)


@cli.command()
@click.argument("question")
@click.option("--context", "-c", default="", help="Additional context")
@click.option("--evidence", "-e", multiple=True, help="Evidence points (can specify multiple)")
@click.pass_context
def reason(ctx, question, context, evidence):
    """Reason about a question with evidence."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    click.echo(f"Reasoning: {question}\n")

    try:
        response = cli_instance.orchestrator.reason(
            question,
            context=context,
            evidence=list(evidence)
        )

        if isinstance(response, dict):
            click.secho("Analysis:", bold=True)
            click.echo(response.get('analysis', ''))
            click.secho("\nConclusion: ", bold=True, nl=False)
            click.echo(response.get('conclusion', ''))
            click.echo(f"Confidence: {response.get('confidence', 'N/A')}")
        else:
            click.echo(response)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance._show_status()


@cli.command()
@click.pass_context
def providers(ctx):
    """List available providers."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance._list_providers()


@cli.command()
@click.argument("provider", required=False)
@click.pass_context
def models(ctx, provider):
    """List available models."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance._list_models(provider or "")


@cli.command()
@click.pass_context
def usage(ctx):
    """Show usage statistics."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance._show_usage()


@cli.command()
@click.pass_context
def interactive(ctx):
    """Start interactive chat mode."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance.interactive_mode()


@cli.command()
@click.pass_context
def context(ctx):
    """Show and manage codebase context."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance._manage_context("")


@cli.command()
@click.argument("path", default=".", required=False)
@click.option("--save", "-s", is_flag=True, help="Save summary to file")
@click.pass_context
def explore(ctx, path, save):
    """Explore and learn about a codebase."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)

    path_obj = Path(path).resolve()
    if not path_obj.exists():
        click.secho(f"Path does not exist: {path_obj}", fg="red")
        sys.exit(1)

    if not path_obj.is_dir():
        click.secho(f"Not a directory: {path_obj}", fg="red")
        sys.exit(1)

    click.secho(f"\nExploring: {path_obj}", bold=True)
    click.echo("-" * 50)

    # Collect codebase information
    with click.progressbar(length=4, label="Scanning codebase") as bar:
        source_files = cli_instance._find_source_files(path_obj)
        bar.update(1)

        structure = cli_instance._analyze_structure(path_obj, source_files)
        bar.update(1)

        key_contents = cli_instance._read_key_files(path_obj, source_files)
        bar.update(1)

        summary = cli_instance._generate_codebase_summary(path_obj, structure, key_contents)
        bar.update(1)

    click.echo()
    click.secho("Codebase Summary:", bold=True)
    click.echo("-" * 50)
    click.echo(summary)

    if save:
        summary_file = path_obj / "CODEBASE_SUMMARY.md"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"# Codebase Summary\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            f.write(summary)
        click.secho(f"\nSaved to: {summary_file}", fg="green")


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
