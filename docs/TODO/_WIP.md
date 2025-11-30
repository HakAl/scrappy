# PROVIDER SETUP (Phase 1)

## Goal

Users without working providers get auto-launched into /setup wizard.
Providers are easy to add/remove as free tiers change.

---

## Part 1: Provider Definitions Module

### Problem

Provider names hardcoded in 8+ places across 4 files:

**`src/orchestrator/config.py`** (5 places):
```python
# Line 28-29
provider_priority: List[str] = field(
    default_factory=lambda: ['cerebras', 'groq', 'gemini', 'cohere', 'github_models']
)

# Lines 32-55: provider_info dict with ProviderInfo for each

# Lines 59-66: task_preferences dict

# Lines 69-71: brain_priority list

# Lines 74-76: fallback_priority list
```

**`src/orchestrator/registration.py`** (2 places):
```python
# Lines 10-26: Imports for each provider class
from ..providers import (
    GroqProvider, CohereProvider, GeminiProvider,
    CerebrasProvider, GitHubModelsProvider,
)

# Lines 56-93: Manual _try_register() calls for each provider
results['github_models'] = self._try_register('GitHub Models', 'github_models', GitHubModelsProvider, ...)
results['cerebras'] = self._try_register('Cerebras', 'cerebras', CerebrasProvider, ...)
# ... repeated for each provider
```

**`src/orchestrator/status_reporter.py`** (2 places):
```python
# Line 21
ALL_KNOWN_PROVIDERS = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']

# Line 24
SELECTION_PRIORITY = ['cerebras', 'groq', 'gemini']
```

**`src/providers/__init__.py`** (1 place):
```python
# Lines 8-12: Imports for each provider
from .groq_provider import GroqProvider
from .cerebras_provider import CerebrasProvider
# ... etc
```

When Cerebras/Groq kill their free tier, we have to update all these places.

### Solution: Single Source of Truth

New file: `src/orchestrator/provider_definitions.py`

One entry per provider. Everything else derived.

```python
from typing import Type, Dict, List, Optional
from dataclasses import dataclass, field

# Import provider classes
from src.providers.groq_provider import GroqProvider
from src.providers.cerebras_provider import CerebrasProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.cohere_provider import CohereProvider
from src.providers.github_models_provider import GitHubModelsProvider
from src.providers.base import LLMProviderBase


@dataclass
class ProviderDefinition:
    """Complete provider definition - single source of truth."""
    quota: str
    description: str
    env_var: str
    console_url: str
    provider_class: Type[LLMProviderBase]
    priority: int = 0                    # Lower = higher priority for brain selection
    supports_brain: bool = True          # Can be used as orchestrator brain
    task_types: List[str] = field(default_factory=list)  # ['planning', 'quick', 'general']


# ============================================================================
# SINGLE REGISTRY - ADD/REMOVE PROVIDERS HERE
# ============================================================================
PROVIDERS: Dict[str, ProviderDefinition] = {
    'cerebras': ProviderDefinition(
        quota='14,400 RPD',
        description='highest daily quota',
        env_var='CEREBRAS_API_KEY',
        console_url='cloud.cerebras.ai',
        provider_class=CerebrasProvider,
        priority=1,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'groq': ProviderDefinition(
        quota='7,000 RPD',
        description='fast and reliable',
        env_var='GROQ_API_KEY',
        console_url='console.groq.com/keys',
        provider_class=GroqProvider,
        priority=2,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'gemini': ProviderDefinition(
        quota='varies',
        description='auto-fallback enabled',
        env_var='GEMINI_API_KEY',
        console_url='aistudio.google.com/apikey',
        provider_class=GeminiProvider,
        priority=3,
        supports_brain=True,
        task_types=['planning', 'execution', 'quick', 'general'],
    ),
    'github_models': ProviderDefinition(
        quota='10K RPD',
        description='general use only - not for agent/brain roles',
        env_var='GITHUB_TOKEN',
        console_url='github.com/settings/tokens',
        provider_class=GitHubModelsProvider,
        priority=4,
        supports_brain=False,  # <-- important: not suitable for brain
        task_types=['general'],
    ),
    'cohere': ProviderDefinition(
        quota='1,000/month',
        description='limited quota - embeddings only',
        env_var='COHERE_API_KEY',
        console_url='dashboard.cohere.com/api-keys',
        provider_class=CohereProvider,
        priority=99,  # lowest priority
        supports_brain=False,
        task_types=[],  # embeddings only
    ),
}


# ============================================================================
# DERIVED HELPERS - consumers use these, not PROVIDERS directly
# ============================================================================
def get_all_provider_names() -> List[str]:
    """All known provider names."""
    return list(PROVIDERS.keys())


def get_provider_priority() -> List[str]:
    """All providers sorted by priority (lowest number = highest priority)."""
    return sorted(PROVIDERS.keys(), key=lambda k: PROVIDERS[k].priority)


def get_brain_priority() -> List[str]:
    """Only providers that can be used as brain, sorted by priority."""
    return [k for k in get_provider_priority() if PROVIDERS[k].supports_brain]


def get_task_providers(task_type: str) -> List[str]:
    """Get providers for a task type, sorted by priority."""
    return [k for k in get_provider_priority()
            if task_type in PROVIDERS[k].task_types]


def get_provider_class(name: str) -> Optional[Type[LLMProviderBase]]:
    """Get provider class by name."""
    if name in PROVIDERS:
        return PROVIDERS[name].provider_class
    return None


def get_env_var(name: str) -> Optional[str]:
    """Get environment variable name for a provider."""
    if name in PROVIDERS:
        return PROVIDERS[name].env_var
    return None
```

