// ==========================================================================
// CONTENT-360.JS — Full Lesson Intelligence Dashboard
// Left: filterable lesson list, Right: expanded 360 view of selected lesson
// ==========================================================================

import { getState, setState, subscribe, markFetched, isFresh } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { openSlideViewer } from '../components/slide-viewer.js';

// ── Constants ──────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 300;

// Direction → color mapping for trait tags
const DIRECTION_COLORS = {
  builds: { bg: '#dcfce7', fg: '#166534', border: '#86efac' },
  leverages: { bg: '#dbeafe', fg: '#1e40af', border: '#93c5fd' },
  challenges: { bg: '#fff7ed', fg: '#9a3412', border: '#fdba74' },
};

const DIFFICULTY_COLORS = ['', '#22c55e', '#22c55e', '#eab308', '#f97316', '#ef4444'];
const DIFFICULTY_LABELS = ['', 'Beginner', 'Easy', 'Moderate', 'Advanced', 'Expert'];

const STYLE_ICONS = {
  visual: '\u{1F3A8}',
  reflective: '\u{1F4AD}',
  active: '\u26A1',
  theoretical: '\u{1F4D6}',
  blended: '\u{1F504}',
};

const TONE_COLORS = {
  motivational: '#f59e0b',
  empathetic: '#ec4899',
  analytical: '#3b82f6',
  challenging: '#ef4444',
  supportive: '#22c55e',
  neutral: '#6b7280',
};

// Known EPP traits for tag editor
const EPP_TRAITS = [
  'Achievement', 'Assertiveness', 'Attention to Detail', 'Cooperativeness',
  'Creativity', 'Dependability', 'Flexibility', 'Initiative',
  'Leadership', 'Optimism', 'Patience', 'Persistence',
  'Self-Confidence', 'Self-Control', 'Social Orientation', 'Stress Tolerance',
];

// ── Module state ───────────────────────────────────────────────────────────

let _lessons = [];
let _filteredLessons = [];
let _selectedLessonId = null;
let _selectedDetail = null;
let _journeys = [];
let _stats = {};
let _viewMode = 'grid'; // 'grid' | 'list'
let _searchTimer = null;
let _loading = false;
let _detailLoading = false;

// ── Render Entry Point ─────────────────────────────────────────────────────

export function renderContent360(root) {
  const container = h('div', { class: 'c360-layout' });
  container.innerHTML = `
    <!-- Top Bar -->
    <div class="c360-topbar">
      <div class="c360-topbar-left">
        <span class="c360-topbar-title">Content 360</span>
        <span class="c360-topbar-stats" id="c360-stats"></span>
      </div>
      <div class="c360-topbar-right">
        <div class="c360-view-toggle" id="c360-view-toggle">
          <button class="c360-vt-btn active" data-mode="grid" title="Grid view">&#9638;</button>
          <button class="c360-vt-btn" data-mode="list" title="List view">&#9776;</button>
        </div>
      </div>
    </div>

    <!-- Main Area: Left sidebar + Right detail -->
    <div class="c360-main">
      <!-- Left: Lesson List -->
      <div class="c360-left" id="c360-left">
        <div class="c360-left-header">
          <div class="c360-search-row">
            <span class="c360-search-icon">&#128269;</span>
            <input type="text" id="c360-search" placeholder="Search lessons, concepts...">
          </div>
          <div class="c360-filters">
            <select id="c360-filter-journey"><option value="">All Journeys</option></select>
            <select id="c360-filter-difficulty">
              <option value="">All Difficulty</option>
              <option value="1">Beginner (1)</option>
              <option value="2">Easy (2)</option>
              <option value="3">Moderate (3)</option>
              <option value="4">Advanced (4)</option>
              <option value="5">Expert (5)</option>
            </select>
            <select id="c360-filter-style">
              <option value="">All Styles</option>
              <option value="visual">Visual</option>
              <option value="reflective">Reflective</option>
              <option value="active">Active</option>
              <option value="theoretical">Theoretical</option>
              <option value="blended">Blended</option>
            </select>
            <select id="c360-filter-tone">
              <option value="">All Tones</option>
              <option value="motivational">Motivational</option>
              <option value="empathetic">Empathetic</option>
              <option value="analytical">Analytical</option>
              <option value="challenging">Challenging</option>
              <option value="supportive">Supportive</option>
            </select>
          </div>
        </div>
        <div class="c360-lesson-list" id="c360-lesson-list"></div>
      </div>

      <!-- Right: Detail View -->
      <div class="c360-right" id="c360-right">
        <div class="c360-placeholder" id="c360-placeholder">
          <div class="c360-placeholder-icon">&#128218;</div>
          <div class="c360-placeholder-text">Select a lesson to view its 360 profile</div>
        </div>
        <div class="c360-detail" id="c360-detail" style="display:none"></div>
      </div>
    </div>
  `;

  root.innerHTML = '';
  root.appendChild(container);

  _bindEvents(container);
  _loadLessons();
}

