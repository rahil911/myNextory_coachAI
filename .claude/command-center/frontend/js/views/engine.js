// ==========================================================================
// ENGINE.JS — Tory Engine Observability Dashboard
// Full transparency: algorithms, formulas, live stats, pipeline traces
// ==========================================================================

import { api } from '../api.js';
import { h } from '../utils/dom.js';
import { showToast } from '../components/toast.js';

// ── Constants ────────────────────────────────────────────────────────────

const EPP_DIMENSIONS = [
  { trait: 'Achievement', desc: 'Drive to accomplish goals and meet high standards', threshold: '< 30 gap, > 70 strength' },
  { trait: 'Motivation', desc: 'Internal energy and self-starting capability', threshold: 'Correlates with Achievement' },
  { trait: 'Competitiveness', desc: 'Drive to outperform others', threshold: 'High = win/lose framing' },
  { trait: 'Managerial', desc: 'Comfort leading, directing, and managing others', threshold: 'Important for leadership paths' },
  { trait: 'Assertiveness', desc: 'Willingness to speak up, advocate, say no', threshold: 'Most impactful coaching target' },
  { trait: 'Extroversion', desc: 'Social energy, preference for group interaction', threshold: 'Networking/presentation relevance' },
  { trait: 'Cooperativeness', desc: 'Teamwork orientation, harmony, helping others', threshold: '> 85 = people-pleasing risk' },
  { trait: 'Patience', desc: 'Tolerance for frustration and slow progress', threshold: 'Low + High Achievement = burnout' },
  { trait: 'SelfConfidence', desc: 'Belief in own abilities and judgment', threshold: 'Foundational - colors everything' },
  { trait: 'Conscientiousness', desc: 'Attention to detail, organization, thoroughness', threshold: 'High = deep exercise engagement' },
  { trait: 'Openness', desc: 'Receptivity to new ideas, change, innovation', threshold: 'Growth mindset indicator' },
  { trait: 'Stability', desc: 'Emotional evenness and composure', threshold: 'Low = needs psych safety early' },
  { trait: 'StressTolerance', desc: 'Performance maintenance under pressure', threshold: 'Distinct from Stability' },
];

const JOB_COMPOSITES = [
  'Accounting', 'AdminAsst', 'Analyst', 'BankTeller', 'Collections',
  'CustomerService', 'FrontDesk', 'Manager', 'MedicalAsst', 'Production',
  'Programmer', 'Sales',
];

const TENSION_PAIRS = [
  { pair: 'Achievement + SelfConfidence', high: 'Achievement', low: 'SelfConfidence', alert: 'Imposter Syndrome', desc: 'Pushes hard for results but doubts their own worthiness. Success feels like luck.' },
  { pair: 'Cooperativeness + Assertiveness', high: 'Cooperativeness', low: 'Assertiveness', alert: 'People-Pleasing', desc: 'Says yes to everything, avoids conflict, burns out serving others.' },
  { pair: 'Competitiveness + Patience', high: 'Competitiveness', low: 'Patience', alert: 'Frustration Spiral', desc: 'Wants to win NOW. Gets frustrated with slow progress or slow colleagues.' },
  { pair: 'Openness + Stability', high: 'Openness', low: 'Stability', alert: 'Change Paradox', desc: 'Excited by new ideas but emotionally destabilized by the change itself.' },
  { pair: 'Motivation + Assertiveness', high: 'Motivation', low: 'Assertiveness', alert: 'Silent Achiever', desc: 'Works incredibly hard but invisible. Needs encouragement, not pressure.' },
];

const THRESHOLDS = {
  discoveryLessons: 5,
  autoApproveConfidence: 75,
  needsReviewConfidence: 50,
  quarterlyDays: 90,
  miniQuestionRange: '3-5',
  backpackSignals: 10,
  driftThreshold: 15,
  maxRetries: 3,
  rateLimitRPM: 100,
  maxConsecutiveJourney: 3,
  diminishingFactor: 0.7,
  maxPathLessons: 20,
  coachLowThreshold: 30,
  coachHighThreshold: 80,
};

// ── Module State ─────────────────────────────────────────────────────────

let _stats = null;
let _loading = false;
let _activeSection = 'overview';
let _pipelineUser = null;
let _pipelineData = null;
let _pipelineLoading = false;
let _availableUsers = null;

// ── Entry Point ──────────────────────────────────────────────────────────

export function renderEngine(root) {
  const container = h('div', { class: 'eng-layout' });
  root.innerHTML = '';
  root.appendChild(container);
  _render(container);
  _loadStats(container);
}

function _render(container) {
  container.innerHTML = `
    <div class="eng-header">
      <div class="eng-header-left">
        <h1 class="eng-title">Tory Engine</h1>
        <span class="eng-subtitle">Recommendation Engine Observability</span>
      </div>
      <div class="eng-header-right">
        <button class="eng-btn eng-btn-refresh" id="eng-refresh">Refresh Stats</button>
      </div>
    </div>

    <div class="eng-nav">
      <button class="eng-nav-btn active" data-section="overview">Overview</button>
      <button class="eng-nav-btn" data-section="formulas">Scoring Formulas</button>
      <button class="eng-nav-btn" data-section="pipeline">Pipeline Steps</button>
      <button class="eng-nav-btn" data-section="epp">EPP Dimensions</button>
      <button class="eng-nav-btn" data-section="tools">MCP Tools</button>
      <button class="eng-nav-btn" data-section="trace">Pipeline Trace</button>
    </div>

    <div class="eng-content" id="eng-content">
      <div class="eng-loading"><div class="eng-spinner"></div> Loading engine data...</div>
    </div>
  `;

  // Nav clicks
  container.querySelectorAll('.eng-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeSection = btn.dataset.section;
      container.querySelectorAll('.eng-nav-btn').forEach(b => b.classList.toggle('active', b === btn));
      _renderSection(container);
    });
  });

  container.querySelector('#eng-refresh')?.addEventListener('click', () => _loadStats(container));
}

async function _loadStats(container) {
  _loading = true;
  _renderSection(container);
  try {
    _stats = await api.getEngineStats();
    _loading = false;
    _renderSection(container);
  } catch (err) {
    _loading = false;
    const el = container.querySelector('#eng-content');
    if (el) el.innerHTML = `<div class="eng-error">Failed to load: ${_esc(err.message)}</div>`;
  }
}

