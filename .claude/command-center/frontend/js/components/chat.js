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

function formatMessageContent(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });
    return marked.parse(text);
  }
  // Fallback if marked not loaded
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code class="mono">$1</code>')
    .replace(/\n/g, '<br>');
}
