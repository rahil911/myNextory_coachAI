# Phase 3i: Command Center UI

## Purpose

The Command Center is the human's primary visual interface to their agent swarm. Without it,
the human is blind -- they can see logs scrolling in terminals, but they cannot answer the
three questions that matter: "What is happening right now?", "What needs my attention?",
and "Is the system healthy?"

This spec builds a production-grade frontend that answers all three at a glance. It lives at
`.claude/command-center/frontend/` and is served by the FastAPI backend (03h) as static files.
Vanilla JS with ES modules, proper file structure, no build step. Just serve the files.

The design philosophy is Linear meets Cursor meets ChatGPT Canvas -- keyboard-first, dark
theme, glassmorphism overlays, optimistic UI, WebSocket-driven real-time updates. The Think
Tank view is the crown jewel: a split-view brainstorming interface where the human and AI
orchestrator co-create project specs through four phases before autonomous execution begins.

## Risks Mitigated

- Risk 40: Human has no visibility into agent swarm activity (CRITICAL)
- Risk 41: Approval requests go unnoticed, blocking agent progress (HIGH)
- Risk 42: No way to detect stuck/dead agents without checking terminals (HIGH)
- Risk 43: Think Tank brainstorming produces vague specs that cause rework (HIGH)
- Risk 44: Human cannot drag-and-drop reprioritize work across the swarm (MEDIUM)
- Risk 45: No audit trail of agent events visible outside log files (MEDIUM)

## Files to Create

All files live under `.claude/command-center/frontend/`.

### HTML
- `index.html` -- Main HTML shell, loads ES modules, defines app skeleton

### CSS (7 files)
- `css/theme.css` -- Linear-style dark theme variables, reset, typography, scrollbar
- `css/layout.css` -- App shell grid, nav sidebar, main content area, responsive breakpoints
- `css/kanban.css` -- Kanban board columns, cards, drag states, priority stripes, WIP limits
- `css/thinktank.css` -- Think Tank split-view, phase stepper, D/A/G chips, spec-kit panel
- `css/timeline.css` -- AgentOps-style waterfall bars, event rows, detail panel
- `css/components.css` -- Buttons, badges, toasts, modals, side panel, approval cards, forms
- `css/animations.css` -- Keyframes, transitions, micro-interactions, shimmer, phase pulse

### JS (18 files)
- `js/app.js` -- Main entry, initializes router/store/WebSocket, registers command palette
- `js/state.js` -- Reactive state store (~50 lines, key-level subscriptions)
- `js/api.js` -- Fetch wrapper with auth/error handling + WebSocket manager with auto-reconnect
- `js/router.js` -- Hash-based router mapping #views to render functions
- `js/views/dashboard.js` -- Overview grid: active agents, open beads, epic progress, alerts
- `js/views/kanban.js` -- Kanban board with DnD, context menus, table toggle, filters
- `js/views/thinktank.js` -- Think Tank split-view orchestrator (chat + spec-kit)
- `js/views/timeline.js` -- Event timeline with waterfall bars and detail panel
- `js/views/agents.js` -- Agent detail: status, heartbeat, current bead, log tail
- `js/views/epics.js` -- Epic progress bars, dependency DAG, bead list
- `js/components/command-palette.js` -- Cmd+K modal with fuzzy search, grouped categories
- `js/components/sidebar.js` -- Right-edge slide-in drawer for detail views
- `js/components/toast.js` -- Toast notification system (4 types, stacking, auto-dismiss)
- `js/components/clipboard.js` -- Paste-to-upload handler for images
- `js/components/approval-card.js` -- Approval card with urgency badge, approve/reject
- `js/components/phase-stepper.js` -- Horizontal phase indicator with animations
- `js/components/spec-kit.js` -- Live spec-kit panel with shimmer, streaming, edit
- `js/components/chat.js` -- Chat messages, D/A/G chips, image previews
- `js/components/risk-card.js` -- Pre-mortem risk cards with Accept/Mitigate/Eliminate
- `js/components/context-menu.js` -- Right-click context menus
- `js/utils/dom.js` -- DOM helpers (h, createElement, $, $$)
- `js/utils/format.js` -- Time formatting (timeAgo, duration), number formatting
- `js/utils/fuzzy.js` -- Fuzzy search scoring for command palette

### Assets
- `assets/icons.svg` -- SVG sprite sheet with minimal icon set

## Files to Modify

- None. This is a greenfield frontend. The backend (03h) serves these files.

---

## Architecture

```
Browser
  |
  +-- index.html (loads ES modules)
  |     |
  |     +-- js/app.js (entry point)
  |           |
  |           +-- js/state.js (reactive store)
  |           +-- js/router.js (hash routing)
  |           +-- js/api.js (REST + WebSocket)
  |           |
  |           +-- js/views/*.js (6 views)
  |           +-- js/components/*.js (10 components)
  |           +-- js/utils/*.js (3 utilities)
  |
  +-- css/*.css (7 stylesheets)
  |
  +-- WebSocket /ws (real-time agent/bead updates)
  +-- WebSocket /ws/thinktank (real-time think tank streaming)
  +-- REST API /api/* (CRUD operations)
  |
  Backend (03h, port 8002)
```

### Data Flow

```
1. Page load:
   app.js -> api.fetchDashboard() -> store.setState({agents, beads, epics})
   router.navigate(window.location.hash)

2. Real-time updates:
   WebSocket /ws -> onMessage -> store.setState({...delta})
   store subscribers -> re-render affected views

3. User actions:
   Click/DnD/keyboard -> optimistic DOM update -> api.patch() -> confirm or rollback

4. Think Tank:
   WebSocket /ws/thinktank -> streaming messages -> chat.appendToken()
   WebSocket /ws/thinktank -> spec-kit deltas -> specKit.updateSection()
   User sends message -> api.postMessage() -> WebSocket echoes response
```

---

## Fix 1: Theme and Design System (css/theme.css)

### Problem

Without a consistent design system, every component will use ad-hoc colors, fonts, and
spacing. The result is visual chaos that signals "prototype" not "production." The Linear
dark theme research proves that a small set of CSS variables creates visual coherence
across unlimited components.

### Solution

A complete CSS custom property system with 5 background layers, text hierarchy, status
colors, phase accent colors, typography scale, button system, glassmorphism helper, and
global reset. Every other CSS file references these variables -- never hardcoded values.

### Implementation: css/theme.css

```css
/* ==========================================================================
   THEME.CSS — Linear-Style Dark Design System
   Variables, reset, typography, scrollbar, selection, glassmorphism
   ========================================================================== */

:root {
  /* ── Background Layers (darkest to lightest) ──────────────────────────── */
  --bg-base:       #0a0a0b;
  --bg-1:          #111113;
  --bg-2:          #1a1a1d;
  --bg-3:          #222226;
  --bg-4:          #2a2a2f;
  --bg-5:          #333339;

  /* ── Semantic backgrounds ─────────────────────────────────────────────── */
  --bg-surface:    var(--bg-1);
  --bg-elevated:   var(--bg-2);
  --bg-card:       rgba(255, 255, 255, 0.04);
  --bg-card-hover: rgba(255, 255, 255, 0.06);
  --bg-input:      rgba(255, 255, 255, 0.05);

  /* ── Text Hierarchy ───────────────────────────────────────────────────── */
  --text-primary:   #e5e5e7;
  --text-secondary: rgba(255, 255, 255, 0.55);
  --text-tertiary:  rgba(255, 255, 255, 0.35);
  --text-strong:    #ffffff;
  --text-inverse:   #0a0a0b;

  /* ── Borders ──────────────────────────────────────────────────────────── */
  --border:        rgba(255, 255, 255, 0.08);
  --border-hover:  rgba(255, 255, 255, 0.15);
  --border-focus:  rgba(99, 102, 241, 0.5);

  /* ── Status Colors ────────────────────────────────────────────────────── */
  --green:   #22c55e;
  --green-dim: rgba(34, 197, 94, 0.15);
  --red:     #ef4444;
  --red-dim: rgba(239, 68, 68, 0.15);
  --yellow:  #f59e0b;
  --yellow-dim: rgba(245, 158, 11, 0.15);
  --blue:    #3b82f6;
  --blue-dim: rgba(59, 130, 246, 0.15);
  --purple:  #a855f7;
  --purple-dim: rgba(168, 85, 247, 0.15);

  /* ── Accent (Primary Actions) ─────────────────────────────────────────── */
  --accent:        #6366f1;
  --accent-hover:  #818cf8;
  --accent-dim:    rgba(99, 102, 241, 0.15);

  /* ── Phase Accent Colors (Think Tank) ─────────────────────────────────── */
  --phase-listen:  #f59e0b;   /* Warm amber — receptive, open */
  --phase-explore: #3b82f6;   /* Electric blue — expansive */
  --phase-scope:   #f97316;   /* Orange-red — critical, analytical */
  --phase-confirm: #059669;   /* Emerald — decisive, go */

  /* ── Priority Colors ──────────────────────────────────────────────────── */
  --priority-0: #ef4444;   /* P0 Critical */
  --priority-1: #f97316;   /* P1 High */
  --priority-2: #f59e0b;   /* P2 Medium */
  --priority-3: #6b7280;   /* P3 Low */

  /* ── Radius ───────────────────────────────────────────────────────────── */
  --radius-xs:  4px;
  --radius-sm:  6px;
  --radius-md:  8px;
  --radius-lg:  12px;
  --radius-xl:  16px;
  --radius-full: 9999px;

  /* ── Spacing ──────────────────────────────────────────────────────────── */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;

  /* ── Typography ───────────────────────────────────────────────────────── */
  --font:      -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  --font-size-xs:   11px;
  --font-size-sm:   12px;
  --font-size-base: 14px;
  --font-size-md:   16px;
  --font-size-lg:   20px;
  --font-size-xl:   28px;

  /* ── Shadows ──────────────────────────────────────────────────────────── */
  --shadow-sm:  0 1px 2px rgba(0,0,0,0.3);
  --shadow-md:  0 4px 12px rgba(0,0,0,0.3);
  --shadow-lg:  0 10px 30px rgba(0,0,0,0.4);
  --shadow-xl:  0 25px 50px rgba(0,0,0,0.5);

  /* ── Transitions ──────────────────────────────────────────────────────── */
  --ease-out:   cubic-bezier(0.4, 0, 0.2, 1);
  --ease-back:  cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast:   150ms;
  --duration-normal: 250ms;
  --duration-slow:   400ms;

  /* ── Z-Index Scale ────────────────────────────────────────────────────── */
  --z-base:      1;
  --z-dropdown:  50;
  --z-sticky:    60;
  --z-overlay:   90;
  --z-panel:     95;
  --z-modal:     100;
  --z-toast:     200;
  --z-command:   9999;
}

/* ── Global Reset ───────────────────────────────────────────────────────── */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  overflow: hidden;
}

body {
  font-family: var(--font);
  font-size: var(--font-size-base);
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--bg-base);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

a {
  color: var(--accent);
  text-decoration: none;
}
a:hover { color: var(--accent-hover); }

img, svg { display: block; max-width: 100%; }

/* ── Typography Scale ───────────────────────────────────────────────────── */
h1 {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--text-strong);
  letter-spacing: -0.02em;
  line-height: 1.2;
}

h2 {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-strong);
  letter-spacing: -0.01em;
  line-height: 1.3;
}

h3 {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

h4 {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.caption {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.overline {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

/* ── Selection ──────────────────────────────────────────────────────────── */
::selection {
  background: rgba(99, 102, 241, 0.3);
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.22);
}

/* Firefox */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.12) transparent;
}

/* ── Glassmorphism Helper ───────────────────────────────────────────────── */
.glass {
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

/* ── Button System ──────────────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 500;
  font-family: var(--font);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all var(--duration-fast) var(--ease-out);
  white-space: nowrap;
  user-select: none;
  line-height: 1;
}

.btn:active { transform: scale(0.97); }
.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
}

.btn-primary {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }

.btn-success {
  background: var(--green);
  color: white;
}
.btn-success:hover:not(:disabled) { background: #16a34a; }

.btn-danger {
  background: transparent;
  color: var(--red);
  border-color: var(--red);
}
.btn-danger:hover:not(:disabled) { background: var(--red-dim); }

.btn-ghost {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border);
}
.btn-ghost:hover:not(:disabled) {
  background: var(--bg-card-hover);
  border-color: var(--border-hover);
}

.btn-sm {
  padding: 4px 10px;
  font-size: var(--font-size-xs);
}

.btn-lg {
  padding: 12px 24px;
  font-size: var(--font-size-base);
  font-weight: 600;
}

.btn-full { width: 100%; }

.btn-icon {
  padding: 6px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-out);
}
.btn-icon:hover {
  color: var(--text-primary);
  background: var(--bg-card-hover);
}

/* ── Badge System ───────────────────────────────────────────────────────── */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: 600;
  line-height: 1.4;
}

.badge-green  { background: var(--green-dim);  color: var(--green);  }
.badge-red    { background: var(--red-dim);    color: var(--red);    }
.badge-yellow { background: var(--yellow-dim); color: var(--yellow); }
.badge-blue   { background: var(--blue-dim);   color: var(--blue);   }
.badge-purple { background: var(--purple-dim); color: var(--purple); }
.badge-gray   { background: rgba(107,114,128,0.2); color: #9ca3af; }

/* ── Form Inputs ────────────────────────────────────────────────────────── */
input[type="text"],
input[type="search"],
textarea,
select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: var(--font);
  font-size: var(--font-size-base);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out);
}

input:focus, textarea:focus, select:focus {
  border-color: var(--border-focus);
}

input::placeholder, textarea::placeholder {
  color: var(--text-tertiary);
}

/* ── Status Dots ────────────────────────────────────────────────────────── */
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.status-dot-idle     { background: var(--priority-3); }
.status-dot-running  { background: var(--blue); animation: pulse-dot 1.5s infinite; }
.status-dot-waiting  { background: var(--yellow); animation: pulse-dot 1s infinite; }
.status-dot-success  { background: var(--green); }
.status-dot-error    { background: var(--red); }
.status-dot-dead     { background: var(--priority-3); opacity: 0.4; }

/* ── Utility Classes ────────────────────────────────────────────────────── */
.flex         { display: flex; }
.flex-col     { display: flex; flex-direction: column; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.gap-1 { gap: var(--space-1); }
.gap-2 { gap: var(--space-2); }
.gap-3 { gap: var(--space-3); }
.gap-4 { gap: var(--space-4); }
.gap-6 { gap: var(--space-6); }
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border: 0;
}
```

---

## Fix 2: Layout Shell (css/layout.css)

### Problem

The app needs a consistent shell -- left nav sidebar for navigation, top bar for context,
main content area that swaps views. Without this, every view would need to recreate the
chrome, leading to inconsistent margins and broken navigation.

### Solution

A CSS Grid layout with a collapsible left sidebar (240px), top bar (48px), and
scrollable main content area. Responsive: sidebar collapses to icons on tablets,
becomes a drawer on mobile.

### Implementation: css/layout.css

```css
/* ==========================================================================
   LAYOUT.CSS — App Shell, Navigation, Panels, Responsive Grid
   ========================================================================== */

/* ── App Shell ──────────────────────────────────────────────────────────── */
.app {
  display: grid;
  grid-template-columns: 240px 1fr;
  grid-template-rows: 48px 1fr;
  grid-template-areas:
    "nav topbar"
    "nav main";
  height: 100vh;
  overflow: hidden;
}

/* ── Top Bar ────────────────────────────────────────────────────────────── */
.topbar {
  grid-area: topbar;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  z-index: var(--z-sticky);
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.topbar-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-strong);
}

.topbar-breadcrumb {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.topbar-cmdk-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.topbar-cmdk-hint:hover {
  border-color: var(--border-hover);
  color: var(--text-secondary);
}

.topbar-cmdk-hint kbd {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(255,255,255,0.08);
}

/* ── Nav Sidebar ────────────────────────────────────────────────────────── */
.nav {
  grid-area: nav;
  display: flex;
  flex-direction: column;
  background: var(--bg-1);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: var(--z-sticky);
}

.nav-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4);
  border-bottom: 1px solid var(--border);
}

.nav-logo {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--accent), var(--purple));
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 700;
  font-size: var(--font-size-sm);
}

.nav-project-name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-strong);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-section {
  padding: var(--space-2) 0;
}

.nav-section-label {
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 6px var(--space-4);
  margin: 1px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  user-select: none;
}

.nav-item:hover {
  background: var(--bg-card-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-dim);
  color: var(--text-strong);
}

.nav-item-icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-item-badge {
  margin-left: auto;
  background: var(--red);
  color: white;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  min-width: 18px;
  text-align: center;
}

.nav-footer {
  margin-top: auto;
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border);
}

.nav-footer-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

/* ── Main Content ───────────────────────────────────────────────────────── */
.main {
  grid-area: main;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--bg-base);
}

.view-container {
  padding: var(--space-6);
  max-width: 1600px;
  min-height: 100%;
}

/* ── View Header (shared pattern for all views) ─────────────────────────── */
.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-6);
}

.view-header-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.view-header-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* ── Filter Chips ───────────────────────────────────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.filter-chip:hover { border-color: var(--border-hover); }
.filter-chip.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--text-strong);
}

.filter-chip-remove {
  font-size: 10px;
  opacity: 0.6;
  cursor: pointer;
}
.filter-chip-remove:hover { opacity: 1; }

/* ── View Toggle Tabs ───────────────────────────────────────────────────── */
.view-tabs {
  display: flex;
  gap: 2px;
  background: var(--bg-3);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.view-tab {
  padding: 5px 14px;
  border-radius: var(--radius-xs);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  font-weight: 500;
  font-family: var(--font);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.view-tab:hover { color: var(--text-primary); }
.view-tab.active {
  background: var(--bg-elevated);
  color: var(--text-strong);
  box-shadow: var(--shadow-sm);
}

/* ── Panel Overlay & Side Panel ─────────────────────────────────────────── */
.panel-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: var(--z-overlay);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-normal) var(--ease-out);
}

.panel-overlay.visible {
  opacity: 1;
  pointer-events: auto;
}

.side-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 520px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-elevated);
  border-left: 1px solid var(--border);
  z-index: var(--z-panel);
  overflow-y: auto;
  padding: var(--space-6);
  transform: translateX(100%);
  transition: transform var(--duration-normal) var(--ease-out);
  box-shadow: -20px 0 60px rgba(0, 0, 0, 0.3);
}

.side-panel.open {
  transform: translateX(0);
}

.side-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-6);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--border);
}

.side-panel-close {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.side-panel-close:hover {
  background: var(--bg-card-hover);
  color: var(--text-primary);
}

/* ── Responsive: Tablet ─────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .app {
    grid-template-columns: 60px 1fr;
  }

  .nav-project-name,
  .nav-section-label,
  .nav-item span:not(.nav-item-icon),
  .nav-item-badge {
    display: none;
  }

  .nav-item {
    justify-content: center;
    padding: 10px;
    margin: 1px 4px;
  }

  .nav-header {
    justify-content: center;
    padding: var(--space-3);
  }
}

/* ── Responsive: Mobile ─────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .app {
    grid-template-columns: 1fr;
    grid-template-rows: 48px 1fr;
    grid-template-areas:
      "topbar"
      "main";
  }

  .nav {
    position: fixed;
    left: -260px;
    top: 0;
    width: 260px;
    height: 100vh;
    z-index: var(--z-modal);
    transition: left var(--duration-normal) var(--ease-out);
    box-shadow: 20px 0 60px rgba(0,0,0,0.5);
  }

  .nav.mobile-open {
    left: 0;
  }

  .nav-project-name,
  .nav-section-label,
  .nav-item span:not(.nav-item-icon),
  .nav-item-badge {
    display: initial;
  }

  .nav-item {
    justify-content: flex-start;
    padding: 6px var(--space-4);
    margin: 1px var(--space-2);
  }

  .view-container {
    padding: var(--space-4);
  }

  .side-panel {
    width: 100vw;
    max-width: 100vw;
  }
}
```

