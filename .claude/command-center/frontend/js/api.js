// ==========================================================================
// API.JS — REST Client + WebSocket Manager with Auto-Reconnect
// ==========================================================================

import { setState, getState } from './state.js';
import { showToast } from './components/toast.js';

const BASE_URL = window.location.origin;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

// ── REST Client ────────────────────────────────────────────────────────────

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${path} failed: ${res.status} ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
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
  createSession:  (data) => request('POST', '/api/thinktank/start', { topic: data.topic || data.name || 'New Session', context: data.context }),
  getSession:     () => request('GET', '/api/thinktank/session'),
  sendMessage:    (sessionId, msg) => request('POST', '/api/thinktank/message', msg),
  sendAction:     (sessionId, action) => request('POST', '/api/thinktank/action', action),
  approveSpec:    (sessionId) => request('POST', '/api/thinktank/approve'),
  getHistory:     () => request('GET', '/api/thinktank/history'),

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

  // Events (timeline) — backend returns {"events": [...]}
  getEvents:      (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/api/dashboard/timeline${qs ? '?' + qs : ''}`).then(r => r.events || []);
  },
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
  switch (data.type) {
    case 'agent_update':
      setState({
        agents: state.agents.map(a => a.id === data.agent.id ? { ...a, ...data.agent } : a)
      });
      break;
    case 'bead_update':
      setState({
        beads: state.beads.map(b => b.id === data.bead.id ? { ...b, ...data.bead } : b)
      });
      break;
    case 'new_event':
      setState({ events: [data.event, ...state.events].slice(0, 500) });
      break;
    case 'approval_needed':
      setState({ approvals: [...state.approvals, data.approval] });
      showToast(`Approval needed: ${data.approval.title}`, 'warning');
      break;
    case 'agent_error':
      showToast(`Agent ${data.agentName} error: ${data.message}`, 'error');
      break;
    default:
      break;
  }
}

function handleThinktankMessage(data) {
  const state = getState();
  const tt = { ...state.thinktank };

  switch (data.type) {
    case 'token':
      // Append streaming token to last AI message
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
