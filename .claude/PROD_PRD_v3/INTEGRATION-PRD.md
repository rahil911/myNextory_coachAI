# OpenClaw x Baap Integration PRD

**Author**: Claude Opus 4.6
**Date**: 2026-02-14
**Status**: Draft
**Audience**: Rahil (sole developer), future contributors

---

## 1. Executive Summary

### What OpenClaw Is

OpenClaw is a 150,000+ star open-source personal AI assistant platform built on Claude. It provides a WebSocket-based gateway server, multi-channel messaging (WhatsApp/Telegram/Slack/Discord/Signal/iMessage), persistent session management, a plugin/skills ecosystem, browser automation via Playwright/CDP, cron scheduling, webhook ingress, voice/TTS, and a declarative agent-to-user interface protocol (A2UI). It runs as a daemon (systemd/launchd) with production-grade security (tool sandboxing, prompt injection defense, DM pairing, detect-secrets).

### What Baap Gains

Baap today is a CLI-first, git-backed, tmux-deployed multi-agent platform. It works, but it has five structural gaps that OpenClaw fills:

1. **Real-time coordination**: Agents poll git for bead status updates. OpenClaw's WebSocket event bus replaces polling with sub-10ms events.
2. **Human reach**: Baap is terminal-only. OpenClaw routes agent notifications to WhatsApp/Slack/Telegram, and enables humans to chat with agents from their phone.
3. **Memory intelligence**: Baap's memory is flat markdown with keyword grep. OpenClaw's hybrid BM25+vector search finds semantically similar past incidents.
4. **Proactive agents**: Baap agents only run when dispatched. OpenClaw's cron + webhook system lets agents self-trigger on schedules and external events.
5. **Production deployment**: Baap runs in tmux panes with no auto-restart. OpenClaw demonstrates systemd services with crash recovery, log rotation, and proper lifecycle management.

### Total Estimated Effort and Impact

| Metric | Value |
|--------|-------|
| Total integration effort | 10-14 weeks (one developer) |
| Dev time saved vs building from scratch | 6-9 weeks |
| Monthly operational cost increase | ~$22 (if TTS enabled), otherwise $0 |
| Components affected in Baap | 8 (orchestrator, session manager, context packager, agent stream, Command Center, deploy workflow, skills, memory) |
| Risk level | Medium (modular adoption, no big-bang migration) |

---

## 2. Integration Map

| # | OpenClaw Component | Baap Component It Replaces/Enhances | Integration Type | Priority | Effort | Impact |
|---|---|---|---|---|---|---|
| 1 | **Gateway WebSocket Event Bus** | Beads Orchestrator (git polling daemon) | Adapt | P0 | 2 weeks | Critical -- eliminates polling latency, enables real-time L0-L1-L2 coordination |
| 2 | **Multi-Channel Messaging** (Telegram, WhatsApp, Slack) | Nothing (CLI-only today) | Adopt | P1 | 3 weeks | High -- humans interact with agents from phone, agent alerts go to Slack |
| 3 | **Session Management** (forking, inter-agent send, command lanes) | Session manager + tmux-based parallelism | Adapt | P1 | 2 weeks | High -- L2 agents inherit L1 context, replace tmux overhead |
| 4 | **Skills Platform** (frontmatter, progressive disclosure, bundled scripts) | `.claude/skills/` (flat markdown) | Adapt | P2 | 1 week | Medium -- better skill triggering, reduced context bloat |
| 5 | **A2UI Protocol** (declarative agent-driven UI) | Command Center vanilla JS (Kanban, Timeline, Dashboard) | Inspire | P2 | 3 weeks | Medium -- agents update UI declaratively, eliminate brittle DOM code |
| 6 | **Memory System** (hybrid search, auto-capture, session indexing) | `MEMORY.md` + `patterns.md` (keyword grep only) | Adapt | P1 | 2 weeks | High -- semantic search across past incidents, auto-capture learnings |
| 7 | **Browser Automation** (Playwright/CDP) + Cron + Webhooks | Nothing (no proactive agents, no browser testing) | Adopt | P2 | 2 weeks | Medium -- scheduled health checks, webhook-triggered investigations, E2E testing |
| 8 | **Security & Deployment** (systemd, detect-secrets, audit framework, pairing) | tmux deployment + no secret scanning | Adopt | P0 | 1 week | Critical -- auto-restart on crash, secret scanning in CI, agent access control |

---

## 3. Phase 1: Foundation (Week 1-2)

