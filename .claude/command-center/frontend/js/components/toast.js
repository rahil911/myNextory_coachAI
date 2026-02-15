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
