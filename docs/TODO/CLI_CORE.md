# src/cli/core.py

**Yes, this class is "doing too much."**

While it attempts to follow good practices by delegating work to sub-components (the Facade pattern), it suffers from **Partial Refactoring Syndrome**. It acts as a "God Class" that has been hollowed out but still retains too much coupling, state management, and backward compatibility glue code.

Here is an analysis based on SOLID principles and software design best practices:

### 1. Single Responsibility Principle (SRP) Violations
The `CLI` class currently has at least three distinct responsibilities:
1.  **Bootstrapping/Composition:** Wiring up dependencies (`initialize_cli_handlers`, `_create_default_...`).
2.  **User Interface Logic:** Handling initialization messages, session restore prompts, and banners.
3.  **Legacy State Proxying:** Acting as a bridge for state that belongs in `PlanStateManager` or `InteractiveMode`.

**The Verdict:** The class should ideally **only** handle Bootstrapping. Once initialized, it should hand off control to an `InteractiveMode` or `Runner` class and disappear.

### 2. The "Proxy/Passthrough" Anti-Pattern
Lines 300–400 are the biggest "code smell." You have massive blocks of properties like this:

```python
    @property
    def active_plan(self):
        """Get active plan from state manager."""
        return self.state_manager.active_plan
```

**Why this is bad:**
*   **Leaky Abstraction:** The `CLI` is pretending to be the `StateManager`.
*   **Maintenance Burden:** If you add a feature to `StateManager`, you have to update `CLI` to expose it.
*   **Confusion:** Developers won't know whether to check `cli.active_plan` or `cli.state_manager.active_plan`.

### 3. Fragile State Synchronization
In `_handle_command`, the code creates a router, executes it, and then manually syncs state back:

```python
        # Sync state back
        self.conversation_history = router.conversation_history
        self.multiline_mode = router.multiline_mode
        # ... (3 more lines of syncing)
```

**Why this is bad:**
*   This indicates that **State Ownership is ambiguous**.
*   Does the `CLI` own the history? Does the `Router`? Does `InteractiveMode`?
*   If one property is forgotten during this sync, the application enters an inconsistent state.
*   **Fix:** Pass a shared `Context` or `SessionState` object to the Router. The Router modifies that object directly. No copying back and forth is needed.

### 4. High Coupling (Dependency Management)
The `imports` section is massive. The `CLI` knows about almost every subsystem in the application (`Codebase`, `Tasks`, `SmartQuery`, `AgentManager`, `IO`, `Rich`, etc.).

While a main entry point *needs* to know about dependencies to wire them up, the fact that it also contains logic methods (`_execute_current_task`, `_check_and_offer_session_restore`) means that logic is tightly coupled to *all* those dependencies.

### Refactoring Recommendations

To adhere to SOLID principles, you should aggressively strip this class down.

#### Step 1: Remove Proxy Properties
Delete all `@property` methods that simply delegate to `self.state_manager`.
*   **Before:** `cli.active_plan`
*   **After:** `cli.state_manager.active_plan`

#### Step 2: Move Logic to `InteractiveMode`
The `interactive_mode` method creates an `InteractiveMode` class, but the `CLI` class *also* contains methods like `_read_multiline_input` and `_handle_command`.
*   Move **all** interactive loop logic, input handling, and command routing inside `InteractiveMode`.
*   The `CLI` class should look like this:
    ```python
    def interactive_mode(self):
        mode = InteractiveMode(self.dependencies...)
        mode.run()
    ```

#### Step 3: Centralize State
Create a `SessionContext` object that holds `conversation_history`, `multiline_mode`, etc.
*   Pass this context to `CommandRouter`, `InteractiveMode`, and `CLI`.
*   Eliminate the "sync state back" block in `_handle_command`.

#### Step 4: Extract "Bootstrapper"
The logic inside `__init__` and `initialize` (checking flags, setting up logging, loading session) is actually a **Builder** or **Factory** pattern logic.
*   Consider creating a `CLIFactory` or `AppBuilder`.
*   The `CLI` class should ideally be very dumb: "I hold the components, and I have a `run()` method."

### Final Ideal Structure

The resulting class should look something like this:

```python
class CLI:
    def __init__(self, components: CLIComponents):
        self.components = components

    def start(self):
        # 1. Run startup checks (moved from initialize)
        self.components.session_manager.check_restore()
        
        # 2. Hand off to interactive loop
        interactive = InteractiveMode(
            router=self.components.router, 
            state=self.components.state_manager,
            io=self.components.io
        )
        interactive.run()
```

**Conclusion:** The class is currently a hybrid of a **Service Locator** (good) and a **Legacy Wrapper** (bad). Removing the backward compatibility layers and enforcing strict ownership of state will fix the issues.