# Summary: 42 TYPE_CHECKING blocks fall into 4 categories

Protocol Files in Wrong Locations

  Some protocols are defined inline with their implementations rather than in dedicated protocol files:
  - StatusComponentProtocol is in cli/protocols.py but requires Textual widget types
  - ActivityState enum is in cli/protocols.py but used across layers
  ---
##  Proposed Solutions

  Architectural Fixes:

  1. Break CLI <-> Context circular dependency:
    - Create a ProgressReporterProtocol in protocols/ --> src/scrappy/infrastructure/progress.py
    - Context layer depends on protocol, CLI provides implementation
    - Context doesn't need to know about CLIIOProtocol
  2. Break TUI <-> Interactive circular dependency:
    - InteractiveMode should not import from textual_app.py
    - Extract shared types/protocols to a neutral location
  3. Consolidate protocol locations:
    - Move ActivityState, StatusComponentProtocol to protocols/ layer
    - Keep protocol files dependency-free


  ---
## SYMPTOM OF LAYERING VIOLATION - Internal Concrete Classes

  ~15 instances

  # Example from textual_app.py
  if TYPE_CHECKING:
      from .interactive import InteractiveMode
      from ..context.codebase_context import CodebaseContext

  Problem: textual_app.py depends on InteractiveMode, but InteractiveMode likely imports from textual_app.py somewhere. This is a bidirectional dependency.

  Root Cause: Circular dependency between:
  - CLI layer <-> Context layer
  - TUI (textual_app) <-> Interactive mode
  - Agent <-> Orchestrator

  Fix: Extract shared protocols or restructure dependencies.

  ---
  Root Causes Analysis

  1. Bidirectional Dependencies Between Layers

  cli/textual_app.py  <-->  cli/interactive.py
  agent/agent_loop.py <-->  orchestrator_adapter.py
  context/            <-->  cli/ (for progress reporting)

  The CLI layer knows about the context layer, and the context layer knows about the CLI layer (for progress/IO). This violates dependency inversion.

