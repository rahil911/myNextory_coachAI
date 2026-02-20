// ==========================================================================
// SLIDE-VIEWER.JS — Shared slide viewer modal with Swiper carousel
// Used by tory-workspace.js and content-360.js
// Renders all 68 slide types via type-specific renderers
// ==========================================================================

import { api } from '../api.js';
import { showToast } from './toast.js';

// ── Module state ─────────────────────────────────────────────────────────

let _slides = null;
let _slideIdx = 0;
let _slidesLoading = false;

// ── Public API ───────────────────────────────────────────────────────────

export async function openSlideViewer(lessonDetailId, lessonName) {
  _slides = null;
  _slideIdx = 0;
  _slidesLoading = true;

  _renderSlideModal(lessonName);

  try {
    const data = await api.getToryLessonSlides(lessonDetailId);
    _slides = data.slides || data || [];
    _slidesLoading = false;
    _renderSlideModal(lessonName);
  } catch (err) {
    _slidesLoading = false;
    showToast(`Failed to load slides: ${err.message}`, 'error');
    closeSlideViewer();
  }
}

export function closeSlideViewer() {
  const modal = document.getElementById('sv-slide-modal');
  if (modal) {
    if (modal._keyHandler) document.removeEventListener('keydown', modal._keyHandler);
    _destroyInstances();
    modal.remove();
  }
  _slides = null;
  _slideIdx = 0;
}

// ── Modal Rendering ──────────────────────────────────────────────────────

function _renderSlideModal(lessonName) {
  _destroyInstances();
  document.getElementById('sv-slide-modal')?.remove();

  const modal = document.createElement('div');
  modal.className = 'tw-slide-modal';
  modal.id = 'sv-slide-modal';

  if (_slidesLoading) {
    modal.innerHTML = `
      <div class="tw-slide-overlay"></div>
      <div class="tw-slide-container">
        <div class="tw-slide-header">
          <span class="tw-slide-title">${_esc(lessonName || 'Slides')}</span>
          <button class="tw-slide-close" id="sv-slide-close">&times;</button>
        </div>
        <div class="tw-loading" style="flex:1"><div class="tw-spinner"></div> Loading slides...</div>
      </div>
    `;
    document.body.appendChild(modal);
    _wireClose(modal);
    return;
  }

  const slides = _slides || [];
  if (slides.length === 0) {
    modal.innerHTML = `
      <div class="tw-slide-overlay"></div>
      <div class="tw-slide-container">
        <div class="tw-slide-header">
          <span class="tw-slide-title">${_esc(lessonName || 'Slides')}</span>
          <button class="tw-slide-close" id="sv-slide-close">&times;</button>
        </div>
        <div class="tw-placeholder" style="flex:1"><div class="tw-placeholder-text">No slides found</div></div>
      </div>
    `;
    document.body.appendChild(modal);
    _wireClose(modal);
    return;
  }

  const total = slides.length;

  const swiperSlides = slides.map((slide) => {
    let content = slide.content || slide.slide_content;
    if (typeof content === 'string') {
      try { content = JSON.parse(content); } catch { content = {}; }
    }
    content = content || {};
    const slideType = slide.type || slide.slide_type || 'unknown';
    const slideHtml = renderSlideContent(slideType, content, slide);
    return `<div class="swiper-slide">
      <div class="tw-slide-inner">${slideHtml}</div>
      <div class="tw-slide-type-badge">${_esc(slideType)}</div>
    </div>`;
  }).join('');

  const dotsHtml = Array.from({ length: total }, (_, i) =>
    `<button class="tw-slide-dot${i === 0 ? ' active' : ''}" data-idx="${i}"></button>`
  ).join('');

  modal.innerHTML = `
    <div class="tw-slide-overlay"></div>
    <div class="tw-slide-container">
      <div class="tw-slide-header">
        <span class="tw-slide-title">${_esc(lessonName || 'Slides')}</span>
        <span class="tw-slide-counter" id="sv-slide-counter">Slide 1 / ${total}</span>
        <button class="tw-slide-close" id="sv-slide-close">&times;</button>
      </div>
      <div class="swiper tw-swiper" id="sv-swiper">
        <div class="swiper-wrapper">${swiperSlides}</div>
      </div>
      <button class="tw-slide-nav-prev" id="sv-slide-prev" aria-label="Previous slide">&#8249;</button>
      <button class="tw-slide-nav-next" id="sv-slide-next" aria-label="Next slide">&#8250;</button>
      <div class="tw-slide-dots" id="sv-slide-dots">${dotsHtml}</div>
    </div>
  `;

  document.body.appendChild(modal);
  _wireClose(modal);

  // Defer Swiper init to next frame so browser has completed layout
  requestAnimationFrame(() => {
    const startIdx = Math.max(0, Math.min(_slideIdx, total - 1));
    const swiper = new Swiper('#sv-swiper', {
      slidesPerView: 1,
      initialSlide: startIdx,
      effect: 'slide',
      speed: 300,
      keyboard: { enabled: true, onlyInViewport: false },
      observer: true,
      observeParents: true,
    });
    modal._swiperInstance = swiper;

    const prevBtn = modal.querySelector('#sv-slide-prev');
    const nextBtnEl = modal.querySelector('#sv-slide-next');
    const counterEl = modal.querySelector('#sv-slide-counter');
    const dotsContainer = modal.querySelector('#sv-slide-dots');

    prevBtn.addEventListener('click', () => swiper.slidePrev());
    nextBtnEl.addEventListener('click', () => swiper.slideNext());

    dotsContainer.addEventListener('click', (e) => {
      const dot = e.target.closest('.tw-slide-dot');
      if (dot) swiper.slideTo(parseInt(dot.dataset.idx, 10));
    });

    const updateSlideUI = () => {
      const idx = swiper.activeIndex;
      _slideIdx = idx;
      if (counterEl) counterEl.textContent = `Slide ${idx + 1} / ${total}`;
      prevBtn.disabled = idx === 0;
      nextBtnEl.disabled = idx === total - 1;
      dotsContainer.querySelectorAll('.tw-slide-dot').forEach((d, i) => {
        d.classList.toggle('active', i === idx);
      });
    };
    swiper.on('slideChange', updateSlideUI);
    updateSlideUI();

    // Initialize Plyr for video and audio elements
    const plyrInstances = [];
    modal.querySelectorAll('.tw-plyr-video').forEach(el => {
      plyrInstances.push(new Plyr(el, { controls: ['play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen'] }));
    });
    modal.querySelectorAll('.tw-plyr-audio').forEach(el => {
      plyrInstances.push(new Plyr(el, { controls: ['play', 'progress', 'current-time', 'mute', 'volume'] }));
    });
    modal._plyrInstances = plyrInstances;
  });
}

