// ==========================================================================
// THINKTANK.JS — Think Tank Split-View (Chat + Spec-Kit) + Session History
// ==========================================================================

import { getState, setState, subscribe } from '../state.js';
import { api, connectThinktankWs, disconnectThinktankWs, thinktankWs, parseDagLine, stripSpecKitBlocks } from '../api.js';
import { showToast } from '../components/toast.js';
import { renderPhaseStepper } from '../components/phase-stepper.js';
import { renderChatMessage, renderTypingIndicator, renderChatInput } from '../components/chat.js';
import { renderSpecKit } from '../components/spec-kit.js';
import { h } from '../utils/dom.js';
import { timeAgo } from '../utils/format.js';

let _currentMode = null; // 'history' | 'session'
let _dispatchPollTimer = null;

export function renderThinkTank(root) {
  const container = h('div', { class: 'thinktank-root', id: 'thinktank-root' });
  root.appendChild(container);

  // Initial render
  _doRender(container);

  // Re-render on state changes
  subscribe('thinktank', () => _doRender(container));
}

function _doRender(container) {
  const tt = getState().thinktank;

  if (tt.sessionId) {
    _ensureDispatchPolling(tt.sessionId, tt.phase >= 4);
    if (_currentMode !== 'session') {
      container.innerHTML = '';
      _renderSessionView(container);
      _currentMode = 'session';
    } else {
      _updateSessionView(tt);
    }
  } else {
    _stopDispatchPolling();
    if (_currentMode !== 'history') {
      container.innerHTML = '';
      _renderHistoryView(container);
      _currentMode = 'history';
    }
  }
}

// ── History View ──────────────────────────────────────────────────────────

async function _renderHistoryView(container) {
  const wrapper = h('div', { class: 'tt-history view-container' });

  // Header
  const header = h('div', { class: 'view-header' });
  const headerLeft = h('div', { class: 'view-header-left' });
  headerLeft.appendChild(h('h2', {}, 'Think Tank Sessions'));
  header.appendChild(headerLeft);

  const headerRight = h('div', { class: 'view-header-right' });
  const newBtn = h('button', { class: 'btn btn-primary', onClick: _startNewSession });
  newBtn.textContent = '+ New Session';
  headerRight.appendChild(newBtn);
  header.appendChild(headerRight);
  wrapper.appendChild(header);

  // Session list container
  const list = h('div', { class: 'tt-session-list', id: 'tt-session-list' });
  list.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-tertiary)">Loading sessions...</div>';
  wrapper.appendChild(list);
  container.appendChild(wrapper);

  // Fetch history
  try {
    const sessions = await api.getHistory();
    list.innerHTML = '';

    if (!sessions || sessions.length === 0) {
      list.innerHTML = `
        <div class="tt-empty-state">
          <div class="tt-empty-icon">&#9733;</div>
          <h3>No sessions yet</h3>
          <p>Start a brainstorming session to collaboratively design features with AI.</p>
        </div>
      `;
      return;
    }

    sessions.forEach(s => list.appendChild(_renderSessionCard(s)));
  } catch (err) {
    list.innerHTML = `<div style="text-align:center;padding:40px;color:var(--red)">Failed to load: ${err.message}</div>`;
  }
}