// ── Event Binding ──────────────────────────────────────────────────────────

function _bindEvents(container) {
  // Search
  const searchInput = container.querySelector('#c360-search');
  searchInput?.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => _applyFilters(container), DEBOUNCE_MS);
  });

  // Filters
  ['#c360-filter-journey', '#c360-filter-difficulty', '#c360-filter-style', '#c360-filter-tone'].forEach(sel => {
    container.querySelector(sel)?.addEventListener('change', () => _applyFilters(container));
  });

  // View toggle
  container.querySelector('#c360-view-toggle')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.c360-vt-btn');
    if (!btn) return;
    _viewMode = btn.dataset.mode;
    container.querySelectorAll('.c360-vt-btn').forEach(b => b.classList.toggle('active', b === btn));
    _renderLessonList(container);
  });
}

// ── Data Loading ───────────────────────────────────────────────────────────

async function _loadLessons() {
  _loading = true;
  const container = document.querySelector('.c360-layout');
  if (!container) return;

  const listEl = container.querySelector('#c360-lesson-list');
  if (listEl) listEl.innerHTML = '<div class="c360-loading">Loading lessons...</div>';

  try {
    const data = await api.getContent360();
    _lessons = data.lessons || [];
    _journeys = data.journeys || [];
    _stats = data.stats || {};

    // Populate journey filter
    const journeySelect = container.querySelector('#c360-filter-journey');
    if (journeySelect) {
      journeySelect.innerHTML = '<option value="">All Journeys</option>';
      _journeys.forEach(j => {
        const opt = document.createElement('option');
        opt.value = j;
        opt.textContent = j;
        journeySelect.appendChild(opt);
      });
    }

    // Update stats bar
    _renderStats(container);

    _filteredLessons = _lessons;
    _applyFilters(container);
  } catch (err) {
    console.error('Content 360 load failed:', err);
    if (listEl) listEl.innerHTML = `<div class="c360-error">Failed to load: ${err.message}</div>`;
  } finally {
    _loading = false;
  }
}

function _renderStats(container) {
  const statsEl = container.querySelector('#c360-stats');
  if (!statsEl) return;
  const tagged = _stats.tagged || 0;
  const total = _stats.total || _lessons.length;
  statsEl.innerHTML = `
    <span class="c360-stat">${total} lessons</span>
    <span class="c360-stat-sep">&middot;</span>
    <span class="c360-stat">${tagged} AI-tagged</span>
    <span class="c360-stat-sep">&middot;</span>
    <span class="c360-stat">${total - tagged} basic</span>
  `;
}

// ── Filtering ──────────────────────────────────────────────────────────────