function _wireClose(modal) {
  modal.querySelector('#sv-slide-close')?.addEventListener('click', closeSlideViewer);
  modal.querySelector('.tw-slide-overlay')?.addEventListener('click', closeSlideViewer);
  modal._keyHandler = (e) => {
    if (e.key === 'Escape') closeSlideViewer();
  };
  document.addEventListener('keydown', modal._keyHandler);
}

function _destroyInstances() {
  const existing = document.getElementById('sv-slide-modal');
  if (!existing) return;
  if (existing._swiperInstance) { try { existing._swiperInstance.destroy(true, true); } catch {} }
  if (existing._plyrInstances) { existing._plyrInstances.forEach(p => { try { p.destroy(); } catch {} }); }
}

// ── Slide Content Router ─────────────────────────────────────────────────

export function renderSlideContent(type, content, slide) {
  if (/^video/.test(type))
    return _renderVideo(type, content, slide);
  if (type === 'greetings')
    return _renderGreeting(content);
  if (type === 'take-away')
    return _renderTakeaway(content);
  if (type === 'one-word-apprication' || type === 'one-word-content-box')
    return _renderOneWord(content);
  if (/^image\d*$/.test(type) || /^special-image/.test(type) || type === 'sparkle')
    return _renderImage(type, content);
  if (/^image-with-/.test(type))
    return _renderImageHybrid(type, content);
  if (/^question-answer/.test(type) || type === 'question-with-example' || type === 'questions-example2')
    return _renderQuestion(type, content);
  if (/^stakeholder/.test(type) || type === 'answered-stakeholders')
    return _renderStakeholder(type, content);
  if (type === 'multiple-choice' || type === 'single-choice-with-message')
    return _renderMultipleChoice(content);
  if (type === 'select-true-or-false' || type === 'choose-true-or-false')
    return _renderTrueFalse(content);
  if (type === 'check-yes-or-no')
    return _renderCheckYesNo(content);
  if (type === 'select-range')
    return _renderSelectRange(content);
  if (type === 'three-word' || type === 'select-one-word' || type === 'one-word-select-option')
    return _renderWordSelection(type, content);
  if (/^select-option/.test(type) || type === 'select-the-best')
    return _renderSelectOption(type, content);
  if (type === 'side-by-side-dropdown-selector')
    return _renderDropdownSelector(content);
  if (/^side-by-side-/.test(type))
    return _renderSideBySideForm(content);
  if (type === 'celebrate' || type === 'show-gratitude' || type === 'decision' || type === 'decision2' ||
      type === 'take-to-lunch' || type === 'people-you-would-like-to-thank' || type === 'chat-interface' ||
      type === 'build-your-network')
    return _renderEngagement(type, content);
  return _renderFallback(type, content);
}

// ── Helpers ──────────────────────────────────────────────────────────────

function _esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function _html(val) {
  if (!val) return '';
  return String(val)
    .replace(/u201c/g, '\u201c').replace(/u201d/g, '\u201d')
    .replace(/u2018/g, '\u2018').replace(/u2019/g, '\u2019')
    .replace(/u2014/g, '\u2014').replace(/u2013/g, '\u2013')
    .replace(/u2026/g, '\u2026');
}

