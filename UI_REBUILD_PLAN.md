Tory UI Rebuild -- Implementation Plan

       Executive Summary

       This plan covers rebuilding the Tory views in the Command Center from a single-user lookup tool into a full-featured split-view workspace with a
       people list, path builder kanban, impact preview, agent session tracking, and a content library. The work spans 5 phases across 4 layers: new MCP
       tools, new backend endpoints, new frontend views/components, and a new database table.

       ---
       Architecture Analysis (What Exists Today)

       Frontend patterns:
       - Vanilla JS with ES modules, h() DOM helper, centralized state.js store with key-level subscriptions
       - Router is hash-based (#tory, #tory-admin) with view caching (render once, toggle display)
       - Kanban already has native HTML5 drag-and-drop (draggable, dragstart, dragover, drop) -- no library needed
       - Side panel component (sidebar.js) available for slide-in detail
       - Toast notifications, context menus, command palette all exist as reusable components

       Backend patterns:
       - FastAPI routers under routes/, service classes under services/, all registered in main.py
       - MySQL queries via subprocess mysql baap --batch --raw -e "..." (no ORM)
       - MCP tools in tory_engine.py are async functions prefixed _tool_*, invocable directly from routes

       Data reality:
       - 1,449 users total, 180 with EPP+Q&A, 2 profiled, 1 with generated path (user 200)
       - 25 lessons across 4 journeys, 79 content tags
       - Claude session transcripts stored as .jsonl files in ~/.claude/projects/-home-rahil-Projects-baap/{uuid}.jsonl

       ---
       Design Decisions (Answering the 7 Questions)

       1. Drag-and-drop kanban: library or custom?

       Decision: Custom, using the existing kanban.js pattern.

       The kanban view at /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/kanban.js lines 140-174 already implements native HTML5 DnD
       with dragover, dragleave, drop, placeholder insertion, and getDragAfterElement() for position detection. The path builder kanban has 4 columns with
       at most 25 cards total -- this is well within the capability of custom DnD. No external library needed. The existing pattern provides: drag ghost
       opacity, column highlight on drag-over, positional placeholder, and optimistic state updates.

       2. Paginate 1,449 users: virtual scroll vs paginated?

       Decision: Server-side pagination with client-side search-as-you-type.

       1,449 rows is not a virtual scroll scenario (that is for 10K+). The plan:
       - Backend returns paginated results (50 per page) with total count
       - Client-side debounced search sends query param to backend, which does WHERE email LIKE '%term%' OR first_name LIKE '%term%'
       - Filter dropdowns for Company/Status/Department filter server-side
       - Status is computed server-side by LEFT JOINing tory_learner_profiles and nx_user_onboardings
       - This keeps initial load fast (~50 rows) while supporting the full 1,449

       3. Impact preview during drag: client-side or server call?

       Decision: Hybrid -- preload trait data, compute basic metrics client-side, fetch detailed impact from server on drop-hover (debounced).

       When the right panel loads for a user, the API returns the full profile (strengths/gaps with scores) and all available lessons with their trait tags.
        Basic coverage math (which gaps are addressed, gap/strength ratio) can be computed in JS from this preloaded data. The expensive server-side call
       (tory_preview_lesson_impact) is only needed for the precise score recalculation and is called with a 300ms debounce while the user hovers over a drop
        zone. This gives instant visual feedback with precise numbers following shortly after.

       4. "Resume Chat" connecting to Claude process from web UI?

       Decision: Backend spawns Claude Code with --resume flag, streams output via WebSocket.

       The flow:
       1. Frontend sends POST /api/tory/agent-sessions/{user_id}/{session_id}/chat
       2. Backend runs claude --resume {session_id} --output-format stream-json -p "{message}" as a subprocess
       3. Backend reads stdout line-by-line and pushes each JSON event through a dedicated WebSocket channel /ws/tory-agent/{session_id}
       4. Frontend displays streaming tool calls and responses
       5. On process exit, backend updates the session record

       This is analogous to the existing Think Tank WebSocket pattern at /home/rahil/Projects/baap/.claude/command-center/backend/routes/websocket.py lines
       54-80.

       5. Parse JSONL transcripts for tool calls and reasoning?

       Decision: Server-side parsing with a dedicated service function.

       Claude JSONL transcripts have a known structure: each line is a JSON object with type field (assistant, user, tool_use, tool_result). The backend
       parses these into a structured timeline:
       [
         {"type": "reasoning", "content": "...", "ts": "..."},
         {"type": "tool_call", "tool": "tory_interpret_profile", "input": {...}, "ts": "..."},
         {"type": "tool_result", "tool": "tory_interpret_profile", "output": {...}, "ts": "..."},
         ...
       ]
       This is served as JSON to the frontend, which renders it as a collapsible timeline. No JSONL parsing in the browser.

       6. Rebuild tory.js from scratch or incrementally modify?

       Decision: Rebuild from scratch as a new file tory-workspace.js.

       The current tory.js (400 lines) is a single-user lookup view. The new workspace is fundamentally different in structure (split-view, people list,
       kanban columns, impact preview, agent sessions). Incrementally modifying would create an unmaintainable hybrid. The old file remains available as
       reference for the profile card and lesson card rendering patterns, which will be extracted into reusable sub-functions.

       The old #tory route gets remapped to the new renderToryWorkspace function. The #tory-admin route stays as-is (HR dashboard serves a different
       persona).

       7. Agent session lifecycle (spawn, monitor, resume, cleanup)?

       Decision: New ToryAgentService class managing session records and Claude processes.

       The lifecycle:
       1. Spawn: POST /api/tory/process/{id} calls claude -p "Run full Tory pipeline for user {id}" --output-format stream-json as an async subprocess. A
       tory_agent_sessions DB row is created with status=running.
       2. Monitor: The subprocess stdout is read line-by-line. Each line is: (a) written to a transcript file at
       .claude/sessions/tory/{user_id}/{session_id}.jsonl, (b) pushed to the event bus as TORY_AGENT_PROGRESS events.
       3. Complete: On process exit code 0, status becomes completed. On non-zero, failed.
       4. Resume: POST triggers claude --resume {session_id} with the user's message appended.
       5. Cleanup: Transcript files are retained. DB record is never deleted, only status-updated.

       ---
       Phase 1: Data Foundation (Backend + MCP + DB)

       Goal: All the data the frontend needs is available via REST endpoints.

       1A. New database table: tory_agent_sessions

       CREATE TABLE tory_agent_sessions (
         id INT AUTO_INCREMENT PRIMARY KEY,
         nx_user_id BIGINT NOT NULL,
         session_id VARCHAR(100) NOT NULL,      -- Claude session UUID
         transcript_path VARCHAR(500),           -- .jsonl file path
         status VARCHAR(20) NOT NULL DEFAULT 'running',  -- running|completed|failed|resumed
         tool_call_count INT DEFAULT 0,
         error_message TEXT,
         pipeline_steps JSON,                    -- [{step, status, duration_ms}]
         created_at DATETIME,
         updated_at DATETIME,
         deleted_at DATETIME,
         INDEX idx_tory_as_user (nx_user_id),
         INDEX idx_tory_as_session (session_id),
         INDEX idx_tory_as_status (status)
       );

       This table is created by the platform-agent via a migration bead.

       1B. New MCP tool: tory_list_users_with_status

       File: /home/rahil/Projects/baap/.claude/mcp/tory_engine.py

       Add a new _tool_list_users_with_status function that queries:
       SELECT u.id, u.email, o.first_name, o.last_name,
         CASE
           WHEN r.nx_user_id IS NOT NULL THEN 'processed'
           WHEN p.nx_user_id IS NOT NULL THEN 'profiled'
           WHEN o.assesment_result IS NOT NULL AND o.why_did_you_come IS NOT NULL THEN 'has_epp'
           ELSE 'no_data'
         END AS tory_status,
         cl.name AS company_name, d.department_title AS department
       FROM nx_users u
       LEFT JOIN nx_user_onboardings o ON o.nx_user_id = u.id
       LEFT JOIN tory_learner_profiles p ON p.nx_user_id = u.id AND p.deleted_at IS NULL
       LEFT JOIN tory_recommendations r ON r.nx_user_id = u.id AND r.deleted_at IS NULL
       LEFT JOIN employees e ON e.nx_user_id = u.id AND e.deleted_at IS NULL
       LEFT JOIN clients cl ON cl.id = e.client_id AND cl.deleted_at IS NULL
       LEFT JOIN departments d ON d.id = e.department_id AND d.deleted_at IS NULL
       WHERE u.deleted_at IS NULL
       GROUP BY u.id

       Supports pagination (offset, limit), search (search param for LIKE on email/name), and filter (status, company, department).

       1C. New MCP tool: tory_preview_lesson_impact

       File: /home/rahil/Projects/baap/.claude/mcp/tory_engine.py

       A dry-run function that:
       1. Takes nx_user_id, add_lesson_ids[], remove_lesson_ids[]
       2. Loads the user's profile (strengths/gaps)
       3. Loads trait tags for the added/removed lessons
       4. Computes before/after metrics:
         - Gap coverage per trait (which gaps are addressed by remaining lessons)
         - Path balance (gap-fill % vs strength-lead %)
         - Journey mix (lessons per journey)
         - Discovery/main split
       5. Returns the delta without writing to DB

       1D. New backend endpoint file: routes/tory_workspace.py

       New file: /home/rahil/Projects/baap/.claude/command-center/backend/routes/tory_workspace.py

       Endpoints:

       GET  /api/tory/users?page=1&limit=50&search=&status=&company=&department=
            -> {users: [...], total: 1449, page: 1, pages: 29}

       GET  /api/tory/users/{id}/detail
            -> Full profile + path + all lessons with tags (for kanban builder)

       POST /api/tory/process/{id}
            -> Spawns agent, returns {session_id, status: "started"}

       POST /api/tory/batch-process
            -> Body: {user_ids: [1,2,3]} or {company_id: 5}
            -> Returns {batch_id, count, status}

       GET  /api/tory/preview-impact?user_id=200&add=5,6&remove=3
            -> {before: {...}, after: {...}, delta: {...}}

       GET  /api/tory/agent-sessions/{user_id}
            -> [{session_id, status, tool_call_count, created_at}]

       GET  /api/tory/agent-sessions/{user_id}/{session_id}
            -> {timeline: [{type, tool, content, ts}...], summary: {...}}

       POST /api/tory/agent-sessions/{user_id}/{session_id}/chat
            -> Body: {message: "..."}, returns {status: "resumed"}

       GET  /api/tory/content-library
            -> All 25 lessons grouped by journey, with tags and review status

       POST /api/tory/content-library/{tag_id}/approve
       POST /api/tory/content-library/{tag_id}/correct
       POST /api/tory/content-library/{tag_id}/dismiss

       1E. New service: services/tory_agent_service.py

       New file: /home/rahil/Projects/baap/.claude/command-center/backend/services/tory_agent_service.py

       Manages:
       - Spawning Claude processes (subprocess.Popen with stdout=PIPE)
       - Reading JSONL output and pushing to event bus
       - Writing transcript files
       - Updating tory_agent_sessions table
       - Resume logic (re-spawning with --resume)
       - Batch processing queue (sequential, with configurable concurrency)

       1F. Register new router and service in main.py

       File: /home/rahil/Projects/baap/.claude/command-center/backend/main.py

       Add:
       from services.tory_agent_service import ToryAgentService
       from routes import tory_workspace
       Register tory_workspace.router and create _tory_agent_service singleton in lifespan.

       ---
       Phase 2: People List (Left Panel)

       Goal: The left panel displays all 1,449 users with search, filter, and batch selection.

       2A. New frontend view: views/tory-workspace.js

       New file: /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/tory-workspace.js

       Structure:
       <div class="tw-container">
         <div class="tw-left-panel">
           <div class="tw-search-bar">
             <input type="text" placeholder="Search users...">
             <select id="tw-filter-status">...</select>
             <select id="tw-filter-company">...</select>
           </div>
           <div class="tw-batch-actions">
             <button>Process Selected (0)</button>
             <button>Batch: Company</button>
           </div>
           <div class="tw-people-list" id="tw-people-list">
             <!-- Paginated user rows -->
           </div>
           <div class="tw-pagination">...</div>
         </div>
         <div class="tw-right-panel" id="tw-right-panel">
           <!-- Empty state or selected user detail -->
         </div>
       </div>

       Each user row shows:
       - Checkbox (for batch selection)
       - Avatar (initials)
       - Name + email
       - Status badge: green "Processed", yellow "Has EPP", gray "No Data"
       - Company name (truncated)

       Click selects and loads detail in right panel. Checkbox does not trigger navigation.

       2B. State management additions in state.js

       Add a new state key:
       toryWorkspace: {
         users: [],
         totalUsers: 0,
         page: 1,
         search: '',
         filters: { status: '', company: '', department: '' },
         selectedUserId: null,
         selectedUserDetail: null,
         batchSelected: new Set(),
         loading: false,
         detailLoading: false,
       }

       2C. API additions in api.js

       Add methods:
       getToryUsers: (params) => request('GET', `/api/tory/users?${new URLSearchParams(params)}`),
       getToryUserDetail: (id) => request('GET', `/api/tory/users/${id}/detail`),
       processToryUser: (id) => request('POST', `/api/tory/process/${id}`, {}, 120000),
       batchProcessTory: (body) => request('POST', '/api/tory/batch-process', body, 300000),
       getToryImpactPreview: (params) => request('GET', `/api/tory/preview-impact?${new URLSearchParams(params)}`),
       getToryAgentSessions: (userId) => request('GET', `/api/tory/agent-sessions/${userId}`),
       getToryAgentSession: (userId, sessionId) => request('GET', `/api/tory/agent-sessions/${userId}/${sessionId}`),
       resumeToryAgentChat: (userId, sessionId, message) => request('POST', `/api/tory/agent-sessions/${userId}/${sessionId}/chat`, { message }, 120000),
       getToryContentLibrary: () => request('GET', '/api/tory/content-library'),
       approveToryTag: (tagId) => request('POST', `/api/tory/content-library/${tagId}/approve`),
       correctToryTag: (tagId, data) => request('POST', `/api/tory/content-library/${tagId}/correct`, data),
       dismissToryTag: (tagId) => request('POST', `/api/tory/content-library/${tagId}/dismiss`),

       2D. CSS file: css/tory-workspace.css

       New file: /home/rahil/Projects/baap/.claude/command-center/frontend/css/tory-workspace.css

       Key layout:
       .tw-container {
         display: grid;
         grid-template-columns: 380px 1fr;
         height: calc(100vh - 120px);
         gap: 0;
       }
       .tw-left-panel {
         border-right: 1px solid var(--border);
         display: flex;
         flex-direction: column;
         overflow: hidden;
       }
       .tw-people-list {
         flex: 1;
         overflow-y: auto;
       }
       .tw-right-panel {
         overflow-y: auto;
         padding: var(--space-5);
       }

       Status badges reuse existing badge classes. User rows follow the ta-row hover pattern from tory-admin.css.

       2E. Router + navigation updates

       File: /home/rahil/Projects/baap/.claude/command-center/frontend/index.html

       Replace the "Learning Path" nav item's data-view="tory" to still point at tory but update the label. Or add a new nav item for tory-workspace and
       keep the old one. Given the requirement to replace the #tory view:

       File: /home/rahil/Projects/baap/.claude/command-center/frontend/js/app.js

       Change:
       // OLD: registerRoute('tory', renderTory);
       registerRoute('tory', renderToryWorkspace);

       Import from views/tory-workspace.js instead of views/tory.js.

       Also update the router titles map in /home/rahil/Projects/baap/.claude/command-center/frontend/js/router.js:
       tory: 'Tory Workspace'

       ---
       Phase 3: Path Builder Kanban (Right Panel Core)

       Goal: When a user is selected, the right panel shows their profile and a 4-column kanban for path editing.

       3A. Profile card component

       Extract from the existing renderProfile() in /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/tory.js lines 155-277 into a reusable
        function in tory-workspace.js. The card is a compact version showing:
       - Avatar + name + email
       - Strengths (top 5 traits with scores)
       - Gaps (top 5 traits with scores)
       - Learning style badge
       - Confidence %
       - Narrative (collapsible)

       3B. Kanban board with 4 columns

       Implemented within tory-workspace.js as a renderPathBuilder() function.

       Columns:
       1. Available Pool -- All 25 lessons minus those already in the path. Cards show: title, journey badge, match score (computed from preloaded data),
       difficulty dots.
       2. Discovery -- First 3-5 lessons marked is_discovery=1. Max 5 slots.
       3. Main Path -- Remaining ordered lessons. Numbered sequence.
       4. Completed -- Placeholder for future use. Empty initially.

       Each lesson card structure:
       <div class="tw-lesson-card" draggable="true" data-lesson-id="4" data-column="discovery">
         <div class="tw-lesson-title">Conflict Resolution</div>
         <div class="tw-lesson-meta">
           <span class="badge badge-blue badge-sm">Leadership</span>
           <span class="tw-lesson-score">85%</span>
           <span class="tw-lesson-difficulty">●●○○○</span>
         </div>
         <div class="tw-lesson-traits">Cooperativeness, Patience</div>
       </div>

       3C. Drag-and-drop logic

       Following the exact pattern from /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/kanban.js lines 140-217:

       - dragstart: Set opacity 0.3, store dragged element ref, set dataTransfer
       - dragover: e.preventDefault(), show placeholder at position via getDragAfterElement()
       - dragleave: Remove highlight
       - drop: Move card to column, call onLessonMove(lessonId, fromColumn, toColumn, position)
       - dragend: Cleanup

       The onLessonMove handler:
       1. Immediately shows the impact preview panel (Phase 3D)
       2. Debounces (300ms) a call to api.getToryImpactPreview() for precise numbers
       3. On confirm: calls the appropriate MCP-backed endpoint (coach_swap, coach_reorder, or generates a new path)

       3D. Impact preview panel

       A floating panel that appears below the kanban when a drag is in progress or just completed:

       <div class="tw-impact-preview">
         <h4>Impact Preview</h4>
         <div class="tw-impact-grid">
           <div class="tw-impact-item">
             <span class="tw-impact-label">Assertiveness coverage</span>
             <span class="tw-impact-before">0%</span>
             <span class="tw-impact-arrow">--></span>
             <span class="tw-impact-after tw-impact-improved">30%</span>
           </div>
           <div class="tw-impact-item">
             <span class="tw-impact-label">Path balance</span>
             <span class="tw-impact-before">45% gap-fill</span>
             <span class="tw-impact-arrow">--></span>
             <span class="tw-impact-after">52% gap-fill</span>
           </div>
           <div class="tw-impact-item">
             <span class="tw-impact-label">Journey mix</span>
             <span class="tw-impact-before">4 Leadership, 2 Comm</span>
             <span class="tw-impact-arrow">--></span>
             <span class="tw-impact-after">3 Leadership, 3 Comm</span>
           </div>
         </div>
         <div class="tw-impact-actions">
           <button class="btn btn-ghost btn-sm">Cancel</button>
           <button class="btn btn-primary btn-sm">Apply Change</button>
         </div>
       </div>

       Client-side computation for instant feedback:
       - Gap coverage: For each user gap trait, count how many lessons in the path have that trait tagged. coverage = count / total_lessons_with_trait *
       100.
       - Path balance: gap_lessons / total * 100 where gap_lessons are those whose primary direction is "builds" on a gap trait.
       - Journey mix: Simple count by journey_id.

       ---
       Phase 4: Agent Session UI

       Goal: Each processed user shows their agent session history with full reasoning logs.

       4A. Agent session panel in right panel

       Below the path builder, a collapsible section:

       <div class="tw-agent-section">
         <div class="tw-agent-header">
           <h4>Agent Sessions</h4>
           <div class="tw-agent-actions">
             <button class="btn btn-primary btn-sm" id="tw-process-btn">Process</button>
             <button class="btn btn-ghost btn-sm" id="tw-reprocess-btn">Re-process</button>
           </div>
         </div>
         <div class="tw-agent-sessions" id="tw-agent-sessions">
           <!-- Session cards -->
         </div>
       </div>

       Each session card:
       <div class="tw-session-card">
         <div class="tw-session-header">
           <span class="badge badge-green badge-sm">completed</span>
           <span class="tw-session-time">2h ago</span>
           <span class="tw-session-tools">12 tool calls</span>
         </div>
         <button class="btn btn-ghost btn-sm">View Full Log</button>
         <button class="btn btn-ghost btn-sm">Resume Chat</button>
       </div>

       4B. Reasoning log view (expandable timeline)

       "View Full Log" opens the side panel (openSidePanel from /home/rahil/Projects/baap/.claude/command-center/frontend/js/components/sidebar.js) with a
       timeline:

       <div class="tw-log-timeline">
         <div class="tw-log-entry tw-log-reasoning">
           <span class="tw-log-icon">thought</span>
           <div class="tw-log-content">Analyzing EPP scores for user 200...</div>
           <span class="tw-log-time">0:00</span>
         </div>
         <div class="tw-log-entry tw-log-tool-call">
           <span class="tw-log-icon">tool</span>
           <div class="tw-log-content">
             <div class="tw-log-tool-name">tory_interpret_profile</div>
             <details>
               <summary>Input</summary>
               <pre>{nx_user_id: 200}</pre>
             </details>
             <details>
               <summary>Output (2.3KB)</summary>
               <pre>{profile: {...}}</pre>
             </details>
           </div>
           <span class="tw-log-time">0:03</span>
         </div>
       </div>

       4C. Resume Chat UI

       "Resume Chat" opens a chat interface in the side panel, similar to the Think Tank chat component at
       /home/rahil/Projects/baap/.claude/command-center/frontend/js/components/chat.js. The pattern:

       1. Open side panel with a chat input at the bottom
       2. Show the last few messages from the transcript as context
       3. User types a message, POST to /api/tory/agent-sessions/{userId}/{sessionId}/chat
       4. Backend spawns claude --resume {sessionId} with the message
       5. WebSocket /ws/tory-agent/{sessionId} streams responses back
       6. Frontend renders streaming messages in the chat panel

       4D. WebSocket channel for agent progress

       File: /home/rahil/Projects/baap/.claude/command-center/backend/routes/websocket.py

       Add a new WebSocket endpoint:
       @router.websocket("/ws/tory-agent/{session_id}")
       async def tory_agent_websocket(ws: WebSocket, session_id: str):
           # Subscribe to event bus, filter for TORY_AGENT_* events matching session_id
           ...

       New event types on the event bus:
       - TORY_AGENT_STARTED -- {user_id, session_id}
       - TORY_AGENT_PROGRESS -- {session_id, type: "tool_call"|"reasoning", content}
       - TORY_AGENT_COMPLETED -- {session_id, status, tool_call_count}
       - TORY_AGENT_FAILED -- {session_id, error}

       ---
       Phase 5: Content Library (Separate Tab)

       Goal: A standalone view for managing lesson tags independent of any learner.

       5A. Content library view

       Two approaches to routing:
       - Option A: Add a third nav item under the "Tory" section: "Content Library" at #content-library
       - Option B: Tab within the tory workspace (tabs: "Workspace" | "Content Library")

       Decision: Option A -- separate route. The content library is independent of learner selection and used by a different persona (content admin vs
       coach).

       New file: /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/content-library.js

       Layout: A kanban-style board with 4 columns (one per journey), each containing lesson cards with their tags.

       Leadership & Management (7) | Communication & Teamwork (6) | Resilience & Wellbeing (6) | Career Growth & Sales (6)
         [Setting Team Goals]       [Empathetic Listening]          [Understanding Stress]        [Understanding Customers]
           tags: Managerial 85       tags: Empathy 90                tags: StressTol 85            tags: Sociability 80
           status: approved          status: pending                  status: approved              status: needs_review
           [Approve] [Edit]          [Approve] [Edit]                [Approve] [Edit]              [Approve] [Edit]

       5B. Tag management

       Each lesson card in the content library has:
       - Trait tag pills (e.g., "Managerial 85" with color coding by direction)
       - Learning style badge
       - Difficulty level (1-5 dots)
       - Confidence score bar
       - Review status badge
       - Action buttons: Approve / Edit / Dismiss

       "Edit" opens the side panel with a form to correct trait tags (trait name dropdown, relevance score slider, direction radio).

       5C. Review queue integration

       A toolbar button "Review Queue (N pending)" filters to show only items with review_status = 'pending' or 'needs_review', sorted by confidence
       ascending (lowest confidence first = most uncertain tags reviewed first).

       "Bulk Approve" button: approves all tags above a confidence threshold (default 70).

       ---
       File Inventory

       New Files to Create


       ┌────────────────────────────────────────┬──────────────────────────────────────────────┬─────────────┐
       │                  File                  │                   Purpose                    │ Lines (est) │
       ├────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
       │ frontend/js/views/tory-workspace.js    │ Split-view workspace (people list + detail)  │ ~800        │
       ├────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
       │ frontend/js/views/content-library.js   │ Content library kanban + tag management      │ ~400        │
       ├────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
       │ frontend/css/tory-workspace.css        │ Styles for workspace, kanban, impact preview │ ~500        │
       ├────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
       │ frontend/css/content-library.css       │ Styles for content library view              │ ~200        │
       ├────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
       │ backend/routes/tory_workspace.py       │ REST endpoints for workspace                 │ ~350        │
       ├────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
       │ backend/services/tory_agent_service.py │ Agent spawn/monitor/resume service           │ ~300        │
       └────────────────────────────────────────┴──────────────────────────────────────────────┴─────────────┘

       Files to Modify

       ┌─────────────────────────────┬──────────────────────────────────────────────────────────────────────┐
       │            File             │                                Change                                │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ frontend/js/app.js          │ Import new views, register new routes                                │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ frontend/js/api.js          │ Add ~12 new API methods                                              │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ frontend/js/state.js        │ Add toryWorkspace and contentLibrary state keys                      │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ frontend/js/router.js       │ Add titles for new routes                                            │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ frontend/index.html         │ Add "Content Library" nav item, update CSS link tags                 │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ backend/main.py             │ Import and register new router, create agent service singleton       │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ backend/routes/websocket.py │ Add /ws/tory-agent/{session_id} endpoint                             │
       ├─────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
       │ .claude/mcp/tory_engine.py  │ Add tory_list_users_with_status and tory_preview_lesson_impact tools │
       └─────────────────────────────┴──────────────────────────────────────────────────────────────────────┘

       Files NOT Modified (kept as-is)

       ┌──────────────────────────────────┬──────────────────────────────────────────────────────────┐
       │               File               │                          Reason                          │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ frontend/js/views/tory.js        │ Kept for reference; route remapped to new workspace      │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ frontend/js/views/tory-admin.js  │ HR dashboard stays separate (different persona)          │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ frontend/css/tory.css            │ Old styles kept; new workspace uses own CSS file         │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ frontend/css/tory-admin.css      │ Unchanged                                                │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ backend/routes/tory.py           │ Existing endpoints still valid (profile, feedback, path) │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ backend/routes/tory_admin.py     │ HR dashboard endpoints unchanged                         │
       ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
       │ backend/services/tory_service.py │ Still used by existing tory.py routes                    │
       └──────────────────────────────────┴──────────────────────────────────────────────────────────┘

       ---
       Bead Decomposition (for Agent Dispatch)

       Epic: "Tory UI Rebuild" (baap-tory-rebuild)

       Bead 1 (platform-agent): Create tory_agent_sessions table
       - SQL migration
       - Blocked by: nothing
       - Blocks: Bead 4

       Bead 2 (content-agent / tory-agent): Add 2 new MCP tools to tory_engine.py
       - tory_list_users_with_status, tory_preview_lesson_impact
       - Blocked by: nothing
       - Blocks: Bead 3

       Bead 3 (platform-agent): Create tory_workspace.py routes + tory_agent_service.py
       - All REST endpoints, agent spawn/monitor service
       - Blocked by: Bead 1, Bead 2
       - Blocks: Bead 5, Bead 6

       Bead 4 (platform-agent): Add WebSocket channel for agent sessions
       - /ws/tory-agent/{session_id} endpoint, event types
       - Blocked by: Bead 1
       - Blocks: Bead 6

       Bead 5 (platform-agent): Build left panel + right panel skeleton
       - tory-workspace.js, tory-workspace.css, people list, search/filter, pagination
       - Update app.js, api.js, state.js, router.js, index.html
       - Blocked by: Bead 3
       - Blocks: Bead 6, Bead 7

       Bead 6 (platform-agent): Build path builder kanban + impact preview
       - 4-column DnD kanban, lesson cards, impact preview computation
       - Blocked by: Bead 5

       Bead 7 (platform-agent): Build agent session UI
       - Session list, reasoning log timeline, resume chat integration
       - Blocked by: Bead 4, Bead 5

       Bead 8 (content-agent): Build content library view
       - content-library.js, content-library.css, tag management, review queue
       - Blocked by: Bead 3 (needs content-library endpoint)

       ---
       Risks and Mitigations

       ┌──────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┐
       │                           Risk                           │                                     Mitigation                                     │
       ├──────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
       │ Claude --resume may not work for old sessions            │ Check session age; offer "Re-process from scratch" as fallback                     │
       ├──────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
       │ 1,449-user query slow on first load                      │ Server-side pagination; cache company/department dropdown options                  │
       ├──────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
       │ Impact preview computation accuracy                      │ Client-side gives approximate; server confirms; "Apply" only after server response │
       ├──────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
       │ DnD conflicts with scroll on mobile                      │ Touch events need separate handling; defer to Phase 2+ polish                      │
       ├──────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
       │ Batch processing 180 users exhausts API budget           │ Queue with concurrency limit (3); budget check before each spawn; stop button      │
       ├──────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
       │ Transcript JSONL format may vary between Claude versions │ Defensive parsing with fallbacks; log unparseable lines rather than crash          │
       └──────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┘

       ---
       Critical Files for Implementation

       - /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/kanban.js - Reference for the exact HTML5 drag-and-drop pattern
       (dragstart/dragover/drop/getDragAfterElement) to replicate in the path builder
       - /home/rahil/Projects/baap/.claude/command-center/backend/routes/tory_admin.py - Pattern for querying user data with JOINs across
       nx_users/onboardings/employees/departments; the _mysql_query helper to reuse
       - /home/rahil/Projects/baap/.claude/mcp/tory_engine.py - MCP engine where 2 new tools must be added; contains all existing _tool_* functions and the
       cosine similarity scoring logic needed for impact preview
       - /home/rahil/Projects/baap/.claude/command-center/frontend/js/views/tory.js - Source for extracting the profile card and lesson card rendering logic
        into the new workspace view
       - /home/rahil/Projects/baap/.claude/command-center/backend/routes/websocket.py - Pattern for the new /ws/tory-agent/{session_id} WebSocket channel;
       shows event bus subscription and filtered forwarding







       --------


       PLAN FILE: 



       # Tory Workspace: Split-View Path Builder with Agent Observability