### 3.1 Replace tmux with systemd Services

**What it is**: Three systemd user services replacing the three tmux panes on India machine.

**Why it matters**: The current `e2e-test` tmux session has no auto-restart, no log rotation, no dependency ordering, and dies on SSH disconnect if linger is not enabled. A single `Ctrl+C` in the wrong pane takes down production.

**What Baap code changes**:

Create three unit files on India machine:

```ini
# ~/.config/systemd/user/baap-bc-analytics.service
[Unit]
Description=BC_ANALYTICS Backend
After=network.target

[Service]
Type=simple
ExecStart=/home/rahil/Projects/BC_ANALYTICS/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
WorkingDirectory=/home/rahil/Projects/BC_ANALYTICS
Restart=on-failure
RestartSec=5s
StandardOutput=append:/home/rahil/logs/bc-analytics.log
StandardError=append:/home/rahil/logs/bc-analytics.err.log

[Install]
WantedBy=default.target
```

```ini
# ~/.config/systemd/user/baap-canvas-backend.service
[Unit]
Description=Decision Canvas Backend
After=network.target baap-bc-analytics.service

[Service]
Type=simple
ExecStart=/home/rahil/Projects/decision-canvas-os/.venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8001
WorkingDirectory=/home/rahil/Projects/decision-canvas-os
Restart=on-failure
RestartSec=5s
StandardOutput=append:/home/rahil/logs/canvas-backend.log
StandardError=append:/home/rahil/logs/canvas-backend.err.log

[Install]
WantedBy=default.target
```

```ini
# ~/.config/systemd/user/baap-canvas-ui.service
[Unit]
Description=Decision Canvas UI
After=network.target baap-canvas-backend.service

[Service]
Type=simple
ExecStart=/usr/bin/npm start
WorkingDirectory=/home/rahil/Projects/decision-canvas-os/ui
Environment="NODE_ENV=production"
Restart=on-failure
RestartSec=5s
StandardOutput=append:/home/rahil/logs/canvas-ui.log
StandardError=append:/home/rahil/logs/canvas-ui.err.log

[Install]
WantedBy=default.target
```

Update `.github/workflows/deploy.yml` to restart systemd services instead of sending tmux keys:

```yaml
- name: Restart services
  run: |
    ssh india-linux << 'EOF'
      cd ~/Projects/decision-canvas-os && git stash && git pull && git stash pop || true
      cd ui && npm run build
      systemctl --user restart baap-canvas-backend.service
      systemctl --user restart baap-canvas-ui.service
    EOF
```

Enable linger: `ssh india-linux "loginctl enable-linger rahil"`

**Success criteria**:
- All three services show `active (running)` via `systemctl --user status`
- Services auto-restart after `kill -9 <pid>`
- Services survive SSH disconnect
- `journalctl --user -u baap-canvas-backend -f` shows structured logs
- Deploy workflow uses `systemctl restart` instead of `tmux send-keys`

### 3.2 Add detect-secrets to CI/CD

**What it is**: Automated secret scanning using the same tool OpenClaw uses (detect-secrets 1.5.0).

**Why it matters**: Baap handles Snowflake credentials, API keys, and bot tokens. A single accidental commit of `credentials.json` to the public repo would be catastrophic.

**What Baap code changes**:

Create `.detect-secrets.cfg`:

```ini
[exclude-files]
pattern = (^|/)pnpm-lock\.yaml$
pattern = (^|/)(dist|vendor|node_modules|\.next)/
pattern = (^|/)\.secrets\.baseline$
pattern = (^|/)sessions/
pattern = (^|/)capsules/
pattern = (^|/)\.beads/
pattern = (^|/)test-results/

[exclude-lines]
pattern = SNOWFLAKE_ACCOUNT.*=.*"example"
pattern = "credentials\.json"
pattern = sk-ant-.*example
```

Generate baseline: `detect-secrets scan > .secrets.baseline`

Add to `.github/workflows/deploy.yml` (or create separate `security.yml`):

```yaml
  detect-secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install detect-secrets==1.5.0
      - run: detect-secrets scan --baseline .secrets.baseline
```

**Success criteria**:
- CI fails if a new secret is introduced in any commit
- No false positives on existing code (baseline tuned)
- `.secrets.baseline` committed to repo

### 3.3 WebSocket Event Bus (Prototype)

**What it is**: A lightweight WebSocket server in Baap's backend that broadcasts bead lifecycle events, replacing git polling.

