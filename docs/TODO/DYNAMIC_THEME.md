  Plan: Dynamic Theme Loading for TUI

  Step 1: Convert theme defaults to hex values

  File: src/infrastructure/theme.py

  Update ScrappyTheme, LightTheme, and CustomTheme defaults to use hex values instead of color names.

  Step 2: Remove static variable definitions from TCSS

  File: src/cli/scrappy.tcss

  Remove the $surface, $primary, etc. definitions at the top. Keep the rest of the file unchanged (it already
  references these variables).

  Step 3: Create Theme from ThemeProtocol in ScrappyApp

  File: src/cli/textual_app.py

  In on_mount():
  - Create Textual Theme object from self._theme
  - Map text_muted -> text-muted, surface_alt -> surface-alt
  - Call register_theme() and set self.theme

  Step 4: Update tests

  - Verify existing theme tests still pass with hex values
  - Add test for Theme object creation from ThemeProtocol
