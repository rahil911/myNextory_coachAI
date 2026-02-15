// ==========================================================================
// FORMAT.JS — Time & Number Formatting
// ==========================================================================

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Relative time string: "2m ago", "3h ago", "1d ago"
 */
export function timeAgo(dateStr) {
  if (!dateStr) return '';
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  const diff = Date.now() - date.getTime();

  if (diff < MINUTE) return 'just now';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d ago`;
  return date.toLocaleDateString();
}

/**
 * Duration string: "1.2s", "450ms", "3m 12s"
 */
export function formatDuration(ms) {
  if (ms == null) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const min = Math.floor(ms / 60000);
  const sec = Math.round((ms % 60000) / 1000);
  return `${min}m ${sec}s`;
}

/**
 * Compact number: "1.2K", "3.4M"
 */
export function compactNumber(num) {
  if (num == null) return '0';
  if (num < 1000) return String(num);
  if (num < 1000000) return (num / 1000).toFixed(1) + 'K';
  return (num / 1000000).toFixed(1) + 'M';
}

/**
 * Generate a consistent color from a string (for agent badges)
 */
export function stringToColor(str) {
  if (!str) return '#6366f1';
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 60%, 55%)`;
}

/**
 * Generate star rating: "****_" for 4/5
 */
export function starRating(score, max = 5) {
  return '\u2605'.repeat(score) + '\u2606'.repeat(max - score);
}
