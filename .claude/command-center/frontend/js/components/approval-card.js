// ==========================================================================
// APPROVAL-CARD.JS — Approval Request Cards
// ==========================================================================

import { api } from '../api.js';
import { showToast } from './toast.js';
import { timeAgo, stringToColor } from '../utils/format.js';

export function renderApprovalCard(approval) {
  const urgencyColors = {
    critical: 'var(--red)',
    high: 'var(--priority-1)',
    medium: 'var(--yellow)',
    low: 'var(--green)'
  };

  const card = document.createElement('div');
  card.className = `approval-card urgency-${approval.urgency || 'medium'}`;
  card.dataset.id = approval.id;

  const confidenceColor = (approval.confidence || 0) >= 80 ? 'badge-green'
    : (approval.confidence || 0) >= 50 ? 'badge-yellow'
    : 'badge-red';

  card.innerHTML = `
    <div class="approval-card-header">
      <span class="badge badge-${approval.urgency === 'critical' ? 'red' : approval.urgency === 'high' ? 'yellow' : 'blue'}">
        ${(approval.urgency || 'MEDIUM').toUpperCase()}
      </span>
      <span class="badge ${confidenceColor}">${approval.confidence || '?'}% confidence</span>
      <span class="caption" style="margin-left:auto">${timeAgo(approval.createdAt)}</span>
    </div>

    <div class="approval-card-body">
      <div class="approval-card-title">${approval.title || 'Untitled'}</div>
      <div class="approval-card-desc">${approval.description || ''}</div>

      ${approval.evidence ? `
        <div class="approval-card-evidence">
          <details>
            <summary>Evidence (${approval.evidence.length} items)</summary>
            <ul style="padding-left:16px;margin-top:4px;font-size:12px;color:var(--text-secondary)">
              ${approval.evidence.map(e => `<li>${e}</li>`).join('')}
            </ul>
          </details>
        </div>
      ` : ''}

      ${approval.impact ? `
        <div class="approval-card-impact">
          <span class="caption">Impact:</span> ${approval.impact}
        </div>
      ` : ''}
    </div>

    <div class="approval-card-actions">
      <button class="btn-approve">\u2713 Approve</button>
      <button class="btn-reject">\u2717 Reject</button>
    </div>

    <div class="approval-reject-area">
      <textarea placeholder="Reason for rejection (required)..."></textarea>
      <div class="flex gap-2">
        <button class="btn btn-danger btn-sm confirm-reject-btn">Confirm Reject</button>
        <button class="btn btn-ghost btn-sm cancel-reject-btn">Cancel</button>
      </div>
    </div>
  `;

  // Approve handler
  card.querySelector('.btn-approve').addEventListener('click', async () => {
    const origHTML = card.innerHTML;
    card.classList.add('approved');
    card.querySelector('.approval-card-actions').innerHTML =
      '<span class="caption">Approved -- sending to agent...</span>';

    try {
      await api.executeCommand({ type: 'approve', approvalId: approval.id });
      card.style.transition = 'all 0.3s ease';
      card.style.opacity = '0';
      card.style.transform = 'translateX(100px)';
      setTimeout(() => card.remove(), 300);
      showToast(`Approved: ${approval.title}`, 'success');
    } catch (err) {
      card.classList.remove('approved');
      card.innerHTML = origHTML;
      showToast(`Failed: ${err.message}`, 'error');
    }
  });

  // Reject handlers
  const rejectArea = card.querySelector('.approval-reject-area');
  card.querySelector('.btn-reject').addEventListener('click', () => {
    rejectArea.classList.add('visible');
    rejectArea.querySelector('textarea').focus();
  });
  card.querySelector('.cancel-reject-btn').addEventListener('click', () => {
    rejectArea.classList.remove('visible');
  });
  card.querySelector('.confirm-reject-btn').addEventListener('click', async () => {
    const reason = rejectArea.querySelector('textarea').value.trim();
    if (!reason) {
      rejectArea.querySelector('textarea').style.borderColor = 'var(--red)';
      return;
    }
    card.classList.add('rejected');
    try {
      await api.executeCommand({ type: 'reject', approvalId: approval.id, reason });
      setTimeout(() => card.remove(), 2000);
      showToast('Rejected with reason', 'warning');
    } catch (err) {
      card.classList.remove('rejected');
      showToast(`Failed: ${err.message}`, 'error');
    }
  });

  return card;
}
