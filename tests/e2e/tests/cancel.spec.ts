import { test, expect } from "@microsoft/tui-test";

/**
 * Tests for cancellation behavior and post-cancel input handling.
 *
 * Bug: scrappy-z719 - Arrow keys don't work after agent cancel
 * Root cause: InputCaptureManager.cancel() doesn't reset _mode flag,
 * so is_capturing stays True and blocks history navigation.
 */

// Run tests sequentially to avoid resource contention
test.describe.configure({ mode: "serial" });

// Configure scrappy with no tracing
test.use({
  program: { file: "scrappy" },
  env: {
    LANGFUSE_PUBLIC_KEY: "",
    LANGFUSE_SECRET_KEY: "",
  },
});

test.describe("Cancellation and Arrow Keys", () => {
  test("arrow keys work for history after cancel during prompt", async ({
    terminal,
  }) => {
    // Wait for app to fully render
    await new Promise((r) => setTimeout(r, 8000));

    // Accept disclaimer if it appears
    const buffer = terminal.getViewableBuffer().join("\n");
    if (buffer.includes("NOTICE")) {
      terminal.submit("ok");
      await new Promise((r) => setTimeout(r, 5000));
    }

    // Skip if we're in wizard (no API keys configured)
    const currentBuffer = terminal.getViewableBuffer().join("\n");
    if (currentBuffer.includes("Provider Setup")) {
      test.skip();
      return;
    }

    // Type and submit a command to add to history
    terminal.submit("hello");
    await new Promise((r) => setTimeout(r, 2000));

    // If agent started (shows thinking indicator), cancel with escape
    terminal.keyEscape();
    await new Promise((r) => setTimeout(r, 1000));

    // Type another command
    terminal.submit("world");
    await new Promise((r) => setTimeout(r, 2000));

    // Cancel again if needed
    terminal.keyEscape();
    await new Promise((r) => setTimeout(r, 1000));

    // Now test arrow key history navigation
    // Up arrow should bring back "world" from history
    terminal.keyUp();
    await new Promise((r) => setTimeout(r, 500));

    // The input should now contain "world"
    await expect(terminal.getByText("world")).toBeVisible();

    // Up arrow again should bring back "hello"
    terminal.keyUp();
    await new Promise((r) => setTimeout(r, 500));

    await expect(terminal.getByText("hello")).toBeVisible();
  });

  test("escape key cancels and returns to idle state", async ({ terminal }) => {
    // Wait for app to fully render
    await new Promise((r) => setTimeout(r, 8000));

    // Accept disclaimer if it appears
    const buffer = terminal.getViewableBuffer().join("\n");
    if (buffer.includes("NOTICE")) {
      terminal.submit("ok");
      await new Promise((r) => setTimeout(r, 5000));
    }

    // Skip if in wizard
    const currentBuffer = terminal.getViewableBuffer().join("\n");
    if (currentBuffer.includes("Provider Setup")) {
      test.skip();
      return;
    }

    // Type a command to potentially start an agent
    terminal.submit("test");
    await new Promise((r) => setTimeout(r, 1000));

    // Press escape to cancel
    terminal.keyEscape();
    await new Promise((r) => setTimeout(r, 1000));

    // Should be able to type new input (not stuck)
    terminal.write("new input");
    await new Promise((r) => setTimeout(r, 500));

    await expect(terminal.getByText("new input")).toBeVisible();
  });

  test("ctrl+c double tap exits cleanly", async ({ terminal }) => {
    // Wait for app to start
    await new Promise((r) => setTimeout(r, 3000));

    // Double ctrl+c should exit
    terminal.keyCtrlC(2);

    // Give time for clean exit
    await new Promise((r) => setTimeout(r, 1000));
  });
});
