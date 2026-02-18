// ==========================================================================
// ARCHITECTURE.JS — Full System Architecture Visualization
// ==========================================================================

import { h } from '../utils/dom.js';
import { getState, subscribe } from '../state.js';

export function renderArchitecture(root) {
  const container = h('div', { class: 'arch-root', id: 'arch-root' });

  // Hero
  container.appendChild(_renderHero());

  // Section 1: Pipeline Flow
  container.appendChild(_renderSection('The Pipeline', 'From your idea to running software — every step', _renderPipeline()));

  // Section 2: Dispatch Sequence
  container.appendChild(_renderSection('What Happens When You Click "Approve"', 'The complete sequence from approval to agents writing code', _renderSequence()));

  // Section 3: Wave Execution
  container.appendChild(_renderSection('Agent Swarm — Wave Execution', 'Agents spawn in waves, respecting dependencies. Max 3 concurrent.', _renderWaves()));

  // Section 4: Architecture Layers
  container.appendChild(_renderSection('System Architecture', 'Every component, from your browser to the agent swarm', _renderLayers()));

  // Section 5: Controls
  container.appendChild(_renderSection('Your Controls', 'Everything you can do from the Command Center', _renderControls()));

  root.appendChild(container);
}

// ── Hero ────────────────────────────────────────────────────────

function _renderHero() {
  const hero = h('div', { class: 'arch-hero' });
  hero.innerHTML = `
    <h1>Baap Architecture</h1>
    <div class="arch-subtitle">AI-Native Application Platform &mdash; Idea to Deployment, Autonomously</div>
  `;
  return hero;
}

function _renderSection(title, desc, content) {
  const section = h('div', { class: 'arch-section' });
  const header = h('div', { class: 'arch-section-title' });
  header.textContent = title;
  section.appendChild(header);
  if (desc) {
    const d = h('p', { style: { color: 'var(--text-tertiary)', fontSize: '13px', margin: '0 0 16px', lineHeight: '1.5' } });
    d.textContent = desc;
    section.appendChild(d);
  }
  section.appendChild(content);
  return section;
}

// ── Pipeline Flow ───────────────────────────────────────────────

function _renderPipeline() {
  const steps = [
    { icon: '\uD83D\uDCA1', label: 'Your Idea',     cls: 'human',  tip: 'You describe what you want to build in plain English' },
    { icon: '\uD83C\uDFAF', label: 'Think Tank',     cls: 'ai',     tip: '4-phase brainstorm: Listen \u2192 Explore \u2192 Scope \u2192 Confirm' },
    { icon: '\uD83D\uDCCB', label: 'Spec-Kit',       cls: 'ai',     tip: 'Requirements, constraints, risks, execution plan accumulate' },
    { icon: '\u2705',       label: 'Approve',        cls: 'human',  tip: 'You review and click "Approve & Start Building"' },
    { icon: '\uD83D\uDCE6', label: 'Beads',          cls: 'system', tip: 'Claude decomposes spec into phased tasks with dependencies' },
    { icon: '\uD83E\uDDE0', label: 'KG Routing',     cls: 'system', tip: 'Ownership KG assigns each task to the best agent' },
    { icon: '\u26A1',       label: 'Spawn',          cls: 'infra',  tip: 'spawn.sh creates git worktree + tmux + Claude Code session' },
    { icon: '\uD83E\uDD16', label: 'Agents Work',    cls: 'infra',  tip: 'Agents read bead spec, write code, run tests, close bead' },
    { icon: '\uD83D\uDD0D', label: 'Review',         cls: 'system', tip: 'Security scan \u2192 test gate \u2192 review agent \u2192 approve' },
    { icon: '\uD83D\uDD00', label: 'Merge',          cls: 'system', tip: 'cleanup.sh merges worktree back to main branch' },
    { icon: '\uD83D\uDE80', label: 'Done',           cls: 'output', tip: 'Feature built, tested, reviewed, and merged' },
  ];

  const flow = h('div', { class: 'pipeline-flow' });

  steps.forEach((step, i) => {
    const node = h('div', { class: 'pipeline-node', title: step.tip });
    const icon = h('div', { class: `pipeline-icon ${step.cls}` });
    icon.textContent = step.icon;
    const label = h('div', { class: 'pipeline-label' });
    label.textContent = step.label;
    node.appendChild(icon);
    node.appendChild(label);
    flow.appendChild(node);

    if (i < steps.length - 1) {
      const arrow = h('div', { class: 'pipeline-arrow' });
      arrow.textContent = '\u2192';
      flow.appendChild(arrow);
    }
  });

  return flow;
}

