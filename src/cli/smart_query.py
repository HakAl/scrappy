"""
Smart query functionality for the CLI.
Provides research-first queries using tools to gather context.
"""

from typing import Optional

from ..agent import CodeAgent
from src.task_router.intent import RegexIntentClassifier, RegexEntityExtractor
from src.task_router.protocols import IntentResult
from .io_interface import CLIIOProtocol
from .rich_output import RichIO
from .research_prompt_builder import ResearchPromptBuilder
from .research_handlers import create_default_registry
from .research_handlers.base import ClassificationResult
from .display_manager import DisplayManager
from .protocols import DisplayManagerProtocol


class CLISmartQuery:
    """Handles smart queries with tool-based research."""

    def __init__(
        self,
        orchestrator,
        classifier: Optional[RegexIntentClassifier] = None,
        entity_extractor: Optional[RegexEntityExtractor] = None,
        prompt_builder: Optional[ResearchPromptBuilder] = None,
        handler_registry: Optional[dict] = None
    ):
        """Initialize smart query handler.

        Args:
            orchestrator: The AgentOrchestrator instance
            classifier: Optional intent classifier
            entity_extractor: Optional entity extractor
            prompt_builder: Optional prompt builder
            handler_registry: Optional research handler registry
        """
        self.orchestrator = orchestrator
        self.classifier = classifier or self._create_default_classifier()
        self.entity_extractor = entity_extractor or self._create_default_extractor()
        self.prompt_builder = prompt_builder or self._create_default_prompt_builder()
        self.handler_registry = handler_registry or self._create_default_handler_registry()

    def _create_default_classifier(self) -> RegexIntentClassifier:
        """Create default intent classifier."""
        return RegexIntentClassifier()

    def _create_default_extractor(self) -> RegexEntityExtractor:
        """Create default entity extractor."""
        return RegexEntityExtractor()

    def _create_default_prompt_builder(self) -> ResearchPromptBuilder:
        """Create default prompt builder."""
        return ResearchPromptBuilder()

    def _create_default_handler_registry(self) -> dict:
        """Create default research handler registry."""
        return create_default_registry()

    def smart_query(
        self,
        query: str,
        io: Optional[CLIIOProtocol] = None,
        display: Optional[DisplayManagerProtocol] = None
    ):
        """Perform a smart query using tools to gather context before answering.

        Classifies the query intent, executes relevant research actions using
        code analysis tools, then generates an informed response with the
        gathered context.

        Supported intents include: file structure, code search, code explanation,
        git history, dependencies, architecture, bug investigation, testing,
        configuration, security, and documentation.

        Args:
            query: The user's question or query string.
            io: I/O interface for output. Deprecated, use display instead.
            display: Display manager for coordinated output. Creates default if not provided.

        State Changes:
            - Saves research results to orchestrator working memory
            - Adds discovery to orchestrator with query classification info

        Side Effects:
            - Writes progress messages to stdout via io
            - Reads files and searches codebase using CodeAgent tools
            - Makes LLM API call to generate response
            - Updates dashboard if dashboard mode is enabled

        Returns:
            LLMResponse: The response object containing the answer, provider info,
                token usage, and latency.
        """
        # Support backward compatibility with io parameter
        if display is None:
            if io is None:
                display = DisplayManager(dashboard_enabled=False)
            else:
                display = DisplayManager(io=io, dashboard_enabled=False)

        io = display.get_io()
        dashboard = display.get_dashboard()

        io.secho("\n[Smart Query] Analyzing intent...", fg="cyan", bold=True)

        # Update dashboard if enabled
        if dashboard:
            dashboard.set_state("thinking", "Analyzing query intent...")
            dashboard.update_thought_process(f"Query: {query}")

        # Classify the query intent and extract entities
        intent_result = self.classifier.classify(query)
        entities = self.entity_extractor.extract(query)

        # Create classification result wrapper for handlers
        classification = ClassificationResult(
            query=query,
            intent_result=intent_result,
            entities=entities,
            keywords=[]  # Keywords can be extracted from metadata if needed
        )

        # Display classification info
        self._display_classification(classification, io)

        if dashboard:
            dashboard.append_thought(f"\nPrimary intent: {intent_result.intent.value}")
            dashboard.set_state("scanning", "Researching codebase...")

        io.secho("\n[Smart Query] Researching...", fg="cyan", bold=True)

        # Create a research agent (read-only)
        agent = CodeAgent(self.orchestrator)

        # Gather context using handlers based on the classification
        research_results = []
        tools_used = 0

        # Execute research using handler for the classified intent
        handler = self.handler_registry.get_handler(intent_result.intent)
        if handler:
            results = handler.execute(agent, classification, io)
            research_results.extend(results)
            tools_used += len(results)

            if dashboard:
                dashboard.append_terminal(f"Researched: {intent_result.intent} ({len(results)} results)")

        # Get project summary if available
        project_summary = None
        if self.orchestrator.context.summary:
            project_summary = self.orchestrator.context.summary

        io.echo(f"  - Gathered {tools_used} research results")

        if dashboard:
            dashboard.set_state("thinking", "Generating response...")
            dashboard.append_thought(f"\nGathered {tools_used} research results")

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

        if dashboard:
            dashboard.set_state("idle", "Query complete")
            dashboard.update_context([], response.tokens_used)

        # Save smart query research to working memory
        self._save_to_memory(query, classification, research_results, tools_used)

        return response

    def _display_classification(self, classification: ClassificationResult, io: CLIIOProtocol) -> None:
        """Display classification information to the user.

        Args:
            classification: The classification result
            io: IO interface for output
        """
        io.echo(f"  Primary intent: {classification.intent_result.intent.value} "
                f"(confidence: {classification.intent_result.confidence:.2f})")

        if classification.entities:
            for entity_type, values in classification.entities.items():
                if values:
                    io.echo(f"  Extracted {entity_type}: {', '.join(values[:5])}")

    def _save_to_memory(
        self,
        query: str,
        classification: ClassificationResult,
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
                f"Smart query '{query[:50]}...' classified as {classification.intent_result.intent.value}, researched {tools_used} sources",
                "smart_query"
            )
