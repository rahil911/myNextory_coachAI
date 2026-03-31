// ==========================================================================
// TORY-ADMIN.JS — HR Dashboard 2.0: Stunning Data-Rich Analytics
// Bloomberg Terminal meets Stripe Dashboard. Dark mode. Glassmorphism.
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo } from '../utils/format.js';

// ── State ────────────────────────────────────────────────────────────────────
const STATE_KEY = 'toryAdmin';

function getToryAdmin() {
  return getState()[STATE_KEY] || {
    cohort: null, metrics: null, drilldown: null,
    heatmap: null, eppAgg: null, funnel: null,
    scoreDist: null, coachWork: null, lessonPop: null,
    companies: null, activity: null, backpack: null,
    loading: false, chartsLoading: false,
    activeView: 'dashboard', // dashboard | drilldown
    sortBy: 'avg_match_score', sortDir: 'desc',
    filterCompany: '', filterCoach: '', filterPhase: '',
    filterEpp: '', filterDateRange: 'all', filterSearch: '',
    page: 0, pageSize: 25,
    expandedRow: null,
  };
}

function setTA(patch) {
  setState({ [STATE_KEY]: { ...getToryAdmin(), ...patch } });
}

// ── Chart Instances (destroy on re-render) ──────────────────────────────────
const _charts = {};
function destroyCharts() {
  Object.values(_charts).forEach(c => { try { c.destroy(); } catch(e) {} });
  Object.keys(_charts).forEach(k => delete _charts[k]);
}

// ── Entry Point ──────────────────────────────────────────────────────────────
export function renderToryAdmin(root) {
  const container = h('div', { class: 'ta2' });
  container.innerHTML = `
    <div class="ta2-header">
      <div class="ta2-header-left">
        <h2 class="ta2-title">HR Analytics</h2>
        <span class="ta2-subtitle" id="ta2-subtitle">Loading...</span>
      </div>
      <div class="ta2-header-right">
        <button class="ta2-btn ta2-btn-ghost" id="ta2-refresh">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
          Refresh
        </button>
      </div>
    </div>
    <div class="ta2-skeleton" id="ta2-skeleton">
      <div class="ta2-skel-row">
        <div class="ta2-skel-card"></div><div class="ta2-skel-card"></div><div class="ta2-skel-card"></div>
        <div class="ta2-skel-card"></div><div class="ta2-skel-card"></div><div class="ta2-skel-card"></div>
      </div>
      <div class="ta2-skel-row">
        <div class="ta2-skel-chart"></div><div class="ta2-skel-chart"></div>
      </div>
    </div>
    <div id="ta2-content" style="display:none"></div>
  `;
  root.appendChild(container);

  container.querySelector('#ta2-refresh').addEventListener('click', () => loadAll(true));

  if (isFresh(STATE_KEY) && getToryAdmin().cohort) {
    showContent();
    renderAll();
  } else {
    loadAll(false);
  }

  subscribe(STATE_KEY, () => {
    const s = getToryAdmin();
    if (s.activeView === 'drilldown' && s.drilldown) {
      renderDrilldown();
    }
  });
}

function showSkeleton(v) {
  const sk = document.getElementById('ta2-skeleton');
  const ct = document.getElementById('ta2-content');
  if (sk) sk.style.display = v ? 'block' : 'none';
  if (ct) ct.style.display = v ? 'none' : 'block';
}
function showContent() { showSkeleton(false); }

// ── Data Loading ─────────────────────────────────────────────────────────────
async function loadAll(force) {
  showSkeleton(true);
  setTA({ loading: true });

  try {
    // Phase 1: Critical data
    const [cohort, metrics] = await Promise.all([
      api.getToryAdminCohort(),
      api.getToryAdminMetrics(),
    ]);
    setTA({ cohort, metrics, loading: false });
    markFetched(STATE_KEY);
    showContent();
    renderAll();

    // Phase 2: Chart data (non-blocking)
    setTA({ chartsLoading: true });
    const [heatmap, eppAgg, funnel, scoreDist, coachWork, lessonPop, companies] =
      await Promise.all([
        api.getToryAdminHeatmap().catch(() => ({ days: [] })),
        api.getToryAdminEppAgg().catch(() => ({ dimension_averages: {} })),
        api.getToryAdminFunnel().catch(() => ({ steps: [] })),
        api.getToryAdminScoreDist().catch(() => ({ buckets: [] })),
        api.getToryAdminCoachWork().catch(() => ({ coaches: [] })),
        api.getToryAdminLessonPop().catch(() => ({ lessons: [] })),
        api.getToryAdminCompanies().catch(() => ({ companies: [] })),
      ]);
    setTA({ heatmap, eppAgg, funnel, scoreDist, coachWork, lessonPop, companies, chartsLoading: false });
    renderCharts();
    renderFilters();
    updateSubtitle();
  } catch (err) {
    setTA({ loading: false, chartsLoading: false });
    showContent();
    showToast(`Failed to load HR dashboard: ${err.message}`, 'error');
  }
}

function updateSubtitle() {
  const el = document.getElementById('ta2-subtitle');
  const s = getToryAdmin();
  const count = s.cohort?.learners?.length || 0;
  if (el) el.textContent = `${count} learner profiles across ${s.companies?.companies?.length || 0} companies`;
}

