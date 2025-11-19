"""
Smart query functionality for the CLI.
Provides research-first queries using tools to gather context.
"""

from typing import Optional

from ..agent import CodeAgent
from ..intent_classifier import IntentClassifier, get_research_actions
from .io_interface import CLIIOProtocol
from .rich_output import RichIO
from .prompt_builder import PromptBuilder
from .research_handlers import create_default_registry


class CLISmartQuery:
    """Handles smart queries with tool-based research."""

    def __init__(self, orchestrator):
        """Initialize smart query handler.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator
        self.classifier = IntentClassifier()
        self.prompt_builder = PromptBuilder()
        self.handler_registry = create_default_registry()

    def smart_query(self, query: str, io: Optional[CLIIOProtocol] = None):
        """Perform a smart query using tools to gather context before answering.

        Classifies the query intent, executes relevant research actions using
        code analysis tools, then generates an informed response with the
        gathered context.

        Supported intents include: file structure, code search, code explanation,
        git history, dependencies, architecture, bug investigation, testing,
        configuration, security, and documentation.

        Args:
            query: The user's question or query string.
            io: I/O interface for output. If None, uses ClickIO.

        State Changes:
            - Saves research results to orchestrator working memory
            - Adds discovery to orchestrator with query classification info

        Side Effects:
            - Writes progress messages to stdout via io
            - Reads files and searches codebase using CodeAgent tools
            - Makes LLM API call to generate response

        Returns:
            LLMResponse: The response object containing the answer, provider info,
                token usage, and latency.
        """
        if io is None:
            io = RichIO()

        io.secho("\n[Smart Query] Analyzing intent...", fg="cyan", bold=True)

        # Classify the query intent
        classification = self.classifier.classify(query)

        # Display classification info
        self._display_classification(classification, io)

        io.secho("\n[Smart Query] Researching...", fg="cyan", bold=True)

        # Create a research agent (read-only)
        agent = CodeAgent(self.orchestrator)

        # Gather context using handlers based on the classification
        research_results = []
        tools_used = 0

        # Get recommended research actions
        actions = get_research_actions(classification)

        # Execute research using handler registry
        for action in actions:
            intent = action['intent']
            handler = self.handler_registry.get_handler(intent)

            if handler:
                results = handler.execute(agent, classification, io)
                research_results.extend(results)
                tools_used += len(results)

        # Get project summary if available
        project_summary = None
        if self.orchestrator.context.summary:
            project_summary = self.orchestrator.context.summary

        io.echo(f"  - Gathered {tools_used} research results")

        # Build prompt using PromptBuilder
        prompt = self.prompt_builder.build(
            query=query,
            classification=classification,
            research_results=research_results,
            project_summary=project_summary
        )

        # Get response from LLM
        io.secho("\nAssistant: ", fg="blue", bold=True, nl=False)
        response = self.orchestrator.delegate(
            self.orchestrator.brain,
            prompt,
            system_prompt=self.prompt_builder.get_system_prompt()
        )

        io.echo(response.content)
        io.secho(
            f"[{response.provider}/{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms | {tools_used} tools used]",
            fg="cyan"
        )

        # Save smart query research to working memory
        self._save_to_memory(query, classification, research_results, tools_used)

        return response

    def _display_classification(self, classification, io: CLIIOProtocol) -> None:
        """Display classification information to the user.

        Args:
            classification: The classification result
            io: IO interface for output
        """
        io.echo(f"  Primary intent: {classification.primary_intent.intent.value} "
                f"(confidence: {classification.primary_intent.confidence:.2f})")

        if classification.secondary_intents:
            secondary_str = ", ".join([
                f"{i.intent.value}({i.confidence:.2f})"
                for i in classification.secondary_intents[:3]
            ])
            io.echo(f"  Secondary intents: {secondary_str}")

        if classification.entities:
            for entity_type, values in classification.entities.items():
                if values:
                    io.echo(f"  Extracted {entity_type}: {', '.join(values[:5])}")

    def _save_to_memory(
        self,
        query: str,
        classification,
        research_results: list,
        tools_used: int
    ) -> None:
        """Save smart query results to working memory.

        Args:
            query: The original query
            classification: The classification result
            research_results: List of research results
            tools_used: Number of tools/results gathered
        """
        if tools_used > 0:
            self.orchestrator.working_memory.remember_search(
                f"smart_query: {query}",
                research_results[:5]  # Save top 5 research results
            )
            self.orchestrator.working_memory.add_discovery(
                f"Smart query '{query[:50]}...' classified as {classification.primary_intent.intent.value}, researched {tools_used} sources",
                "smart_query"
            )