### Result
- Add provider = add ONE entry to PROVIDERS dict
- Remove provider = delete ONE entry
- No more hunting through 8 places
- All consumers import from provider_definitions.py

---

## Part 2: Setup Wizard (TUI)

### UX Flow

Single TUI-based wizard used for both:
- First-time setup (forced until at least one provider configured)
- `/setup` command (optional, can cancel)

Uses existing TUI components: RichLog for output, status bar for prompts, input box for user input.

```
[RichLog output area]:
+------------------------------------------+
|  Provider Setup                          |
+------------------------------------------+
|                                          |
|  [--] 1. Cerebras (14,400 RPD)           |
|         cloud.cerebras.ai                |
|                                          |
|  [--] 2. Groq (7,000 RPD)                |
|         console.groq.com/keys            |
|                                          |
|  [--] 3. Gemini (varies)                 |
|         aistudio.google.com/apikey       |
|                                          |
|  [q] Done                                |
+------------------------------------------+

[Input box]: _
[Status bar]: Select provider (1-3 or q):
```

After selecting a provider:
```
[Input box]: ******** (masked input)
[Status bar]: Enter CEREBRAS_API_KEY:
```

After validation:
```
[RichLog]: Validating... Cerebras configured!

[RichLog shows updated menu with [OK] next to Cerebras]
```

Menu generated from PROVIDERS dict. No hardcoding.

### Implementation

Uses existing `InputCaptureManager` from `textual_app.py` for prompts.
Wizard logic lives in a new module, but IO goes through the TUI.

New file: `src/cli/setup_wizard.py`

