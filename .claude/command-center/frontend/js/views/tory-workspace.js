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

// ── Profile Tab ─────────────────────────────────────────────────────────────

function renderProfileTab(el, detail) {
  el.innerHTML = '';

  const learner = detail.learner || {};
  const rawProfile = learner.profile || {};
  const user = learner.user || {};
  const coach = learner.coach || null;

  // Merge user info into profile for display (profile lacks email/name)
  const tw = getState().toryWorkspace;
  const listUser = tw.users.find(u => u.nx_user_id === tw.selectedUserId) || {};
  const profile = {
    ...rawProfile,
    email: user.email || listUser.email || rawProfile.email || '',
    first_name: listUser.first_name || rawProfile.first_name || '',
    last_name: listUser.last_name || rawProfile.last_name || '',
    client_name: listUser.company_name || rawProfile.client_name || '',
  };

  // Parse strengths/gaps if stored as JSON strings
  if (typeof profile.strengths === 'string') {
    try { profile.strengths = JSON.parse(profile.strengths); } catch { profile.strengths = []; }
  }
  if (typeof profile.gaps === 'string') {
    try { profile.gaps = JSON.parse(profile.gaps); } catch { profile.gaps = []; }
  }

  const card = h('div', { class: 'tw-profile-card' });

  const initials = ((profile.first_name || '')[0] || '') + ((profile.last_name || '')[0] || '');
  const displayName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.email || `User ${tw.selectedUserId}`;

  let html = `
    <div class="tw-profile-header">
      <div class="tw-profile-avatar">${esc(initials) || '?'}</div>
      <div>
        <div class="tw-profile-name">${esc(displayName)}</div>
        <div class="tw-profile-email">${esc(profile.email || '')}</div>
        ${profile.client_name ? `<div class="tw-profile-company">${esc(profile.client_name)}</div>` : ''}
      </div>
    </div>
  `;

  // Coach
  if (coach) {
    const signalMap = { green: '#22c55e', yellow: '#f59e0b', red: '#ef4444' };
    const signalColor = signalMap[coach.compat_signal] || signalMap.green;
    html += `
      <div class="tw-coach-card">
        <div class="tw-coach-signal" style="color:${signalColor}">&#9679;</div>
        <div>
          <div class="tw-coach-name">Coach: ${esc(coach.coach_name || 'Assigned')}</div>
          <div class="tw-coach-compat">${esc(coach.compat_message || '')}</div>
        </div>
      </div>
    `;
  }

  // Narrative
  if (profile.profile_narrative) {
    html += `
      <div class="tw-profile-section">
        <div class="tw-profile-section-label">Narrative</div>
        <div class="tw-profile-narrative">${esc(profile.profile_narrative)}</div>
      </div>
    `;
  }

  // Strengths
  const strengths = profile.strengths || [];
  if (strengths.length > 0) {
    html += `
      <div class="tw-profile-section">
        <div class="tw-profile-section-label">Strengths</div>
        <div class="tw-trait-list">
          ${strengths.slice(0, 8).map(s => `<span class="tw-trait tw-trait-strength">${esc(s.trait)} ${Math.round(s.score)}</span>`).join('')}
        </div>
      </div>
    `;
  }

  // Gaps
  const gaps = profile.gaps || [];
  if (gaps.length > 0) {
    html += `
      <div class="tw-profile-section">
        <div class="tw-profile-section-label">Growth Areas</div>
        <div class="tw-trait-list">
          ${gaps.slice(0, 8).map(g => `<span class="tw-trait tw-trait-gap">${esc(g.trait)} ${Math.round(g.score)}</span>`).join('')}
        </div>
      </div>
    `;
  }

  // Learning style + stats
  html += `<div class="tw-profile-section"><div class="tw-profile-section-label">Info</div><div class="tw-profile-stats">`;
  if (profile.learning_style) {
    html += `<div class="tw-profile-stat"><div class="tw-profile-stat-value">${esc(profile.learning_style)}</div><div class="tw-profile-stat-label">Learning Style</div></div>`;
  }
  if (profile.confidence != null) {
    html += `<div class="tw-profile-stat"><div class="tw-profile-stat-value">${profile.confidence}%</div><div class="tw-profile-stat-label">Confidence</div></div>`;
  }
  if (profile.version != null) {
    html += `<div class="tw-profile-stat"><div class="tw-profile-stat-value">v${profile.version}</div><div class="tw-profile-stat-label">Version</div></div>`;
  }
  html += `</div></div>`;

  // Process button
  html += `
    <div class="tw-profile-section" style="text-align:center">
      <button class="btn btn-primary" id="tw-process-user">Process with AI</button>
    </div>
  `;

  card.innerHTML = html;
  el.appendChild(card);

  // Process button handler
  const processBtn = card.querySelector('#tw-process-user');
  if (processBtn) {
    processBtn.addEventListener('click', () => processUser(getState().toryWorkspace.selectedUserId));
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

  // Filter journeys
  const filtered = _contentJourneyFilter
    ? journeys.filter(j => j.journey_name === _contentJourneyFilter)
    : journeys;

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
    const header = document.createElement('div');
    header.className = 'tw-content-journey-header';
    header.innerHTML = `
      <span class="tw-content-journey-name">${esc(journey.journey_name)}</span>
      <span class="tw-content-journey-count">${lessons.length} lesson${lessons.length !== 1 ? 's' : ''}${pathMap.size > 0 ? ` · ${inPathCount} in path` : ''}</span>
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

  const card = document.createElement('div');
  card.className = `tw-content-card${isExpanded ? ' expanded' : ''}`;
  card.dataset.lessonId = lessonId;

  const confidence = Math.round(lesson.confidence || 0);
  const difficulty = lesson.difficulty || 3;
  const reviewStatus = lesson.review_status || 'pending';
  const learningStyle = lesson.learning_style || '';
  const slideCount = lesson.slide_count || 0;

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

  card.innerHTML = `
    ${matchOverlay}
    <div class="tw-content-card-title">${esc(lesson.lesson_name || 'Untitled')}</div>
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
  // Remove existing
  document.getElementById('tw-slide-modal')?.remove();

  const modal = document.createElement('div');
  modal.className = 'tw-slide-modal';
  modal.id = 'tw-slide-modal';

  if (_contentSlidesLoading) {
    modal.innerHTML = `
      <div class="tw-slide-overlay"></div>
      <div class="tw-slide-content">
        <div class="tw-slide-header">
          <span class="tw-slide-title">${esc(lessonName || 'Slides')}</span>
          <button class="tw-slide-close" id="tw-slide-close">&times;</button>
        </div>
        <div class="tw-loading" style="flex:1"><div class="tw-spinner"></div> Loading slides...</div>
      </div>
    `;
    document.body.appendChild(modal);
    wireSlideModalBase(modal);
    return;
  }

  const slides = _contentSlides || [];
  if (slides.length === 0) {
    modal.innerHTML = `
      <div class="tw-slide-overlay"></div>
      <div class="tw-slide-content">
        <div class="tw-slide-header">
          <span class="tw-slide-title">${esc(lessonName || 'Slides')}</span>
          <button class="tw-slide-close" id="tw-slide-close">&times;</button>
        </div>
        <div class="tw-placeholder" style="flex:1"><div class="tw-placeholder-text">No slides found</div></div>
      </div>
    `;
    document.body.appendChild(modal);
    wireSlideModalBase(modal);
    return;
  }

  const idx = Math.max(0, Math.min(_contentSlideIdx, slides.length - 1));
  const slide = slides[idx];
  const total = slides.length;

  // Parse slide content — API returns {type, content} not {slide_type, slide_content}
  let content = slide.content || slide.slide_content;
  if (typeof content === 'string') {
    try { content = JSON.parse(content); } catch { content = {}; }
  }
  content = content || {};

  const slideType = slide.type || slide.slide_type || 'unknown';
  // SAS URLs are embedded in content (content.background_image, content.audio, etc.)
  const urls = slide.media_urls || content;

  // Render slide content based on type
  const slideHtml = renderSlideContent(slideType, content, urls);

  // Dots navigation
  const dots = Array.from({ length: total }, (_, i) =>
    `<span class="tw-slide-dot${i === idx ? ' active' : ''}" data-idx="${i}"></span>`
  ).join('');

  modal.innerHTML = `
    <div class="tw-slide-overlay"></div>
    <div class="tw-slide-content">
      <div class="tw-slide-header">
        <span class="tw-slide-title">${esc(lessonName || 'Slides')}</span>
        <span class="tw-slide-counter">Slide ${idx + 1}/${total}</span>
        <button class="tw-slide-close" id="tw-slide-close">&times;</button>
      </div>
      <div class="tw-slide-body">
        ${slideHtml}
      </div>
      <div class="tw-slide-nav">
        <button class="tw-slide-arrow" id="tw-slide-prev" ${idx === 0 ? 'disabled' : ''}>&larr;</button>
        <div class="tw-slide-dots">${dots}</div>
        <button class="tw-slide-arrow" id="tw-slide-next" ${idx >= total - 1 ? 'disabled' : ''}>&rarr;</button>
      </div>
      <div class="tw-slide-type-badge">${esc(slideType)}</div>
    </div>
  `;

  document.body.appendChild(modal);
  wireSlideModalBase(modal);

  // Nav arrows
  modal.querySelector('#tw-slide-prev')?.addEventListener('click', () => {
    if (_contentSlideIdx > 0) {
      _contentSlideIdx--;
      renderSlideModal(lessonName);
    }
  });
  modal.querySelector('#tw-slide-next')?.addEventListener('click', () => {
    if (_contentSlideIdx < total - 1) {
      _contentSlideIdx++;
      renderSlideModal(lessonName);
    }
  });

  // Dot navigation
  modal.querySelectorAll('.tw-slide-dot').forEach(dot => {
    dot.addEventListener('click', () => {
      _contentSlideIdx = parseInt(dot.dataset.idx, 10);
      renderSlideModal(lessonName);
    });
  });

  // Keyboard navigation
  modal._keyHandler = (e) => {
    if (e.key === 'ArrowLeft' && _contentSlideIdx > 0) {
      _contentSlideIdx--;
      renderSlideModal(lessonName);
    } else if (e.key === 'ArrowRight' && _contentSlideIdx < total - 1) {
      _contentSlideIdx++;
      renderSlideModal(lessonName);
    } else if (e.key === 'Escape') {
      closeSlideViewer();
    }
  };
  document.addEventListener('keydown', modal._keyHandler);
}

function wireSlideModalBase(modal) {
  // Close button
  modal.querySelector('#tw-slide-close')?.addEventListener('click', closeSlideViewer);
  // Click overlay to close
  modal.querySelector('.tw-slide-overlay')?.addEventListener('click', closeSlideViewer);
}

function closeSlideViewer() {
  const modal = document.getElementById('tw-slide-modal');
  if (modal) {
    if (modal._keyHandler) document.removeEventListener('keydown', modal._keyHandler);
    modal.remove();
  }
  _contentSlides = null;
  _contentSlideIdx = 0;
}

function renderSlideContent(type, content, urls) {
  let html = '';

  // Title
  const title = content.slide_title || content.title || '';
  const text = content.content || content.content_title || content.text || content.body || '';

  // Background image
  const bgImage = urls.background_image || content.background_image || '';

  // Video
  const videoUrl = urls.video || content.video_url || '';

  // Audio
  const audioUrl = urls.audio || content.audio_url || '';

  if (type.startsWith('image') || (bgImage && !type.startsWith('video'))) {
    // Image slide
    if (bgImage) {
      html += `<div class="tw-slide-media"><img src="${esc(bgImage)}" alt="${esc(title)}" loading="lazy"></div>`;
    }
  } else if (type.startsWith('video') || videoUrl) {
    // Video slide
    if (videoUrl) {
      html += `<div class="tw-slide-media"><video controls preload="metadata" src="${esc(videoUrl)}"></video></div>`;
    } else if (bgImage) {
      html += `<div class="tw-slide-media"><img src="${esc(bgImage)}" alt="${esc(title)}" loading="lazy"></div>`;
    }
  }

  // Slide types with text content
  if (type === 'greetings' || type === 'take-away' || type === 'celebrate') {
    html += `<div class="tw-slide-text-content">`;
    if (title) html += `<h3 class="tw-slide-text-title">${esc(title)}</h3>`;
    if (text) html += `<p class="tw-slide-text-body">${esc(text)}</p>`;
    html += `</div>`;
  } else if (type.startsWith('question-answer') || type.includes('question')) {
    html += `<div class="tw-slide-text-content">`;
    if (title) html += `<h3 class="tw-slide-text-title">${esc(title)}</h3>`;
    if (text) html += `<p class="tw-slide-text-body">${esc(text)}</p>`;
    // Render answer options if present
    const options = content.options || content.answers || content.choices || [];
    if (options.length > 0) {
      html += '<div class="tw-slide-options">';
      for (const opt of options) {
        const optText = typeof opt === 'string' ? opt : (opt.text || opt.label || opt.answer || JSON.stringify(opt));
        html += `<div class="tw-slide-option">${esc(optText)}</div>`;
      }
      html += '</div>';
    }
    html += `</div>`;
  } else if (type.startsWith('select-') || type.startsWith('choose-')) {
    html += `<div class="tw-slide-text-content">`;
    if (title) html += `<h3 class="tw-slide-text-title">${esc(title)}</h3>`;
    if (text) html += `<p class="tw-slide-text-body">${esc(text)}</p>`;
    const choices = content.options || content.choices || [];
    if (choices.length > 0) {
      html += '<div class="tw-slide-options">';
      for (const ch of choices) {
        const chText = typeof ch === 'string' ? ch : (ch.text || ch.label || JSON.stringify(ch));
        html += `<div class="tw-slide-option">${esc(chText)}</div>`;
      }
      html += '</div>';
    }
    html += `</div>`;
  } else {
    // Default: show title + text, or formatted JSON
    html += `<div class="tw-slide-text-content">`;
    if (title) html += `<h3 class="tw-slide-text-title">${esc(title)}</h3>`;
    if (text) {
      html += `<p class="tw-slide-text-body">${esc(text)}</p>`;
    } else if (!bgImage && !videoUrl) {
      // No media and no text — show formatted JSON
      html += `<pre class="tw-slide-json">${esc(JSON.stringify(content, null, 2))}</pre>`;
    }
    html += `</div>`;
  }

  // Audio player
  if (audioUrl) {
    html += `<div class="tw-slide-audio"><audio controls preload="metadata" src="${esc(audioUrl)}"></audio></div>`;
  }

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
