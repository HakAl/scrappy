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
    from .agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint
except ImportError:
    # Allow running as script
    from orchestrator import AgentOrchestrator
    from agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint


class CLI:
    """Interactive CLI for the LLM Agent Team."""

    def __init__(self, brain: Optional[str] = None, auto_explore: bool = False, context_aware: bool = True):
        """Initialize CLI with orchestrator."""
        click.secho("Initializing LLM Agent Team...", fg="cyan")
        self.orchestrator = AgentOrchestrator(
            orchestrator_provider=brain,
            auto_explore=auto_explore,
            context_aware=context_aware
        )
        self.session_start = datetime.now()
        click.echo(f"Brain: {click.style(self.orchestrator.brain, fg='green', bold=True)}")
        providers_list = ', '.join(self.orchestrator.providers.list_available())
        click.echo(f"Available providers: {click.style(providers_list, fg='cyan')}")

        # Show context status
        if self.orchestrator.context.is_explored():
            click.secho(f"Context: {self.orchestrator.context.project_path.name} (cached)", fg="cyan")
        elif context_aware:
            click.secho("Context: Not explored (use /context to explore)", fg="yellow")

        click.echo()

    def interactive_mode(self):
        """Run interactive chat mode."""
        click.secho("=" * 60, fg="cyan")
        click.secho("LLM Agent Team - Interactive Mode", fg="cyan", bold=True)
        click.secho("=" * 60, fg="cyan")
        click.echo("Commands:")
        click.echo(f"  {click.style('/help', fg='yellow')}          - Show all commands")
        click.echo(f"  {click.style('/plan', fg='yellow')} <task>   - Create a task plan")
        click.echo(f"  {click.style('/reason', fg='yellow')} <q>    - Reason about a question")
        click.echo(f"  {click.style('/agent', fg='yellow')} <task>  - Run code agent (with human approval)")
        click.echo(f"  {click.style('/context', fg='yellow')}       - Manage codebase context")
        click.echo(f"  {click.style('/status', fg='yellow')}        - Show system status")
        click.echo(f"  {click.style('/quit', fg='yellow')}          - Exit the CLI")
        click.echo(f"  {click.style('(any text)', fg='bright_white')}     - Chat with current brain")
        click.secho("=" * 60, fg="cyan")
        click.echo()

        conversation_history = []

        while True:
            try:
                user_input = click.prompt(click.style("You", fg="green", bold=True), default="", show_default=False).strip()

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

                click.secho("Assistant: ", fg="blue", bold=True, nl=False)

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
            click.secho("\nGoodbye!", fg="cyan", bold=True)
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

        elif cmd == "/agent":
            if not args:
                click.echo("Usage: /agent <task description>")
            else:
                self._run_agent(args)

        elif cmd == "/cache":
            self._manage_cache(args)

        else:
            click.secho(f"Unknown command: {cmd}", fg="yellow")
            click.echo("Type /help for available commands.")

        click.echo()
        return True

    def _show_help(self):
        """Display help information."""
        click.secho("\nAvailable Commands:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")
        click.secho("Chat & Conversation:", bold=True)
        click.echo(f"  {click.style('(text)', fg='yellow')}           - Send message to current brain")
        click.echo(f"  {click.style('/clear', fg='yellow')}           - Clear conversation history")
        click.echo()
        click.secho("Task Operations:", bold=True)
        click.echo(f"  {click.style('/plan', fg='yellow')} <task>     - Break down task into steps")
        click.echo(f"  {click.style('/reason', fg='yellow')} <q>      - Analyze question with reasoning")
        click.echo(f"  {click.style('/agent', fg='yellow')} <task>    - Run code agent to complete task")
        click.echo(f"  {click.style('/synthesize', fg='yellow')}      - Combine multiple provider responses")
        click.echo(f"  {click.style('/delegate', fg='yellow')} <p>    - Send prompt to specific provider")
        click.echo(f"  {click.style('/explore', fg='yellow')} [path]  - Explore and learn about a codebase")
        click.echo()
        click.secho("Provider Management:", bold=True)
        click.echo(f"  {click.style('/providers', fg='yellow')}       - List all available providers")
        click.echo(f"  {click.style('/brain', fg='yellow')} <name>    - Switch orchestrator brain")
        click.echo(f"  {click.style('/models', fg='yellow')} [prov]   - List models (optionally for provider)")
        click.echo(f"  {click.style('/status', fg='yellow')}          - Show current system status")
        click.echo(f"  {click.style('/usage', fg='yellow')}           - Show usage statistics")
        click.echo()
        click.secho("Context Management:", bold=True)
        click.echo(f"  {click.style('/context', fg='yellow')}         - Show context status")
        click.echo(f"  {click.style('/context explore', fg='yellow')} - Explore current project")
        click.echo(f"  {click.style('/context clear', fg='yellow')}   - Clear cached context")
        click.echo(f"  {click.style('/context toggle', fg='yellow')}  - Toggle context awareness")
        click.echo()
        click.secho("Cache Management:", bold=True)
        click.echo(f"  {click.style('/cache', fg='yellow')}           - Show cache statistics")
        click.echo("  /cache clear     - Clear response cache")
        click.echo("  /cache toggle    - Toggle caching on/off")
        click.echo()
        click.secho("System:", bold=True)
        click.echo("  /help            - Show this help message")
        click.echo("  /quit or /exit   - Exit the CLI")

    def _show_status(self):
        """Display current system status."""
        status = self.orchestrator.status()

        click.secho("\nSystem Status:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")
        brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
        click.echo(f"Current Brain: {click.style(brain, fg='green', bold=True)}")
        click.echo(f"Total Providers: {len(status.get('available_providers', []))}")
        click.echo(f"Available: {click.style(', '.join(status['available_providers']), fg='cyan')}")
        click.echo(f"Tasks Completed: {status.get('tasks_executed', 0)}")
        click.echo(f"Session Duration: {datetime.now() - self.session_start}")

    def _list_providers(self):
        """List all providers with their details."""
        click.secho("\nAvailable Providers:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")

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

        click.secho("\nUsage Statistics:", fg="cyan", bold=True)
        click.secho("-" * 50, fg="cyan")
        click.echo(f"Total Tasks: {click.style(str(report.get('total_tasks', 0)), fg='green', bold=True)}")
        if 'cached_hits' in report:
            click.echo(f"Cache Hits: {click.style(str(report['cached_hits']), fg='green')}")
            click.echo(f"API Calls: {report['api_calls']}")
        click.echo(f"Session Duration: {report.get('session_duration', 'N/A')}")

        if report.get('by_provider'):
            click.secho("\nBy Provider:", bold=True)
            for provider, stats in report['by_provider'].items():
                click.secho(f"  {provider}:", fg="cyan", bold=True)
                click.echo(f"    Requests: {stats['count']}")
                if stats.get('cached_hits', 0) > 0:
                    click.echo(f"    Cached Hits: {click.style(str(stats['cached_hits']), fg='green')}")
                click.echo(f"    Total Tokens: {stats['total_tokens']:,}")
                click.echo(f"    Avg Tokens/Request: {stats['avg_tokens']:.1f}")
                click.echo(f"    Total Latency: {stats['total_latency_ms']:.0f}ms")

        if 'cache_stats' in report:
            cache_stats = report['cache_stats']
            click.secho("\nCache:", bold=True)
            click.echo(f"  Hit Rate: {cache_stats['hit_rate']}")
            click.echo(f"  Entries: {cache_stats['total_entries']}")

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
                results.append(response)  # Append LLMResponse object, not .content
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
            click.secho("\nContext Status:", fg="cyan", bold=True)
            click.secho("-" * 50, fg="cyan")
            click.echo(f"Project: {click.style(str(status['project_path']), fg='bright_white')}")
            click.echo(f"Explored: {click.style('Yes' if status['is_explored'] else 'No', fg='green' if status['is_explored'] else 'yellow')}")
            click.echo(f"Has Summary: {'Yes' if status['has_summary'] else 'No'}")
            if status['explored_at']:
                click.echo(f"Explored At: {status['explored_at']}")
            click.echo(f"Total Files: {status['total_files']}")
            if status.get('has_git_history'):
                click.echo(f"Git Branch: {click.style(status.get('git_branch', 'unknown'), fg='cyan')}")
                click.echo(f"Git Commits: {status.get('git_commits', 0)}")
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

    def _manage_cache(self, args: str = ""):
        """Manage response cache."""
        if not args:
            # Show cache status
            stats = self.orchestrator.get_cache_stats()
            click.secho("\nCache Statistics:", bold=True)
            click.echo("-" * 50)
            click.echo(f"Total Entries: {stats['total_entries']}")
            click.echo(f"Cache Hits: {stats['hits']}")
            click.echo(f"Cache Misses: {stats['misses']}")
            click.echo(f"Cache Saves: {stats['saves']}")
            click.secho(f"Hit Rate: {stats['hit_rate']}", fg="green" if float(stats['hit_rate'].rstrip('%')) > 50 else "yellow")
            click.echo(f"Cache File: {stats['cache_file']}")
            click.echo(f"Caching: {click.style('Enabled' if self.orchestrator.caching_enabled else 'Disabled', fg='green' if self.orchestrator.caching_enabled else 'red')}")

        elif args.lower() == "clear":
            self.orchestrator.clear_cache()
            click.secho("Response cache cleared.", fg="green")

        elif args.lower() == "toggle":
            new_state = self.orchestrator.toggle_cache()
            status = "enabled" if new_state else "disabled"
            click.secho(f"Response caching {status}.", fg="green" if new_state else "yellow")

        else:
            click.echo("Usage: /cache [clear|toggle]")
            click.echo("  (no args)  - Show cache statistics")
            click.echo("  clear      - Clear all cached responses")
            click.echo("  toggle     - Toggle caching on/off")

    def _run_agent(self, task: str):
        """Run the code agent on a task with human-in-the-loop approval."""
        click.secho(f"\nCode Agent - Task: {task}", bold=True)
        click.echo("-" * 60)

        # Safety options
        dry_run = click.confirm("Run in dry-run mode? (no actual changes)", default=False)
        create_checkpoint = click.confirm("Create git checkpoint before running?", default=True)

        checkpoint_hash = None
        if create_checkpoint:
            click.echo("Creating git checkpoint...")
            checkpoint_hash = create_git_checkpoint(str(self.orchestrator.context.project_path))
            if checkpoint_hash:
                click.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
            else:
                click.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

        # Create agent
        agent = CodeAgent(self.orchestrator)
        agent.dry_run = dry_run

        # Show agent configuration
        click.echo(f"\nAgent Configuration:")
        click.echo(f"  Planner (smart tasks): {agent.planner}")
        click.echo(f"  Executor (fast tasks): {agent.executor}")
        click.echo(f"  Project root: {agent.project_root}")
        if dry_run:
            click.secho("  Mode: DRY RUN (no actual changes)", fg="yellow")
        click.echo()

        if not click.confirm("Start agent?", default=True):
            click.echo("Agent cancelled.")
            return

        # Run agent
        try:
            result = agent.run(task)

            click.echo("\n" + "=" * 60)
            if result['success']:
                click.secho("Task Completed Successfully!", fg="green", bold=True)
            else:
                click.secho("Task Did Not Complete", fg="yellow", bold=True)

            click.echo(f"Result: {result['result']}")
            click.echo(f"Iterations: {result['iterations']}")

            # Show audit log summary
            if result['audit_log']:
                click.secho("\nAudit Log:", bold=True)
                for entry in result['audit_log']:
                    approved = click.style("Approved", fg="green") if entry['approved'] else click.style("Denied", fg="red")
                    click.echo(f"  [{entry['timestamp'][:19]}] {entry['action']} - {approved}")

            # Offer to save audit log
            if click.confirm("\nSave audit log to file?", default=False):
                log_path = agent.save_audit_log()
                click.secho(f"Saved to: {log_path}", fg="green")

            # Offer rollback if checkpoint was created
            if checkpoint_hash and not dry_run:
                if click.confirm("\nRollback to checkpoint?", default=False):
                    if rollback_to_checkpoint(checkpoint_hash, str(agent.project_root)):
                        click.secho(f"Rolled back to {checkpoint_hash[:8]}", fg="green")
                    else:
                        click.secho("Rollback failed", fg="red")

        except KeyboardInterrupt:
            click.echo("\n\nAgent interrupted by user.")
        except Exception as e:
            click.secho(f"\nAgent error: {e}", fg="red")


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
@click.option("--clear", is_flag=True, help="Clear cached context")
@click.option("--refresh", is_flag=True, help="Force re-exploration")
@click.pass_context
def context(ctx, clear, refresh):
    """Show and manage codebase context."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)

    if clear:
        cli_instance.orchestrator.context.clear_cache()
        click.secho("Context cache cleared.", fg="green")
    elif refresh:
        cli_instance._manage_context("refresh")
    else:
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


@cli.command()
@click.argument("task")
@click.option("--dry-run", "-d", is_flag=True, help="Run in dry-run mode (no actual changes)")
@click.option("--no-checkpoint", is_flag=True, help="Skip git checkpoint creation")
@click.option("--auto-confirm", is_flag=True, help="Auto-confirm all actions (use with caution)")
@click.option("--max-iterations", "-m", default=10, type=int, help="Maximum agent iterations")
@click.pass_context
def agent(ctx, task, dry_run, no_checkpoint, auto_confirm, max_iterations):
    """Run code agent to complete a task with human approval.

    The agent uses Gemini for planning/code generation (smart tasks)
    and Cerebras for quick operations. All file modifications require
    your explicit approval unless --auto-confirm is used.

    Example:
        python llm_team.py agent "Add a health check endpoint to the Flask app"
    """
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)

    click.secho(f"\nCode Agent - Task: {task}", bold=True)
    click.echo("-" * 60)

    # Create checkpoint if requested
    checkpoint_hash = None
    if not no_checkpoint:
        click.echo("Creating git checkpoint...")
        checkpoint_hash = create_git_checkpoint(str(cli_instance.orchestrator.context.project_path))
        if checkpoint_hash:
            click.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
        else:
            click.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

    # Create agent
    code_agent = CodeAgent(cli_instance.orchestrator)
    code_agent.dry_run = dry_run

    # Show agent configuration
    click.echo(f"\nAgent Configuration:")
    click.echo(f"  Planner (smart tasks): {code_agent.planner}")
    click.echo(f"  Executor (fast tasks): {code_agent.executor}")
    click.echo(f"  Project root: {code_agent.project_root}")
    click.echo(f"  Max iterations: {max_iterations}")
    if dry_run:
        click.secho("  Mode: DRY RUN (no actual changes)", fg="yellow")
    if auto_confirm:
        click.secho("  WARNING: Auto-confirm enabled - no approval prompts", fg="red", bold=True)
    click.echo()

    # Run agent
    try:
        result = code_agent.run(task, max_iterations=max_iterations, auto_confirm=auto_confirm)

        click.echo("\n" + "=" * 60)
        if result['success']:
            click.secho("Task Completed Successfully!", fg="green", bold=True)
        else:
            click.secho("Task Did Not Complete", fg="yellow", bold=True)

        click.echo(f"Result: {result['result']}")
        click.echo(f"Iterations: {result['iterations']}")

        # Show audit log summary
        if result['audit_log']:
            click.secho("\nAudit Log:", bold=True)
            for entry in result['audit_log']:
                approved = click.style("Approved", fg="green") if entry['approved'] else click.style("Denied", fg="red")
                click.echo(f"  [{entry['timestamp'][:19]}] {entry['action']} - {approved}")

        # Save audit log
        log_path = code_agent.save_audit_log()
        click.secho(f"\nAudit log saved to: {log_path}", fg="cyan")

        # Show rollback option
        if checkpoint_hash and not dry_run:
            click.echo(f"\nTo rollback changes: git reset --hard {checkpoint_hash}")

    except KeyboardInterrupt:
        click.echo("\n\nAgent interrupted by user.")
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nAgent error: {e}", fg="red")
        sys.exit(1)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
