// ==========================================================================
// TORY-WORKSPACE.JS — 3-Pane Split-View Path Builder
// Left: People list, Center: 4-tab panel, Right: AI Co-pilot
// ==========================================================================

import { getState, setState, subscribe, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';

// ── Constants ──────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 300;
const PAGE_SIZE = 50;

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
      <div class="tw-person-status ${status}"></div>
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
    case 'content':
      renderContentTab(contentEl);
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
  const profile = learner.profile || learner;
  const coach = learner.coach || null;

  const card = h('div', { class: 'tw-profile-card' });

  const initials = ((profile.first_name || '')[0] || '') + ((profile.last_name || '')[0] || '');
  const displayName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.email || `User ${getState().toryWorkspace.selectedUserId}`;

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

// ── Path Tab ────────────────────────────────────────────────────────────────

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

  const recs = pathData.recommendations || [];
  if (recs.length === 0) {
    el.innerHTML = `
      <div class="tw-placeholder">
        <div class="tw-placeholder-icon">&#128736;</div>
        <div class="tw-placeholder-text">Path is empty. Process this user to generate recommendations.</div>
      </div>
    `;
    return;
  }

  // Stats row
  const statsDiv = h('div', { class: 'tw-profile-stats', style: { marginBottom: '16px' } });
  statsDiv.innerHTML = `
    <div class="tw-profile-stat"><div class="tw-profile-stat-value">${recs.length}</div><div class="tw-profile-stat-label">Lessons</div></div>
    <div class="tw-profile-stat"><div class="tw-profile-stat-value">${recs.filter(r => r.is_discovery).length}</div><div class="tw-profile-stat-label">Discovery</div></div>
    <div class="tw-profile-stat"><div class="tw-profile-stat-value">${recs.filter(r => r.locked_by_coach).length}</div><div class="tw-profile-stat-label">Coach Locked</div></div>
  `;
  el.appendChild(statsDiv);

  // Lesson cards
  for (const rec of recs) {
    const card = h('div', { class: 'tw-profile-card', style: { marginBottom: '8px', padding: '12px 16px' } });

    let badges = '';
    if (rec.is_discovery) badges += '<span class="badge badge-purple">Discovery</span> ';
    if (rec.locked_by_coach) badges += '<span class="badge badge-yellow">Locked</span> ';
    if (rec.source && rec.source !== 'tory') badges += `<span class="badge badge-blue">${esc(rec.source)}</span> `;

    const score = Math.min(Math.round(rec.match_score || 0), 100);

    card.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:var(--font-size-xs);color:var(--text-tertiary)">#${rec.sequence}</span>
          <span style="font-weight:500;color:var(--text-primary)">${esc(rec.lesson_title || `Lesson ${rec.nx_lesson_id}`)}</span>
        </div>
        <div>${badges}</div>
      </div>
      ${rec.journey_title ? `<div style="font-size:var(--font-size-xs);color:var(--text-secondary);margin-bottom:4px">${esc(rec.journey_title)}</div>` : ''}
      ${rec.match_rationale ? `<div style="font-size:var(--font-size-xs);color:var(--text-tertiary);margin-bottom:4px">${esc(rec.match_rationale)}</div>` : ''}
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:var(--font-size-xs);color:var(--text-secondary)">Match ${score}%</span>
        <div style="flex:1;height:4px;background:var(--bg-4);border-radius:2px;overflow:hidden">
          <div style="width:${score}%;height:100%;background:var(--accent);border-radius:2px"></div>
        </div>
      </div>
    `;

    el.appendChild(card);
  }
}

// ── Content Tab ─────────────────────────────────────────────────────────────

function renderContentTab(el) {
  el.innerHTML = `
    <div class="tw-placeholder">
      <div class="tw-placeholder-icon">&#128218;</div>
      <div class="tw-placeholder-text">Content library — coming in a future update</div>
    </div>
  `;
}

// ── Agent Log Tab ───────────────────────────────────────────────────────────

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
  for (const session of sessions) {
    const card = h('div', { class: 'tw-profile-card', style: { marginBottom: '8px', padding: '12px 16px' } });

    const statusClass = session.status === 'completed' ? 'completed' : session.status === 'running' ? 'running' : 'error';

    card.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span class="tw-session-badge ${statusClass}">${esc(session.status)}</span>
        <span style="font-size:var(--font-size-xs);color:var(--text-tertiary)">${esc(session.created_at || '')}</span>
      </div>
      <div style="font-size:var(--font-size-xs);color:var(--text-secondary)">
        ${session.tool_call_count || 0} tool calls · ${(session.pipeline_steps || []).length} steps
      </div>
      ${session.error_message ? `<div style="font-size:var(--font-size-xs);color:var(--red);margin-top:4px">${esc(session.error_message)}</div>` : ''}
    `;

    // Click to view session detail in copilot
    card.style.cursor = 'pointer';
    card.addEventListener('click', () => openSessionInCopilot(session.id));

    el.appendChild(card);
  }
}

