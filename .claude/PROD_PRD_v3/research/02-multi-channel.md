# OpenClaw Multi-Channel Messaging System Research

**Research Date**: 2026-02-14
**Research Focus**: Multi-channel architecture and integration opportunities for Baap AI platform

---

## Executive Summary

OpenClaw implements a sophisticated **plugin-based multi-channel messaging architecture** supporting 15+ platforms (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Matrix, MS Teams, Google Chat, IRC, and more). The system uses a **unified adapter pattern** where each channel plugin implements a common interface (`ChannelPlugin<ResolvedAccount>`), enabling consistent message routing, security policies, and action handling across all channels.

**Key Integration Opportunities for Baap**:
1. Route agent notification beads to WhatsApp/Slack/Telegram
2. Enable human-agent conversations through messaging apps instead of CLI-only
3. Stream agent status updates to Slack channels for team visibility
4. Connect Baap Command Center as a "web channel" in the OpenClaw framework

---

## 1. Channel Abstraction Layer

### 1.1 Core Plugin Interface

Every channel implements `ChannelPlugin<ResolvedAccount, Probe, Audit>` with these required components:

```typescript
// From src/channels/plugins/types.plugin.ts
type ChannelPlugin<ResolvedAccount = any, Probe = unknown, Audit = unknown> = {
  id: ChannelId;                          // "telegram", "whatsapp", "slack", etc.
  meta: ChannelMeta;                      // UI labels, docs paths, system icons
  capabilities: ChannelCapabilities;      // Supported features (polls, threads, reactions)

  // Core adapters (required)
  config: ChannelConfigAdapter<ResolvedAccount>;

  // Optional adapters
  onboarding?: ChannelOnboardingAdapter;  // CLI setup wizard
  pairing?: ChannelPairingAdapter;        // DM pairing for unknown senders
  security?: ChannelSecurityAdapter;      // DM/group policies
  outbound?: ChannelOutboundAdapter;      // Message sending
  actions?: ChannelMessageActionAdapter;  // Tool actions (send, react, etc.)
  directory?: ChannelDirectoryAdapter;    // Contact/group lookups
  threading?: ChannelThreadingAdapter;    // Thread/reply behavior
  messaging?: ChannelMessagingAdapter;    // Target normalization
  mentions?: ChannelMentionAdapter;       // @mention stripping
  groups?: ChannelGroupAdapter;           // Group-specific logic
  gateway?: ChannelGatewayAdapter;        // Long-lived connections
  agentTools?: ChannelAgentToolFactory;   // Channel-specific AI tools
}
```

**Key Design Pattern**: Channels are **composition over inheritance**. Each adapter is optional, with sensible defaults. This allows extension channels to only implement what they need.

### 1.2 Channel Registration & Discovery

Channels register via **plugin discovery** at runtime:

1. **Bundled channels**: Loaded from `extensions/` directory (Telegram, WhatsApp, Slack, Discord, Signal)
2. **External plugins**: Discovered from:
   - `~/.openclaw/extensions/` (user-installed)
   - `./extensions/` (workspace-level)
   - npm packages with `openclaw.extensions` in package.json metadata
3. **Plugin registry**: Singleton global registry (`requireActivePluginRegistry()`) holds all loaded channels

```typescript
// From src/channels/plugins/index.ts
function listChannelPlugins(): ChannelPlugin[] {
  const registry = requireActivePluginRegistry();
  return registry.channels.map(entry => entry.plugin);
}

function getChannelPlugin(id: ChannelId): ChannelPlugin | undefined {
  return listChannelPlugins().find(plugin => plugin.id === id);
}
```

**Extension Example** (from `extensions/telegram/src/channel.ts`):

```typescript
export const telegramPlugin: ChannelPlugin<ResolvedTelegramAccount, TelegramProbe> = {
  id: "telegram",
  meta: {
    label: "Telegram",
    selectionLabel: "Telegram Bot API",
    docsPath: "/channels/telegram",
    blurb: "Telegram Bot API integration"
  },
  capabilities: {
    chatTypes: ["direct", "group", "channel", "thread"],
    reactions: true,
    threads: true,
    media: true,
    polls: true,
    nativeCommands: true,
    blockStreaming: true
  },
  // ... adapters
};
```

### 1.3 Capabilities Declaration

Each channel declares what features it supports:

```typescript
// From src/channels/plugins/types.core.ts
type ChannelCapabilities = {
  chatTypes: Array<ChatType | "thread">;  // "direct", "group", "channel", "thread"
  polls?: boolean;                        // Supports poll creation
  reactions?: boolean;                    // Emoji reactions
  edit?: boolean;                         // Message editing
  unsend?: boolean;                       // Message deletion
  reply?: boolean;                        // Threaded replies
  effects?: boolean;                      // Message effects (iMessage)
  groupManagement?: boolean;              // Create/manage groups
  threads?: boolean;                      // Thread support
  media?: boolean;                        // Image/video/file attachments
  nativeCommands?: boolean;               // Slash commands
  blockStreaming?: boolean;               // Block-by-block streaming
}
```

**Capability Examples**:
- **WhatsApp**: `["direct", "group"]`, polls ✓, reactions ✓, threads ✗, media ✓
- **Telegram**: `["direct", "group", "channel", "thread"]`, all features ✓
- **Slack**: `["direct", "channel", "thread"]`, reactions ✓, threads ✓, streaming ✓
- **Discord**: `["direct", "channel", "thread"]`, polls ✓, reactions ✓, threads ✓

