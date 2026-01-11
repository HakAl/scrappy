import { defineConfig } from "@microsoft/tui-test";

export default defineConfig({
  retries: 1,
  timeout: 30000,
  trace: "on-first-retry",
});
