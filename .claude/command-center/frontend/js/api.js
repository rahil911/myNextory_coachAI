// ==========================================================================
// API.JS — REST Client + WebSocket Manager with Auto-Reconnect
// ==========================================================================

import { setState, getState } from './state.js';
import { showToast } from './components/toast.js';

const BASE_URL = window.location.origin;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

// ── REST Client ────────────────────────────────────────────────────────────

async function request(method, path, body = null, timeoutMs = 15000, extraHeaders = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
    signal: controller.signal,
  };
  if (body) opts.body = JSON.stringify(body);

  try {
    const res = await fetch(`${BASE_URL}${path}`, opts);
    clearTimeout(timeout);
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${method} ${path} failed: ${res.status} ${text}`);
    }
    if (res.status === 204) return null;
    return res.json();
  } catch (err) {
    clearTimeout(timeout);
    if (err.name === 'AbortError') {
      throw new Error(`${method} ${path} timed out (${timeoutMs / 1000}s)`);
    }
    throw err;
  }
}

export const api = {
  // Dashboard
  getDashboard:   () => request('GET', '/api/dashboard'),

  // Agents — backend returns {"agents": [...], "count": N}
  getAgents:      () => request('GET', '/api/agents').then(r => r.agents || []),
  getAgent:       (id) => request('GET', `/api/agents/${id}`),
  killAgent:      (id) => request('POST', `/api/agents/${id}/kill`),
  retryAgent:     (id) => request('POST', `/api/agents/${id}/retry`),

  // Beads (Kanban)
  getKanban:      () => request('GET', '/api/kanban'),
  getBeads:       () => request('GET', '/api/beads').then(r => Array.isArray(r) ? r : r.beads || []),
  getBead:        (id) => request('GET', `/api/beads/${id}`),
  moveBead:       (id, column) => request('PATCH', `/api/beads/${id}/move`, { column }),
  updateBead:     (id, data) => request('PATCH', `/api/beads/${id}`, data),
  commentBead:    (id, text) => request('POST', `/api/beads/${id}/comment`, { text }),

  // Think Tank — backend expects {topic: ...}
  createSession:  (data) => request('POST', '/api/thinktank/start', { topic: data.topic || data.name || 'New Session', context: data.context }, 60000),
  getSession:     () => request('GET', '/api/thinktank/session'),
  sendMessage:    (sessionId, msg) => request('POST', '/api/thinktank/message', msg, 60000),
  sendAction:     (sessionId, action) => request('POST', '/api/thinktank/action', action, 60000),
  approveSpec:    (sessionId, { dryRun = false } = {}) => {
    const idempotencyKey = crypto.randomUUID();
    const qs = dryRun ? '?dry_run=true' : '';
    return request('POST', `/api/thinktank/approve/${sessionId}${qs}`, {}, 60000, {
      'X-Idempotency-Key': idempotencyKey,
    });
  },
  getHistory:     () => request('GET', '/api/thinktank/history'),
  getSessionById: (id) => request('GET', `/api/thinktank/session/${id}`),
  resumeSession:  (id) => request('POST', `/api/thinktank/resume/${id}`),
  deleteSession:  (id) => request('DELETE', `/api/thinktank/session/${id}`),
  setPhase:       (sessionId, phase) => request('POST', `/api/thinktank/session/${sessionId}/phase?phase=${phase}`),
  saveAsDraft:    (sessionId) => request('POST', `/api/thinktank/session/${sessionId}/draft`),

  // Health
  checkDispatchHealth: () => request('GET', '/api/dashboard/health/dispatch-ready'),

  // Dispatch
  getDispatchStatus: (sessionId) => request('GET', `/api/thinktank/dispatch/${sessionId}`),
  cancelDispatch:    (sessionId) => request('POST', `/api/thinktank/dispatch/${sessionId}/cancel`),
  retryDispatch:     (sessionId) => request('POST', `/api/thinktank/dispatch/${sessionId}/retry`),

  // Epics — backend returns {"epics": [...], "count": N}
  getEpics:       () => request('GET', '/api/epics').then(r => r.epics || []),

  // Commands
  executeCommand: (cmd) => request('POST', '/api/commands/execute', cmd),

  // Attachments
  uploadAttachment: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/api/attachments`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },

  // Approvals — backend returns {"pending": [...], "history": [...], "pending_count": N}
  getApprovals:   () => request('GET', '/api/approvals'),
  approveItem:    (id) => request('POST', `/api/approvals/${id}/approve`),
  rejectItem:     (id, reason) => request('POST', `/api/approvals/${id}/reject`, { reason: reason || '' }),
  approveAll:     () => request('POST', '/api/approvals/approve-all'),

  // Events (timeline) — backend returns {"events": [...]}
  getEvents:      (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/api/dashboard/timeline${qs ? '?' + qs : ''}`).then(r => r.events || []);
  },

  // Tory — Learner path, profile, feedback
  getToryPath:     (learnerId) => request('GET', `/api/tory/path/${learnerId}`),
  getToryProfile:  (learnerId) => request('GET', `/api/tory/profile/${learnerId}`),
  submitToryFeedback: (learnerId, type, comment) =>
    request('POST', '/api/tory/feedback', { learner_id: learnerId, type, comment }),

  // Tory Admin — HR Dashboard
  getToryAdminCohort:   (qs) => request('GET', `/api/tory/admin/cohort${qs ? '?' + qs : ''}`),
  getToryAdminLearner:  (id) => request('GET', `/api/tory/admin/learner/${id}`),
  getToryAdminMetrics:  () => request('GET', '/api/tory/admin/metrics'),

  // Tory Workspace — split-view path builder
  getToryUsers: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString();
    return request('GET', `/api/tory/users${qs ? '?' + qs : ''}`);
  },
  getToryUserDetail:    (userId) => request('GET', `/api/tory/users/${userId}/detail`),
  processToryUser:      (userId) => request('POST', `/api/tory/process/${userId}`, {}, 60000),
  batchProcessTory:     (body) => request('POST', '/api/tory/batch-process', body, 60000),
  getToryPreviewImpact: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString();
    return request('GET', `/api/tory/preview-impact${qs ? '?' + qs : ''}`);
  },
  getToryAgentSessions: (userId) => request('GET', `/api/tory/agent-sessions/${userId}`),
  getToryAgentSession:  (userId, sessionId) => request('GET', `/api/tory/agent-sessions/${userId}/${sessionId}`),
  chatWithToryAgent:    (userId, sessionId, text) => request('POST', `/api/tory/agent-sessions/${userId}/${sessionId}/chat`, { text }, 60000),
  cancelToryAgent:      (userId, sessionId) => request('DELETE', `/api/tory/agent-sessions/${userId}/${sessionId}`),
  getToryContentLibrary: (reviewStatus) => {
    const qs = reviewStatus ? `?review_status=${encodeURIComponent(reviewStatus)}` : '';
    return request('GET', `/api/tory/content-library${qs}`);
  },
  getToryLessonSlides:  (lessonDetailId) => request('GET', `/api/tory/lesson/${lessonDetailId}/slides`, null, 30000),
  reorderToryPath:      (userId, body) => request('PUT', `/api/tory/path/${userId}/reorder`, body),
  swapToryLesson:       (userId, body) => request('POST', `/api/tory/path/${userId}/swap`, body),
  lockToryRecommendation: (userId, recId, body) => request('POST', `/api/tory/path/${userId}/lock/${recId}`, body),

  // Tory Content Review
  reviewApprove:        (tagId, reviewerId, notes) =>
    request('POST', `/api/tory/review/${tagId}/approve`, { reviewer_id: reviewerId, notes }),
  reviewCorrect:        (tagId, reviewerId, correctedTags, opts = {}) =>
    request('POST', `/api/tory/review/${tagId}/correct`, {
      reviewer_id: reviewerId,
      corrected_tags: correctedTags,
      corrected_difficulty: opts.difficulty,
      corrected_learning_style: opts.learningStyle,
      notes: opts.notes,
    }),
  reviewDismiss:        (tagId, reviewerId, notes) =>
    request('POST', `/api/tory/review/${tagId}/dismiss`, { reviewer_id: reviewerId, notes }),
  reviewBulkApprove:    (reviewerId, minConfidence = 70) =>
    request('POST', '/api/tory/review/bulk-approve', { reviewer_id: reviewerId, min_confidence: minConfidence }),
  getReviewStats:       () => request('GET', '/api/tory/review/stats'),
};

// ── WebSocket Manager ──────────────────────────────────────────────────────

class WebSocketManager {
  constructor(path, onMessage) {
    this.path = path;
    this.onMessage = onMessage;
    this.ws = null;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.reconnectTimer = null;
    this.intentionalClose = false;
  }

  connect() {
    this.intentionalClose = false;
    const url = `${WS_BASE}${this.path}`;

    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      console.error(`WebSocket connect error [${this.path}]:`, err);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log(`WebSocket connected: ${this.path}`);
      this.reconnectDelay = 1000;
      setState({ wsConnected: true });
      this._updateStatusUI(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch (err) {
        console.error(`WebSocket parse error [${this.path}]:`, err);
      }
    };

    this.ws.onclose = (event) => {
      console.log(`WebSocket closed: ${this.path} (code=${event.code})`);
      setState({ wsConnected: false });
      this._updateStatusUI(false);
      if (!this.intentionalClose) {
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = (err) => {
      console.error(`WebSocket error [${this.path}]:`, err);
    };
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  close() {
    this.intentionalClose = true;
    clearTimeout(this.reconnectTimer);
    if (this.ws) this.ws.close();
  }

  _scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    console.log(`WebSocket reconnecting in ${this.reconnectDelay}ms...`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this.connect();
    }, this.reconnectDelay);
  }

  _updateStatusUI(connected) {
    const dot = document.getElementById('ws-status-dot');
    const text = document.getElementById('ws-status-text');
    if (dot) {
      dot.className = `status-dot ${connected ? 'status-dot-success' : 'status-dot-error'}`;
    }
    if (text) {
      text.textContent = connected ? 'Connected' : 'Reconnecting...';
    }
  }
}

// ── WebSocket Instances ────────────────────────────────────────────────────

function handleEventMessage(data) {
  const state = getState();
  const payload = data.payload || data;

  switch (data.type) {
    // ── Agent lifecycle events ──
    case 'AGENT_STATUS_CHANGE':
    case 'AGENT_SPAWNED':
    case 'AGENT_WORKING':
    case 'AGENT_COMPLETED': {
      const name = payload.agent || payload.name;
      if (name) {
        setState({
          agents: state.agents.map(a => a.name === name ? { ...a, ...payload } : a)
        });
      }
      break;
    }
    case 'AGENT_FAILED': {
      const name = payload.agent || payload.name;
      if (name) {
        setState({
          agents: state.agents.map(a => a.name === name ? { ...a, status: 'failed', ...payload } : a)
        });
        showToast(`Agent ${name} failed${payload.message ? ': ' + payload.message : ''}`, 'error');
      }
      break;
    }

    // ── Bead lifecycle ──
    case 'BEAD_TRANSITION': {
      const id = payload.id || payload.bead;
      if (id) {
        setState({
          beads: state.beads.map(b => b.id === id ? { ...b, ...payload } : b)
        });
      }
      break;
    }

    // ── Timeline events ──
    case 'TIMELINE_EVENT':
      setState({ events: [payload, ...state.events].slice(0, 500) });
      break;

    // ── Approvals ──
    case 'APPROVAL_NEEDED':
      setState({ _approvalTick: Date.now() });
      showToast(`Approval needed: ${payload.file || payload.title || 'new proposal'}`, 'warning');
      break;
    case 'APPROVAL_RESOLVED':
      setState({ _approvalTick: Date.now() });
      break;

    // ── Dispatch Engine events ──
    case 'DISPATCH_STARTED':
      showToast(`Build started: ${payload.topic || 'project'}`, 'info');
      break;

    case 'DISPATCH_PROGRESS':
      showToast(`Build progress: ${payload.status}`, 'info');
      break;

    case 'DISPATCH_COMPLETE': {
      const statusMsg = payload.status === 'completed'
        ? `Build complete! ${payload.completed}/${payload.total} tasks done.`
        : `Build finished with issues. ${payload.completed}/${payload.total} completed, ${payload.failed} failed.`;
      showToast(statusMsg, payload.status === 'completed' ? 'success' : 'warning');
      break;
    }

    case 'DISPATCH_ERROR':
      showToast(`Build error: ${payload.error}`, 'error');
      break;

    case 'AGENT_PROGRESS':
      // Update agent cards in dashboard view if visible
      break;

    case 'AGENT_RETRYING':
      showToast(`Retrying ${payload.agent} (attempt ${payload.attempt})`, 'warning');
      break;

    case 'BEAD_STATUS_CHANGE':
      setState({ _beadTick: Date.now() });
      break;

    case 'FAILURE_HANDLED':
      showToast(`Failure handled: ${payload.agent} — ${payload.action}`, 'warning');
      break;

    // ── System toasts from backend ──
    case 'TOAST':
      showToast(payload.message || payload.text || 'Notification', payload.level || 'info');
      break;

    default:
      console.debug('Unhandled WS event type:', data.type, data);
      break;
  }
}

function handleThinktankMessage(data) {
  const state = getState();
  const tt = { ...state.thinktank };

  const pushDispatchEvent = (eventType, payload = {}) => {
    const events = [
      ...(tt.dispatchEvents || []),
      {
        ts: new Date().toISOString(),
        type: eventType,
        payload,
      },
    ].slice(-30);
    return events;
  };

  switch (data.type) {
    // Backend event bus types
    case 'THINKTANK_MESSAGE': {
      const msg = data.payload?.message;
      if (msg && msg.role !== 'system') {
        const isAi = msg.role === 'orchestrator';
        let content = msg.content;
        let chips = [];

        if (isAi) {
          // Strip any remaining spec-kit blocks from display
          content = stripSpecKitBlocks(content);
          // Parse D/A/G action line into clickable chips
          const dagResult = parseDagLine(content);
          content = dagResult.content;
          chips = dagResult.chips;
        }

        const mapped = {
          role: isAi ? 'ai' : msg.role,
          content,
          streaming: false,
          chips,
        };

        // Replace streaming AI placeholder if one exists
        const messages = [...tt.messages];
        if (isAi) {
          const lastIdx = messages.length - 1;
          if (lastIdx >= 0 && messages[lastIdx].role === 'ai' && messages[lastIdx].streaming) {
            messages[lastIdx] = mapped;
          } else {
            messages.push(mapped);
          }
        } else {
          messages.push(mapped);
        }
        setState({ thinktank: { ...tt, messages } });
      }
      break;
    }
    case 'THINKTANK_SPECKIT_DELTA': {
      const section = data.payload?.section;
      const content = data.payload?.content;
      if (section && content) {
        const sk = { ...tt.specKit };
        sk[section] = { ...(sk[section] || {}), content, status: data.payload.status || 'draft' };
        setState({ thinktank: { ...tt, specKit: sk } });
      }
      break;
    }
    case 'THINKTANK_PHASE_CHANGE': {
      const phaseMap = { listen: 1, explore: 2, scope: 3, confirm: 4, building: 5 };
      const phaseNum = phaseMap[data.payload?.phase] || tt.phase;
      setState({ thinktank: { ...tt, phase: phaseNum } });
      break;
    }

    // Dispatch events (also arrive on thinktank WS channel)
    case 'DISPATCH_STARTED':
    case 'DISPATCH_PROGRESS':
    case 'DISPATCH_COMPLETE':
    case 'DISPATCH_ERROR':
      if (data.payload) {
        const dispatchEvents = pushDispatchEvent(data.type, data.payload);
        setState({
          thinktank: {
            ...tt,
            dispatchStatus: data.payload,
            dispatchEvents,
          }
        });
      }
      break;

    // Streaming types (for future Agent SDK integration)
    case 'token':
      if (tt.messages.length > 0) {
        const last = tt.messages[tt.messages.length - 1];
        if (last.role === 'ai' && last.streaming) {
          last.content += data.token;
          setState({ thinktank: { ...tt, messages: [...tt.messages] } });
        }
      }
      break;
    case 'message_complete':
      if (tt.messages.length > 0) {
        const last = tt.messages[tt.messages.length - 1];
        last.streaming = false;
        last.chips = data.chips || [];
        setState({ thinktank: { ...tt, messages: [...tt.messages] } });
      }
      break;
    case 'speckit_update':
      setState({ thinktank: { ...tt, specKit: { ...tt.specKit, ...data.sections } } });
      break;
    case 'phase_advance':
      setState({ thinktank: { ...tt, phase: data.phase } });
      break;
    case 'risk_added':
      setState({ thinktank: { ...tt, risks: [...tt.risks, data.risk] } });
      break;
    default:
      break;
  }
}

export { WebSocketManager };

export let eventsWs = null;
export let thinktankWs = null;

export function connectWebSockets() {
  eventsWs = new WebSocketManager('/ws', handleEventMessage);
  eventsWs.connect();
}

export function connectThinktankWs(sessionId) {
  if (thinktankWs) thinktankWs.close();
  thinktankWs = new WebSocketManager(`/ws/thinktank?session=${sessionId}`, handleThinktankMessage);
  thinktankWs.connect();
}

export function disconnectThinktankWs() {
  if (thinktankWs) {
    thinktankWs.close();
    thinktankWs = null;
  }
}

// ── Tory Agent WebSocket ─────────────────────────────────────────────────

let _toryAgentWs = null;

export function connectToryAgentWs(sessionId, onMessage) {
  if (_toryAgentWs) _toryAgentWs.close();
  _toryAgentWs = new WebSocketManager(`/ws/tory-agent?session=${sessionId}`, onMessage);
  _toryAgentWs.connect();
  return _toryAgentWs;
}

export function sendToryAgentMessage(data) {
  if (_toryAgentWs) _toryAgentWs.send(data);
}

export function disconnectToryAgentWs() {
  if (_toryAgentWs) {
    _toryAgentWs.close();
    _toryAgentWs = null;
  }
}

// ── D/A/G Parsing & Spec-Kit Stripping ──────────────────────────────────

/**
 * Strip ```spec-kit blocks from displayed message content.
 */
export function stripSpecKitBlocks(content) {
  return content.replace(/```spec-kit\s*\n[\s\S]*?\n```/g, '').trim();
}

/**
 * Parse [D]...|[A]...|[G]... action line from AI response.
 * Returns { content (cleaned), chips[] }.
 */
export function parseDagLine(content) {
  const dagRegex = /\n?\[D\]\s*(.+?)\s*\|\s*\[A\]\s*(.+?)\s*\|\s*\[G\]\s*(.+?)$/m;
  const match = content.match(dagRegex);
  if (!match) return { content, chips: [] };

  const cleanContent = content.replace(match[0], '').trim();
  const chips = [
    { label: match[1].trim(), icon: '', action: () => sendDagLetter('D') },
    { label: match[2].trim(), icon: '', action: () => sendDagLetter('A') },
    { label: match[3].trim(), icon: '', action: () => sendDagLetter('G') },
  ];
  return { content: cleanContent, chips };
}

/**
 * Send a D/A/G letter as a user message (adds user msg + streaming placeholder).
 */
export function sendDagLetter(letter) {
  const tt = getState().thinktank;
  const userMsg = { role: 'human', content: letter, streaming: false, chips: [] };
  const aiPlaceholder = { role: 'ai', content: '', streaming: true, chips: [] };
  setState({
    thinktank: {
      ...tt,
      messages: [...tt.messages, userMsg, aiPlaceholder],
    }
  });

  if (thinktankWs) {
    thinktankWs.send({ type: 'message', text: letter });
  } else {
    const sessionId = tt?.sessionId;
    if (sessionId) {
      request('POST', '/api/thinktank/message', { text: letter }).catch(err => {
        showToast(`Send failed: ${err.message}`, 'error');
      });
    }
  }
}
