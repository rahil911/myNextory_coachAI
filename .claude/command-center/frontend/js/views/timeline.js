// ==========================================================================
// TIMELINE.JS — AgentOps-Style Waterfall Timeline
// ==========================================================================

import { getState, subscribe, setState } from '../state.js';
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
      <button class="filter-chip" data-type="agent-spawn">Agents</button>
      <button class="filter-chip" data-type="tool-call">Tools</button>
      <button class="filter-chip" data-type="bead">Beads</button>
      <button class="filter-chip" data-type="error">Errors</button>
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

  loadTimelineData();
  subscribe('events', () => renderEventList());
}

async function loadTimelineData() {
  try {
    const events = await api.getEvents({ limit: 200 });
    setState({ events: events || [] });
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
  const times = filtered.map(e => new Date(e.timestamp || 0).getTime()).filter(t => t > 0);
  const minTime = Math.min(...times, Date.now());
  const maxTime = Math.max(...times, Date.now());
  const range = maxTime - minTime || 1;

  container.innerHTML = filtered.map((e, i) => {
    const startPct = ((new Date(e.timestamp || 0).getTime() - minTime) / range) * 100;
    const widthPct = Math.max(2, ((e.duration || 100) / range) * 100);

    return `
      <div class="timeline-event" data-index="${i}">
        <span class="timeline-event-name">
          <span class="status-dot status-dot-${e.type === 'error' ? 'error' : 'running'}"></span>
          ${e.name || e.description || 'Event'}
        </span>
        <span class="timeline-event-type">
          <span class="badge badge-${e.type === 'error' ? 'red' : e.type === 'agent-spawn' ? 'purple' : 'blue'}">${e.type || 'event'}</span>
        </span>
        <div class="timeline-bar-container">
          <div class="timeline-bar type-${e.type || 'status'}" style="left:${startPct}%;width:${widthPct}%"></div>
        </div>
        <span class="timeline-event-duration">${formatDuration(e.duration)}</span>
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

  detail.innerHTML = `
    <div class="timeline-detail-title">${event.name || event.description || 'Event'}</div>

    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Type</div>
      <span class="badge badge-${event.type === 'error' ? 'red' : 'blue'}">${event.type}</span>
    </div>

    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Timestamp</div>
      <div class="timeline-detail-value">${event.timestamp || '--'} (${timeAgo(event.timestamp)})</div>
    </div>

    ${event.duration ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Duration</div>
      <div class="timeline-detail-value">${formatDuration(event.duration)}</div>
    </div>` : ''}

    ${event.agentName ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Agent</div>
      <div class="timeline-detail-value">${event.agentName}</div>
    </div>` : ''}

    ${event.data ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Data</div>
      <pre class="timeline-detail-code">${JSON.stringify(event.data, null, 2)}</pre>
    </div>` : ''}

    ${event.error ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Error</div>
      <pre class="timeline-detail-code" style="color:var(--red)">${event.error}</pre>
    </div>` : ''}
  `;
}