// ── Dispatch Sequence ───────────────────────────────────────────

function _renderSequence() {
  const steps = [
    {
      color: 'purple', badge: 'human', badgeText: 'YOU',
      title: 'Click "Approve & Start Building"',
      desc: 'POST /api/thinktank/approve \u2014 session status becomes "approved", phase becomes "building"',
    },
    {
      color: 'blue', badge: 'claude', badgeText: 'CLAUDE',
      title: 'Spec-Kit Decomposition',
      desc: 'BeadGenerator sends your spec-kit to Claude: "Break this into phased, implementable tasks." Claude returns a JSON array of 4\u201312 tasks grouped by phase.',
    },
    {
      color: 'green', badge: 'system', badgeText: 'SYSTEM',
      title: 'Bead Creation',
      desc: 'Creates an epic bead + one task bead per task. Sets dependencies: phase 2 tasks depend on all phase 1 tasks. \u2192 bd create, bd dep add',
    },
    {
      color: 'cyan', badge: 'system', badgeText: 'KG',
      title: 'Agent Assignment via Knowledge Graph',
      desc: 'For each bead, AgentAssigner queries the Ownership KG. Scores agents by: domain keyword match, capability overlap, file ownership, and domain hint. Picks the highest scorer.',
    },
    {
      color: 'yellow', badge: 'system', badgeText: 'DISPATCH',
      title: 'Wave 1 — Spawn Unblocked Agents',
      desc: 'DispatchEngine finds all beads with no blockers. Spawns up to 3 agents in parallel. Each gets: git worktree + tmux window + Claude Code session + bead context.',
    },
    {
      color: 'red', badge: 'agent', badgeText: 'AGENTS',
      title: 'Agents Write Code',
      desc: 'Each agent: reads CLAUDE.md \u2192 bd show (task spec) \u2192 queries KG for context \u2192 writes code \u2192 runs tests \u2192 bd close \u2192 updates memory \u2192 cleanup.sh merge.',
    },
    {
      color: 'green', badge: 'system', badgeText: 'GATES',
      title: 'Quality Gate Chain',
      desc: 'Before merge: scan-security.sh (check for secrets) \u2192 test-gate.sh (run tests) \u2192 review-agent.sh (Opus reviews code) \u2192 merge to main if all pass.',
    },
    {
      color: 'yellow', badge: 'system', badgeText: 'WAVE 2+',
      title: 'Dependency Cascade',
      desc: 'When Wave 1 beads close, Wave 2 beads unblock automatically. DispatchEngine detects this and spawns the next wave. Repeats until all beads are done.',
    },
    {
      color: 'purple', badge: 'system', badgeText: 'COMPLETE',
      title: 'Build Complete \u2192 You Get Notified',
      desc: 'All beads closed. Epic marked complete. WebSocket event: DISPATCH_COMPLETE. Toast: "Build complete! 5/5 tasks done." Feature is merged and ready.',
    },
  ];

  const container = h('div', { class: 'seq-container' });

  steps.forEach((step, i) => {
    const row = h('div', { class: 'seq-step' });

    // Timeline dot + line
    const timeline = h('div', { class: 'seq-timeline' });
    const dot = h('div', { class: `seq-dot ${step.color}` });
    timeline.appendChild(dot);
    if (i < steps.length - 1) {
      timeline.appendChild(h('div', { class: 'seq-line' }));
    }
    row.appendChild(timeline);

    // Content
    const content = h('div', { class: 'seq-content' });
    const title = h('div', { class: 'seq-title' });
    const badge = h('span', { class: `seq-badge ${step.badge}` });
    badge.textContent = step.badgeText;
    title.appendChild(badge);
    title.appendChild(document.createTextNode(step.title));
    content.appendChild(title);

    const desc = h('div', { class: 'seq-desc' });
    desc.textContent = step.desc;
    content.appendChild(desc);

    row.appendChild(content);
    container.appendChild(row);
  });

  return container;
}

