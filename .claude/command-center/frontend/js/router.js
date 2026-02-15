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