function _headsUp(c) {
  if (!c.is_headsup && !c.heads_up) return '';
  const tip = c.heads_up || '';
  return tip ? `<div class="tw-slide-headsup"><strong>Heads up</strong><div>${_html(tip)}</div></div>` : '';
}

function _backpackBadge(c) {
  let badges = '';
  if (c.is_backpack) badges += '<span class="tw-slide-badge tw-badge-backpack">Backpack</span>';
  if (c.is_task) badges += `<span class="tw-slide-badge tw-badge-task">${_esc(c.task_name || 'Task')}</span>`;
  return badges ? `<div class="tw-slide-badges">${badges}</div>` : '';
}

// ── Category A: Video ──
function _renderVideo(type, content, slide) {
  let html = '';
  const vl = slide && slide.video_library;
  if (vl && vl.video_url) {
    const title = content.slide_title || vl.title || '';
    if (title) html += `<div class="tw-slide-text-content"><h3 class="tw-slide-text-title">${_html(title)}</h3></div>`;
    html += `<div class="tw-slide-media tw-slide-video-wrap">
      <video class="tw-plyr-video" playsinline controls preload="metadata"
        ${vl.thumbnail_url ? `poster="${_esc(vl.thumbnail_url)}"` : ''}>
        <source src="${_esc(vl.video_url)}" type="video/mp4">
      </video>
    </div>`;
    if (vl.transcript) {
      html += `<div class="tw-slide-transcript"><div class="tw-slide-transcript-label">Transcript</div><div class="tw-slide-transcript-text">${_html(vl.transcript)}</div></div>`;
    }
    if (vl.source === 'blob_inventory') {
      html += `<div class="tw-slide-source-badge">Video matched from library</div>`;
    }
  } else {
    html += `<div class="tw-slide-media"><div class="tw-slide-placeholder tw-slide-video-placeholder">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.5;margin-bottom:1rem"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
      <div style="font-size:1.1rem;font-weight:500">Video content</div>
      <div style="font-size:0.85rem;opacity:0.6;margin-top:0.25rem">${_esc(content.slide_title || 'Available in the MyNextory app')}</div>
    </div></div>`;
    if (content.slide_title) html += `<div class="tw-slide-text-content"><h3 class="tw-slide-text-title">${_html(content.slide_title)}</h3></div>`;
  }
  html += _headsUp(content);
  if (content.options && Array.isArray(content.options)) {
    html += '<div class="tw-slide-options">';
    for (const opt of content.options) {
      html += `<div class="tw-slide-option"><strong>${_html(opt.title || '')}</strong><div>${_html(opt.msg || '')}</div></div>`;
    }
    html += '</div>';
  }
  if (content.questions && Array.isArray(content.questions)) {
    if (content.content_title) html += `<div class="tw-slide-content-title">${_html(content.content_title)}</div>`;
    html += '<div class="tw-slide-questions">';
    for (const q of content.questions) {
      html += `<div class="tw-slide-question-item">`;
      if (q.word) html += `<div class="tw-slide-question-word">${_html(q.word)}</div>`;
      if (q.question1) html += `<label>${_html(q.question1)}</label><textarea class="tw-slide-textarea" rows="2" placeholder="Your answer..."></textarea>`;
      if (q.question2) html += `<label>${_html(q.question2)}</label><textarea class="tw-slide-textarea" rows="2" placeholder="Your answer..."></textarea>`;
      html += '</div>';
    }
    html += '</div>';
  }
  html += _backpackBadge(content);
  return html;
}