function _renderSessionCard(session) {
  const card = h('div', { class: 'tt-session-card' });

  const statusClass = {
    active: 'status-active', paused: 'status-paused',
    approved: 'status-approved', completed: 'status-completed',
  }[session.status] || 'status-paused';

  const phaseLabel = session.phase.charAt(0).toUpperCase() + session.phase.slice(1);

  card.innerHTML = `
    <div class="tt-card-main">
      <div class="tt-card-topic">${_escapeHtml(session.topic)}</div>
      <div class="tt-card-meta">
        <span class="tt-card-badge ${statusClass}">${session.status}</span>
        <span class="tt-card-badge tt-phase-badge">${phaseLabel}</span>
        <span class="tt-card-stat">${session.message_count} messages</span>
        <span class="tt-card-time">${timeAgo(session.updated_at)}</span>
      </div>
    </div>
    <div class="tt-card-actions"></div>
  `;

  const actions = card.querySelector('.tt-card-actions');

  const openBtn = h('button', {
    class: 'btn btn-sm',
    onClick: (e) => { e.stopPropagation(); _openSession(session.id); }
  });
  openBtn.textContent = session.status === 'active' ? 'Open' : 'Resume';
  actions.appendChild(openBtn);

  const delBtn = h('button', {
    class: 'btn btn-sm btn-danger',
    onClick: async (e) => {
      e.stopPropagation();
      if (!confirm(`Delete session "${session.topic}"?`)) return;
      try {
        await api.deleteSession(session.id);
        card.remove();
        showToast('Session deleted', 'info');
        // If list is now empty, show empty state
        const list = document.getElementById('tt-session-list');
        if (list && !list.querySelector('.tt-session-card')) {
          list.innerHTML = `
            <div class="tt-empty-state">
              <div class="tt-empty-icon">&#9733;</div>
              <h3>No sessions yet</h3>
              <p>Start a brainstorming session to collaboratively design features with AI.</p>
            </div>
          `;
        }
      } catch (err) {
        showToast(`Delete failed: ${err.message}`, 'error');
      }
    }
  });
  delBtn.textContent = 'Delete';
  actions.appendChild(delBtn);

  card.addEventListener('click', () => _openSession(session.id));
  return card;
}

// ── Session Open / Create ─────────────────────────────────────────────────

async function _openSession(sessionId) {
  try {
    const session = await api.resumeSession(sessionId);
    const phaseMap = { listen: 1, explore: 2, scope: 3, confirm: 4, building: 5, complete: 6 };

    const messages = (session.messages || [])
      .filter(m => m.role !== 'system')
      .map(m => {
        const isAi = m.role === 'orchestrator';
        let content = m.content;
        let chips = [];

        if (isAi) {
          content = stripSpecKitBlocks(content);
          const dagResult = parseDagLine(content);
          content = dagResult.content;
          chips = dagResult.chips;
        }

        return {
          role: isAi ? 'ai' : m.role,
          content,
          streaming: false,
          chips,
        };
      });

    const specKit = {};
    if (session.spec_kit) {
      for (const [key, val] of Object.entries(session.spec_kit)) {
        if (val) specKit[key] = val;
      }
    }

    setState({
      thinktank: {
        phase: phaseMap[session.phase] || 1,
        messages,
        specKit,
        risks: [],
        sessionId: session.id,
        status: session.status,
        dispatchStatus: null,
        dispatchEvents: [],
        dispatchHealth: null,
      }
    });

    connectThinktankWs(session.id);
  } catch (err) {
    showToast(`Failed to open session: ${err.message}`, 'error');
  }
}

async function _startNewSession() {
  const topic = prompt('What do you want to brainstorm?');
  if (!topic || !topic.trim()) return;

  try {
    const session = await api.createSession({ topic: topic.trim() });
    setState({
      thinktank: {
        phase: 1,
        messages: [],
        specKit: {},
        risks: [],
        sessionId: session.id,
        status: 'active',
        dispatchStatus: null,
        dispatchEvents: [],
        dispatchHealth: null,
      }
    });
    connectThinktankWs(session.id);
  } catch (err) {
    showToast(`Failed to create session: ${err.message}`, 'error');
  }
}

// ── Session View (Chat + Spec-Kit) ────────────────────────────────────────

