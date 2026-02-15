# OpenClaw Skills & Tools Platform — Research Report

**Date:** 2026-02-14
**Focus:** Understanding OpenClaw's skills/tools architecture for potential integration with Baap
**Research Scope:** `/skills/`, `/src/agents/skills/`, `/src/plugin-sdk/`, `/extensions/`, documentation

---

## Executive Summary

OpenClaw has built a **sophisticated, multi-layered skills platform** that extends far beyond simple markdown instructions. It combines:

1. **Progressive Disclosure** — Skills load metadata first, then body content, then bundled resources only when needed
2. **Workspace Scoping** — Skills cascade from bundled → managed → workspace → project-specific `.agents/skills/`
3. **Dependency-Aware Loading** — Skills declare binary/env/config requirements and are auto-filtered based on platform
4. **Self-Contained Packaging** — Skills ship as `.skill` files (zipped archives) with scripts, references, and assets
5. **Installation Automation** — Skills include install specs for brew/node/go/uv/download
6. **Plugin Integration** — Plugins can contribute skills, tools, gateway methods, and commands
7. **MCP Support** — `mcporter` skill enables direct interaction with Model Context Protocol servers

This is **far more sophisticated** than Baap's current markdown-only `.claude/skills/` approach.

---

## 1. Skill Definition — Schema & Format

### 1.1 SKILL.md Structure

Every skill is defined by a **SKILL.md** file with YAML frontmatter + Markdown body:

```markdown
---
name: github
description: "Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries."
metadata:
  {
    "openclaw":
      {
        "emoji": "🐙",
        "requires": { "bins": ["gh"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "gh",
              "bins": ["gh"],
              "label": "Install GitHub CLI (brew)",
            }
          ]
      }
  }
---

# GitHub Skill
[Markdown instructions here...]
```

### 1.2 Required Fields

| Field | Location | Purpose |
|-------|----------|---------|
| `name` | frontmatter | Skill identifier (lowercase-hyphen-case, max 64 chars) |
| `description` | frontmatter | **PRIMARY TRIGGER** — Model reads this to decide when to invoke skill |
| Markdown body | After frontmatter | Instructions loaded AFTER skill triggers |

**Critical insight:** The `description` field is the **only field the model reads before triggering**. It must be comprehensive and include "when to use" scenarios. The body is NOT loaded until after the skill triggers.

### 1.3 Optional OpenClaw Metadata

Nested under `metadata.openclaw`:

| Field | Type | Purpose |
|-------|------|---------|
| `emoji` | string | Icon for UI display |
| `homepage` | string | Documentation URL |
| `skillKey` | string | Override config key (default = skill name) |
| `primaryEnv` | string | Primary env var (enables apiKey substitution) |
| `os` | string[] | Platform filter (`["darwin", "linux"]`) |
| `always` | boolean | Always include (skip all requirements checks) |
| `requires.bins` | string[] | Required binaries (ALL must exist) |
| `requires.anyBins` | string[] | At least ONE must exist |
| `requires.env` | string[] | Required environment variables |
| `requires.config` | string[] | Config paths that must be truthy |
| `install` | InstallSpec[] | Installation methods (brew/node/go/uv/download) |

### 1.4 Invocation Policy (Frontmatter)

```yaml
user-invocable: true  # Can users trigger via slash command?
disable-model-invocation: false  # Exclude from model prompt?
command-dispatch: tool  # Auto-dispatch to tool instead of LLM
command-tool: my_tool_name  # Tool to invoke
command-arg-mode: raw  # How to pass args
```

### 1.5 Install Specs

Skills can define **multiple installation methods** with platform-specific targeting:

```json
{
  "id": "brew",
  "kind": "brew",
  "formula": "gh",
  "bins": ["gh"],
  "os": ["darwin", "linux"],
  "label": "Install GitHub CLI (brew)"
}
```

**Supported kinds:**
- `brew` — Homebrew formula
- `node` — npm/pnpm/yarn/bun package
- `go` — Go module
- `uv` — Python UV package
- `download` — Direct download + extract

---

## 2. Skill Types — Bundled vs Managed vs Workspace

