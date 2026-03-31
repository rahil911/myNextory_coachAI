// ==========================================================================
// APP.JS — Main Entry Point
// Wires state, router, WebSocket, command palette, keyboard shortcuts
// ==========================================================================

import { getState, setState, subscribe } from './state.js';
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
import { renderApprovals } from './views/approvals.js';
import { renderArchitecture } from './views/architecture.js';
import { renderToryWorkspace } from './views/tory-workspace.js';
import { renderToryAdmin } from './views/tory-admin.js';
import { renderContent360 } from './views/content-360.js';
import { renderCompanionChat } from './views/companion-chat.js';
import { renderEngine } from './views/engine.js';

// ── Initialize ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // 1. Register routes
  registerRoute('dashboard', renderDashboard);
  registerRoute('kanban', renderKanban);
  registerRoute('thinktank', renderThinkTank);
  registerRoute('timeline', renderTimeline);
  registerRoute('agents', renderAgents);
  registerRoute('epics', renderEpics);
  registerRoute('architecture', renderArchitecture);
  registerRoute('approvals', renderApprovals);
  registerRoute('tory', renderToryWorkspace);
  registerRoute('tory-admin', renderToryAdmin);
  registerRoute('content-360', renderContent360);
  registerRoute('companion', renderCompanionChat);
  registerRoute('engine', renderEngine);

  // 2. Initialize router
  initRouter();

  // 3. Connect WebSocket for real-time updates
  connectWebSockets();

  // 3.5. Load approval badge count + subscribe for real-time updates
  function refreshApprovalBadge() {
    api.getApprovals().then(data => {
      const count = data.pending_count || 0;
      const badge = document.getElementById('approval-badge');
      if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-flex' : 'none';
      }
    }).catch(() => {});
  }
  refreshApprovalBadge();
  subscribe('_approvalTick', () => refreshApprovalBadge());

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
    { name: 'Go to Architecture', description: 'System architecture visualization', category: 'Navigation',
      shortcut: 'G R', icon: '\u25a6', action: () => { window.location.hash = 'architecture'; } },
    { name: 'Go to Approvals', description: 'Review pending ownership proposals', category: 'Navigation',
      shortcut: 'G P', icon: '\u26A0', action: () => { window.location.hash = 'approvals'; } },
    { name: 'Go to Learning Path', description: 'Tory learner roadmap and profile', category: 'Navigation',
      shortcut: 'G Y', icon: '\u2728', action: () => { window.location.hash = 'tory'; } },
    { name: 'Go to HR Dashboard', description: 'Tory progress tracking for HR/Admin', category: 'Navigation',
      shortcut: 'G H', icon: '\u25A4', action: () => { window.location.hash = 'tory-admin'; } },
    { name: 'Go to Content 360', description: 'Full lesson intelligence dashboard', category: 'Navigation',
      shortcut: 'G C', icon: '\uD83D\uDCDA', action: () => { window.location.hash = 'content-360'; } },
    { name: 'Go to Companion', description: 'Learner AI companion chat', category: 'Navigation',
      shortcut: 'G M', icon: '\uD83D\uDCAC', action: () => { window.location.hash = 'companion'; } },

    // Actions
    { name: 'New Think Tank Session', description: 'Start brainstorming', category: 'Actions',
      shortcut: 'N', icon: '\u2795', action: () => {
        setState({ thinktank: { ...getState().thinktank, sessionId: null, messages: [], specKit: {}, risks: [], phase: 1, status: null } });
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
        const running = agents.filter(a => a.status === 'working' || a.status === 'spawning');
        for (const a of running) {
          try { await api.killAgent(a.name); } catch {}
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
      case '7': window.location.hash = 'approvals'; break;
      case '8': window.location.hash = 'architecture'; break;
      case '9': window.location.hash = 'tory'; break;
      case '0': window.location.hash = 'tory-admin'; break;
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
