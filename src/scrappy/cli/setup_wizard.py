"""Provider setup wizard - TUI-based configuration."""
import os
from contextlib import contextmanager
from enum import Enum, auto
from typing import Optional, Tuple, Callable, TYPE_CHECKING

from scrappy.orchestrator.provider_definitions import PROVIDERS
from scrappy.infrastructure.config.api_keys import (
    ApiKeyConfigServiceProtocol,
    ApiKeyValidationError,
    create_api_key_service,
)
from scrappy.infrastructure.validation import validate_api_key
from scrappy.orchestrator.protocols import LLMServiceProtocol

if TYPE_CHECKING:
    from .unified_io import UnifiedIO


# Map provider names to LiteLLM model IDs for validation
PROVIDER_TO_MODEL = {
    "groq": "groq/llama-3.1-8b-instant",
    "cerebras": "cerebras/llama-3.3-70b",
    "gemini": "gemini/gemini-2.0-flash-lite",
    "sambanova": "sambanova/Meta-Llama-3.1-8B-Instruct",
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
    DISCLAIMER = auto()    # Showing disclaimer (first-run only)
    MENU = auto()          # Showing provider menu
    ACTION_MENU = auto()   # Showing action menu for configured provider
    AWAITING_KEY = auto()  # Waiting for API key input
    CONFIRM_REMOVE = auto()  # Confirming key removal
    DONE = auto()          # Wizard complete


DISCLAIMER_TEXT = """
NOTICE: scrappy can read, modify, and delete files on your system.

  - Review all file operations before confirming
  - Back up important work before using agent mode
  - The authors are not liable for data loss

By continuing, you acknowledge these risks.
"""


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

        Shows disclaimer (if not acknowledged), then menu.
        Returns immediately. Use handle_input() to process user input.

        Args:
            allow_cancel: If False, user must configure at least one provider
            on_complete: Callback when wizard completes (receives has_provider bool)
        """
        self._allow_cancel = allow_cancel
        self._on_complete = on_complete

        # Check if disclaimer needs to be shown
        if not self._config_service.is_disclaimer_acknowledged():
            self._state = WizardState.DISCLAIMER
            self._show_disclaimer()
        else:
            self._state = WizardState.MENU
            self._show_menu()

    @property
    def is_active(self) -> bool:
        """Check if wizard is currently active."""
        return self._state != WizardState.DONE

    @property
    def current_prompt(self) -> str:
        """Get prompt text for status bar based on current state."""
        if self._state == WizardState.DISCLAIMER:
            return "Type 'ok' to continue, or 'q' to quit"
        elif self._state == WizardState.MENU:
            # Always show "q" option - user can always exit
            return f"Select provider (1-{len(PROVIDERS)}) or q to exit"
        elif self._state == WizardState.ACTION_MENU:
            return "1=Update key, 2=Remove key, q=Back"
        elif self._state == WizardState.AWAITING_KEY:
            info = PROVIDERS[self._current_provider]
            return f"Enter {info.env_var} or q to cancel"
        elif self._state == WizardState.CONFIRM_REMOVE:
            return "Remove this API key? (y/n)"
        return ""

    def handle_input(self, user_input: str) -> None:
        """
        Handle user input based on current state (non-blocking for TUI).

        Called by TUI when user presses Enter.

        Args:
            user_input: Raw user input
        """
        user_input = user_input.strip()

        if self._state == WizardState.DISCLAIMER:
            self._handle_disclaimer_input(user_input.lower())
        elif self._state == WizardState.MENU:
            self._handle_menu_input(user_input.lower())
        elif self._state == WizardState.ACTION_MENU:
            self._handle_action_input(user_input.lower())
        elif self._state == WizardState.AWAITING_KEY:
            self._handle_key_input(user_input)
        elif self._state == WizardState.CONFIRM_REMOVE:
            self._handle_confirm_remove_input(user_input.lower())

    def _handle_disclaimer_input(self, response: str) -> None:
        """Handle disclaimer acknowledgment input."""
        if response == 'q':
            self._finish()
            return

        if response in ('ok', 'yes', 'y'):
            self._config_service.acknowledge_disclaimer()
            self._state = WizardState.MENU
            self._show_menu()
        else:
            self.io.secho("Please type 'ok' to continue or 'q' to quit.", fg="yellow")

    def _show_disclaimer(self) -> None:
        """Display disclaimer notice."""
        from rich.panel import Panel

        panel = Panel(
            DISCLAIMER_TEXT.strip(),
            title="Terms of Use",
            border_style="yellow",
            expand=False
        )

        if hasattr(self.io, 'output_sink') and self.io.output_sink:
            self.io.output_sink.post_renderable(panel)
        else:
            from rich.console import Console
            console = Console()
            console.print(panel)

    def _handle_menu_input(self, choice: str) -> None:
        """Handle menu selection input."""
        if choice == 'q':
            # Always allow exit - user can quit anytime
            self._finish()
            return

        provider_name = self._get_provider_by_index(choice)
        if provider_name:
            self._current_provider = provider_name
            if self._is_configured(provider_name):
                # Show action menu for configured providers
                self._state = WizardState.ACTION_MENU
                self._show_action_menu()
            else:
                # Go straight to key input for unconfigured providers
                self._state = WizardState.AWAITING_KEY
                info = PROVIDERS[provider_name]
                self.io.echo(f"\nConfiguring {provider_name.replace('_', ' ').title()}")
                self.io.echo(f"Get your API key from: {info.console_url}")
        else:
            self.io.secho("Invalid selection.", fg=self.io.theme.error)
            self._show_menu()

    def _handle_key_input(self, key: str) -> None:
        """Handle API key input."""
        if not key or key.lower() == 'q':
            self.io.secho("Configuration cancelled.", fg="yellow")
            self._state = WizardState.MENU
            # Screen will handle showing menu after clearing
            return

        # Validate key format and security
        validation_result = validate_api_key(key)
        if not validation_result.is_valid:
            self.io.secho(f"Invalid key: {validation_result.error}", fg=self.io.theme.error)
            return

        # Use sanitized value from validation
        sanitized_key = validation_result.sanitized_value

        self.io.echo("Validating with provider...")
        valid, error_msg = self._test_provider_key(self._current_provider, sanitized_key)
        if not valid:
            self.io.secho(f"API key validation failed: {error_msg}", fg=self.io.theme.error)
            return

        # Save the key (config service will validate again as defense-in-depth)
        info = PROVIDERS[self._current_provider]
        try:
            self._save_key(info.env_var, sanitized_key)
            self.io.secho(f"{self._current_provider.replace('_', ' ').title()} configured!", fg=self.io.theme.success)
        except ApiKeyValidationError as e:
            self.io.secho(f"Failed to save key: {e}", fg=self.io.theme.error)
            return

        # Return to menu - screen will handle showing menu after clearing
        self._state = WizardState.MENU

    def _show_action_menu(self) -> None:
        """Display action menu for a configured provider."""
        from rich.panel import Panel

        provider_title = self._current_provider.replace('_', ' ').title()
        info = PROVIDERS[self._current_provider]

        # Mask the current key for display
        current_key = self._config_service.get_key(info.env_var) or ""
        if len(current_key) > 8:
            masked = f"{current_key[:4]}...{current_key[-4:]}"
        else:
            masked = "****"

        content = f"""[bold]{provider_title}[/bold]
Current key: [dim]{masked}[/dim]

  1. Update API key
  2. Remove API key
  q. Back to menu"""

        panel = Panel(content, title="Manage Provider", border_style="blue", expand=False)

        if hasattr(self.io, 'output_sink') and self.io.output_sink:
            self.io.output_sink.post_renderable(panel)
        else:
            from rich.console import Console
            console = Console()
            console.print(panel)

    def _handle_action_input(self, choice: str) -> None:
        """Handle action menu selection."""
        if choice == 'q':
            self._state = WizardState.MENU
            self._show_menu()
            return

        if choice == '1':
            # Update key - same flow as adding a new key
            self._state = WizardState.AWAITING_KEY
            info = PROVIDERS[self._current_provider]
            self.io.echo(f"\nUpdating {self._current_provider.replace('_', ' ').title()}")
            self.io.echo(f"Get your API key from: {info.console_url}")
        elif choice == '2':
            # Remove key - confirm first
            self._state = WizardState.CONFIRM_REMOVE
            provider_title = self._current_provider.replace('_', ' ').title()
            self.io.echo(f"\nRemove API key for {provider_title}?")
        else:
            self.io.secho("Invalid selection. Enter 1, 2, or q.", fg=self.io.theme.error)

    def _handle_confirm_remove_input(self, response: str) -> None:
        """Handle removal confirmation input."""
        if response in ('y', 'yes'):
            self._remove_key()
            provider_title = self._current_provider.replace('_', ' ').title()
            self.io.secho(f"{provider_title} API key removed.", fg=self.io.theme.success)
            self._state = WizardState.MENU
            # Screen will handle showing menu after clearing
        elif response in ('n', 'no', 'q'):
            self.io.secho("Removal cancelled.", fg="yellow")
            self._state = WizardState.MENU
            # Screen will handle showing menu after clearing
        else:
            self.io.secho("Please enter 'y' or 'n'.", fg=self.io.theme.error)

    def _remove_key(self) -> None:
        """Remove the current provider's API key."""
        info = PROVIDERS[self._current_provider]
        config = self._config_service.load()
        if info.env_var in config.api_keys:
            del config.api_keys[info.env_var]
            self._config_service.save(config)

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
                self.io.secho("Must configure at least one provider.", fg=self.io.theme.error)
                continue

            provider_name = self._get_provider_by_index(choice)
            if provider_name:
                self._configure_provider(provider_name)
            else:
                self.io.secho("Invalid selection.", fg=self.io.theme.error)

        return self._has_any_provider()

    def _show_menu(self) -> None:
        """Display provider menu in RichLog."""
        from rich.panel import Panel
        from rich.table import Table

        table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        table.add_column("Status", width=6, no_wrap=True)
        table.add_column("Num", width=3, no_wrap=True)
        table.add_column("Provider", no_wrap=False, overflow="fold", max_width=50)

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
        table.add_row("", "", "[bold]q - Done / Exit Setup[/]")

        panel = Panel(table, title="Provider Setup", border_style="blue", expand=False)
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

        # Validate key format and security
        validation_result = validate_api_key(key)
        if not validation_result.is_valid:
            self.io.secho(f"Invalid key: {validation_result.error}", fg=self.io.theme.error)
            return False

        sanitized_key = validation_result.sanitized_value

        self.io.echo("Validating with provider...")
        valid, error_msg = self._test_provider_key(name, sanitized_key)
        if not valid:
            self.io.secho(f"API key validation failed: {error_msg}", fg=self.io.theme.error)
            return False

        try:
            self._save_key(info.env_var, sanitized_key)
            self.io.secho(f"{name.replace('_', ' ').title()} configured!", fg=self.io.theme.success)
            return True
        except ApiKeyValidationError as e:
            self.io.secho(f"Failed to save key: {e}", fg=self.io.theme.error)
            return False

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
