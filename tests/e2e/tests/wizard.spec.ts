import { test, expect } from "@microsoft/tui-test";

// Run tests sequentially to avoid resource contention
// Serial mode - tests run one at a time

// Run scrappy - no API keys = wizard should appear
test.use({
  program: { file: "scrappy" },
  env: {
    LANGFUSE_PUBLIC_KEY: "",
    LANGFUSE_SECRET_KEY: "",
  },
});

test("wizard shows disclaimer on first run", async ({ terminal }) => {
  // Wait for app to fully render (8s for Docker startup time)
  await new Promise((r) => setTimeout(r, 8000));

  // Check for NOTICE in disclaimer
  await expect(terminal.getByText("NOTICE")).toBeVisible();
});

test("wizard accepts disclaimer and shows provider menu", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Verify disclaimer visible
  await expect(terminal.getByText("NOTICE")).toBeVisible();

  // Accept disclaimer - use submit with text (type + enter combined)
  terminal.submit("ok");

  // Wait for transition to provider menu
  await new Promise((r) => setTimeout(r, 5000));

  // Provider menu should appear
  await expect(terminal.getByText("Provider Setup")).toBeVisible();
});

test("wizard can quit with q", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Verify disclaimer
  await expect(terminal.getByText("NOTICE")).toBeVisible();

  // Accept disclaimer
  terminal.submit("ok");

  // Wait for transition to provider menu
  await new Promise((r) => setTimeout(r, 5000));

  // Verify provider menu
  await expect(terminal.getByText("Provider Setup")).toBeVisible();

  // Quit
  terminal.submit("q");

  // Wait for exit
  await new Promise((r) => setTimeout(r, 2000));
});

test("wizard shows invalid input message for gibberish", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Accept disclaimer
  terminal.submit("ok");
  await new Promise((r) => setTimeout(r, 5000));

  // Type invalid input at provider menu
  terminal.submit("xyz");
  await new Promise((r) => setTimeout(r, 1000));

  // Should show invalid selection message
  await expect(terminal.getByText("Invalid selection")).toBeVisible();
});

test("wizard shows provider config when selecting a provider", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Accept disclaimer
  terminal.submit("ok");
  await new Promise((r) => setTimeout(r, 5000));

  // Select first provider (Groq)
  terminal.submit("1");
  await new Promise((r) => setTimeout(r, 2000));

  // Should show configuring message and URL
  await expect(terminal.getByText("Configuring")).toBeVisible();
});

test("wizard cancels key input with q", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Accept disclaimer
  terminal.submit("ok");
  await new Promise((r) => setTimeout(r, 5000));

  // Select first provider
  terminal.submit("1");
  await new Promise((r) => setTimeout(r, 2000));

  // Cancel with q
  terminal.submit("q");
  await new Promise((r) => setTimeout(r, 2000));

  // Should show cancelled message and return to menu
  await expect(terminal.getByText("cancelled")).toBeVisible();
});

test("wizard rejects invalid API key format", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Accept disclaimer
  terminal.submit("ok");
  await new Promise((r) => setTimeout(r, 5000));

  // Select first provider
  terminal.submit("1");
  await new Promise((r) => setTimeout(r, 2000));

  // Enter invalid key (too short)
  terminal.submit("abc");
  await new Promise((r) => setTimeout(r, 2000));

  // Should show invalid key message
  await expect(terminal.getByText("Invalid key")).toBeVisible();
});

test("wizard disclaimer rejects invalid input", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Type something other than ok or q
  terminal.submit("hello");
  await new Promise((r) => setTimeout(r, 1000));

  // Should prompt to type ok or q
  await expect(terminal.getByText("type 'ok'")).toBeVisible();
});

test("wizard can quit from disclaimer with q", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Verify disclaimer visible
  await expect(terminal.getByText("NOTICE")).toBeVisible();

  // Quit directly from disclaimer
  terminal.submit("q");

  // Wait for exit
  await new Promise((r) => setTimeout(r, 2000));
});

test("wizard menu shows all providers", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Accept disclaimer
  terminal.submit("ok");
  await new Promise((r) => setTimeout(r, 5000));

  // Menu should show multiple providers
  await expect(terminal.getByText("Groq")).toBeVisible();
  await expect(terminal.getByText("Cerebras")).toBeVisible();
  await expect(terminal.getByText("Gemini")).toBeVisible();
});

test("wizard shows console URL when configuring provider", async ({ terminal }) => {
  // Wait for app to fully render
  await new Promise((r) => setTimeout(r, 8000));

  // Accept disclaimer
  terminal.submit("ok");
  await new Promise((r) => setTimeout(r, 5000));

  // Select first provider
  terminal.submit("1");
  await new Promise((r) => setTimeout(r, 2000));

  // Should show console URL for getting API key
  await expect(terminal.getByText("console.groq.com")).toBeVisible();
});
