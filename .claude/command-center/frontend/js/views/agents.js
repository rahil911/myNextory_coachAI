// ==========================================================================
// AGENTS.JS — Agent Detail View
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo, stringToColor } from '../utils/format.js';

export function renderAgents(root) {
  const container = h('div', { class: 'view-container' });
  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left"><h2>Agents</h2></div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="agents-refresh">Refresh</button>
      </div>
    </div>
    <div class="dash-grid" id="agents-grid"></div>
  `;
  root.appendChild(container);

  container.querySelector('#agents-refresh').addEventListener('click', loadAgents);
  if (isFresh('agents') && getState().agents.length > 0) {
    renderAgentGrid();
  } else {
    document.getElementById('agents-grid').innerHTML = '<div class="view-loading"><div class="view-loading-spinner"></div>Loading agents...</div>';
    loadAgents();
  }
  subscribe('agents', () => renderAgentGrid());
}

async function loadAgents() {
  try {
    const agents = await api.getAgents();
    setState({ agents: agents || [] });
    markFetched('agents');
    renderAgentGrid();
  } catch (err) {
    showToast(`Failed to load agents: ${err.message}`, 'error');
  }
}

function renderAgentGrid() {
  const grid = document.getElementById('agents-grid');
  if (!grid) return;

  const { agents } = getState();
  grid.innerHTML = (agents || []).map(a => {
    const statusClass = a.status === 'working' || a.status === 'spawning' ? 'running' : a.status === 'idle' ? 'idle' : a.status === 'failed' ? 'error' : 'dead';
    const hbText = a.heartbeat_stale ? 'STALE' : a.heartbeat_age_s != null ? `${a.heartbeat_age_s}s ago` : '';
    return `
      <div class="dash-card" style="cursor:pointer" data-agent-id="${a.name}">
        <div class="flex items-center gap-3" style="margin-bottom:12px">
          <span class="status-dot status-dot-${statusClass}"></span>
          <span style="font-weight:600;color:var(--text-strong)">${a.name}</span>
          <span class="badge badge-${statusClass === 'running' ? 'green' : statusClass === 'error' ? 'red' : 'gray'}" style="margin-left:auto">
            ${a.status || 'unknown'}
          </span>
        </div>
        <div style="font-size:12px;color:var(--text-secondary)">
          ${a.level ? `<div>Level: ${a.level}</div>` : ''}
          ${a.bead ? `<div>Current: ${a.bead}</div>` : ''}
          ${a.current_action ? `<div>${a.current_action}</div>` : ''}
          ${a.worktree ? `<div class="mono" style="font-size:11px">${a.worktree}</div>` : ''}
          ${hbText ? `<div>Heartbeat: ${hbText}</div>` : ''}
          ${a.errors > 0 ? `<div style="color:var(--red)">Errors: ${a.errors}</div>` : ''}
        </div>
        <div class="flex gap-2" style="margin-top:12px">
          <button class="btn btn-danger btn-sm kill-btn" data-id="${a.name}">Kill</button>
          <button class="btn btn-ghost btn-sm retry-btn" data-id="${a.name}">Retry</button>
        </div>
      </div>
    `;
  }).join('') || '<p class="caption">No agents registered</p>';

  // Action handlers
  grid.querySelectorAll('.kill-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('Kill this agent?')) return;
      try {
        await api.killAgent(btn.dataset.id);
        showToast('Agent killed', 'warning');
        loadAgents();
      } catch (err) { showToast(`Failed: ${err.message}`, 'error'); }
    });
  });

  grid.querySelectorAll('.retry-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      try {
        await api.retryAgent(btn.dataset.id);
        showToast('Agent retrying', 'success');
        loadAgents();
      } catch (err) { showToast(`Failed: ${err.message}`, 'error'); }
    });
  });
}
