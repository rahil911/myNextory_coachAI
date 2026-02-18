// ==========================================================================
// EPICS.JS — Epic Progress View
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';

export function renderEpics(root) {
  const container = h('div', { class: 'view-container' });
  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left"><h2>Epics</h2></div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="epics-refresh">Refresh</button>
      </div>
    </div>
    <div id="epics-list"></div>
  `;
  root.appendChild(container);

  container.querySelector('#epics-refresh').addEventListener('click', loadEpics);
  if (isFresh('epics') && getState().epics.length > 0) {
    renderEpicsList();
  } else {
    document.getElementById('epics-list').innerHTML = '<div class="view-loading"><div class="view-loading-spinner"></div>Loading epics...</div>';
    loadEpics();
  }
  subscribe('epics', () => renderEpicsList());
}

async function loadEpics() {
  try {
    const epics = await api.getEpics();
    setState({ epics: epics || [] });
    markFetched('epics');
    renderEpicsList();
  } catch (err) {
    showToast(`Failed to load epics: ${err.message}`, 'error');
  }
}

function renderEpicsList() {
  const list = document.getElementById('epics-list');
  if (!list) return;
  const { epics } = getState();

  list.innerHTML = (epics || []).map(e => {
    const total = e.total || 0;
    const completed = e.completed || 0;
    const inProgress = e.in_progress || 0;
    const blocked = e.blocked || 0;
    const open = e.open || 0;
    const pct = e.progress_pct || 0;
    const donePct = total ? (completed / total * 100) : 0;
    const wipPct = total ? (inProgress / total * 100) : 0;
    const blockedPct = total ? (blocked / total * 100) : 0;

    return `
      <div class="dash-card" style="margin-bottom:12px">
        <div class="flex items-center gap-3" style="margin-bottom:8px">
          <span style="font-weight:600;color:var(--text-strong);font-size:15px">${e.epic || 'Unnamed'}</span>
          <span class="caption" style="margin-left:auto">${Math.round(pct)}%</span>
        </div>
        <div class="epic-progress-bar" style="height:8px;border-radius:4px;background:var(--surface-2);overflow:hidden;display:flex;margin-bottom:12px">
          <div style="width:${donePct}%;background:var(--green);transition:width 0.3s"></div>
          <div style="width:${wipPct}%;background:var(--yellow);transition:width 0.3s"></div>
          <div style="width:${blockedPct}%;background:var(--red);transition:width 0.3s"></div>
        </div>
        <div class="flex gap-3" style="font-size:12px;flex-wrap:wrap">
          <span style="color:var(--green)">${completed} done</span>
          <span style="color:var(--yellow)">${inProgress} in progress</span>
          <span style="color:var(--red)">${blocked} blocked</span>
          <span style="color:var(--text-secondary)">${open} open</span>
          <span style="margin-left:auto;color:var(--text-secondary)">${total} total</span>
        </div>
        ${e.beads && e.beads.length ? `<div style="margin-top:8px;font-size:11px;color:var(--text-tertiary)" class="mono">${e.beads.join(', ')}</div>` : ''}
      </div>
    `;
  }).join('') || '<p class="caption">No epics defined</p>';
}