---

## Fix 3: Kanban Board Styles (css/kanban.css)

### Problem

The Kanban board is the primary work management view. Cards need drag states, priority
stripes, agent color badges, hover expand, WIP limit warnings, and bottleneck detection
highlights. Without dedicated styles, the board looks flat and unreadable.

### Solution

Complete Kanban CSS covering column layout, card design with priority left-border, drag
ghost/placeholder states, hover expansion, WIP limit badges, and table view fallback.

### Implementation: css/kanban.css

```css
/* ==========================================================================
   KANBAN.CSS — Board, Columns, Cards, Drag States, Table View
   ========================================================================== */

/* ── Board Layout ───────────────────────────────────────────────────────── */
.kanban-board {
  display: flex;
  gap: var(--space-3);
  overflow-x: auto;
  overflow-y: hidden;
  height: calc(100vh - 180px);
  padding-bottom: var(--space-4);
}

/* ── Column ─────────────────────────────────────────────────────────────── */
.kanban-column {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  transition: background var(--duration-normal) var(--ease-out),
              outline var(--duration-normal) var(--ease-out);
  min-height: 200px;
}

.kanban-column.drag-over {
  background: var(--accent-dim);
  outline: 2px dashed rgba(99, 102, 241, 0.3);
  outline-offset: -2px;
}

.kanban-column.bottleneck {
  outline: 2px solid rgba(239, 68, 68, 0.3);
  outline-offset: -2px;
}

.kanban-column-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2) var(--space-3);
}

.kanban-column-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.kanban-column-title {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

.kanban-column-count {
  background: rgba(255,255,255,0.08);
  border-radius: var(--radius-full);
  padding: 1px 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
}

.kanban-column-wip {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-tertiary);
}

.kanban-column-wip.over-limit {
  color: var(--red);
  font-weight: 600;
}

.kanban-cards {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-height: 50px;
}

/* ── Card ───────────────────────────────────────────────────────────────── */
.kanban-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  cursor: grab;
  transition: transform var(--duration-fast) var(--ease-out),
              box-shadow var(--duration-fast) var(--ease-out),
              opacity var(--duration-fast);
  user-select: none;
  position: relative;
  /* Priority stripe via left border */
  border-left: 3px solid var(--priority-3);
}

.kanban-card[data-priority="0"] { border-left-color: var(--priority-0); }
.kanban-card[data-priority="1"] { border-left-color: var(--priority-1); }
.kanban-card[data-priority="2"] { border-left-color: var(--priority-2); }
.kanban-card[data-priority="3"] { border-left-color: var(--priority-3); }

.kanban-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  border-color: var(--border-hover);
}

.kanban-card:active {
  cursor: grabbing;
}

.kanban-card.dragging {
  opacity: 0.3;
  transform: rotate(1deg);
}

.kanban-card.selected {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}

.kanban-card-title {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: var(--space-2);
}

.kanban-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.kanban-card-agent {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  color: white;
  background: var(--accent);
}

.kanban-card-type {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  background: rgba(255,255,255,0.06);
  color: var(--text-secondary);
}

.kanban-card-time {
  font-size: 10px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.kanban-card-deps {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--yellow);
}

/* ── Card Hover Expand ──────────────────────────────────────────────────── */
.kanban-card-details {
  max-height: 0;
  overflow: hidden;
  transition: max-height var(--duration-normal) var(--ease-out),
              padding var(--duration-normal) var(--ease-out),
              opacity var(--duration-normal) var(--ease-out);
  opacity: 0;
  padding-top: 0;
}

.kanban-card:hover .kanban-card-details {
  max-height: 120px;
  opacity: 1;
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
  margin-top: var(--space-2);
}

.kanban-card-detail-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  padding: 2px 0;
}

.kanban-card-detail-label {
  color: var(--text-secondary);
  min-width: 50px;
}

/* ── Drop Placeholder ───────────────────────────────────────────────────── */
.drop-placeholder {
  height: 56px;
  border: 2px dashed rgba(99, 102, 241, 0.35);
  border-radius: var(--radius-md);
  background: var(--accent-dim);
  transition: height var(--duration-fast) var(--ease-out);
}

/* ── Table View ─────────────────────────────────────────────────────────── */
.kanban-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.kanban-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg-base);
  z-index: 2;
}

.kanban-table td {
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-sm);
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
}

.kanban-table tr {
  transition: background var(--duration-fast);
}

.kanban-table tr:hover {
  background: var(--bg-card-hover);
}

.kanban-table .priority-cell {
  width: 4px;
  padding: 0;
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .kanban-column {
    flex: 0 0 240px;
  }
}

@media (max-width: 768px) {
  .kanban-board {
    flex-direction: column;
    height: auto;
    overflow-x: hidden;
  }

  .kanban-column {
    flex: none;
    width: 100%;
  }
}
```

---

## Fix 4: Think Tank Styles (css/thinktank.css)

### Problem

The Think Tank is the crown jewel view. It requires a split-view layout (chat left, spec-kit
right), a horizontal phase stepper with three visual states and animated transitions, D/A/G
action chips with staggered fade-in, shimmer loading placeholders for the spec-kit, risk cards
with severity borders, and the full-width emerald approval button. Standard component classes
cannot cover all of this.

### Solution

Dedicated Think Tank CSS with phase stepper animations, split-view proportions, chat bubble
styles, D/A/G chip states, spec-kit section cards with shimmer, risk card severity borders,
and the approval gate button with its two-phase click animation.

### Implementation: css/thinktank.css

```css
/* ==========================================================================
   THINKTANK.CSS — Split View, Phase Stepper, Chat, Spec-Kit, Risk Cards
   ========================================================================== */

/* ── Split View Layout ──────────────────────────────────────────────────── */
.thinktank {
  display: flex;
  height: calc(100vh - 48px);
  overflow: hidden;
}

.thinktank-chat {
  flex: 0 0 55%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  position: relative;
  overflow: hidden;
}

.thinktank-speckit {
  flex: 0 0 45%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--bg-1);
}

/* ── Phase Background Tint ──────────────────────────────────────────────── */
.thinktank-chat[data-phase="listen"]  { background: linear-gradient(180deg, rgba(245,158,11,0.03) 0%, transparent 30%); }
.thinktank-chat[data-phase="explore"] { background: linear-gradient(180deg, rgba(59,130,246,0.03) 0%, transparent 30%); }
.thinktank-chat[data-phase="scope"]   { background: linear-gradient(180deg, rgba(249,115,22,0.03) 0%, transparent 30%); }
.thinktank-chat[data-phase="confirm"] { background: linear-gradient(180deg, rgba(5,150,105,0.03) 0%, transparent 30%); }

/* ── Phase Stepper ──────────────────────────────────────────────────────── */
.phase-stepper {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) var(--space-6);
  border-bottom: 1px solid var(--border);
  gap: 0;
  flex-shrink: 0;
}

.phase-step {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.phase-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: all var(--duration-slow) var(--ease-out);
  position: relative;
  flex-shrink: 0;
}

/* Upcoming phase */
.phase-step.upcoming .phase-circle {
  border: 2px dashed var(--text-tertiary);
  color: var(--text-tertiary);
  background: transparent;
}

/* Active phase */
.phase-step.active .phase-circle {
  border: 2px solid var(--accent);
  color: white;
  background: var(--accent);
  animation: phase-pulse 2s infinite;
}

/* Completed phase */
.phase-step.completed .phase-circle {
  border: 2px solid var(--green);
  color: white;
  background: var(--green);
  animation: phase-check-pop 0.4s var(--ease-back) forwards;
}

.phase-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  transition: color var(--duration-normal);
}

.phase-step.upcoming .phase-label { color: var(--text-tertiary); }
.phase-step.active .phase-label   { color: var(--text-strong); }
.phase-step.completed .phase-label { color: var(--green); }

.phase-sublabel {
  font-size: 10px;
  color: var(--text-tertiary);
  display: block;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
}

/* Phase connecting line */
.phase-line {
  width: 48px;
  height: 2px;
  margin: 0 var(--space-2);
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

.phase-line.completed {
  background: var(--green);
}

.phase-line.active {
  background: var(--border);
}

.phase-line.active::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, var(--accent), var(--purple));
  animation: phase-line-flow 1.5s linear infinite;
}

.phase-line.upcoming {
  background: var(--border);
  border-style: dashed;
}

/* ── Chat Messages ──────────────────────────────────────────────────────── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.chat-message {
  display: flex;
  gap: var(--space-3);
  max-width: 85%;
  animation: message-fade-in 0.3s var(--ease-out);
}

.chat-message.ai {
  align-self: flex-start;
}

.chat-message.human {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: 600;
  flex-shrink: 0;
}

.chat-avatar.ai {
  background: linear-gradient(135deg, var(--accent), var(--purple));
  color: white;
}

.chat-avatar.human {
  background: var(--bg-4);
  color: var(--text-secondary);
}

.chat-bubble {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  line-height: 1.6;
}

.chat-message.ai .chat-bubble {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-top-left-radius: var(--radius-xs);
}

.chat-message.human .chat-bubble {
  background: var(--accent);
  color: white;
  border-top-right-radius: var(--radius-xs);
}

.chat-bubble img {
  max-width: 300px;
  border-radius: var(--radius-md);
  margin-top: var(--space-2);
}

.chat-typing-indicator {
  display: flex;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
}

.chat-typing-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: typing-bounce 1.2s infinite;
}

.chat-typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.chat-typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

/* ── D/A/G Action Chips ─────────────────────────────────────────────────── */
.dag-chips {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-3);
  flex-wrap: wrap;
}

.dag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  font-family: var(--font);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  opacity: 0;
  transform: translateY(8px);
}

/* Staggered fade-in */
.dag-chip:nth-child(1) { animation: chip-fade-in 0.3s 0.1s var(--ease-out) forwards; }
.dag-chip:nth-child(2) { animation: chip-fade-in 0.3s 0.2s var(--ease-out) forwards; }
.dag-chip:nth-child(3) { animation: chip-fade-in 0.3s 0.3s var(--ease-out) forwards; }

.dag-chip:hover {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--text-strong);
  transform: scale(1.02);
}

.dag-chip:active {
  transform: scale(0.97);
}

.dag-chip .dag-shortcut {
  font-size: 10px;
  font-family: var(--font-mono);
  opacity: 0.5;
  padding: 1px 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
}

.dag-chip.used {
  opacity: 0.3;
  pointer-events: none;
}

/* ── Chat Input ─────────────────────────────────────────────────────────── */
.chat-input-area {
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.chat-input-previews {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  overflow-x: auto;
}

.chat-input-preview {
  position: relative;
  width: 80px;
  height: 60px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px dashed var(--border);
  flex-shrink: 0;
}

.chat-input-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-input-preview-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.8);
  color: white;
  border: none;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chat-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-2);
  transition: border-color var(--duration-fast);
}

.chat-input-wrapper:focus-within {
  border-color: var(--border-focus);
}

.chat-input-wrapper textarea {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-family: var(--font);
  font-size: var(--font-size-base);
  line-height: 1.5;
  resize: none;
  outline: none;
  min-height: 24px;
  max-height: 120px;
  padding: 4px 8px;
}

.chat-input-actions {
  display: flex;
  gap: 2px;
}

/* ── Spec-Kit Panel ─────────────────────────────────────────────────────── */
.speckit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.speckit-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-strong);
}

.speckit-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.speckit-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  transition: all var(--duration-normal) var(--ease-out);
}

.speckit-section.locked {
  opacity: 0.4;
  pointer-events: none;
}

.speckit-section.locked::after {
  content: attr(data-lock-label);
  display: block;
  text-align: center;
  padding: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.speckit-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.speckit-section-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

.speckit-section-edit {
  font-size: var(--font-size-xs);
  color: var(--accent);
  cursor: pointer;
  border: none;
  background: none;
  font-family: var(--font);
}

.speckit-section-edit:hover {
  color: var(--accent-hover);
  text-decoration: underline;
}

/* Streaming highlight for new content */
.speckit-highlight {
  background: rgba(34, 197, 94, 0.08);
  border-left: 2px solid var(--green);
  padding-left: var(--space-2);
  animation: highlight-fade 2s ease forwards;
}

/* User edit highlight */
.speckit-user-edit {
  background: rgba(245, 158, 11, 0.08);
  border-left: 2px solid var(--yellow);
  padding-left: var(--space-2);
}

.speckit-field {
  margin-bottom: var(--space-2);
}

.speckit-field-label {
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--text-tertiary);
  margin-bottom: 2px;
}

.speckit-field-value {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

/* Requirement checkboxes */
.speckit-requirement {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: 4px 0;
}

.speckit-requirement input[type="checkbox"] {
  margin-top: 3px;
  accent-color: var(--accent);
}

/* ── Risk Cards (Pre-mortem) ────────────────────────────────────────────── */
.risk-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  border-left: 4px solid var(--priority-3);
  margin-bottom: var(--space-3);
  transition: all var(--duration-normal) var(--ease-out);
}

.risk-card.severity-critical {
  border-left-color: var(--red);
  background: rgba(239, 68, 68, 0.02);
}

.risk-card.severity-watch {
  border-left-color: var(--yellow);
  background: rgba(245, 158, 11, 0.02);
}

.risk-card.severity-low {
  border-left-color: var(--green);
  background: rgba(34, 197, 94, 0.02);
}

.risk-card-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-strong);
  margin-bottom: var(--space-1);
}

.risk-card-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
  line-height: 1.5;
}

.risk-card-scores {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.risk-score {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
}

.risk-stars {
  letter-spacing: 2px;
  color: var(--yellow);
}

.risk-mitigation {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-card);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-3);
}

.risk-actions {
  display: flex;
  gap: var(--space-2);
}

.risk-btn {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  font-family: var(--font);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.risk-btn:hover {
  background: var(--bg-card-hover);
  border-color: var(--border-hover);
}

.risk-btn.selected {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--text-strong);
}

.risk-btn.selected.accept   { border-color: var(--green); background: var(--green-dim); }
.risk-btn.selected.mitigate { border-color: var(--yellow); background: var(--yellow-dim); }
.risk-btn.selected.eliminate { border-color: var(--red); background: var(--red-dim); }

/* ── Risk Summary Bar ───────────────────────────────────────────────────── */
.risk-summary {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.risk-summary-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.risk-summary-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* ── Approval Gate ──────────────────────────────────────────────────────── */
.approval-gate {
  padding: var(--space-6) var(--space-5);
  border-top: 1px solid var(--border);
}

.approval-gate-btn {
  width: 100%;
  padding: 16px 24px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--phase-confirm);
  color: white;
  font-size: var(--font-size-md);
  font-weight: 700;
  font-family: var(--font);
  cursor: pointer;
  transition: all var(--duration-normal) var(--ease-out);
  position: relative;
  overflow: hidden;
}

.approval-gate-btn:hover {
  background: #047857;
  box-shadow: 0 0 24px rgba(5, 150, 105, 0.2);
}

.approval-gate-btn:active {
  transform: scale(0.98);
}

.approval-gate-btn.approved {
  background: #065f46;
  cursor: default;
}

.approval-gate-escape {
  display: flex;
  justify-content: center;
  gap: var(--space-6);
  margin-top: var(--space-3);
}

.approval-gate-escape a {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  cursor: pointer;
}
.approval-gate-escape a:hover {
  color: var(--text-secondary);
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .thinktank {
    flex-direction: column;
  }

  .thinktank-chat {
    flex: 1 1 60%;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }

  .thinktank-speckit {
    flex: 1 1 40%;
  }
}

@media (max-width: 768px) {
  .thinktank-speckit {
    display: none;
  }

  .thinktank-chat {
    flex: 1 1 100%;
  }

  .phase-sublabel {
    display: none;
  }

  .phase-line {
    width: 24px;
  }
}
```

---

## Fix 5: Timeline, Components, and Animations CSS (css/timeline.css, css/components.css, css/animations.css)

### Problem

The remaining three CSS files cover the timeline waterfall, shared components (toasts, modals,
command palette, context menus, approval cards), and all keyframe animations. These are the
visual polish that makes the dashboard feel production-grade.

### Implementation: css/timeline.css

