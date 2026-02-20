// ==========================================================================
// TORY-WORKSPACE.JS — 3-Pane Split-View Path Builder
// Left: People list, Center: 4-tab panel, Right: AI Co-pilot
// ==========================================================================

import { getState, setState, subscribe, markFetched } from '../state.js';
import { api, connectToryAgentWs, sendToryAgentMessage, disconnectToryAgentWs } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';

// ── Constants ──────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 300;
const PAGE_SIZE = 50;

// ── Module-level copilot state (persists across tab switches) ────────────

let _copilotSessionId = null;   // Currently connected session
let _copilotMessages = [];      // Chat history
let _copilotStreaming = false;   // Is agent currently streaming?
let _copilotWsConnected = false;

// ── Render Entry Point ─────────────────────────────────────────────────────

export function renderToryWorkspace(root) {
  const container = h('div', { class: 'tw-layout' });

  // Build the 3-pane structure
  container.innerHTML = `
    <!-- Top Bar -->
    <div class="tw-topbar">
      <div class="tw-topbar-left">
        <button class="tw-toggle-btn active" id="tw-toggle-left">&#9664; People</button>
        <span class="tw-topbar-title">Tory Workspace</span>
        <div class="tw-topbar-stats" id="tw-topbar-stats"></div>
      </div>
      <div class="tw-topbar-right">
        <button class="tw-toggle-btn active" id="tw-toggle-right">AI Co-pilot &#9654;</button>
      </div>
    </div>

    <!-- Left Drawer: People -->
    <div class="tw-left" id="tw-left">
      <div class="tw-left-header">
        <div class="tw-search-row">
          <span class="tw-search-icon">&#128269;</span>
          <input type="text" id="tw-search" placeholder="Search users...">
        </div>
        <div class="tw-filters">
          <select id="tw-filter-company">
            <option value="">All Companies</option>
          </select>
          <select id="tw-filter-status">
            <option value="">All Status</option>
            <option value="processed">Processed</option>
            <option value="has_epp">Has EPP</option>
            <option value="no_data">No Data</option>
          </select>
        </div>
      </div>
      <div class="tw-people-list" id="tw-people-list"></div>
      <div class="tw-left-collapsed-strip" id="tw-collapsed-avatars"></div>
      <div class="tw-left-footer" id="tw-left-footer">
        <div class="tw-batch-row">
          <button class="btn btn-primary btn-sm" id="tw-batch-process" disabled>Process Selected (0)</button>
        </div>
        <div class="tw-pagination">
          <button class="btn btn-ghost btn-sm" id="tw-prev-page" disabled>&lt; Prev</button>
          <span class="tw-page-info" id="tw-page-info">Page 1/1</span>
          <button class="btn btn-ghost btn-sm" id="tw-next-page" disabled>Next &gt;</button>
        </div>
      </div>
    </div>

    <!-- Center Panel: Tabs -->
    <div class="tw-center">
      <div class="tw-tabs" id="tw-tabs">
        <button class="tw-tab active" data-tab="profile">Profile</button>
        <button class="tw-tab" data-tab="path">Path</button>
        <button class="tw-tab" data-tab="content">Content</button>
        <button class="tw-tab" data-tab="agentlog">Agent Log</button>
      </div>
      <div class="tw-tab-content" id="tw-tab-content">
        <div class="tw-placeholder">
          <div class="tw-placeholder-icon">&#128100;</div>
          <div class="tw-placeholder-text">Select a user from the left panel to view their profile</div>
        </div>
      </div>
    </div>

    <!-- Right Drawer: AI Co-pilot -->
    <div class="tw-right" id="tw-right">
      <div class="tw-right-header">
        <span class="tw-right-title">AI Co-pilot</span>
        <span class="tw-session-badge" id="tw-session-status" style="display:none"></span>
      </div>
      <div class="tw-session-meta" id="tw-session-meta" style="display:none"></div>
      <div class="tw-chat-messages" id="tw-chat-messages"></div>
      <div class="tw-right-placeholder" id="tw-right-placeholder">
        <div class="tw-right-placeholder-icon">&#129302;</div>
        <div class="tw-right-placeholder-text">Select a user and process them to start chatting with the AI co-pilot</div>
      </div>
      <div class="tw-chat-input-area" id="tw-chat-input" style="display:none">
        <div class="tw-chat-input-wrapper">
          <textarea id="tw-chat-textarea" placeholder="Ask Tory AI..." rows="1"></textarea>
          <button class="tw-chat-send-btn" id="tw-chat-send">Send</button>
        </div>
      </div>
      <div class="tw-right-collapsed-strip" id="tw-right-collapsed">
        <div class="tw-collapsed-icon" id="tw-expand-right">&#129302;</div>
        <span class="tw-collapsed-label">AI Co-pilot</span>
      </div>
    </div>
  `;

  root.appendChild(container);

  // ── Wire Up Events ───────────────────────────────────────────────────

  // Drawer toggles
  container.querySelector('#tw-toggle-left').addEventListener('click', toggleLeftDrawer);
  container.querySelector('#tw-toggle-right').addEventListener('click', toggleRightDrawer);
  container.querySelector('#tw-expand-right').addEventListener('click', toggleRightDrawer);

  // Search (debounced)
  let searchTimer = null;
  container.querySelector('#tw-search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const tw = getState().toryWorkspace;
      setState({ toryWorkspace: { ...tw, search: e.target.value.trim(), page: 1 } });
      loadUsers();
    }, DEBOUNCE_MS);
  });

  // Filters
  container.querySelector('#tw-filter-company').addEventListener('change', (e) => {
    const tw = getState().toryWorkspace;
    setState({ toryWorkspace: { ...tw, filters: { ...tw.filters, company: e.target.value }, page: 1 } });
    loadUsers();
  });

  container.querySelector('#tw-filter-status').addEventListener('change', (e) => {
    const tw = getState().toryWorkspace;
    setState({ toryWorkspace: { ...tw, filters: { ...tw.filters, status: e.target.value }, page: 1 } });
    loadUsers();
  });

  // Pagination
  container.querySelector('#tw-prev-page').addEventListener('click', () => {
    const tw = getState().toryWorkspace;
    if (tw.page > 1) {
      setState({ toryWorkspace: { ...tw, page: tw.page - 1 } });
      loadUsers();
    }
  });

  container.querySelector('#tw-next-page').addEventListener('click', () => {
    const tw = getState().toryWorkspace;
    if (tw.page < tw.totalPages) {
      setState({ toryWorkspace: { ...tw, page: tw.page + 1 } });
      loadUsers();
    }
  });

  // Batch process
  container.querySelector('#tw-batch-process').addEventListener('click', batchProcess);

  // Tabs
  container.querySelector('#tw-tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.tw-tab');
    if (!tab) return;
    const tabName = tab.dataset.tab;
    const tw = getState().toryWorkspace;
    setState({ toryWorkspace: { ...tw, activeTab: tabName } });
    renderTabs();
    renderTabContent();
  });

  // Chat
  const chatTextarea = container.querySelector('#tw-chat-textarea');
  chatTextarea.addEventListener('input', () => {
    chatTextarea.style.height = 'auto';
    chatTextarea.style.height = Math.min(chatTextarea.scrollHeight, 100) + 'px';
  });
  chatTextarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });
  container.querySelector('#tw-chat-send').addEventListener('click', sendChatMessage);

  // ── State Subscriptions ──────────────────────────────────────────────

  subscribe('toryWorkspace', (tw) => {
    renderPeopleList();
    renderPagination();
    renderBatchButton();
    renderTopbarStats();
  });

  // ── Initial Load ─────────────────────────────────────────────────────

  loadUsers();
}

// ── Data Loading ────────────────────────────────────────────────────────────

async function loadUsers() {
  const tw = getState().toryWorkspace;
  setState({ toryWorkspace: { ...tw, loading: true } });

  const listEl = document.getElementById('tw-people-list');
  if (listEl) listEl.innerHTML = '<div class="tw-loading"><div class="tw-spinner"></div> Loading users...</div>';

  try {
    const params = {
      page: tw.page,
      limit: PAGE_SIZE,
    };
    if (tw.search) params.search = tw.search;
    if (tw.filters.status) params.status_filter = tw.filters.status;
    if (tw.filters.company) params.company_filter = tw.filters.company;

    const data = await api.getToryUsers(params);
    const users = data.users || [];
    const totalUsers = data.total || 0;
    const totalPages = data.total_pages || Math.ceil(totalUsers / PAGE_SIZE) || 1;
    const companies = data.companies || tw.companies;

    setState({
      toryWorkspace: {
        ...getState().toryWorkspace,
        users,
        totalUsers,
        totalPages,
        companies,
        loading: false,
      }
    });
    markFetched('toryWorkspace');

    // Populate company filter if we got companies back
    if (companies.length > 0) {
      populateCompanyFilter(companies);
    }

    renderPeopleList();
    renderPagination();
    renderTopbarStats();
  } catch (err) {
    setState({ toryWorkspace: { ...getState().toryWorkspace, loading: false } });
    if (listEl) listEl.innerHTML = `<div class="tw-placeholder"><div class="tw-placeholder-text">Failed to load users: ${esc(err.message)}</div></div>`;
    showToast(`Failed to load users: ${err.message}`, 'error');
  }
}

async function loadUserDetail(userId) {
  const tw = getState().toryWorkspace;

  // Reset copilot state when user changes (disconnect WS, clear chat)
  if (tw.selectedUserId !== userId) {
    disconnectToryAgentWs();
    _copilotSessionId = null;
    _copilotMessages = [];
    _copilotStreaming = false;
    _copilotWsConnected = false;
    _agentLogSessionId = null;
    _agentLogEvents = [];
  }

  setState({ toryWorkspace: { ...tw, selectedUserId: userId, detailLoading: true, selectedUserDetail: null } });

  renderPeopleList();
  renderTabContent();

  try {
    const detail = await api.getToryUserDetail(userId);
    setState({
      toryWorkspace: {
        ...getState().toryWorkspace,
        selectedUserDetail: detail,
        detailLoading: false,
      }
    });
    renderTabContent();

    // Also load agent sessions for this user
    loadAgentSessions(userId);
  } catch (err) {
    setState({ toryWorkspace: { ...getState().toryWorkspace, detailLoading: false } });
    showToast(`Failed to load user detail: ${err.message}`, 'error');
    renderTabContent();
  }
}

async function loadAgentSessions(userId) {
  try {
    const data = await api.getToryAgentSessions(userId);
    const tw = getState().toryWorkspace;
    setState({ toryWorkspace: { ...tw, agentSessions: data.sessions || [] } });
    // If there are sessions, update the copilot drawer
    renderCopilotDrawer();
  } catch (err) {
    // Non-critical — copilot just won't show sessions
    console.warn('Failed to load agent sessions:', err.message);
  }
}

// ── Render Functions ────────────────────────────────────────────────────────

function renderPeopleList() {
  const listEl = document.getElementById('tw-people-list');
  const collapsedEl = document.getElementById('tw-collapsed-avatars');
  if (!listEl) return;

  const tw = getState().toryWorkspace;
  if (tw.loading) return; // Already showing loading spinner

  listEl.innerHTML = '';
  if (collapsedEl) collapsedEl.innerHTML = '';

  if (tw.users.length === 0) {
    listEl.innerHTML = '<div class="tw-placeholder"><div class="tw-placeholder-text">No users found</div></div>';
    return;
  }

  for (const user of tw.users) {
    // Full row
    const row = h('div', {
      class: `tw-person${user.nx_user_id === tw.selectedUserId ? ' selected' : ''}`,
      dataset: { userId: user.nx_user_id },
    });

    const status = getUserStatus(user);

    row.innerHTML = `
      <input type="checkbox" class="tw-person-check" data-uid="${user.nx_user_id}" ${tw.batchSelected.has(user.nx_user_id) ? 'checked' : ''}>
      <div class="tw-person-status status-${status}"></div>
      <div class="tw-person-info">
        <div class="tw-person-name">${esc(getUserName(user))}</div>
        <div class="tw-person-meta">${esc(user.email || '')}${user.client_name ? ' · ' + esc(user.client_name) : ''}</div>
      </div>
    `;

    // Click row → select user
    row.addEventListener('click', (e) => {
      if (e.target.classList.contains('tw-person-check')) return;
      loadUserDetail(user.nx_user_id);
    });

    // Checkbox
    const checkbox = row.querySelector('.tw-person-check');
    checkbox.addEventListener('change', (e) => {
      const tw = getState().toryWorkspace;
      const newSet = new Set(tw.batchSelected);
      if (e.target.checked) {
        newSet.add(user.nx_user_id);
      } else {
        newSet.delete(user.nx_user_id);
      }
      setState({ toryWorkspace: { ...tw, batchSelected: newSet } });
      renderBatchButton();
    });

    listEl.appendChild(row);

    // Mini avatar for collapsed view
    if (collapsedEl) {
      const initials = getInitials(user);
      const mini = h('div', {
        class: `tw-mini-avatar status-${status}${user.nx_user_id === tw.selectedUserId ? ' selected' : ''}`,
        title: getUserName(user),
      }, initials);
      mini.addEventListener('click', () => loadUserDetail(user.nx_user_id));
      collapsedEl.appendChild(mini);
    }
  }
}

function renderPagination() {
  const tw = getState().toryWorkspace;
  const prevBtn = document.getElementById('tw-prev-page');
  const nextBtn = document.getElementById('tw-next-page');
  const info = document.getElementById('tw-page-info');

  if (prevBtn) prevBtn.disabled = tw.page <= 1;
  if (nextBtn) nextBtn.disabled = tw.page >= tw.totalPages;
  if (info) info.textContent = `Page ${tw.page}/${tw.totalPages || 1}`;
}

function renderBatchButton() {
  const tw = getState().toryWorkspace;
  const btn = document.getElementById('tw-batch-process');
  if (!btn) return;
  const count = tw.batchSelected.size;
  btn.textContent = `Process Selected (${count})`;
  btn.disabled = count === 0;
}

function renderTopbarStats() {
  const tw = getState().toryWorkspace;
  const el = document.getElementById('tw-topbar-stats');
  if (!el) return;
  el.innerHTML = `
    <span class="tw-topbar-stat"><strong>${tw.totalUsers}</strong> users</span>
    <span class="tw-topbar-stat"><strong>${tw.batchSelected.size}</strong> selected</span>
  `;
}

function renderTabs() {
  const tw = getState().toryWorkspace;
  const tabs = document.querySelectorAll('#tw-tabs .tw-tab');
  tabs.forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tw.activeTab);
  });
}

