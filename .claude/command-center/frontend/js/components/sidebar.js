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
