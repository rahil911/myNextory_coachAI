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
