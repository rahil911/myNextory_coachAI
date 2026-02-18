// ==========================================================================
// TIMELINE.JS — AgentOps-Style Waterfall Timeline
// ==========================================================================

import { getState, subscribe, setState, isFresh, markFetched } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo, formatDuration } from '../utils/format.js';

export function renderTimeline(root) {
  const container = h('div', { class: 'view-container', style: { padding: '16px' } });
  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left"><h2>Timeline</h2></div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="tl-refresh">Refresh</button>
      </div>
    </div>
    <div class="filter-bar" id="tl-filters">
      <button class="filter-chip active" data-type="all">All</button>
      <button class="filter-chip" data-type="agent_spawned">Agents</button>
      <button class="filter-chip" data-type="status_change">Status</button>
      <button class="filter-chip" data-type="bead_moved">Beads</button>
      <button class="filter-chip" data-type="agent_gone">Gone</button>
    </div>
    <div class="timeline-container">
      <div class="timeline-list" id="tl-list">
        <div class="timeline-header-row">
          <span>Event</span><span>Type</span><span>Duration</span><span>Time</span>
        </div>
        <div id="tl-events"></div>
      </div>
      <div class="timeline-detail" id="tl-detail">
        <div class="timeline-detail-empty">Select an event to view details</div>
      </div>
    </div>
  `;
  root.appendChild(container);

  // Filter handlers
  container.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      renderEventList(chip.dataset.type);
    });
  });

  container.querySelector('#tl-refresh').addEventListener('click', loadTimelineData);

  if (isFresh('events') && getState().events.length > 0) {
    renderEventList();
  } else {
    document.getElementById('tl-events').innerHTML = '<div class="view-loading"><div class="view-loading-spinner"></div>Loading events...</div>';
    loadTimelineData();
  }
  subscribe('events', () => renderEventList());
}

async function loadTimelineData() {
  try {
    const events = await api.getEvents({ limit: 200 });
    setState({ events: events || [] });
    markFetched('events');
    renderEventList();
  } catch (err) {
    showToast(`Failed to load events: ${err.message}`, 'error');
  }
}

function renderEventList(filterType = 'all') {
  const container = document.getElementById('tl-events');
  if (!container) return;

  const { events } = getState();
  let filtered = events || [];
  if (filterType !== 'all') {
    filtered = filtered.filter(e => e.type === filterType);
  }

  // Calculate timeline boundaries for waterfall positioning
  const times = filtered.map(e => new Date(e.ts || e.timestamp || 0).getTime()).filter(t => t > 0);
  const minTime = Math.min(...times, Date.now());
  const maxTime = Math.max(...times, Date.now());
  const range = maxTime - minTime || 1;

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#8614;</div><div class="empty-state-text">No events to display</div></div>';
    return;
  }

  container.innerHTML = filtered.map((e, i) => {
    const ts = e.ts || e.timestamp || '';
    const startPct = ((new Date(ts || 0).getTime() - minTime) / range) * 100;
    const widthPct = Math.max(2, ((e.duration || 100) / range) * 100);
    const agentLabel = e.agent ? `<strong>${e.agent}</strong>: ` : '';
    const detail = e.detail || e.name || e.description || '';
    const typeBadgeColor = e.type === 'agent_gone' ? 'red' : e.type === 'agent_spawned' ? 'purple' : e.type === 'status_change' ? 'yellow' : 'blue';

    return `
      <div class="timeline-event" data-index="${i}">
        <span class="timeline-event-name">
          <span class="status-dot status-dot-${e.type === 'agent_gone' ? 'error' : 'running'}"></span>
          ${agentLabel}${detail}
        </span>
        <span class="timeline-event-type">
          <span class="badge badge-${typeBadgeColor}">${e.type || 'event'}</span>
        </span>
        <div class="timeline-bar-container">
          <div class="timeline-bar type-${e.type || 'status'}" style="left:${startPct}%;width:${widthPct}%"></div>
        </div>
        <span class="timeline-event-duration">${ts ? timeAgo(ts) : '--'}</span>
      </div>
    `;
  }).join('');

  // Click handlers
  container.querySelectorAll('.timeline-event').forEach(row => {
    row.addEventListener('click', () => {
      container.querySelectorAll('.timeline-event').forEach(r => r.classList.remove('selected'));
      row.classList.add('selected');
      const idx = parseInt(row.dataset.index);
      showEventDetail(filtered[idx]);
    });
  });
}

function showEventDetail(event) {
  const detail = document.getElementById('tl-detail');
  if (!detail || !event) return;

  const evTs = event.ts || event.timestamp || '';
  detail.innerHTML = `
    <div class="timeline-detail-title">${event.detail || event.name || event.description || 'Event'}</div>

    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Type</div>
      <span class="badge badge-${event.type === 'error' ? 'red' : 'blue'}">${event.type}</span>
    </div>

    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Timestamp</div>
      <div class="timeline-detail-value">${evTs || '--'} (${timeAgo(evTs)})</div>
    </div>

    ${event.duration ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Duration</div>
      <div class="timeline-detail-value">${formatDuration(event.duration)}</div>
    </div>` : ''}

    ${event.agent ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Agent</div>
      <div class="timeline-detail-value">${event.agent}</div>
    </div>` : ''}

    ${event.bead ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Bead</div>
      <div class="timeline-detail-value">${event.bead}</div>
    </div>` : ''}

    ${event.data ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Data</div>
      <pre class="timeline-detail-code">${JSON.stringify(event.data, null, 2)}</pre>
    </div>` : ''}
  `;
}
