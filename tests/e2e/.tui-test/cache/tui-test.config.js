//# hash=53dc099c95b2639270828ba0615a638a
//# sourceMappingURL=tui-test.config.js.map

import { defineConfig } from "@microsoft/tui-test";
export default defineConfig({
    retries: 1,
    timeout: 30000,
    trace: "on-first-retry",
    program: {
        file: "scrappy"
    }
});
