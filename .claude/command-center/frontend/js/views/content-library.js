// ==========================================================================
// CONTENT-LIBRARY.JS — Content Tab: lesson library by journey with
// tag management and Azure Blob content viewer
// ==========================================================================

import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';

// Default reviewer ID (coach/admin). In production, this would come from auth.
const REVIEWER_ID = 1;

// EPP trait list for the tag editor
const EPP_TRAITS = [
  'Achievement', 'Motivation', 'Competitiveness', 'Goal_Setting',
  'Planning', 'Initiative', 'Team_Player', 'Manageability',
  'Decisiveness', 'Accommodation', 'Savvy', 'Dominance',
  'Self_Confidence', 'Empathy', 'Helpfulness', 'Sociability',
  'Approval_Seeking', 'Self_Disclosure', 'Composure',
  'Positive_About_People', 'Social_Desirability',
  'Energy', 'Stress_Tolerance', 'Openness_To_Feedback',
  'JobFit_Accountability', 'JobFit_Interpersonal_Skills',
  'JobFit_Management_Leadership', 'JobFit_Motivational_Fit',
  'JobFit_Self_Management',
];

// Module state
let _data = null;         // { journeys, tag_count, review_stats }
let _filter = 'all';      // review status filter
let _container = null;     // root container ref
let _viewerSlides = null;  // slides for the content viewer modal
let _viewerIndex = 0;      // current slide index

// ── Public API ────────────────────────────────────────────────────────────

/**
 * Render the Content tab into a container element.
 * Called by the workspace shell when the Content tab is active.
 */
export async function renderContentTab(container) {
  _container = container;
  container.innerHTML = '';

  // Toolbar
  container.appendChild(_buildToolbar());

  // Loading state
  const loading = h('div', { class: 'cl-loading' });
  loading.innerHTML = '<div class="view-loading-spinner"></div><span>Loading content library...</span>';
  container.appendChild(loading);

  try {
    _data = await api.getContentLibrary(_filter === 'all' ? null : _filter);
    loading.remove();
    _renderLibrary();
  } catch (err) {
    loading.remove();
    const errEl = h('div', { class: 'dash-alert' });
    errEl.innerHTML = `<span class="dash-alert-icon">\u26A0</span><span>Failed to load content library: ${_esc(err.message)}</span>`;
    container.appendChild(errEl);
  }
}

// ── Toolbar ────────────────────────────────────────────────────────────────

function _buildToolbar() {
  const toolbar = h('div', { class: 'cl-toolbar' });

  // Review queue count
  const countSpan = h('span', { class: 'cl-review-count', id: 'cl-review-count' }, 'Loading...');
  _loadReviewStats(countSpan);

  // Filter dropdown
  const filterSelect = h('select', { class: 'cl-filter-select' });
  const filterOpts = [
    ['all', 'All'],
    ['pending', 'Pending Review'],
    ['approved', 'Approved'],
    ['needs_review', 'Needs Review'],
    ['dismissed', 'Dismissed'],
  ];
  for (const [val, label] of filterOpts) {
    const opt = h('option', { value: val }, label);
    if (val === _filter) opt.selected = true;
    filterSelect.appendChild(opt);
  }
  filterSelect.addEventListener('change', () => {
    _filter = filterSelect.value;
    renderContentTab(_container);
  });

  // Bulk approve button
  const bulkBtn = h('button', { class: 'btn btn-sm cl-btn-bulk' }, 'Bulk Approve (conf > 70)');
  bulkBtn.addEventListener('click', async () => {
    bulkBtn.disabled = true;
    bulkBtn.textContent = 'Approving...';
    try {
      const result = await api.reviewBulkApprove(REVIEWER_ID, 70);
      showToast(`Bulk approved ${result.approved_count || 0} tags`, 'success');
      renderContentTab(_container);
    } catch (err) {
      showToast(`Bulk approve failed: ${err.message}`, 'error');
      bulkBtn.disabled = false;
      bulkBtn.textContent = 'Bulk Approve (conf > 70)';
    }
  });

  toolbar.appendChild(countSpan);
  toolbar.appendChild(filterSelect);
  toolbar.appendChild(bulkBtn);
  return toolbar;
}

