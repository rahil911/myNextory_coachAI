# OpenClaw Canvas & A2UI Research Report
## Integration Analysis for Baap

**Date**: 2026-02-14  
**Research Scope**: Canvas architecture, A2UI protocol, rendering model, component library, and integration opportunities with Baap's AI-native development platform.

---

## Executive Summary

OpenClaw's **Canvas** is an agent-controlled visual workspace that runs in a WKWebView panel (macOS/iOS) or WebView (Android). **A2UI (Agent-to-User Interface)** is an open-source declarative JSON protocol that allows agents to generate rich, interactive UIs safely. Together, they provide a powerful model for agents to drive visual workspaces without executing arbitrary code.

**Key Integration Opportunities for Baap**:
1. **Replace hand-built vanilla JS components** (Kanban, Timeline, Dashboard) with A2UI-driven surfaces
2. **Use Canvas as the rendering target** for Decision Capsule investigations
3. **Stream agent work-in-progress** (file changes, test results, KG queries) to Canvas
4. **Render Ownership KG** as interactive A2UI components
5. **Enable agent-driven dashboards** where agents can create custom visualizations on-the-fly

---

## 1. Canvas Architecture

### What is Canvas?

Canvas is a **lightweight visual workspace for HTML/CSS/JS and A2UI**, embedded in OpenClaw's native apps. It provides a borderless, resizable panel where agents can display interactive content.

### Key Characteristics

| Feature | Description |
|---------|-------------|
| **Platform** | macOS: WKWebView panel, iOS/Android: WebView |
| **Storage** | `~/Library/Application Support/OpenClaw/canvas/<session>/` |
| **URL Scheme** | `openclaw-canvas://<session>/<path>` (custom scheme, no loopback server) |
| **Live Reload** | Auto-reloads when local canvas files change (via WebSocket) |
| **Panel Behavior** | Borderless, resizable, remembers size/position per session |
| **Security** | Blocks directory traversal; files must live under session root |

### Agent API Surface

Canvas is exposed via **Gateway WebSocket**, allowing agents to:

- **Show/Hide** the panel: `openclaw nodes canvas present --node <id>`
- **Navigate** to a path or URL: `openclaw nodes canvas navigate --node <id> --url "/"`
- **Evaluate JavaScript**: `openclaw nodes canvas eval --node <id> --js "document.title"`
- **Capture snapshot**: `openclaw nodes canvas snapshot --node <id>`

### File Structure

```
~/Library/Application Support/OpenClaw/canvas/
  ├── main/
  │   ├── index.html          # Entry point (auto-created if missing)
  │   ├── assets/
  │   │   ├── app.css
  │   │   └── app.js
  │   └── widgets/
  │       └── todo/
  │           └── index.html
```

If no `index.html` exists, Canvas shows a **built-in scaffold page** with demo buttons.

---

## 2. A2UI Protocol

### What is A2UI?

**A2UI (Agent-to-User Interface)** is an open-source declarative JSON protocol that allows agents to generate updateable, interactive UIs. It separates UI structure from UI implementation, ensuring agent-generated UIs are **"safe like data, but expressive like code."**

### Core Design Principles

| Principle | Description |
|-----------|-------------|
| **Security First** | Declarative data format (not executable code). Agents can only render components from a pre-approved catalog. |
| **LLM-Friendly** | Flat list of components with ID references. Easy for LLMs to generate incrementally. |
| **Incrementally Updateable** | Agents can efficiently update specific components without regenerating the entire UI. |
| **Framework-Agnostic** | Same JSON payload renders on Lit, Angular, Flutter, React, etc. |
| **Flexible** | Open registry pattern allows mapping server-side types to custom client implementations. |

### Message Types (v0.8)

A2UI uses **four server→client message types**:

#### 1. `surfaceUpdate`

Defines or updates components on a surface.

```json
{
  "surfaceUpdate": {
    "surfaceId": "main",
    "components": [
      {
        "id": "root",
        "component": {
          "Column": {
            "children": { "explicitList": ["title", "content"] }
          }
        }
      },
      {
        "id": "title",
        "component": {
          "Text": {
            "text": { "literalString": "Canvas (A2UI v0.8)" },
            "usageHint": "h1"
          }
        }
      },
      {
        "id": "content",
        "component": {
          "Text": {
            "text": { "literalString": "If you can read this, A2UI push works." },
            "usageHint": "body"
          }
        }
      }
    ]
  }
}
```

#### 2. `beginRendering`

Tells the client to start rendering a surface with a specified root component.

