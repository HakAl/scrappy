import { test, expect } from "@microsoft/tui-test";

/**
 * Tests for escape key cancellation behavior.
 *
 * Bug: scrappy-kzqy - Need to press escape multiple times to cancel agent
 *
 * Root causes investigated:
 * 1. InputCaptureManager.cancel() didn't reset is_capturing (FIXED in scrappy-z719)
 * 2. Sync LLM calls are blocking - no cancellation check during call
 *
 * This test verifies that a single escape press is sufficient to cancel,
 * and that the UI responds appropriately.
 */

// Serial mode - tests run one at a time

test.use({
  program: { file: "scrappy" },
  env: {
    LANGFUSE_PUBLIC_KEY: "",
    LANGFUSE_SECRET_KEY: "",
  },
});

test.describe("Escape Key Cancellation", () => {
  test("single escape cancels and returns to idle state", async ({
    terminal,
  }) => {
    // Wait for app to start
    await new Promise((r) => setTimeout(r, 8000));

    // Handle disclaimer
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

    // Submit a query that will start the agent
    terminal.submit("what is 2+2");

    // Wait a moment for agent to start
    await new Promise((r) => setTimeout(r, 1000));

    // Press escape ONCE to cancel
    terminal.keyEscape();

    // Wait for cancellation to take effect
    await new Promise((r) => setTimeout(r, 2000));

    // Should be able to type new input (not stuck)
    terminal.write("new query");
    await new Promise((r) => setTimeout(r, 500));

    // The text we typed should be visible
    await expect(terminal.getByText("new query")).toBeVisible();

    // Clean up with double ctrl+c
    terminal.keyCtrlC(2);
  });

  test("escape during activity indicator shows idle after cancel", async ({
    terminal,
  }) => {
    // Wait for app
    await new Promise((r) => setTimeout(r, 8000));

    // Handle disclaimer
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

    // Start agent
    terminal.submit("hello");
    await new Promise((r) => setTimeout(r, 1500));

    // Cancel
    terminal.keyEscape();
    await new Promise((r) => setTimeout(r, 1500));

    // After cancel, the activity indicator should be hidden
    // and input should be ready for new commands
    // We verify by typing - if stuck, this won't appear
    terminal.write("test after cancel");
    await new Promise((r) => setTimeout(r, 500));

    await expect(terminal.getByText("test after cancel")).toBeVisible();

    // Clean up
    terminal.keyCtrlC(2);
  });

  test("escape works during capture mode prompt", async ({ terminal }) => {
    // This test verifies the InputCaptureManager.cancel() fix (scrappy-z719)
    // When in capture mode, escape should cancel and reset state

    // Wait for app
    await new Promise((r) => setTimeout(r, 8000));

    // Handle disclaimer
    const buffer = terminal.getViewableBuffer().join("\n");
    if (buffer.includes("NOTICE")) {
      terminal.submit("ok");
      await new Promise((r) => setTimeout(r, 5000));
    }

    // Skip if in wizard - we need main screen
    const currentBuffer = terminal.getViewableBuffer().join("\n");
    if (currentBuffer.includes("Provider Setup")) {
      test.skip();
      return;
    }

    // Try to trigger a prompt that enters capture mode
    // (This depends on having an API key configured for the agent to run)
    terminal.submit("create a file test.txt");
    await new Promise((r) => setTimeout(r, 2000));

    // If we got a confirmation prompt, escape should cancel it
    // If agent isn't running (no API key), escape should still work
    terminal.keyEscape();
    await new Promise((r) => setTimeout(r, 1000));

    // Verify we can type (not stuck in capture mode)
    terminal.write("after escape");
    await new Promise((r) => setTimeout(r, 500));

    await expect(terminal.getByText("after escape")).toBeVisible();

    // Clean up
    terminal.keyCtrlC(2);
  });
});