**Why it matters**: The Beads Orchestrator currently watches `.beads/` via git log, introducing 1-5 second latency and creating race conditions when multiple agents commit simultaneously. A WebSocket event bus delivers events in <10ms.

**What Baap code changes**:

Add a new file `src/api/event_bus.py`:

```python
import asyncio
import json
from typing import Set
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

class EventBus:
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self._seq = 0

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, event: str, payload: dict):
        self._seq += 1
        frame = json.dumps({"type": "event", "event": event, "payload": payload, "seq": self._seq})
        dead = []
        for client in self.clients:
            try:
                await client.send_text(frame)
            except Exception:
                dead.append(client)
        for d in dead:
            self.clients.discard(d)

event_bus = EventBus()
```

Hook into bead creation in the orchestrator:

```python
# When a bead transitions to "ready"
await event_bus.broadcast("bead.ready", {
    "bead_id": bead.id,
    "title": bead.title,
    "priority": bead.priority,
    "assigned_to": bead.assigned_to,
    "level": "L1"
})
```

Add WebSocket endpoint to FastAPI:

```python
@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await event_bus.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        event_bus.disconnect(websocket)
```

**Success criteria**:
- Command Center receives bead events via WebSocket in <50ms
- Event bus handles 10+ concurrent clients without back-pressure issues
- Git-based polling remains as fallback (not removed yet)

---

## 4. Phase 2: Communication Layer (Week 3-4)

### 4.1 Notification Routing to Slack/Telegram

**What it is**: Route agent notification beads to Slack channels and Telegram DMs via OpenClaw Gateway.

**Why it matters**: Today, when an agent completes an investigation or finds an anomaly, the result sits in a capsule file on disk. Nobody sees it until they open the Command Center. With notification routing, critical alerts arrive on the developer's phone within seconds.

**What Baap code changes**:

Install and configure OpenClaw Gateway on India machine as a separate process (port 18789). Configure Slack and Telegram channels in `~/.openclaw/openclaw.json`.

Create `src/notifications/router.py`:

```python
import httpx
from typing import List, Optional

class NotificationRouter:
    def __init__(self, gateway_url: str = "http://localhost:18789"):
        self.gateway_url = gateway_url
        self.client = httpx.AsyncClient()

    async def route(self, title: str, body: str, priority: int, channels: List[str]):
        for channel_target in channels:
            channel, target = channel_target.split(":", 1)
            await self.client.post(
                f"{self.gateway_url}/api/send",
                json={"channel": channel, "to": target, "text": f"**{title}**\n\n{body}"}
            )
```

Create `config/notifications.yaml`:

```yaml
notifications:
  enabled: true
  openclaw_gateway: "http://localhost:18789"
  routes:
    - name: critical-alerts
      priority: [3]
      channels: ["telegram:@rahil_dev", "slack:C_ENGINEERING"]
    - name: agent-status
      event_types: [agent_complete, agent_fail]
      channels: ["slack:C_BAAP_STATUS"]
```

Hook into capsule creation and agent lifecycle events.

**Success criteria**:
- High-priority capsule creation triggers Telegram notification within 5 seconds
- Agent spawn/complete/fail events appear in Slack #baap-status
- Notification routing is configurable via YAML (no code changes to add channels)

### 4.2 Inter-Agent Messaging via sessions_send

**What it is**: Direct agent-to-agent messaging tool, replacing bead-mediated async communication.

**Why it matters**: When L1 dispatches a task to L2, L1 currently creates a bead, L2 polls for it, processes it, updates the bead, and L1 polls again to see the result. This round-trip can take 10-30 seconds. With `sessions_send`, L1 sends a message directly to L2 and gets a synchronous response.

**What Baap code changes**:

Add `sessions_send` as an MCP tool in the agent runtime:

```python
# src/tools/sessions_send.py
async def sessions_send(target_agent: str, message: str, timeout: int = 60) -> dict:
    """Send message to another agent and wait for response."""
    ws = await connect_to_event_bus()
    request_id = str(uuid4())
    await ws.send(json.dumps({
        "type": "request",
        "method": "agent.send",
        "id": request_id,
        "params": {"target": target_agent, "message": message}
    }))
    response = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(response)
```

Register in `.mcp.json` or as a native tool in agent_stream.py.

**Success criteria**:
- L1 agent can send "Fix authentication bug" to L2 and receive "Fixed, tests pass" within the same turn
- Messages logged to session transcript for replay
- Policy enforcement: only allowed agent pairs can message each other

### 4.3 Agent Status Broadcasting to Command Center