OpenClaw has a **cascading skill precedence** system:

### 2.1 Skill Source Hierarchy (Lowest to Highest Precedence)

```
extraDirs (config.skills.load.extraDirs)
  ↓
bundled (skills/ in OpenClaw repo)
  ↓
managed (~/.openclaw/skills/)
  ↓
personal agents (~/.agents/skills/)
  ↓
project agents (<workspace>/.agents/skills/)
  ↓
workspace (<workspace>/skills/)
```

**Key rules:**
- Higher precedence **overwrites** lower (by skill name)
- Bundled skills can be **allowlisted** via `config.skills.allowBundled`
- Plugin-contributed skills inject into extraDirs

### 2.2 Skill Sources

| Source | Location | Use Case |
|--------|----------|----------|
| **Bundled** | `openclaw/skills/` | OpenClaw-provided (54 skills) |
| **Managed** | `~/.openclaw/skills/` | User-installed via `openclaw skills install` |
| **Personal Agents** | `~/.agents/skills/` | Global agent-facing skills |
| **Project Agents** | `<workspace>/.agents/skills/` | Project-specific agent skills |
| **Workspace** | `<workspace>/skills/` | Workspace-local skills |
| **Plugin-contributed** | Plugins export skill dirs | Extension-provided skills |

**Critical insight:** OpenClaw supports **both** the Pi Coding Agent `.agents/skills/` convention AND OpenClaw's native `skills/` directory. This enables cross-tool compatibility.

### 2.3 Bundled Skill Allowlist

Bundled skills (from OpenClaw repo) can be gated:

```json
{
  "skills": {
    "allowBundled": ["github", "1password", "tmux"]
  }
}
```

If unset, all bundled skills load. This prevents "skill bloat" when you only want specific bundled skills.

---

## 3. Tool Registration — How Tools Get to the Agent

### 3.1 Skills vs Tools

**Skills** and **Tools** are DIFFERENT:

- **Skill** = Markdown instructions + optional bundled resources
- **Tool** = Executable function exposed to the LLM (TypeScript implementation)

Skills can **reference** tools, but they don't define them. Tools come from:

1. **Core tools** (built into OpenClaw)
2. **Plugin-contributed tools**
3. **MCP servers** (via `mcporter` skill)

### 3.2 Plugin Tool Registration

Plugins export a `tools` function that returns tool factories:

```typescript
// Plugin SDK export
export type OpenClawPluginToolFactory = (
  ctx: OpenClawPluginToolContext,
) => AnyAgentTool | AnyAgentTool[] | null | undefined;

// Example plugin tool
export function tools(ctx: OpenClawPluginToolContext): AnyAgentTool[] {
  return [
    {
      name: "my_tool",
      description: "Does something cool",
      inputSchema: { /* JSON Schema */ },
      async handler(input) {
        // Implementation
      }
    }
  ];
}
```

**Plugin tool context includes:**
- `config` — OpenClaw config
- `workspaceDir` — Current workspace
- `agentDir` — Agent directory
- `sessionKey` — Current session
- `sandboxed` — Whether sandboxed

### 3.3 MCP Integration (mcporter Skill)

The `mcporter` skill enables **direct MCP server interaction**:

```bash
# List MCP servers
mcporter list

# Call MCP tool
mcporter call linear.list_issues team=ENG limit:5

# Auth with OAuth
mcporter auth linear

# Generate TypeScript client
mcporter emit-ts linear --mode client
```

**Key capabilities:**
- HTTP or stdio MCP servers
- OAuth flow support
- CLI generation from MCP schemas
- Ad-hoc server invocation

This is HUGE — it means OpenClaw can consume any MCP server as a skill.

---

## 4. Plugin SDK — API Surface for Developers

### 4.1 Plugin Exports (extension.ts)

Plugins export an object with these optional methods:

```typescript
export default {
  // Metadata
  id: "my-plugin",
  label: "My Plugin",
  version: "1.0.0",

  // Lifecycle
  async init(runtime: PluginRuntime) { },
  async dispose() { },

  // Tool contribution
  tools(ctx: OpenClawPluginToolContext): AnyAgentTool[] { },

  // Skill contribution
  skillDirs?: string[],  // Paths to skill directories

  // Gateway methods (HTTP endpoints)
  gatewayMethods(): OpenClawPluginGatewayMethod[] { },

  // Commands (slash commands)
  commands(): OpenClawPluginCommandDefinition[] { },

  // HTTP routes
  async handleHttp(req, res): Promise<boolean> { },

  // Hooks
  hooks: {
    "run:started": async (event) => { }
  }
};
```

### 4.2 Plugin Runtime

Plugins receive a `PluginRuntime` object in `init()`:

```typescript
type PluginRuntime = {
  logger: PluginLogger;
  config: OpenClawConfig;
  workspaceDir?: string;
  pluginConfig?: Record<string, unknown>;
  registerHttpRoute(path: string, handler: HttpRouteHandler): void;
  emitEvent(name: string, payload: unknown): void;
};
```

### 4.3 Plugin Discovery

Plugins are discovered from:

1. **Bundled** — `extensions/` in OpenClaw repo
2. **Installed** — `~/.openclaw/extensions/`
3. **Config paths** — `config.plugins.load.paths`

Plugins can be:
- **Single files** (`.ts`, `.js`, `.mjs`)
- **npm packages** with `package.json` metadata

### 4.4 Plugin Config Schema

Plugins can define config schemas with UI hints:

```typescript
export const configSchema: OpenClawPluginConfigSchema = {
  safeParse(value) {
    // Zod validation
  },
  uiHints: {
    apiKey: {
      label: "API Key",
      sensitive: true,
      placeholder: "sk-..."
    }
  }
};
```

---

## 5. Skill Discovery — How the Agent Finds Skills

### 5.1 Discovery Flow

```
1. Load config (openclaw.json)
   ↓
2. Scan skill directories (bundled, managed, workspace, .agents, plugins)
   ↓
3. Parse SKILL.md frontmatter for each
   ↓
4. Build SkillEntry objects (skill + frontmatter + metadata)
   ↓
5. Filter by eligibility (os, bins, env, config, allowlist)
   ↓
6. Build skills snapshot (name + description for all eligible)
   ↓
7. Format into prompt text
   ↓
8. Inject into agent system prompt
```

### 5.2 Eligibility Checks

Skills are filtered based on:

| Check | Logic |
|-------|-------|
| `enabled` | `config.skills.entries.<skillKey>.enabled !== false` |
| `allowBundled` | Bundled skills must be in allowlist (if set) |
| `os` | Current platform OR remote platform must match |
| `requires.bins` | ALL binaries must exist locally OR remotely |
| `requires.anyBins` | At least ONE binary must exist |
| `requires.env` | ENV vars OR `apiKey` in config must exist |
| `requires.config` | Config paths must resolve to truthy values |
| `always` | Bypass all checks if true |

### 5.3 Remote Mode

OpenClaw supports **remote gateway mode** where skills run on a different machine. Eligibility checks account for this:

```typescript
type SkillEligibilityContext = {
  remote?: {
    platforms: string[];  // Remote OS platforms
    hasBin: (bin: string) => boolean;  // Check remote bins
    hasAnyBin: (bins: string[]) => boolean;
    note?: string;  // Injected into prompt
  };
};
```

This enables skills to be filtered based on **remote gateway capabilities**, not just local.

---

## 6. Workspace Scoping — Project-Specific Skills

### 6.1 Workspace Directory Structure

```
my-project/
├── skills/               # Workspace skills (highest precedence)
│   └── my-skill/
│       └── SKILL.md
├── .agents/             # Pi Coding Agent compatible
│   └── skills/
│       └── agent-skill/
│           └── SKILL.md
└── openclaw.json        # Workspace config
```

### 6.2 Config Scoping

Skills can be configured per workspace:

```json
{
  "skills": {
    "allowBundled": ["github"],  // Only allow github bundled skill
    "entries": {
      "my-api": {
        "enabled": true,
        "apiKey": "sk-...",
        "env": {
          "API_BASE_URL": "https://api.example.com"
        },
        "config": {
          "rate_limit": 100
        }
      }
    },
    "load": {
      "extraDirs": ["/path/to/custom/skills"]
    }
  }
}
```