function _renderSessionView(container) {
  const tt = getState().thinktank;
  const isReadOnly = tt.status === 'completed' || tt.status === 'approved';

  const thinktankEl = h('div', { class: 'thinktank' });

  // Left: Chat Panel
  const chatPanel = h('div', { class: 'thinktank-chat', dataset: { phase: getPhaseId(tt.phase) } });

  // Back header
  const backHeader = h('div', { class: 'tt-back-header' });
  const backBtn = h('button', { class: 'tt-back-btn', onClick: _goToHistory });
  backBtn.innerHTML = '&#8592; Sessions';
  backHeader.appendChild(backBtn);
  chatPanel.appendChild(backHeader);

  // Phase stepper
  chatPanel.appendChild(renderPhaseStepper(tt.phase));

  // Messages
  const messagesArea = h('div', { class: 'chat-messages', id: 'tt-messages' });
  renderMessages(messagesArea, tt.messages);
  chatPanel.appendChild(messagesArea);

  // Chat input or read-only bar
  if (!isReadOnly) {
    chatPanel.appendChild(renderChatInput(async (text, images) => {
      const msg = { role: 'human', content: text, images: [], streaming: false };
      if (images && images.length) {
        for (const img of images) {
          try {
            const result = await api.uploadAttachment(img);
            msg.images.push(result.url);
          } catch (err) {
            showToast(`Image upload failed: ${err.message}`, 'error');
          }
        }
      }

      const newMessages = [...getState().thinktank.messages, msg];
      setState({ thinktank: { ...getState().thinktank, messages: newMessages } });

      const aiMsg = { role: 'ai', content: '', streaming: true, chips: [] };
      setState({
        thinktank: {
          ...getState().thinktank,
          messages: [...getState().thinktank.messages, aiMsg]
        }
      });

      if (thinktankWs) {
        thinktankWs.send({ type: 'message', text: text });
      } else {
        try {
          const sessionId = getState().thinktank.sessionId;
          if (sessionId) await api.sendMessage(sessionId, { text: text });
        } catch (err) {
          showToast(`Send failed: ${err.message}`, 'error');
        }
      }
    }));
  } else {
    const readOnlyBar = h('div', { class: 'tt-readonly-bar' });
    readOnlyBar.textContent = 'This session is read-only (completed)';
    chatPanel.appendChild(readOnlyBar);
  }

  // Right: Spec-Kit Panel
  const specPanel = h('div', { class: 'thinktank-speckit' });
  const specHeader = h('div', { class: 'speckit-header' });
  specHeader.innerHTML = '<span class="speckit-title">Spec-Kit</span>';
  if (isReadOnly) {
    const badge = h('span', { class: 'tt-card-badge status-completed', style: { fontSize: '11px', marginLeft: '8px' } });
    badge.textContent = 'Read-only';
    specHeader.appendChild(badge);
  }
  specPanel.appendChild(specHeader);

  const onEdit = isReadOnly ? null : (key, val) => {
    const sk = { ...getState().thinktank.specKit };
    sk[key] = val;
    setState({ thinktank: { ...getState().thinktank, specKit: sk } });
    showToast('Spec updated', 'info');
  };
  specPanel.appendChild(renderSpecKit(tt, onEdit));

  // Always show dispatch observability once flow reaches confirm+ or if dispatch has started
  if (tt.phase >= 4 || tt.dispatchStatus || (tt.dispatchEvents && tt.dispatchEvents.length)) {
    specPanel.appendChild(_renderDispatchVisibility(tt));
  }

  // Approval gate (Phase 4+ only, not read-only)
  if (tt.phase >= 4 && !isReadOnly) {
    const gate = h('div', { class: 'approval-gate' });

    // Error panel (hidden by default)
    const errorPanel = h('div', { class: 'approval-error-panel', style: { display: 'none' } });
    errorPanel.id = 'approval-error-panel';

    // Dry-run preview panel (hidden by default)
    const previewPanel = h('div', { class: 'approval-preview-panel', style: { display: 'none' } });
    previewPanel.id = 'approval-preview-panel';

    let awaitingConfirm = false;
    let confirmSessionId = null;

    const approveBtn = h('button', {
      class: 'approval-gate-btn',
      onClick: async () => {
        // Double-click protection: disable immediately
        approveBtn.disabled = true;
        errorPanel.style.display = 'none';

        try {
          const sessionId = confirmSessionId || getState().thinktank.sessionId;
          if (!sessionId) throw new Error('No session ID');

          if (awaitingConfirm) {
            approveBtn.textContent = 'Starting build...';
            previewPanel.style.display = 'none';

            const result = await api.approveSpec(sessionId);
            if (result.success) {
              awaitingConfirm = false;
              confirmSessionId = null;
              setState({ thinktank: { ...getState().thinktank, dispatchStatus: result } });
              approveBtn.textContent = 'Build queued! Agents dispatching...';
              approveBtn.classList.add('approved');
              approveBtn.style.animation = 'approval-burst 0.8s ease forwards';
              showToast('Build started!', 'success');
            } else {
              throw new Error(result.error || 'Unknown error');
            }
            return;
          }

          approveBtn.textContent = 'Approving...';
          previewPanel.style.display = 'none';

          // Step 1: Dry-run preview
          const preview = await api.approveSpec(sessionId, { dryRun: true });

          if (preview.dry_run && preview.preview) {
            // Show preview for user confirmation
            const tasks = preview.preview.tasks || [];
            previewPanel.innerHTML = `
              <h4 style="margin:0 0 8px">Build Plan Preview (${tasks.length} tasks)</h4>
              <ul style="margin:0;padding-left:20px;font-size:13px">
                ${tasks.map(t => `<li><strong>Phase ${t.phase}:</strong> ${_escapeHtml(t.title)} <em>(${t.suggested_agent || 'auto'})</em></li>`).join('')}
              </ul>
            `;
            previewPanel.style.display = 'block';

            // Change button to "Confirm Build" and keep a single click handler
            awaitingConfirm = true;
            confirmSessionId = sessionId;
            approveBtn.textContent = 'Confirm Build \u2192';
            approveBtn.disabled = false;
            return;
          }

          // No preview returned — proceed directly
          if (preview.success) {
            approveBtn.textContent = 'Build queued! Agents dispatching...';
            approveBtn.classList.add('approved');
            approveBtn.style.animation = 'approval-burst 0.8s ease forwards';
            showToast('Build started!', 'success');
          } else {
            throw new Error(preview.error || 'Unknown error');
          }

        } catch (err) {
          awaitingConfirm = false;
          confirmSessionId = null;
          _showApprovalError(errorPanel, approveBtn, err.message);
        }
      }
    });
    approveBtn.textContent = 'Approve & Start Building \u2192';

    const escapes = h('div', { class: 'approval-gate-escape' });

    const goBackLink = h('a', {
      href: '#',
      onClick: async (e) => {
        e.preventDefault();
        // Go back to scope phase via dedicated API
        const sessionId = getState().thinktank.sessionId;
        if (sessionId) {
          try {
            await api.setPhase(sessionId, 2); // 2 = SCOPE phase index
            showToast('Returned to Scope phase', 'info');
          } catch (err) {
            showToast(`Failed: ${err.message}`, 'error');
          }
        }
      }
    });
    goBackLink.textContent = 'Go Back to Scope';

    const saveDraftLink = h('a', {
      href: '#',
      onClick: async (e) => {
        e.preventDefault();
        const sessionId = getState().thinktank.sessionId;
        if (sessionId) {
          try {
            await api.saveAsDraft(sessionId);
            showToast('Session saved as draft', 'info');
            _goToHistory();
          } catch (err) {
            showToast(`Failed to save: ${err.message}`, 'error');
          }
        }
      }
    });
    saveDraftLink.textContent = 'Save as Draft';

    escapes.appendChild(goBackLink);
    escapes.appendChild(document.createTextNode(' '));
    escapes.appendChild(saveDraftLink);

    const pauseNote = h('p', { style: { textAlign: 'center', fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '8px' } });
    pauseNote.textContent = 'You can pause the build at any time.';

    gate.appendChild(errorPanel);
    gate.appendChild(previewPanel);
    gate.appendChild(approveBtn);
    gate.appendChild(escapes);
    gate.appendChild(pauseNote);
    specPanel.appendChild(gate);

    // Check dispatch health on render — disable button if not ready
    api.checkDispatchHealth().then(health => {
      setState({ thinktank: { ...getState().thinktank, dispatchHealth: health } });
      if (!health.ready) {
        approveBtn.disabled = true;
        approveBtn.title = `Missing: ${health.missing.join(', ')}`;
        approveBtn.textContent = `Cannot build (missing: ${health.missing.join(', ')})`;
      }
    }).catch(() => {});
  }

  thinktankEl.appendChild(chatPanel);
  thinktankEl.appendChild(specPanel);
  container.appendChild(thinktankEl);

  // D/A/G keyboard shortcuts
  document.removeEventListener('keydown', _dagHandler);
  document.addEventListener('keydown', _dagHandler);
}