**What it is**: Real-time agent lifecycle events (spawn, working, complete, fail) streamed to Command Center via WebSocket.

**Why it matters**: Currently the unified agent page shows events only during a live session. There is no global view of "what are all agents doing right now." Broadcasting agent status events enables a dashboard showing the swarm.

**What Baap code changes**:

Extend `event_bus.py` with agent lifecycle events. Add a new panel to Command Center showing all active agents, their current task, and status.

**Success criteria**:
- Command Center shows a real-time list of active agents with status indicators
- Agent failures trigger both Slack notification and Command Center alert

---

## 5. Phase 3: Intelligence Layer (Month 2)

### 5.1 Hybrid Memory Search

**What it is**: Replace keyword grep on `MEMORY.md` with BM25 + vector hybrid search using SQLite + embeddings.

**Why it matters**: When the triage agent searches for "similar past ROAS incidents," keyword search only finds documents containing the exact word "ROAS." Hybrid search also finds "return on ad spend dropped" and "advertising efficiency declined." OpenClaw's memory-core extension demonstrates this with <50ms search latency on 10k chunks.

**What Baap code changes**:

Add `src/memory/index_manager.py` implementing:
- SQLite FTS5 for BM25 keyword search
- Embedding vectors (OpenAI `text-embedding-3-small`) stored alongside
- Hybrid scoring: `0.7 * vectorScore + 0.3 * bm25Score`
- File watcher on `.claude/agents/*/memory/` with 1.5s debounce
- Embedding cache to avoid re-embedding unchanged chunks

Expose as MCP tool:

```python
memory_search(query="how to handle ROAS drops", max_results=5)
# Returns: ranked snippets with file path + line number citations
```

**Success criteria**:
- `memory_search("advertising efficiency")` returns ROAS-related entries even if the word "ROAS" does not appear in the query
- Search latency <100ms on Baap's current memory corpus
- Markdown files remain source of truth (index is derived, rebuildable)

### 5.2 Auto-Memory Flush Before Compaction

**What it is**: When an agent session nears its context window limit, automatically prompt the agent to write durable notes to `memory/YYYY-MM-DD.md` before compacting.

**Why it matters**: Long investigation sessions (30+ minutes) accumulate critical findings that get lost when the context window compacts. Auto-flush ensures the agent journals its discoveries before they are summarized away.

**What Baap code changes**:

Add compaction hook to `agent_stream.py` that triggers a silent "write findings" turn when token count crosses 80% of context window.

**Success criteria**:
- Daily log files auto-populated during long sessions
- No human intervention required
- Findings preserved in searchable markdown

### 5.3 Skill Platform Upgrade

**What it is**: Add YAML frontmatter to all `.claude/skills/` files with `description`, `requires`, and progressive disclosure via `references/` subdirectories.

**Why it matters**: Baap's skills are flat markdown blobs. The agent loads the entire skill into context even when it only needs the high-level workflow. With frontmatter, the model reads a 100-word description to decide whether to trigger the skill, then loads the body only if triggered. With references, detailed procedures stay out of context until explicitly needed.

**What Baap code changes**:

Migrate all skills to frontmatter format:

```markdown
---
name: investigate-metric
description: Full investigation protocol for metric breaches. Use when a metric
  crosses threshold or shows anomaly. Walks causal graph, checks data quality,
  forecasts impact, recommends actions.
metadata:
  baap:
    requires:
      bins: [bd]
      config: [snowflake.enabled]
---

# Investigate Metric

## Quick Reference
1. Validate data quality -> [references/data-quality.md](references/data-quality.md)
2. Walk causal graph -> [references/causal-analysis.md](references/causal-analysis.md)
...

## Core Workflow
[500 lines of high-level procedure]
```

Split `investigate-metric` (currently the largest skill) into core + 4 reference files.

**Success criteria**:
- All 5 skills have valid YAML frontmatter
- `investigate-metric` core SKILL.md is <500 lines
- Agent context usage drops by 30-50% when skills are not triggered

---

## 6. Phase 4: Automation Layer (Month 3)

### 6.1 Cron-Scheduled Health Checks

**What it is**: Use OpenClaw's cron service to run proactive agent checks on a schedule.

**Why it matters**: Today, Baap only investigates when a human creates a bead. With cron, agents can proactively check metrics every 4 hours, run test suites daily, and audit dependencies weekly -- catching issues before humans notice.

**What Baap code changes**:

Configure cron jobs in OpenClaw Gateway config:

```json
{
  "cron": {
    "enabled": true,
    "jobs": [
      {
        "name": "Morning metrics triage",
        "schedule": { "kind": "cron", "expr": "0 7 * * *", "tz": "America/Chicago" },
        "sessionTarget": "isolated",
        "payload": {
          "kind": "agentTurn",
          "message": "Check overnight revenue metrics, investigate anomalies, create Decision Capsule if breach detected"
        },
        "delivery": { "mode": "announce", "channel": "slack", "to": "channel:C_BAAP_STATUS" }
      }
    ]
  }
}
```

Implement a thin adapter in Baap's backend that receives cron-triggered agent runs and dispatches to the existing agent_stream pipeline.

**Success criteria**:
- Morning triage runs at 7 AM daily without human intervention
- Anomalies generate Decision Capsules automatically
- Results posted to Slack

### 6.2 Webhook-Triggered Investigations

**What it is**: HTTP webhook endpoints that trigger agent investigations from external systems (GitHub, BC_ANALYTICS metric breaches, CI/CD failures).

**Why it matters**: When BC_ANALYTICS detects a ROAS breach, it currently has no way to tell Baap to investigate. A webhook endpoint closes this loop: BC_ANALYTICS calls `POST /hooks/agent` with the breach details, and Baap auto-spawns an investigation.

**What Baap code changes**:

Add `POST /api/webhooks/investigate` to FastAPI:

```python
@app.post("/api/webhooks/investigate")
async def webhook_investigate(payload: dict, x_webhook_token: str = Header(None)):
    if x_webhook_token != WEBHOOK_SECRET:
        raise HTTPException(401)
    await event_bus.broadcast("bead.auto_create", {
        "title": payload["title"],
        "metric": payload["metric"],
        "source": "webhook",
        "priority": payload.get("priority", 2)
    })
    return {"status": "dispatched"}
```

Configure BC_ANALYTICS to call this webhook when a metric breaches its threshold.

**Success criteria**:
- BC_ANALYTICS ROAS breach -> webhook -> Baap investigation -> capsule -> Slack notification, all within 5 minutes
- Webhook authenticated via bearer token
- Rate-limited to prevent abuse

### 6.3 Browser Automation for E2E Validation

**What it is**: Use OpenClaw's Playwright/CDP integration to give agents the ability to interact with web UIs during testing.

**Why it matters**: When an agent generates or modifies a UI component, there is no automated way to verify the visual result. Browser automation lets the agent screenshot the running app, validate it matches expectations, and catch visual regressions.

**What Baap code changes**:

Install Playwright on India machine. Configure OpenClaw browser profile. Agents can use the `browser` tool to navigate, snapshot, and screenshot.

**Success criteria**:
- Agent can navigate to `http://localhost:3500`, take a screenshot, and validate the Decision Canvas renders correctly
- Screenshots stored alongside capsules for visual audit trail

### 6.4 Voice (Future, P3)

Voice interaction via TTS/STT is a low-priority enhancement. It would enable voice-based bead creation via Telegram voice notes and audio narration of Decision Capsules. Defer until Phases 1-3 are stable.

---

## 7. Architecture: Before vs After

### Before (Current Baap)

```
Human (terminal only)
  |
  v
Baap CLI --> creates bead --> writes to .beads/ (git)
                                  |
                            [1-5s polling]
                                  |
                                  v
                          Beads Orchestrator (watches git log)
                                  |
                                  v
                          tmux new-window --> L1 Agent (tmux pane)
                                                |
                                          git worktree add
                                                |
                                          L2 Agent (another tmux pane)
                                                |
                                          writes to bead (git commit)
                                                |
                                          [L1 polls for completion]
                                                |
                                          L1 merges, closes bead

Deployment: tmux session "e2e-test" on India machine
  Pane 0: uvicorn BC_ANALYTICS :8000
  Pane 1: uvicorn decision-canvas-os :8001
  Pane 2: npm start :3500

Notifications: None (results sit in capsule files)
Memory: MEMORY.md (keyword grep)
Proactive agents: None
```

### After (Baap + OpenClaw)