## Context

The Tory engine (MCP-powered learning path personalization) is fully built and operational:
- 24 MCP tools, 14 DB tables, 25 tagged lessons, 1,449 users
- But the UI is a basic single-user lookup (enter ID, see profile)
- The user needs a production-grade workspace where they can see ALL users, choose who to process, visually build paths with drag-and-drop, simulate impact, and interrogate the agent that made each decision

**Problem**: No batch operations, no visual path editing, no agent observability, no content viewing
**Solution**: Rebuild the `#tory` view into a split-view workspace with people list, path builder kanban, impact preview, per-learner agent sessions with full reasoning logs and resumable chat, and Azure Blob content viewer

**Critical constraints**:
- **NO dummy data** — every data point comes from real DB queries via MCP tools
- **Content viewing** via Azure Blob Storage (credentials in `.env`)
- All connected to actual `baap` database (1,449 users, 25 lessons, 521 slides)

---

## Layout: 3-Pane with Collapsible Drawers + Tabs

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Tory Workspace                                    [◀ People] [AI Co-pilot ▶]   │
├─────────────────┬──────────────────────────────────────────────┬─────────────────┤
│  LEFT DRAWER    │  CENTER                                      │  RIGHT DRAWER   │
│  (slides in/out)│  ┌─────────┬──────┬─────────┬──────────┐    │  AI Co-pilot    │
│                 │  │ Profile │ Path │ Content │ Agent Log│    │  (slides in/out)│
│  PEOPLE (1,449) │  └─────────┴──────┴─────────┴──────────┘    │                 │
│                 │                                              │  tsigler's Agent│
│  ┌─────────────┐│  ═══════════════════════════════════════     │  ────────────── │
│  │[Search...]  ││                                              │                 │
│  │[Company  v] ││  « PATH » TAB ACTIVE:                       │  ┌─────────────┐│
│  │[Status   v] ││                                              │  │ 12 tool calls││
│  └─────────────┘│  Available   Discovery   Main Path   Done   │  │ Conf: 75%   ││
│                 │   Pool                                       │  │ 2026-02-19  ││
│  ┌─────────────┐│  ┌────────┐ ┌────────┐ ┌────────┐          │  └─────────────┘│
│  │● tsigler    ││  │Change  │ │Conflict│ │Setting │          │                 │
│  │  TOC Group  ││  │Mgmt    │ │Resolut.│ │Team    │          │  You:           │
│  │  ✓Processed ││  │Sc: 68  │ │Sc: 80  │ │Goals   │          │  Why is Deleg.  │
│  └─────────────┘│  └────────┘ └────────┘ │Sc: 100 │          │  at position 3? │
│  ┌─────────────┐│  ┌────────┐ ┌────────┐ └────────┘          │                 │
│  │○ jmaddren   ││  │Persuasn│ │Deleg.  │ ┌────────┐          │  Agent:         │
│  │  Conner Str ││  │Sc: 34  │ │Skills  │ │Empath. │          │  Delegation     │
│  │  ✓Processed ││  └────────┘ │Sc: 70  │ │Listen  │          │  builds Assert. │
│  └─────────────┘│  ┌────────┐ └────────┘ │Sc: 49  │          │  (gap at 12)    │
│  ┌─────────────┐│  │Network │            └────────┘          │  and leverages  │
│  │○ mwade      ││  │Stratgy │ ┌────────┐ ┌────────┐          │  Managerial     │
│  │  Conner Str ││  │Sc: 24  │ │Mindful │ │Present.│          │  (78). Placed   │
│  │  ◐ Has EPP  ││  └────────┘ │ness    │ │Skills  │          │  after Conflict │
│  └─────────────┘│             │Sc: 34  │ │Sc: 49  │          │  Resolution to  │
│  ┌─────────────┐│             └────────┘ └────────┘          │  scaffold the   │
│  │─ user@co    ││                                              │  assertiveness  │
│  │  No Data    ││  ┌─ IMPACT PREVIEW (appears on drag) ─────┐ │  growth arc.    │
│  │             ││  │ + Delegation Skills → Main Path         │ │                 │
│  └─────────────┘│  │ Assertiveness:  0% ──→ 30% covered     │ │  ────────────── │
│  ...1,445 more  │  │ Path Balance:  45% ──→ 52% gap-fill    │ │                 │
│                 │  │ Journey Mix:   +1 Leadership (4/20)     │ │  [_____________]│
│  ┌─────────────┐│  │                                         │ │  [Send]         │
│  │☐ Select All ││  │ [Cancel]                  [Apply Change]│ │                 │
│  │[Process (0)]││  └─────────────────────────────────────────┘ │                 │
│  │[Batch: Co.] ││                                              │                 │
│  └─────────────┘│                                              │                 │
└─────────────────┴──────────────────────────────────────────────┴─────────────────┘
```

### Drawer States

```
STATE 1: All open (default)
┌──────────┬────────────────────────────────┬──────────┐
│  People  │  Center (tabs)                  │ AI Chat  │
│  280px   │  flex: 1                        │  320px   │
└──────────┴────────────────────────────────┴──────────┘

