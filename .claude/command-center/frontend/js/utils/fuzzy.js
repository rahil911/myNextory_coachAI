// ==========================================================================
// FUZZY.JS — Fuzzy Search for Command Palette
// ==========================================================================

/**
 * Score how well query matches text.
 * Each char of query must appear in order in text.
 * Bonuses for: word boundary matches, consecutive chars, early matches.
 * Returns 0 for no match, positive score for match.
 */
export function fuzzyScore(query, text) {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let qi = 0;
  let score = 0;
  let consecutiveBonus = 0;

  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) {
      score += 1 + consecutiveBonus;
      // Word boundary bonus
      if (i === 0 || t[i - 1] === ' ' || t[i - 1] === '-' || t[i - 1] === '_') {
        score += 5;
      }
      consecutiveBonus += 2;
      qi++;
    } else {
      consecutiveBonus = 0;
    }
  }

  return qi === q.length ? score : 0;
}

/**
 * Filter and sort items by fuzzy match score.
 * @param {string} query
 * @param {Array} items
 * @param {string|Function} keyOrFn - property name or function to extract text
 * @returns {Array} matched items sorted by score (best first)
 */
export function fuzzySearch(query, items, keyOrFn = 'name') {
  if (!query || !query.trim()) return items;

  const getText = typeof keyOrFn === 'function'
    ? keyOrFn
    : (item) => [item[keyOrFn], item.description, item.category].filter(Boolean).join(' ');

  return items
    .map(item => ({ item, score: fuzzyScore(query, getText(item)) }))
    .filter(r => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(r => r.item);
}
