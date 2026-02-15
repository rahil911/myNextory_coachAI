# OpenClaw Session Management & Agent Coordination Research

**Research Date**: 2026-02-14
**Target**: OpenClaw session management, inter-agent communication, and Pi agent runtime
**Purpose**: Integration analysis for Baap (AI-native multi-agent software platform)

---

## Executive Summary

OpenClaw provides a sophisticated session management and agent coordination system with the following key capabilities:

1. **Persistent Session Store**: File-based JSONL sessions with SQLite-like locking, pruning, and rotation
2. **Agent-to-Agent Communication**: Three inter-agent tools (`sessions_send`, `sessions_spawn`, `sessions_list`) with permission policies
3. **ACP Bridge**: Agent Client Protocol server for IDE integration (Zed, VS Code) with session mapping
4. **Pi Agent Runtime**: External dependency (`@mariozechner/pi-coding-agent`) providing SessionManager
5. **Command Queue System**: Lane-based serialization for parallel execution with concurrency control
6. **Session Forking**: Branch-based session creation from parent sessions

**Integration Potential for Baap**: HIGH - Multiple complementary patterns, especially session forking and inter-agent messaging.

---

## 1. Session Lifecycle

### Data Model

**SessionEntry** (`src/config/sessions/types.ts`):
```typescript
type SessionEntry = {
  sessionId: string;           // UUID for session file
  sessionFile?: string;        // Path to JSONL file
  updatedAt: number;          // Timestamp for pruning

  // Session metadata
  label?: string;             // Human-readable label
  displayName?: string;       // Formatted display name
  spawnedBy?: string;         // Parent session key (for subagents)

  // Execution state
  systemSent?: boolean;
  abortedLastRun?: boolean;

  // Configuration overrides
  thinkingLevel?: string;
  verboseLevel?: string;
  modelOverride?: string;
  providerOverride?: string;

  // Token tracking
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  totalTokensFresh?: boolean;  // Validity flag

  // Delivery context (for messaging)
  deliveryContext?: DeliveryContext;
  lastChannel?: SessionChannelId;
  lastTo?: string;
  lastAccountId?: string;
  lastThreadId?: string | number;

  // Group chat support
  chatType?: SessionChatType;  // "direct" | "group" | "channel"
  groupId?: string;
  groupChannel?: string;

  // Skills/tools snapshot
  skillsSnapshot?: SessionSkillSnapshot;
  systemPromptReport?: SessionSystemPromptReport;
};
```

### Session Store Architecture

**Storage**: `~/.openclaw/sessions/sessions.json` (configurable per agent)

**Caching**: In-memory cache with TTL (default 45s), mtime-based invalidation

**Locking**: In-process queue-based locking with timeout and stale detection:
- Default timeout: 10s
- Stale lock threshold: 30s
- Per-file lock queue serializes concurrent writers
- Prevents write conflicts without external lock daemon

**Maintenance**:
- **Pruning**: Auto-delete sessions older than 30 days (configurable)
- **Capping**: Keep only 500 most recent sessions (configurable)
- **Rotation**: Rename sessions.json when it exceeds 10MB, keep 3 backups
- **Modes**: `"warn"` (skip if would evict active session) or `"enforce"` (always prune)

### Session Creation

**Resolution Path**:
1. Resolve session key from context (sender, channel, group)
2. Check for reset trigger (`/new`, `/reset`)
3. Load existing session entry or create new UUID
4. Resolve session file path: `~/.openclaw/sessions/<agentId>/<timestamp>_<sessionId>.jsonl`
5. Update session store with metadata patch
6. Return session context

**Session Key Format**:
- Main session: `agent:main:main` (or `global` if scope=global)
- Agent-specific: `agent:<agentId>:<mainKey>`
- Subagent: `agent:<agentId>:subagent:<uuid>`
- Cron/Hook: `agent:<agentId>:cron:<name>`, `agent:<agentId>:hook:<name>`

### Session Forking