STATE 2: Left collapsed (focused on one person)
┌──┬─────────────────────────────────────────┬──────────┐
│● │  Center (tabs) — more room for kanban   │ AI Chat  │
│○ │                                          │          │
└──┴─────────────────────────────────────────┴──────────┘
 48px icon strip — click to expand

STATE 3: Both collapsed (maximum kanban space)
┌──┬──────────────────────────────────────────────────┬──┐
│● │  Center (tabs) — FULL WIDTH for path editing     │💬│
│○ │                                                   │  │
└──┴──────────────────────────────────────────────────┴──┘

STATE 4: Right collapsed (browsing people, no AI needed)
┌──────────┬─────────────────────────────────────────┬──┐
│  People  │  Center (tabs)                           │💬│
└──────────┴─────────────────────────────────────────┴──┘
```

### Center Tabs

**Profile tab**: EPP strength/gap bar charts, learning style, motivation cluster, narrative, [Generate Profile] / [Re-process] buttons

**Path tab**: 4-column DnD kanban (Available Pool | Discovery | Main Path | Completed) + impact preview panel on drag

**Content tab**: All 25 lessons in 4 journey columns with tag management (approve/edit/dismiss), review queue filter, bulk approve

**Agent Log tab**: Full reasoning timeline — every tool call with expandable input/output, reasoning blocks, timestamps. [View Raw JSONL] [Resume Session] [Re-process]

### AI Co-pilot (right drawer)

- Context-aware: knows which learner is selected, persists across tab switches
- Shows session metadata (tool calls, confidence)
- Chat interface for interrogating the agent ("Why did you rank X at #3?", "What if pedagogy was strength-lead?", "Move Conflict Resolution to position 1")
- Streams responses via WebSocket
- "Resume" wakes the original processing agent with full prior context

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Layout | 3-pane with collapsible drawers + tabs | Left=people, Center=tabbed content, Right=AI co-pilot. Drawers collapse for focus. |
| DnD library | Custom (HTML5 native) | Existing `kanban.js:140-217` has the exact pattern |
| User pagination | Server-side (50/page) | 1,449 rows is manageable; keeps initial load fast |
| Impact preview | Hybrid (client-side + server confirm) | Preload trait data, compute basic metrics in JS, fetch precise delta on hover with 300ms debounce |
| Agent session resume | Claude Code `--resume` via subprocess | Native session management, transcripts already stored as JSONL |
| Agent streaming | WebSocket (like Think Tank) | `websocket.py:54-80` is the exact template |
| Rebuild vs modify | New file `tory-workspace.js` | Current `tory.js` is fundamentally different structure; keep as reference |
| Content library | Tab inside center panel | Content management is a center tab, not a separate route. Shows all lessons by journey with tag management. |
| AI co-pilot | Persistent right drawer | Stays open across tab switches. Context-aware chat with the learner's agent. |
| Data source | Real DB only (NO mocks) | All queries go through MCP tools to `baap` database |
| Content viewing | Azure Blob SAS URLs | Backend generates time-limited SAS tokens for images/audio/video from `productionmynextory` storage account |

---

## Phase 1: Data Foundation

### 1A. New DB table: `tory_agent_sessions`

**Agent**: platform-agent | **Blocked by**: nothing

```sql
CREATE TABLE tory_agent_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nx_user_id BIGINT NOT NULL,
  session_id VARCHAR(100) NOT NULL,
  transcript_path VARCHAR(500),
  status VARCHAR(20) DEFAULT 'running',  -- running|completed|failed|resumed
  tool_call_count INT DEFAULT 0,
  error_message TEXT,
  pipeline_steps JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at DATETIME,
  INDEX idx_user (nx_user_id),
  INDEX idx_session (session_id),
  INDEX idx_status (status)
);
```

### 1B. New MCP tools in `tory_engine.py`

**Agent**: content-agent | **Blocked by**: nothing

**`tory_list_users_with_status`** — Paginated user list with Tory processing status:
- Params: `page`, `limit`, `search`, `status_filter`, `company_filter`
- Computes status per user: `processed` (has recommendations), `profiled` (has profile only), `has_epp` (has onboarding data), `no_data`
- JOINs: `nx_users` LEFT JOIN `nx_user_onboardings` LEFT JOIN `tory_learner_profiles` LEFT JOIN `tory_recommendations` LEFT JOIN `clients`

**`tory_preview_lesson_impact`** — Dry-run impact simulation:
- Params: `nx_user_id`, `add_lesson_ids[]`, `remove_lesson_ids[]`
- Returns: before/after gap coverage per trait, path balance (gap% vs strength%), journey mix, discovery/main split
- NO database writes

### 1C. Azure Blob content proxy

**Agent**: platform-agent | **Blocked by**: nothing

Backend service to generate SAS (Shared Access Signature) URLs for content assets stored in Azure Blob Storage:

**Azure config** (from `.env`):
- Account: `productionmynextory`
- Key: `AZURE_STORAGE_KEY`
- Base URL: `https://productionmynextory.blob.core.windows.net/`
- Container: `staging`