async function _loadReviewStats(el) {
  try {
    const stats = await api.getReviewStats();
    const pending = (stats.pending_count || 0) + (stats.needs_review_count || 0);
    el.textContent = `Review Queue: ${pending} pending`;
  } catch {
    el.textContent = 'Review Queue';
  }
}

// ── Library Grid ───────────────────────────────────────────────────────────

function _renderLibrary() {
  if (!_data || !_container) return;

  const journeys = _data.journeys || [];
  const grid = h('div', { class: 'cl-journey-grid' });

  for (const journey of journeys) {
    grid.appendChild(_renderJourneyColumn(journey));
  }

  // If no content after filtering
  if (journeys.length === 0) {
    const empty = h('div', { class: 'cl-empty' }, 'No lessons match the current filter.');
    _container.appendChild(empty);
    return;
  }

  _container.appendChild(grid);
}

function _renderJourneyColumn(journey) {
  const col = h('div', { class: 'cl-journey-col' });

  // Column header
  const header = h('div', { class: 'cl-journey-header' });
  header.innerHTML = `
    <h3 class="cl-journey-title">${_esc(journey.journey_name || 'Uncategorized')}</h3>
    <span class="cl-journey-count">${journey.lessons.length} lessons</span>
  `;
  col.appendChild(header);

  // Lesson cards
  for (const lesson of journey.lessons) {
    col.appendChild(_renderLessonCard(lesson));
  }

  return col;
}

// ── Lesson Card ────────────────────────────────────────────────────────────

function _renderLessonCard(lesson) {
  const card = h('div', {
    class: 'cl-card',
    dataset: { tagId: lesson.tag_id, lessonId: lesson.nx_lesson_id },
  });

  // Header: title + review badge
  const statusClass = `cl-badge-${lesson.review_status || 'pending'}`;
  const statusLabel = (lesson.review_status || 'pending').replace('_', ' ');

  // Tags
  const tagsHtml = (lesson.trait_tags || []).slice(0, 5).map(tag => {
    const dirClass = `cl-tag-${tag.direction || 'builds'}`;
    const arrow = tag.direction === 'builds' ? '\u25B2' : tag.direction === 'challenges' ? '\u25BC' : '\u2192';
    return `<span class="cl-tag ${dirClass}" title="${tag.direction} ${_esc(tag.trait)} (${tag.relevance_score})">${_esc(tag.trait)} ${arrow}${tag.relevance_score}</span>`;
  }).join('');

  // Difficulty dots
  const diff = lesson.difficulty || 0;
  const dots = '\u25CF'.repeat(diff) + '\u25CB'.repeat(Math.max(0, 5 - diff));

  card.innerHTML = `
    <div class="cl-card-header">
      <h4 class="cl-card-title">${_esc(lesson.lesson_name || `Lesson ${lesson.nx_lesson_id}`)}</h4>
      <span class="cl-badge ${statusClass}">${statusLabel}</span>
    </div>
    <div class="cl-card-desc">${_esc(lesson.lesson_desc || '')}</div>
    <div class="cl-card-tags">${tagsHtml || '<span class="cl-tag-empty">No tags</span>'}</div>
    <div class="cl-card-meta">
      <span class="cl-meta-style">${_esc(lesson.learning_style || '?')}</span>
      <span class="cl-meta-diff" title="Difficulty ${diff}/5">${dots}</span>
      <span class="cl-meta-conf">Conf: ${lesson.confidence ?? '?'}%</span>
    </div>
    <div class="cl-card-actions"></div>
  `;

  // Action buttons
  const actions = card.querySelector('.cl-card-actions');
  const canReview = ['pending', 'needs_review'].includes(lesson.review_status);

  if (canReview) {
    // Approve
    const approveBtn = h('button', { class: 'cl-action cl-action-approve', title: 'Approve tags' }, '\u2713');
    approveBtn.addEventListener('click', (e) => { e.stopPropagation(); _handleApprove(lesson, card); });
    actions.appendChild(approveBtn);

    // Edit
    const editBtn = h('button', { class: 'cl-action cl-action-edit', title: 'Edit tags' }, '\u270E');
    editBtn.addEventListener('click', (e) => { e.stopPropagation(); _handleEdit(lesson, card); });
    actions.appendChild(editBtn);

    // Dismiss
    const dismissBtn = h('button', { class: 'cl-action cl-action-dismiss', title: 'Dismiss' }, '\u2715');
    dismissBtn.addEventListener('click', (e) => { e.stopPropagation(); _handleDismiss(lesson, card); });
    actions.appendChild(dismissBtn);
  }

  // View content
  const viewBtn = h('button', { class: 'cl-action cl-action-view', title: 'View content' }, '\uD83D\uDC41');
  viewBtn.addEventListener('click', (e) => { e.stopPropagation(); _handleViewContent(lesson); });
  actions.appendChild(viewBtn);

  return card;
}