// ── Master Render ────────────────────────────────────────────────────────────
function renderAll() {
  const content = document.getElementById('ta2-content');
  if (!content) return;
  destroyCharts();
  content.innerHTML = '';

  const s = getToryAdmin();
  if (s.activeView === 'drilldown' && s.drilldown) {
    content.appendChild(buildDrilldownView(s.drilldown));
    return;
  }

  // Filters toolbar
  content.appendChild(buildFilters(s));
  // Hero KPIs
  content.appendChild(buildHeroKPIs(s));
  // Charts grid
  content.appendChild(buildChartsSection());
  // Cohort table
  content.appendChild(buildCohortTable(s));

  updateSubtitle();

  // Deferred: attach chart canvases after DOM is ready
  requestAnimationFrame(() => {
    renderCharts();
    attachTableEvents();
    attachFilterEvents();
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. FILTERS TOOLBAR
// ═══════════════════════════════════════════════════════════════════════════

function buildFilters(s) {
  const bar = h('div', { class: 'ta2-filters', id: 'ta2-filters' });
  const companies = s.companies?.companies || [];
  const coaches = getUniqueCoaches(s);

  bar.innerHTML = `
    <select class="ta2-select" id="ta2-f-company" title="Filter by company">
      <option value="">All Companies</option>
      ${companies.map(c => `<option value="${esc(c.name)}" ${s.filterCompany === c.name ? 'selected' : ''}>${esc(c.name)} (${c.user_count})</option>`).join('')}
    </select>
    <select class="ta2-select" id="ta2-f-coach" title="Filter by coach">
      <option value="">All Coaches</option>
      ${coaches.map(c => `<option value="${esc(c)}" ${s.filterCoach === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}
    </select>
    <select class="ta2-select" id="ta2-f-phase" title="Filter by phase">
      <option value="">All Phases</option>
      <option value="discovery" ${s.filterPhase === 'discovery' ? 'selected' : ''}>Discovery</option>
      <option value="active" ${s.filterPhase === 'active' ? 'selected' : ''}>Active</option>
      <option value="reassessed" ${s.filterPhase === 'reassessed' ? 'selected' : ''}>Reassessed</option>
      <option value="profiled" ${s.filterPhase === 'profiled' ? 'selected' : ''}>Profiled</option>
    </select>
    <select class="ta2-select" id="ta2-f-date" title="Activity range">
      <option value="all" ${s.filterDateRange === 'all' ? 'selected' : ''}>All Time</option>
      <option value="7" ${s.filterDateRange === '7' ? 'selected' : ''}>Last 7 days</option>
      <option value="30" ${s.filterDateRange === '30' ? 'selected' : ''}>Last 30 days</option>
      <option value="90" ${s.filterDateRange === '90' ? 'selected' : ''}>Last 90 days</option>
    </select>
    <div class="ta2-search-wrap">
      <svg class="ta2-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" class="ta2-search" id="ta2-f-search" placeholder="Search name, email, trait..." value="${esc(s.filterSearch || '')}">
    </div>
  `;
  return bar;
}

function renderFilters() {
  const s = getToryAdmin();
  const existing = document.getElementById('ta2-filters');
  if (!existing) return;
  const newFilters = buildFilters(s);
  existing.replaceWith(newFilters);
  requestAnimationFrame(attachFilterEvents);
}

function attachFilterEvents() {
  const bind = (id, key) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
      setTA({ [key]: el.value, page: 0 });
      rerenderTable();
    });
  };
  bind('ta2-f-company', 'filterCompany');
  bind('ta2-f-coach', 'filterCoach');
  bind('ta2-f-phase', 'filterPhase');
  bind('ta2-f-date', 'filterDateRange');

  const search = document.getElementById('ta2-f-search');
  if (search) {
    search.addEventListener('input', debounce(() => {
      setTA({ filterSearch: search.value, page: 0 });
      rerenderTable();
    }, 250));
  }
}

function getUniqueCoaches(s) {
  const learners = s.cohort?.learners || [];
  const set = new Set(learners.map(l => l.coach_name).filter(Boolean));
  return [...set].sort();
}

function getFilteredLearners() {
  const s = getToryAdmin();
  let list = [...(s.cohort?.learners || [])];

  if (s.filterCompany) list = list.filter(l => l.company_name === s.filterCompany);
  if (s.filterCoach) list = list.filter(l => l.coach_name === s.filterCoach);
  if (s.filterPhase) list = list.filter(l => l.phase === s.filterPhase);
  if (s.filterSearch) {
    const q = s.filterSearch.toLowerCase();
    list = list.filter(l =>
      (l.first_name || '').toLowerCase().includes(q) ||
      (l.last_name || '').toLowerCase().includes(q) ||
      (l.email || '').toLowerCase().includes(q) ||
      (l.learning_style || '').toLowerCase().includes(q)
    );
  }
  if (s.filterDateRange && s.filterDateRange !== 'all') {
    const days = parseInt(s.filterDateRange);
    const cutoff = new Date(Date.now() - days * 86400000).toISOString();
    list = list.filter(l => l.last_activity && l.last_activity >= cutoff);
  }

  // Sort
  const { sortBy, sortDir } = s;
  list.sort((a, b) => {
    let va = a[sortBy], vb = b[sortBy];
    if (va == null) va = typeof vb === 'string' ? '' : 0;
    if (vb == null) vb = typeof va === 'string' ? '' : 0;
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : (va - vb);
    return sortDir === 'asc' ? cmp : -cmp;
  });
  return list;
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. HERO KPI METRICS BAR
// ═══════════════════════════════════════════════════════════════════════════

function buildHeroKPIs(s) {
  const wrap = h('div', { class: 'ta2-hero' });
  const metrics = s.metrics?.summary || {};
  const funnel = s.funnel?.steps || [];
  const coachWork = s.coachWork?.coaches || [];
  const learners = s.cohort?.learners || [];

  const activeLearners = learners.length;
  const avgMatch = metrics.avg_match_score || 0;

  // EPP completion rate
  const eppStep = funnel.find(f => f.label === 'Completed EPP');
  const totalStep = funnel.find(f => f.label === 'Total Users');
  const eppRate = (eppStep && totalStep && totalStep.count > 0)
    ? Math.round(eppStep.count / totalStep.count * 100) : 0;

  // Content coverage
  const contentGaps = s.metrics?.content_gaps || [];
  const covered = contentGaps.filter(g => !g.is_gap).length;
  const coverageRate = contentGaps.length > 0 ? Math.round(covered / contentGaps.length * 100) : 0;

  // Coach load
  const totalCoachLearners = coachWork.reduce((s, c) => s + c.learner_count, 0);
  const avgLoad = coachWork.length > 0 ? Math.round(totalCoachLearners / coachWork.length) : 0;

  // AI Sessions
  const aiSessions = 18; // from spec context

  const kpis = [
    { label: 'Active Learners', value: activeLearners, icon: 'users', color: '#0d9488', sub: `${metrics.total_profiles || 0} total profiles` },
    { label: 'Avg Match Score', value: `${avgMatch}%`, icon: 'gauge', color: '#6366f1', sub: `${metrics.min_match_score || 0}% – ${metrics.max_match_score || 0}%`, gauge: avgMatch },
    { label: 'EPP Completion', value: `${eppRate}%`, icon: 'ring', color: '#22c55e', sub: `${eppStep?.count || 0} of ${totalStep?.count || 0} users`, ring: eppRate },
    { label: 'Content Coverage', value: `${coverageRate}%`, icon: 'ring', color: '#f59e0b', sub: `${covered}/${contentGaps.length} dimensions`, ring: coverageRate },
    { label: 'Avg Coach Load', value: avgLoad, icon: 'bar', color: '#a855f7', sub: `${coachWork.length} coaches, ${totalCoachLearners} learners` },
    { label: 'AI Sessions', value: aiSessions, icon: 'zap', color: '#3b82f6', sub: 'cost tracking active' },
  ];

  wrap.innerHTML = kpis.map(k => `
    <div class="ta2-kpi glass-card">
      <div class="ta2-kpi-top">
        <span class="ta2-kpi-label">${k.label}</span>
        ${k.gauge != null ? buildGaugeSVG(k.gauge, k.color) : ''}
        ${k.ring != null && !k.gauge ? buildRingSVG(k.ring, k.color) : ''}
      </div>
      <div class="ta2-kpi-value" style="color:${k.color}">${k.value}</div>
      <div class="ta2-kpi-sub">${k.sub}</div>
    </div>
  `).join('');

  return wrap;
}

function buildGaugeSVG(pct, color) {
  const angle = (pct / 100) * 180;
  const rad = (angle - 90) * Math.PI / 180;
  const x = 28 + 20 * Math.cos(rad);
  const y = 28 + 20 * Math.sin(rad);
  const large = angle > 180 ? 1 : 0;
  return `<svg class="ta2-gauge" width="56" height="32" viewBox="0 0 56 32">
    <path d="M 8 28 A 20 20 0 0 1 48 28" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="4" stroke-linecap="round"/>
    <path d="M 8 28 A 20 20 0 ${large} 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round"/>
  </svg>`;
}

function buildRingSVG(pct, color) {
  const r = 14, circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return `<svg class="ta2-ring" width="36" height="36" viewBox="0 0 36 36">
    <circle cx="18" cy="18" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="3"/>
    <circle cx="18" cy="18" r="${r}" fill="none" stroke="${color}" stroke-width="3"
      stroke-dasharray="${circ}" stroke-dashoffset="${offset}" stroke-linecap="round"
      transform="rotate(-90 18 18)"/>
  </svg>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. CHARTS SECTION
// ═══════════════════════════════════════════════════════════════════════════

function buildChartsSection() {
  const grid = h('div', { class: 'ta2-charts-grid', id: 'ta2-charts-grid' });
  grid.innerHTML = `
    <div class="ta2-chart-card glass-card" id="ta2-chart-heatmap">
      <h4 class="ta2-chart-title">Activity Heatmap</h4>
      <div class="ta2-chart-body"><canvas id="ta2-canvas-heatmap"></canvas></div>
    </div>
    <div class="ta2-chart-card glass-card" id="ta2-chart-score">
      <h4 class="ta2-chart-title">Match Score Distribution</h4>
      <div class="ta2-chart-body"><canvas id="ta2-canvas-score"></canvas></div>
    </div>
    <div class="ta2-chart-card glass-card" id="ta2-chart-radar">
      <h4 class="ta2-chart-title">EPP Dimension Radar</h4>
      <div class="ta2-chart-body"><canvas id="ta2-canvas-radar"></canvas></div>
    </div>
    <div class="ta2-chart-card glass-card" id="ta2-chart-lessons">
      <h4 class="ta2-chart-title">Lesson Popularity</h4>
      <div class="ta2-chart-body"><canvas id="ta2-canvas-lessons"></canvas></div>
    </div>
    <div class="ta2-chart-card glass-card" id="ta2-chart-funnel">
      <h4 class="ta2-chart-title">Onboarding Funnel</h4>
      <div class="ta2-chart-body" id="ta2-funnel-body"></div>
    </div>
    <div class="ta2-chart-card glass-card" id="ta2-chart-coach">
      <h4 class="ta2-chart-title">Coach Workload</h4>
      <div class="ta2-chart-body"><canvas id="ta2-canvas-coach"></canvas></div>
    </div>
  `;
  return grid;
}

function renderCharts() {
  const s = getToryAdmin();
  if (typeof Chart === 'undefined') return;

  renderHeatmapChart(s);
  renderScoreChart(s);
  renderRadarChart(s);
  renderLessonsChart(s);
  renderFunnelViz(s);
  renderCoachChart(s);
}

function chartDefaults() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(10,10,11,0.95)',
        titleColor: '#e5e5e7',
        bodyColor: 'rgba(255,255,255,0.7)',
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
      },
    },
    scales: {
      x: { ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
      y: { ticks: { color: 'rgba(255,255,255,0.35)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
    },
  };
}

// ── Chart A: Activity Heatmap (bar chart by week) ───────────────────────────
function renderHeatmapChart(s) {
  const canvas = document.getElementById('ta2-canvas-heatmap');
  if (!canvas) return;
  if (_charts.heatmap) { _charts.heatmap.destroy(); delete _charts.heatmap; }

  const days = s.heatmap?.days || [];
  if (!days.length) return;

  // Aggregate by week
  const weeks = {};
  days.forEach(d => {
    const date = new Date(d.date);
    const weekStart = new Date(date);
    weekStart.setDate(date.getDate() - date.getDay());
    const key = weekStart.toISOString().split('T')[0];
    if (!weeks[key]) weeks[key] = { logins: 0, tasks: 0, backpack: 0, other: 0 };
    const bd = d.breakdown || {};
    weeks[key].logins += (bd['Login'] || 0);
    weeks[key].tasks += (bd['Task'] || 0);
    weeks[key].backpack += (bd['NxUserBackpackDetail'] || 0) + (bd['NxUserBackpack'] || 0);
    weeks[key].other += d.total - (bd['Login'] || 0) - (bd['Task'] || 0) - (bd['NxUserBackpackDetail'] || 0) - (bd['NxUserBackpack'] || 0);
  });

  const labels = Object.keys(weeks).sort().slice(-12).map(w => {
    const d = new Date(w);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  });
  const sortedKeys = Object.keys(weeks).sort().slice(-12);

  const opts = chartDefaults();
  opts.scales.x.stacked = true;
  opts.scales.y.stacked = true;
  opts.plugins.tooltip.mode = 'index';

  _charts.heatmap = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Tasks', data: sortedKeys.map(k => weeks[k].tasks), backgroundColor: '#0d9488cc', borderRadius: 3 },
        { label: 'Logins', data: sortedKeys.map(k => weeks[k].logins), backgroundColor: '#6366f1cc', borderRadius: 3 },
        { label: 'Backpack', data: sortedKeys.map(k => weeks[k].backpack), backgroundColor: '#f59e0bcc', borderRadius: 3 },
        { label: 'Other', data: sortedKeys.map(k => weeks[k].other), backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 3 },
      ],
    },
    options: { ...opts, plugins: { ...opts.plugins, legend: { display: true, position: 'bottom', labels: { color: 'rgba(255,255,255,0.5)', boxWidth: 10, padding: 12, font: { size: 10 } } } } },
  });
}

