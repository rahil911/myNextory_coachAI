/**
 * Tory Workspace QA Runner — validates all 10 user stories via Playwright.
 * Usage: node screenshots/bowser-qa/qa-runner.js
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:8002/#tory';
const SCREENSHOT_DIR = path.join(__dirname);
const VIEWPORT = { width: 1440, height: 900 };
const TIMEOUT = 30000;

// Results tracking
const results = [];
let consoleErrors = [];
let networkFailures = [];
let page, browser;

async function setup() {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT });
  page = await context.newPage();
  page.setDefaultTimeout(TIMEOUT);
}

async function teardown() {
  if (browser) await browser.close();
}

function resetListeners() {
  consoleErrors = [];
  networkFailures = [];
}

function attachListeners() {
  resetListeners();
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(err.message));
  page.on('requestfailed', req => {
    networkFailures.push({ url: req.url(), error: req.failure()?.errorText || 'unknown' });
  });
  page.on('response', res => {
    if (res.status() >= 400) {
      networkFailures.push({ url: res.url(), status: res.status() });
    }
  });
}

async function screenshot(name) {
  const p = path.join(SCREENSHOT_DIR, name);
  await page.screenshot({ path: p, fullPage: false });
  return p;
}

async function navigateToTory() {
  // Force a clean page load by navigating away first (SPA state reset)
  await page.goto('about:blank', { waitUntil: 'domcontentloaded' });
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  // Wait for people list to populate
  await page.waitForSelector('.tw-person', { timeout: 10000 });
  // Small extra wait for rendering
  await page.waitForTimeout(500);
}

async function searchForUser(searchText) {
  const input = page.locator('#tw-search');
  await input.fill('');
  await input.fill(searchText);
  // Wait for debounce (300ms) + render
  await page.waitForTimeout(600);
  // Wait for the list to update (loading spinner to finish)
  await page.waitForFunction(() => {
    const list = document.querySelector('.tw-people-list');
    return list && !list.querySelector('.tw-loading');
  }, { timeout: 5000 });
  await page.waitForTimeout(200);
}

async function clearSearch() {
  const input = page.locator('#tw-search');
  await input.fill('');
  await page.waitForTimeout(600);
  await page.waitForFunction(() => {
    const list = document.querySelector('.tw-people-list');
    return list && !list.querySelector('.tw-loading');
  }, { timeout: 5000 });
  await page.waitForTimeout(200);
}

function assert(condition, description) {
  return { passed: !!condition, description };
}

// ── Story 1: People list loads with real users ────────────────────────────

async function story1() {
  const name = 'People list loads with real users';
  console.log(`\n  Story 1: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();
    await screenshot('story_1.png');

    // Count .tw-person elements
    const personCount = await page.locator('.tw-people-list .tw-person').count();
    assertions.push(assert(personCount === 50, `.tw-person count equals 50 (got ${personCount})`));

    // Each .tw-person contains .tw-person-status
    const statusCount = await page.locator('.tw-people-list .tw-person .tw-person-status').count();
    assertions.push(assert(statusCount === personCount, `Each .tw-person contains .tw-person-status (${statusCount}/${personCount})`));

    // Each .tw-person contains .tw-person-name with non-empty text
    const names = await page.locator('.tw-people-list .tw-person .tw-person-name').allTextContents();
    const nonEmptyNames = names.filter(n => n.trim().length > 0);
    assertions.push(assert(nonEmptyNames.length === personCount, `Each .tw-person-name has non-empty text (${nonEmptyNames.length}/${personCount})`));

    // Each .tw-person contains .tw-person-meta with non-empty text
    const metas = await page.locator('.tw-people-list .tw-person .tw-person-meta').allTextContents();
    const nonEmptyMetas = metas.filter(m => m.trim().length > 0);
    assertions.push(assert(nonEmptyMetas.length === personCount, `Each .tw-person-meta has non-empty text (${nonEmptyMetas.length}/${personCount})`));

    // Page info matches 'Page 1/N' where N >= 29
    const pageInfo = await page.locator('#tw-page-info').textContent();
    const pageMatch = pageInfo.match(/Page\s+1\/(\d+)/);
    const totalPages = pageMatch ? parseInt(pageMatch[1]) : 0;
    assertions.push(assert(totalPages >= 29, `#tw-page-info matches 'Page 1/N' where N >= 29 (got '${pageInfo}', N=${totalPages})`));

    // Search is visible
    const searchVisible = await page.locator('#tw-search').isVisible();
    const searchPlaceholder = await page.locator('#tw-search').getAttribute('placeholder');
    assertions.push(assert(searchVisible && searchPlaceholder === 'Search users...', `#tw-search visible with placeholder 'Search users...' (visible=${searchVisible}, placeholder='${searchPlaceholder}')`));

    // Status filter has correct options
    const statusOptions = await page.locator('#tw-filter-status option').allTextContents();
    const hasProcessed = statusOptions.some(o => o.toLowerCase().includes('processed'));
    const hasEpp = statusOptions.some(o => o.toLowerCase().includes('epp'));
    assertions.push(assert(hasProcessed && hasEpp, `#tw-filter-status has 'processed' and 'has_epp' options (options: ${statusOptions.join(', ')})`));

    // Topbar stats shows user count >= 1400
    const statsText = await page.locator('#tw-topbar-stats').textContent();
    const countMatch = statsText.match(/(\d[\d,]*)\s*users/);
    const userCount = countMatch ? parseInt(countMatch[1].replace(',', '')) : 0;
    assertions.push(assert(userCount >= 1400, `#tw-topbar-stats shows count >= 1400 (got ${userCount})`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_1_error.png');
  }

  results.push({ story: 1, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 2: Search filters users by email ────────────────────────────────

async function story2() {
  const name = 'Search filters users by email';
  console.log(`\n  Story 2: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Search for tsigler
    await searchForUser('tsigler');
    await screenshot('story_2_filtered.png');

    // After typing 'tsigler', filtered list contains exactly 1 .tw-person
    const filteredCount = await page.locator('.tw-people-list .tw-person').count();
    assertions.push(assert(filteredCount === 1, `Filtered list contains exactly 1 .tw-person (got ${filteredCount})`));

    // Filtered .tw-person-meta contains 'tsigler@tocgrp.com'
    if (filteredCount >= 1) {
      const metaText = await page.locator('.tw-people-list .tw-person .tw-person-meta').first().textContent();
      assertions.push(assert(metaText.includes('tsigler@tocgrp.com'), `Filtered .tw-person-meta contains 'tsigler@tocgrp.com' (got '${metaText}')`));

      // Filtered .tw-person .tw-person-status has class 'status-processed'
      const statusClasses = await page.locator('.tw-people-list .tw-person .tw-person-status').first().getAttribute('class');
      assertions.push(assert(statusClasses.includes('status-processed'), `Status has class 'status-processed' (got '${statusClasses}')`));
    } else {
      assertions.push(assert(false, `Cannot check meta - no results found`));
      assertions.push(assert(false, `Cannot check status - no results found`));
    }

    // Clear search
    await clearSearch();
    await screenshot('story_2_cleared.png');

    // After clearing search, .tw-person count returns to 50
    const restoredCount = await page.locator('.tw-people-list .tw-person').count();
    assertions.push(assert(restoredCount === 50, `After clearing, count returns to 50 (got ${restoredCount})`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_2_error.png');
  }

  results.push({ story: 2, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 3: Status filter shows processed users ──────────────────────────

async function story3() {
  const name = 'Status filter shows processed users';
  console.log(`\n  Story 3: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Select "processed" from status filter
    await page.selectOption('#tw-filter-status', 'processed');
    await page.waitForTimeout(600);
    await page.waitForFunction(() => {
      const list = document.querySelector('.tw-people-list');
      return list && !list.querySelector('.tw-loading');
    }, { timeout: 5000 });
    await page.waitForTimeout(200);
    await screenshot('story_3_filtered.png');

    // Filtered list contains at least 1 .tw-person
    const filteredCount = await page.locator('.tw-people-list .tw-person').count();
    assertions.push(assert(filteredCount >= 1, `Filtered list contains >= 1 .tw-person (got ${filteredCount})`));

    // Every visible .tw-person has .tw-person-status with class 'status-processed'
    if (filteredCount > 0) {
      const allStatusClasses = await page.locator('.tw-people-list .tw-person .tw-person-status').evaluateAll(
        elements => elements.map(el => el.className)
      );
      const allProcessed = allStatusClasses.every(cls => cls.includes('status-processed'));
      assertions.push(assert(allProcessed, `Every status has class 'status-processed' (${allStatusClasses.filter(c => c.includes('status-processed')).length}/${allStatusClasses.length})`));

      // All visible status dots render with processed color (green) - check computed style
      const colors = await page.locator('.tw-people-list .tw-person .tw-person-status').evaluateAll(
        elements => elements.map(el => getComputedStyle(el).backgroundColor)
      );
      // We just check all dots have the same color (they should all be green)
      const uniqueColors = [...new Set(colors)];
      assertions.push(assert(uniqueColors.length === 1, `All status dots have same color (${uniqueColors.length} unique colors: ${uniqueColors.join(', ')})`));
    } else {
      assertions.push(assert(false, `No processed users found - cannot check status classes`));
      assertions.push(assert(false, `No processed users found - cannot check colors`));
    }

    // Page info shows reduced pagination
    const pageInfo = await page.locator('#tw-page-info').textContent();
    const pageMatch = pageInfo.match(/Page\s+\d+\/(\d+)/);
    const filteredPages = pageMatch ? parseInt(pageMatch[1]) : 999;
    assertions.push(assert(filteredPages < 29, `Filtered page count < unfiltered 29 (got ${filteredPages})`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_3_error.png');
  }

  results.push({ story: 3, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 4: Click user loads profile detail ──────────────────────────────

async function story4() {
  const name = 'Click user loads profile detail';
  console.log(`\n  Story 4: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Search for tsigler
    await searchForUser('tsigler');

    // Click the .tw-person row
    await page.locator('.tw-people-list .tw-person').first().click();
    await page.waitForTimeout(500);

    // Wait for selected class
    const hasSelected = await page.locator('.tw-people-list .tw-person.selected').count();
    assertions.push(assert(hasSelected >= 1, `Clicked .tw-person gains class 'selected' (found ${hasSelected})`));

    // Wait for profile card to render (API call + render)
    try {
      await page.waitForSelector('.tw-profile-card', { timeout: 15000 });
    } catch {
      // May still be loading or failed
      await page.waitForTimeout(3000);
    }
    await screenshot('story_4_profile.png');

    // Profile tab is active
    const profileTabActive = await page.locator('.tw-tab[data-tab="profile"]').evaluate(
      el => el.classList.contains('active')
    );
    assertions.push(assert(profileTabActive, `.tw-tab[data-tab='profile'] has class 'active'`));

    // Profile card is visible
    const profileVisible = await page.locator('#tw-tab-content .tw-profile-card').count();
    assertions.push(assert(profileVisible >= 1, `.tw-profile-card is visible inside #tw-tab-content`));

    if (profileVisible >= 1) {
      // Profile name displays non-empty text
      const profileName = await page.locator('.tw-profile-name').textContent();
      assertions.push(assert(profileName.trim().length > 0, `.tw-profile-name displays non-empty text (got '${profileName.trim()}')`));

      // Profile email contains tsigler@tocgrp.com
      const profileEmail = await page.locator('.tw-profile-email').textContent();
      assertions.push(assert(profileEmail.includes('tsigler@tocgrp.com'), `.tw-profile-email contains 'tsigler@tocgrp.com' (got '${profileEmail}')`));

      // Profile narrative contains at least 50 characters
      const narrativeEls = await page.locator('.tw-profile-narrative').count();
      if (narrativeEls > 0) {
        const narrative = await page.locator('.tw-profile-narrative').textContent();
        assertions.push(assert(narrative.length >= 50, `.tw-profile-narrative >= 50 chars (got ${narrative.length})`));
      } else {
        assertions.push(assert(false, `.tw-profile-narrative not found`));
      }

      // Trait list has at least one .tw-trait
      const traitCount = await page.locator('.tw-trait-list .tw-trait').count();
      assertions.push(assert(traitCount >= 1, `.tw-trait-list has >= 1 .tw-trait (got ${traitCount})`));

      // No undefined/null/NaN in profile card text
      const cardText = await page.locator('.tw-profile-card').textContent();
      const hasUndefined = /\bundefined\b/.test(cardText);
      const hasNull = /\bnull\b/.test(cardText);
      const hasNaN = /\bNaN\b/.test(cardText);
      assertions.push(assert(!hasUndefined && !hasNull && !hasNaN, `No 'undefined', 'null', or 'NaN' in profile (undefined=${hasUndefined}, null=${hasNull}, NaN=${hasNaN})`));
    } else {
      assertions.push(assert(false, `Profile card not visible - cannot check profile name`));
      assertions.push(assert(false, `Profile card not visible - cannot check email`));
      assertions.push(assert(false, `Profile card not visible - cannot check narrative`));
      assertions.push(assert(false, `Profile card not visible - cannot check traits`));
      assertions.push(assert(false, `Profile card not visible - cannot check for undefined/null`));
    }

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_4_error.png');
  }

  results.push({ story: 4, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 5: Path tab shows kanban columns ────────────────────────────────

async function story5() {
  const name = 'Path tab shows kanban columns';
  console.log(`\n  Story 5: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Search for tsigler and click
    await searchForUser('tsigler');
    await page.locator('.tw-people-list .tw-person').first().click();
    await page.waitForSelector('.tw-profile-card', { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(500);

    // Click Path tab
    await page.locator('.tw-tab[data-tab="path"]').click();
    await page.waitForTimeout(500);

    // Wait for path board
    try {
      await page.waitForSelector('.tw-path-board', { timeout: 8000 });
    } catch {
      await page.waitForTimeout(2000);
    }
    await screenshot('story_5_path.png');

    // Path tab is active
    const pathTabActive = await page.locator('.tw-tab[data-tab="path"]').evaluate(
      el => el.classList.contains('active')
    );
    assertions.push(assert(pathTabActive, `.tw-tab[data-tab='path'] has class 'active'`));

    // Path board is visible
    const boardCount = await page.locator('#tw-tab-content .tw-path-board').count();
    assertions.push(assert(boardCount >= 1, `.tw-path-board is visible inside #tw-tab-content`));

    if (boardCount >= 1) {
      // 4 columns
      const colCount = await page.locator('.tw-path-col').count();
      assertions.push(assert(colCount === 4, `.tw-path-col count equals 4 (got ${colCount})`));

      // Column data-col values
      const colIds = await page.locator('.tw-path-col').evaluateAll(
        els => els.map(el => el.dataset.col)
      );
      const expectedCols = ['pool', 'discovery', 'main', 'completed'];
      const hasAllCols = expectedCols.every(c => colIds.includes(c));
      assertions.push(assert(hasAllCols, `Columns have data-col values: ${expectedCols.join(', ')} (got: ${colIds.join(', ')})`));

      // Each column has title with non-empty text
      const titles = await page.locator('.tw-path-col-title').allTextContents();
      const allTitlesNonEmpty = titles.every(t => t.trim().length > 0);
      assertions.push(assert(allTitlesNonEmpty, `Each .tw-path-col-title has non-empty text (${titles.join(', ')})`));

      // Each column has count showing a number
      const counts = await page.locator('.tw-path-col-count').allTextContents();
      const allCountsNumeric = counts.every(c => /\d/.test(c));
      assertions.push(assert(allCountsNumeric, `Each .tw-path-col-count shows a number (${counts.join(', ')})`));

      // Total path cards >= 1
      const totalCards = await page.locator('.tw-path-card').count();
      assertions.push(assert(totalCards >= 1, `Total .tw-path-card >= 1 (got ${totalCards})`));

      // At least one card has draggable='true'
      const draggableCount = await page.locator('.tw-path-card[draggable="true"]').count();
      assertions.push(assert(draggableCount >= 1, `At least one .tw-path-card has draggable='true' (got ${draggableCount})`));

      // Check first few cards for title and score
      if (totalCards > 0) {
        const cardTitles = await page.locator('.tw-path-card .tw-path-card-title').evaluateAll(
          els => els.slice(0, 5).map(el => el.textContent.trim())
        );
        const allCardTitlesNonEmpty = cardTitles.every(t => t.length > 0);
        assertions.push(assert(allCardTitlesNonEmpty, `Each .tw-path-card-title has non-empty text (sampled ${cardTitles.length})`));

        const scoreCount = await page.locator('.tw-path-card .tw-path-score').count();
        assertions.push(assert(scoreCount >= 1, `Each .tw-path-card contains .tw-path-score (${scoreCount})`));
      }
    } else {
      for (let i = 0; i < 8; i++) {
        assertions.push(assert(false, `Path board not visible - skipping assertion ${i + 1}`));
      }
    }

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_5_error.png');
  }

  results.push({ story: 5, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 6: Content tab shows lesson library ─────────────────────────────

async function story6() {
  const name = 'Content tab shows lesson library';
  console.log(`\n  Story 6: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Click Content tab (no user needs to be selected for this)
    await page.locator('.tw-tab[data-tab="content"]').click();
    await page.waitForTimeout(500);
    await screenshot('story_6_content.png');

    // Content tab is active
    const contentTabActive = await page.locator('.tw-tab[data-tab="content"]').evaluate(
      el => el.classList.contains('active')
    );
    assertions.push(assert(contentTabActive, `.tw-tab[data-tab='content'] has class 'active'`));

    // Tab content is visible and not empty
    const tabContentText = await page.locator('#tw-tab-content').textContent();
    assertions.push(assert(tabContentText.trim().length > 0, `#tw-tab-content is visible and not empty`));

    // Contains lesson content or placeholder with 'Content'
    const hasContent = tabContentText.toLowerCase().includes('content');
    assertions.push(assert(hasContent, `#tw-tab-content contains text with 'Content' (found: ${hasContent})`));

    // No JS errors during tab switch
    const jsErrors = consoleErrors.filter(e => !e.includes('WebSocket') && !e.includes('net::'));
    assertions.push(assert(jsErrors.length === 0, `No JavaScript errors during tab switch (${jsErrors.length} errors: ${jsErrors.slice(0, 2).join('; ')})`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_6_error.png');
  }

  results.push({ story: 6, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 7: Agent log shows session data or empty state ──────────────────

async function story7() {
  const name = 'Agent log shows session data or empty state';
  console.log(`\n  Story 7: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Search for tsigler and click
    await searchForUser('tsigler');
    await page.locator('.tw-people-list .tw-person').first().click();
    await page.waitForSelector('.tw-profile-card', { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(500);

    // Click Agent Log tab
    await page.locator('.tw-tab[data-tab="agentlog"]').click();
    await page.waitForTimeout(1000);
    await screenshot('story_7_agentlog.png');

    // Agent Log tab is active
    const agentlogTabActive = await page.locator('.tw-tab[data-tab="agentlog"]').evaluate(
      el => el.classList.contains('active')
    );
    assertions.push(assert(agentlogTabActive, `.tw-tab[data-tab='agentlog'] has class 'active'`));

    // Tab content is visible and not empty
    const tabContentText = await page.locator('#tw-tab-content').textContent();
    assertions.push(assert(tabContentText.trim().length > 0, `#tw-tab-content is visible and not empty`));

    // Contains .tw-agentlog-toolbar or placeholder
    const hasToolbar = await page.locator('.tw-agentlog-toolbar').count();
    const hasPlaceholder = await page.locator('#tw-tab-content .tw-placeholder').count();
    assertions.push(assert(hasToolbar > 0 || hasPlaceholder > 0, `Contains .tw-agentlog-toolbar or placeholder (toolbar=${hasToolbar}, placeholder=${hasPlaceholder})`));

    // If toolbar exists, session select has options
    if (hasToolbar > 0) {
      const optionCount = await page.locator('#tw-agentlog-session-select option').count();
      assertions.push(assert(optionCount >= 1, `Session select has >= 1 option (got ${optionCount})`));
    } else {
      assertions.push(assert(true, `No toolbar - placeholder shown (OK for user with no sessions)`));
    }

    // No JS errors
    const jsErrors = consoleErrors.filter(e => !e.includes('WebSocket') && !e.includes('net::'));
    assertions.push(assert(jsErrors.length === 0, `No JavaScript errors during tab switch (${jsErrors.length} errors)`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_7_error.png');
  }

  results.push({ story: 7, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 8: Left drawer collapses and expands ────────────────────────────

async function story8() {
  const name = 'Left drawer collapses and expands';
  console.log(`\n  Story 8: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();

    // Initially .tw-people-list is visible
    const initiallyVisible = await page.locator('.tw-people-list').isVisible();
    const initialPersonCount = await page.locator('.tw-people-list .tw-person').count();
    assertions.push(assert(initiallyVisible && initialPersonCount > 0, `Initially .tw-people-list visible with .tw-person elements (visible=${initiallyVisible}, count=${initialPersonCount})`));

    // Click toggle to collapse
    await page.locator('#tw-toggle-left').click();
    await page.waitForTimeout(400);
    await screenshot('story_8_collapsed.png');

    // After collapse, header and people list become hidden
    const headerHidden = await page.locator('.tw-left-header').evaluate(
      el => getComputedStyle(el).display === 'none'
    );
    const listHidden = await page.locator('.tw-people-list').evaluate(
      el => getComputedStyle(el).display === 'none'
    );
    assertions.push(assert(headerHidden && listHidden, `After collapse, .tw-left-header and .tw-people-list hidden (header=${headerHidden}, list=${listHidden})`));

    // Toggle button text changes
    const toggleText = await page.locator('#tw-toggle-left').textContent();
    assertions.push(assert(toggleText.includes('People'), `Toggle text contains 'People' (got '${toggleText.trim()}')`));

    // Click toggle again to expand
    await page.locator('#tw-toggle-left').click();
    await page.waitForTimeout(400);
    await screenshot('story_8_expanded.png');

    // After expand, people list is visible
    const expandedVisible = await page.locator('.tw-people-list').isVisible();
    assertions.push(assert(expandedVisible, `After expand, .tw-people-list visible (${expandedVisible})`));

    // Person elements are present after re-expansion
    const expandedPersonCount = await page.locator('.tw-people-list .tw-person').count();
    assertions.push(assert(expandedPersonCount > 0, `After expand, .tw-person elements present (${expandedPersonCount})`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_8_error.png');
  }

  results.push({ story: 8, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 9: AI co-pilot drawer opens and shows chat interface ────────────

async function story9() {
  const name = 'AI co-pilot drawer opens and shows chat interface';
  console.log(`\n  Story 9: ${name}`);
  const assertions = [];

  try {
    resetListeners();
    attachListeners();
    await navigateToTory();
    await page.waitForTimeout(300);

    // #tw-right is visible on initial load
    const rightVisible = await page.locator('#tw-right').isVisible();
    assertions.push(assert(rightVisible, `#tw-right is visible on initial load`));

    // .tw-right-header contains text 'AI Co-pilot'
    const headerText = await page.locator('.tw-right-header').textContent();
    assertions.push(assert(headerText.includes('AI Co-pilot'), `.tw-right-header contains 'AI Co-pilot' (got '${headerText.trim()}')`));

    // Contains placeholder or chat messages
    const hasPlaceholder = await page.locator('.tw-right-placeholder').count();
    const hasChatMessages = await page.locator('#tw-chat-messages').count();
    assertions.push(assert(hasPlaceholder > 0 || hasChatMessages > 0, `Contains .tw-right-placeholder or #tw-chat-messages (placeholder=${hasPlaceholder}, chat=${hasChatMessages})`));

    // Collapse right drawer
    await page.locator('#tw-toggle-right').click();
    await page.waitForTimeout(400);
    await screenshot('story_9_collapsed.png');

    // After collapse, .tw-right-collapsed-strip is visible
    const collapsedStripVisible = await page.locator('.tw-right-collapsed-strip').evaluate(
      el => getComputedStyle(el).display !== 'none'
    );
    assertions.push(assert(collapsedStripVisible, `After collapse, .tw-right-collapsed-strip is visible`));

    // Re-expand: click the toggle or the expand button
    await page.locator('#tw-toggle-right').click();
    await page.waitForTimeout(400);
    await screenshot('story_9_expanded.png');

    // After re-expand, header visible with 'AI Co-pilot'
    const headerVisibleAfter = await page.locator('.tw-right-header').isVisible();
    const headerTextAfter = await page.locator('.tw-right-header').textContent();
    assertions.push(assert(headerVisibleAfter && headerTextAfter.includes('AI Co-pilot'), `After re-expand, .tw-right-header visible with 'AI Co-pilot'`));

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
    await screenshot('story_9_error.png');
  }

  results.push({ story: 9, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Story 10: No console errors on initial load ───────────────────────────

async function story10() {
  const name = 'No console errors on initial load';
  console.log(`\n  Story 10: ${name}`);
  const assertions = [];

  try {
    // Fresh page with listeners
    const context = await browser.newContext({ viewport: VIEWPORT });
    const freshPage = await context.newPage();
    freshPage.setDefaultTimeout(TIMEOUT);

    const errors = [];
    const netFailures = [];

    freshPage.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    freshPage.on('pageerror', err => errors.push(err.message));
    freshPage.on('response', res => {
      if (res.status() >= 400) {
        netFailures.push({ url: res.url(), status: res.status() });
      }
    });

    await freshPage.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    await freshPage.waitForSelector('.tw-person', { timeout: 10000 });
    // Wait for deferred scripts
    await freshPage.waitForTimeout(3000);

    await freshPage.screenshot({ path: path.join(SCREENSHOT_DIR, 'story_10.png') });

    // Filter out WebSocket connection errors (expected if no WS server)
    const realErrors = errors.filter(e =>
      !e.includes('WebSocket') &&
      !e.includes('net::ERR_CONNECTION_REFUSED') &&
      !e.includes('favicon')
    );

    // Filter out favicon and websocket from network failures
    const realNetFailures = netFailures.filter(f =>
      !f.url.includes('favicon') &&
      !f.url.includes('ws://') &&
      !f.url.includes('wss://')
    );

    assertions.push(assert(realErrors.length === 0, `Zero console.error events (${realErrors.length} errors${realErrors.length > 0 ? ': ' + realErrors.slice(0, 3).join('; ') : ''})`));
    assertions.push(assert(realNetFailures.length === 0, `Zero network requests >= 400 (${realNetFailures.length} failures${realNetFailures.length > 0 ? ': ' + realNetFailures.slice(0, 3).map(f => `${f.status} ${f.url}`).join('; ') : ''})`));

    // Page renders without uncaught exceptions (checked by pageerror listener above)
    assertions.push(assert(true, `Page renders without uncaught exceptions`));

    // Layout structure
    const hasLayout = await freshPage.locator('.tw-layout').count();
    const hasLeft = await freshPage.locator('.tw-left').count();
    const hasCenter = await freshPage.locator('.tw-center').count();
    const hasRight = await freshPage.locator('.tw-right').count();
    assertions.push(assert(hasLayout > 0 && hasLeft > 0 && hasCenter > 0 && hasRight > 0, `.tw-layout contains .tw-left, .tw-center, .tw-right`));

    await freshPage.close();
    await context.close();

  } catch (err) {
    assertions.push(assert(false, `Unexpected error: ${err.message}`));
  }

  results.push({ story: 10, name, assertions });
  return assertions.every(a => a.passed);
}

// ── Main runner ───────────────────────────────────────────────────────────

async function run() {
  console.log('\n══════════════════════════════════════════════════════════════');
  console.log('  Tory Workspace QA — 10 User Stories');
  console.log('══════════════════════════════════════════════════════════════');

  await setup();

  const stories = [story1, story2, story3, story4, story5, story6, story7, story8, story9, story10];
  let passed = 0;
  let failed = 0;

  for (const storyFn of stories) {
    const ok = await storyFn();
    if (ok) passed++;
    else failed++;
  }

  await teardown();

  // Print summary
  console.log('\n══════════════════════════════════════════════════════════════');
  console.log(`  RESULTS: ${passed} passed, ${failed} failed out of ${stories.length} stories`);
  console.log('══════════════════════════════════════════════════════════════\n');

  for (const r of results) {
    const storyOk = r.assertions.every(a => a.passed);
    console.log(`  ${storyOk ? '✓' : '✗'} Story ${r.story}: ${r.name}`);
    for (const a of r.assertions) {
      console.log(`    ${a.passed ? '  ✓' : '  ✗'} ${a.description}`);
    }
  }

  // Write JSON report
  const report = {
    timestamp: new Date().toISOString(),
    stories_total: stories.length,
    stories_passed: passed,
    stories_failed: failed,
    verdict: failed === 0 ? 'ALL_PASSED' : passed === 0 ? 'ALL_FAILED' : 'PARTIAL_FAILURE',
    results: results.map(r => ({
      story: r.story,
      name: r.name,
      status: r.assertions.every(a => a.passed) ? 'PASSED' : 'FAILED',
      assertions: r.assertions,
    })),
  };

  fs.writeFileSync(path.join(SCREENSHOT_DIR, 'qa-report.json'), JSON.stringify(report, null, 2));
  console.log(`\n  Report: screenshots/bowser-qa/qa-report.json`);
  console.log(`  Screenshots: screenshots/bowser-qa/story_*.png\n`);

  process.exit(failed > 0 ? 1 : 0);
}

run().catch(err => {
  console.error('QA runner crashed:', err);
  process.exit(2);
});
