// ==========================================================================
// EPICS.JS — Epic Progress View
// ==========================================================================

import { getState, subscribe } from '../state.js';
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
  loadEpics();
  subscribe('epics', () => renderEpicsList());
}

async function loadEpics() {
  try {
    const epics = await api.getEpics();
    const { setState } = await import('../state.js');
    setState({ epics: epics || [] });
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
    const total = (e.done || 0) + (e.wip || 0) + (e.blocked || 0) + (e.remaining || 0);
    const donePct = total ? ((e.done || 0) / total * 100) : 0;
    const wipPct = total ? ((e.wip || 0) / total * 100) : 0;
    const blockedPct = total ? ((e.blocked || 0) / total * 100) : 0;

    return `
      <div class="epic-card">
        <div class="epic-title">${e.name || e.id}</div>
        <div class="epic-progress-bar">
          <div class="epic-progress-done" style="width:${donePct}%"></div>
          <div class="epic-progress-wip" style="width:${wipPct}%"></div>
          <div class="epic-progress-blocked" style="width:${blockedPct}%"></div>
        </div>
        <div class="epic-meta">
          <span style="color:var(--green)">${e.done || 0} done</span>
          <span style="color:var(--yellow)">${e.wip || 0} WIP</span>
          <span style="color:var(--red)">${e.blocked || 0} blocked</span>
          <span>${e.remaining || 0} remaining</span>
          <span style="margin-left:auto">${total} total beads</span>
        </div>
      </div>
    `;
  }).join('') || '<p class="caption">No epics defined</p>';
}