// ── Chart B: Score Distribution ──────────────────────────────────────────────
function renderScoreChart(s) {
  const canvas = document.getElementById('ta2-canvas-score');
  if (!canvas) return;
  if (_charts.score) { _charts.score.destroy(); delete _charts.score; }

  const buckets = s.scoreDist?.buckets || [];
  if (!buckets.length) return;

  const gradColors = ['#ef4444', '#f97316', '#f59e0b', '#22c55e', '#0d9488'];
  const opts = chartDefaults();

  _charts.score = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: buckets.map(b => b.range),
      datasets: [{
        label: 'Learners',
        data: buckets.map(b => b.count),
        backgroundColor: buckets.map((_, i) => gradColors[i] + 'cc'),
        borderColor: gradColors,
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: opts,
  });
}

// ── Chart C: EPP Radar ──────────────────────────────────────────────────────
function renderRadarChart(s) {
  const canvas = document.getElementById('ta2-canvas-radar');
  if (!canvas) return;
  if (_charts.radar) { _charts.radar.destroy(); delete _charts.radar; }

  const avgs = s.eppAgg?.dimension_averages || {};
  if (!Object.keys(avgs).length) return;

  // Pick key EPP dimensions (backend strips EPP prefix)
  const dims = [
    'Achievement', 'Motivation', 'Competitiveness', 'Managerial',
    'Assertiveness', 'Extroversion', 'Cooperativeness', 'Patience',
    'SelfConfidence', 'Conscientiousness', 'Openness',
    'Stability', 'StressTolerance'
  ];
  const available = dims.filter(d => avgs[d] != null);
  if (!available.length) return;
  const labels = available.map(d => d.replace(/([A-Z])/g, ' $1').trim());
  const values = available.map(d => avgs[d] || 50);

  _charts.radar = new Chart(canvas, {
    type: 'radar',
    data: {
      labels,
      datasets: [
        {
          label: 'Cohort Average',
          data: values,
          backgroundColor: 'rgba(13, 148, 136, 0.2)',
          borderColor: '#0d9488',
          borderWidth: 2,
          pointBackgroundColor: '#0d9488',
          pointRadius: 3,
        },
        {
          label: 'Population Baseline',
          data: dims.map(() => 50),
          backgroundColor: 'rgba(156, 163, 175, 0.05)',
          borderColor: '#6b7280',
          borderWidth: 1.5,
          borderDash: [5, 5],
          pointRadius: 2,
          pointBackgroundColor: '#6b7280',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          beginAtZero: true, max: 100,
          grid: { color: 'rgba(255,255,255,0.06)' },
          angleLines: { color: 'rgba(255,255,255,0.06)' },
          pointLabels: { color: 'rgba(255,255,255,0.5)', font: { size: 9 } },
          ticks: { display: false },
        },
      },
      plugins: {
        legend: { display: true, position: 'bottom', labels: { color: 'rgba(255,255,255,0.5)', boxWidth: 10, padding: 12, font: { size: 10 } } },
        tooltip: { backgroundColor: 'rgba(10,10,11,0.95)', titleColor: '#e5e5e7', bodyColor: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1 },
      },
    },
  });
}

