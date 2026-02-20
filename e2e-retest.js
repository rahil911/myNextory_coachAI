/**
 * E2E Re-Test — Focused on areas that had timing issues in first run
 * Tests: Content 360 detail click, Curator chat, Path tab, Agent Log tab
 * Also: Additional API tests with correct endpoints
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8002';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots', 'bowser-qa', 'new-features');
const USER_ID = 200;

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] ${msg}`);
}

async function screenshot(page, name, description) {
  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: false });
  log(`  Screenshot: ${name}.png — ${description}`);
}

// Helper: Navigate to tory workspace, search for user, select them, wait for load
async function selectUserInWorkspace(page) {
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2500);

  // Wait for user list to load
  await page.waitForSelector('.tw-person', { timeout: 10000 });

  // Search for user
  await page.fill('#tw-search', 'tsigler');
  await page.waitForTimeout(2000);

  // Wait for search results
  await page.waitForSelector('.tw-person', { timeout: 10000 });

  // Click on the user
  await page.click('.tw-person');
  await page.waitForTimeout(3000);
}

async function main() {
  log('Starting focused re-tests...\n');
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  // Capture console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text().substring(0, 200));
    }
  });

  // ─── TEST A: Content 360 — Lesson Detail + Slide Viewer ──────────────
  log('═══ RE-TEST A: Content 360 — Lesson Detail Click ═══');
  try {
    await page.goto(`${BASE}/#content-360`);
    await page.waitForTimeout(3000);

    // Wait for lesson cards
    await page.waitForSelector('.c360-card', { timeout: 10000 });
    const cardCount = await page.locator('.c360-card').count();
    log(`  Found ${cardCount} lesson cards`);

    // Scroll to make first card visible and click it
    const firstCard = page.locator('.c360-card').first();
    await firstCard.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await firstCard.click();
    await page.waitForTimeout(3000);

    await screenshot(page, 'A01_content360_detail_view', 'Content 360 lesson detail after click');

    // Check for detail panel
    const hasDetail = await page.isVisible('#c360-detail');
    log(`  Detail panel visible: ${hasDetail}`);

    // Check trait bars
    const traitCount = await page.locator('.c360-trait-row').count();
    log(`  Trait rows: ${traitCount}`);

    if (traitCount > 0) {
      await screenshot(page, 'A02_content360_trait_mapping', 'EPP trait mapping bars');
    }

    // Check coaching prompts
    const promptCount = await page.locator('.c360-prompt-card').count();
    log(`  Coaching prompts: ${promptCount}`);
    if (promptCount > 0) {
      // Expand first prompt
      await page.locator('.c360-prompt-card').first().click();
      await page.waitForTimeout(500);
      await screenshot(page, 'A03_content360_coaching_prompt', 'Expanded coaching prompt');
    }

    // Check slide analysis
    const timelineItems = await page.locator('.c360-timeline-item').count();
    log(`  Timeline items: ${timelineItems}`);
    if (timelineItems > 0) {
      await screenshot(page, 'A04_content360_slide_timeline', 'Slide analysis timeline');
    }

    // Check key concepts
    const concepts = await page.locator('.c360-concept-pills .c360-pill').count();
    log(`  Key concepts: ${concepts}`);

    // Check quality stars
    const hasQuality = await page.isVisible('.c360-card-quality');
    log(`  Quality rating visible: ${hasQuality}`);

    // Check for related lessons
    const pairs = await page.locator('.c360-pair-card').count();
    log(`  Related lessons: ${pairs}`);

    // Scroll down to see slide grid
    const hasSlideGrid = await page.isVisible('.c360-slides-grid');
    if (hasSlideGrid) {
      await page.locator('.c360-slides-grid').scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await screenshot(page, 'A05_content360_slides_grid', 'Slide grid with type chips');
    }

    // Try clicking a second lesson to verify navigation works
    const cards = page.locator('.c360-card');
    if (await cards.count() > 1) {
      await cards.nth(1).scrollIntoViewIfNeeded();
      await cards.nth(1).click();
      await page.waitForTimeout(2000);
      await screenshot(page, 'A06_content360_second_lesson', 'Second lesson detail view');
    }

    // Check for "no AI" banner on basic lessons
    const hasNoAi = await page.isVisible('.c360-no-ai-banner');
    log(`  "No AI metadata" banner: ${hasNoAi}`);

  } catch (e) {
    log(`  ERROR: ${e.message.split('\n')[0]}`);
    await screenshot(page, 'A_error', 'Content 360 re-test error');
  }

  // ─── TEST B: Curator AI Chat — with correct selectors ─────────────────
  log('\n═══ RE-TEST B: Curator AI Chat — Focused Test ═══');
  try {
    await selectUserInWorkspace(page);

    // The right panel should already show the curator
    await screenshot(page, 'B01_curator_workspace_loaded', 'Workspace with user selected for curator');

    // Check if curator panel is expanded (right side)
    const curatorToggle = await page.isVisible('#tw-toggle-right');
    log(`  Curator toggle button visible: ${curatorToggle}`);

    // Check if chat textarea is available
    const chatVisible = await page.isVisible('#tw-chat-textarea');
    log(`  Chat textarea initially visible: ${chatVisible}`);

    if (!chatVisible) {
      // May need to expand the right panel
      try {
        await page.click('#tw-toggle-right');
        await page.waitForTimeout(1000);
      } catch (e) {
        log(`  Toggle click failed: ${e.message.split('\n')[0]}`);
      }
    }

    // Wait for chat input to appear
    await page.waitForTimeout(2000);
    await screenshot(page, 'B02_curator_panel_state', 'Curator panel state after user selection');

    // Check for briefing with loading state
    const hasBriefing = await page.isVisible('#tw-curator-briefing');
    log(`  Curator briefing visible: ${hasBriefing}`);

    // Try typing in chat
    const hasChatTextarea = await page.isVisible('#tw-chat-textarea');
    log(`  Chat textarea available: ${hasChatTextarea}`);

    if (hasChatTextarea) {
      await page.fill('#tw-chat-textarea', 'What are Patricia\'s key personality traits?');
      await screenshot(page, 'B03_curator_message_typed', 'Message typed in curator chat');

      await page.click('#tw-chat-send');
      log('  Message sent to Curator AI...');

      // Wait for response (AI takes time)
      await page.waitForTimeout(15000);
      await screenshot(page, 'B04_curator_response', 'Curator AI response');

      // Check for messages in chat
      const chatMsgs = await page.locator('#tw-chat-messages > *').count();
      log(`  Chat messages: ${chatMsgs}`);
    }

    // Check session metadata
    const cost = await page.textContent('#tw-curator-cost').catch(() => 'N/A');
    const msgCount = await page.textContent('#tw-curator-msg-count').catch(() => 'N/A');
    const model = await page.textContent('#tw-curator-model-badge').catch(() => 'N/A');
    log(`  Model: ${model}, Cost: ${cost}, Msgs: ${msgCount}`);

    // Check voice button
    const hasVoiceBtn = await page.isVisible('#tw-curator-voice-btn');
    log(`  Voice button in curator: ${hasVoiceBtn}`);
    if (hasVoiceBtn) {
      await screenshot(page, 'B05_curator_voice_btn', 'Voice button in curator panel');
    }

  } catch (e) {
    log(`  ERROR: ${e.message.split('\n')[0]}`);
    await screenshot(page, 'B_error', 'Curator re-test error');
  }

  // ─── TEST C: Path Tab ─────────────────────────────────────────────────
  log('\n═══ RE-TEST C: Learning Path Tab ═══');
  try {
    // User should already be selected from test B
    // Click Path tab
    const pathTab = page.locator('button[data-tab="path"]');
    if (await pathTab.isVisible()) {
      await pathTab.click();
      await page.waitForTimeout(3000);
      await screenshot(page, 'C01_path_tab', 'Learning Path tab selected');

      // Check for path items
      const pathItems = await page.locator('.tw-path-item').count();
      log(`  Path items: ${pathItems}`);

      if (pathItems > 0) {
        await screenshot(page, 'C02_path_items', 'Path items list');

        // Check for lesson cards
        const pathCards = await page.locator('.tw-path-item-card').count();
        log(`  Path cards: ${pathCards}`);

        // Try expanding first item
        const toggleBtn = page.locator('.tw-lesson-toggle').first();
        if (await toggleBtn.isVisible()) {
          await toggleBtn.click();
          await page.waitForTimeout(1000);
          await screenshot(page, 'C03_path_expanded', 'Expanded path item with reasoning');
        }
      } else {
        log('  No path items — user may not have generated path');
        await screenshot(page, 'C01_path_empty', 'Empty path tab');
      }
    }
  } catch (e) {
    log(`  ERROR: ${e.message.split('\n')[0]}`);
    await screenshot(page, 'C_error', 'Path tab re-test error');
  }

  // ─── TEST D: Content Tab in Workspace ─────────────────────────────────
  log('\n═══ RE-TEST D: Content Tab in Workspace ═══');
  try {
    const contentTab = page.locator('button[data-tab="content"]');
    if (await contentTab.isVisible()) {
      await contentTab.click();
      await page.waitForTimeout(3000);
      await screenshot(page, 'D01_content_tab', 'Content tab in workspace');

      // Check for content library
      const hasContentLib = await page.isVisible('#tw-content-library');
      log(`  Content library visible: ${hasContentLib}`);
    }
  } catch (e) {
    log(`  ERROR: ${e.message.split('\n')[0]}`);
  }

  // ─── TEST E: Agent Log Tab & Session History ──────────────────────────
  log('\n═══ RE-TEST E: Agent Log Tab ═══');
  try {
    const agentLogTab = page.locator('button[data-tab="agentlog"]');
    if (await agentLogTab.isVisible()) {
      await agentLogTab.click();
      await page.waitForTimeout(3000);
      await screenshot(page, 'E01_agent_log_tab', 'Agent Log tab');

      // Check for session list
      const sessions = await page.locator('.tw-session-item, .session-item, [class*="session"]').count();
      log(`  Session items: ${sessions}`);
    }

    // Also check the Agent Log in the curator panel
    const agentCuratorTab = page.locator('#tw-curator-tab-agent');
    if (await agentCuratorTab.isVisible()) {
      await agentCuratorTab.click();
      await page.waitForTimeout(2000);
      await screenshot(page, 'E02_agent_panel', 'Agent panel (right side)');

      const hasAgentMsgs = await page.isVisible('#tw-agent-messages');
      log(`  Agent messages container: ${hasAgentMsgs}`);
    }
  } catch (e) {
    log(`  ERROR: ${e.message.split('\n')[0]}`);
  }

  // ─── TEST F: Additional API Tests ─────────────────────────────────────
  log('\n═══ RE-TEST F: Additional API Tests ═══');
  const { execSync } = require('child_process');

  const apis = [
    { method: 'GET', path: '/api/tory/content-360', name: 'Content 360 (correct path)' },
    { method: 'GET', path: '/api/tory/curator/session/200', name: 'Curator Session' },
    { method: 'GET', path: '/api/tory/curator/briefing/200', name: 'Curator Briefing', timeout: 90 },
    { method: 'GET', path: '/api/tory/instantiate/200/status', name: 'Instantiation Status' },
    { method: 'GET', path: '/api/tory/sessions/200', name: 'AI Sessions List' },
    { method: 'GET', path: '/api/companion/greeting/200', name: 'Companion Greeting' },
    { method: 'GET', path: '/api/companion/session/200', name: 'Companion Session' },
    { method: 'GET', path: '/api/companion/actions/200', name: 'Companion Actions' },
    { method: 'GET', path: '/api/tory/path/200/reasoning/1', name: 'Lesson Reasoning' },
    { method: 'GET', path: '/api/tory/review/stats', name: 'Review Queue Stats' },
  ];

  for (const ep of apis) {
    try {
      const timeoutSec = ep.timeout || 15;
      const cmd = `curl -s -o /tmp/api_test_resp.json -w "%{http_code}" -X ${ep.method} "${BASE}${ep.path}" --max-time ${timeoutSec}`;
      const status = execSync(cmd, { encoding: 'utf-8', timeout: (timeoutSec + 5) * 1000 }).trim();
      const ok = parseInt(status) >= 200 && parseInt(status) < 400;
      log(`  ${ok ? 'PASS' : 'FAIL'}: ${ep.method} ${ep.path} → ${status} (${ep.name})`);

      // For interesting endpoints, log response preview
      if (ok && ['Curator Briefing', 'Companion Greeting', 'Review Queue Stats'].includes(ep.name)) {
        try {
          const resp = fs.readFileSync('/tmp/api_test_resp.json', 'utf-8');
          const parsed = JSON.parse(resp);
          const preview = JSON.stringify(parsed).substring(0, 200);
          log(`    Response: ${preview}`);
        } catch (e) { /* ignore */ }
      }
    } catch (e) {
      log(`  FAIL: ${ep.method} ${ep.path} — ${e.message.split('\n')[0]}`);
    }
  }

  // Test Curator Chat API with correct endpoint
  log('\n  Testing Curator Chat API (correct endpoint)...');
  try {
    const cmd = `curl -s -X POST "${BASE}/api/tory/curator/chat" -H "Content-Type: application/json" -d '{"user_id":200,"message":"What are this learner strengths?"}' --max-time 90`;
    const response = execSync(cmd, { encoding: 'utf-8', timeout: 100000 }).trim();
    const parsed = JSON.parse(response);
    log(`  Curator Chat response keys: ${Object.keys(parsed).join(', ')}`);
    if (parsed.response) {
      log(`  PASS: Curator Chat — ${parsed.response.substring(0, 200)}`);
    } else if (parsed.content) {
      log(`  PASS: Curator Chat — ${parsed.content.substring(0, 200)}`);
    } else {
      log(`  Response: ${JSON.stringify(parsed).substring(0, 200)}`);
    }
  } catch (e) {
    log(`  WARN: Curator Chat — ${e.message.split('\n')[0]}`);
  }

  await browser.close();

  log('\n═══ Console Errors ═══');
  consoleErrors.forEach(e => log(`  ${e}`));
  log(`\n  Total console errors: ${consoleErrors.length}`);
  log('\nRe-test complete.');
}

main().catch(e => {
  console.error('Re-test crashed:', e);
  process.exit(2);
});
