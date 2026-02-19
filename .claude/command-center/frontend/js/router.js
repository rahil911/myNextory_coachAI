// ==========================================================================
// ROUTER.JS — Hash-Based Router with View Caching
// Views are created once and toggled via display:none/block for instant switching.
// ==========================================================================

import { setState } from './state.js';

const _routes = {};
// Cache of already-rendered view containers keyed by view name
const _viewCache = {};

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
    epics: 'Epics',
    approvals: 'Approvals',
    tory: 'Learning Path'
  };
  const titleEl = document.getElementById('topbar-title');
  if (titleEl) titleEl.textContent = titles[view] || view;

  // Update state
  setState({ currentView: view });

  // Hide all cached views
  for (const [name, el] of Object.entries(_viewCache)) {
    el.style.display = 'none';
  }

  // Show cached view or create new one
  if (_viewCache[view]) {
    _viewCache[view].style.display = '';
  } else {
    const renderFn = _routes[view];
    if (renderFn) {
      const wrapper = document.createElement('div');
      wrapper.dataset.viewName = view;
      root.appendChild(wrapper);
      renderFn(wrapper);
      _viewCache[view] = wrapper;
    } else {
      // Uncached 404 — render inline (no caching needed)
      const wrapper = document.createElement('div');
      wrapper.innerHTML = `<div class="view-container"><h2>View not found: ${view}</h2></div>`;
      root.appendChild(wrapper);
      _viewCache[view] = wrapper;
    }
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
