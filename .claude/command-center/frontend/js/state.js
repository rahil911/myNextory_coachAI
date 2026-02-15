// ==========================================================================
// STATE.JS — Minimal Reactive Store (~50 lines)
// Key-level subscriptions: only re-render what changed
// ==========================================================================

const _state = {
  agents: [],
  beads: [],
  epics: [],
  events: [],
  approvals: [],
  thinktank: {
    phase: 1,
    messages: [],
    specKit: {},
    risks: [],
    sessionId: null
  },
  currentView: 'dashboard',
  selectedBeadId: null,
  selectedAgentId: null,
  selectedEventId: null,
  filters: {},
  wsConnected: false
};

const _listeners = new Map();

export function getState() {
  return _state;
}

export function setState(patch) {
  const prev = {};
  for (const key of Object.keys(patch)) {
    prev[key] = _state[key];
    _state[key] = patch[key];
  }
  // Notify listeners for changed keys
  for (const [key, fns] of _listeners) {
    if (key in patch && _state[key] !== prev[key]) {
      fns.forEach(fn => {
        try { fn(_state[key], prev[key]); }
        catch (err) { console.error(`State listener error [${key}]:`, err); }
      });
    }
  }
}

export function subscribe(key, fn) {
  if (!_listeners.has(key)) _listeners.set(key, new Set());
  _listeners.get(key).add(fn);
  // Return unsubscribe function
  return () => _listeners.get(key).delete(fn);
}

// Convenience: subscribe to multiple keys
export function subscribeMany(keys, fn) {
  const unsubs = keys.map(k => subscribe(k, () => fn(getState())));
  return () => unsubs.forEach(u => u());
}
