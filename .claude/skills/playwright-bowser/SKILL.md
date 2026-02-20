---
name: playwright-bowser
description: |
  Headless browser automation for the Baap Command Center using Playwright CLI.
  Capture screenshots, generate test code, validate UI state, and detect console errors.
  Default target: http://localhost:8002 (Command Center dashboard).

  Triggers: "take screenshot", "capture page", "browser test", "ui validation",
  "screenshot dashboard", "check the UI", "open browser", "codegen".
metadata:
  baap:
    requires:
      bins: [npx, playwright]
    defaults:
      url: http://localhost:8002
      screenshots_dir: ./screenshots/bowser-qa/
      viewport: "1440,900"
      browser: chromium
---

# Playwright Bowser — Headless Browser Skill for Baap

Provides headless Chromium browser control via the Playwright CLI (`npx playwright`).
Used by `bowser-qa-agent` for UI validation against goal-state user stories.

## Defaults

| Setting | Value |
|---------|-------|
| Base URL | `http://localhost:8002` |
| Screenshots dir | `./screenshots/bowser-qa/` |
| Viewport | 1440x900 |
| Browser | Chromium (headless) |
| Timeout | 30000ms |

## Core Commands

### Screenshot — Capture a page

```bash
# Basic screenshot (full viewport)
npx playwright screenshot http://localhost:8002 ./screenshots/bowser-qa/dashboard.png

# Full-page screenshot (entire scrollable area)
npx playwright screenshot --full-page http://localhost:8002 ./screenshots/bowser-qa/dashboard-full.png

# Wait for a specific element before capturing
npx playwright screenshot --wait-for-selector ".agent-card" http://localhost:8002 ./screenshots/bowser-qa/agents-loaded.png

# Wait for a timeout (ms) before capturing
npx playwright screenshot --wait-for-timeout 3000 http://localhost:8002 ./screenshots/bowser-qa/after-load.png

# Dark mode
npx playwright screenshot --color-scheme dark http://localhost:8002 ./screenshots/bowser-qa/dark-mode.png

# Custom viewport (use with open, not screenshot — screenshot uses default viewport)
# For custom viewport screenshots, use the Node.js API (see Programmatic section)
```

### Open — Interactive browser session

```bash
# Open dashboard in headed Chromium (for debugging)
npx playwright open http://localhost:8002

# Open with custom viewport
npx playwright open --viewport-size "1440,900" http://localhost:8002

# Open and save session storage for reuse
npx playwright open --save-storage auth.json http://localhost:8002

# Open with saved session (skip login)
npx playwright open --load-storage auth.json http://localhost:8002
```

### Codegen — Generate test code from user actions

```bash
# Record interactions and generate Playwright test code
npx playwright codegen http://localhost:8002

# Generate Python test code instead
npx playwright codegen --target python http://localhost:8002

# Save generated code to file
npx playwright codegen -o ./tests/generated-test.spec.js http://localhost:8002

# Use data-testid attribute for selectors
npx playwright codegen --test-id-attribute data-testid http://localhost:8002
```

### PDF — Save page as PDF

```bash
# Save dashboard as PDF (Chromium only)
npx playwright pdf http://localhost:8002 ./screenshots/bowser-qa/dashboard.pdf

# Specific paper format
npx playwright pdf --paper-format A4 http://localhost:8002 ./screenshots/bowser-qa/dashboard-a4.pdf

# Wait for content before PDF
npx playwright pdf --wait-for-selector ".dashboard-loaded" http://localhost:8002 ./screenshots/bowser-qa/report.pdf
```

## Session Naming Convention

Name screenshots and artifacts using the bead ID:

```
screenshots/bowser-qa/{date}_{bead-id}_{description}.png
```

Examples:
```
screenshots/bowser-qa/2026-02-19_baap-8rg_dashboard-overview.png
screenshots/bowser-qa/2026-02-19_baap-8rg_agent-cards-loaded.png
screenshots/bowser-qa/2026-02-19_baap-8rg_epic-progress.png
```

## Programmatic Control (Node.js API)

For advanced scenarios beyond the CLI (custom viewport, multiple actions, console capture):