// ── Category A: Image family ──
function _renderImage(type, content) {
  let html = '';
  const bg = content.background_image || '';
  if (bg) {
    html += `<div class="tw-slide-media"><img src="${_esc(bg)}" alt="${_esc(content.slide_title || 'Lesson image')}" loading="lazy"
      onerror="this.onerror=null;this.parentElement.innerHTML='<div class=\\'tw-slide-placeholder\\'>Image unavailable</div>';"></div>`;
  }
  html += '<div class="tw-slide-text-content">';
  if (content.slide_title) html += `<h3 class="tw-slide-text-title">${_html(content.slide_title)}</h3>`;
  if (content.content_title) html += `<div class="tw-slide-content-title">${_html(content.content_title)}</div>`;
  if (content.content) html += `<div class="tw-slide-text-body">${_html(content.content)}</div>`;
  if (content.short_description) html += `<div class="tw-slide-text-body tw-slide-description">${_html(content.short_description)}</div>`;
  if (type === 'image5' && content.options && Array.isArray(content.options)) {
    html += '<div class="tw-slide-options tw-slide-expand-options">';
    for (const opt of content.options) {
      const title = typeof opt === 'string' ? opt : (opt.option || '');
      const desc = opt.description || '';
      html += `<details class="tw-slide-option tw-slide-expand-item"><summary>${_html(title)}</summary><div class="tw-slide-expand-desc">${_html(desc)}</div></details>`;
    }
    html += '</div>';
  }
  if (content.imageExamples && Array.isArray(content.imageExamples)) {
    html += '<div class="tw-slide-image-examples">';
    for (const ex of content.imageExamples) {
      const imgSrc = ex.background_image || '';
      html += `<div class="tw-slide-image-example-card">`;
      if (imgSrc) html += `<img src="${_esc(imgSrc)}" alt="${_esc(ex.image_title || '')}" loading="lazy" onerror="this.style.display='none'">`;
      if (ex.image_title) html += `<div class="tw-slide-image-example-label">${_html(ex.image_title)}</div>`;
      if (ex.name) html += `<div class="tw-slide-image-example-name">${_html(ex.name)}</div>`;
      if (ex.description) html += `<div class="tw-slide-image-example-desc">${_html(ex.description)}</div>`;
      html += '</div>';
    }
    html += '</div>';
  }
  if (type === 'special-image1' || type === 'special-image') {
    if (content.content1) html += `<div class="tw-slide-text-body">${_html(content.content1)}</div>`;
    if (content.content2) html += `<div class="tw-slide-text-body">${_html(content.content2)}</div>`;
    if (content.special_word) html += `<div class="tw-slide-special-word">${_html(content.special_word)}</div>`;
  }
  html += '</div>';
  html += _headsUp(content);
  if (content.audio) {
    html += `<div class="tw-slide-audio"><audio class="tw-plyr-audio" preload="metadata"><source src="${_esc(content.audio)}"></audio></div>`;
  }
  return html;
}

// ── Category E: Image + Interactive hybrid ──
function _renderImageHybrid(type, content) {
  let html = '';
  const bg = content.background_image || content.image || '';
  if (bg) {
    html += `<div class="tw-slide-media"><img src="${_esc(bg)}" alt="${_esc(content.slide_title || '')}" loading="lazy"
      onerror="this.onerror=null;this.parentElement.innerHTML='<div class=\\'tw-slide-placeholder\\'>Image unavailable</div>';"></div>`;
  }
  html += '<div class="tw-slide-text-content">';
  if (content.slide_title) html += `<h3 class="tw-slide-text-title">${_html(content.slide_title)}</h3>`;
  if (content.content_title) html += `<div class="tw-slide-content-title">${_html(content.content_title)}</div>`;
  if (content.content && type === 'image-with-content') html += `<div class="tw-slide-content-title">${_html(content.content)}</div>`;
  if (content.content_on_image) html += `<div class="tw-slide-text-body">${_html(content.content_on_image)}</div>`;
  if (content.content_description) html += `<div class="tw-slide-text-body">${_html(content.content_description)}</div>`;
  if (content.card_title) html += `<div class="tw-slide-text-body"><strong>${_html(content.card_title)}</strong></div>`;
  if (content.card_content) html += `<div class="tw-slide-text-body">${_html(content.card_content)}</div>`;
  if (content.options && Array.isArray(content.options)) {
    html += '<div class="tw-slide-options">';
    for (const opt of content.options) {
      if (typeof opt === 'string') {
        html += `<div class="tw-slide-option">${_html(opt)}</div>`;
      } else {
        html += `<div class="tw-slide-option"><strong>${_html(opt.title || opt.question || '')}</strong>`;
        if (opt.box) html += `<div>${_html(opt.box)}</div>`;
        html += '</div>';
      }
    }
    html += '</div>';
  }
  if (content.questions && Array.isArray(content.questions)) {
    html += '<div class="tw-slide-questions">';
    for (const q of content.questions) {
      const qText = typeof q === 'string' ? q : (q.question || q.title || '');
      html += `<div class="tw-slide-question-item"><textarea class="tw-slide-textarea" placeholder="Your answer..." rows="2"></textarea><label>${_html(qText)}</label></div>`;
    }
    html += '</div>';
  }
  if (content.note) html += `<div class="tw-slide-note">${_html(content.note)}</div>`;
  if (content.message) html += `<div class="tw-slide-feedback tw-feedback-good">${_html(content.message)}</div>`;
  if (content.right_answer_message) html += `<div class="tw-slide-feedback tw-feedback-good">${_html(content.right_answer_message)}</div>`;
  if (content.wrong_answer_message) html += `<div class="tw-slide-feedback tw-feedback-improve">${_html(content.wrong_answer_message)}</div>`;
  html += '</div>';
  html += _backpackBadge(content);
  html += _headsUp(content);
  if (content.audio) {
    html += `<div class="tw-slide-audio"><audio class="tw-plyr-audio" preload="metadata"><source src="${_esc(content.audio)}"></audio></div>`;
  }
  return html;
}

// ── Category F: Greetings ──
function _renderGreeting(c) {
  return `<div class="tw-slide-text-content tw-slide-greeting">
    ${c.slide_title ? `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>` : ''}
    <div class="tw-slide-greeting-message">${_html(c.greetings || '')}</div>
    <div class="tw-slide-greeting-sig">
      <span class="tw-slide-advisor-name">${_html(c.advisor_name || '')}</span>
      <span class="tw-slide-advisor-role">${_html(c.advisor_content || '')}</span>
    </div>
    ${_headsUp(c)}
  </div>`;
}

