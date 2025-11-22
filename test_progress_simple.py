"""Quick test of Rich Live transient behavior."""
import time

try:
    from rich.console import Console
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.text import Text

    print("Testing Rich Live with transient=True\n")

    console = Console(stderr=True)

    print("Test 1: Live display with transient=True")
    with Live(
        Spinner("dots", text=Text("Loading...", style="cyan")),
        console=console,
        transient=True,
        refresh_per_second=10
    ) as live:
        time.sleep(1)
        live.update(Spinner("dots", text=Text("Still loading...", style="cyan")))
        time.sleep(1)
        live.update(Text("✓ Complete", style="green"))
        time.sleep(0.5)
    # Should disappear here

    print("\nDid the progress disappear? (It should have)")
    time.sleep(1)

    print("\nTest 2: Live display WITHOUT transient")
    with Live(
        Spinner("dots", text=Text("Loading...", style="cyan")),
        console=console,
        transient=False,  # Should NOT disappear
        refresh_per_second=10
    ) as live:
        time.sleep(1)
        live.update(Text("✓ Complete", style="green"))
        time.sleep(0.5)
    # Should remain visible

    print("\nDid the progress stay visible? (It should have)")
    time.sleep(1)

    print("\nTests complete")

except ImportError as e:
    print(f"Rich not available: {e}")