// ── Wave Execution ──────────────────────────────────────────────

function _renderWaves() {
  const waves = [
    {
      label: 'Wave 1',
      sublabel: 'No deps',
      agents: [
        { name: 'platform-agent', task: 'Create DB schema', cls: 'db', status: 'done' },
        { name: 'identity-agent', task: 'Auth tables', cls: 'auth', status: 'done' },
        { name: 'kg-agent', task: 'Update KG', cls: 'kg', status: 'done' },
      ],
    },
    {
      label: 'Wave 2',
      sublabel: 'Needs Wave 1',
      agents: [
        { name: 'platform-agent', task: 'Build API endpoints', cls: 'api', status: 'running' },
        { name: 'comms-agent', task: 'Notification service', cls: 'comms', status: 'running' },
      ],
    },
    {
      label: 'Wave 3',
      sublabel: 'Needs Wave 2',
      agents: [
        { name: 'platform-agent', task: 'Build UI pages', cls: 'ui', status: 'waiting' },
        { name: 'review-agent', task: 'Code review (Opus)', cls: 'api', status: 'waiting' },
      ],
    },
  ];

  const container = h('div', { class: 'wave-container' });

  waves.forEach((wave, wi) => {
    const row = h('div', { class: 'wave-row' });

    // Label
    const label = h('div', { class: 'wave-label' });
    label.innerHTML = `<div>${wave.label}</div><div style="font-size:10px;color:var(--text-tertiary);font-weight:400">${wave.sublabel}</div>`;
    row.appendChild(label);

    // Track
    const track = h('div', { class: 'wave-track' });
    wave.agents.forEach(agent => {
      const card = h('div', { class: `wave-agent ${agent.cls}` });
      card.innerHTML = `
        <div>
          <div class="wave-agent-name">${agent.name}</div>
          <div class="wave-agent-task">${agent.task}</div>
        </div>
        <div class="wave-agent-status ${agent.status}"></div>
      `;
      track.appendChild(card);
    });
    row.appendChild(track);
    container.appendChild(row);

    // Arrow between waves
    if (wi < waves.length - 1) {
      const arrow = h('div', { class: 'wave-arrow' });
      arrow.innerHTML = `
        <div class="wave-arrow-line"></div>
        <div class="wave-dep-label">beads close \u2192 dependents unblock</div>
        <div class="wave-arrow-line"></div>
      `;
      container.appendChild(arrow);
    }
  });

  // Quality gate
  const gateRow = h('div', { class: 'wave-row', style: { marginTop: '16px' } });
  const gateLabel = h('div', { class: 'wave-label' });
  gateLabel.innerHTML = '<div>Each Merge</div><div style="font-size:10px;color:var(--text-tertiary);font-weight:400">Quality gates</div>';
  gateRow.appendChild(gateLabel);

  const gateTrack = h('div', { class: 'wave-track' });
  const gates = [
    { name: 'scan-security.sh', icon: '\uD83D\uDD12' },
    { name: 'test-gate.sh', icon: '\uD83E\uDDEA' },
    { name: 'review-agent.sh', icon: '\uD83D\uDD0D' },
    { name: 'merge \u2192 main', icon: '\u2705' },
  ];
  gates.forEach((gate, i) => {
    const box = h('div', { class: 'wave-agent api', style: { borderColor: 'var(--accent)' } });
    box.innerHTML = `<div><div class="wave-agent-name">${gate.icon} ${gate.name}</div></div>`;
    gateTrack.appendChild(box);
    if (i < gates.length - 1) {
      const a = h('span', { style: { color: 'var(--text-tertiary)', fontSize: '14px' } });
      a.textContent = '\u2192';
      gateTrack.appendChild(a);
    }
  });
  gateRow.appendChild(gateTrack);
  container.appendChild(gateRow);

  return container;
}

