// ==========================================================================
// STATE.JS — Minimal Reactive Store (~50 lines)
// Key-level subscriptions: only re-render what changed
// ==========================================================================

// Staleness threshold: data younger than this is considered fresh (ms)
const STALE_MS = 10000;

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
    sessionId: null,
    status: null,
    dispatchStatus: null,
    dispatchEvents: [],
    dispatchHealth: null,
  },
  tory: {
    learnerId: null,
    path: null,       // { profile, recommendations, coach, discovery_count, total_count }
    loading: false,
    error: null,
    feedbackSent: false,
  },
  toryAdmin: {
    cohort: null,
    metrics: null,
    drilldown: null,
    loading: false,
    activeTab: 'cohort',
    sortBy: 'avg_match_score',
    sortDir: 'desc',
    coachFilter: '',
    departmentFilter: '',
  },
  toryWorkspace: {
    users: [],
    totalUsers: 0,
    page: 1,
    totalPages: 0,
    search: '',
    filters: { status: 'has_epp', company: '' },
    companies: [],
    selectedUserId: null,
    selectedUserDetail: null,
    activeTab: 'profile',
    batchSelected: new Set(),
    leftOpen: true,
    rightOpen: true,
    loading: false,
    detailLoading: false,
    agentSessions: [],
  },
  currentView: 'dashboard',
  selectedBeadId: null,
  selectedAgentId: null,
  selectedEventId: null,
  filters: {},
  wsConnected: false,
  // Timestamps of last successful fetch per data key
  _fetchedAt: {},
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

// Mark a data key as freshly fetched
export function markFetched(key) {
  _state._fetchedAt[key] = Date.now();
}

// Check if a data key's data is still fresh (fetched within STALE_MS)
export function isFresh(key) {
  const ts = _state._fetchedAt[key];
  return ts && (Date.now() - ts) < STALE_MS;
}