```css
/* ==========================================================================
   TIMELINE.CSS — AgentOps-Style Waterfall, Event Rows, Detail Panel
   ========================================================================== */

.timeline-container {
  display: flex;
  height: calc(100vh - 180px);
  gap: 0;
}

.timeline-list {
  flex: 0 0 60%;
  overflow-y: auto;
  border-right: 1px solid var(--border);
}

.timeline-detail {
  flex: 0 0 40%;
  overflow-y: auto;
  padding: var(--space-6);
  background: var(--bg-1);
}

.timeline-detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

/* ── Timeline Header ───────────────────────────────────────────────────── */
.timeline-header-row {
  display: grid;
  grid-template-columns: 200px 100px 1fr 80px;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg-base);
  z-index: 2;
}

/* ── Event Row ──────────────────────────────────────────────────────────── */
.timeline-event {
  display: grid;
  grid-template-columns: 200px 100px 1fr 80px;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background var(--duration-fast);
  align-items: center;
}

.timeline-event:hover {
  background: var(--bg-card-hover);
}

.timeline-event.selected {
  background: var(--accent-dim);
}

.timeline-event-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.timeline-event-type {
  font-size: var(--font-size-xs);
}

/* Waterfall bar */
.timeline-bar-container {
  position: relative;
  height: 20px;
}

.timeline-bar {
  position: absolute;
  top: 4px;
  height: 12px;
  border-radius: 3px;
  min-width: 4px;
  transition: opacity var(--duration-fast);
}

.timeline-bar.type-agent-spawn { background: var(--purple); }
.timeline-bar.type-tool-call   { background: var(--blue); }
.timeline-bar.type-status      { background: var(--green); }
.timeline-bar.type-bead        { background: var(--yellow); }
.timeline-bar.type-error       { background: var(--red); }
.timeline-bar.type-approval    { background: var(--phase-listen); }

.timeline-event-duration {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--text-tertiary);
  text-align: right;
}

/* ── Detail Panel Content ───────────────────────────────────────────────── */
.timeline-detail-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-strong);
  margin-bottom: var(--space-4);
}

.timeline-detail-section {
  margin-bottom: var(--space-5);
}

.timeline-detail-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  margin-bottom: var(--space-2);
}

.timeline-detail-value {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.timeline-detail-code {
  background: var(--bg-3);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .timeline-container {
    flex-direction: column;
  }
  .timeline-list {
    flex: 1;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .timeline-detail {
    flex: 0 0 300px;
  }
}
```

### Implementation: css/components.css

```css
/* ==========================================================================
   COMPONENTS.CSS — Toast, Command Palette, Context Menu, Approval Card, Modal
   ========================================================================== */

/* ── Toast Notifications ────────────────────────────────────────────────── */
.toast-container {
  position: fixed;
  bottom: var(--space-6);
  right: var(--space-6);
  display: flex;
  flex-direction: column-reverse;
  gap: var(--space-2);
  z-index: var(--z-toast);
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--font-size-sm);
  pointer-events: auto;
  max-width: 400px;
  box-shadow: var(--shadow-lg);
  animation: toast-in 0.3s var(--ease-out) forwards;
}

.toast.success { background: #065f46; border: 1px solid var(--green); }
.toast.error   { background: #7f1d1d; border: 1px solid var(--red); }
.toast.warning { background: #78350f; border: 1px solid var(--yellow); }
.toast.info    { background: #1e3a5f; border: 1px solid var(--blue); }

.toast-icon { font-size: 16px; flex-shrink: 0; }
.toast-message { flex: 1; }

.toast-close {
  background: none;
  border: none;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  font-size: 16px;
  padding: 0 2px;
  flex-shrink: 0;
}
.toast-close:hover { color: white; }

.toast.dismissing {
  animation: toast-out 0.3s var(--ease-out) forwards;
}

/* ── Command Palette ────────────────────────────────────────────────────── */
.cmd-palette-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: var(--z-command);
  display: flex;
  justify-content: center;
  padding-top: 15vh;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.cmd-palette-overlay.visible {
  opacity: 1;
  pointer-events: auto;
}

.cmd-palette {
  width: 560px;
  max-height: 480px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-xl);
  transform: translateY(-10px) scale(0.98);
  transition: transform var(--duration-fast) var(--ease-out);
}

.cmd-palette-overlay.visible .cmd-palette {
  transform: translateY(0) scale(1);
}

.cmd-palette-input {
  width: 100%;
  padding: var(--space-4) var(--space-5);
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--text-primary);
  font-size: var(--font-size-md);
  font-family: var(--font);
  outline: none;
}

.cmd-palette-input::placeholder {
  color: var(--text-tertiary);
}

.cmd-palette-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.cmd-palette-category {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  padding: var(--space-2) var(--space-3) var(--space-1);
}

.cmd-palette-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-fast);
}

.cmd-palette-item:hover,
.cmd-palette-item.selected {
  background: rgba(255, 255, 255, 0.08);
}

.cmd-icon {
  width: 20px;
  text-align: center;
  font-size: var(--font-size-base);
  opacity: 0.7;
  flex-shrink: 0;
}

.cmd-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cmd-name {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-primary);
}

.cmd-desc {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.cmd-shortcut {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  background: rgba(255,255,255,0.08);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  white-space: nowrap;
  flex-shrink: 0;
}

.cmd-palette-hints {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--border);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.cmd-palette-hints kbd {
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(255,255,255,0.08);
  font-family: var(--font-mono);
  margin: 0 2px;
  font-size: 10px;
}

.cmd-palette-empty {
  padding: var(--space-6);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

/* ── Context Menu ───────────────────────────────────────────────────────── */
.context-menu {
  position: fixed;
  width: 220px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-hover);
  border-radius: var(--radius-md);
  padding: var(--space-1);
  z-index: var(--z-command);
  box-shadow: var(--shadow-lg);
  display: none;
}

.context-menu.visible { display: block; }

.context-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  transition: background var(--duration-fast);
}

.context-item:hover {
  background: rgba(255,255,255,0.08);
}

.context-item-icon {
  width: 18px;
  text-align: center;
  font-size: var(--font-size-sm);
  opacity: 0.6;
}

.context-item kbd {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(255,255,255,0.06);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.context-separator {
  height: 1px;
  background: var(--border);
  margin: var(--space-1) var(--space-2);
}

.context-item.danger { color: var(--red); }
.context-item.success { color: var(--green); }

/* ── Approval Card ──────────────────────────────────────────────────────── */
.approval-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  border-left: 3px solid var(--priority-3);
  transition: all var(--duration-normal) var(--ease-out);
}

.approval-card.urgency-critical {
  border-left-color: var(--red);
  animation: pulse-border-red 2s infinite;
}
.approval-card.urgency-high { border-left-color: var(--priority-1); }
.approval-card.urgency-medium { border-left-color: var(--yellow); }
.approval-card.urgency-low { border-left-color: var(--green); }

.approval-card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.approval-card-body {
  margin-bottom: var(--space-3);
}

.approval-card-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-strong);
  margin-bottom: var(--space-1);
}

.approval-card-desc {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.approval-card-evidence {
  margin-top: var(--space-2);
}

.approval-card-evidence summary {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  cursor: pointer;
}

.approval-card-impact {
  margin-top: var(--space-2);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-card);
  border-radius: var(--radius-sm);
}

.approval-card-confidence {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.approval-card-actions {
  display: flex;
  gap: var(--space-2);
}

.approval-card-actions .btn-approve {
  background: var(--green);
  color: white;
  border: none;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-sm);
  font-family: var(--font);
  transition: all var(--duration-fast) var(--ease-out);
}
.approval-card-actions .btn-approve:hover { background: #16a34a; }
.approval-card-actions .btn-approve:active { transform: scale(0.97); }

.approval-card-actions .btn-reject {
  background: transparent;
  color: var(--red);
  border: 1px solid var(--red);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-sm);
  font-family: var(--font);
  transition: all var(--duration-fast) var(--ease-out);
}
.approval-card-actions .btn-reject:hover { background: var(--red-dim); }

.approval-reject-area {
  display: none;
  margin-top: var(--space-3);
}

.approval-reject-area.visible { display: block; }

.approval-reject-area textarea {
  width: 100%;
  min-height: 60px;
  margin-bottom: var(--space-2);
}

.approval-card.approved {
  opacity: 0.6;
  border-left-color: var(--green);
  background: var(--green-dim);
}

.approval-card.rejected {
  opacity: 0.6;
  border-left-color: var(--red);
  background: var(--red-dim);
}

/* ── Dashboard Cards ────────────────────────────────────────────────────── */
.dash-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.dash-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: all var(--duration-fast) var(--ease-out);
}

.dash-card:hover {
  border-color: var(--border-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.dash-card-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  margin-bottom: var(--space-2);
}

.dash-card-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-strong);
  line-height: 1;
}

.dash-card-sub {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}

/* Alert banner */
.dash-alert {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--red-dim);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--red);
}

.dash-alert-icon { font-size: 18px; }

/* Quick actions */
.dash-actions {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

/* ── Epic Progress Bars ─────────────────────────────────────────────────── */
.epic-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  margin-bottom: var(--space-3);
}

.epic-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-strong);
  margin-bottom: var(--space-2);
}

.epic-progress-bar {
  height: 8px;
  border-radius: 4px;
  background: var(--bg-3);
  overflow: hidden;
  display: flex;
}

.epic-progress-done {
  background: var(--green);
  transition: width var(--duration-slow) var(--ease-out);
}

.epic-progress-wip {
  background: var(--yellow);
  transition: width var(--duration-slow) var(--ease-out);
}

.epic-progress-blocked {
  background: var(--red);
  transition: width var(--duration-slow) var(--ease-out);
}

.epic-meta {
  display: flex;
  gap: var(--space-4);
  margin-top: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

/* ── Shimmer Loading ────────────────────────────────────────────────────── */
.shimmer {
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--bg-3) 25%, var(--bg-4) 50%, var(--bg-3) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.shimmer-short { width: 30%; }
.shimmer-medium { width: 60%; }
.shimmer-long { width: 90%; }

/* ── Modal (generic) ────────────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(4px);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.modal-overlay.visible {
  opacity: 1;
  pointer-events: auto;
}

.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  max-width: 500px;
  width: 90%;
  box-shadow: var(--shadow-xl);
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-strong);
  margin-bottom: var(--space-4);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-5);
}
```

### Implementation: css/animations.css

```css
/* ==========================================================================
   ANIMATIONS.CSS — Keyframes, Micro-Interactions, Phase Animations
   ========================================================================== */

/* ── Pulse (status dots) ────────────────────────────────────────────────── */
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ── Phase Stepper Pulse ────────────────────────────────────────────────── */
@keyframes phase-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(99, 102, 241, 0); }
}

/* ── Phase Check Pop ────────────────────────────────────────────────────── */
@keyframes phase-check-pop {
  0% { transform: scale(0); }
  70% { transform: scale(1.15); }
  100% { transform: scale(1); }
}

/* ── Phase Line Flow ────────────────────────────────────────────────────── */
@keyframes phase-line-flow {
  0% { left: -40%; }
  100% { left: 100%; }
}

/* ── Toast Enter/Exit ───────────────────────────────────────────────────── */
@keyframes toast-in {
  from { opacity: 0; transform: translateX(100px) scale(0.95); }
  to   { opacity: 1; transform: translateX(0) scale(1); }
}

@keyframes toast-out {
  from { opacity: 1; transform: translateX(0) scale(1); }
  to   { opacity: 0; transform: translateX(100px) scale(0.95); }
}

/* ── Message Fade In ────────────────────────────────────────────────────── */
@keyframes message-fade-in {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Chip Fade In (staggered) ───────────────────────────────────────────── */
@keyframes chip-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Typing Bounce ──────────────────────────────────────────────────────── */
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-4px); }
}

/* ── Shimmer ────────────────────────────────────────────────────────────── */
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── Highlight Fade (spec-kit new content) ──────────────────────────────── */
@keyframes highlight-fade {
  0% { background: rgba(34, 197, 94, 0.12); }
  100% { background: transparent; border-left-color: transparent; }
}

/* ── Pulse Border (critical approval) ───────────────────────────────────── */
@keyframes pulse-border-red {
  0%, 100% { border-left-color: var(--red); }
  50% { border-left-color: #fca5a5; }
}

/* ── Card Hover Lift ────────────────────────────────────────────────────── */
@keyframes card-appear {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Slide Down (section reveal) ────────────────────────────────────────── */
@keyframes slide-down {
  from { max-height: 0; opacity: 0; }
  to   { max-height: 500px; opacity: 1; }
}

/* ── Spin (loading) ─────────────────────────────────────────────────────── */
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* ── Fade In/Out Utility ────────────────────────────────────────────────── */
.fade-enter {
  animation: fade-in var(--duration-normal) var(--ease-out) forwards;
}

.fade-exit {
  animation: fade-out var(--duration-normal) var(--ease-out) forwards;
}

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes fade-out {
  from { opacity: 1; }
  to   { opacity: 0; }
}

/* ── Confetti / Success burst (approval gate) ───────────────────────────── */
@keyframes approval-burst {
  0% { transform: scale(1); }
  30% { transform: scale(0.97); }
  60% { transform: scale(1); background: #065f46; }
  100% { transform: scale(1); background: #065f46; }
}
```

---

## Fix 6: HTML Shell (index.html)

### Problem

The app needs a single HTML entry point that loads all CSS files, defines the app skeleton
(nav sidebar, topbar, main content area, overlay containers), and bootstraps the JS modules.

### Solution

A clean HTML file with semantic structure, all CSS imports, the SVG sprite sheet inline,
and a single `<script type="module">` that imports `app.js`.

### Implementation: index.html

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Command Center</title>

  <!-- CSS (order matters: theme first, then layout, then specifics) -->
  <link rel="stylesheet" href="css/theme.css">
  <link rel="stylesheet" href="css/layout.css">
  <link rel="stylesheet" href="css/kanban.css">
  <link rel="stylesheet" href="css/thinktank.css">
  <link rel="stylesheet" href="css/timeline.css">
  <link rel="stylesheet" href="css/components.css">
  <link rel="stylesheet" href="css/animations.css">

  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#9881;</text></svg>">
</head>
<body>

  <div class="app" id="app">

    <!-- ── Navigation Sidebar ──────────────────────────────────────────── -->
    <nav class="nav" id="nav">
      <div class="nav-header">
        <div class="nav-logo">B</div>
        <span class="nav-project-name">Command Center</span>
      </div>

      <div class="nav-section">
        <div class="nav-section-label">Views</div>
        <a class="nav-item active" data-view="dashboard" href="#dashboard">
          <span class="nav-item-icon">&#9633;</span>
          <span>Dashboard</span>
        </a>
        <a class="nav-item" data-view="kanban" href="#kanban">
          <span class="nav-item-icon">&#9638;</span>
          <span>Kanban</span>
        </a>
        <a class="nav-item" data-view="thinktank" href="#thinktank">
          <span class="nav-item-icon">&#9733;</span>
          <span>Think Tank</span>
        </a>
        <a class="nav-item" data-view="timeline" href="#timeline">
          <span class="nav-item-icon">&#8614;</span>
          <span>Timeline</span>
        </a>
        <a class="nav-item" data-view="agents" href="#agents">
          <span class="nav-item-icon">&#9881;</span>
          <span>Agents</span>
        </a>
        <a class="nav-item" data-view="epics" href="#epics">
          <span class="nav-item-icon">&#9776;</span>
          <span>Epics</span>
        </a>
      </div>

      <div class="nav-section">
        <div class="nav-section-label">Quick</div>
        <a class="nav-item" id="nav-approvals" href="#dashboard">
          <span class="nav-item-icon">&#9888;</span>
          <span>Approvals</span>
          <span class="nav-item-badge" id="approval-badge" style="display:none">0</span>
        </a>
      </div>

      <div class="nav-footer">
        <div class="nav-footer-item">
          <span class="status-dot status-dot-success" id="ws-status-dot"></span>
          <span id="ws-status-text">Connected</span>
        </div>
      </div>
    </nav>

    <!-- ── Top Bar ─────────────────────────────────────────────────────── -->
    <header class="topbar">
      <div class="topbar-left">
        <button class="btn-icon" id="mobile-menu-btn" style="display:none" aria-label="Menu">&#9776;</button>
        <span class="topbar-title" id="topbar-title">Dashboard</span>
      </div>
      <div class="topbar-right">
        <div class="topbar-cmdk-hint" id="cmdk-trigger">
          <kbd>&#8984;K</kbd>
          <span>Search commands</span>
        </div>
      </div>
    </header>

    <!-- ── Main Content Area ───────────────────────────────────────────── -->
    <main class="main" id="main">
      <div id="view-root"></div>
    </main>

  </div>

  <!-- ── Overlay Containers (outside app grid) ─────────────────────────── -->
  <div class="panel-overlay" id="panel-overlay"></div>
  <div class="side-panel" id="side-panel"></div>
  <div class="context-menu" id="context-menu"></div>
  <div class="toast-container" id="toast-container"></div>

  <!-- ── App Entry Point ───────────────────────────────────────────────── -->
  <script type="module" src="js/app.js"></script>

</body>
</html>
```

---

## Fix 7: Core JS Infrastructure (js/state.js, js/api.js, js/router.js, js/utils/*.js)

### Problem

The app needs three infrastructure modules before any views can render: a reactive state
store that notifies subscribers when data changes, an API client that handles REST calls
and WebSocket connections with auto-reconnect, and a hash-based router. Plus utility
modules for DOM helpers, time formatting, and fuzzy search.

### Solution

Minimal, focused ES modules. The state store is ~50 lines with key-level subscriptions.
The API client wraps fetch with error handling and manages two WebSocket connections. The
router maps hash fragments to view render functions.

### Implementation: js/state.js

```javascript
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
```

### Implementation: js/api.js

```javascript
// ==========================================================================
// API.JS — REST Client + WebSocket Manager with Auto-Reconnect
// ==========================================================================

import { setState, getState } from './state.js';
import { showToast } from './components/toast.js';

const BASE_URL = window.location.origin;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

