"""
Multi-provider operations for the CLI.
Handles synthesis and delegation across multiple providers.
"""

from typing import TYPE_CHECKING, Optional

from .io_interface import CLIIOProtocol
from .validators import is_empty_or_whitespace, validate_provider
from .user_interaction import CLIUserInteraction

if TYPE_CHECKING:
    from .protocols import UserInteractionProtocol


class CLIMultiProvider:
    """Handles multi-provider coordination operations."""

    def __init__(
        self,
        orchestrator,
        io: CLIIOProtocol,
        user_interaction: Optional["UserInteractionProtocol"] = None,
    ):
        """Initialize multi-provider handler.

        Args:
            orchestrator: The AgentOrchestrator instance
            io: I/O interface for output
            user_interaction: Optional interaction handler for prompts/confirms.
                Defaults to CLIUserInteraction if not provided.
        """
        self.orchestrator = orchestrator
        self.io = io
        # Inject user interaction - defaults to CLI mode
        self._interaction = user_interaction or CLIUserInteraction(io)

    def synthesize_mode(self):
        """Interactive synthesis mode - gather responses from multiple providers.

        Prompts user for a question and provider selection, queries each selected
        provider, then synthesizes their responses into a combined answer.

        State Changes:
            - Adds discovery to orchestrator working memory with synthesis info

        Side Effects:
            - Prompts user for question and provider selection via self.io
            - Makes multiple LLM API calls (one per provider + synthesis)
            - Writes progress and results to stdout via self.io

        Returns:
            None
        """
        self.io.secho("\nSynthesis Mode", bold=True)
        self.io.echo("-" * 50)
        self.io.echo("This will query multiple providers and synthesize their responses.")

        # Use injected interaction handler for mode-aware prompts
        prompt = self._interaction.prompt("Enter your question")
        if is_empty_or_whitespace(prompt):
            self.io.echo("No question provided.")
            return

        available = self.orchestrator.providers.list_available()
        self.io.echo(f"\nAvailable providers: {', '.join(available)}")

        providers_input = self._interaction.prompt(
            "Providers to query (comma-separated, or 'all')"
        )

        if providers_input.lower() == 'all':
            providers_to_use = available
        else:
            providers_to_use = [p.strip() for p in providers_input.split(",")]
            providers_to_use = [p for p in providers_to_use if p in available]

        if len(providers_to_use) < 2:
            self.io.secho("Need at least 2 providers for synthesis.", fg=self.io.theme.warning)
            return

        self.io.echo(f"\nQuerying: {', '.join(providers_to_use)}")

        results = []
        for provider in providers_to_use:
            self.io.echo(f"  Asking {provider}...", nl=False)
            try:
                response = self.orchestrator.delegate(provider, prompt)
                results.append(response)  # Append LLMResponse object, not .content
                self.io.secho(f" Done ({response.tokens_used} tokens)", fg=self.io.theme.success)
            except Exception as e:
                self.io.secho(f" Error: {e}", fg=self.io.theme.error)

        if len(results) < 2:
            self.io.secho("Not enough responses for synthesis.", fg=self.io.theme.warning)
            return

        self.io.echo("\nSynthesizing responses...")
        synthesis = self.orchestrator.synthesize(
            results,
            "Combine these perspectives into a comprehensive answer:"
        )

        self.io.secho(f"\nSynthesized Response:", bold=True)
        self.io.echo("-" * 50)
        self.io.echo(synthesis)

        # Save synthesis result to working memory
        self.orchestrator.working_memory.add_discovery(
            f"Synthesized {len(results)} provider responses for '{prompt[:50]}...'",
            "synthesis"
        )

    def delegate_mode(self, args: str):
        """Delegate a task to a specific provider.

        Sends a prompt directly to a specified provider, bypassing the default
        brain. Useful for comparing provider responses or using specific
        provider capabilities.

        Args:
            args: Space-separated string of "provider prompt". If empty,
                prompts user interactively for both.

        State Changes:
            - Adds discovery to orchestrator working memory with delegation info

        Side Effects:
            - May prompt user for provider/prompt via self.io
            - Makes LLM API call to specified provider
            - Writes response to stdout via self.io

        Returns:
            None
        """
        if not args:
            self.io.echo("Usage: /delegate <provider> <prompt>")
            self.io.echo("   or: /delegate (for interactive mode)")

            # Use injected interaction handler for mode-aware prompts
            provider = self._interaction.prompt("Provider")
            prompt = self._interaction.prompt("Prompt")
        else:
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                self.io.echo("Usage: /delegate <provider> <prompt>")
                return
            provider, prompt = parts

        if is_empty_or_whitespace(provider) or is_empty_or_whitespace(prompt):
            self.io.secho("Both provider and prompt are required.", fg=self.io.theme.warning)
            return

        # Validate provider with availability check
        available = self.orchestrator.providers.list_available()
        validation = validate_provider(provider, available_providers=available)

        if not validation.is_valid:
            self.io.secho(f"{validation.error}", fg=self.io.theme.error)
            return

        self.io.echo(f"\nDelegating to {validation.provider}...")

        try:
            response = self.orchestrator.delegate(validation.provider, prompt)
            self.io.secho(f"\nResponse from {validation.provider}:", bold=True)
            self.io.echo("-" * 50)
            self.io.echo(response.content)
            self.io.secho(
                f"\n[{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                fg=self.io.theme.primary
            )

            # Save delegation result to working memory
            self.orchestrator.working_memory.add_discovery(
                f"Delegated '{prompt[:40]}...' to {validation.provider} ({response.tokens_used} tokens)",
                "delegation"
            )
        except Exception as e:
            self.io.secho(f"Error: {e}", fg=self.io.theme.error)
