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

def show_help_table(
    io: UnifiedIO,
    category: Optional[str] = None
) -> None:
    """Display help information as a Rich Table.

    Args:
        io: UnifiedIO instance with theme for output
        category: Optional category filter (e.g., 'provider', 'task')
    """
    # Define command categories
    categories = {
        'Chat & Conversation': [
            ('/help', 'Show all commands'),
            ('/ml', 'Toggle multiline input mode'),
            ('/clear', 'Clear conversation history'),
            ('/history [n]', 'Show last n messages'),
        ],
        'Task Operations': [
            ('/plan <task>', 'Break down task into steps'),
            ('/tasks', 'View current plan progress'),
            ('/reason <q>', 'Analyze with reasoning'),
            ('/agent <task>', 'Run code agent'),
            ('/smart <query>', 'Research-first query'),
            ('/explore [path]', 'Explore codebase'),
        ],
        'Provider Management': [
            ('/setup', 'Configure API keys'),
            ('/models [filter]', 'List available models'),
            ('/model [mode]', 'Set model tier (fast/chat/instruct)'),
            ('/status', 'Show system status'),
            ('/usage', 'Show usage statistics'),
        ],
        'Context Management': [
            ('/context', 'Show context status'),
            ('/context refresh', 'Force re-exploration'),
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
            ('/quit, /exit', 'Exit the CLI'),
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
        io: UnifiedIO instance with theme for output
        orchestrator: The orchestrator instance
        session_start: Session start time
    """
    status = orchestrator.status()

    # Build status content
    tasks = status.get('tasks_executed', 0)
    duration = datetime.now() - session_start
    current_tier = status.get('current_tier', 'instruct')
    mode_str = current_tier.upper()

    # Model groups info (LiteLLM)
    model_groups = status.get('model_groups', [])
    configured_models = status.get('configured_models', [])
    provider_health = status.get('provider_health', {})

    # Build models by group
    fast_models = [m for m in configured_models if m.get('group') == 'fast']
    chat_models = [m for m in configured_models if m.get('group') == 'chat']
    instruct_models = [m for m in configured_models if m.get('group') == 'instruct']

    # Format model list with health indicators
    def format_model(m: dict) -> str:
        provider = m.get('provider', 'unknown')
        model_id = m.get('model_id', 'unknown')
        health = provider_health.get(provider, {})
        if health:
            healthy = health.get('healthy', True)
            indicator = "[OK]" if healthy else "[!!]"
            return f"  {indicator} {model_id}"
        return f"  [--] {model_id}"

    # Get unique configured providers
    configured_providers = sorted(set(m.get('provider', '') for m in configured_models))

    # Build content sections
    lines = [
        f"Mode: {mode_str}",
        f"Tasks Completed: {tasks}",
        f"Session Duration: {str(duration).split('.')[0]}",
        f"Providers: {', '.join(configured_providers) if configured_providers else 'None configured'}",
        "",
        "Model Groups:",
    ]

    if fast_models:
        lines.append("  FAST (8B, speed priority):")
        for m in fast_models:
            lines.append(format_model(m))
    else:
        lines.append("  FAST: No models configured")

    if chat_models:
        lines.append("  CHAT (70B, conversation):")
        for m in chat_models:
            lines.append(format_model(m))
    else:
        lines.append("  CHAT: No models configured")

    if instruct_models:
        lines.append("  INSTRUCT (agent/tools):")
        for m in instruct_models:
            lines.append(format_model(m))
    else:
        lines.append("  INSTRUCT: No models configured")

    # Add health summary if any requests have been made
    if provider_health:
        lines.append("")
        lines.append("Provider Performance:")
        for provider, health in sorted(provider_health.items()):
            healthy = health.get('healthy', True)
            requests = health.get('request_count', 0)
            success_rate = health.get('success_rate', 1.0)
            avg_latency = health.get('avg_latency_ms', 0)
            tokens = health.get('total_tokens', 0)
            indicator = "[OK]" if healthy else "[!!]"
            lines.append(
                f"  {indicator} {provider}: "
                f"{success_rate:.0%} success, "
                f"{avg_latency:.0f}ms avg, "
                f"{tokens:,} tokens, "
                f"{requests} reqs"
            )

    content = "\n".join(lines)
    io.panel(content, title="System Status", border_style=io.theme.primary)


# =============================================================================
# Rate Limits Display
# =============================================================================

def show_rate_limits_rich(
    io: UnifiedIO,
    rate_data: Dict[str, Any]
) -> None:
    """Display rate limits with progress bars.

    Args:
        io: UnifiedIO instance with theme for output
        rate_data: Rate limit data with provider information
    """
    providers = rate_data.get('providers', {})

    if not providers:
        io.secho("No rate limit data available.", fg=io.theme.warning)
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

    Uses consistent table styling throughout for visual coherence.

    Args:
        io: RichIO instance for output
        report: Usage report dictionary
    """
    # Summary as a table (consistent styling with other sections)
    summary_headers = ["Metric", "Value"]
    summary_rows = [
        ["Total Tasks", str(report.get('total_tasks', 0))],
    ]

    if 'cached_hits' in report:
        summary_rows.append(["Cache Hits", str(report.get('cached_hits', 0))])
        summary_rows.append(["API Calls", str(report.get('api_calls', 0))])

    summary_rows.append(["Session Duration", report.get('session_duration', 'N/A')])

    io.table(summary_headers, summary_rows, title="Usage Summary")

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

    # Cache statistics as a table (consistent with other sections)
    cache_stats = report.get('cache_stats', {})
    if cache_stats:
        total_entries = (
            cache_stats.get('exact_cache_entries', 0) +
            cache_stats.get('intent_cache_entries', 0)
        )

        cache_headers = ["Metric", "Value"]
        cache_rows = [
            ["Exact Hit Rate", cache_stats.get('exact_hit_rate', 'N/A')],
            ["Intent Hit Rate", cache_stats.get('intent_hit_rate', 'N/A')],
            ["Total Entries", str(total_entries)],
        ]

        io.table(cache_headers, cache_rows, title="Cache Statistics")


# =============================================================================
# Plan/Task Tree Display
# =============================================================================

def show_plan_tree(
    io: UnifiedIO,
    plan: Dict[str, Any]
) -> None:
    """Display plan and tasks as a Rich Tree structure.

    Args:
        io: UnifiedIO instance with theme for output
        plan: Plan dictionary with goal and tasks
    """
    goal = plan.get('goal', '')
    tasks = plan.get('tasks', [])

    if not goal and not tasks:
        io.secho("No active plan.", fg=io.theme.warning)
        return

    # Create tree
    tree_title = f"[bold {io.theme.primary}]{goal or 'Plan'}[/bold {io.theme.primary}]"
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