```
Human (terminal + WhatsApp + Slack + Telegram + Command Center)
  |
  v
Baap CLI / OpenClaw Channel Adapter
  |
  v
WebSocket Event Bus (:8001/ws/events)
  |
  +---> Beads Orchestrator (subscribes to bead.ready events)
  |       |
  |       v
  |     Agent Spawner (command lanes, in-process concurrency)
  |       |
  |       +---> L1 Agent (sessions_send to L2)
  |       |       |
  |       |       v
  |       |     L2 Agent (forked session, inherits L1 context)
  |       |       |
  |       |       v
  |       |     sessions_send(result) back to L1
  |       |
  |       +---> Notification Router --> Slack / Telegram / WhatsApp
  |
  +---> Command Center (subscribes to all events)
  |
  +---> Cron Service (scheduled health checks)
  |
  +---> Webhook Ingress (GitHub PR, metric breaches, CI failures)

Deployment: systemd user services on India machine
  baap-bc-analytics.service    :8000 (auto-restart, log rotation)
  baap-canvas-backend.service  :8001 (auto-restart, depends on bc-analytics)
  baap-canvas-ui.service       :3500 (auto-restart, depends on backend)
  openclaw-gateway.service     :18789 (channels, cron, webhooks)

Notifications: Slack (#baap-status, #baap-alerts), Telegram DM, WhatsApp
Memory: Hybrid BM25 + vector search, auto-capture, daily logs
Proactive agents: Cron (daily triage, 4h health checks, weekly audits)
```

---

## 8. Risk Assessment

### 8.1 Dependency Risk on OpenClaw

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| OpenClaw breaks on update | Medium | Medium | Pin to specific version. OpenClaw is MIT-licensed; can fork if abandoned. |
| OpenClaw's API changes | Low | Low | Baap uses OpenClaw as a sidecar (HTTP/WS API), not as a library. API surface is stable. |
| OpenClaw project abandoned | Very Low | Low | 150k+ stars, active community. If it dies, the patterns are documented here and can be reimplemented. |

**Key insight**: Baap does not import OpenClaw code. It runs OpenClaw as a separate process and communicates via HTTP/WebSocket. This means OpenClaw can be replaced with any message routing system without touching Baap core.

### 8.2 Migration Complexity

| Migration | Complexity | Reversibility |
|-----------|-----------|---------------|
| tmux -> systemd | Low | High (can go back to tmux in 5 minutes) |
| detect-secrets | Very Low | High (just remove CI step) |
| Event bus (alongside git polling) | Medium | High (git polling remains as fallback) |
| Notification routing | Low | High (just disable in config) |
| Hybrid memory search | Medium | Medium (requires keeping SQLite index in sync) |
| Skill frontmatter | Low | High (frontmatter is backward-compatible) |
| A2UI migration | High | Low (requires rewriting Command Center components) |

### 8.3 Operational Risks

| Risk | Mitigation |
|------|-----------|
| OpenClaw Gateway crashes on India machine | systemd auto-restarts. Gateway is stateless (sessions in files). |
| WebSocket event bus loses messages | Events are ephemeral (UI state). Beads remain git-backed for durability. |
| Slack/Telegram bot token leaked | detect-secrets catches in CI. Tokens stored in env vars, not config files. |
| Agent-to-agent messaging creates infinite loop | Policy enforcement: agent pairs must be explicitly allowlisted. Timeout on sessions_send (default 60s). |
| Memory index grows unbounded | Auto-prune sessions >30 days. Cap at 500 entries. Embedding cache limits. |

### 8.4 Performance Risks