---

## 2. Message Format Normalization

### 2.1 Unified Message Context

All inbound messages are normalized to `MsgContext` before processing:

```typescript
// From src/auto-reply/templating.ts
type MsgContext = {
  // Text content (multiple representations)
  Body?: string;                    // Raw message text
  BodyForAgent?: string;            // Formatted for AI (may include history)
  CommandBody?: string;             // Clean text for command parsing
  BodyForCommands?: string;         // Preferred for command detection

  // Routing metadata
  From?: string;                    // Sender identifier
  To?: string;                      // Recipient identifier (bot)
  SessionKey?: string;              // Conversation session key
  AccountId?: string;               // Multi-account support

  // Message IDs
  MessageSid?: string;              // Message ID (short form)
  MessageSidFull?: string;          // Full message ID
  ReplyToId?: string;               // Replied-to message ID
  ReplyToIdFull?: string;           // Full replied-to ID

  // Thread context
  MessageThreadId?: string | number; // Thread/topic ID
  ThreadLabel?: string;             // Thread title
  ThreadStarterBody?: string;       // Original thread message
  ThreadHistoryBody?: string;       // Full thread history

  // Media attachments
  MediaPath?: string;               // Local file path
  MediaUrl?: string;                // Remote URL
  MediaType?: string;               // MIME type
  MediaPaths?: string[];            // Multiple attachments
  MediaUrls?: string[];
  MediaTypes?: string[];

  // Sender identity
  SenderName?: string;
  SenderId?: string;
  SenderUsername?: string;
  SenderE164?: string;              // Phone number (E.164 format)

  // Chat context
  ChatType?: string;                // "direct", "group", "channel"
  ConversationLabel?: string;       // Display label (e.g., "#general")
  GroupSubject?: string;
  GroupChannel?: string;
  GroupSpace?: string;

  // Security
  WasMentioned?: boolean;
  CommandAuthorized?: boolean;
  OwnerAllowFrom?: Array<string | number>;

  // Channel metadata
  Provider?: string;                // "whatsapp", "telegram"
  Surface?: string;                 // Preferred channel label
  OriginatingChannel?: ChannelId;   // For reply routing
  OriginatingTo?: string;           // Reply destination
}
```

### 2.2 Normalization Pipeline

Each channel has a **normalization function** that translates platform-specific events into `MsgContext`:

```typescript
// From src/channels/plugins/normalize/telegram.ts
function normalizeTelegramMessagingTarget(raw: string): string | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;

  let normalized = trimmed;

  // Strip telegram: or tg: prefix
  if (normalized.startsWith("telegram:")) {
    normalized = normalized.slice("telegram:".length).trim();
  } else if (normalized.startsWith("tg:")) {
    normalized = normalized.slice("tg:".length).trim();
  }

  // Parse t.me URLs
  const tmeMatch = /^https?:\/\/t\.me\/([A-Za-z0-9_]+)$/i.exec(normalized);
  if (tmeMatch?.[1]) {
    normalized = `@${tmeMatch[1]}`;
  }

  return `telegram:${normalized}`.toLowerCase();
}
```

**Finalization Step** (ensures consistency):

```typescript
// From src/auto-reply/reply/inbound-context.ts
function finalizeInboundContext(ctx: MsgContext): FinalizedMsgContext {
  // Normalize newlines
  ctx.Body = normalizeInboundTextNewlines(ctx.Body ?? "");
  ctx.RawBody = normalizeInboundTextNewlines(ctx.RawBody);

  // Normalize chat type
  ctx.ChatType = normalizeChatType(ctx.ChatType);

  // Default BodyForAgent
  ctx.BodyForAgent = ctx.BodyForAgent ??
                     ctx.CommandBody ??
                     ctx.RawBody ??
                     ctx.Body;

  // Default BodyForCommands
  ctx.BodyForCommands = ctx.BodyForCommands ??
                        ctx.CommandBody ??
                        ctx.RawBody ??
                        ctx.Body;

  // Resolve conversation label
  ctx.ConversationLabel = resolveConversationLabel(ctx);

  // Default-deny command authorization
  ctx.CommandAuthorized = ctx.CommandAuthorized === true;

  // Pad MediaTypes array to match MediaPaths/MediaUrls length
  // (ensures all media has a MIME type)

  return ctx;
}
```

### 2.3 Media Handling

Media attachments are normalized with type-safe arrays:

- **Single attachment**: `MediaPath`, `MediaUrl`, `MediaType` (singular)
- **Multiple attachments**: `MediaPaths[]`, `MediaUrls[]`, `MediaTypes[]` (arrays)
- **Type padding**: If `MediaTypes.length < MediaPaths.length`, pad with `"application/octet-stream"`
- **Media understanding**: Optional `MediaUnderstanding[]` for AI-analyzed descriptions

**Media limits by channel**:
- WhatsApp: 16MB (Web API), varies by type
- Telegram: 50MB (photos), 2GB (files), 20MB (voice)
- Slack: 1GB per file
- Discord: 25MB (100MB for Nitro)

---

## 3. Routing Rules & Session Management

### 3.1 Inbound Message Routing

**Routing Decision Tree**:

```
1. Check DM policy (pairing/allowlist/open)
   └─ If pairing required → Send pairing code, block message
   └─ If allowlist → Check sender in allowFrom[]
   └─ If open → Allow all

2. Check group policy (if group chat)
   └─ Require mention? Check WasMentioned
   └─ Check group in allowlist
   └─ Check sender in group allowFrom

3. Command authorization
   └─ Owner-only commands → Check OwnerAllowFrom
   └─ Elevated commands → Check GatewayClientScopes

4. Session key resolution
   └─ Build: hash(channel, accountId, from, groupId, threadId)
   └─ Lookup existing session or create new

5. Route to agent
   └─ Load session context
   └─ Pass MsgContext to agent
```

### 3.2 Session Key Derivation

```typescript
// Session keys uniquely identify conversations
function buildSessionKey(params: {
  channel: ChannelId;
  accountId?: string;
  from: string;
  groupId?: string;
  threadId?: string | number;
}): string {
  // Example: "telegram:main:user123456"
  // Example: "slack:default:C123456:thread_ts_123"

  const parts = [
    params.channel,
    params.accountId || "default",
    params.from
  ];

  if (params.groupId) {
    parts.push(params.groupId);
  }

  if (params.threadId) {
    parts.push(String(params.threadId));
  }

  return parts.join(":");
}
```

### 3.3 Outbound Reply Routing

**Reply Target Resolution**:

1. Check `MsgContext.OriginatingChannel` (explicit override)
2. Fall back to `SessionEntry.lastChannel` (most recent inbound)
3. Fall back to default account for channel

```typescript
// From src/channels/session.ts
async function recordInboundSession(params: {
  storePath: string;
  sessionKey: string;
  ctx: MsgContext;
  updateLastRoute?: {
    sessionKey: string;
    channel: ChannelId;
    to: string;
    accountId?: string;
    threadId?: string | number;
  };
}): Promise<void> {
  // Update session metadata
  await recordSessionMetaFromInbound({
    storePath,
    sessionKey,
    ctx,
  });

  // Update last route for replies
  if (params.updateLastRoute) {
    await updateLastRoute({
      storePath,
      sessionKey: params.updateLastRoute.sessionKey,
      deliveryContext: {
        channel: params.updateLastRoute.channel,
        to: params.updateLastRoute.to,
        accountId: params.updateLastRoute.accountId,
        threadId: params.updateLastRoute.threadId,
      },
    });
  }
}
```

---

## 4. Pairing & Security System

### 4.1 DM Pairing Flow

When an unknown sender DMs the bot:

1. **Generate pairing code** (8-char alphanumeric, no ambiguous chars)
2. **Send pairing message** to sender:
   ```
   OpenClaw: access not configured.

   Telegram user ID: 123456789

   Pairing code: ABCD1234

   Ask the bot owner to approve with:
   openclaw pairing approve telegram ABCD1234
   ```
3. **Owner approves** via CLI:
   ```bash
   openclaw pairing approve telegram ABCD1234
   ```
4. **Sender added to allowFrom** automatically
5. **Approval notification** sent to sender: "Access approved! You can now chat with OpenClaw."

**Pairing Store** (JSON file at `~/.openclaw/credentials/<channel>-pairing.json`):

```json
{
  "version": 1,
  "requests": [
    {
      "id": "123456789",
      "code": "ABCD1234",
      "createdAt": "2026-02-14T10:30:00Z",
      "lastSeenAt": "2026-02-14T10:30:00Z",
      "meta": {
        "username": "@alice",
        "name": "Alice Smith"
      }
    }
  ]
}
```

**TTL & Limits**:
- Pairing codes expire after **60 minutes**
- Max **3 pending requests** per channel (oldest pruned)
- Codes are **8 characters** from alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no 0/O/1/I confusion)

### 4.2 Security Policies

Each channel adapter implements `ChannelSecurityAdapter`:

```typescript
// From extensions/telegram/src/channel.ts (example)
security: {
  resolveDmPolicy: ({ cfg, accountId, account }) => {
    return {
      policy: account.config.dmPolicy ?? "pairing",  // "pairing" | "allowlist" | "open"
      allowFrom: account.config.allowFrom ?? [],     // Approved sender IDs
      policyPath: "channels.telegram.dmPolicy",
      allowFromPath: "channels.telegram.",
      approveHint: "openclaw pairing approve telegram <CODE>",
      normalizeEntry: (raw) => raw.replace(/^(telegram|tg):/i, "")
    };
  },
  collectWarnings: ({ account, cfg }) => {
    // Return security warnings for "openclaw status" output
    if (account.config.groupPolicy === "open") {
      return ["- Telegram groups: groupPolicy='open' allows any group (mention-gated)"];
    }
    return [];
  }
}
```

**Group Security**:
- **Allowlist mode**: Only configured groups allowed
- **Open mode**: Any group allowed (but mention-gated by default)
- **Per-group sender allowlist**: Restrict who can trigger in allowed groups

### 4.3 Multi-Account Support

Channels support multiple accounts (e.g., 3 different Telegram bots):

```yaml
# config.yaml
channels:
  telegram:
    enabled: true
    accounts:
      main:
        botToken: "123:ABC"
        dmPolicy: pairing
        allowFrom: [123456]
      support:
        botToken: "456:DEF"
        dmPolicy: allowlist
        allowFrom: [789012]
      alerts:
        botToken: "789:GHI"
        dmPolicy: open
```

