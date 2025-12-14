"""Provider setup wizard - TUI-based configuration."""
import os
import sys
from contextlib import contextmanager
from enum import Enum, auto
from typing import Optional, Tuple, Callable, TYPE_CHECKING

from scrappy.orchestrator.provider_definitions import PROVIDERS
from scrappy.infrastructure.config.api_keys import (
    ApiKeyConfigServiceProtocol,
    create_api_key_service,
)
from scrappy.orchestrator.protocols import LLMServiceProtocol

if TYPE_CHECKING:
    from .unified_io import UnifiedIO


# Map provider names to LiteLLM model IDs for validation
PROVIDER_TO_MODEL = {
    "groq": "groq/llama-3.1-8b-instant",
    "cerebras": "cerebras/llama-3.3-70b",
    "gemini": "gemini/gemini-2.0-flash-lite",
    "openrouter": "openrouter/meta-llama/llama-3.1-8b-instruct:free",
    "github_models": "azure/gpt-4o-mini",  # GitHub models uses Azure
}


@contextmanager
def suppress_native_stderr():
    """Suppress stderr at OS level to capture C-library output (gRPC, etc.).

    Native libraries can print directly to stderr fd, bypassing Python's
    sys.stderr. This captures those at the OS file descriptor level.

    Note: In Textual TUI mode, stderr may be redirected. We suppress
    fd 2 directly regardless of what sys.stderr points to.
    """
    saved_stderr_fd = None
    try:
        # Always use fd 2 (stderr) directly, not sys.stderr.fileno()
        # because Textual may have replaced sys.stderr
        saved_stderr_fd = os.dup(2)
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
        yield
    except OSError:
        # If we can't manipulate fds, just proceed without suppression
        yield
    finally:
        if saved_stderr_fd is not None:
            try:
                os.dup2(saved_stderr_fd, 2)
                os.close(saved_stderr_fd)
            except OSError:
                pass


class WizardState(Enum):
    """State machine states for non-blocking wizard operation."""
    MENU = auto()          # Showing provider menu
    AWAITING_KEY = auto()  # Waiting for API key input
    DONE = auto()          # Wizard complete