// ── REST Client ────────────────────────────────────────────────────────────

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${path} failed: ${res.status} ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Dashboard
  getDashboard:   () => request('GET', '/api/dashboard'),

  // Agents
  getAgents:      () => request('GET', '/api/agents'),
  getAgent:       (id) => request('GET', `/api/agents/${id}`),
  killAgent:      (id) => request('POST', `/api/agents/${id}/kill`),
  retryAgent:     (id) => request('POST', `/api/agents/${id}/retry`),

  // Beads (Kanban)
  getKanban:      () => request('GET', '/api/kanban'),
  getBeads:       () => request('GET', '/api/beads'),
  getBead:        (id) => request('GET', `/api/beads/${id}`),
  moveBead:       (id, column) => request('PATCH', `/api/beads/${id}/move`, { column }),
  updateBead:     (id, data) => request('PATCH', `/api/beads/${id}`, data),
  commentBead:    (id, text) => request('POST', `/api/beads/${id}/comment`, { text }),

  // Think Tank
  createSession:  (data) => request('POST', '/api/thinktank/start', data),
  getSession:     () => request('GET', '/api/thinktank/session'),
  sendMessage:    (sessionId, msg) => request('POST', '/api/thinktank/message', msg),
  sendAction:     (sessionId, action) => request('POST', '/api/thinktank/action', action),
  approveSpec:    (sessionId) => request('POST', '/api/thinktank/approve'),
  getHistory:     () => request('GET', '/api/thinktank/history'),

  // Epics
  getEpics:       () => request('GET', '/api/epics'),

  // Commands
  executeCommand: (cmd) => request('POST', '/api/commands/execute', cmd),

  // Attachments
  uploadAttachment: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/api/attachments`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },

  // Events (timeline)
  getEvents:      (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/api/dashboard/timeline${qs ? '?' + qs : ''}`);
  },
};

// ── WebSocket Manager ──────────────────────────────────────────────────────

class WebSocketManager {
  constructor(path, onMessage) {
    this.path = path;
    this.onMessage = onMessage;
    this.ws = null;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.reconnectTimer = null;
    this.intentionalClose = false;
  }

  connect() {
    this.intentionalClose = false;
    const url = `${WS_BASE}${this.path}`;

    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      console.error(`WebSocket connect error [${this.path}]:`, err);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log(`WebSocket connected: ${this.path}`);
      this.reconnectDelay = 1000;
      setState({ wsConnected: true });
      this._updateStatusUI(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch (err) {
        console.error(`WebSocket parse error [${this.path}]:`, err);
      }
    };

    this.ws.onclose = (event) => {
      console.log(`WebSocket closed: ${this.path} (code=${event.code})`);
      setState({ wsConnected: false });
      this._updateStatusUI(false);
      if (!this.intentionalClose) {
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = (err) => {
      console.error(`WebSocket error [${this.path}]:`, err);
    };
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  close() {
    this.intentionalClose = true;
    clearTimeout(this.reconnectTimer);
    if (this.ws) this.ws.close();
  }

  _scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    console.log(`WebSocket reconnecting in ${this.reconnectDelay}ms...`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this.connect();
    }, this.reconnectDelay);
  }

  _updateStatusUI(connected) {
    const dot = document.getElementById('ws-status-dot');
    const text = document.getElementById('ws-status-text');
    if (dot) {
      dot.className = `status-dot ${connected ? 'status-dot-success' : 'status-dot-error'}`;
    }
    if (text) {
      text.textContent = connected ? 'Connected' : 'Reconnecting...';
    }
  }
}

// ── WebSocket Instances ────────────────────────────────────────────────────

function handleEventMessage(data) {
  const state = getState();
  switch (data.type) {
    case 'agent_update':
      setState({
        agents: state.agents.map(a => a.id === data.agent.id ? { ...a, ...data.agent } : a)
      });
      break;
    case 'bead_update':
      setState({
        beads: state.beads.map(b => b.id === data.bead.id ? { ...b, ...data.bead } : b)
      });
      break;
    case 'new_event':
      setState({ events: [data.event, ...state.events].slice(0, 500) });
      break;
    case 'approval_needed':
      setState({ approvals: [...state.approvals, data.approval] });
      showToast(`Approval needed: ${data.approval.title}`, 'warning');
      break;
    case 'agent_error':
      showToast(`Agent ${data.agentName} error: ${data.message}`, 'error');
      break;
    default:
      break;
  }
}

function handleThinktankMessage(data) {
  const state = getState();
  const tt = { ...state.thinktank };

  switch (data.type) {
    case 'token':
      // Append streaming token to last AI message
      if (tt.messages.length > 0) {
        const last = tt.messages[tt.messages.length - 1];
        if (last.role === 'ai' && last.streaming) {
          last.content += data.token;
          setState({ thinktank: { ...tt, messages: [...tt.messages] } });
        }
      }
      break;
    case 'message_complete':
      if (tt.messages.length > 0) {
        const last = tt.messages[tt.messages.length - 1];
        last.streaming = false;
        last.chips = data.chips || [];
        setState({ thinktank: { ...tt, messages: [...tt.messages] } });
      }
      break;
    case 'speckit_update':
      setState({ thinktank: { ...tt, specKit: { ...tt.specKit, ...data.sections } } });
      break;
    case 'phase_advance':
      setState({ thinktank: { ...tt, phase: data.phase } });
      break;
    case 'risk_added':
      setState({ thinktank: { ...tt, risks: [...tt.risks, data.risk] } });
      break;
    default:
      break;
  }
}

export let eventsWs = null;
export let thinktankWs = null;

export function connectWebSockets() {
  eventsWs = new WebSocketManager('/ws', handleEventMessage);
  eventsWs.connect();
}

export function connectThinktankWs(sessionId) {
  if (thinktankWs) thinktankWs.close();
  thinktankWs = new WebSocketManager(`/ws/thinktank?session=${sessionId}`, handleThinktankMessage);
  thinktankWs.connect();
}

export function disconnectThinktankWs() {
  if (thinktankWs) {
    thinktankWs.close();
    thinktankWs = null;
  }
}
```

### Implementation: js/router.js

```javascript
// ==========================================================================
// ROUTER.JS — Hash-Based Router
// ==========================================================================

import { setState } from './state.js';

const _routes = {};

export function registerRoute(name, renderFn) {
  _routes[name] = renderFn;
}

export function navigate(hash) {
  const view = hash.replace('#', '') || 'dashboard';
  const root = document.getElementById('view-root');
  if (!root) return;

  // Update nav active state
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === view);
  });

  // Update topbar title
  const titles = {
    dashboard: 'Dashboard',
    kanban: 'Kanban Board',
    thinktank: 'Think Tank',
    timeline: 'Timeline',
    agents: 'Agents',
    epics: 'Epics'
  };
  const titleEl = document.getElementById('topbar-title');
  if (titleEl) titleEl.textContent = titles[view] || view;

  // Update state
  setState({ currentView: view });

  // Render view
  const renderFn = _routes[view];
  if (renderFn) {
    root.innerHTML = '';
    renderFn(root);
  } else {
    root.innerHTML = `<div class="view-container"><h2>View not found: ${view}</h2></div>`;
  }
}

export function initRouter() {
  window.addEventListener('hashchange', () => navigate(window.location.hash));

  // Nav click handler
  document.querySelectorAll('.nav-item[data-view]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.hash = item.dataset.view;
    });
  });

  // Initial route
  navigate(window.location.hash || '#dashboard');
}
```

### Implementation: js/utils/dom.js

```javascript
// ==========================================================================
// DOM.JS — DOM Helpers
// ==========================================================================

/**
 * Create an element with attributes and children.
 * h('div', { class: 'foo', onclick: fn }, 'text', childEl)
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);

  for (const [key, val] of Object.entries(attrs)) {
    if (key === 'class' || key === 'className') {
      el.className = val;
    } else if (key === 'style' && typeof val === 'object') {
      Object.assign(el.style, val);
    } else if (key.startsWith('on') && typeof val === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), val);
    } else if (key === 'dataset') {
      Object.assign(el.dataset, val);
    } else if (key === 'htmlContent') {
      el.innerHTML = val;
    } else {
      el.setAttribute(key, val);
    }
  }

  for (const child of children) {
    if (child == null || child === false) continue;
    if (typeof child === 'string' || typeof child === 'number') {
      el.appendChild(document.createTextNode(String(child)));
    } else if (child instanceof Node) {
      el.appendChild(child);
    }
  }

  return el;
}

/** Query selector shorthand */
export const $ = (sel, ctx = document) => ctx.querySelector(sel);
export const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/** Safely set innerHTML */
export function setHTML(el, html) {
  if (typeof el === 'string') el = $(el);
  if (el) el.innerHTML = html;
}

/** Remove all children */
export function clearChildren(el) {
  if (typeof el === 'string') el = $(el);
  while (el && el.firstChild) el.removeChild(el.firstChild);
}
```

### Implementation: js/utils/format.js

```javascript
// ==========================================================================
// FORMAT.JS — Time & Number Formatting
// ==========================================================================

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Relative time string: "2m ago", "3h ago", "1d ago"
 */
export function timeAgo(dateStr) {
  if (!dateStr) return '';
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  const diff = Date.now() - date.getTime();

  if (diff < MINUTE) return 'just now';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d ago`;
  return date.toLocaleDateString();
}

/**
 * Duration string: "1.2s", "450ms", "3m 12s"
 */
export function formatDuration(ms) {
  if (ms == null) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const min = Math.floor(ms / 60000);
  const sec = Math.round((ms % 60000) / 1000);
  return `${min}m ${sec}s`;
}

/**
 * Compact number: "1.2K", "3.4M"
 */
export function compactNumber(num) {
  if (num == null) return '0';
  if (num < 1000) return String(num);
  if (num < 1000000) return (num / 1000).toFixed(1) + 'K';
  return (num / 1000000).toFixed(1) + 'M';
}

/**
 * Generate a consistent color from a string (for agent badges)
 */
export function stringToColor(str) {
  if (!str) return '#6366f1';
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 60%, 55%)`;
}

/**
 * Generate star rating: "****_" for 4/5
 */
export function starRating(score, max = 5) {
  return '\u2605'.repeat(score) + '\u2606'.repeat(max - score);
}
```

### Implementation: js/utils/fuzzy.js

```javascript
// ==========================================================================
// FUZZY.JS — Fuzzy Search for Command Palette
// ==========================================================================

/**
 * Score how well query matches text.
 * Each char of query must appear in order in text.
 * Bonuses for: word boundary matches, consecutive chars, early matches.
 * Returns 0 for no match, positive score for match.
 */
export function fuzzyScore(query, text) {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let qi = 0;
  let score = 0;
  let consecutiveBonus = 0;

  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) {
      score += 1 + consecutiveBonus;
      // Word boundary bonus
      if (i === 0 || t[i - 1] === ' ' || t[i - 1] === '-' || t[i - 1] === '_') {
        score += 5;
      }
      consecutiveBonus += 2;
      qi++;
    } else {
      consecutiveBonus = 0;
    }
  }

  return qi === q.length ? score : 0;
}

/**
 * Filter and sort items by fuzzy match score.
 * @param {string} query
 * @param {Array} items
 * @param {string|Function} keyOrFn - property name or function to extract text
 * @returns {Array} matched items sorted by score (best first)
 */
