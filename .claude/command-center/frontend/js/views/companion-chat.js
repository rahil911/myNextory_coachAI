// ==========================================================================
// COMPANION-CHAT.JS — Learner-Facing AI Companion Chat Interface
// Modern chat UI with mode detection, quick actions, backpack cards,
// progress bar, and markdown rendering.
// ==========================================================================

import { getState, setState, subscribe } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';

// ── Module state ──────────────────────────────────────────────────────────

let _sessionId = null;
let _userId = null;
let _messages = [];
let _currentMode = null;
let _progress = null;
let _wsConnection = null;
let _isTyping = false;
let _chatContainer = null;

// ── Mode display config ──────────────────────────────────────────────────

const MODE_CONFIG = {
  teach:     { label: 'Teaching',    color: '#4a9eff', icon: '\u{1F4D6}' },
  quiz:      { label: 'Quiz',        color: '#f59e0b', icon: '\u{2753}' },
  reflect:   { label: 'Reflecting',  color: '#8b5cf6', icon: '\u{1F4AD}' },
  prepare:   { label: 'Preparing',   color: '#10b981', icon: '\u{1F3AF}' },
  celebrate: { label: 'Celebrating', color: '#f43f5e', icon: '\u{1F389}' },
  connect:   { label: 'Connecting',  color: '#06b6d4', icon: '\u{1F517}' },
  escalate:  { label: 'Support',     color: '#ef4444', icon: '\u{2764}' },
};

// ── Render entry point ──────────────────────────────────────────────────

export function renderCompanionChat(root) {
  const container = h('div', { class: 'companion-layout' });
  container.innerHTML = `
    <!-- User Selector Bar -->
    <div class="companion-topbar">
      <div class="companion-topbar-left">
        <span class="companion-logo">T</span>
        <span class="companion-title">Tory Companion</span>
        <span class="companion-mode-pill" id="companion-mode" style="display:none"></span>
      </div>
      <div class="companion-topbar-center">
        <div class="companion-progress-bar" id="companion-progress-bar" style="display:none">
          <div class="companion-progress-fill" id="companion-progress-fill"></div>
          <span class="companion-progress-text" id="companion-progress-text"></span>
        </div>
      </div>
      <div class="companion-topbar-right">
        <div class="companion-user-select">
          <input type="number" id="companion-user-id" placeholder="User ID" min="1">
          <button class="companion-btn companion-btn-primary" id="companion-connect">Connect</button>
        </div>
      </div>
    </div>

    <!-- Main chat area -->
    <div class="companion-main">
      <!-- Chat messages -->
      <div class="companion-messages" id="companion-messages">
        <div class="companion-welcome" id="companion-welcome">
          <div class="companion-welcome-icon">T</div>
          <h2>Meet Tory, your learning companion</h2>
          <p>Enter a learner's User ID above to start a personalized conversation.</p>
          <p class="companion-welcome-sub">Tory knows your learning path, your personality profile, and your own words from lesson reflections.</p>
        </div>
      </div>

      <!-- Quick action pills -->
      <div class="companion-actions" id="companion-actions" style="display:none">
        <div class="companion-actions-scroll" id="companion-actions-scroll"></div>
      </div>

      <!-- Input area -->
      <div class="companion-input-area" id="companion-input-area" style="display:none">
        <div class="companion-input-wrapper">
          <textarea id="companion-textarea" placeholder="Ask Tory anything about your learning..." rows="1" maxlength="5000"></textarea>
          <button class="companion-send-btn" id="companion-send" disabled>
            <span class="companion-send-arrow">&uarr;</span>
          </button>
        </div>
        <div class="companion-input-hint">
          Press Enter to send, Shift+Enter for new line
        </div>
      </div>
    </div>
  `;

  root.appendChild(container);
  _chatContainer = container;

  // Wire events
  _wireEvents(container);
}

// ── Event wiring ─────────────────────────────────────────────────────────

