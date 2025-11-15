"""
Multi-provider operations for the CLI.
Handles synthesis and delegation across multiple providers.
"""

import click


class CLIMultiProvider:
    """Handles multi-provider coordination operations."""

    def __init__(self, orchestrator):
        """Initialize multi-provider handler.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator

    def synthesize_mode(self):
        """Interactive synthesis mode - gather responses from multiple providers."""
        click.secho("\nSynthesis Mode", bold=True)
        click.echo("-" * 50)
        click.echo("This will query multiple providers and synthesize their responses.")

        prompt = click.prompt("Enter your question")
        if not prompt:
            click.echo("No question provided.")
            return

        available = self.orchestrator.providers.list_available()
        click.echo(f"\nAvailable providers: {', '.join(available)}")

        providers_input = click.prompt("Providers to query (comma-separated, or 'all')")

        if providers_input.lower() == 'all':
            providers_to_use = available
        else:
            providers_to_use = [p.strip() for p in providers_input.split(",")]
            providers_to_use = [p for p in providers_to_use if p in available]

        if len(providers_to_use) < 2:
            click.secho("Need at least 2 providers for synthesis.", fg="yellow")
            return

        click.echo(f"\nQuerying: {', '.join(providers_to_use)}")

        results = []
        for provider in providers_to_use:
            click.echo(f"  Asking {provider}...", nl=False)
            try:
                response = self.orchestrator.delegate(provider, prompt)
                results.append(response)  # Append LLMResponse object, not .content
                click.secho(f" Done ({response.tokens_used} tokens)", fg="green")
            except Exception as e:
                click.secho(f" Error: {e}", fg="red")

        if len(results) < 2:
            click.secho("Not enough responses for synthesis.", fg="yellow")
            return

        click.echo("\nSynthesizing responses...")
        synthesis = self.orchestrator.synthesize(
            results,
            "Combine these perspectives into a comprehensive answer:"
        )

        click.secho(f"\nSynthesized Response:", bold=True)
        click.echo("-" * 50)
        click.echo(synthesis)

        # Save synthesis result to working memory
        self.orchestrator.add_discovery(
            f"Synthesized {len(results)} provider responses for '{prompt[:50]}...'",
            "synthesis"
        )

    def delegate_mode(self, args: str):
        """Delegate a task to a specific provider."""
        if not args:
            click.echo("Usage: /delegate <provider> <prompt>")
            click.echo("   or: /delegate (for interactive mode)")

            provider = click.prompt("Provider")
            prompt = click.prompt("Prompt")
        else:
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                click.echo("Usage: /delegate <provider> <prompt>")
                return
            provider, prompt = parts

        if not provider or not prompt:
            click.secho("Both provider and prompt are required.", fg="yellow")
            return

        provider = provider.lower().strip()
        available = self.orchestrator.providers.list_available()

        if provider not in available:
            click.secho(f"Provider '{provider}' not available.", fg="red")
            click.echo(f"Available: {', '.join(available)}")
            return

        click.echo(f"\nDelegating to {provider}...")

        try:
            response = self.orchestrator.delegate(provider, prompt)
            click.secho(f"\nResponse from {provider}:", bold=True)
            click.echo("-" * 50)
            click.echo(response.content)
            click.secho(
                f"\n[{response.model} | {response.tokens_used} tokens | {response.latency_ms:.0f}ms]",
                fg="cyan"
            )

            # Save delegation result to working memory
            self.orchestrator.add_discovery(
                f"Delegated '{prompt[:40]}...' to {provider} ({response.tokens_used} tokens)",
                "delegation"
            )
        except Exception as e:
            click.secho(f"Error: {e}", fg="red")