**Account resolution**:
- Inbound: Detect account from webhook/event metadata
- Outbound: Use `accountId` parameter or fall back to `defaultAccountId()`

---

## 5. Channel Capabilities Comparison

| Feature | WhatsApp | Telegram | Slack | Discord | Signal | iMessage |
|---------|----------|----------|-------|---------|--------|----------|
| **Chat Types** |
| Direct Messages | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Group Chats | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Channels | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Threads | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Media** |
| Images/Videos | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Files | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Voice Messages | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ |
| Stickers | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ |
| **Interactivity** |
| Reactions | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Polls | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| Buttons | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Slash Commands | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Text Features** |
| Markdown | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Edit Messages | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Delete Messages | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Streaming | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Connection** |
| Long Polling | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ |
| WebSocket | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ |
| Webhooks | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Local Protocol | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

**Text Chunk Limits**:
- WhatsApp: 4000 chars (text mode)
- Telegram: 4000 chars (Markdown mode)
- Slack: No hard limit (split at 40k for readability)
- Discord: 2000 chars (Markdown mode)
- Signal: 64KB

**Streaming Support**:
- **Telegram**: Block-by-block streaming (edit message on each block)
- **Slack**: Block-by-block streaming with coalesce (1500 chars or 1s idle)
- **Discord**: Block-by-block streaming with coalesce (1500 chars or 1s idle)
- **WhatsApp/Signal/iMessage**: No streaming (send complete messages only)

---

## 6. Extension Pattern & Plugin Interface

### 6.1 Creating a New Channel Extension

**Minimal Example** (hypothetical Baap web channel):

```typescript
// extensions/baap-web/src/channel.ts
import { type ChannelPlugin } from "openclaw/plugin-sdk";

type BaapWebAccount = {
  accountId: string;
  enabled: boolean;
  apiKey: string;
  baseUrl: string;
};

export const baapWebPlugin: ChannelPlugin<BaapWebAccount> = {
  id: "baap-web",
  meta: {
    id: "baap-web",
    label: "Baap Command Center",
    selectionLabel: "Baap Web Interface",
    docsPath: "/channels/baap-web",
    blurb: "Real-time web interface for Baap agents"
  },
  capabilities: {
    chatTypes: ["direct"],
    media: false,
    reactions: false,
    threads: false,
  },
  config: {
    listAccountIds: (cfg) => ["default"],
    resolveAccount: (cfg, accountId) => ({
      accountId: accountId || "default",
      enabled: cfg.channels?.baapWeb?.enabled ?? false,
      apiKey: cfg.channels?.baapWeb?.apiKey ?? "",
      baseUrl: cfg.channels?.baapWeb?.baseUrl ?? "http://localhost:3500"
    }),
    isConfigured: (account) => Boolean(account.apiKey && account.baseUrl),
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ to, text, accountId }) => {
      // POST to Baap Command Center API
      const account = /* resolve account */;
      await fetch(`${account.baseUrl}/api/agent-messages`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${account.apiKey}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ to, text })
      });

      return { channel: "baap-web", messageId: `msg_${Date.now()}` };
    }
  }
};
```

**Package Manifest** (`extensions/baap-web/package.json`):

```json
{
  "name": "@baap/openclaw-baap-web",
  "version": "1.0.0",
  "openclaw": {
    "channel": {
      "id": "baap-web",
      "label": "Baap Command Center"
    },
    "extensions": ["./dist/channel.js"]
  },
  "main": "./dist/channel.js",
  "exports": {
    ".": "./dist/channel.js"
  }
}
```

### 6.2 Plugin Discovery Process

1. **Scan directories**:
   - `<openclaw-repo>/extensions/` (bundled)
   - `~/.openclaw/extensions/` (global user)
   - `<workspace>/extensions/` (workspace-local)
   - `node_modules/` (npm packages with `openclaw` metadata)

2. **Load package.json** from each directory

3. **Extract `openclaw.extensions`** array:
   ```json
   {
     "openclaw": {
       "extensions": ["./dist/telegram.js", "./dist/whatsapp.js"]
     }
   }
   ```

4. **Import each module** and call exported function (or use default export)

5. **Register plugins** in global `PluginRegistry`

6. **Deduplicate by ID** (first-found wins based on origin priority: config > workspace > global > bundled)

**Origin Priority**:
1. **config**: Explicitly configured in `config.yaml`
2. **workspace**: Project-local `extensions/`
3. **global**: User-level `~/.openclaw/extensions/`
4. **bundled**: Built-in `<repo>/extensions/`

### 6.3 Outbound Delivery Modes

Channels choose one of three **delivery modes**:

1. **Direct**: Channel adapter sends messages directly (Telegram, Discord)
   ```typescript
   outbound: {
     deliveryMode: "direct",
     sendText: async ({ to, text, accountId }) => {
       // Call Telegram API directly
       const result = await sendMessageTelegram(to, text, { accountId });
       return { channel: "telegram", ...result };
     }
   }
   ```

2. **Gateway**: Messages routed through long-lived gateway process (WhatsApp, Signal)
   ```typescript
   outbound: {
     deliveryMode: "gateway",
     sendText: async ({ to, text, accountId, deps }) => {
       // Send via gateway RPC
       const send = deps?.sendWhatsApp ?? sendMessageWhatsApp;
       const result = await send(to, text, { accountId });
       return { channel: "whatsapp", ...result };
     }
   }
   ```