function renderTabContent() {
  const contentEl = document.getElementById('tw-tab-content');
  if (!contentEl) return;

  const tw = getState().toryWorkspace;

  // Content tab works without a user selected (it's the content library)
  if (tw.activeTab === 'content') {
    renderContentTab(contentEl);
    return;
  }

  // No user selected
  if (!tw.selectedUserId) {
    contentEl.innerHTML = `
      <div class="tw-placeholder">
        <div class="tw-placeholder-icon">&#128100;</div>
        <div class="tw-placeholder-text">Select a user from the left panel to view their profile</div>
      </div>
    `;
    return;
  }

  // Loading
  if (tw.detailLoading) {
    contentEl.innerHTML = '<div class="tw-loading"><div class="tw-spinner"></div> Loading user detail...</div>';
    return;
  }

  // Error / no detail
  if (!tw.selectedUserDetail) {
    contentEl.innerHTML = `
      <div class="tw-placeholder">
        <div class="tw-placeholder-text">Failed to load user detail. Try selecting the user again.</div>
      </div>
    `;
    return;
  }

  switch (tw.activeTab) {
    case 'profile':
      renderProfileTab(contentEl, tw.selectedUserDetail);
      break;
    case 'path':
      renderPathTab(contentEl, tw.selectedUserDetail);
      break;
    case 'agentlog':
      renderAgentLogTab(contentEl);
      break;
    default:
      contentEl.innerHTML = '<div class="tw-placeholder"><div class="tw-placeholder-text">Unknown tab</div></div>';
  }
}

// ── Profile Tab — EPP Profile Display ────────────────────────────────────────

// EPP dimension descriptions for tooltips
const EPP_DESCRIPTIONS = {
  Achievement: 'Drive to accomplish goals and exceed standards',
  Motivation: 'Internal drive and energy level; self-starting tendency',
  Competitiveness: 'Desire to outperform others and win',
  Managerial: 'Comfort with leading, directing, and managing others',
  Assertiveness: 'Willingness to speak up, push back, and advocate',
  Extroversion: 'Preference for social interaction and external stimulation',
  Cooperativeness: 'Orientation toward teamwork, harmony, and helping others',
  Patience: 'Tolerance for delay, pace of work, frustration threshold',
  SelfConfidence: 'Trust in own abilities and judgment',
  Conscientiousness: 'Attention to detail, organization, and rule-following',
  Openness: 'Receptivity to new ideas, change, and unconventional approaches',
  Stability: 'Emotional evenness and resilience to stress',
  StressTolerance: 'Ability to function effectively under pressure',
};

const JOBFIT_LABELS = {
  Accounting_JobFit: 'Accounting',
  AdminAsst_JobFit: 'Admin Asst',
  Analyst_JobFit: 'Analyst',
  BankTeller_JobFit: 'Bank Teller',
  Collections_JobFit: 'Collections',
  CustomerService_JobFit: 'Customer Svc',
  FrontDesk_JobFit: 'Front Desk',
  Manager_JobFit: 'Manager',
  MedicalAsst_JobFit: 'Medical Asst',
  Production_JobFit: 'Production',
  Programmer_JobFit: 'Programmer',
  Sales_JobFit: 'Sales',
};

// Track active Chart.js instances so we can destroy them on re-render
let _eppRadarChart = null;
let _eppBarChart = null;

// Cache for loaded EPP profile data (keyed by user_id)
const _eppProfileCache = {};

async function renderProfileTab(el, detail) {
  el.innerHTML = '';

  const learner = detail.learner || {};
  const user = learner.user || {};
  const coach = learner.coach || null;
  const rawProfile = learner.profile || {};

  const tw = getState().toryWorkspace;
  const userId = tw.selectedUserId;
  const listUser = tw.users.find(u => u.nx_user_id === userId) || {};

  const displayFirst = listUser.first_name || user.first_name || rawProfile.first_name || '';
  const displayLast = listUser.last_name || user.last_name || rawProfile.last_name || '';
  const displayEmail = user.email || listUser.email || rawProfile.email || '';
  const displayCompany = listUser.company_name || rawProfile.client_name || '';
  const initials = ((displayFirst)[0] || '') + ((displayLast)[0] || '');
  const displayName = [displayFirst, displayLast].filter(Boolean).join(' ') || displayEmail || `User ${userId}`;

  // Build skeleton HTML immediately
  const container = h('div', { class: 'tw-epp-profile' });
  container.innerHTML = `
    <div class="tw-profile-header">
      <div class="tw-profile-avatar">${esc(initials) || '?'}</div>
      <div>
        <div class="tw-profile-name">${esc(displayName)}</div>
        <div class="tw-profile-email">${esc(displayEmail)}</div>
        ${displayCompany ? `<div class="tw-profile-company">${esc(displayCompany)}</div>` : ''}
      </div>
      <div class="tw-epp-source-badge" id="tw-epp-source"></div>
    </div>
    ${coach ? `
      <div class="tw-coach-card">
        <div class="tw-coach-signal" style="color:${({green:'#22c55e',yellow:'#f59e0b',red:'#ef4444'})[coach.compat_signal] || '#22c55e'}">&#9679;</div>
        <div>
          <div class="tw-coach-name">Coach: ${esc(coach.coach_name || 'Assigned')}</div>
          <div class="tw-coach-compat">${esc(coach.compat_message || '')}</div>
        </div>
      </div>
    ` : ''}
    <div id="tw-epp-loading" class="tw-loading"><div class="tw-spinner"></div> Loading EPP profile...</div>
    <div id="tw-epp-content" style="display:none">
      <div class="tw-epp-charts-row">
        <div class="tw-epp-chart-wrap">
          <div class="tw-profile-section-label">Personality Dimensions</div>
          <canvas id="tw-epp-radar" width="400" height="400"></canvas>
        </div>
        <div class="tw-epp-chart-wrap">
          <div class="tw-profile-section-label">Job Fit Dimensions</div>
          <canvas id="tw-epp-bar" width="400" height="300"></canvas>
        </div>
      </div>
      <div class="tw-epp-pills-row" id="tw-epp-pills"></div>
      <div id="tw-epp-narrative-section"></div>
      <div id="tw-epp-qa-section"></div>
    </div>
    <div class="tw-profile-section" style="text-align:center">
      <button class="btn btn-primary" id="tw-process-user">Process with AI</button>
    </div>
  `;
  el.appendChild(container);

  // Process button
  const processBtn = container.querySelector('#tw-process-user');
  if (processBtn) {
    processBtn.addEventListener('click', () => processUser(userId));
  }

  // Fetch EPP profile data
  try {
    let profileData = _eppProfileCache[userId];
    if (!profileData) {
      const resp = await api(`/api/tory/users/${userId}/profile`);
      profileData = resp;
      _eppProfileCache[userId] = profileData;
    }

    container.querySelector('#tw-epp-loading').style.display = 'none';
    container.querySelector('#tw-epp-content').style.display = 'block';

    // Source badge
    const sourceBadge = container.querySelector('#tw-epp-source');
    if (profileData.source === 'tory_profile') {
      sourceBadge.textContent = 'AI Profile';
      sourceBadge.classList.add('source-ai');
    } else if (profileData.source === 'raw_assessment') {
      sourceBadge.textContent = 'Raw EPP';
      sourceBadge.classList.add('source-raw');
    } else {
      sourceBadge.textContent = 'No EPP';
      sourceBadge.classList.add('source-none');
    }

    // ── Radar Chart (13 personality dims) ──
    const personalityScores = profileData.personality_scores || {};
    const radarLabels = Object.keys(EPP_DESCRIPTIONS);
    const radarValues = radarLabels.map(d => personalityScores[d] ?? null);

    // Color each point: red <30, yellow 30-70, green >70
    const radarPointColors = radarValues.map(v =>
      v == null ? '#555' : v <= 30 ? '#f87171' : v >= 70 ? '#4ade80' : '#fbbf24'
    );

    // Destroy previous charts
    if (_eppRadarChart) { _eppRadarChart.destroy(); _eppRadarChart = null; }
    if (_eppBarChart) { _eppBarChart.destroy(); _eppBarChart = null; }

    const radarCanvas = container.querySelector('#tw-epp-radar');
    if (radarCanvas && radarLabels.length > 0 && radarValues.some(v => v != null)) {
      const radarCtx = radarCanvas.getContext('2d');
      _eppRadarChart = new Chart(radarCtx, {
        type: 'radar',
        data: {
          labels: radarLabels.map(d => d.replace('SelfConfidence', 'Self-Confidence').replace('StressTolerance', 'Stress Tol.')),
          datasets: [{
            label: 'Score',
            data: radarValues,
            backgroundColor: 'rgba(88, 166, 255, 0.15)',
            borderColor: '#58a6ff',
            borderWidth: 2,
            pointBackgroundColor: radarPointColors,
            pointBorderColor: radarPointColors,
            pointRadius: 5,
            pointHoverRadius: 8,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          scales: {
            r: {
              min: 0,
              max: 100,
              ticks: {
                stepSize: 20,
                backdropColor: 'transparent',
                color: '#888',
                font: { size: 10 },
              },
              grid: { color: 'rgba(255,255,255,0.06)' },
              angleLines: { color: 'rgba(255,255,255,0.08)' },
              pointLabels: {
                color: '#ccc',
                font: { size: 11 },
              },
            },
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: (items) => {
                  const idx = items[0]?.dataIndex;
                  return radarLabels[idx] || '';
                },
                label: (item) => {
                  const dim = radarLabels[item.dataIndex];
                  const score = item.raw;
                  const zone = score <= 30 ? 'Gap' : score >= 70 ? 'Strength' : 'Average';
                  return [`Score: ${score} (${zone})`, EPP_DESCRIPTIONS[dim] || ''];
                },
              },
            },
          },
        },
      });
    }

    // ── Bar Chart (12 job fit dims) ──
    const jobfitScores = profileData.jobfit_scores || {};
    const barDims = Object.keys(JOBFIT_LABELS);
    const barLabels = barDims.map(d => JOBFIT_LABELS[d]);
    const barValues = barDims.map(d => jobfitScores[d] ?? 0);
    const barColors = barValues.map(v =>
      v <= 30 ? '#f87171' : v >= 70 ? '#4ade80' : '#fbbf24'
    );

    const barCanvas = container.querySelector('#tw-epp-bar');
    if (barCanvas && barValues.some(v => v > 0)) {
      const barCtx = barCanvas.getContext('2d');
      _eppBarChart = new Chart(barCtx, {
        type: 'bar',
        data: {
          labels: barLabels,
          datasets: [{
            label: 'Job Fit',
            data: barValues,
            backgroundColor: barColors.map(c => c + '99'),
            borderColor: barColors,
            borderWidth: 1,
            borderRadius: 3,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          indexAxis: 'y',
          scales: {
            x: {
              min: 0, max: 100,
              ticks: { color: '#888', font: { size: 10 } },
              grid: { color: 'rgba(255,255,255,0.06)' },
            },
            y: {
              ticks: { color: '#ccc', font: { size: 11 } },
              grid: { display: false },
            },
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => `Score: ${item.raw}`,
              },
            },
          },
        },
      });
    }

    // ── Strengths + Gaps Pills ──
    const pillsEl = container.querySelector('#tw-epp-pills');
    const topStrengths = profileData.top_strengths || [];
    const topGaps = profileData.top_gaps || [];
    let pillsHtml = '';

    if (topStrengths.length > 0) {
      pillsHtml += `<div class="tw-epp-pill-group"><span class="tw-epp-pill-label">Strengths</span>`;
      pillsHtml += topStrengths.map(s =>
        `<span class="tw-trait tw-trait-strength">${esc(s.trait)} ${Math.round(s.score)}</span>`
      ).join('');
      pillsHtml += '</div>';
    }
    if (topGaps.length > 0) {
      pillsHtml += `<div class="tw-epp-pill-group"><span class="tw-epp-pill-label">Growth Areas</span>`;
      pillsHtml += topGaps.map(g =>
        `<span class="tw-trait tw-trait-gap">${esc(g.trait)} ${Math.round(g.score)}</span>`
      ).join('');
      pillsHtml += '</div>';
    }
    if (pillsHtml) pillsEl.innerHTML = pillsHtml;

    // ── Narrative ──
    const narrativeSection = container.querySelector('#tw-epp-narrative-section');
    if (profileData.profile_narrative) {
      narrativeSection.innerHTML = `
        <div class="tw-profile-section">
          <div class="tw-profile-section-label">Profile Narrative</div>
          <blockquote class="tw-epp-narrative">${esc(profileData.profile_narrative)}</blockquote>
        </div>
      `;
    }

    // ── Learning style + motivation ──
    if (profileData.learning_style || (profileData.motivation_cluster && profileData.motivation_cluster.length > 0)) {
      let metaHtml = '<div class="tw-profile-section"><div class="tw-profile-section-label">Learning Profile</div><div class="tw-epp-meta-row">';
      if (profileData.learning_style) {
        metaHtml += `<div class="tw-profile-stat"><div class="tw-profile-stat-value">${esc(profileData.learning_style)}</div><div class="tw-profile-stat-label">Learning Style</div></div>`;
      }
      metaHtml += '</div>';
      if (profileData.motivation_cluster && profileData.motivation_cluster.length > 0) {
        metaHtml += `<div class="tw-epp-motivation"><span class="tw-epp-pill-label">Motivators</span>`;
        metaHtml += profileData.motivation_cluster.map(m =>
          `<span class="tw-trait tw-trait-motivation">${esc(typeof m === 'string' ? m : JSON.stringify(m))}</span>`
        ).join('');
        metaHtml += '</div>';
      }
      metaHtml += '</div>';
      narrativeSection.innerHTML += metaHtml;
    }

    // ── Onboarding Q&A Cards ──
    const qaSection = container.querySelector('#tw-epp-qa-section');
    const qaItems = profileData.onboarding_qa || [];
    if (qaItems.length > 0) {
      let qaHtml = '<div class="tw-profile-section"><div class="tw-profile-section-label">Onboarding Q&A</div><div class="tw-epp-qa-grid">';
      for (const qa of qaItems) {
        const val = qa.value;
        let displayVal;
        if (Array.isArray(val)) {
          displayVal = val.map(v => `<span class="tw-epp-qa-tag">${esc(String(v))}</span>`).join('');
        } else {
          displayVal = `<p class="tw-epp-qa-text">${esc(String(val))}</p>`;
        }
        qaHtml += `
          <div class="tw-epp-qa-card">
            <div class="tw-epp-qa-label">${esc(qa.label)}</div>
            <div class="tw-epp-qa-value">${displayVal}</div>
          </div>
        `;
      }
      qaHtml += '</div></div>';
      qaSection.innerHTML = qaHtml;
    }

  } catch (err) {
    console.error('Failed to load EPP profile:', err);
    container.querySelector('#tw-epp-loading').innerHTML =
      `<div class="tw-epp-error">Failed to load EPP data. ${esc(String(err.message || err))}</div>`;
  }
}

// ── Path Tab: 4-Column Kanban ─────────────────────────────────────────────

// Journey color palette for badges
const JOURNEY_COLORS = [
  '#58a6ff', '#d29922', '#bc8cff', '#3fb950', '#f85149',
  '#ff7b72', '#79c0ff', '#e3b341', '#d2a8ff', '#56d364',
];
function journeyColor(journeyId) {
  return JOURNEY_COLORS[(journeyId || 0) % JOURNEY_COLORS.length];
}