**Content storage pattern** (from DB):
- `lesson_slides.slide_content` = JSON with relative blob paths: `Image/xxx.jpg`, `Audio/xxx.mp3`
- `video_libraries.video` = `Video/6/xxx.mp4`, `video_libraries.thumbnail` = `Video/Thumbnail/xxx.png`
- 521 slides across 68 types (image, video, question-answer, three-word, greetings, take-away, etc.)
- Full URL: `{AZURE_STORAGE_URL}{container}/{relative_path}?{sas_token}`

**New service**: `services/azure_blob_service.py`
- `generate_sas_url(blob_path, container='staging', expiry_hours=1)` → signed URL
- `list_lesson_assets(lesson_detail_id)` → all image/audio/video paths for a lesson
- Uses `azure-storage-blob` Python SDK with connection string from env

**New endpoint**: `GET /api/tory/blob/{container}/{path:path}` → redirect to SAS URL (or proxy)

### 1D. New backend routes: `routes/tory_workspace.py`

**Agent**: platform-agent | **Blocked by**: 1A, 1B, 1C

```
GET  /api/tory/users?page=1&limit=50&search=&status=&company=
GET  /api/tory/users/{id}/detail          (profile + path + all lessons with tags)
POST /api/tory/process/{id}               (spawn agent, return session_id)
POST /api/tory/batch-process              (batch spawn for user_ids[] or company_id)
GET  /api/tory/preview-impact             (dry-run simulation)
GET  /api/tory/agent-sessions/{user_id}
GET  /api/tory/agent-sessions/{user_id}/{session_id}  (parsed reasoning timeline)
POST /api/tory/agent-sessions/{user_id}/{session_id}/chat  (resume agent)
GET  /api/tory/content-library            (all lessons grouped by journey + tags + slides)
GET  /api/tory/blob/{container}/{path:path}  (SAS URL redirect for content assets)
GET  /api/tory/lesson/{id}/slides         (parsed slides with SAS URLs for media)
```

