# Interactive UX Research: From Passive Monitoring to Active Command Center

> Research compiled 2026-02-14 for a single-file vanilla JS/HTML/CSS dashboard
> monitoring an AI agent swarm. No React, no npm, no build step.

---

## Table of Contents

1. [Linear App: Why It's the Gold Standard](#1-linear-app-why-its-the-gold-standard)
2. [Notion Database Views: Multi-View Data Switching](#2-notion-database-views-multi-view-data-switching)
3. [Plane.so: Open-Source Kanban + Issues](#3-planeso-open-source-kanban--issues)
4. [GitHub Projects: Automated Status Workflows](#4-github-projects-automated-status-workflows)
5. [Retool / Internal Tools: Approval Workflows](#5-retool--internal-tools-approval-workflows)
6. [Implementation Pattern: Clipboard Paste-to-Upload](#6-implementation-pattern-clipboard-paste-to-upload)
7. [Implementation Pattern: Inline Commenting](#7-implementation-pattern-inline-commenting)
8. [Implementation Pattern: Approval Workflows](#8-implementation-pattern-approval-workflows)
9. [Implementation Pattern: Command Palette (Cmd+K)](#9-implementation-pattern-command-palette-cmdk)
10. [Implementation Pattern: Drag-and-Drop Kanban](#10-implementation-pattern-drag-and-drop-kanban)
11. [Implementation Pattern: Optimistic UI](#11-implementation-pattern-optimistic-ui)
12. [Implementation Pattern: Toast Notifications](#12-implementation-pattern-toast-notifications)
13. [Implementation Pattern: Context Menus](#13-implementation-pattern-context-menus)
14. [Implementation Pattern: Side Panel / Drawer](#14-implementation-pattern-side-panel--drawer)
15. [Visual Design: Linear-Style Dark Theme](#15-visual-design-linear-style-dark-theme)
16. [Architecture: Single-File Component Strategy](#16-architecture-single-file-component-strategy)

---

## 1. Linear App: Why It's the Gold Standard

### Design Philosophy

Linear is considered the gold standard for project management UX because of four
principles that compound together:

1. **Keyboard-First Design** -- Nearly every action can be performed without
   touching the mouse. `C` creates an issue, `A` assigns, `L` labels,
   `P` sets priority, `F` filters. Navigation uses `G` then `I` for inbox,
   `G` then `V` for current cycle. The `?` key shows all shortcuts.

2. **Command Palette (Cmd+K)** -- A single universal entry point for ANY action.
   Opens a context-aware command list. On an issue? Shows move, assign, label
   actions. On a project? Shows different commands. Users type to filter, arrow
   keys to navigate, Enter to execute.

3. **Minimal Visual Noise** -- Dark backgrounds, monochrome palette with very
   few accent colors. Bold typography for hierarchy. Glassmorphism and subtle
   gradients for depth. No competing CTAs. Each section serves one purpose.

4. **Opinionated Workflow** -- Issues flow through a predefined pipeline:
   Triage -> Backlog -> Todo -> In Progress -> Done -> Cancelled. This reduces
   decision fatigue. Users can customize, but the defaults are sensible.

### What Makes Linear Feel Fast

- **Instant transitions**: No loading spinners between views. Data is prefetched.
- **Optimistic UI**: Actions appear to complete instantly. Server syncs in background.
- **Keyboard shortcuts shown inline**: Every action in the command palette shows
  its keyboard shortcut, training users to get faster over time.
- **Real-time sync**: Changes from teammates appear immediately via WebSocket.

### Applicable Patterns for Our Dashboard

| Pattern | Implementation Difficulty | Impact |
|---------|--------------------------|--------|
| Cmd+K command palette | Medium | Very High |
| Single-key shortcuts (C, A, L) | Easy | High |
| Dark theme with accent colors | Easy | High |
| Opinionated status workflow | Easy | Medium |
| Optimistic UI on actions | Medium | High |
| Context-aware right-click menus | Medium | Medium |

Sources:
- https://linear.app/now/how-we-redesigned-the-linear-ui
- https://blog.logrocket.com/ux-design/linear-design/
- https://shortcuts.design/tools/toolspage-linear/
- https://www.morgen.so/blog-posts/linear-project-management

---

## 2. Notion Database Views: Multi-View Data Switching

### How Notion Handles View Switching

Notion allows any database to be viewed through multiple layouts, all operating
on the same underlying data:

- **Table**: Spreadsheet-like rows and columns. Best for data-dense views.
- **Board/Kanban**: Cards grouped by a Select/Multi-Select/Person property.
  Cards can be dragged between columns.
- **Timeline/Gantt**: Horizontal bars on a date axis. Bars can be resized.
- **Calendar**: Items positioned by date. Drag to reschedule.
- **List**: Minimal rows, one-line-per-item. Best for quick scanning.
- **Gallery**: Card grid with image previews.

### Key UX Details

1. **Tab-based switching**: Views are tabs at the top of the database. Click to
   switch instantly. No page reload.
2. **Each view has independent filters/sorts**: A "Board" view can filter to
   show only "In Progress" while the "Table" shows everything.
3. **Same data, different lens**: Changing a card's status in Board view
   immediately reflects in Table view.
4. **Drag actions are view-specific**: In Calendar, drag changes date. In Board,
   drag changes status column. In Timeline, drag changes duration.

### Implementation Strategy for Single-File Dashboard

```javascript
// Core pattern: Single data store, multiple render functions
const state = {
  items: [...],
  currentView: 'kanban', // 'kanban' | 'table' | 'timeline'
  filters: {},
  sorts: {}
};

const renderers = {
  kanban: (items) => renderKanbanBoard(items),
  table: (items) => renderDataTable(items),
  timeline: (items) => renderTimeline(items)
};

function switchView(viewName) {
  state.currentView = viewName;
  const container = document.getElementById('main-view');
  container.innerHTML = '';
  renderers[viewName](filterAndSort(state.items));
  // Update active tab styling
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.view === viewName);
  });
}
```

```html
<!-- View switching tabs -->
<div class="view-tabs">
  <button class="view-tab active" data-view="kanban" onclick="switchView('kanban')">
    <svg><!-- board icon --></svg> Board
  </button>
  <button class="view-tab" data-view="table" onclick="switchView('table')">
    <svg><!-- table icon --></svg> Table
  </button>
  <button class="view-tab" data-view="timeline" onclick="switchView('timeline')">
    <svg><!-- timeline icon --></svg> Timeline
  </button>
</div>
```

Sources:
- https://www.notion.com/help/views-filters-and-sorts
- https://www.notion.com/help/boards
- https://www.notion.vip/insights/compare-and-configure-notion-s-database-formats-tables-lists-galleries-boards-and-timelines

---

## 3. Plane.so: Open-Source Kanban + Issues

### What Plane Gets Right

Plane is the closest open-source equivalent to Linear. Key patterns:

1. **Five view types out of the box**: Kanban, List, Gantt, Calendar, Spreadsheet.
   Same data, different presentations.

2. **Clean, minimal interface**: No visual clutter. Lots of whitespace.
   Clear information hierarchy.

3. **Cycles and Modules**: Groups of issues with start/end dates (like sprints).
   This maps well to "agent investigation sessions" in our dashboard.

4. **Pages**: Rich text documents linked to issues. Could map to our
   "investigation notes" or "decision capsule details."

### Patterns to Steal

- **Issue states with colors**: Each status has a distinct color. The kanban
  columns use these colors for their headers. Instant visual parsing.
- **Grouping and sub-grouping**: Issues can be grouped by status, priority,
  assignee, label, or any custom property. Two levels of grouping.
- **Inline property editing**: Click a priority badge on a card to change it
  inline via dropdown. No modal needed.

Sources:
- https://plane.so
- https://github.com/makeplane/plane

---

## 4. GitHub Projects: Automated Status Workflows

### Automation Patterns

GitHub Projects offers built-in workflow automation:

1. **Auto-set on add**: When an issue is added to the project, auto-set its
   status to "Todo."
2. **Auto-move on state change**: When a PR is merged, move the linked issue
   to "Done."
3. **Auto-archive**: When items match criteria (e.g., closed > 7 days), archive them.
4. **Custom fields**: Single-select, number, date, text, iteration fields.

### Status Workflow for Agent Swarm Dashboard

Map GitHub's approach to agent task states:

```
Queued -> Running -> Needs Approval -> Approved -> Executing -> Complete
                         |                                       |
                         +-> Rejected -> Archived                +-> Failed -> Needs Retry
```

Each transition can trigger actions:
- `Running -> Needs Approval`: Play notification sound, highlight card, show timer
- `Needs Approval -> Approved`: Optimistic UI, send API call, move card
- `Failed -> Needs Retry`: Auto-move back to Queued after configurable delay

Sources:
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects
- https://docs.github.com/en/issues/organizing-your-work-with-project-boards/managing-project-boards/about-automation-for-project-boards

---

## 5. Retool / Internal Tools: Approval Workflows

### Retool's Approval Modal Pattern

Retool builds approval workflows with these components:

1. **Form for capturing requests**: Structured input with validation.
2. **Modal for handling decisions**: Shows context + approve/reject buttons.
3. **Toast notifications**: Confirmation feedback after action.
4. **Validation**: Prevents empty submissions or incomplete reviews.

### Key Design Insight

> "When making edits, ensure that anything a user is editing is displayed on
> the screen where they submit." -- Retool best practice

This means: DO NOT use tabbed forms where the submit button is on the last tab.
The user should see all relevant context when making an approval decision.

### Airplane.dev's Approach (Before Shutdown, April 2024)

Airplane treated **code as the source of truth** for internal tools. Their pattern:
- Define a task in code (e.g., "approve refund")
- Airplane auto-generates UI: form fields, submit button, confirmation
- Approval workflows are just tasks with an "approval" step

This maps perfectly to our agent swarm: each agent action that needs human
approval is a "task" with auto-generated UI showing the context and
approve/reject buttons.

Sources:
- https://retoolers.io/use-cases/change-request-approval-modal-operations-automation-tool
- https://www.cflowapps.com/approval-workflow-design-patterns/

---

## 6. Implementation Pattern: Clipboard Paste-to-Upload

### How Slack/Discord/Linear Handle Image Paste

All three use the same core browser API. The user copies a screenshot
(Cmd+Shift+4 on Mac, or copies from any image), then pastes (Cmd+V) into
a text input or contenteditable area. The app intercepts the paste event,
extracts the image blob, shows a preview, and uploads it.

### Complete Vanilla JS Implementation

```javascript
// ============================================
// CLIPBOARD IMAGE PASTE HANDLER
// Works with any element - attach to document
// for global paste, or specific container
// ============================================

const IMAGE_MIME_REGEX = /^image\/(png|jpeg|gif|webp|svg\+xml)$/i;

/**
 * Initialize paste-to-upload on a target element.
 * @param {HTMLElement} target - Element to listen for paste events
 * @param {Function} onImagePaste - Callback receiving { blob, dataUrl, file }
 */
function initPasteUpload(target, onImagePaste) {
  target.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    for (const item of items) {
      if (IMAGE_MIME_REGEX.test(item.type)) {
        e.preventDefault();

        const blob = item.getAsFile();
        const reader = new FileReader();

        reader.onload = (event) => {
          onImagePaste({
            blob,
            dataUrl: event.target.result,
            file: new File([blob], `paste-${Date.now()}.png`, { type: blob.type }),
            width: null,  // Set after image loads
            height: null
          });
        };

        reader.readAsDataURL(blob);
        return; // Only handle first image
      }
    }
  });
}

// ============================================
// USAGE: Attach to a comment input area
// ============================================

const commentBox = document.getElementById('comment-input');

initPasteUpload(commentBox, ({ blob, dataUrl, file }) => {
  // Show inline preview
  const preview = document.createElement('div');
  preview.className = 'paste-preview';
  preview.innerHTML = `
    <img src="${dataUrl}" style="max-width:300px; max-height:200px; border-radius:8px;" />
    <button onclick="this.parentElement.remove()" class="remove-btn">&times;</button>
    <span class="paste-label">Pasted image (${(blob.size / 1024).toFixed(1)}KB)</span>
  `;
  commentBox.parentElement.appendChild(preview);

  // Store blob for later upload
  commentBox._pendingImages = commentBox._pendingImages || [];
  commentBox._pendingImages.push(file);
});

// ============================================
// PROGRESSIVE ENHANCEMENT: Also support
// modern async Clipboard API for button-triggered reads
// ============================================

async function readClipboardImage() {
  if (!navigator.clipboard?.read) return null;
  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      const imageType = item.types.find(t => t.startsWith('image/'));
      if (imageType) {
        const blob = await item.getType(imageType);
        return URL.createObjectURL(blob);
      }
    }
  } catch (err) {
    // User denied permission or no image in clipboard
    console.debug('Clipboard read failed:', err.message);
  }
  return null;
}
```

### Browser Support

| API | Chrome | Firefox | Safari | Edge |
|-----|--------|---------|--------|------|
| `paste` event + `clipboardData.items` | 66+ | 63+ | 13.1+ | 79+ |
| `navigator.clipboard.read()` (async) | 76+ | 127+ | 13.1+ | 79+ |

**Recommendation**: Use the `paste` event approach. It has broader support and
does not require explicit permission prompts. The async API is only needed for
button-triggered reads (not paste events).

### CSS for Paste Preview

```css
.paste-preview {
  position: relative;
  display: inline-block;
  margin: 8px 0;
  padding: 8px;
  background: rgba(255,255,255,0.05);
  border: 1px dashed rgba(255,255,255,0.2);
  border-radius: 8px;
}

.paste-preview .remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: rgba(255,0,0,0.7);
  color: white;
  cursor: pointer;
  font-size: 12px;
  line-height: 20px;
  text-align: center;
}

.paste-preview .paste-label {
  display: block;
  font-size: 11px;
  color: rgba(255,255,255,0.5);
  margin-top: 4px;
}
```

Sources:
- https://web.dev/patterns/clipboard/paste-images
- https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/read
- https://gist.github.com/dusanmarsa/2ca9f1df36e14864328a2bb0b353332e

---

## 7. Implementation Pattern: Inline Commenting

### The Problem with Modals

Modal dialogs for commenting break the user's flow. They obscure context.
The user loses sight of surrounding cards and state. Modern tools avoid
modals for high-frequency actions like commenting.

### Alternatives That Work Without Modals

#### Pattern A: Expandable Card Footer

The card expands in-place to reveal a comment input area. Other cards shift
down to make room. Uses CSS `max-height` transition for smooth animation.

```javascript
function toggleCommentArea(cardId) {
  const card = document.querySelector(`[data-card-id="${cardId}"]`);
  const commentArea = card.querySelector('.comment-area');

  if (commentArea.classList.contains('expanded')) {
    commentArea.classList.remove('expanded');
  } else {
    commentArea.classList.add('expanded');
    commentArea.querySelector('textarea').focus();
  }
}
```

```css
.comment-area {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease, padding 0.3s ease;
  padding: 0 12px;
}

.comment-area.expanded {
  max-height: 200px;
  padding: 12px;
}

.comment-area textarea {
  width: 100%;
  min-height: 60px;
  resize: vertical;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px;
  color: inherit;
  padding: 8px;
  font-family: inherit;
  font-size: 13px;
}
```

#### Pattern B: Side Panel / Drawer

Clicking a card opens a detail panel on the right side of the screen.
The panel shows full card details + comment thread. The kanban board
remains visible and interactive on the left.

```javascript
function openDetailPanel(cardId) {
  const panel = document.getElementById('detail-panel');
  const card = state.items.find(i => i.id === cardId);

  panel.innerHTML = renderCardDetail(card);
  panel.classList.add('open');
  document.getElementById('main-content').classList.add('panel-open');
}
```

```css
#detail-panel {
  position: fixed;
  top: 0;
  right: -480px;
  width: 480px;
  height: 100vh;
  background: var(--bg-elevated);
  border-left: 1px solid var(--border);
  transition: right 0.25s ease;
  z-index: 100;
  overflow-y: auto;
  padding: 24px;
}

#detail-panel.open {
  right: 0;
  box-shadow: -10px 0 30px rgba(0,0,0,0.3);
}

#main-content.panel-open {
  margin-right: 480px;
  transition: margin-right 0.25s ease;
}
```

#### Pattern C: Popover Comment (Lightweight)

A small popover appears anchored to the card when the user clicks a comment
icon. Best for quick one-line notes. Uses `position: absolute` relative to
the card.

```javascript
function showCommentPopover(event, cardId) {
  event.stopPropagation();
  const btn = event.currentTarget;
  const rect = btn.getBoundingClientRect();

  const popover = document.createElement('div');
  popover.className = 'comment-popover';
  popover.innerHTML = `
    <textarea placeholder="Add a note..." autofocus></textarea>
    <div class="popover-actions">
      <button onclick="submitComment('${cardId}', this)">Save</button>
      <button onclick="this.closest('.comment-popover').remove()">Cancel</button>
    </div>
  `;

  // Position below the button
  popover.style.top = `${rect.bottom + 8}px`;
  popover.style.left = `${rect.left}px`;
  document.body.appendChild(popover);

  // Close on outside click
  setTimeout(() => {
    document.addEventListener('click', function closePopover(e) {
      if (!popover.contains(e.target)) {
        popover.remove();
        document.removeEventListener('click', closePopover);
      }
    });
  }, 0);
}
```

### Recommendation for Agent Swarm Dashboard

Use **Pattern B (Side Panel)** as the primary detail/comment view, with
**Pattern A (Expandable Footer)** for quick status notes on cards.
Reserve modals ONLY for destructive/irreversible actions (e.g., "Kill agent process").

---

## 8. Implementation Pattern: Approval Workflows

### Design Principles (from Retool + Cflow Research)

1. **Show full context at decision point**: Never hide relevant info behind tabs.
2. **One-click approve/reject**: Primary actions should be single-click buttons.
3. **Require reason for rejection**: Approve can be instant; reject needs explanation.
4. **Visual urgency**: Pending approvals should be visually prominent (badge count,
   pulsing indicator, color coding).
5. **Audit trail**: Show who approved what and when.

### Four Approval Workflow Types

| Type | Use Case | Agent Dashboard Example |
|------|----------|------------------------|
| **Sequential** | Chain of approvals in order | Agent recommends -> Lead reviews -> Exec approves |
| **Parallel** | Multiple reviewers simultaneously | Both data-quality and causal-analyst must approve |
| **Conditional** | Route based on criteria | Low risk = auto-approve, high risk = human review |
| **Matrix** | Role-based, not person-based | Any "admin" role can approve budget changes |

### Complete Vanilla JS Approval Component

```javascript
// ============================================
// APPROVAL CARD COMPONENT
// Renders a pending approval with context,
// approve/reject buttons, and state management
// ============================================

function renderApprovalCard(approval) {
  const urgencyColors = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#22c55e'
  };

  const card = document.createElement('div');
  card.className = `approval-card urgency-${approval.urgency}`;
  card.dataset.id = approval.id;

  card.innerHTML = `
    <div class="approval-header">
      <span class="urgency-badge" style="background:${urgencyColors[approval.urgency]}">
        ${approval.urgency.toUpperCase()}
      </span>
      <span class="approval-agent">${approval.agentName}</span>
      <span class="approval-time">${timeAgo(approval.createdAt)}</span>
    </div>

    <div class="approval-body">
      <h3 class="approval-title">${approval.title}</h3>
      <p class="approval-description">${approval.description}</p>

      ${approval.evidence ? `
        <div class="approval-evidence">
          <details>
            <summary>Evidence (${approval.evidence.length} items)</summary>
            <ul>
              ${approval.evidence.map(e => `<li>${e}</li>`).join('')}
            </ul>
          </details>
        </div>
      ` : ''}

      ${approval.impact ? `
        <div class="approval-impact">
          <span class="impact-label">Projected Impact:</span>
          <span class="impact-value">${approval.impact}</span>
        </div>
      ` : ''}
    </div>

    <div class="approval-actions">
      <button class="btn-approve" onclick="handleApproval('${approval.id}', 'approve')">
        <svg width="16" height="16" viewBox="0 0 16 16"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" fill="currentColor"/></svg>
        Approve
      </button>
      <button class="btn-reject" onclick="showRejectReason('${approval.id}')">
        <svg width="16" height="16" viewBox="0 0 16 16"><path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" fill="currentColor"/></svg>
        Reject
      </button>
      <button class="btn-snooze" onclick="snoozeApproval('${approval.id}', 30)">
        Snooze 30m
      </button>
    </div>

    <div class="reject-reason-area" style="display:none">
      <textarea placeholder="Reason for rejection (required)..."></textarea>
      <div class="reject-actions">
        <button onclick="submitRejection('${approval.id}')">Confirm Reject</button>
        <button onclick="hideRejectReason('${approval.id}')">Cancel</button>
      </div>
    </div>
  `;

  return card;
}

// ============================================
// APPROVAL STATE MACHINE WITH OPTIMISTIC UI
// ============================================

async function handleApproval(id, action) {
  const card = document.querySelector(`[data-id="${id}"]`);
  const originalHTML = card.innerHTML;

  // Optimistic: immediately show approved state
  card.classList.add('approved');
  card.querySelector('.approval-actions').innerHTML = `
    <span class="status-approved">Approved - sending to agent...</span>
  `;

  try {
    const response = await fetch(`/api/approvals/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, approvedBy: 'human', timestamp: Date.now() })
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    // Success: animate card out
    card.style.transition = 'all 0.3s ease';
    card.style.opacity = '0';
    card.style.transform = 'translateX(100px)';
    setTimeout(() => card.remove(), 300);

    showToast(`Approved: ${card.querySelector('.approval-title').textContent}`, 'success');
  } catch (err) {
    // Rollback: restore original state
    card.classList.remove('approved');
    card.innerHTML = originalHTML;
    showToast(`Failed to approve: ${err.message}`, 'error');
  }
}

function showRejectReason(id) {
  const card = document.querySelector(`[data-id="${id}"]`);
  card.querySelector('.reject-reason-area').style.display = 'block';
  card.querySelector('.reject-reason-area textarea').focus();
}

function hideRejectReason(id) {
  const card = document.querySelector(`[data-id="${id}"]`);
  card.querySelector('.reject-reason-area').style.display = 'none';
}

async function submitRejection(id) {
  const card = document.querySelector(`[data-id="${id}"]`);
  const reason = card.querySelector('.reject-reason-area textarea').value.trim();

  if (!reason) {
    card.querySelector('.reject-reason-area textarea').classList.add('error');
    return;
  }

  // Optimistic rejection
  card.classList.add('rejected');
  card.querySelector('.approval-actions').innerHTML = `
    <span class="status-rejected">Rejected - notifying agent...</span>
  `;

  try {
    await fetch(`/api/approvals/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'reject', reason, rejectedBy: 'human', timestamp: Date.now() })
    });

    setTimeout(() => card.remove(), 2000);
    showToast(`Rejected with reason`, 'warning');
  } catch (err) {
    showToast(`Failed to reject: ${err.message}`, 'error');
  }
}
```

```css
.approval-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  transition: all 0.2s ease;
  border-left: 3px solid transparent;
}

.approval-card.urgency-critical {
  border-left-color: #ef4444;
  animation: pulse-border 2s infinite;
}

.approval-card.urgency-high {
  border-left-color: #f97316;
}

@keyframes pulse-border {
  0%, 100% { border-left-color: #ef4444; }
  50% { border-left-color: #fca5a5; }
}

.approval-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.btn-approve {
  background: #22c55e;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: transform 0.1s, background 0.2s;
}

.btn-approve:hover {
  background: #16a34a;
  transform: scale(1.02);
}

.btn-approve:active {
  transform: scale(0.98);
}

.btn-reject {
  background: transparent;
  color: #ef4444;
  border: 1px solid #ef4444;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-reject:hover {
  background: rgba(239, 68, 68, 0.1);
}

.btn-snooze {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-left: auto;
}

.approval-card.approved {
  background: rgba(34, 197, 94, 0.05);
  border-color: rgba(34, 197, 94, 0.3);
}

.approval-card.rejected {
  background: rgba(239, 68, 68, 0.05);
  border-color: rgba(239, 68, 68, 0.3);
}
```

Sources:
- https://retoolers.io/use-cases/change-request-approval-modal-operations-automation-tool
- https://www.cflowapps.com/approval-workflow-design-patterns/

---

## 9. Implementation Pattern: Command Palette (Cmd+K)

### Why This Matters

The command palette is the single highest-impact UX pattern for power users.
It replaces menus, navigation, and toolbar buttons with a single searchable
interface. Linear, VS Code, Slack, Raycast, Superhuman, and GitHub all use it.

### Is It Feasible in Vanilla JS?

**Yes, absolutely.** The `light-cmd-palette` library proves this can be done
in pure vanilla JS + CSS with zero dependencies. The core is ~200 lines.

### Complete Implementation

```javascript
// ============================================
// COMMAND PALETTE (Cmd+K)
// Vanilla JS, zero dependencies, ~250 lines
// ============================================

class CommandPalette {
  constructor() {
    this.commands = [];
    this.filteredCommands = [];
    this.selectedIndex = 0;
    this.isOpen = false;
    this.overlay = null;
    this.input = null;
    this.list = null;

    this._createDOM();
    this._bindKeys();
  }

  /**
   * Register commands.
   * @param {Array<{id, name, description, shortcut, category, action, icon}>} commands
   */
  register(commands) {
    this.commands = commands;
    this.filteredCommands = [...commands];
  }

  _createDOM() {
    // Overlay
    this.overlay = document.createElement('div');
    this.overlay.className = 'cmd-palette-overlay';
    this.overlay.addEventListener('click', () => this.close());

    // Container
    const container = document.createElement('div');
    container.className = 'cmd-palette';
    container.addEventListener('click', (e) => e.stopPropagation());

    // Search input
    this.input = document.createElement('input');
    this.input.className = 'cmd-palette-input';
    this.input.placeholder = 'Type a command...';
    this.input.addEventListener('input', () => this._filter());
    this.input.addEventListener('keydown', (e) => this._handleNav(e));

    // Results list
    this.list = document.createElement('div');
    this.list.className = 'cmd-palette-list';

    // Hint bar
    const hints = document.createElement('div');
    hints.className = 'cmd-palette-hints';
    hints.innerHTML = `
      <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> Navigate</span>
      <span><kbd>Enter</kbd> Execute</span>
      <span><kbd>Esc</kbd> Close</span>
    `;

    container.appendChild(this.input);
    container.appendChild(this.list);
    container.appendChild(hints);
    this.overlay.appendChild(container);
    document.body.appendChild(this.overlay);
  }

  _bindKeys() {
    document.addEventListener('keydown', (e) => {
      // Cmd+K or Ctrl+K to toggle
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.isOpen ? this.close() : this.open();
      }
      // Escape to close
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
    });
  }

  open() {
    this.isOpen = true;
    this.overlay.classList.add('visible');
    this.input.value = '';
    this.selectedIndex = 0;
    this._filter();
    // Slight delay to ensure transition plays
    requestAnimationFrame(() => this.input.focus());
  }

  close() {
    this.isOpen = false;
    this.overlay.classList.remove('visible');
    this.input.blur();
  }

  _filter() {
    const query = this.input.value.toLowerCase().trim();

    if (!query) {
      this.filteredCommands = [...this.commands];
    } else {
      // Fuzzy match: each character of query must appear in order
      this.filteredCommands = this.commands.filter(cmd => {
        const target = (cmd.name + ' ' + (cmd.description || '') + ' ' + (cmd.category || '')).toLowerCase();
        let qi = 0;
        for (let i = 0; i < target.length && qi < query.length; i++) {
          if (target[i] === query[qi]) qi++;
        }
        return qi === query.length;
      });

      // Score by how early matches appear
      this.filteredCommands.sort((a, b) => {
        const aIdx = a.name.toLowerCase().indexOf(query[0]);
        const bIdx = b.name.toLowerCase().indexOf(query[0]);
        return aIdx - bIdx;
      });
    }

    this.selectedIndex = 0;
    this._render();
  }

  _handleNav(e) {
    const len = this.filteredCommands.length;
    if (!len) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.selectedIndex = (this.selectedIndex + 1) % len;
      this._render();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.selectedIndex = (this.selectedIndex - 1 + len) % len;
      this._render();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const cmd = this.filteredCommands[this.selectedIndex];
      if (cmd) {
        this.close();
        cmd.action();
      }
    }
  }

  _render() {
    // Group by category
    const groups = {};
    this.filteredCommands.forEach(cmd => {
      const cat = cmd.category || 'Actions';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(cmd);
    });

    let html = '';
    let globalIdx = 0;

    for (const [category, cmds] of Object.entries(groups)) {
      html += `<div class="cmd-palette-category">${category}</div>`;
      for (const cmd of cmds) {
        const isSelected = globalIdx === this.selectedIndex;
        html += `
          <div class="cmd-palette-item ${isSelected ? 'selected' : ''}"
               data-index="${globalIdx}"
               onmouseenter="cmdPalette.selectedIndex=${globalIdx}; cmdPalette._render()"
               onclick="cmdPalette.filteredCommands[${globalIdx}].action(); cmdPalette.close()">
            ${cmd.icon ? `<span class="cmd-icon">${cmd.icon}</span>` : ''}
            <div class="cmd-text">
              <span class="cmd-name">${cmd.name}</span>
              ${cmd.description ? `<span class="cmd-desc">${cmd.description}</span>` : ''}
            </div>
            ${cmd.shortcut ? `<kbd class="cmd-shortcut">${cmd.shortcut}</kbd>` : ''}
          </div>
        `;
        globalIdx++;
      }
    }

    this.list.innerHTML = html || '<div class="cmd-palette-empty">No commands found</div>';

    // Scroll selected item into view
    const selected = this.list.querySelector('.selected');
    if (selected) selected.scrollIntoView({ block: 'nearest' });
  }
}

// ============================================
// INITIALIZATION
// ============================================

const cmdPalette = new CommandPalette();

cmdPalette.register([
  // Navigation
  { name: 'Go to Dashboard', description: 'Main overview', category: 'Navigation',
    shortcut: 'G D', icon: '&#9633;', action: () => switchView('dashboard') },
  { name: 'Go to Kanban Board', description: 'Agent task board', category: 'Navigation',
    shortcut: 'G K', icon: '&#9632;', action: () => switchView('kanban') },
  { name: 'Go to Approvals', description: 'Pending human approvals', category: 'Navigation',
    shortcut: 'G A', icon: '&#9888;', action: () => switchView('approvals') },

  // Agent Actions
  { name: 'Start Investigation', description: 'Launch a new metric investigation', category: 'Agent',
    shortcut: 'I', icon: '&#128269;', action: () => startInvestigation() },
  { name: 'Approve All Low-Risk', description: 'Batch approve low-risk actions', category: 'Agent',
    action: () => batchApprove('low') },
  { name: 'Pause All Agents', description: 'Emergency stop all running agents', category: 'Agent',
    shortcut: 'Ctrl+Shift+P', icon: '&#9632;', action: () => pauseAllAgents() },

  // View Controls
  { name: 'Toggle Dark/Light Mode', category: 'Settings',
    action: () => toggleTheme() },
  { name: 'Toggle Sound Notifications', category: 'Settings',
    action: () => toggleSound() },
  { name: 'Refresh Data', category: 'Actions',
    shortcut: 'R', action: () => refreshAllData() },
]);
```

### Command Palette CSS

```css
.cmd-palette-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  justify-content: center;
  padding-top: 15vh;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.cmd-palette-overlay.visible {
  opacity: 1;
  pointer-events: auto;
}

.cmd-palette {
  width: 560px;
  max-height: 480px;
  background: var(--bg-elevated, #1c1c1e);
  border: 1px solid var(--border, rgba(255,255,255,0.1));
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 50px rgba(0,0,0,0.5);
  transform: translateY(-10px);
  transition: transform 0.15s ease;
}

.cmd-palette-overlay.visible .cmd-palette {
  transform: translateY(0);
}

.cmd-palette-input {
  width: 100%;
  padding: 16px 20px;
  border: none;
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.1));
  background: transparent;
  color: var(--text, #fff);
  font-size: 16px;
  outline: none;
}

.cmd-palette-input::placeholder {
  color: var(--text-muted, rgba(255,255,255,0.4));
}

.cmd-palette-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.cmd-palette-category {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted, rgba(255,255,255,0.4));
  padding: 8px 12px 4px;
}

.cmd-palette-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.1s;
}

.cmd-palette-item:hover,
.cmd-palette-item.selected {
  background: rgba(255, 255, 255, 0.08);
}

.cmd-icon {
  width: 20px;
  text-align: center;
  font-size: 14px;
  opacity: 0.7;
}

.cmd-text {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.cmd-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text, #fff);
}

.cmd-desc {
  font-size: 12px;
  color: var(--text-muted, rgba(255,255,255,0.4));
}

.cmd-shortcut {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255,255,255,0.1);
  color: var(--text-muted, rgba(255,255,255,0.5));
  font-family: monospace;
  white-space: nowrap;
}

.cmd-palette-hints {
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  border-top: 1px solid var(--border, rgba(255,255,255,0.1));
  font-size: 11px;
  color: var(--text-muted, rgba(255,255,255,0.3));
}

.cmd-palette-hints kbd {
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(255,255,255,0.1);
  font-family: monospace;
  margin: 0 2px;
}

.cmd-palette-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-muted, rgba(255,255,255,0.3));
}
```

### Single-Key Shortcuts (Linear-Style)

```javascript
// ============================================
// GLOBAL KEYBOARD SHORTCUTS
// Only active when no input/textarea focused
// ============================================

document.addEventListener('keydown', (e) => {
  // Skip if typing in an input
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return; // Let cmd+k and system shortcuts through

  switch (e.key) {
    case '?': showKeyboardShortcutsHelp(); break;
    case 'c': createNewTask(); break;
    case 'a': openAssignDropdown(); break;
    case 'r': refreshAllData(); break;
    case 'f': toggleFilterPanel(); break;
    case '1': switchView('kanban'); break;
    case '2': switchView('table'); break;
    case '3': switchView('timeline'); break;
    case 'j': selectNextCard(); break;  // Vim-style down
    case 'k': selectPrevCard(); break;  // Vim-style up
    case 'Enter': openSelectedCard(); break;
    case 'x': toggleCardSelection(); break;
    case 'Escape': clearSelection(); break;
  }
});
```

Sources:
- https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/
- https://github.com/julianmateu/light-cmd-palette
- https://github.com/stefanjudis/awesome-command-palette
- https://www.commandpalette.org/

---

## 10. Implementation Pattern: Drag-and-Drop Kanban

### HTML5 Drag and Drop: Is It Sufficient?

**Yes, with caveats.** The native HTML5 Drag and Drop API is sufficient for a
good kanban UX. You do NOT need a library. The MDN tutorial provides a complete
working implementation. The main limitation is that touch devices need additional
handling (pointer events or a polyfill).

### Key Events

| Event | Target | Purpose |
|-------|--------|---------|
| `dragstart` | Card | Mark which card is being dragged, set data |
| `dragover` | Column | Show where card will drop (placeholder), `preventDefault()` to allow drop |
| `dragleave` | Column | Remove placeholder when cursor exits column |
| `drop` | Column | Move card DOM element to new column, update state |
| `dragend` | Card | Clean up visual styles (opacity, etc.) |

### Complete Implementation

```javascript
// ============================================
// DRAG-AND-DROP KANBAN BOARD
// Pure HTML5 API, no library, ~100 lines
// ============================================

let draggedCard = null;

function initKanbanDragDrop() {
  // Make all cards draggable
  document.querySelectorAll('.kanban-card').forEach(card => {
    card.draggable = true;

    card.addEventListener('dragstart', (e) => {
      draggedCard = card;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', card.dataset.id);

      // Ghost image: slightly transparent version of the card
      // (Browser default is usually fine, but you can customize)
      requestAnimationFrame(() => {
        card.style.opacity = '0.3';
      });
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      card.style.opacity = '1';
      draggedCard = null;

      // Remove all placeholders
      document.querySelectorAll('.drop-placeholder').forEach(p => p.remove());
      document.querySelectorAll('.drag-over').forEach(c => c.classList.remove('drag-over'));
    });
  });

  // Make columns accept drops
  document.querySelectorAll('.kanban-column').forEach(column => {
    const dropZone = column.querySelector('.kanban-cards');

    column.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      column.classList.add('drag-over');

      // Position placeholder at cursor location
      const afterElement = getDragAfterElement(dropZone, e.clientY);
      const placeholder = getOrCreatePlaceholder();

      if (afterElement) {
        dropZone.insertBefore(placeholder, afterElement);
      } else {
        dropZone.appendChild(placeholder);
      }
    });

    column.addEventListener('dragleave', (e) => {
      // Only remove styles if actually leaving the column
      if (!column.contains(e.relatedTarget)) {
        column.classList.remove('drag-over');
        column.querySelector('.drop-placeholder')?.remove();
      }
    });

    column.addEventListener('drop', (e) => {
      e.preventDefault();
      column.classList.remove('drag-over');

      const placeholder = column.querySelector('.drop-placeholder');
      if (!draggedCard || !placeholder) return;

      // Insert card where placeholder is
      dropZone.insertBefore(draggedCard, placeholder);
      placeholder.remove();

      // Update state
      const cardId = draggedCard.dataset.id;
      const newStatus = column.dataset.status;
      updateCardStatus(cardId, newStatus);
    });
  });
}

// Find the card that the cursor is directly above
function getDragAfterElement(container, y) {
  const cards = [...container.querySelectorAll('.kanban-card:not(.dragging)')];

  let closest = null;
  let closestOffset = Number.NEGATIVE_INFINITY;

  cards.forEach(card => {
    const box = card.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;

    if (offset < 0 && offset > closestOffset) {
      closestOffset = offset;
      closest = card;
    }
  });

  return closest;
}

function getOrCreatePlaceholder() {
  let placeholder = document.querySelector('.drop-placeholder');
  if (!placeholder) {
    placeholder = document.createElement('div');
    placeholder.className = 'drop-placeholder';
  }
  return placeholder;
}

async function updateCardStatus(cardId, newStatus) {
  // Optimistic: state already updated in DOM
  try {
    await fetch(`/api/tasks/${cardId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    showToast(`Moved to ${newStatus}`, 'success');
  } catch (err) {
    showToast(`Failed to update: ${err.message}`, 'error');
    // TODO: rollback DOM change
  }
}
```

### Kanban CSS with Smooth Animations

```css
/* ---- Column Layout ---- */
.kanban-board {
  display: flex;
  gap: 16px;
  padding: 16px;
  overflow-x: auto;
  height: calc(100vh - 120px);
}

.kanban-column {
  flex: 0 0 300px;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface, rgba(255,255,255,0.03));
  border-radius: 10px;
  padding: 12px;
  transition: background 0.2s;
}

.kanban-column.drag-over {
  background: rgba(99, 102, 241, 0.05);
  outline: 2px dashed rgba(99, 102, 241, 0.3);
  outline-offset: -2px;
}

.kanban-column-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px 12px;
  font-weight: 600;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-muted);
}

.kanban-column-header .count {
  background: rgba(255,255,255,0.1);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 11px;
}

.kanban-cards {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 50px;
}

/* ---- Card ---- */
.kanban-card {
  background: var(--bg-card, rgba(255,255,255,0.06));
  border: 1px solid var(--border, rgba(255,255,255,0.08));
  border-radius: 8px;
  padding: 12px;
  cursor: grab;
  transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s;
  user-select: none;
}

.kanban-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  border-color: rgba(255,255,255,0.15);
}

.kanban-card:active {
  cursor: grabbing;
}

.kanban-card.dragging {
  opacity: 0.3;
  transform: rotate(2deg);
}

/* ---- Drop Placeholder ---- */
.drop-placeholder {
  height: 60px;
  border: 2px dashed rgba(99, 102, 241, 0.4);
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.05);
  transition: height 0.15s ease;
}

/* ---- Status Colors ---- */
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.status-dot.queued { background: #6b7280; }
.status-dot.running { background: #3b82f6; animation: pulse 1.5s infinite; }
.status-dot.needs-approval { background: #f59e0b; animation: pulse 1s infinite; }
.status-dot.approved { background: #22c55e; }
.status-dot.failed { background: #ef4444; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

### Touch Device Support

HTML5 drag-and-drop does not work on mobile. For touch support, use pointer
events as a fallback:

```javascript
// Simplified touch fallback (add alongside HTML5 DnD)
if ('ontouchstart' in window) {
  document.querySelectorAll('.kanban-card').forEach(card => {
    let startX, startY, clone;

    card.addEventListener('touchstart', (e) => {
      const touch = e.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;

      // Long press to start drag
      card._longPressTimer = setTimeout(() => {
        clone = card.cloneNode(true);
        clone.classList.add('touch-dragging');
        document.body.appendChild(clone);
        card.classList.add('dragging');
      }, 300);
    });

    card.addEventListener('touchmove', (e) => {
      clearTimeout(card._longPressTimer);
      if (!clone) return;
      e.preventDefault();
      const touch = e.touches[0];
      clone.style.position = 'fixed';
      clone.style.left = `${touch.clientX - 150}px`;
      clone.style.top = `${touch.clientY - 30}px`;
    });

    card.addEventListener('touchend', (e) => {
      clearTimeout(card._longPressTimer);
      if (!clone) return;
      // Detect which column the touch ended over
      const touch = e.changedTouches[0];
      clone.style.display = 'none';
      const target = document.elementFromPoint(touch.clientX, touch.clientY);
      clone.remove();
      card.classList.remove('dragging');

      const column = target?.closest('.kanban-column');
      if (column) {
        column.querySelector('.kanban-cards').appendChild(card);
        updateCardStatus(card.dataset.id, column.dataset.status);
      }
    });
  });
}
```

Sources:
- https://developer.mozilla.org/en-US/docs/Web/API/HTML_Drag_and_Drop_API/Kanban_board
- https://www.geeksforgeeks.org/javascript/build-a-drag-drop-kanban-board-using-html-css-javascript/
- https://github.com/flowforfrank/drag-n-drop

---

## 11. Implementation Pattern: Optimistic UI

### Core Principle

Update the UI instantly (< 100ms), assume the server will succeed, and only
roll back if the server actually fails. This makes the dashboard feel like
a native app.

### Three-State Pattern

```
IDLE  -->  OPTIMISTIC (instant)  -->  CONFIRMED (server success)
                 |
                 +-- ROLLBACK (server failure, show toast)
```

### Implementation

```javascript
// ============================================
// GENERIC OPTIMISTIC ACTION HANDLER
// ============================================

async function optimisticAction({
  // What to do immediately in the UI
  onOptimistic,
  // How to restore UI if server fails
  onRollback,
  // The actual server call
  serverAction,
  // Success callback
  onConfirm,
  // Failure callback
  onError
}) {
  // 1. Save current state for rollback
  const savedState = onOptimistic();

  try {
    // 2. Execute server action
    const result = await serverAction();

    // 3. Confirm success
    if (onConfirm) onConfirm(result);
  } catch (err) {
    // 4. Rollback on failure
    onRollback(savedState);
    if (onError) onError(err);
    showToast(`Action failed: ${err.message}. Reverted.`, 'error');
  }
}

// ============================================
// EXAMPLE: Approve with optimistic UI
// ============================================

function approveTask(taskId) {
  const card = document.querySelector(`[data-id="${taskId}"]`);

  optimisticAction({
    onOptimistic: () => {
      const savedHTML = card.innerHTML;
      const savedClass = card.className;
      card.classList.add('approved');
      card.querySelector('.actions').innerHTML = '<span>Approved</span>';
      return { savedHTML, savedClass };
    },
    onRollback: ({ savedHTML, savedClass }) => {
      card.innerHTML = savedHTML;
      card.className = savedClass;
    },
    serverAction: () => fetch(`/api/tasks/${taskId}/approve`, { method: 'POST' })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
    onConfirm: () => {
      // Animate card out after 1 second
      setTimeout(() => {
        card.style.transition = 'all 0.3s ease';
        card.style.maxHeight = '0';
        card.style.opacity = '0';
        card.style.marginBottom = '0';
        card.style.padding = '0';
        setTimeout(() => card.remove(), 300);
      }, 1000);
    }
  });
}
```

### When to Use Optimistic UI

| Action | Use Optimistic? | Reason |
|--------|-----------------|--------|
| Approve low-risk task | YES | Fast, reliable, easily reversible |
| Reject with reason | YES | Same reasoning |
| Move card between columns | YES | DOM already updated, just persist |
| Delete/kill agent | NO | Destructive, confirm first |
| Start investigation | NO | Complex, server needs to validate |
| Change critical budget | NO | Needs validation |

Sources:
- https://simonhearne.com/2021/optimistic-ui-patterns/
- https://derekndavis.com/posts/lightning-fast-front-end-build-optimistic-ui

---

## 12. Implementation Pattern: Toast Notifications

### Minimal Toast System (< 50 Lines)

```javascript
// ============================================
// TOAST NOTIFICATION SYSTEM
// ============================================

const toastContainer = (() => {
  const container = document.createElement('div');
  container.id = 'toast-container';
  container.style.cssText = `
    position: fixed; bottom: 24px; right: 24px;
    display: flex; flex-direction: column-reverse; gap: 8px;
    z-index: 10000; pointer-events: none;
  `;
  document.body.appendChild(container);
  return container;
})();

/**
 * Show a toast notification.
 * @param {string} message - Text to display
 * @param {'success'|'error'|'warning'|'info'} type - Visual style
 * @param {number} duration - Auto-dismiss in ms (0 = manual dismiss)
 */
function showToast(message, type = 'info', duration = 4000) {
  const colors = {
    success: { bg: '#065f46', border: '#10b981', icon: '&#10003;' },
    error:   { bg: '#7f1d1d', border: '#ef4444', icon: '&#10007;' },
    warning: { bg: '#78350f', border: '#f59e0b', icon: '&#9888;' },
    info:    { bg: '#1e3a5f', border: '#3b82f6', icon: '&#8505;' }
  };

  const style = colors[type] || colors.info;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <span class="toast-icon">${style.icon}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
  `;

  toast.style.cssText = `
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; border-radius: 8px;
    background: ${style.bg}; border: 1px solid ${style.border};
    color: white; font-size: 13px; pointer-events: auto;
    animation: toast-in 0.3s ease forwards;
    max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.3);
  `;

  toastContainer.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => {
      toast.style.animation = 'toast-out 0.3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  return toast;
}
```

```css
@keyframes toast-in {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes toast-out {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to { opacity: 0; transform: translateY(20px) scale(0.95); }
}

.toast-close {
  background: none;
  border: none;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  font-size: 16px;
  padding: 0 4px;
  margin-left: 8px;
}
```

---

## 13. Implementation Pattern: Context Menus

### Custom Right-Click Menu

```javascript
// ============================================
// CONTEXT MENU (Right-Click)
// ============================================

function initContextMenu() {
  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.display = 'none';
  document.body.appendChild(menu);

  // Close on any click
  document.addEventListener('click', () => menu.style.display = 'none');
  document.addEventListener('contextmenu', (e) => {
    // Only show custom menu on cards
    const card = e.target.closest('.kanban-card');
    if (!card) return;

    e.preventDefault();
    const cardId = card.dataset.id;
    const status = card.closest('.kanban-column')?.dataset.status;

    const items = [
      { label: 'Open Details', icon: '&#128196;', action: () => openDetailPanel(cardId) },
      { label: 'Assign', icon: '&#128100;', shortcut: 'A', action: () => openAssignDropdown(cardId) },
      { label: 'Change Priority', icon: '&#9733;', shortcut: 'P', action: () => openPriorityDropdown(cardId) },
      { type: 'separator' },
      ...(status === 'needs-approval' ? [
        { label: 'Approve', icon: '&#10003;', class: 'text-green', action: () => handleApproval(cardId, 'approve') },
        { label: 'Reject', icon: '&#10007;', class: 'text-red', action: () => showRejectReason(cardId) },
      ] : []),
      { type: 'separator' },
      { label: 'Copy ID', icon: '&#128203;', action: () => { navigator.clipboard.writeText(cardId); showToast('Copied'); } },
      { label: 'Archive', icon: '&#128451;', class: 'text-muted', action: () => archiveCard(cardId) },
    ];

    menu.innerHTML = items.map(item => {
      if (item.type === 'separator') return '<div class="context-separator"></div>';
      return `
        <div class="context-item ${item.class || ''}" onclick="(${item.action})()">
          <span class="context-icon">${item.icon || ''}</span>
          <span class="context-label">${item.label}</span>
          ${item.shortcut ? `<kbd>${item.shortcut}</kbd>` : ''}
        </div>
      `;
    }).join('');

    // Position: ensure menu stays within viewport
    const x = Math.min(e.clientX, window.innerWidth - 220);
    const y = Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 20);
    menu.style.cssText = `display:block; left:${x}px; top:${y}px;`;
  });
}
```

```css
.context-menu {
  position: fixed;
  width: 220px;
  background: var(--bg-elevated, #2a2a2c);
  border: 1px solid var(--border, rgba(255,255,255,0.12));
  border-radius: 8px;
  padding: 6px;
  z-index: 9998;
  box-shadow: 0 10px 30px rgba(0,0,0,0.4);
}

.context-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text, #e5e5e5);
  transition: background 0.1s;
}

.context-item:hover {
  background: rgba(255,255,255,0.08);
}

.context-item .context-icon {
  width: 18px;
  text-align: center;
  font-size: 13px;
}

.context-item kbd {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(255,255,255,0.08);
  color: var(--text-muted);
  font-family: monospace;
}

.context-separator {
  height: 1px;
  background: var(--border, rgba(255,255,255,0.08));
  margin: 4px 8px;
}

.text-green { color: #22c55e; }
.text-red { color: #ef4444; }
.text-muted { color: var(--text-muted); }
```

Sources:
- https://developer.mozilla.org/en-US/docs/Web/API/Element/contextmenu_event
- https://www.sitepoint.com/building-custom-right-click-context-menu-javascript/

---

## 14. Implementation Pattern: Side Panel / Drawer

### Slide-In Detail Panel

Used when clicking a card to see full details, comment thread, and
approval actions without navigating away from the kanban board.

```javascript
// ============================================
// SIDE PANEL / DRAWER
// ============================================

function openPanel(content) {
  const panel = document.getElementById('side-panel');
  const overlay = document.getElementById('panel-overlay');
  const mainContent = document.getElementById('main-content');

  panel.innerHTML = content;
  panel.classList.add('open');
  overlay.classList.add('visible');
  mainContent.classList.add('shifted');

  // Close on Escape
  const closeHandler = (e) => {
    if (e.key === 'Escape') {
      closePanel();
      document.removeEventListener('keydown', closeHandler);
    }
  };
  document.addEventListener('keydown', closeHandler);
}

function closePanel() {
  document.getElementById('side-panel').classList.remove('open');
  document.getElementById('panel-overlay').classList.remove('visible');
  document.getElementById('main-content').classList.remove('shifted');
}
```

```html
<!-- Add these to your HTML -->
<div id="panel-overlay" onclick="closePanel()"></div>
<div id="side-panel">
  <!-- Content injected dynamically -->
</div>
```

```css
#panel-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 90;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s ease;
}

#panel-overlay.visible {
  opacity: 1;
  pointer-events: auto;
}

#side-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 520px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-elevated, #1c1c1e);
  border-left: 1px solid var(--border);
  z-index: 95;
  overflow-y: auto;
  padding: 24px;
  transform: translateX(100%);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: -20px 0 60px rgba(0,0,0,0.3);
}

#side-panel.open {
  transform: translateX(0);
}

#main-content {
  transition: margin-right 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

#main-content.shifted {
  margin-right: 520px;
}
```

---

## 15. Visual Design: Linear-Style Dark Theme

### CSS Custom Properties

```css
:root {
  /* ---- Background Layers ---- */
  --bg-base: #0a0a0b;
  --bg-surface: #111113;
  --bg-elevated: #1a1a1d;
  --bg-card: rgba(255, 255, 255, 0.04);
  --bg-card-hover: rgba(255, 255, 255, 0.06);

  /* ---- Text ---- */
  --text: #e5e5e7;
  --text-muted: rgba(255, 255, 255, 0.45);
  --text-strong: #ffffff;

  /* ---- Borders ---- */
  --border: rgba(255, 255, 255, 0.08);
  --border-hover: rgba(255, 255, 255, 0.15);

  /* ---- Accent Colors ---- */
  --accent: #6366f1;     /* Indigo - primary actions */
  --accent-hover: #818cf8;
  --green: #22c55e;      /* Success / Approve */
  --red: #ef4444;        /* Error / Reject */
  --amber: #f59e0b;      /* Warning / Needs Attention */
  --blue: #3b82f6;       /* Info / Running */

  /* ---- Radius ---- */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* ---- Font ---- */
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
}

/* ---- Glassmorphism Helper ---- */
.glass {
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

/* ---- Selection ---- */
::selection {
  background: rgba(99, 102, 241, 0.3);
}

/* ---- Scrollbar ---- */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.15);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.25);
}

/* ---- Global Reset ---- */
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font);
  background: var(--bg-base);
  color: var(--text);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
```

### Typography Scale

```css
h1 { font-size: 28px; font-weight: 700; color: var(--text-strong); letter-spacing: -0.02em; }
h2 { font-size: 20px; font-weight: 600; color: var(--text-strong); letter-spacing: -0.01em; }
h3 { font-size: 16px; font-weight: 600; color: var(--text); }
.body-text { font-size: 14px; color: var(--text); }
.caption { font-size: 12px; color: var(--text-muted); }
.mono { font-family: var(--font-mono); font-size: 13px; }
```

### Button System

```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;
  font-family: var(--font);
}

.btn-primary {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}
.btn-primary:hover { background: var(--accent-hover); }

.btn-ghost {
  background: transparent;
  color: var(--text);
  border-color: var(--border);
}
.btn-ghost:hover { background: var(--bg-card-hover); border-color: var(--border-hover); }

.btn-danger {
  background: transparent;
  color: var(--red);
  border-color: var(--red);
}
.btn-danger:hover { background: rgba(239,68,68,0.1); }

/* Micro-interaction: press effect */
.btn:active { transform: scale(0.97); }
```

---

## 16. Architecture: Single-File Component Strategy

### How to Organize 2000+ Lines in One HTML File

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Swarm Command Center</title>
  <style>
    /* ==============================
       SECTION 1: CSS Variables & Reset
       ============================== */
    :root { /* ... */ }

    /* ==============================
       SECTION 2: Layout (Grid/Flex)
       ============================== */
    .layout-app { /* ... */ }

    /* ==============================
       SECTION 3: Component Styles
       ============================== */
    /* 3a: Kanban Board */
    /* 3b: Approval Cards */
    /* 3c: Command Palette */
    /* 3d: Side Panel */
    /* 3e: Toast Notifications */
    /* 3f: Context Menu */

    /* ==============================
       SECTION 4: Animations
       ============================== */
    @keyframes pulse { /* ... */ }
    @keyframes toast-in { /* ... */ }
  </style>
</head>
<body>
  <!-- ==============================
       SECTION 5: HTML Structure
       ============================== -->

  <!-- 5a: Top Bar (title, view tabs, Cmd+K hint) -->
  <!-- 5b: Sidebar (agent list, stats) -->
  <!-- 5c: Main Content Area (view-switched) -->
  <!-- 5d: Side Panel (hidden by default) -->
  <!-- 5e: Overlays (command palette, context menu, toast container) -->

  <script>
    // ==============================
    // SECTION 6: State Management
    // ==============================
    const state = {
      items: [],
      agents: [],
      approvals: [],
      currentView: 'kanban',
      selectedCard: null,
      filters: {}
    };

    // ==============================
    // SECTION 7: Core Rendering
    // ==============================
    // 7a: View Switcher
    // 7b: Kanban Renderer
    // 7c: Table Renderer
    // 7d: Timeline Renderer

    // ==============================
    // SECTION 8: Interaction Handlers
    // ==============================
    // 8a: Drag and Drop
    // 8b: Keyboard Shortcuts
    // 8c: Command Palette
    // 8d: Context Menu
    // 8e: Clipboard Paste

    // ==============================
    // SECTION 9: API Layer
    // ==============================
    // 9a: Fetch wrapper with optimistic UI
    // 9b: SSE/WebSocket for real-time updates
    // 9c: Approval endpoints

    // ==============================
    // SECTION 10: Utilities
    // ==============================
    // 10a: Toast system
    // 10b: Time formatting
    // 10c: Fuzzy search

    // ==============================
    // SECTION 11: Initialization
    // ==============================
    document.addEventListener('DOMContentLoaded', () => {
      initKanbanDragDrop();
      initContextMenu();
      // Command palette auto-initializes
      loadInitialData();
    });
  </script>
</body>
</html>
```

### State Management Without a Framework

```javascript
// ============================================
// MINIMAL REACTIVE STATE STORE
// No framework needed. ~30 lines.
// ============================================

function createStore(initialState) {
  let state = { ...initialState };
  const listeners = new Map();

  return {
    getState: () => state,

    setState: (patch) => {
      const prev = { ...state };
      state = { ...state, ...patch };

      // Notify listeners for changed keys
      for (const [key, fns] of listeners) {
        if (state[key] !== prev[key]) {
          fns.forEach(fn => fn(state[key], prev[key]));
        }
      }
    },

    subscribe: (key, fn) => {
      if (!listeners.has(key)) listeners.set(key, new Set());
      listeners.get(key).add(fn);
      return () => listeners.get(key).delete(fn); // unsubscribe
    }
  };
}

// Usage
const store = createStore({
  items: [],
  currentView: 'kanban',
  approvals: [],
  agents: []
});

// Re-render kanban when items change
store.subscribe('items', (items) => renderKanbanBoard(items));

// Re-render approval badge when approvals change
store.subscribe('approvals', (approvals) => {
  document.querySelector('.approval-count').textContent = approvals.length;
});
```

### Fuzzy Search (For Command Palette)

```javascript
// ============================================
// FUZZY SEARCH - Sequential character matching
// Returns matching indices sorted by relevance
// ============================================

function fuzzyMatch(query, text) {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let qi = 0;
  let score = 0;
  let consecutiveBonus = 0;

  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) {
      score += 1 + consecutiveBonus;
      if (i === 0 || t[i - 1] === ' ' || t[i - 1] === '-') {
        score += 5; // Word boundary bonus
      }
      consecutiveBonus += 2; // Consecutive chars score higher
      qi++;
    } else {
      consecutiveBonus = 0;
    }
  }

  return qi === q.length ? score : 0; // 0 = no match
}

function fuzzySearch(query, items, key = 'name') {
  if (!query) return items;
  return items
    .map(item => ({ item, score: fuzzyMatch(query, item[key]) }))
    .filter(r => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(r => r.item);
}
```

---

## Summary: Priority Implementation Order

For maximum impact with minimum effort, implement in this order:

| Priority | Pattern | Lines of Code | Impact |
|----------|---------|---------------|--------|
| 1 | Dark theme + CSS variables | ~80 | Foundation for everything |
| 2 | Kanban board with drag-and-drop | ~200 | Core interaction model |
| 3 | Approval cards with approve/reject | ~150 | Primary use case |
| 4 | Toast notifications | ~50 | Essential feedback |
| 5 | Command palette (Cmd+K) | ~250 | Power user accelerator |
| 6 | Side panel / drawer | ~80 | Detail views |
| 7 | Context menu (right-click) | ~100 | Discoverability |
| 8 | Keyboard shortcuts | ~40 | Speed for regulars |
| 9 | View switching (kanban/table) | ~100 | Flexibility |
| 10 | Clipboard paste-to-upload | ~60 | Nice-to-have |
| 11 | Inline commenting | ~80 | Collaboration |
| 12 | Optimistic UI wrapper | ~40 | Polish |

**Total estimated: ~1,230 lines of JavaScript + ~500 lines of CSS**

This is entirely achievable in a single HTML file without React, npm, or a build step.

---

## Key Takeaways

1. **Linear's secret is not one feature** -- it is the compounding effect of
   keyboard-first + command palette + optimistic UI + minimal visual noise.
   Each individually is good; together they create a "fast" feeling.

2. **HTML5 Drag and Drop is good enough** for desktop kanban. No library needed.
   Touch support requires a ~40 line polyfill with pointer events.

3. **Clipboard paste is trivial** -- the `paste` event + `clipboardData.items`
   pattern is 15 lines of code and works in all modern browsers.

4. **Command palette in vanilla JS is ~250 lines** including fuzzy search,
   keyboard navigation, and grouped rendering. This is the single
   highest-value interactive feature to add.

5. **Optimistic UI is a mindset, not a library** -- wrap every server call with
   "update UI first, rollback on failure." This alone makes the app feel 10x faster.

6. **Approval workflows need exactly two things**: (a) full context visible at
   decision point, (b) one-click approve, reason-required reject.

7. **Notion's multi-view pattern** (same data, different renderers) is achievable
   with a simple `renderers[currentView](data)` pattern. No framework needed.

8. **The dark theme matters more than you think** -- it signals "professional tool"
   and reduces eye strain for monitoring dashboards. Use very few accent colors
   (indigo for primary, green/red/amber for status).
