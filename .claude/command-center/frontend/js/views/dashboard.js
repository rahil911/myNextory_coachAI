// ==========================================================================
// DASHBOARD.JS — Overview Home View
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { renderApprovalCard } from '../components/approval-card.js';
import { h } from '../utils/dom.js';
import { timeAgo, compactNumber } from '../utils/format.js';

export function renderDashboard(root) {
  const container = h('div', { class: 'view-container' });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>Dashboard</h2>
      </div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="dash-refresh">Refresh</button>
      </div>
    </div>

    <div id="dash-alerts"></div>

    <div class="dash-actions">
      <button class="btn btn-primary" id="dash-new-thinktank">New Think Tank Session</button>
      <button class="btn btn-ghost" id="dash-view-kanban">View Kanban</button>
    </div>

    <div class="dash-grid" id="dash-grid">
      <div class="dash-card"><div class="dash-card-label">Active Agents</div><div class="dash-card-value" id="stat-agents">--</div><div class="dash-card-sub" id="stat-agents-sub"></div></div>
      <div class="dash-card"><div class="dash-card-label">Open Beads</div><div class="dash-card-value" id="stat-beads">--</div><div class="dash-card-sub" id="stat-beads-sub"></div></div>
      <div class="dash-card"><div class="dash-card-label">Epic Progress</div><div class="dash-card-value" id="stat-epics">--</div><div class="dash-card-sub" id="stat-epics-sub"></div></div>
      <div class="dash-card"><div class="dash-card-label">Events (24h)</div><div class="dash-card-value" id="stat-events">--</div><div class="dash-card-sub" id="stat-events-sub"></div></div>
    </div>

    <h3 style="margin: 24px 0 16px">Pending Approvals</h3>
    <div id="dash-approvals"></div>

    <h3 style="margin: 24px 0 16px">Recent Events</h3>
    <div id="dash-recent-events"></div>
  `;

  root.appendChild(container);

  // Quick actions
  container.querySelector('#dash-new-thinktank').addEventListener('click', () => {
    window.location.hash = 'thinktank';
  });
  container.querySelector('#dash-view-kanban').addEventListener('click', () => {
    window.location.hash = 'kanban';
  });
  container.querySelector('#dash-refresh').addEventListener('click', () => loadDashData());

  // Use cached state if fresh, otherwise fetch
  if (isFresh('dashboard')) {
    updateDashStats();
    renderDashApprovals();
    renderDashRecentEvents();
    checkAlerts();
  } else {
    document.querySelectorAll('.dash-card-value').forEach(el => el.textContent = '...');
    loadDashData();
  }

  // Subscribe to real-time updates
  subscribe('agents', () => updateDashStats());
  subscribe('approvals', () => renderDashApprovals());
  subscribe('events', () => renderDashRecentEvents());
}

async function loadDashData() {
  try {
    const [agents, beads, epics, events, approvalsData] = await Promise.all([
      api.getAgents().catch(() => []),
      api.getBeads().catch(() => []),
      api.getEpics().catch(() => []),
      api.getEvents({ limit: 20 }).catch(() => []),
      api.getApprovals().catch(() => ({ pending: [], history: [], pending_count: 0 })),
    ]);

    setState({ agents, beads, epics, events, approvals: approvalsData.pending || [] });
    markFetched('dashboard');
    markFetched('agents');
    markFetched('beads');
    markFetched('epics');
    markFetched('events');
    updateDashStats();
    renderDashApprovals();
    renderDashRecentEvents();
    checkAlerts();
  } catch (err) {
    showToast(`Failed to load dashboard: ${err.message}`, 'error');
  }
}

function updateDashStats() {
  const state = getState();
  const agents = state.agents || [];
  const beads = state.beads || [];
  const epics = state.epics || [];
  const events = state.events || [];

  const active = agents.filter(a => a.status === 'working' || a.status === 'spawning').length;
  const el = (id) => document.getElementById(id);

  if (el('stat-agents')) el('stat-agents').textContent = active;
  if (el('stat-agents-sub')) el('stat-agents-sub').textContent = `${agents.length} total`;

  const open = beads.filter(b => b.status !== 'done' && b.status !== 'closed').length;
  if (el('stat-beads')) el('stat-beads').textContent = open;
  if (el('stat-beads-sub')) el('stat-beads-sub').textContent = `${beads.length} total`;

  if (el('stat-epics')) el('stat-epics').textContent = epics.length;
  if (el('stat-events')) el('stat-events').textContent = events.length;
}

function renderDashApprovals() {
  const container = document.getElementById('dash-approvals');
  if (!container) return;
  const { approvals } = getState();
  container.innerHTML = '';
  if (!approvals || !approvals.length) {
    container.innerHTML = '<p class="caption">No pending approvals</p>';
    return;
  }
  approvals.forEach(a => container.appendChild(renderApprovalCard(a)));
}

function renderDashRecentEvents() {
  const container = document.getElementById('dash-recent-events');
  if (!container) return;
  const { events } = getState();
  if (!events || !events.length) {
    container.innerHTML = '<p class="caption">No recent events</p>';
    return;
  }
  const eventBadgeColor = (type) => {
    if (type === 'agent_gone' || type === 'agent_failed') return 'red';
    if (type === 'agent_spawned') return 'purple';
    if (type === 'status_change' || type === 'bead_moved') return 'yellow';
    return 'blue';
  };
  container.innerHTML = events.slice(0, 10).map(e => `
    <div class="flex items-center gap-3" style="padding:6px 0;border-bottom:1px solid var(--border)">
      <span class="badge badge-${eventBadgeColor(e.type)}">${e.type || 'event'}</span>
      <span style="font-size:13px;flex:1">${e.agent ? '<strong>' + e.agent + '</strong>: ' : ''}${e.detail || e.description || e.name || ''}</span>
      <span class="caption">${timeAgo(e.ts || e.timestamp)}</span>
    </div>
  `).join('');
}

function checkAlerts() {
  const container = document.getElementById('dash-alerts');
  if (!container) return;
  const { agents } = getState();
  const stale = (agents || []).filter(a => a.heartbeat_stale);
  if (stale.length > 0) {
    container.innerHTML = `
      <div class="dash-alert">
        <span class="dash-alert-icon">\u26A0</span>
        <span>${stale.length} agent(s) with stale heartbeats: ${stale.map(a => a.name).join(', ')}</span>
      </div>
    `;
  }
}