function _wireEvents(container) {
  // Connect button
  const connectBtn = container.querySelector('#companion-connect');
  const userInput = container.querySelector('#companion-user-id');

  connectBtn.addEventListener('click', () => _connectUser(container));
  userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') _connectUser(container);
  });

  // Send button
  const sendBtn = container.querySelector('#companion-send');
  const textarea = container.querySelector('#companion-textarea');

  sendBtn.addEventListener('click', () => _sendMessage(container));
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _sendMessage(container);
    }
  });

  // Auto-resize textarea
  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    sendBtn.disabled = !textarea.value.trim();
  });
}

// ── Connect to user ─────────────────────────────────────────────────────

async function _connectUser(container) {
  const input = container.querySelector('#companion-user-id');
  const userId = parseInt(input.value);
  if (!userId || userId < 1) {
    showToast('Enter a valid User ID', 'warning');
    return;
  }

  _userId = userId;
  _messages = [];

  // Show loading state
  const welcome = container.querySelector('#companion-welcome');
  if (welcome) welcome.innerHTML = '<div class="companion-loading">Connecting...</div>';

  try {
    // Load greeting + session in parallel
    const [greetingData, sessionData] = await Promise.all([
      api.companionGreeting(userId),
      api.companionSession(userId),
    ]);

    _sessionId = greetingData.session_id || sessionData.session_id;
    _progress = greetingData.progress;

    // Update progress bar
    _updateProgress(container, greetingData.progress);

    // Show greeting as first message
    _addMessage(container, 'assistant', greetingData.greeting, 'prepare');

    // Show quick actions
    _renderActions(container, greetingData.quick_actions);

    // Show input area
    container.querySelector('#companion-input-area').style.display = '';

    // Remove welcome
    if (welcome) welcome.remove();

    // Focus textarea
    container.querySelector('#companion-textarea').focus();

  } catch (err) {
    showToast(`Failed to connect: ${err.message}`, 'error');
    if (welcome) {
      welcome.innerHTML = `
        <div class="companion-welcome-icon">T</div>
        <h2>Connection failed</h2>
        <p>${err.message}</p>
      `;
    }
  }
}

// ── Send message ────────────────────────────────────────────────────────

async function _sendMessage(container) {
  const textarea = container.querySelector('#companion-textarea');
  const message = textarea.value.trim();
  if (!message || !_userId || _isTyping) return;

  // Add user message to chat
  _addMessage(container, 'user', message);

  // Clear input
  textarea.value = '';
  textarea.style.height = 'auto';
  container.querySelector('#companion-send').disabled = true;

  // Show typing indicator
  _isTyping = true;
  const typingEl = _addTypingIndicator(container);

  try {
    const result = await api.companionChat({
      user_id: _userId,
      message: message,
      session_id: _sessionId,
    });

    // Remove typing indicator
    typingEl.remove();
    _isTyping = false;

    // Update mode
    _updateMode(container, result.mode, result.mode_confidence);

    // Add assistant response
    _addMessage(container, 'assistant', result.response, result.mode, result.sources);

    // Handle escalation
    if (result.escalate) {
      _addSystemMessage(container, 'Your coach has been notified. Your wellbeing matters most.');
    }

    // Update session ID if returned
    if (result.session_id) _sessionId = result.session_id;

  } catch (err) {
    typingEl.remove();
    _isTyping = false;
    _addSystemMessage(container, `Something went wrong: ${err.message}. Try again?`);
  }
}

// ── Message rendering ───────────────────────────────────────────────────

