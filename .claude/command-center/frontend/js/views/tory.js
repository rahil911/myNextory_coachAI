// ==========================================================================
// TORY.JS — Learner Roadmap & Profile View
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
// Default learner for demo — can be changed via input
const DEFAULT_LEARNER_ID = 200;

export function renderTory(root) {
  const container = h('div', { class: 'view-container' });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>Learning Path</h2>
      </div>
      <div class="view-header-right">
        <div class="tory-selector">
          <label class="caption" for="tory-learner-input">Learner ID</label>
          <input type="text" id="tory-learner-input" value="${DEFAULT_LEARNER_ID}" placeholder="User ID">
          <button class="btn btn-primary btn-sm" id="tory-load-btn">Load</button>
        </div>
      </div>
    </div>

    <div id="tory-loading" class="view-loading" style="display:none">
      <div class="view-loading-spinner"></div>
      <span>Loading learner path...</span>
    </div>

    <div id="tory-error" style="display:none"></div>

    <div id="tory-content" style="display:none">
      <div class="tory-layout">
        <aside id="tory-sidebar"></aside>
        <section id="tory-main"></section>
      </div>
    </div>
  `;

  root.appendChild(container);

  // Event handlers
  container.querySelector('#tory-load-btn').addEventListener('click', () => {
    const id = parseInt(container.querySelector('#tory-learner-input').value, 10);
    if (id > 0) loadLearnerPath(id);
  });

  container.querySelector('#tory-learner-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const id = parseInt(e.target.value, 10);
      if (id > 0) loadLearnerPath(id);
    }
  });

  // Load default learner
  const tory = getState().tory;
  if (tory.path && isFresh('tory')) {
    renderToryContent();
  } else {
    loadLearnerPath(DEFAULT_LEARNER_ID);
  }

  subscribe('tory', () => renderToryContent());
}

async function loadLearnerPath(learnerId) {
  const tory = getState().tory;
  setState({ tory: { ...tory, loading: true, error: null, learnerId } });

  showLoading(true);
  showError(null);
  showContent(false);

  try {
    const path = await api.getToryPath(learnerId);
    setState({
      tory: {
        ...getState().tory,
        path,
        loading: false,
        error: null,
        feedbackSent: false,
      }
    });
    markFetched('tory');
    showLoading(false);
    renderToryContent();
  } catch (err) {
    setState({
      tory: {
        ...getState().tory,
        path: null,
        loading: false,
        error: err.message,
      }
    });
    showLoading(false);
    showError(err.message);
    showToast(`Failed to load path: ${err.message}`, 'error');
  }
}

function showLoading(visible) {
  const el = document.getElementById('tory-loading');
  if (el) el.style.display = visible ? 'flex' : 'none';
}

function showError(msg) {
  const el = document.getElementById('tory-error');
  if (!el) return;
  if (msg) {
    el.style.display = 'block';
    el.innerHTML = `
      <div class="dash-alert">
        <span class="dash-alert-icon">\u26A0</span>
        <span>${msg}</span>
      </div>
    `;
  } else {
    el.style.display = 'none';
    el.innerHTML = '';
  }
}

function showContent(visible) {
  const el = document.getElementById('tory-content');
  if (el) el.style.display = visible ? 'block' : 'none';
}

// ── Render Full Content ──────────────────────────────────────────────────

function renderToryContent() {
  const { tory } = getState();
  if (!tory.path) return;

  showContent(true);

  const sidebar = document.getElementById('tory-sidebar');
  const main = document.getElementById('tory-main');
  if (!sidebar || !main) return;

  sidebar.innerHTML = '';
  main.innerHTML = '';

  sidebar.appendChild(renderProfile(tory.path.profile, tory.path.coach, tory));
  main.appendChild(renderRoadmap(tory.path));
}

// ── ToryProfile Component ────────────────────────────────────────────────

function renderProfile(profile, coach, toryState) {
  const frag = document.createDocumentFragment();

  const card = h('div', { class: 'tory-profile' });

  // Header
  const initials = ((profile.first_name || '')[0] || '') + ((profile.last_name || '')[0] || '');
  const displayName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.email || `User ${profile.nx_user_id}`;

  let headerHtml = `
    <div class="tory-profile-header">
      <div class="tory-profile-avatar">${initials || '?'}</div>
      <div>
        <div class="tory-profile-name">${esc(displayName)}</div>
        <div class="tory-profile-email">${esc(profile.email || '')}</div>
      </div>
    </div>
  `;

  // Coach section
  if (coach) {
    const signalEmoji = { green: '\uD83D\uDFE2', yellow: '\uD83D\uDFE1', red: '\uD83D\uDD34' };
    const emoji = signalEmoji[coach.compat_signal] || '\uD83D\uDFE2';
    headerHtml += `
      <div class="tory-coach">
        <span class="tory-coach-signal">${emoji}</span>
        <div>
          <div class="tory-coach-name">Coach: ${esc(coach.coach_name || 'Assigned')}</div>
          <div class="tory-coach-message">${esc(coach.compat_message || '')}</div>
        </div>
      </div>
    `;
  }

  // Narrative
  if (profile.profile_narrative) {
    headerHtml += `
      <div class="tory-profile-narrative">${esc(profile.profile_narrative)}</div>
    `;
  }

  // Strengths
  const strengths = profile.strengths || [];
  const personalityStrengths = strengths.filter(s => !s.trait.includes('_JobFit')).slice(0, 5);
  if (personalityStrengths.length > 0) {
    headerHtml += `
      <div class="tory-profile-section">
        <div class="tory-profile-section-label">Strengths</div>
        <div class="tory-trait-list">
          ${personalityStrengths.map(s =>
            `<span class="tory-trait tory-trait-strength">${esc(s.trait)} ${Math.round(s.score)}</span>`
          ).join('')}
        </div>
      </div>
    `;
  }

  // Gaps
  const gaps = profile.gaps || [];
  const personalityGaps = gaps.filter(g => !g.trait.includes('_JobFit')).slice(0, 5);
  if (personalityGaps.length > 0) {
    headerHtml += `
      <div class="tory-profile-section">
        <div class="tory-profile-section-label">Growth Areas</div>
        <div class="tory-trait-list">
          ${personalityGaps.map(g =>
            `<span class="tory-trait tory-trait-gap">${esc(g.trait)} ${Math.round(g.score)}</span>`
          ).join('')}
        </div>
      </div>
    `;
  }

  // Learning style
  if (profile.learning_style) {
    headerHtml += `
      <div class="tory-profile-section">
        <div class="tory-profile-section-label">Learning Style</div>
        <span class="badge badge-blue">${esc(profile.learning_style)}</span>
      </div>
    `;
  }

  // Confidence + version
  headerHtml += `
    <div class="tory-profile-section">
      <div class="tory-profile-section-label">Profile Info</div>
      <div class="tory-stat">Confidence: <strong>${profile.confidence}%</strong></div>
      <div class="tory-stat">Version: <strong>${profile.version}</strong></div>
    </div>
  `;

  // Feedback button
  headerHtml += `<div class="tory-profile-feedback" id="tory-feedback-area"></div>`;

  card.innerHTML = headerHtml;

  // Feedback area logic
  const feedbackArea = card.querySelector('#tory-feedback-area');
  if (toryState.feedbackSent) {
    feedbackArea.innerHTML = '<div class="tory-feedback-sent">Feedback submitted. We\'ll refine your profile.</div>';
  } else {
    const btn = h('button', { class: 'tory-feedback-btn' }, "This doesn't sound like me");
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Sending...';
      try {
        await api.submitToryFeedback(profile.nx_user_id, 'not_like_me');
        setState({ tory: { ...getState().tory, feedbackSent: true } });
        feedbackArea.innerHTML = '<div class="tory-feedback-sent">Feedback submitted. We\'ll refine your profile.</div>';
        showToast('Feedback submitted', 'success');
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "This doesn't sound like me";
        showToast(`Feedback failed: ${err.message}`, 'error');
      }
    });
    feedbackArea.appendChild(btn);
  }

  frag.appendChild(card);
  return frag;
}

// ── ToryRoadmap Component ────────────────────────────────────────────────

function renderRoadmap(pathData) {
  const frag = document.createDocumentFragment();
  const recs = pathData.recommendations || [];

  // Stats
  const stats = h('div', { class: 'tory-stats' });
  stats.innerHTML = `
    <div class="tory-stat"><strong>${pathData.total_count}</strong> lessons</div>
    <div class="tory-stat"><strong>${pathData.discovery_count}</strong> discovery</div>
    <div class="tory-stat"><strong>${recs.filter(r => r.locked_by_coach).length}</strong> coach-modified</div>
  `;
  frag.appendChild(stats);

  // Path change notifications (coach overrides since last visit)
  const pathEvents = pathData.path_events || [];
  if (pathEvents.length > 0) {
    for (const evt of pathEvents) {
      const change = h('div', { class: 'tory-path-change' });
      const coachLabel = evt.coach_name ? ` by ${esc(evt.coach_name)}` : '';
      change.innerHTML = `
        <span class="tory-path-change-icon">\u2139\uFE0F</span>
        <div class="tory-path-change-text">
          <strong>Path ${esc(evt.type)}</strong>${coachLabel}${evt.reason ? ' \u2014 ' + esc(evt.reason) : ''}
        </div>
      `;
      frag.appendChild(change);
    }
  }

  // Discovery banner (if discovery items exist)
  if (pathData.discovery_count > 0) {
    const banner = h('div', { class: 'tory-discovery-banner' });
    banner.innerHTML = `
      <span class="tory-discovery-icon">\uD83D\uDD2E</span>
      <div class="tory-discovery-text">
        <strong>Discovery Phase</strong> \u2014 We're learning about you. Try these first ${pathData.discovery_count} lessons and tell us what resonates. Your path will adapt based on your engagement.
      </div>
    `;
    frag.appendChild(banner);
  }

  // Roadmap timeline
  const timeline = h('div', { class: 'tory-roadmap' });

  let discoveryEnded = false;

  for (const rec of recs) {
    // Insert separator after discovery phase ends
    if (!rec.is_discovery && !discoveryEnded && pathData.discovery_count > 0) {
      discoveryEnded = true;
      const sep = h('div', { class: 'tory-discovery-separator' });
      sep.innerHTML = `
        <span class="tory-discovery-separator-text">Your Personalized Path</span>
        <div class="tory-discovery-separator-line"></div>
      `;
      timeline.appendChild(sep);
    }

    timeline.appendChild(renderLessonCard(rec));
  }

  frag.appendChild(timeline);
  return frag;
}

// ── Lesson Card ──────────────────────────────────────────────────────────

function renderLessonCard(rec) {
  const classes = ['tory-lesson'];
  if (rec.is_discovery) classes.push('discovery');
  if (rec.locked_by_coach) classes.push('coach-modified');

  const card = h('div', { class: classes.join(' ') });

  // Badges
  let badgesHtml = '';
  if (rec.is_discovery) {
    badgesHtml += '<span class="badge badge-purple">Discovery</span>';
  }
  if (rec.locked_by_coach) {
    badgesHtml += '<span class="badge badge-yellow">Coach</span>';
  }
  if (rec.source !== 'tory') {
    badgesHtml += `<span class="badge badge-blue">${esc(rec.source)}</span>`;
  }

  // Match score bar
  const scorePercent = Math.min(Math.round(rec.match_score), 100);

  card.innerHTML = `
    <div class="tory-lesson-dot"></div>
    <div class="tory-lesson-card">
      <div class="tory-lesson-card-header">
        <span class="tory-lesson-sequence">#${rec.sequence}</span>
        <span class="tory-lesson-title">${esc(rec.lesson_title || `Lesson ${rec.nx_lesson_id}`)}</span>
        <div class="tory-lesson-badges">${badgesHtml}</div>
      </div>
      <div class="tory-lesson-journey">${esc(rec.journey_title || '')}</div>
      <div class="tory-lesson-rationale">${esc(rec.match_rationale || '')}</div>
      <div class="tory-lesson-score">
        <span>Match ${scorePercent}%</span>
        <div class="tory-lesson-score-bar">
          <div class="tory-lesson-score-fill" style="width: ${scorePercent}%"></div>
        </div>
      </div>
    </div>
  `;

  return card;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