function difficultyDots(level) {
  const n = Math.max(1, Math.min(5, Math.round(level || 3)));
  return '<span class="tw-diff-dots">' +
    Array.from({ length: 5 }, (_, i) =>
      `<span class="tw-diff-dot${i < n ? ' filled' : ''}"></span>`
    ).join('') + '</span>';
}

// Module-level DnD state
let _pathDraggedCard = null;
let _pathPreDragState = null;  // snapshot for cancel
let _impactDebounce = null;

function renderPathTab(el, detail) {
  el.innerHTML = '';
  const pathData = detail.path;

  if (!pathData) {
    el.innerHTML = `
      <div class="tw-placeholder">
        <div class="tw-placeholder-icon">&#128736;</div>
        <div class="tw-placeholder-text">No path data yet. Process this user to generate their learning path.</div>
      </div>
    `;
    return;
  }

  const recs = pathData.path || pathData.recommendations || [];
  if (recs.length === 0) {
    el.innerHTML = `
      <div class="tw-placeholder">
        <div class="tw-placeholder-icon">&#128736;</div>
        <div class="tw-placeholder-text">Path is empty. Process this user to generate recommendations.</div>
      </div>
    `;
    return;
  }

  // Partition into columns
  const discovery = recs.filter(r => r.is_discovery);
  const mainPath = recs.filter(r => !r.is_discovery);
  // Available pool = loaded asynchronously from content library
  // Completed = empty for now

  // Build kanban board
  const board = h('div', { class: 'tw-path-board' });

  const columns = [
    { id: 'pool', title: 'Available Pool', items: [], accepts: true },
    { id: 'discovery', title: 'Discovery', items: discovery, accepts: true, maxSlots: 5 },
    { id: 'main', title: 'Main Path', items: mainPath, accepts: true },
    { id: 'completed', title: 'Completed', items: [], accepts: false },
  ];

  for (const col of columns) {
    const column = h('div', { class: 'tw-path-col', dataset: { col: col.id } });
    column.innerHTML = `
      <div class="tw-path-col-header">
        <span class="tw-path-col-title">${col.title}</span>
        <span class="tw-path-col-count">${col.items.length}${col.maxSlots ? '/' + col.maxSlots : ''}</span>
      </div>
    `;

    const cardsContainer = h('div', { class: 'tw-path-cards' });

    for (let i = 0; i < col.items.length; i++) {
      const rec = col.items[i];
      cardsContainer.appendChild(buildPathCard(rec, col.id, i));
    }

    // Empty slot indicator
    if (col.items.length === 0 && col.id !== 'pool') {
      const empty = h('div', { class: 'tw-path-empty' });
      empty.textContent = col.id === 'completed' ? 'No completed lessons yet' : 'Drop lessons here';
      cardsContainer.appendChild(empty);
    }

    column.appendChild(cardsContainer);
    board.appendChild(column);

    // Drop zone handlers (reuse kanban.js pattern)
    if (col.accepts) {
      column.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        column.classList.add('tw-drag-over');

        const afterEl = pathGetDragAfterElement(cardsContainer, e.clientY);
        const placeholder = pathGetOrCreatePlaceholder();
        if (afterEl) {
          cardsContainer.insertBefore(placeholder, afterEl);
        } else {
          cardsContainer.appendChild(placeholder);
        }
      });

      column.addEventListener('dragleave', (e) => {
        if (!column.contains(e.relatedTarget)) {
          column.classList.remove('tw-drag-over');
          column.querySelector('.tw-path-drop-ph')?.remove();
        }
      });

      column.addEventListener('drop', (e) => {
        e.preventDefault();
        column.classList.remove('tw-drag-over');
        const placeholder = column.querySelector('.tw-path-drop-ph');
        if (!_pathDraggedCard || !placeholder) return;

        // Remove empty slot placeholder if present
        const emptySlot = cardsContainer.querySelector('.tw-path-empty');
        if (emptySlot) emptySlot.remove();

        cardsContainer.insertBefore(_pathDraggedCard, placeholder);
        placeholder.remove();

        // Fire move callback
        const lessonId = _pathDraggedCard.dataset.lessonId;
        const fromCol = _pathDraggedCard.dataset.fromCol;
        const toCol = col.id;
        const position = [...cardsContainer.querySelectorAll('.tw-path-card')].indexOf(_pathDraggedCard);

        _pathDraggedCard.dataset.fromCol = toCol; // update origin
        onLessonMove(lessonId, fromCol, toCol, position);
      });
    }
  }

  el.appendChild(board);

  // Impact preview panel (hidden until drag)
  const preview = h('div', { class: 'tw-impact-preview', id: 'tw-impact-preview' });
  preview.style.display = 'none';
  preview.innerHTML = `
    <div class="tw-impact-header">
      <span class="tw-impact-title">Impact Preview</span>
      <span class="tw-impact-action" id="tw-impact-action"></span>
    </div>
    <div class="tw-impact-body" id="tw-impact-body">
      <div class="tw-loading"><div class="tw-spinner"></div> Calculating impact...</div>
    </div>
    <div class="tw-impact-footer">
      <button class="btn btn-ghost btn-sm" id="tw-impact-cancel">Cancel</button>
      <button class="btn btn-primary btn-sm" id="tw-impact-apply">Apply Change</button>
    </div>
  `;
  el.appendChild(preview);

  // Wire cancel/apply
  preview.querySelector('#tw-impact-cancel').addEventListener('click', cancelPathChange);
  preview.querySelector('#tw-impact-apply').addEventListener('click', applyPathChange);

  // Load available pool asynchronously
  loadAvailablePool(recs);
}

function buildPathCard(rec, colId, idx) {
  const isLocked = rec.locked_by_coach;
  const card = h('div', {
    class: `tw-path-card${isLocked ? ' locked' : ''}`,
    dataset: {
      lessonId: String(rec.nx_lesson_id),
      recId: String(rec.recommendation_id || ''),
      fromCol: colId,
    },
    draggable: isLocked ? 'false' : 'true',
  });

  const score = Math.min(Math.round(rec.match_score || 0), 100);
  const jColor = journeyColor(rec.journey_id);
  const seqBadge = (colId === 'discovery' || colId === 'main')
    ? `<span class="tw-path-seq">#${rec.sequence || idx + 1}</span>` : '';
  const lockIcon = isLocked ? '<span class="tw-path-lock" title="Locked by coach">&#128274;</span>' : '';

  card.innerHTML = `
    <div class="tw-path-card-top">
      <span class="tw-path-journey" style="background:${jColor}20;color:${jColor}">${esc(rec.journey_name || rec.journey_title || 'J' + (rec.journey_id || '?'))}</span>
      <span class="tw-path-score">Score ${score}</span>
    </div>
    <div class="tw-path-card-title">${seqBadge}${lockIcon}${esc(rec.lesson_name || rec.lesson_title || 'Lesson ' + rec.nx_lesson_id)}</div>
    <div class="tw-path-card-bottom">
      ${difficultyDots(rec.difficulty)}
      <span class="tw-path-source ${rec.source || 'tory'}">${esc(rec.source || 'tory')}</span>
    </div>
  `;

  // Drag handlers (reuse kanban.js:204-217 pattern)
  if (!isLocked) {
    card.addEventListener('dragstart', (e) => {
      _pathDraggedCard = card;
      // Snapshot the board state for cancel
      _pathPreDragState = snapshotBoardState();
      card.classList.add('tw-dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', rec.nx_lesson_id);
      requestAnimationFrame(() => { card.style.opacity = '0.3'; });
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('tw-dragging');
      card.style.opacity = '1';
      _pathDraggedCard = null;
      document.querySelectorAll('.tw-path-drop-ph').forEach(p => p.remove());
      document.querySelectorAll('.tw-drag-over').forEach(c => c.classList.remove('tw-drag-over'));
    });
  }

  return card;
}

// ── Path DnD Helpers (adapted from kanban.js:329-353) ─────────────────────

function pathGetDragAfterElement(container, y) {
  const cards = [...container.querySelectorAll('.tw-path-card:not(.tw-dragging)')];
  let closest = null;
  let closestOffset = Number.NEGATIVE_INFINITY;

  cards.forEach(card => {
    const box = card.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closestOffset) {
      closestOffset = offset;
      closest = card;
    }
  });

  return closest;
}

function pathGetOrCreatePlaceholder() {
  let ph = document.querySelector('.tw-path-drop-ph');
  if (!ph) {
    ph = document.createElement('div');
    ph.className = 'tw-path-drop-ph';
  }
  return ph;
}

// ── Board State Snapshot / Restore ────────────────────────────────────────

function snapshotBoardState() {
  const state = {};
  document.querySelectorAll('.tw-path-col').forEach(col => {
    const colId = col.dataset.col;
    const cards = [...col.querySelectorAll('.tw-path-card')];
    state[colId] = cards.map(c => c.outerHTML);
  });
  return state;
}

function restoreBoardState(snapshot) {
  if (!snapshot) return;
  document.querySelectorAll('.tw-path-col').forEach(col => {
    const colId = col.dataset.col;
    const cardsContainer = col.querySelector('.tw-path-cards');
    if (!cardsContainer || !snapshot[colId]) return;

    cardsContainer.innerHTML = '';
    for (const html of snapshot[colId]) {
      const temp = document.createElement('div');
      temp.innerHTML = html;
      const card = temp.firstChild;
      // Re-attach drag handlers
      if (card.getAttribute('draggable') === 'true') {
        card.addEventListener('dragstart', (e) => {
          _pathDraggedCard = card;
          _pathPreDragState = snapshotBoardState();
          card.classList.add('tw-dragging');
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', card.dataset.lessonId);
          requestAnimationFrame(() => { card.style.opacity = '0.3'; });
        });
        card.addEventListener('dragend', () => {
          card.classList.remove('tw-dragging');
          card.style.opacity = '1';
          _pathDraggedCard = null;
          document.querySelectorAll('.tw-path-drop-ph').forEach(p => p.remove());
          document.querySelectorAll('.tw-drag-over').forEach(c => c.classList.remove('tw-drag-over'));
        });
      }
      cardsContainer.appendChild(card);
    }

    // Re-add empty slot if no cards
    if (snapshot[colId].length === 0 && colId !== 'pool') {
      const empty = h('div', { class: 'tw-path-empty' });
      empty.textContent = colId === 'completed' ? 'No completed lessons yet' : 'Drop lessons here';
      cardsContainer.appendChild(empty);
    }
  });
}

// ── Lesson Move + Impact Preview ──────────────────────────────────────────

function onLessonMove(lessonId, fromCol, toCol, position) {
  const preview = document.getElementById('tw-impact-preview');
  if (!preview) return;

  // Show impact preview
  preview.style.display = '';
  const actionEl = document.getElementById('tw-impact-action');
  const bodyEl = document.getElementById('tw-impact-body');

  const cardTitle = _pathDraggedCard?.querySelector('.tw-path-card-title')?.textContent || `Lesson ${lessonId}`;
  const colNames = { pool: 'Available Pool', discovery: 'Discovery', main: 'Main Path', completed: 'Completed' };
  actionEl.textContent = `+ ${cardTitle.replace(/^#\d+/, '').replace(/^[\u{1F512}]/u, '').trim()} \u2192 ${colNames[toCol] || toCol} (position ${position + 1})`;
  bodyEl.innerHTML = '<div class="tw-loading"><div class="tw-spinner"></div> Calculating impact...</div>';

  // Store move context for apply
  preview.dataset.lessonId = lessonId;
  preview.dataset.fromCol = fromCol;
  preview.dataset.toCol = toCol;
  preview.dataset.position = position;

  // Debounced impact fetch
  clearTimeout(_impactDebounce);
  _impactDebounce = setTimeout(() => fetchImpactPreview(lessonId, fromCol, toCol), DEBOUNCE_MS);
}

async function fetchImpactPreview(lessonId, fromCol, toCol) {
  const bodyEl = document.getElementById('tw-impact-body');
  if (!bodyEl) return;

  const tw = getState().toryWorkspace;
  const userId = tw.selectedUserId;
  if (!userId) return;

  try {
    const addIds = (fromCol === 'pool' && toCol !== 'pool') ? lessonId : '';
    const removeIds = (toCol === 'pool' && fromCol !== 'pool') ? lessonId : '';

    const data = await api.getToryPreviewImpact({
      user_id: userId,
      add_lesson_ids: addIds,
      remove_lesson_ids: removeIds,
    });

    renderImpactData(bodyEl, data);
  } catch (err) {
    bodyEl.innerHTML = `<div class="tw-impact-error">Failed to calculate impact: ${esc(err.message)}</div>`;
  }
}

function renderImpactData(bodyEl, data) {
  if (!data || data.error) {
    bodyEl.innerHTML = `<div class="tw-impact-error">${esc(data?.error || 'No data')}</div>`;
    return;
  }

  const before = data.before || {};
  const after = data.after || {};
  const delta = data.delta || {};

  let html = '';

  // Trait coverage bars
  const gapBefore = before.gap_coverage || {};
  const gapAfter = after.gap_coverage || {};
  const allTraits = [...new Set([...Object.keys(gapBefore), ...Object.keys(gapAfter)])];

  if (allTraits.length > 0) {
    html += '<div class="tw-impact-section"><div class="tw-impact-section-label">Trait Coverage</div>';
    for (const trait of allTraits.slice(0, 6)) {
      const bv = Math.round((gapBefore[trait] || 0) * 100);
      const av = Math.round((gapAfter[trait] || 0) * 100);
      const diff = av - bv;
      const diffStr = diff > 0 ? `+${diff}%` : diff < 0 ? `${diff}%` : 'no change';
      const diffClass = diff > 0 ? 'positive' : diff < 0 ? 'negative' : 'neutral';

      html += `
        <div class="tw-impact-trait">
          <span class="tw-impact-trait-name">${esc(trait)}</span>
          <span class="tw-impact-trait-before">${bv}%</span>
          <span class="tw-impact-arrow">\u25B6</span>
          <span class="tw-impact-trait-after">${av}%</span>
          <div class="tw-impact-bar">
            <div class="tw-impact-bar-before" style="width:${bv}%"></div>
            <div class="tw-impact-bar-after" style="width:${av}%"></div>
          </div>
          <span class="tw-impact-diff ${diffClass}">(${diffStr})</span>
        </div>
      `;
    }
    html += '</div>';
  }

  // Path balance
  const balBefore = before.path_balance || {};
  const balAfter = after.path_balance || {};
  html += `
    <div class="tw-impact-section">
      <div class="tw-impact-section-label">Path Balance</div>
      <div class="tw-impact-balance">
        <span>${balBefore.gap_pct || 0}% gap / ${balBefore.strength_pct || 0}% strength</span>
        <span class="tw-impact-arrow">\u25B6</span>
        <span>${balAfter.gap_pct || 0}% gap / ${balAfter.strength_pct || 0}% strength</span>
      </div>
    </div>
  `;

  // Journey mix
  const jBefore = before.journey_mix || {};
  const jAfter = after.journey_mix || {};
  const allJourneys = [...new Set([...Object.keys(jBefore), ...Object.keys(jAfter)])];
  if (allJourneys.length > 0) {
    html += '<div class="tw-impact-section"><div class="tw-impact-section-label">Journey Mix</div><div class="tw-impact-journey-list">';
    for (const j of allJourneys) {
      const bCount = jBefore[j] || 0;
      const aCount = jAfter[j] || 0;
      const diff = aCount - bCount;
      if (diff !== 0) {
        html += `<span class="tw-impact-journey-item">${diff > 0 ? '+' : ''}${diff} ${esc(j)} (now ${aCount})</span>`;
      }
    }
    html += '</div></div>';
  }

  bodyEl.innerHTML = html || '<div class="tw-impact-neutral">No significant changes detected</div>';
}

