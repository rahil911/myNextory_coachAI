// ==========================================================================
// SPEC-KIT.JS — Live Spec-Kit Panel with Shimmer and Streaming
// ==========================================================================

import { h } from '../utils/dom.js';

/**
 * Render the spec-kit panel content.
 * @param {{ phase: number, specKit: object, risks: Array }} state
 * @param {Function} onEdit - (sectionKey, newValue) => void
 * @returns {HTMLElement}
 */
export function renderSpecKit(state, onEdit) {
  const container = h('div', { class: 'speckit-content' });

  // Project Brief (always visible)
  container.appendChild(renderSection('brief', 'Project Brief', state.specKit.brief, state.phase >= 1, onEdit));

  // Requirements (Phase 1+)
  container.appendChild(renderRequirements(state.specKit.requirements, state.phase >= 1, onEdit));

  // Constraints (Phase 2+)
  container.appendChild(renderSection('constraints', 'Constraints', state.specKit.constraints, state.phase >= 2, onEdit));

  // Pre-Mortem (Phase 3+)
  if (state.phase >= 3) {
    container.appendChild(renderPreMortemSection(state.risks));
  } else {
    container.appendChild(renderLockedSection('pre-mortem', 'Pre-Mortem', 'Unlocks in Phase 3: Scope'));
  }

  // Execution Plan (Phase 4)
  if (state.phase >= 4) {
    container.appendChild(renderSection('execution', 'Execution Plan', state.specKit.execution, true, onEdit));
  } else {
    container.appendChild(renderLockedSection('execution', 'Execution Plan', 'Unlocks in Phase 4: Confirm'));
  }

  return container;
}

function renderSection(key, title, content, unlocked, onEdit) {
  const section = h('div', {
    class: `speckit-section ${unlocked ? '' : 'locked'}`,
    dataset: { lockLabel: unlocked ? '' : 'Locked' }
  });

  const header = h('div', { class: 'speckit-section-header' });
  header.innerHTML = `
    <span class="speckit-section-title">${title}</span>
    ${unlocked ? '<button class="speckit-section-edit">[edit]</button>' : ''}
  `;

  section.appendChild(header);

  if (unlocked && content) {
    if (typeof content === 'object' && !Array.isArray(content)) {
      for (const [fieldKey, fieldVal] of Object.entries(content)) {
        const field = h('div', { class: 'speckit-field' });
        field.innerHTML = `
          <div class="speckit-field-label">${fieldKey}</div>
          <div class="speckit-field-value">${fieldVal || ''}</div>
        `;
        section.appendChild(field);
      }
    } else if (typeof content === 'string') {
      const body = h('div', { class: 'speckit-field-value' });
      body.innerHTML = content.replace(/\n/g, '<br>');
      section.appendChild(body);
    }
  } else if (unlocked) {
    // Shimmer placeholders
    section.appendChild(h('div', { class: 'shimmer shimmer-long', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-medium', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-short' }));
  }

  // Edit click handler
  const editBtn = section.querySelector('.speckit-section-edit');
  if (editBtn && onEdit) {
    editBtn.addEventListener('click', () => {
      // Toggle inline editing
      const body = section.querySelector('.speckit-field-value');
      if (!body) return;
      const textarea = document.createElement('textarea');
      textarea.value = body.textContent;
      textarea.style.cssText = 'width:100%;min-height:60px;margin-top:8px;';
      textarea.className = 'speckit-user-edit';
      body.replaceWith(textarea);
      textarea.focus();

      textarea.addEventListener('blur', () => {
        onEdit(key, textarea.value);
        const newBody = h('div', { class: 'speckit-field-value speckit-user-edit' });
        newBody.innerHTML = textarea.value.replace(/\n/g, '<br>');
        textarea.replaceWith(newBody);
      });
    });
  }

  return section;
}