function _applyFilters(container) {
  const search = (container.querySelector('#c360-search')?.value || '').toLowerCase().trim();
  const journey = container.querySelector('#c360-filter-journey')?.value || '';
  const difficulty = container.querySelector('#c360-filter-difficulty')?.value || '';
  const style = container.querySelector('#c360-filter-style')?.value || '';
  const tone = container.querySelector('#c360-filter-tone')?.value || '';

  _filteredLessons = _lessons.filter(l => {
    if (journey && l.journey_name !== journey) return false;
    if (difficulty && l.difficulty !== parseInt(difficulty)) return false;
    if (style && l.learning_style !== style) return false;
    if (tone && l.emotional_tone !== tone) return false;
    if (search) {
      const haystack = [
        l.lesson_name,
        l.summary,
        l.journey_name,
        l.chapter_name,
        Array.isArray(l.key_concepts) ? l.key_concepts.join(' ') : (l.key_concepts || ''),
      ].join(' ').toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });

  _renderLessonList(container);
}

// ── Lesson List Rendering ──────────────────────────────────────────────────

function _renderLessonList(container) {
  const listEl = container.querySelector('#c360-lesson-list');
  if (!listEl) return;

  if (_filteredLessons.length === 0) {
    listEl.innerHTML = '<div class="c360-empty">No lessons match your filters</div>';
    return;
  }

  if (_viewMode === 'list') {
    _renderListView(listEl);
  } else {
    _renderGridView(listEl);
  }
}

function _renderGridView(listEl) {
  listEl.className = 'c360-lesson-list c360-grid-mode';
  listEl.innerHTML = _filteredLessons.map(l => `
    <div class="c360-card ${_selectedLessonId === l.lesson_detail_id ? 'selected' : ''}"
         data-id="${l.lesson_detail_id}">
      <div class="c360-card-header">
        <div class="c360-card-title">${_esc(l.lesson_name || 'Untitled')}</div>
        <div class="c360-card-breadcrumb">${_esc(l.journey_name || '')} ${l.chapter_name ? '&rsaquo; ' + _esc(l.chapter_name) : ''}</div>
      </div>
      ${l.summary ? `<div class="c360-card-summary">${_esc(_truncate(l.summary, 120))}</div>` : ''}
      <div class="c360-card-badges">
        ${_difficultyBadge(l.difficulty)}
        ${l.estimated_minutes ? `<span class="c360-badge c360-badge-time">${l.estimated_minutes}m</span>` : ''}
        ${l.learning_style ? `<span class="c360-badge c360-badge-style">${STYLE_ICONS[l.learning_style] || ''} ${l.learning_style}</span>` : ''}
        <span class="c360-badge c360-badge-slides">${l.slide_count} slides</span>
        ${l.emotional_tone ? `<span class="c360-badge c360-badge-tone" style="background:${TONE_COLORS[l.emotional_tone] || '#6b7280'}20;color:${TONE_COLORS[l.emotional_tone] || '#6b7280'}">${l.emotional_tone}</span>` : ''}
      </div>
      ${_renderKeyConceptPills(l.key_concepts)}
      ${l.content_quality ? _renderQualityStars(l.content_quality) : ''}
      ${!l.tag_id ? '<div class="c360-card-untagged">Basic info only</div>' : ''}
    </div>
  `).join('');

  // Click handlers
  listEl.querySelectorAll('.c360-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = parseInt(card.dataset.id);
      _selectLesson(id);
    });
  });
}

