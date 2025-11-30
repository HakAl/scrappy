"""
Shared types and protocols for formatters.

Defines minimal interfaces that formatters need for styling output,
avoiding direct dependencies on higher-level CLI modules.
"""

from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.theme import ThemeProtocol


@runtime_checkable
class FormatterOutputProtocol(Protocol):
    """Minimal protocol for formatter output needs.

    Defines just what formatters need: styling text and accessing theme colors.
    This avoids formatters depending directly on CLI modules like UnifiedIO.

    Following SOLID principles:
    - Dependency Inversion: Formatters depend on this abstraction, not concrete IO
    - Interface Segregation: Minimal interface with only what formatters need

    Implementations:
    - UnifiedIO: Implements this protocol (and more)
    - CLIIOProtocol implementations: Also provide these methods
    """

    @property
    def theme(self) -> "ThemeProtocol":
        """Get the theme for color access.

        Returns:
            ThemeProtocol instance with color definitions
        """
        ...

    def style(
        self,
        text: str,
        fg: str | None = None,
        bold: bool = False
    ) -> str:
        """Apply styling to text.

        Args:
            text: Text to style
            fg: Foreground color
            bold: Whether to make text bold

        Returns:
            Styled text string
        """
        ...
