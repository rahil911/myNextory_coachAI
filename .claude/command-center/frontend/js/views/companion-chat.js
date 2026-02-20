// ==========================================================================
// COMPANION-CHAT.JS — Learner-Facing AI Companion Chat Interface
// Two-panel layout: Left sidebar (user list + filters), Right (chat area).
// Reuses /api/tory/users endpoint for user list with filter support.
// ==========================================================================

import { getState, setState, subscribe } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { VoiceChat } from '../components/voice-chat.js';

// ── Module state ──────────────────────────────────────────────────────────

let _sessionId = null;
let _userId = null;
let _messages = [];
let _currentMode = null;
let _progress = null;
let _wsConnection = null;
let _isTyping = false;
let _chatContainer = null;
let _voiceChat = null;

// ── User list state ───────────────────────────────────────────────────────

let _users = [];
let _companies = [];
let _totalUsers = 0;
let _totalPages = 1;
let _currentPage = 1;
let _filters = {
  search: '',
  company: '',
  status: 'has_epp',       // Default: Has EPP
  has_backpack: 'yes',     // Default: Has Backpack
};
let _usersLoading = false;
let _searchDebounce = null;

const PAGE_SIZE = 50;

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
    <!-- Top Bar -->
    <div class="companion-topbar">
      <div class="companion-topbar-left">
        <button class="cc-sidebar-toggle" id="cc-toggle-sidebar" title="Toggle user list">&#9664; Users</button>
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
        <div class="cc-topbar-stats" id="cc-topbar-stats"></div>
        <span id="companion-voice-btn" style="display:none"></span>
      </div>
    </div>

    <!-- Body: Sidebar + Chat -->
    <div class="companion-body">
      <!-- Left Sidebar: User List -->
      <div class="cc-sidebar" id="cc-sidebar">
        <div class="cc-sidebar-header">
          <div class="cc-search-row">
            <span class="cc-search-icon">&#128269;</span>
            <input type="text" id="cc-search" placeholder="Search name or email...">
          </div>
          <div class="cc-filters">
            <select id="cc-filter-company">
              <option value="">All Companies</option>
            </select>
            <select id="cc-filter-status">
              <option value="">All Status</option>
              <option value="has_epp" selected>Has EPP</option>
              <option value="processed">Processed</option>
              <option value="no_data">No Data</option>
            </select>
            <select id="cc-filter-backpack">
              <option value="">All Backpack</option>
              <option value="yes" selected>Has Backpack</option>
              <option value="no">No Backpack</option>
            </select>
          </div>
        </div>
        <div class="cc-user-list" id="cc-user-list"></div>
        <div class="cc-sidebar-footer">
          <div class="cc-pagination">
            <button class="cc-page-btn" id="cc-prev-page" disabled>&lt;</button>
            <span class="cc-page-info" id="cc-page-info">Page 1/1</span>
            <button class="cc-page-btn" id="cc-next-page" disabled>&gt;</button>
          </div>
        </div>
      </div>

      <!-- Right: Chat Area -->
      <div class="companion-main">
        <!-- Chat messages -->
        <div class="companion-messages" id="companion-messages">
          <div class="companion-welcome" id="companion-welcome">
            <div class="companion-welcome-icon">T</div>
            <h2>Meet Tory, your learning companion</h2>
            <p>Select a learner from the sidebar to start a personalized conversation.</p>
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
    </div>
  `;

  root.appendChild(container);
  _chatContainer = container;

  // Wire events
  _wireEvents(container);

  // Load users on mount
  _loadUsers();
}

// ── Event wiring ─────────────────────────────────────────────────────────

function _wireEvents(container) {
  // Sidebar toggle
  container.querySelector('#cc-toggle-sidebar').addEventListener('click', () => {
    const sidebar = container.querySelector('#cc-sidebar');
    const btn = container.querySelector('#cc-toggle-sidebar');
    sidebar.classList.toggle('collapsed');
    btn.classList.toggle('collapsed');
    btn.innerHTML = sidebar.classList.contains('collapsed') ? '&#9654; Users' : '&#9664; Users';
  });

  // Search
  container.querySelector('#cc-search').addEventListener('input', (e) => {
    clearTimeout(_searchDebounce);
    _searchDebounce = setTimeout(() => {
      _filters.search = e.target.value.trim();
      _currentPage = 1;
      _loadUsers();
    }, 300);
  });

  // Filter: company
  container.querySelector('#cc-filter-company').addEventListener('change', (e) => {
    _filters.company = e.target.value;
    _currentPage = 1;
    _loadUsers();
  });

  // Filter: status
  container.querySelector('#cc-filter-status').addEventListener('change', (e) => {
    _filters.status = e.target.value;
    _currentPage = 1;
    _loadUsers();
  });

  // Filter: backpack
  container.querySelector('#cc-filter-backpack').addEventListener('change', (e) => {
    _filters.has_backpack = e.target.value;
    _currentPage = 1;
    _loadUsers();
  });

  // Pagination
  container.querySelector('#cc-prev-page').addEventListener('click', () => {
    if (_currentPage > 1) {
      _currentPage--;
      _loadUsers();
    }
  });
  container.querySelector('#cc-next-page').addEventListener('click', () => {
    if (_currentPage < _totalPages) {
      _currentPage++;
      _loadUsers();
    }
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

// ── User list loading ────────────────────────────────────────────────────

async function _loadUsers() {
  _usersLoading = true;
  const listEl = _chatContainer.querySelector('#cc-user-list');
  if (listEl) listEl.innerHTML = '<div class="cc-loading"><div class="cc-spinner"></div> Loading users...</div>';

  try {
    const params = { page: _currentPage, limit: PAGE_SIZE };
    if (_filters.search) params.search = _filters.search;
    if (_filters.status) params.status_filter = _filters.status;
    if (_filters.company) params.company_filter = _filters.company;
    if (_filters.has_backpack) params.has_backpack = _filters.has_backpack;

    const data = await api.getToryUsers(params);
    _users = data.users || [];
    _totalUsers = data.total || 0;
    _totalPages = data.total_pages || Math.ceil(_totalUsers / PAGE_SIZE) || 1;

    if (data.companies && data.companies.length > 0) {
      _companies = data.companies;
      _populateCompanyFilter();
    }

    _usersLoading = false;
    _renderUserList();
    _renderPagination();
    _renderTopbarStats();
  } catch (err) {
    _usersLoading = false;
    if (listEl) listEl.innerHTML = `<div class="cc-empty">Failed to load users: ${_esc(err.message)}</div>`;
    showToast(`Failed to load users: ${err.message}`, 'error');
  }
}

function _populateCompanyFilter() {
  const select = _chatContainer.querySelector('#cc-filter-company');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">All Companies</option>';
  for (const company of _companies) {
    const opt = document.createElement('option');
    opt.value = company.id || '';
    opt.textContent = company.name || `Company ${company.id || ''}`;
    select.appendChild(opt);
  }
  if (current) select.value = current;
}

function _renderUserList() {
  const listEl = _chatContainer.querySelector('#cc-user-list');
  if (!listEl) return;
  listEl.innerHTML = '';

  if (_users.length === 0) {
    listEl.innerHTML = '<div class="cc-empty">No users found</div>';
    return;
  }

  for (const user of _users) {
    const card = document.createElement('div');
    const isSelected = user.nx_user_id === _userId;
    card.className = `cc-user-card${isSelected ? ' selected' : ''}`;

    const name = _getUserName(user);
    const status = user.tory_status || 'no_data';

    // Build badge HTML
    let badges = '';
    if (status === 'has_epp' || status === 'processed' || status === 'profiled') {
      badges += `<span class="cc-badge cc-badge-epp">EPP</span>`;
    }
    if (user.has_backpack) {
      badges += `<span class="cc-badge cc-badge-backpack">Backpack</span>`;
    }
    if (status === 'processed') {
      badges += `<span class="cc-badge cc-badge-processed">Path</span>`;
    }

    card.innerHTML = `
      <div class="cc-user-card-main">
        <div class="cc-user-avatar">${_getInitials(user)}</div>
        <div class="cc-user-info">
          <div class="cc-user-name">${_esc(name)}</div>
          <div class="cc-user-meta">${_esc(user.email || '')}</div>
          ${user.company_name ? `<div class="cc-user-meta">${_esc(user.company_name)}</div>` : ''}
        </div>
      </div>
      <div class="cc-user-badges">${badges}</div>
    `;

    card.addEventListener('click', () => _connectUser(_chatContainer, user.nx_user_id));
    listEl.appendChild(card);
  }
}

function _renderPagination() {
  const prevBtn = _chatContainer.querySelector('#cc-prev-page');
  const nextBtn = _chatContainer.querySelector('#cc-next-page');
  const info = _chatContainer.querySelector('#cc-page-info');
  if (prevBtn) prevBtn.disabled = _currentPage <= 1;
  if (nextBtn) nextBtn.disabled = _currentPage >= _totalPages;
  if (info) info.textContent = `Page ${_currentPage}/${_totalPages || 1}`;
}

function _renderTopbarStats() {
  const el = _chatContainer.querySelector('#cc-topbar-stats');
  if (!el) return;
  el.innerHTML = `<span class="cc-stat"><strong>${_totalUsers}</strong> users</span>`;
}

// ── Connect to user ─────────────────────────────────────────────────────

async function _connectUser(container, userId) {
  if (!userId || userId < 1) {
    showToast('Invalid User ID', 'warning');
    return;
  }

  _userId = userId;
  _messages = [];

  // Highlight selected user in list
  _renderUserList();

  // Show loading state
  const welcome = container.querySelector('#companion-welcome');
  const messagesEl = container.querySelector('#companion-messages');
  if (welcome) welcome.innerHTML = '<div class="companion-loading">Connecting...</div>';
  // Clear previous messages if reconnecting
  if (!welcome && messagesEl) {
    messagesEl.innerHTML = '<div class="companion-loading">Connecting...</div>';
  }

  try {
    // Load greeting + session in parallel
    const [greetingData, sessionData] = await Promise.all([
      api.companionGreeting(userId),
      api.companionSession(userId),
    ]);

    _sessionId = greetingData.session_id || sessionData.session_id;
    _progress = greetingData.progress;

    // Clear messages area for fresh conversation
    if (messagesEl) messagesEl.innerHTML = '';

    // Update progress bar
    _updateProgress(container, greetingData.progress);

    // Show greeting as first message
    _addMessage(container, 'assistant', greetingData.greeting, 'prepare');

    // Show quick actions
    _renderActions(container, greetingData.quick_actions);

    // Show input area
    container.querySelector('#companion-input-area').style.display = '';

    // Remove welcome if still present
    if (welcome) welcome.remove();

    // Focus textarea
    container.querySelector('#companion-textarea').focus();

    // Init voice chat
    _initVoice(container, userId);

  } catch (err) {
    showToast(`Failed to connect: ${err.message}`, 'error');
    if (messagesEl) {
      messagesEl.innerHTML = `
        <div class="companion-welcome">
          <div class="companion-welcome-icon">T</div>
          <h2>Connection failed</h2>
          <p>${err.message}</p>
        </div>
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

    // Add assistant response (with referenced lessons)
    _addMessage(container, 'assistant', result.response, result.mode, result.sources, result.referenced_lessons);

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

