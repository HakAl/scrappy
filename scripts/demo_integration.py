#!/usr/bin/env python3
"""
Demo: Integrated semantic search with Rich progress display.

Shows how CodebaseContext + BackgroundInitializerProtocol + Rich work together.

This demonstrates P0 requirements:
- Loads in background on app start with rich progress
- Progress displayed clearly to user
- Progress display goes away shortly after complete
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from src.context.codebase_context import CodebaseContext
from src.context.semantic.initializer import SemanticSearchInitializer

console = Console()


def show_initialization_progress(context: CodebaseContext):
    """
    Display initialization progress with Rich.

    Polls background thread and updates UI in main thread (thread-safe).
    Progress bar disappears when done (transient=True).
    """
    status = context.get_semantic_initialization_status()
    if not status:
        console.print("[yellow]No semantic search initialization configured[/yellow]")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        transient=True,  # Disappears when done
    ) as progress:
        task = progress.add_task("Initializing semantic search...", total=None)

        while not context.is_semantic_search_ready():
            status = context.get_semantic_initialization_status()
            if status:
                progress.update(task, description=f"[cyan]{status}[/cyan]")
            time.sleep(0.1)  # Poll every 100ms

        # Show completion briefly
        progress.update(task, description="[green]Semantic search ready![/green]")
        time.sleep(0.5)  # Show for 500ms then disappear


def main():
    """Demonstrate integrated semantic search with Rich progress."""
    console.print("\n[bold]Semantic Search Integration Demo[/bold]\n")

    # Create context with semantic search initializer
    console.print("[dim]Creating CodebaseContext...[/dim]")
    initializer = SemanticSearchInitializer(Path.cwd())
    context = CodebaseContext(
        project_path=".",
        semantic_initializer=initializer
    )

    # Start background initialization (non-blocking)
    console.print("[dim]Starting background initialization...[/dim]")
    context.start_background_initialization()

    # Show progress in main thread
    show_initialization_progress(context)

    # Progress bar is now gone (transient=True)
    console.print("\n[green]Background initialization complete![/green]")
    console.print(f"[dim]Semantic search ready: {context.is_semantic_search_ready()}[/dim]\n")

    # Now explore the codebase
    console.print("[bold]Exploring codebase...[/bold]")
    result = context.explore()
    console.print(f"[green]Exploration complete: {result['status']}[/green]")

    # Verify semantic search was used
    if context._ensure_semantic_search():
        console.print("[green]Semantic search is available and indexed![/green]")
    else:
        console.print("[yellow]Semantic search not available[/yellow]")


if __name__ == "__main__":
    main()