export function fuzzySearch(query, items, keyOrFn = 'name') {
  if (!query || !query.trim()) return items;

  const getText = typeof keyOrFn === 'function'
    ? keyOrFn
    : (item) => [item[keyOrFn], item.description, item.category].filter(Boolean).join(' ');

  return items
    .map(item => ({ item, score: fuzzyScore(query, getText(item)) }))
    .filter(r => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(r => r.item);
}
```

---

## Fix 8: Components (js/components/*.js)

### Problem

The app needs reusable interactive components: command palette, toast notifications, context
menus, sidebar panel, clipboard paste handler, approval cards, and the Think Tank specific
components (phase stepper, chat, spec-kit, risk cards). Without these as standalone modules,
views would be bloated and components could not be reused.

### Implementation: js/components/toast.js

```javascript
// ==========================================================================
// TOAST.JS — Notification System
// ==========================================================================

let container = null;

function ensureContainer() {
  if (!container) {
    container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
  }
  return container;
}

const ICONS = {
  success: '\u2713',
  error: '\u2717',
  warning: '\u26A0',
  info: '\u2139'
};

/**
 * Show a toast notification.
 * @param {string} message
 * @param {'success'|'error'|'warning'|'info'} type
 * @param {number} duration - ms, 0 for manual dismiss
 */
export function showToast(message, type = 'info', duration = 4000) {
  const cont = ensureContainer();

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${ICONS[type] || ICONS.info}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" aria-label="Close">\u00D7</button>
  `;

  toast.querySelector('.toast-close').addEventListener('click', () => dismissToast(toast));
  cont.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => dismissToast(toast), duration);
  }

  return toast;
}

function dismissToast(toast) {
  if (!toast || !toast.parentElement) return;
  toast.classList.add('dismissing');
  setTimeout(() => toast.remove(), 300);
}
```

### Implementation: js/components/command-palette.js

```javascript
// ==========================================================================
// COMMAND-PALETTE.JS — Cmd+K Modal with Fuzzy Search
// ==========================================================================

import { fuzzySearch } from '../utils/fuzzy.js';

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
    this._bindGlobalKeys();
  }

  register(commands) {
    this.commands = commands;
    this.filteredCommands = [...commands];
  }

  _createDOM() {
    this.overlay = document.createElement('div');
    this.overlay.className = 'cmd-palette-overlay';
    this.overlay.addEventListener('click', () => this.close());

    const palette = document.createElement('div');
    palette.className = 'cmd-palette';
    palette.addEventListener('click', e => e.stopPropagation());

    this.input = document.createElement('input');
    this.input.className = 'cmd-palette-input';
    this.input.placeholder = 'Type a command...';
    this.input.addEventListener('input', () => this._filter());
    this.input.addEventListener('keydown', e => this._handleNav(e));

    this.list = document.createElement('div');
    this.list.className = 'cmd-palette-list';

    const hints = document.createElement('div');
    hints.className = 'cmd-palette-hints';
    hints.innerHTML = `
      <span><kbd>\u2191</kbd><kbd>\u2193</kbd> Navigate</span>
      <span><kbd>Enter</kbd> Execute</span>
      <span><kbd>Esc</kbd> Close</span>
    `;

    palette.appendChild(this.input);
    palette.appendChild(this.list);
    palette.appendChild(hints);
    this.overlay.appendChild(palette);
    document.body.appendChild(this.overlay);
  }

  _bindGlobalKeys() {
    document.addEventListener('keydown', e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.isOpen ? this.close() : this.open();
      }
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
    requestAnimationFrame(() => this.input.focus());
  }

  close() {
    this.isOpen = false;
    this.overlay.classList.remove('visible');
    this.input.blur();
  }

  _filter() {
    const query = this.input.value.trim();
    this.filteredCommands = query
      ? fuzzySearch(query, this.commands, cmd =>
          [cmd.name, cmd.description, cmd.category].filter(Boolean).join(' ')
        )
      : [...this.commands];
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
    const groups = {};
    this.filteredCommands.forEach(cmd => {
      const cat = cmd.category || 'Actions';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(cmd);
    });

    let html = '';
    let idx = 0;

    for (const [category, cmds] of Object.entries(groups)) {
      html += `<div class="cmd-palette-category">${category}</div>`;
      for (const cmd of cmds) {
        const sel = idx === this.selectedIndex ? 'selected' : '';
        html += `
          <div class="cmd-palette-item ${sel}" data-index="${idx}">
            ${cmd.icon ? `<span class="cmd-icon">${cmd.icon}</span>` : ''}
            <div class="cmd-text">
              <span class="cmd-name">${cmd.name}</span>
              ${cmd.description ? `<span class="cmd-desc">${cmd.description}</span>` : ''}
            </div>
            ${cmd.shortcut ? `<kbd class="cmd-shortcut">${cmd.shortcut}</kbd>` : ''}
          </div>
        `;
        idx++;
      }
    }

    this.list.innerHTML = html || '<div class="cmd-palette-empty">No commands found</div>';

    // Add click handlers
    this.list.querySelectorAll('.cmd-palette-item').forEach(item => {
      const i = parseInt(item.dataset.index);
      item.addEventListener('click', () => {
        const cmd = this.filteredCommands[i];
        if (cmd) { this.close(); cmd.action(); }
      });
      item.addEventListener('mouseenter', () => {
        this.selectedIndex = i;
        this._render();
      });
    });

    // Scroll selected into view
    const selected = this.list.querySelector('.selected');
    if (selected) selected.scrollIntoView({ block: 'nearest' });
  }
}

// Singleton
let instance = null;

export function getCommandPalette() {
  if (!instance) instance = new CommandPalette();
  return instance;
}
```

### Implementation: js/components/context-menu.js

```javascript
// ==========================================================================
// CONTEXT-MENU.JS — Right-Click Context Menus
// ==========================================================================

let menuEl = null;

function ensureMenu() {
  if (!menuEl) {
    menuEl = document.getElementById('context-menu');
    if (!menuEl) {
      menuEl = document.createElement('div');
      menuEl.id = 'context-menu';
      menuEl.className = 'context-menu';
      document.body.appendChild(menuEl);
    }
  }
  // Close on any click outside
  document.addEventListener('click', () => hideContextMenu(), { once: true });
  return menuEl;
}

export function hideContextMenu() {
  if (menuEl) menuEl.classList.remove('visible');
}

/**
 * Show a context menu at the given position.
 * @param {number} x - clientX
 * @param {number} y - clientY
 * @param {Array<{label, icon, shortcut, action, class, type}>} items
 *   type: 'separator' for divider, otherwise regular item
 */
export function showContextMenu(x, y, items) {
  const menu = ensureMenu();

  menu.innerHTML = items.map((item, i) => {
    if (item.type === 'separator') {
      return '<div class="context-separator"></div>';
    }
    return `
      <div class="context-item ${item.class || ''}" data-index="${i}">
        <span class="context-item-icon">${item.icon || ''}</span>
        <span>${item.label}</span>
        ${item.shortcut ? `<kbd>${item.shortcut}</kbd>` : ''}
      </div>
    `;
  }).join('');

  // Add click handlers
  menu.querySelectorAll('.context-item').forEach(el => {
    const idx = parseInt(el.dataset.index);
    const item = items[idx];
    if (item && item.action) {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        hideContextMenu();
        item.action();
      });
    }
  });

  // Position within viewport
  const posX = Math.min(x, window.innerWidth - 240);
  const posY = Math.min(y, window.innerHeight - 300);
  menu.style.left = `${posX}px`;
  menu.style.top = `${posY}px`;
  menu.classList.add('visible');
}
```

### Implementation: js/components/sidebar.js

```javascript
// ==========================================================================
// SIDEBAR.JS — Slide-In Detail Panel
// ==========================================================================

export function openSidePanel(contentHTML) {
  const panel = document.getElementById('side-panel');
  const overlay = document.getElementById('panel-overlay');
  if (!panel || !overlay) return;

  panel.innerHTML = `
    <div class="side-panel-header">
      <h3>Details</h3>
      <button class="side-panel-close" id="side-panel-close">\u00D7</button>
    </div>
    <div class="side-panel-body">${contentHTML}</div>
  `;

  panel.classList.add('open');
  overlay.classList.add('visible');

  // Close handlers
  const closeBtn = document.getElementById('side-panel-close');
  if (closeBtn) closeBtn.addEventListener('click', closeSidePanel);
  overlay.addEventListener('click', closeSidePanel, { once: true });

  const escHandler = (e) => {
    if (e.key === 'Escape') {
      closeSidePanel();
      document.removeEventListener('keydown', escHandler);
    }
  };
  document.addEventListener('keydown', escHandler);
}

export function closeSidePanel() {
  const panel = document.getElementById('side-panel');
  const overlay = document.getElementById('panel-overlay');
  if (panel) panel.classList.remove('open');
  if (overlay) overlay.classList.remove('visible');
}
```

### Implementation: js/components/clipboard.js

```javascript
// ==========================================================================
// CLIPBOARD.JS — Paste-to-Upload Handler
// ==========================================================================

const IMAGE_MIME_REGEX = /^image\/(png|jpeg|gif|webp|svg\+xml)$/i;

/**
 * Initialize paste-to-upload on a target element.
 * @param {HTMLElement} target
 * @param {Function} onImagePaste - receives { blob, dataUrl, file }
 */
export function initPasteUpload(target, onImagePaste) {
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
            file: new File([blob], `paste-${Date.now()}.png`, { type: blob.type })
          });
        };

        reader.readAsDataURL(blob);
        return;
      }
    }
  });
}

/**
 * Create an image preview thumbnail element.
 * @param {string} dataUrl
 * @param {Function} onRemove
 * @returns {HTMLElement}
 */
export function createImagePreview(dataUrl, onRemove) {
  const preview = document.createElement('div');
  preview.className = 'chat-input-preview';
  preview.innerHTML = `
    <img src="${dataUrl}" alt="Pasted image">
    <button class="chat-input-preview-remove">\u00D7</button>
  `;
  preview.querySelector('.chat-input-preview-remove').addEventListener('click', () => {
    preview.remove();
    if (onRemove) onRemove();
  });
  return preview;
}
```

### Implementation: js/components/approval-card.js

```javascript
// ==========================================================================
// APPROVAL-CARD.JS — Approval Request Cards
// ==========================================================================

import { api } from '../api.js';
import { showToast } from './toast.js';
import { timeAgo, stringToColor } from '../utils/format.js';

export function renderApprovalCard(approval) {
  const urgencyColors = {
    critical: 'var(--red)',
    high: 'var(--priority-1)',
    medium: 'var(--yellow)',
    low: 'var(--green)'
  };

  const card = document.createElement('div');
  card.className = `approval-card urgency-${approval.urgency || 'medium'}`;
  card.dataset.id = approval.id;

  const confidenceColor = (approval.confidence || 0) >= 80 ? 'badge-green'
    : (approval.confidence || 0) >= 50 ? 'badge-yellow'
    : 'badge-red';

  card.innerHTML = `
    <div class="approval-card-header">
      <span class="badge badge-${approval.urgency === 'critical' ? 'red' : approval.urgency === 'high' ? 'yellow' : 'blue'}">
        ${(approval.urgency || 'MEDIUM').toUpperCase()}
      </span>
      <span class="badge ${confidenceColor}">${approval.confidence || '?'}% confidence</span>
      <span class="caption" style="margin-left:auto">${timeAgo(approval.createdAt)}</span>
    </div>

    <div class="approval-card-body">
      <div class="approval-card-title">${approval.title || 'Untitled'}</div>
      <div class="approval-card-desc">${approval.description || ''}</div>

      ${approval.evidence ? `
        <div class="approval-card-evidence">
          <details>
            <summary>Evidence (${approval.evidence.length} items)</summary>
            <ul style="padding-left:16px;margin-top:4px;font-size:12px;color:var(--text-secondary)">
              ${approval.evidence.map(e => `<li>${e}</li>`).join('')}
            </ul>
          </details>
        </div>
      ` : ''}

      ${approval.impact ? `
        <div class="approval-card-impact">
          <span class="caption">Impact:</span> ${approval.impact}
        </div>
      ` : ''}
    </div>

    <div class="approval-card-actions">
      <button class="btn-approve">\u2713 Approve</button>
      <button class="btn-reject">\u2717 Reject</button>
    </div>

    <div class="approval-reject-area">
      <textarea placeholder="Reason for rejection (required)..."></textarea>
      <div class="flex gap-2">
        <button class="btn btn-danger btn-sm confirm-reject-btn">Confirm Reject</button>
        <button class="btn btn-ghost btn-sm cancel-reject-btn">Cancel</button>
      </div>
    </div>
  `;

  // Approve handler
  card.querySelector('.btn-approve').addEventListener('click', async () => {
    const origHTML = card.innerHTML;
    card.classList.add('approved');
    card.querySelector('.approval-card-actions').innerHTML =
      '<span class="caption">Approved -- sending to agent...</span>';

    try {
      await api.executeCommand({ type: 'approve', approvalId: approval.id });
      card.style.transition = 'all 0.3s ease';
      card.style.opacity = '0';
      card.style.transform = 'translateX(100px)';
      setTimeout(() => card.remove(), 300);
      showToast(`Approved: ${approval.title}`, 'success');
    } catch (err) {
      card.classList.remove('approved');
      card.innerHTML = origHTML;
      showToast(`Failed: ${err.message}`, 'error');
    }
  });

  // Reject handlers
  const rejectArea = card.querySelector('.approval-reject-area');
  card.querySelector('.btn-reject').addEventListener('click', () => {
    rejectArea.classList.add('visible');
    rejectArea.querySelector('textarea').focus();
  });
  card.querySelector('.cancel-reject-btn').addEventListener('click', () => {
    rejectArea.classList.remove('visible');
  });
  card.querySelector('.confirm-reject-btn').addEventListener('click', async () => {
    const reason = rejectArea.querySelector('textarea').value.trim();
    if (!reason) {
      rejectArea.querySelector('textarea').style.borderColor = 'var(--red)';
      return;
    }
    card.classList.add('rejected');
    try {
      await api.executeCommand({ type: 'reject', approvalId: approval.id, reason });
      setTimeout(() => card.remove(), 2000);
      showToast('Rejected with reason', 'warning');
    } catch (err) {
      card.classList.remove('rejected');
      showToast(`Failed: ${err.message}`, 'error');
    }
  });

  return card;
}
```

### Implementation: js/components/phase-stepper.js

```javascript
// ==========================================================================
// PHASE-STEPPER.JS — Horizontal Phase Indicator
// ==========================================================================

const PHASES = [
  { id: 'listen',  num: 1, label: 'Listen',  sub: 'Understanding your vision' },
  { id: 'explore', num: 2, label: 'Explore', sub: 'Mapping possibilities' },
  { id: 'scope',   num: 3, label: 'Scope',   sub: 'Stress-testing risks' },
  { id: 'confirm', num: 4, label: 'Confirm', sub: 'Final review' },
];

/**
 * Render the phase stepper.
 * @param {number} currentPhase - 1-4
 * @returns {HTMLElement}
 */
export function renderPhaseStepper(currentPhase) {
  const stepper = document.createElement('div');
  stepper.className = 'phase-stepper';

  PHASES.forEach((phase, i) => {
    const status = phase.num < currentPhase ? 'completed'
      : phase.num === currentPhase ? 'active'
      : 'upcoming';

    const step = document.createElement('div');
    step.className = `phase-step ${status}`;

    const circle = document.createElement('div');
    circle.className = 'phase-circle';
    circle.textContent = status === 'completed' ? '\u2713' : String(phase.num);

    const labelWrap = document.createElement('div');
    labelWrap.innerHTML = `
      <span class="phase-label">${phase.label}</span>
      <span class="phase-sublabel">${phase.sub}</span>
    `;

    step.appendChild(circle);
    step.appendChild(labelWrap);
    stepper.appendChild(step);

    // Add connecting line (except after last phase)
    if (i < PHASES.length - 1) {
      const line = document.createElement('div');
      const lineStatus = phase.num < currentPhase ? 'completed'
        : phase.num === currentPhase ? 'active'
        : 'upcoming';
      line.className = `phase-line ${lineStatus}`;
      stepper.appendChild(line);
    }
  });

  return stepper;
}
```

### Implementation: js/components/chat.js

```javascript
// ==========================================================================
// CHAT.JS — Chat Messages + D/A/G Chips + Image Previews
// ==========================================================================

import { h } from '../utils/dom.js';
import { initPasteUpload, createImagePreview } from './clipboard.js';
import { thinktankWs } from '../api.js';

/**
 * Render a chat message bubble.
 * @param {{ role: 'ai'|'human', content: string, chips: Array, streaming: boolean, images: Array }} msg
 * @returns {HTMLElement}
 */
export function renderChatMessage(msg) {
  const wrapper = h('div', { class: `chat-message ${msg.role}` });

  const avatar = h('div', { class: `chat-avatar ${msg.role}` });
  avatar.textContent = msg.role === 'ai' ? 'AI' : 'You';

  const bubble = h('div', { class: 'chat-bubble' });
  bubble.innerHTML = formatMessageContent(msg.content);

  // Inline images
  if (msg.images && msg.images.length) {
    msg.images.forEach(imgUrl => {
      const img = h('img', { src: imgUrl, alt: 'Attached image' });
      bubble.appendChild(img);
    });
  }

  // Streaming cursor
  if (msg.streaming) {
    const cursor = h('span', {
      style: { display: 'inline-block', width: '2px', height: '14px', background: 'var(--accent)', animation: 'pulse-dot 1s infinite', marginLeft: '2px', verticalAlign: 'middle' }
    });
    bubble.appendChild(cursor);
  }

  wrapper.appendChild(avatar);
  wrapper.appendChild(bubble);

  // D/A/G Chips (only on AI messages, after streaming completes)
  if (msg.role === 'ai' && msg.chips && msg.chips.length && !msg.streaming) {
    const chipsContainer = h('div', { class: 'dag-chips' });
    msg.chips.forEach((chip, i) => {
      const shortcutKey = ['D', 'A', 'G'][i] || '';
      const btn = h('button', {
        class: `dag-chip ${msg.chipUsed ? 'used' : ''}`,
        onClick: () => {
          if (chip.action) chip.action();
        }
      });
      btn.innerHTML = `
        <span>${chip.icon || ''}</span>
        <span>${chip.label}</span>
        <span class="dag-shortcut">${shortcutKey}</span>
      `;
      chipsContainer.appendChild(btn);
    });
    // Chips appear below the bubble wrapper
    const chipRow = h('div', { style: { paddingLeft: '44px' } }, chipsContainer);
    // Return a fragment-like approach
    const frag = document.createDocumentFragment();
    frag.appendChild(wrapper);
    frag.appendChild(chipRow);
    return frag;
  }

  return wrapper;
}

/**
 * Render typing indicator.
 */
export function renderTypingIndicator() {
  const wrapper = h('div', { class: 'chat-message ai' });
  const avatar = h('div', { class: 'chat-avatar ai' });
  avatar.textContent = 'AI';
  const dots = h('div', { class: 'chat-typing-indicator' });
  dots.innerHTML = '<span></span><span></span><span></span>';
  wrapper.appendChild(avatar);
  wrapper.appendChild(dots);
  return wrapper;
}

/**
 * Render the chat input area.
 * @param {Function} onSend - (text, images) => void
 * @returns {HTMLElement}
 */
export function renderChatInput(onSend) {
  const area = h('div', { class: 'chat-input-area' });
  const previews = h('div', { class: 'chat-input-previews', id: 'chat-previews' });
  const wrapper = h('div', { class: 'chat-input-wrapper' });

  const textarea = document.createElement('textarea');
  textarea.placeholder = 'Type a message...';
  textarea.rows = 1;

  const pendingImages = [];

  // Auto-resize
  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  });

  // Enter to send (Shift+Enter for newline)
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const text = textarea.value.trim();
      if (text || pendingImages.length) {
        onSend(text, [...pendingImages]);
        textarea.value = '';
        textarea.style.height = 'auto';
        pendingImages.length = 0;
        previews.innerHTML = '';
      }
    }
  });

  // Paste-to-upload
  initPasteUpload(textarea, ({ dataUrl, file }) => {
    pendingImages.push(file);
    const preview = createImagePreview(dataUrl, () => {
      const idx = pendingImages.indexOf(file);
      if (idx > -1) pendingImages.splice(idx, 1);
    });
    previews.appendChild(preview);
  });

  const actions = h('div', { class: 'chat-input-actions' });
  // Upload button
  const uploadBtn = h('button', {
    class: 'btn-icon',
    title: 'Attach image',
    onClick: () => fileInput.click()
  });
  uploadBtn.innerHTML = '\u{1F4CE}';

  const fileInput = h('input', {
    type: 'file',
    accept: 'image/*',
    style: { display: 'none' }
  });
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      pendingImages.push(file);
      const preview = createImagePreview(e.target.result, () => {
        const idx = pendingImages.indexOf(file);
        if (idx > -1) pendingImages.splice(idx, 1);
      });
      previews.appendChild(preview);
    };
    reader.readAsDataURL(file);
    fileInput.value = '';
  });

  // Send button
  const sendBtn = h('button', {
    class: 'btn-icon',
    title: 'Send',
    onClick: () => {
      const text = textarea.value.trim();
      if (text || pendingImages.length) {
        onSend(text, [...pendingImages]);
        textarea.value = '';
        textarea.style.height = 'auto';
        pendingImages.length = 0;
        previews.innerHTML = '';
      }
    }
  });
  sendBtn.innerHTML = '\u2191';

  actions.appendChild(uploadBtn);
  actions.appendChild(fileInput);
  actions.appendChild(sendBtn);

  wrapper.appendChild(textarea);
  wrapper.appendChild(actions);
  area.appendChild(previews);
  area.appendChild(wrapper);

  return area;
}

// Simple markdown-ish formatting
function formatMessageContent(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code class="mono">$1</code>')
    .replace(/\n/g, '<br>');
}
```

### Implementation: js/components/spec-kit.js

```javascript
// ==========================================================================
// SPEC-KIT.JS — Live Spec-Kit Panel with Shimmer and Streaming
// ==========================================================================

import { h } from '../utils/dom.js';

/**
 * Render the spec-kit panel content.
 * @param {{ phase: number, specKit: object, risks: Array }} state
 * @param {Function} onEdit - (sectionKey, newValue) => void
 * @returns {HTMLElement}
 */
export function renderSpecKit(state, onEdit) {
  const container = h('div', { class: 'speckit-content' });

  // Project Brief (always visible)
  container.appendChild(renderSection('brief', 'Project Brief', state.specKit.brief, state.phase >= 1, onEdit));

  // Requirements (Phase 1+)
  container.appendChild(renderRequirements(state.specKit.requirements, state.phase >= 1, onEdit));

  // Constraints (Phase 2+)
  container.appendChild(renderSection('constraints', 'Constraints', state.specKit.constraints, state.phase >= 2, onEdit));

  // Pre-Mortem (Phase 3+)
  if (state.phase >= 3) {
    container.appendChild(renderPreMortemSection(state.risks));
  } else {
    container.appendChild(renderLockedSection('pre-mortem', 'Pre-Mortem', 'Unlocks in Phase 3: Scope'));
  }

  // Execution Plan (Phase 4)
  if (state.phase >= 4) {
    container.appendChild(renderSection('execution', 'Execution Plan', state.specKit.execution, true, onEdit));
  } else {
    container.appendChild(renderLockedSection('execution', 'Execution Plan', 'Unlocks in Phase 4: Confirm'));
  }

  return container;
}

function renderSection(key, title, content, unlocked, onEdit) {
  const section = h('div', {
    class: `speckit-section ${unlocked ? '' : 'locked'}`,
    dataset: { lockLabel: unlocked ? '' : 'Locked' }
  });

  const header = h('div', { class: 'speckit-section-header' });
  header.innerHTML = `
    <span class="speckit-section-title">${title}</span>
    ${unlocked ? '<button class="speckit-section-edit">[edit]</button>' : ''}
  `;

  section.appendChild(header);

  if (unlocked && content) {
    if (typeof content === 'object' && !Array.isArray(content)) {
      for (const [fieldKey, fieldVal] of Object.entries(content)) {
        const field = h('div', { class: 'speckit-field' });
        field.innerHTML = `
          <div class="speckit-field-label">${fieldKey}</div>
          <div class="speckit-field-value">${fieldVal || ''}</div>
        `;
        section.appendChild(field);
      }
    } else if (typeof content === 'string') {
      const body = h('div', { class: 'speckit-field-value' });
      body.innerHTML = content.replace(/\n/g, '<br>');
      section.appendChild(body);
    }
  } else if (unlocked) {
    // Shimmer placeholders
    section.appendChild(h('div', { class: 'shimmer shimmer-long', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-medium', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-short' }));
  }

  // Edit click handler
  const editBtn = section.querySelector('.speckit-section-edit');
  if (editBtn && onEdit) {
    editBtn.addEventListener('click', () => {
      // Toggle inline editing
      const body = section.querySelector('.speckit-field-value');
      if (!body) return;
      const textarea = document.createElement('textarea');
      textarea.value = body.textContent;
      textarea.style.cssText = 'width:100%;min-height:60px;margin-top:8px;';
      textarea.className = 'speckit-user-edit';
      body.replaceWith(textarea);
      textarea.focus();

      textarea.addEventListener('blur', () => {
        onEdit(key, textarea.value);
        const newBody = h('div', { class: 'speckit-field-value speckit-user-edit' });
        newBody.innerHTML = textarea.value.replace(/\n/g, '<br>');
        textarea.replaceWith(newBody);
      });
    });
  }

  return section;
}

function renderRequirements(reqs, unlocked, onEdit) {
  const section = h('div', { class: `speckit-section ${unlocked ? '' : 'locked'}` });
  section.innerHTML = `<div class="speckit-section-header">
    <span class="speckit-section-title">Requirements</span>
    ${unlocked ? '<button class="speckit-section-edit">[edit]</button>' : ''}
  </div>`;

  if (unlocked && reqs) {
    if (reqs.mustHave) {
      const mustHaveLabel = h('div', { class: 'speckit-field-label', style: { marginTop: '8px' } });
      mustHaveLabel.textContent = 'Must-Have';
      section.appendChild(mustHaveLabel);
      reqs.mustHave.forEach(r => {
        section.appendChild(renderRequirement(r));
      });
    }
    if (reqs.niceToHave) {
      const niceLabel = h('div', { class: 'speckit-field-label', style: { marginTop: '12px' } });
      niceLabel.textContent = 'Nice-to-Have';
      section.appendChild(niceLabel);
      reqs.niceToHave.forEach(r => {
        section.appendChild(renderRequirement(r));
      });
    }
  } else if (unlocked) {
    section.appendChild(h('div', { class: 'shimmer shimmer-long', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-medium' }));
  }

  return section;
}

function renderRequirement(req) {
  const item = h('div', { class: 'speckit-requirement' });
  const text = typeof req === 'string' ? req : req.text;
  const done = typeof req === 'object' ? req.done : false;
  item.innerHTML = `
    <input type="checkbox" ${done ? 'checked' : ''}>
    <span style="font-size:14px">${text}</span>
  `;
  return item;
}

function renderLockedSection(key, title, lockMessage) {
  const section = h('div', {
    class: 'speckit-section locked',
    dataset: { lockLabel: lockMessage }
  });
  section.innerHTML = `<div class="speckit-section-header">
    <span class="speckit-section-title">${title}</span>
    <span style="font-size:11px;color:var(--text-tertiary)">\u{1F512}</span>
  </div>`;
  return section;
}

function renderPreMortemSection(risks) {
  const section = h('div', { class: 'speckit-section' });
  section.innerHTML = `<div class="speckit-section-header">
    <span class="speckit-section-title">Pre-Mortem</span>
  </div>
  <p style="font-size:12px;color:var(--text-tertiary);margin-bottom:12px;font-style:italic">
    "It's 6 months from now and the project failed. What went wrong?"
  </p>`;

  if (risks && risks.length) {
    risks.forEach(risk => {
      section.appendChild(renderRiskCardElement(risk));
    });

    // Risk summary
    const critical = risks.filter(r => r.severity === 'critical').length;
    const watch = risks.filter(r => r.severity === 'watch').length;
    const low = risks.filter(r => r.severity === 'low').length;
    const addressed = risks.filter(r => r.disposition).length;

    const summary = h('div', { class: 'risk-summary' });
    summary.innerHTML = `
      <span class="risk-summary-item"><span class="risk-summary-dot" style="background:var(--red)"></span> ${critical} Critical</span>
      <span class="risk-summary-item"><span class="risk-summary-dot" style="background:var(--yellow)"></span> ${watch} Watch</span>
      <span class="risk-summary-item"><span class="risk-summary-dot" style="background:var(--green)"></span> ${low} Low</span>
      <span style="margin-left:auto;font-size:11px;color:var(--text-tertiary)">${addressed}/${risks.length} addressed</span>
    `;
    section.appendChild(summary);
  } else {
    section.appendChild(h('div', { class: 'shimmer shimmer-long', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-medium' }));
  }

  return section;
}

function renderRiskCardElement(risk) {
  const card = h('div', { class: `risk-card severity-${risk.severity || 'watch'}` });
  card.innerHTML = `
    <div class="risk-card-title">${risk.title || 'Untitled Risk'}</div>
    <div class="risk-card-description">${risk.description || ''}</div>
    <div class="risk-card-scores">
      <span class="risk-score">Likelihood: <span class="risk-stars">${'\u2605'.repeat(risk.likelihood || 3)}${'\u2606'.repeat(5 - (risk.likelihood || 3))}</span></span>
      <span class="risk-score">Impact: <span class="risk-stars">${'\u2605'.repeat(risk.impact || 3)}${'\u2606'.repeat(5 - (risk.impact || 3))}</span></span>
    </div>
    ${risk.mitigation ? `<div class="risk-mitigation">${risk.mitigation}</div>` : ''}
    <div class="risk-actions">
      <button class="risk-btn ${risk.disposition === 'accept' ? 'selected accept' : ''}" data-action="accept">Accept Risk</button>
      <button class="risk-btn ${risk.disposition === 'mitigate' ? 'selected mitigate' : ''}" data-action="mitigate">Mitigate</button>
      <button class="risk-btn ${risk.disposition === 'eliminate' ? 'selected eliminate' : ''}" data-action="eliminate">Eliminate</button>
    </div>
  `;

  card.querySelectorAll('.risk-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      card.querySelectorAll('.risk-btn').forEach(b => b.classList.remove('selected', 'accept', 'mitigate', 'eliminate'));
      btn.classList.add('selected', btn.dataset.action);
      risk.disposition = btn.dataset.action;
    });
  });

  return card;
}
```

---

## Fix 9: Views (js/views/*.js)

### Problem

The app needs six view render functions, each responsible for fetching data, rendering into
the `#view-root` container, and setting up event listeners. Views are the top-level pages
the router switches between.

### Implementation: js/views/dashboard.js

```javascript
// ==========================================================================
// DASHBOARD.JS — Overview Home View
// ==========================================================================

import { getState, subscribe } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { renderApprovalCard } from '../components/approval-card.js';
import { h } from '../utils/dom.js';
import { timeAgo, compactNumber } from '../utils/format.js';

export function renderDashboard(root) {
  const container = h('div', { class: 'view-container' });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>Dashboard</h2>
      </div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="dash-refresh">Refresh</button>
      </div>
    </div>

    <div id="dash-alerts"></div>

    <div class="dash-actions">
      <button class="btn btn-primary" id="dash-new-thinktank">New Think Tank Session</button>
      <button class="btn btn-ghost" id="dash-view-kanban">View Kanban</button>
    </div>

    <div class="dash-grid" id="dash-grid">
      <div class="dash-card"><div class="dash-card-label">Active Agents</div><div class="dash-card-value" id="stat-agents">--</div><div class="dash-card-sub" id="stat-agents-sub"></div></div>
      <div class="dash-card"><div class="dash-card-label">Open Beads</div><div class="dash-card-value" id="stat-beads">--</div><div class="dash-card-sub" id="stat-beads-sub"></div></div>
      <div class="dash-card"><div class="dash-card-label">Epic Progress</div><div class="dash-card-value" id="stat-epics">--</div><div class="dash-card-sub" id="stat-epics-sub"></div></div>
      <div class="dash-card"><div class="dash-card-label">Events (24h)</div><div class="dash-card-value" id="stat-events">--</div><div class="dash-card-sub" id="stat-events-sub"></div></div>
    </div>

    <h3 style="margin: 24px 0 16px">Pending Approvals</h3>
    <div id="dash-approvals"></div>

    <h3 style="margin: 24px 0 16px">Recent Events</h3>
    <div id="dash-recent-events"></div>
  `;

  root.appendChild(container);

  // Quick actions
  container.querySelector('#dash-new-thinktank').addEventListener('click', () => {
    window.location.hash = 'thinktank';
  });
  container.querySelector('#dash-view-kanban').addEventListener('click', () => {
    window.location.hash = 'kanban';
  });
  container.querySelector('#dash-refresh').addEventListener('click', () => loadDashData());

  loadDashData();

  // Subscribe to real-time updates
  subscribe('agents', () => updateDashStats());
  subscribe('approvals', () => renderDashApprovals());
  subscribe('events', () => renderDashRecentEvents());
}

async function loadDashData() {
  try {
    const [agents, beads, epics, events] = await Promise.all([
      api.getAgents().catch(() => []),
      api.getBeads().catch(() => []),
      api.getEpics().catch(() => []),
      api.getEvents({ limit: 20 }).catch(() => []),
    ]);

    const { setState } = await import('../state.js');
    setState({ agents, beads, epics, events });
    updateDashStats();
    renderDashApprovals();
    renderDashRecentEvents();
    checkAlerts();
  } catch (err) {
    showToast(`Failed to load dashboard: ${err.message}`, 'error');
  }
}

function updateDashStats() {
  const state = getState();
  const agents = state.agents || [];
  const beads = state.beads || [];
  const epics = state.epics || [];
  const events = state.events || [];

  const active = agents.filter(a => a.status === 'running').length;
  const el = (id) => document.getElementById(id);

  if (el('stat-agents')) el('stat-agents').textContent = active;
  if (el('stat-agents-sub')) el('stat-agents-sub').textContent = `${agents.length} total`;

  const open = beads.filter(b => b.status !== 'done' && b.status !== 'closed').length;
  if (el('stat-beads')) el('stat-beads').textContent = open;
  if (el('stat-beads-sub')) el('stat-beads-sub').textContent = `${beads.length} total`;

  if (el('stat-epics')) el('stat-epics').textContent = epics.length;
  if (el('stat-events')) el('stat-events').textContent = events.length;
}

function renderDashApprovals() {
  const container = document.getElementById('dash-approvals');
  if (!container) return;
  const { approvals } = getState();
  container.innerHTML = '';
  if (!approvals || !approvals.length) {
    container.innerHTML = '<p class="caption">No pending approvals</p>';
    return;
  }
  approvals.forEach(a => container.appendChild(renderApprovalCard(a)));
}

function renderDashRecentEvents() {
  const container = document.getElementById('dash-recent-events');
  if (!container) return;
  const { events } = getState();
  if (!events || !events.length) {
    container.innerHTML = '<p class="caption">No recent events</p>';
    return;
  }
  container.innerHTML = events.slice(0, 10).map(e => `
    <div class="flex items-center gap-3" style="padding:6px 0;border-bottom:1px solid var(--border)">
      <span class="badge badge-${e.type === 'error' ? 'red' : e.type === 'approval' ? 'yellow' : 'blue'}">${e.type || 'event'}</span>
      <span style="font-size:13px;flex:1">${e.description || e.name || ''}</span>
      <span class="caption">${timeAgo(e.timestamp)}</span>
    </div>
  `).join('');
}

function checkAlerts() {
  const container = document.getElementById('dash-alerts');
  if (!container) return;
  const { agents } = getState();
  const stale = (agents || []).filter(a => {
    if (!a.lastHeartbeat) return false;
    return Date.now() - new Date(a.lastHeartbeat).getTime() > 5 * 60 * 1000;
  });
  if (stale.length > 0) {
    container.innerHTML = `
      <div class="dash-alert">
        <span class="dash-alert-icon">\u26A0</span>
        <span>${stale.length} agent(s) with stale heartbeats: ${stale.map(a => a.name).join(', ')}</span>
      </div>
    `;
  }
}
```

### Implementation: js/views/kanban.js

```javascript
// ==========================================================================
// KANBAN.JS — Kanban Board with DnD, Context Menus, Table Toggle
// ==========================================================================

import { getState, subscribe, setState } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { showContextMenu } from '../components/context-menu.js';
import { openSidePanel } from '../components/sidebar.js';
import { h } from '../utils/dom.js';
import { timeAgo, stringToColor } from '../utils/format.js';

const COLUMNS = [
  { id: 'backlog',     title: 'Backlog',      color: '#8b949e', wipLimit: 0 },
  { id: 'ready',       title: 'Ready',        color: '#58a6ff', wipLimit: 0 },
  { id: 'in_progress', title: 'In Progress',  color: '#d29922', wipLimit: 5 },
  { id: 'in_review',   title: 'In Review',    color: '#bc8cff', wipLimit: 3 },
  { id: 'blocked',     title: 'Blocked',      color: '#f85149', wipLimit: 0 },
  { id: 'done',        title: 'Done',         color: '#3fb950', wipLimit: 0 },
];

let currentViewMode = 'kanban';
let draggedCard = null;

export function renderKanban(root) {
  const container = h('div', { class: 'view-container', style: { padding: '16px' } });

  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left">
        <h2>Kanban Board</h2>
      </div>
      <div class="view-header-right">
        <div class="view-tabs">
          <button class="view-tab active" data-mode="kanban">Board</button>
          <button class="view-tab" data-mode="table">Table</button>
        </div>
      </div>
    </div>
    <div class="filter-bar" id="kanban-filters"></div>
    <div id="kanban-content"></div>
  `;

  root.appendChild(container);

  // View mode toggle
  container.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      container.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentViewMode = tab.dataset.mode;
      renderBoard();
    });
  });

  loadKanbanData();
  subscribe('beads', () => renderBoard());
}

async function loadKanbanData() {
  try {
    const data = await api.getKanban();
    if (data && data.columns) {
      // Flatten columns into beads with column info
      const beads = [];
      for (const [colId, col] of Object.entries(data.columns)) {
        (col.beads || []).forEach(b => beads.push({ ...b, column: colId }));
      }
      setState({ beads });
    }
  } catch (err) {
    showToast(`Failed to load Kanban: ${err.message}`, 'error');
  }
  renderBoard();
}

function renderBoard() {
  const content = document.getElementById('kanban-content');
  if (!content) return;

  if (currentViewMode === 'table') {
    renderTableView(content);
  } else {
    renderKanbanBoard(content);
  }
}

function renderKanbanBoard(content) {
  const { beads } = getState();
  content.innerHTML = '';

  const board = h('div', { class: 'kanban-board' });

  // Find largest non-done column for bottleneck detection
  const columnCounts = {};
  COLUMNS.forEach(c => { columnCounts[c.id] = 0; });
  (beads || []).forEach(b => { if (columnCounts[b.column] !== undefined) columnCounts[b.column]++; });
  let maxNonDone = 0;
  let bottleneckCol = null;
  COLUMNS.forEach(c => {
    if (c.id !== 'done' && c.id !== 'backlog' && columnCounts[c.id] > maxNonDone) {
      maxNonDone = columnCounts[c.id];
      bottleneckCol = c.id;
    }
  });

  COLUMNS.forEach(col => {
    const colBeads = (beads || []).filter(b => b.column === col.id);
    const isBottleneck = col.id === bottleneckCol && maxNonDone > 2;
    const overWip = col.wipLimit > 0 && colBeads.length > col.wipLimit;

    const column = h('div', {
      class: `kanban-column ${isBottleneck ? 'bottleneck' : ''}`,
      dataset: { status: col.id }
    });

    column.innerHTML = `
      <div class="kanban-column-header">
        <span class="kanban-column-dot" style="background:${col.color}"></span>
        <span class="kanban-column-title">${col.title}</span>
        <span class="kanban-column-count">${colBeads.length}</span>
        ${col.wipLimit ? `<span class="kanban-column-wip ${overWip ? 'over-limit' : ''}">WIP ${colBeads.length}/${col.wipLimit}</span>` : ''}
      </div>
    `;

    const cardsContainer = h('div', { class: 'kanban-cards' });
    colBeads.forEach(bead => {
      cardsContainer.appendChild(renderKanbanCard(bead));
    });
    column.appendChild(cardsContainer);
    board.appendChild(column);

    // Drop zone handlers
    column.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      column.classList.add('drag-over');

      const afterEl = getDragAfterElement(cardsContainer, e.clientY);
      const placeholder = getOrCreatePlaceholder();
      if (afterEl) {
        cardsContainer.insertBefore(placeholder, afterEl);
      } else {
        cardsContainer.appendChild(placeholder);
      }
    });

    column.addEventListener('dragleave', (e) => {
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

      cardsContainer.insertBefore(draggedCard, placeholder);
      placeholder.remove();

      const beadId = draggedCard.dataset.id;
      const newCol = col.id;
      moveBeadOptimistic(beadId, newCol);
    });
  });

  content.appendChild(board);
}

function renderKanbanCard(bead) {
  const card = h('div', {
    class: 'kanban-card',
    dataset: { id: bead.id, priority: bead.priority ?? 3 },
    draggable: 'true'
  });

  const agentColor = stringToColor(bead.assignee);

  card.innerHTML = `
    <div class="kanban-card-title">${bead.title || 'Untitled'}</div>
    <div class="kanban-card-meta">
      ${bead.assignee ? `<span class="kanban-card-agent" style="background:${agentColor}">${bead.assignee}</span>` : ''}
      <span class="kanban-card-type">${bead.type || 'task'}</span>
      ${bead.dep_count ? `<span class="kanban-card-deps">\u{1F517} ${bead.dep_count}</span>` : ''}
      <span class="kanban-card-time">${timeAgo(bead.created_at)}</span>
    </div>
    <div class="kanban-card-details">
      ${bead.epic ? `<div class="kanban-card-detail-row"><span class="kanban-card-detail-label">Epic</span><span>${bead.epic}</span></div>` : ''}
      ${bead.notes ? `<div class="kanban-card-detail-row"><span class="kanban-card-detail-label">Notes</span><span>${bead.notes}</span></div>` : ''}
      <div class="kanban-card-detail-row"><span class="kanban-card-detail-label">ID</span><span class="mono">${bead.id}</span></div>
    </div>
  `;

  // Drag handlers
  card.addEventListener('dragstart', (e) => {
    draggedCard = card;
    card.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', bead.id);
    requestAnimationFrame(() => { card.style.opacity = '0.3'; });
  });

  card.addEventListener('dragend', () => {
    card.classList.remove('dragging');
    card.style.opacity = '1';
    draggedCard = null;
    document.querySelectorAll('.drop-placeholder').forEach(p => p.remove());
    document.querySelectorAll('.drag-over').forEach(c => c.classList.remove('drag-over'));
  });

  // Click to open side panel
  card.addEventListener('click', (e) => {
    if (e.defaultPrevented) return;
    openBeadDetail(bead);
  });

  // Right-click context menu
  card.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    showContextMenu(e.clientX, e.clientY, [
      { label: 'Open Details', icon: '\u{1F4C4}', action: () => openBeadDetail(bead) },
      { label: 'Copy ID', icon: '\u{1F4CB}', action: () => { navigator.clipboard.writeText(bead.id); showToast('Copied'); } },
      { type: 'separator' },
      ...COLUMNS.filter(c => c.id !== bead.column).map(c => ({
        label: `Move to ${c.title}`, action: () => moveBeadOptimistic(bead.id, c.id)
      })),
    ]);
  });

  return card;
}

function renderTableView(content) {
  const { beads } = getState();
  content.innerHTML = `
    <table class="kanban-table">
      <thead><tr>
        <th style="width:4px"></th>
        <th>Title</th>
        <th>Status</th>
        <th>Agent</th>
        <th>Priority</th>
        <th>Type</th>
        <th>Created</th>
      </tr></thead>
      <tbody id="kanban-table-body"></tbody>
    </table>
  `;

  const tbody = content.querySelector('#kanban-table-body');
  (beads || []).forEach(b => {
    const col = COLUMNS.find(c => c.id === b.column);
    const row = document.createElement('tr');
    row.innerHTML = `
      <td class="priority-cell" style="background:var(--priority-${b.priority ?? 3})"></td>
      <td>${b.title || 'Untitled'}</td>
      <td><span class="badge badge-blue">${col ? col.title : b.column}</span></td>
      <td>${b.assignee || '--'}</td>
      <td>P${b.priority ?? '?'}</td>
      <td>${b.type || 'task'}</td>
      <td class="caption">${timeAgo(b.created_at)}</td>
    `;
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => openBeadDetail(b));
    tbody.appendChild(row);
  });
}

async function moveBeadOptimistic(beadId, newColumn) {
  try {
    await api.moveBead(beadId, newColumn);
    const { beads } = getState();
    setState({
      beads: beads.map(b => b.id === beadId ? { ...b, column: newColumn } : b)
    });
    showToast(`Moved to ${newColumn.replace('_', ' ')}`, 'success');
  } catch (err) {
    showToast(`Move failed: ${err.message}`, 'error');
    loadKanbanData(); // Reload to fix state
  }
}

function openBeadDetail(bead) {
  openSidePanel(`
    <h3>${bead.title || 'Untitled'}</h3>
    <div style="margin-top:16px">
      <div class="speckit-field"><div class="speckit-field-label">ID</div><div class="mono">${bead.id}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Status</div><div>${bead.column || bead.status}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Agent</div><div>${bead.assignee || 'Unassigned'}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Priority</div><div>P${bead.priority ?? '?'}</div></div>
      <div class="speckit-field"><div class="speckit-field-label">Type</div><div>${bead.type || 'task'}</div></div>
      ${bead.epic ? `<div class="speckit-field"><div class="speckit-field-label">Epic</div><div>${bead.epic}</div></div>` : ''}
      ${bead.notes ? `<div class="speckit-field"><div class="speckit-field-label">Notes</div><div>${bead.notes}</div></div>` : ''}
      <div class="speckit-field"><div class="speckit-field-label">Created</div><div>${bead.created_at || '--'}</div></div>
    </div>
    <div style="margin-top:24px">
      <h4>Add Comment</h4>
      <textarea id="bead-comment-input" placeholder="Type a comment..." style="margin-top:8px"></textarea>
      <button class="btn btn-primary btn-sm" id="bead-comment-submit" style="margin-top:8px">Comment</button>
    </div>
  `);

  const submitBtn = document.getElementById('bead-comment-submit');
  if (submitBtn) {
    submitBtn.addEventListener('click', async () => {
      const input = document.getElementById('bead-comment-input');
      const text = input?.value?.trim();
      if (!text) return;
      try {
        await api.commentBead(bead.id, text);
        input.value = '';
        showToast('Comment added', 'success');
      } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
      }
    });
  }
}

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
  let ph = document.querySelector('.drop-placeholder');
  if (!ph) {
    ph = document.createElement('div');
    ph.className = 'drop-placeholder';
  }
  return ph;
}
```

### Implementation: js/views/thinktank.js

```javascript
// ==========================================================================
// THINKTANK.JS — Think Tank Split-View (Chat + Spec-Kit)
// ==========================================================================

import { getState, setState, subscribe } from '../state.js';
import { api, connectThinktankWs, thinktankWs } from '../api.js';
import { showToast } from '../components/toast.js';
import { renderPhaseStepper } from '../components/phase-stepper.js';
import { renderChatMessage, renderTypingIndicator, renderChatInput } from '../components/chat.js';
import { renderSpecKit } from '../components/spec-kit.js';
import { h } from '../utils/dom.js';

export function renderThinkTank(root) {
  const state = getState();
  const tt = state.thinktank;

  const container = h('div', { class: 'thinktank' });

  // Left: Chat Panel
  const chatPanel = h('div', { class: 'thinktank-chat', dataset: { phase: getPhaseId(tt.phase) } });

  // Phase stepper
  chatPanel.appendChild(renderPhaseStepper(tt.phase));

  // Messages area
  const messagesArea = h('div', { class: 'chat-messages', id: 'tt-messages' });
  renderMessages(messagesArea, tt.messages);
  chatPanel.appendChild(messagesArea);

  // Chat input
  const chatInput = renderChatInput(async (text, images) => {
    // Add human message to state
    const msg = { role: 'human', content: text, images: [], streaming: false };

    // Upload images if any
    if (images && images.length) {
      for (const img of images) {
        try {
          const result = await api.uploadAttachment(img);
          msg.images.push(result.url);
        } catch (err) {
          showToast(`Image upload failed: ${err.message}`, 'error');
        }
      }
    }

    const newMessages = [...getState().thinktank.messages, msg];
    setState({ thinktank: { ...getState().thinktank, messages: newMessages } });

    // Add placeholder AI message
    const aiMsg = { role: 'ai', content: '', streaming: true, chips: [] };
    setState({
      thinktank: {
        ...getState().thinktank,
        messages: [...getState().thinktank.messages, aiMsg]
      }
    });

    // Send via WebSocket or REST
    if (thinktankWs) {
      thinktankWs.send({ type: 'message', content: text, images: msg.images });
    } else {
      try {
        const sessionId = getState().thinktank.sessionId;
        if (sessionId) {
          await api.sendMessage(sessionId, { content: text, images: msg.images });
        }
      } catch (err) {
        showToast(`Send failed: ${err.message}`, 'error');
      }
    }
  });
  chatPanel.appendChild(chatInput);

  // Right: Spec-Kit Panel
  const specPanel = h('div', { class: 'thinktank-speckit' });
  const specHeader = h('div', { class: 'speckit-header' });
  specHeader.innerHTML = '<span class="speckit-title">Spec-Kit</span>';
  specPanel.appendChild(specHeader);

  specPanel.appendChild(renderSpecKit(tt, (key, val) => {
    const sk = { ...getState().thinktank.specKit };
    sk[key] = val;
    setState({ thinktank: { ...getState().thinktank, specKit: sk } });
    showToast('Spec updated', 'info');
  }));

  // Approval gate (Phase 4 only)
  if (tt.phase >= 4) {
    const gate = h('div', { class: 'approval-gate' });
    const approveBtn = h('button', {
      class: 'approval-gate-btn',
      onClick: async () => {
        approveBtn.textContent = 'Building... You\'ll be notified when ready';
        approveBtn.classList.add('approved');
        approveBtn.style.animation = 'approval-burst 0.8s ease forwards';
        try {
          const sessionId = getState().thinktank.sessionId;
          if (sessionId) await api.approveSpec(sessionId);
          showToast('Spec approved -- build started!', 'success');
        } catch (err) {
          showToast(`Approval failed: ${err.message}`, 'error');
          approveBtn.textContent = 'Approve & Start Building \u2192';
          approveBtn.classList.remove('approved');
        }
      }
    });
    approveBtn.textContent = 'Approve & Start Building \u2192';

    const escapes = h('div', { class: 'approval-gate-escape' });
    escapes.innerHTML = `
      <a href="#" onclick="event.preventDefault()">Go Back to Scope</a>
      <a href="#" onclick="event.preventDefault()">Save as Draft</a>
    `;
    const pauseNote = h('p', { style: { textAlign: 'center', fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '8px' } });
    pauseNote.textContent = 'You can pause the build at any time.';

    gate.appendChild(approveBtn);
    gate.appendChild(escapes);
    gate.appendChild(pauseNote);
    specPanel.appendChild(gate);
  }

  container.appendChild(chatPanel);
  container.appendChild(specPanel);
  root.appendChild(container);

  // Initialize session if needed
  initThinktankSession();

  // Subscribe to thinktank state changes
  subscribe('thinktank', (tt) => {
    // Update messages
    const msgArea = document.getElementById('tt-messages');
    if (msgArea) renderMessages(msgArea, tt.messages);

    // Update phase stepper
    const chatEl = document.querySelector('.thinktank-chat');
    if (chatEl) {
      chatEl.dataset.phase = getPhaseId(tt.phase);
      const stepper = chatEl.querySelector('.phase-stepper');
      if (stepper) stepper.replaceWith(renderPhaseStepper(tt.phase));
    }
  });

  // D/A/G keyboard shortcuts
  const dagHandler = (e) => {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const lastMsg = getState().thinktank.messages.filter(m => m.role === 'ai' && m.chips?.length).pop();
    if (!lastMsg || !lastMsg.chips) return;

    switch (e.key.toUpperCase()) {
      case 'D': if (lastMsg.chips[0]?.action) lastMsg.chips[0].action(); break;
      case 'A': if (lastMsg.chips[1]?.action) lastMsg.chips[1].action(); break;
      case 'G': if (lastMsg.chips[2]?.action) lastMsg.chips[2].action(); break;
    }
  };
  document.addEventListener('keydown', dagHandler);
}

async function initThinktankSession() {
  const state = getState();
  if (!state.thinktank.sessionId) {
    try {
      const session = await api.createSession({ name: `Session ${Date.now()}` });
      setState({
        thinktank: {
          ...state.thinktank,
          sessionId: session.id,
          phase: 1,
          messages: [{
            role: 'ai',
            content: 'Welcome to the Think Tank. Tell me what you\'re trying to build. What problem are you solving, and who is it for?',
            streaming: false,
            chips: [
              { label: 'Describe the problem', icon: '\u{1F50D}', action: () => {} },
              { label: 'Show a reference', icon: '\u{1F4CE}', action: () => {} },
              { label: 'Start from template', icon: '\u{1F4CB}', action: () => {} },
            ]
          }]
        }
      });
      connectThinktankWs(session.id);
    } catch (err) {
      showToast(`Failed to create session: ${err.message}`, 'error');
    }
  }
}

function renderMessages(container, messages) {
  container.innerHTML = '';
  (messages || []).forEach(msg => {
    const el = renderChatMessage(msg);
    if (el instanceof DocumentFragment) {
      container.appendChild(el);
    } else {
      container.appendChild(el);
    }
  });
  // Auto-scroll to bottom
  container.scrollTop = container.scrollHeight;
}

function getPhaseId(num) {
  return ['listen', 'explore', 'scope', 'confirm'][num - 1] || 'listen';
}
```

### Implementation: js/views/timeline.js

```javascript
// ==========================================================================
// TIMELINE.JS — AgentOps-Style Waterfall Timeline
// ==========================================================================

import { getState, subscribe, setState } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo, formatDuration } from '../utils/format.js';

export function renderTimeline(root) {
  const container = h('div', { class: 'view-container', style: { padding: '16px' } });
  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left"><h2>Timeline</h2></div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="tl-refresh">Refresh</button>
      </div>
    </div>
    <div class="filter-bar" id="tl-filters">
      <button class="filter-chip active" data-type="all">All</button>
      <button class="filter-chip" data-type="agent-spawn">Agents</button>
      <button class="filter-chip" data-type="tool-call">Tools</button>
      <button class="filter-chip" data-type="bead">Beads</button>
      <button class="filter-chip" data-type="error">Errors</button>
    </div>
    <div class="timeline-container">
      <div class="timeline-list" id="tl-list">
        <div class="timeline-header-row">
          <span>Event</span><span>Type</span><span>Duration</span><span>Time</span>
        </div>
        <div id="tl-events"></div>
      </div>
      <div class="timeline-detail" id="tl-detail">
        <div class="timeline-detail-empty">Select an event to view details</div>
      </div>
    </div>
  `;
  root.appendChild(container);

  // Filter handlers
  container.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      renderEventList(chip.dataset.type);
    });
  });

  container.querySelector('#tl-refresh').addEventListener('click', loadTimelineData);

  loadTimelineData();
  subscribe('events', () => renderEventList());
}