function _addMessage(container, role, content, mode = null, sources = []) {
  const messagesEl = container.querySelector('#companion-messages');
  const msgEl = document.createElement('div');
  msgEl.className = `companion-msg companion-msg-${role}`;

  const modeConfig = mode ? MODE_CONFIG[mode] : null;

  // Parse markdown using marked.js
  let htmlContent = content;
  if (typeof marked !== 'undefined') {
    try {
      htmlContent = marked.parse(content);
    } catch { /* fall back to raw text */ }
  }

  // Build message HTML
  let inner = '';

  if (role === 'assistant') {
    inner += '<div class="companion-msg-avatar">T</div>';
  }

  inner += `<div class="companion-msg-bubble ${role === 'assistant' ? 'companion-msg-ai' : ''}">`;

  // Mode badge for assistant messages
  if (role === 'assistant' && modeConfig) {
    inner += `<div class="companion-msg-mode" style="color: ${modeConfig.color}">
      ${modeConfig.icon} ${modeConfig.label}
    </div>`;
  }

  inner += `<div class="companion-msg-content">${htmlContent}</div>`;

  // Source citations
  if (sources && sources.length > 0) {
    inner += '<div class="companion-msg-sources">';
    inner += '<span class="companion-sources-label">Sources:</span>';
    for (const src of sources) {
      const label = src.lesson_name
        ? `${src.slide_index ? 'Slide ' + src.slide_index + ' of ' : ''}${src.lesson_name}`
        : src.source;
      inner += `<span class="companion-source-chip" title="Relevance: ${src.score}">${label}</span>`;
    }
    inner += '</div>';
  }

  inner += '</div>';

  // Timestamp
  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  inner += `<div class="companion-msg-time">${now}</div>`;

  msgEl.innerHTML = inner;
  messagesEl.appendChild(msgEl);

  // Store message
  _messages.push({ role, content, mode, timestamp: Date.now() });

  // Scroll to bottom
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function _addTypingIndicator(container) {
  const messagesEl = container.querySelector('#companion-messages');
  const el = document.createElement('div');
  el.className = 'companion-msg companion-msg-assistant companion-typing';
  el.innerHTML = `
    <div class="companion-msg-avatar">T</div>
    <div class="companion-msg-bubble companion-msg-ai">
      <div class="companion-typing-dots">
        <span></span><span></span><span></span>
      </div>
    </div>
  `;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function _addSystemMessage(container, text) {
  const messagesEl = container.querySelector('#companion-messages');
  const el = document.createElement('div');
  el.className = 'companion-system-msg';
  el.textContent = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Quick actions ───────────────────────────────────────────────────────

function _renderActions(container, actions) {
  const actionsEl = container.querySelector('#companion-actions');
  const scrollEl = container.querySelector('#companion-actions-scroll');

  if (!actions || actions.length === 0) {
    actionsEl.style.display = 'none';
    return;
  }

  scrollEl.innerHTML = '';
  for (const action of actions) {
    const pill = document.createElement('button');
    pill.className = 'companion-action-pill';
    pill.innerHTML = `<span class="companion-action-icon">${action.icon || ''}</span> ${action.label}`;
    pill.addEventListener('click', () => {
      // Set the prompt in textarea and send
      const textarea = container.querySelector('#companion-textarea');
      textarea.value = action.prompt;
      textarea.dispatchEvent(new Event('input'));
      _sendMessage(container);
    });
    scrollEl.appendChild(pill);
  }

  actionsEl.style.display = '';
}

// ── Progress bar ────────────────────────────────────────────────────────

function _updateProgress(container, progress) {
  if (!progress || !progress.has_path) return;

  const bar = container.querySelector('#companion-progress-bar');
  const fill = container.querySelector('#companion-progress-fill');
  const text = container.querySelector('#companion-progress-text');

  bar.style.display = '';
  fill.style.width = `${progress.completion_pct}%`;
  text.textContent = `${progress.completed_lessons}/${progress.total_lessons} lessons (${progress.completion_pct}%)`;
}

// ── Mode indicator ──────────────────────────────────────────────────────

function _updateMode(container, mode, confidence) {
  const modeEl = container.querySelector('#companion-mode');
  const config = MODE_CONFIG[mode];

  if (!config || !mode) {
    modeEl.style.display = 'none';
    return;
  }

  modeEl.style.display = '';
  modeEl.style.background = config.color + '22';
  modeEl.style.color = config.color;
  modeEl.style.borderColor = config.color + '44';
  modeEl.innerHTML = `${config.icon} ${config.label}`;
  _currentMode = mode;
}
