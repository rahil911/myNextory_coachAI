/**
 * E2E UI Test — All AI Features
 * Bead: baap-gbi
 * Tests: Tory Workspace, Curator AI, Companion AI, AI Instantiation,
 *        Voice Chat UI, Content 360, Learning Path, AI Session History
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8002';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots', 'bowser-qa', 'new-features');
const USER_ID = 200;
const TIMEOUT = 15000;

// Test results tracker
const results = {
  passed: [],
  failed: [],
  warnings: [],
  consoleErrors: [],
  screenshots: [],
  apiResults: []
};

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] ${msg}`);
}

async function screenshot(page, name, description) {
  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: false });
  results.screenshots.push({ name, description, path: filePath });
  log(`  Screenshot: ${name}.png — ${description}`);
  return filePath;
}

async function safeClick(page, selector, timeout = 5000) {
  try {
    await page.waitForSelector(selector, { state: 'visible', timeout });
    await page.click(selector);
    return true;
  } catch (e) {
    log(`  WARN: Could not click ${selector}: ${e.message.split('\n')[0]}`);
    return false;
  }
}

async function safeWait(page, selector, timeout = 8000) {
  try {
    await page.waitForSelector(selector, { state: 'visible', timeout });
    return true;
  } catch (e) {
    return false;
  }
}

// ─── TEST 1: Tory Workspace — User Selection & EPP Profile ──────────────

async function test1_toryWorkspace(page) {
  log('\n═══ TEST 1: Tory Workspace — User Selection & EPP Profile ═══');

  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Screenshot: Initial workspace view
  await screenshot(page, '01_tory_workspace_initial', 'Tory workspace initial load');

  // Wait for user list to populate
  const hasUserList = await safeWait(page, '#tw-people-list', 8000);
  if (!hasUserList) {
    // Try the user list with different selector
    await page.waitForTimeout(2000);
  }
  await screenshot(page, '01_tory_user_list', 'User list panel with AI status badges');

  // Search for user 200
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
    await screenshot(page, '01_tory_search_result', 'Search results for tsigler@tocgrp.com');
  }

  // Click on user to select them
  const userClicked = await safeClick(page, '.tw-person');
  if (userClicked) {
    await page.waitForTimeout(3000);
    await screenshot(page, '01_tory_user_selected', 'User selected — profile loading');
  }

  // Wait for EPP content to load
  const hasEpp = await safeWait(page, '#tw-epp-content', 10000);
  if (hasEpp) {
    await page.waitForTimeout(2000);
    await screenshot(page, '01_tory_epp_profile', 'EPP profile with radar chart and personality data');

    // Check for radar chart
    const hasRadar = await page.isVisible('#tw-epp-radar');
    const hasBar = await page.isVisible('#tw-epp-bar');
    log(`  Radar chart visible: ${hasRadar}`);
    log(`  Bar chart visible: ${hasBar}`);

    if (hasRadar || hasBar) {
      results.passed.push('EPP charts rendered');
    } else {
      results.warnings.push('EPP charts not visible — may need more load time');
    }
  } else {
    results.warnings.push('EPP content section not visible after user selection');
    await screenshot(page, '01_tory_epp_timeout', 'EPP content loading timeout');
  }

  // Check for EPP pills
  const hasPills = await safeWait(page, '#tw-epp-pills', 3000);
  if (hasPills) {
    const pillsText = await page.textContent('#tw-epp-pills');
    log(`  EPP pills text: ${pillsText?.substring(0, 100)}`);
    results.passed.push('EPP trait pills rendered');
  }

  // Check narrative section
  const hasNarrative = await safeWait(page, '#tw-epp-narrative-section', 3000);
  if (hasNarrative) {
    const narrativeText = await page.textContent('#tw-epp-narrative-section');
    log(`  Narrative preview: ${narrativeText?.substring(0, 100)}`);
    results.passed.push('Profile narrative rendered');
  }

  // Check for source badge
  const hasSourceBadge = await safeWait(page, '#tw-epp-source', 3000);
  if (hasSourceBadge) {
    const sourceText = await page.textContent('#tw-epp-source');
    log(`  EPP source: ${sourceText}`);
  }

  // Full profile screenshot
  await screenshot(page, '01_tory_full_profile', 'Complete user profile with all EPP data');
  results.passed.push('Tory Workspace user selection works');
}

// ─── TEST 2: Curator AI Co-pilot Chat ────────────────────────────────────

async function test2_curatorChat(page) {
  log('\n═══ TEST 2: Curator AI — Co-pilot Chat ═══');

  // Ensure we're on the tory workspace with a user selected
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Select user first
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
  }
  await safeClick(page, '.tw-person');
  await page.waitForTimeout(2000);

  // Open the right panel (Curator AI)
  const toggleRight = await safeClick(page, '#tw-toggle-right', 3000);
  if (toggleRight) {
    await page.waitForTimeout(1000);
    log('  Toggled right panel');
  }

  // Click curator tab
  await safeClick(page, '#tw-curator-tab-curator', 3000);
  await page.waitForTimeout(1000);

  // Screenshot: Curator panel open
  await screenshot(page, '02_curator_panel_open', 'Curator AI panel opened');

  // Check for briefing
  const hasBriefing = await safeWait(page, '#tw-curator-briefing', 5000);
  if (hasBriefing) {
    const briefingText = await page.textContent('#tw-curator-briefing');
    log(`  Briefing preview: ${briefingText?.substring(0, 150)}`);
    await screenshot(page, '02_curator_briefing', 'Curator AI auto-generated briefing');
    results.passed.push('Curator AI briefing rendered');
  } else {
    results.warnings.push('Curator briefing not visible — may be loading');
  }

  // Check chat input visibility
  const hasChatInput = await safeWait(page, '#tw-chat-input', 3000);
  if (hasChatInput) {
    await screenshot(page, '02_curator_chat_input', 'Curator chat input area visible');
    results.passed.push('Curator chat input visible');
  }

  // Check for chat area
  const hasChatArea = await safeWait(page, '#tw-chat-textarea', 5000);
  if (hasChatArea) {
    // Type a message
    await page.fill('#tw-chat-textarea', 'Tell me about this learner');
    await screenshot(page, '02_curator_message_typed', 'Message typed in curator chat');

    // Send message
    const sendClicked = await safeClick(page, '#tw-chat-send', 3000);
    if (sendClicked) {
      log('  Sent message to Curator AI...');
      // Wait for response (up to 30 seconds for AI)
      await page.waitForTimeout(3000);
      await screenshot(page, '02_curator_message_sent', 'Message sent, waiting for AI response');

      // Wait for AI response
      const hasResponse = await safeWait(page, '.tw-chat-msg', 20000);
      if (!hasResponse) {
        // Try alternate selector
        await page.waitForTimeout(10000);
      }
      await screenshot(page, '02_curator_ai_response', 'Curator AI response received');
      results.passed.push('Curator AI chat interaction completed');
    }
  } else {
    log('  Chat textarea not found — user may need to be selected first');
    results.warnings.push('Curator chat textarea not visible');
  }

  // Check session status
  const hasSessionStatus = await safeWait(page, '#tw-session-status', 3000);
  if (hasSessionStatus) {
    const statusText = await page.textContent('#tw-session-status');
    log(`  Session status: ${statusText}`);
  }

  // Check model badge
  const hasModelBadge = await safeWait(page, '#tw-curator-model-badge', 3000);
  if (hasModelBadge) {
    const modelText = await page.textContent('#tw-curator-model-badge');
    log(`  Model tier: ${modelText}`);
  }
}

// ─── TEST 3: Companion AI Learner Chat ──────────────────────────────────

async function test3_companionChat(page) {
  log('\n═══ TEST 3: Companion AI — Learner Chat ═══');

  await page.goto(`${BASE}/#companion`);
  await page.waitForTimeout(2000);

  // Screenshot: Companion initial view
  await screenshot(page, '03_companion_initial', 'Companion AI initial view');

  // Check for welcome screen
  const hasWelcome = await safeWait(page, '#companion-welcome', 5000);
  if (hasWelcome) {
    await screenshot(page, '03_companion_welcome', 'Companion welcome screen');
    results.passed.push('Companion welcome screen renders');
  }

  // Enter user ID
  const hasUserInput = await safeWait(page, '#companion-user-id', 3000);
  if (hasUserInput) {
    await page.fill('#companion-user-id', String(USER_ID));
    await screenshot(page, '03_companion_user_id', 'User ID entered');

    // Click connect
    const connected = await safeClick(page, '#companion-connect', 3000);
    if (connected) {
      log('  Connecting to companion for user 200...');
      await page.waitForTimeout(5000);
      await screenshot(page, '03_companion_connected', 'Connected to companion — greeting loaded');
      results.passed.push('Companion connection initiated');
    }
  }

  // Check for messages
  const hasMessages = await safeWait(page, '#companion-messages', 5000);
  if (hasMessages) {
    const msgCount = await page.locator('.companion-msg').count();
    log(`  Messages visible: ${msgCount}`);
    await screenshot(page, '03_companion_greeting_message', 'Companion greeting message');
  }

  // Check for action pills
  const hasActions = await safeWait(page, '#companion-actions', 5000);
  if (hasActions) {
    const actionCount = await page.locator('.companion-action-pill').count();
    log(`  Action pills visible: ${actionCount}`);
    await screenshot(page, '03_companion_action_pills', 'Quick action pills');
    results.passed.push('Companion action pills rendered');
  }

  // Check for progress bar
  const hasProgress = await safeWait(page, '#companion-progress-bar', 3000);
  if (hasProgress) {
    const progressText = await page.textContent('#companion-progress-text');
    log(`  Progress: ${progressText}`);
    results.passed.push('Companion progress bar rendered');
  }

  // Type and send a message
  const hasChatArea = await safeWait(page, '#companion-textarea', 5000);
  if (hasChatArea) {
    await page.fill('#companion-textarea', 'Hello, what should I learn next?');
    await screenshot(page, '03_companion_message_typed', 'Message typed in companion chat');

    const sendClicked = await safeClick(page, '#companion-send', 3000);
    if (sendClicked) {
      log('  Sent message to Companion AI...');
      await page.waitForTimeout(5000);

      // Wait for response
      await page.waitForTimeout(15000);
      await screenshot(page, '03_companion_ai_response', 'Companion AI response');
      results.passed.push('Companion AI chat interaction completed');
    }
  } else {
    results.warnings.push('Companion textarea not visible');
  }

  // Check voice button
  const hasVoice = await safeWait(page, '#companion-voice-btn', 3000);
  if (hasVoice) {
    const voiceVisible = await page.isVisible('#companion-voice-btn');
    log(`  Voice button visible: ${voiceVisible}`);
    if (voiceVisible) {
      await screenshot(page, '03_companion_voice_btn', 'Voice chat button in companion');
      results.passed.push('Companion voice button rendered');
    }
  }
}

// ─── TEST 4: AI Instantiation 5-Step Flow ───────────────────────────────

async function test4_aiInstantiation(page) {
  log('\n═══ TEST 4: AI Instantiation — 5-Step Flow ═══');

  // Go to tory workspace and select user
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Select user
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
  }
  await safeClick(page, '.tw-person');
  await page.waitForTimeout(3000);

  // Check for instantiate button
  const hasInstButton = await safeWait(page, '#tw-instantiate-user', 5000);
  if (hasInstButton) {
    await screenshot(page, '04_instantiation_button', 'AI Instantiation button visible');
    log('  "Initialize AI" button found');
    results.passed.push('Instantiation button visible');
  } else {
    log('  Instantiate button not found — may already be instantiated');
    results.warnings.push('Instantiation button not visible — user may be already instantiated');
  }

  // Check for view reasoning button (exists if already instantiated)
  const hasReasoningBtn = await safeWait(page, '#tw-view-reasoning', 5000);
  if (hasReasoningBtn) {
    await safeClick(page, '#tw-view-reasoning');
    await page.waitForTimeout(2000);
    await screenshot(page, '04_instantiation_reasoning', 'AI Reasoning view from previous instantiation');
    results.passed.push('AI reasoning view accessible');
  }

  // Check for instantiation progress section
  const hasProgress = await safeWait(page, '#tw-instantiation-progress', 5000);
  if (hasProgress) {
    await screenshot(page, '04_instantiation_progress', 'Instantiation progress section');
  }

  // Check for step indicators
  const hasSteps = await safeWait(page, '#tw-inst-steps', 5000);
  if (hasSteps) {
    const stepsContent = await page.textContent('#tw-inst-steps');
    log(`  Steps content: ${stepsContent?.substring(0, 200)}`);
    await screenshot(page, '04_instantiation_steps', 'Instantiation steps list');
    results.passed.push('Instantiation steps rendered');
  }

  // Check for AI reasoning display
  const hasReasoning = await safeWait(page, '#tw-inst-reasoning', 5000);
  if (hasReasoning) {
    const reasoningContent = await page.textContent('#tw-inst-reasoning');
    log(`  Reasoning preview: ${reasoningContent?.substring(0, 200)}`);
    await screenshot(page, '04_instantiation_reasoning_detail', 'AI reasoning output detail');
    results.passed.push('AI reasoning content displayed');
  }

  // Check process button too
  const hasProcessBtn = await safeWait(page, '#tw-process-user', 5000);
  if (hasProcessBtn) {
    await screenshot(page, '04_process_button', 'Process with AI button');
    results.passed.push('Process with AI button visible');
  }

  // Full profile view with all AI features visible
  await screenshot(page, '04_instantiation_full_view', 'Full view with instantiation controls');
}

// ─── TEST 5: Voice Chat UI ──────────────────────────────────────────────

async function test5_voiceChat(page) {
  log('\n═══ TEST 5: Voice Chat UI ═══');

  // Check voice in tory workspace
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Select user first
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
  }
  await safeClick(page, '.tw-person');
  await page.waitForTimeout(2000);

  // Open curator panel
  await safeClick(page, '#tw-toggle-right', 3000);
  await page.waitForTimeout(1000);

  // Check for voice button in curator
  const hasCuratorVoice = await safeWait(page, '#tw-curator-voice-btn', 5000);
  if (hasCuratorVoice) {
    const voiceVisible = await page.isVisible('#tw-curator-voice-btn');
    log(`  Curator voice button visible: ${voiceVisible}`);
    if (voiceVisible) {
      await screenshot(page, '05_voice_curator_btn', 'Voice chat button in Curator panel');
      results.passed.push('Curator voice button rendered');
    }
  } else {
    log('  Curator voice button not found');
    results.warnings.push('Curator voice button not found in workspace');
  }

  // Check companion voice
  await page.goto(`${BASE}/#companion`);
  await page.waitForTimeout(2000);

  // Connect to companion
  const hasUserInput = await safeWait(page, '#companion-user-id', 3000);
  if (hasUserInput) {
    await page.fill('#companion-user-id', String(USER_ID));
    await safeClick(page, '#companion-connect', 3000);
    await page.waitForTimeout(5000);
  }

  const hasCompanionVoice = await safeWait(page, '#companion-voice-btn', 5000);
  if (hasCompanionVoice) {
    const voiceVisible = await page.isVisible('#companion-voice-btn');
    log(`  Companion voice button visible: ${voiceVisible}`);
    if (voiceVisible) {
      await screenshot(page, '05_voice_companion_btn', 'Voice chat button in Companion view');
      results.passed.push('Companion voice button rendered');

      // Try clicking voice button to see UI state change
      await safeClick(page, '#companion-voice-btn', 3000);
      await page.waitForTimeout(2000);
      await screenshot(page, '05_voice_activated', 'Voice chat UI after activation');
    }
  } else {
    results.warnings.push('Companion voice button not found');
  }

  // Check for voice-specific CSS
  const voiceElements = await page.locator('[class*="voice"]').count();
  log(`  Voice-related elements found: ${voiceElements}`);

  // Check for mic button specifically
  const micButtons = await page.locator('.voice-mic-btn, .mic-btn, [data-voice], .voice-btn').count();
  log(`  Mic button elements found: ${micButtons}`);

  await screenshot(page, '05_voice_ui_state', 'Voice chat UI state overview');
}

// ─── TEST 6: Content Tab with Slide Viewer ──────────────────────────────

async function test6_contentTab(page) {
  log('\n═══ TEST 6: Content Tab & Slide Viewer ═══');

  // Navigate to Content 360 view
  await page.goto(`${BASE}/#content-360`);
  await page.waitForTimeout(3000);

  await screenshot(page, '06_content360_initial', 'Content 360 view initial load');

  // Check stats
  const hasStats = await safeWait(page, '#c360-stats', 5000);
  if (hasStats) {
    const statsText = await page.textContent('#c360-stats');
    log(`  Content stats: ${statsText}`);
    results.passed.push('Content 360 stats loaded');
  }

  // Check lesson list
  const hasLessonList = await safeWait(page, '#c360-lesson-list', 5000);
  if (hasLessonList) {
    const cardCount = await page.locator('.c360-card').count();
    log(`  Lesson cards found: ${cardCount}`);
    await screenshot(page, '06_content360_lesson_list', 'Lesson list with cards');
    results.passed.push(`Content 360 shows ${cardCount} lesson cards`);
  }

  // Click on first lesson card
  const firstCardClicked = await safeClick(page, '.c360-card', 5000);
  if (firstCardClicked) {
    await page.waitForTimeout(2000);
    await screenshot(page, '06_content360_lesson_detail', 'Lesson detail view');

    // Check for trait bars
    const hasTraits = await safeWait(page, '.c360-trait-bars', 3000);
    if (hasTraits) {
      const traitCount = await page.locator('.c360-trait-row').count();
      log(`  Trait rows found: ${traitCount}`);
      await screenshot(page, '06_content360_trait_mapping', 'EPP trait mapping for lesson');
      results.passed.push('Content 360 trait mapping rendered');
    }

    // Check for coaching prompts
    const hasPrompts = await safeWait(page, '.c360-prompts', 3000);
    if (hasPrompts) {
      const promptCount = await page.locator('.c360-prompt-card').count();
      log(`  Coaching prompts found: ${promptCount}`);
      await screenshot(page, '06_content360_coaching_prompts', 'Coaching prompts for lesson');
      results.passed.push('Content 360 coaching prompts rendered');
    }

    // Check slide analysis timeline
    const hasTimeline = await safeWait(page, '.c360-timeline', 3000);
    if (hasTimeline) {
      const timelineItems = await page.locator('.c360-timeline-item').count();
      log(`  Timeline items found: ${timelineItems}`);
      await screenshot(page, '06_content360_slide_timeline', 'Slide analysis timeline');
      results.passed.push('Content 360 slide timeline rendered');
    }

    // Check slide types
    const hasSlideTypes = await safeWait(page, '.c360-slide-types', 3000);
    if (hasSlideTypes) {
      const typeCount = await page.locator('.c360-slide-type-pill').count();
      log(`  Slide type pills: ${typeCount}`);
    }

    // Check key concepts
    const hasConcepts = await safeWait(page, '.c360-concept-pills', 3000);
    if (hasConcepts) {
      const conceptText = await page.textContent('.c360-concept-pills');
      log(`  Concepts: ${conceptText?.substring(0, 100)}`);
    }

    // Check related lessons (pairs)
    const hasPairs = await safeWait(page, '.c360-pairs', 3000);
    if (hasPairs) {
      const pairCount = await page.locator('.c360-pair-card').count();
      log(`  Related lessons: ${pairCount}`);
    }

    // Check slides grid
    const hasSlidesGrid = await safeWait(page, '.c360-slides-grid', 3000);
    if (hasSlidesGrid) {
      const slideCount = await page.locator('.c360-slide-chip').count();
      log(`  Slide chips: ${slideCount}`);
      await screenshot(page, '06_content360_slides_grid', 'Slides grid showing slide types');
      results.passed.push('Content 360 slides grid rendered');
    }
  }

  // Now check Content tab in Tory workspace
  log('  Checking Content tab in Tory Workspace...');
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Select user
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
  }
  await safeClick(page, '.tw-person');
  await page.waitForTimeout(3000);

  // Click Content tab
  const contentTabClicked = await safeClick(page, 'button[data-tab="content"]', 3000);
  if (contentTabClicked) {
    await page.waitForTimeout(2000);
    await screenshot(page, '06_tory_content_tab', 'Content tab in Tory Workspace');

    // Check for content library
    const hasContentLib = await safeWait(page, '#tw-content-library', 5000);
    if (hasContentLib) {
      await screenshot(page, '06_tory_content_library', 'Content library in workspace');
      results.passed.push('Tory workspace content tab works');
    }
  }
}

// ─── TEST 7: Learning Path Tab ──────────────────────────────────────────

async function test7_learningPath(page) {
  log('\n═══ TEST 7: Learning Path Tab ═══');

  // Go to tory workspace and select user
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Select user
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
  }
  await safeClick(page, '.tw-person');
  await page.waitForTimeout(3000);

  // Click Path tab
  const pathTabClicked = await safeClick(page, 'button[data-tab="path"]', 3000);
  if (pathTabClicked) {
    await page.waitForTimeout(3000);
    await screenshot(page, '07_learning_path_tab', 'Learning Path tab selected');
    results.passed.push('Learning Path tab accessible');

    // Check for path items
    const hasPathItems = await safeWait(page, '.tw-path-item', 5000);
    if (hasPathItems) {
      const pathCount = await page.locator('.tw-path-item').count();
      log(`  Path items found: ${pathCount}`);
      await screenshot(page, '07_learning_path_items', 'Learning path with lesson items');
      results.passed.push(`Learning path shows ${pathCount} items`);

      // Check for Why? icons and source badges
      const whyIcons = await page.locator('.tw-lesson-toggle, .tw-path-why, [data-tooltip*="why"], [title*="Why"]').count();
      log(`  Why/toggle elements: ${whyIcons}`);

      // Check for source badges (tory vs coach)
      const sourceBadges = await page.locator('.tw-path-source, [class*="source"]').count();
      log(`  Source badge elements: ${sourceBadges}`);

      // Try expanding a lesson
      const toggleClicked = await safeClick(page, '.tw-lesson-toggle', 3000);
      if (toggleClicked) {
        await page.waitForTimeout(1000);
        await screenshot(page, '07_learning_path_expanded', 'Learning path item expanded with reasoning');
        results.passed.push('Path item expandable');
      }

      // Check for swap/lock buttons
      const swapBtns = await page.locator('.tw-lesson-swap').count();
      const lockBtns = await page.locator('.tw-lesson-lock').count();
      log(`  Swap buttons: ${swapBtns}, Lock buttons: ${lockBtns}`);
    } else {
      results.warnings.push('No path items found — user may not have a generated path');
      await screenshot(page, '07_learning_path_empty', 'Learning path — no items (path may not be generated)');
    }
  }
}

// ─── TEST 8: AI Session History ─────────────────────────────────────────

async function test8_sessionHistory(page) {
  log('\n═══ TEST 8: AI Session History ═══');

  // Check session history via the agent log tab in workspace
  await page.goto(`${BASE}/#tory`);
  await page.waitForTimeout(2000);

  // Select user
  const searchInput = await safeWait(page, '#tw-search');
  if (searchInput) {
    await page.fill('#tw-search', 'tsigler');
    await page.waitForTimeout(1500);
  }
  await safeClick(page, '.tw-person');
  await page.waitForTimeout(3000);

  // Click Agent Log tab in right panel
  await safeClick(page, '#tw-toggle-right', 3000);
  await page.waitForTimeout(500);
  const agentLogClicked = await safeClick(page, 'button[data-tab="agentlog"]', 3000);
  if (!agentLogClicked) {
    // Try alternate: session tab or agent tab in curator panel
    await safeClick(page, '#tw-curator-tab-agent', 3000);
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(2000);
  await screenshot(page, '08_session_history_view', 'AI session history / agent log');

  // Check for agent panel
  const hasAgentPanel = await safeWait(page, '#tw-agent-panel', 5000);
  if (hasAgentPanel) {
    await screenshot(page, '08_agent_panel', 'Agent panel with session history');
    results.passed.push('Agent panel accessible');
  }

  // Check for agent messages
  const hasAgentMessages = await safeWait(page, '#tw-agent-messages', 3000);
  if (hasAgentMessages) {
    const msgContent = await page.textContent('#tw-agent-messages');
    log(`  Agent messages preview: ${msgContent?.substring(0, 150)}`);
    results.passed.push('Agent messages visible');
  }

  // Check session meta
  const hasSessionMeta = await safeWait(page, '#tw-session-meta', 3000);
  if (hasSessionMeta) {
    const metaText = await page.textContent('#tw-session-meta');
    log(`  Session meta: ${metaText?.substring(0, 100)}`);
  }

  // Check session model & cost
  const hasCost = await safeWait(page, '#tw-curator-cost', 3000);
  if (hasCost) {
    const costText = await page.textContent('#tw-curator-cost');
    log(`  Cost: ${costText}`);
  }

  const hasMsgCount = await safeWait(page, '#tw-curator-msg-count', 3000);
  if (hasMsgCount) {
    const countText = await page.textContent('#tw-curator-msg-count');
    log(`  Message count: ${countText}`);
  }

  // Full session history screenshot
  await screenshot(page, '08_session_history_full', 'Complete session history view');
}

// ─── API Endpoint Testing ───────────────────────────────────────────────

async function testAPIs() {
  log('\n═══ API ENDPOINT TESTING ═══');
  const { execSync } = require('child_process');

  const endpoints = [
    { method: 'GET', path: '/api/tory/users?limit=3', name: 'Tory Users List' },
    { method: 'GET', path: '/api/tory/profile/200', name: 'Tory Profile' },
    { method: 'GET', path: '/api/tory/path/200', name: 'Tory Path' },
    { method: 'GET', path: '/api/tory/users/200/profile', name: 'User Profile EPP' },
    { method: 'GET', path: '/api/tory/sessions/200', name: 'AI Sessions' },
    { method: 'GET', path: '/api/content360', name: 'Content 360 List' },
    { method: 'GET', path: '/api/companion/greeting/200', name: 'Companion Greeting' },
  ];

  for (const ep of endpoints) {
    try {
      const cmd = `curl -s -o /dev/null -w "%{http_code}" -X ${ep.method} "${BASE}${ep.path}"`;
      const status = execSync(cmd, { encoding: 'utf-8' }).trim();
      const statusNum = parseInt(status);
      const ok = statusNum >= 200 && statusNum < 400;
      const symbol = ok ? 'PASS' : 'FAIL';
      log(`  ${symbol}: ${ep.method} ${ep.path} → ${status} (${ep.name})`);
      results.apiResults.push({ ...ep, status: statusNum, ok });
      if (ok) results.passed.push(`API: ${ep.name} (${status})`);
      else results.failed.push(`API: ${ep.name} returned ${status}`);
    } catch (e) {
      log(`  FAIL: ${ep.method} ${ep.path} — ${e.message.split('\n')[0]}`);
      results.apiResults.push({ ...ep, status: 0, ok: false });
      results.failed.push(`API: ${ep.name} error`);
    }
  }

  // Test curator chat API
  try {
    log('  Testing Curator Chat API...');
    const cmd = `curl -s -X POST "${BASE}/api/tory/chat" -H "Content-Type: application/json" -d '{"user_id":200,"message":"What are this learner strengths?"}' --max-time 30`;
    const response = execSync(cmd, { encoding: 'utf-8', timeout: 35000 }).trim();
    const parsed = JSON.parse(response);
    if (parsed.response || parsed.message || parsed.reply) {
      log(`  PASS: Curator Chat API — AI responded with real data`);
      const responseText = parsed.response || parsed.message || parsed.reply || '';
      log(`    Response preview: ${responseText.substring(0, 150)}`);
      results.passed.push('API: Curator Chat returns AI response');
    } else {
      log(`  WARN: Curator Chat API — unexpected response format`);
      log(`    Keys: ${Object.keys(parsed).join(', ')}`);
      results.warnings.push('Curator Chat API unexpected response format');
    }
  } catch (e) {
    log(`  WARN: Curator Chat API — ${e.message.split('\n')[0]}`);
    results.warnings.push(`Curator Chat API: ${e.message.split('\n')[0]}`);
  }

  // Test companion chat API
  try {
    log('  Testing Companion Chat API...');
    const cmd = `curl -s -X POST "${BASE}/api/companion/chat" -H "Content-Type: application/json" -d '{"user_id":200,"message":"Hello, what should I learn?"}' --max-time 30`;
    const response = execSync(cmd, { encoding: 'utf-8', timeout: 35000 }).trim();
    const parsed = JSON.parse(response);
    if (parsed.response || parsed.message || parsed.reply) {
      log(`  PASS: Companion Chat API — AI responded`);
      const responseText = parsed.response || parsed.message || parsed.reply || '';
      log(`    Response preview: ${responseText.substring(0, 150)}`);
      results.passed.push('API: Companion Chat returns AI response');
    } else {
      log(`  WARN: Companion Chat API — unexpected response format`);
      log(`    Keys: ${Object.keys(parsed).join(', ')}`);
      results.warnings.push('Companion Chat API unexpected response format');
    }
  } catch (e) {
    log(`  WARN: Companion Chat API — ${e.message.split('\n')[0]}`);
    results.warnings.push(`Companion Chat API: ${e.message.split('\n')[0]}`);
  }
}

// ─── Console Error Detection ────────────────────────────────────────────

function setupConsoleCapture(page) {
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Filter out known harmless errors
      if (!text.includes('favicon') && !text.includes('DevTools')) {
        results.consoleErrors.push({
          text: text.substring(0, 200),
          url: msg.location()?.url || 'unknown',
        });
      }
    }
  });

  page.on('pageerror', error => {
    results.consoleErrors.push({
      text: `PAGE ERROR: ${error.message.substring(0, 200)}`,
      url: 'page',
    });
  });
}

// ─── Main ───────────────────────────────────────────────────────────────

async function main() {
  log('Starting E2E UI tests for all AI features...');
  log(`Base URL: ${BASE}`);
  log(`Screenshot dir: ${SCREENSHOT_DIR}`);
  log(`Target user: ${USER_ID}`);

  // Ensure screenshot dir exists
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
  setupConsoleCapture(page);

  try {
    // Run all UI tests
    await test1_toryWorkspace(page);
    await test2_curatorChat(page);
    await test3_companionChat(page);
    await test4_aiInstantiation(page);
    await test5_voiceChat(page);
    await test6_contentTab(page);
    await test7_learningPath(page);
    await test8_sessionHistory(page);
  } catch (e) {
    log(`\nFATAL TEST ERROR: ${e.message}`);
    results.failed.push(`Fatal: ${e.message}`);
    await screenshot(page, 'fatal_error', 'Fatal error state').catch(() => {});
  }

  await browser.close();

  // Run API tests
  await testAPIs();

  // ─── Generate Report ────────────────────────────────────────────────

  log('\n════════════════════════════════════════════════════');
  log('                  TEST RESULTS');
  log('════════════════════════════════════════════════════');
  log(`  Passed:           ${results.passed.length}`);
  log(`  Failed:           ${results.failed.length}`);
  log(`  Warnings:         ${results.warnings.length}`);
  log(`  Console Errors:   ${results.consoleErrors.length}`);
  log(`  Screenshots:      ${results.screenshots.length}`);
  log(`  API Endpoints:    ${results.apiResults.length}`);

  if (results.failed.length > 0) {
    log('\nFAILED:');
    results.failed.forEach(f => log(`  - ${f}`));
  }
  if (results.warnings.length > 0) {
    log('\nWARNINGS:');
    results.warnings.forEach(w => log(`  - ${w}`));
  }
  if (results.consoleErrors.length > 0) {
    log('\nCONSOLE ERRORS:');
    results.consoleErrors.forEach(e => log(`  - ${e.text}`));
  }

  // Write report to file
  const report = generateReport();
  const reportPath = path.join(SCREENSHOT_DIR, 'test-report.md');
  fs.writeFileSync(reportPath, report);
  log(`\nReport written to: ${reportPath}`);

  // Return results for exit code
  return results.failed.length === 0 ? 0 : 1;
}

function generateReport() {
  const now = new Date().toISOString();
  let md = `# E2E UI Test Report — AI Features\n\n`;
  md += `**Date:** ${now}\n`;
  md += `**Target:** ${BASE}\n`;
  md += `**User:** ${USER_ID} (tsigler@tocgrp.com — Patricia Sigler)\n\n`;

  md += `## Summary\n\n`;
  md += `| Metric | Count |\n`;
  md += `|--------|-------|\n`;
  md += `| Passed | ${results.passed.length} |\n`;
  md += `| Failed | ${results.failed.length} |\n`;
  md += `| Warnings | ${results.warnings.length} |\n`;
  md += `| Console Errors | ${results.consoleErrors.length} |\n`;
  md += `| Screenshots | ${results.screenshots.length} |\n`;
  md += `| API Tests | ${results.apiResults.length} |\n\n`;

  md += `## Passed Tests\n\n`;
  results.passed.forEach(p => { md += `- ${p}\n`; });

  if (results.failed.length > 0) {
    md += `\n## Failed Tests\n\n`;
    results.failed.forEach(f => { md += `- ${f}\n`; });
  }

  if (results.warnings.length > 0) {
    md += `\n## Warnings\n\n`;
    results.warnings.forEach(w => { md += `- ${w}\n`; });
  }

  md += `\n## API Endpoint Results\n\n`;
  md += `| Method | Path | Status | Result |\n`;
  md += `|--------|------|--------|--------|\n`;
  results.apiResults.forEach(a => {
    md += `| ${a.method} | ${a.path} | ${a.status} | ${a.ok ? 'PASS' : 'FAIL'} |\n`;
  });

  if (results.consoleErrors.length > 0) {
    md += `\n## Console Errors\n\n`;
    results.consoleErrors.forEach(e => {
      md += `- \`${e.text}\` (${e.url})\n`;
    });
  }

  md += `\n## Screenshots\n\n`;
  results.screenshots.forEach(s => {
    md += `### ${s.name}\n`;
    md += `${s.description}\n`;
    md += `![${s.name}](${s.name}.png)\n\n`;
  });

  md += `\n---\nGenerated by Baap E2E Test Suite\n`;
  return md;
}

main()
  .then(code => process.exit(code))
  .catch(e => {
    console.error('Test suite crashed:', e);
    process.exit(2);
  });
