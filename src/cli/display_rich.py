"""
Rich-enhanced display functions for CLI.

Provides Rich-based versions of help, status, usage, and other displays
using Tables, Panels, Progress bars, and Tree structures.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.tree import Tree
from rich.text import Text

from .rich_output import RichIO


# =============================================================================
# Help Display
# =============================================================================

def show_help_table(io: RichIO, category: Optional[str] = None) -> None:
    """Display help information as a Rich Table.

    Args:
        io: RichIO instance for output
        category: Optional category filter (e.g., 'provider', 'task')
    """
    # Define command categories
    categories = {
        'Chat & Conversation': [
            ('/help', 'Show all commands'),
            ('/ml', 'Toggle multiline input mode'),
            ('/clear', 'Clear conversation history'),
        ],
        'Task Operations': [
            ('/plan <task>', 'Break down task into steps'),
            ('/tasks', 'View current plan progress'),
            ('/reason <q>', 'Analyze with reasoning'),
            ('/agent <task>', 'Run code agent'),
            ('/smart <query>', 'Research-first query'),
            ('/synthesize', 'Combine provider responses'),
            ('/delegate <p>', 'Send to specific provider'),
            ('/explore [path]', 'Explore codebase'),
        ],
        'Provider Management': [
            ('/providers', 'List all providers'),
            ('/brain <name>', 'Switch brain provider'),
            ('/models [prov]', 'List available models'),
            ('/status', 'Show system status'),
            ('/usage', 'Show usage statistics'),
        ],
        'Context Management': [
            ('/context', 'Show context status'),
            ('/context explore', 'Explore current project'),
            ('/context clear', 'Clear cached context'),
            ('/context toggle', 'Toggle context awareness'),
        ],
        'Cache Management': [
            ('/cache', 'Show cache statistics'),
            ('/cache clear', 'Clear response cache'),
            ('/cache toggle', 'Toggle caching'),
        ],
        'Session Management': [
            ('/session', 'Show session info'),
            ('/session save', 'Save current session'),
            ('/session load', 'Load previous session'),
            ('/session clear', 'Delete saved session'),
        ],
        'System': [
            ('/quit', 'Exit the CLI'),
            ('/exit', 'Exit the CLI'),
        ],
    }

    # Filter by category if specified
    if category:
        category_lower = category.lower()
        filtered = {}
        for cat_name, commands in categories.items():
            if category_lower in cat_name.lower():
                filtered[cat_name] = commands
        if filtered:
            categories = filtered

    # Create table
    table = Table(title="Available Commands", show_header=True, header_style="bold cyan")
    table.add_column("Command", style="yellow", width=20)
    table.add_column("Description", style="white")

    for cat_name, commands in categories.items():
        # Add category header as a section
        table.add_row(f"[bold]{cat_name}[/bold]", "", style="cyan")
        for cmd, desc in commands:
            table.add_row(f"  {cmd}", desc)
        table.add_row("", "")  # Spacing between categories

    io.console.print(table)


# =============================================================================
# Status Display
# =============================================================================

def show_status_rich(
    io: RichIO,
    orchestrator,
    session_start: datetime
) -> None:
    """Display system status using Rich components.

    Args:
        io: RichIO instance for output
        orchestrator: The orchestrator instance
        session_start: Session start time
    """
    status = orchestrator.status()

    # Build status content
    content = Text()

    # Current brain
    brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
    content.append("Current Brain: ", style="bold")
    content.append(f"{brain}\n", style="bold green")

    # Provider count
    providers = status.get('available_providers', [])
    content.append("Total Providers: ", style="bold")
    content.append(f"{len(providers)}\n", style="white")

    # Available providers
    content.append("Available: ", style="bold")
    content.append(f"{', '.join(providers)}\n", style="cyan")

    # Tasks completed
    tasks = status.get('tasks_executed', 0)
    content.append("Tasks Completed: ", style="bold")
    content.append(f"{tasks}\n", style="white")

    # Session duration
    duration = datetime.now() - session_start
    content.append("Session Duration: ", style="bold")
    content.append(str(duration).split('.')[0], style="white")  # Remove microseconds

    # Create panel
    panel = Panel(
        content,
        title="[bold cyan]System Status[/bold cyan]",
        border_style="cyan"
    )
    io.console.print(panel)


# =============================================================================
# Rate Limits Display
# =============================================================================

def show_rate_limits_rich(io: RichIO, rate_data: Dict[str, Any]) -> None:
    """Display rate limits with progress bars.

    Args:
        io: RichIO instance for output
        rate_data: Rate limit data with provider information
    """
    providers = rate_data.get('providers', {})

    if not providers:
        io.secho("No rate limit data available.", fg="yellow")
        return

    # Create table for rate limits
    table = Table(title="Rate Limit Usage", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Requests", justify="right")
    table.add_column("Usage", width=20)
    table.add_column("Tokens", justify="right")

    for provider_name, data in providers.items():
        requests_today = data.get('requests_today', 0)
        daily_limit = data.get('daily_limit', 100)
        tokens_today = data.get('tokens_today', 0)
        token_limit = data.get('daily_token_limit', 10000)

        # Calculate percentages
        request_pct = (requests_today / daily_limit * 100) if daily_limit > 0 else 0
        token_pct = (tokens_today / token_limit * 100) if token_limit > 0 else 0

        # Create progress bar representation
        bar_width = 15
        filled = int(request_pct / 100 * bar_width)
        empty = bar_width - filled

        # Color based on usage
        if request_pct >= 90:
            bar_color = "red"
        elif request_pct >= 70:
            bar_color = "yellow"
        else:
            bar_color = "green"

        progress_bar = f"[{bar_color}]{'|' * filled}[/{bar_color}][dim]{'.' * empty}[/dim]"

        # Format request info
        request_info = f"{requests_today}/{daily_limit} ({request_pct:.0f}%)"

        # Format token info
        token_info = f"{tokens_today:,}/{token_limit:,}"

        table.add_row(
            provider_name.upper(),
            request_info,
            progress_bar,
            token_info
        )

    io.console.print(table)


# =============================================================================
# Usage Statistics Display
# =============================================================================

def show_usage_rich(io: RichIO, report: Dict[str, Any]) -> None:
    """Display usage statistics with Rich formatting.

    Args:
        io: RichIO instance for output
        report: Usage report dictionary
    """
    # Summary panel
    summary = Text()
    summary.append("Total Tasks: ", style="bold")
    summary.append(f"{report.get('total_tasks', 0)}\n", style="green bold")

    if 'cached_hits' in report:
        summary.append("Cache Hits: ", style="bold")
        summary.append(f"{report['cached_hits']}\n", style="green")
        summary.append("API Calls: ", style="bold")
        summary.append(f"{report.get('api_calls', 0)}\n", style="white")

    summary.append("Session Duration: ", style="bold")
    summary.append(f"{report.get('session_duration', 'N/A')}", style="white")

    panel = Panel(
        summary,
        title="[bold cyan]Usage Summary[/bold cyan]",
        border_style="cyan"
    )
    io.console.print(panel)

    # Provider breakdown table
    by_provider = report.get('by_provider', {})
    if by_provider:
        table = Table(title="By Provider", show_header=True, header_style="bold cyan")
        table.add_column("Provider", style="bold")
        table.add_column("Requests", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Avg Tokens", justify="right")
        table.add_column("Latency", justify="right")

        for provider, stats in by_provider.items():
            table.add_row(
                provider,
                str(stats.get('count', 0)),
                f"{stats.get('total_tokens', 0):,}",
                f"{stats.get('avg_tokens', 0):.1f}",
                f"{stats.get('total_latency_ms', 0):.0f}ms"
            )

        io.console.print(table)

    # Cache statistics
    cache_stats = report.get('cache_stats', {})
    if cache_stats:
        cache_text = Text()
        cache_text.append("Exact Hit Rate: ", style="bold")
        cache_text.append(f"{cache_stats.get('exact_hit_rate', 'N/A')}\n", style="white")
        cache_text.append("Intent Hit Rate: ", style="bold")
        cache_text.append(f"{cache_stats.get('intent_hit_rate', 'N/A')}\n", style="white")

        total_entries = (
            cache_stats.get('exact_cache_entries', 0) +
            cache_stats.get('intent_cache_entries', 0)
        )
        cache_text.append("Total Entries: ", style="bold")
        cache_text.append(str(total_entries), style="white")

        cache_panel = Panel(
            cache_text,
            title="[bold]Cache Statistics[/bold]",
            border_style="blue"
        )
        io.console.print(cache_panel)


# =============================================================================
# Plan/Task Tree Display
# =============================================================================

def show_plan_tree(io: RichIO, plan: Dict[str, Any]) -> None:
    """Display plan and tasks as a Rich Tree structure.

    Args:
        io: RichIO instance for output
        plan: Plan dictionary with goal and tasks
    """
    goal = plan.get('goal', '')
    tasks = plan.get('tasks', [])

    if not goal and not tasks:
        io.secho("No active plan.", fg="yellow")
        return

    # Create tree
    tree_title = f"[bold cyan]{goal or 'Plan'}[/bold cyan]"
    tree = Tree(tree_title)

    # Add tasks as branches
    for task in tasks:
        task_id = task.get('id', '?')
        description = task.get('description', 'Unknown task')
        status = task.get('status', 'pending')

        # Format based on status
        if status == 'completed':
            icon = "[green][x][/green]"
            style = "dim"
        elif status == 'in_progress':
            icon = "[yellow][>][/yellow]"
            style = "bold yellow"
        else:  # pending
            icon = "[dim][ ][/dim]"
            style = "dim"

        task_text = f"{icon} [{style}]{description}[/{style}]"
        tree.add(task_text)

    io.console.print(tree)
