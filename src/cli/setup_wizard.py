"""Provider setup wizard - TUI-based configuration."""
import os
import json
from typing import Optional, Dict, Tuple, TYPE_CHECKING

from src.orchestrator.provider_definitions import PROVIDERS
from src.cli.config.paths import USER_CONFIG_DIR, USER_CONFIG_FILE

if TYPE_CHECKING:
    from .unified_io import UnifiedIO


class SetupWizard:
    """Interactive wizard for configuring API keys via TUI."""

    def __init__(self, io: "UnifiedIO"):
        self.io = io

    def run(self, allow_cancel: bool = True) -> bool:
        """Run the setup wizard.

        Args:
            allow_cancel: If False, user must configure at least one provider.
                         Used for first-time setup.

        Returns:
            True if at least one provider configured.
        """
        while True:
            self._show_menu()
            choice = self._get_choice(allow_cancel)

            if choice == 'q':
                if allow_cancel or self._has_any_provider():
                    break
                self.io.secho("Must configure at least one provider.", fg="red")
                continue

            provider_name = self._get_provider_by_index(choice)
            if provider_name:
                self._configure_provider(provider_name)
            else:
                self.io.secho("Invalid selection.", fg="red")

        return self._has_any_provider()

    def _show_menu(self) -> None:
        """Display provider menu in RichLog."""
        from rich.panel import Panel
        from rich.table import Table

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Status", width=4)
        table.add_column("Num", width=3)
        table.add_column("Provider")

        for i, (name, info) in enumerate(sorted(
            PROVIDERS.items(), key=lambda x: x[1].priority
        ), 1):
            status = "[green][OK][/]" if self._is_configured(name) else "[dim][--][/]"
            table.add_row(
                status,
                f"{i}.",
                f"[bold]{name.replace('_', ' ').title()}[/] ({info.quota})\n[dim]{info.console_url}[/]"
            )

        table.add_row("", "", "")
        table.add_row("", "[q]", "[bold]Done[/]")

        panel = Panel(table, title="Provider Setup", border_style="blue")
        self.io.echo("")

        # Post panel to RichLog via OutputSink
        if hasattr(self.io, 'output_sink') and self.io.output_sink:
            self.io.output_sink.post_renderable(panel)
        else:
            # CLI mode - print directly
            from rich.console import Console
            console = Console()
            console.print(panel)

    def _get_choice(self, allow_cancel: bool) -> str:
        """Get user selection via TUI prompt."""
        hint = "1-{} or q".format(len(PROVIDERS))
        if not allow_cancel and not self._has_any_provider():
            hint = "1-{}".format(len(PROVIDERS))

        prompt_text = f"Select provider ({hint})"
        return self.io.prompt(prompt_text, default="").strip().lower()

    def _get_provider_by_index(self, choice: str) -> Optional[str]:
        """Get provider name by menu index.

        Args:
            choice: User's numeric choice (as string)

        Returns:
            Provider name or None if invalid
        """
        try:
            index = int(choice)
            sorted_providers = sorted(PROVIDERS.items(), key=lambda x: x[1].priority)
            if 1 <= index <= len(sorted_providers):
                return sorted_providers[index - 1][0]
        except ValueError:
            pass
        return None

    def _configure_provider(self, name: str) -> bool:
        """Configure a single provider via TUI prompts.

        Args:
            name: Provider name

        Returns:
            True if configured successfully
        """
        info = PROVIDERS[name]

        self.io.echo(f"\nConfiguring {name.replace('_', ' ').title()}")
        self.io.echo(f"Get your API key from: {info.console_url}")

        # Use TUI prompt (routes through InputCaptureManager)
        key = self.io.prompt(f"Enter {info.env_var}", default="").strip()
        if not key:
            self.io.secho("Configuration cancelled.", fg="yellow")
            return False

        if not self._validate_key_format(key):
            self.io.secho("Invalid key format", fg="red")
            return False

        self.io.echo("Validating...")
        valid, error_msg = self._test_provider_key(name, key)
        if not valid:
            self.io.secho(f"API key validation failed: {error_msg}", fg="red")
            return False

        self._save_key(info.env_var, key)
        # Update environment immediately
        os.environ[info.env_var] = key
        self.io.secho(f"{name.replace('_', ' ').title()} configured!", fg="green")
        return True

    def _test_provider_key(self, name: str, key: str) -> Tuple[bool, str]:
        """Test if a key works by making a simple API call.

        Args:
            name: Provider name
            key: API key to test

        Returns:
            Tuple of (success, error_message)
        """
        info = PROVIDERS[name]
        try:
            # Temporarily set the key in environment
            old_key = os.environ.get(info.env_var)
            os.environ[info.env_var] = key

            try:
                provider = info.provider_class()
                # Make a minimal test call
                provider.chat([{"role": "user", "content": "test"}], max_tokens=5)
                return True, ""
            finally:
                # Restore old key
                if old_key is not None:
                    os.environ[info.env_var] = old_key
                elif info.env_var in os.environ:
                    del os.environ[info.env_var]

        except Exception as e:
            error_msg = str(e)
            # Try to extract useful error message
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                error_msg = "Invalid API key"
            elif "403" in error_msg or "forbidden" in error_msg.lower():
                error_msg = "API key does not have required permissions"
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                error_msg = "Rate limit exceeded"
            elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                error_msg = "Network error - check your connection"
            return False, error_msg

    def _validate_key_format(self, key: str) -> bool:
        """Basic format validation.

        Args:
            key: API key to validate

        Returns:
            True if format appears valid
        """
        if not key or len(key) < 10:
            return False
        if ' ' in key or '\n' in key or '\t' in key:
            return False
        return True

    def _is_configured(self, name: str) -> bool:
        """Check if provider is configured.

        Args:
            name: Provider name

        Returns:
            True if configured
        """
        env_var = PROVIDERS[name].env_var
        return bool(os.environ.get(env_var))

    def _has_any_provider(self) -> bool:
        """Check if any provider is configured.

        Returns:
            True if at least one provider configured
        """
        return any(self._is_configured(name) for name in PROVIDERS)

    def _save_key(self, env_var: str, value: str) -> None:
        """Save API key to config file.

        Args:
            env_var: Environment variable name
            value: API key value
        """
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = self._load_config()
        if 'api_keys' not in config:
            config['api_keys'] = {}
        config['api_keys'][env_var] = value
        with open(USER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

    def _load_config(self) -> Dict:
        """Load config from file.

        Returns:
            Config dictionary
        """
        if USER_CONFIG_FILE.exists():
            try:
                with open(USER_CONFIG_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    @staticmethod
    def load_saved_keys() -> None:
        """Load saved keys into os.environ. Called at startup."""
        if not USER_CONFIG_FILE.exists():
            return
        try:
            with open(USER_CONFIG_FILE) as f:
                config = json.load(f)
            for env_var, value in config.get('api_keys', {}).items():
                if env_var not in os.environ:
                    os.environ[env_var] = value
        except (json.JSONDecodeError, IOError):
            pass
