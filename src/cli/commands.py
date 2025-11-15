#!/usr/bin/env python3
"""
Click command handlers for the LLM Agent Team CLI.
Provides the main entry point and subcommands.
"""

import click
import sys
import os
from datetime import datetime
from pathlib import Path

from .core import CLI

try:
    from ..agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint
except ImportError:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from agent import CodeAgent, create_git_checkpoint, rollback_to_checkpoint


@click.group(invoke_without_command=True)
@click.option("--brain", "-b", default=None, help="Orchestrator brain provider (cerebras, groq, gemini)")
@click.option("--auto-explore", "-a", is_flag=True, help="Automatically explore codebase on startup")
@click.option("--no-context", is_flag=True, help="Disable context-aware prompts")
@click.option("--resume", "-r", is_flag=True, help="Resume from last saved session")
@click.option("--no-save", is_flag=True, help="Disable auto-save on exit")
@click.pass_context
def cli(ctx, brain, auto_explore, no_context, resume, no_save):
    """LLM Agent Team CLI - Multi-provider orchestrator interface.

    Start interactive mode by running without arguments, or use subcommands
    for one-shot operations.

    Sessions are auto-saved on /quit by default. Use --resume to continue.
    """
    ctx.ensure_object(dict)

    # Store preferences
    ctx.obj['brain'] = brain
    ctx.obj['auto_explore'] = auto_explore
    ctx.obj['context_aware'] = not no_context
    ctx.obj['resume'] = resume
    ctx.obj['auto_save'] = not no_save

    # If no subcommand, start interactive mode
    if ctx.invoked_subcommand is None:
        cli_instance = CLI(brain=brain, auto_explore=auto_explore, context_aware=not no_context)
        cli_instance.auto_save = not no_save

        # Resume previous session if requested
        if resume:
            result = cli_instance.orchestrator.load_session()
            if result['status'] == 'loaded':
                click.secho(f"\nResumed session from {result['saved_at']}", fg="green", bold=True)
                click.echo(f"  Files restored: {result['files_restored']}")
                click.echo(f"  Searches restored: {result['searches_restored']}")
                click.echo(f"  Git ops restored: {result['git_ops_restored']}")
                click.echo(f"  Discoveries restored: {result['discoveries_restored']}")
                click.echo(f"  Task history: {result['tasks_restored']} entries")

                conversation = result.get('conversation_history', [])
                if conversation:
                    cli_instance.conversation_history = conversation
                    click.echo(f"  Conversation: {len(conversation)} messages restored")

                    click.secho("\nLast conversation:", fg="cyan")
                    for msg in conversation[-4:]:
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')[:100]
                        if len(msg.get('content', '')) > 100:
                            content += "..."
                        if role == 'user':
                            click.echo(f"  You: {content}")
                        else:
                            click.echo(f"  Assistant: {content}")
            elif result['status'] == 'no_session':
                click.secho("No previous session found. Starting fresh.", fg="yellow")
            else:
                click.secho(f"Error loading session: {result.get('message', 'unknown')}", fg="red")

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
    cli_instance.tasks.plan_task(task)


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
@click.argument("query")
@click.pass_context
def smart(ctx, query):
    """Perform a research-first query using tools to gather context."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance.smart.smart_query(query)


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance.display.show_status()


@cli.command()
@click.pass_context
def providers(ctx):
    """List available providers."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance.display.list_providers()


@cli.command()
@click.argument("provider", required=False)
@click.pass_context
def models(ctx, provider):
    """List available models."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance.display.list_models(provider or "")


@cli.command()
@click.pass_context
def usage(ctx):
    """Show usage statistics."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)
    cli_instance.display.show_usage()


@cli.command()
@click.option("--resume", "-r", is_flag=True, help="Resume from last session")
@click.pass_context
def interactive(ctx, resume):
    """Start interactive chat mode."""
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)

    if resume:
        result = cli_instance.orchestrator.load_session()
        if result['status'] == 'loaded':
            click.secho(f"\nResumed session from {result['saved_at']}", fg="green", bold=True)
            click.echo(f"  Files restored: {result['files_restored']}")
            click.echo(f"  Searches restored: {result['searches_restored']}")
            click.echo(f"  Git ops restored: {result['git_ops_restored']}")
            click.echo(f"  Discoveries restored: {result['discoveries_restored']}")
            click.echo(f"  Task history: {result['tasks_restored']} entries")

            conversation = result.get('conversation_history', [])
            if conversation:
                cli_instance.conversation_history = conversation
                click.echo(f"  Conversation: {len(conversation)} messages restored")

                click.secho("\nLast conversation:", fg="cyan")
                for msg in conversation[-4:]:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')[:100]
                    if len(msg.get('content', '')) > 100:
                        content += "..."
                    if role == 'user':
                        click.echo(f"  You: {content}")
                    else:
                        click.echo(f"  Assistant: {content}")
        elif result['status'] == 'no_session':
            click.secho("No previous session found. Starting fresh.", fg="yellow")
        else:
            click.secho(f"Error loading session: {result.get('message', 'unknown')}", fg="red")

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
        cli_instance.session_mgr.manage_context("refresh")
    else:
        cli_instance.session_mgr.manage_context("")


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

    original_cwd = os.getcwd()
    try:
        os.chdir(path_obj)
        click.echo("Scanning codebase...")
        result = cli_instance.orchestrator.explore_project(force=True)
        summary = cli_instance.orchestrator.context.summary or "No summary generated"
    finally:
        os.chdir(original_cwd)

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
        llm-team agent "Add a health check endpoint to the Flask app"
    """
    auto_explore = ctx.obj.get('auto_explore', False)
    context_aware = ctx.obj.get('context_aware', True)
    cli_instance = CLI(brain=ctx.obj.get('brain'), auto_explore=auto_explore, context_aware=context_aware)

    click.secho(f"\nCode Agent - Task: {task}", bold=True)
    click.echo("-" * 60)

    checkpoint_hash = None
    if not no_checkpoint:
        click.echo("Creating git checkpoint...")
        checkpoint_hash = create_git_checkpoint(str(cli_instance.orchestrator.context.project_path))
        if checkpoint_hash:
            click.secho(f"Checkpoint created: {checkpoint_hash[:8]}", fg="green")
        else:
            click.secho("Could not create checkpoint (not a git repo?)", fg="yellow")

    code_agent = CodeAgent(cli_instance.orchestrator)
    code_agent.dry_run = dry_run

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

    try:
        result = code_agent.run(task, max_iterations=max_iterations, auto_confirm=auto_confirm)

        click.echo("\n" + "=" * 60)
        if result['success']:
            click.secho("Task Completed Successfully!", fg="green", bold=True)
        else:
            click.secho("Task Did Not Complete", fg="yellow", bold=True)

        click.echo(f"Result: {result['result']}")
        click.echo(f"Iterations: {result['iterations']}")

        if result['audit_log']:
            click.secho("\nAudit Log:", bold=True)
            for entry in result['audit_log']:
                approved = click.style("Approved", fg="green") if entry['approved'] else click.style("Denied", fg="red")
                click.echo(f"  [{entry['timestamp'][:19]}] {entry['action']} - {approved}")

        log_path = code_agent.save_audit_log()
        click.secho(f"\nAudit log saved to: {log_path}", fg="cyan")

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