| Concern | Measured Performance | Verdict |
|---------|---------------------|---------|
| WebSocket event bus latency | <10ms per broadcast | Acceptable |
| Hybrid memory search | <50ms on 10k chunks | Acceptable |
| OpenClaw Gateway startup | ~2-3s cold start | Acceptable (daemon stays running) |
| Notification routing | <5s end-to-end | Acceptable |
| Embedding cost | ~$0.02 per 1000 chunks (OpenAI) | Acceptable (~$5/month for Baap's corpus) |

---

## 9. What NOT to Adopt

### 9.1 Voice Wake / Talk Mode

OpenClaw has a sophisticated voice system with wake words, continuous listening, and TTS narration. Baap is a developer tool used on a server; nobody is talking to it. Voice adds complexity (audio processing, TTS API costs) with near-zero value for Baap's use case.

**If this changes**: Revisit when Baap has a mobile app or warehouse IoT use case.

### 9.2 Canvas / Native App (WKWebView)

OpenClaw's Canvas runs in a macOS WKWebView panel. Baap's Command Center is a web app at `:3500` served over HTTP. There is no native app and no plan for one. The Canvas host server, URL scheme (`openclaw-canvas://`), and native message bridges are irrelevant.

**What to take instead**: The A2UI *protocol* (JSON messages) is valuable, even without the native Canvas shell. Use it to drive the Command Center via WebSocket.

### 9.3 Node System (Remote Device Pairing)

OpenClaw's node system pairs iPhones, Raspberry Pis, and remote machines for distributed execution. Baap has exactly one production machine (India) and one dev machine (Mac). Multi-device pairing adds complexity with no payoff.

**If this changes**: Revisit if Baap scales to multiple production servers.

### 9.4 Multi-Provider LLM Abstraction

OpenClaw supports 20+ LLM providers (OpenAI, Gemini, Ollama, etc.) through a unified provider interface. Baap is deeply integrated with Claude Code (Anthropic API). Abstracting the provider layer would add complexity without clear benefit, since Baap's value comes from Claude Code's specific capabilities (file editing, bash, tool use), not from model-agnostic prompting.

**If this changes**: Revisit if cost optimization requires routing simple tasks to cheaper models (Haiku for L2+ agents).

### 9.5 DM Pairing for Agent Access Control

OpenClaw's DM pairing (8-character codes, 60-minute TTL) is designed for public-facing bots where unknown strangers might DM you on Telegram. Baap is a private, single-user system. The pairing flow adds friction with no security benefit since the only user is Rahil.

**What to take instead**: If Baap becomes multi-user, adopt the pairing pattern. For now, use simple bearer token auth on the webhook endpoints.

### 9.6 Full Plugin Architecture

OpenClaw's plugin system (PluginRegistry, PluginRuntime, dynamic TypeScript compilation, plugin lifecycle) is engineering overkill for a one-developer project. Baap's extension point is MCP servers, which are simpler and already working.

**What to take instead**: The *concept* of skills declaring their requirements via frontmatter (bins, env, config). Skip the dynamic plugin loading machinery.

---

## 10. Concrete Next Steps

### Step 1: Deploy systemd services on India machine (Day 1)

```bash
# SSH to India
ssh india-linux

# Create log directory
mkdir -p ~/logs

# Create service files (see Section 3.1 for content)
mkdir -p ~/.config/systemd/user
# Write baap-bc-analytics.service
# Write baap-canvas-backend.service
# Write baap-canvas-ui.service

# Enable linger
loginctl enable-linger rahil

# Reload, enable, start
systemctl --user daemon-reload
systemctl --user enable baap-bc-analytics baap-canvas-backend baap-canvas-ui
systemctl --user start baap-bc-analytics baap-canvas-backend baap-canvas-ui

# Verify
systemctl --user status baap-bc-analytics baap-canvas-backend baap-canvas-ui

# Kill tmux session (the old way)
tmux kill-session -t e2e-test
```

**Files to create on India machine**:
- `~/.config/systemd/user/baap-bc-analytics.service`
- `~/.config/systemd/user/baap-canvas-backend.service`
- `~/.config/systemd/user/baap-canvas-ui.service`

### Step 2: Add detect-secrets to CI (Day 1)

```bash
# On Mac (dev machine)
cd /Users/rahilharihar/Projects/decision-canvas-os

# Install detect-secrets
pip install detect-secrets==1.5.0

# Generate baseline
detect-secrets scan > .secrets.baseline

# Review and mark false positives
detect-secrets audit .secrets.baseline

# Create config file
cat > .detect-secrets.cfg << 'EOF'
[exclude-files]
pattern = (^|/)pnpm-lock\.yaml$
pattern = (^|/)(dist|vendor|node_modules|\.next)/
pattern = (^|/)\.secrets\.baseline$
pattern = (^|/)sessions/
pattern = (^|/)capsules/
pattern = (^|/)\.beads/
pattern = (^|/)test-results/
pattern = .*\.(png|jpg|jpeg|gif|svg|ico|har)$

[exclude-lines]
pattern = SNOWFLAKE.*example
pattern = "credentials\.json"
EOF

# Add scan step to deploy workflow
# Edit .github/workflows/deploy.yml
```

**Files to create/edit**:
- `/Users/rahilharihar/Projects/decision-canvas-os/.detect-secrets.cfg`
- `/Users/rahilharihar/Projects/decision-canvas-os/.secrets.baseline`
- `/Users/rahilharihar/Projects/decision-canvas-os/.github/workflows/deploy.yml` (add detect-secrets step)

### Step 3: Create WebSocket event bus (Day 2-3)

```bash
# Create the event bus module
# File: /Users/rahilharihar/Projects/decision-canvas-os/src/api/event_bus.py
# (See Section 3.3 for implementation)

# Add WebSocket endpoint to main.py
# Add /ws/events route

# Test with wscat
npm install -g wscat
wscat -c ws://localhost:8001/ws/events
```

**Files to create/edit**:
- `/Users/rahilharihar/Projects/decision-canvas-os/src/api/event_bus.py`
- `/Users/rahilharihar/Projects/decision-canvas-os/src/api/main.py` (add WS route)

### Step 4: Add frontmatter to skills (Day 4)

```bash
# Edit each skill file to add YAML frontmatter
# Files:
#   .claude/skills/investigate-metric/SKILL.md
#   .claude/skills/trace-lineage/SKILL.md
#   .claude/skills/root-cause-analysis/SKILL.md
#   .claude/skills/forecast-impact/SKILL.md
#   .claude/skills/recommend-action/SKILL.md
```

For each, add frontmatter block with `name`, `description`, and `metadata.baap.requires`. See Section 5.3 for the template.

**Files to edit**:
- `/Users/rahilharihar/Projects/decision-canvas-os/.claude/skills/investigate-metric/SKILL.md`
- `/Users/rahilharihar/Projects/decision-canvas-os/.claude/skills/trace-lineage/SKILL.md`
- `/Users/rahilharihar/Projects/decision-canvas-os/.claude/skills/root-cause-analysis/SKILL.md`
- `/Users/rahilharihar/Projects/decision-canvas-os/.claude/skills/forecast-impact/SKILL.md`
- `/Users/rahilharihar/Projects/decision-canvas-os/.claude/skills/recommend-action/SKILL.md`

### Step 5: Install OpenClaw Gateway on India machine (Day 5)

```bash
ssh india-linux

# Install Node 22 (if not already)
# Install OpenClaw
npm install -g openclaw@latest

# Run onboarding (quickstart mode, loopback only)
openclaw onboard --flow quickstart

# Configure Slack channel (for notifications)
# Edit ~/.openclaw/openclaw.json to add Slack bot token

# Install as systemd service
openclaw gateway install --daemon

# Verify
systemctl --user status openclaw-gateway
curl http://localhost:18789/health
```

**Config to create on India machine**:
- `~/.openclaw/openclaw.json` (gateway config with Slack channel)
- `~/.config/systemd/user/openclaw-gateway.service` (auto-created by `openclaw gateway install --daemon`)

---

## Appendix: Key File References

### OpenClaw Source Files (for reference when implementing)

| Pattern | OpenClaw File | Baap Equivalent |
|---------|--------------|-----------------|
| WebSocket event bus | `src/gateway/server-broadcast.ts` | `src/api/event_bus.py` |
| Session management | `src/gateway/session-utils.ts` | `src/session_manager.py` |
| Plugin/tool registration | `src/plugins/registry.ts` | `.mcp.json` |
| Channel adapter | `src/channels/plugins/types.plugin.ts` | `src/notifications/router.py` |
| Security audit | `src/security/audit.ts` | (new) `src/security/audit.py` |
| Prompt injection defense | `src/security/external-content.ts` | (new) `src/security/content_filter.py` |
| Cron service | `src/cron/service/` | OpenClaw Gateway config |
| Browser control | `src/browser/pw-session.ts` | MCP Playwright tool |
| Memory search | `extensions/memory-core/` | (new) `src/memory/index_manager.py` |
| Skill loading | `src/agents/skills/` | `src/context_packager.py` |
| A2UI protocol | `src/a2ui/` | (future) Command Center WebSocket messages |
| Daemon management | `src/daemon/systemd.ts` | systemd unit files (manual) |

### Research Reports Index

| Report | Key Takeaways for Baap |
|--------|----------------------|
| `01-gateway-architecture.md` | WebSocket event bus pattern, session routing, plugin API |
| `02-multi-channel.md` | Channel adapter pattern, notification routing, MsgContext normalization |
| `03-sessions-coordination.md` | Session forking for L1->L2, sessions_send tool, command lanes |
| `04-skills-tools.md` | Frontmatter-driven skills, progressive disclosure, MCP skill wrappers |
| `05-canvas-a2ui.md` | A2UI protocol for declarative agent-driven UI |
| `06-memory-persistence.md` | Hybrid BM25+vector search, auto-capture, compaction flush |
| `07-browser-automation.md` | Browser E2E testing, cron scheduling, webhook ingress, TTS |
| `08-security-deployment.md` | detect-secrets, systemd services, security audit, multi-agent safety |
