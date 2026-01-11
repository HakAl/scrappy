//# hash=edbe9279c41206b2039d0e0992e810c3
//# sourceMappingURL=tui-test.config.js.map

import { defineConfig } from "@microsoft/tui-test";
export default defineConfig({
    retries: 1,
    timeout: 30000,
    trace: "on-first-retry"
});