```python
"""Provider setup wizard - TUI-based configuration."""
import os
import json
from typing import Optional, Dict, TYPE_CHECKING

from src.orchestrator.provider_definitions import PROVIDERS
from src.cli.config.paths import USER_CONFIG_DIR, USER_CONFIG_FILE

if TYPE_CHECKING:
    from .unified_io import UnifiedIO


class SetupWizard:
    """Interactive wizard for configuring API keys via TUI."""

    def __init__(self, io: "UnifiedIO"):
        self.io = io

    async def run(self, allow_cancel: bool = True) -> bool:
        """Run the setup wizard.

        Args:
            allow_cancel: If False, user must configure at least one provider.
                         Used for first-time setup.

        Returns:
            True if at least one provider configured.
        """
        while True:
            self._show_menu()
            choice = await self._get_choice(allow_cancel)

            if choice == 'q':
                if allow_cancel or self._has_any_provider():
                    break
                self.io.echo("Must configure at least one provider.")
                continue

            provider_name = self._get_provider_by_index(choice)
            if provider_name:
                await self._configure_provider(provider_name)

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
                f"[bold]{name.title()}[/] ({info.quota})\n[dim]{info.console_url}[/]"
            )

        panel = Panel(table, title="Provider Setup", border_style="blue")
        self.io.echo("")  # Clear line
        # Post panel to RichLog via OutputSink
        if self.io.output_sink:
            self.io.output_sink.post_renderable(panel)
        self.io.echo("\n[q] Done")

    async def _get_choice(self, allow_cancel: bool) -> str:
        """Get user selection via TUI prompt."""
        hint = "1-{} or q".format(len(PROVIDERS))
        if not allow_cancel and not self._has_any_provider():
            hint = "1-{}".format(len(PROVIDERS))
        return self.io.prompt(f"Select provider ({hint})").strip().lower()

    async def _configure_provider(self, name: str) -> bool:
        """Configure a single provider via TUI prompts."""
        info = PROVIDERS[name]

        self.io.echo(f"\nConfiguring {name.title()}")
        self.io.echo(f"Get your API key from: [link]{info.console_url}[/link]")

        # Use TUI prompt (routes through InputCaptureManager)
        key = self.io.prompt(f"Enter {info.env_var}")
        if not key:
            return False

        if not self._validate_key_format(key):
            self.io.secho("Invalid key format", fg="red")
            return False

        self.io.echo("Validating...")
        if not self._test_provider_key(name, key):
            self.io.secho("API key validation failed", fg="red")
            return False

        self._save_key(info.env_var, key)
        self.io.secho(f"{name.title()} configured!", fg="green")
        return True

    def _test_provider_key(self, name: str, key: str) -> bool:
        """Test if a key works by making a simple API call."""
        info = PROVIDERS[name]
        try:
            os.environ[info.env_var] = key
            provider = info.provider_class()
            provider.chat([{"role": "user", "content": "test"}], max_tokens=5)
            return True
        except Exception:
            return False

    def _validate_key_format(self, key: str) -> bool:
        """Basic format validation."""
        if not key or len(key) < 10:
            return False
        if ' ' in key or '\n' in key:
            return False
        return True

    def _is_configured(self, name: str) -> bool:
        """Check if provider is configured."""
        env_var = PROVIDERS[name].env_var
        return bool(os.environ.get(env_var))

    def _has_any_provider(self) -> bool:
        """Check if any provider is configured."""
        return any(self._is_configured(name) for name in PROVIDERS)

    def _save_key(self, env_var: str, value: str) -> None:
        """Save API key to config file."""
        USER_CONFIG_DIR.mkdir(exist_ok=True)
        config = self._load_config()
        if 'api_keys' not in config:
            config['api_keys'] = {}
        config['api_keys'][env_var] = value
        with open(USER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

    def _load_config(self) -> Dict:
        """Load config from file."""
        if USER_CONFIG_FILE.exists():
            with open(USER_CONFIG_FILE) as f:
                return json.load(f)
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
        except Exception:
            pass
```

### Key Storage

Keys stored in `USER_CONFIG_FILE` (defined in `src/cli/config/paths.py` as `~/.scrappy/config.json`):

```json
{
  "api_keys": {
    "GROQ_API_KEY": "gsk_xxxxx",
    "GEMINI_API_KEY": "AIza..."
  }
}
```

Loaded at startup before TUI launches (in `commands.py:main()`).

---

## Part 3: Mandatory Setup Flow

No providers = setup wizard is forced. The app needs an LLM to function.

```
Launch scrappy
  |
  v
Load .env + ~/.scrappy/config.json -> inject into os.environ
  |
  v
Launch TUI (always)
  |
  v
on_mount: Any providers available?
  |
  +-- NO --> Force setup wizard (allow_cancel=False)
  |             |
  |             v
  |          User configures provider --> Unlock normal TUI
  |             |
  |          User tries to cancel --> "Must configure at least one provider"
  |
  +-- YES --> Show normal welcome banner, ready for input
```

### Implementation: TUI Startup Check

The check happens in `ScrappyApp.on_mount()` AFTER TUI is running:

```python
# In src/cli/textual_app.py

class ScrappyApp(App):
    def on_mount(self) -> None:
        """Called when app starts."""
        # ... existing setup (theme, components, etc.) ...

        # Check if providers are available
        if not self._has_any_provider():
            # No providers - force setup wizard
            self._launch_setup_wizard(allow_cancel=False)
        else:
            # Normal startup
            from src.cli.interactive_banner import display_banner
            display_banner(self.interactive_mode.io)

    def _has_any_provider(self) -> bool:
        """Check if any provider is configured."""
        from src.orchestrator.provider_definitions import PROVIDERS
        for name, info in PROVIDERS.items():
            if os.environ.get(info.env_var):
                return True
        return False

    def _launch_setup_wizard(self, allow_cancel: bool = True) -> None:
        """Launch setup wizard in worker thread."""
        self._run_setup_wizard(allow_cancel)

    @work(exclusive=True, thread=True)
    def _run_setup_wizard(self, allow_cancel: bool) -> None:
        """Run wizard in worker thread (blocking IO safe)."""
        from .setup_wizard import SetupWizard
        wizard = SetupWizard(self.interactive_mode.io)
        wizard.run(allow_cancel=allow_cancel)
        # After wizard completes, show welcome banner
        if self._has_any_provider():
            from src.cli.interactive_banner import display_banner
            display_banner(self.interactive_mode.io)
```

### /setup Command Handler

Add to `command_router.py`:

```python
def _handle_setup(self) -> None:
    """Handle /setup command - launch setup wizard."""
    # Get app reference and launch wizard with allow_cancel=True
    if hasattr(self, '_app') and self._app:
        self._app._launch_setup_wizard(allow_cancel=True)
    else:
        self.io.echo("Setup wizard only available in TUI mode")
```

### Key Points

1. **TUI always launches** - no pre-TUI console wizard
2. **Wizard is same for both cases** - just `allow_cancel` differs
3. **Worker thread** - wizard runs in @work thread so IO doesn't block
4. **InputCaptureManager** - handles prompts via existing TUI infrastructure

---

## Implementation Order

### Step 1: provider_definitions.py (new file)
Create `src/orchestrator/provider_definitions.py` with:
- `ProviderDefinition` dataclass
- `PROVIDERS` dict with all provider entries
- Helper functions: `get_provider_priority()`, `get_brain_priority()`, etc.

**Test**: Import and verify helper functions return correct values.

### Step 2: Refactor registration.py
Change `src/orchestrator/registration.py`:
```python
# Before (lines 56-93): Manual calls for each provider
results['github_models'] = self._try_register('GitHub Models', 'github_models', GitHubModelsProvider, ...)
results['cerebras'] = self._try_register('Cerebras', 'cerebras', CerebrasProvider, ...)

# After: Loop over PROVIDERS
from .provider_definitions import PROVIDERS

def auto_register_all(self) -> Dict[str, bool]:
    results = {}
    for name, info in PROVIDERS.items():
        results[name] = self._try_register(
            name.replace('_', ' ').title(),  # 'github_models' -> 'Github Models'
            name,
            info.provider_class,
            f"{name} provider registered ({info.quota})"
        )
    return results
```

**Test**: Existing tests should pass unchanged.

### Step 3: Refactor status_reporter.py
Change `src/orchestrator/status_reporter.py`:
```python
# Before (lines 21, 24):
ALL_KNOWN_PROVIDERS = ['github_models', 'cerebras', 'groq', 'gemini', 'cohere']
SELECTION_PRIORITY = ['cerebras', 'groq', 'gemini']

# After: Import from provider_definitions
from .provider_definitions import get_all_provider_names, get_brain_priority

class ProviderStatusReporter:
    @property
    def ALL_KNOWN_PROVIDERS(self):
        return get_all_provider_names()

    @property
    def SELECTION_PRIORITY(self):
        return get_brain_priority()
```

**Test**: Verify status output looks the same.

### Step 4: Refactor config.py
Change `src/orchestrator/config.py`:
```python
# Before: Hardcoded lists in OrchestratorConfig dataclass

# After: Derive from provider_definitions
from .provider_definitions import (
    PROVIDERS, get_provider_priority, get_brain_priority, get_task_providers
)

@dataclass
class OrchestratorConfig(BaseConfig):
    # Remove hardcoded defaults, compute from PROVIDERS
    @property
    def provider_priority(self) -> List[str]:
        return get_provider_priority()

    @property
    def brain_priority(self) -> List[str]:
        return get_brain_priority()
```

