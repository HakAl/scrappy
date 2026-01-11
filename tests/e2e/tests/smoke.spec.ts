import { test } from "@microsoft/tui-test";

// Run scrappy with no tracing
test.use({
  program: { file: "scrappy" },
  env: {
    LANGFUSE_PUBLIC_KEY: "",
    LANGFUSE_SECRET_KEY: "",
  },
});

test.describe("Scrappy Smoke Tests", () => {
  test("app starts and exits with ctrl+c", async ({ terminal }) => {
    // Give app time to start
    await new Promise((r) => setTimeout(r, 3000));

    // Double ctrl+c should exit cleanly
    terminal.keyCtrlC(2);

    // Give time for clean exit
    await new Promise((r) => setTimeout(r, 1000));
  });
});