// ── Apply / Cancel ────────────────────────────────────────────────────────

function cancelPathChange() {
  // Revert DOM to pre-drag state
  restoreBoardState(_pathPreDragState);
  _pathPreDragState = null;

  const preview = document.getElementById('tw-impact-preview');
  if (preview) preview.style.display = 'none';
}

async function applyPathChange() {
  const preview = document.getElementById('tw-impact-preview');
  if (!preview) return;

  const lessonId = parseInt(preview.dataset.lessonId, 10);
  const fromCol = preview.dataset.fromCol;
  const toCol = preview.dataset.toCol;

  const tw = getState().toryWorkspace;
  const userId = tw.selectedUserId;
  if (!userId) return;

  const applyBtn = document.getElementById('tw-impact-apply');
  if (applyBtn) { applyBtn.disabled = true; applyBtn.textContent = 'Applying...'; }

  try {
    if (fromCol === 'pool' && (toCol === 'discovery' || toCol === 'main')) {
      // Adding a lesson from pool — swap with nothing (add)
      await api.swapToryLesson(userId, {
        coach_id: 0,
        remove_lesson_id: 0,
        add_lesson_id: lessonId,
        reason: 'Added via path builder kanban',
      });
    } else if ((fromCol === 'discovery' || fromCol === 'main') && toCol === 'pool') {
      // Removing a lesson back to pool
      await api.swapToryLesson(userId, {
        coach_id: 0,
        remove_lesson_id: lessonId,
        add_lesson_id: 0,
        reason: 'Removed via path builder kanban',
      });
    } else {
      // Reorder within or between discovery/main — collect current ordering
      const ordering = [];
      let seq = 1;
      for (const colId of ['discovery', 'main']) {
        const colEl = document.querySelector(`.tw-path-col[data-col="${colId}"] .tw-path-cards`);
        if (!colEl) continue;
        const cards = colEl.querySelectorAll('.tw-path-card');
        cards.forEach(card => {
          const recId = parseInt(card.dataset.recId, 10);
          if (recId) {
            ordering.push({ recommendation_id: recId, new_sequence: seq++ });
          }
        });
      }

      if (ordering.length > 0) {
        await api.reorderToryPath(userId, {
          coach_id: 0,
          ordering,
          reason: 'Reordered via path builder kanban',
        });
      }
    }

    showToast('Path updated successfully', 'success');
    _pathPreDragState = null;
    preview.style.display = 'none';

    // Reload detail to reflect new state
    loadUserDetail(userId);
  } catch (err) {
    showToast(`Failed to update path: ${err.message}`, 'error');
    if (applyBtn) { applyBtn.disabled = false; applyBtn.textContent = 'Apply Change'; }
  }
}

// ── Available Pool Loader ─────────────────────────────────────────────────

async function loadAvailablePool(currentRecs) {
  const poolCol = document.querySelector('.tw-path-col[data-col="pool"] .tw-path-cards');
  if (!poolCol) return;

  poolCol.innerHTML = '<div class="tw-loading"><div class="tw-spinner"></div> Loading lessons...</div>';

  try {
    const data = await api.getToryContentLibrary();
    const journeys = data.journeys || [];

    // Build set of lesson IDs already in the path
    const inPath = new Set(currentRecs.map(r => parseInt(r.nx_lesson_id, 10)));

    // Flatten all lessons from the content library (deduplicate by lesson ID)
    const poolLessons = [];
    const seen = new Set();
    for (const journey of journeys) {
      const lessons = journey.lessons || [];
      for (const lesson of lessons) {
        const lid = parseInt(lesson.nx_lesson_id || lesson.lesson_id, 10);
        if (!inPath.has(lid) && !seen.has(lid)) {
          seen.add(lid);
          poolLessons.push({
            nx_lesson_id: lid,
            lesson_name: lesson.lesson_name || lesson.name || `Lesson ${lid}`,
            journey_id: lesson.journey_detail_id || journey.journey_detail_id || 0,
            journey_name: lesson.journey_name || journey.journey_name || '',
            match_score: lesson.match_score || 0,
            difficulty: lesson.difficulty || 3,
            source: 'pool',
          });
        }
      }
    }

    // Sort by match_score descending
    poolLessons.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));

    // Update count
    const countEl = document.querySelector('.tw-path-col[data-col="pool"] .tw-path-col-count');
    if (countEl) countEl.textContent = String(poolLessons.length);

    poolCol.innerHTML = '';
    if (poolLessons.length === 0) {
      poolCol.innerHTML = '<div class="tw-path-empty">All lessons are in the path</div>';
      return;
    }

    for (let i = 0; i < poolLessons.length; i++) {
      poolCol.appendChild(buildPathCard(poolLessons[i], 'pool', i));
    }
  } catch (err) {
    poolCol.innerHTML = `<div class="tw-path-empty">Failed to load: ${esc(err.message)}</div>`;
  }
}

// ── Content Tab ─────────────────────────────────────────────────────────────

// Module-level content library state
let _contentCache = null;        // Cached content library data
let _contentSearch = '';         // Search filter
let _contentJourneyFilter = '';  // Journey filter
let _contentReviewFilter = '';   // Review status filter
let _contentExpanded = null;     // { lessonId, tagId } of expanded card
let _contentSlides = null;       // Current slides data for modal
let _contentSlideIdx = 0;        // Current slide index
let _contentSlidesLoading = false;

// Known EPP traits for tag editor
const EPP_TRAITS = [
  'Achievement', 'Assertiveness', 'Attention to Detail', 'Cooperativeness',
  'Creativity', 'Dependability', 'Flexibility', 'Initiative',
  'Leadership', 'Optimism', 'Patience', 'Persistence',
  'Self-Confidence', 'Self-Control', 'Social Orientation', 'Stress Tolerance',
];

function renderContentTab(el) {
  el.innerHTML = '';

  // Show loading on first load
  if (!_contentCache) {
    el.innerHTML = '<div class="tw-loading"><div class="tw-spinner"></div> Loading content library...</div>';
    loadContentLibrary().then(() => {
      const freshEl = document.getElementById('tw-tab-content');
      if (freshEl) renderContentTab(freshEl);
    });
    return;
  }

  const journeys = _contentCache.journeys || [];

  // ── Toolbar ──
  const toolbar = document.createElement('div');
  toolbar.className = 'tw-content-toolbar';
  toolbar.innerHTML = `
    <div class="tw-content-toolbar-left">
      <div class="tw-search-row">
        <span class="tw-search-icon">&#128269;</span>
        <input type="text" id="tw-content-search" placeholder="Search lessons..." value="${esc(_contentSearch)}">
      </div>
      <select id="tw-content-journey-filter">
        <option value="">All Journeys</option>
        ${journeys.map(j => `<option value="${esc(j.journey_name)}" ${_contentJourneyFilter === j.journey_name ? 'selected' : ''}>${esc(j.journey_name)} (${(j.lessons || []).length})</option>`).join('')}
      </select>
      <select id="tw-content-review-filter">
        <option value="">All Status</option>
        <option value="pending" ${_contentReviewFilter === 'pending' ? 'selected' : ''}>Pending</option>
        <option value="approved" ${_contentReviewFilter === 'approved' ? 'selected' : ''}>Approved</option>
        <option value="needs_review" ${_contentReviewFilter === 'needs_review' ? 'selected' : ''}>Needs Review</option>
        <option value="corrected" ${_contentReviewFilter === 'corrected' ? 'selected' : ''}>Corrected</option>
      </select>
    </div>
    <div class="tw-content-toolbar-right">
      <button class="btn btn-ghost btn-sm" id="tw-content-refresh" title="Refresh content library">Refresh</button>
      <button class="btn btn-primary btn-sm" id="tw-content-bulk-approve">Bulk Approve (70%+)</button>
    </div>
  `;
  el.appendChild(toolbar);

  // Wire toolbar events
  let contentSearchTimer = null;
  toolbar.querySelector('#tw-content-search').addEventListener('input', (e) => {
    clearTimeout(contentSearchTimer);
    contentSearchTimer = setTimeout(() => {
      _contentSearch = e.target.value.trim().toLowerCase();
      renderContentLibraryBody();
    }, DEBOUNCE_MS);
  });
  toolbar.querySelector('#tw-content-journey-filter').addEventListener('change', (e) => {
    _contentJourneyFilter = e.target.value;
    renderContentLibraryBody();
  });
  toolbar.querySelector('#tw-content-review-filter').addEventListener('change', (e) => {
    _contentReviewFilter = e.target.value;
    renderContentLibraryBody();
  });
  toolbar.querySelector('#tw-content-refresh').addEventListener('click', () => {
    _contentCache = null;
    renderContentTab(el);
  });
  toolbar.querySelector('#tw-content-bulk-approve').addEventListener('click', bulkApproveContent);

  // ── Library Body (swim lanes) ──
  const body = document.createElement('div');
  body.className = 'tw-content-library';
  body.id = 'tw-content-library';
  el.appendChild(body);

  renderContentLibraryBody();
}

async function loadContentLibrary() {
  try {
    const data = await api.getToryContentLibrary();
    _contentCache = data;
  } catch (err) {
    showToast(`Failed to load content library: ${err.message}`, 'error');
    _contentCache = { journeys: [] };
  }
}

function renderContentLibraryBody() {
  const body = document.getElementById('tw-content-library');
  if (!body || !_contentCache) return;

  body.innerHTML = '';
  const journeys = _contentCache.journeys || [];

  // Get user path data if user is selected
  const tw = getState().toryWorkspace;
  const pathRecs = tw.selectedUserDetail?.path?.path || [];
  const pathMap = new Map();
  for (const rec of pathRecs) {
    pathMap.set(parseInt(rec.nx_lesson_id, 10), rec);
  }

  // Sort journeys: those with slides first, empty seed data last
  const sorted = [...journeys].sort((a, b) => {
    const aSlides = (a.lessons || []).reduce((s, l) => s + (parseInt(l.slide_count, 10) || 0), 0);
    const bSlides = (b.lessons || []).reduce((s, l) => s + (parseInt(l.slide_count, 10) || 0), 0);
    if (aSlides > 0 && bSlides === 0) return -1;
    if (aSlides === 0 && bSlides > 0) return 1;
    return 0;
  });

  // Filter journeys
  const filtered = _contentJourneyFilter
    ? sorted.filter(j => j.journey_name === _contentJourneyFilter)
    : sorted;

  if (filtered.length === 0) {
    body.innerHTML = '<div class="tw-placeholder"><div class="tw-placeholder-text">No journeys found</div></div>';
    return;
  }

  for (const journey of filtered) {
    const lessons = filterLessons(journey.lessons || []);
    if (lessons.length === 0 && _contentSearch) continue;

    const inPathCount = lessons.filter(l => pathMap.has(parseInt(l.nx_lesson_id, 10))).length;

    // Journey row
    const row = document.createElement('div');
    row.className = 'tw-content-journey';

    // Header
    const totalSlides = lessons.reduce((s, l) => s + (parseInt(l.slide_count, 10) || 0), 0);
    const hasContent = totalSlides > 0;
    const header = document.createElement('div');
    header.className = 'tw-content-journey-header';
    header.innerHTML = `
      <span class="tw-content-journey-name">${esc(journey.journey_name)}</span>
      <span class="tw-content-journey-count">${lessons.length} lesson${lessons.length !== 1 ? 's' : ''}${pathMap.size > 0 ? ` · ${inPathCount} in path` : ''}${!hasContent ? ' · metadata only' : ''}</span>
    `;
    row.appendChild(header);

    // Swim lane
    const lane = document.createElement('div');
    lane.className = 'tw-content-lane';

    for (const lesson of lessons) {
      const lessonId = parseInt(lesson.nx_lesson_id, 10);
      const pathRec = pathMap.get(lessonId);
      lane.appendChild(buildContentCard(lesson, pathRec, journey));
    }

    if (lessons.length === 0) {
      lane.innerHTML = '<div class="tw-content-lane-empty">No matching lessons</div>';
    }

    row.appendChild(lane);
    body.appendChild(row);

    // Expansion panel (rendered below the row if a card in this journey is expanded)
    if (_contentExpanded) {
      const expandedLesson = lessons.find(l =>
        parseInt(l.nx_lesson_id, 10) === _contentExpanded.lessonId
      );
      if (expandedLesson) {
        const panel = buildContentPreview(expandedLesson, pathMap.get(_contentExpanded.lessonId), journey);
        body.appendChild(panel);
      }
    }
  }
}

function filterLessons(lessons) {
  return lessons.filter(l => {
    if (_contentSearch) {
      const name = (l.lesson_name || '').toLowerCase();
      const desc = (l.lesson_desc || '').toLowerCase();
      if (!name.includes(_contentSearch) && !desc.includes(_contentSearch)) return false;
    }
    if (_contentReviewFilter && l.review_status !== _contentReviewFilter) return false;
    return true;
  });
}