**Test**: Config validation tests should pass.

### Step 5: setup_wizard.py (new file)
Create `src/cli/setup_wizard.py` with:
- `SetupWizard` class (TUI-based, uses UnifiedIO)
- `load_saved_keys()` classmethod
- Menu generation from PROVIDERS (Rich Panel/Table)
- Key validation + test API call
- Save to `~/.scrappy/config.json`

**Test**: Mock IO, verify menu generation, key save/load.

### Step 6: Integrate into textual_app.py
Modify `src/cli/textual_app.py:ScrappyApp`:
```python
def on_mount(self) -> None:
    # ... existing setup ...

    # Check if providers are available
    if not self._has_any_provider():
        self._launch_setup_wizard(allow_cancel=False)
    else:
        display_banner(self.interactive_mode.io)

def _has_any_provider(self) -> bool:
    from src.orchestrator.provider_definitions import PROVIDERS
    for name, info in PROVIDERS.items():
        if os.environ.get(info.env_var):
            return True
    return False

def _launch_setup_wizard(self, allow_cancel: bool = True) -> None:
    self._run_setup_wizard(allow_cancel)

@work(exclusive=True, thread=True)
def _run_setup_wizard(self, allow_cancel: bool) -> None:
    from .setup_wizard import SetupWizard
    wizard = SetupWizard(self.interactive_mode.io)
    wizard.run(allow_cancel=allow_cancel)
```

Also add key loading in `commands.py:main()`:
```python
def main():
    load_dotenv(override=False)
    SetupWizard.load_saved_keys()  # Load ~/.scrappy/config.json
    cli(obj={})
```

**Test**: Verify TUI launches wizard when no providers.

### Step 7: /setup slash command
Add `/setup` command to `src/cli/command_router.py`:
```python
def _handle_setup(self) -> None:
    """Handle /setup command - launches TUI wizard."""
    # Signal to app to launch wizard
    # (Implementation depends on how command_router accesses app)
    self.io.echo("Launching provider setup...")
    # App handles the actual wizard launch
```

**Test**: Verify /setup launches wizard in running session.

---

## File Changes Summary

| File | Change |
|------|--------|
| `src/orchestrator/provider_definitions.py` | **NEW**: ProviderDefinition, PROVIDERS dict, helper functions |
| `src/orchestrator/config.py` | Remove hardcoded lists, derive from provider_definitions |
| `src/orchestrator/registration.py` | Loop over PROVIDERS instead of manual calls |
| `src/orchestrator/status_reporter.py` | Import from provider_definitions |
| `src/cli/config/paths.py` | Add `USER_CONFIG_DIR`, `USER_CONFIG_FILE` for global user config |
| `src/cli/setup_wizard.py` | **NEW**: SetupWizard class (TUI-based), key storage |
| `src/cli/textual_app.py` | Add `_has_any_provider()`, `_launch_setup_wizard()`, modify `on_mount()` |
| `src/cli/commands.py` | Load saved keys at startup |
| `src/cli/command_router.py` | Add /setup command handler |
| `tests/orchestrator/test_provider_definitions.py` | **NEW**: Tests for helper functions |
| `tests/cli/test_setup_wizard.py` | **NEW**: Tests for setup wizard |

---

## Testing Strategy

### Unit Tests
- `test_provider_definitions.py`: Helper functions return correct values
- `test_setup_wizard.py`: Menu generation, key format validation, save/load

### Integration Tests
- TUI startup with no providers shows wizard (allow_cancel=False)
- TUI startup with saved keys shows normal banner
- /setup command launches wizard (allow_cancel=True)

### Manual Tests
1. Delete `~/.scrappy/config.json` + unset env vars, run `scrappy` - TUI shows wizard, can't cancel until configured
2. Configure a provider, exit, run `scrappy` again - TUI shows normal welcome
3. From running session, `/setup` - shows wizard menu, can cancel with 'q'

---

## Out of Scope (Phase 1)

- Key rotation/expiry detection (just re-run /setup)
- Multiple key profiles (just one config.json for now)
- See OFFLINE_MODE.md for future local-only/hybrid mode planning
