// ==========================================================================
// THINKTANK.JS — Think Tank Split-View (Chat + Spec-Kit)
// ==========================================================================

import { getState, setState, subscribe } from '../state.js';
import { api, connectThinktankWs, thinktankWs } from '../api.js';
import { showToast } from '../components/toast.js';
import { renderPhaseStepper } from '../components/phase-stepper.js';
import { renderChatMessage, renderTypingIndicator, renderChatInput } from '../components/chat.js';
import { renderSpecKit } from '../components/spec-kit.js';
import { h } from '../utils/dom.js';

export function renderThinkTank(root) {
  const state = getState();
  const tt = state.thinktank;

  const container = h('div', { class: 'thinktank' });

  // Left: Chat Panel
  const chatPanel = h('div', { class: 'thinktank-chat', dataset: { phase: getPhaseId(tt.phase) } });

  // Phase stepper
  chatPanel.appendChild(renderPhaseStepper(tt.phase));

  // Messages area
  const messagesArea = h('div', { class: 'chat-messages', id: 'tt-messages' });
  renderMessages(messagesArea, tt.messages);
  chatPanel.appendChild(messagesArea);

  // Chat input
  const chatInput = renderChatInput(async (text, images) => {
    // Add human message to state
    const msg = { role: 'human', content: text, images: [], streaming: false };

    // Upload images if any
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

    // Add placeholder AI message
    const aiMsg = { role: 'ai', content: '', streaming: true, chips: [] };
    setState({
      thinktank: {
        ...getState().thinktank,
        messages: [...getState().thinktank.messages, aiMsg]
      }
    });

    // Send via WebSocket or REST
    if (thinktankWs) {
      thinktankWs.send({ type: 'message', content: text, images: msg.images });
    } else {
      try {
        const sessionId = getState().thinktank.sessionId;
        if (sessionId) {
          await api.sendMessage(sessionId, { content: text, images: msg.images });
        }
      } catch (err) {
        showToast(`Send failed: ${err.message}`, 'error');
      }
    }
  });
  chatPanel.appendChild(chatInput);

  // Right: Spec-Kit Panel
  const specPanel = h('div', { class: 'thinktank-speckit' });
  const specHeader = h('div', { class: 'speckit-header' });
  specHeader.innerHTML = '<span class="speckit-title">Spec-Kit</span>';
  specPanel.appendChild(specHeader);

  specPanel.appendChild(renderSpecKit(tt, (key, val) => {
    const sk = { ...getState().thinktank.specKit };
    sk[key] = val;
    setState({ thinktank: { ...getState().thinktank, specKit: sk } });
    showToast('Spec updated', 'info');
  }));

  // Approval gate (Phase 4 only)
  if (tt.phase >= 4) {
    const gate = h('div', { class: 'approval-gate' });
    const approveBtn = h('button', {
      class: 'approval-gate-btn',
      onClick: async () => {
        approveBtn.textContent = 'Building... You\'ll be notified when ready';
        approveBtn.classList.add('approved');
        approveBtn.style.animation = 'approval-burst 0.8s ease forwards';
        try {
          const sessionId = getState().thinktank.sessionId;
          if (sessionId) await api.approveSpec(sessionId);
          showToast('Spec approved -- build started!', 'success');
        } catch (err) {
          showToast(`Approval failed: ${err.message}`, 'error');
          approveBtn.textContent = 'Approve & Start Building \u2192';
          approveBtn.classList.remove('approved');
        }
      }
    });
    approveBtn.textContent = 'Approve & Start Building \u2192';

    const escapes = h('div', { class: 'approval-gate-escape' });
    escapes.innerHTML = `
      <a href="#" onclick="event.preventDefault()">Go Back to Scope</a>
      <a href="#" onclick="event.preventDefault()">Save as Draft</a>
    `;
    const pauseNote = h('p', { style: { textAlign: 'center', fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '8px' } });
    pauseNote.textContent = 'You can pause the build at any time.';

    gate.appendChild(approveBtn);
    gate.appendChild(escapes);
    gate.appendChild(pauseNote);
    specPanel.appendChild(gate);
  }

  container.appendChild(chatPanel);
  container.appendChild(specPanel);
  root.appendChild(container);

  // Initialize session if needed
  initThinktankSession();

  // Subscribe to thinktank state changes
  subscribe('thinktank', (tt) => {
    // Update messages
    const msgArea = document.getElementById('tt-messages');
    if (msgArea) renderMessages(msgArea, tt.messages);

    // Update phase stepper
    const chatEl = document.querySelector('.thinktank-chat');
    if (chatEl) {
      chatEl.dataset.phase = getPhaseId(tt.phase);
      const stepper = chatEl.querySelector('.phase-stepper');
      if (stepper) stepper.replaceWith(renderPhaseStepper(tt.phase));
    }
  });

  // D/A/G keyboard shortcuts
  const dagHandler = (e) => {
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
  };
  document.addEventListener('keydown', dagHandler);
}

async function initThinktankSession() {
  const state = getState();
  if (!state.thinktank.sessionId) {
    try {
      const session = await api.createSession({ name: `Session ${Date.now()}` });
      setState({
        thinktank: {
          ...state.thinktank,
          sessionId: session.id,
          phase: 1,
          messages: [{
            role: 'ai',
            content: 'Welcome to the Think Tank. Tell me what you\'re trying to build. What problem are you solving, and who is it for?',
            streaming: false,
            chips: [
              { label: 'Describe the problem', icon: '\u{1F50D}', action: () => {} },
              { label: 'Show a reference', icon: '\u{1F4CE}', action: () => {} },
              { label: 'Start from template', icon: '\u{1F4CB}', action: () => {} },
            ]
          }]
        }
      });
      connectThinktankWs(session.id);
    } catch (err) {
      showToast(`Failed to create session: ${err.message}`, 'error');
    }
  }
}

function renderMessages(container, messages) {
  container.innerHTML = '';
  (messages || []).forEach(msg => {
    const el = renderChatMessage(msg);
    if (el instanceof DocumentFragment) {
      container.appendChild(el);
    } else {
      container.appendChild(el);
    }
  });
  // Auto-scroll to bottom
  container.scrollTop = container.scrollHeight;
}

function getPhaseId(num) {
  return ['listen', 'explore', 'scope', 'confirm'][num - 1] || 'listen';
}