**Implementation** (`src/auto-reply/reply/session.ts:forkSessionFromParent`):
```typescript
function forkSessionFromParent(params: {
  parentEntry: SessionEntry;
  agentId: string;
  sessionsDir: string;
}): { sessionId: string; sessionFile: string } | null {
  const parentSessionFile = resolveSessionFilePath(...);
  const manager = SessionManager.open(parentSessionFile);  // Pi runtime
  const leafId = manager.getLeafId();

  if (leafId) {
    // Branch from leaf node
    const sessionFile = manager.createBranchedSession(leafId);
    return { sessionId: manager.getSessionId(), sessionFile };
  }

  // Fallback: create new session with parentSession reference
  const sessionId = crypto.randomUUID();
  const sessionFile = path.join(manager.getSessionDir(), `${timestamp}_${sessionId}.jsonl`);
  fs.writeFileSync(sessionFile, JSON.stringify({
    type: "session",
    version: CURRENT_SESSION_VERSION,
    id: sessionId,
    timestamp,
    cwd: manager.getCwd(),
    parentSession: parentSessionFile  // Link to parent
  }));
  return { sessionId, sessionFile };
}
```

**Relevance to Baap**: This is similar to Baap's L1→L2 agent spawning pattern. OpenClaw forks sessions at the transcript level, while Baap forks git worktrees + tmux panes.

---

## 2. Inter-Agent Communication

OpenClaw provides three agent-to-agent tools:

### `sessions_send`

**Purpose**: Send a message to another session and get synchronous response

**Schema**:
```typescript
{
  sessionKey?: string,      // Direct session key
  label?: string,           // Or resolve by label
  agentId?: string,         // Agent ID for label resolution
  message: string,          // Message to send
  timeoutSeconds?: number   // Response timeout
}
```

**Flow**:
1. Resolve target session (by key or label lookup)
2. Check agent-to-agent policy (configured in `tools.agentToAgent`)
3. Call Gateway `agent` endpoint with message
4. Wait for response (streaming or synchronous)
5. Return assistant text or error

**Agent-to-Agent Policy**:
```typescript
{
  enabled: boolean,
  allow?: {
    from: string[],  // Agent IDs or "*"
    to: string[]     // Agent IDs or "*"
  }[]
}
```

**Sandboxing**: Sandboxed sessions can only send to sessions they spawned (visibility="spawned")

### `sessions_spawn`

**Purpose**: Spawn a background subagent run with isolated session

**Schema**:
```typescript
{
  task: string,               // Task description
  label?: string,             // Session label
  agentId?: string,           // Target agent ID
  model?: string,             // Model override
  thinking?: string,          // Thinking level
  runTimeoutSeconds?: number, // Execution timeout
  cleanup?: "delete" | "keep" // Session cleanup
}
```

**Flow**:
1. Validate agent delegation policy (`subagents.allowAgents`)
2. Create subagent session key: `agent:<agentId>:subagent:<uuid>`
3. Apply model/thinking overrides via Gateway `sessions.patch`
4. Build subagent system prompt with requester context
5. Call Gateway `agent` endpoint with `lane=subagent`, `deliver=false`, `spawnedBy=<requesterKey>`
6. Register subagent run in global registry
7. Return `{ status: "accepted", childSessionKey, runId }`

**Cleanup**: Subagent registry tracks runs and deletes sessions after completion (if cleanup="delete")

### `sessions_list`

**Purpose**: List accessible sessions with filters

**Schema**:
```typescript
{
  kinds?: string[],        // ["main", "group", "cron", "hook", "node", "other"]
  limit?: number,          // Max sessions
  activeMinutes?: number,  // Only sessions active in last N minutes
  messageLimit?: number    // Include last N messages
}
```

**Filters**:
- **Sandbox visibility**: If sandboxed, only show sessions spawned by requester
- **Agent-to-agent policy**: Hide sessions from agents not allowed by policy
- **Kind filtering**: User can request only specific session types

**Relevance to Baap**: Similar to `bd list` for beads, but for sessions. Could replace Baap's manual session tracking.

---

## 3. Agent Runtime (Pi)

**External Dependency**: `@mariozechner/pi-coding-agent`

OpenClaw uses Pi's `SessionManager` for low-level session operations:

### SessionManager API (inferred from usage)

```typescript
class SessionManager {
  static open(sessionFile: string): SessionManager;

  getSessionId(): string;
  getSessionFile(): string;
  getSessionDir(): string;
  getCwd(): string;
  getLeafId(): string | null;

  createBranchedSession(leafId: string): string | null;
}
```

**JSONL Format**:
- Each line is a JSON event (user message, assistant message, tool call, etc.)
- First line is session header with `version`, `id`, `cwd`, optional `parentSession`
- Pi manages branching/forking at the transcript level

**RPC Mode**: Not found in OpenClaw integration. Pi appears to be used as a library, not a separate process.

**Relevance to Baap**: Baap stores session logs in `sessions/<id>/agent_stream.log` (SSE format). Pi's JSONL format is more structured and supports branching. Could adopt Pi's format for better session replay/forking.

---

## 4. Provider Abstraction

**Location**: `docs/providers/index.md`, `src/providers/`

OpenClaw supports 20+ LLM providers through a unified interface:

### Supported Providers

- **Anthropic**: Claude (Sonnet, Opus, Haiku)
- **OpenAI**: GPT-4, o1, o3
- **AWS Bedrock**: Claude, Llama, etc.
- **Google**: Gemini
- **Local**: Ollama, vLLM
- **Gateways**: LiteLLM, OpenRouter, Vercel AI Gateway, Cloudflare AI Gateway
- **Chinese**: Qwen, Moonshot, Zhipu (GLM), Baidu Qianfan

### Abstraction Layers

1. **Gateway Client** (`src/gateway/client.ts`): WebSocket connection to OpenClaw Gateway
2. **Provider-Specific Auth** (`src/agents/auth-profiles/`): OAuth flows, token management, profile switching
3. **Model Normalization**: Provider-specific quirks handled in `src/providers/<provider>-shared.ts`
4. **Streaming Translation**: Provider-specific SSE/streaming formats converted to unified events

**Relevance to Baap**: Baap currently hardcodes Anthropic. Could adopt OpenClaw's provider abstraction to support multiple LLMs (especially for cost optimization with cheaper models for simple tasks).

---

## 5. Process Management

**Location**: `src/process/`

### Command Queue System

**Lanes** (`src/process/lanes.ts`):
```typescript
enum CommandLane {
  Main = "main",           // Auto-reply workflow
  Cron = "cron",           // Scheduled jobs
  Hook = "hook",           // Git hooks
  Subagent = "subagent"    // Background agents
}
```

**Queue Architecture** (`src/process/command-queue.ts`):
- In-process queue per lane
- Configurable concurrency per lane (default 1)
- FIFO execution within lane
- Timeout warnings if queued >2s
- Lane clearing on restart (SIGUSR1 handling)

**Drain Logic**:
```typescript
while (activeTaskIds.size < maxConcurrency && queue.length > 0) {
  const entry = queue.shift();
  const taskId = nextTaskId++;
  activeTaskIds.add(taskId);

  // Execute task
  const result = await entry.task();
  activeTaskIds.delete(taskId);
  entry.resolve(result);

  pump();  // Continue draining
}
```

**Relevance to Baap**: Baap uses tmux panes for parallelism. OpenClaw's lane system could enable in-process concurrency (e.g., parallel bead processing without spawning tmux panes).

### Process Spawning

**Spawn with Fallback** (`src/process/spawn-utils.ts`):
```typescript
spawnWithFallback({
  argv: ["bash", "-c", command],
  options: { stdio: ["pipe", "pipe", "pipe"], cwd },
  fallbacks: [
    { label: "sh", options: { shell: "/bin/sh" } },
    { label: "cmd", options: { shell: "cmd.exe" } }
  ],
  retryCodes: ["EBADF"]  // Retry on specific errors
});
```

**Features**:
- Graceful fallback on spawn errors
- PTY vs pipe stdio selection
- Timeout and abort controller support

**Relevance to Baap**: Baap spawns agents via `tmux new-window`. Could use OpenClaw's fallback logic for cross-platform robustness.

---

## 6. Session Forking Deep Dive

