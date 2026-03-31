# MyNextory CoachAI
## Intelligent Coaching & Personalized Learning Platform

| | |
|---|---|
| **Prepared by** | ThoughtWire |
| **Prepared for** | MyNextory Leadership |
| **Date** | March 2026 |
| **Version** | 1.0 — Scope & Capability Document |
| **Classification** | Confidential |

---

## 1. Executive Summary

MyNextory has built a strong foundation — a content-rich learning platform with journeys, lessons, and a dedicated coaching network serving corporate learners. The opportunity now is to transform this into an **AI-powered personalized coaching engine** that matches the right content to the right learner at the right time.

**CoachAI** is ThoughtWire's proposed intelligence layer that sits on top of MyNextory's existing platform. It uses personality assessment data (EPP), learner behavior signals, and AI-driven content analysis to create individualized learning paths — dramatically reducing the manual effort coaches spend on path planning while improving learner outcomes.

**The core promise:** Every learner gets a path as thoughtful as if a master coach spent hours studying their personality, strengths, and gaps — delivered automatically, refined continuously, and always explainable to both the learner and their coach.

---

## 2. Current State Assessment

### What MyNextory Has Today

| Asset | Details |
|-------|---------|
| **Content Library** | 16 journeys, 46 chapters, 90 lessons, 600+ interactive slides (video, quizzes, reflections, scenarios) |
| **Learner Base** | 1,500+ registered users across 37 corporate clients |
| **Coaching Network** | 5 active coaches managing learner relationships |
| **EPP Assessments** | 400+ learners have completed the Criteria Corp Employee Personality Profile (25 dimensions) |
| **Engagement Data** | 8,000+ backpack saves, 3,300+ ratings, 2,800+ tasks, 67,000+ activity log entries |
| **Onboarding Q&A** | Rich qualitative data — learners share motivations, goals, and self-assessments during onboarding |

### Where the Gaps Are

1. **No personalization** — All learners see the same content in the same order, regardless of their personality, strengths, or goals
2. **EPP data is underutilized** — Assessments are collected but not systematically connected to content recommendations
3. **Coach bottleneck** — Coaches manually decide which lessons to assign, creating inconsistency and limiting scale
4. **No adaptive learning** — The system doesn't respond to learner progress, engagement patterns, or changing needs
5. **Limited analytics** — HR leaders lack visibility into cohort progress, content effectiveness, and coaching ROI
6. **Content is untagged** — Lessons aren't mapped to competencies, difficulty levels, or learning styles, making intelligent matching impossible

### The Untapped Goldmine

MyNextory is sitting on exceptionally rich data: personality profiles, behavioral signals, coach observations, and qualitative self-reflections. This data, when properly analyzed and connected, can power a level of personalization that very few learning platforms achieve.

---

## 3. Proposed Solution: CoachAI

### Vision

CoachAI transforms MyNextory from a content delivery platform into an **intelligent coaching partner** that understands each learner as an individual.

### How It Works

> **Step 1 — Learner Assessment**
> Learner takes EPP Assessment + answers onboarding questions
>
> **Step 2 — Profile Intelligence**
> AI analyzes personality across 25 dimensions. Identifies strengths, growth areas, learning style. Generates a human-readable personality narrative.
>
> **Step 3 — Content Intelligence**
> AI independently analyzes every lesson in the library. Tags each with: traits it builds, difficulty, style, emotional tone, coaching prompts, prerequisites.
>
> **Step 4 — Matching Engine**
> Scores every lesson against the learner's profile. Factors in: gap-filling, strength-building, pedagogy mode. Applies diversity rules for balanced, engaging paths.
>
> **Step 5 — Personalized Roadmap**
> 20-lesson personalized learning path generated. First 3-5 lessons = low-commitment "discovery" phase. Coach reviews, adjusts, and locks specific items.
>
> **Step 6 — Continuous Adaptation**
> System monitors engagement: saves, ratings, completions. Triggers reassessment when patterns shift. Path re-ranks automatically — coach notified.

### Key Design Principles