### 6.3 Skill Sync (Sandbox)

When running in **sandboxed mode**, OpenClaw syncs skills into the sandbox workspace:

```typescript
await syncSkillsToWorkspace({
  sourceWorkspaceDir: "/host/project",
  targetWorkspaceDir: "/sandbox/project",
  config
});
```

This ensures sandboxed agents have the same skills as the host.

---

## 7. Extension Lifecycle — Install, Update, Uninstall

### 7.1 Skill Installation

OpenClaw provides **automated skill installation**:

```bash
# List available skills
openclaw skills list

# Install a skill
openclaw skills install <skill-name>

# Install dependencies
openclaw skills install github --deps
```

**Installation flow:**
1. Parse skill metadata
2. Check platform compatibility
3. Find matching install spec
4. Execute installer (brew/node/go/uv/download)
5. Verify binary installation
6. Enable skill in config

### 7.2 Skill Update

Skills are **immutable once installed** (they're markdown + scripts). Updates happen by:

1. Replacing the skill directory
2. Re-running dependency installers
3. Syncing to sandboxed workspaces

### 7.3 Skill Uninstall

```bash
openclaw skills remove <skill-name>
```

**Uninstall flow:**
1. Remove from managed skills directory
2. Optionally remove dependencies (if not used by other skills)
3. Remove from config `skills.entries`

### 7.4 Plugin Lifecycle

Plugins have a richer lifecycle:

```typescript
// Plugin init (on load)
async init(runtime: PluginRuntime) {
  this.db = await openDB();
}

// Plugin dispose (on unload/reload)
async dispose() {
  await this.db.close();
}
```

**Install tracking:**

```json
{
  "plugins": {
    "installs": {
      "voice-call": {
        "source": "npm",
        "spec": "voice-call@1.2.0",
        "version": "1.2.0",
        "installedAt": "2025-01-15T..."
      }
    }
  }
}
```

---

## 8. Bundled Resources — Scripts, References, Assets

### 8.1 Directory Structure

```
skill-name/
├── SKILL.md              # Required
├── scripts/              # Executable code
│   ├── rotate_pdf.py
│   └── helper.sh
├── references/           # Documentation (loaded into context)
│   ├── api_reference.md
│   └── schema.md
└── assets/               # Files used in output
    ├── template.pptx
    └── logo.png
```

### 8.2 Resource Types

| Directory | Purpose | Context Loading | Examples |
|-----------|---------|----------------|----------|
| `scripts/` | Executable code | Optional (for patching) | Python scripts, shell scripts, CLI wrappers |
| `references/` | Documentation | On-demand | API docs, schemas, detailed workflows |
| `assets/` | Output resources | Never | Templates, boilerplate, images, fonts |

### 8.3 Progressive Disclosure Pattern

OpenClaw uses a **three-level loading strategy**:

1. **Metadata** (name + description) — Always in context (~100 words)
2. **SKILL.md body** — Loaded when skill triggers (<5k words)
3. **Bundled resources** — Loaded only when explicitly referenced

**Design principle:** Keep SKILL.md lean (<500 lines). Split large content into references. Link to them from SKILL.md with clear "when to read" guidance.

**Example pattern:**

```markdown
## Advanced Features

- **Form filling**: See [references/forms.md](references/forms.md) for complete guide
- **API reference**: See [references/api.md](references/api.md) for all methods
```

Agent reads references ONLY when needed, minimizing context bloat.

### 8.4 Skill Packaging

Skills are distributed as `.skill` files (ZIP archives):

```bash
# Create skill
scripts/init_skill.py my-skill --path skills/public --resources scripts,references

# Package skill
scripts/package_skill.py skills/public/my-skill
# Creates: my-skill.skill (ZIP with proper structure)
```

**Validation** happens automatically before packaging:
- YAML frontmatter format
- Required fields (name, description)
- File organization
- Description quality (comprehensive + "when to use")

---

## 9. Integration Analysis for Baap

### 9.1 Current Baap Architecture

**Baap's skills:**
- Location: `.claude/skills/<name>/SKILL.md`
- Format: Pure markdown instructions
- No frontmatter, no metadata
- No bundled resources
- No installation specs
- No dependency checking
- No workspace scoping
- No progressive disclosure

**Baap's MCP tools:**
- `ownership-graph` — Queries code ownership data
- `db-tools` — Queries Snowflake
- Custom MCP servers in `.mcp.json`

### 9.2 Adoption Opportunities

#### Level 1: Add Frontmatter (Low Effort, High Value)

**Change:** Add YAML frontmatter to existing `.claude/skills/` files.

```markdown
---
name: investigate-metric
description: Full investigation protocol for metric breaches. Use when a metric crosses threshold or shows anomaly. Walks causal graph, checks data quality, forecasts impact, recommends actions.
metadata:
  {
    "baap": {
      "requires": { "bins": ["bd"], "config": ["snowflake.enabled"] },
      "install": [
        { "kind": "uv", "package": "beads-cli", "bins": ["bd"] }
      ]
    }
  }
---

# Investigate Metric
[Existing content...]
```

**Benefits:**
- Better skill triggering (comprehensive descriptions)
- Dependency awareness
- Future-proof for OpenClaw-style loading

#### Level 2: Progressive Disclosure (Medium Effort, Context Savings)

**Change:** Split large skills into references.

**Example: `investigate-metric`**

```
.claude/skills/investigate-metric/
├── SKILL.md                    # Core workflow (< 500 lines)
├── references/
│   ├── causal-graph.md         # Graph traversal patterns
│   ├── data-quality.md         # Quality check procedures
│   └── impact-forecasting.md   # Revenue impact formulas
```

**Benefits:**
- Reduce context bloat (load references only when needed)
- Easier maintenance
- Better organization

#### Level 3: Bundled Scripts (Medium-High Effort, Determinism)

**Change:** Move repeated logic into scripts.

**Example: `trace-lineage`**

```
.claude/skills/trace-lineage/
├── SKILL.md
└── scripts/
    └── walk_lineage.py         # Deterministic lineage walking
```

**Benefits:**
- Deterministic execution (no LLM hallucination)
- Token efficiency (scripts execute without loading into context)
- Faster execution

#### Level 4: MCP Tool Skills (High Value, Moderate Effort)

**Change:** Treat MCP tools as skills.

**Current:** MCP tools are invisible to agents (they discover them via tool schema).

**Proposed:** Create "skill wrappers" for MCP tools:

```
.claude/skills/ownership-graph/
└── SKILL.md
```

```markdown
---
name: ownership-graph
description: Query code ownership data. Use when investigating who owns specific code, when code was last modified, or finding related files.
metadata:
  {
    "baap": {
      "requires": { "config": ["mcp.servers.ownership-graph"] },
      "tool-wrapper": "ownership_graph"
    }
  }
---

# Ownership Graph

Use the `ownership_graph` tool to query code ownership.

## Common Queries

**Who owns this file?**
```json
{
  "operation": "get_owner",
  "path": "src/api/agent_stream.py"
}
```
[More examples...]
```

**Benefits:**
- Agents understand WHEN to use MCP tools
- Documentation co-located with tool
- Better triggering context

#### Level 5: Workspace Scoping (High Effort, Multi-Project Support)

**Change:** Support project-specific skills.

**Current:** All skills global in `.claude/`.

**Proposed:**

```
decision-canvas-os/
├── .claude/                    # Global Baap skills
│   └── skills/
└── skills/                     # Project-specific skills
    └── bc-analytics-query/
        └── SKILL.md
```

**Benefits:**
- Project-specific knowledge
- No cross-contamination between projects
- Easier skill sharing (commit to repo)

### 9.3 Agent Specs as Skills?

**Question:** Should Baap agent specs (`.claude/agents/{name}/agent.md`) become OpenClaw-style skills?

**Analysis:**

| Aspect | Current (agent.md) | As Skill |
|--------|-------------------|----------|
| **Triggering** | Explicit handoff | Model decides when to invoke |
| **Scope** | Agent-specific identity | Shareable capability |
| **Precedence** | N/A | Workspace can override |
| **Bundled resources** | No | Yes |

**Recommendation:** **Keep agents separate from skills.**

- **Agents** = Identity + personality + handoff protocol
- **Skills** = Reusable capabilities

**But:** Agent specs could **reference skills** more explicitly:

```markdown
# Causal Analyst Agent

## Capabilities

Uses these skills:
- `/root-cause-analysis` — Walk causal graph upstream
- `/trace-lineage` — Data lineage tracing
- `/ownership-graph` — Find data owners
```

### 9.4 Agent Learning (patterns.md) as Skills

**Current:** `.claude/agents/patterns.md` — Shared knowledge across agents.

**Proposed:** Treat as a **reference file** in a meta-skill:

```
.claude/skills/agent-patterns/
├── SKILL.md
└── references/
    └── patterns.md
```

```markdown
---
name: agent-patterns
description: Shared investigation patterns learned from past incidents. Reference when you encounter similar breach types or data issues.
---

# Agent Patterns

See [references/patterns.md](references/patterns.md) for learned patterns.
```

**Benefits:**
- Progressive disclosure (load only when relevant)
- Explicit skill for "learned patterns" vs embedded in agent specs
- Agents can reference when they hit similar issues

---

## 10. Detailed Integration Recommendations

### 10.1 Phase 1: Frontmatter (Week 1)

**Goal:** Make Baap skills OpenClaw-compatible.

**Tasks:**
1. Add YAML frontmatter to all `.claude/skills/*/SKILL.md`
2. Write comprehensive `description` fields (include "when to use")
3. Add `requires.bins` for skills that need `bd`, `gh`, etc.
4. Add `requires.config` for Snowflake-dependent skills

**Example migration:**

```diff
+---
+name: investigate-metric
+description: Full investigation protocol for metric breaches. Use when a metric crosses threshold or shows anomaly. Walks causal graph, checks data quality, forecasts impact, recommends actions.
+metadata:
+  {
+    "baap": {
+      "requires": { "bins": ["bd"] }
+    }
+  }
+---
+
 # Investigate Metric
```

**Validation:** Write a simple parser to check all skills have valid frontmatter.

### 10.2 Phase 2: Progressive Disclosure (Week 2-3)

**Goal:** Reduce context bloat.

**Target skills:**
- `investigate-metric` (longest)
- `root-cause-analysis`
- `trace-lineage`

**Pattern:**
1. Keep core workflow in SKILL.md (<500 lines)
2. Move detailed procedures to `references/`
3. Add explicit "See [file]" links

**Example:**

```markdown
## Data Quality Checks

Run these checks in order:

1. Freshness (SLA: 1-4 hours depending on source)
2. Completeness (>95% for critical, >80% for medium)
3. Schema changes

**For detailed procedures:** See [references/data-quality.md](references/data-quality.md)
```

### 10.3 Phase 3: MCP Skill Wrappers (Week 4)

**Goal:** Improve MCP tool discoverability.

**Create skills:**
- `ownership-graph` — Wrap MCP ownership graph tool
- `db-tools` — Wrap Snowflake query tools
- `causal-graph` — Wrap knowledge graph MCP tools

**Structure:**

```
.claude/skills/ownership-graph/
└── SKILL.md
```

```markdown
---
name: ownership-graph
description: Query code ownership data. Use when investigating who owns specific code, when code was last modified, or finding related files.
metadata:
  {
    "baap": {
      "requires": { "config": ["mcp.servers.ownership-graph"] }
    }
  }
---

# Ownership Graph

Use `ownership_graph` MCP tool to query:

## Who owns a file?

```json
{"operation": "get_owner", "path": "src/..."}
```

## When was it last modified?

```json
{"operation": "get_history", "path": "src/..."}
```
```

**Benefits:**
- Agent knows WHEN to use ownership graph
- Examples co-located with tool
- Better than relying on tool schema alone

### 10.4 Phase 4: Script Extraction (Ongoing)

**Goal:** Move deterministic logic out of LLM context.

**Candidates:**
- Snowflake queries (repetitive schema)
- Beads CLI workflows (common patterns)
- Data quality checks (deterministic formulas)

**Example: Data Quality Script**

```python
# .claude/skills/data-quality/scripts/check_freshness.py
import sys
import json
from datetime import datetime, timedelta

def check_freshness(source: str, last_updated: str, sla_hours: int):
    last = datetime.fromisoformat(last_updated)
    now = datetime.now()
    age = (now - last).total_seconds() / 3600

    return {
        "source": source,
        "age_hours": age,
        "sla_hours": sla_hours,
        "status": "ok" if age <= sla_hours else "stale",
        "breach_hours": max(0, age - sla_hours)
    }

if __name__ == "__main__":
    data = json.load(sys.stdin)
    result = check_freshness(**data)
    print(json.dumps(result))
```

**SKILL.md:**

```markdown
## Check Data Freshness

Run the freshness checker:

```bash
echo '{"source":"magento","last_updated":"2025-01-15T10:00:00","sla_hours":1}' | \
  python scripts/check_freshness.py
```

Returns JSON with status and breach hours.
```

**Benefits:**
- No hallucination (deterministic)
- Faster execution
- Easier testing

### 10.5 Phase 5: Workspace Scoping (Future)

**Goal:** Support project-specific skills.

**Changes:**
1. Support `<project>/skills/` in addition to `.claude/skills/`
2. Skills in project override global
3. Commit project skills to repo

**Use case:**
- BC_ANALYTICS project has `bc-analytics-api` skill
- Decision-canvas-os does NOT see it
- Reduces cross-contamination

**Implementation:**
- Update `context_packager.py` to scan both locations
- Apply precedence (workspace > global)

---

## 11. Key Takeaways

### 11.1 What OpenClaw Does REALLY Well

1. **Progressive Disclosure** — Metadata → Body → Resources. Minimizes context waste.
2. **Dependency Awareness** — Skills declare what they need. Auto-filtered.
3. **Installation Automation** — Skills ship with install specs. One command to setup.
4. **Workspace Scoping** — Project-specific skills. No global pollution.
5. **MCP Integration** — `mcporter` enables ANY MCP server as a skill.
6. **Plugin Architecture** — Skills + Tools + Gateway methods all extensible.

### 11.2 What Baap Should Adopt

**Immediate (Weeks 1-2):**
- ✅ Frontmatter with `description` + `requires`
- ✅ Progressive disclosure for large skills

**Medium-term (Month 1-2):**
- ✅ MCP tool skill wrappers
- ✅ Script extraction for deterministic logic
- ✅ Skill packaging (`.skill` files for sharing)

**Long-term (Quarter 1):**
- ✅ Workspace scoping
- ✅ Plugin architecture for team extensions
- ✅ Installation automation

### 11.3 What Baap Should NOT Adopt

**Avoid:**
- ❌ Converting agent specs to skills (agents ≠ skills)
- ❌ Over-engineering bundled resources (scripts only when truly deterministic)
- ❌ Complex install specs (Baap's simpler: venv + pip)

### 11.4 Risk Assessment

| Change | Effort | Risk | Value |
|--------|--------|------|-------|
| Frontmatter | Low | Low | High (better triggering) |
| Progressive disclosure | Medium | Low | High (context savings) |
| MCP wrappers | Medium | Low | High (discoverability) |
| Script extraction | Medium | Medium | Medium (determinism) |
| Workspace scoping | High | Medium | Medium (multi-project) |
| Plugin architecture | Very High | High | Low (YAGNI for now) |

---

## 12. Concrete Next Steps for Baap

### Step 1: Audit Current Skills (1 day)

**Action:** List all `.claude/skills/` and measure:
- Line count (identify candidates for splitting)
- Dependency mentions (bd, gh, snowflake)
- Repetitive code blocks (candidates for scripts)

### Step 2: Add Frontmatter (2 days)

**Action:** Migrate all skills to frontmatter format.

**Template:**

```markdown
---
name: <skill-name>
description: [Comprehensive description including WHEN to use]
metadata:
  {
    "baap": {
      "requires": { "bins": [...], "config": [...] }
    }
  }
---

[Existing content]
```

### Step 3: Split Large Skills (3 days)

**Targets:**
- `investigate-metric`
- `root-cause-analysis`
- `trace-lineage`

**Pattern:**
```
skill-name/
├── SKILL.md (core <500 lines)
└── references/
    ├── detailed-workflows.md
    └── examples.md
```

### Step 4: MCP Skill Wrappers (2 days)

**Create:**
- `ownership-graph` skill
- `db-tools` skill
- `causal-graph` skill

**Structure:** SKILL.md with usage examples + MCP tool references.

### Step 5: Extract One Script (1 day)

**Target:** Data quality freshness check (repetitive, deterministic).

**Deliverable:** `scripts/check_freshness.py` in `data-quality` skill.

### Step 6: Document Patterns (1 day)

**Action:** Write `SKILLS.md` in `.claude/` documenting:
- Frontmatter schema
- Progressive disclosure guidelines
- When to extract scripts
- MCP wrapper pattern

---

## 13. Appendix: Example Conversions

### A. Before/After: Investigate Metric Skill

**Before (Baap current):**

```markdown
# Investigate Metric

When a metric breach is detected, follow this protocol:

[3000 lines of procedures...]
```

**After (OpenClaw-style):**

```markdown
---
name: investigate-metric
description: Full investigation protocol for metric breaches. Use when a metric crosses threshold or shows anomaly. Walks causal graph, checks data quality, forecasts impact, recommends actions.
metadata:
  {
    "baap": {
      "requires": { "bins": ["bd"], "config": ["snowflake.enabled"] }
    }
  }
---

# Investigate Metric

## Quick Reference

1. Validate data quality → [references/data-quality.md](references/data-quality.md)
2. Walk causal graph → [references/causal-analysis.md](references/causal-analysis.md)
3. Forecast impact → [references/impact-forecasting.md](references/impact-forecasting.md)
4. Recommend actions → [references/action-recommendations.md](references/action-recommendations.md)

## Core Workflow

[500 lines of high-level procedure]
```

**Changes:**
- ✅ Frontmatter with description + requires
- ✅ Split into references
- ✅ Core workflow < 500 lines
- ✅ Clear navigation to detailed procedures

### B. MCP Tool Wrapper Example

**New skill: `ownership-graph`**

```markdown
---
name: ownership-graph
description: Query code ownership data. Use when investigating who owns specific code, when code was last modified, or finding related files.
metadata:
  {
    "baap": {
      "requires": { "config": ["mcp.servers.ownership-graph"] }
    }
  }
---

# Ownership Graph

Use the `ownership_graph` MCP tool to query code ownership.

## Get File Owner

```json
{
  "operation": "get_owner",
  "path": "src/api/agent_stream.py"
}
```

Returns: `{"owner": "rahil", "last_modified": "2025-01-15", ...}`

## Find Related Files

```json
{
  "operation": "find_related",
  "path": "src/api/agent_stream.py"
}
```

Returns: List of files in same ownership cluster.

## Get Modification History

```json
{
  "operation": "get_history",
  "path": "src/api/agent_stream.py",
  "limit": 10
}
```

Returns: Recent commits affecting this file.
```

**Benefits:**
- Agent knows WHEN to use ownership graph
- Examples in context
- Better than raw tool schema

---

## 14. References

**OpenClaw Files Analyzed:**
- `/tmp/openclaw-repo/skills/` — 54 bundled skills
- `/tmp/openclaw-repo/src/agents/skills/` — Skills loading system
- `/tmp/openclaw-repo/src/plugin-sdk/` — Plugin SDK
- `/tmp/openclaw-repo/skills/skill-creator/` — Skill creation tooling
- `/tmp/openclaw-repo/docs/platforms/mac/skills.md` — Skills UI docs

**Key Insights:**
- Progressive disclosure is the killer feature
- Frontmatter-driven triggering beats embedded descriptions
- Workspace scoping prevents skill pollution
- MCP integration via `mcporter` enables infinite extensibility

**Baap Integration Path:**
1. Frontmatter (immediate)
2. Progressive disclosure (quick win)
3. MCP wrappers (discoverability)
4. Script extraction (determinism)
5. Workspace scoping (multi-project future)