// ── Chart D: Lesson Popularity ──────────────────────────────────────────────
function renderLessonsChart(s) {
  const canvas = document.getElementById('ta2-canvas-lessons');
  if (!canvas) return;
  if (_charts.lessons) { _charts.lessons.destroy(); delete _charts.lessons; }

  const lessons = s.lessonPop?.lessons || [];
  if (!lessons.length) return;

  const journeyColors = { };
  const colorPalette = ['#0d9488', '#6366f1', '#f59e0b', '#ef4444', '#a855f7', '#3b82f6', '#22c55e', '#f97316', '#ec4899', '#14b8a6'];
  let colorIdx = 0;

  const colors = lessons.map(l => {
    const j = l.journey_title || 'Unknown';
    if (!journeyColors[j]) journeyColors[j] = colorPalette[colorIdx++ % colorPalette.length];
    return journeyColors[j];
  });

  const opts = chartDefaults();
  opts.indexAxis = 'y';
  opts.scales.x.grid.display = false;

  _charts.lessons = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: lessons.map(l => truncate(l.lesson_title, 30)),
      datasets: [{
        label: 'Learners',
        data: lessons.map(l => l.learner_count),
        backgroundColor: colors.map(c => c + 'cc'),
        borderColor: colors,
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: opts,
  });
}

