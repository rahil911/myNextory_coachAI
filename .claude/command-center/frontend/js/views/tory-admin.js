// ==========================================================================
// TORY-ADMIN.JS — HR/Admin Dashboard for Tory Progress Tracking
// Three views: Cohort Overview, Individual Drilldown, Aggregate Metrics
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo } from '../utils/format.js';

// ── State key ───────────────────────────────────────────────────────────────
const STATE_KEY = 'toryAdmin';

function getToryAdmin() {
  return getState()[STATE_KEY] || {
    cohort: null,
    metrics: null,
    drilldown: null,
    loading: false,
    activeTab: 'cohort',
    sortBy: 'avg_match_score',
    sortDir: 'desc',
    coachFilter: '',
    departmentFilter: '',
  };
}

function setToryAdmin(patch) {
  setState({ [STATE_KEY]: { ...getToryAdmin(), ...patch } });
}

export function renderToryAdmin(root) {
  const container = h('div', { class: 'view-container' });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>HR Dashboard</h2>
      </div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="ta-refresh">Refresh</button>
      </div>
    </div>

    <div class="ta-tabs" id="ta-tabs">
      <button class="ta-tab active" data-tab="cohort">Cohort Overview</button>
      <button class="ta-tab" data-tab="metrics">Aggregate Metrics</button>
    </div>

    <div id="ta-loading" class="view-loading" style="display:none">
      <div class="view-loading-spinner"></div>
      <span>Loading dashboard data...</span>
    </div>

    <div id="ta-content"></div>
  `;

  root.appendChild(container);

  // Tab switching
  container.querySelector('#ta-tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('[data-tab]');
    if (!tab) return;
    const tabName = tab.dataset.tab;
    container.querySelectorAll('.ta-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    setToryAdmin({ activeTab: tabName, drilldown: null });
    renderContent();
  });

  container.querySelector('#ta-refresh').addEventListener('click', () => loadData());

  // Initial load
  if (isFresh(STATE_KEY)) {
    renderContent();
  } else {
    loadData();
  }

  subscribe(STATE_KEY, () => renderContent());
}

async function loadData() {
  setToryAdmin({ loading: true });
  showLoading(true);

  try {
    const [cohort, metrics] = await Promise.all([
      api.getToryAdminCohort(),
      api.getToryAdminMetrics(),
    ]);
    setToryAdmin({ cohort, metrics, loading: false });
    markFetched(STATE_KEY);
    showLoading(false);
    renderContent();
  } catch (err) {
    setToryAdmin({ loading: false });
    showLoading(false);
    showToast(`Failed to load dashboard: ${err.message}`, 'error');
  }
}

async function loadDrilldown(learnerId) {
  setToryAdmin({ loading: true });
  showLoading(true);
  try {
    const drilldown = await api.getToryAdminLearner(learnerId);
    setToryAdmin({ drilldown, loading: false, activeTab: 'drilldown' });
    showLoading(false);

    // Update tab bar to show drilldown
    const tabs = document.getElementById('ta-tabs');
    if (tabs) {
      tabs.querySelectorAll('.ta-tab').forEach(t => t.classList.remove('active'));
      // Add drilldown tab if not present
      let ddTab = tabs.querySelector('[data-tab="drilldown"]');
      if (!ddTab) {
        ddTab = h('button', { class: 'ta-tab active', dataset: { tab: 'drilldown' } });
        tabs.appendChild(ddTab);
      }
      const name = [drilldown.profile?.first_name, drilldown.profile?.last_name].filter(Boolean).join(' ') || `User ${learnerId}`;
      ddTab.textContent = name;
      ddTab.classList.add('active');
    }

    renderContent();
  } catch (err) {
    setToryAdmin({ loading: false });
    showLoading(false);
    showToast(`Failed to load learner: ${err.message}`, 'error');
  }
}

function showLoading(visible) {
  const el = document.getElementById('ta-loading');
  if (el) el.style.display = visible ? 'flex' : 'none';
}

function renderContent() {
  const content = document.getElementById('ta-content');
  if (!content) return;
  content.innerHTML = '';

  const state = getToryAdmin();
  switch (state.activeTab) {
    case 'cohort':
      content.appendChild(renderCohort(state));
      break;
    case 'metrics':
      content.appendChild(renderMetrics(state));
      break;
    case 'drilldown':
      if (state.drilldown) {
        content.appendChild(renderDrilldown(state.drilldown));
      }
      break;
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// COHORT OVERVIEW TABLE
// ═══════════════════════════════════════════════════════════════════════════

function renderCohort(state) {
  const frag = document.createDocumentFragment();
  const learners = state.cohort?.learners || [];

  // Toolbar: filters + CSV export
  const toolbar = h('div', { class: 'ta-toolbar' });
  toolbar.innerHTML = `
    <div class="ta-toolbar-filters">
      <input type="text" class="ta-filter-input" id="ta-coach-filter" placeholder="Filter by coach..." value="${esc(state.coachFilter || '')}">
      <input type="text" class="ta-filter-input" id="ta-dept-filter" placeholder="Filter by department..." value="${esc(state.departmentFilter || '')}">
    </div>
    <div class="ta-toolbar-actions">
      <span class="ta-count">${learners.length} learner${learners.length !== 1 ? 's' : ''}</span>
      <button class="btn btn-ghost btn-sm" id="ta-csv-export">Export CSV</button>
    </div>
  `;
  frag.appendChild(toolbar);

  // Filter handlers
  setTimeout(() => {
    const coachInput = document.getElementById('ta-coach-filter');
    const deptInput = document.getElementById('ta-dept-filter');
    if (coachInput) {
      coachInput.addEventListener('input', debounce((e) => {
        setToryAdmin({ coachFilter: e.target.value });
        loadFilteredCohort();
      }, 300));
    }
    if (deptInput) {
      deptInput.addEventListener('input', debounce((e) => {
        setToryAdmin({ departmentFilter: e.target.value });
        loadFilteredCohort();
      }, 300));
    }
    const csvBtn = document.getElementById('ta-csv-export');
    if (csvBtn) {
      csvBtn.addEventListener('click', () => {
        window.open('/api/tory/admin/cohort/csv', '_blank');
      });
    }
  }, 0);

  // Table
  const table = h('div', { class: 'ta-table-wrap' });

  // Sort config
  const { sortBy, sortDir } = state;
  const sortArrow = (field) => {
    if (sortBy !== field) return '';
    return sortDir === 'asc' ? ' \u2191' : ' \u2193';
  };

  // Apply local filters
  let filtered = learners;
  if (state.coachFilter) {
    const cf = state.coachFilter.toLowerCase();
    filtered = filtered.filter(l => l.coach_name && l.coach_name.toLowerCase().includes(cf));
  }
  if (state.departmentFilter) {
    const df = state.departmentFilter.toLowerCase();
    filtered = filtered.filter(l => l.department && l.department.toLowerCase().includes(df));
  }

  // Apply local sort
  const sorted = [...filtered].sort((a, b) => {
    let va = a[sortBy], vb = b[sortBy];
    if (typeof va === 'string') va = va || '';
    if (typeof vb === 'string') vb = vb || '';
    if (va == null) va = typeof vb === 'string' ? '' : 0;
    if (vb == null) vb = typeof va === 'string' ? '' : 0;
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : (va - vb);
    return sortDir === 'asc' ? cmp : -cmp;
  });

  table.innerHTML = `
    <table class="ta-table">
      <thead>
        <tr>
          <th class="ta-th-sortable" data-sort="first_name">Name${sortArrow('first_name')}</th>
          <th>Department</th>
          <th class="ta-th-sortable" data-sort="total_lessons">Path${sortArrow('total_lessons')}</th>
          <th class="ta-th-sortable" data-sort="phase">Phase${sortArrow('phase')}</th>
          <th class="ta-th-sortable" data-sort="avg_match_score">Match${sortArrow('avg_match_score')}</th>
          <th class="ta-th-sortable" data-sort="confidence">Confidence${sortArrow('confidence')}</th>
          <th>Coach</th>
          <th class="ta-th-sortable" data-sort="last_activity">Last Active${sortArrow('last_activity')}</th>
        </tr>
      </thead>
      <tbody>
        ${sorted.length === 0 ? '<tr><td colspan="8" class="ta-empty">No learners with Tory profiles yet</td></tr>' : ''}
        ${sorted.map(l => `
          <tr class="ta-row" data-learner-id="${l.nx_user_id}">
            <td>
              <div class="ta-learner-name">${esc(l.first_name || '')} ${esc(l.last_name || '')}</div>
              <div class="ta-learner-email">${esc(l.email || '')}</div>
            </td>
            <td>${esc(l.department || '--')}</td>
            <td>
              <span class="ta-path-progress">${l.total_lessons} lessons</span>
              ${l.coach_modified > 0 ? `<span class="badge badge-yellow badge-sm">${l.coach_modified} coach</span>` : ''}
            </td>
            <td><span class="badge ${phaseBadgeClass(l.phase)}">${esc(l.phase)}</span></td>
            <td>
              <div class="ta-match-cell">
                <span>${l.avg_match_score}%</span>
                <div class="ta-mini-bar"><div class="ta-mini-bar-fill" style="width:${Math.min(l.avg_match_score, 100)}%"></div></div>
              </div>
            </td>
            <td>${l.confidence}%</td>
            <td>
              ${l.coach_name ? `
                <div class="ta-coach-cell">
                  <span class="ta-compat-dot ta-compat-${l.compat_signal || 'green'}"></span>
                  <span>${esc(l.coach_name)}</span>
                </div>
              ` : '<span class="ta-muted">--</span>'}
            </td>
            <td><span class="ta-muted">${l.last_activity ? timeAgo(l.last_activity) : '--'}</span></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  frag.appendChild(table);

  // Row click → drilldown
  setTimeout(() => {
    document.querySelectorAll('.ta-row').forEach(row => {
      row.addEventListener('click', () => {
        const id = parseInt(row.dataset.learnerId, 10);
        if (id > 0) loadDrilldown(id);
      });
    });
    // Sort header click
    document.querySelectorAll('.ta-th-sortable').forEach(th => {
      th.addEventListener('click', () => {
        const field = th.dataset.sort;
        const currentSort = getToryAdmin();
        const newDir = currentSort.sortBy === field && currentSort.sortDir === 'desc' ? 'asc' : 'desc';
        setToryAdmin({ sortBy: field, sortDir: newDir });
        renderContent();
      });
    });
  }, 0);

  return frag;
}

async function loadFilteredCohort() {
  try {
    const state = getToryAdmin();
    const params = new URLSearchParams();
    if (state.coachFilter) params.set('coach_filter', state.coachFilter);
    if (state.departmentFilter) params.set('department_filter', state.departmentFilter);
    const cohort = await api.getToryAdminCohort(params.toString());
    setToryAdmin({ cohort });
  } catch (err) {
    // Silent fail, local filter still works
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// INDIVIDUAL DRILLDOWN
// ═══════════════════════════════════════════════════════════════════════════

function renderDrilldown(data) {
  const frag = document.createDocumentFragment();
  const profile = data.profile;

  // Back button
  const back = h('button', { class: 'btn btn-ghost btn-sm ta-back-btn', onclick: () => {
    setToryAdmin({ activeTab: 'cohort', drilldown: null });
    // Remove drilldown tab
    const ddTab = document.querySelector('[data-tab="drilldown"]');
    if (ddTab) ddTab.remove();
    // Reactivate cohort tab
    const cohortTab = document.querySelector('[data-tab="cohort"]');
    if (cohortTab) cohortTab.classList.add('active');
    renderContent();
  }}, '\u2190 Back to Cohort');
  frag.appendChild(back);

  // Profile header
  const header = h('div', { class: 'ta-dd-header' });
  const displayName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.email;
  const initials = ((profile.first_name || '')[0] || '') + ((profile.last_name || '')[0] || '');

  header.innerHTML = `
    <div class="ta-dd-profile">
      <div class="tory-profile-avatar">${initials || '?'}</div>
      <div>
        <div class="ta-dd-name">${esc(displayName)}</div>
        <div class="ta-dd-email">${esc(profile.email || '')}</div>
      </div>
      <div class="ta-dd-badges">
        <span class="badge badge-blue">${esc(profile.learning_style || 'unknown')}</span>
        <span class="badge badge-green">v${profile.version}</span>
        <span class="badge badge-purple">${profile.confidence}% confidence</span>
      </div>
    </div>
    ${data.coach ? `
      <div class="ta-dd-coach">
        <span class="ta-compat-dot ta-compat-${data.coach.compat_signal || 'green'}"></span>
        Coach: ${esc(data.coach.coach_name || 'Assigned')}
        ${data.coach.compat_message ? ` - ${esc(data.coach.compat_message)}` : ''}
      </div>
    ` : ''}
  `;
  frag.appendChild(header);

  // Stats row
  const stats = h('div', { class: 'ta-dd-stats' });
  stats.innerHTML = `
    <div class="dash-card"><div class="dash-card-label">Total Lessons</div><div class="dash-card-value">${data.total_count}</div></div>
    <div class="dash-card"><div class="dash-card-label">Discovery</div><div class="dash-card-value">${data.discovery_count}</div></div>
    <div class="dash-card"><div class="dash-card-label">Coach Modified</div><div class="dash-card-value">${data.coach_modified_count}</div></div>
    <div class="dash-card"><div class="dash-card-label">Feedback</div><div class="dash-card-value">${profile.feedback_flags}</div></div>
  `;
  frag.appendChild(stats);

  // Profile narrative
  if (profile.profile_narrative) {
    const narr = h('div', { class: 'ta-dd-section' });
    narr.innerHTML = `
      <h4>Profile Narrative</h4>
      <div class="tory-profile-narrative">${esc(profile.profile_narrative)}</div>
    `;
    frag.appendChild(narr);
  }

  // Strengths & Gaps side by side
  const traits = h('div', { class: 'ta-dd-traits' });
  const strengths = profile.strengths || [];
  const gaps = profile.gaps || [];
  traits.innerHTML = `
    <div class="ta-dd-section">
      <h4>Strengths</h4>
      <div class="tory-trait-list">
        ${strengths.map(s =>
          `<span class="tory-trait tory-trait-strength">${esc(s.trait)} ${Math.round(s.score)}</span>`
        ).join('') || '<span class="ta-muted">None identified</span>'}
      </div>
    </div>
    <div class="ta-dd-section">
      <h4>Growth Areas</h4>
      <div class="tory-trait-list">
        ${gaps.map(g =>
          `<span class="tory-trait tory-trait-gap">${esc(g.trait)} ${Math.round(g.score)}</span>`
        ).join('') || '<span class="ta-muted">None identified</span>'}
      </div>
    </div>
  `;
  frag.appendChild(traits);

  // Full Path (recommendations)
  const pathSection = h('div', { class: 'ta-dd-section' });
  const recs = data.recommendations || [];
  pathSection.innerHTML = `
    <h4>Learning Path (${recs.length} lessons)</h4>
    <div class="ta-path-list">
      ${recs.map(r => `
        <div class="ta-path-item ${r.is_discovery ? 'discovery' : ''} ${r.locked_by_coach ? 'coach-modified' : ''}">
          <span class="ta-path-seq">#${r.sequence}</span>
          <div class="ta-path-info">
            <div class="ta-path-title">${esc(r.lesson_title || `Lesson ${r.nx_lesson_id}`)}</div>
            <div class="ta-path-journey">${esc(r.journey_title || '')}</div>
          </div>
          <div class="ta-path-meta">
            ${r.is_discovery ? '<span class="badge badge-purple badge-sm">Discovery</span>' : ''}
            ${r.locked_by_coach ? '<span class="badge badge-yellow badge-sm">Coach</span>' : ''}
            <span class="ta-path-score">${Math.round(r.match_score)}%</span>
          </div>
        </div>
      `).join('') || '<div class="ta-muted">No recommendations generated yet</div>'}
    </div>
  `;
  frag.appendChild(pathSection);

  // Path Events Timeline
  const eventsSection = h('div', { class: 'ta-dd-section' });
  const events = data.path_events || [];
  eventsSection.innerHTML = `
    <h4>Path Events Timeline (${events.length})</h4>
    <div class="ta-events-list">
      ${events.length === 0 ? '<div class="ta-muted">No path events recorded</div>' : ''}
      ${events.map(e => `
        <div class="ta-event-item">
          <span class="badge ${eventBadgeClass(e.event_type)} badge-sm">${esc(e.event_type)}</span>
          <div class="ta-event-details">
            ${e.coach_name ? `<span class="ta-event-coach">by ${esc(e.coach_name)}</span>` : ''}
            ${e.reason ? `<span class="ta-event-reason">${esc(e.reason)}</span>` : ''}
            ${e.divergence_pct != null ? `<span class="ta-event-divergence">${e.divergence_pct}% divergence${e.flagged_for_review ? ' (flagged)' : ''}</span>` : ''}
          </div>
          <span class="ta-event-time">${e.created_at ? timeAgo(e.created_at) : ''}</span>
        </div>
      `).join('')}
    </div>
  `;
  frag.appendChild(eventsSection);

  // Reassessment History
  const reassessSection = h('div', { class: 'ta-dd-section' });
  const reassessments = data.reassessment_history || [];
  reassessSection.innerHTML = `
    <h4>Reassessment History (${reassessments.length})</h4>
    <div class="ta-events-list">
      ${reassessments.length === 0 ? '<div class="ta-muted">No reassessments yet</div>' : ''}
      ${reassessments.map(ra => `
        <div class="ta-event-item">
          <span class="badge ${ra.status === 'completed' ? 'badge-green' : 'badge-yellow'} badge-sm">${esc(ra.type)}</span>
          <div class="ta-event-details">
            <span>${esc(ra.trigger_reason || '')}</span>
            <span class="badge ${ra.status === 'completed' ? 'badge-green' : ra.status === 'pending' ? 'badge-yellow' : 'badge-blue'} badge-sm">${esc(ra.status)}</span>
            ${ra.drift_detected ? '<span class="badge badge-red badge-sm">drift</span>' : ''}
            ${ra.path_action ? `<span class="ta-muted">${esc(ra.path_action)}</span>` : ''}
          </div>
          <span class="ta-event-time">${ra.created_at ? timeAgo(ra.created_at) : ''}</span>
        </div>
      `).join('')}
    </div>
  `;
  frag.appendChild(reassessSection);

  // Feedback History
  if (data.feedback_history && data.feedback_history.length > 0) {
    const fbSection = h('div', { class: 'ta-dd-section' });
    fbSection.innerHTML = `
      <h4>Feedback History (${data.feedback_history.length})</h4>
      <div class="ta-events-list">
        ${data.feedback_history.map(fb => `
          <div class="ta-event-item">
            <span class="badge badge-red badge-sm">${esc(fb.type)}</span>
            <div class="ta-event-details">
              ${fb.comment ? `<span>${esc(fb.comment)}</span>` : '<span class="ta-muted">No comment</span>'}
              <span class="ta-muted">Profile v${fb.profile_version}</span>
              ${fb.resolved ? '<span class="badge badge-green badge-sm">resolved</span>' : ''}
            </div>
            <span class="ta-event-time">${fb.created_at ? timeAgo(fb.created_at) : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
    frag.appendChild(fbSection);
  }

  return frag;
}


// ═══════════════════════════════════════════════════════════════════════════
// AGGREGATE METRICS
// ═══════════════════════════════════════════════════════════════════════════

function renderMetrics(state) {
  const frag = document.createDocumentFragment();
  const metrics = state.metrics;
  if (!metrics) {
    const empty = h('div', { class: 'ta-muted' }, 'No metrics data available');
    frag.appendChild(empty);
    return frag;
  }

  const summary = metrics.summary || {};

  // Metric cards
  const cards = h('div', { class: 'ta-metrics-grid' });
  cards.innerHTML = `
    <div class="dash-card">
      <div class="dash-card-label">Active Paths</div>
      <div class="dash-card-value">${summary.total_active_paths || 0}</div>
      <div class="dash-card-sub">${summary.total_profiles || 0} profiles total</div>
    </div>
    <div class="dash-card">
      <div class="dash-card-label">Avg Match Score</div>
      <div class="dash-card-value">${summary.avg_match_score || 0}%</div>
      <div class="dash-card-sub">Range: ${summary.min_match_score}% - ${summary.max_match_score}%</div>
    </div>
    <div class="dash-card">
      <div class="dash-card-label">Coach Intervention</div>
      <div class="dash-card-value">${summary.coach_intervention_rate || 0}%</div>
      <div class="dash-card-sub">${summary.coach_locked || 0} locked, ${summary.coach_sourced || 0} sourced</div>
    </div>
    <div class="dash-card">
      <div class="dash-card-label">Total Recommendations</div>
      <div class="dash-card-value">${summary.total_recommendations || 0}</div>
    </div>
  `;
  frag.appendChild(cards);

  // Content Review Status
  const reviewSection = h('div', { class: 'ta-dd-section' });
  const cr = metrics.content_review || {};
  reviewSection.innerHTML = `
    <h4>Content Tag Review Status</h4>
    <div class="ta-review-bars">
      ${Object.entries(cr).map(([status, info]) => `
        <div class="ta-review-bar-row">
          <span class="ta-review-label">${esc(status)}</span>
          <div class="ta-review-bar-track">
            <div class="ta-review-bar-fill ta-review-${status}" style="width:${Math.min(info.count * 2, 100)}%"></div>
          </div>
          <span class="ta-review-count">${info.count} (${info.avg_confidence}% avg conf)</span>
        </div>
      `).join('') || '<div class="ta-muted">No content tags</div>'}
    </div>
  `;
  frag.appendChild(reviewSection);

  // Content Gap Heatmap
  const heatmapSection = h('div', { class: 'ta-dd-section' });
  const gaps = metrics.content_gaps || [];
  const maxCount = Math.max(...gaps.map(g => g.lesson_count), 1);

  heatmapSection.innerHTML = `
    <h4>Content Gap Heatmap</h4>
    <p class="ta-heatmap-desc">EPP dimensions with fewer than 5 tagged lessons are highlighted as gaps.</p>
    <div class="ta-heatmap">
      ${gaps.map(g => {
        const intensity = Math.min(g.lesson_count / maxCount, 1);
        const cellClass = g.is_gap ? 'ta-heatmap-gap' : 'ta-heatmap-ok';
        return `
          <div class="ta-heatmap-cell ${cellClass}" title="${g.dimension}: ${g.lesson_count} lessons">
            <div class="ta-heatmap-label">${esc(formatDimension(g.dimension))}</div>
            <div class="ta-heatmap-value">${g.lesson_count}</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
  frag.appendChild(heatmapSection);

  // Event Breakdown
  const eventBreakdown = metrics.event_breakdown || {};
  if (Object.keys(eventBreakdown).length > 0) {
    const eventSection = h('div', { class: 'ta-dd-section' });
    eventSection.innerHTML = `
      <h4>Path Event Breakdown</h4>
      <div class="ta-event-breakdown">
        ${Object.entries(eventBreakdown).map(([type, count]) => `
          <div class="ta-breakdown-item">
            <span class="badge ${eventBadgeClass(type)} badge-sm">${esc(type)}</span>
            <span class="ta-breakdown-count">${count}</span>
          </div>
        `).join('')}
      </div>
    `;
    frag.appendChild(eventSection);
  }

  // Pedagogy Distribution
  const pedagogy = metrics.pedagogy_distribution || {};
  if (Object.keys(pedagogy).length > 0) {
    const pedSection = h('div', { class: 'ta-dd-section' });
    pedSection.innerHTML = `
      <h4>Pedagogy Mode Distribution</h4>
      <div class="ta-event-breakdown">
        ${Object.entries(pedagogy).map(([mode, count]) => `
          <div class="ta-breakdown-item">
            <span class="badge badge-blue badge-sm">${esc(mode)}</span>
            <span class="ta-breakdown-count">${count} learners</span>
          </div>
        `).join('')}
      </div>
    `;
    frag.appendChild(pedSection);
  }

  return frag;
}


// ── Helpers ──────────────────────────────────────────────────────────────────

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function phaseBadgeClass(phase) {
  switch (phase) {
    case 'discovery': return 'badge-purple';
    case 'active': return 'badge-green';
    case 'reassessed': return 'badge-blue';
    case 'profiled': return 'badge-yellow';
    default: return 'badge-blue';
  }
}

function eventBadgeClass(type) {
  switch (type) {
    case 'reordered': return 'badge-yellow';
    case 'swapped': return 'badge-blue';
    case 'locked': return 'badge-purple';
    case 'generated': return 'badge-green';
    default: return 'badge-blue';
  }
}

function formatDimension(dim) {
  // "JobFit_Accountability" → "Accountability"
  // "Self_Confidence" → "Self Conf."
  let label = dim.replace('JobFit_', '').replace(/_/g, ' ');
  if (label.length > 14) {
    // Abbreviate long names
    const words = label.split(' ');
    if (words.length > 1) {
      label = words[0] + ' ' + words.slice(1).map(w => w[0] + '.').join('');
    }
  }
  return label;
}

function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}