function _renderSection(container) {
  const el = container.querySelector('#eng-content');
  if (!el) return;

  if (_loading) {
    el.innerHTML = '<div class="eng-loading"><div class="eng-spinner"></div> Loading engine data...</div>';
    return;
  }

  switch (_activeSection) {
    case 'overview': _renderOverview(el); break;
    case 'formulas': _renderFormulas(el); break;
    case 'pipeline': _renderPipeline(el); break;
    case 'epp': _renderEPP(el); break;
    case 'tools': _renderTools(el); break;
    case 'trace': _renderTrace(el); break;
  }
}

// ── OVERVIEW TAB ──────────────────────────────────────────────────────────

function _renderOverview(el) {
  const s = _stats || {};
  const p = s.profiles || {};
  const r = s.recommendations || {};
  const t = s.content_tags || {};
  const l = s.lessons || {};
  const re = s.reassessments || {};
  const rm = s.roadmaps || {};
  const ai = s.ai_sessions || {};
  const pe = s.path_events || {};
  const cf = s.coach_flags || {};

  el.innerHTML = `
    <!-- Stats Grid -->
    <div class="eng-stats-grid">
      ${_statCard('Learner Profiles', p.users || 0, 'Unique learners with EPP-derived profiles', '#8b5cf6')}
      ${_statCard('Learning Paths', r.users_with_paths || 0, 'Learners with generated recommendation paths', '#3b82f6')}
      ${_statCard('Recommendations', r.total || 0, `Avg score: ${r.avg_score || 0}`, '#22c55e')}
      ${_statCard('Content Tags', t.total || 0, `${t.approved || 0} approved, ${t.pending || 0} pending`, '#f59e0b')}
      ${_statCard('Lessons Tagged', `${l.tagged_lessons || 0}/${l.total_lessons || 0}`, `${l.total_lessons > 0 ? Math.round((l.tagged_lessons || 0) / l.total_lessons * 100) : 0}% coverage`, '#ec4899')}
      ${_statCard('Reassessments', re.total || 0, `${re.drift_triggered || 0} drift triggers, ${re.paths_reranked || 0} re-ranked`, '#ef4444')}
      ${_statCard('AI Sessions', ai.total || 0, `${ai.total_messages || 0} messages total`, '#06b6d4')}
      ${_statCard('Coach Actions', pe.total || 0, `${pe.reorders || 0} reorders, ${pe.swaps || 0} swaps, ${pe.locks || 0} locks`, '#f97316')}
    </div>

    <!-- Pedagogy Config -->
    <div class="eng-section">
      <h2 class="eng-section-title">Active Pedagogy Configuration</h2>
      <div class="eng-pedagogy-grid">
        ${(s.pedagogy || []).length > 0 ? (s.pedagogy || []).map(p => `
          <div class="eng-pedagogy-card">
            <div class="eng-pedagogy-mode">${_esc(_pedagogyLabel(p.mode))}</div>
            <div class="eng-pedagogy-ratio">
              <div class="eng-ratio-bar">
                <div class="eng-ratio-gap" style="width:${p.gap_ratio}%">${p.gap_ratio}% Gap</div>
                <div class="eng-ratio-str" style="width:${p.strength_ratio}%">${p.strength_ratio}% Str</div>
              </div>
            </div>
            <div class="eng-pedagogy-client">Client #${p.client_id}</div>
          </div>
        `).join('') : `
          <div class="eng-pedagogy-card">
            <div class="eng-pedagogy-mode">Balanced (Default)</div>
            <div class="eng-pedagogy-ratio">
              <div class="eng-ratio-bar">
                <div class="eng-ratio-gap" style="width:50%">50% Gap</div>
                <div class="eng-ratio-str" style="width:50%">50% Str</div>
              </div>
            </div>
            <div class="eng-pedagogy-client">All clients</div>
          </div>
        `}
      </div>
    </div>

    <!-- Coach Compatibility -->
    <div class="eng-section">
      <h2 class="eng-section-title">Coach Compatibility Signals</h2>
      <div class="eng-traffic-grid">
        <div class="eng-traffic-card green">
          <div class="eng-traffic-light"></div>
          <div class="eng-traffic-count">${cf.green || 0}</div>
          <div class="eng-traffic-label">Green</div>
          <div class="eng-traffic-desc">No concerns</div>
        </div>
        <div class="eng-traffic-card yellow">
          <div class="eng-traffic-light"></div>
          <div class="eng-traffic-count">${cf.yellow || 0}</div>
          <div class="eng-traffic-label">Yellow</div>
          <div class="eng-traffic-desc">Some considerations</div>
        </div>
        <div class="eng-traffic-card red">
          <div class="eng-traffic-light"></div>
          <div class="eng-traffic-count">${cf.red || 0}</div>
          <div class="eng-traffic-label">Red</div>
          <div class="eng-traffic-desc">Review recommended</div>
        </div>
      </div>
    </div>

    <!-- Score Distribution -->
    <div class="eng-two-col">
      <div class="eng-section">
        <h2 class="eng-section-title">Match Score Distribution</h2>
        ${_renderDistChart(s.score_distribution || [], '#3b82f6')}
      </div>
      <div class="eng-section">
        <h2 class="eng-section-title">Tag Confidence Distribution</h2>
        ${_renderDistChart(s.confidence_distribution || [], '#8b5cf6')}
      </div>
    </div>

    <!-- Trait Coverage -->
    <div class="eng-section">
      <h2 class="eng-section-title">Trait Coverage in Content Tags</h2>
      <div class="eng-trait-bars">
        ${(s.trait_coverage || []).map(t => {
          const max = Math.max(...(s.trait_coverage || []).map(x => parseInt(x.tag_count) || 0), 1);
          const pct = Math.round((parseInt(t.tag_count) || 0) / max * 100);
          return `
            <div class="eng-trait-row">
              <span class="eng-trait-name">${_esc(t.trait_name)}</span>
              <div class="eng-trait-bar-bg"><div class="eng-trait-bar-fill" style="width:${pct}%"></div></div>
              <span class="eng-trait-count">${t.tag_count}</span>
            </div>
          `;
        }).join('')}
      </div>
    </div>

    <!-- Top Matched Traits -->
    <div class="eng-section">
      <h2 class="eng-section-title">Most Matched Traits in Recommendations</h2>
      <div class="eng-matched-grid">
        ${(s.top_matched_traits || []).slice(0, 16).map(t => {
          const isGap = t.match_type === 'gap';
          return `<div class="eng-matched-pill ${isGap ? 'gap' : 'strength'}">
            <span class="eng-matched-name">${_esc(t.trait_name)}</span>
            <span class="eng-matched-type">${isGap ? 'gap' : 'str'}</span>
            <span class="eng-matched-count">${t.match_count}</span>
          </div>`;
        }).join('')}
      </div>
    </div>

    <!-- Constants -->
    <div class="eng-section">
      <h2 class="eng-section-title">Engine Constants & Thresholds</h2>
      <div class="eng-constants-grid">
        ${Object.entries(THRESHOLDS).map(([k, v]) => `
          <div class="eng-const-card">
            <div class="eng-const-val">${v}</div>
            <div class="eng-const-key">${_humanizeKey(k)}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

// ── FORMULAS TAB ──────────────────────────────────────────────────────────

function _renderFormulas(el) {
  el.innerHTML = `
    <div class="eng-formulas">

      <!-- 1. Content Scoring -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">1. Content Scoring Formula</h2>
        <p class="eng-formula-desc">Each lesson is scored against a learner's EPP profile by computing weighted overlap between the lesson's trait tags and the learner's gaps/strengths.</p>

        <div class="eng-formula-box">
          <div class="eng-formula-label">Gap Score</div>
          <pre class="eng-formula-math">gap_score = SUM( relevance_i * gap_trait_i / 100 )
  for each trait_tag where trait in learner.gaps</pre>
        </div>

        <div class="eng-formula-box">
          <div class="eng-formula-label">Strength Score</div>
          <pre class="eng-formula-math">strength_score = SUM( relevance_i * strength_trait_i / 100 )
  for each trait_tag where trait in learner.strengths</pre>
        </div>

        <div class="eng-formula-box highlight">
          <div class="eng-formula-label">Total Match Score</div>
          <pre class="eng-formula-math">total = (gap_score * gap_ratio/100) + (strength_score * strength_ratio/100)
match_score = CLAMP(total * 100, 0, 100)</pre>
        </div>

        <div class="eng-formula-example">
          <strong>Example:</strong> Learner has Assertiveness=12 (gap). Lesson "Power of No" has trait_tag {trait: "Assertiveness", relevance: 85, direction: "builds"}.
          <br>gap_score += 85 * 12 / 100 = 10.2
          <br>With balanced pedagogy (50/50): total = 10.2 * 0.5 = 5.1, scaled = 510 -> clamped to 100
        </div>
      </div>

      <!-- 2. Pedagogy Modes -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">2. Pedagogy Modes</h2>
        <p class="eng-formula-desc">The gap/strength ratio determines how the engine balances remedial vs reinforcement content.</p>

        <div class="eng-pedagogy-modes">
          <div class="eng-mode-card">
            <div class="eng-mode-letter">A</div>
            <div class="eng-mode-name">Gap Fill</div>
            <div class="eng-mode-ratio">70% Gap / 30% Strength</div>
            <div class="eng-mode-desc">Prioritizes growth areas. Best for learners who need to build missing capabilities. The path will heavily weight lessons that target low-scoring EPP traits.</div>
          </div>
          <div class="eng-mode-card">
            <div class="eng-mode-letter">B</div>
            <div class="eng-mode-name">Strength Lead</div>
            <div class="eng-mode-ratio">30% Gap / 70% Strength</div>
            <div class="eng-mode-desc">Builds on existing strengths. Best for confident learners who respond to positive reinforcement. Leverages high-scoring traits to build momentum.</div>
          </div>
          <div class="eng-mode-card">
            <div class="eng-mode-letter">C</div>
            <div class="eng-mode-name">Balanced</div>
            <div class="eng-mode-ratio">Custom ratio (default 50/50)</div>
            <div class="eng-mode-desc">Equal weight to gaps and strengths. The default mode. HR can customize the exact ratio per client company.</div>
          </div>
        </div>
      </div>

      <!-- 3. Sequencing Algorithm -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">3. Sequencing & Diversity Algorithm</h2>
        <p class="eng-formula-desc">After scoring, lessons are sequenced through a 4-phase pipeline to ensure variety and prevent trait stacking.</p>

        <div class="eng-phase-list">
          <div class="eng-phase">
            <div class="eng-phase-num">1</div>
            <div class="eng-phase-body">
              <div class="eng-phase-name">Diminishing Returns</div>
              <div class="eng-phase-desc">When the same trait appears in multiple lessons, each subsequent occurrence gets penalized.</div>
              <div class="eng-formula-box">
                <pre class="eng-formula-math">adjusted_score = score * (0.7 ^ trait_repeat_count)
  where 0.7 = diminishing_factor</pre>
              </div>
              <div class="eng-formula-example">1st lesson with Assertiveness: score * 1.0<br>2nd: score * 0.7<br>3rd: score * 0.49<br>4th: score * 0.343</div>
            </div>
          </div>

          <div class="eng-phase">
            <div class="eng-phase-num">2</div>
            <div class="eng-phase-body">
              <div class="eng-phase-name">Journey Diversity</div>
              <div class="eng-phase-desc">No more than 3 consecutive lessons from the same journey. Deferred lessons go to a backlog.</div>
              <div class="eng-formula-box">
                <pre class="eng-formula-math">if consecutive_same_journey >= 3:
    defer(lesson)  # try to fit later
else:
    select(lesson)</pre>
              </div>
            </div>
          </div>

          <div class="eng-phase">
            <div class="eng-phase-num">3</div>
            <div class="eng-phase-body">
              <div class="eng-phase-name">Fill Deferred</div>
              <div class="eng-phase-desc">Deferred lessons from Phase 2 are appended to fill remaining slots up to max_lessons (20).</div>
            </div>
          </div>

          <div class="eng-phase">
            <div class="eng-phase-num">4</div>
            <div class="eng-phase-body">
              <div class="eng-phase-name">Gap/Strength Interleaving</div>
              <div class="eng-phase-desc">Alternate between gap-targeting and strength-leveraging lessons. Max 3 in a row of either type.</div>
              <div class="eng-formula-box">
                <pre class="eng-formula-math">while gap_lessons OR strength_lessons:
  if streak_type == "gap" and streak >= 3:
      pick_strength()
  elif streak_type == "strength" and streak >= 3:
      pick_gap()
  else:
      pick(higher_adjusted_score)</pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 4. Profile Drift -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">4. Profile Drift Calculation</h2>
        <p class="eng-formula-desc">When new EPP data arrives (quarterly retake, mini-assessment, or passive signals), the engine computes how much the profile has shifted.</p>

        <div class="eng-formula-box highlight">
          <div class="eng-formula-label">Drift Percentage</div>
          <pre class="eng-formula-math">drift_pct = AVG( |new_score_i - old_score_i| ) across all traits

changed_traits = traits where |delta| >= 5  (meaningful threshold)

if drift_pct >= 15%:
    trigger path re-ranking</pre>
        </div>

        <div class="eng-formula-example">
          <strong>Example:</strong> If 13 traits average 3.2 points of change, drift = 3.2%. No re-ranking.
          <br>If Assertiveness jumps from 12 to 45 (+33) and others shift moderately, drift might hit 18%. Path gets re-ranked.
        </div>
      </div>

      <!-- 5. Coach Compatibility -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">5. Coach Compatibility Heuristic</h2>
        <p class="eng-formula-desc">Traffic light system based on learner's EPP extremes. V1 uses rule-based heuristics (coaches don't have EPP yet).</p>

        <div class="eng-formula-box">
          <pre class="eng-formula-math">low_traits  = traits where score < 30
high_traits = traits where score > 80

warnings = []
if len(low_traits) > 5:      warn("Many low traits")
if "StressTolerance" in low:  warn("Needs supportive style")
if "Assertiveness" in low
   AND "Motivation" in high:  warn("Encourage, don't pressure")

RED:    warnings >= 3  "Potential mismatch"
YELLOW: warnings >= 1  "Some considerations"
GREEN:  warnings == 0  "No concerns"</pre>
        </div>
      </div>

      <!-- 6. Rationale Generation -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">6. Rationale Generation</h2>
        <p class="eng-formula-desc">Each recommendation gets a human-readable explanation. Template-based (no LLM call) referencing specific EPP dimensions.</p>

        <div class="eng-formula-box">
          <pre class="eng-formula-math">if is_discovery:
  "Discovery lesson: exploratory recommendation..."
  + gap traits named + strength traits named

else:
  if gap_traits:  "Targets growth areas in {traits}"
  if str_traits:  "Leverages strong {traits} scores"
  if score > 70:  "High-confidence match"
  elif score > 40: "Moderate match for balanced development"</pre>
        </div>
      </div>

      <!-- 7. Discovery Phase -->
      <div class="eng-formula-card">
        <h2 class="eng-formula-title">7. Discovery Phase (Cold Start)</h2>
        <p class="eng-formula-desc">First 5 lessons in any new path are marked as "discovery" with exploratory framing. Lower commitment language, broader trait coverage.</p>

        <div class="eng-formula-box">
          <pre class="eng-formula-math">DISCOVERY_LESSON_COUNT = 5

for i, lesson in path[:5]:
    lesson.is_discovery = True
    lesson.rationale = discovery_framing(lesson)

Discovery framing uses gentler language:
  "Gently introduces growth areas..."
  "Allowing you to explore at your own pace..."</pre>
        </div>
      </div>
    </div>
  `;
}

// ── PIPELINE TAB ──────────────────────────────────────────────────────────

function _renderPipeline(el) {
  el.innerHTML = `
    <div class="eng-pipeline">
      <h2 class="eng-section-title">End-to-End Pipeline Architecture</h2>
      <p class="eng-pipeline-intro">From raw EPP scores to a personalized learning path, every step is traceable and auditable.</p>

      <div class="eng-pipeline-flow">

        <div class="eng-pipe-step">
          <div class="eng-pipe-num">1</div>
          <div class="eng-pipe-card">
            <div class="eng-pipe-title">EPP Assessment Intake</div>
            <div class="eng-pipe-io">
              <div class="eng-pipe-in"><strong>Input:</strong> 29 raw scores from Criteria Corp (13 personality + 12 composites + 4 meta)</div>
              <div class="eng-pipe-out"><strong>Output:</strong> epp_scores JSON in tory_learner_profiles</div>
            </div>
            <div class="eng-pipe-detail">
              <code>tory_get_learner_data(nx_user_id)</code>
              <p>Fetches EPP scores from epp_scores table, onboarding Q&A from user_onboarding_qa, existing profile if any, current roadmap, backpack interactions, ratings, and task completions.</p>
            </div>
          </div>
        </div>

        <div class="eng-pipe-arrow"></div>

        <div class="eng-pipe-step">
          <div class="eng-pipe-num">2</div>
          <div class="eng-pipe-card">
            <div class="eng-pipe-title">Profile Interpretation</div>
            <div class="eng-pipe-io">
              <div class="eng-pipe-in"><strong>Input:</strong> Raw EPP scores + Q&A answers</div>
              <div class="eng-pipe-out"><strong>Output:</strong> Trait vector, strengths[], gaps[], motivation cluster, narrative</div>
            </div>
            <div class="eng-pipe-detail">
              <code>tory_interpret_profile(nx_user_id)</code>
              <p>Classifies each trait as strength (> 70) or gap (< 30). Middle range (30-70) excluded. Generates profile_narrative text and motivation_cluster tags. Stores in tory_learner_profiles.</p>
              <div class="eng-formula-box">
                <pre class="eng-formula-math">for trait, score in epp_scores:
  if score > 70: strengths.append({trait, score, type: "strength"})
  elif score < 30: gaps.append({trait, score, type: "gap"})

learning_style = derived from Q&A answers
motivation_cluster = ["career_advance", "personal_growth", ...]</pre>
              </div>
            </div>
          </div>
        </div>

        <div class="eng-pipe-arrow"></div>

        <div class="eng-pipe-step">
          <div class="eng-pipe-num">3</div>
          <div class="eng-pipe-card">
            <div class="eng-pipe-title">Content Scoring</div>
            <div class="eng-pipe-io">
              <div class="eng-pipe-in"><strong>Input:</strong> Learner profile + all tory_content_tags</div>
              <div class="eng-pipe-out"><strong>Output:</strong> Ranked list of {lesson_id, score, gap_contrib, strength_contrib, matching_traits}</div>
            </div>
            <div class="eng-pipe-detail">
              <code>tory_score_content(nx_user_id)</code>
              <p>For each tagged lesson, computes match_score using the pedagogy-weighted formula. Returns sorted by score descending.</p>
            </div>
          </div>
        </div>

        <div class="eng-pipe-arrow"></div>

        <div class="eng-pipe-step">
          <div class="eng-pipe-num">4</div>
          <div class="eng-pipe-card">
            <div class="eng-pipe-title">Sequencing & Diversity</div>
            <div class="eng-pipe-io">
              <div class="eng-pipe-in"><strong>Input:</strong> Scored lessons + journey mapping</div>
              <div class="eng-pipe-out"><strong>Output:</strong> Ordered path of max 20 lessons with adjusted_score</div>
            </div>
            <div class="eng-pipe-detail">
              <code>apply_sequencing(scored_lessons)</code>
              <p>4-phase pipeline: diminishing returns (0.7^n) -> journey diversity (max 3 consecutive) -> fill deferred -> gap/strength interleaving (max 3 streak).</p>
            </div>
          </div>
        </div>

        <div class="eng-pipe-arrow"></div>

        <div class="eng-pipe-step">
          <div class="eng-pipe-num">5</div>
          <div class="eng-pipe-card">
            <div class="eng-pipe-title">Discovery Marking + Rationale</div>
            <div class="eng-pipe-io">
              <div class="eng-pipe-in"><strong>Input:</strong> Sequenced path</div>
              <div class="eng-pipe-out"><strong>Output:</strong> Path with is_discovery flags + match_rationale text</div>
            </div>
            <div class="eng-pipe-detail">
              <code>generate_rationale(lesson)</code>
              <p>First 5 lessons get discovery framing. Each lesson gets a template-based rationale referencing specific EPP dimensions by name. Stored in tory_recommendations.match_rationale.</p>
            </div>
          </div>
        </div>

        <div class="eng-pipe-arrow"></div>

        <div class="eng-pipe-step">
          <div class="eng-pipe-num">6</div>
          <div class="eng-pipe-card">
            <div class="eng-pipe-title">Coach Compatibility + Persistence</div>
            <div class="eng-pipe-io">
              <div class="eng-pipe-in"><strong>Input:</strong> Learner EPP + coach_id</div>
              <div class="eng-pipe-out"><strong>Output:</strong> Traffic light signal + all data to tory_recommendations + tory_coach_flags</div>
            </div>
            <div class="eng-pipe-detail">
              <code>tory_generate_path(nx_user_id, coach_id)</code>
              <p>Main entry point orchestrating steps 2-5. Also computes coach compatibility (green/yellow/red). Writes everything to DB. Returns full path with rationale.</p>
            </div>
          </div>
        </div>
      </div>

      <h2 class="eng-section-title" style="margin-top:32px">Reassessment Pipeline</h2>
      <div class="eng-reassess-flow">
        <div class="eng-reassess-card">
          <h3>Quarterly EPP</h3>
          <p>Full Criteria Corp retake every ${THRESHOLDS.quarterlyDays} days. New scores trigger drift calculation. If drift >= ${THRESHOLDS.driftThreshold}%, path is re-ranked.</p>
          <code>tory_schedule_quarterly_epp()</code>
        </div>
        <div class="eng-reassess-card">
          <h3>Mini Assessment</h3>
          <p>${THRESHOLDS.miniQuestionRange} targeted questions mid-lesson. Stored as type=mini reassessment. Computes profile adjustments per-trait.</p>
          <code>tory_mini_assessment(responses)</code>
        </div>
        <div class="eng-reassess-card">
          <h3>Passive Signals</h3>
          <p>After ${THRESHOLDS.backpackSignals} new backpack/rating/task interactions, aggregates engagement patterns. Derives implicit trait shifts from behavioral data.</p>
          <code>tory_check_passive_signals()</code>
        </div>
      </div>

      <h2 class="eng-section-title" style="margin-top:32px">Content Tagging Pipeline</h2>
      <div class="eng-pipeline-flow" style="flex-direction:row;flex-wrap:wrap;gap:16px">
        <div class="eng-pipe-mini">
          <strong>L1: Extract</strong><br>Text from all slide types (68 types supported)
        </div>
        <div class="eng-pipe-mini-arrow"></div>
        <div class="eng-pipe-mini">
          <strong>L2: Claude Opus</strong><br>Single API call extracts 15 fields per lesson
        </div>
        <div class="eng-pipe-mini-arrow"></div>
        <div class="eng-pipe-mini">
          <strong>L2b: Second Pass</strong><br>Agreement scoring with different frame
        </div>
        <div class="eng-pipe-mini-arrow"></div>
        <div class="eng-pipe-mini">
          <strong>L3: Confidence Gate</strong><br>&ge; ${THRESHOLDS.autoApproveConfidence}% auto-approve, &lt; ${THRESHOLDS.needsReviewConfidence}% needs review
        </div>
        <div class="eng-pipe-mini-arrow"></div>
        <div class="eng-pipe-mini">
          <strong>L4: FAISS Embed</strong><br>Semantic chunks to shared vector index
        </div>
      </div>
    </div>
  `;
}

// ── EPP DIMENSIONS TAB ──────────────────────────────────────────────────

function _renderEPP(el) {
  el.innerHTML = `
    <div class="eng-epp">
      <h2 class="eng-section-title">13 Personality Dimensions</h2>
      <p class="eng-epp-intro">These are the core EPP (Employee Personality Profile) dimensions from Criteria Corp. Each dimension is scored 0-100 as a percentile.</p>

      <div class="eng-epp-grid">
        ${EPP_DIMENSIONS.map((d, i) => `
          <div class="eng-epp-card">
            <div class="eng-epp-card-header">
              <span class="eng-epp-num">${i + 1}</span>
              <span class="eng-epp-trait">${_esc(d.trait)}</span>
            </div>
            <p class="eng-epp-desc">${_esc(d.desc)}</p>
            <div class="eng-epp-threshold">${_esc(d.threshold)}</div>
          </div>
        `).join('')}
      </div>

      <h2 class="eng-section-title" style="margin-top:32px">12 Job Fit Composites</h2>
      <p class="eng-epp-intro">Composite scores derived from personality dimensions. Used for role-specific matching.</p>
      <div class="eng-composite-pills">
        ${JOB_COMPOSITES.map(c => `<span class="eng-composite-pill">${_esc(c)}</span>`).join('')}
      </div>

      <h2 class="eng-section-title" style="margin-top:32px">Tension Pairs (Coaching Alerts)</h2>
      <p class="eng-epp-intro">When specific trait combinations appear in a learner's profile, the engine flags these as coaching opportunities.</p>

      <div class="eng-tension-grid">
        ${TENSION_PAIRS.map(t => `
          <div class="eng-tension-card">
            <div class="eng-tension-header">
              <span class="eng-tension-alert">${_esc(t.alert)}</span>
            </div>
            <div class="eng-tension-pair">
              <span class="eng-tension-high">High ${_esc(t.high)}</span>
              <span class="eng-tension-plus">+</span>
              <span class="eng-tension-low">Low ${_esc(t.low)}</span>
            </div>
            <p class="eng-tension-desc">${_esc(t.desc)}</p>
          </div>
        `).join('')}
      </div>

      <h2 class="eng-section-title" style="margin-top:32px">Content-Trait Mapping Directions</h2>
      <div class="eng-direction-grid">
        <div class="eng-direction-card builds">
          <div class="eng-direction-name">Builds</div>
          <div class="eng-direction-desc">Lesson directly develops this trait. Example: Assertiveness training lesson -> Assertiveness (builds). The lesson teaches skills that grow this dimension.</div>
        </div>
        <div class="eng-direction-card leverages">
          <div class="eng-direction-name">Leverages</div>
          <div class="eng-direction-desc">Lesson requires this trait to fully engage. Example: Group role-play exercise -> Extroversion (leverages). High scorers thrive; low scorers may struggle.</div>
        </div>
        <div class="eng-direction-card challenges">
          <div class="eng-direction-name">Challenges</div>
          <div class="eng-direction-desc">Lesson is uncomfortable for extreme scorers. Example: "Say No" exercise -> Cooperativeness (challenges). Very high scorers will find this difficult but growth-producing.</div>
        </div>
      </div>
    </div>
  `;
}

// ── MCP TOOLS TAB ──────────────────────────────────────────────────────────

function _renderTools(el) {
  const tools = [
    { category: 'Core Pipeline', items: [
      { name: 'tory_get_learner_data', desc: 'Fetch all available data for a learner: EPP scores, onboarding Q&A, existing profile, current roadmap, backpack interactions, ratings, and task completions.', input: 'nx_user_id', output: 'Comprehensive data package' },
      { name: 'tory_interpret_profile', desc: 'Parse EPP scores and Q&A answers. Produces trait vector, motivation cluster, strengths, gaps, and profile narrative. Stores in tory_learner_profiles.', input: 'nx_user_id', output: 'Structured profile with trait vector' },
      { name: 'tory_score_content', desc: 'Score all tagged lessons against learner profile using pedagogy-weighted formula. Returns ranked list with match scores and trait explanations.', input: 'nx_user_id, max_lessons', output: 'Ranked lessons with scores' },
      { name: 'tory_generate_roadmap', desc: 'Create discovery phase (3-5 exploratory lessons) or full path. Stores in tory_roadmaps + tory_roadmap_items.', input: 'nx_user_id, mode (discovery|full)', output: 'Roadmap with items' },
      { name: 'tory_generate_path', desc: 'Main entry point. Loads profile, scores content via weighted formula, applies diversity rules, generates top-N recommendations with rationale, marks discovery phase, computes coach compatibility.', input: 'nx_user_id, coach_id?, max_recommendations', output: 'Full path + coach flags' },
      { name: 'tory_check_coach_compatibility', desc: 'Traffic light signal (green/yellow/red) based on EPP heuristics. Checks for extreme scores that need specific coaching attention.', input: 'nx_user_id, coach_id', output: 'Signal + warnings' },
    ]},
    { category: 'Learner Data Access', items: [
      { name: 'tory_get_roadmap', desc: 'Current roadmap with all items, completion status, and coach overrides.', input: 'nx_user_id', output: 'Roadmap + items' },
      { name: 'tory_get_progress', desc: 'Completion percentage, engagement score, path changes, coach overrides, and recommendations.', input: 'nx_user_id', output: 'Progress summary' },
      { name: 'tory_get_path', desc: 'Full ordered learning path. Source field distinguishes tory (algorithm) vs coach (manually modified). Divergence detection at 30%.', input: 'nx_user_id', output: 'Ordered recommendations' },
    ]},
    { category: 'Coach Controls', items: [
      { name: 'tory_coach_reorder', desc: 'Reorder lessons in path. Accepts ordering array. Logs path_event with type=reordered. Locked items cannot be moved.', input: 'nx_user_id, coach_id, ordering[], reason', output: 'Updated path' },
      { name: 'tory_coach_swap', desc: 'Replace a lesson. Removes one, adds another. Logs type=swapped. Locked items cannot be swapped out.', input: 'nx_user_id, coach_id, remove_id, add_id, reason', output: 'Updated path' },
      { name: 'tory_coach_lock', desc: 'Lock a recommendation. Locked items survive future Tory re-ranking. Sets source=coach.', input: 'nx_user_id, coach_id, recommendation_id, reason', output: 'Locked confirmation' },
    ]},
    { category: 'Reassessment Engine', items: [
      { name: 'tory_schedule_quarterly_epp', desc: 'Schedule quarterly EPP retake via Criteria Corp API. Creates pending reassessment. Computes drift on return. Falls back to mini-assessment after 3 retries.', input: 'nx_user_id', output: 'Reassessment record' },
      { name: 'tory_mini_assessment', desc: 'Process 3-5 mid-lesson questions. Stores as type=mini. Computes per-trait adjustments. Triggers re-ranking if drift exceeds threshold.', input: 'nx_user_id, responses[]', output: 'Profile update + drift' },
      { name: 'tory_check_passive_signals', desc: 'Aggregates backpack saves, ratings, task completions. If threshold (10) crossed, derives implicit trait shifts.', input: 'nx_user_id', output: 'Signal summary + possible drift' },
      { name: 'tory_reassessment_status', desc: 'History of all reassessments: completed, pending, upcoming. Shows drift data and scheduling.', input: 'nx_user_id', output: 'Reassessment timeline' },
    ]},
    { category: 'Content Review', items: [
      { name: 'tory_list_content_tags', desc: 'List all content tags or tags for a specific lesson. Shows trait tags, confidence, review status.', input: 'nx_lesson_id?, review_status?', output: 'Tag list' },
      { name: 'tory_review_queue', desc: 'Pending content tags for coach review. Ordered by confidence ascending (lowest first). Supports pagination.', input: 'offset, limit, status_filter', output: 'Queue items' },
      { name: 'tory_review_approve', desc: 'Approve a content tag. Sets review_status=approved. Records reviewer.', input: 'tag_id, reviewer_id', output: 'Confirmation' },
      { name: 'tory_review_correct', desc: 'Update trait tags with corrected values. Stores original in review_notes. Sets status=corrected.', input: 'tag_id, reviewer_id, corrected_tags[]', output: 'Updated tag' },
      { name: 'tory_review_dismiss', desc: 'Remove from queue without modifying tags. For irrelevant or needs-retag items.', input: 'tag_id, reviewer_id', output: 'Dismissed' },
      { name: 'tory_review_bulk_approve', desc: 'Batch approve all tags matching criteria. Default: confidence >= 70%.', input: 'reviewer_id, min_confidence', output: 'Count approved' },
      { name: 'tory_review_queue_stats', desc: 'Queue analytics: total pending, reviewed today, avg confidence, distribution.', input: 'none', output: 'Stats object' },
    ]},
    { category: 'Admin & Analytics', items: [
      { name: 'tory_set_pedagogy', desc: 'Set pedagogy mode per client company. Options: gap_fill (A), strength_lead (B), balanced (C).', input: 'client_id, mode, gap_ratio?, strength_ratio?', output: 'Config saved' },
      { name: 'tory_dashboard_snapshot', desc: 'Progress snapshot for HR. Single user or aggregate for department/client.', input: 'nx_user_id? | client_id? | department_id?', output: 'Snapshot data' },
    ]},
  ];

  el.innerHTML = `
    <div class="eng-tools">
      <h2 class="eng-section-title">Tory Engine MCP Tools (${tools.reduce((a, c) => a + c.items.length, 0)} tools)</h2>
      <p class="eng-tools-intro">Every tool is callable via the MCP (Model Context Protocol) server. Each tool is auditable — inputs and outputs are stored in session state.</p>

      ${tools.map(cat => `
        <div class="eng-tool-category">
          <h3 class="eng-tool-cat-title">${_esc(cat.category)} <span class="eng-tool-cat-count">${cat.items.length}</span></h3>
          <div class="eng-tool-list">
            ${cat.items.map(t => `
              <div class="eng-tool-card">
                <div class="eng-tool-name"><code>${_esc(t.name)}</code></div>
                <div class="eng-tool-desc">${_esc(t.desc)}</div>
                <div class="eng-tool-io">
                  <span class="eng-tool-in">In: ${_esc(t.input)}</span>
                  <span class="eng-tool-out">Out: ${_esc(t.output)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

// ── TRACE TAB ──────────────────────────────────────────────────────────────

function _renderTrace(el) {
  el.innerHTML = `
    <div class="eng-trace">
      <h2 class="eng-section-title">Pipeline Trace</h2>
      <p class="eng-trace-intro">Select a learner to see the complete scoring trace — every step from EPP input to final path output.</p>

      <div class="eng-trace-search">
        <select id="eng-trace-select" class="eng-trace-select">
          <option value="">-- Select a learner --</option>
        </select>
        <button class="eng-btn eng-btn-primary" id="eng-trace-go">Load Trace</button>
      </div>

      <div id="eng-trace-result">
        ${_pipelineData ? _renderPipelineResult() : '<div class="eng-trace-empty">Select a learner above to load their pipeline trace</div>'}
      </div>
    </div>
  `;

  // Load users for dropdown
  _loadTraceUsers(el);

  el.querySelector('#eng-trace-go')?.addEventListener('click', () => _loadTrace(el));
  el.querySelector('#eng-trace-select')?.addEventListener('change', (e) => {
    if (e.target.value) _loadTrace(el);
  });
}

async function _loadTraceUsers(el) {
  const select = el.querySelector('#eng-trace-select');
  if (!select) return;

  if (_availableUsers) {
    _populateUserDropdown(select);
    return;
  }

  try {
    _availableUsers = await api.getEngineUsers();
    _populateUserDropdown(select);
  } catch (err) {
    select.innerHTML = '<option value="">Failed to load users</option>';
  }
}

function _populateUserDropdown(select) {
  if (!_availableUsers || !_availableUsers.length) {
    select.innerHTML = '<option value="">No profiled users found</option>';
    return;
  }

  const withPath = _availableUsers.filter(u => parseInt(u.path_lessons) > 0);
  const withoutPath = _availableUsers.filter(u => !parseInt(u.path_lessons));

  let html = '<option value="">-- Select a learner --</option>';

  if (withPath.length) {
    html += '<optgroup label="With Generated Path">';
    for (const u of withPath) {
      const name = (u.name || '').trim() || `User ${u.nx_user_id}`;
      const sel = _pipelineUser == u.nx_user_id ? ' selected' : '';
      html += `<option value="${u.nx_user_id}"${sel}>${name} (#${u.nx_user_id}) — ${u.path_lessons} lessons, ${u.confidence}% conf</option>`;
    }
    html += '</optgroup>';
  }

  if (withoutPath.length) {
    html += `<optgroup label="Profile Only (${withoutPath.length} users)">`;
    for (const u of withoutPath.slice(0, 50)) {
      const name = (u.name || '').trim() || `User ${u.nx_user_id}`;
      const sel = _pipelineUser == u.nx_user_id ? ' selected' : '';
      html += `<option value="${u.nx_user_id}"${sel}>${name} (#${u.nx_user_id}) — ${u.confidence}% conf</option>`;
    }
    if (withoutPath.length > 50) {
      html += `<option disabled>... and ${withoutPath.length - 50} more</option>`;
    }
    html += '</optgroup>';
  }

  select.innerHTML = html;
}

async function _loadTrace(el) {
  const select = el.querySelector('#eng-trace-select');
  const userId = parseInt(select?.value, 10);
  if (!userId) { showToast('Select a learner first', 'error'); return; }

  const resultEl = el.querySelector('#eng-trace-result');
  if (resultEl) resultEl.innerHTML = '<div class="eng-loading"><div class="eng-spinner"></div> Loading pipeline trace...</div>';

  try {
    _pipelineData = await api.getEnginePipeline(userId);
    _pipelineUser = userId;
    if (resultEl) resultEl.innerHTML = _renderPipelineResult();
  } catch (err) {
    if (resultEl) resultEl.innerHTML = `<div class="eng-error">Failed: ${_esc(err.message)}</div>`;
  }
}

function _renderPipelineResult() {
  if (!_pipelineData) return '';
  const d = _pipelineData;
  const profile = d.profile || {};
  const recs = d.recommendations || [];
  const reassessments = d.reassessments || [];
  const flag = d.coach_flag || {};
  const events = d.path_events || [];

  // Parse JSON fields
  let eppSummary = {}, strengths = [], gaps = [];
  try { eppSummary = typeof profile.epp_summary === 'string' ? JSON.parse(profile.epp_summary) : (profile.epp_summary || {}); } catch(e) {}
  try { strengths = typeof profile.strengths === 'string' ? JSON.parse(profile.strengths) : (profile.strengths || []); } catch(e) {}
  try { gaps = typeof profile.gaps === 'string' ? JSON.parse(profile.gaps) : (profile.gaps || []); } catch(e) {}

  const sortedEpp = Object.entries(eppSummary).sort((a, b) => b[1] - a[1]);

  return `
    <div class="eng-trace-result">
      <!-- Profile -->
      <div class="eng-trace-section">
        <h3>Step 1-2: Profile (User #${d.user_id})</h3>
        <div class="eng-trace-meta">
          <span>Version: ${profile.version || 1}</span>
          <span>Source: ${_esc(profile.source || 'initial')}</span>
          <span>Confidence: ${profile.confidence || 0}%</span>
          <span>Style: ${_esc(profile.learning_style || 'unknown')}</span>
          <span>Created: ${_esc(profile.created_at || '')}</span>
        </div>
        ${profile.profile_narrative ? `<div class="eng-trace-narrative">${_esc(profile.profile_narrative)}</div>` : ''}

        <div class="eng-trace-epp-grid">
          ${sortedEpp.map(([trait, score]) => {
            const isGap = score < 30;
            const isStr = score > 70;
            return `<div class="eng-trace-epp-row ${isGap ? 'gap' : isStr ? 'strength' : ''}">
              <span class="eng-trace-epp-trait">${_esc(trait)}</span>
              <div class="eng-trace-epp-bar"><div class="eng-trace-epp-fill" style="width:${score}%"></div></div>
              <span class="eng-trace-epp-score">${score}</span>
            </div>`;
          }).join('')}
        </div>

        <div class="eng-trace-sg">
          <div class="eng-trace-sg-col">
            <h4>Strengths (> 70)</h4>
            ${strengths.map(s => `<span class="eng-trace-tag strength">${_esc(s.trait)} ${s.score}</span>`).join('') || '<span class="eng-trace-none">None</span>'}
          </div>
          <div class="eng-trace-sg-col">
            <h4>Gaps (< 30)</h4>
            ${gaps.map(g => `<span class="eng-trace-tag gap">${_esc(g.trait)} ${g.score}</span>`).join('') || '<span class="eng-trace-none">None</span>'}
          </div>
        </div>
      </div>

      <!-- Coach Flag -->
      ${flag.signal ? `
        <div class="eng-trace-section">
          <h3>Step 6: Coach Compatibility</h3>
          <div class="eng-trace-flag ${flag.signal}">
            <span class="eng-trace-flag-light"></span>
            <span class="eng-trace-flag-signal">${flag.signal.toUpperCase()}</span>
            <span class="eng-trace-flag-msg">${_esc(flag.message || '')}</span>
          </div>
        </div>
      ` : ''}

      <!-- Recommendations -->
      <div class="eng-trace-section">
        <h3>Steps 3-5: Scored & Sequenced Path (${recs.length} lessons)</h3>
        <div class="eng-trace-recs">
          <table class="eng-trace-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Lesson</th>
                <th>Match</th>
                <th>Adj.</th>
                <th>Gap</th>
                <th>Str</th>
                <th>Discovery</th>
                <th>Source</th>
                <th>Lock</th>
                <th>Conf</th>
                <th>Matching Traits</th>
              </tr>
            </thead>
            <tbody>
              ${recs.map(r => {
                let traits = [];
                try { traits = typeof r.matching_traits === 'string' ? JSON.parse(r.matching_traits) : (r.matching_traits || []); } catch(e) {}
                const isDisc = r.is_discovery === '1' || r.is_discovery === 1 || r.is_discovery === true;
                const isLocked = r.locked_by_coach === '1' || r.locked_by_coach === 1;
                return `<tr class="${isDisc ? 'discovery' : ''} ${isLocked ? 'locked' : ''}">
                  <td>${r.sequence}</td>
                  <td class="eng-trace-lesson">${_esc(r.lesson_name || `Lesson ${r.nx_lesson_id}`)}</td>
                  <td class="eng-trace-score">${r.match_score}</td>
                  <td>${r.adjusted_score || '-'}</td>
                  <td>${r.gap_contribution || '-'}</td>
                  <td>${r.strength_contribution || '-'}</td>
                  <td>${isDisc ? 'Yes' : ''}</td>
                  <td><span class="eng-trace-src ${r.source || 'tory'}">${r.source || 'tory'}</span></td>
                  <td>${isLocked ? 'Locked' : ''}</td>
                  <td>${r.confidence || r.tag_confidence || '-'}</td>
                  <td class="eng-trace-traits">${traits.map(t => `<span class="eng-trace-trait-pill ${t.type || ''}">${_esc(t.trait)}</span>`).join('')}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Reassessments -->
      ${reassessments.length > 0 ? `
        <div class="eng-trace-section">
          <h3>Reassessment History</h3>
          <div class="eng-trace-reassess">
            ${reassessments.map(r => {
              let delta = {};
              try { delta = typeof r.result_delta === 'string' ? JSON.parse(r.result_delta) : (r.result_delta || {}); } catch(e) {}
              return `<div class="eng-trace-reassess-card">
                <div class="eng-trace-reassess-header">
                  <span class="eng-trace-reassess-type">${_esc(r.type)}</span>
                  <span class="eng-trace-reassess-date">${_esc(r.created_at || '')}</span>
                  <span class="eng-trace-reassess-status ${r.status}">${_esc(r.status || '')}</span>
                  ${r.drift_detected === '1' ? '<span class="eng-trace-drift-badge">Drift Detected</span>' : ''}
                  ${r.path_action === 'reranked' ? '<span class="eng-trace-rerank-badge">Path Re-ranked</span>' : ''}
                </div>
                ${delta.drift_pct ? `<div class="eng-trace-reassess-drift">Drift: ${delta.drift_pct}%</div>` : ''}
              </div>`;
            }).join('')}
          </div>
        </div>
      ` : ''}

      <!-- Path Events -->
      ${events.length > 0 ? `
        <div class="eng-trace-section">
          <h3>Coach Path Events</h3>
          ${events.map(e => `
            <div class="eng-trace-event">
              <span class="eng-trace-event-type">${_esc(e.event_type)}</span>
              <span class="eng-trace-event-date">${_esc(e.created_at || '')}</span>
              <span class="eng-trace-event-detail">${_esc(e.details || '')}</span>
            </div>
          `).join('')}
        </div>
      ` : ''}
    </div>
  `;
}

// ── Helpers ──────────────────────────────────────────────────────────────

function _statCard(title, value, subtitle, color) {
  return `
    <div class="eng-stat-card" style="border-top:3px solid ${color}">
      <div class="eng-stat-value" style="color:${color}">${value}</div>
      <div class="eng-stat-title">${title}</div>
      <div class="eng-stat-sub">${subtitle}</div>
    </div>
  `;
}

function _renderDistChart(data, color) {
  if (!data || data.length === 0) return '<div class="eng-no-data">No data yet</div>';
  const max = Math.max(...data.map(d => parseInt(d.count) || 0), 1);
  return `<div class="eng-dist-chart">
    ${data.map(d => {
      const pct = Math.round((parseInt(d.count) || 0) / max * 100);
      return `<div class="eng-dist-bar-wrap">
        <div class="eng-dist-bar" style="height:${pct}%;background:${color}"></div>
        <div class="eng-dist-label">${d.bucket}</div>
        <div class="eng-dist-count">${d.count}</div>
      </div>`;
    }).join('')}
  </div>`;
}

function _pedagogyLabel(mode) {
  if (mode === 'gap_fill') return 'Mode A: Gap Fill';
  if (mode === 'strength_lead') return 'Mode B: Strength Lead';
  return 'Mode C: Balanced';
}

function _humanizeKey(key) {
  return key.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase()).trim();
}

function _esc(str) {
  if (str == null) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}
