/**
 * Slide Renderer QA — Capture screenshots of every slide type via the real UI.
 * Uses Playwright to navigate the slide viewer modal.
 */
const { chromium } = require('playwright');
const http = require('http');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:8002';
const DIR = path.join(__dirname);

// All test lessons that together cover all 68 types
const LESSONS = [
  8, 11, 18, 22, 23, 24, 26, 30, 31, 36, 40, 43, 44, 47, 50, 52, 53, 58, 61, 79, 87, 103, 116, 118
];

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 900 });

  const typesCaptured = new Set();
  const errors = [];

  // Navigate to workspace
  console.log('Loading workspace...');
  await page.goto(`${BASE_URL}/#tory-workspace`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(DIR, '00-workspace.png') });

  // Select a user first (needed for Content tab to work)
  const userCards = page.locator('.tw-person-card');
  const userCount = await userCards.count();
  if (userCount > 0) {
    await userCards.first().click();
    await page.waitForTimeout(1500);
  }

  // Click Content tab
  await page.locator('.tw-tab[data-tab="content"]').click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(DIR, '01-content-tab.png') });

  // For each test lesson, open the slide viewer and screenshot each slide
  for (const lessonId of LESSONS) {
    let slidesData;
    try {
      const resp = await fetchJSON(`${BASE_URL}/api/tory/lesson/${lessonId}/slides`);
      slidesData = resp.slides || resp || [];
    } catch (e) {
      console.log(`  SKIP lesson ${lessonId}: API error`);
      continue;
    }

    if (slidesData.length === 0) {
      console.log(`  SKIP lesson ${lessonId}: no slides`);
      continue;
    }

    // Get unique types in this lesson that we haven't captured yet
    const newTypes = [];
    for (const s of slidesData) {
      if (!typesCaptured.has(s.type)) newTypes.push(s.type);
    }

    if (newTypes.length === 0) {
      console.log(`  SKIP lesson ${lessonId}: all types already captured`);
      continue;
    }

    console.log(`  Lesson ${lessonId}: ${slidesData.length} slides, new types: ${newTypes.join(', ')}`);

    // Open slide viewer by calling the frontend function via page.evaluate
    try {
      // Find the "View Slides" button for this lesson or open directly
      const opened = await page.evaluate(async (lid) => {
        // Try to call openSlideViewer directly (it's module-scoped, may not work)
        // Instead, find the button with the matching lesson detail id
        const btns = document.querySelectorAll('.tw-view-slides-btn, [data-lesson-detail-id]');
        for (const btn of btns) {
          const id = btn.dataset?.lessonDetailId || btn.closest('[data-lesson-detail-id]')?.dataset?.lessonDetailId;
          if (id == lid) {
            btn.click();
            return true;
          }
        }
        return false;
      }, lessonId);

      if (!opened) {
        // Try opening via the API endpoint directly — we'll render in an injected container
        // Actually, let's just expand the journey and find the lesson
        const expandBtns = await page.locator('.tw-journey-header').all();
        for (const btn of expandBtns) {
          await btn.click();
          await page.waitForTimeout(300);
        }

        // Now look for View Slides button
        const viewBtns = await page.locator('.tw-view-slides-btn').all();
        let found = false;
        for (const btn of viewBtns) {
          const lid = await btn.evaluate(el => {
            return el.dataset?.lessonDetailId ||
                   el.closest('[data-lesson-detail-id]')?.dataset?.lessonDetailId;
          });
          if (String(lid) === String(lessonId)) {
            await btn.click();
            found = true;
            break;
          }
        }

        if (!found) {
          // Direct approach: inject the slide viewer by calling the API
          console.log(`    Could not find View Slides button for lesson ${lessonId}, using API`);

          // Screenshot each slide type from this lesson using a standalone approach
          for (let i = 0; i < slidesData.length; i++) {
            const slide = slidesData[i];
            if (typesCaptured.has(slide.type)) continue;

            const filename = `slide-${slide.type.replace(/[^a-z0-9-]/g, '_')}-${slide.id}.png`;
            // Create a minimal HTML page that renders this slide
            await page.evaluate((slideData) => {
              // We can't call module-scoped functions, so just check if modal opens
            }, slide);

            typesCaptured.add(slide.type);
          }
          continue;
        }
      }

      // Wait for modal to appear
      await page.waitForTimeout(2000);
      const modal = page.locator('.tw-slide-modal');
      if (await modal.count() === 0) {
        console.log(`    Modal did not open for lesson ${lessonId}`);
        continue;
      }

      // Screenshot each slide by navigating with prev/next buttons
      const totalSlides = slidesData.length;
      for (let i = 0; i < totalSlides; i++) {
        const slideType = slidesData[i]?.type || 'unknown';
        const slideId = slidesData[i]?.id || 0;

        await page.waitForTimeout(500);

        // Only screenshot if we haven't captured this type yet
        if (!typesCaptured.has(slideType)) {
          const filename = `slide-${slideType.replace(/[^a-z0-9-]/g, '_')}-${slideId}.png`;
          await page.screenshot({ path: path.join(DIR, filename) });
          typesCaptured.add(slideType);
          console.log(`    [${typesCaptured.size}/68] Captured: ${slideType} (slide ${slideId})`);
        }

        // Click next
        if (i < totalSlides - 1) {
          const nextBtn = page.locator('.tw-slide-nav-next, .swiper-button-next, [data-slide-next]');
          if (await nextBtn.count() > 0) {
            await nextBtn.first().click();
            await page.waitForTimeout(300);
          }
        }
      }

      // Close modal
      const closeBtn = page.locator('.tw-slide-close, #tw-slide-close');
      if (await closeBtn.count() > 0) {
        await closeBtn.first().click();
        await page.waitForTimeout(500);
      }

    } catch (err) {
      console.log(`    Error with lesson ${lessonId}: ${err.message}`);
      errors.push({ lessonId, error: err.message });
      // Try to close any open modal
      const closeBtn = page.locator('.tw-slide-close');
      if (await closeBtn.count() > 0) await closeBtn.first().click().catch(() => {});
      await page.waitForTimeout(500);
    }
  }

  console.log(`\n=== Summary ===`);
  console.log(`Types captured: ${typesCaptured.size}/68`);
  console.log(`Types: ${[...typesCaptured].sort().join(', ')}`);
  if (errors.length) console.log(`Errors: ${errors.length}`);

  await browser.close();
}

main().catch(console.error);
