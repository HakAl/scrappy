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

from .unified_io import UnifiedIO


# =============================================================================
# Help Display
# =============================================================================

def show_help_table(io: UnifiedIO, category: Optional[str] = None) -> None:
    """Display help information as a Rich Table.

    Args:
        io: UnifiedIO instance for output
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

    # Build rows with category headers
    headers = ["Command", "Description"]
    rows = []
    for cat_name, commands in categories.items():
        rows.append([f"--- {cat_name} ---", ""])
        for cmd, desc in commands:
            rows.append([cmd, desc])
        rows.append(["", ""])  # Spacing

    io.table(headers, rows, title="Available Commands")


# =============================================================================
# Status Display
# =============================================================================

def show_status_rich(
    io: UnifiedIO,
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
    brain = status.get('orchestrator_brain', status.get('brain', 'unknown'))
    providers = status.get('available_providers', [])
    tasks = status.get('tasks_executed', 0)
    duration = datetime.now() - session_start

    content = f"""Current Brain: {brain}
Total Providers: {len(providers)}
Available: {', '.join(providers)}
Tasks Completed: {tasks}
Session Duration: {str(duration).split('.')[0]}"""

    io.panel(content, title="System Status", border_style="cyan")


# =============================================================================
# Rate Limits Display
# =============================================================================

def show_rate_limits_rich(io: UnifiedIO, rate_data: Dict[str, Any]) -> None:
    """Display rate limits with progress bars.

    Args:
        io: RichIO instance for output
        rate_data: Rate limit data with provider information
    """
    providers = rate_data.get('providers', {})

    if not providers:
        io.secho("No rate limit data available.", fg="yellow")
        return

    # Build table data
    headers = ["Provider", "Requests", "Usage %", "Tokens"]
    rows = []

    for provider_name, data in providers.items():
        requests_today = data.get('requests_today', 0)
        daily_limit = data.get('daily_limit', 100)
        tokens_today = data.get('tokens_today', 0)
        token_limit = data.get('daily_token_limit', 10000)

        request_pct = (requests_today / daily_limit * 100) if daily_limit > 0 else 0
        request_info = f"{requests_today}/{daily_limit}"
        token_info = f"{tokens_today:,}/{token_limit:,}"

        rows.append([
            provider_name.upper(),
            request_info,
            f"{request_pct:.0f}%",
            token_info
        ])

    io.table(headers, rows, title="Rate Limit Usage")


# =============================================================================
# Usage Statistics Display
# =============================================================================

def show_usage_rich(io: UnifiedIO, report: Dict[str, Any]) -> None:
    """Display usage statistics with Rich formatting.

    Args:
        io: RichIO instance for output
        report: Usage report dictionary
    """
    # Summary panel
    # Build summary content
    summary_parts = [f"Total Tasks: {report.get('total_tasks', 0)}"]

    if 'cached_hits' in report:
        summary_parts.append(f"Cache Hits: {report['cached_hits']}")
        summary_parts.append(f"API Calls: {report.get('api_calls', 0)}")

    summary_parts.append(f"Session Duration: {report.get('session_duration', 'N/A')}")

    io.panel("\n".join(summary_parts), title="Usage Summary", border_style="cyan")

    # Provider breakdown table
    by_provider = report.get('by_provider', {})
    if by_provider:
        headers = ["Provider", "Requests", "Tokens", "Avg Tokens", "Latency"]
        rows = []

        for provider, stats in by_provider.items():
            rows.append([
                provider,
                str(stats.get('count', 0)),
                f"{stats.get('total_tokens', 0):,}",
                f"{stats.get('avg_tokens', 0):.1f}",
                f"{stats.get('total_latency_ms', 0):.0f}ms"
            ])

        io.table(headers, rows, title="By Provider")

    # Cache statistics
    cache_stats = report.get('cache_stats', {})
    if cache_stats:
        total_entries = (
            cache_stats.get('exact_cache_entries', 0) +
            cache_stats.get('intent_cache_entries', 0)
        )

        cache_content = f"""Exact Hit Rate: {cache_stats.get('exact_hit_rate', 'N/A')}
Intent Hit Rate: {cache_stats.get('intent_hit_rate', 'N/A')}
Total Entries: {total_entries}"""

        io.panel(cache_content, title="Cache Statistics", border_style="blue")


# =============================================================================
# Plan/Task Tree Display
# =============================================================================

def show_plan_tree(io: UnifiedIO, plan: Dict[str, Any]) -> None:
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
            icon = "[x]"
        elif status == 'in_progress':
            icon = "[>]"
        else:  # pending
            icon = "[ ]"

        task_text = f"{icon} {description}"
        tree.add(task_text)

    # Use io.echo instead of accessing console directly
    # Tree rendering will be simpler without Rich formatting
    io.echo(f"\n{goal}:")
    for task in tasks:
        status = task.get('status', 'pending')
        description = task.get('description', 'Unknown task')
        if status == 'completed':
            icon = "[x]"
        elif status == 'in_progress':
            icon = "[>]"
        else:
            icon = "[ ]"
        io.echo(f"  {icon} {description}")