// ── Architecture Layers ─────────────────────────────────────────

function _renderLayers() {
  const layers = h('div', { class: 'arch-layers' });

  // Browser Layer
  layers.appendChild(_layer('browser', 'Browser', 'Your browser at rahil911.duckdns.org:8002', [
    { title: 'Dashboard', detail: 'Agents, beads, events, WebSocket status' },
    { title: 'Kanban', detail: 'Beads as cards: Backlog \u2192 In Progress \u2192 Done' },
    { title: 'Think Tank', detail: '4-phase brainstorm with Claude, Spec-Kit panel' },
    { title: 'Timeline', detail: 'Every event chronologically, filterable' },
    { title: 'Agents', detail: 'Agent cards: status, beads, kill/retry' },
    { title: 'Epics', detail: 'Progress bars, phase breakdowns' },
    { title: 'Approvals', detail: 'Human sign-off for medium-risk actions' },
    { title: 'Architecture', detail: 'This page \u2014 you are here', highlight: true },
  ]));

  // Connector
  layers.appendChild(_connector('WebSocket (real-time) + REST (on demand)'));

  // API Layer
  layers.appendChild(_layer('api', 'API', 'FastAPI server on port 8002', [
    { title: '/api/thinktank/*', detail: 'Sessions, messages, approve, dispatch' },
    { title: '/api/agents/*', detail: 'Status, spawn, kill, retry' },
    { title: '/api/beads/*', detail: 'CRUD, move, comment' },
    { title: '/api/dashboard/*', detail: 'Metrics, timeline events' },
    { title: '/api/approvals/*', detail: 'Approve, reject, approve-all' },
    { title: '/ws + /ws/thinktank', detail: 'Real-time event streaming' },
  ]));

  // Connector
  layers.appendChild(_connector('Python imports'));

  // Services Layer
  layers.appendChild(_layer('services', 'Services', 'The business logic \u2014 where decisions are made', [
    { title: 'ThinkTankService', detail: 'Brainstorm sessions, Claude conversations, approve()', highlight: true },
    { title: 'DispatchEngine', detail: 'Core loop: decompose \u2192 assign \u2192 spawn \u2192 monitor', highlight: true },
    { title: 'BeadGenerator', detail: 'Spec-kit \u2192 phased beads via Claude decomposition' },
    { title: 'AgentAssigner', detail: 'KG-based scoring: keywords + capabilities + file ownership' },
    { title: 'BeadsBridge', detail: 'Session \u2194 epic sync, bead status monitoring' },
    { title: 'ProgressBridge', detail: 'Heartbeat + tmux + bead \u2192 WebSocket events' },
    { title: 'FailureRecovery', detail: 'Classify error, cleanup worktree, retry or escalate' },
    { title: 'EventBus', detail: 'Publish/subscribe for WebSocket broadcasting' },
  ]));

  // Connector
  layers.appendChild(_connector('claude_agent_sdk + bd CLI + KG cache'));

  // Infrastructure Layer
  layers.appendChild(_layer('infra', 'Infrastructure', 'Persistent systems that agents depend on', [
    { title: 'Claude Agent SDK', detail: 'query() with bypassPermissions, max_turns=1' },
    { title: 'Ownership KG', detail: '41KB cache, 9 agents, BFS traversal, <1ms' },
    { title: 'Beads System', detail: 'SQLite DB + CLI: bd create/close/dep/list' },
    { title: 'MariaDB', detail: '200+ tables, passwordless, app database' },
    { title: 'MCP Servers', detail: 'ownership-graph (10 tools) + db-tools (5 tools)' },
    { title: 'Git', detail: 'Worktrees per agent, merge to main via cleanup.sh' },
  ]));

  // Connector
  layers.appendChild(_connector('spawn.sh + tmux + git worktree'));

  // Agent Layer
  layers.appendChild(_layer('agents', 'Agent Swarm', 'Claude Code sessions running autonomously in tmux', [
    { title: 'platform-agent', detail: 'L1: Architecture, DB, API, deployment' },
    { title: 'identity-agent', detail: 'L1: Auth, users, sessions, permissions' },
    { title: 'comms-agent', detail: 'L1: Notifications, email, SMS, push' },
    { title: 'content-agent', detail: 'L1: CMS, media, documents, search' },
    { title: 'engagement-agent', detail: 'L1: Analytics, tracking, campaigns' },
    { title: 'meetings-agent', detail: 'L1: Calendar, scheduling, booking' },
    { title: 'kg-agent', detail: 'L1: Knowledge graph maintenance' },
    { title: 'review-agent', detail: 'Opus: Code review with fresh context' },
  ]));

  return layers;
}