### Use Cases

1. **Subagent Spawning**: Parent session spawns subagent with forked transcript
2. **Branching Conversations**: User creates "what-if" branch from conversation point
3. **Rollback**: Fork from earlier state, discard current branch

### Implementation Details

**Branching Strategy**:
- Pi maintains a DAG of session nodes
- `getLeafId()` returns the latest node in conversation
- `createBranchedSession(leafId)` creates new branch from that node
- Parent-child relationship stored in session header (`parentSession` field)

**File Management**:
- Each branch gets a new JSONL file
- Filenames include timestamp and UUID
- Session directory: `~/.openclaw/sessions/<agentId>/`

**Relevance to Baap's L1→L2 Pattern**:

| Baap L1→L2 | OpenClaw Session Forking |
|------------|--------------------------|
| L1 agent assigns bead to L2 | Parent session spawns subagent session |
| L2 gets git worktree + tmux pane | Subagent gets forked session file |
| L2 commits to feature branch, L1 merges | Subagent writes to own transcript, result returned to parent |
| L2 cleaned up after task | Subagent session deleted if cleanup="delete" |

**Integration Opportunity**: Baap could adopt OpenClaw's session forking for:
- **Transcript continuity**: L2 agent inherits L1's conversation context
- **Faster spawning**: Fork in-memory session instead of `git worktree add`
- **Better cleanup**: Delete session file instead of `rm -rf` worktree

---

## 7. ACP (Agent Client Protocol)

**Location**: `src/acp/`, `docs.acp.md`

### Overview

ACP is a standardized protocol for IDE integration. OpenClaw implements both client and server sides.

### Server Mode

**Command**: `openclaw acp`

**Architecture**:
```
IDE (Zed/VS Code)
  ↓ stdio (NDJSON)
OpenClaw ACP Server (src/acp/server.ts)
  ↓ WebSocket
OpenClaw Gateway
  ↓ HTTP/SSE
OpenClaw Agent
```

**Session Mapping**:
- Each ACP session gets a unique Gateway session key (default: `acp:<uuid>`)
- User can override with `--session agent:main:main`
- ACP metadata can specify `sessionKey`, `sessionLabel`, `resetSession`

**Permission Resolution**:
- Auto-approve safe tools (read, search)
- Prompt user for risky tools (execute, edit, delete)
- Configurable via `DANGEROUS_ACP_TOOLS` list

### Client Mode

**Usage**: Spawn OpenClaw agent from Node.js

```typescript
const { client, agent, sessionId } = await createAcpClient({
  cwd: "/path/to/project",
  serverArgs: ["--session", "agent:main:main"]
});

const response = await client.prompt({
  sessionId,
  prompt: [{ type: "text", text: "Fix the bug" }]
});
```

**Relevance to Baap**: Baap's agent_stream.py could be wrapped in ACP server to enable IDE integration (Cursor, Windsurf, Zed).

---

## 8. Integration Analysis for Baap

### Current Baap Architecture

**Agent Lifecycle**:
1. Bead assigned → `bd assign <bead> <agent>`
2. Onboarding hook spawns tmux pane: `tmux new-window -t baap -n <agent>`
3. Agent runs in git worktree: `git worktree add .worktrees/<agent> <branch>`
4. Agent writes to bead: `bd update <bead> "status"`
5. Agent closes bead: `bd close <bead>`
6. L1 agent merges feature branch, deletes worktree

**Inter-Agent Communication**:
- Beads act as message queue
- `bd search`, `bd list` for discovery
- No direct agent→agent messaging

**Session Management**:
- Sessions stored in `sessions/<id>/`
- SSE streaming logs in `agent_stream.log`
- No session forking or branching

### OpenClaw Patterns That Could Enhance Baap

#### 1. Session Forking for L1→L2 Delegation

**Current Pain Point**: L2 agent starts with empty context, must read bead description

**OpenClaw Solution**:
```typescript
// L1 agent spawns L2 with forked session
const { childSessionKey, runId } = await sessions_spawn({
  task: "Fix authentication bug in user service",
  label: "fix-auth-bug",
  agentId: "backend-specialist",
  cleanup: "delete"
});

// L2 inherits L1's conversation history up to spawn point
// L2 result automatically delivered back to L1
```