function buildContentCard(lesson, pathRec, journey) {
  const lessonId = parseInt(lesson.nx_lesson_id, 10);
  const isExpanded = _contentExpanded && _contentExpanded.lessonId === lessonId;
  const slideCount = parseInt(lesson.slide_count, 10) || 0;

  const card = document.createElement('div');
  const noSlides = slideCount === 0;
  card.className = `tw-content-card${isExpanded ? ' expanded' : ''}${noSlides ? ' no-content' : ''}`;
  card.dataset.lessonId = lessonId;

  const confidence = Math.round(lesson.confidence || 0);
  const difficulty = lesson.difficulty || 3;
  const reviewStatus = lesson.review_status || 'pending';
  const learningStyle = lesson.learning_style || '';

  // Review status color map
  const reviewColors = {
    approved: 'var(--green)',
    pending: 'var(--yellow)',
    needs_review: 'var(--red)',
    corrected: 'var(--blue)',
    dismissed: 'var(--text-tertiary)',
  };
  const reviewColor = reviewColors[reviewStatus] || reviewColors.pending;

  // Match score overlay (when user selected)
  let matchOverlay = '';
  if (pathRec) {
    const score = Math.round(pathRec.match_score || 0);
    const matchClass = score >= 70 ? 'high' : score >= 40 ? 'mid' : 'low';
    matchOverlay = `<div class="tw-content-match ${matchClass}">${score}</div>`;

    // Path position badge
    const seq = pathRec.sequence || '?';
    const isDiscovery = pathRec.is_discovery;
    matchOverlay += `<div class="tw-content-path-badge">In Path #${seq}</div>`;
    if (isDiscovery) {
      matchOverlay += `<div class="tw-content-discovery-badge">Discovery</div>`;
    }
  }

  // Media icons for production content
  let mediaIcons = '';
  if (slideCount > 0) {
    mediaIcons = `<span class="tw-content-slides-badge" title="${slideCount} slides">&#128444; ${slideCount}</span>`;
  }

  // Description
  const desc = lesson.lesson_desc || '';

  // Trait tags (top 3 by relevance)
  const traits = (lesson.trait_tags || [])
    .sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))
    .slice(0, 3);
  const traitHtml = traits.length > 0
    ? `<div class="tw-content-card-traits">${traits.map(t =>
        `<span class="tw-content-trait ${esc(t.direction || '')}" title="${esc(t.trait)}: ${t.relevance_score}% (${t.direction})">${esc(t.trait)}</span>`
      ).join('')}</div>`
    : '';

  card.innerHTML = `
    ${matchOverlay}
    <div class="tw-content-card-title">${esc(lesson.lesson_name || 'Untitled')}</div>
    ${desc ? `<div class="tw-content-card-desc">${esc(desc)}</div>` : ''}
    ${traitHtml}
    <div class="tw-content-card-meta">
      ${difficultyDots(difficulty)}
      ${learningStyle ? `<span class="tw-content-ls-badge">${esc(learningStyle)}</span>` : ''}
    </div>
    <div class="tw-content-card-bottom">
      <span class="tw-content-review" style="color:${reviewColor}">${esc(reviewStatus)}</span>
      <div class="tw-content-confidence" title="Confidence: ${confidence}%">
        <div class="tw-content-confidence-bar" style="width:${confidence}%"></div>
      </div>
      ${mediaIcons}
    </div>
  `;

  // Click to expand
  card.addEventListener('click', () => {
    if (_contentExpanded && _contentExpanded.lessonId === lessonId) {
      _contentExpanded = null;
    } else {
      _contentExpanded = { lessonId, tagId: lesson.tag_id };
    }
    renderContentLibraryBody();
  });

  return card;
}

// ── Layer 2: Lesson Detail Preview ──────────────────────────────────────────

function buildContentPreview(lesson, pathRec, journey) {
  const panel = document.createElement('div');
  panel.className = 'tw-content-preview';

  const tags = lesson.trait_tags || [];
  if (typeof tags === 'string') {
    try { lesson.trait_tags = JSON.parse(tags); } catch { lesson.trait_tags = []; }
  }
  const traitTags = Array.isArray(lesson.trait_tags) ? lesson.trait_tags : [];

  const directionColors = { builds: 'var(--green)', leverages: 'var(--blue)', challenges: 'var(--yellow)' };
  const slideCount = lesson.slide_count || 0;

  let html = `
    <div class="tw-content-preview-header">
      <div class="tw-content-preview-title">${esc(lesson.lesson_name || 'Untitled')}</div>
      <button class="tw-content-preview-close" id="tw-preview-close">&times;</button>
    </div>
    <div class="tw-content-preview-body">
      <div class="tw-content-preview-info">
        <span class="tw-content-preview-journey">${esc(journey.journey_name)}</span>
        <span>Difficulty: ${difficultyDots(lesson.difficulty || 3)}</span>
        <span>Style: ${esc(lesson.learning_style || '—')}</span>
      </div>
      ${lesson.lesson_desc ? `<p class="tw-content-preview-desc">${esc(lesson.lesson_desc)}</p>` : ''}

      <div class="tw-content-preview-section">
        <div class="tw-content-preview-label">Trait Tags</div>
        <div class="tw-content-tags">
          ${traitTags.length > 0 ? traitTags.map(t => {
            const color = directionColors[t.direction] || 'var(--text-secondary)';
            return `<span class="tw-content-tag" style="border-left-color:${color}">
              <strong>${esc(t.trait)}</strong> ${t.relevance_score || ''}
              <em>${esc(t.direction || '')}</em>
            </span>`;
          }).join('') : '<span class="tw-content-tag-empty">No tags</span>'}
        </div>
      </div>

      <div class="tw-content-preview-section">
        <div class="tw-content-preview-label">Review</div>
        <div class="tw-content-preview-review">
          <span>Status: <strong>${esc(lesson.review_status || 'pending')}</strong></span>
          <span>Confidence: <strong>${Math.round(lesson.confidence || 0)}%</strong></span>
        </div>
      </div>
  `;

  // Path info if user selected
  if (pathRec) {
    html += `
      <div class="tw-content-preview-section">
        <div class="tw-content-preview-label">Path Match</div>
        <div class="tw-content-preview-match">
          <span>Score: <strong>${Math.round(pathRec.match_score || 0)}</strong></span>
          <span>Position: <strong>#${pathRec.sequence || '?'}</strong></span>
          ${pathRec.is_discovery ? '<span class="tw-content-discovery-badge">Discovery</span>' : ''}
        </div>
        ${pathRec.rationale ? `<p class="tw-content-preview-rationale">${esc(pathRec.rationale)}</p>` : ''}
      </div>
    `;
  }

  html += '</div>'; // close preview body

  // Action buttons
  html += `
    <div class="tw-content-preview-actions">
      ${slideCount > 0 ? `<button class="btn btn-primary btn-sm" id="tw-view-slides" data-ldid="${esc(String(lesson.lesson_detail_id || ''))}" data-name="${esc(lesson.lesson_name || '')}">View Slides (${slideCount})</button>` : ''}
      <button class="btn btn-ghost btn-sm tw-action-approve" data-tag-id="${lesson.tag_id || ''}">Approve</button>
      <button class="btn btn-ghost btn-sm tw-action-dismiss" data-tag-id="${lesson.tag_id || ''}">Dismiss</button>
      <button class="btn btn-ghost btn-sm tw-action-edit-tags" data-tag-id="${lesson.tag_id || ''}">Edit Tags</button>
    </div>
  `;

  // Tag editor (hidden initially)
  html += `
    <div class="tw-tag-editor" id="tw-tag-editor" style="display:none">
      <div class="tw-tag-editor-title">Edit Tags</div>
      <div id="tw-tag-editor-rows"></div>
      <button class="btn btn-ghost btn-sm" id="tw-tag-add-row">+ Add Tag</button>
      <div class="tw-tag-editor-actions">
        <button class="btn btn-ghost btn-sm" id="tw-tag-cancel">Cancel</button>
        <button class="btn btn-primary btn-sm" id="tw-tag-save" data-tag-id="${lesson.tag_id || ''}">Save Tags</button>
      </div>
    </div>
  `;

  panel.innerHTML = html;

  // Wire events
  panel.querySelector('#tw-preview-close').addEventListener('click', () => {
    _contentExpanded = null;
    renderContentLibraryBody();
  });

  // View slides
  const viewSlidesBtn = panel.querySelector('#tw-view-slides');
  if (viewSlidesBtn) {
    viewSlidesBtn.addEventListener('click', () => {
      const ldId = viewSlidesBtn.dataset.ldid;
      const name = viewSlidesBtn.dataset.name;
      if (ldId) openSlideViewer(ldId, name);
    });
  }

  // Approve
  panel.querySelector('.tw-action-approve')?.addEventListener('click', async (e) => {
    const tagId = parseInt(e.target.dataset.tagId, 10);
    if (!tagId) return;
    try {
      await api.reviewApprove(tagId, 0, '');
      showToast('Tag approved', 'success');
      _contentCache = null;
      renderContentTab(document.getElementById('tw-tab-content'));
    } catch (err) {
      showToast(`Approve failed: ${err.message}`, 'error');
    }
  });

  // Dismiss
  panel.querySelector('.tw-action-dismiss')?.addEventListener('click', async (e) => {
    const tagId = parseInt(e.target.dataset.tagId, 10);
    if (!tagId) return;
    try {
      await api.reviewDismiss(tagId, 0, 'Dismissed via content library');
      showToast('Tag dismissed', 'success');
      _contentCache = null;
      renderContentTab(document.getElementById('tw-tab-content'));
    } catch (err) {
      showToast(`Dismiss failed: ${err.message}`, 'error');
    }
  });

  // Edit tags toggle
  panel.querySelector('.tw-action-edit-tags')?.addEventListener('click', () => {
    const editor = panel.querySelector('#tw-tag-editor');
    if (!editor) return;
    const isVisible = editor.style.display !== 'none';
    editor.style.display = isVisible ? 'none' : '';
    if (!isVisible) populateTagEditor(panel, traitTags);
  });

  // Tag editor cancel
  panel.querySelector('#tw-tag-cancel')?.addEventListener('click', () => {
    panel.querySelector('#tw-tag-editor').style.display = 'none';
  });

  // Tag editor add row
  panel.querySelector('#tw-tag-add-row')?.addEventListener('click', () => {
    addTagEditorRow(panel.querySelector('#tw-tag-editor-rows'), null);
  });

  // Tag editor save
  panel.querySelector('#tw-tag-save')?.addEventListener('click', async (e) => {
    const tagId = parseInt(e.target.dataset.tagId, 10);
    if (!tagId) return;
    const rows = panel.querySelectorAll('.tw-tag-row');
    const correctedTags = [];
    rows.forEach(row => {
      const trait = row.querySelector('.tw-tag-trait')?.value;
      const score = parseInt(row.querySelector('.tw-tag-relevance')?.value || '50', 10);
      const direction = row.querySelector('.tw-tag-direction')?.value || 'builds';
      if (trait) correctedTags.push({ trait, relevance_score: score, direction });
    });
    try {
      await api.reviewCorrect(tagId, 0, correctedTags);
      showToast('Tags updated', 'success');
      _contentCache = null;
      renderContentTab(document.getElementById('tw-tab-content'));
    } catch (err) {
      showToast(`Tag correction failed: ${err.message}`, 'error');
    }
  });

  return panel;
}

function populateTagEditor(panel, existingTags) {
  const container = panel.querySelector('#tw-tag-editor-rows');
  if (!container) return;
  container.innerHTML = '';
  if (existingTags.length === 0) {
    addTagEditorRow(container, null);
  } else {
    for (const tag of existingTags) {
      addTagEditorRow(container, tag);
    }
  }
}