function renderRequirements(reqs, unlocked, onEdit) {
  const section = h('div', { class: `speckit-section ${unlocked ? '' : 'locked'}` });
  section.innerHTML = `<div class="speckit-section-header">
    <span class="speckit-section-title">Requirements</span>
    ${unlocked ? '<button class="speckit-section-edit">[edit]</button>' : ''}
  </div>`;

  if (unlocked && reqs) {
    if (reqs.mustHave) {
      const mustHaveLabel = h('div', { class: 'speckit-field-label', style: { marginTop: '8px' } });
      mustHaveLabel.textContent = 'Must-Have';
      section.appendChild(mustHaveLabel);
      reqs.mustHave.forEach(r => {
        section.appendChild(renderRequirement(r));
      });
    }
    if (reqs.niceToHave) {
      const niceLabel = h('div', { class: 'speckit-field-label', style: { marginTop: '12px' } });
      niceLabel.textContent = 'Nice-to-Have';
      section.appendChild(niceLabel);
      reqs.niceToHave.forEach(r => {
        section.appendChild(renderRequirement(r));
      });
    }
  } else if (unlocked) {
    section.appendChild(h('div', { class: 'shimmer shimmer-long', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-medium' }));
  }

  return section;
}

function renderRequirement(req) {
  const item = h('div', { class: 'speckit-requirement' });
  const text = typeof req === 'string' ? req : req.text;
  const done = typeof req === 'object' ? req.done : false;
  item.innerHTML = `
    <input type="checkbox" ${done ? 'checked' : ''}>
    <span style="font-size:14px">${text}</span>
  `;
  return item;
}

function renderLockedSection(key, title, lockMessage) {
  const section = h('div', {
    class: 'speckit-section locked',
    dataset: { lockLabel: lockMessage }
  });
  section.innerHTML = `<div class="speckit-section-header">
    <span class="speckit-section-title">${title}</span>
    <span style="font-size:11px;color:var(--text-tertiary)">\u{1F512}</span>
  </div>`;
  return section;
}

function renderPreMortemSection(risks) {
  const section = h('div', { class: 'speckit-section' });
  section.innerHTML = `<div class="speckit-section-header">
    <span class="speckit-section-title">Pre-Mortem</span>
  </div>
  <p style="font-size:12px;color:var(--text-tertiary);margin-bottom:12px;font-style:italic">
    "It's 6 months from now and the project failed. What went wrong?"
  </p>`;

  if (risks && risks.length) {
    risks.forEach(risk => {
      section.appendChild(renderRiskCardElement(risk));
    });

    // Risk summary
    const critical = risks.filter(r => r.severity === 'critical').length;
    const watch = risks.filter(r => r.severity === 'watch').length;
    const low = risks.filter(r => r.severity === 'low').length;
    const addressed = risks.filter(r => r.disposition).length;

    const summary = h('div', { class: 'risk-summary' });
    summary.innerHTML = `
      <span class="risk-summary-item"><span class="risk-summary-dot" style="background:var(--red)"></span> ${critical} Critical</span>
      <span class="risk-summary-item"><span class="risk-summary-dot" style="background:var(--yellow)"></span> ${watch} Watch</span>
      <span class="risk-summary-item"><span class="risk-summary-dot" style="background:var(--green)"></span> ${low} Low</span>
      <span style="margin-left:auto;font-size:11px;color:var(--text-tertiary)">${addressed}/${risks.length} addressed</span>
    `;
    section.appendChild(summary);
  } else {
    section.appendChild(h('div', { class: 'shimmer shimmer-long', style: { marginBottom: '8px' } }));
    section.appendChild(h('div', { class: 'shimmer shimmer-medium' }));
  }

  return section;
}

function renderRiskCardElement(risk) {
  const card = h('div', { class: `risk-card severity-${risk.severity || 'watch'}` });
  card.innerHTML = `
    <div class="risk-card-title">${risk.title || 'Untitled Risk'}</div>
    <div class="risk-card-description">${risk.description || ''}</div>
    <div class="risk-card-scores">
      <span class="risk-score">Likelihood: <span class="risk-stars">${'\u2605'.repeat(risk.likelihood || 3)}${'\u2606'.repeat(5 - (risk.likelihood || 3))}</span></span>
      <span class="risk-score">Impact: <span class="risk-stars">${'\u2605'.repeat(risk.impact || 3)}${'\u2606'.repeat(5 - (risk.impact || 3))}</span></span>
    </div>
    ${risk.mitigation ? `<div class="risk-mitigation">${risk.mitigation}</div>` : ''}
    <div class="risk-actions">
      <button class="risk-btn ${risk.disposition === 'accept' ? 'selected accept' : ''}" data-action="accept">Accept Risk</button>
      <button class="risk-btn ${risk.disposition === 'mitigate' ? 'selected mitigate' : ''}" data-action="mitigate">Mitigate</button>
      <button class="risk-btn ${risk.disposition === 'eliminate' ? 'selected eliminate' : ''}" data-action="eliminate">Eliminate</button>
    </div>
  `;

  card.querySelectorAll('.risk-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      card.querySelectorAll('.risk-btn').forEach(b => b.classList.remove('selected', 'accept', 'mitigate', 'eliminate'));
      btn.classList.add('selected', btn.dataset.action);
      risk.disposition = btn.dataset.action;
    });
  });

  return card;
}
