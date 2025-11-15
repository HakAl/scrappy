"""
Smart query functionality for the CLI.
Provides research-first queries using tools to gather context.
"""

import click

try:
    from ..agent import CodeAgent
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent import CodeAgent


class CLISmartQuery:
    """Handles smart queries with tool-based research."""

    def __init__(self, orchestrator):
        """Initialize smart query handler.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def smart_query(self, query: str):
        """Perform a smart query using tools to gather context before answering.

        Returns:
            LLMResponse object with the answer
        """
        click.secho("\n[Smart Query] Researching...", fg="cyan", bold=True)

        # Create a research agent (read-only)
        agent = CodeAgent(self.orchestrator)

        # Gather context using tools based on the query
        research_results = []
        tools_used = 0

        # Analyze query to decide what to research
        query_lower = query.lower()

        # If asking about specific files/directories
        if any(word in query_lower for word in ['file', 'folder', 'directory', 'structure', 'what files', 'show me']):
            click.echo("  - Checking directory structure...")
            result = agent._tool_list_directory(".", depth=1)
            research_results.append(f"Directory Structure:\n{result}")
            tools_used += 1

        # If asking about specific code/functions/classes
        if any(word in query_lower for word in ['function', 'class', 'method', 'implement', 'how does', 'where is']):
            # Try to extract keywords to search for
            for word in query.split():
                if len(word) > 3 and word[0].isupper():  # Likely a class/function name
                    click.echo(f"  - Searching for '{word}'...")
                    result = agent._tool_search_code(word, "*.py")
                    if "No matches" not in result:
                        research_results.append(f"Code search for '{word}':\n{result[:1000]}")
                        tools_used += 1
                        break

        # If asking about recent changes/history
        if any(word in query_lower for word in ['recent', 'change', 'commit', 'history', 'what changed', 'update']):
            click.echo("  - Checking git history...")
            result = agent._tool_git_log(n=5)
            research_results.append(f"Recent Commits:\n{result}")
            tools_used += 1

        # If asking about specific module/component
        keywords = ['auth', 'api', 'database', 'config', 'test', 'model', 'view', 'controller', 'service', 'util']
        for keyword in keywords:
            if keyword in query_lower:
                click.echo(f"  - Searching for '{keyword}' related code...")
                result = agent._tool_search_code(keyword, "*.py")
                if "No matches" not in result:
                    research_results.append(f"Code containing '{keyword}':\n{result[:1500]}")
                    tools_used += 1
                break

        # Always include project summary if available
        if self.orchestrator.context.summary:
            research_results.insert(0, f"Project Summary:\n{self.orchestrator.context.summary}")

        click.echo(f"  - Gathered {tools_used} research results")

        # Now answer with the gathered context
        if research_results:
            context = "\n\n---\n\n".join(research_results)
            prompt = f"""Based on this research about the codebase:

{context}

Answer this question: {query}

Provide a helpful, specific answer based on the research findings."""
        else:
            prompt = query

        click.secho("\nAssistant: ", fg="blue", bold=True, nl=False)
        response = self.orchestrator.delegate(
            self.orchestrator.brain,
            prompt,
            system_prompt="You are a helpful AI assistant with access to codebase research. Use the provided research to give specific, accurate answers."
        )

        click.echo(response.content)
        click.secho(
            f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms | {tools_used} tools used]",
            fg="cyan"
        )

        # Save smart query research to working memory
        if tools_used > 0:
            self.orchestrator.remember_search(
                f"smart_query: {query}",
                research_results[:5]  # Save top 5 research results
            )
            self.orchestrator.add_discovery(
                f"Smart query '{query[:50]}...' researched {tools_used} sources",
                "smart_query"
            )

        return response
