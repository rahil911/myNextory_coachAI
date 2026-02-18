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
    if (_currentMode !== 'session') {
      container.innerHTML = '';
      _renderSessionView(container);
      _currentMode = 'session';
    } else {
      _updateSessionView(tt);
    }
  } else {
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

  // Approval gate (Phase 4+ only, not read-only)
  if (tt.phase >= 4 && !isReadOnly) {
    const gate = h('div', { class: 'approval-gate' });

    // Error panel (hidden by default)
    const errorPanel = h('div', { class: 'approval-error-panel', style: { display: 'none' } });
    errorPanel.id = 'approval-error-panel';

    // Dry-run preview panel (hidden by default)
    const previewPanel = h('div', { class: 'approval-preview-panel', style: { display: 'none' } });
    previewPanel.id = 'approval-preview-panel';

    // State machine: 'preview' (initial) or 'confirm' (after dry-run)
    let approvePhase = 'preview';
    let confirmedSessionId = null;

    const approveBtn = h('button', {
      class: 'approval-gate-btn',
      onClick: async () => {
        // Double-click protection: disable immediately
        approveBtn.disabled = true;
        errorPanel.style.display = 'none';

        try {
          const sessionId = getState().thinktank.sessionId;
          if (!sessionId) throw new Error('No session ID');

          if (approvePhase === 'preview') {
            // Step 1: Dry-run preview
            approveBtn.textContent = 'Approving...';
            previewPanel.style.display = 'none';

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

              // Transition to confirm phase
              approvePhase = 'confirm';
              confirmedSessionId = sessionId;
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

          } else if (approvePhase === 'confirm') {
            // Step 2: Actual build
            approveBtn.textContent = 'Starting build...';
            previewPanel.style.display = 'none';

            const result = await api.approveSpec(confirmedSessionId || sessionId);
            if (result.success) {
              approveBtn.textContent = 'Build queued! Agents dispatching...';
              approveBtn.classList.add('approved');
              approveBtn.style.animation = 'approval-burst 0.8s ease forwards';
              showToast('Build started!', 'success');
            } else {
              throw new Error(result.error || 'Unknown error');
            }
          }

        } catch (err) {
          // Reset to preview phase on error so user can retry
          approvePhase = 'preview';
          confirmedSessionId = null;
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
  _currentMode = null; // Force re-render
  setState({
    thinktank: { phase: 1, messages: [], specKit: {}, risks: [], sessionId: null, status: null }
  });
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
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