// ── Category F: Take-away ──
function _renderTakeaway(c) {
  return `<div class="tw-slide-text-content tw-slide-takeaway">
    ${c.slide_title ? `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>` : ''}
    <div class="tw-slide-takeaway-msg">${_html(c.message || '')}</div>
    ${c.message_1 ? `<div class="tw-slide-takeaway-prompt">${_html(c.message_1)}</div>` : ''}
    ${c.message_2 ? `<div class="tw-slide-takeaway-prompt tw-slide-takeaway-q">${_html(c.message_2)}</div>` : ''}
    ${_headsUp(c)}
  </div>`;
}

// ── Category F: One-word appreciation ──
function _renderOneWord(c) {
  return `<div class="tw-slide-text-content tw-slide-oneword">
    ${c.slide_title ? `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>` : ''}
    <div class="tw-slide-appreciation">${_html(c.appreciation || c.content || '')}</div>
    ${_backpackBadge(c)}
  </div>`;
}

// ── Category B: Question-answer family ──
function _renderQuestion(type, c) {
  let html = '<div class="tw-slide-text-content tw-slide-question-card">';
  html += c.card_title ? `<h3 class="tw-slide-text-title">${_html(c.card_title)}</h3>` :
          c.slide_title ? `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>` : '';
  if (c.card_content) html += `<div class="tw-slide-text-body">${_html(c.card_content)}</div>`;
  if (c.content_title) html += `<div class="tw-slide-content-title">${_html(c.content_title)}</div>`;

  const questions = c.questions || c.questionss || [];
  if (questions && questions.LHS) {
    const lhsItems = (typeof questions.LHS === 'string') ? questions.LHS.split('<br />').filter(Boolean) : (questions.LHS || []);
    const rhsItems = (typeof questions.RHS === 'string') ? questions.RHS.split('<br />').filter(Boolean) : (questions.RHS || []);
    if (c.lhs_popup_header || c.rhs_popup_header) {
      html += '<div class="tw-slide-form-header">';
      html += `<div class="tw-slide-form-lhs">${_html(c.lhs_popup_header || '')}</div>`;
      html += `<div class="tw-slide-form-rhs">${_html(c.rhs_popup_header || '')}</div>`;
      html += '</div>';
    }
    const count = Math.max(lhsItems.length, rhsItems.length);
    html += '<div class="tw-slide-questions">';
    for (let i = 0; i < count; i++) {
      html += '<div class="tw-slide-form-row">';
      if (i < lhsItems.length) html += `<div class="tw-slide-form-lhs">${_html(lhsItems[i])}</div>`;
      if (i < rhsItems.length) html += `<div class="tw-slide-form-rhs">${_html(rhsItems[i])}</div>`;
      html += '</div>';
    }
    html += '</div>';
  } else if (Array.isArray(questions)) {
    html += '<div class="tw-slide-questions">';
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      if (typeof q === 'string') {
        html += `<div class="tw-slide-question-item"><label>${_html(q)}</label><textarea class="tw-slide-textarea" rows="2" placeholder="Your answer..."></textarea></div>`;
      } else {
        const label = q.title ? `<strong>${_html(q.title)}</strong>: ${_html(q.question || '')}` : _html(q.question || q.word || '');
        html += `<div class="tw-slide-question-item"><label>${label}</label><textarea class="tw-slide-textarea" rows="2" placeholder="Your answer..."></textarea></div>`;
      }
    }
    html += '</div>';
  }

  if (c.examples && Array.isArray(c.examples)) {
    html += '<div class="tw-slide-examples">';
    for (let i = 0; i < c.examples.length; i++) {
      const exList = c.examples[i];
      const header = (questions[i] && questions[i].header) || `Examples ${i + 1}`;
      if (Array.isArray(exList) && exList.length > 0) {
        html += `<details class="tw-slide-example-group"><summary>${_html(header)}</summary><ul>`;
        for (const ex of exList) html += `<li>${_html(ex)}</li>`;
        html += '</ul></details>';
      }
    }
    html += '</div>';
  }

  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category G: Stakeholder ──
