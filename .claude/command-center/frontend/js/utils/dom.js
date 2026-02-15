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
