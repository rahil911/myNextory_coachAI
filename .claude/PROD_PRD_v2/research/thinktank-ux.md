# Think Tank UX Research: Patterns for AI-Assisted Brainstorming

> "Good enough is the enemy of humanity."

This document captures specific, actionable UI/UX patterns for building a **Think Tank** view
where a human brainstorms with an AI orchestrator through 4 phases:
**Listen -> Explore -> Scope -> Confirm** before autonomous execution begins.

Research conducted 2026-02-14 across 40+ sources.

---

## Table of Contents

1. [The Split-View Paradigm: Chat + Living Document](#1-the-split-view-paradigm)
2. [Phase Indicator Patterns](#2-phase-indicator-patterns)
3. [Menu-Based Response Patterns (D/A/G)](#3-menu-based-response-patterns)
4. [Live Spec Formation: Document Being Written](#4-live-spec-formation)
5. [Pre-Mortem Visualization](#5-pre-mortem-visualization)
6. [The Approval Gate: "Go Build It"](#6-the-approval-gate)
7. [Screenshot/Image Attachment in Chat](#7-screenshotimage-attachment-in-chat)
8. [Synthesis: Recommended Architecture](#8-synthesis-recommended-architecture)

---

## 1. The Split-View Paradigm

### What the Best Tools Do

The dominant pattern across every modern AI collaboration tool is the **chat + artifact split view**.
This is not optional. It is table stakes.

#### ChatGPT Canvas
- Opens a **dedicated side panel** to the right of the chat when substantial content is generated
- Chat becomes the "conversation about the work"; Canvas becomes the "work itself"
- Users can **highlight specific text** in Canvas and a mini-prompt box appears for inline edits
- Supports **version history** with a back button to restore previous states
- Key insight: Canvas activates automatically when content is >15 lines and self-contained
- Source: [OpenAI Canvas](https://openai.com/index/introducing-canvas/)

#### Claude Artifacts
- Artifacts appear in a **dedicated right-side panel** with two tabs: "Code" and "Preview"
- The conversation stays focused on intent; the artifact holds the structured output
- Supports multi-format: Markdown documents, HTML/CSS/JS, SVG, Mermaid diagrams, React components
- Users can **edit artifacts directly** without cluttering the chat
- Key insight: Artifacts are standalone modules -- they make sense without the conversation
- Source: [Claude Artifacts Help](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them)

#### CopilotKit Generative UI
- Defines three tiers of generative UI:
  1. **Controlled**: Pre-built components, agent chooses which to render and passes data
  2. **Declarative**: Agent returns structured JSON description, frontend renders it
  3. **Open-ended**: Agent generates raw UI markup at runtime
- For Think Tank, **Controlled Generative UI** is the right call -- you own the spec-kit layout,
  the AI populates it with structured data
- **Synchronized state layer**: Both agents and UI can read/write state in real-time
- Source: [CopilotKit Generative UI](https://www.copilotkit.ai/generative-ui)

### Specific Pattern for Think Tank

```
+------------------------------------------+------------------------------------+
|                                          |                                    |
|         CHAT PANEL (left, ~55%)          |      SPEC-KIT PANEL (right, ~45%) |
|                                          |                                    |
|  [Phase Indicator: Listen -> Explore ->  |  +------------------------------+  |
|   Scope -> Confirm]                      |  | PROJECT BRIEF               |  |
|                                          |  | Goal: ________________      |  |
|  AI: "Tell me what you're trying to      |  | Users: _______________      |  |
|  build. What problem are you solving?"   |  | Success: _____________      |  |
|                                          |  +------------------------------+  |
|  User: "I need a dashboard that..."      |  | REQUIREMENTS (forming...)   |  |
|                                          |  | [shimmer placeholder]       |  |
|  AI: "Interesting. Who are the primary   |  | [shimmer placeholder]       |  |
|  users of this dashboard?"               |  +------------------------------+  |
|                                          |  | PRE-MORTEM (Phase 3)        |  |
|  [D] Dig deeper  [A] Adjust  [G] Go     |  | [locked until Phase 3]      |  |
|                                          |  +------------------------------+  |
|  +------------------------------------+  |  | APPROVAL (Phase 4)          |  |
|  | Type a message... [img] [mic]      |  |  | [locked until Phase 4]      |  |
|  +------------------------------------+  |  +------------------------------+  |
+------------------------------------------+------------------------------------+
```

**Why this works**: The chat handles the *conversation* (messy, exploratory, human).
The spec-kit handles the *structured output* (clean, organized, machine-readable).
The human watches their intent crystallize in real-time on the right side.

---

## 2. Phase Indicator Patterns

### Research Findings

#### Stepper/Wizard UX Best Practices
- **3-7 steps** is the sweet spot; Think Tank's 4 phases is perfect
- Each step needs three visual states: **completed** (checkmark), **active** (highlighted), **upcoming** (dimmed)
- **Connected dots/lines** between steps show progression and relationship
- Labels are mandatory -- never rely on just numbers or icons
- Source: [Eleken Stepper Examples](https://www.eleken.co/blog-posts/stepper-ui-examples)
- Source: [Nick Babich Wizard Design](https://uxplanet.org/wizard-design-pattern-8c86e14f2a38)

#### Miro/FigJam Workshop Phases
- Structure sessions with **explicit divergent/convergent phases**
- Use **color-coded sections** so participants know where they are
- Miro's Creative Problem Solving framework: Clarify -> Ideate -> Develop -> Implement
  (maps well to Listen -> Explore -> Scope -> Confirm)
- Source: [Miro Brainstorming](https://miro.com/brainstorming/what-is-brainstorming/)

#### USWDS Step Indicator
- Federal design system's step indicator uses: step number, step label, completion status
- Current step gets a filled circle; completed steps get checkmarks; future steps are hollow
- A connecting line between circles shows the journey
- Source: [USWDS Step Indicator](https://designsystem.digital.gov/components/step-indicator/)

### Specific Pattern for Think Tank

```
Phase indicator (horizontal, top of chat panel):

  (1)---------(2)---------(3)---------(4)
 LISTEN      EXPLORE      SCOPE      CONFIRM
 "Hear you"  "Map it"    "Stress it" "Lock it"

Visual states:
- Completed: Solid teal circle with white checkmark, teal connecting line
- Active: Pulsing teal circle with white number, animated gradient on connecting line
- Upcoming: Gray outline circle with gray number, gray dashed connecting line

Micro-copy under each phase (visible on hover or always):
- Listen:  "Understanding your vision"
- Explore: "Mapping possibilities & constraints"
- Scope:   "Stress-testing with pre-mortem"
- Confirm: "Final review before autonomous build"
```

**Delightful touches**:
- The connecting line between completed and active phase should have a **subtle animated gradient**
  (like a flowing river) to convey forward momentum
- When a phase completes, the checkmark should **pop in with a satisfying scale animation**
  (scale from 0 -> 1.1 -> 1.0, 300ms, ease-out-back)
- Each phase has a distinct **accent color gradient** that tints the chat background subtly:
  - Listen: warm amber (receptive, open)
  - Explore: electric blue (expansive, creative)
  - Scope: orange-red (critical, analytical)
  - Confirm: emerald green (decisive, go)

**Anti-pattern**: Do NOT make it a progress bar. Progress bars imply linear, predictable completion.
Brainstorming is non-linear. The stepper communicates *phase* not *percentage*.

---

## 3. Menu-Based Response Patterns (D/A/G)

### Research Findings

#### NN/Group Prompt Controls Research
- **Prompt controls** = UI components that surround the input field to expedite and supplement text input
- Four main uses: conversation starters, scope-setting, modification controls, followup facilitation
- **Buttons work best for discoverable, predetermined actions**
- **Free text remains necessary for open-ended queries**
- Hybrid approaches (buttons + text) optimize usability
- Icons MUST have labels -- few icons are universally recognized
- Limit to **3-5 quick reply options** for conversational clarity
- Source: [NN/G Prompt Controls](https://www.nngroup.com/articles/prompt-controls-genai/)

#### Quick Reply Chips (Industry Standard)
- Google calls them "chips" -- small pill-shaped buttons below a message
- Displayed as bubbles next to the message typing area
- Users click instead of typing, reducing friction
- Best practice: 3-5 options maximum, short labels (2-4 words)
- Source: [Chatbot Buttons vs Quick Replies](https://activechat.ai/news/chatbot-buttons-vs-quick-replies/)

#### Perplexity Focus Mode
- Uses buttons to narrow scope BEFORE conversation begins
- Sets structural constraints with a single click
- Demonstrates "scope-setting controls" pattern

### Specific Pattern for Think Tank

**After each AI message during phase transitions, render three action chips:**

```
AI: "I've mapped out 3 possible approaches for your dashboard.
     Here's what I'm seeing: [summary].
     The spec-kit on the right has been updated with these options."

     +-----------------+  +---------------+  +------------------+
     | [magnifier] Dig |  | [pencil] Edit |  | [arrow-r] Next   |
     |     Deeper      |  |    & Adjust   |  |    Phase ->      |
     +-----------------+  +---------------+  +------------------+

     +--------------------------------------------------+
     | Or type freely...                    [img] [mic] |
     +--------------------------------------------------+
```

**Design specifics**:

1. **Chip Design**:
   - Rounded rectangles (border-radius: 12px), not full pills
   - Icon + label (never icon alone)
   - Subtle border (1px) in phase accent color, transparent fill
   - On hover: fill with 10% opacity of phase accent color, slight scale(1.02)
   - On click: solid fill, white text, haptic-like scale animation (press-in 0.97 -> release 1.0)

2. **Chip Semantics**:
   - **Dig Deeper** [D]: "I want to explore this thread further" -- stays in current phase
   - **Edit & Adjust** [A]: "Something's off, let me correct course" -- opens inline edit or new prompt
   - **Next Phase ->** [G]: "I'm satisfied, move forward" -- transitions to next phase with animation

3. **Progressive Enhancement**:
   - Chips appear with a **staggered fade-in** (100ms delay between each, left to right)
   - After 5 seconds of inactivity, a subtle pulse on the text input hints "or type your own thought"
   - The chips should **not disappear** when the user starts typing -- they remain as shortcuts
   - After the user sends a message, the previous chips gray out (still visible for context)

4. **Keyboard Shortcuts** (for power users):
   - `D` key -> Dig Deeper (when input is empty)
   - `A` key -> Edit & Adjust
   - `G` key -> Go Next
   - Show shortcut hints on hover: "Press D" in small text below chip
   - This makes the chat feel like a command-line for people who want speed

5. **Contextual Chip Content**:
   - Chips should have **contextual labels** not generic ones:
   - Instead of "Dig Deeper" -> "Explore the data model further"
   - Instead of "Next Phase" -> "Move to Pre-Mortem"
   - The AI should populate chip text based on conversation context

**Anti-pattern**: Do NOT use a command palette or slash commands for this. The DAG options
should be visible without any discovery burden. The user should never wonder "what can I do next?"

---

## 4. Live Spec Formation: Document Being Written

### Research Findings

#### Vercel AI SDK useObject Hook
- **Streams typed, structured objects directly to the client** via `streamObject` / `useObject`
- Partial objects appear as they're being generated -- users see the document form field-by-field
- In array output mode, only complete array elements appear (no half-rendered items)
- This is the technical foundation for "live spec formation"
- Source: [Vercel AI SDK streamObject](https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-object)

#### Notion AI Block-by-Block Generation
- Notion AI generates content **inline within the document**, block by block
- Users can hit spacebar to trigger AI generation at any cursor position
- AI Blocks are special blocks powered by AI that auto-generate content in context
- The generation appears progressively, matching the document's own formatting
- Source: [Notion AI Blocks](https://noteforms.com/notion-glossary/ai-blocks)

#### Skeleton/Shimmer Loading Patterns
- **Shimmer effect**: A moving light gradient sweeps across placeholder shapes
- Match the size of actual components to prevent layout shifts
- Facebook, LinkedIn, YouTube all use this to convey "content is being prepared"
- The shimmer should match the exact layout of the final content
- Source: [NN/G Skeleton Screens](https://www.nngroup.com/articles/skeleton-screens/)

#### Typewriter/Streaming Text
- Character-by-character rendering conveys "this is being written right now"
- Variable speed typing feels more natural than constant speed
- A blinking cursor at the insertion point shows where new content will appear
- Source: [TypeIt.js](https://www.typeitjs.com/)

### Specific Pattern for Think Tank

The spec-kit panel should feel like **watching a brilliant analyst fill in a dossier in real-time**.

#### Spec-Kit Document Structure

```
+-----------------------------------------------+
| SPEC-KIT                          [collapse ^] |
|                                                |
| +-------------------------------------------+ |
| | PROJECT BRIEF                    [edit]    | |
| | Goal: Build a real-time marketing...       | |
| | Users: Marketing team, CEO                 | |
| | Success: Reduce decision time by 50%       | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | REQUIREMENTS                     [edit]    | |
| | Must-Have:                                 | |
| |   [x] Real-time ROAS monitoring           | |
| |   [x] Channel-level drill-down            | |
| |   [ ] ...[shimmer]...                      | |
| | Nice-to-Have:                              | |
| |   [x] AI anomaly detection                | |
| |   [ ] ...[shimmer]...                      | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | CONSTRAINTS & BOUNDARIES         [edit]    | |
| | - Must integrate with existing Snowflake   | |
| | - Budget: < $5K/month infra               | |
| | - ...[shimmer]...                          | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | ARCHITECTURE SKETCH (Phase 2+)   [expand] | |
| | [Mermaid diagram placeholder]              | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | PRE-MORTEM (Phase 3)             [locked]  | |
| | [Appears during Scope phase]               | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | EXECUTION PLAN (Phase 4)         [locked]  | |
| | [Appears during Confirm phase]             | |
| +-------------------------------------------+ |
+-----------------------------------------------+
```

#### Animation & UX Details

1. **Section Reveal**:
   - Sections unlock progressively as phases advance
   - Locked sections show a subtle **lock icon + phase label** ("Unlocks in Phase 3: Scope")
   - When a section unlocks, it **slides down from 0 height** with a spring animation
     (duration: 400ms, slight overshoot)

2. **Content Streaming**:
   - New content appears with a **soft teal highlight** that fades over 2 seconds
     (like Google Docs when a collaborator edits)
   - Each new line/bullet streams in with the text appearing character-by-character
   - A **thin glowing cursor** at the insertion point pulses gently
   - After streaming completes, the highlight fades and content looks "settled"

3. **Shimmer Placeholders**:
   - For sections the AI hasn't filled yet, show shimmer bars that match the expected layout
   - Three sizes: short (30% width), medium (60%), long (90%) -- mixed randomly
   - The shimmer gradient should use the **phase accent color** at 5% opacity
   - As real content replaces shimmers, use a **crossfade** (200ms)

4. **User Editing**:
   - Each section has an **[edit] button** that switches to inline editing mode
   - Users can correct/add to the spec directly -- these edits are **highlighted in a different color**
     (user edits in amber, AI content in default) so the provenance is clear
   - When user edits, the chat shows: "I see you updated the success criteria. Let me factor that in."

5. **Scroll Sync** (optional but delightful):
   - When the AI is discussing requirements in chat, the spec-kit auto-scrolls to the Requirements section
   - Subtle, not jarring -- uses smooth scrolling with a 300ms delay

---

## 5. Pre-Mortem Visualization

### Research Findings

#### Risk Heat Map / Risk Matrix
- Standard risk visualization: **5x5 grid**, Likelihood (x-axis) vs Impact (y-axis)
- Color coding: Red = High Risk, Amber/Yellow = Medium, Green = Low
- Each risk is plotted as a dot or card on the matrix
- Modern tools make these interactive -- click a risk to see details
- Source: [Miro Risk Heat Map](https://miro.com/templates/risk-heat-map/)
- Source: [MetricStream Risk Heat Map](https://www.metricstream.com/learn/risk-heat-map.html)

#### Traffic Light Cards
- Individual risks displayed as cards with colored left border (Red/Amber/Green)
- Each card shows: Risk title, Likelihood (1-5), Impact (1-5), Mitigation strategy
- Cards can be sorted by severity, grouped by category
- Source: [Bizzdesign Risk Visualization](https://support.bizzdesign.com/display/knowledge/Visualization+of+risk-related+properties+and+risk+analysis+results)

### Specific Pattern for Think Tank

The pre-mortem should feel like a **war room briefing** -- serious but actionable.

#### Pre-Mortem Card Layout

```
+-----------------------------------------------+
| PRE-MORTEM: What Could Kill This Project?      |
| "It's 6 months from now and the project       |
|  failed. What went wrong?"                     |
|                                                |
| +-------------------------------------------+ |
| | [RED] CRITICAL                             | |
| |                                            | |
| | +---------------------------------------+ | |
| | | [!] Data Freshness                     | | |
| | | "Snowflake queries take >30s, making   | | |
| | |  'real-time' dashboard feel sluggish"  | | |
| | | Likelihood: ****_ (4/5)               | | |
| | | Impact:     *****  (5/5)              | | |
| | | Mitigation: Pre-aggregate hourly,      | | |
| | |  add materialized views               | | |
| | | [Accept Risk] [Mitigate] [Eliminate]   | | |
| | +---------------------------------------+ | |
| |                                            | |
| | +---------------------------------------+ | |
| | | [!] Scope Creep                        | | |
| | | "CEO adds 'one more chart' every week" | | |
| | | Likelihood: ***** (5/5)               | | |
| | | Impact:     ***__ (3/5)               | | |
| | | Mitigation: Feature-freeze after v1,   | | |
| | |  backlog for v2                        | | |
| | | [Accept Risk] [Mitigate] [Eliminate]   | | |
| | +---------------------------------------+ | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | [AMBER] WATCH                              | |
| | ...                                        | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | [GREEN] ACKNOWLEDGED                       | |
| | ...                                        | |
| +-------------------------------------------+ |
|                                                |
| Risk Summary:                                  |
| Critical: 2  |  Watch: 3  |  Acknowledged: 1  |
| [All risks mitigated or accepted to proceed]  |
+-----------------------------------------------+
```

#### Design Details

1. **Risk Cards**:
   - Left border: 4px solid, color-coded (Red #EF4444, Amber #F59E0B, Green #22C55E)
   - Background: very subtle tint of the border color (2% opacity)
   - The AI generates these by **asking provocative questions** during Phase 3:
     "What if the Snowflake queries are too slow? What if the CEO keeps adding requirements?"
   - The human can **dismiss, edit, or add risks** via the chat or direct interaction

2. **Likelihood/Impact Stars**:
   - Use filled/empty stars (accessible, universally understood)
   - On hover, show a tooltip with the numeric score and what it means
   - The AI explains its reasoning: "I rated this 4/5 likelihood because..."

3. **Action Buttons Per Risk**:
   - **Accept Risk**: "We know about this and will proceed" (card gets a subtle "accepted" badge)
   - **Mitigate**: "We'll add a mitigation plan" (opens inline text input for mitigation details)
   - **Eliminate**: "We'll change the scope to avoid this entirely" (crosses out the risk, updates spec-kit)
   - All three buttons should be **outline style** until clicked, then the chosen one fills solid

4. **Risk Summary Bar**:
   - At the bottom of the pre-mortem section
   - Shows counts by severity with colored dots
   - Must show "All risks addressed" before the Confirm phase unlocks
   - This creates a **natural gate**: you cannot proceed to approval until every risk has a disposition

5. **Interactive Risk Matrix** (optional, expandable):
   - A mini 5x5 heat map visualization that plots all risks
   - Dots on the matrix are interactive -- click to scroll to that risk's card
   - The matrix updates in real-time as risks are added/addressed

**The pre-mortem framing is key**: The prompt "It's 6 months from now and the project failed.
What went wrong?" is psychologically powerful because it removes optimism bias and forces
genuine risk thinking. The AI should explicitly use this framing.

---

## 6. The Approval Gate: "Go Build It"

### Research Findings

#### Replit Plan Mode -> Build Mode
- Agent creates a plan in Plan Mode that the user reviews
- The user clicks **"Start Building"** to approve and transition to autonomous execution
- The user is NOT charged during planning -- only when Agent implements approved changes
- Key insight: Separating planning from execution makes the approval feel consequential
- Source: [Replit Plan Mode Docs](https://docs.replit.com/replitai/plan-mode)

#### Devin AI Two-Checkpoint System
- Checkpoint 1: **Planning Checkpoint** -- review and approve the step-by-step plan
- Checkpoint 2: **PR Checkpoint** -- review the actual code changes before merge
- Optional "Agency mode" lets Devin proceed without waiting for approval
- Key insight: Two gates (plan approval + output review) builds maximum trust
- Source: [Devin AI](https://docs.devin.ai/release-notes/overview)

#### Cursor Plan Mode
- Separates "what" from "how" -- the plan is a **reviewable artifact**
- Users can edit the plan before approving
- Changes can be accepted partially or completely
- Key insight: The plan itself is editable, not just approve/reject binary
- Source: [Cursor 2.0](https://prismic.io/blog/cursor-ai)

#### Agent UX Guardrails (Zypsy)
- **Pre-flight summary**: Show who/what/when/where/value before approval
- **Human-readable diffs** for any updates
- Rollback strategy must be visible
- **Cost/time estimates** shown before approval
- Double-confirm only for high-risk actions
- Source: [Agent UX Guardrails](https://llms.zypsy.com/agent-ux-guardrails)

#### Confirmation UX Best Practices
- Use the **intended action name** as the primary button text (not "OK" or "Submit")
- Clearly explain what will happen in the dialog body
- Provide an option to undo or revert when possible
- For irreversible actions, reiterate the outcome and potential repercussions
- Source: [DhiWise Confirmation Modal](https://www.dhiwise.com/post/smart-confirmation-modal-design-for-better-click-decisions)

### Specific Pattern for Think Tank

The approval moment should feel like **signing a contract** -- weighty, clear, and ceremonial.

#### Phase 4: Confirm View

```
+-----------------------------------------------+
| PHASE 4: CONFIRM                               |
| "Review everything. Once you approve, the      |
|  AI orchestrator will build autonomously."      |
|                                                |
| +-------------------------------------------+ |
| | FINAL SPEC SUMMARY                         | |
| |                                            | |
| | Goal: Real-time marketing dashboard        | |
| | Scope: 5 views, 12 charts, 3 data sources | |
| | Timeline estimate: ~4 hours autonomous     | |
| | Risk disposition: 2 mitigated, 3 accepted  | |
| |                                            | |
| | [View Full Spec-Kit ->]                    | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | WHAT WILL HAPPEN NEXT                      | |
| |                                            | |
| | 1. AI creates project structure            | |
| | 2. AI builds components in order:          | |
| |    a. Data layer & API connections         | |
| |    b. Core dashboard views                 | |
| |    c. Chart components                     | |
| |    d. Interactivity & drill-downs          | |
| | 3. AI runs validation tests                | |
| | 4. You'll review the output                | |
| |                                            | |
| | [!] You can pause the build at any time    | |
| +-------------------------------------------+ |
|                                                |
| +-------------------------------------------+ |
| | CHANGES SINCE LAST REVIEW                  | |
| | - Added: "anomaly detection" to must-have  | |
| | - Removed: "PDF export" from nice-to-have  | |
| | - Risk: "Data freshness" -> mitigated      | |
| +-------------------------------------------+ |
|                                                |
|   +-------------------------------------------+|
|   |                                           ||
|   |      [Approve & Start Building ->]        ||
|   |                                           ||
|   |  or [Go Back to Scope] [Save as Draft]    ||
|   +-------------------------------------------+|
|                                                |
+-----------------------------------------------+
```

#### Design Details

1. **The Approval Button**:
   - **Full-width**, not a small button lost in a corner
   - **Emerald green** (#059669) with white text, 48px height minimum
   - Text: **"Approve & Start Building ->"** (action-specific, never "Submit" or "OK")
   - On hover: slight brightness increase, subtle glow effect (box-shadow with green at 20% opacity)
   - On click: **two-phase animation**:
     - Phase 1 (0-200ms): Button contracts slightly, fills with a satisfying "confirmed" state
     - Phase 2 (200-800ms): Button expands into a full-width banner that says
       "Building... You'll be notified when ready" with a rocket/launch icon
   - **No double-confirm dialog** -- the entire Phase 4 IS the confirmation dialog.
     Adding another modal on top is an anti-pattern.

2. **Pre-Flight Summary**:
   - Shows the key decisions in **scannable, card-based format**
   - Each card is collapsible (progressive disclosure) for users who want to review details
   - Changes since last review are **highlighted with amber left border** (diff-style)
   - Timeline estimate creates expectation setting ("~4 hours" tells the user what to expect)

3. **Escape Hatches** (critical for trust):
   - **"Go Back to Scope"**: Takes them back without losing any work
   - **"Save as Draft"**: Saves the entire session state for later -- the brainstorm doesn't die
   - **"You can pause the build at any time"**: This single line reduces anxiety more than
     anything else. It turns an irreversible-feeling action into a reversible one.
   - These should be **text links**, not buttons -- visually subordinate to the primary action

4. **Post-Approval Transition**:
   - After clicking "Approve & Start Building":
     - The chat panel transitions to a **build log** view (like a terminal, but beautiful)
     - The spec-kit panel stays visible as a reference
     - The phase indicator shows all 4 phases completed, plus a new animated "Building..." state
     - A **progress feed** shows what the AI is doing: "Creating project structure...",
       "Building data layer...", "Running tests..." with timestamps
   - The user should be able to **leave and come back** -- the build continues asynchronously

---

## 7. Screenshot/Image Attachment in Chat

### Research Findings

#### Modern Chat Upload Patterns
- **Three input methods**: Click upload button, drag-and-drop onto chat, paste from clipboard (Cmd+V)
- All three should trigger the same upload flow and preview
- Source: [CometChat Feedback](https://feedback.cometchat.com/p/support-clipboard-paste-and-drag-and-drop-image-upload-in)

#### Drag-and-Drop UX
- When a drag starts, show a **visual drop zone** overlay on the chat area
- The drop zone should have a dashed border, slight background tint, and "Drop image here" text
- After drop, show an **inline preview thumbnail** with a remove button
- Source: [Filestack Upload UI](https://blog.filestack.com/building-modern-drag-and-drop-upload-ui/)

#### File Upload Best Practices
- Show **preview before sending** -- never auto-send an uploaded image
- Display file type, size, and a thumbnail
- Allow removing/replacing before send
- Show upload progress for large files
- Support multiple image upload in a single message
- Source: [Uploadcare UX Best Practices](https://uploadcare.com/blog/file-uploader-ux-best-practices/)

### Specific Pattern for Think Tank

Images are critical for Think Tank because users will paste screenshots of existing dashboards,
whiteboard photos, mockups, and reference designs.

#### Implementation Details

```
Chat input area:

+------------------------------------------------------+
| [attached images appear here as thumbnails]           |
| +--------+  +--------+                               |
| |  [img]  |  |  [img]  |                              |
| | dash.png|  | sketch  |                              |
| |   [x]   |  |   [x]   |                              |
| +--------+  +--------+                               |
|                                                       |
| Type a message...              [camera] [clip] [mic] |
+------------------------------------------------------+
```

1. **Input Triggers**:
   - **Camera icon** [camera]: Opens file picker filtered to images
   - **Clip icon** [clip]: Opens file picker for any file type
   - **Cmd+V / Ctrl+V**: Detects image data on clipboard, creates inline preview
   - **Drag-and-drop**: Shows blue-tinted overlay on the entire chat panel

2. **Preview Thumbnails**:
   - 80x80px thumbnails with rounded corners (border-radius: 8px)
   - Appear ABOVE the text input, not replacing it
   - Each has an [x] remove button in the top-right corner
   - Click thumbnail to see full-size preview in a lightbox overlay
   - Multiple images arranged horizontally, scrollable if >3

3. **In-Chat Rendering**:
   - After sending, images appear **inline in the chat bubble** at reasonable size
     (max-width: 300px, maintaining aspect ratio)
   - The AI can **reference specific parts** of the image in its response:
     "I see the chart in the top-right corner of your screenshot. Is that the ROAS trend you want?"
   - AI responses can include **annotated versions** of uploaded images (ideal but complex)

4. **Spec-Kit Integration**:
   - When the user uploads a reference design, the AI should ask:
     "Should I add this to the spec-kit as a reference design?"
   - If yes, it appears in a "Reference Designs" section in the spec-kit panel
   - This makes the images part of the formal spec, not lost in chat history

---

## 8. Synthesis: Recommended Architecture

### The Think Tank Should Feel Like:

1. **A brilliant co-founder** who listens intently (Phase 1), explores every angle (Phase 2),
   plays devil's advocate (Phase 3), and then says "I've got this" (Phase 4)

2. **A living document** that writes itself as you talk -- you watch your messy thoughts
   crystallize into a clean spec in real-time on the right panel

3. **A workshop facilitator** who knows when to expand (divergent) and when to converge --
   the phases enforce healthy thinking discipline

4. **A launchpad** -- the approval moment should feel like pressing a launch button,
   not filling out a form

### Key Technical Decisions

| Decision | Recommendation | Why |
|----------|---------------|-----|
| Layout | Split-view: Chat left (55%), Spec-kit right (45%) | Industry standard (ChatGPT Canvas, Claude Artifacts) |
| Phase indicator | Horizontal stepper with connected dots, top of chat | Clear, scannable, shows progress without interrupting flow |
| Response options | Contextual chips below AI messages + always-available text input | NN/G research: buttons for common actions, text for open-ended |
| Spec streaming | Vercel AI SDK `useObject` for structured streaming | Partial objects render as they generate, no layout shifts |
| Pre-mortem | Risk cards with severity borders + interactive matrix | Combines detail (cards) with overview (matrix) |
| Approval | Full-width button with pre-flight summary, no double-confirm | The entire Phase 4 IS the confirmation dialog |
| Image upload | Paste + drag-drop + button; preview thumbnails above input | All three methods are expected in 2025; preview before send |
| Persistence | Auto-save session state; "Save as Draft" escape hatch | Users must be able to leave and return to any Think Tank session |

### Component Hierarchy

```
<ThinkTank>
  <PhaseIndicator phase={1-4} />
  <SplitView>
    <ChatPanel>
      <MessageList>
        <AIMessage>
          <MessageContent />
          <ActionChips options={["Dig Deeper", "Adjust", "Next Phase"]} />
        </AIMessage>
        <UserMessage>
          <MessageContent />
          <AttachedImages />
        </UserMessage>
      </MessageList>
      <ChatInput>
        <ImagePreviewStrip />
        <TextInput />
        <InputActions> [camera] [clip] [mic] </InputActions>
      </ChatInput>
    </ChatPanel>
    <SpecKitPanel>
      <ProjectBrief />
      <Requirements />
      <Constraints />
      <ArchitectureSketch />    {/* Phase 2+ */}
      <PreMortem />             {/* Phase 3+ */}
      <ExecutionPlan />         {/* Phase 4  */}
      <ApprovalGate />          {/* Phase 4  */}
    </SpecKitPanel>
  </SplitView>
</ThinkTank>
```

### Interaction Flow Summary

```
Phase 1: LISTEN
  AI asks open-ended questions about vision, users, goals
  Spec-kit: Project Brief section fills in real-time
  Chips: [Dig Deeper] [Adjust] [Move to Explore ->]

Phase 2: EXPLORE
  AI maps possibilities, asks about constraints, tech stack, integrations
  AI may generate architecture sketches (Mermaid diagrams)
  Spec-kit: Requirements + Constraints + Architecture fill in
  Chips: [Dig Deeper] [Adjust] [Move to Scope ->]

Phase 3: SCOPE (mandatory pre-mortem)
  AI plays devil's advocate: "What could go wrong?"
  AI generates risk cards; user must address each one
  Spec-kit: Pre-mortem section populates with risk cards
  Gate: Cannot proceed until all risks have a disposition
  Chips: [Add Another Risk] [Adjust Mitigation] [All Risks Addressed ->]

Phase 4: CONFIRM
  AI presents final summary with changes highlighted
  User reviews full spec-kit, pre-flight checklist
  Spec-kit: Execution Plan section fills in
  Approval: [Approve & Start Building ->]
  Escape: [Go Back] [Save as Draft]

Post-Approval: BUILD
  Chat transitions to build log
  Spec-kit remains visible as reference
  Phase indicator shows "Building..." with animated state
  User can pause/resume at any time
```

---

## Appendix: Sources

### AI Collaboration Tools
- [OpenAI Canvas Introduction](https://openai.com/index/introducing-canvas/)
- [Claude Artifacts Help Center](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them)
- [CopilotKit Generative UI](https://www.copilotkit.ai/generative-ui)
- [CopilotKit Developer Guide to Generative UI 2026](https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026)

### Workshop & Brainstorming Tools
- [Miro Brainstorming](https://miro.com/brainstorming/what-is-brainstorming/)
- [Miro Creative Problem Solving](https://miro.com/brainstorming/what-is-creative-problem-solving/)
- [FigJam Brainstorming Best Practices](https://www.figma.com/best-practices/collaborating-in-figjam/brainstorming/)
- [FigJam Collaborative Whiteboard](https://www.figma.com/figjam/)

### AI Builder Platforms
- [v0.dev Prompt Guide](https://vercel.com/blog/how-to-prompt-v0)
- [v0.dev Maximizing Outputs](https://vercel.com/blog/maximizing-outputs-with-v0-from-ui-generation-to-code-creation)
- [Lovable AI Ultimate Guide](https://www.nocode.mba/articles/ultimate-guide-lovable)
- [Lovable Getting Started (UX Collective)](https://uxdesign.cc/getting-started-with-lovable-the-no-hype-beginner-tips-to-building-with-ai-36460d46249d)
- [Replit Plan Mode](https://docs.replit.com/replitai/plan-mode)
- [Replit Plan Mode Blog](https://blog.replit.com/introducing-plan-mode-a-safer-way-to-vibe-code)
- [Devin AI Docs](https://docs.devin.ai/release-notes/overview)
- [Cursor AI Review](https://prismic.io/blog/cursor-ai)

### Notion & Coda AI
- [Notion AI Inline Guide](https://www.eesel.ai/blog/notion-ai-inline)
- [Notion AI Blocks](https://noteforms.com/notion-glossary/ai-blocks)
- [Notion AI for Docs](https://www.notion.com/help/guides/notion-ai-for-docs)

### UX Patterns & Research
- [NN/G Prompt Controls in GenAI Chatbots](https://www.nngroup.com/articles/prompt-controls-genai/)
- [NN/G Response Outlining](https://www.nngroup.com/articles/response-outlining/)
- [NN/G Skeleton Screens](https://www.nngroup.com/articles/skeleton-screens/)
- [NN/G Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
- [Shape of AI UX Patterns](https://www.shapeof.ai/)
- [Smashing Magazine Design Patterns for AI Interfaces](https://www.smashingmagazine.com/2025/07/design-patterns-ai-interfaces/)
- [Nick Babich Wizard Design Pattern](https://uxplanet.org/wizard-design-pattern-8c86e14f2a38)
- [Eleken 32 Stepper UI Examples](https://www.eleken.co/blog-posts/stepper-ui-examples)

### Approval & Trust Patterns
- [Agent UX Guardrails (Zypsy)](https://llms.zypsy.com/agent-ux-guardrails)
- [Human-in-the-Loop for AI Agents (Permit.io)](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo)
- [DhiWise Confirmation Modal](https://www.dhiwise.com/post/smart-confirmation-modal-design-for-better-click-decisions)
- [Trust Falls in UX (Shelby Lauren)](https://medium.com/@shelbycdesign/trust-falls-in-ux-building-confidence-with-confirmation-moments-6bc4f6a4ef25)
- [Confirmation Patterns (Design Systems Collective)](https://www.designsystemscollective.com/designing-success-part-2-dos-don-ts-and-use-cases-of-confirmation-patterns-6e760ccd1708)

### Technical Implementation
- [Vercel AI SDK streamObject](https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-object)
- [Vercel AI SDK useObject Template](https://vercel.com/templates/next.js/use-object)
- [Flowbite Tailwind CSS Stepper](https://flowbite.com/docs/components/stepper/)
- [Preline Tailwind CSS Stepper](https://preline.co/docs/stepper.html)
- [Miro Risk Heat Map Template](https://miro.com/templates/risk-heat-map/)

### Upload & Image Patterns
- [Filestack Modern Drag-and-Drop Upload UI](https://blog.filestack.com/building-modern-drag-and-drop-upload-ui/)
- [Uploadcare File Uploader UX Best Practices](https://uploadcare.com/blog/file-uploader-ux-best-practices/)
- [Sendbird Chatbot UI Examples](https://sendbird.com/blog/chatbot-ui)