// ── Review Actions ────────────────────────────────────────────────────────

async function _handleApprove(lesson, card) {
  try {
    await api.reviewApprove(lesson.tag_id, REVIEWER_ID);
    showToast(`Approved: ${lesson.lesson_name || lesson.nx_lesson_id}`, 'success');
    // Update card in-place
    const badge = card.querySelector('.cl-badge');
    if (badge) {
      badge.className = 'cl-badge cl-badge-approved';
      badge.textContent = 'approved';
    }
    // Remove approve/edit/dismiss buttons
    const actions = card.querySelector('.cl-card-actions');
    card.querySelectorAll('.cl-action-approve, .cl-action-edit, .cl-action-dismiss').forEach(b => b.remove());
  } catch (err) {
    showToast(`Approve failed: ${err.message}`, 'error');
  }
}

async function _handleDismiss(lesson, card) {
  try {
    await api.reviewDismiss(lesson.tag_id, REVIEWER_ID);
    showToast(`Dismissed: ${lesson.lesson_name || lesson.nx_lesson_id}`, 'success');
    const badge = card.querySelector('.cl-badge');
    if (badge) {
      badge.className = 'cl-badge cl-badge-dismissed';
      badge.textContent = 'dismissed';
    }
    card.querySelectorAll('.cl-action-approve, .cl-action-edit, .cl-action-dismiss').forEach(b => b.remove());
  } catch (err) {
    showToast(`Dismiss failed: ${err.message}`, 'error');
  }
}