```json
{
  "beginRendering": {
    "surfaceId": "main",
    "root": "root"
  }
}
```

#### 3. `dataModelUpdate`

Updates the data model without changing component structure (e.g., updating a chart's data points).

```json
{
  "dataModelUpdate": {
    "surfaceId": "main",
    "dataModel": {
      "revenue": 125000,
      "roas": 3.8
    }
  }
}
```

#### 4. `deleteSurface`

Removes a surface entirely.

```json
{
  "deleteSurface": {
    "surfaceId": "temp-dialog"
  }
}
```

### Client→Server Messages

#### `userAction`

Sent when a user interacts with a component (e.g., clicks a button).

```json
{
  "userAction": {
    "id": "abc-123",
    "name": "submit",
    "surfaceId": "main",
    "sourceComponentId": "submit-button",
    "context": { "formData": { "email": "user@example.com" } }
  }
}
```

#### `clientUiCapabilities`

Sent at initialization to inform the server which components the client supports.

```json
{
  "clientUiCapabilities": {
    "supportedComponents": ["Text", "Button", "Column", "Row", "Card", "Image"],
    "version": "0.8"
  }
}
```

#### `error`

Reports errors back to the server.

```json
{
  "error": {
    "surfaceId": "main",
    "message": "Component 'ChartPro' not found in catalog"
  }
}
```

---

## 3. Rendering Model

### Server-Side vs. Client-Side

| Aspect | A2UI Approach |
|--------|---------------|
| **Generation** | Server-side (agent generates JSON) |
| **Rendering** | Client-side (native components) |
| **Transport** | JSON over WebSocket or HTTP |
| **Framework** | Lit Web Components (primary), Angular, Flutter (via GenUI), React (planned) |

### Canvas Host Server

The Canvas host runs as an HTTP server (default port auto-assigned) with two routes:

- `/__openclaw__/canvas` → serves local canvas files (HTML/CSS/JS)
- `/__openclaw__/a2ui` → serves A2UI renderer bundle (`a2ui.bundle.js`)

### A2UI Renderer Bundle

The A2UI renderer is a Lit-based web component system:

```html
<openclaw-a2ui-host></openclaw-a2ui-host>
<script src="a2ui.bundle.js"></script>
```

When the agent sends A2UI messages via WebSocket, the renderer:

1. **Parses** the JSON message
2. **Resolves** component types from the catalog
3. **Instantiates** Lit web components
4. **Binds** data model to components
5. **Emits** `userAction` events back to the agent

### Live Reload

Canvas injects a **live reload snippet** into all HTML pages:

```javascript
const ws = new WebSocket("ws://" + location.host + "/__openclaw__/ws");
ws.onmessage = (ev) => {
  if (String(ev.data || "") === "reload") location.reload();
};
```

This watches the local canvas directory and triggers a reload on file changes.

---

## 4. Interaction Model

### Agent → Canvas Flow

```
Agent (Python/Node.js)
  ↓ (generates A2UI JSON)
Gateway WebSocket
  ↓ (pushes surfaceUpdate)
Canvas Host HTTP Server
  ↓ (serves a2ui.bundle.js)
WKWebView/WebView
  ↓ (renders Lit components)
User sees UI
```

### User → Agent Flow

```
User clicks button
  ↓
Lit component fires event
  ↓
A2UI renderer calls openclawSendUserAction()
  ↓
iOS: webkit.messageHandlers.openclawCanvasA2UIAction.postMessage(...)
Android: window.openclawCanvasA2UIAction.postMessage(...)
  ↓
Native app receives message
  ↓
Gateway WebSocket sends userAction to agent
  ↓
Agent responds with surfaceUpdate or dataModelUpdate
```

### Cross-Platform Bridge

The A2UI renderer injects a **cross-platform action bridge**:

```javascript
function postToNode(payload) {
  const raw = typeof payload === "string" ? payload : JSON.stringify(payload);
  
  // iOS
  const iosHandler = globalThis.webkit?.messageHandlers?.openclawCanvasA2UIAction;
  if (iosHandler && typeof iosHandler.postMessage === "function") {
    iosHandler.postMessage(raw);
    return true;
  }
  
  // Android
  const androidHandler = globalThis.openclawCanvasA2UIAction;
  if (androidHandler && typeof androidHandler.postMessage === "function") {
    androidHandler.postMessage(raw);
    return true;
  }
  
  return false;
}

globalThis.openclawSendUserAction = (userAction) => {
  const id = userAction?.id || globalThis.crypto?.randomUUID?.();
  return postToNode({ userAction: { ...userAction, id } });
};
```

---

## 5. Component Library

### Standard Catalog (v0.8)

The A2UI standard catalog defines **15+ core components**:

#### Layout Components

| Component | Description | Properties |
|-----------|-------------|------------|
| **Column** | Vertical layout | `children` (list of IDs), `alignment`, `spacing` |
| **Row** | Horizontal layout | `children` (list of IDs), `alignment`, `spacing` |
| **Card** | Container with background/border | `children`, `elevation`, `padding` |
| **Divider** | Visual separator | `thickness`, `color` |
| **Modal** | Overlay dialog | `title`, `body`, `actions` |

#### Content Components

| Component | Description | Properties |
|-----------|-------------|------------|
| **Text** | Styled text | `text`, `usageHint` (h1, h2, body, caption), `style` |
| **Image** | Image display | `src`, `alt`, `width`, `height`, `fit` |
| **Video** | Video player | `src`, `controls`, `autoplay`, `muted` |
| **Audio** | Audio player | `src`, `controls`, `autoplay` |

#### Input Components

| Component | Description | Properties |
|-----------|-------------|------------|
| **Button** | Clickable button | `text`, `actionName`, `style` (primary, secondary, danger) |
| **Checkbox** | Boolean toggle | `label`, `checked`, `actionName` |
| **Slider** | Numeric range input | `min`, `max`, `value`, `step`, `label` |
| **TextField** | Text input | `label`, `value`, `placeholder`, `type` (text, password, email) |

#### Data Visualization

| Component | Description | Properties |
|-----------|-------------|------------|
| **Table** | Tabular data | `headers`, `rows`, `sortable`, `filterable` |
| **Chart** | Data charts | `type` (line, bar, pie), `data`, `xAxis`, `yAxis` |

### Custom Components

Developers can **register custom components** via the catalog registry:

```typescript
import { registerComponent } from "@openclaw/a2ui-renderer";

registerComponent("KanbanBoard", {
  props: {
    columns: { type: "array", required: true },
    cards: { type: "array", required: true }
  },
  render: (props, context) => {
    return html`
      <div class="kanban">
        ${props.columns.map(col => html`
          <div class="column">
            <h3>${col.title}</h3>
            ${props.cards
              .filter(card => card.columnId === col.id)
              .map(card => html`<div class="card">${card.title}</div>`)}
          </div>
        `)}
      </div>
    `;
  }
});
```

---

## 6. Canvas Persistence

### Canvas State Storage

| Aspect | Behavior |
|--------|----------|
| **Session Files** | Persisted in `~/Library/Application Support/OpenClaw/canvas/<session>/` |
| **Panel Position** | Remembered per session (stored in app preferences) |
| **Panel Size** | Remembered per session |
| **History** | No built-in history; agent must manage state |

### Sharing Canvas States

Canvas states are **local to each user** by default. To share:

1. **Export canvas directory** as a tarball
2. **Send via file sharing** (Dropbox, GitHub, etc.)
3. **Import** by extracting to another user's canvas directory

Alternatively, agents can:

- **Generate A2UI JSON** and store in a database
- **Replay** the JSON to recreate the UI on any client

---

## 7. Integration Analysis for Baap

### Current Baap Architecture (Vanilla JS)

Baap's Command Center has several hand-built components:

| Component | Current Tech | Pain Points |
|-----------|--------------|-------------|
| **Kanban Board** | Vanilla JS + DOM manipulation | Hard to update, fragile event handling |
| **Think Tank** | Vanilla JS | No declarative updates |
| **Timeline** | Vanilla JS + custom rendering | Brittle, hard to extend |
| **Dashboard** | Vanilla JS + Chart.js | Static, agent can't modify on-the-fly |
| **Decision Canvas** | JSON → custom renderers (FiveThings, EvidenceGrid) | Tightly coupled to specific schemas |
| **Ownership KG Viz** | (Not yet implemented) | No good solution for agent-driven graph UI |

### Integration Strategy

#### Option 1: Full A2UI Migration (Recommended)

**Replace all Command Center components with A2UI surfaces.**

**Pros**:
- Agents can **update any UI component** declaratively
- **No more brittle vanilla JS** DOM manipulation
- **Unified rendering model** across all panels
- **LLM-friendly** (agents already speak JSON)
- **Future-proof** (A2UI is an open standard)

**Cons**:
- **Migration effort** (rewrite existing components)
- **Learning curve** (team must learn A2UI catalog)

**Implementation**:

```typescript
// Baap agent sends A2UI messages to Command Center
agent.send({
  surfaceUpdate: {
    surfaceId: "kanban",
    components: [
      {
        id: "root",
        component: {
          Column: {
            children: { explicitList: ["header", "board"] }
          }
        }
      },
      {
        id: "header",
        component: {
          Text: {
            text: { literalString: "Task Board" },
            usageHint: "h1"
          }
        }
      },
      {
        id: "board",
        component: {
          Row: {
            children: { explicitList: ["todo", "inprogress", "done"] }
          }
        }
      },
      // ... define columns and cards
    ]
  }
});
```

#### Option 2: Hybrid A2UI + Custom Components

**Use A2UI for new features, keep existing vanilla JS.**

**Pros**:
- **Lower migration risk**
- **Gradual adoption**
- **Can still use custom components** (register them in A2UI catalog)

**Cons**:
- **Two rendering systems** (complexity)
- **Agents must know which system to use**

**Implementation**:

```typescript
// Register Baap's existing Kanban as a custom A2UI component
registerComponent("BaapKanban", {
  props: {
    tasks: { type: "array", required: true }
  },
  render: (props, context) => {
    // Wrap existing vanilla JS Kanban
    return html`<baap-kanban .tasks=${props.tasks}></baap-kanban>`;
  }
});

// Agent can now use it
agent.send({
  surfaceUpdate: {
    surfaceId: "main",
    components: [
      {
        id: "kanban",
        component: {
          BaapKanban: {
            tasks: [
              { id: 1, title: "Fix auth bug", column: "todo" },
              { id: 2, title: "Deploy to staging", column: "inprogress" }
            ]
          }
        }
      }
    ]
  }
});
```

#### Option 3: A2UI for Decision Canvas Only

**Use A2UI only for rendering investigation results.**

**Pros**:
- **Minimal disruption** to existing code
- **Immediate value** (Decision Canvas is the most dynamic UI)
- **Agents can render custom charts** without schema changes

**Cons**:
- **Limited scope** (misses opportunity to unify other UIs)
- **Still have two rendering systems**

**Implementation**:

```typescript
// Decision Canvas investigation result
agent.send({
  surfaceUpdate: {
    surfaceId: "investigation",
    components: [
      {
        id: "root",
        component: {
          Column: {
            children: { explicitList: ["fivethings", "evidence", "chart", "actions"] }
          }
        }
      },
      {
        id: "fivethings",
        component: {
          Card: {
            children: { explicitList: ["ft1", "ft2", "ft3", "ft4", "ft5"] }
          }
        }
      },
      {
        id: "ft1",
        component: {
          Text: {
            text: { literalString: "ROAS dropped from 4.0x to 2.8x (-30%)" },
            usageHint: "body"
          }
        }
      },
      // ... FiveThings items
      {
        id: "chart",
        component: {
          Chart: {
            type: "line",
            data: {
              labels: ["Jan 1", "Jan 2", "Jan 3", "Jan 4", "Jan 5"],
              datasets: [
                {
                  label: "ROAS",
                  data: [4.0, 3.9, 3.5, 3.0, 2.8]
                }
              ]
            }
          }
        }
      },
      {
        id: "actions",
        component: {
          Row: {
            children: { explicitList: ["approve", "reject"] }
          }
        }
      },
      {
        id: "approve",
        component: {
          Button: {
            text: { literalString: "Approve" },
            actionName: "approve-investigation",
            style: "primary"
          }
        }
      },
      {
        id: "reject",
        component: {
          Button: {
            text: { literalString: "Reject" },
            actionName: "reject-investigation",
            style: "secondary"
          }
        }
      }
    ]
  }
});
```

### Use Case: Ownership KG Visualization

**Problem**: Baap has an Ownership Knowledge Graph (files, modules, tests, owners) but no good way to visualize it.

**Solution**: Create a custom A2UI component for interactive graph rendering.

```typescript
// Register custom KG component
registerComponent("OwnershipGraph", {
  props: {
    nodes: { type: "array", required: true },
    edges: { type: "array", required: true },
    focusNode: { type: "string", required: false }
  },
  render: (props, context) => {
    return html`
      <div class="kg-graph">
        <svg>
          ${props.edges.map(edge => html`
            <line
              x1=${edge.x1}
              y1=${edge.y1}
              x2=${edge.x2}
              y2=${edge.y2}
              stroke="#666"
            />
          `)}
          ${props.nodes.map(node => html`
            <circle
              cx=${node.x}
              cy=${node.y}
              r=${node.id === props.focusNode ? 12 : 8}
              fill=${node.color}
              @click=${() => context.sendUserAction("node-click", { nodeId: node.id })}
            />
            <text x=${node.x} y=${node.y + 20}>${node.label}</text>
          `)}
        </svg>
      </div>
    `;
  }
});

// Agent sends KG data
agent.send({
  surfaceUpdate: {
    surfaceId: "ownership",
    components: [
      {
        id: "graph",
        component: {
          OwnershipGraph: {
            nodes: [
              { id: "auth.py", x: 100, y: 100, label: "auth.py", color: "#4CAF50" },
              { id: "auth_test.py", x: 200, y: 100, label: "auth_test.py", color: "#2196F3" },
              { id: "alice", x: 150, y: 200, label: "Alice", color: "#FF9800" }
            ],
            edges: [
              { x1: 100, y1: 100, x2: 200, y2: 100 },  // auth.py → auth_test.py
              { x1: 100, y1: 100, x2: 150, y2: 200 },  // auth.py → Alice
              { x1: 200, y1: 100, x2: 150, y2: 200 }   // auth_test.py → Alice
            ],
            focusNode: "auth.py"
          }
        }
      }
    ]
  }
});
```

### Use Case: Agent Work-in-Progress Stream

**Problem**: When agents make file changes, run tests, or query the KG, users have no visibility.

**Solution**: Stream agent actions to Canvas as A2UI components.

```typescript
// Agent updates Canvas with live progress
agent.send({
  surfaceUpdate: {
    surfaceId: "progress",
    components: [
      {
        id: "root",
        component: {
          Column: {
            children: { explicitList: ["title", "steps"] }
          }
        }
      },
      {
        id: "title",
        component: {
          Text: {
            text: { literalString: "Agent Progress" },
            usageHint: "h2"
          }
        }
      },
      {
        id: "steps",
        component: {
          Column: {
            children: { explicitList: ["step1", "step2", "step3"] }
          }
        }
      },
      {
        id: "step1",
        component: {
          Row: {
            children: { explicitList: ["step1-icon", "step1-text"] }
          }
        }
      },
      {
        id: "step1-icon",
        component: {
          Text: {
            text: { literalString: "✅" },
            usageHint: "body"
          }
        }
      },
      {
        id: "step1-text",
        component: {
          Text: {
            text: { literalString: "Edited src/auth.py (added rate limiting)" },
            usageHint: "body"
          }
        }
      },
      {
        id: "step2",
        component: {
          Row: {
            children: { explicitList: ["step2-icon", "step2-text"] }
          }
        }
      },
      {
        id: "step2-icon",
        component: {
          Text: {
            text: { literalString: "⏳" },
            usageHint: "body"
          }
        }
      },
      {
        id: "step2-text",
        component: {
          Text: {
            text: { literalString: "Running tests/test_auth.py..." },
            usageHint: "body"
          }
        }
      },
      {
        id: "step3",
        component: {
          Row: {
            children: { explicitList: ["step3-icon", "step3-text"] }
          }
        }
      },
      {
        id: "step3-icon",
        component: {
          Text: {
            text: { literalString: "⏸️" },
            usageHint: "body"
          }
        }
      },
      {
        id: "step3-text",
        component: {
          Text: {
            text: { literalString: "Querying KG for dependent modules..." },
            usageHint: "body"
          }
        }
      }
    ]
  }
});

// Update step2 when tests pass
agent.send({
  surfaceUpdate: {
    surfaceId: "progress",
    components: [
      {
        id: "step2-icon",
        component: {
          Text: {
            text: { literalString: "✅" },
            usageHint: "body"
          }
        }
      },
      {
        id: "step2-text",
        component: {
          Text: {
            text: { literalString: "Tests passed (12/12)" },
            usageHint: "body"
          }
        }
      }
    ]
  }
});
```

---

## 8. Technical Implementation Guide

### Step 1: Install A2UI Renderer

```bash
npm install @openclaw/a2ui-renderer
```

### Step 2: Embed A2UI Host in Baap UI

```html
<!-- Baap's index.html -->
<div id="command-center">
  <openclaw-a2ui-host></openclaw-a2ui-host>
</div>

<script type="module">
  import { A2UIHost } from '@openclaw/a2ui-renderer';
  
  const host = document.querySelector('openclaw-a2ui-host');
  
  // Connect to Baap's agent WebSocket
  const ws = new WebSocket('ws://localhost:8001/agent/stream');
  
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    
    if (message.surfaceUpdate) {
      host.handleSurfaceUpdate(message.surfaceUpdate);
    } else if (message.beginRendering) {
      host.handleBeginRendering(message.beginRendering);
    } else if (message.dataModelUpdate) {
      host.handleDataModelUpdate(message.dataModelUpdate);
    } else if (message.deleteSurface) {
      host.handleDeleteSurface(message.deleteSurface);
    }
  };
  
  // Send user actions back to agent
  host.addEventListener('userAction', (event) => {
    ws.send(JSON.stringify({ userAction: event.detail }));
  });
</script>
```

### Step 3: Agent Sends A2UI Messages

```python
# Baap agent (Python)
import json
import asyncio
from websockets import connect

async def send_kanban_ui():
    async with connect("ws://localhost:8001/agent/stream") as ws:
        # Send surface update
        await ws.send(json.dumps({
            "surfaceUpdate": {
                "surfaceId": "kanban",
                "components": [
                    {
                        "id": "root",
                        "component": {
                            "Column": {
                                "children": {"explicitList": ["header", "board"]}
                            }
                        }
                    },
                    {
                        "id": "header",
                        "component": {
                            "Text": {
                                "text": {"literalString": "Task Board"},
                                "usageHint": "h1"
                            }
                        }
                    },
                    # ... more components
                ]
            }
        }))
        
        # Begin rendering
        await ws.send(json.dumps({
            "beginRendering": {
                "surfaceId": "kanban",
                "root": "root"
            }
        }))
        
        # Listen for user actions
        async for message in ws:
            data = json.loads(message)
            if "userAction" in data:
                action = data["userAction"]
                print(f"User clicked: {action['name']} on {action['sourceComponentId']}")
                
                # Update UI based on action
                if action["name"] == "move-card":
                    await ws.send(json.dumps({
                        "surfaceUpdate": {
                            "surfaceId": "kanban",
                            "components": [
                                {
                                    "id": action["sourceComponentId"],
                                    "component": {
                                        "Card": {
                                            "children": {"explicitList": ["card-title"]},
                                            "style": "success"
                                        }
                                    }
                                }
                            ]
                        }
                    }))

asyncio.run(send_kanban_ui())
```

### Step 4: Register Custom Components

```typescript
// Baap custom components (TypeScript)
import { registerComponent } from '@openclaw/a2ui-renderer';
import { html } from 'lit';

// Register Decision Packet component
registerComponent('DecisionPacket', {
  props: {
    fiveThings: { type: 'array', required: true },
    evidence: { type: 'array', required: true },
    actions: { type: 'array', required: true }
  },
  render: (props, context) => {
    return html`
      <div class="decision-packet">
        <div class="five-things">
          <h2>Key Findings</h2>
          <ul>
            ${props.fiveThings.map(item => html`<li>${item}</li>`)}
          </ul>
        </div>
        
        <div class="evidence">
          <h2>Evidence</h2>
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Value</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              ${props.evidence.map(row => html`
                <tr>
                  <td>${row.metric}</td>
                  <td>${row.value}</td>
                  <td class=${row.change > 0 ? 'positive' : 'negative'}>
                    ${row.change > 0 ? '+' : ''}${row.change}%
                  </td>
                </tr>
              `)}
            </tbody>
          </table>
        </div>
        
        <div class="actions">
          <h2>Recommended Actions</h2>
          ${props.actions.map(action => html`
            <button
              @click=${() => context.sendUserAction('action-click', { actionId: action.id })}
              class=${action.risk}
            >
              ${action.label}
            </button>
          `)}
        </div>
      </div>
    `;
  }
});

// Agent can now use it
agent.send({
  surfaceUpdate: {
    surfaceId: 'investigation',
    components: [
      {
        id: 'packet',
        component: {
          DecisionPacket: {
            fiveThings: [
              'ROAS dropped from 4.0x to 2.8x (-30%)',
              'Root cause: CPC spiked by 45% in Google Shopping',
              'Triggered by competitor bidding war on "heirloom seeds"',
              'Projected 7d impact: -$15,000 revenue',
              'Recommended action: Reduce bids by 15% on high-CPC keywords'
            ],
            evidence: [
              { metric: 'ROAS', value: '2.8x', change: -30 },
              { metric: 'CPC', value: '$1.45', change: 45 },
              { metric: 'Spend', value: '$3,200', change: 12 }
            ],
            actions: [
              { id: 'reduce-bids', label: 'Reduce Bids 15%', risk: 'low' },
              { id: 'pause-campaign', label: 'Pause Campaign', risk: 'high' }
            ]
          }
        }
      }
    ]
  }
});
```

---

## 9. Performance Considerations

### A2UI Bundle Size

| Asset | Size | Notes |
|-------|------|-------|
| `a2ui.bundle.js` | ~150KB (gzipped) | Lit + standard catalog |
| Custom components | +10-50KB | Per component |

### Incremental Updates

A2UI's **incremental update model** ensures efficient rendering:

- Only changed components are re-rendered
- Data model updates don't trigger full re-render
- Lit uses virtual DOM diffing for minimal DOM manipulation

### WebSocket vs. HTTP Polling

| Method | Latency | Overhead | Recommendation |
|--------|---------|----------|----------------|
| WebSocket | <10ms | Low | **Use for live updates** (agent progress, data streams) |
| HTTP Polling | 100-1000ms | High | **Use for static content** (capsule history) |

---

## 10. Security Considerations

### Sandboxing

A2UI's **declarative model** prevents code injection:

- Agents can only render **pre-approved components**
- No `eval()` or `Function()` execution
- XSS protection via Lit's HTML sanitization

### Trust Ladder

Custom components can implement **trust levels**:

```typescript
registerComponent('TrustedIframe', {
  props: {
    url: { type: 'string', required: true },
    trustLevel: { type: 'string', required: true }
  },
  render: (props, context) => {
    if (props.trustLevel === 'low') {
      // Sandboxed iframe (no scripts, no forms)
      return html`<iframe src=${props.url} sandbox=""></iframe>`;
    } else if (props.trustLevel === 'medium') {
      // Allow scripts but block forms
      return html`<iframe src=${props.url} sandbox="allow-scripts"></iframe>`;
    } else if (props.trustLevel === 'high') {
      // Full access
      return html`<iframe src=${props.url}></iframe>`;
    }
  }
});
```

### Content Security Policy

Canvas enforces **CSP headers**:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
```

---

## 11. Comparison: A2UI vs. Existing Solutions

| Solution | Security | Flexibility | LLM-Friendly | Framework-Agnostic | Incremental Updates |
|----------|----------|-------------|--------------|--------------------|--------------------|
| **A2UI** | ✅ Declarative | ✅ Custom components | ✅ JSON format | ✅ Lit/Angular/Flutter/React | ✅ ID-based updates |
| **React Server Components** | ⚠️ Requires trust | ✅ Full React | ⚠️ JSX (not JSON) | ❌ React-only | ✅ Reconciliation |
| **HTML over WebSocket** | ❌ XSS risk | ✅ Full HTML/CSS/JS | ❌ Not structured | ✅ Browser-native | ❌ Full page reloads |
| **JSON → Custom Renderer** | ✅ Safe | ⚠️ Limited to schema | ✅ JSON format | ⚠️ Custom per app | ⚠️ Depends on impl |

**Verdict**: A2UI strikes the best balance for **agent-driven UIs** that need security, flexibility, and LLM-friendliness.

---

## 12. Recommendations for Baap

### Immediate Actions (Week 1-2)

1. **Install A2UI renderer** in Baap's UI (`npm install @openclaw/a2ui-renderer`)
2. **Create a test surface** (e.g., "Hello World" card) in Command Center
3. **Send a simple A2UI message** from a Baap agent to verify WebSocket plumbing

### Short-Term Wins (Month 1)

4. **Migrate Decision Canvas** to A2UI (replace FiveThings/EvidenceGrid custom renderers)
5. **Register custom DecisionPacket component** with FiveThings, Evidence, Actions sections
6. **Stream agent progress** to Canvas (file edits, test runs, KG queries)

### Medium-Term Goals (Month 2-3)

7. **Migrate Kanban Board** to A2UI (replace vanilla JS drag-and-drop with A2UI Row/Column/Card)
8. **Build Ownership KG visualizer** as custom A2UI component (interactive graph with node-click actions)
9. **Add agent-driven dashboards** (agents can create custom charts on-the-fly)

### Long-Term Vision (Quarter 2)

10. **Replace all Command Center components** with A2UI surfaces
11. **Extend A2UI catalog** with Baap-specific components (CodeBlock, TestResult, KGQuery, PRDiff)
12. **Open-source Baap's A2UI components** (contribute back to A2UI ecosystem)

### Technical Debt to Address

| Issue | Current State | A2UI Solution |
|-------|---------------|---------------|
| **Brittle DOM manipulation** | Vanilla JS `appendChild()` | Declarative components |
| **Hard to update UIs** | Manual event handlers | `dataModelUpdate` messages |
| **Agent-UI coupling** | Agents must know HTML structure | Agents send abstract component tree |
| **No UI versioning** | Breaking changes on schema updates | Client reports `clientUiCapabilities` |

---

## 13. Open Questions

1. **Does Baap need multi-surface support?** (e.g., separate surfaces for Kanban, Timeline, Dashboard)
   - **Answer**: Yes, likely 3-5 surfaces (command-center, kanban, decision-canvas, ownership-kg, timeline)

2. **Should Baap agents generate A2UI JSON directly, or use a template system?**
   - **Recommendation**: Start with templates (easier to test), migrate to LLM-generated JSON later

3. **How will Baap handle A2UI version upgrades?** (v0.8 → v0.9 → v1.0)
   - **Recommendation**: Use `clientUiCapabilities` to negotiate supported versions

4. **Should Baap fork A2UI or use upstream?**
   - **Recommendation**: Use upstream for now, contribute custom components back to A2UI

5. **How will Baap agents coordinate multiple surfaces?** (e.g., update Kanban and Decision Canvas simultaneously)
   - **Recommendation**: Use WebSocket channels or surface namespacing

---

## 14. Conclusion

OpenClaw's **Canvas** and **A2UI** provide a mature, battle-tested solution for agent-driven visual workspaces. By adopting A2UI, Baap can:

- **Eliminate brittle vanilla JS** UI code
- **Enable agents to drive UIs declaratively** without code execution risks
- **Unify rendering across all panels** (Kanban, Timeline, Dashboard, Decision Canvas)
- **Future-proof** UI architecture with an open, framework-agnostic standard

The **recommended path forward** is:

1. **Start small** (Decision Canvas only)
2. **Prove the model** (test with real investigations)
3. **Expand incrementally** (Kanban → Timeline → Dashboard)
4. **Contribute back** (open-source Baap's custom components)

By year-end, Baap could have a **fully agent-driven Command Center** where agents generate custom UIs for every task, investigation, and insight—without writing a single line of UI code.

---

## Appendix A: A2UI Message Examples

### Example 1: Simple Card

```json
{
  "surfaceUpdate": {
    "surfaceId": "main",
    "components": [
      {
        "id": "root",
        "component": {
          "Card": {
            "children": { "explicitList": ["title", "body"] },
            "elevation": 2
          }
        }
      },
      {
        "id": "title",
        "component": {
          "Text": {
            "text": { "literalString": "Hello, Baap!" },
            "usageHint": "h1"
          }
        }
      },
      {
        "id": "body",
        "component": {
          "Text": {
            "text": { "literalString": "This card is rendered via A2UI." },
            "usageHint": "body"
          }
        }
      }
    ]
  }
}
```

### Example 2: Interactive Form

```json
{
  "surfaceUpdate": {
    "surfaceId": "form",
    "components": [
      {
        "id": "root",
        "component": {
          "Column": {
            "children": { "explicitList": ["email-input", "submit-btn"] }
          }
        }
      },
      {
        "id": "email-input",
        "component": {
          "TextField": {
            "label": { "literalString": "Email" },
            "value": { "literalString": "" },
            "placeholder": { "literalString": "you@example.com" },
            "type": "email"
          }
        }
      },
      {
        "id": "submit-btn",
        "component": {
          "Button": {
            "text": { "literalString": "Submit" },
            "actionName": "submit-form",
            "style": "primary"
          }
        }
      }
    ]
  }
}
```

### Example 3: Data Table

```json
{
  "surfaceUpdate": {
    "surfaceId": "table",
    "components": [
      {
        "id": "root",
        "component": {
          "Table": {
            "headers": { "literalList": ["Metric", "Value", "Change"] },
            "rows": {
              "literalList": [
                ["ROAS", "2.8x", "-30%"],
                ["CPC", "$1.45", "+45%"],
                ["Spend", "$3,200", "+12%"]
              ]
            },
            "sortable": true
          }
        }
      }
    ]
  }
}
```

---

## Appendix B: Baap Custom Component Registry

### DecisionPacket

Renders investigation results with FiveThings, Evidence, and Actions.

### OwnershipGraph

Interactive knowledge graph visualization with node-click actions.

### CodeDiff

Side-by-side diff viewer for file changes.

### TestResults

Test suite results with pass/fail indicators and error messages.

### Timeline

Chronological event timeline with agent actions and user interactions.

### KanbanBoard

Drag-and-drop task board with columns and cards.

---

**End of Report**

Generated: 2026-02-14  
Researcher: Claude (Sonnet 4.5)  
For: Baap AI-Native Development Platform