function addTagEditorRow(container, tag) {
  if (!container) return;
  const row = document.createElement('div');
  row.className = 'tw-tag-row';
  row.innerHTML = `
    <select class="tw-tag-trait">
      <option value="">Select trait...</option>
      ${EPP_TRAITS.map(t => `<option value="${esc(t)}" ${tag && tag.trait === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
    </select>
    <input type="range" class="tw-tag-relevance" min="0" max="100" value="${tag ? tag.relevance_score || 50 : 50}">
    <span class="tw-tag-relevance-val">${tag ? tag.relevance_score || 50 : 50}</span>
    <select class="tw-tag-direction">
      <option value="builds" ${tag && tag.direction === 'builds' ? 'selected' : ''}>builds</option>
      <option value="leverages" ${tag && tag.direction === 'leverages' ? 'selected' : ''}>leverages</option>
      <option value="challenges" ${tag && tag.direction === 'challenges' ? 'selected' : ''}>challenges</option>
    </select>
    <button class="tw-tag-remove" title="Remove">&times;</button>
  `;

  // Wire range display
  const range = row.querySelector('.tw-tag-relevance');
  const rangeVal = row.querySelector('.tw-tag-relevance-val');
  range.addEventListener('input', () => { rangeVal.textContent = range.value; });

  // Wire remove
  row.querySelector('.tw-tag-remove').addEventListener('click', () => row.remove());

  container.appendChild(row);
}

async function bulkApproveContent() {
  try {
    const result = await api.reviewBulkApprove(0, 70);
    const count = result.approved_count || result.count || 0;
    showToast(`Bulk approved ${count} tags with 70%+ confidence`, 'success');
    _contentCache = null;
    renderContentTab(document.getElementById('tw-tab-content'));
  } catch (err) {
    showToast(`Bulk approve failed: ${err.message}`, 'error');
  }
}

// ── Layer 3: Slide Viewer Modal ─────────────────────────────────────────────

async function openSlideViewer(lessonDetailId, lessonName) {
  _contentSlides = null;
  _contentSlideIdx = 0;
  _contentSlidesLoading = true;

  // Create modal immediately with loading
  renderSlideModal(lessonName);

  try {
    const data = await api.getToryLessonSlides(lessonDetailId);
    _contentSlides = data.slides || data || [];
    _contentSlidesLoading = false;
    renderSlideModal(lessonName);
  } catch (err) {
    _contentSlidesLoading = false;
    showToast(`Failed to load slides: ${err.message}`, 'error');
    closeSlideViewer();
  }
}

function renderSlideModal(lessonName) {
  // Remove existing modal & clean up Swiper/Plyr instances
  _destroySlideViewerInstances();
  document.getElementById('tw-slide-modal')?.remove();

  const modal = document.createElement('div');
  modal.className = 'tw-slide-modal';
  modal.id = 'tw-slide-modal';

  if (_contentSlidesLoading) {
    modal.innerHTML = `
      <div class="tw-slide-overlay"></div>
      <div class="tw-slide-container">
        <div class="tw-slide-header">
          <span class="tw-slide-title">${esc(lessonName || 'Slides')}</span>
          <button class="tw-slide-close" id="tw-slide-close">&times;</button>
        </div>
        <div class="tw-loading" style="flex:1"><div class="tw-spinner"></div> Loading slides...</div>
      </div>
    `;
    document.body.appendChild(modal);
    _wireSlideClose(modal);
    return;
  }

  const slides = _contentSlides || [];
  if (slides.length === 0) {
    modal.innerHTML = `
      <div class="tw-slide-overlay"></div>
      <div class="tw-slide-container">
        <div class="tw-slide-header">
          <span class="tw-slide-title">${esc(lessonName || 'Slides')}</span>
          <button class="tw-slide-close" id="tw-slide-close">&times;</button>
        </div>
        <div class="tw-placeholder" style="flex:1"><div class="tw-placeholder-text">No slides found</div></div>
      </div>
    `;
    document.body.appendChild(modal);
    _wireSlideClose(modal);
    return;
  }

  const total = slides.length;

  // Build swiper-slide elements for each slide
  const swiperSlides = slides.map((slide, i) => {
    let content = slide.content || slide.slide_content;
    if (typeof content === 'string') {
      try { content = JSON.parse(content); } catch { content = {}; }
    }
    content = content || {};
    const slideType = slide.type || slide.slide_type || 'unknown';
    const slideHtml = renderSlideContent(slideType, content, slide);
    return `<div class="swiper-slide">
      <div class="tw-slide-inner">${slideHtml}</div>
      <div class="tw-slide-type-badge">${esc(slideType)}</div>
    </div>`;
  }).join('');

  // Build dot pagination (max 15 visible, then show first/last)
  const maxDots = Math.min(total, 15);
  const dotsHtml = Array.from({ length: total }, (_, i) =>
    `<button class="tw-slide-dot${i === 0 ? ' active' : ''}" data-idx="${i}"></button>`
  ).join('');

  modal.innerHTML = `
    <div class="tw-slide-overlay"></div>
    <div class="tw-slide-container">
      <div class="tw-slide-header">
        <span class="tw-slide-title">${esc(lessonName || 'Slides')}</span>
        <span class="tw-slide-counter" id="tw-slide-counter">Slide 1 / ${total}</span>
        <button class="tw-slide-close" id="tw-slide-close">&times;</button>
      </div>
      <div class="swiper tw-swiper" id="tw-swiper">
        <div class="swiper-wrapper">${swiperSlides}</div>
      </div>
      <button class="tw-slide-nav-prev" id="tw-slide-prev" aria-label="Previous slide">&#8249;</button>
      <button class="tw-slide-nav-next" id="tw-slide-next" aria-label="Next slide">&#8250;</button>
      <div class="tw-slide-dots" id="tw-slide-dots">${dotsHtml}</div>
    </div>
  `;

  document.body.appendChild(modal);
  _wireSlideClose(modal);

  // Defer Swiper init to next frame so browser has completed layout
  requestAnimationFrame(() => {
    const startIdx = Math.max(0, Math.min(_contentSlideIdx, total - 1));
    const swiper = new Swiper('#tw-swiper', {
      slidesPerView: 1,
      initialSlide: startIdx,
      effect: 'slide',
      speed: 300,
      keyboard: { enabled: true, onlyInViewport: false },
      observer: true,
      observeParents: true,
    });
    modal._swiperInstance = swiper;

    // Custom nav buttons
    const prevBtn = modal.querySelector('#tw-slide-prev');
    const nextBtnEl = modal.querySelector('#tw-slide-next');
    const counterEl = modal.querySelector('#tw-slide-counter');
    const dotsContainer = modal.querySelector('#tw-slide-dots');

    prevBtn.addEventListener('click', () => swiper.slidePrev());
    nextBtnEl.addEventListener('click', () => swiper.slideNext());

    // Dot clicks
    dotsContainer.addEventListener('click', (e) => {
      const dot = e.target.closest('.tw-slide-dot');
      if (dot) swiper.slideTo(parseInt(dot.dataset.idx, 10));
    });

    // Update UI on slide change
    const updateSlideUI = () => {
      const idx = swiper.activeIndex;
      _contentSlideIdx = idx;
      if (counterEl) counterEl.textContent = `Slide ${idx + 1} / ${total}`;
      prevBtn.disabled = idx === 0;
      nextBtnEl.disabled = idx === total - 1;
      dotsContainer.querySelectorAll('.tw-slide-dot').forEach((d, i) => {
        d.classList.toggle('active', i === idx);
      });
    };
    swiper.on('slideChange', updateSlideUI);
    updateSlideUI(); // initial state

    // Initialize Plyr for video and audio elements
    const plyrInstances = [];
    modal.querySelectorAll('.tw-plyr-video').forEach(el => {
      plyrInstances.push(new Plyr(el, { controls: ['play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen'] }));
    });
    modal.querySelectorAll('.tw-plyr-audio').forEach(el => {
      plyrInstances.push(new Plyr(el, { controls: ['play', 'progress', 'current-time', 'mute', 'volume'] }));
    });
    modal._plyrInstances = plyrInstances;
  }); // end requestAnimationFrame
}

function _wireSlideClose(modal) {
  modal.querySelector('#tw-slide-close')?.addEventListener('click', closeSlideViewer);
  modal.querySelector('.tw-slide-overlay')?.addEventListener('click', closeSlideViewer);
  // Escape for loading/empty states
  modal._keyHandler = (e) => {
    if (e.key === 'Escape') closeSlideViewer();
  };
  document.addEventListener('keydown', modal._keyHandler);
}

function _destroySlideViewerInstances() {
  const existing = document.getElementById('tw-slide-modal');
  if (!existing) return;
  if (existing._swiperInstance) { try { existing._swiperInstance.destroy(true, true); } catch {} }
  if (existing._plyrInstances) { existing._plyrInstances.forEach(p => { try { p.destroy(); } catch {} }); }
}

function closeSlideViewer() {
  const modal = document.getElementById('tw-slide-modal');
  if (modal) {
    if (modal._keyHandler) document.removeEventListener('keydown', modal._keyHandler);
    _destroySlideViewerInstances();
    modal.remove();
  }
  _contentSlides = null;
  _contentSlideIdx = 0;
}

function renderSlideContent(type, content, slide) {
  // Category router — dispatches to type-specific renderers based on data model
  // Reference: .claude/knowledge/slide-data-model.md

  // Category A: Video (94 slides) — video_library_id FK, not in slide_content
  if (/^video/.test(type))
    return _renderVideo(type, content, slide);

  // Category F: Greetings (27) — uses greetings field, NOT content
  if (type === 'greetings')
    return _renderGreeting(content);

  // Category F: Take-away (33) — uses message + message_1/message_2
  if (type === 'take-away')
    return _renderTakeaway(content);

  // Category F: One-word-apprication (7) — uses appreciation with DYNAMIC_WORD
  if (type === 'one-word-apprication' || type === 'one-word-content-box')
    return _renderOneWord(content);

  // Category A: Image family (39+15+14+9+4+4+3+2+2+2 = 94 slides)
  if (/^image\d*$/.test(type) || /^special-image/.test(type) || type === 'sparkle')
    return _renderImage(type, content);

  // Category E: Image + Interactive hybrid (16+6+1+1 = 24)
  if (/^image-with-/.test(type))
    return _renderImageHybrid(type, content);

  // Category B: Question-answer family (29+6+2+5 = 42)
  if (/^question-answer/.test(type) || type === 'question-with-example' || type === 'questions-example2')
    return _renderQuestion(type, content);

  // Category G: Stakeholder (11+11+1+1+1 = 25)
  if (/^stakeholder/.test(type) || type === 'answered-stakeholders')
    return _renderStakeholder(type, content);

  // Category C: Multiple-choice / quiz (6+1)
  if (type === 'multiple-choice' || type === 'single-choice-with-message')
    return _renderMultipleChoice(content);

  // Category C: True/false (3+2 = 5)
  if (type === 'select-true-or-false' || type === 'choose-true-or-false')
    return _renderTrueFalse(content);

  // Category C: Check yes-or-no (5)
  if (type === 'check-yes-or-no')
    return _renderCheckYesNo(content);

  // Category C: Select-range / Likert (3)
  if (type === 'select-range')
    return _renderSelectRange(content);

  // Category C: Three-word / select-one-word (2+2+2 = 6)
  if (type === 'three-word' || type === 'select-one-word' || type === 'one-word-select-option')
    return _renderWordSelection(type, content);

  // Category C: Select-option family (2+6+9+3+5+5+3+1+1 = 35)
  if (/^select-option/.test(type) || type === 'select-the-best')
    return _renderSelectOption(type, content);

  // Category C: Side-by-side dropdown selector (7)
  if (type === 'side-by-side-dropdown-selector')
    return _renderDropdownSelector(content);

  // Category D: Side-by-side forms (6+1+1+1 = 9)
  if (/^side-by-side-/.test(type))
    return _renderSideBySideForm(content);

  // Category F: Special engagement types
  if (type === 'celebrate' || type === 'show-gratitude' || type === 'decision' || type === 'decision2' ||
      type === 'take-to-lunch' || type === 'people-you-would-like-to-thank' || type === 'chat-interface' ||
      type === 'build-your-network')
    return _renderEngagement(type, content);

  // Fallback: unknown type — show type badge + prettified JSON
  return _renderFallback(type, content);
}

// ── Helper: render HTML content safely (preserves HTML entities + tags) ──
function _html(val) {
  if (!val) return '';
  // Fix unicode escape notation stored as literal text in the DB
  return String(val)
    .replace(/u201c/g, '\u201c').replace(/u201d/g, '\u201d')  // smart quotes
    .replace(/u2018/g, '\u2018').replace(/u2019/g, '\u2019')  // smart apostrophes
    .replace(/u2014/g, '\u2014').replace(/u2013/g, '\u2013')  // em/en dash
    .replace(/u2026/g, '\u2026');                               // ellipsis
}
function _headsUp(c) {
  if (!c.is_headsup && !c.heads_up) return '';
  const tip = c.heads_up || '';
  return tip ? `<div class="tw-slide-headsup"><strong>Heads up</strong><div>${_html(tip)}</div></div>` : '';
}
function _backpackBadge(c) {
  let badges = '';
  if (c.is_backpack) badges += '<span class="tw-slide-badge tw-badge-backpack">Backpack</span>';
  if (c.is_task) badges += `<span class="tw-slide-badge tw-badge-task">${esc(c.task_name || 'Task')}</span>`;
  return badges ? `<div class="tw-slide-badges">${badges}</div>` : '';
}

// ── Category A: Video ──
function _renderVideo(type, content, slide) {
  let html = '';
  const vl = slide && slide.video_library;
  if (vl && vl.video_url) {
    // Title above video
    const title = content.slide_title || vl.title || '';
    if (title) html += `<div class="tw-slide-text-content"><h3 class="tw-slide-text-title">${_html(title)}</h3></div>`;
    // Plyr video player
    html += `<div class="tw-slide-media tw-slide-video-wrap">
      <video class="tw-plyr-video" playsinline controls preload="metadata"
        ${vl.thumbnail_url ? `poster="${esc(vl.thumbnail_url)}"` : ''}>
        <source src="${esc(vl.video_url)}" type="video/mp4">
      </video>
    </div>`;
    // Transcript below video
    if (vl.transcript) {
      html += `<div class="tw-slide-transcript"><div class="tw-slide-transcript-label">Transcript</div><div class="tw-slide-transcript-text">${_html(vl.transcript)}</div></div>`;
    }
    // Source badge for blob_inventory matches
    if (vl.source === 'blob_inventory') {
      html += `<div class="tw-slide-source-badge">Video matched from library</div>`;
    }
  } else {
    // No video available — informative placeholder
    html += `<div class="tw-slide-media"><div class="tw-slide-placeholder tw-slide-video-placeholder">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.5;margin-bottom:1rem"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
      <div style="font-size:1.1rem;font-weight:500">Video content</div>
      <div style="font-size:0.85rem;opacity:0.6;margin-top:0.25rem">${esc(content.slide_title || 'Available in the MyNextory app')}</div>
    </div></div>`;
    if (content.slide_title) html += `<div class="tw-slide-text-content"><h3 class="tw-slide-text-title">${_html(content.slide_title)}</h3></div>`;
  }
  html += _headsUp(content);
  // Video variants (video3-6) have options
  if (content.options && Array.isArray(content.options)) {
    html += '<div class="tw-slide-options">';
    for (const opt of content.options) {
      html += `<div class="tw-slide-option"><strong>${_html(opt.title || '')}</strong><div>${_html(opt.msg || '')}</div></div>`;
    }
    html += '</div>';
  }
  // video-with-question: questions[{word, question1, question2}]
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
    html += `<div class="tw-slide-media"><img src="${esc(bg)}" alt="${esc(content.slide_title || 'Lesson image')}" loading="lazy"
      onerror="this.onerror=null;this.parentElement.innerHTML='<div class=\\'tw-slide-placeholder\\'>Image unavailable</div>';"></div>`;
  }
  // Text overlay
  html += '<div class="tw-slide-text-content">';
  if (content.slide_title) html += `<h3 class="tw-slide-text-title">${_html(content.slide_title)}</h3>`;
  if (content.content_title) html += `<div class="tw-slide-content-title">${_html(content.content_title)}</div>`;
  if (content.content) html += `<div class="tw-slide-text-body">${_html(content.content)}</div>`;
  if (content.short_description) html += `<div class="tw-slide-text-body tw-slide-description">${_html(content.short_description)}</div>`;
  // image5: expandable options [{option, description}]
  if (type === 'image5' && content.options && Array.isArray(content.options)) {
    html += '<div class="tw-slide-options tw-slide-expand-options">';
    for (const opt of content.options) {
      const title = typeof opt === 'string' ? opt : (opt.option || '');
      const desc = opt.description || '';
      html += `<details class="tw-slide-option tw-slide-expand-item"><summary>${_html(title)}</summary><div class="tw-slide-expand-desc">${_html(desc)}</div></details>`;
    }
    html += '</div>';
  }
  // image2: imageExamples [{image_title, name, description, background_image}]
  if (content.imageExamples && Array.isArray(content.imageExamples)) {
    html += '<div class="tw-slide-image-examples">';
    for (const ex of content.imageExamples) {
      const imgSrc = ex.background_image || '';
      html += `<div class="tw-slide-image-example-card">`;
      if (imgSrc) html += `<img src="${esc(imgSrc)}" alt="${esc(ex.image_title || '')}" loading="lazy" onerror="this.style.display='none'">`;
      if (ex.image_title) html += `<div class="tw-slide-image-example-label">${_html(ex.image_title)}</div>`;
      if (ex.name) html += `<div class="tw-slide-image-example-name">${_html(ex.name)}</div>`;
      if (ex.description) html += `<div class="tw-slide-image-example-desc">${_html(ex.description)}</div>`;
      html += '</div>';
    }
    html += '</div>';
  }
  // special-image1: background_color, content1, content2, special_word
  if (type === 'special-image1' || type === 'special-image') {
    if (content.content1) html += `<div class="tw-slide-text-body">${_html(content.content1)}</div>`;
    if (content.content2) html += `<div class="tw-slide-text-body">${_html(content.content2)}</div>`;
    if (content.special_word) html += `<div class="tw-slide-special-word">${_html(content.special_word)}</div>`;
  }
  html += '</div>';
  html += _headsUp(content);
  // Audio player
  if (content.audio) {
    html += `<div class="tw-slide-audio"><audio class="tw-plyr-audio" preload="metadata"><source src="${esc(content.audio)}"></audio></div>`;
  }
  return html;
}

// ── Category E: Image + Interactive hybrid ──
function _renderImageHybrid(type, content) {
  let html = '';
  const bg = content.background_image || content.image || '';
  if (bg) {
    html += `<div class="tw-slide-media"><img src="${esc(bg)}" alt="${esc(content.slide_title || '')}" loading="lazy"
      onerror="this.onerror=null;this.parentElement.innerHTML='<div class=\\'tw-slide-placeholder\\'>Image unavailable</div>';"></div>`;
  }
  html += '<div class="tw-slide-text-content">';
  if (content.slide_title) html += `<h3 class="tw-slide-text-title">${_html(content.slide_title)}</h3>`;
  if (content.content_title) html += `<div class="tw-slide-content-title">${_html(content.content_title)}</div>`;
  // image-with-content: uses content as subtitle, content_description as body
  if (content.content && type === 'image-with-content') html += `<div class="tw-slide-content-title">${_html(content.content)}</div>`;
  if (content.content_on_image) html += `<div class="tw-slide-text-body">${_html(content.content_on_image)}</div>`;
  if (content.content_description) html += `<div class="tw-slide-text-body">${_html(content.content_description)}</div>`;
  // image-with-radio: card_title + card_content
  if (content.card_title) html += `<div class="tw-slide-text-body"><strong>${_html(content.card_title)}</strong></div>`;
  if (content.card_content) html += `<div class="tw-slide-text-body">${_html(content.card_content)}</div>`;
  // image-with-question2: options[{question, title, box, answer[]}]
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
  // image-with-questions: questions[] string array
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
    html += `<div class="tw-slide-audio"><audio class="tw-plyr-audio" preload="metadata"><source src="${esc(content.audio)}"></audio></div>`;
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

  // questions can be string[] or [{question, word}] or [{title, question, header}]
  // questions-example2: data typo uses "questionss" with LHS/RHS format
  const questions = c.questions || c.questionss || [];
  if (questions && questions.LHS) {
    // LHS/RHS format (questions-example2)
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

  // question-with-example: examples[][] — show as expandable hints
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
    html += `<div class="tw-slide-text-body">Select ${esc(c.select_count || '3')} stakeholders:</div>`;
    html += '<div class="tw-slide-stakeholder-grid">';
    for (const s of c.stakeholders) {
      const img = s.image || '';
      html += `<div class="tw-slide-stakeholder-card">
        ${img ? `<img src="${esc(img)}" alt="${esc(s.name)}" class="tw-slide-stakeholder-img" onerror="this.style.display='none'">` : '<div class="tw-slide-stakeholder-avatar">&#128100;</div>'}
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
      html += `<div class="tw-slide-question-item"><label>${_html(qs[i])}</label><textarea class="tw-slide-textarea" rows="2" placeholder="${esc(phs[i] || 'Your answer...')}"></textarea></div>`;
    }
    html += '</div>';
  } else {
    // stakeholders-selected, answered-stakeholders
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
  // Header row
  html += '<div class="tw-slide-likert-table"><div class="tw-slide-likert-header"><div class="tw-slide-likert-q"></div>';
  for (const opt of options) html += `<div class="tw-slide-likert-opt">${_html(opt)}</div>`;
  html += '</div>';
  // Question rows
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
    for (const w of words) html += `<span class="tw-slide-word-chip">${esc(w)}</span>`;
    html += '</div>';
  } else if (type === 'select-one-word') {
    if (c.question) html += `<div class="tw-slide-text-body">${_html(c.question)}</div>`;
  } else {
    if (c.content) html += `<div class="tw-slide-text-body">${_html(c.content)}</div>`;
  }
  // one-word-select-option: options[] array of action items
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
  // select-option5: categorization — questions mapped to options
  if (c.questions && Array.isArray(c.questions) && typeof c.questions[0] === 'string') {
    html += '<div class="tw-slide-questions" style="margin-top:1rem">';
    for (const q of c.questions) html += `<div class="tw-slide-question-item"><label>${_html(q)}</label></div>`;
    html += '</div>';
  }
  // select-option-with-message: data[{right_option, wrong_option, message}]
  if (c.data && Array.isArray(c.data)) {
    html += '<div class="tw-slide-options">';
    for (const d of c.data) {
      if (d.right_option) html += `<div class="tw-slide-option tw-quiz-correct">${_html(d.right_option)}</div>`;
      if (d.wrong_option) html += `<div class="tw-slide-option">${_html(d.wrong_option)}</div>`;
      if (d.message) html += `<div class="tw-slide-feedback tw-feedback-improve">${_html(d.message)}</div>`;
    }
    html += '</div>';
  }
  // select-the-best: images[] array for image-based selection
  if (c.images && Array.isArray(c.images)) {
    html += '<div class="tw-slide-image-examples">';
    for (let i = 0; i < c.images.length; i++) {
      html += `<div class="tw-slide-image-example-card"><img src="${esc(c.images[i])}" alt="Option ${i + 1}" loading="lazy" onerror="this.style.display='none'"><div class="tw-slide-image-example-label">Option ${i + 1}</div></div>`;
    }
    html += '</div>';
    if (c.right_message) html += `<div class="tw-slide-feedback tw-feedback-good">${_html(c.right_message)}</div>`;
    if (c.wrong_message) html += `<div class="tw-slide-feedback tw-feedback-improve">${_html(c.wrong_message)}</div>`;
  }
  // select-option-with-button: bonus_material
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
    for (const opt of options) html += `<option>${esc(opt)}</option>`;
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
    html += `<div class="tw-slide-form-lhs"><label>${_html(lhs[i] || '')}</label><textarea class="tw-slide-textarea" rows="2" placeholder="${esc(plhsL[i] || '')}"></textarea></div>`;
    html += `<div class="tw-slide-form-rhs"><label>${_html(rhs[i] || '')}</label><textarea class="tw-slide-textarea" rows="2" placeholder="${esc(plhsR[i] || '')}"></textarea></div>`;
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
    // take-to-lunch, people-you-would-like-to-thank, etc.
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
  html += `<div class="tw-slide-text-body" style="opacity:0.6;font-size:0.85rem">Type: ${esc(type)}</div>`;
  const title = c.slide_title || c.card_title || c.content_title || '';
  if (title) html += `<h3 class="tw-slide-text-title">${_html(title)}</h3>`;
  const text = c.content || c.message || c.greetings || c.appreciation || c.card_content || '';
  if (text) html += `<div class="tw-slide-text-body">${_html(text)}</div>`;
  if (!title && !text) html += `<pre class="tw-slide-json">${esc(JSON.stringify(c, null, 2))}</pre>`;
  html += _headsUp(c);
  html += '</div>';
  return html;
}

