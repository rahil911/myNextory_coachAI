// ==========================================================================
// KANBAN.JS — Kanban Board with DnD, Context Menus, Table Toggle
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { showContextMenu } from '../components/context-menu.js';
import { openSidePanel } from '../components/sidebar.js';
import { h } from '../utils/dom.js';
import { timeAgo, stringToColor } from '../utils/format.js';

const COLUMNS = [
  { id: 'backlog',     title: 'Backlog',      color: '#8b949e', wipLimit: 0 },
  { id: 'ready',       title: 'Ready',        color: '#58a6ff', wipLimit: 0 },
  { id: 'in_progress', title: 'In Progress',  color: '#d29922', wipLimit: 5 },
  { id: 'in_review',   title: 'In Review',    color: '#bc8cff', wipLimit: 3 },
  { id: 'blocked',     title: 'Blocked',      color: '#f85149', wipLimit: 0 },
  { id: 'done',        title: 'Done',         color: '#3fb950', wipLimit: 0 },
];

let currentViewMode = 'kanban';
let draggedCard = null;

export function renderKanban(root) {
  const container = h('div', { class: 'view-container', style: { padding: '16px' } });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>Kanban Board</h2>
      </div>
      <div class="view-header-right">
        <div class="view-tabs">
          <button class="view-tab active" data-mode="kanban">Board</button>
          <button class="view-tab" data-mode="table">Table</button>
        </div>
      </div>
    </div>
    <div class="filter-bar" id="kanban-filters"></div>
    <div id="kanban-content"></div>
  `;

  root.appendChild(container);

  // View mode toggle
  container.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      container.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentViewMode = tab.dataset.mode;
      renderBoard();
    });
  });

  if (isFresh('beads') && getState().beads.length > 0) {
    renderBoard();
  } else {
    document.getElementById('kanban-content').innerHTML = '<div class="view-loading"><div class="view-loading-spinner"></div>Loading kanban...</div>';
    loadKanbanData();
  }
  subscribe('beads', () => renderBoard());
}

async function loadKanbanData() {
  try {
    const data = await api.getKanban();
    if (data && data.columns) {
      // Flatten columns into beads with column info
      const beads = [];
      for (const [colId, col] of Object.entries(data.columns)) {
        (col.beads || []).forEach(b => beads.push({ ...b, column: colId }));
      }
      setState({ beads });
      markFetched('beads');
    }
  } catch (err) {
    showToast(`Failed to load Kanban: ${err.message}`, 'error');
  }
  renderBoard();
}

function renderBoard() {
  const content = document.getElementById('kanban-content');
  if (!content) return;

  if (currentViewMode === 'table') {
    renderTableView(content);
  } else {
    renderKanbanBoard(content);
  }
}

function renderKanbanBoard(content) {
  const { beads } = getState();
  content.innerHTML = '';

  const board = h('div', { class: 'kanban-board' });

  // Find largest non-done column for bottleneck detection
  const columnCounts = {};
  COLUMNS.forEach(c => { columnCounts[c.id] = 0; });
  (beads || []).forEach(b => { if (columnCounts[b.column] !== undefined) columnCounts[b.column]++; });
  let maxNonDone = 0;
  let bottleneckCol = null;
  COLUMNS.forEach(c => {
    if (c.id !== 'done' && c.id !== 'backlog' && columnCounts[c.id] > maxNonDone) {
      maxNonDone = columnCounts[c.id];
      bottleneckCol = c.id;
    }
  });

  COLUMNS.forEach(col => {
    const colBeads = (beads || []).filter(b => b.column === col.id);
    const isBottleneck = col.id === bottleneckCol && maxNonDone > 2;
    const overWip = col.wipLimit > 0 && colBeads.length > col.wipLimit;

    const column = h('div', {
      class: `kanban-column ${isBottleneck ? 'bottleneck' : ''}`,
      dataset: { status: col.id }
    });

    column.innerHTML = `
      <div class="kanban-column-header">
        <span class="kanban-column-dot" style="background:${col.color}"></span>
        <span class="kanban-column-title">${col.title}</span>
        <span class="kanban-column-count">${colBeads.length}</span>
        ${col.wipLimit ? `<span class="kanban-column-wip ${overWip ? 'over-limit' : ''}">WIP ${colBeads.length}/${col.wipLimit}</span>` : ''}
      </div>
    `;

    const cardsContainer = h('div', { class: 'kanban-cards' });
    colBeads.forEach(bead => {
      cardsContainer.appendChild(renderKanbanCard(bead));
    });
    column.appendChild(cardsContainer);
    board.appendChild(column);

    // Drop zone handlers
    column.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      column.classList.add('drag-over');

      const afterEl = getDragAfterElement(cardsContainer, e.clientY);
      const placeholder = getOrCreatePlaceholder();
      if (afterEl) {
        cardsContainer.insertBefore(placeholder, afterEl);
      } else {
        cardsContainer.appendChild(placeholder);
      }
    });

    column.addEventListener('dragleave', (e) => {
      if (!column.contains(e.relatedTarget)) {
        column.classList.remove('drag-over');
        column.querySelector('.drop-placeholder')?.remove();
      }
    });

    column.addEventListener('drop', (e) => {
      e.preventDefault();
      column.classList.remove('drag-over');
      const placeholder = column.querySelector('.drop-placeholder');
      if (!draggedCard || !placeholder) return;

      cardsContainer.insertBefore(draggedCard, placeholder);
      placeholder.remove();

      const beadId = draggedCard.dataset.id;
      const newCol = col.id;
      moveBeadOptimistic(beadId, newCol);
    });
  });

  content.appendChild(board);
}

function renderKanbanCard(bead) {
  const card = h('div', {
    class: 'kanban-card',
    dataset: { id: bead.id, priority: bead.priority ?? 3 },
    draggable: 'true'
  });

  const agentColor = stringToColor(bead.assignee);

  card.innerHTML = `
    <div class="kanban-card-title">${bead.title || 'Untitled'}</div>
    <div class="kanban-card-meta">
      ${bead.assignee ? `<span class="kanban-card-agent" style="background:${agentColor}">${bead.assignee}</span>` : ''}
      <span class="kanban-card-type">${bead.type || 'task'}</span>
      ${bead.dep_count ? `<span class="kanban-card-deps">\u{1F517} ${bead.dep_count}</span>` : ''}
      <span class="kanban-card-time">${timeAgo(bead.created_at)}</span>
    </div>
    <div class="kanban-card-details">
      ${bead.epic ? `<div class="kanban-card-detail-row"><span class="kanban-card-detail-label">Epic</span><span>${bead.epic}</span></div>` : ''}
      ${bead.notes ? `<div class="kanban-card-detail-row"><span class="kanban-card-detail-label">Notes</span><span>${bead.notes}</span></div>` : ''}
      <div class="kanban-card-detail-row"><span class="kanban-card-detail-label">ID</span><span class="mono">${bead.id}</span></div>
    </div>
  `;

  // Drag handlers
  card.addEventListener('dragstart', (e) => {
    draggedCard = card;
    card.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', bead.id);
    requestAnimationFrame(() => { card.style.opacity = '0.3'; });
  });

  card.addEventListener('dragend', () => {
    card.classList.remove('dragging');
    card.style.opacity = '1';
    draggedCard = null;
    document.querySelectorAll('.drop-placeholder').forEach(p => p.remove());
    document.querySelectorAll('.drag-over').forEach(c => c.classList.remove('drag-over'));
  });

  // Click to open side panel
  card.addEventListener('click', (e) => {
    if (e.defaultPrevented) return;
    openBeadDetail(bead);
  });

  // Right-click context menu
  card.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    showContextMenu(e.clientX, e.clientY, [
      { label: 'Open Details', icon: '\u{1F4C4}', action: () => openBeadDetail(bead) },
      { label: 'Copy ID', icon: '\u{1F4CB}', action: () => { navigator.clipboard.writeText(bead.id); showToast('Copied'); } },
      { type: 'separator' },
      ...COLUMNS.filter(c => c.id !== bead.column).map(c => ({
        label: `Move to ${c.title}`, action: () => moveBeadOptimistic(bead.id, c.id)
      })),
    ]);
  });

  return card;
}

function renderTableView(content) {
  const { beads } = getState();
  content.innerHTML = `
    <table class="kanban-table">
      <thead><tr>
        <th style="width:4px"></th>
        <th>Title</th>
        <th>Status</th>
        <th>Agent</th>
        <th>Priority</th>
        <th>Type</th>
        <th>Created</th>
      </tr></thead>
      <tbody id="kanban-table-body"></tbody>
    </table>
  `;

  const tbody = content.querySelector('#kanban-table-body');
  (beads || []).forEach(b => {
    const col = COLUMNS.find(c => c.id === b.column);
    const row = document.createElement('tr');
    row.innerHTML = `
      <td class="priority-cell" style="background:var(--priority-${b.priority ?? 3})"></td>
      <td>${b.title || 'Untitled'}</td>
      <td><span class="badge badge-blue">${col ? col.title : b.column}</span></td>
      <td>${b.assignee || '--'}</td>
      <td>P${b.priority ?? '?'}</td>
      <td>${b.type || 'task'}</td>
      <td class="caption">${timeAgo(b.created_at)}</td>
    `;
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => openBeadDetail(b));
    tbody.appendChild(row);
  });
}

async function moveBeadOptimistic(beadId, newColumn) {
  try {
    await api.moveBead(beadId, newColumn);
    const { beads } = getState();
    setState({
      beads: beads.map(b => b.id === beadId ? { ...b, column: newColumn } : b)
    });
    showToast(`Moved to ${newColumn.replace('_', ' ')}`, 'success');
  } catch (err) {
    showToast(`Move failed: ${err.message}`, 'error');
    loadKanbanData(); // Reload to fix state
  }
}

function openBeadDetail(bead) {
  openSidePanel(`
    <h3>${bead.title || 'Untitled'}</h3>
    <div style="margin-top:16px">
      <div class="speckit-field"><div class="speckit-field-label">ID</div><div class="mono">${bead.id}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Status</div><div>${bead.column || bead.status}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Agent</div><div>${bead.assignee || 'Unassigned'}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Priority</div><div>P${bead.priority ?? '?'}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Type</div><div>${bead.type || 'task'}</div></div>
      ${bead.epic ? `<div class="speckit-field"><div class="speckit-field-label">Epic</div><div>${bead.epic}</div></div>` : ''}
      ${bead.notes ? `<div class="speckit-field"><div class="speckit-field-label">Notes</div><div>${bead.notes}</div></div>` : ''}
      <div class="speckit-field"><div class="speckit-field-label">Created</div><div>${bead.created_at || '--'}</div></div>
    </div>
    <div style="margin-top:24px">
      <h4>Add Comment</h4>
      <textarea id="bead-comment-input" placeholder="Type a comment..." style="margin-top:8px"></textarea>
      <button class="btn btn-primary btn-sm" id="bead-comment-submit" style="margin-top:8px">Comment</button>
    </div>
  `);

  const submitBtn = document.getElementById('bead-comment-submit');
  if (submitBtn) {
    submitBtn.addEventListener('click', async () => {
      const input = document.getElementById('bead-comment-input');
      const text = input?.value?.trim();
      if (!text) return;
      try {
        await api.commentBead(bead.id, text);
        input.value = '';
        showToast('Comment added', 'success');
      } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
      }
    });
  }
}

function getDragAfterElement(container, y) {
  const cards = [...container.querySelectorAll('.kanban-card:not(.dragging)')];
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

function getOrCreatePlaceholder() {
  let ph = document.querySelector('.drop-placeholder');
  if (!ph) {
    ph = document.createElement('div');
    ph.className = 'drop-placeholder';
  }
  return ph;
}
