"""
Multi-provider operations for the CLI.
Handles synthesis and delegation across multiple providers.
"""

from typing import Optional

from .io_interface import CLIIOProtocol, ClickIO


class CLIMultiProvider:
    """Handles multi-provider coordination operations."""

    def __init__(self, orchestrator):
        """Initialize multi-provider handler.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def synthesize_mode(self, io: Optional[CLIIOProtocol] = None):
        """Interactive synthesis mode - gather responses from multiple providers.

        Prompts user for a question and provider selection, queries each selected
        provider, then synthesizes their responses into a combined answer.

        Args:
            io: I/O interface for input/output. Defaults to ClickIO if None.

        State Changes:
            - Adds discovery to orchestrator working memory with synthesis info

        Side Effects:
            - Prompts user for question and provider selection via io
            - Makes multiple LLM API calls (one per provider + synthesis)
            - Writes progress and results to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        io.secho("\nSynthesis Mode", bold=True)
        io.echo("-" * 50)
        io.echo("This will query multiple providers and synthesize their responses.")

        prompt = io.prompt("Enter your question")
        if not prompt:
            io.echo("No question provided.")
            return

        available = self.orchestrator.providers.list_available()
        io.echo(f"\nAvailable providers: {', '.join(available)}")

        providers_input = io.prompt("Providers to query (comma-separated, or 'all')")

        if providers_input.lower() == 'all':
            providers_to_use = available
        else:
            providers_to_use = [p.strip() for p in providers_input.split(",")]
            providers_to_use = [p for p in providers_to_use if p in available]

        if len(providers_to_use) < 2:
            io.secho("Need at least 2 providers for synthesis.", fg="yellow")
            return

        io.echo(f"\nQuerying: {', '.join(providers_to_use)}")

        results = []
        for provider in providers_to_use:
            io.echo(f"  Asking {provider}...", nl=False)
            try:
                response = self.orchestrator.delegate(provider, prompt)
                results.append(response)  # Append LLMResponse object, not .content
                io.secho(f" Done ({response.tokens_used} tokens)", fg="green")
            except Exception as e:
                io.secho(f" Error: {e}", fg="red")

        if len(results) < 2:
            io.secho("Not enough responses for synthesis.", fg="yellow")
            return

        io.echo("\nSynthesizing responses...")
        synthesis = self.orchestrator.synthesize(
            results,
            "Combine these perspectives into a comprehensive answer:"
        )

        io.secho(f"\nSynthesized Response:", bold=True)
        io.echo("-" * 50)
        io.echo(synthesis)

        # Save synthesis result to working memory
        self.orchestrator.working_memory.add_discovery(
            f"Synthesized {len(results)} provider responses for '{prompt[:50]}...'",
            "synthesis"
        )

    def delegate_mode(self, args: str, io: Optional[CLIIOProtocol] = None):
        """Delegate a task to a specific provider.

        Sends a prompt directly to a specified provider, bypassing the default
        brain. Useful for comparing provider responses or using specific
        provider capabilities.

        Args:
            args: Space-separated string of "provider prompt". If empty,
                prompts user interactively for both.
            io: I/O interface for input/output. Defaults to ClickIO if None.

        State Changes:
            - Adds discovery to orchestrator working memory with delegation info

        Side Effects:
            - May prompt user for provider/prompt via io
            - Makes LLM API call to specified provider
            - Writes response to stdout via io

        Returns:
            None
        """
        if io is None:
            io = ClickIO()

        if not args:
            io.echo("Usage: /delegate <provider> <prompt>")
            io.echo("   or: /delegate (for interactive mode)")

            provider = io.prompt("Provider")
            prompt = io.prompt("Prompt")
        else:
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                io.echo("Usage: /delegate <provider> <prompt>")
                return
            provider, prompt = parts

        if not provider or not prompt:
            io.secho("Both provider and prompt are required.", fg="yellow")
            return

        provider = provider.lower().strip()
        available = self.orchestrator.providers.list_available()

        if provider not in available:
            io.secho(f"Provider '{provider}' not available.", fg="red")
            io.echo(f"Available: {', '.join(available)}")
            return

        io.echo(f"\nDelegating to {provider}...")

        try:
            response = self.orchestrator.delegate(provider, prompt)
            io.secho(f"\nResponse from {provider}:", bold=True)
            io.echo("-" * 50)
            io.echo(response.content)
            io.secho(
                f"\n[{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                fg="cyan"
            )

            # Save delegation result to working memory
            self.orchestrator.working_memory.add_discovery(
                f"Delegated '{prompt[:40]}...' to {provider} ({response.tokens_used} tokens)",
                "delegation"
            )
        except Exception as e:
            io.secho(f"Error: {e}", fg="red")
