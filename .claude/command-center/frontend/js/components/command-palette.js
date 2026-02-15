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