```bash
# Inline Node.js script for custom viewport screenshot
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto('http://localhost:8002');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: './screenshots/bowser-qa/custom.png', fullPage: true });
  await browser.close();
})();
"
```

### Console Error Capture

```bash
# Capture console errors during page load
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto('http://localhost:8002');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: './screenshots/bowser-qa/with-errors.png' });
  if (errors.length > 0) {
    console.error('CONSOLE ERRORS:', JSON.stringify(errors, null, 2));
    process.exit(1);
  }
  console.log('No console errors detected.');
  await browser.close();
})();
"
```

### Network Failure Capture

```bash
# Capture failed network requests
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const failures = [];
  page.on('requestfailed', req => failures.push({ url: req.url(), error: req.failure().errorText }));
  await page.goto('http://localhost:8002');
  await page.waitForLoadState('networkidle');
  if (failures.length > 0) {
    console.error('NETWORK FAILURES:', JSON.stringify(failures, null, 2));
    process.exit(1);
  }
  console.log('No network failures detected.');
  await browser.close();
})();
"
```

## Element Selection Strategies

In order of preference for Baap Command Center:

| Strategy | Selector | When to Use |
|----------|----------|-------------|
| Test ID | `[data-testid="agent-card"]` | Best — explicit, stable |
| Role | `role=heading[name="Agents"]` | ARIA roles — accessible |
| Text | `text=Active Agents` | Visible text — readable |
| CSS | `.agent-card .status-badge` | Class-based — fragile |
| XPath | `//div[@class="agent-card"]` | Last resort — brittle |

## Wait Strategies

| Strategy | CLI Flag / API | When to Use |
|----------|---------------|-------------|
| Selector visible | `--wait-for-selector ".loaded"` | Wait for specific element |
| Timeout | `--wait-for-timeout 3000` | Fixed delay (avoid if possible) |
| Network idle | `waitForLoadState('networkidle')` | API-only — all requests done |
| DOM content loaded | `waitForLoadState('domcontentloaded')` | API-only — DOM parsed |

## HAR Recording

Capture all network activity for debugging:

```bash
# Screenshot with HAR capture
npx playwright screenshot --save-har ./screenshots/bowser-qa/network.har http://localhost:8002 ./screenshots/bowser-qa/with-har.png

# Filter HAR to API calls only
npx playwright screenshot --save-har ./screenshots/bowser-qa/api.har --save-har-glob "**/api/**" http://localhost:8002 ./screenshots/bowser-qa/api-check.png
```

## Common Patterns for Baap QA

### Validate Dashboard Loads

```bash
npx playwright screenshot \
  --wait-for-selector ".dashboard-container" \
  --wait-for-timeout 2000 \
  http://localhost:8002 \
  ./screenshots/bowser-qa/$(date +%Y-%m-%d)_dashboard-loaded.png
```

### Validate Specific Route

```bash
# Agent detail page
npx playwright screenshot \
  --wait-for-selector ".agent-detail" \
  http://localhost:8002/agents/platform-agent \
  ./screenshots/bowser-qa/$(date +%Y-%m-%d)_agent-detail.png

# Beads list
npx playwright screenshot \
  --wait-for-selector ".bead-list" \
  http://localhost:8002/beads \
  ./screenshots/bowser-qa/$(date +%Y-%m-%d)_beads-list.png
```

### Full QA Suite (screenshot all key pages)

```bash
PAGES=("/" "/agents" "/beads" "/epics" "/timeline")
DATE=$(date +%Y-%m-%d)
for page in "${PAGES[@]}"; do
  slug=$(echo "$page" | tr '/' '-' | sed 's/^-/home/')
  npx playwright screenshot \
    --wait-for-timeout 2000 \
    "http://localhost:8002${page}" \
    "./screenshots/bowser-qa/${DATE}_${slug}.png"
done
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Browser not installed" | `npx playwright install chromium` |
| Blank screenshot | Add `--wait-for-timeout 3000` or `--wait-for-selector` |
| Viewport too small | Use Node.js API with explicit viewport |
| SSL errors | Add `--ignore-https-errors` |
| Need auth state | Use `--save-storage` / `--load-storage` |
| Timeout errors | Increase `--timeout 60000` |