3. **Hybrid**: Both direct and gateway supported (future use)

**Why Gateway Mode?**
- WhatsApp Web requires persistent WebSocket connection
- Signal CLI requires long-running daemon
- Gateway process manages connection lifecycle, CLI spawns just send RPC

---

## 7. Integration Analysis for Baap

### 7.1 Current Baap Architecture (Before OpenClaw Integration)

**Notification Flow**:
```
Agent Worker → creates Bead → writes JSON to .beads/
                                 ↓
                            (goes nowhere)
```

**Agent-Human Communication**:
```
Human → Baap CLI → spawns agent → agent responds → prints to stdout
                                                       ↓
                                                   Human reads CLI
```

**Agent Status Updates**:
```
Orchestrator → spawns agents → agents work
                                  ↓
                            (no visibility)
```

**Current Limitations**:
- Beads are write-only (no delivery mechanism)
- CLI-only interaction (no remote/mobile access)
- No real-time status visibility
- No team collaboration

### 7.2 Proposed Integration: "Baap Messaging Bridge"

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Baap Platform                            │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Orchestrator│  │ Agent Workers│  │ Command Center│      │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                           ↓                                 │
│              ┌────────────────────────┐                     │
│              │  Baap Messaging API    │                     │
│              │  (FastAPI backend)     │                     │
│              └────────┬───────────────┘                     │
└───────────────────────┼─────────────────────────────────────┘
                        │ HTTP/WebSocket
                        ↓
┌─────────────────────────────────────────────────────────────┐
│                   OpenClaw Gateway                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  WhatsApp    │  │  Telegram    │  │    Slack     │      │
│  │  Monitor     │  │  Webhook     │  │  WebSocket   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                           ↓                                 │
│              ┌────────────────────────┐                     │
│              │  Channel Adapters      │                     │
│              │  (normalize MsgContext)│                     │
│              └────────┬───────────────┘                     │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ↓
             ┌──────────────────────┐
             │  Human (WhatsApp/    │
             │  Telegram/Slack)     │
             └──────────────────────┘
```

### 7.3 Integration Point 1: Notification Beads → Messaging

**Use Case**: Agent creates notification bead "users table schema changed", route to WhatsApp

**Implementation**:

```python
# src/beads/notification_router.py
from typing import Optional
import requests

class NotificationRouter:
    def __init__(self, openclaw_gateway_url: str):
        self.gateway_url = openclaw_gateway_url

    async def route_bead_notification(
        self,
        bead: Bead,
        recipients: list[str],  # ["whatsapp:+1234567890", "telegram:@alice"]
        channel_preference: Optional[str] = None
    ):
        """Route a notification bead to messaging channels."""

        # Format bead as message
        message = self._format_bead_notification(bead)

        # Send via OpenClaw gateway
        for recipient in recipients:
            channel, target = recipient.split(":", 1)

            await self._send_openclaw_message(
                channel=channel,
                to=target,
                text=message,
                metadata={
                    "bead_id": bead.id,
                    "priority": bead.priority,
                    "category": bead.category
                }
            )

    def _format_bead_notification(self, bead: Bead) -> str:
        """Format bead as human-readable message."""
        emoji = {
            0: "🔵",  # info
            1: "🟡",  # low
            2: "🟠",  # medium
            3: "🔴"   # high
        }[bead.priority]

        return f"""
{emoji} **Baap Agent Notification**

**Title**: {bead.title}
**Priority**: {bead.priority_label}
**Agent**: {bead.created_by}

{bead.body[:200]}...

View details: baap bead view {bead.id}
"""

    async def _send_openclaw_message(
        self,
        channel: str,
        to: str,
        text: str,
        metadata: dict
    ):
        """Send message via OpenClaw gateway API."""
        response = await requests.post(
            f"{self.gateway_url}/api/send",
            json={
                "channel": channel,
                "to": to,
                "text": text,
                "metadata": metadata
            }
        )
        response.raise_for_status()
```

**Configuration** (`config/notifications.yaml`):

```yaml
notifications:
  enabled: true
  openclaw_gateway: "http://localhost:9999"

  # Route high-priority beads to WhatsApp
  routes:
    - priority: [3]  # high only
      channels:
        - whatsapp:+14155551234

    # Route medium+ to Telegram
    - priority: [2, 3]
      channels:
        - telegram:@rahil_dev

    # Route all to Slack #baap-alerts
    - priority: [0, 1, 2, 3]
      channels:
        - slack:C123456  # #baap-alerts channel
```

### 7.4 Integration Point 2: Orchestrator → Messaging

**Use Case**: "Agent spawned", "Agent finished", "Agent failed" status updates to Slack

**Implementation**:

```python
# src/orchestrator/status_broadcaster.py
class AgentStatusBroadcaster:
    def __init__(self, notification_router: NotificationRouter):
        self.router = notification_router

    async def on_agent_spawned(self, agent_name: str, task: str):
        """Broadcast agent spawn event."""
        await self.router.send_status_update(
            channel="slack",
            to="C123456",  # #baap-status channel
            text=f"🚀 Agent **{agent_name}** spawned\n📋 Task: {task}"
        )

    async def on_agent_working(
        self,
        agent_name: str,
        step: str,
        progress: Optional[str] = None
    ):
        """Broadcast agent progress."""
        message = f"⚙️ Agent **{agent_name}**: {step}"
        if progress:
            message += f"\n📊 {progress}"

        await self.router.send_status_update(
            channel="slack",
            to="C123456",
            text=message
        )

    async def on_agent_complete(self, agent_name: str, summary: str):
        """Broadcast agent completion."""
        await self.router.send_status_update(
            channel="slack",
            to="C123456",
            text=f"✅ Agent **{agent_name}** complete\n\n{summary}"
        )

    async def on_agent_failed(self, agent_name: str, error: str):
        """Broadcast agent failure."""
        await self.router.send_status_update(
            channel="slack",
            to="C123456",
            text=f"❌ Agent **{agent_name}** failed\n\n```\n{error}\n```"
        )
