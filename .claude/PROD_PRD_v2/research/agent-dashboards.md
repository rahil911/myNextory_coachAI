# Agent Monitoring & Orchestration Dashboard Research (2025-2026)

Research conducted February 2026. Focus: concrete UX patterns from production systems we can steal.

---

## Table of Contents

1. [CrewAI Studio / Enterprise](#1-crewai-studio--enterprise)
2. [LangGraph Studio / LangSmith](#2-langgraph-studio--langsmith)
3. [AutoGen Studio](#3-autogen-studio-microsoft)
4. [Strands Agents (AWS)](#4-strands-agents-aws)
5. [Cursor / Windsurf / Devin](#5-cursor--windsurf--devin)
6. [AgentOps](#6-agentops)
7. [Langfuse](#7-langfuse)
8. [Helicone](#8-helicone)
9. [Arize Phoenix](#9-arize-phoenix)
10. [Braintrust](#10-braintrust)
11. [AG-UI Protocol (CopilotKit)](#11-ag-ui-protocol-copilotkit)
12. [Agentic Design Patterns (Cross-Platform)](#12-agentic-design-patterns-cross-platform)
13. [Stealable Patterns Summary](#13-stealable-patterns-summary)

---

## 1. CrewAI Studio / Enterprise

**Source**: [CrewAI Docs](https://docs.crewai.com/en/enterprise/features/crew-studio) | [CrewAI Enterprise](https://www.crewai.com/)

### Layout

Three-panel layout:
- **Left Panel - AI Thoughts**: Streams the AI assistant's reasoning as the workflow is being designed. Shows what the system is "thinking" while you build.
- **Center Canvas**: Node-and-edge diagram where agents and tasks are distinct visual nodes connected by edges representing task dependencies and data flow. Supports drag-and-drop composition.
- **Right Panel - Resources**: Component library sidebar for adding agents, tasks, and tools to the canvas.

### Key UX Patterns

**Dual-mode creation**: Chat-based AND drag-and-drop share state and can be used interchangeably. You can describe what you want in natural language, then adjust visually on the canvas, or vice versa. Both modes stay synced.

**Execution view**: Provides event timeline tracking workflow progression, with multi-tab detailed logs (Details, Messages, Raw Data). Supports local testing before publication.

**Hierarchical process management**: The system automatically assigns a manager agent to the crew to coordinate task planning, delegation, and result validation.

**Export options**: Published automations can be consumed as Chat, React Component, or MCP endpoint.

### Human-in-the-Loop
- Manager agent pattern: a supervisor agent validates results before passing to next task
- Human input via `human_input=True` flag on tasks, which pauses execution and prompts the user

### Monitoring (via SigNoz Integration)

SigNoz provides a pre-built CrewAI dashboard template ([SigNoz CrewAI Dashboard](https://signoz.io/docs/dashboards/dashboard-templates/crewai-dashboard/)) with these panels:
- **Token Usage Over Time**: Time series of input/output token consumption
- **Average Duration of Crew**: Total execution time per Crew run
- **Duration Over Time (Per Agent)**: How individual agent execution time changes over time
- **Duration Over Time (Per Tool)**: Tool-level performance trends
- **Average Time Per Agent**: Comparative bar chart of agent efficiency
- **Average Time Per Tool**: Tool latency comparison
- **Tasks Per Agent**: Workload distribution view
- **Agent and Task Span List**: Clickable spans linking to full traces

### STEAL THIS
- **Three-panel layout** (AI reasoning | canvas | component library) is excellent for investigation dashboards
- **Dual-mode creation** (chat + visual) lets users choose their preferred interaction style
- **SigNoz dashboard panels** are a blueprint for our agent performance monitoring

---

## 2. LangGraph Studio / LangSmith

**Source**: [LangGraph Studio Blog](https://blog.langchain.com/langgraph-studio-the-first-agent-ide/) | [LangSmith Studio Docs](https://docs.langchain.com/langsmith/studio) | [LangSmith Observability](https://www.langchain.com/langsmith/observability)

### Layout

Two operational modes:
- **Graph Mode**: Full feature-set showing traversed nodes, intermediate states, LangSmith integrations. Interactive graph visualization of the agent's state machine.
- **Chat Mode**: Simplified chat interface for testing conversational agents.

### Key UX Patterns

**Interactive graph visualization**: Renders the agent's state machine as a visual graph. Each node represents a step (tool call, LLM call, decision point). You can see the agent decide which tools to call, call them, and continue looping in real-time.

**State editing at any point**: You can click on any node and directly modify the agent's state/response at that step, then continue execution with the altered state. This "what-if" capability lets you simulate alternative outcomes without re-running the entire workflow.

**Real-time streaming**: During agent interaction, a stream of real-time information shows what steps are happening. You see tool calls, decisions, and looping behavior as it occurs.

**Code-linked hot reload**: LangGraph Studio detects changes to underlying code files. You can update prompts in your code editor and rerun individual nodes if the agent responds poorly. No need to restart the entire agent.

### Human-in-the-Loop

**Interrupt checkpoints**: Click on any node in the graph and mark "Interrupt After" checkbox. Execution pauses at that node, presents current state to operator for review. Operator can modify state, then resume.

**Two interrupt modes**:
1. **Standard interrupt**: Pause if the agent veers off course (selective)
2. **Debug mode**: Pause after EVERY step for step-through debugging

### Observability (LangSmith)

Custom dashboards track:
- Token usage, latency (P50, P99), error rates, cost breakdowns
- Feedback scores
- Trace execution paths with state transitions
- Runtime metrics for debugging

### STEAL THIS
- **"Interrupt After" checkbox on graph nodes** is the simplest possible HITL UX. One checkbox per node.
- **State editing mid-execution** is the killer feature. Click a step, edit the state, resume. No restart.
- **Code-linked hot reload** for prompt iteration without full reruns.
- **Graph + Chat dual mode** lets power users see the graph while casual users just chat.

---

## 3. AutoGen Studio (Microsoft)

**Source**: [AutoGen Studio Docs](https://microsoft.github.io/autogen/dev//user-guide/autogenstudio-user-guide/index.html) | [Microsoft Research Blog](https://www.microsoft.com/en-us/research/blog/introducing-autogen-studio-a-low-code-interface-for-building-multi-agent-workflows/)

### Layout

Four main interfaces:
1. **Team Builder**: Visual drag-and-drop for creating agent teams. Supports both declarative JSON and visual configuration of teams, agents, tools, models, and termination conditions.
2. **Playground**: Interactive testing environment with live message streaming between agents, control transition graph visualization, and pause/stop execution controls.
3. **Gallery**: Central hub for discovering and importing community-created components (agent templates, tool packages).
4. **Deployment**: Python code export, endpoint setup, Docker container execution.

### Key UX Patterns

**Control transition graph**: Visualizes how messages flow between agents as a directed graph. Each node is an agent, edges show message paths. This reveals the conversation topology in multi-agent scenarios.

**Live message streaming**: See messages flowing between agents in real-time during execution. This is not just a log; it is a visual representation of agent-to-agent communication.

**Pause/stop controls**: Interactive execution management lets you halt an agent mid-conversation, inspect state, and optionally resume.

**Community gallery**: A marketplace for pre-built agent teams and components. Import a community agent configuration and modify it for your use case.

### Human-in-the-Loop
- **UserProxyAgent**: Dedicated agent type that represents the human user in the conversation loop
- Execution controls: pause/stop allow manual intervention during multi-agent conversations

### STEAL THIS
- **Control transition graph** showing which agent is talking to which agent, with message flow edges
- **Gallery/marketplace pattern** for reusable investigation templates
- **Pause/stop execution controls** as first-class UI elements during agent runs

---

## 4. Strands Agents (AWS)

**Source**: [AWS Blog](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/) | [Strands Docs](https://strandsagents.com/latest/) | [Deep Dive](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/)

### Observability Approach

Strands takes a different approach from dedicated UIs: built-in OpenTelemetry instrumentation sends traces to any compatible backend (Datadog, SigNoz, Jaeger, etc.).

**Key components**:
- Built-in OpenTelemetry spans for every tool call, LLM call, and agent step
- Native AWS service integration (CloudWatch, X-Ray)
- Deploys to Lambda, Fargate, EKS, Bedrock AgentCore
- Integrates with Datadog LLM Observability ([Datadog + Strands](https://www.datadoghq.com/blog/llm-aws-strands/))

### AG-UI Integration (Jan 2026)

Recently integrated with CopilotKit's AG-UI protocol ([CopilotKit Blog](https://www.copilotkit.ai/blog/aws-strands-agents-now-compatible-with-ag-ui)), enabling standardized frontend rendering of agent state and tool calls.

### STEAL THIS
- **OpenTelemetry-first approach**: Don't build custom observability; emit standard OTel spans and let users pick their backend
- **AG-UI integration**: Standardized protocol for agent-to-UI communication is the future

---

## 5. Cursor / Windsurf / Devin

### Cursor

**Source**: [Cursor 2.0](https://www.codecademy.com/article/cursor-2-0-new-ai-model-explained) | [Cursor Changelog](https://releasebot.io/updates/cursor)

**Key UX Patterns**:

- **Agent sidebar**: Right-side panel where developers create, name, and manage multiple agents. Each agent shows its own status, progress indicators, and output logs.
- **Context pills**: Visual indicators showing which files and code sections each agent is working with. Inline badges like "searching codebase" or "editing files".
- **Mission Control**: Grid-view interface (like macOS Expose) for monitoring multiple in-progress agent tasks simultaneously. Scaled previews of open windows with quick-switch.
- **Interactive Q&A during execution**: Agents can ask clarifying questions mid-task. While waiting for your response, the agent continues reading files and making progress. Answers are incorporated asynchronously.
- **Plan Mode**: Explicit planning step before execution. Agent creates a structured plan, user reviews/modifies, then execution begins.

### Windsurf (Cascade)

**Source**: [Windsurf Cascade Docs](https://docs.windsurf.com/windsurf/cascade/cascade) | [Windsurf Editor](https://windsurf.com/editor)

**Key UX Patterns**:

- **Todo list progress tracking**: Cascade creates an inline Todo list within the conversation to track progress on complex tasks. Checkboxes show completed vs pending steps.
- **Dual-agent planning**: A specialized planning agent continuously refines the long-term plan in the background while the execution model takes short-term actions.
- **Side-by-side Cascade panes** (Wave 13): Multi-agent sessions running in parallel with Git worktrees. Monitor progress and compare outputs side-by-side.
- **Arena Mode**: Run two agents side-by-side with hidden model identities. Vote on which performs better. A/B testing for agent quality.
- **Checkpoints**: Save code state before each change, with instant rollback via Esc-Esc or `/rewind`.

### Devin 2.0

**Source**: [Devin 2.0 Blog](https://cognition.ai/blog/devin-2) | [Devin AI](https://devin.ai/)

**Key UX Patterns**:

- **Agent-native cloud IDE**: Each Devin instance gets its own cloud IDE with code editor, terminal, sandboxed browser, and planning tools. Multiple Devins run in parallel.
- **Interactive planning**: Auto-generates preliminary plans showing relevant files, findings, and proposed steps. Users can modify the plan before autonomous execution begins.
- **Plan-then-execute pattern**: Devin researches the codebase, generates a plan within seconds, shows relevant files and findings, then waits for user approval before proceeding.
- **Live preview tab**: Built-in browser showing live previews of whatever the agent is building. Real-time visual feedback on UI work.
- **Devin Wiki**: Auto-generated documentation with architecture diagrams, source links, and codebase knowledge that updates as the agent works.
- **Devin Search**: Agentic codebase exploration tool with cited code references. "Deep Mode" for complex queries.

### STEAL THIS
- **Todo checklist progress tracking** (Windsurf) is dead simple and universally understood
- **Context pills** (Cursor) showing which files/data each agent is touching
- **Mission Control grid view** (Cursor) for monitoring multiple parallel investigations
- **Plan-then-execute** (Devin/Cursor) with explicit user review before autonomous action
- **Live preview** (Devin) showing results as they happen
- **Checkpoints with instant rollback** (Windsurf/Claude Code) for safety
- **Arena Mode** (Windsurf) for A/B testing different agent strategies

---

## 6. AgentOps

**Source**: [AgentOps](https://www.agentops.ai/) | [AgentOps Dashboard Docs](https://docs.agentops.ai/v1/usage/dashboard-info)

### Dashboard Components

1. **Session List**: All previously recorded sessions with total execution time, SDK versions, framework info. Filterable and searchable.

2. **Session Waterfall** (primary visualization):
   - Left panel: Time-aligned visualization of ALL events (LLM calls, Action events, Tool calls, Errors) as horizontal bars on a timeline
   - Right panel: Detail view showing exact prompt/completion for any selected event
   - Click any bar to see full context on the right
   - Events are color-coded by type

3. **Session Overview**: Aggregated cross-session analytics. Meta-analysis across multiple recordings.

4. **Chat History View**: LLM calls rendered as familiar chat bubbles for readability.

5. **Event Type Charts**: Breakdown of event types and their durations as pie/bar charts.

### Key UX Patterns

- **Session replay**: Rewind and replay agent runs with point-in-time precision. Like a video player for agent execution.
- **Waterfall timeline**: Horizontal bars showing event duration and sequencing. Click any bar to drill into details. This is the Chrome DevTools Network tab pattern applied to agent execution.
- **Two-line integration**: Add `import agentops; agentops.init()` and monitoring is automatic.
- **12% overhead**: Measured performance impact, reasonable for production.

### STEAL THIS
- **Waterfall timeline** (left: timeline, right: detail) is the most intuitive agent debugging UX. Chrome DevTools proved this pattern works.
- **Session replay** with point-in-time scrubbing
- **Chat history view** as an alternative rendering of LLM calls (familiar to users)

---

## 7. Langfuse

**Source**: [Langfuse Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs) | [Langfuse for Agents](https://langfuse.com/changelog/2025-11-05-langfuse-for-agents) | [Trace Timeline](https://langfuse.com/changelog/2024-06-12-timeline-view)

### Dashboard Components

1. **Traces Dashboard**: Each row is one complete pipeline execution with trace ID, execution time (0.00s to 34.08s), token counts, environment filter (dev/prod).

2. **Agent Graphs** (GA as of Nov 2025): Visual representation of agent workflow as directed graph. Graph structure is inferred automatically from observation timings and nesting. No manual configuration required. Works with any framework.

3. **Three Trace Views**:
   - **Graph View**: Visual flow showing agent orchestration (e.g., SequentialChain -> LLMChain -> ChatOpenAI). Hierarchical structure. Each node is clickable to see span details.
   - **Timeline View**: Horizontal bars showing latency, parallelism detection, multi-step reasoning depth. Color-coded by latency/cost percentiles relative to siblings.
   - **Log View**: Single concatenated scrollable view of ALL data in a trace. Search across the entire trace. Best for "just scrolling through everything."

4. **Agent Tools Panel**: Shows all available tools at the top of each LLM generation. Click any tool to see full definition, description, parameters. Called tools show arguments and call IDs with matched numbering.

5. **Expanded Observation Types**: Tool calls, embeddings, agent actions each get distinct visual treatment with icons/colors to identify observation type at a glance.

### Key UX Patterns

- **Auto-inferred graphs**: No manual instrumentation needed. Langfuse infers the agent graph from timing and nesting of spans. Zero-config visualization.
- **Three views of the same data**: Graph (for flow understanding), Timeline (for performance), Log (for detail). Each optimized for a different debugging task.
- **Nested tree with color coding**: Expandable tree rendering with recursive indentation. Nodes color-coded by latency/cost percentiles relative to siblings (not absolute). This relative coloring instantly highlights slow steps.
- **Cost/Usage/Latency dashboards**: Separate dedicated dashboards for spending, execution metrics, and response time analysis.

### STEAL THIS
- **Three views pattern** (Graph | Timeline | Log) of the same trace data is brilliant. Users pick the view that matches their mental model.
- **Auto-inferred agent graphs** from span timing/nesting (zero config)
- **Relative color coding** of nodes by percentile vs siblings (not absolute values)
- **Tool definition panel** showing available tools with click-to-expand details
- **Log View** for "just let me scroll through everything" users

---

## 8. Helicone

**Source**: [Helicone](https://www.helicone.ai/) | [Helicone GitHub](https://github.com/Helicone/helicone)

### Dashboard Components

- **Request logging**: Every LLM request with prompt, completion, latency, tokens, cost
- **Sessions & Traces**: Multi-step interaction tracing showing exactly where things go wrong
- **Analytics dashboards**: Token usage, cost tracking, multi-provider routing stats
- **Playground**: Rapid prompt testing and iteration within the UI

### Key UX Patterns

- **Proxy-based integration**: Swap your API base URL to Helicone's proxy. Zero SDK changes. Every request is automatically logged.
- **15-minute setup**: Minimal friction to first dashboard view
- **Cost-first analytics**: Spending is the primary lens, not traces

### STEAL THIS
- **Proxy-based zero-code integration** is the ultimate low-friction pattern
- **Cost as primary lens** appeals to business users who care about spend

---

## 9. Arize Phoenix

**Source**: [Arize Phoenix](https://phoenix.arize.com/) | [Observe 2025 Releases](https://arize.com/blog/observe-2025-releases/)

### Dashboard Components

1. **Traces View**: OpenTelemetry-based trace visualization with span trees
2. **Spans View**: Individual span analysis with latency, token count, evaluation metrics
3. **Agents Tab** (NEW 2025): Dedicated tab for agent orchestration visualization

### Agent Visibility (Key Innovation)

**Interactive Flowchart**: Automatically visualizes agent runs as an interactive node-based flowchart showing how agents, tools, and components interact step-by-step.

- Tracks node transitions, agent handoffs, and metadata automatically
- Zero-configuration for compatible frameworks (Agno, AutoGen, CrewAI, LangGraph, OpenAI Agents, SmolAgents)
- Graph nodes link directly to corresponding span data for latency and failure analysis
- "What took four hours of manual JSON parsing can be reduced to 30 seconds of visual inspection"

**Agent Graph and Path Visualization**: Abstracts individual spans into a node-based graph, mapping the application flow in a human-understandable way.

### Key UX Patterns

- **Zero-config agent visualization**: Automatically detects agentic patterns and renders flowchart. No manual annotation needed.
- **Span-to-graph linking**: Click any node in the agent graph to jump to the underlying span with full detail.
- **Framework-agnostic**: Works with 6+ agent frameworks automatically.
- **Cost tracking**: Track LLM usage and cost across models, prompts, and users.

### STEAL THIS
- **Zero-config interactive flowchart** from traces is the holy grail. No manual graph building.
- **Dedicated Agents tab** alongside Traces and Spans tabs
- **Span-to-graph bidirectional linking**: click graph node to see span, click span to highlight in graph

---

## 10. Braintrust

**Source**: [Braintrust](https://www.braintrust.dev/) | [Agent Observability 2026](https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026)

### Dashboard Components

- **Expandable tree views**: Every agent step with inputs, outputs, timing, and costs. Recursive tree with expand/collapse.
- **Chain-of-thought visualization**: Intermediate reasoning steps for agents using reasoning models. Shows WHY the agent made specific decisions.
- **Side-by-side trace comparison**: Compare two traces to see exactly what changed between runs.
- **Live dashboards**: Real-time request flows with drill-down into individual traces. Surfaces slowest calls, highest token consumption, error patterns.

### Key UX Patterns

- **Evaluation-first architecture**: Every code change triggers automated evaluation. Catching issues, diagnosing root causes, and preventing recurrence happen in the same system.
- **Side-by-side diff of traces**: Compare two agent runs to understand behavioral changes. Like `git diff` for agent behavior.
- **Chain-of-thought rendering**: Not just showing WHAT happened, but WHY. Reasoning steps are first-class UI elements.

### STEAL THIS
- **Side-by-side trace diff** is incredibly powerful for debugging regressions
- **Chain-of-thought as first-class UI** (not hidden in logs)
- **Evaluation integrated into the trace view** (not a separate tool)

---

## 11. AG-UI Protocol (CopilotKit)

**Source**: [AG-UI Protocol](https://www.copilotkit.ai/ag-ui) | [CopilotKit](https://www.copilotkit.ai/)

### Protocol Design

AG-UI is an open, lightweight, event-based protocol defining how agents communicate with frontends. Adopted by Google, LangChain, AWS, Microsoft, Mastra, PydanticAI.

**Event Types**:
- `TEXT_MESSAGE_CONTENT`: Streaming text from agent
- `TOOL_CALL_START` / `TOOL_CALL_END`: Tool invocation lifecycle
- `STATE_DELTA`: Incremental state updates

**Capabilities**:
- Bi-directional state synchronization (read/write or read-only)
- Tool-Based GenUI: Agents emit tool calls that render as UI components
- Agentic GenUI: Agents dynamically specify which UI to render
- Shared State: Application and agent state stay synced
- Human in the Loop: Pause for user input, resume after
- Predictive Updates: Optimistic UI updates before confirmation

### STEAL THIS
- **Event-based protocol** for agent-to-UI communication. Define a small set of event types and build all UI reactively.
- **STATE_DELTA pattern**: Send incremental state updates, not full state. Efficient for real-time streaming.
- **Tool calls as UI components**: Each tool call type can map to a custom React component for rich rendering.

---

## 12. Agentic Design Patterns (Cross-Platform)

**Source**: [Agentic Design Patterns](https://agentic-design.ai/patterns/ui-ux-patterns) | [Smashing Magazine (Feb 2026)](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)

### Pattern 1: Intent Preview (Pre-Action Control)

Show the user what the agent PLANS to do before doing it:
- Clear summary of planned actions in plain language
- Sequential step breakdown for multi-step operations
- Three choices: **Proceed** | **Edit** | **Handle Myself**
- Non-negotiable for irreversible actions, financial transactions, data sharing
- Target: >85% acceptance rate without modification

### Pattern 2: Autonomy Dial (Progressive Authorization)

Four-tier permission model per task type:
1. **Observe & Suggest**: Notifications only
2. **Plan & Propose**: Agent creates plans, user reviews
3. **Act with Confirmation**: Agent prepares, user gives final approval
4. **Act Autonomously**: Pre-approved tasks execute with post-action notification

Per-task-type granularity (e.g., separate dials for "send Slack alert" vs "pause campaign").

### Pattern 3: Progressive Disclosure (Three-Layer)

1. **Summary Layer**: Final recommendation + confidence score
2. **Detailed Layer**: Step-by-step reasoning, alternatives considered, decision factors
3. **Technical Layer**: Full execution trace, API responses, model parameters, token usage

Implementation: Expandable decision trees, collapsible panels with "show reasoning" toggles, breadcrumb navigation. Max 3-4 nesting levels. Lazy-load technical details.

State management: Remember user's disclosure preferences per session. Smooth animations (200-300ms).

### Pattern 4: Confidence Visualization

- **Color coding**: Green (high 95%+) | Orange/Yellow (medium ~70%) | Red (low <30%)
- Show ranges, not point estimates: "75-85% likely" with error bars
- Multiple scenarios: "Most likely" vs "Alternative" options
- Badge system: "High/Medium/Low Confidence" labels
- Never show false precision (avoid "99.73%", say "very high")

### Pattern 5: Action Audit & Undo

- Chronological timeline of all agent-initiated actions
- Status indicators: successful | in-progress | undone
- Time-limited undo windows with transparent expiration ("Undo available for 15 min")
- Clearly communicate when actions become irreversible
- Target: <5% reversion rate

### Pattern 6: Escalation Pathway

Three types:
1. **Clarification requests**: "Do you mean X or Y?"
2. **Option presentation**: Multiple valid alternatives for user selection
3. **Human handoff**: "This seems unusual. Should a human review this?"

Healthy escalation frequency: 5-15% of total tasks.

### STEAL THIS (ALL OF THESE)
- **Intent Preview** before every medium/high-risk action
- **Autonomy Dial** per-action-type (our existing low/medium/high maps perfectly to tiers 2-4)
- **Three-layer progressive disclosure** for investigation results
- **Confidence badges** with color coding on every recommendation
- **Undo windows** with visible countdown timers
- **Escalation as a structured UI** (not just a Slack message)

---

## 13. Stealable Patterns Summary

### Highest Priority (Implement First)

| Pattern | Source | Why It Matters |
|---------|--------|----------------|
| **Waterfall Timeline** | AgentOps | Chrome DevTools pattern. Left: timeline bars. Right: detail panel. Everyone already knows this UX. |
| **Three Views** (Graph/Timeline/Log) | Langfuse | Different users want different views of the same data. Toggle between flow, performance, and raw detail. |
| **Intent Preview** | Smashing Magazine | Show planned actions BEFORE execution. Proceed/Edit/Handle Myself buttons. |
| **Progressive Disclosure** (3 layers) | Agentic Design | Summary -> Reasoning -> Technical. Collapsible panels. Don't overwhelm. |
| **Confidence Badges** | Agentic Design | Green/Orange/Red badges on every recommendation. Ranges not points. |

### High Priority (Implement Second)

| Pattern | Source | Why It Matters |
|---------|--------|----------------|
| **Zero-config Agent Flowchart** | Arize Phoenix | Auto-infer the investigation graph from span timing. No manual wiring. |
| **State Editing Mid-Execution** | LangGraph Studio | Click any step, modify the state, resume. "What-if" for investigations. |
| **Todo Checklist Progress** | Windsurf | Simple checkbox list showing investigation progress. Universal UX. |
| **Side-by-Side Trace Diff** | Braintrust | Compare two investigation runs. Like git diff for agent behavior. |
| **Context Pills** | Cursor | Inline badges showing which data sources each agent is using. |

### Nice-to-Have (Implement Third)

| Pattern | Source | Why It Matters |
|---------|--------|----------------|
| **Mission Control Grid** | Cursor | Monitor multiple parallel investigations in a grid view. |
| **Arena Mode** | Windsurf | A/B test two investigation strategies side-by-side. |
| **Autonomy Dial** | Smashing Magazine | Per-action-type permission slider (observe/propose/confirm/auto). |
| **Community Gallery** | AutoGen Studio | Reusable investigation templates that can be shared. |
| **Dual-Mode Creation** | CrewAI | Chat + visual canvas sharing state. Build via conversation or drag-drop. |
| **Session Replay** | AgentOps | Rewind and replay past investigations with scrubbing. |
| **Checkpoint Rollback** | Claude Code / Windsurf | Save state before each step, instant rollback with Esc-Esc. |

### Cross-Cutting Patterns (Apply Everywhere)

| Pattern | Implementation |
|---------|---------------|
| **Relative color coding** | Color nodes by percentile vs siblings, not absolute values (Langfuse) |
| **Lazy-load details** | Only fetch technical-layer data when expanded (Progressive Disclosure) |
| **Remember preferences** | Persist which disclosure level user prefers per session |
| **200-300ms transitions** | Smooth animations on expand/collapse to reduce cognitive jarring |
| **Event-based streaming** | Use SSE with typed events (TEXT, TOOL_START, TOOL_END, STATE_DELTA) per AG-UI |
| **Cost as primary metric** | Surface token cost prominently, not buried in details (Helicone) |
| **Undo with countdown** | Visible timer on reversible actions (Agentic Design) |

---

## Architecture Implications for Decision Canvas

Based on this research, our agent monitoring UI should have:

### Core Layout
```
+------------------+----------------------------+------------------+
|                  |                            |                  |
|   Session List   |    Main Investigation      |   Detail Panel   |
|   + New Chat     |    Area (3 view modes)     |   (context-     |
|                  |                            |    sensitive)    |
|   [sessions]     |   [Graph | Timeline | Log] |                  |
|                  |                            |   Click any      |
|                  |   Investigation flow with  |   event to see   |
|                  |   streaming events,        |   full details,  |
|                  |   tool calls, decisions    |   edit state,    |
|                  |                            |   or intervene   |
|                  |   +---------------------+  |                  |
|                  |   | Decision Canvas     |  |   [Approve]      |
|                  |   | (capsule output)    |  |   [Reject]       |
|                  |   +---------------------+  |   [Modify]       |
+------------------+----------------------------+------------------+
```

### Event Stream Protocol
```typescript
// AG-UI-inspired event types for our SSE stream
type AgentEvent =
  | { type: 'THINKING'; content: string }           // Agent reasoning
  | { type: 'TOOL_CALL_START'; tool: string; args: any }
  | { type: 'TOOL_CALL_END'; tool: string; result: any }
  | { type: 'METRIC_QUERY'; metric: string; value: number }
  | { type: 'HYPOTHESIS'; text: string; confidence: number }
  | { type: 'APPROVAL_NEEDED'; action: Action; risk: 'low'|'medium'|'high' }
  | { type: 'DECISION_PACKET'; packet: DecisionCapsule }
  | { type: 'STATE_DELTA'; path: string; value: any }
  | { type: 'CHECKPOINT'; id: string; label: string }
  | { type: 'ERROR'; message: string; recoverable: boolean }
```

### Human-in-the-Loop UI Components
```
+------------------------------------------+
| APPROVAL NEEDED                    [HIGH] |
|                                          |
| Agent wants to: Pause Google Shopping    |
| campaign (spend: $2,400/day)             |
|                                          |
| Reason: CPC spike 47% above threshold.  |
| ROAS dropped to 2.1x (target: 4.0x).   |
|                                          |
| Confidence: ████████░░ 82%              |
|                                          |
| Impact: -$2,400/day spend, estimated    |
| +$1,200/day savings at current ROAS     |
|                                          |
| [Approve] [Modify & Approve] [Reject]   |
| Undo available for 15 minutes            |
+------------------------------------------+
```

### Progressive Disclosure for Investigation Results
```
Layer 1 (always visible):
  "ROAS dropped to 2.8x (target 4.0x) due to CPC spike in Google Shopping"
  [Confidence: 87%] [Impact: -$3,200/day]

Layer 2 (click "Show reasoning"):
  Step 1: Detected ROAS breach at 2.8x (30% below target)
  Step 2: Decomposed ROAS = Revenue / Spend
  Step 3: Revenue stable ($12,400/day), Spend spiked 35%
  Step 4: Traced to CPC increase in Google Shopping (0.85 -> 1.24)
  Step 5: Isolated to mobile device segment (68% of impact)

Layer 3 (click "Show technical details"):
  API calls: /api/marketing-mix/charts/roas-trending (14ms)
  Causal graph: get_upstream_causes("roas", depth=3) -> [cpc, spend]
  Data freshness: Google Ads last sync 2h ago (within SLA)
  Tokens used: 4,230 input / 1,890 output ($0.08)
  Full trace: [View in Timeline] [View as Graph]
```

---

## Sources

- [CrewAI Enterprise](https://www.crewai.com/)
- [CrewAI Studio Docs](https://docs.crewai.com/en/enterprise/features/crew-studio)
- [SigNoz CrewAI Dashboard](https://signoz.io/docs/dashboards/dashboard-templates/crewai-dashboard/)
- [LangGraph Studio Blog](https://blog.langchain.com/langgraph-studio-the-first-agent-ide/)
- [LangSmith Studio Docs](https://docs.langchain.com/langsmith/studio)
- [LangSmith Observability](https://www.langchain.com/langsmith/observability)
- [AutoGen Studio Docs](https://microsoft.github.io/autogen/dev//user-guide/autogenstudio-user-guide/index.html)
- [AutoGen Studio Research Blog](https://www.microsoft.com/en-us/research/blog/introducing-autogen-studio-a-low-code-interface-for-building-multi-agent-workflows/)
- [Strands Agents](https://strandsagents.com/latest/)
- [Strands Agents Deep Dive](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/)
- [Cursor 2.0](https://www.codecademy.com/article/cursor-2-0-new-ai-model-explained)
- [Windsurf Cascade](https://docs.windsurf.com/windsurf/cascade/cascade)
- [Devin 2.0](https://cognition.ai/blog/devin-2)
- [AgentOps Dashboard](https://docs.agentops.ai/v1/usage/dashboard-info)
- [Langfuse Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs)
- [Langfuse for Agents Changelog](https://langfuse.com/changelog/2025-11-05-langfuse-for-agents)
- [Langfuse Timeline View](https://langfuse.com/changelog/2024-06-12-timeline-view)
- [Helicone](https://www.helicone.ai/)
- [Arize Phoenix](https://phoenix.arize.com/)
- [Arize Observe 2025 Releases](https://arize.com/blog/observe-2025-releases/)
- [Braintrust](https://www.braintrust.dev/)
- [Braintrust Agent Observability 2026](https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026)
- [AG-UI Protocol](https://www.copilotkit.ai/ag-ui)
- [Agentic Design Patterns](https://agentic-design.ai/patterns/ui-ux-patterns)
- [Confidence Visualization Patterns](https://agentic-design.ai/patterns/ui-ux-patterns/confidence-visualization-patterns)
- [Progressive Disclosure Patterns](https://agentic-design.ai/patterns/ui-ux-patterns/progressive-disclosure-patterns)
- [Smashing Magazine: Designing for Agentic AI (Feb 2026)](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)
- [AI Agent Observability Tools 2026](https://research.aimultiple.com/agentic-monitoring/)
- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [Datadog + Strands](https://www.datadoghq.com/blog/llm-aws-strands/)