function _renderStakeholder(type, c) {
  let html = '<div class="tw-slide-text-content tw-slide-stakeholder">';
  if (c.slide_title) html += `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>`;

  if (type === 'stakeholders' && c.stakeholders && Array.isArray(c.stakeholders)) {
    html += `<div class="tw-slide-text-body">Select ${_esc(c.select_count || '3')} stakeholders:</div>`;
    html += '<div class="tw-slide-stakeholder-grid">';
    for (const s of c.stakeholders) {
      const img = s.image || '';
      html += `<div class="tw-slide-stakeholder-card">
        ${img ? `<img src="${_esc(img)}" alt="${_esc(s.name)}" class="tw-slide-stakeholder-img" onerror="this.style.display='none'">` : '<div class="tw-slide-stakeholder-avatar">&#128100;</div>'}
        <div class="tw-slide-stakeholder-name">${_html(s.name || '')}</div>
      </div>`;
    }
    html += '</div>';
  } else if (type === 'stakeholder-question') {
    if (c.stakeholder_name) html += `<div class="tw-slide-stakeholder-label">${_html(c.stakeholder_name)}</div>`;
    if (c.card_title) html += `<div class="tw-slide-text-body"><strong>${_html(c.card_title)}</strong></div>`;
    if (c.question) html += `<div class="tw-slide-text-body">${_html(c.question)}</div>`;
  } else if (type === 'stakeholder-question-answer') {
    if (c.stakeholder_name) html += `<div class="tw-slide-stakeholder-label">${_html(c.stakeholder_name)}</div>`;
    const qs = c.questions || [];
    const phs = c.placeholders || [];
    html += '<div class="tw-slide-questions">';
    for (let i = 0; i < qs.length; i++) {
      html += `<div class="tw-slide-question-item"><label>${_html(qs[i])}</label><textarea class="tw-slide-textarea" rows="2" placeholder="${_esc(phs[i] || 'Your answer...')}"></textarea></div>`;
    }
    html += '</div>';
  } else {
    if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
  }

  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category C: Multiple-choice ──
function _renderMultipleChoice(c) {
  let html = '<div class="tw-slide-text-content tw-slide-quiz">';
  if (c.card_title) html += `<h3 class="tw-slide-text-title">${_html(c.card_title)}</h3>`;
  const questions = c.questions || [];
  for (let qi = 0; qi < questions.length; qi++) {
    const q = questions[qi];
    html += `<div class="tw-slide-quiz-question"><div class="tw-slide-quiz-q">${_html(q.question || '')}</div>`;
    html += '<div class="tw-slide-options tw-slide-quiz-options">';
    for (const opt of (q.options || [])) {
      const cls = opt.is_true ? 'tw-slide-option tw-quiz-correct' : 'tw-slide-option';
      html += `<div class="${cls}">${_html(opt.option || '')}</div>`;
    }
    html += '</div></div>';
  }
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category C: True/False ──
function _renderTrueFalse(c) {
  let html = '<div class="tw-slide-text-content tw-slide-quiz">';
  if (c.content_title) html += `<h3 class="tw-slide-text-title">${_html(c.content_title)}</h3>`;
  if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
  const questions = c.questions || [];
  for (const q of questions) {
    html += `<div class="tw-slide-quiz-question"><div class="tw-slide-quiz-q">${_html(q.question || '')}</div>`;
    html += `<div class="tw-slide-options"><div class="tw-slide-option ${q.answer === 'True' ? 'tw-quiz-correct' : ''}">True</div><div class="tw-slide-option ${q.answer === 'False' ? 'tw-quiz-correct' : ''}">False</div></div>`;
    if (q.true_statement) html += `<div class="tw-slide-quiz-explain"><em>${_html(q.true_statement)}</em></div>`;
    html += '</div>';
  }
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category C: Check Yes-or-No ──
function _renderCheckYesNo(c) {
  let html = '<div class="tw-slide-text-content tw-slide-checklist">';
  if (c.content_title) html += `<h3 class="tw-slide-text-title">${_html(c.content_title)}</h3>`;
  if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
  const items = c.question || [];
  if (Array.isArray(items)) {
    html += '<div class="tw-slide-checklist-items">';
    for (const item of items) {
      html += `<div class="tw-slide-checklist-item"><span class="tw-slide-check-box">&#9744;</span> <span>${_html(item)}</span></div>`;
    }
    html += '</div>';
  }
  if (c.moreThan2Message) html += `<div class="tw-slide-feedback tw-feedback-good">${_html(c.moreThan2Message)}</div>`;
  if (c.lessThan2Message) html += `<div class="tw-slide-feedback tw-feedback-improve">${_html(c.lessThan2Message)}</div>`;
  html += _backpackBadge(c);
  html += '</div>';
  return html;
}

// ── Category C: Select-range (Likert scale) ──
function _renderSelectRange(c) {
  let html = '<div class="tw-slide-text-content tw-slide-likert">';
  if (c.slide_title) html += `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>`;
  if (c.heading) html += `<div class="tw-slide-text-body">${_html(c.heading)}</div>`;
  const options = c.options || [];
  const questions = c.questions || [];
  html += '<div class="tw-slide-likert-table"><div class="tw-slide-likert-header"><div class="tw-slide-likert-q"></div>';
  for (const opt of options) html += `<div class="tw-slide-likert-opt">${_html(opt)}</div>`;
  html += '</div>';
  for (const q of questions) {
    html += `<div class="tw-slide-likert-row"><div class="tw-slide-likert-q">${_html(q)}</div>`;
    for (let i = 0; i < options.length; i++) html += `<div class="tw-slide-likert-opt"><span class="tw-slide-radio-circle"></span></div>`;
    html += '</div>';
  }
  html += '</div>';
  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category C: Word selection (three-word, select-one-word) ──
function _renderWordSelection(type, c) {
  let html = '<div class="tw-slide-text-content tw-slide-word-cloud">';
  if (c.slide_title) html += `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>`;
  if (type === 'three-word' && c.words) {
    const words = c.words.split(',').map(w => w.trim()).filter(Boolean);
    const max = parseInt(c.no_of_words, 10) || 3;
    html += `<div class="tw-slide-text-body" style="margin-bottom:1rem">Choose up to ${max} words:</div>`;
    html += '<div class="tw-slide-word-chips">';
    for (const w of words) html += `<span class="tw-slide-word-chip">${_esc(w)}</span>`;
    html += '</div>';
  } else if (type === 'select-one-word') {
    if (c.question) html += `<div class="tw-slide-text-body">${_html(c.question)}</div>`;
  } else {
    if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
  }
  if (c.options && Array.isArray(c.options) && type !== 'three-word') {
    html += '<div class="tw-slide-options">';
    for (const opt of c.options) {
      const text = typeof opt === 'string' ? opt : (opt.option || JSON.stringify(opt));
      html += `<div class="tw-slide-option">${_html(text)}</div>`;
    }
    html += '</div>';
  }
  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category C: Select-option family ──
function _renderSelectOption(type, c) {
  let html = '<div class="tw-slide-text-content tw-slide-select">';
  const title = c.card_title || c.slide_title || c.content_title || '';
  if (title) html += `<h3 class="tw-slide-text-title">${_html(title)}</h3>`;
  if (c.content_description) html += `<div class="tw-slide-text-body">${_html(c.content_description)}</div>`;
  if (c.option_title1) html += `<div class="tw-slide-text-body">${_html(c.option_title1)}</div>`;
  const options = c.options || [];
  if (options.length > 0) {
    html += '<div class="tw-slide-options">';
    for (const opt of options) {
      const text = typeof opt === 'string' ? opt : (opt.option || opt.label || JSON.stringify(opt));
      html += `<div class="tw-slide-option">${_html(text)}</div>`;
    }
    html += '</div>';
  }
  if (c.option_title2) html += `<div class="tw-slide-text-body" style="margin-top:1rem">${_html(c.option_title2)}</div>`;
  if (c.message) html += `<div class="tw-slide-note">${_html(c.message)}</div>`;
  if (c.feedback) html += `<div class="tw-slide-note">${_html(c.feedback)}</div>`;
  if (c.questions && Array.isArray(c.questions) && typeof c.questions[0] === 'string') {
    html += '<div class="tw-slide-questions" style="margin-top:1rem">';
    for (const q of c.questions) html += `<div class="tw-slide-question-item"><label>${_html(q)}</label></div>`;
    html += '</div>';
  }
  if (c.data && Array.isArray(c.data)) {
    html += '<div class="tw-slide-options">';
    for (const d of c.data) {
      if (d.right_option) html += `<div class="tw-slide-option tw-quiz-correct">${_html(d.right_option)}</div>`;
      if (d.wrong_option) html += `<div class="tw-slide-option">${_html(d.wrong_option)}</div>`;
      if (d.message) html += `<div class="tw-slide-feedback tw-feedback-improve">${_html(d.message)}</div>`;
    }
    html += '</div>';
  }
  if (c.images && Array.isArray(c.images)) {
    html += '<div class="tw-slide-image-examples">';
    for (let i = 0; i < c.images.length; i++) {
      html += `<div class="tw-slide-image-example-card"><img src="${_esc(c.images[i])}" alt="Option ${i + 1}" loading="lazy" onerror="this.style.display='none'"><div class="tw-slide-image-example-label">Option ${i + 1}</div></div>`;
    }
    html += '</div>';
    if (c.right_message) html += `<div class="tw-slide-feedback tw-feedback-good">${_html(c.right_message)}</div>`;
    if (c.wrong_message) html += `<div class="tw-slide-feedback tw-feedback-improve">${_html(c.wrong_message)}</div>`;
  }
  if (c.bonus_material && c.bonus_material.is_enable) {
    html += `<details class="tw-slide-expand-item" style="margin-top:1rem"><summary>${_html(c.bonus_material.title || 'Bonus Material')}</summary>`;
    html += `<div class="tw-slide-text-body">${_html(c.bonus_material.content || '')}</div></details>`;
  }
  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category C: Side-by-side dropdown selector ──
function _renderDropdownSelector(c) {
  let html = '<div class="tw-slide-text-content tw-slide-dropdown-selector">';
  if (c.slide_title) html += `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>`;
  const lhs = c.LHS_title || 'Statement';
  const rhs = c.RHS_title || 'Rating';
  const options = c.options || [];
  const questions = c.questions || [];
  html += `<div class="tw-slide-form-header"><div class="tw-slide-form-lhs">${_html(lhs)}</div><div class="tw-slide-form-rhs">${_html(rhs)}</div></div>`;
  for (const q of questions) {
    html += `<div class="tw-slide-form-row"><div class="tw-slide-form-lhs">${_html(q)}</div>`;
    html += '<div class="tw-slide-form-rhs"><select class="tw-slide-select-input">';
    html += '<option value="">Select...</option>';
    for (const opt of options) html += `<option>${_esc(opt)}</option>`;
    html += '</select></div></div>';
  }
  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category D: Side-by-side form ──
function _renderSideBySideForm(c) {
  let html = '<div class="tw-slide-text-content tw-slide-form">';
  if (c.slide_title) html += `<h3 class="tw-slide-text-title">${_html(c.slide_title)}</h3>`;
  const lTitle = c.lhs_title || 'Present';
  const rTitle = c.rhs_title || 'Future';
  const q = c.questions || {};
  const lhs = q.LHS || [];
  const rhs = q.RHS || [];
  const plhsL = q.placeholderLHS || [];
  const plhsR = q.placeholderRHS || [];
  const count = Math.max(lhs.length, rhs.length);
  html += `<div class="tw-slide-form-header"><div class="tw-slide-form-lhs">${_html(lTitle)}</div><div class="tw-slide-form-rhs">${_html(rTitle)}</div></div>`;
  for (let i = 0; i < count; i++) {
    html += '<div class="tw-slide-form-row">';
    html += `<div class="tw-slide-form-lhs"><label>${_html(lhs[i] || '')}</label><textarea class="tw-slide-textarea" rows="2" placeholder="${_esc(plhsL[i] || '')}"></textarea></div>`;
    html += `<div class="tw-slide-form-rhs"><label>${_html(rhs[i] || '')}</label><textarea class="tw-slide-textarea" rows="2" placeholder="${_esc(plhsR[i] || '')}"></textarea></div>`;
    html += '</div>';
  }
  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Category F: Special engagement types ──
function _renderEngagement(type, c) {
  let html = '<div class="tw-slide-text-content tw-slide-engagement">';
  const title = c.slide_title || c.content_title || c.card_title || '';
  if (title) html += `<h3 class="tw-slide-text-title">${_html(title)}</h3>`;

  if (type === 'celebrate') {
    if (c.content_description) html += `<div class="tw-slide-text-body">${_html(c.content_description)}</div>`;
    if (c.content_heading) html += `<div class="tw-slide-text-body"><strong>${_html(c.content_heading)}</strong></div>`;
  } else if (type === 'decision' || type === 'decision2') {
    const decisions = c.decision || [];
    if (Array.isArray(decisions)) {
      html += '<div class="tw-slide-options">';
      for (const d of decisions) html += `<div class="tw-slide-option"><strong>${_html(d.title || '')}</strong><div>${_html(d.content || '')}</div></div>`;
      html += '</div>';
    }
  } else if (type === 'chat-interface') {
    const pairs = c.options || [];
    html += '<div class="tw-slide-chat">';
    for (const p of pairs) {
      html += `<div class="tw-slide-chat-q">${_html(p.question || '')}</div>`;
      html += `<div class="tw-slide-chat-a">${_html(p.answer || '')}</div>`;
    }
    html += '</div>';
  } else if (type === 'build-your-network') {
    if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
    const cats = c.options || [];
    for (const cat of cats) {
      html += `<details class="tw-slide-expand-item"><summary>${_html(cat.card_title || '')}</summary>`;
      const qs = cat.question || [];
      for (let i = 0; i < qs.length; i++) {
        html += `<div class="tw-slide-question-item"><label>${_html(qs[i])}</label></div>`;
      }
      html += '</details>';
    }
  } else if (type === 'show-gratitude') {
    if (c.content_description) html += `<div class="tw-slide-text-body">${_html(c.content_description)}</div>`;
    if (c.card_title) html += `<div class="tw-slide-text-body"><strong>${_html(c.card_title)}</strong></div>`;
  } else {
    if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
    if (c.content_description) html += `<div class="tw-slide-text-body">${_html(c.content_description)}</div>`;
  }

  html += _backpackBadge(c);
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Fallback: unknown type ──
function _renderFallback(type, c) {
  let html = '<div class="tw-slide-text-content tw-slide-fallback">';
  html += `<div class="tw-slide-text-body" style="opacity:0.6;font-size:0.85rem">Type: ${_esc(type)}</div>`;
  const title = c.slide_title || c.card_title || c.content_title || '';
  if (title) html += `<h3 class="tw-slide-text-title">${_html(title)}</h3>`;
  const text = c.content || c.message || c.greetings || c.appreciation || c.card_content || '';
  if (text) html += `<div class="tw-slide-text-body">${_html(text)}</div>`;
  if (!title && !text) html += `<pre class="tw-slide-json">${_esc(JSON.stringify(c, null, 2))}</pre>`;
  html += _headsUp(c);
  html += '</div>';
  return html;
}
