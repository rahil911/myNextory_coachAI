# OpenClaw Gateway Architecture — Deep Research Report

**Research Focus**: The Gateway as a WebSocket-based control plane for multi-agent coordination
**Integration Target**: Baap — AI-native multi-agent software development platform
**Date**: 2026-02-14

---

## Executive Summary

OpenClaw's Gateway is a **WebSocket-based control plane** that coordinates all aspects of a personal AI assistant across multiple channels, devices, and agents. It provides:

1. **Centralized Event Bus**: All events (chat, agent runs, tool calls, node events) flow through a single WS server
2. **Session Management**: Persistent session keys map channels/peers to isolated conversation contexts
3. **Plugin/Extension System**: Dynamic loading of tools, hooks, channels, providers via TypeScript plugins
4. **Node Coordination**: Remote device pairing (iOS/Android/macOS) with capability discovery and RPC invoke
5. **Multi-Agent Routing**: Route inbound messages to different agents based on channel/peer/guild/team bindings

**For Baap**: The Gateway pattern could replace or enhance the beads orchestrator daemon by providing:
- Real-time WebSocket event bus for agent coordination (vs polling git-backed beads)
- Multi-level agent swarm coordination (L0→L1→L2→L3) via session routing
- Standardized plugin API for extending agent capabilities
- Node-based execution model for distributed work (similar to Baap's multi-agent swarm)

---

## 1. Architecture Overview

### 1.1 Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Gateway Server                         │
│                  (src/gateway/server.impl.ts)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ WebSocket   │  │  HTTP Server │  │ Control UI   │      │
│  │ (ws://...)  │  │ (REST APIs)  │  │ (Dashboard)  │      │
│  └─────────────┘  └──────────────┘  └──────────────┘      │
│         │                │                  │               │
│         └────────────────┴──────────────────┘               │
│                          │                                  │
│         ┌────────────────┴────────────────┐                │
│         │                                  │                │
│  ┌──────▼──────┐                    ┌─────▼──────┐        │
│  │ Event Bus   │                    │ Session    │        │
│  │ (Broadcast) │◄───────────────────│ Manager    │        │
│  └──────┬──────┘                    └─────┬──────┘        │
│         │                                  │                │
│  ┌──────▼──────┐  ┌──────────────┐  ┌────▼───────┐       │
│  │ Node        │  │ Channel      │  │ Plugin     │       │
│  │ Registry    │  │ Manager      │  │ Registry   │       │
│  └─────────────┘  └──────────────┘  └────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Entry Point and Boot Flow

**File**: `src/entry.ts`

```typescript
// Entry point flow:
1. Normalize environment (NO_COLOR, NODE_OPTIONS)
2. Suppress experimental warnings via respawn trick
3. Parse CLI profile args (--profile flag)
4. Import and run CLI (src/cli/run-main.js)

// The respawn trick ensures clean logs:
if (!hasExperimentalWarningSuppressed()) {
  const child = spawn(
    process.execPath,
    [EXPERIMENTAL_WARNING_FLAG, ...process.execArgv, ...process.argv.slice(1)],
    { stdio: "inherit", env: process.env }
  );
  // Parent exits, child continues
  return true;
}
```

**CLI Routing** (`src/cli/run-main.ts`):
- Loads `.env` silently
- Enforces Node ≥22 runtime check
- Builds Commander program with lazy command registration
- Registers plugin CLI commands dynamically
- Routes to Gateway start command

### 1.3 Gateway Server Startup

**File**: `src/gateway/server.impl.ts` — The heart of OpenClaw.

```typescript
export async function startGatewayServer(
  port = 18789,
  opts: GatewayServerOptions = {}
): Promise<GatewayServer>
```

**Startup Sequence** (~740 lines):

1. **Config Validation**:
   - Load `~/.openclaw/config.json`
   - Migrate legacy schema
   - Auto-enable plugins based on env vars
   - Validate schema with AJV

2. **Plugin Loading** (`loadGatewayPlugins`):
   - Scan bundled, managed, workspace plugin directories
   - Compile TypeScript plugins on-the-fly
   - Register tools, hooks, channels, providers, gateway handlers
   - Build unified plugin registry

3. **Runtime State Creation** (`createGatewayRuntimeState`):
   - HTTP server (Node's `http` or `https`)
   - WebSocket server (`ws` library)
   - Client set (active WS connections)
   - Broadcast function (event dispatcher)
   - Chat run state (active agent sessions)
   - Dedupe buffers, abort controllers

4. **Infrastructure Initialization**:
   - Node registry (paired devices)
   - Channel manager (WhatsApp/Telegram/Slack/Discord/etc.)
   - Cron service (scheduled jobs)
   - Exec approval manager (command gating)
   - Heartbeat runner (presence updates)

5. **Network Services**:
   - Bonjour/mDNS discovery (advertise gateway on LAN)
   - Tailscale Serve/Funnel (optional public exposure)
   - Browser control server (dedicated Chrome/Chromium)
   - Canvas host (visual workspace for macOS/iOS)

6. **Event Subscriptions**:
   - Agent event bus (`onAgentEvent`)
   - Heartbeat events (`onHeartbeatEvent`)
   - Config reload watcher (hot-reload on file change)

7. **WebSocket Handler Attachment** (`attachGatewayWsHandlers`):
   - Bind WS handlers for all gateway methods
   - Auth middleware (token/password)
   - Rate limiting (configurable)
   - Message routing to handler functions

**Key Data Structures**:

```typescript
type GatewayRuntimeState = {
  httpServer: http.Server | https.Server;
  wss: WebSocketServer;
  clients: Set<GatewayWsClient>;
  broadcast: (event: string, payload: unknown, opts?) => void;
  agentRunSeq: Map<string, number>; // sessionId -> run sequence
  chatRunState: {
    buffers: Map<string, string>; // runId -> accumulated text
    deltaSentAt: Map<string, number>; // runId -> last timestamp
    abortedRuns: Set<string>;
  };
  chatAbortControllers: Map<string, AbortController>;
  toolEventRecipients: Set<{ connId: string; runId: string }>;
};
```

---

## 2. Event System

### 2.1 Event Types

**Core Events** (defined in `src/gateway/protocol/schema/`):

| Event Type | Schema | Description |
|------------|--------|-------------|
| `agent` | `AgentEvent` | Agent run lifecycle (start, tool_use, text_delta, finish, error) |
| `chat` | `ChatEvent` | Chat message updates (delta, finish) |
| `tick` | `TickEvent` | Periodic presence heartbeat |
| `heartbeat` | `HeartbeatEvent` | System health metrics |
| `shutdown` | `ShutdownEvent` | Gateway shutdown notification |
| `device.pair.*` | — | Device pairing flow |
| `node.pair.*` | — | Node pairing flow |
| `exec.approval.*` | — | Command approval requests |

**Agent Event Structure**:

```typescript
type AgentEvent = {
  event: "start" | "tool_use" | "text_delta" | "finish" | "error" | "cancelled";
  runId: string;
  sessionKey: string;
  timestamp: number;
  payload?: {
    model?: string;
    thinking?: string;
    toolName?: string;
    toolInput?: unknown;
    delta?: string;
    usage?: { input_tokens: number; output_tokens: number };
    error?: string;
  };
};
```

### 2.2 Pub/Sub Model

**Broadcaster** (`src/gateway/server-broadcast.ts`):

```typescript
function createGatewayBroadcaster(params: { clients: Set<GatewayWsClient> }) {
  let seq = 0;

  const broadcast = (event: string, payload: unknown, opts?: {
    dropIfSlow?: boolean;
    stateVersion?: { presence?: number; health?: number };
  }) => {
    const frame = JSON.stringify({
      type: "event",
      event,
      payload,
      seq: ++seq,
      stateVersion: opts?.stateVersion,
    });

    for (const client of params.clients) {
      // Scope check: some events require specific permissions
      if (!hasEventScope(client, event)) continue;

      // Back-pressure handling
      const slow = client.socket.bufferedAmount > MAX_BUFFERED_BYTES;
      if (slow && opts?.dropIfSlow) continue;
      if (slow) {
        client.socket.close(1008, "slow consumer");
        continue;
      }

      client.socket.send(frame);
    }
  };

  return { broadcast, broadcastToConnIds };
}
```

**Key Features**:
- **Global sequence numbers** for event ordering
- **Scope-based filtering**: Events like `exec.approval.requested` require `operator.approvals` scope
- **Back-pressure handling**: Drop slow consumers or skip events with `dropIfSlow`
- **Targeted broadcasts**: `broadcastToConnIds` for specific clients

### 2.3 Event Dispatch Flow

```
Agent Run Start
      │
      ▼
onAgentEvent (src/infra/agent-events.ts)
      │
      ▼
createAgentEventHandler (src/gateway/server-chat.ts)
      │
      ├─► broadcast("agent", { event: "start", ... })
      │        │
      │        ▼
      │   All connected WS clients receive event
      │
      ├─► nodeSendToSession(sessionKey, "chat", { delta: "..." })
      │        │
      │        ▼
      │   Subscribed nodes receive chat update
      │
      └─► chatRunState.buffers.set(runId, accumulated)
               │
               ▼
          Maintain state for streaming UI
```

**Agent Event Handler** (`src/gateway/server-chat.ts`):

```typescript
function createAgentEventHandler(ctx: {
  broadcast: BroadcastFn;
  nodeSendToSession: NodeSessionSender;
  agentRunSeq: Map<string, number>;
  chatRunState: ChatRunState;
  toolEventRecipients: Set<ToolEventRecipient>;
}): (evt: AgentEvent) => void {
  return (evt) => {
    // Increment run sequence for session
    const sessionId = evt.payload?.sessionId;
    if (sessionId) {
      const seq = (ctx.agentRunSeq.get(sessionId) ?? 0) + 1;
      ctx.agentRunSeq.set(sessionId, seq);
    }

    // Broadcast to all WS clients
    ctx.broadcast("agent", evt, { dropIfSlow: true });

    // Send to subscribed nodes (e.g., mobile devices watching this session)
    const runKey = chatRunState.get(evt.runId);
    if (runKey?.sessionKey) {
      ctx.nodeSendToSession(runKey.sessionKey, "chat", {
        event: evt.event,
        delta: evt.payload?.delta,
      });
    }

    // Accumulate text for streaming
    if (evt.event === "text_delta" && evt.payload?.delta) {
      const buf = ctx.chatRunState.buffers.get(evt.runId) ?? "";
      ctx.chatRunState.buffers.set(evt.runId, buf + evt.payload.delta);
    }
  };
}
```

---

## 3. Session Model

### 3.1 Session Keys

**Structure**: `agent:<agent-id>:<main-key>` or `<channel>:<kind>:<id>`

Examples:
- `agent:default:main` — Default agent's main session
- `telegram:direct:user123` — Telegram DM with user123
- `discord:group:channel456` — Discord group channel
- `node-device789` — Session for a paired node

**Session Store** (`~/.openclaw/sessions.json`):

```json
{
  "agent:default:main": {
    "sessionId": "550e8400-e29b-41d4-a716-446655440000",
    "updatedAt": 1707955200000,
    "thinkingLevel": "high",
    "verboseLevel": true,
    "sendPolicy": "auto",
    "lastChannel": "telegram",
    "lastTo": "+1234567890"
  }
}
```

### 3.2 Session Lifecycle

**Creation** (`src/gateway/session-utils.ts`):

```typescript
export function loadSessionEntry(sessionKey: string) {
  const cfg = loadConfig();
  const canonicalKey = resolveSessionStoreKey({ cfg, sessionKey });
  const agentId = resolveSessionStoreAgentId(cfg, canonicalKey);
  const storePath = resolveStorePath(cfg.session?.store, { agentId });
  const store = loadSessionStore(storePath);

  // Find by exact or case-insensitive match
  const match = findStoreMatch(store, canonicalKey, sessionKey.trim());

  return {
    cfg,
    storePath,
    store,
    entry: match?.entry,
    canonicalKey,
    legacyKey: match?.key !== canonicalKey ? match?.key : undefined
  };
}
```

**Session Routing** (`src/routing/resolve-route.ts`):

OpenClaw uses **bindings** to route inbound messages to specific agents:

```typescript
type ResolveAgentRouteInput = {
  cfg: OpenClawConfig;
  channel: string; // "telegram", "discord", etc.
  accountId?: string; // Multi-account support
  peer?: { kind: "direct" | "group" | "channel"; id: string };
  guildId?: string; // Discord guild
  teamId?: string; // Slack team
  memberRoleIds?: string[]; // Discord roles
};

type ResolvedAgentRoute = {
  agentId: string;
  sessionKey: string; // Internal key for persistence
  mainSessionKey: string; // Convenience alias
  matchedBy: "binding.peer" | "binding.guild" | "default";
};
```

**Binding Example** (config.json):

```json
{
  "bindings": [
    {
      "match": {
        "channel": "discord",
        "account": "default",
        "guild": "123456",
        "roles": ["admin", "moderator"]
      },
      "agent": "ops-bot"
    },
    {
      "match": {
        "channel": "telegram",
        "peer": { "kind": "direct", "id": "user789" }
      },
      "agent": "personal-assistant"
    }
  ]
}
```

### 3.3 Multi-Agent Coordination

**Key Insight**: OpenClaw supports **agent-to-agent communication** via session tools:

- `sessions_list` — Discover active sessions
- `sessions_history` — Fetch transcript from another session
- `sessions_send` — Send message to another session with optional reply-back

This is analogous to **Baap's multi-level agent swarm**:

| OpenClaw Concept | Baap Equivalent |
|------------------|-----------------|
| Session | Bead (git-backed issue) |
| Agent | L0/L1/L2/L3 Agent |
| `sessions_send` | Bead assignment + handoff |
| Session routing | Agent swarm orchestration |

**Example Flow**:

```typescript
// L0 agent receives task from user
const userSession = "telegram:direct:user123";

// L0 agent creates sub-session for L1 agent
await sessions_send({
  to: "agent:code-gen:main",
  message: "Implement login feature with JWT auth",
  replyBack: true, // Ping-pong coordination
  announceStep: "REPLY_SKIP" // Don't broadcast intermediate steps
});

// L1 agent processes, optionally spawns L2 agents
await sessions_send({
  to: "agent:test-writer:main",
  message: "Write tests for login endpoint",
  replyBack: false
});

// When L1 completes, reply back to L0
await sessions_send({
  to: userSession,
  message: "Login feature implemented. PR created: #123"
});
```

---

## 4. Routing: Message Flow Between Channels and Agents

### 4.1 Channel Architecture

**Channel Plugin** (`src/channels/plugins/types.ts`):

```typescript
type ChannelPlugin = {
  id: ChannelId; // "telegram", "discord", etc.
  name: string;
  config: {
    listAccountIds: (cfg: OpenClawConfig) => string[];
    resolveAccount: (cfg: OpenClawConfig, accountId: string) => unknown;
    isEnabled?: (account: unknown, cfg: OpenClawConfig) => boolean;
    isConfigured?: (account: unknown, cfg: OpenClawConfig) => Promise<boolean>;
  };
  gateway?: {
    startAccount: (opts: {
      cfg: OpenClawConfig;
      accountId: string;
      account: unknown;
      runtime: RuntimeEnv;
      abortSignal: AbortSignal;
      log: Logger;
      getStatus: () => ChannelAccountSnapshot;
      setStatus: (patch: ChannelAccountSnapshot) => void;
    }) => Promise<void>;
    stopAccount: (opts: { ... }) => Promise<void>;
  };
};
```

### 4.2 Channel Manager

**File**: `src/gateway/server-channels.ts`

```typescript
export function createChannelManager(opts: {
  loadConfig: () => OpenClawConfig;
  channelLogs: Record<ChannelId, Logger>;
  channelRuntimeEnvs: Record<ChannelId, RuntimeEnv>;
}): ChannelManager {
  const channelStores = new Map<ChannelId, ChannelRuntimeStore>();

  const startChannel = async (channelId: ChannelId, accountId?: string) => {
    const plugin = getChannelPlugin(channelId);
    if (!plugin?.gateway?.startAccount) return;

    const store = getStore(channelId);
    const accountIds = accountId ? [accountId] : plugin.config.listAccountIds(cfg);

    await Promise.all(accountIds.map(async (id) => {
      const abort = new AbortController();
      store.aborts.set(id, abort);

      const task = plugin.gateway.startAccount({
        cfg,
        accountId: id,
        account: plugin.config.resolveAccount(cfg, id),
        runtime: channelRuntimeEnvs[channelId],
        abortSignal: abort.signal,
        log: channelLogs[channelId],
        getStatus: () => getRuntime(channelId, id),
        setStatus: (next) => setRuntime(channelId, id, next),
      });

      store.tasks.set(id, task);
    }));
  };

  return { startChannels, startChannel, stopChannel, getRuntimeSnapshot };
}
```

### 4.3 Inbound Message Routing

**Flow**:

```
Telegram User → Telegram Channel Plugin
                      │
                      ▼
              resolveAgentRoute({ channel: "telegram", peer: { ... } })
                      │
                      ▼
              ┌───────┴────────┐
              │ Binding Match? │
              └───────┬────────┘
                      │
                      ├─► Yes: Use matched agent + session key
                      └─► No:  Use default agent
                      │
                      ▼
              agentCommand({
                message: "Hello",
                sessionKey: "telegram:direct:user123",
                sessionId: "uuid",
                channel: "telegram",
                to: originalPeer
              })
                      │
                      ▼
              Agent processes → Optionally delivers back via channel
```

---

## 5. Plugin/Extension System

### 5.1 Plugin Registry

**File**: `src/plugins/registry.ts`

```typescript
export type PluginRegistry = {
  plugins: PluginRecord[];
  tools: PluginToolRegistration[];
  hooks: PluginHookRegistration[];
  channels: PluginChannelRegistration[];
  providers: PluginProviderRegistration[];
  gatewayHandlers: GatewayRequestHandlers;
  httpHandlers: PluginHttpRegistration[];
  httpRoutes: PluginHttpRouteRegistration[];
  cliRegistrars: PluginCliRegistration[];
  services: PluginServiceRegistration[];
  commands: PluginCommandRegistration[];
  diagnostics: PluginDiagnostic[];
};
```

### 5.2 Plugin Loading

**File**: `src/plugins/loader.ts`

**Loading Sequence**:

1. **Scan Directories**:
   - `~/.openclaw/bundled/` — Built-in plugins
   - `~/.openclaw/managed/` — Installed via ClawHub
   - `~/.openclaw/workspace/plugins/` — User-created plugins

2. **Discover Plugin Manifests**:
   - Look for `PLUGIN.md` or `package.json` with `openclaw-plugin` metadata
   - Extract plugin ID, name, version, kind (tool/channel/provider)

3. **Compile TypeScript** (if needed):
   - Use `esbuild` to bundle `.ts` files into `.js`
   - Cache compiled output in `.openclaw/cache/`

4. **Import and Register**:
   - Dynamically `import()` the plugin module
   - Call plugin's `register(api)` function
   - Plugin uses `api.registerTool()`, `api.registerHook()`, etc.

### 5.3 Plugin API Surface

**File**: `src/plugins/types.ts`

```typescript
export type OpenClawPluginApi = {
  config: {
    get: <T>(key: string) => T | undefined;
    set: (key: string, value: unknown) => void;
  };
  logger: PluginLogger;
  runtime: PluginRuntime;

  registerTool: (
    tool: AnyAgentTool | OpenClawPluginToolFactory,
    opts?: { name?: string; optional?: boolean }
  ) => void;

  registerHook: (
    events: string | string[],
    handler: HookHandler,
    opts?: OpenClawPluginHookOptions
  ) => void;

  registerChannel: (registration: OpenClawPluginChannelRegistration) => void;
  registerProvider: (provider: ProviderPlugin) => void;
  registerGatewayHandler: (method: string, handler: GatewayRequestHandler) => void;
  registerHttpHandler: (handler: OpenClawPluginHttpHandler) => void;
  registerService: (service: OpenClawPluginService) => void;
  registerCliCommand: (command: OpenClawPluginCommandDefinition) => void;
};
```

**Example Plugin** (hypothetical Baap integration):

```typescript
// ~/.openclaw/workspace/plugins/baap-integration/index.ts

import type { OpenClawPlugin } from "openclaw/plugin";

const plugin: OpenClawPlugin = {
  name: "baap-integration",
  version: "1.0.0",

  register: (api) => {
    // Register Baap orchestrator as a tool
    api.registerTool({
      name: "baap_spawn_agent",
      description: "Spawn a Baap agent at specified level (L0/L1/L2/L3)",
      parameters: {
        level: { type: "string", enum: ["L0", "L1", "L2", "L3"] },
        task: { type: "string" },
        context: { type: "object", optional: true }
      },
      execute: async (params) => {
        // Create bead, assign agent, return bead ID
        return { beadId: "bd-123", status: "dispatched" };
      }
    });

    // Register hook to sync Baap beads with OpenClaw sessions
    api.registerHook("agent.finish", async (ctx) => {
      // When agent completes, update Baap bead status
      const beadId = ctx.sessionKey.split(":")[2]; // Extract from session key
      await updateBeadStatus(beadId, "completed");
    });

    // Register gateway method for Baap orchestrator queries
    api.registerGatewayHandler("baap.query", async (req, res) => {
      const beads = await listActiveBeads();
      res.ok({ beads });
    });
  }
};

export default plugin;
```

### 5.4 Hook System

**File**: `src/hooks/types.ts`

```typescript
export type OpenClawHookMetadata = {
  events: string[]; // e.g., ["command:new", "session:start", "agent.finish"]
  export?: string; // Default: "default"
  os?: string[]; // Platform filter
  requires?: {
    bins?: string[]; // Required binaries (e.g., ["git", "docker"])
    env?: string[]; // Required env vars
    config?: string[]; // Required config keys
  };
};

export type Hook = {
  name: string;
  description: string;
  source: "openclaw-bundled" | "openclaw-managed" | "openclaw-workspace" | "openclaw-plugin";
  pluginId?: string;
  filePath: string; // Path to HOOK.md
  baseDir: string;
  handlerPath: string; // Path to handler.ts/js
};
```

**Hook Invocation**:

```typescript
// src/plugins/hook-runner-global.ts

export async function runGlobalHook(
  hookName: string,
  event: string,
  ctx: HookContext
): Promise<void> {
  const hooks = getHooksForEvent(event);

  for (const hook of hooks) {
    if (!isHookEligible(hook, ctx)) continue;

    const handler = await importHookHandler(hook.handlerPath);
    await handler({ event, ...ctx });
  }
}
```

**Example Hook** (Baap bead sync):

```typescript
// ~/.openclaw/workspace/hooks/baap-sync/handler.ts

export default async function handler(ctx: {
  event: string;
  sessionKey: string;
  sessionId: string;
  message?: string;
}) {
  if (ctx.event === "agent.finish") {
    // Extract Baap bead ID from session key
    const beadId = extractBeadId(ctx.sessionKey);

    // Update bead status in Baap git repo
    await exec(`bd close ${beadId} --reason "Agent completed"`);

    // Optionally trigger next agent in swarm
    await exec(`bd ready bd-next --priority 1`);
  }
}
```

---

## 6. Deployment: Docker, Daemon, Launchd

### 6.1 Docker Compose

**File**: `docker-compose.yml`

```yaml
services:
  openclaw-gateway:
    image: ${OPENCLAW_IMAGE:-openclaw:local}
    environment:
      HOME: /home/node
      OPENCLAW_GATEWAY_TOKEN: ${OPENCLAW_GATEWAY_TOKEN}
      CLAUDE_AI_SESSION_KEY: ${CLAUDE_AI_SESSION_KEY}
    volumes:
      - ${OPENCLAW_CONFIG_DIR}:/home/node/.openclaw
      - ${OPENCLAW_WORKSPACE_DIR}:/home/node/.openclaw/workspace
    ports:
      - "${OPENCLAW_GATEWAY_PORT:-18789}:18789"
      - "${OPENCLAW_BRIDGE_PORT:-18790}:18790"
    restart: unless-stopped
    command:
      [
        "node",
        "dist/index.js",
        "gateway",
        "--bind", "${OPENCLAW_GATEWAY_BIND:-lan}",
        "--port", "18789"
      ]
```

**Key Points**:
- Gateway runs on port 18789 (WebSocket + HTTP)
- Bridge on port 18790 (device pairing)
- Bind modes: `loopback`, `lan`, `tailnet`, `auto`
- Persistent volumes for config and workspace

### 6.2 Launchd (macOS)

**File**: `~/Library/LaunchAgents/ai.openclaw.gateway.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.openclaw.gateway</string>

  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/node</string>
    <string>/usr/local/lib/node_modules/openclaw/dist/index.js</string>
    <string>gateway</string>
    <string>--port</string>
    <string>18789</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/user/.openclaw/logs/gateway.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/user/.openclaw/logs/gateway.err</string>
</dict>
</plist>
```

**Commands**:
```bash
launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist
launchctl start ai.openclaw.gateway
launchctl stop ai.openclaw.gateway
launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```

### 6.3 Systemd (Linux)

**File**: `~/.config/systemd/user/openclaw-gateway.service`

```ini
[Unit]
Description=OpenClaw Gateway
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/node /usr/lib/node_modules/openclaw/dist/index.js gateway --port 18789
Restart=on-failure
RestartSec=5s
StandardOutput=append:/home/user/.openclaw/logs/gateway.log
StandardError=append:/home/user/.openclaw/logs/gateway.err

[Install]
WantedBy=default.target
```

**Commands**:
```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-gateway
systemctl --user start openclaw-gateway
systemctl --user status openclaw-gateway
```

---

## 7. Integration Analysis for Baap

### 7.1 Current Baap Architecture

**Beads Orchestrator Daemon**:
- Watches `.beads/` directory for `ready` beads
- Polls git log for changes
- Dispatches agents based on priority/status
- No real-time event bus — relies on git commits

**Multi-Level Agent Swarm**:
- L0: User-facing orchestrator
- L1: Task-specific agents (code-gen, test-writer, etc.)
- L2: Sub-task executors
- L3: Atomic operation handlers

**Communication**:
- Agents write to git-backed beads
- Polling for status updates
- No WebSocket/real-time coordination

### 7.2 Gateway Pattern for Baap

**Proposal**: Replace or enhance beads orchestrator with Gateway-style WebSocket control plane.

```
┌─────────────────────────────────────────────────────────────┐
│                    Baap Gateway                             │
│               (WebSocket Control Plane)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ WebSocket   │  │ Bead Sync    │  │ Agent        │      │
│  │ (ws://...)  │  │ (Git Watch)  │  │ Registry     │      │
│  └─────────────┘  └──────────────┘  └──────────────┘      │
│         │                │                  │               │
│         └────────────────┴──────────────────┘               │
│                          │                                  │
│         ┌────────────────┴────────────────┐                │
│         │                                  │                │
│  ┌──────▼──────┐                    ┌─────▼──────┐        │
│  │ Event Bus   │                    │ Session    │        │
│  │ (Broadcast) │◄───────────────────│ Manager    │        │
│  └──────┬──────┘                    └─────┬──────┘        │
│         │                                  │                │
│  ┌──────▼──────┐  ┌──────────────┐  ┌────▼───────┐       │
│  │ L0 Agents   │  │ L1 Agents    │  │ L2/L3      │       │
│  │ (User Ops)  │  │ (Task Exec)  │  │ Agents     │       │
│  └─────────────┘  └──────────────┘  └────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Specific Integration Points

#### A. Real-Time Event Bus

**Replace**: Git polling for bead status
**With**: WebSocket events

```typescript
// When L0 agent creates sub-task
broadcast("bead.created", {
  beadId: "bd-123",
  level: "L1",
  task: "Implement login feature",
  assignedTo: "code-gen-agent"
});

// L1 agent subscribes to its assigned beads
subscribe("bead.created", (evt) => {
  if (evt.assignedTo === myAgentId) {
    startProcessing(evt.beadId);
  }
});
```

#### B. Session Routing for Multi-Level Swarm

**Replace**: Manual bead assignment
**With**: Session keys + bindings

```json
{
  "bindings": [
    {
      "match": { "level": "L0", "taskType": "feature" },
      "agent": "orchestrator-agent"
    },
    {
      "match": { "level": "L1", "taskType": "codegen" },
      "agent": "code-gen-agent"
    },
    {
      "match": { "level": "L2", "taskType": "test" },
      "agent": "test-writer-agent"
    }
  ]
}
```

**Session Key Format**:
- `baap:L0:user-task-123` — L0 orchestrator session
- `baap:L1:codegen:bd-456` — L1 code-gen session for bead 456
- `baap:L2:test:bd-789` — L2 test-writer session

#### C. Plugin API for Baap-Specific Tools

**Register Beads Commands as Tools**:

```typescript
api.registerTool({
  name: "bead_create",
  description: "Create a new bead for sub-task delegation",
  parameters: {
    title: { type: "string" },
    level: { type: "string", enum: ["L1", "L2", "L3"] },
    priority: { type: "number", optional: true }
  },
  execute: async (params) => {
    const beadId = await exec(`bd create "${params.title}" --level ${params.level}`);
    return { beadId, status: "ready" };
  }
});

api.registerTool({
  name: "bead_status",
  description: "Query bead status",
  parameters: {
    beadId: { type: "string" }
  },
  execute: async (params) => {
    const status = await exec(`bd show ${params.beadId} --format json`);
    return JSON.parse(status);
  }
});
```

#### D. Node-Based Execution for Distributed Work

**Leverage OpenClaw's Node Registry**:

- Register each Baap agent as a "node"
- Use `node.invoke` for remote execution
- Capability discovery: L1 agents advertise "codegen", L2 agents advertise "testing"

```typescript
// Register L1 code-gen agent as a node
await nodePairRequest({
  nodeId: "code-gen-001",
  capabilities: ["codegen", "refactor"],
  platform: "linux"
});

// L0 orchestrator invokes L1 agent remotely
const result = await nodeInvoke({
  nodeId: "code-gen-001",
  method: "codegen.implement",
  params: {
    spec: "Login feature with JWT",
    constraints: ["TypeScript", "Express"]
  }
});
```

### 7.4 Migration Path

**Phase 1**: Hybrid Mode
- Keep git-backed beads as source of truth
- Add Gateway WebSocket server for real-time events
- Sync bead changes to Gateway event bus
- Agents can subscribe to events OR poll git

**Phase 2**: Gateway-First
- Move orchestration logic to Gateway
- Beads become passive data store (like OpenClaw sessions)
- All coordination happens via WebSocket
- Git commits used only for persistence/audit trail

**Phase 3**: Full Integration
- Unified CLI (`baap gateway`, `baap agent`, `baap bead`)
- Plugin ecosystem for custom agent capabilities
- Multi-tenant support via session routing
- Dashboard UI (similar to OpenClaw Control UI)

---

## 8. Key Learnings and Recommendations

### 8.1 Strengths of OpenClaw Gateway

1. **Unified Control Plane**: Single WebSocket server for all coordination
2. **Flexible Session Model**: Supports multi-agent routing, group isolation, per-peer contexts
3. **Rich Plugin API**: Easy to extend with tools, hooks, channels, providers
4. **Robust Event System**: Back-pressure handling, scoped permissions, targeted broadcasts
5. **Production-Ready**: Docker, systemd, launchd support; config hot-reload; auth/rate-limiting

### 8.2 Adoption for Baap

**What to Adopt**:
- WebSocket event bus architecture
- Session key routing with bindings
- Plugin registry for agent capabilities
- Node-based remote execution model

**What to Adapt**:
- Replace "channels" with "bead sources" (git, GitHub Issues, Jira, etc.)
- Swap "agents" with "Baap agent levels" (L0/L1/L2/L3)
- Use beads ID as session key suffix (`baap:L1:bd-123`)

**What to Skip**:
- Voice Wake / Talk Mode (not relevant for dev agents)
- Canvas / A2UI (unless Baap adds visual workspace)
- Multi-channel messaging (Telegram/Slack/etc.) — Baap is CLI-first

### 8.3 Recommended Architecture

```typescript
// Baap Gateway (baap-gateway/src/server.ts)

export async function startBaapGateway(port = 8765) {
  // 1. Load Baap config
  const cfg = loadBaapConfig();

  // 2. Create WebSocket server (reuse OpenClaw's pattern)
  const { wss, clients, broadcast } = createWsServer(port);

  // 3. Load agent registry (L0/L1/L2/L3 agents)
  const agentRegistry = loadAgentRegistry(cfg);

  // 4. Start bead watcher (git monitor)
  const beadWatcher = startBeadWatcher({
    onBeadCreated: (bead) => {
      broadcast("bead.created", bead);
      routeBeadToAgent(bead, agentRegistry);
    },
    onBeadUpdated: (bead) => {
      broadcast("bead.updated", bead);
    }
  });

  // 5. Attach WS handlers
  attachWsHandlers(wss, {
    "bead.create": async (req, res) => {
      const beadId = await createBead(req.params);
      res.ok({ beadId });
    },
    "agent.status": async (req, res) => {
      const status = agentRegistry.getStatus(req.params.agentId);
      res.ok(status);
    },
    "session.send": async (req, res) => {
      // Inter-agent messaging (like OpenClaw's sessions_send)
      const targetSession = resolveSession(req.params.to);
      await sendToAgent(targetSession, req.params.message);
      res.ok({ sent: true });
    }
  });

  return { close: () => wss.close() };
}
```

---

## 9. Code Examples: Key Patterns

### 9.1 WebSocket Request/Response Pattern

```typescript
// Client sends request
ws.send(JSON.stringify({
  type: "request",
  id: "req-123",
  method: "sessions.list",
  params: { agentId: "default" }
}));

// Server responds
ws.send(JSON.stringify({
  type: "response",
  id: "req-123",
  ok: true,
  result: { sessions: [...] }
}));
```

### 9.2 Event Broadcast Pattern

```typescript
// Server broadcasts event to all clients
broadcast("agent", {
  event: "text_delta",
  runId: "run-456",
  sessionKey: "agent:default:main",
  payload: { delta: "Hello" }
});

// Clients receive
{
  type: "event",
  event: "agent",
  payload: { ... },
  seq: 42
}
```

### 9.3 Plugin Registration Pattern

```typescript
export default {
  name: "my-plugin",
  register: (api) => {
    api.registerTool({
      name: "my_tool",
      execute: async (params) => ({ result: "done" })
    });

    api.registerHook("agent.finish", async (ctx) => {
      console.log("Agent finished:", ctx.sessionKey);
    });
  }
};
```

---

## 10. Conclusion

OpenClaw's Gateway provides a **battle-tested architecture** for coordinating multi-agent systems via WebSocket. Its session model, event bus, and plugin ecosystem are directly applicable to Baap's needs:

- **Replace git polling** with real-time WebSocket events
- **Route tasks to agents** using session keys and bindings
- **Enable inter-agent communication** via `sessions_send`
- **Extend capabilities** through plugins

**Next Steps for Baap**:

1. **Prototype Gateway Server**: Start with minimal WS server + bead sync
2. **Implement Session Routing**: Map bead IDs to session keys, route by level
3. **Build Plugin API**: Allow custom tools for agent capabilities
4. **Migrate Orchestrator**: Replace polling daemon with event-driven Gateway
5. **Add Dashboard UI**: Visualize agent swarm status (inspired by OpenClaw Control UI)

**Key Insight**: OpenClaw proves that a WebSocket-based control plane can **scale to hundreds of concurrent agents** while maintaining real-time responsiveness. Baap can adopt this pattern to unlock true multi-agent coordination without git polling bottlenecks.

---

## References

- OpenClaw GitHub: https://github.com/openclaw/openclaw
- OpenClaw Docs: https://docs.openclaw.ai
- Gateway Architecture: `src/gateway/server.impl.ts`
- Protocol Schemas: `src/gateway/protocol/schema/`
- Session Model: `src/gateway/session-utils.ts`
- Routing: `src/routing/resolve-route.ts`
- Plugin System: `src/plugins/registry.ts`

**Research Date**: 2026-02-14
**Repository Snapshot**: main branch (shallow clone)