async function loadTimelineData() {
  try {
    const events = await api.getEvents({ limit: 200 });
    setState({ events: events || [] });
    renderEventList();
  } catch (err) {
    showToast(`Failed to load events: ${err.message}`, 'error');
  }
}

function renderEventList(filterType = 'all') {
  const container = document.getElementById('tl-events');
  if (!container) return;

  const { events } = getState();
  let filtered = events || [];
  if (filterType !== 'all') {
    filtered = filtered.filter(e => e.type === filterType);
  }

  // Calculate timeline boundaries for waterfall positioning
  const times = filtered.map(e => new Date(e.timestamp || 0).getTime()).filter(t => t > 0);
  const minTime = Math.min(...times, Date.now());
  const maxTime = Math.max(...times, Date.now());
  const range = maxTime - minTime || 1;

  container.innerHTML = filtered.map((e, i) => {
    const startPct = ((new Date(e.timestamp || 0).getTime() - minTime) / range) * 100;
    const widthPct = Math.max(2, ((e.duration || 100) / range) * 100);

    return `
      <div class="timeline-event" data-index="${i}">
        <span class="timeline-event-name">
          <span class="status-dot status-dot-${e.type === 'error' ? 'error' : 'running'}"></span>
          ${e.name || e.description || 'Event'}
        </span>
        <span class="timeline-event-type">
          <span class="badge badge-${e.type === 'error' ? 'red' : e.type === 'agent-spawn' ? 'purple' : 'blue'}">${e.type || 'event'}</span>
        </span>
        <div class="timeline-bar-container">
          <div class="timeline-bar type-${e.type || 'status'}" style="left:${startPct}%;width:${widthPct}%"></div>
        </div>
        <span class="timeline-event-duration">${formatDuration(e.duration)}</span>
      </div>
    `;
  }).join('');

  // Click handlers
  container.querySelectorAll('.timeline-event').forEach(row => {
    row.addEventListener('click', () => {
      container.querySelectorAll('.timeline-event').forEach(r => r.classList.remove('selected'));
      row.classList.add('selected');
      const idx = parseInt(row.dataset.index);
      showEventDetail(filtered[idx]);
    });
  });
}