```

**Example Slack Output**:

```
🚀 Agent data-quality-checker spawned
📋 Task: Validate Snowflake data freshness for revenue metrics

⚙️ Agent data-quality-checker: Querying Snowflake
📊 Checking 15 tables...

⚙️ Agent data-quality-checker: Analyzing SLA compliance
📊 3 tables stale (exceeded 4h SLA)

✅ Agent data-quality-checker complete

Found 3 stale tables:
- revenue_daily (6h stale)
- conversions_hourly (5h stale)
- spend_hourly (4.5h stale)

Recommended: Trigger dbt refresh for marketing models
```

### 7.5 Integration Point 3: Human ↔ Agent via Messaging

**Use Case**: Chat with Baap agent through WhatsApp instead of CLI

**Flow**:

```
Human (WhatsApp) → "Investigate ROAS drop"
                    ↓
            OpenClaw Gateway (receives webhook)
                    ↓
            Normalize to MsgContext
                    ↓
            POST to Baap API /api/agent-chat
                    ↓
            Baap Orchestrator spawns agent
                    ↓
            Agent streams responses
                    ↓
            Baap API forwards to OpenClaw
                    ↓
            OpenClaw sends WhatsApp messages
```

**Implementation**:

```python
# src/api/agent_chat.py (FastAPI endpoint)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class InboundMessage(BaseModel):
    channel: str
    from_: str
    to: str
    body: str
    session_key: str
    account_id: Optional[str]

@router.post("/api/agent-chat/inbound")
async def handle_inbound_message(msg: InboundMessage):
    """Handle inbound message from OpenClaw."""

    # Parse command
    if msg.body.startswith("/investigate"):
        metric = msg.body.split(maxsplit=1)[1] if len(msg.body.split()) > 1 else "roas"

        # Spawn investigation agent
        agent_task = spawn_investigation_agent(
            metric=metric,
            session_key=msg.session_key,
            reply_channel=msg.channel,
            reply_to=msg.from_
        )

        # Send acknowledgment
        await send_openclaw_reply(
            session_key=msg.session_key,
            channel=msg.channel,
            to=msg.from_,
            text=f"🔍 Starting investigation for {metric}..."
        )

        # Stream agent responses
        async for status_update in agent_task.stream():
            await send_openclaw_reply(
                session_key=msg.session_key,
                channel=msg.channel,
                to=msg.from_,
                text=status_update
            )

        return {"status": "ok"}

    else:
        raise HTTPException(400, "Unknown command")

async def send_openclaw_reply(
    session_key: str,
    channel: str,
    to: str,
    text: str
):
    """Send reply via OpenClaw gateway."""
    response = await requests.post(
        f"{OPENCLAW_GATEWAY_URL}/api/send",
        json={
            "channel": channel,
            "to": to,
            "text": text,
            "session_key": session_key  # Thread replies together
        }
    )
    response.raise_for_status()
```

**Example WhatsApp Conversation**:

```
[You]
/investigate roas

[Baap Agent]
🔍 Starting investigation for roas...

[Baap Agent]
✅ Triage complete (5s)
- Severity: HIGH
- Primary metric: roas (current: 2.8x, target: 4.0x)
- Related: revenue, spend, cpc

[Baap Agent]
✅ Data validation complete (12s)
- Magento: fresh (last update 15min ago)
- Google Ads: fresh (last update 10min ago)
- Data quality: PASS

[Baap Agent]
🔎 Walking causal graph...
- ROAS = revenue / spend
- Revenue: DOWN 15% (anomaly detected)
- Spend: NORMAL

[Baap Agent]
📊 Root cause found:
- Google Shopping CPC spiked +40% (from $0.80 to $1.12)
- Caused by new competitor bidding on top keywords
- Affecting 60% of traffic

[Baap Agent]
💡 Recommended actions (medium risk):
1. Reduce Google Shopping budget by 15% (AUTO-EXECUTABLE)
2. Pause low-performing ad groups (NEEDS APPROVAL)
3. Switch to Target ROAS bidding (NEEDS APPROVAL)

Reply /approve 1 to auto-execute action 1
```

### 7.6 Integration Point 4: Command Center as Web Channel

**Use Case**: Baap Command Center (Next.js UI) connects as a "channel" to OpenClaw

**Architecture**:

```typescript
// ui/src/lib/openclaw-channel.ts
import { io, Socket } from "socket.io-client";

export class BaapCommandCenterChannel {
  private socket: Socket;
  private sessionKey: string;

  constructor(apiUrl: string, userId: string) {
    this.sessionKey = `baap-web:${userId}`;

    this.socket = io(apiUrl, {
      auth: { userId }
    });

    this.socket.on("message", this.handleInbound.bind(this));
  }

