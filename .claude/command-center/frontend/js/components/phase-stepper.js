// ==========================================================================
// PHASE-STEPPER.JS — Horizontal Phase Indicator
// ==========================================================================

const PHASES = [
  { id: 'listen',  num: 1, label: 'Listen',  sub: 'Understanding your vision' },
  { id: 'explore', num: 2, label: 'Explore', sub: 'Mapping possibilities' },
  { id: 'scope',   num: 3, label: 'Scope',   sub: 'Stress-testing risks' },
  { id: 'confirm', num: 4, label: 'Confirm', sub: 'Final review' },
];

/**
 * Render the phase stepper.
 * @param {number} currentPhase - 1-4
 * @returns {HTMLElement}
 */
export function renderPhaseStepper(currentPhase) {
  const stepper = document.createElement('div');
  stepper.className = 'phase-stepper';

  PHASES.forEach((phase, i) => {
    const status = phase.num < currentPhase ? 'completed'
      : phase.num === currentPhase ? 'active'
      : 'upcoming';

    const step = document.createElement('div');
    step.className = `phase-step ${status}`;

    const circle = document.createElement('div');
    circle.className = 'phase-circle';
    circle.textContent = status === 'completed' ? '\u2713' : String(phase.num);

    const labelWrap = document.createElement('div');
    labelWrap.innerHTML = `
      <span class="phase-label">${phase.label}</span>
      <span class="phase-sublabel">${phase.sub}</span>
    `;

    step.appendChild(circle);
    step.appendChild(labelWrap);
    stepper.appendChild(step);

    // Add connecting line (except after last phase)
    if (i < PHASES.length - 1) {
      const line = document.createElement('div');
      const lineStatus = phase.num < currentPhase ? 'completed'
        : phase.num === currentPhase ? 'active'
        : 'upcoming';
      line.className = `phase-line ${lineStatus}`;
      stepper.appendChild(line);
    }
  });

  return stepper;
}