function showEventDetail(event) {
  const detail = document.getElementById('tl-detail');
  if (!detail || !event) return;

  detail.innerHTML = `
    <div class="timeline-detail-title">${event.name || event.description || 'Event'}</div>

    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Type</div>
      <span class="badge badge-${event.type === 'error' ? 'red' : 'blue'}">${event.type}</span>
    </div>

    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Timestamp</div>
      <div class="timeline-detail-value">${event.timestamp || '--'} (${timeAgo(event.timestamp)})</div>
    </div>

    ${event.duration ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Duration</div>
      <div class="timeline-detail-value">${formatDuration(event.duration)}</div>
    </div>` : ''}

    ${event.agentName ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Agent</div>
      <div class="timeline-detail-value">${event.agentName}</div>
    </div>` : ''}

    ${event.data ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Data</div>
      <pre class="timeline-detail-code">${JSON.stringify(event.data, null, 2)}</pre>
    </div>` : ''}

    ${event.error ? `
    <div class="timeline-detail-section">
      <div class="timeline-detail-label">Error</div>
      <pre class="timeline-detail-code" style="color:var(--red)">${event.error}</pre>
    </div>` : ''}
  `;
}
```

### Implementation: js/views/agents.js

```javascript
// ==========================================================================
// AGENTS.JS — Agent Detail View
// ==========================================================================

import { getState, subscribe } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';
import { timeAgo, stringToColor } from '../utils/format.js';

export function renderAgents(root) {
  const container = h('div', { class: 'view-container' });
  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left"><h2>Agents</h2></div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="agents-refresh">Refresh</button>
      </div>
    </div>
    <div class="dash-grid" id="agents-grid"></div>
  `;
  root.appendChild(container);

  container.querySelector('#agents-refresh').addEventListener('click', loadAgents);
  loadAgents();
  subscribe('agents', () => renderAgentGrid());
}

async function loadAgents() {
  try {
    const agents = await api.getAgents();
    const { setState } = await import('../state.js');
    setState({ agents: agents || [] });
    renderAgentGrid();
  } catch (err) {
    showToast(`Failed to load agents: ${err.message}`, 'error');
  }
}

function renderAgentGrid() {
  const grid = document.getElementById('agents-grid');
  if (!grid) return;

  const { agents } = getState();
  grid.innerHTML = (agents || []).map(a => {
    const statusClass = a.status === 'running' ? 'running' : a.status === 'idle' ? 'idle' : a.status === 'error' ? 'error' : 'dead';
    return `
      <div class="dash-card" style="cursor:pointer" data-agent-id="${a.id}">
        <div class="flex items-center gap-3" style="margin-bottom:12px">
          <span class="status-dot status-dot-${statusClass}"></span>
          <span style="font-weight:600;color:var(--text-strong)">${a.name || a.id}</span>
          <span class="badge badge-${statusClass === 'running' ? 'green' : statusClass === 'error' ? 'red' : 'gray'}" style="margin-left:auto">
            ${a.status || 'unknown'}
          </span>
        </div>
        <div style="font-size:12px;color:var(--text-secondary)">
          ${a.level ? `<div>Level: ${a.level}</div>` : ''}
          ${a.currentBead ? `<div>Current: ${a.currentBead}</div>` : ''}
          ${a.worktree ? `<div class="mono" style="font-size:11px">${a.worktree}</div>` : ''}
          ${a.lastHeartbeat ? `<div>Heartbeat: ${timeAgo(a.lastHeartbeat)}</div>` : ''}
        </div>
        <div class="flex gap-2" style="margin-top:12px">
          <button class="btn btn-danger btn-sm kill-btn" data-id="${a.id}">Kill</button>
          <button class="btn btn-ghost btn-sm retry-btn" data-id="${a.id}">Retry</button>
        </div>
      </div>
    `;
  }).join('') || '<p class="caption">No agents registered</p>';

  // Action handlers
  grid.querySelectorAll('.kill-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('Kill this agent?')) return;
      try {
        await api.killAgent(btn.dataset.id);
        showToast('Agent killed', 'warning');
        loadAgents();
      } catch (err) { showToast(`Failed: ${err.message}`, 'error'); }
    });
  });

  grid.querySelectorAll('.retry-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      try {
        await api.retryAgent(btn.dataset.id);
        showToast('Agent retrying', 'success');
        loadAgents();
      } catch (err) { showToast(`Failed: ${err.message}`, 'error'); }
    });
  });
}
```

### Implementation: js/views/epics.js

```javascript
// ==========================================================================
// EPICS.JS — Epic Progress View
// ==========================================================================

