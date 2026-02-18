// ==========================================================================
// APPROVALS.JS — Pending Approvals & Review History
// ==========================================================================

import { getState, subscribe } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo } from '../utils/format.js';

let _pendingData = [];
let _historyData = [];

export function renderApprovals(root) {
  const container = h('div', { class: 'view-container' });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>Approvals</h2>
        <span class="badge badge-yellow" id="approvals-count" style="margin-left:8px">0</span>
      </div>
      <div class="view-header-right">
        <button class="btn btn-primary btn-sm" id="approve-all-btn" style="display:none">Approve All</button>
        <button class="btn btn-ghost btn-sm" id="approvals-refresh">Refresh</button>
      </div>
    </div>

    <div id="approvals-pending"></div>

    <div style="margin-top:32px">
      <button class="btn btn-ghost btn-sm" id="history-toggle" style="display:none">
        <span id="history-toggle-icon">&#9654;</span> Review History
      </button>
      <div id="approvals-history" style="display:none;margin-top:12px"></div>
    </div>
  `;

  root.appendChild(container);

  container.querySelector('#approvals-refresh').addEventListener('click', loadApprovals);
  container.querySelector('#approve-all-btn').addEventListener('click', handleApproveAll);
  container.querySelector('#history-toggle').addEventListener('click', () => {
    const hist = document.getElementById('approvals-history');
    const icon = document.getElementById('history-toggle-icon');
    if (hist) {
      const open = hist.style.display !== 'none';
      hist.style.display = open ? 'none' : 'block';
      if (icon) icon.innerHTML = open ? '&#9654;' : '&#9660;';
    }
  });

  document.getElementById('approvals-pending').innerHTML = '<div class="view-loading"><div class="view-loading-spinner"></div>Loading approvals...</div>';
  loadApprovals();

  // Re-fetch when a WS approval event fires
  subscribe('_approvalTick', () => loadApprovals());
}

async function loadApprovals() {
  try {
    const data = await api.getApprovals();
    _pendingData = data.pending || [];
    _historyData = data.history || [];
    renderPending();
    renderHistory();
    updateBadge(_pendingData.length);
  } catch (err) {
    showToast(`Failed to load approvals: ${err.message}`, 'error');
  }
}

function updateBadge(count) {
  const badge = document.getElementById('approvals-count');
  if (badge) {
    badge.textContent = count;
    badge.style.display = count > 0 ? 'inline-block' : 'none';
  }
  const approveAllBtn = document.getElementById('approve-all-btn');
  if (approveAllBtn) approveAllBtn.style.display = count > 1 ? 'inline-block' : 'none';

  // Also update sidebar badge
  const navBadge = document.getElementById('approval-badge');
  if (navBadge) {
    navBadge.textContent = count;
    navBadge.style.display = count > 0 ? 'inline-flex' : 'none';
  }
}

function renderPending() {
  const container = document.getElementById('approvals-pending');
  if (!container) return;

  if (_pendingData.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:48px 0;color:var(--text-secondary)">
        <div style="font-size:32px;margin-bottom:12px">&#10003;</div>
        <p>No pending approvals</p>
      </div>
    `;
    return;
  }

  container.innerHTML = _pendingData.map(a => `
    <div class="dash-card" style="margin-bottom:12px;border-left:3px solid var(--yellow)" data-id="${a.id}">
      <div class="flex items-center gap-3" style="margin-bottom:8px">
        <span class="badge badge-yellow">${a.source || 'ownership'}</span>
        <span style="font-weight:600;color:var(--text-strong);flex:1">${a.file || 'Unknown file'}</span>
        <span class="caption">${timeAgo(a.proposed_at)}</span>
      </div>
      <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px">
        <div style="margin-bottom:4px"><strong>Agent:</strong> ${a.agent || 'unknown'}</div>
        <div style="margin-bottom:4px"><strong>Evidence:</strong> ${a.evidence || 'No evidence provided'}</div>
        ${a.reason ? `<div class="caption">${a.reason}</div>` : ''}
      </div>
      <div class="flex gap-2">
        <button class="btn btn-sm approve-btn" style="background:var(--green);color:#fff" data-id="${a.id}">Approve</button>
        <button class="btn btn-sm reject-btn" style="background:var(--red);color:#fff" data-id="${a.id}">Reject</button>
      </div>
    </div>
  `).join('');

  // Approve buttons
  container.querySelectorAll('.approve-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      btn.disabled = true;
      btn.textContent = 'Approving...';
      try {
        await api.approveItem(id);
        showToast(`Approved: ${id}`, 'success');
        loadApprovals();
      } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
        btn.disabled = false;
        btn.textContent = 'Approve';
      }
    });
  });

  // Reject buttons
  container.querySelectorAll('.reject-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      const reason = prompt('Rejection reason (optional):') ?? '';
      btn.disabled = true;
      btn.textContent = 'Rejecting...';
      try {
        await api.rejectItem(id, reason);
        showToast(`Rejected: ${id}`, 'warning');
        loadApprovals();
      } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
        btn.disabled = false;
        btn.textContent = 'Reject';
      }
    });
  });
}

function renderHistory() {
  const container = document.getElementById('approvals-history');
  const toggle = document.getElementById('history-toggle');
  if (!container) return;

  if (_historyData.length === 0) {
    if (toggle) toggle.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  if (toggle) toggle.style.display = 'inline-flex';

  container.innerHTML = _historyData.map(a => {
    const isApproved = a.status === 'approved';
    const borderColor = isApproved ? 'var(--green)' : 'var(--red)';
    const statusBadge = isApproved
      ? '<span class="badge badge-green">approved</span>'
      : '<span class="badge badge-red">rejected</span>';

    return `
      <div class="dash-card" style="margin-bottom:8px;border-left:3px solid ${borderColor};opacity:0.75">
        <div class="flex items-center gap-3">
          ${statusBadge}
          <span style="font-size:13px;flex:1">${a.file || 'Unknown'}</span>
          <span class="caption">${a.agent || ''}</span>
          <span class="caption">${timeAgo(a.reviewed_at || a.proposed_at)}</span>
        </div>
        ${a.reject_reason ? `<div class="caption" style="margin-top:4px;color:var(--red)">Reason: ${a.reject_reason}</div>` : ''}
      </div>
    `;
  }).join('');
}

async function handleApproveAll() {
  if (!confirm(`Approve all ${_pendingData.length} pending proposals?`)) return;
  try {
    const result = await api.approveAll();
    showToast(result.message || 'All approved', 'success');
    loadApprovals();
  } catch (err) {
    showToast(`Failed: ${err.message}`, 'error');
  }
}