function _handleEdit(lesson, card) {
  // Check if editor already open
  if (card.querySelector('.cl-tag-editor')) return;

  const editor = h('div', { class: 'cl-tag-editor' });
  const existingTags = Array.isArray(lesson.trait_tags) ? [...lesson.trait_tags] : [];

  // Editable tag rows
  const tagList = h('div', { class: 'cl-editor-tags' });
  const tagRows = [];

  function addTagRow(tag = { trait: EPP_TRAITS[0], relevance_score: 50, direction: 'builds' }) {
    const row = h('div', { class: 'cl-editor-row' });

    const traitSelect = h('select', { class: 'cl-editor-trait' });
    for (const t of EPP_TRAITS) {
      const opt = h('option', { value: t }, t.replace(/_/g, ' '));
      if (t === tag.trait) opt.selected = true;
      traitSelect.appendChild(opt);
    }

    const slider = h('input', {
      type: 'range', min: '0', max: '100', value: String(tag.relevance_score),
      class: 'cl-editor-slider',
    });
    const sliderVal = h('span', { class: 'cl-editor-slider-val' }, String(tag.relevance_score));
    slider.addEventListener('input', () => { sliderVal.textContent = slider.value; });

    const dirGroup = h('div', { class: 'cl-editor-dir' });
    for (const d of ['builds', 'leverages', 'challenges']) {
      const label = h('label', { class: 'cl-editor-dir-label' });
      const radio = h('input', { type: 'radio', name: `dir-${tagRows.length}`, value: d });
      if (d === tag.direction) radio.checked = true;
      label.appendChild(radio);
      label.appendChild(document.createTextNode(d.charAt(0).toUpperCase() + d.slice(1)));
      dirGroup.appendChild(label);
    }

    const removeBtn = h('button', { class: 'cl-editor-remove', title: 'Remove tag' }, '\u2715');
    removeBtn.addEventListener('click', () => {
      row.remove();
      const idx = tagRows.indexOf(row);
      if (idx >= 0) tagRows.splice(idx, 1);
    });

    row.appendChild(traitSelect);
    row.appendChild(slider);
    row.appendChild(sliderVal);
    row.appendChild(dirGroup);
    row.appendChild(removeBtn);
    tagList.appendChild(row);
    tagRows.push(row);
  }

  // Populate existing tags or add one empty row
  if (existingTags.length > 0) {
    for (const t of existingTags) addTagRow(t);
  } else {
    addTagRow();
  }

  // Add tag button
  const addBtn = h('button', { class: 'btn btn-sm cl-editor-add' }, '+ Add Tag');
  addBtn.addEventListener('click', () => addTagRow());

  // Save / Cancel
  const btnRow = h('div', { class: 'cl-editor-btns' });
  const saveBtn = h('button', { class: 'btn btn-sm btn-primary' }, 'Save Correction');
  const cancelBtn = h('button', { class: 'btn btn-sm' }, 'Cancel');

  cancelBtn.addEventListener('click', () => editor.remove());
  saveBtn.addEventListener('click', async () => {
    // Gather corrected tags from rows
    const corrected = [];
    for (const row of tagRows) {
      const trait = row.querySelector('.cl-editor-trait').value;
      const score = parseInt(row.querySelector('.cl-editor-slider').value, 10);
      const checkedRadio = row.querySelector('.cl-editor-dir input:checked');
      const direction = checkedRadio ? checkedRadio.value : 'builds';
      corrected.push({ trait, relevance_score: score, direction });
    }
    if (corrected.length === 0) {
      showToast('Add at least one tag', 'warning');
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    try {
      await api.reviewCorrect(lesson.tag_id, REVIEWER_ID, corrected);
      showToast(`Corrected: ${lesson.lesson_name || lesson.nx_lesson_id}`, 'success');
      // Refresh this card
      renderContentTab(_container);
    } catch (err) {
      showToast(`Correction failed: ${err.message}`, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Correction';
    }
  });

  btnRow.appendChild(saveBtn);
  btnRow.appendChild(cancelBtn);

  editor.appendChild(tagList);
  editor.appendChild(addBtn);
  editor.appendChild(btnRow);

  // Insert after card-actions
  card.appendChild(editor);
}

// ── Azure Content Viewer ──────────────────────────────────────────────────

async function _handleViewContent(lesson) {
  // Try lesson_detail_id = nx_lesson_id first
  const lessonDetailId = lesson.nx_lesson_id;

  // Create modal backdrop
  const modal = h('div', { class: 'cl-viewer-overlay', id: 'cl-viewer-overlay' });
  const dialog = h('div', { class: 'cl-viewer-modal' });

  dialog.innerHTML = `
    <div class="cl-viewer-header">
      <h3>${_esc(lesson.lesson_name || `Lesson ${lesson.nx_lesson_id}`)}</h3>
      <button class="cl-viewer-close" title="Close">\u2715</button>
    </div>
    <div class="cl-viewer-body">
      <div class="cl-viewer-loading">
        <div class="view-loading-spinner"></div>
        <span>Loading slides...</span>
      </div>
    </div>
    <div class="cl-viewer-nav" style="display:none">
      <button class="btn btn-sm cl-viewer-prev" disabled>\u25C0 Prev</button>
      <span class="cl-viewer-counter">Slide 0 of 0</span>
      <button class="btn btn-sm cl-viewer-next">\u25B6 Next</button>
    </div>
  `;

  modal.appendChild(dialog);
  document.body.appendChild(modal);

  // Close handlers
  const closeBtn = dialog.querySelector('.cl-viewer-close');
  closeBtn.addEventListener('click', () => modal.remove());
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  document.addEventListener('keydown', function onEsc(e) {
    if (e.key === 'Escape') { modal.remove(); document.removeEventListener('keydown', onEsc); }
  });

  const body = dialog.querySelector('.cl-viewer-body');
  const nav = dialog.querySelector('.cl-viewer-nav');

  try {
    const result = await api.getLessonSlides(lessonDetailId);
    const slides = result.slides || [];
    body.querySelector('.cl-viewer-loading').remove();

    if (slides.length === 0) {
      body.innerHTML = '<div class="cl-viewer-empty">No content available for this lesson.</div>';
      return;
    }

    _viewerSlides = slides;
    _viewerIndex = 0;
    nav.style.display = 'flex';

    const prevBtn = dialog.querySelector('.cl-viewer-prev');
    const nextBtn = dialog.querySelector('.cl-viewer-next');
    const counter = dialog.querySelector('.cl-viewer-counter');

    function showSlide(idx) {
      _viewerIndex = idx;
      counter.textContent = `Slide ${idx + 1} of ${slides.length}`;
      prevBtn.disabled = idx === 0;
      nextBtn.disabled = idx === slides.length - 1;
      body.innerHTML = '';
      body.appendChild(_renderSlide(slides[idx]));
    }

    prevBtn.addEventListener('click', () => { if (_viewerIndex > 0) showSlide(_viewerIndex - 1); });
    nextBtn.addEventListener('click', () => { if (_viewerIndex < slides.length - 1) showSlide(_viewerIndex + 1); });

    // Keyboard nav
    document.addEventListener('keydown', function onKey(e) {
      if (!document.getElementById('cl-viewer-overlay')) {
        document.removeEventListener('keydown', onKey);
        return;
      }
      if (e.key === 'ArrowLeft' && _viewerIndex > 0) showSlide(_viewerIndex - 1);
      if (e.key === 'ArrowRight' && _viewerIndex < slides.length - 1) showSlide(_viewerIndex + 1);
    });

    showSlide(0);
  } catch (err) {
    body.querySelector('.cl-viewer-loading')?.remove();
    body.innerHTML = `<div class="cl-viewer-empty">No content available for this lesson.</div>`;
  }
}

function _renderSlide(slide) {
  const el = h('div', { class: 'cl-slide' });
  const content = slide.content || {};
  const type = slide.type || 'unknown';

  // Title
  if (content.slide_title) {
    const title = h('div', { class: 'cl-slide-title' }, content.slide_title);
    el.appendChild(title);
  }

  switch (type) {
    case 'image': {
      if (content.background_image) {
        const img = h('img', {
          class: 'cl-slide-img',
          src: content.background_image,
          alt: content.slide_title || 'Slide image',
        });
        img.addEventListener('error', () => { img.alt = 'Image failed to load'; img.style.display = 'none'; });
        el.appendChild(img);
      }
      if (content.audio) {
        const audio = h('audio', { controls: '', class: 'cl-slide-audio', src: content.audio });
        el.appendChild(audio);
      }
      // Text overlay
      if (content.text_content) {
        el.appendChild(h('div', { class: 'cl-slide-text' }, content.text_content));
      }
      break;
    }
    case 'video': {
      if (content.video_url || content.background_video) {
        const video = h('video', {
          controls: '', class: 'cl-slide-video',
          src: content.video_url || content.background_video,
        });
        el.appendChild(video);
      }
      break;
    }
    case 'question-answer': {
      const questions = content.questions || [];
      if (questions.length > 0) {
        const qList = h('div', { class: 'cl-slide-qa' });
        for (const q of questions) {
          const qEl = h('div', { class: 'cl-slide-question' });
          qEl.innerHTML = `<strong>Q:</strong> ${_esc(q.question || q.text || JSON.stringify(q))}`;
          if (q.answer) qEl.innerHTML += `<br><em>A:</em> ${_esc(q.answer)}`;
          qList.appendChild(qEl);
        }
        el.appendChild(qList);
      }
      break;
    }
    case 'take-away': {
      const text = content.summary || content.text_content || content.takeaway || '';
      if (text) el.appendChild(h('div', { class: 'cl-slide-takeaway' }, text));
      break;
    }
    case 'greetings': {
      const text = content.greeting || content.text_content || content.welcome || '';
      if (text) el.appendChild(h('div', { class: 'cl-slide-greeting' }, text));
      break;
    }
    default: {
      // Generic: render any text content found
      const html = content.html_content || content.text_content || content.body || '';
      if (html) {
        const div = h('div', { class: 'cl-slide-generic' });
        div.textContent = html;
        el.appendChild(div);
      }
      // Show type badge
      const badge = h('span', { class: 'cl-slide-type-badge' }, type);
      el.prepend(badge);
      break;
    }
  }

  // If slide has audio and is not image type
  if (type !== 'image' && content.audio) {
    el.appendChild(h('audio', { controls: '', class: 'cl-slide-audio', src: content.audio }));
  }

  return el;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function _esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