import { getState, subscribe } from '../state.js';
import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { h } from '../utils/dom.js';

export function renderEpics(root) {
  const container = h('div', { class: 'view-container' });
  container.innerHTML = `
    <div class="view-header">
      <div class="view-header-left"><h2>Epics</h2></div>
      <div class="view-header-right">
        <button class="btn btn-ghost btn-sm" id="epics-refresh">Refresh</button>
      </div>
    </div>
    <div id="epics-list"></div>
  `;
  root.appendChild(container);

  container.querySelector('#epics-refresh').addEventListener('click', loadEpics);
  loadEpics();
  subscribe('epics', () => renderEpicsList());
}

async function loadEpics() {
  try {
    const epics = await api.getEpics();
    const { setState } = await import('../state.js');
    setState({ epics: epics || [] });
    renderEpicsList();
  } catch (err) {
    showToast(`Failed to load epics: ${err.message}`, 'error');
  }
}

function renderEpicsList() {
  const list = document.getElementById('epics-list');
  if (!list) return;
  const { epics } = getState();

  list.innerHTML = (epics || []).map(e => {
    const total = (e.done || 0) + (e.wip || 0) + (e.blocked || 0) + (e.remaining || 0);
    const donePct = total ? ((e.done || 0) / total * 100) : 0;
    const wipPct = total ? ((e.wip || 0) / total * 100) : 0;
    const blockedPct = total ? ((e.blocked || 0) / total * 100) : 0;

    return `
      <div class="epic-card">
        <div class="epic-title">${e.name || e.id}</div>
        <div class="epic-progress-bar">
          <div class="epic-progress-done" style="width:${donePct}%"></div>
          <div class="epic-progress-wip" style="width:${wipPct}%"></div>
          <div class="epic-progress-blocked" style="width:${blockedPct}%"></div>
        </div>
        <div class="epic-meta">
          <span style="color:var(--green)">${e.done || 0} done</span>
          <span style="color:var(--yellow)">${e.wip || 0} WIP</span>
          <span style="color:var(--red)">${e.blocked || 0} blocked</span>
          <span>${e.remaining || 0} remaining</span>
          <span style="margin-left:auto">${total} total beads</span>
        </div>
      </div>
    `;
  }).join('') || '<p class="caption">No epics defined</p>';
}
```

---

## Fix 10: App Entry Point (js/app.js)

### Problem

All the modules exist in isolation. The app needs an entry point that wires everything
together: initializes the state store, connects WebSockets, registers routes, sets up the
command palette with commands, binds global keyboard shortcuts, and renders the initial view.

### Solution

`app.js` is the orchestrator. It imports all modules and initializes them in the correct order.

### Implementation: js/app.js

```javascript
// ==========================================================================
// APP.JS — Main Entry Point
// Wires state, router, WebSocket, command palette, keyboard shortcuts
// ==========================================================================

import { getState, setState } from './state.js';
import { api, connectWebSockets } from './api.js';
import { initRouter, registerRoute, navigate } from './router.js';
import { getCommandPalette } from './components/command-palette.js';
import { showToast } from './components/toast.js';

// Views
import { renderDashboard } from './views/dashboard.js';
import { renderKanban } from './views/kanban.js';
import { renderThinkTank } from './views/thinktank.js';
import { renderTimeline } from './views/timeline.js';
import { renderAgents } from './views/agents.js';
import { renderEpics } from './views/epics.js';

// ── Initialize ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // 1. Register routes
  registerRoute('dashboard', renderDashboard);
  registerRoute('kanban', renderKanban);
  registerRoute('thinktank', renderThinkTank);
  registerRoute('timeline', renderTimeline);
  registerRoute('agents', renderAgents);
  registerRoute('epics', renderEpics);

  // 2. Initialize router
  initRouter();

  // 3. Connect WebSocket for real-time updates
  connectWebSockets();

  // 4. Set up command palette
  setupCommandPalette();

  // 5. Global keyboard shortcuts
  setupKeyboardShortcuts();

  // 6. Mobile menu toggle
  setupMobileMenu();

  // 7. Cmd+K trigger button
  const cmdkTrigger = document.getElementById('cmdk-trigger');
  if (cmdkTrigger) {
    cmdkTrigger.addEventListener('click', () => getCommandPalette().open());
  }

  console.log('Command Center initialized');
});

// ── Command Palette Setup ──────────────────────────────────────────────────

function setupCommandPalette() {
  const palette = getCommandPalette();

  palette.register([
    // Navigation
    { name: 'Go to Dashboard', description: 'Overview and stats', category: 'Navigation',
      shortcut: 'G D', icon: '\u25A1', action: () => { window.location.hash = 'dashboard'; } },
    { name: 'Go to Kanban Board', description: 'Drag-and-drop task board', category: 'Navigation',
      shortcut: 'G K', icon: '\u25A6', action: () => { window.location.hash = 'kanban'; } },
    { name: 'Go to Think Tank', description: 'Brainstorm with AI', category: 'Navigation',
      shortcut: 'G T', icon: '\u2605', action: () => { window.location.hash = 'thinktank'; } },
    { name: 'Go to Timeline', description: 'Event waterfall', category: 'Navigation',
      shortcut: 'G L', icon: '\u2192', action: () => { window.location.hash = 'timeline'; } },
    { name: 'Go to Agents', description: 'Agent status and control', category: 'Navigation',
      shortcut: 'G A', icon: '\u2699', action: () => { window.location.hash = 'agents'; } },
    { name: 'Go to Epics', description: 'Epic progress tracking', category: 'Navigation',
      shortcut: 'G E', icon: '\u2630', action: () => { window.location.hash = 'epics'; } },

    // Actions
    { name: 'New Think Tank Session', description: 'Start brainstorming', category: 'Actions',
      shortcut: 'N', icon: '\u2795', action: () => {
        setState({ thinktank: { ...getState().thinktank, sessionId: null, messages: [], specKit: {}, risks: [], phase: 1 } });
        window.location.hash = 'thinktank';
      }
    },
    { name: 'Refresh Data', description: 'Reload all data from server', category: 'Actions',
      shortcut: 'R', icon: '\u21BB', action: async () => {
        showToast('Refreshing...', 'info', 2000);
        try {
          const [agents, beads, epics] = await Promise.all([
            api.getAgents().catch(() => []),
            api.getBeads().catch(() => []),
            api.getEpics().catch(() => []),
          ]);
          setState({ agents, beads, epics });
          navigate(window.location.hash);
          showToast('Data refreshed', 'success');
        } catch (err) {
          showToast(`Refresh failed: ${err.message}`, 'error');
        }
      }
    },

    // Agent Actions
    { name: 'Kill All Agents', description: 'Emergency stop all running agents', category: 'Agent',
      icon: '\u26D4', action: async () => {
        if (!confirm('Kill ALL running agents?')) return;
        const { agents } = getState();
        const running = agents.filter(a => a.status === 'running');
        for (const a of running) {
          try { await api.killAgent(a.id); } catch {}
        }
        showToast(`Killed ${running.length} agents`, 'warning');
      }
    },
  ]);
}

// ── Global Keyboard Shortcuts ──────────────────────────────────────────────

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Skip if typing in an input
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    switch (e.key) {
      case '?':
        showToast('Keyboard: Cmd+K (palette), 1-6 (views), R (refresh), N (new session)', 'info', 6000);
        break;
      case '1': window.location.hash = 'dashboard'; break;
      case '2': window.location.hash = 'kanban'; break;
      case '3': window.location.hash = 'thinktank'; break;
      case '4': window.location.hash = 'timeline'; break;
      case '5': window.location.hash = 'agents'; break;
      case '6': window.location.hash = 'epics'; break;
      case 'r':
      case 'R':
        getCommandPalette().commands.find(c => c.name === 'Refresh Data')?.action();
        break;
    }
  });
}

// ── Mobile Menu ────────────────────────────────────────────────────────────

function setupMobileMenu() {
  const menuBtn = document.getElementById('mobile-menu-btn');
  const nav = document.getElementById('nav');

  // Show menu button on mobile
  const mql = window.matchMedia('(max-width: 768px)');
  function handleMobile(e) {
    if (menuBtn) menuBtn.style.display = e.matches ? 'flex' : 'none';
  }
  mql.addEventListener('change', handleMobile);
  handleMobile(mql);

  if (menuBtn && nav) {
    menuBtn.addEventListener('click', () => {
      nav.classList.toggle('mobile-open');
    });
    // Close nav when a nav item is clicked on mobile
    nav.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => {
        if (mql.matches) nav.classList.remove('mobile-open');
      });
    });
  }
}
```

---

## Fix 11: SVG Icons (assets/icons.svg)

### Problem

The app uses text-based unicode icons inline for simplicity, but having a proper SVG sprite
sheet allows for more polished icons where needed. This is a minimal sprite with the most
commonly used icons.

### Implementation: assets/icons.svg

```svg
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">

  <symbol id="icon-check" viewBox="0 0 16 16">
    <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" fill="currentColor"/>
  </symbol>

  <symbol id="icon-x" viewBox="0 0 16 16">
    <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" fill="currentColor"/>
  </symbol>

  <symbol id="icon-search" viewBox="0 0 16 16">
    <path d="M11.5 7a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zm-.82 4.74a6 6 0 111.06-1.06l3.04 3.04a.75.75 0 11-1.06 1.06l-3.04-3.04z" fill="currentColor"/>
  </symbol>

  <symbol id="icon-arrow-right" viewBox="0 0 16 16">
    <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" fill="currentColor"/>
  </symbol>

  <symbol id="icon-alert" viewBox="0 0 16 16">
    <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM7.25 5a.75.75 0 011.5 0v3a.75.75 0 01-1.5 0V5zm.75 6.5a1 1 0 100-2 1 1 0 000 2z" fill="currentColor"/>
  </symbol>

  <symbol id="icon-play" viewBox="0 0 16 16">
    <path d="M4 2.5v11a.5.5 0 00.757.429l9-5.5a.5.5 0 000-.858l-9-5.5A.5.5 0 004 2.5z" fill="currentColor"/>
  </symbol>

  <symbol id="icon-stop" viewBox="0 0 16 16">
    <rect x="3" y="3" width="10" height="10" rx="1" fill="currentColor"/>
  </symbol>

</svg>
```

---

## File Ownership

| File | Owner | Modification Type |
|------|-------|-------------------|
| `.claude/command-center/frontend/index.html` | 03i (this spec) | CREATE |
| `.claude/command-center/frontend/css/theme.css` | 03i | CREATE |
| `.claude/command-center/frontend/css/layout.css` | 03i | CREATE |
| `.claude/command-center/frontend/css/kanban.css` | 03i | CREATE |
| `.claude/command-center/frontend/css/thinktank.css` | 03i | CREATE |
| `.claude/command-center/frontend/css/timeline.css` | 03i | CREATE |
| `.claude/command-center/frontend/css/components.css` | 03i | CREATE |
| `.claude/command-center/frontend/css/animations.css` | 03i | CREATE |
| `.claude/command-center/frontend/js/app.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/state.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/api.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/router.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/views/dashboard.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/views/kanban.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/views/thinktank.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/views/timeline.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/views/agents.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/views/epics.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/command-palette.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/sidebar.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/toast.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/clipboard.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/approval-card.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/phase-stepper.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/spec-kit.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/chat.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/components/context-menu.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/utils/dom.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/utils/format.js` | 03i | CREATE |
| `.claude/command-center/frontend/js/utils/fuzzy.js` | 03i | CREATE |
| `.claude/command-center/frontend/assets/icons.svg` | 03i | CREATE |

---

## Success Criteria

- [ ] All 31 files created under `.claude/command-center/frontend/`
- [ ] `index.html` opens in browser and shows the app shell (nav sidebar, topbar, main area)
- [ ] Hash routing works: `#dashboard`, `#kanban`, `#thinktank`, `#timeline`, `#agents`, `#epics`
- [ ] CSS custom properties in `theme.css` provide consistent dark theme across all views
- [ ] Responsive layout: sidebar collapses at 1024px, becomes drawer at 768px
- [ ] Command palette opens with Cmd+K, fuzzy searches across all commands, arrow key navigation, Enter to execute
- [ ] Single-key shortcuts work: 1-6 for views, R for refresh, ? for help
- [ ] Toast notifications appear bottom-right, auto-dismiss after 4s, stack with 8px gap
- [ ] Dashboard view shows summary cards, approval list, recent events, alert banners
- [ ] Kanban board renders 6 columns with cards showing priority stripe, agent badge, title
- [ ] Kanban drag-and-drop moves cards between columns with placeholder animation
- [ ] Kanban table view toggle renders same data in tabular format
- [ ] Right-click context menu on Kanban cards shows contextual actions
- [ ] Side panel slides in from right (520px) when clicking a Kanban card
- [ ] Think Tank split-view renders chat (55%) and spec-kit (45%) side by side
- [ ] Phase stepper shows 4 phases with completed/active/upcoming visual states
- [ ] Phase stepper connecting lines animate (gradient flow for active, solid for completed, dashed for upcoming)
- [ ] D/A/G chips appear below AI messages with staggered fade-in animation
- [ ] D/A/G keyboard shortcuts (D, A, G keys) work when chat input is not focused
- [ ] Spec-kit sections unlock progressively: Brief (Phase 1), Requirements/Constraints (Phase 2), Pre-mortem (Phase 3), Execution (Phase 4)
- [ ] Shimmer placeholders show for unfilled spec-kit sections
- [ ] Risk cards in pre-mortem have red/amber/green severity borders
- [ ] Accept/Mitigate/Eliminate buttons on risk cards toggle visual state
- [ ] Risk summary bar shows counts by severity
- [ ] Approval gate button is full-width emerald, text "Approve & Start Building ->"
- [ ] No double-confirm on approval -- Phase 4 IS the confirmation
- [ ] "Go Back" and "Save as Draft" escape hatches visible below approval button
- [ ] Chat input supports Cmd+V paste-to-upload with inline thumbnail preview
- [ ] Timeline view shows waterfall bars with event type color coding
- [ ] Timeline click selects event and shows detail in right panel
- [ ] Agent view shows agent cards with status dots, heartbeat age, Kill/Retry buttons
- [ ] Epic view shows progress bars with done/WIP/blocked segments
- [ ] WebSocket auto-reconnects with exponential backoff (1s, 2s, 4s... up to 30s)
- [ ] WebSocket status indicator in nav footer shows green/red dot
- [ ] All animations use 200-300ms transitions with CSS variables
- [ ] Glassmorphism blur on command palette and modal overlays
- [ ] No build step required -- all files served directly by FastAPI static mount

## Verification

### Test 1: Static file serving

```bash
# On India machine, serve the frontend files
cd .claude/command-center/frontend
python3 -m http.server 3333

# Open in browser
open http://localhost:3333

# Should see: dark theme app shell with nav sidebar, topbar, empty dashboard view
```

### Test 2: Navigation and routing

```
1. Click each nav item: Dashboard, Kanban, Think Tank, Timeline, Agents, Epics
2. Verify URL hash changes: #dashboard, #kanban, #thinktank, #timeline, #agents, #epics
3. Verify topbar title updates
4. Press 1-6 keys: verify views switch
5. Cmd+K: verify palette opens, type "kan", verify "Kanban" appears, Enter to navigate
```

### Test 3: Kanban drag-and-drop (with mock data)

```javascript
// In browser console, inject mock data
import('/js/state.js').then(m => {
  m.setState({
    beads: [
      { id: 'b1', title: 'Fix login bug', column: 'backlog', priority: 0, assignee: 'agent-1', type: 'bug' },
      { id: 'b2', title: 'Add auth middleware', column: 'in_progress', priority: 1, assignee: 'agent-2', type: 'task' },
      { id: 'b3', title: 'Review API spec', column: 'in_review', priority: 2, type: 'task' },
      { id: 'b4', title: 'Deploy to staging', column: 'blocked', priority: 1, assignee: 'agent-1', type: 'task', dep_count: 1 },
    ]
  });
});

// Drag a card from Backlog to In Progress
// Verify: placeholder appears, card moves, toast shows "Moved to in_progress"
```

### Test 4: Think Tank phase stepper

```
1. Navigate to #thinktank
2. Verify Phase 1 (Listen) is active with pulsing circle
3. Verify spec-kit shows Project Brief unlocked, Pre-Mortem locked
4. Verify D/A/G chips appear below AI welcome message
5. Type a message and press Enter
6. Verify human message bubble appears right-aligned
```

### Test 5: Responsive behavior

```
1. Resize browser to <1024px: sidebar collapses to icons only
2. Resize to <768px: sidebar disappears, hamburger menu button appears
3. Click hamburger: sidebar slides in as drawer
4. Click a nav item: sidebar closes
5. Think Tank: spec-kit panel hides on mobile, chat takes full width
```

### Test 6: Keyboard shortcuts

```
1. Press Cmd+K: palette opens
2. Press Escape: palette closes
3. Press 1: dashboard view
4. Press 2: kanban view
5. Press ?: help toast appears
6. Click into a textarea, press 1: no view change (input focused)
```

### Test 7: Toast notifications

```javascript
// In browser console
import('/js/components/toast.js').then(m => {
  m.showToast('Success message', 'success');
  m.showToast('Error message', 'error');
  m.showToast('Warning message', 'warning');
  m.showToast('Info message', 'info');
});
// Verify: 4 toasts stack bottom-right, auto-dismiss after 4s, close button works
```