function _updateSessionView(tt) {
  const msgArea = document.getElementById('tt-messages');
  if (msgArea) renderMessages(msgArea, tt.messages);

  const chatEl = document.querySelector('.thinktank-chat');
  if (chatEl) {
    chatEl.dataset.phase = getPhaseId(tt.phase);
    const stepper = chatEl.querySelector('.phase-stepper');
    if (stepper) stepper.replaceWith(renderPhaseStepper(tt.phase));
  }
}

function _goToHistory() {
  disconnectThinktankWs();
  document.removeEventListener('keydown', _dagHandler);
  _stopDispatchPolling();
  _currentMode = null; // Force re-render
  setState({
    thinktank: {
      phase: 1,
      messages: [],
      specKit: {},
      risks: [],
      sessionId: null,
      status: null,
      dispatchStatus: null,
      dispatchEvents: [],
      dispatchHealth: null,
    }
  });
}

function _ensureDispatchPolling(sessionId, shouldPoll) {
  if (!shouldPoll || !sessionId) {
    _stopDispatchPolling();
    return;
  }

  const activeSession = _dispatchPollTimer?.sessionId;
  if (activeSession === sessionId) return;

  _stopDispatchPolling();

  const poll = async () => {
    try {
      const status = await api.getDispatchStatus(sessionId);
      if (status && status.status && status.status !== 'not_dispatched') {
        const state = getState();
        if (state.thinktank.sessionId !== sessionId) return;

        const events = [
          ...(state.thinktank.dispatchEvents || []),
          { ts: new Date().toISOString(), type: 'DISPATCH_SNAPSHOT', payload: status },
        ].slice(-30);

        setState({
          thinktank: {
            ...state.thinktank,
            dispatchStatus: status,
            dispatchEvents: events,
            dispatchHealth: status.health || state.thinktank.dispatchHealth,
          },
        });
      }
    } catch {
      // Best-effort polling; websocket remains primary channel.
    }
  };

  poll();
  const timerId = setInterval(poll, 5000);
  _dispatchPollTimer = { sessionId, timerId };
}