### 1E. New service: `services/tory_agent_service.py` (MUST be fully functional)

**Agent**: platform-agent | **Blocked by**: 1A

**Follow the EXACT ThinkTank session management pattern** from `services/thinktank_service.py`:

#### Session lifecycle (mirror ThinkTank):
- **Session ID format**: `tory_{8-char-hex}` (like ThinkTank's `tt_{8-char-hex}`)
- **Storage**: File-based JSON at `.claude/command-center/sessions/tory/{session_id}.json`
- **In-memory cache**: `ToryAgentService._sessions` dict (like ThinkTank's `_sessions`)
- **Load on startup**: `_load_all_sessions()` reads `tory_*.json` from sessions dir
- **Debounced persist**: `_schedule_persist()` / `_persist_now()` — max 1 write/sec, critical changes immediate
- **Active session per user**: Only ONE active session per `nx_user_id` at a time

#### Pydantic models (in `models.py`):
```python
class ToryAgentEvent(BaseModel):
    type: str  # "reasoning" | "tool_call" | "tool_result" | "error" | "complete"
    content: str | None = None
    tool: str | None = None
    input: dict | None = None
    output: dict | None = None
    timestamp: str

class ToryAgentSession(BaseModel):
    id: str                    # tory_{hex8}
    nx_user_id: int
    status: str = "running"    # running | completed | failed | resumed
    events: list[ToryAgentEvent] = []
    tool_call_count: int = 0
    error_message: str | None = None
    pipeline_steps: list[str] = []  # ["interpret_profile", "score_content", "generate_path"]
    created_at: str
    updated_at: str
    claude_session_id: str | None = None  # Claude Code's internal session ID for --resume
```

#### Real Claude subprocess (NOT mock):
- **Spawn**: `asyncio.create_subprocess_exec("claude", "-p", prompt, "--output-format", "stream-json")`
- **Monitor**: `async for line in process.stdout` → parse JSONL → append to `session.events` → push to event bus
- **Complete**: Update session status + tool_call_count on process exit
- **Resume**: `claude --resume {claude_session_id} -p "{user_message}"` — wakes agent with full prior context
- **Stream to WebSocket**: Each parsed event → `event_bus.publish(TORY_AGENT_PROGRESS, {...})` → WebSocket subscribers get it
- **Batch queue**: `asyncio.Semaphore(3)` for concurrency, queue per user
- **Process management**: Track PIDs in `_processes` dict, SIGTERM on cancel, 5-min timeout

#### WebSocket (mirror ThinkTank's `/ws/thinktank` pattern):
- Endpoint: `/ws/tory-agent?session={session_id}`
- On connect: replay all existing `session.events` as catch-up (same dedup via `seen_timestamps`)
- Reader: accepts `{ type: "message", text: "..." }` → triggers resume
- Writer: filters event bus for `TORY_AGENT_*` events matching this session
- Concurrent reader/writer tasks (exact copy of `websocket.py:97-158`)

### 1F. Wire into `main.py`

Import `tory_workspace` router + `ToryAgentService` + `AzureBlobService` singletons in lifespan.

---

## Phase 2: 3-Pane Shell + People Drawer

**Agent**: platform-agent | **Blocked by**: Phase 1

### Files

| File | Action |
|------|--------|
| `frontend/js/views/tory-workspace.js` | **NEW** ~900 lines — 3-pane layout, drawers, tabs, people list |
| `frontend/css/tory-workspace.css` | **NEW** ~600 lines — 3-pane grid, drawer animations, cards, badges |
| `frontend/js/api.js` | **MODIFY** — add ~12 new API methods |
| `frontend/js/state.js` | **MODIFY** — add `toryWorkspace` state key |
| `frontend/js/router.js` | **MODIFY** — add title for `tory` |
| `frontend/js/app.js` | **MODIFY** — import `renderToryWorkspace`, replace `renderTory` registration |
| `frontend/index.html` | **MODIFY** — add CSS link, add Content Library nav item |

### Left panel features
- Paginated user rows (50/page) with search-as-you-type (debounced 300ms)
- Filter dropdowns: Company, Status (Processed/Has EPP/No Data/All)
- Status indicators: green dot = processed, yellow = has EPP, gray = no data
- Checkbox multi-select for batch processing
- "Process Selected (N)" and "Batch: [Company Name]" action buttons
- Click row = load detail in right panel

### State shape
```js
toryWorkspace: {
  users: [], totalUsers: 0, page: 1,
  search: '', filters: { status: '', company: '' },
  selectedUserId: null, selectedUserDetail: null,
  batchSelected: new Set(),
  loading: false, detailLoading: false,
}
```

---

## Phase 3: Center Tabs — Profile + Path Builder + Content

**Agent**: platform-agent | **Blocked by**: Phase 2

### Profile tab (center panel)
- Extracted from existing `tory.js:155-277` pattern
- EPP strength/gap bar charts with scores
- Learning style badge, confidence %, motivation cluster
- Collapsible narrative
- [Generate Profile] for unprocessed users, [Re-process] for existing

### Kanban board (4 columns)
- **Available Pool**: All 25 lessons minus those in the path. Cards show: title, journey badge, match score, difficulty dots
- **Discovery**: First 3-5 lessons (is_discovery=1). Max 5 slots
- **Main Path**: Remaining ordered lessons. Numbered sequence
- **Completed**: Future use. Empty initially

### Drag-and-drop
Reuses exact pattern from `kanban.js:140-217`:
- `dragstart`: opacity 0.3, store ref, `effectAllowed='move'`
- `dragover`: `preventDefault()`, `getDragAfterElement()` for positional placeholder
- `drop`: move card, trigger `onLessonMove(lessonId, fromCol, toCol, position)`
- `dragend`: cleanup

### Impact preview (appears on drag/drop)
- Client-side instant feedback from preloaded trait data:
  - Gap coverage per trait: `addressedCount / totalLessonsForTrait`
  - Path balance: `gapLessons / total * 100`
  - Journey mix: count by journey_id
- Server-side confirmation via `/api/tory/preview-impact` (debounced 300ms)
- "Apply Change" button commits via coach_swap / coach_reorder MCP tools
- "Cancel" reverts the drag

---

## Phase 4: AI Co-pilot Drawer + Agent Log Tab

**Agent**: platform-agent | **Blocked by**: Phase 2 + 1D

### AI Co-pilot (right drawer)
- Persistent across tab switches — always knows the selected learner
- Session metadata card: tool call count, confidence, timestamp
- Chat interface (reuse `chat.js` pattern from Think Tank)
- POST message to `/api/tory/agent-sessions/{userId}/{sessionId}/chat`
- Backend runs `claude --resume {sessionId} -p "{message}"` as subprocess
- Streams responses via WebSocket `/ws/tory-agent/{sessionId}` (reuse `websocket.py:54-80` pattern)
- Use cases: "Why did you rank X at #3?", "What if pedagogy was strength-lead?", "Move Conflict Resolution to position 1"

### Agent Log tab (center panel)
- Full reasoning timeline — every tool call with expandable input/output
- Backend parses JSONL transcript into structured timeline:
  ```json
  [{"type": "reasoning", "content": "...", "ts": "..."},
   {"type": "tool_call", "tool": "tory_interpret_profile", "input": {...}},
   {"type": "tool_result", "output": {...}}]
  ```
- Frontend renders collapsible entries with `<details>` tags
- Buttons: [View Raw JSONL] [Resume This Session] [Re-process]

### WebSocket channel
**File**: `backend/routes/websocket.py` — add `/ws/tory-agent/{session_id}` endpoint
- Event types: `TORY_AGENT_STARTED`, `TORY_AGENT_PROGRESS`, `TORY_AGENT_COMPLETED`, `TORY_AGENT_FAILED`

---

## Phase 5: Content Library (Separate Tab)

**Agent**: content-agent | **Blocked by**: Phase 1C

### New files
| File | Action |
|------|--------|
| `frontend/js/views/content-library.js` | **NEW** ~400 lines |
| `frontend/css/content-library.css` | **NEW** ~200 lines |

### Layout
- 4 columns (one per journey): Leadership & Management | Communication & Teamwork | Resilience & Wellbeing | Career Growth & Sales
- Each lesson card shows: title, trait tag pills (color-coded by direction), learning style, difficulty, confidence bar, review status badge
- Actions per card: Approve, Edit (opens side panel form), Dismiss
- Toolbar: "Review Queue (N pending)" filter, "Bulk Approve (conf > 70)" button
- Tag editing form: trait dropdown, relevance score slider, direction radio (builds/leverages/challenges)
- Wraps existing MCP tools: `tory_review_approve`, `tory_review_correct`, `tory_review_dismiss`, `tory_review_bulk_approve`

---

## Bead Decomposition

| # | Bead | Agent | Depends On | Deliverable |
|---|------|-------|------------|-------------|
| 1 | DB migration: tory_agent_sessions | platform-agent | — | SQL migration |
| 2 | MCP tools: list_users + preview_impact | content-agent | — | 2 new tools in tory_engine.py |
| 3 | Azure Blob service + content proxy | platform-agent | — | services/azure_blob_service.py + SAS URL endpoint |
| 4 | Backend: tory_workspace routes + agent service (REAL Claude subprocess) | platform-agent | 1, 2, 3 | routes/tory_workspace.py + services/tory_agent_service.py + main.py wiring |
| 5 | WebSocket: tory-agent channel (REAL streaming) | platform-agent | 1 | /ws/tory-agent/{id} in websocket.py |
| 6 | Frontend: 3-pane shell + people list | platform-agent | 4 | tory-workspace.js + .css + api.js + state.js + router.js + app.js + index.html |
| 7 | Frontend: path builder kanban + impact preview | platform-agent | 6 | DnD kanban, lesson cards, impact panel |
| 8 | Frontend: agent log + AI co-pilot (REAL resume chat) | platform-agent | 5, 6 | Session log timeline, chat interface, WebSocket streaming |
| 9 | Frontend: content library + Azure content viewer | content-agent | 4 | Content tab with slides, images, video from Azure Blob |

---

## Key Files Reference

| Existing File | Reuse For |
|---------------|-----------|
| `frontend/js/views/kanban.js:140-217` | HTML5 DnD pattern (dragstart/over/drop/getDragAfterElement) |
| `backend/routes/websocket.py:54-80` | WebSocket event bus subscription (Think Tank pattern) |
| `frontend/js/views/tory.js:155-277` | Profile card rendering (strengths/gaps/narrative) |
| `frontend/js/components/chat.js` | Chat interface for agent resume |
| `frontend/js/components/sidebar.js` | Side panel for log viewer and tag editor |
| `frontend/js/state.js` | Reactive store with key-level subscriptions |
| `.claude/mcp/tory_engine.py` | Cosine similarity scoring logic for impact preview |

---

## Verification

1. **People list**: Load page, see 50 users per page with correct status badges. Filter by company. Search by email.
2. **Processing**: Select an unprocessed user with EPP data. Click "Generate Profile". See agent spawn, tool calls stream in real-time, profile appears when done.
3. **Path builder**: Select a processed user. See their 20 recommendations in kanban columns. Drag a lesson from Available to Main Path. See impact preview with before/after numbers. Click Apply.
4. **Agent session**: Click "View Full Log" — see collapsible timeline of tool calls. Click "Resume Chat" — ask "Why did you rank lesson 4 first?" — get a reasoned response.
5. **Batch processing**: Select 5 users with EPP, click "Process Selected". See progress indicators as each processes sequentially.
6. **Content library**: Navigate to `#content-library`. See 25 lessons in 4 journey columns. Click Edit on a lesson, modify trait tags, save. Click "Bulk Approve" — pending tags with confidence > 70 become approved.