function _renderListView(listEl) {
  listEl.className = 'c360-lesson-list c360-list-mode';
  listEl.innerHTML = `
    <table class="c360-table">
      <thead>
        <tr>
          <th>Lesson</th>
          <th>Journey</th>
          <th>Slides</th>
          <th>Diff</th>
          <th>Style</th>
          <th>Tone</th>
          <th>Time</th>
          <th>Quality</th>
        </tr>
      </thead>
      <tbody>
        ${_filteredLessons.map(l => `
          <tr class="c360-table-row ${_selectedLessonId === l.lesson_detail_id ? 'selected' : ''}"
              data-id="${l.lesson_detail_id}">
            <td class="c360-table-name">${_esc(l.lesson_name || 'Untitled')}</td>
            <td>${_esc(l.journey_name || '-')}</td>
            <td>${l.slide_count}</td>
            <td>${_difficultyBadge(l.difficulty)}</td>
            <td>${l.learning_style ? STYLE_ICONS[l.learning_style] + ' ' + l.learning_style : '-'}</td>
            <td>${l.emotional_tone || '-'}</td>
            <td>${l.estimated_minutes ? l.estimated_minutes + 'm' : '-'}</td>
            <td>${l.content_quality ? _renderQualityStarsInline(l.content_quality) : '-'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;

  listEl.querySelectorAll('.c360-table-row').forEach(row => {
    row.addEventListener('click', () => {
      const id = parseInt(row.dataset.id);
      _selectLesson(id);
    });
  });
}

// ── Lesson Selection & Detail ──────────────────────────────────────────────

async function _selectLesson(lessonDetailId) {
  _selectedLessonId = lessonDetailId;
  const container = document.querySelector('.c360-layout');
  if (!container) return;

  // Highlight in list
  container.querySelectorAll('.c360-card, .c360-table-row').forEach(el => {
    el.classList.toggle('selected', parseInt(el.dataset.id) === lessonDetailId);
  });

  const placeholder = container.querySelector('#c360-placeholder');
  const detailEl = container.querySelector('#c360-detail');
  if (placeholder) placeholder.style.display = 'none';
  if (detailEl) {
    detailEl.style.display = 'block';
    detailEl.innerHTML = '<div class="c360-loading">Loading lesson detail...</div>';
  }

  try {
    const detail = await api.getContent360Detail(lessonDetailId);
    _selectedDetail = detail;
    _renderDetail(container, detail);
  } catch (err) {
    console.error('Detail load failed:', err);
    if (detailEl) detailEl.innerHTML = `<div class="c360-error">Failed: ${err.message}</div>`;
  }
}

function _renderDetail(container, d) {
  const detailEl = container.querySelector('#c360-detail');
  if (!detailEl) return;

  const hasAI = !!d.tag_id;

  detailEl.innerHTML = `
    <!-- Header -->
    <div class="c360-detail-header">
      <div class="c360-detail-breadcrumb">${_esc(d.journey_name || '')} ${d.chapter_name ? '&rsaquo; ' + _esc(d.chapter_name) : ''}</div>
      <h2 class="c360-detail-title">${_esc(d.lesson_name || 'Untitled')}</h2>
      <div class="c360-detail-badges">
        ${_difficultyBadge(d.difficulty)}
        ${d.estimated_minutes ? `<span class="c360-badge c360-badge-time">${d.estimated_minutes} min</span>` : ''}
        ${d.learning_style ? `<span class="c360-badge c360-badge-style">${STYLE_ICONS[d.learning_style] || ''} ${d.learning_style}</span>` : ''}
        <span class="c360-badge c360-badge-slides">${d.slide_count} slides</span>
        ${d.slide_count > 0 ? `<button class="c360-btn-view-slides" data-ld-id="${d.lesson_detail_id}" data-name="${_escAttr(d.lesson_name || 'Slides')}">&#9654; View Slides</button>` : ''}
        ${d.emotional_tone ? `<span class="c360-badge c360-badge-tone" style="background:${TONE_COLORS[d.emotional_tone] || '#6b7280'}20;color:${TONE_COLORS[d.emotional_tone] || '#6b7280'}">${d.emotional_tone}</span>` : ''}
        ${d.target_seniority ? `<span class="c360-badge c360-badge-seniority">${d.target_seniority}</span>` : ''}
        ${d.confidence ? `<span class="c360-badge c360-badge-confidence">AI ${d.confidence}%</span>` : ''}
      </div>
      ${d.content_quality ? _renderQualityStarsBlock(d.content_quality) : ''}
    </div>

    ${!hasAI ? `
      <div class="c360-no-ai-banner">
        <span class="c360-no-ai-icon">&#9432;</span>
        AI metadata not yet generated. Showing basic lesson information.
      </div>
    ` : ''}

    <!-- Summary -->
    ${d.summary ? `
      <div class="c360-section">
        <h3 class="c360-section-title">Summary</h3>
        <p class="c360-summary-text">${_esc(d.summary)}</p>
      </div>
    ` : ''}

    <!-- Key Concepts -->
    ${_renderKeyConceptsSection(d.key_concepts)}

    <!-- Learning Objectives -->
    ${_renderObjectivesSection(d.learning_objectives)}

    <!-- EPP Trait Tags -->
    ${_renderTraitTagsSection(d.trait_tags)}

    <!-- Tag Review Actions -->
    ${hasAI ? `
      <div class="c360-section c360-review-section">
        <div class="c360-review-bar">
          <span class="c360-review-status">Review: <strong>${_esc(d.review_status || 'pending')}</strong></span>
          <span class="c360-review-confidence">Confidence: <strong>${Math.round(d.confidence || 0)}%</strong></span>
          <div class="c360-review-actions">
            <button class="c360-btn c360-btn-approve" data-tag-id="${d.tag_id}">Approve</button>
            <button class="c360-btn c360-btn-dismiss" data-tag-id="${d.tag_id}">Dismiss</button>
            <button class="c360-btn c360-btn-edit-tags" data-tag-id="${d.tag_id}">Edit Tags</button>
          </div>
        </div>
        <div class="c360-tag-editor" id="c360-tag-editor" style="display:none">
          <div class="c360-tag-editor-title">Edit Tags</div>
          <div id="c360-tag-editor-rows"></div>
          <button class="c360-btn c360-btn-add-row" id="c360-tag-add-row">+ Add Tag</button>
          <div class="c360-tag-editor-actions">
            <button class="c360-btn c360-btn-cancel" id="c360-tag-cancel">Cancel</button>
            <button class="c360-btn c360-btn-save" id="c360-tag-save" data-tag-id="${d.tag_id}">Save Tags</button>
          </div>
        </div>
      </div>
    ` : ''}

    <!-- Coaching Prompts -->
    ${_renderCoachingPromptsSection(d.coaching_prompts)}

    <!-- Slide Analysis Timeline -->
    ${_renderSlideAnalysisSection(d.slide_analysis, d.slides)}

    <!-- Pair Recommendations -->
    ${_renderPairRecommendationsSection(d.pair_recommendations)}

    <!-- Slide Breakdown -->
    ${_renderSlideBreakdownSection(d.slides)}
  `;

  // Bind coaching prompt copy buttons
  detailEl.querySelectorAll('.c360-copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const text = btn.dataset.text;
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
      });
    });
  });

  // Bind expandable prompts
  detailEl.querySelectorAll('.c360-prompt-card').forEach(card => {
    card.addEventListener('click', () => card.classList.toggle('expanded'));
  });

  // Bind pair recommendation clicks
  detailEl.querySelectorAll('.c360-pair-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = parseInt(card.dataset.id);
      if (id) _selectLesson(id);
    });
  });

  // Bind View Slides button
  detailEl.querySelector('.c360-btn-view-slides')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const btn = e.currentTarget;
    const ldId = parseInt(btn.dataset.ldId);
    const name = btn.dataset.name;
    if (ldId) openSlideViewer(ldId, name);
  });

  // ── Tag Review Actions ──
  _bindTagReviewActions(detailEl, d);
}

// ── Tag Review Actions ──────────────────────────────────────────────────────

function _bindTagReviewActions(detailEl, d) {
  if (!d.tag_id) return;

  const traitTags = Array.isArray(d.trait_tags) ? d.trait_tags : [];

  // Approve
  detailEl.querySelector('.c360-btn-approve')?.addEventListener('click', async (e) => {
    const tagId = parseInt(e.target.dataset.tagId, 10);
    if (!tagId) return;
    try {
      await api.reviewApprove(tagId, 0, '');
      showToast('Tag approved', 'success');
      if (_selectedLessonId) _selectLesson(_selectedLessonId);
    } catch (err) {
      showToast(`Approve failed: ${err.message}`, 'error');
    }
  });

  // Dismiss
  detailEl.querySelector('.c360-btn-dismiss')?.addEventListener('click', async (e) => {
    const tagId = parseInt(e.target.dataset.tagId, 10);
    if (!tagId) return;
    try {
      await api.reviewDismiss(tagId, 0, 'Dismissed via Content 360');
      showToast('Tag dismissed', 'success');
      if (_selectedLessonId) _selectLesson(_selectedLessonId);
    } catch (err) {
      showToast(`Dismiss failed: ${err.message}`, 'error');
    }
  });

  // Edit Tags toggle
  detailEl.querySelector('.c360-btn-edit-tags')?.addEventListener('click', () => {
    const editor = detailEl.querySelector('#c360-tag-editor');
    if (!editor) return;
    const isVisible = editor.style.display !== 'none';
    editor.style.display = isVisible ? 'none' : '';
    if (!isVisible) _populateTagEditor(detailEl, traitTags);
  });

  // Cancel
  detailEl.querySelector('#c360-tag-cancel')?.addEventListener('click', () => {
    const editor = detailEl.querySelector('#c360-tag-editor');
    if (editor) editor.style.display = 'none';
  });

  // Add Row
  detailEl.querySelector('#c360-tag-add-row')?.addEventListener('click', () => {
    _addTagEditorRow(detailEl.querySelector('#c360-tag-editor-rows'), null);
  });

  // Save Tags
  detailEl.querySelector('#c360-tag-save')?.addEventListener('click', async (e) => {
    const tagId = parseInt(e.target.dataset.tagId, 10);
    if (!tagId) return;
    const rows = detailEl.querySelectorAll('.c360-tag-row');
    const correctedTags = [];
    rows.forEach(row => {
      const trait = row.querySelector('.c360-tag-trait')?.value;
      const score = parseInt(row.querySelector('.c360-tag-relevance')?.value || '50', 10);
      const direction = row.querySelector('.c360-tag-direction')?.value || 'builds';
      if (trait) correctedTags.push({ trait, relevance_score: score, direction });
    });
    try {
      await api.reviewCorrect(tagId, 0, correctedTags);
      showToast('Tags updated', 'success');
      if (_selectedLessonId) _selectLesson(_selectedLessonId);
    } catch (err) {
      showToast(`Tag correction failed: ${err.message}`, 'error');
    }
  });
}

function _populateTagEditor(container, existingTags) {
  const rows = container.querySelector('#c360-tag-editor-rows');
  if (!rows) return;
  rows.innerHTML = '';
  if (!existingTags || existingTags.length === 0) {
    _addTagEditorRow(rows, null);
  } else {
    for (const tag of existingTags) {
      _addTagEditorRow(rows, tag);
    }
  }
}

function _addTagEditorRow(container, tag) {
  if (!container) return;
  const row = document.createElement('div');
  row.className = 'c360-tag-row';
  row.innerHTML = `
    <select class="c360-tag-trait">
      <option value="">Select trait...</option>
      ${EPP_TRAITS.map(t => `<option value="${_esc(t)}" ${tag && tag.trait === t ? 'selected' : ''}>${_esc(t)}</option>`).join('')}
    </select>
    <input type="range" class="c360-tag-relevance" min="0" max="100" value="${tag ? tag.relevance_score || 50 : 50}">
    <span class="c360-tag-relevance-val">${tag ? tag.relevance_score || 50 : 50}</span>
    <select class="c360-tag-direction">
      <option value="builds" ${tag && tag.direction === 'builds' ? 'selected' : ''}>builds</option>
      <option value="leverages" ${tag && tag.direction === 'leverages' ? 'selected' : ''}>leverages</option>
      <option value="challenges" ${tag && tag.direction === 'challenges' ? 'selected' : ''}>challenges</option>
    </select>
    <button class="c360-tag-remove" title="Remove">&times;</button>
  `;

  const range = row.querySelector('.c360-tag-relevance');
  const rangeVal = row.querySelector('.c360-tag-relevance-val');
  range.addEventListener('input', () => { rangeVal.textContent = range.value; });
  row.querySelector('.c360-tag-remove').addEventListener('click', () => row.remove());

  container.appendChild(row);
}

// ── Section Renderers ──────────────────────────────────────────────────────

function _renderKeyConceptPills(concepts) {
  if (!concepts || (Array.isArray(concepts) && concepts.length === 0)) return '';
  const items = Array.isArray(concepts) ? concepts : [concepts];
  if (items.length === 0) return '';
  return `<div class="c360-concept-pills">${items.slice(0, 4).map(c =>
    `<span class="c360-pill">${_esc(String(c))}</span>`
  ).join('')}${items.length > 4 ? `<span class="c360-pill c360-pill-more">+${items.length - 4}</span>` : ''}</div>`;
}

function _renderKeyConceptsSection(concepts) {
  if (!concepts || (Array.isArray(concepts) && concepts.length === 0)) return '';
  const items = Array.isArray(concepts) ? concepts : [concepts];
  return `
    <div class="c360-section">
      <h3 class="c360-section-title">Key Concepts</h3>
      <div class="c360-concept-pills">
        ${items.map(c => `<span class="c360-pill">${_esc(String(c))}</span>`).join('')}
      </div>
    </div>
  `;
}

function _renderObjectivesSection(objectives) {
  if (!objectives || (Array.isArray(objectives) && objectives.length === 0)) return '';
  const items = Array.isArray(objectives) ? objectives : [objectives];
  return `
    <div class="c360-section">
      <h3 class="c360-section-title">Learning Objectives</h3>
      <ul class="c360-objectives-list">
        ${items.map(o => `<li class="c360-objective-item"><span class="c360-check">&#10003;</span> ${_esc(String(o))}</li>`).join('')}
      </ul>
    </div>
  `;
}

function _renderTraitTagsSection(traitTags) {
  if (!traitTags || (Array.isArray(traitTags) && traitTags.length === 0)) return '';
  const tags = Array.isArray(traitTags) ? traitTags : [];
  if (tags.length === 0) return '';

  return `
    <div class="c360-section">
      <h3 class="c360-section-title">EPP Trait Mapping</h3>
      <div class="c360-trait-bars">
        ${tags.map(t => {
          const dir = t.direction || 'builds';
          const colors = DIRECTION_COLORS[dir] || DIRECTION_COLORS.builds;
          const score = t.relevance_score || 0;
          return `
            <div class="c360-trait-row">
              <div class="c360-trait-label">
                <span class="c360-trait-name">${_esc(t.trait || '')}</span>
                <span class="c360-trait-dir" style="background:${colors.bg};color:${colors.fg};border:1px solid ${colors.border}">${dir}</span>
              </div>
              <div class="c360-trait-bar-bg">
                <div class="c360-trait-bar-fill" style="width:${score}%;background:${colors.fg}"></div>
              </div>
              <span class="c360-trait-score">${score}</span>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function _renderCoachingPromptsSection(prompts) {
  if (!prompts || (Array.isArray(prompts) && prompts.length === 0)) return '';
  const items = Array.isArray(prompts) ? prompts : [prompts];
  if (items.length === 0) return '';

  return `
    <div class="c360-section">
      <h3 class="c360-section-title">Coaching Prompts</h3>
      <div class="c360-prompts">
        ${items.map((p, i) => {
          const text = typeof p === 'string' ? p : (p.prompt || p.text || JSON.stringify(p));
          return `
            <div class="c360-prompt-card">
              <div class="c360-prompt-header">
                <span class="c360-prompt-num">${i + 1}</span>
                <span class="c360-prompt-preview">${_esc(_truncate(text, 80))}</span>
                <button class="c360-copy-btn" data-text="${_escAttr(text)}">Copy</button>
              </div>
              <div class="c360-prompt-body">${_esc(text)}</div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function _renderSlideAnalysisSection(analysis, slides) {
  if (!analysis && (!slides || slides.length === 0)) return '';

  // If we have structured slide_analysis, group by phase and show summary
  if (analysis && Array.isArray(analysis) && analysis.length > 0) {
    // Group consecutive same-phase slides into segments
    const segments = [];
    let current = null;
    for (const s of analysis) {
      const phase = s.phase || s.role || 'core';
      if (current && current.phase === phase) {
        current.count++;
        if (s.description) current.descriptions.push(s.description);
        current.importance = Math.max(current.importance, s.importance || s.importance_score || 5);
      } else {
        current = { phase, count: 1, descriptions: s.description ? [s.description] : [], importance: s.importance || s.importance_score || 5, type: s.type || s.slide_type || '' };
        segments.push(current);
      }
    }

    const PHASE_COLORS = { intro: '#3b82f6', core: '#8b5cf6', exercise: '#f59e0b', reflection: '#ec4899', summary: '#22c55e', 'warm-up': '#3b82f6', 'wrap-up': '#22c55e' };

    return `
      <div class="c360-section">
        <h3 class="c360-section-title">Slide Flow (${analysis.length} slides)</h3>
        <div class="c360-slide-flow">
          ${segments.map(seg => {
            const color = PHASE_COLORS[seg.phase] || '#6b7280';
            const width = Math.max(20, (seg.count / analysis.length) * 100);
            return `<div class="c360-flow-segment" style="flex:${seg.count};background:${color}20;border:1px solid ${color}40" title="${seg.phase}: ${seg.count} slide${seg.count > 1 ? 's' : ''}">
              <span class="c360-flow-label" style="color:${color}">${_esc(seg.phase)}</span>
              <span class="c360-flow-count">${seg.count}</span>
            </div>`;
          }).join('')}
        </div>
        <div class="c360-phase-legend">
          ${[...new Set(segments.map(s => s.phase))].map(phase => {
            const color = PHASE_COLORS[phase] || '#6b7280';
            return `<span class="c360-legend-item"><span class="c360-legend-dot" style="background:${color}"></span>${_esc(phase)}</span>`;
          }).join('')}
        </div>
      </div>
    `;
  }

  // Fallback: if we only have raw slides, show type breakdown
  if (slides && slides.length > 0) {
    const typeCounts = {};
    slides.forEach(s => { typeCounts[s.type] = (typeCounts[s.type] || 0) + 1; });
    return `
      <div class="c360-section">
        <h3 class="c360-section-title">Slide Types</h3>
        <div class="c360-slide-types">
          ${Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).map(([type, count]) => `
            <span class="c360-slide-type-pill">${_esc(type)} <strong>${count}</strong></span>
          `).join('')}
        </div>
      </div>
    `;
  }

  return '';
}

function _renderPairRecommendationsSection(pairs) {
  if (!pairs || (Array.isArray(pairs) && pairs.length === 0)) return '';
  const items = Array.isArray(pairs) ? pairs : [pairs];
  if (items.length === 0) return '';

  return `
    <div class="c360-section">
      <h3 class="c360-section-title">Related Lessons</h3>
      <div class="c360-pairs">
        ${items.map(p => {
          const id = p.lesson_detail_id || p.id || null;
          const name = p.lesson_name || p.title || p.name || 'Related Lesson';
          const reason = p.reason || p.shared_dimensions || '';
          return `
            <div class="c360-pair-card" data-id="${id || ''}" ${id ? 'style="cursor:pointer"' : ''}>
              <div class="c360-pair-name">${_esc(String(name))}</div>
              ${reason ? `<div class="c360-pair-reason">${_esc(String(reason))}</div>` : ''}
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function _renderSlideBreakdownSection(slides) {
  if (!slides || slides.length === 0) return '';

  return `
    <div class="c360-section">
      <h3 class="c360-section-title">Slides (${slides.length})</h3>
      <div class="c360-slides-grid">
        ${slides.map((s, i) => `
          <div class="c360-slide-chip">
            <span class="c360-slide-num">${i + 1}</span>
            <span class="c360-slide-type">${_esc(s.type || 'unknown')}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

// ── Badge Renderers ────────────────────────────────────────────────────────

function _difficultyBadge(d) {
  if (!d) return '';
  return `<span class="c360-badge c360-badge-diff" style="background:${DIFFICULTY_COLORS[d]}20;color:${DIFFICULTY_COLORS[d]};border:1px solid ${DIFFICULTY_COLORS[d]}40">${DIFFICULTY_LABELS[d] || d}</span>`;
}

function _renderQualityStars(quality) {
  const score = _extractQualityScore(quality);
  if (score === null) return '';
  const full = Math.floor(score);
  const half = score - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return `<div class="c360-card-quality">${'\u2605'.repeat(full)}${half ? '\u00BD' : ''}${'&#9734;'.repeat(empty)}</div>`;
}

function _renderQualityStarsInline(quality) {
  const score = _extractQualityScore(quality);
  if (score === null) return '-';
  return `${score.toFixed(1)}`;
}

function _renderQualityStarsBlock(quality) {
  const score = _extractQualityScore(quality);
  if (score === null) return '';
  const full = Math.floor(score);
  const half = score - full >= 0.5 ? 1 : 0;
  return `
    <div class="c360-quality-block">
      <span class="c360-quality-stars">${'\u2605'.repeat(full)}${half ? '\u2BEA' : ''}${'\u2606'.repeat(5 - full - half)}</span>
      <span class="c360-quality-score">${score.toFixed(1)}/5</span>
    </div>
  `;
}

function _extractQualityScore(quality) {
  if (!quality) return null;
  if (typeof quality === 'number') return quality;
  if (typeof quality === 'object') {
    return quality.overall || quality.score || quality.rating || null;
  }
  const num = parseFloat(quality);
  return isNaN(num) ? null : num;
}

// ── Utilities ──────────────────────────────────────────────────────────────

function _esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function _escAttr(str) {
  return (str || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;');
}

function _truncate(str, max) {
  if (!str || str.length <= max) return str || '';
  return str.slice(0, max) + '...';
}