function _stopDispatchPolling() {
  if (_dispatchPollTimer?.timerId) {
    clearInterval(_dispatchPollTimer.timerId);
  }
  _dispatchPollTimer = null;
}

function _renderDispatchVisibility(tt) {
  const panel = h('div', { class: 'dispatch-visibility' });
  const status = tt.dispatchStatus || {};
  const total = Number(status.total || 0);
  const completed = Number(status.completed || 0);
  const failed = Number(status.failed || 0);
  const running = Number(status.running || 0);
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  panel.innerHTML = `
    <div class="dispatch-visibility-header">
      <span>Build Control Tower</span>
      <span class="dispatch-status-pill">${_escapeHtml(status.status || 'not_dispatched')}</span>
    </div>
    <div class="dispatch-visibility-grid">
      <div><strong>${completed}</strong><label>Completed</label></div>
      <div><strong>${running}</strong><label>Running</label></div>
      <div><strong>${failed}</strong><label>Failed</label></div>
      <div><strong>${total}</strong><label>Total</label></div>
    </div>
    <div class="dispatch-progress-bar"><span style="width:${pct}%"></span></div>
    <div class="dispatch-progress-text">Progress: ${pct}%</div>
  `;

  // Per-task breakdown table
  const tasks = status.tasks || [];
  if (tasks.length > 0) {
    const tableWrap = h('div', { class: 'dispatch-task-table' });
    tableWrap.innerHTML = `
      <div class="dispatch-feed-title">Task Breakdown</div>
      <table class="dt-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Agent</th>
            <th>Status</th>
            <th>Elapsed</th>
            <th>Retries</th>
          </tr>
        </thead>
        <tbody>
          ${tasks.map(t => {
            const scores = t.assignment_scores || {};
            const chosen = scores.chosen || '';
            const allScores = scores.scores || {};
            const scoreLines = Object.entries(allScores)
              .sort((a, b) => (b[1].score || 0) - (a[1].score || 0))
              .slice(0, 5)
              .map(([a, s]) => `${a}: ${s.score}`)
              .join('\n');
            const agentTitle = scoreLines ? `Assignment scores:\n${scoreLines}` : '';
            return `
            <tr class="dt-row dt-status-${t.status}">
              <td class="dt-cell-title" title="${_escapeHtml(t.bead_id || '')}">${_escapeHtml(t.title || 'Untitled')}</td>
              <td title="${_escapeHtml(agentTitle)}">${_escapeHtml(t.agent || 'unassigned')}</td>
              <td><span class="dt-status-badge dt-badge-${t.status}">${_escapeHtml(t.status || 'unknown')}</span></td>
              <td>${t.elapsed_s != null ? _formatElapsed(t.elapsed_s) : '-'}</td>
              <td>${t.retry_count || 0}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    `;
    panel.appendChild(tableWrap);
  }

  // Health checks (refreshed every poll cycle)
  const health = tt.dispatchHealth;
  if (health) {
    const healthEl = h('div', { class: 'dispatch-health' });
    const checks = Object.entries(health.checks || {});
    healthEl.innerHTML = `
      <div class="dispatch-health-title">Readiness</div>
      <ul>${checks.map(([k, ok]) => `<li>${ok ? '✅' : '❌'} ${_escapeHtml(k)}</li>`).join('')}</ul>
    `;
    panel.appendChild(healthEl);
  }

  // Token usage / cost estimate
  const tokenUsage = status.token_usage;
  if (tokenUsage && (tokenUsage.input || tokenUsage.output)) {
    const input = tokenUsage.input || 0;
    const output = tokenUsage.output || 0;
    const estCost = ((input * 3 + output * 15) / 1_000_000).toFixed(3);
    const costEl = h('div', { class: 'dispatch-health' });
    costEl.innerHTML = `
      <div class="dispatch-health-title">Token Usage</div>
      <div style="font-size:12px;padding:4px 0">
        Input: ${input.toLocaleString()} | Output: ${output.toLocaleString()}
        | Est. cost: ~$${estCost}
      </div>
    `;
    panel.appendChild(costEl);
  }

  // Live event feed
  const events = tt.dispatchEvents || [];
  const feed = h('div', { class: 'dispatch-feed' });
  const feedEvents = events.filter(ev => !(ev.payload && ev.payload.cycle));
  feed.innerHTML = `
    <div class="dispatch-feed-title">Live feed</div>
    ${feedEvents.length ? `<ul>${feedEvents.slice(-8).reverse().map(ev => `<li><span>${_escapeHtml((ev.type || '').toLowerCase())}</span><em>${_escapeHtml(_dispatchEventSummary(ev.payload || {}))}</em></li>`).join('')}</ul>` : '<p>No dispatch events yet. Use preview to inspect the plan before launch.</p>'}
  `;
  panel.appendChild(feed);

  return panel;
}

function _formatElapsed(seconds) {
  if (seconds == null) return '-';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function _dispatchEventSummary(payload) {
  if (payload.message) return payload.message;
  if (payload.status) return `status=${payload.status}`;
  if (payload.error) return payload.error;
  if (payload.topic) return payload.topic;
  return 'update received';
}

// ── Helpers ───────────────────────────────────────────────────────────────

function _dagHandler(e) {
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  const lastMsg = getState().thinktank.messages.filter(m => m.role === 'ai' && m.chips?.length).pop();
  if (!lastMsg || !lastMsg.chips) return;

  switch (e.key.toUpperCase()) {
    case 'D': if (lastMsg.chips[0]?.action) lastMsg.chips[0].action(); break;
    case 'A': if (lastMsg.chips[1]?.action) lastMsg.chips[1].action(); break;
    case 'G': if (lastMsg.chips[2]?.action) lastMsg.chips[2].action(); break;
  }
}

function renderMessages(container, messages) {
  container.innerHTML = '';
  (messages || []).forEach(msg => {
    container.appendChild(renderChatMessage(msg));
  });
  container.scrollTop = container.scrollHeight;
}

function getPhaseId(num) {
  return ['listen', 'explore', 'scope', 'confirm'][num - 1] || 'listen';
}

function _escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function _showApprovalError(errorPanel, approveBtn, message) {
  errorPanel.innerHTML = `
    <div style="background:var(--red-bg, #3a1a1a);border:1px solid var(--red, #ff4444);border-radius:8px;padding:12px;margin-bottom:12px">
      <strong style="color:var(--red, #ff4444)">Dispatch failed</strong>
      <p style="margin:4px 0 8px;font-size:13px;color:var(--text-secondary)">${_escapeHtml(message)}</p>
      <button class="btn btn-sm" onclick="this.closest('.approval-error-panel').style.display='none'">Dismiss</button>
    </div>
  `;
  errorPanel.style.display = 'block';
  approveBtn.textContent = 'Retry: Approve & Start Building \u2192';
  approveBtn.classList.remove('approved');
  approveBtn.disabled = false;
  showToast(`Approval failed: ${message}`, 'error');
}