**Baap Integration**:
- Store session transcripts in Pi JSONL format
- Fork session when creating L2 agent
- L2 sees full context of bead discussion
- L2's work becomes a branch in session DAG

#### 2. Direct Agent-to-Agent Messaging

**Current Pain Point**: L1 must poll bead status, no real-time updates

**OpenClaw Solution**:
```typescript
// L2 agent sends update to L1
await sessions_send({
  label: "triage-agent",
  message: "Authentication bug fixed, tests passing. Ready for review."
});

// L1 receives message and can respond
```

**Baap Integration**:
- Replace polling with `sessions_send` for status updates
- Enable L1→L2 real-time instructions (e.g., "abort and try different approach")
- Agent-to-agent policy prevents rogue agents from spamming

#### 3. Command Queue for Parallel Bead Processing

**Current Pain Point**: Baap processes beads sequentially in tmux panes

**OpenClaw Solution**:
```typescript
// Set subagent lane to max 5 concurrent
setCommandLaneConcurrency(CommandLane.Subagent, 5);

// Enqueue 10 bead processing tasks
for (const bead of beads) {
  enqueueCommandInLane(CommandLane.Subagent, async () => {
    await processBeadWithAgent(bead);
  });
}
// First 5 execute immediately, rest queued
```

**Baap Integration**:
- Replace tmux-based parallelism with in-process lanes
- Lower overhead (no process spawning)
- Better resource control (global concurrency limit)

#### 4. ACP Bridge for IDE Integration

**Current Pain Point**: Baap is CLI-only, no IDE integration

**OpenClaw Solution**:
```bash
# In Zed/VS Code settings:
{
  "agent_servers": {
    "Baap": {
      "type": "custom",
      "command": "baap",
      "args": ["acp", "--agent", "triage"]
    }
  }
}
```

**Baap Integration**:
- Wrap agent_stream.py in ACP server
- IDE users can spawn Baap agents directly
- Session mapping: each IDE workspace → Baap agent session

#### 5. Session Store with Pruning/Rotation

**Current Pain Point**: `sessions/` directory grows unbounded

**OpenClaw Solution**:
- Auto-prune sessions older than 30 days
- Rotate sessions.json when >10MB
- Keep only 500 most recent sessions

**Baap Integration**:
- Adopt OpenClaw's session store format
- Enable `bd sessions prune` command
- Add session archival to S3/backblaze

---

## 9. Specific Integration Recommendations

### Recommendation 1: Adopt Pi JSONL Session Format

**Why**: Better structure, branching support, tooling ecosystem

**Migration Path**:
1. Install `@mariozechner/pi-coding-agent` in Baap
2. Convert SSE logs to JSONL events during streaming
3. Store sessions in `~/.baap/sessions/<agent>/<timestamp>_<id>.jsonl`
4. Update session replay logic to read JSONL