// ── Co-pilot Drawer ─────────────────────────────────────────────────────────

let _copilotWs = null;

function renderCopilotDrawer() {
  const tw = getState().toryWorkspace;
  const sessions = tw.agentSessions || [];
  const placeholder = document.getElementById('tw-right-placeholder');
  const chatMessages = document.getElementById('tw-chat-messages');
  const chatInput = document.getElementById('tw-chat-input');
  const sessionMeta = document.getElementById('tw-session-meta');
  const sessionStatus = document.getElementById('tw-session-status');

  if (sessions.length === 0 || !tw.selectedUserId) {
    // Show placeholder
    if (placeholder) placeholder.style.display = '';
    if (chatMessages) chatMessages.style.display = 'none';
    if (chatInput) chatInput.style.display = 'none';
    if (sessionMeta) sessionMeta.style.display = 'none';
    if (sessionStatus) sessionStatus.style.display = 'none';
    return;
  }

  // Show latest session
  const latest = sessions[0];
  if (placeholder) placeholder.style.display = 'none';
  if (chatMessages) { chatMessages.style.display = ''; chatMessages.innerHTML = ''; }
  if (chatInput) chatInput.style.display = '';

  // Session meta
  if (sessionMeta) {
    sessionMeta.style.display = '';
    sessionMeta.innerHTML = `
      <span style="font-size:var(--font-size-xs);color:var(--text-secondary)">
        Session: ${esc(latest.id.substring(0, 8))}... · ${latest.tool_call_count || 0} tool calls
      </span>
    `;
  }
  if (sessionStatus) {
    sessionStatus.style.display = '';
    const cls = latest.status === 'completed' ? 'completed' : latest.status === 'running' ? 'running' : 'error';
    sessionStatus.className = `tw-session-badge ${cls}`;
    sessionStatus.textContent = latest.status;
  }

  // Add a welcome message
  appendChatMessage('ai', `I've processed this user. You can ask me questions about their profile, learning path, or request changes.`);

  // Connect WebSocket for this session
  connectCopilotWs(latest.id);
}

function appendChatMessage(role, content) {
  const chatMessages = document.getElementById('tw-chat-messages');
  if (!chatMessages) return;

  const msg = h('div', { class: `tw-chat-message ${role}` });

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
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function connectCopilotWs(sessionId) {
  if (_copilotWs) {
    _copilotWs.close();
    _copilotWs = null;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/ws/tory-agent?session=${sessionId}`;

  try {
    _copilotWs = new WebSocket(url);

    _copilotWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleCopilotMessage(data);
      } catch (err) {
        console.error('Copilot WS parse error:', err);
      }
    };

    _copilotWs.onclose = () => {
      _copilotWs = null;
    };

    _copilotWs.onerror = (err) => {
      console.error('Copilot WS error:', err);
    };
  } catch (err) {
    console.error('Failed to connect copilot WS:', err);
  }
}

function handleCopilotMessage(data) {
  switch (data.type) {
    case 'agent_message':
    case 'TORY_AGENT_MESSAGE':
      if (data.content) {
        appendChatMessage('ai', data.content);
      }
      break;
    case 'agent_tool_use':
    case 'TORY_AGENT_TOOL':
      // Show tool usage as system message
      appendChatMessage('ai', `_Using tool: ${data.tool || data.name || 'unknown'}_`);
      break;
    case 'agent_complete':
    case 'TORY_AGENT_COMPLETE':
      appendChatMessage('ai', data.summary || 'Processing complete.');
      // Refresh sessions + detail
      const tw = getState().toryWorkspace;
      if (tw.selectedUserId) {
        loadUserDetail(tw.selectedUserId);
      }
      break;
    case 'agent_error':
    case 'TORY_AGENT_ERROR':
      appendChatMessage('ai', `Error: ${data.error || data.message || 'Unknown error'}`);
      break;
    default:
      break;
  }
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

  const latest = sessions[0];

  // Send via WebSocket if connected
  if (_copilotWs && _copilotWs.readyState === WebSocket.OPEN) {
    _copilotWs.send(JSON.stringify({ type: 'message', text }));
    return;
  }

  // Fallback: REST API
  try {
    await api.chatWithToryAgent(tw.selectedUserId, latest.id, text);
  } catch (err) {
    appendChatMessage('ai', `Failed to send message: ${err.message}`);
  }
}

function openSessionInCopilot(sessionId) {
  // Make sure right drawer is open
  const layout = document.querySelector('.tw-layout');
  if (layout && layout.classList.contains('right-collapsed')) {
    toggleRightDrawer();
  }

  // Load this specific session's events
  const tw = getState().toryWorkspace;
  const session = tw.agentSessions.find(s => s.id === sessionId);
  if (session) {
    renderCopilotDrawer();
  }
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