class SetupWizard:
    """
    Interactive wizard for configuring API keys via TUI.

    Responsibilities:
    - Display provider menu
    - Collect user input
    - Validate API key format (basic)
    - Test provider connectivity via LLMService

    NOT responsible for:
    - File I/O (delegated to ApiKeyConfigService)
    - Config validation (delegated to ApiKeyConfig)
    - Path management (handled by infrastructure)

    Design Principles:
    - Single Responsibility: Only handles UI/UX for setup
    - Dependency Injection: Takes LLMService and ApiKeyConfigService via constructor
    - Testable: Can inject mock services for testing
    """

    def __init__(
        self,
        io: "UnifiedIO",
        llm_service: LLMServiceProtocol,
        config_service: Optional[ApiKeyConfigServiceProtocol] = None,
    ):
        """
        Initialize wizard with dependencies.

        Args:
            io: Output interface for TUI
            llm_service: LLM service for key validation
            config_service: API key config service (uses default if None)
        """
        self.io = io
        self._llm_service = llm_service
        self._config_service = config_service or create_api_key_service()

        # State machine for non-blocking TUI operation
        self._state = WizardState.DONE
        self._allow_cancel = True
        self._current_provider: Optional[str] = None
        self._on_complete: Optional[Callable[[bool], None]] = None

    def start(self, allow_cancel: bool = True, on_complete: Optional[Callable[[bool], None]] = None) -> None:
        """
        Start wizard in non-blocking mode (for TUI).

        Shows menu and returns immediately. Use handle_input() to process user input.

        Args:
            allow_cancel: If False, user must configure at least one provider
            on_complete: Callback when wizard completes (receives has_provider bool)
        """
        self._allow_cancel = allow_cancel
        self._on_complete = on_complete
        self._state = WizardState.MENU
        self._show_menu()

    @property
    def is_active(self) -> bool:
        """Check if wizard is currently active."""
        return self._state != WizardState.DONE

    @property
    def current_prompt(self) -> str:
        """Get prompt text for status bar based on current state."""
        if self._state == WizardState.MENU:
            # Always show "q" option - user can always exit
            return f"Select provider (1-{len(PROVIDERS)} or q)"
        elif self._state == WizardState.AWAITING_KEY:
            info = PROVIDERS[self._current_provider]
            return f"Enter {info.env_var} (or empty to cancel)"
        return ""

    def handle_input(self, user_input: str) -> None:
        """
        Handle user input based on current state (non-blocking for TUI).

        Called by TUI when user presses Enter.

        Args:
            user_input: Raw user input
        """
        user_input = user_input.strip()

        if self._state == WizardState.MENU:
            self._handle_menu_input(user_input.lower())
        elif self._state == WizardState.AWAITING_KEY:
            self._handle_key_input(user_input)

    def _handle_menu_input(self, choice: str) -> None:
        """Handle menu selection input."""
        if choice == 'q':
            # Always allow exit - user can quit anytime
            self._finish()
            return

        provider_name = self._get_provider_by_index(choice)
        if provider_name:
            self._current_provider = provider_name
            self._state = WizardState.AWAITING_KEY
            info = PROVIDERS[provider_name]
            self.io.echo(f"\nConfiguring {provider_name.replace('_', ' ').title()}")
            self.io.echo(f"Get your API key from: {info.console_url}")
        else:
            self.io.secho("Invalid selection.", fg="red")
            self._show_menu()

    def _handle_key_input(self, key: str) -> None:
        """Handle API key input."""
        if not key:
            self.io.secho("Configuration cancelled.", fg="yellow")
            self._state = WizardState.MENU
            # Screen will handle showing menu after clearing
            return

        if not self._validate_key_format(key):
            self.io.secho("Invalid key format", fg="red")
            return

        self.io.echo("Validating...")
        valid, error_msg = self._test_provider_key(self._current_provider, key)
        if not valid:
            self.io.secho(f"API key validation failed: {error_msg}", fg="red")
            return

        # Save the key
        info = PROVIDERS[self._current_provider]
        self._save_key(info.env_var, key)
        self.io.secho(f"{self._current_provider.replace('_', ' ').title()} configured!", fg="green")

        # Return to menu - screen will handle showing menu after clearing
        self._state = WizardState.MENU

    def _finish(self) -> None:
        """Complete the wizard."""
        self._state = WizardState.DONE
        if self._on_complete:
            self._on_complete(self._has_any_provider())

    def run(self, allow_cancel: bool = True) -> bool:
        """
        Run the setup wizard in BLOCKING mode (for CLI only).

        DO NOT use in TUI - use start() + handle_input() instead.

        Args:
            allow_cancel: If False, user must configure at least one provider

        Returns:
            True if at least one provider configured
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
        table.add_row("", "[bold][q][/]", "[bold]Done - Exit Setup[/]")

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
        self.io.secho(f"{name.replace('_', ' ').title()} configured!", fg="green")
        return True

    def _test_provider_key(self, name: str, key: str) -> Tuple[bool, str]:
        """
        Test if a key works by using LLMService.validate_key().

        Uses LLMService for validation to ensure all LiteLLM interaction
        goes through the service layer.

        Args:
            name: Provider name
            key: API key to test

        Returns:
            Tuple of (success, error_message)
        """
        model = PROVIDER_TO_MODEL.get(name)
        if not model:
            return False, f"Unknown provider: {name}"

        try:
            with suppress_native_stderr():
                is_valid, error_msg = self._llm_service.validate_key(model, key, timeout=10.0)

            if is_valid:
                return True, ""
            return False, error_msg or "Validation failed"
        except Exception as e:
            return False, self._format_error(str(e))

    def _format_error(self, error_msg: str) -> str:
        """
        Format error message for display.

        Args:
            error_msg: Raw error message

        Returns:
            Formatted error message
        """
        # Truncate very long error messages
        if len(error_msg) > 200:
            return error_msg[:197] + "..."
        return error_msg

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
        """Check if provider is configured via config service.

        Args:
            name: Provider name

        Returns:
            True if configured
        """
        env_var = PROVIDERS[name].env_var
        return self._config_service.get_key(env_var) is not None

    def _has_any_provider(self) -> bool:
        """Check if any provider is configured.

        Returns:
            True if at least one provider configured
        """
        env_vars = [info.env_var for info in PROVIDERS.values()]
        return self._config_service.has_any_key(env_vars)

    def _save_key(self, env_var: str, value: str) -> None:
        """Save API key via config service.

        Args:
            env_var: Environment variable name
            value: API key value
        """
        self._config_service.set_key(env_var, value)
