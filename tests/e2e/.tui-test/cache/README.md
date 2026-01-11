# E2E Tests for Scrappy

End-to-end tests using [Microsoft tui-test](https://github.com/microsoft/tui-test).

## Prerequisites

- Node.js 16+ (for tui-test)
- Python 3.11+ (for scrappy)
- scrappy installed (`pip install -e .` from repo root)

## Local Setup

```bash
cd e2e
npm install
```

## Running Tests

### Local (requires scrappy in PATH)

```bash
cd e2e
npm test
```

### With Tracing (saves terminal replay)

```bash
npm run test:trace
```

Traces are saved to `e2e/tui-traces/` and can be viewed with:

```bash
npx tui-test show-trace tui-traces/<trace-file>
```

### Docker

Run from repo root (not e2e/):

```bash
# Using docker compose
docker compose -f e2e/docker-compose.yml up --build

# Or using docker directly
docker build -f e2e/Dockerfile -t scrappy-e2e .
docker run --rm scrappy-e2e
```

## Test Files

- `tests/smoke.spec.ts` - Basic smoke tests (start, exit)

## Configuration

- `tui-test.config.ts` - Test runner configuration
- `package.json` - Node.js dependencies

## Writing Tests

```typescript
import { test, expect } from "@microsoft/tui-test";

test("example", async ({ terminal }) => {
  // Wait for text to appear
  await expect(terminal.getByText("some text")).toBeVisible();

  // Type input
  terminal.write("hello");

  // Submit (press enter)
  terminal.submit();

  // Press special keys
  terminal.keyEscape();       // Escape
  terminal.keyCtrlC();        // Ctrl+C
  terminal.keyCtrlC(2);       // Double Ctrl+C
  terminal.keyUp();           // Arrow up
  terminal.keyDown();         // Arrow down
  terminal.keyBackspace();    // Backspace

  // Snapshot testing
  await expect(terminal).toMatchSnapshot();
});
```

```
  Assertions

  Locator assertions (on terminal.getByText()):
  - toBeVisible({ timeout? }) - Text appears on screen
  - toHaveFgColor(color, { timeout? }) - Foreground color check
  - toHaveBgColor(color, { timeout? }) - Background color check

  Color formats: ANSI 256 (255), hex ("#FFFFFF"), or RGB ([255, 255, 255])

  Terminal assertions:
  - toMatchSnapshot({ includeColors? }) - Snapshot entire terminal state

  Terminal Actions

  // Input
  terminal.write("text");        // Type without enter
  terminal.submit("text");       // Type + enter
  terminal.submit();             // Just enter

  // Navigation
  terminal.keyUp(count?);
  terminal.keyDown(count?);
  terminal.keyLeft(count?);
  terminal.keyRight(count?);

  // Control
  terminal.keyEscape(count?);
  terminal.keyCtrlC(count?);
  terminal.keyCtrlD(count?);
  terminal.keyBackspace(count?);
  terminal.keyDelete(count?);

  // Terminal state
  terminal.resize(cols, rows);
  terminal.getBuffer();          // Full buffer as string[][]
  terminal.getViewableBuffer();  // Visible portion
  terminal.getCursor();          // { x, y, baseY }

  Test Types We Could Write

  1. UI state tests - Verify prompts, messages, status appear
  2. Navigation tests - Arrow keys work in menus/history
  3. Input handling - Commands processed correctly
  4. Color/styling tests - Error messages are red, etc.
  5. Snapshot tests - Catch UI regressions
  6. Interrupt handling - Ctrl+C behavior in different states
```

## CI Integration

Add to GitHub Actions:

```yaml
e2e-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - run: pip install -e .
    - run: cd e2e && npm install
    - run: cd e2e && npm test
```