**Benefits**:
- Session forking for L1→L2 delegation
- Third-party tools (Pi's session viewer)
- Smaller file sizes (structured JSON vs raw logs)

### Recommendation 2: Implement `sessions_*` Tools in Baap

**Why**: Enable agent collaboration without manual bead management

**Implementation**:
```python
# In src/tools/sessions_send.py
async def sessions_send(sessionKey: str, message: str) -> dict:
    # Resolve target agent session
    session = get_session(sessionKey)

    # Check agent-to-agent policy
    if not is_allowed(requester_agent, target_agent):
        return {"status": "forbidden"}

    # Send message via SSE stream
    await session.send_message(message)

    # Wait for response (with timeout)
    response = await session.wait_for_response(timeout=60)
    return {"status": "ok", "response": response}
```

**Benefits**:
- Real-time L1↔L2 communication
- No polling, no manual bead updates
- Easier debugging (see agent conversations in session log)

### Recommendation 3: Replace Tmux with Command Lanes

**Why**: Lower overhead, better resource control

**Implementation**:
```python
# In src/agent_spawner.py
from command_queue import enqueue_in_lane, CommandLane

async def spawn_agent(bead_id: str, agent_name: str):
    await enqueue_in_lane(
        lane=CommandLane.AGENT,
        task=lambda: run_agent_session(bead_id, agent_name)
    )

# Configure concurrency
set_lane_concurrency(CommandLane.AGENT, max_concurrent=5)
```

**Benefits**:
- Process 5 beads in parallel without 5 tmux panes
- Graceful shutdown (drain queue before exit)
- Automatic retry on failure (queue re-enqueue)

### Recommendation 4: Add ACP Server for IDE Integration

**Why**: Enable Cursor, Windsurf, Zed users

**Implementation**:
1. Create `src/acp_server.py` (similar to `agent_stream.py`)
2. Parse ACP NDJSON messages from stdin
3. Translate to agent_stream SSE events
4. Map ACP sessionId → Baap agent session

**Example Usage**:
```bash
# In Cursor settings:
{
  "agent_servers": {
    "Baap Triage": {
      "command": "baap",
      "args": ["acp", "--agent", "triage"]
    }
  }
}
```

**Benefits**:
- IDE users can spawn Baap agents without CLI
- Session continuity across IDE restarts
- Permission prompts for risky operations

---

## 10. Comparison Table: Baap vs OpenClaw

| Feature | Baap | OpenClaw | Integration Opportunity |
|---------|------|----------|-------------------------|
| **Session Storage** | SSE logs in `sessions/<id>/` | JSONL in `~/.openclaw/sessions/<agent>/` | Adopt JSONL for structure, branching |
| **Session Forking** | Manual git worktree per agent | Pi SessionManager branching | Fork sessions for L1→L2 context inheritance |
| **Inter-Agent Comms** | Beads (async, polling) | `sessions_send` (sync, streaming) | Add `sessions_*` tools for real-time messaging |
| **Parallelism** | Tmux panes (process-based) | Command lanes (in-process queue) | Replace tmux with lanes for lower overhead |
| **Agent Spawning** | `tmux new-window` + git worktree | `sessions_spawn` tool | Combine: worktree + forked session |
| **IDE Integration** | None | ACP server (Zed, VS Code) | Add ACP server wrapping agent_stream |
| **Session Pruning** | Manual `rm -rf sessions/` | Auto-prune, rotate, cap | Add `bd sessions prune` command |
| **Provider Support** | Anthropic only | 20+ providers | Abstract LLM calls for multi-provider |
| **Agent Discovery** | `bd list`, `bd search` | `sessions_list` tool | Add `sessions_list` to complement beads |
| **Cleanup** | Manual worktree deletion | Auto-cleanup on subagent completion | Track L2 sessions, auto-cleanup after merge |

---

## 11. Conclusion

OpenClaw's session management and agent coordination patterns are highly complementary to Baap's current architecture. The most impactful integrations would be:

1. **Session Forking** (HIGH IMPACT): Enable L2 agents to inherit L1 context
2. **`sessions_send` Tool** (HIGH IMPACT): Real-time L1↔L2 messaging without beads
3. **Command Lanes** (MEDIUM IMPACT): Parallel bead processing without tmux overhead
4. **ACP Server** (MEDIUM IMPACT): IDE integration for broader user adoption
5. **JSONL Session Format** (LOW IMPACT): Better structure, but requires migration

### Next Steps

1. **Prototype session forking**: Integrate Pi SessionManager for L1→L2 spawning
2. **Implement `sessions_send`**: Add to Baap's tool registry, test with 2-agent workflow
3. **Benchmark lanes vs tmux**: Measure overhead difference for 10 parallel agents
4. **Design ACP integration**: Spec out Baap-specific ACP extensions (bead operations)

### Risk Assessment

- **Migration Risk**: JSONL format requires rewriting session storage (2-3 weeks)
- **Dependency Risk**: Pi agent runtime is external, could break on updates
- **Complexity Risk**: Adding lanes + ACP increases codebase complexity

**Recommendation**: Start with `sessions_send` tool (low risk, high value), then evaluate session forking based on user feedback.

---

**End of Report**
