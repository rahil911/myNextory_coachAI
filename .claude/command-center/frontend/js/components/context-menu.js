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