function _addMessage(container, role, content, mode = null, sources = [], referencedLessons = []) {
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

  // Referenced lesson cards
  if (referencedLessons && referencedLessons.length > 0) {
    inner += '<div class="companion-lesson-cards">';
    for (const lesson of referencedLessons) {
      inner += _renderLessonCard(lesson);
    }
    inner += '</div>';
  }

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

  // Wire lesson card buttons
  if (referencedLessons && referencedLessons.length > 0) {
    _wireLessonCardActions(msgEl, referencedLessons);
  }

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

// ── Voice chat integration ──────────────────────────────────────────────

function _initVoice(container, userId) {
  // Destroy previous instance
  if (_voiceChat) {
    _voiceChat.destroy();
    _voiceChat = null;
  }

  const voiceContainer = container.querySelector('#companion-voice-btn');
  if (!voiceContainer) return;
  voiceContainer.style.display = '';

  _voiceChat = new VoiceChat({
    role: 'companion',
    userId: userId,
    container: voiceContainer,
    onTranscript: (text) => {
      // Show user's spoken text as a chat message
      _addMessage(container, 'user', text);
    },
    onResponse: (text) => {
      // Show AI response as a chat message
      _addMessage(container, 'assistant', text, _currentMode);
    },
    onStateChange: (state) => {
      // Update mode pill with voice state
      const modeEl = container.querySelector('#companion-mode');
      if (state === 'listening') {
        modeEl.style.display = '';
        modeEl.style.background = '#22c55e22';
        modeEl.style.color = '#22c55e';
        modeEl.innerHTML = 'Listening...';
      } else if (state === 'thinking') {
        modeEl.style.display = '';
        modeEl.style.background = '#f59e0b22';
        modeEl.style.color = '#f59e0b';
        modeEl.innerHTML = 'Thinking...';
      } else if (state === 'speaking') {
        modeEl.style.display = '';
        modeEl.style.background = '#6366f122';
        modeEl.style.color = '#6366f1';
        modeEl.innerHTML = 'Speaking...';
      } else if (state === 'idle') {
        modeEl.style.display = 'none';
      }
    },
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────

function _getUserName(user) {
  const parts = [user.first_name, user.last_name].filter(Boolean);
  return parts.length > 0 ? parts.join(' ') : user.email || `User ${user.nx_user_id}`;
}

function _getInitials(user) {
  const first = (user.first_name || '')[0] || '';
  const last = (user.last_name || '')[0] || '';
  return (first + last).toUpperCase() || '?';
}

function _esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

// ── Inline lesson cards ──────────────────────────────────────────────────

function _renderLessonCard(lesson) {
  const diffLabel = lesson.difficulty ? `${lesson.difficulty}/5` : '';
  const diffClass = lesson.difficulty ? `difficulty-${lesson.difficulty}` : '';
  const duration = lesson.estimated_minutes ? `${lesson.estimated_minutes} min` : '';

  let html = `<div class="companion-lesson-card" data-detail-id="${lesson.lesson_detail_id}">`;

  // Header: title + badges
  html += '<div class="lesson-card-header">';
  html += `<span class="lesson-card-title">${_esc(lesson.lesson_title)}</span>`;
  html += '<div class="lesson-card-badges">';
  if (diffLabel) html += `<span class="lesson-card-badge ${diffClass}">${diffLabel}</span>`;
  if (duration) html += `<span class="lesson-card-badge badge-duration">${duration}</span>`;
  html += '</div></div>';

  // Journey name
  if (lesson.journey_name) {
    html += `<div class="lesson-card-journey">${_esc(lesson.journey_name)}</div>`;
  }

  // Summary
  if (lesson.summary) {
    html += `<p class="lesson-card-summary">${_esc(lesson.summary)}</p>`;
  }

  // Actions
  html += '<div class="lesson-card-actions">';
  if (lesson.slide_count > 0) {
    html += `<button class="lesson-card-btn btn-view-slides" data-detail-id="${lesson.lesson_detail_id}" data-title="${_esc(lesson.lesson_title)}">`;
    html += `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg> `;
    html += `View Slides (${lesson.slide_count})</button>`;
  }
  if (lesson.has_video) {
    html += `<button class="lesson-card-btn btn-play-video" data-detail-id="${lesson.lesson_detail_id}" data-title="${_esc(lesson.lesson_title)}">`;
    html += `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> `;
    html += 'Play Video</button>';
  }
  html += '</div></div>';

  return html;
}

function _wireLessonCardActions(msgEl, lessons) {
  // View Slides buttons
  msgEl.querySelectorAll('.btn-view-slides').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const detailId = parseInt(btn.dataset.detailId);
      const title = btn.dataset.title || 'Slides';
      _openCompanionSlideViewer(detailId, title);
    });
  });

  // Play Video buttons — fetches resolved video URL from slides API
  msgEl.querySelectorAll('.btn-play-video').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const detailId = parseInt(btn.dataset.detailId);
      const card = btn.closest('.companion-lesson-card');

      // Toggle: if video already showing, remove it
      const existing = card.querySelector('.companion-inline-video');
      if (existing) {
        existing.remove();
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play Video`;
        return;
      }

      // Show loading state
      btn.disabled = true;
      btn.innerHTML = 'Loading...';

      try {
        const data = await api.getToryLessonSlides(detailId);
        const slides = data.slides || data || [];

        // Find first video slide with a resolved URL
        const videoSlide = slides.find(s =>
          /^video/.test(s.type) && s.video_library && s.video_library.video_url
        );

        if (!videoSlide) {
          showToast('Video not available for this lesson', 'warning');
          btn.disabled = false;
          btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play Video`;
          return;
        }

        const vl = videoSlide.video_library;
        const videoWrap = document.createElement('div');
        videoWrap.className = 'companion-inline-video';
        videoWrap.innerHTML = `
          <video controls playsinline preload="metadata"
            ${vl.thumbnail_url ? `poster="${_esc(vl.thumbnail_url)}"` : ''}>
            <source src="${_esc(vl.video_url)}" type="video/mp4">
            Your browser does not support video playback.
          </video>
        `;
        card.querySelector('.lesson-card-actions').before(videoWrap);

        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Hide Video`;

        // Init Plyr if available
        const videoEl = videoWrap.querySelector('video');
        if (typeof Plyr !== 'undefined') {
          new Plyr(videoEl, {
            controls: ['play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen'],
          });
        }

        videoWrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play Video`;
        showToast(`Failed to load video: ${err.message}`, 'error');
      }
    });
  });
}