  async sendMessage(text: string, metadata?: Record<string, any>) {
    await fetch(`${this.apiUrl}/api/agent-chat/inbound`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        channel: "baap-web",
        from: this.sessionKey,
        to: "agent",
        body: text,
        session_key: this.sessionKey,
        metadata
      })
    });
  }

  private handleInbound(message: {
    text: string;
    messageId: string;
    timestamp: number;
    metadata?: Record<string, any>;
  }) {
    // Render in Command Center UI
    this.renderMessage(message);
  }

  private renderMessage(message: any) {
    // Append to chat UI
    // Could render Decision Packets, charts, etc.
  }
}
```

**OpenClaw Plugin** (simple direct-mode channel):

```typescript
// extensions/baap-web/src/channel.ts
export const baapWebPlugin: ChannelPlugin = {
  id: "baap-web",
  capabilities: {
    chatTypes: ["direct"],
    media: false,
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ to, text }) => {
      // POST to Baap Command Center API
      await fetch("http://localhost:3500/api/openclaw/outbound", {
        method: "POST",
        json: { sessionKey: to, text }
      });

      return { channel: "baap-web", messageId: `web_${Date.now()}` };
    }
  }
};
```

**Result**: Command Center becomes a **first-class messaging channel** alongside WhatsApp/Telegram/Slack.

---

## 8. Implementation Recommendations

### 8.1 Phase 1: Notification Routing (2 weeks)

**Goal**: Route agent notification beads to WhatsApp/Slack

**Steps**:
1. Set up OpenClaw gateway as separate process (or Docker container)
2. Configure WhatsApp/Telegram/Slack channels in OpenClaw
3. Implement `NotificationRouter` in Baap
4. Add `notifications.yaml` config for routing rules
5. Hook into bead creation lifecycle

**Deliverable**: Agent beads automatically posted to configured channels

### 8.2 Phase 2: Agent Status Broadcasting (1 week)

**Goal**: Stream agent lifecycle events to Slack #baap-status

**Steps**:
1. Implement `AgentStatusBroadcaster`
2. Hook into orchestrator spawn/complete/fail events
3. Configure Slack channel in `notifications.yaml`

**Deliverable**: Real-time Slack feed of agent activity

### 8.3 Phase 3: Bi-Directional Chat (3 weeks)

**Goal**: Humans chat with Baap agents via WhatsApp

**Steps**:
1. Implement `/api/agent-chat/inbound` endpoint
2. Configure OpenClaw webhook to POST inbound messages
3. Implement command parsing (/investigate, /approve, /status)
4. Stream agent responses back to OpenClaw
5. Handle session/thread management

**Deliverable**: Full conversational interface via messaging apps

### 8.4 Phase 4: Command Center Integration (2 weeks)

**Goal**: Command Center UI as OpenClaw channel

**Steps**:
1. Implement WebSocket server in Baap backend
2. Create `baap-web` OpenClaw plugin
3. Implement real-time message rendering in UI
4. Add chat input component to Command Center

**Deliverable**: Web-based chat alongside messaging apps

### 8.5 Phase 5: Rich Interactions (ongoing)

**Future Enhancements**:
- **Buttons**: "Approve action 1" → Telegram inline buttons
- **Decision Packets**: Render as rich cards in Slack
- **Charts**: Send as images (Plotly → PNG → WhatsApp)
- **Reactions**: Acknowledge agent messages with 👍
- **Threads**: Keep investigation conversations in Slack threads

---

## 9. Security Considerations

### 9.1 Authentication

- **Pairing**: Use DM pairing for WhatsApp/Telegram (unknown senders must request access)
- **Allowlist**: Maintain `allowFrom` lists per channel
- **Multi-tenancy**: Separate accounts for different teams (e.g., `baap-prod` vs `baap-dev`)

### 9.2 Authorization

- **Command gating**: Only owners can run `/approve` commands
- **Scope isolation**: Agent sessions isolated by `session_key`
- **Rate limiting**: Prevent spam (use OpenClaw's built-in rate limiting)

### 9.3 Data Privacy

- **PII handling**: Beads may contain sensitive data (schema changes, user counts)
- **Channel encryption**: Use E2E encrypted channels (Signal, WhatsApp) for sensitive alerts
- **Audit logs**: Log all outbound messages for compliance

### 9.4 Network Security

- **OpenClaw Gateway**: Run behind firewall, only expose webhook endpoints
- **TLS**: Use HTTPS for all webhook callbacks
- **Token management**: Store bot tokens in secrets manager (not config files)

---

## 10. Performance & Scalability

### 10.1 Message Throughput

OpenClaw handles:
- **Telegram**: 30 msg/sec per bot (API limit)
- **WhatsApp**: Varies by account tier (Business API: 80 msg/sec)
- **Slack**: 1 msg/sec per channel (tier 1), burst to 100/min
- **Discord**: 50 msg/5sec per channel

**Baap Requirements**:
- Notification beads: ~10/hour (low volume)
- Agent status updates: ~100/hour during peak investigation
- Chat messages: ~50/hour (human-initiated)

**Verdict**: Well within limits, no special queueing needed initially

### 10.2 Gateway Architecture

OpenClaw supports:
- **Single-process**: All channels in one gateway process (simple, <10 agents)
- **Multi-process**: Separate gateway per channel (scalable, 10-100 agents)
- **Distributed**: Load-balanced gateway cluster (enterprise, 100+ agents)

**Recommendation for Baap**: Start with **single-process gateway**, scale to multi-process if needed.

### 10.3 Monitoring

OpenClaw provides:
- `openclaw status` - Channel health checks
- `openclaw channels list` - Active channels
- Gateway logs → stdout (capture with systemd journal)
- Prometheus metrics (optional)

**Integration**: Forward OpenClaw gateway logs to Baap observability stack (DataDog/Grafana).

---

## 11. Conclusion

OpenClaw's multi-channel architecture provides a **production-ready foundation** for routing Baap agent notifications and enabling conversational interfaces. The plugin system is well-designed for extensibility, and the pairing/security model handles authentication gracefully.

**Key Takeaways**:

1. **Channel Abstraction**: Unified `ChannelPlugin` interface makes adding new channels trivial
2. **Message Normalization**: `MsgContext` provides consistent format across all platforms
3. **Security**: DM pairing + allowlists handle unknown senders safely
4. **Extensibility**: Plugin discovery supports bundled, workspace, and npm-installed channels
5. **Capabilities**: Rich feature detection (polls, threads, reactions, streaming)

**Integration Value for Baap**:
- ✅ **Immediate**: Route notification beads to WhatsApp/Slack (Phase 1)
- ✅ **High ROI**: Agent status broadcasting to Slack (Phase 2)
- ✅ **Game-changing**: Conversational agent interface (Phase 3)
- ✅ **Future-proof**: Command Center as messaging channel (Phase 4)

**Next Steps**:
1. Set up OpenClaw gateway locally
2. Configure WhatsApp/Telegram test accounts
3. Implement `NotificationRouter` prototype
4. Test end-to-end flow: Bead → OpenClaw → WhatsApp → Human

---

## Appendix A: Code Locations

### Core Channel Files
- `src/channels/plugins/types.plugin.ts` - Plugin interface
- `src/channels/plugins/types.core.ts` - Core types (capabilities, MsgContext)
- `src/channels/plugins/types.adapters.ts` - Adapter interfaces
- `src/channels/plugins/index.ts` - Plugin registry
- `src/channels/plugins/catalog.ts` - Plugin discovery

### Example Channel Implementations
- `extensions/telegram/src/channel.ts` - Telegram plugin
- `extensions/whatsapp/src/channel.ts` - WhatsApp plugin
- `extensions/slack/src/channel.ts` - Slack plugin
- `extensions/discord/src/channel.ts` - Discord plugin
- `extensions/signal/src/channel.ts` - Signal plugin

### Message Processing
- `src/auto-reply/templating.ts` - MsgContext type definition
- `src/auto-reply/reply/inbound-context.ts` - Message normalization
- `src/channels/plugins/normalize/*.ts` - Channel-specific normalizers

### Security & Routing
- `src/pairing/pairing-store.ts` - Pairing code management
- `src/pairing/pairing-messages.ts` - Pairing message templates
- `src/channels/session.ts` - Session management
- `src/channels/plugins/pairing.ts` - Pairing adapters

### Plugin Discovery
- `src/plugins/discovery.ts` - Plugin scanning
- `src/plugins/runtime.ts` - Plugin registry runtime
- `src/plugins/manifest.ts` - Package manifest parsing

### Outbound Delivery
- `src/infra/outbound/channel-adapters.ts` - Outbound adapter helpers
- `src/infra/outbound/deliver.ts` - Message delivery logic

---

## Appendix B: Configuration Examples

### Multi-Channel Setup

```yaml
# config.yaml (OpenClaw)
channels:
  telegram:
    enabled: true
    botToken: "123456:ABC-DEF..."
    dmPolicy: pairing
    allowFrom: [123456789]

  whatsapp:
    enabled: true
    accounts:
      main:
        enabled: true
        authDir: "~/.openclaw/auth/whatsapp-main"
        dmPolicy: allowlist
        allowFrom: ["+14155551234"]

  slack:
    enabled: true
    botToken: "xoxb-..."
    appToken: "xapp-..."
    dm:
      policy: pairing
      allowFrom: ["U123456"]
    channels:
      C123456:  # #baap-alerts
        requireMention: false
      C789012:  # #baap-status
        requireMention: false

  discord:
    enabled: true
    token: "MTIzNDU2Nzg5..."
    dm:
      policy: pairing
    guilds:
      "987654321":  # Baap Dev Server
        channels:
          "111111111":  # #agent-logs
            requireMention: false
```

### Baap Notification Routing

```yaml
# config/notifications.yaml (Baap)
notifications:
  enabled: true
  openclaw_gateway: "http://localhost:9999"

  routes:
    # Critical beads → WhatsApp
    - name: "critical-alerts"
      priority: [3]
      channels:
        - whatsapp:+14155551234
        - telegram:123456789

    # Medium+ → Slack #baap-alerts
    - name: "medium-alerts"
      priority: [2, 3]
      channels:
        - slack:C123456

    # All agent events → Slack #baap-status
    - name: "status-feed"
      event_types: ["agent_spawn", "agent_complete", "agent_fail"]
      channels:
        - slack:C789012

    # Investigation results → Discord #investigations
    - name: "investigations"
      categories: ["investigation_complete"]
      channels:
        - discord:channel:111111111
```

---

**End of Report**
