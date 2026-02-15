# Canvas & A2UI Research - Executive Summary

## TL;DR

OpenClaw's **Canvas** + **A2UI** is exactly what Baap needs to replace its brittle vanilla JS UI components with agent-driven, declarative interfaces.

**Core Value Proposition**:
- Agents send JSON (not code) to render UIs → security ✅
- Incremental updates (only changed components re-render) → performance ✅
- Framework-agnostic (Lit, React, Flutter, Angular) → flexibility ✅
- LLM-friendly (flat list of components with IDs) → AI-native ✅

---

## What is Canvas?

Agent-controlled visual workspace (WKWebView/WebView panel) that displays:
- Local HTML/CSS/JS files from `~/Library/Application Support/OpenClaw/canvas/<session>/`
- A2UI-rendered components from agents
- Live-reload enabled (WebSocket watches for file changes)

**Agent API**: show/hide panel, navigate, eval JS, capture snapshot

---

## What is A2UI?

Open-source declarative JSON protocol for agents to render UIs.

**Message Types**:
1. `surfaceUpdate` → define/update components
2. `beginRendering` → start rendering a surface
3. `dataModelUpdate` → update data without structure changes
4. `deleteSurface` → remove a surface

**Client→Server**:
- `userAction` → user clicked button, submitted form, etc.
- `clientUiCapabilities` → client reports supported components
- `error` → report rendering errors

**Example**:

```json
{
  "surfaceUpdate": {
    "surfaceId": "main",
    "components": [
      {
        "id": "root",
        "component": {
          "Column": {
            "children": {"explicitList": ["title", "button"]}
          }
        }
      },
      {
        "id": "title",
        "component": {
          "Text": {
            "text": {"literalString": "Hello, Baap!"},
            "usageHint": "h1"
          }
        }
      },
      {
        "id": "button",
        "component": {
          "Button": {
            "text": {"literalString": "Click Me"},
            "actionName": "greet"
          }
        }
      }
    ]
  }
}
```

User clicks button → `userAction` event sent to agent → agent updates UI.

---

## Standard Component Catalog (v0.8)

### Layout
- Column, Row, Card, Divider, Modal

### Content
- Text, Image, Video, Audio

### Input
- Button, Checkbox, Slider, TextField

### Data
- Table, Chart

### Custom Components
Developers can register custom components (e.g., KanbanBoard, CodeDiff, OwnershipGraph).

---

## Rendering Model

**Server-Side**: Agent generates A2UI JSON  
**Client-Side**: Lit web components render the UI  
**Transport**: WebSocket or HTTP  
**Bundle Size**: ~150KB (gzipped)  

**Performance**: Incremental updates (only changed components re-render), <10ms latency over WebSocket.

---

## Security Model

**Declarative, not executable**:
- Agents can only render pre-approved components from catalog
- No `eval()` or `Function()` execution
- XSS protection via Lit's HTML sanitization

**Trust Ladder**: Custom components can implement sandboxing (e.g., iframe with `sandbox=""` attribute).

---

## Integration Opportunities for Baap

### Current Pain Points
| Component | Current Tech | Problem |
|-----------|--------------|---------|
| Kanban Board | Vanilla JS | Hard to update, fragile event handling |
| Timeline | Vanilla JS | Brittle, hard to extend |
| Dashboard | Chart.js | Static, agent can't modify on-the-fly |
| Decision Canvas | Custom JSON renderers | Tightly coupled to schemas |
| Ownership KG | (Not implemented) | No agent-driven graph UI |

### Solution: Replace with A2UI

#### Option 1: Full Migration (Recommended)
Replace **all** Command Center components with A2UI surfaces.

**Pros**: Unified rendering, agents drive everything, no brittle JS  
**Cons**: Migration effort, learning curve

#### Option 2: Hybrid
Use A2UI for new features, keep existing vanilla JS.

**Pros**: Lower risk, gradual adoption  
**Cons**: Two rendering systems (complexity)

#### Option 3: Decision Canvas Only
Use A2UI only for investigation results.

**Pros**: Minimal disruption, immediate value  
**Cons**: Limited scope, missed opportunities

---

## Recommended Path Forward

### Week 1-2: Proof of Concept
1. Install `@openclaw/a2ui-renderer` in Baap UI
2. Create test surface ("Hello World" card)
3. Send simple A2UI message from agent

### Month 1: Decision Canvas
4. Migrate Decision Canvas to A2UI
5. Register custom `DecisionPacket` component (FiveThings, Evidence, Actions)
6. Stream agent progress to Canvas (file edits, test runs, KG queries)

### Month 2-3: Expand to Other Panels
7. Migrate Kanban Board to A2UI (Row/Column/Card components)
8. Build Ownership KG visualizer (custom graph component)
9. Add agent-driven dashboards (custom charts on-the-fly)

### Quarter 2: Full Command Center Migration
10. Replace all Command Center components with A2UI
11. Extend catalog with Baap-specific components (CodeBlock, TestResult, KGQuery, PRDiff)
12. Open-source Baap's A2UI components

---

## Key Technical Details

### Installation
```bash
npm install @openclaw/a2ui-renderer
```