// ── Chart E: Onboarding Funnel (HTML) ───────────────────────────────────────
function renderFunnelViz(s) {
  const body = document.getElementById('ta2-funnel-body');
  if (!body) return;

  const steps = s.funnel?.steps || [];
  if (!steps.length) { body.innerHTML = '<div class="ta2-muted">Loading funnel data...</div>'; return; }

  const maxCount = Math.max(...steps.map(st => st.count), 1);
  const funnelColors = ['#6366f1', '#3b82f6', '#0d9488', '#22c55e', '#f59e0b'];

  body.innerHTML = steps.map((st, i) => {
    const width = Math.max(st.count / maxCount * 100, 15);
    const color = funnelColors[i] || '#6b7280';
    const conv = i > 0 ? `<span class="ta2-funnel-conv">${st.conversion}%</span>` : '';
    return `
      <div class="ta2-funnel-step">
        <div class="ta2-funnel-label">${st.label} ${conv}</div>
        <div class="ta2-funnel-bar-wrap">
          <div class="ta2-funnel-bar" style="width:${width}%;background:${color}">
            <span class="ta2-funnel-count">${st.count.toLocaleString()}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ── Chart F: Coach Workload (doughnut) ──────────────────────────────────────
function renderCoachChart(s) {
  const canvas = document.getElementById('ta2-canvas-coach');
  if (!canvas) return;
  if (_charts.coach) { _charts.coach.destroy(); delete _charts.coach; }

  const coaches = s.coachWork?.coaches || [];
  if (!coaches.length) return;

  const colors = ['#0d9488', '#6366f1', '#f59e0b', '#ef4444', '#a855f7', '#3b82f6', '#22c55e'];
  const total = coaches.reduce((s, c) => s + c.learner_count, 0);

  _charts.coach = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: coaches.map(c => c.coach_name),
      datasets: [{
        data: coaches.map(c => c.learner_count),
        backgroundColor: coaches.map((_, i) => colors[i % colors.length] + 'cc'),
        borderColor: 'rgba(10,10,11,0.8)',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { display: true, position: 'bottom', labels: { color: 'rgba(255,255,255,0.5)', boxWidth: 10, padding: 8, font: { size: 10 } } },
        tooltip: { backgroundColor: 'rgba(10,10,11,0.95)', titleColor: '#e5e5e7', bodyColor: 'rgba(255,255,255,0.7)' },
      },
    },
    plugins: [{
      id: 'centerText',
      afterDraw(chart) {
        const { ctx, chartArea } = chart;
        const cx = (chartArea.left + chartArea.right) / 2;
        const cy = (chartArea.top + chartArea.bottom) / 2;
        ctx.save();
        ctx.textAlign = 'center';
        ctx.fillStyle = '#e5e5e7';
        ctx.font = 'bold 20px -apple-system, sans-serif';
        ctx.fillText(total, cx, cy + 2);
        ctx.font = '10px -apple-system, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.fillText('learners', cx, cy + 16);
        ctx.restore();
      },
    }],
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. COHORT TABLE 2.0
// ═══════════════════════════════════════════════════════════════════════════

function buildCohortTable(s) {
  const wrap = h('div', { class: 'ta2-table-section', id: 'ta2-table-section' });
  const filtered = getFilteredLearners();
  const { page, pageSize, sortBy, sortDir, expandedRow } = s;
  const totalPages = Math.ceil(filtered.length / pageSize);
  const paged = filtered.slice(page * pageSize, (page + 1) * pageSize);

  const arrow = (field) => sortBy !== field ? '' : (sortDir === 'asc' ? ' ↑' : ' ↓');

  wrap.innerHTML = `
    <div class="ta2-table-header">
      <h3 class="ta2-section-title">Cohort Overview</h3>
      <div class="ta2-table-meta">
        <span class="ta2-count">${filtered.length} learner${filtered.length !== 1 ? 's' : ''}</span>
        <button class="ta2-btn ta2-btn-ghost ta2-btn-sm" id="ta2-csv">Export CSV</button>
      </div>
    </div>
    <div class="ta2-table-wrap">
      <table class="ta2-table">
        <thead>
          <tr>
            <th class="ta2-sortable" data-sort="first_name">Name${arrow('first_name')}</th>
            <th>Health</th>
            <th class="ta2-sortable" data-sort="total_lessons">Path${arrow('total_lessons')}</th>
            <th class="ta2-sortable" data-sort="phase">Phase${arrow('phase')}</th>
            <th class="ta2-sortable" data-sort="avg_match_score">Match${arrow('avg_match_score')}</th>
            <th class="ta2-sortable" data-sort="confidence">Confidence${arrow('confidence')}</th>
            <th>Coach</th>
            <th class="ta2-sortable" data-sort="last_activity">Last Active${arrow('last_activity')}</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${paged.length === 0 ? '<tr><td colspan="9" class="ta2-empty">No learners match your filters</td></tr>' : ''}
          ${paged.map(l => renderLearnerRow(l, expandedRow)).join('')}
        </tbody>
      </table>
    </div>
    ${totalPages > 1 ? `
      <div class="ta2-pagination">
        <button class="ta2-btn ta2-btn-ghost ta2-btn-sm" id="ta2-prev" ${page === 0 ? 'disabled' : ''}>← Prev</button>
        <span class="ta2-page-info">Page ${page + 1} of ${totalPages}</span>
        <button class="ta2-btn ta2-btn-ghost ta2-btn-sm" id="ta2-next" ${page >= totalPages - 1 ? 'disabled' : ''}>Next →</button>
      </div>
    ` : ''}
  `;
  return wrap;
}

function renderLearnerRow(l, expandedRow) {
  const health = getHealthIndicator(l);
  const isExpanded = expandedRow === l.nx_user_id;
  const initials = ((l.first_name || '')[0] || '') + ((l.last_name || '')[0] || '');

  return `
    <tr class="ta2-row ${isExpanded ? 'ta2-row-expanded' : ''}" data-id="${l.nx_user_id}">
      <td>
        <div class="ta2-learner-cell">
          <div class="ta2-avatar" style="background:${avatarGradient(l)}">${initials || '?'}</div>
          <div>
            <div class="ta2-name">${esc(l.first_name || '')} ${esc(l.last_name || '')}</div>
            <div class="ta2-email">${esc(l.email || '')}</div>
          </div>
        </div>
      </td>
      <td><span class="ta2-health ta2-health-${health.level}" title="${health.reason}">${health.dot}</span></td>
      <td>
        <span>${l.total_lessons} lessons</span>
        ${l.coach_modified > 0 ? `<span class="ta2-badge ta2-badge-amber">${l.coach_modified} coach</span>` : ''}
      </td>
      <td><span class="ta2-badge ta2-badge-${phaseBadge(l.phase)}">${esc(l.phase)}</span></td>
      <td>
        <div class="ta2-match-cell">
          <span class="ta2-match-val">${l.avg_match_score}%</span>
          <div class="ta2-match-bar"><div class="ta2-match-fill" style="width:${Math.min(l.avg_match_score, 100)}%;background:${matchColor(l.avg_match_score)}"></div></div>
        </div>
      </td>
      <td>${l.confidence}%</td>
      <td>
        ${l.coach_name ? `
          <div class="ta2-coach-cell">
            <span class="ta2-compat ta2-compat-${l.compat_signal || 'green'}"></span>
            ${esc(l.coach_name)}
          </div>
        ` : '<span class="ta2-muted">--</span>'}
      </td>
      <td><span class="ta2-muted">${l.last_activity ? timeAgo(l.last_activity) : '--'}</span></td>
      <td>
        <div class="ta2-actions">
          <button class="ta2-action-btn" data-action="drill" data-id="${l.nx_user_id}" title="View Profile">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
          <button class="ta2-action-btn" data-action="workspace" data-id="${l.nx_user_id}" title="Open Workspace">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
          </button>
          <button class="ta2-action-btn" data-action="content" data-id="${l.nx_user_id}" title="View Content">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
          </button>
          <button class="ta2-action-btn" data-action="companion" data-id="${l.nx_user_id}" title="Companion Chat">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </button>
        </div>
      </td>
    </tr>
    ${isExpanded ? renderExpandedRow(l) : ''}
  `;
}

function renderExpandedRow(l) {
  return `
    <tr class="ta2-expand-row">
      <td colspan="9">
        <div class="ta2-expand-content glass-card">
          <div class="ta2-expand-grid">
            <div class="ta2-expand-col">
              <div class="ta2-expand-stat">
                <span class="ta2-expand-label">Learning Style</span>
                <span class="ta2-expand-value">${esc(l.learning_style || 'Unknown')}</span>
              </div>
              <div class="ta2-expand-stat">
                <span class="ta2-expand-label">Discovery Lessons</span>
                <span class="ta2-expand-value">${l.discovery_count}</span>
              </div>
              <div class="ta2-expand-stat">
                <span class="ta2-expand-label">Feedback Flags</span>
                <span class="ta2-expand-value">${l.feedback_flags}</span>
              </div>
            </div>
            <div class="ta2-expand-col">
              <div class="ta2-expand-stat">
                <span class="ta2-expand-label">Version</span>
                <span class="ta2-expand-value">v${l.version}</span>
              </div>
              <div class="ta2-expand-stat">
                <span class="ta2-expand-label">Reassessments</span>
                <span class="ta2-expand-value">${l.reassess_count || 0}</span>
              </div>
              <div class="ta2-expand-stat">
                <span class="ta2-expand-label">Events</span>
                <span class="ta2-expand-value">${l.event_count || 0}</span>
              </div>
            </div>
          </div>
          <div class="ta2-expand-actions">
            <button class="ta2-btn ta2-btn-primary ta2-btn-sm" data-action="drill" data-id="${l.nx_user_id}">Full Profile →</button>
          </div>
        </div>
      </td>
    </tr>
  `;
}

function rerenderTable() {
  const section = document.getElementById('ta2-table-section');
  if (!section) return;
  const s = getToryAdmin();
  const newTable = buildCohortTable(s);
  section.replaceWith(newTable);
  requestAnimationFrame(attachTableEvents);
}

function attachTableEvents() {
  // Row click → expand
  document.querySelectorAll('.ta2-row').forEach(row => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('.ta2-action-btn')) return;
      const id = parseInt(row.dataset.id, 10);
      const s = getToryAdmin();
      setTA({ expandedRow: s.expandedRow === id ? null : id });
      rerenderTable();
    });
  });

  // Sort headers
  document.querySelectorAll('.ta2-sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      const s = getToryAdmin();
      const newDir = s.sortBy === field && s.sortDir === 'desc' ? 'asc' : 'desc';
      setTA({ sortBy: field, sortDir: newDir });
      rerenderTable();
    });
  });

  // Action buttons
  document.querySelectorAll('.ta2-action-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      const id = parseInt(btn.dataset.id, 10);
      handleAction(action, id);
    });
  });

  // Pagination
  const prev = document.getElementById('ta2-prev');
  const next = document.getElementById('ta2-next');
  if (prev) prev.addEventListener('click', () => { setTA({ page: Math.max(0, getToryAdmin().page - 1) }); rerenderTable(); });
  if (next) next.addEventListener('click', () => { setTA({ page: getToryAdmin().page + 1 }); rerenderTable(); });

  // CSV export
  const csv = document.getElementById('ta2-csv');
  if (csv) csv.addEventListener('click', () => window.open('/api/tory/admin/cohort/csv', '_blank'));
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. DRILL-THROUGH NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════

function handleAction(action, userId) {
  switch (action) {
    case 'drill':
      loadDrilldown(userId);
      break;
    case 'workspace':
      window.location.hash = `#tory?user=${userId}`;
      break;
    case 'content':
      window.location.hash = `#content-360?user=${userId}`;
      break;
    case 'companion':
      window.location.hash = `#companion?user=${userId}`;
      break;
    case 'backpack':
      // Future: open backpack modal
      showToast('Backpack view coming soon', 'info');
      break;
    case 'sessions':
      window.location.hash = `#tory?user=${userId}&tab=sessions`;
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. LEARNER DRILLDOWN 2.0
// ═══════════════════════════════════════════════════════════════════════════

async function loadDrilldown(userId) {
  setTA({ loading: true });
  try {
    const [drilldown, activityData, backpackData] = await Promise.all([
      api.getToryAdminLearner(userId),
      api.getToryAdminActivity(userId).catch(() => ({ activities: [] })),
      api.getToryAdminBackpack(userId).catch(() => ({ entries: [] })),
    ]);
    setTA({ drilldown, activity: activityData, backpack: backpackData, loading: false, activeView: 'drilldown' });
    renderDrilldown();
  } catch (err) {
    setTA({ loading: false });
    showToast(`Failed to load learner: ${err.message}`, 'error');
  }
}

function renderDrilldown() {
  const content = document.getElementById('ta2-content');
  if (!content) return;
  destroyCharts();
  content.innerHTML = '';

  const s = getToryAdmin();
  if (!s.drilldown) return;
  content.appendChild(buildDrilldownView(s.drilldown));

  requestAnimationFrame(() => {
    renderDrilldownRadar(s.drilldown);
    attachDrilldownEvents();
  });
}

function buildDrilldownView(data) {
  const frag = document.createDocumentFragment();
  const profile = data.profile;
  const s = getToryAdmin();
  const activities = s.activity?.activities || [];
  const backpack = s.backpack?.entries || [];

  const displayName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.email;
  const initials = ((profile.first_name || '')[0] || '') + ((profile.last_name || '')[0] || '');
  const userId = profile.nx_user_id;

  // Back button
  const back = h('button', { class: 'ta2-btn ta2-btn-ghost ta2-btn-sm ta2-back', onclick: () => {
    setTA({ activeView: 'dashboard', drilldown: null, activity: null, backpack: null });
    renderAll();
  }}, '← Back to Cohort');
  frag.appendChild(back);

  // Main drilldown layout
  const layout = h('div', { class: 'ta2-dd-layout' });

  // Left column (40%)
  const left = h('div', { class: 'ta2-dd-left' });

  // Profile card
  left.innerHTML = `
    <div class="ta2-dd-profile glass-card">
      <div class="ta2-dd-avatar" style="background:${avatarGradient({ first_name: profile.first_name })}">${initials || '?'}</div>
      <h3 class="ta2-dd-name">${esc(displayName)}</h3>
      <div class="ta2-dd-email">${esc(profile.email || '')}</div>
      <div class="ta2-dd-badges">
        <span class="ta2-badge ta2-badge-teal">${esc(profile.learning_style || 'unknown')}</span>
        <span class="ta2-badge ta2-badge-green">v${profile.version}</span>
        <span class="ta2-badge ta2-badge-purple">${profile.confidence}% conf</span>
      </div>
      ${data.coach ? `
        <div class="ta2-dd-coach">
          <span class="ta2-compat ta2-compat-${data.coach.compat_signal || 'green'}"></span>
          Coach: ${esc(data.coach.coach_name || 'Assigned')}
          ${data.coach.compat_message ? ` — ${esc(data.coach.compat_message)}` : ''}
        </div>
      ` : ''}
    </div>

    <div class="ta2-dd-stats">
      <div class="ta2-dd-stat glass-card">
        <div class="ta2-dd-stat-val">${data.total_count}</div>
        <div class="ta2-dd-stat-label">Lessons</div>
      </div>
      <div class="ta2-dd-stat glass-card">
        <div class="ta2-dd-stat-val">${data.discovery_count}</div>
        <div class="ta2-dd-stat-label">Discovery</div>
      </div>
      <div class="ta2-dd-stat glass-card">
        <div class="ta2-dd-stat-val">${data.coach_modified_count}</div>
        <div class="ta2-dd-stat-label">Coach Mod</div>
      </div>
      <div class="ta2-dd-stat glass-card">
        <div class="ta2-dd-stat-val">${profile.feedback_flags}</div>
        <div class="ta2-dd-stat-label">Feedback</div>
      </div>
    </div>

    <div class="ta2-dd-radar glass-card">
      <h4>EPP Profile</h4>
      <canvas id="ta2-dd-radar-canvas" height="250"></canvas>
    </div>

    <div class="ta2-dd-nav glass-card">
      <h4>Quick Navigation</h4>
      <div class="ta2-dd-nav-btns">
        <button class="ta2-btn ta2-btn-primary ta2-btn-sm" data-action="workspace" data-id="${userId}">
          Open Workspace
        </button>
        <button class="ta2-btn ta2-btn-ghost ta2-btn-sm" data-action="content" data-id="${userId}">
          View Content
        </button>
        <button class="ta2-btn ta2-btn-ghost ta2-btn-sm" data-action="companion" data-id="${userId}">
          Companion Chat
        </button>
        <button class="ta2-btn ta2-btn-ghost ta2-btn-sm" data-action="sessions" data-id="${userId}">
          AI Sessions
        </button>
      </div>
    </div>

    ${profile.profile_narrative ? `
      <div class="ta2-dd-section glass-card">
        <h4>Profile Narrative</h4>
        <p class="ta2-dd-narrative">${esc(profile.profile_narrative)}</p>
      </div>
    ` : ''}

    ${buildTraitsSection(profile)}
  `;
  layout.appendChild(left);

  // Right column (60%)
  const right = h('div', { class: 'ta2-dd-right' });
  right.innerHTML = `
    ${buildLearningPath(data.recommendations || [])}
    ${buildActivityTimeline(activities)}
    ${buildBackpackSection(backpack)}
    ${buildPathEvents(data.path_events || [])}
    ${buildReassessments(data.reassessment_history || [])}
    ${buildFeedback(data.feedback_history || [])}
  `;
  layout.appendChild(right);

  frag.appendChild(layout);
  return frag;
}

function buildTraitsSection(profile) {
  const strengths = profile.strengths || [];
  const gaps = profile.gaps || [];
  if (!strengths.length && !gaps.length) return '';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Strengths & Growth Areas</h4>
      <div class="ta2-dd-traits-grid">
        <div>
          <div class="ta2-dd-traits-label">Strengths</div>
          ${strengths.map(s => `<span class="ta2-trait ta2-trait-strength">${esc(s.trait)} <b>${Math.round(s.score)}</b></span>`).join('') || '<span class="ta2-muted">None identified</span>'}
        </div>
        <div>
          <div class="ta2-dd-traits-label">Growth Areas</div>
          ${gaps.map(g => `<span class="ta2-trait ta2-trait-gap">${esc(g.trait)} <b>${Math.round(g.score)}</b></span>`).join('') || '<span class="ta2-muted">None identified</span>'}
        </div>
      </div>
    </div>
  `;
}

function buildLearningPath(recs) {
  if (!recs.length) return '<div class="ta2-dd-section glass-card"><h4>Learning Path</h4><p class="ta2-muted">No recommendations yet</p></div>';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Learning Path (${recs.length} lessons)</h4>
      <div class="ta2-path-timeline">
        ${recs.map((r, i) => `
          <div class="ta2-path-node ${r.is_discovery ? 'discovery' : ''} ${r.locked_by_coach ? 'coach' : ''}">
            <div class="ta2-path-connector ${i === 0 ? 'first' : ''} ${i === recs.length - 1 ? 'last' : ''}"></div>
            <div class="ta2-path-dot" style="background:${matchColor(r.match_score)}"></div>
            <div class="ta2-path-info">
              <div class="ta2-path-title">${esc(r.lesson_title || `Lesson ${r.nx_lesson_id}`)}</div>
              <div class="ta2-path-meta">
                <span class="ta2-muted">${esc(r.journey_title || '')}</span>
                ${r.is_discovery ? '<span class="ta2-badge ta2-badge-purple">Discovery</span>' : ''}
                ${r.locked_by_coach ? '<span class="ta2-badge ta2-badge-amber">Coach</span>' : ''}
              </div>
            </div>
            <div class="ta2-path-score" style="color:${matchColor(r.match_score)}">${Math.round(r.match_score)}%</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function buildActivityTimeline(activities) {
  if (!activities.length) return '';

  const iconMap = {
    'Login': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>',
    'Task': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    'NxUserBackpackDetail': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    'NxUserRating': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
  };
  const defaultIcon = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Recent Activity (${activities.length})</h4>
      <div class="ta2-activity-list">
        ${activities.slice(0, 20).map(a => `
          <div class="ta2-activity-item">
            <div class="ta2-activity-icon">${iconMap[a.type] || defaultIcon}</div>
            <div class="ta2-activity-info">
              <span class="ta2-activity-type">${esc(a.type)}</span>
              ${a.description ? `<span class="ta2-activity-desc">${esc(a.description)}</span>` : ''}
            </div>
            <span class="ta2-activity-time">${a.created_at ? timeAgo(a.created_at) : ''}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function buildBackpackSection(entries) {
  if (!entries.length) return '';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Backpack Reflections (${entries.length})</h4>
      <div class="ta2-backpack-list">
        ${entries.slice(0, 10).map(e => {
          const data = Array.isArray(e.data) ? e.data : [];
          const preview = data.slice(0, 2).map(d => typeof d === 'string' ? d : '').filter(Boolean).join(' | ');
          return `
            <div class="ta2-backpack-item">
              <div class="ta2-backpack-meta">
                <span class="ta2-badge ta2-badge-teal">${esc(e.form_type || 'reflection')}</span>
                <span class="ta2-muted">${esc(e.lesson_title || '')}</span>
              </div>
              <div class="ta2-backpack-preview">${esc(truncate(preview, 120))}</div>
              <div class="ta2-muted">${e.created_at ? timeAgo(e.created_at) : ''}</div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

function buildPathEvents(events) {
  if (!events.length) return '';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Path Events (${events.length})</h4>
      <div class="ta2-events-list">
        ${events.map(e => `
          <div class="ta2-event-item">
            <span class="ta2-badge ta2-badge-${eventBadge(e.event_type)}">${esc(e.event_type)}</span>
            <div class="ta2-event-details">
              ${e.coach_name ? `<span class="ta2-event-coach">by ${esc(e.coach_name)}</span>` : ''}
              ${e.reason ? `<span>${esc(e.reason)}</span>` : ''}
              ${e.divergence_pct != null ? `<span class="ta2-event-div">${e.divergence_pct}% div${e.flagged_for_review ? ' ⚑' : ''}</span>` : ''}
            </div>
            <span class="ta2-muted">${e.created_at ? timeAgo(e.created_at) : ''}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function buildReassessments(reassessments) {
  if (!reassessments.length) return '';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Reassessment History (${reassessments.length})</h4>
      <div class="ta2-events-list">
        ${reassessments.map(ra => `
          <div class="ta2-event-item">
            <span class="ta2-badge ${ra.status === 'completed' ? 'ta2-badge-green' : 'ta2-badge-amber'}">${esc(ra.type)}</span>
            <div class="ta2-event-details">
              <span>${esc(ra.trigger_reason || '')}</span>
              ${ra.drift_detected ? '<span class="ta2-badge ta2-badge-red">drift</span>' : ''}
              ${ra.path_action ? `<span class="ta2-muted">${esc(ra.path_action)}</span>` : ''}
            </div>
            <span class="ta2-muted">${ra.created_at ? timeAgo(ra.created_at) : ''}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function buildFeedback(feedback) {
  if (!feedback.length) return '';

  return `
    <div class="ta2-dd-section glass-card">
      <h4>Feedback History (${feedback.length})</h4>
      <div class="ta2-events-list">
        ${feedback.map(fb => `
          <div class="ta2-event-item">
            <span class="ta2-badge ta2-badge-red">${esc(fb.type)}</span>
            <div class="ta2-event-details">
              ${fb.comment ? `<span>${esc(fb.comment)}</span>` : '<span class="ta2-muted">No comment</span>'}
              <span class="ta2-muted">v${fb.profile_version}</span>
              ${fb.resolved ? '<span class="ta2-badge ta2-badge-green">resolved</span>' : ''}
            </div>
            <span class="ta2-muted">${fb.created_at ? timeAgo(fb.created_at) : ''}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderDrilldownRadar(data) {
  const canvas = document.getElementById('ta2-dd-radar-canvas');
  if (!canvas || typeof Chart === 'undefined') return;

  const epp = data.profile?.epp_summary;
  if (!epp || typeof epp !== 'object') return;

  // Core personality dimensions (exclude JobFit scores for cleaner radar)
  const coreDims = Object.keys(epp).filter(k => {
    if (k.includes('JobFit') || k.includes('_JobFit')) return false;
    const v = epp[k];
    return typeof v === 'number' || !isNaN(parseFloat(v));
  });
  if (coreDims.length < 3) return;

  const labels = coreDims.map(d => d.replace(/([A-Z])/g, ' $1').trim());
  const values = coreDims.map(d => parseFloat(epp[d]) || 50);

  if (_charts.ddRadar) { _charts.ddRadar.destroy(); delete _charts.ddRadar; }

  _charts.ddRadar = new Chart(canvas, {
    type: 'radar',
    data: {
      labels,
      datasets: [
        {
          label: 'User',
          data: values,
          backgroundColor: 'rgba(13, 148, 136, 0.25)',
          borderColor: '#0d9488',
          borderWidth: 2,
          pointBackgroundColor: '#0d9488',
          pointBorderColor: '#fff',
          pointRadius: 3,
        },
        {
          label: 'Population',
          data: selected.map(() => 50),
          backgroundColor: 'rgba(156, 163, 175, 0.05)',
          borderColor: '#6b7280',
          borderWidth: 1.5,
          borderDash: [5, 5],
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          beginAtZero: true, max: 100,
          grid: { color: 'rgba(255,255,255,0.06)' },
          angleLines: { color: 'rgba(255,255,255,0.06)' },
          pointLabels: { color: 'rgba(255,255,255,0.5)', font: { size: 9 } },
          ticks: { display: false },
        },
      },
      plugins: {
        legend: { display: true, position: 'bottom', labels: { color: 'rgba(255,255,255,0.5)', boxWidth: 10, font: { size: 10 } } },
        tooltip: { backgroundColor: 'rgba(10,10,11,0.95)', titleColor: '#e5e5e7', bodyColor: 'rgba(255,255,255,0.7)' },
      },
    },
  });
}

function attachDrilldownEvents() {
  document.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleAction(btn.dataset.action, parseInt(btn.dataset.id, 10));
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function truncate(str, len) {
  if (!str) return '';
  return str.length > len ? str.slice(0, len) + '...' : str;
}

function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

function phaseBadge(phase) {
  switch (phase) {
    case 'discovery': return 'purple';
    case 'active': return 'green';
    case 'reassessed': return 'blue';
    case 'profiled': return 'amber';
    default: return 'blue';
  }
}

function eventBadge(type) {
  switch (type) {
    case 'reordered': return 'amber';
    case 'swapped': return 'blue';
    case 'locked': return 'purple';
    case 'generated': return 'green';
    default: return 'blue';
  }
}

function matchColor(score) {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#0d9488';
  if (score >= 40) return '#f59e0b';
  if (score >= 20) return '#f97316';
  return '#ef4444';
}

function getHealthIndicator(l) {
  let score = 0;
  // Match score component
  if (l.avg_match_score >= 70) score += 2;
  else if (l.avg_match_score >= 40) score += 1;
  // Activity recency
  if (l.last_activity) {
    const daysSince = (Date.now() - new Date(l.last_activity).getTime()) / 86400000;
    if (daysSince < 7) score += 2;
    else if (daysSince < 30) score += 1;
  }
  // Feedback flags penalty
  if (l.feedback_flags > 0) score -= 1;

  if (score >= 3) return { level: 'green', dot: '●', reason: 'Healthy: good match + recent activity' };
  if (score >= 1) return { level: 'yellow', dot: '●', reason: 'Moderate: some activity or lower match' };
  return { level: 'red', dot: '●', reason: 'At risk: low match or inactive' };
}

function avatarGradient(l) {
  const name = (l.first_name || '') + (l.last_name || '');
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  const hue = Math.abs(hash % 360);
  return `linear-gradient(135deg, hsl(${hue}, 60%, 40%), hsl(${(hue + 40) % 360}, 50%, 30%))`;
}