// ── Agent Log Tab ───────────────────────────────────────────────────────────

let _agentLogSessionId = null;   // Currently viewing session in agent log
let _agentLogEvents = [];        // Events for the selected session
let _agentLogLoading = false;

function renderAgentLogTab(el) {
  const tw = getState().toryWorkspace;
  const sessions = tw.agentSessions || [];

  if (sessions.length === 0) {
    el.innerHTML = `
      <div class="tw-placeholder">
        <div class="tw-placeholder-icon">&#128221;</div>
        <div class="tw-placeholder-text">No agent sessions yet. Process this user to see the agent log.</div>
      </div>
    `;
    return;
  }

  el.innerHTML = '';

  // Session selector + action buttons row
  const toolbar = h('div', { class: 'tw-agentlog-toolbar' });

  // Session dropdown
  const selectHtml = sessions.map(s => {
    const statusIcon = s.status === 'completed' ? '\u2713' : s.status === 'running' ? '\u25CF' : '\u2717';
    const shortId = (s.id || '').substring(0, 10);
    const date = (s.created_at || '').substring(0, 16);
    return `<option value="${esc(s.id)}" ${s.id === _agentLogSessionId ? 'selected' : ''}>${statusIcon} ${shortId}... (${date}) — ${s.tool_call_count || 0} calls</option>`;
  }).join('');

  toolbar.innerHTML = `
    <div class="tw-agentlog-select-row">
      <select class="tw-agentlog-select" id="tw-agentlog-session-select">${selectHtml}</select>
    </div>
    <div class="tw-agentlog-actions">
      <button class="btn btn-ghost btn-sm" id="tw-agentlog-raw" title="View raw JSONL transcript">View Raw JSONL</button>
      <button class="btn btn-ghost btn-sm" id="tw-agentlog-resume" title="Resume this session in AI Co-pilot">Resume Session</button>
      <button class="btn btn-primary btn-sm" id="tw-agentlog-reprocess" title="Re-process this user with a new agent">Re-process</button>
    </div>
  `;
  el.appendChild(toolbar);

  // Wire up session selector
  toolbar.querySelector('#tw-agentlog-session-select').addEventListener('change', (e) => {
    _agentLogSessionId = e.target.value;
    loadSessionEvents(tw.selectedUserId, _agentLogSessionId);
  });

  // Wire up action buttons
  toolbar.querySelector('#tw-agentlog-raw').addEventListener('click', () => viewRawJsonl());
  toolbar.querySelector('#tw-agentlog-resume').addEventListener('click', () => {
    if (_agentLogSessionId) openSessionInCopilot(_agentLogSessionId);
  });
  toolbar.querySelector('#tw-agentlog-reprocess').addEventListener('click', () => {
    if (tw.selectedUserId) processUser(tw.selectedUserId);
  });

  // Session stats card
  const activeSession = sessions.find(s => s.id === _agentLogSessionId) || sessions[0];
  if (!_agentLogSessionId) _agentLogSessionId = activeSession.id;

  const statusClass = activeSession.status === 'completed' ? 'completed' : activeSession.status === 'running' ? 'running' : 'error';
  const statsCard = h('div', { class: 'tw-agentlog-stats' });
  statsCard.innerHTML = `
    <div class="tw-agentlog-stat">
      <span class="tw-session-badge ${statusClass}">${esc(activeSession.status)}</span>
    </div>
    <div class="tw-agentlog-stat"><strong>${activeSession.tool_call_count || 0}</strong> tool calls</div>
    <div class="tw-agentlog-stat"><strong>${(activeSession.pipeline_steps || []).length}</strong> steps</div>
    <div class="tw-agentlog-stat">${esc((activeSession.created_at || '').substring(0, 19))}</div>
    ${activeSession.status === 'running' ? '<div class="tw-agentlog-stat"><span class="tw-live-dot"></span> Live</div>' : ''}
  `;
  if (activeSession.error_message) {
    statsCard.innerHTML += `<div class="tw-agentlog-error">${esc(activeSession.error_message)}</div>`;
  }
  el.appendChild(statsCard);

  // Timeline container
  const timeline = h('div', { class: 'tw-agent-timeline', id: 'tw-agent-timeline' });
  el.appendChild(timeline);

  // Load events if we don't have them yet or session changed
  if (_agentLogEvents.length === 0 || _agentLogSessionId !== activeSession.id) {
    _agentLogSessionId = activeSession.id;
    loadSessionEvents(tw.selectedUserId, _agentLogSessionId);
  } else {
    renderTimelineEvents(timeline);
  }
}

async function loadSessionEvents(userId, sessionId) {
  if (!userId || !sessionId) return;

  const timeline = document.getElementById('tw-agent-timeline');
  if (timeline) timeline.innerHTML = '<div class="tw-loading"><div class="tw-spinner"></div> Loading session events...</div>';

  _agentLogLoading = true;

  try {
    const data = await api.getToryAgentSession(userId, sessionId);
    _agentLogEvents = data.events || [];
    _agentLogLoading = false;

    const el = document.getElementById('tw-agent-timeline');
    if (el) renderTimelineEvents(el);
  } catch (err) {
    _agentLogLoading = false;
    const el = document.getElementById('tw-agent-timeline');
    if (el) el.innerHTML = `<div class="tw-placeholder"><div class="tw-placeholder-text">Failed to load session: ${esc(err.message)}</div></div>`;
  }
}

function renderTimelineEvents(el) {
  el.innerHTML = '';

  if (_agentLogEvents.length === 0) {
    el.innerHTML = '<div class="tw-placeholder"><div class="tw-placeholder-text">No events in this session yet.</div></div>';
    return;
  }

  for (const event of _agentLogEvents) {
    el.appendChild(createTimelineEntry(event));
  }

  // Auto-scroll to bottom for running sessions
  const tw = getState().toryWorkspace;
  const session = (tw.agentSessions || []).find(s => s.id === _agentLogSessionId);
  if (session && session.status === 'running') {
    el.scrollTop = el.scrollHeight;
  }
}

function createTimelineEntry(event) {
  const time = formatEventTime(event.timestamp);

  switch (event.type) {
    case 'reasoning': {
      const entry = h('div', { class: 'tw-event tw-event-reasoning' });
      entry.innerHTML = `
        <span class="tw-event-time">${time}</span>
        <span class="tw-event-icon">\uD83D\uDCAD</span>
        <p class="tw-event-text">${esc(event.content || '')}</p>
      `;
      return entry;
    }

    case 'tool_call': {
      const entry = document.createElement('details');
      entry.className = 'tw-event tw-event-tool-call';
      const toolName = esc(event.tool || event.name || 'unknown');
      const inputSummary = summarizeToolInput(event.input);
      entry.innerHTML = `
        <summary>
          <span class="tw-event-time">${time}</span>
          <span class="tw-event-icon">\uD83D\uDD27</span>
          <span class="tw-event-tool-name">${toolName}</span><span class="tw-event-tool-args">(${esc(inputSummary)})</span>
        </summary>
        <pre class="tw-event-payload">${esc(JSON.stringify(event.input, null, 2))}</pre>
      `;
      return entry;
    }

    case 'tool_result': {
      const entry = document.createElement('details');
      entry.className = 'tw-event tw-event-tool-result';
      const duration = event.duration ? ` (${event.duration})` : '';
      const isError = event.is_error || event.error;
      entry.innerHTML = `
        <summary>
          <span class="tw-event-time">${time}</span>
          <span class="tw-event-icon">${isError ? '\u274C' : '\u2705'}</span>
          <span class="tw-event-result-label">${isError ? 'Error' : 'Result'}${duration}</span>
        </summary>
        <pre class="tw-event-payload">${esc(JSON.stringify(event.output || event.error || event.content, null, 2))}</pre>
      `;
      return entry;
    }

    case 'message':
    case 'text': {
      const entry = h('div', { class: 'tw-event tw-event-message' });
      entry.innerHTML = `
        <span class="tw-event-time">${time}</span>
        <span class="tw-event-icon">\uD83D\uDCAC</span>
        <p class="tw-event-text">${esc(event.content || '')}</p>
      `;
      return entry;
    }

    default: {
      const entry = h('div', { class: 'tw-event tw-event-other' });
      entry.innerHTML = `
        <span class="tw-event-time">${time}</span>
        <span class="tw-event-icon">\u2022</span>
        <span class="tw-event-text">${esc(event.type || 'event')}: ${esc(event.content || JSON.stringify(event).substring(0, 120))}</span>
      `;
      return entry;
    }
  }
}

function summarizeToolInput(input) {
  if (!input) return '';
  if (typeof input !== 'object') return String(input).substring(0, 60);
  // Show key params concisely
  const parts = [];
  for (const [k, v] of Object.entries(input)) {
    if (parts.length >= 3) { parts.push('...'); break; }
    const val = typeof v === 'object' ? '{...}' : String(v).substring(0, 30);
    parts.push(`${k}=${val}`);
  }
  return parts.join(', ');
}

function formatEventTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ts.substring(11, 19) || ''; }
}