### Embed in HTML
```html
<openclaw-a2ui-host></openclaw-a2ui-host>
<script type="module">
  import { A2UIHost } from '@openclaw/a2ui-renderer';
  
  const host = document.querySelector('openclaw-a2ui-host');
  const ws = new WebSocket('ws://localhost:8001/agent/stream');
  
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.surfaceUpdate) host.handleSurfaceUpdate(msg.surfaceUpdate);
    if (msg.beginRendering) host.handleBeginRendering(msg.beginRendering);
  };
  
  host.addEventListener('userAction', (event) => {
    ws.send(JSON.stringify({ userAction: event.detail }));
  });
</script>
```

### Agent Sends A2UI
```python
import json
from websockets import connect

async with connect("ws://localhost:8001/agent/stream") as ws:
    await ws.send(json.dumps({
        "surfaceUpdate": {
            "surfaceId": "kanban",
            "components": [...]
        }
    }))
    
    await ws.send(json.dumps({
        "beginRendering": {
            "surfaceId": "kanban",
            "root": "root"
        }
    }))
```

### Register Custom Component
```typescript
import { registerComponent } from '@openclaw/a2ui-renderer';
import { html } from 'lit';

registerComponent('DecisionPacket', {
  props: {
    fiveThings: { type: 'array', required: true },
    evidence: { type: 'array', required: true },
    actions: { type: 'array', required: true }
  },
  render: (props, context) => {
    return html`
      <div class="decision-packet">
        <h2>Key Findings</h2>
        <ul>${props.fiveThings.map(item => html`<li>${item}</li>`)}</ul>
        
        <h2>Evidence</h2>
        <table>
          ${props.evidence.map(row => html`
            <tr>
              <td>${row.metric}</td>
              <td>${row.value}</td>
              <td>${row.change}%</td>
            </tr>
          `)}
        </table>
        
        <h2>Actions</h2>
        ${props.actions.map(action => html`
          <button @click=${() => context.sendUserAction('action-click', {actionId: action.id})}>
            ${action.label}
          </button>
        `)}
      </div>
    `;
  }
});
```

---

## Use Cases for Baap

### 1. Decision Canvas (Investigation Results)
Agent sends `DecisionPacket` component with:
- FiveThings (key findings)
- Evidence (metrics table)
- Actions (approve/reject buttons)

User clicks "Approve" → `userAction` sent to agent → agent executes action.

### 2. Ownership KG Visualization
Agent sends `OwnershipGraph` component with:
- Nodes (files, modules, owners)
- Edges (relationships)
- FocusNode (highlighted node)

User clicks node → agent updates graph to show related nodes.

### 3. Agent Work-in-Progress Stream
Agent sends `ProgressLog` component with:
- Step 1: ✅ Edited src/auth.py
- Step 2: ⏳ Running tests...
- Step 3: ⏸️ Querying KG...

Agent updates in real-time as work progresses.

### 4. Kanban Board
Agent sends `KanbanBoard` component with:
- Columns (TODO, In Progress, Done)
- Cards (tasks with titles, assignees)

User drags card → `userAction` sent to agent → agent updates backend.

### 5. Dynamic Dashboard
Agent queries metrics API → sends `Chart` components on-the-fly:
- Line chart (ROAS trend)
- Bar chart (revenue by channel)
- Pie chart (spend by device)

User changes date range → agent re-queries and updates charts.

---

## Comparison: A2UI vs. Alternatives

| Solution | Security | LLM-Friendly | Incremental | Framework-Agnostic |
|----------|----------|--------------|-------------|--------------------|
| **A2UI** | ✅ Declarative | ✅ JSON | ✅ ID-based | ✅ Lit/React/Flutter |
| React Server Components | ⚠️ Requires trust | ⚠️ JSX | ✅ Reconciliation | ❌ React-only |
| HTML over WebSocket | ❌ XSS risk | ❌ Not structured | ❌ Full reload | ✅ Browser-native |
| Custom JSON Renderer | ✅ Safe | ✅ JSON | ⚠️ Depends | ⚠️ Custom per app |

**Winner**: A2UI (best balance for agent-driven UIs)

---

## Open Questions

1. **Multi-surface support?** → Yes, 3-5 surfaces (command-center, kanban, decision-canvas, ownership-kg, timeline)
2. **Templates vs. LLM-generated JSON?** → Start with templates, migrate to LLM later
3. **Version upgrades (v0.8 → v1.0)?** → Use `clientUiCapabilities` to negotiate
4. **Fork or upstream?** → Use upstream, contribute custom components back
5. **Multi-surface coordination?** → Use WebSocket channels or surface namespacing

---

## Bottom Line

**A2UI is the perfect fit for Baap's agent-driven Command Center.**

By adopting A2UI, Baap can:
- Eliminate brittle vanilla JS UI code
- Enable agents to drive UIs declaratively (no code execution risks)
- Unify rendering across all panels
- Future-proof with an open, framework-agnostic standard

**Recommended next step**: Migrate Decision Canvas to A2UI in Month 1, prove the model, then expand incrementally to all Command Center components.

By year-end, Baap could have a fully agent-driven Command Center where agents generate custom UIs for every task, investigation, and insight—without writing a single line of UI code.

---

**Full Report**: `/tmp/openclaw-research-output/05-canvas-a2ui.md` (1387 lines, 37KB)

**Generated**: 2026-02-14  
**Researcher**: Claude (Sonnet 4.5)