function _layer(type, name, desc, boxes) {
  const layer = h('div', { class: `arch-layer arch-layer-${type}` });

  const header = h('div', { class: 'arch-layer-header' });
  const badge = h('span', { class: `arch-layer-badge badge-${type}` });
  badge.textContent = type.toUpperCase();
  const nameEl = h('span', { class: 'arch-layer-name' });
  nameEl.textContent = name;
  const descEl = h('span', { class: 'arch-layer-desc' });
  descEl.textContent = desc;
  header.appendChild(badge);
  header.appendChild(nameEl);
  header.appendChild(descEl);
  layer.appendChild(header);

  const content = h('div', { class: 'arch-layer-content' });
  boxes.forEach(box => {
    const el = h('div', { class: `arch-box ${box.highlight ? 'highlight' : ''}` });
    el.innerHTML = `
      <div class="arch-box-title">${box.title}</div>
      <div class="arch-box-detail">${box.detail}</div>
    `;
    content.appendChild(el);
  });
  layer.appendChild(content);

  return layer;
}

function _connector(label) {
  const c = h('div', { class: 'arch-connector' });
  c.innerHTML = `
    <div class="arch-connector-arrow">
      <span>\u25BC</span>
      <span style="font-size:10px;color:var(--text-tertiary)">${label}</span>
      <span>\u25BC</span>
    </div>
  `;
  return c;
}

// ── Controls ────────────────────────────────────────────────────

function _renderControls() {
  const controls = [
    { icon: '\uD83D\uDCA1', action: 'New idea', where: 'Think Tank \u2192 "+ New Session"', desc: 'Starts 4-phase brainstorm' },
    { icon: '\uD83C\uDFAF', action: 'Navigate phases', where: 'D / A / G chips or keyboard', desc: 'Dig deeper, Adjust, Go next' },
    { icon: '\u2705', action: 'Approve spec', where: '"Approve & Start Building" button', desc: 'Triggers full autonomous build' },
    { icon: '\uD83D\uDCCA', action: 'Watch progress', where: 'Dashboard / Kanban / Timeline', desc: 'Real-time via WebSocket' },
    { icon: '\uD83D\uDED1', action: 'Kill agent', where: 'Agents view \u2192 Kill button', desc: 'Terminates agent, cleans worktree' },
    { icon: '\uD83D\uDD04', action: 'Retry failed', where: 'Agents view \u2192 Retry button', desc: 'Re-spawns with checkpoint' },
    { icon: '\u274C', action: 'Cancel build', where: 'API: POST /dispatch/{id}/cancel', desc: 'Kills all agents, stops loop' },
    { icon: '\uD83D\uDC4D', action: 'Approve action', where: 'Approvals view', desc: 'Human sign-off for risky actions' },
    { icon: '\u25B6\uFE0F', action: 'Resume session', where: 'Think Tank \u2192 session card', desc: 'Continue paused conversation' },
    { icon: '\uD83D\uDDD1\uFE0F', action: 'Delete session', where: 'Think Tank \u2192 Delete button', desc: 'Removes session + data' },
  ];

  const grid = h('div', { class: 'controls-grid' });
  controls.forEach(c => {
    const card = h('div', { class: 'control-card' });
    card.innerHTML = `
      <div class="control-icon">${c.icon}</div>
      <div class="control-text">
        <div class="control-action">${c.action}</div>
        <div class="control-where">${c.where}</div>
      </div>
    `;
    card.title = c.desc;
    grid.appendChild(card);
  });
  return grid;
}