function viewRawJsonl() {
  // Show raw events in a modal-style overlay
  const overlay = h('div', { class: 'tw-raw-overlay', id: 'tw-raw-overlay' });
  const jsonl = _agentLogEvents.map(e => JSON.stringify(e)).join('\n');
  overlay.innerHTML = `
    <div class="tw-raw-modal">
      <div class="tw-raw-header">
        <span>Raw JSONL — Session ${(_agentLogSessionId || '').substring(0, 10)}...</span>
        <button class="btn btn-ghost btn-sm" id="tw-raw-copy">Copy</button>
        <button class="btn btn-ghost btn-sm" id="tw-raw-close">\u2715</button>
      </div>
      <pre class="tw-raw-content">${esc(jsonl)}</pre>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelector('#tw-raw-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector('#tw-raw-copy').addEventListener('click', () => {
    navigator.clipboard.writeText(jsonl).then(() => showToast('Copied to clipboard', 'success'));
  });
}

/** Append a new event to the live agent log timeline */
function appendTimelineEvent(event) {
  _agentLogEvents.push(event);
  const el = document.getElementById('tw-agent-timeline');
  if (!el) return;
  el.appendChild(createTimelineEntry(event));
  el.scrollTop = el.scrollHeight;
}

// ── Co-pilot Drawer ─────────────────────────────────────────────────────────

function renderCopilotDrawer() {
  const tw = getState().toryWorkspace;
  const sessions = tw.agentSessions || [];
  const placeholder = document.getElementById('tw-right-placeholder');
  const chatMessagesEl = document.getElementById('tw-chat-messages');
  const chatInput = document.getElementById('tw-chat-input');
  const sessionMeta = document.getElementById('tw-session-meta');
  const sessionStatus = document.getElementById('tw-session-status');

  if (sessions.length === 0 || !tw.selectedUserId) {
    // Show placeholder, disconnect WS
    if (placeholder) placeholder.style.display = '';
    if (chatMessagesEl) chatMessagesEl.style.display = 'none';
    if (chatInput) chatInput.style.display = 'none';
    if (sessionMeta) sessionMeta.style.display = 'none';
    if (sessionStatus) sessionStatus.style.display = 'none';
    disconnectToryAgentWs();
    _copilotSessionId = null;
    _copilotMessages = [];
    return;
  }

  // Determine which session to show
  const targetSession = _copilotSessionId
    ? sessions.find(s => s.id === _copilotSessionId) || sessions[0]
    : sessions[0];

  const needsReconnect = _copilotSessionId !== targetSession.id;

  if (placeholder) placeholder.style.display = 'none';
  if (chatMessagesEl) chatMessagesEl.style.display = '';
  if (chatInput) chatInput.style.display = '';

  // Session metadata card
  if (sessionMeta) {
    sessionMeta.style.display = '';
    const shortId = (targetSession.id || '').substring(0, 10);
    const date = (targetSession.created_at || '').substring(0, 19);
    const confidence = targetSession.confidence != null ? `${targetSession.confidence}%` : '—';
    sessionMeta.innerHTML = `
      <div class="tw-copilot-meta">
        <div class="tw-copilot-meta-name">${esc(getUserNameFromState())}'s Agent</div>
        <div class="tw-copilot-meta-stats">
          <span>${targetSession.tool_call_count || 0} tool calls</span>
          <span>Conf: ${confidence}</span>
          <span>${date}</span>
        </div>
        <div class="tw-copilot-meta-ws" id="tw-copilot-ws-status">
          ${_copilotWsConnected ? '<span class="tw-ws-dot connected"></span> Connected' : '<span class="tw-ws-dot"></span> Disconnected'}
        </div>
      </div>
    `;
  }

  // Session status badge
  if (sessionStatus) {
    sessionStatus.style.display = '';
    const cls = targetSession.status === 'completed' ? 'completed' : targetSession.status === 'running' ? 'running' : 'error';
    sessionStatus.className = `tw-session-badge ${cls}`;
    sessionStatus.textContent = targetSession.status;
  }

  // Restore chat messages from persistent buffer
  if (chatMessagesEl) {
    chatMessagesEl.innerHTML = '';
    if (_copilotMessages.length === 0) {
      // Welcome message for new session
      _copilotMessages.push({ role: 'ai', content: "I've processed this user. You can ask me questions about their profile, learning path, or request changes." });
    }
    for (const msg of _copilotMessages) {
      renderChatMessageEl(chatMessagesEl, msg.role, msg.content);
    }
    if (_copilotStreaming) {
      renderStreamingIndicator(chatMessagesEl);
    }
  }

  // Connect WebSocket (with auto-reconnect) if session changed
  if (needsReconnect) {
    _copilotSessionId = targetSession.id;
    connectCopilotSession(targetSession.id);
  }
}

function connectCopilotSession(sessionId) {
  connectToryAgentWs(sessionId, handleCopilotMessage);
  _copilotWsConnected = true;
  updateCopilotWsStatus(true);
}

function handleCopilotMessage(data) {
  switch (data.type) {
    case 'agent_message':
    case 'TORY_AGENT_MESSAGE':
      if (data.content) {
        // If streaming, replace the last streaming message
        if (_copilotStreaming && _copilotMessages.length > 0) {
          const last = _copilotMessages[_copilotMessages.length - 1];
          if (last._streaming) {
            last.content += data.content;
            refreshChatDisplay();
            break;
          }
        }
        appendChatMessage('ai', data.content);
      }
      break;

    case 'TORY_AGENT_PROGRESS':
    case 'agent_progress': {
      // Append to agent log timeline if visible
      const event = data.event || data.payload || data;
      appendTimelineEvent(event);

      // Show tool calls as system messages in copilot
      if (event.type === 'tool_call') {
        appendChatMessage('system', `Using tool: ${event.tool || event.name || 'unknown'}`);
      }
      break;
    }

    case 'agent_tool_use':
    case 'TORY_AGENT_TOOL':
      appendChatMessage('system', `Using tool: ${data.tool || data.name || 'unknown'}`);
      // Also add to agent log
      appendTimelineEvent({ type: 'tool_call', tool: data.tool || data.name, input: data.input, timestamp: new Date().toISOString() });
      break;

    case 'TORY_AGENT_STREAMING_START':
    case 'agent_streaming_start':
      _copilotStreaming = true;
      _copilotMessages.push({ role: 'ai', content: '', _streaming: true });
      refreshChatDisplay();
      break;

    case 'TORY_AGENT_STREAMING_TOKEN':
    case 'agent_token':
    case 'token':
      if (_copilotMessages.length > 0) {
        const last = _copilotMessages[_copilotMessages.length - 1];
        if (last._streaming) {
          last.content += (data.token || data.content || '');
          refreshChatDisplay();
        }
      }
      break;

    case 'TORY_AGENT_STREAMING_END':
    case 'agent_streaming_end':
      _copilotStreaming = false;
      if (_copilotMessages.length > 0) {
        const last = _copilotMessages[_copilotMessages.length - 1];
        delete last._streaming;
      }
      refreshChatDisplay();
      break;

    case 'agent_complete':
    case 'TORY_AGENT_COMPLETE':
    case 'TORY_AGENT_COMPLETED':
      _copilotStreaming = false;
      appendChatMessage('ai', data.summary || 'Processing complete.');
      // Refresh sessions + user detail
      const tw = getState().toryWorkspace;
      if (tw.selectedUserId) {
        loadUserDetail(tw.selectedUserId);
      }
      break;

    case 'agent_error':
    case 'TORY_AGENT_ERROR':
      _copilotStreaming = false;
      appendChatMessage('ai', `Error: ${data.error || data.message || 'Unknown error'}`);
      break;

    case 'ws_connected':
      _copilotWsConnected = true;
      updateCopilotWsStatus(true);
      break;

    case 'ws_disconnected':
      _copilotWsConnected = false;
      updateCopilotWsStatus(false);
      break;

    default:
      break;
  }
}

function appendChatMessage(role, content) {
  _copilotMessages.push({ role, content });
  const chatMessagesEl = document.getElementById('tw-chat-messages');
  if (!chatMessagesEl) return;
  renderChatMessageEl(chatMessagesEl, role, content);
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function renderChatMessageEl(container, role, content) {
  const msg = h('div', { class: `tw-chat-message ${role}` });

  if (role === 'system') {
    msg.innerHTML = `<span class="tw-chat-system">${esc(content)}</span>`;
    container.appendChild(msg);
    return;
  }

  const avatar = h('div', { class: `tw-chat-avatar ${role}` });
  avatar.textContent = role === 'ai' ? 'AI' : 'You';

  const bubble = h('div', { class: 'tw-chat-bubble' });
  if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });
    bubble.innerHTML = marked.parse(content);
  } else {
    bubble.textContent = content;
  }

  msg.appendChild(avatar);
  msg.appendChild(bubble);
  container.appendChild(msg);
}

function renderStreamingIndicator(container) {
  const indicator = h('div', { class: 'tw-chat-message ai', id: 'tw-streaming-indicator' });
  indicator.innerHTML = `
    <div class="tw-chat-avatar ai">AI</div>
    <div class="tw-chat-bubble tw-chat-streaming">
      <span class="tw-typing-dots"><span>.</span><span>.</span><span>.</span></span>
    </div>
  `;
  container.appendChild(indicator);
}

function refreshChatDisplay() {
  const chatMessagesEl = document.getElementById('tw-chat-messages');
  if (!chatMessagesEl) return;
  chatMessagesEl.innerHTML = '';
  for (const msg of _copilotMessages) {
    renderChatMessageEl(chatMessagesEl, msg.role, msg.content);
  }
  if (_copilotStreaming) {
    renderStreamingIndicator(chatMessagesEl);
  }
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function updateCopilotWsStatus(connected) {
  const el = document.getElementById('tw-copilot-ws-status');
  if (!el) return;
  el.innerHTML = connected
    ? '<span class="tw-ws-dot connected"></span> Connected'
    : '<span class="tw-ws-dot"></span> Reconnecting...';
}

function getUserNameFromState() {
  const tw = getState().toryWorkspace;
  const detail = tw.selectedUserDetail;
  if (!detail) return 'User';
  const profile = detail.learner?.profile || detail.learner || {};
  const parts = [profile.first_name, profile.last_name].filter(Boolean);
  return parts.length > 0 ? parts.join(' ') : profile.email || `User ${tw.selectedUserId}`;
}

async function sendChatMessage() {
  const textarea = document.getElementById('tw-chat-textarea');
  if (!textarea) return;
  const text = textarea.value.trim();
  if (!text) return;

  textarea.value = '';
  textarea.style.height = 'auto';

  // Show user message
  appendChatMessage('human', text);

  const tw = getState().toryWorkspace;
  const sessions = tw.agentSessions || [];
  if (sessions.length === 0 || !tw.selectedUserId) {
    appendChatMessage('ai', 'No active session. Please process this user first.');
    return;
  }

  const sessionId = _copilotSessionId || sessions[0].id;

  // Send via WebSocket if connected (uses WebSocketManager from api.js)
  sendToryAgentMessage({ type: 'message', text });

  // Also POST as fallback (server handles dedup)
  try {
    await api.chatWithToryAgent(tw.selectedUserId, sessionId, text);
  } catch (err) {
    // WS send may have worked, only show error if both fail
    if (!_copilotWsConnected) {
      appendChatMessage('ai', `Failed to send message: ${err.message}`);
    }
  }
}

function openSessionInCopilot(sessionId) {
  // Make sure right drawer is open
  const layout = document.querySelector('.tw-layout');
  if (layout && layout.classList.contains('right-collapsed')) {
    toggleRightDrawer();
  }

  // Switch copilot to this session
  _copilotSessionId = sessionId;
  _copilotMessages = [];
  _copilotStreaming = false;
  renderCopilotDrawer();
}

// ── User Processing ─────────────────────────────────────────────────────────

async function processUser(userId) {
  try {
    showToast('Processing user...', 'info');
    const result = await api.processToryUser(userId);
    showToast(`Agent spawned! Session: ${result.session_id.substring(0, 8)}...`, 'success');

    // Reload sessions + open copilot
    await loadAgentSessions(userId);

    // Make sure right drawer is open
    const layout = document.querySelector('.tw-layout');
    if (layout && layout.classList.contains('right-collapsed')) {
      toggleRightDrawer();
    }
  } catch (err) {
    showToast(`Process failed: ${err.message}`, 'error');
  }
}

async function batchProcess() {
  const tw = getState().toryWorkspace;
  const userIds = [...tw.batchSelected];
  if (userIds.length === 0) return;

  try {
    showToast(`Batch processing ${userIds.length} users...`, 'info');
    const result = await api.batchProcessTory({ user_ids: userIds });
    showToast(`Batch started: ${result.count} agents spawned`, 'success');

    // Clear selection
    setState({ toryWorkspace: { ...getState().toryWorkspace, batchSelected: new Set() } });
    renderBatchButton();
    renderPeopleList();
  } catch (err) {
    showToast(`Batch process failed: ${err.message}`, 'error');
  }
}

// ── Drawer Toggles ──────────────────────────────────────────────────────────

function toggleLeftDrawer() {
  const layout = document.querySelector('.tw-layout');
  const btn = document.getElementById('tw-toggle-left');
  if (!layout) return;

  layout.classList.toggle('left-collapsed');
  const collapsed = layout.classList.contains('left-collapsed');

  if (btn) {
    btn.classList.toggle('active', !collapsed);
    btn.innerHTML = collapsed ? '&#9654; People' : '&#9664; People';
  }

  const tw = getState().toryWorkspace;
  setState({ toryWorkspace: { ...tw, leftOpen: !collapsed } });
}

function toggleRightDrawer() {
  const layout = document.querySelector('.tw-layout');
  const btn = document.getElementById('tw-toggle-right');
  if (!layout) return;

  layout.classList.toggle('right-collapsed');
  const collapsed = layout.classList.contains('right-collapsed');

  if (btn) {
    btn.classList.toggle('active', !collapsed);
    btn.innerHTML = collapsed ? 'AI Co-pilot &#9654;' : 'AI Co-pilot &#9654;';
  }

  const tw = getState().toryWorkspace;
  setState({ toryWorkspace: { ...tw, rightOpen: !collapsed } });
}

// ── Company Filter ──────────────────────────────────────────────────────────

function populateCompanyFilter(companies) {
  const select = document.getElementById('tw-filter-company');
  if (!select) return;

  // Preserve current value
  const current = select.value;
  select.innerHTML = '<option value="">All Companies</option>';

  for (const company of companies) {
    const opt = document.createElement('option');
    opt.value = company.id || company.client_id || '';
    opt.textContent = company.name || company.client_name || `Company ${company.id || ''}`;
    select.appendChild(opt);
  }

  if (current) select.value = current;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function getUserName(user) {
  const parts = [user.first_name, user.last_name].filter(Boolean);
  return parts.length > 0 ? parts.join(' ') : user.email || `User ${user.nx_user_id}`;
}

function getInitials(user) {
  const first = (user.first_name || '')[0] || '';
  const last = (user.last_name || '')[0] || '';
  return (first + last).toUpperCase() || '?';
}

function getUserStatus(user) {
  if (user.tory_status === 'processed' || user.has_path) return 'processed';
  if (user.tory_status === 'has_epp' || user.has_epp) return 'has_epp';
  return 'no_data';
}

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