// ── Companion slide viewer modal ─────────────────────────────────────────
// Self-contained version — does NOT depend on tory-workspace.js exports.

let _compSlides = null;
let _compSlideIdx = 0;

async function _openCompanionSlideViewer(lessonDetailId, lessonName) {
  _compSlides = null;
  _compSlideIdx = 0;

  // Show modal with loading state
  _renderCompanionSlideModal(lessonName, true);

  try {
    const data = await api.getToryLessonSlides(lessonDetailId);
    _compSlides = data.slides || data || [];
    _renderCompanionSlideModal(lessonName, false);
  } catch (err) {
    showToast(`Failed to load slides: ${err.message}`, 'error');
    _closeCompanionSlideModal();
  }
}

function _renderCompanionSlideModal(lessonName, loading) {
  document.getElementById('companion-slide-modal')?.remove();

  const modal = document.createElement('div');
  modal.className = 'companion-slide-modal';
  modal.id = 'companion-slide-modal';

  if (loading) {
    modal.innerHTML = `
      <div class="companion-slide-overlay"></div>
      <div class="companion-slide-container">
        <div class="companion-slide-header">
          <span class="companion-slide-title">${_esc(lessonName)}</span>
          <button class="companion-slide-close">&times;</button>
        </div>
        <div class="companion-slide-loading">Loading slides...</div>
      </div>
    `;
    document.body.appendChild(modal);
    _wireCompanionSlideClose(modal);
    return;
  }

  const slides = _compSlides || [];
  if (slides.length === 0) {
    modal.innerHTML = `
      <div class="companion-slide-overlay"></div>
      <div class="companion-slide-container">
        <div class="companion-slide-header">
          <span class="companion-slide-title">${_esc(lessonName)}</span>
          <button class="companion-slide-close">&times;</button>
        </div>
        <div class="companion-slide-loading">No slides found for this lesson.</div>
      </div>
    `;
    document.body.appendChild(modal);
    _wireCompanionSlideClose(modal);
    return;
  }

  // Build slide carousel
  let slidesHtml = '';
  for (let i = 0; i < slides.length; i++) {
    const slide = slides[i];
    const content = typeof slide.content === 'string' ? (() => { try { return JSON.parse(slide.content); } catch { return {}; } })() : (slide.content || {});
    const type = slide.type || slide.slide_type || 'unknown';
    slidesHtml += `<div class="companion-slide-item ${i === 0 ? 'active' : ''}" data-idx="${i}">
      <div class="companion-slide-body">${_renderCompanionSlide(type, content, slide)}</div>
    </div>`;
  }

  // Pagination dots (max 20 visible)
  const dotCount = Math.min(slides.length, 20);
  let dotsHtml = '';
  for (let i = 0; i < dotCount; i++) {
    dotsHtml += `<span class="companion-slide-dot ${i === 0 ? 'active' : ''}" data-idx="${i}"></span>`;
  }

  modal.innerHTML = `
    <div class="companion-slide-overlay"></div>
    <div class="companion-slide-container">
      <div class="companion-slide-header">
        <span class="companion-slide-title">${_esc(lessonName)}</span>
        <span class="companion-slide-counter">1 / ${slides.length}</span>
        <button class="companion-slide-close">&times;</button>
      </div>
      <div class="companion-slide-carousel">${slidesHtml}</div>
      <div class="companion-slide-nav">
        <button class="companion-slide-prev" disabled>&larr;</button>
        <div class="companion-slide-dots">${dotsHtml}</div>
        <button class="companion-slide-next" ${slides.length <= 1 ? 'disabled' : ''}>&rarr;</button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  _wireCompanionSlideClose(modal);
  _wireCompanionSlideNav(modal, slides.length);

  // Init Plyr for any videos in active slide
  _initCompanionSlidePlyr(modal);
}

function _renderCompanionSlide(type, content, slide) {
  // Video slides
  if (/^video/.test(type)) {
    const vl = slide && slide.video_library;
    if (vl && vl.video_url) {
      let h = '';
      const title = content.slide_title || vl.title || '';
      if (title) h += `<h3 class="companion-slide-text-title">${_esc(title)}</h3>`;
      h += `<div class="companion-slide-media">
        <video class="companion-slide-video" playsinline controls preload="metadata"
          ${vl.thumbnail_url ? `poster="${_esc(vl.thumbnail_url)}"` : ''}>
          <source src="${_esc(vl.video_url)}" type="video/mp4">
        </video>
      </div>`;
      if (vl.transcript) {
        h += `<div class="companion-slide-transcript"><strong>Transcript:</strong> ${_esc(vl.transcript).substring(0, 500)}${vl.transcript.length > 500 ? '...' : ''}</div>`;
      }
      return h;
    }
    return `<div class="companion-slide-placeholder">Video content — available in the MyNextory app</div>`;
  }

  // Image slides
  if (/^image|^special-image|^sparkle/.test(type)) {
    const imgUrl = content.image_url || content.background_image || content.image || '';
    let h = '';
    const title = content.slide_title || content.title || '';
    if (title) h += `<h3 class="companion-slide-text-title">${_esc(title)}</h3>`;
    if (imgUrl) {
      h += `<div class="companion-slide-media"><img src="${_esc(imgUrl)}" alt="${_esc(title)}" loading="lazy"></div>`;
    }
    const desc = content.content || content.description || '';
    if (desc) h += `<div class="companion-slide-text">${_esc(desc)}</div>`;
    return h || '<div class="companion-slide-placeholder">Image slide</div>';
  }

  // Text-based slides (question-answer, greetings, take-away, etc.)
  let h = '';
  const title = content.slide_title || content.title || content.heading || '';
  if (title) h += `<h3 class="companion-slide-text-title">${_esc(title)}</h3>`;

  const body = content.content || content.description || content.text || content.subheading || '';
  if (body) h += `<div class="companion-slide-text">${_esc(body)}</div>`;

  // Questions
  if (content.question) h += `<div class="companion-slide-question">${_esc(content.question)}</div>`;
  if (content.questions && Array.isArray(content.questions)) {
    for (const q of content.questions.slice(0, 5)) {
      const qt = typeof q === 'string' ? q : (q.question || q.text || '');
      if (qt) h += `<div class="companion-slide-question">${_esc(qt)}</div>`;
    }
  }

  // Options
  if (content.options && Array.isArray(content.options)) {
    h += '<div class="companion-slide-options">';
    for (const opt of content.options.slice(0, 6)) {
      const label = typeof opt === 'string' ? opt : (opt.title || opt.text || opt.label || opt.msg || '');
      if (label) h += `<div class="companion-slide-option">${_esc(label)}</div>`;
    }
    h += '</div>';
  }

  return h || `<div class="companion-slide-placeholder">${_esc(type)} slide</div>`;
}

function _wireCompanionSlideClose(modal) {
  modal.querySelector('.companion-slide-close')?.addEventListener('click', _closeCompanionSlideModal);
  modal.querySelector('.companion-slide-overlay')?.addEventListener('click', _closeCompanionSlideModal);
  const handler = (e) => {
    if (e.key === 'Escape') {
      _closeCompanionSlideModal();
      document.removeEventListener('keydown', handler);
    }
  };
  document.addEventListener('keydown', handler);
}

function _wireCompanionSlideNav(modal, total) {
  const prevBtn = modal.querySelector('.companion-slide-prev');
  const nextBtn = modal.querySelector('.companion-slide-next');
  const counter = modal.querySelector('.companion-slide-counter');
  const dots = modal.querySelectorAll('.companion-slide-dot');
  const items = modal.querySelectorAll('.companion-slide-item');

  function goTo(idx) {
    if (idx < 0 || idx >= total) return;
    items.forEach(el => el.classList.remove('active'));
    items[idx]?.classList.add('active');
    dots.forEach(d => d.classList.remove('active'));
    dots[idx]?.classList.add('active');
    if (counter) counter.textContent = `${idx + 1} / ${total}`;
    prevBtn.disabled = idx === 0;
    nextBtn.disabled = idx === total - 1;
    _compSlideIdx = idx;
    _initCompanionSlidePlyr(modal);
  }

  prevBtn?.addEventListener('click', () => goTo(_compSlideIdx - 1));
  nextBtn?.addEventListener('click', () => goTo(_compSlideIdx + 1));
  dots.forEach(d => d.addEventListener('click', () => goTo(parseInt(d.dataset.idx))));

  // Keyboard nav
  const keyHandler = (e) => {
    if (!document.getElementById('companion-slide-modal')) {
      document.removeEventListener('keydown', keyHandler);
      return;
    }
    if (e.key === 'ArrowLeft') goTo(_compSlideIdx - 1);
    if (e.key === 'ArrowRight') goTo(_compSlideIdx + 1);
  };
  document.addEventListener('keydown', keyHandler);
}

function _initCompanionSlidePlyr(modal) {
  if (typeof Plyr === 'undefined') return;
  const active = modal.querySelector('.companion-slide-item.active');
  if (!active) return;
  active.querySelectorAll('video:not(.plyr--setup)').forEach(v => {
    if (!v.closest('.plyr')) {
      new Plyr(v, { controls: ['play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen'] });
      v.classList.add('plyr--setup');
    }
  });
}

function _closeCompanionSlideModal() {
  const modal = document.getElementById('companion-slide-modal');
  if (modal) {
    // Destroy any Plyr instances
    modal.querySelectorAll('.plyr').forEach(el => el.plyr?.destroy?.());
    modal.remove();
  }
  _compSlides = null;
  _compSlideIdx = 0;
}