- **Coach-augmented, not coach-replaced** — AI handles the analysis and sequencing; coaches bring human judgment, relationship, and override authority
- **Explainable recommendations** — Every lesson comes with a rationale: "This lesson builds Assertiveness (your growth area at 12th percentile) while leveraging your strength in Achievement (78th percentile)"
- **Configurable pedagogy** — Different organizations can choose gap-filling (remedial focus), strength-leading (amplify what's working), or balanced approaches
- **Continuous adaptation** — The system learns from engagement signals, coach overrides, and periodic reassessments
- **Human review gates** — AI-generated content tags go through a confidence-gated review queue before influencing recommendations

---

## 4. Full Capability Map

### 4.1 Learner Intelligence

| Capability | Description |
|------------|-------------|
| **EPP Profile Interpretation** | Parse 25-dimension personality assessment into structured profiles with strengths, gaps, and narrative summaries |
| **Motivation Cluster Analysis** | Extract motivation drivers from onboarding Q&A (intrinsic vs. extrinsic, career growth vs. personal development) |
| **Learning Style Inference** | Determine preferred learning modality (visual, reflective, active, theoretical) from personality traits and behavior |
| **Tension Pair Detection** | Identify psychologically significant trait combinations (e.g., high Achievement + low SelfConfidence = imposter syndrome risk) |
| **Strength & Gap Mapping** | Quantified identification of top strengths (>70th percentile) and developmental areas (<30th percentile) |
| **Profile Versioning** | Track how a learner's profile evolves over time through reassessments |

### 4.2 Content Intelligence

| Capability | Description |
|------------|-------------|
| **AI Content Tagging** | Analyze every lesson's slide content to extract trait associations, difficulty, learning style, prerequisites, and emotional tone |
| **Multi-Pass Confidence Scoring** | Two independent AI analyses per lesson, with agreement scoring to ensure tag quality |
| **Confidence-Gated Review** | Auto-approve high-confidence tags (>75%), flag low-confidence (<50%) for human review, queue moderate ones |
| **Content-Trait Mapping** | Map each lesson to EPP dimensions with directional tags: "builds" (develops the trait), "leverages" (requires the trait), "challenges" (stretches the trait) |
| **Semantic Content Search** | AI-powered search across all lesson content — find lessons by meaning, not just keywords |
| **Slide-Level Analysis** | Per-slide breakdown of content type, engagement potential, and instructional approach |
| **Coaching Prompt Generation** | AI-generated discussion starters for coaches to use with each lesson |
| **Content Quality Scoring** | Automated assessment of lesson relevance, depth, and instructional design quality |
| **Pair Recommendations** | Identify which lessons work well together (complementary topics, progressive difficulty) |

### 4.3 Personalized Path Engine

| Capability | Description |
|------------|-------------|
| **Content-Learner Matching** | Score every lesson against each learner's profile using trait-based similarity matching |
| **Configurable Pedagogy Modes** | Three modes: Gap-Fill (70% remedial / 30% strength), Strength-Lead (30% / 70%), Balanced (custom ratio) — configurable per organization |
| **Intelligent Sequencing** | Apply diversity rules: max 3 consecutive same-journey lessons, diminishing returns on repeated traits, interleaved gap/strength content |
| **Discovery Phase** | First 3-5 lessons use softer, exploratory framing — lets learners ease in before deeper commitment |
| **20-Lesson Roadmap Generation** | Curated sequence with match scores, rationale, and trait coverage for each item |
| **Match Rationale** | Human-readable explanation for every recommendation ("Why this lesson for this learner") |

### 4.4 Coach Empowerment

| Capability | Description |
|------------|-------------|
| **Coach Compatibility Signals** | Traffic-light assessment (Green / Yellow / Red) of coach-learner fit based on personality alignment |
| **Path Curation Tools** | Coaches can reorder, swap, and lock lessons — overrides persist through AI re-rankings |
| **Divergence Detection** | When >30% of a path is coach-modified, system flags it as "coach insight" for review — not blocked, but noted |
| **Override Audit Trail** | Every coach decision (swap, lock, reorder) is logged with rationale and timestamp |
| **Coach Workspace** | Dedicated interface: search learners, view profiles, edit paths, track sessions |
| **Curator AI Copilot** | AI assistant that coaches can converse with to understand a learner's profile, get suggestions, and explore "what-if" scenarios |

### 4.5 Continuous Adaptation

| Capability | Description |
|------------|-------------|
| **Quarterly EPP Reassessment** | Scheduled full personality re-evaluation — detects drift and triggers path re-ranking if >15% change |
| **Mini-Assessments** | Quick 3-5 question check-ins during the learning journey to capture real-time trait signals |
| **Passive Signal Monitoring** | Track backpack saves, ratings, task completions — aggregate patterns trigger automatic reassessment |
| **Profile Drift Detection** | Compare current vs. original assessment — quantify how much a learner has changed |
| **Automatic Path Re-Ranking** | When significant drift is detected, regenerate recommendations with updated profile — coach notified |
| **Learner Feedback Loop** | "This doesn't sound like me" buttons on profiles — direct signal for profile correction |

### 4.6 HR & Leadership Analytics

| Capability | Description |
|------------|-------------|
| **Cohort Dashboard** | Organization-wide view: all learners, their phases (profiled / discovery / active / reassessed), progress metrics |
| **EPP Heatmaps** | Visual trait distribution across the organization — identify company-wide strengths and gaps |
| **Engagement Funnels** | Track learner progression through platform stages with drop-off analysis |
| **Content Effectiveness** | Which lessons drive the most engagement, ratings, and backpack saves |
| **Coach Performance** | Learner progress under each coach, override frequency, path divergence rates |
| **Score Distribution** | How well the AI's recommendations match learner profiles across the cohort |
| **Export & Reporting** | CSV/PDF export of learner progress, cohort metrics, and coaching activity |
| **Department Filtering** | Slice all analytics by company, department, coach, or learner phase |

### 4.7 Learner Experience (Future Enhancement)

| Capability | Description |
|------------|-------------|
| **AI Companion Chat** | Conversational AI that helps learners reflect, quiz themselves, prepare for coaching sessions, and celebrate milestones |
| **Companion Modes** | Context-aware conversation: teach (explain concepts), quiz (test understanding), reflect (deepen learning), prepare (pre-session), celebrate (acknowledge wins) |
| **Personalized Greeting** | Companion opens with context-aware greetings based on learner's current path position and recent activity |
| **Interactive Content Viewer** | Rich slide viewer with video playback, interactive quizzes, and reflection prompts |
| **Mobile-Responsive Experience** | Full learning experience accessible on tablet and mobile devices |
| **Progress Visualization** | Visual representation of learning journey — where you are, where you're going, what you've accomplished |

### 4.8 Platform Intelligence

| Capability | Description |
|------------|-------------|
| **Lesson Impact Preview** | Before adding/removing a lesson from the catalog, preview how it would affect existing learner paths |
| **Content Gap Analysis** | Identify EPP dimensions that aren't well-served by the current content library — guide content creation |
| **Algorithm Observability** | Dashboard showing how the matching engine works: formulas, thresholds, EPP dimension weights, pipeline traces |
| **Batch Processing** | Process all untagged content in bulk — handle new content additions efficiently |
| **Review Queue Management** | Workflow for reviewing, approving, correcting, or dismissing AI-generated content tags |

---

## 5. Phase Breakdown

### Phase 1: Foundation & Data Intelligence
**Objective:** Understand the data, prepare the infrastructure, connect the EPP assessment layer.

| Deliverable | Description |
|-------------|-------------|
| Data Model Analysis | Map all existing tables, relationships, content hierarchies, and user data flows |
| Content Taxonomy Mapping | Document the journey > chapter > lesson > slide hierarchy with all 68 slide types |
| EPP Integration Architecture | Design the connection between Criteria Corp EPP data and the AI profiling engine |
| Database Optimization | Create indexes, views, and query patterns optimized for AI workloads |
| Schema Extensions | Design new tables for profiles, content tags, recommendations, coaching overrides, and reassessments |
| Infrastructure Setup | AI engine runtime, API layer, secure credential management |

| Metric | Value |
|--------|-------|
| **Complexity** | Medium |
| **Estimated Effort** | 120–160 hours |
| **Duration** | 3–4 weeks |
| **Deliverables** | Data model documentation, schema design, EPP integration spec, infrastructure ready |

---

### Phase 2: Learner Intelligence Engine
**Objective:** Turn raw EPP scores and onboarding data into rich, actionable learner profiles.

| Deliverable | Description |
|-------------|-------------|
| EPP Parser | Extract and normalize 25 personality dimensions from assessment data |
| Profile Interpretation Engine | AI-powered analysis that generates narrative profiles, identifies strengths/gaps, detects tension pairs |
| Motivation Analysis | Parse onboarding Q&A to classify motivation drivers and learning preferences |
| Learning Style Inference | Map personality traits to preferred learning modalities |
| Profile API | REST endpoints for generating, retrieving, and updating learner profiles |
| Batch Profiling | Process all 400+ existing EPP-assessed learners in bulk |
| Feedback System | "Not like me" mechanism for learners to flag inaccurate profiles |

| Metric | Value |
|--------|-------|
| **Complexity** | Heavy |
| **Estimated Effort** | 200–280 hours |
| **Duration** | 5–7 weeks |
| **Deliverables** | Profile engine, batch processing, 400+ learner profiles generated, feedback loop |
| **Depends On** | Phase 1 |

---

### Phase 3: Content Intelligence Pipeline
**Objective:** Analyze and tag every lesson in the library so the AI can match content to learners.

| Deliverable | Description |
|-------------|-------------|
| Content Analysis Pipeline | Multi-stage AI pipeline that extracts 15 structured fields from each lesson's slide content |
| Trait-Content Mapping | Tag every lesson with EPP dimensions it builds, leverages, or challenges — with confidence scores |
| Confidence Gating System | Auto-approve high-confidence tags, queue moderate ones for review, flag low-confidence for coaching input |
| Semantic Search Index | AI embeddings for all lesson content — enables meaning-based search across the library |
| Review Queue | Interface for coaches/admins to review, approve, correct, or dismiss AI-generated tags |
| Content Quality Assessment | Automated scoring of lesson relevance, depth, and instructional design |
| Bulk Processing | Tag all 90 lessons with full audit trail |

| Metric | Value |
|--------|-------|
| **Complexity** | Heavy |
| **Estimated Effort** | 240–320 hours |
| **Duration** | 6–8 weeks |
| **Deliverables** | Tagged content library, semantic search, review queue, quality scores |
| **Depends On** | Phase 1 |

---

### Phase 4: Personalized Path Engine & Coach Tools
**Objective:** Generate individualized learning paths and give coaches the tools to curate them.

| Deliverable | Description |
|-------------|-------------|
| Matching Algorithm | Score every lesson against each learner's profile using trait-based similarity with configurable pedagogy weights |
| Path Generation | Produce 20-lesson roadmaps with intelligent sequencing, diversity rules, and discovery phases |
| Pedagogy Configuration | Per-organization settings: gap-fill, strength-lead, or balanced — with custom ratios |
| Match Rationale Engine | Generate human-readable explanations for every recommendation |
| Coach Workspace | Dedicated interface for coaches to search learners, view profiles, and manage paths |
| Coach Curation Tools | Drag-and-drop reorder, lesson swap, lesson lock — all persisting through AI re-rankings |
| Coach Compatibility Engine | Traffic-light signals (Green/Yellow/Red) for coach-learner fit |
| Divergence Detection | Flag paths where >30% is coach-modified as "coach insight" |
| Curator AI Copilot | Conversational AI assistant for coaches to explore learner data and get suggestions |

| Metric | Value |
|--------|-------|
| **Complexity** | Heavy |
| **Estimated Effort** | 280–360 hours |
| **Duration** | 7–9 weeks |
| **Deliverables** | Path engine, coach workspace, curation tools, compatibility signals, AI copilot |
| **Depends On** | Phase 2, Phase 3 |

---

### Phase 5: Analytics, Adaptation & Learner Experience
**Objective:** Close the loop with continuous adaptation, leadership analytics, and the learner-facing AI companion.

| Deliverable | Description |
|-------------|-------------|
| HR Analytics Dashboard | Cohort overview, EPP heatmaps, engagement funnels, content effectiveness, department filtering |
| Quarterly Reassessment Engine | Scheduled EPP retakes with drift detection and automatic path re-ranking |
| Mini-Assessment System | Quick mid-journey check-ins to capture real-time learning signals |
| Passive Signal Monitoring | Aggregate engagement patterns (saves, ratings, completions) to trigger adaptive re-ranking |
| AI Companion | Conversational learning partner for learners: teach, quiz, reflect, prepare, celebrate modes |
| Content 360 View | Detailed lesson intelligence view: traits, difficulty, slides, coaching prompts, metadata |
| Algorithm Observability | Diagnostic dashboard: formulas, thresholds, pipeline traces, EPP dimension weights |
| Reporting & Export | CSV/PDF export of all metrics, learner progress, and coaching activity |
| Lesson Impact Preview | Dry-run tool: "what happens to learner paths if we add/remove this lesson?" |

| Metric | Value |
|--------|-------|
| **Complexity** | Medium–Heavy |
| **Estimated Effort** | 240–320 hours |
| **Duration** | 6–8 weeks |
| **Deliverables** | HR dashboard, reassessment engine, AI companion, reporting suite |
| **Depends On** | Phase 4 |

---

## 6. Consolidated Effort Summary

| Phase | Name | Complexity | Hours (Est.) | Duration | Dependencies |
|-------|------|-----------|-------------|----------|-------------|
| 1 | Foundation & Data Intelligence | Medium | 120–160 | 3–4 weeks | — |
| 2 | Learner Intelligence Engine | Heavy | 200–280 | 5–7 weeks | Phase 1 |
| 3 | Content Intelligence Pipeline | Heavy | 240–320 | 6–8 weeks | Phase 1 |
| 4 | Personalized Path Engine & Coach Tools | Heavy | 280–360 | 7–9 weeks | Phase 2, 3 |
| 5 | Analytics, Adaptation & Learner Experience | Medium–Heavy | 240–320 | 6–8 weeks | Phase 4 |
| | **Total** | | **1,080–1,440** | **27–36 weeks** | |

**Note:** Phases 2 and 3 can run in parallel after Phase 1 completes, reducing the overall timeline to approximately **22–30 weeks**.

---

## 7. Technology Approach

CoachAI is built on a modern AI architecture powered by leading foundation models and proven infrastructure:

- **AI Intelligence Layer** — Powered by state-of-the-art large language models for content analysis, profile interpretation, and conversational coaching
- **Semantic Search** — Vector embeddings enable meaning-based content discovery, going beyond keyword matching
- **Deterministic Matching** — The path generation algorithm uses mathematical scoring (not AI generation) for consistency, speed, and explainability
- **Human-in-the-Loop Design** — Every AI output passes through confidence gates and human review workflows before impacting learners
- **API-First Architecture** — RESTful APIs with real-time WebSocket updates for responsive coach and admin interfaces
- **Existing Stack Compatible** — Designed to layer on top of MyNextory's existing database and infrastructure without migration risk

### Technical Appendix (for CTO)

| Component | Technology |
|-----------|-----------|
| AI Engine | Anthropic Claude (content analysis, profile interpretation, coaching AI) |
| Embeddings | OpenAI text-embedding-3-small (semantic search) |
| Vector Index | FAISS (fast similarity search at scale) |
| External Assessment | Criteria Corp EPP API (personality profiling) |
| API Server | Python / FastAPI (async, high-performance) |
| Frontend | Lightweight JavaScript (no heavy frameworks — fast load, easy maintenance) |
| Database | Compatible with MyNextory's existing MariaDB infrastructure |
| Real-Time | WebSocket connections for live dashboard updates |

---

## 8. Success Metrics

### For Learners
- **Path relevance score** — Average AI match score across recommendations (target: >70/100)
- **Discovery completion** — % of learners who complete the initial 3-5 lesson discovery phase (target: >60%)
- **Engagement lift** — Backpack saves and ratings per learner vs. pre-CoachAI baseline
- **Profile accuracy** — % of learners who do NOT flag "this doesn't sound like me" (target: >85%)

### For Coaches
- **Time savings** — Reduction in hours spent manually planning learner paths (target: 70% reduction)
- **Override rate** — % of AI recommendations coaches modify (healthy range: 10-30%)
- **Curation quality** — Learner outcomes in coach-modified vs. AI-only paths

### For HR / Leadership
- **Cohort progression** — % of learners moving through phases (profiled > discovery > active > reassessed)
- **Content utilization** — % of content library effectively matched to learners (target: >80%)
- **EPP dimension coverage** — % of personality dimensions addressed by recommended content
- **Reassessment drift** — Average profile change at quarterly reassessment (indicates learning impact)

---

## 9. What Makes This Different

| Traditional LMS | CoachAI |
|-----------------|---------|
| Same content for everyone | Personalized to personality and goals |
| Coach assigns based on intuition | AI recommends based on 25-dimension analysis |
| Static path, never adapts | Continuous adaptation from engagement signals |
| Content is a black box | Every lesson tagged with traits, difficulty, style |
| "Did they complete it?" | "Did it build the right competency?" |
| HR sees completion rates | HR sees personality growth, engagement depth, coaching effectiveness |
| Coach manually researches each learner | Coach gets AI-generated profile + compatibility signals + suggestions |

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| EPP data quality varies across learners | Medium | Medium | Confidence scoring on profiles; fallback to Q&A-only profiling |
| Content library too small for good matching | Low | High | Content gap analysis tool identifies where new content is needed |
| Coaches resist AI recommendations | Medium | Medium | Coach override tools preserve autonomy; AI is positioned as assistant, not replacement |
| Learner privacy concerns with personality data | Medium | High | All data stays within MyNextory infrastructure; no external sharing; consent-based profiling |
| AI hallucination in content tagging | Low | Medium | Multi-pass confidence scoring + human review queue catches errors before they affect learners |
| Assessment fatigue from reassessments | Low | Low | Mini-assessments are 3-5 questions; passive signals reduce need for explicit reassessments |

---

## 11. Next Steps

1. **Alignment meeting** — Walk through this scope with MyNextory leadership, prioritize capabilities, confirm phasing
2. **Data access** — ThoughtWire will need read access to the production database and EPP assessment data
3. **Phase 1 kickoff** — Begin with data model analysis and infrastructure setup
4. **Coaching team interview** — 30-minute sessions with 2-3 coaches to understand their current workflow and pain points
5. **Success metrics agreement** — Align on KPIs before development begins

---

*Prepared by ThoughtWire | Confidential — For MyNextory Internal Use Only*
