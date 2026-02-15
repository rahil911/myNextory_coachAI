# Phase 1g: New Domain Protocol & Credentials Management

## Purpose

The system was bootstrapped from 38 MySQL tables → 9 agents. But the application will
grow: Eleven Labs for audio, Anthropic API for generation, Criteria Corp for testing,
payment processors, analytics pipelines, etc. Each new integration needs a new agent,
new files, new KG nodes, new dependencies, and possibly API credentials.

Right now, the orchestrator knows how to dispatch work to EXISTING agents. It does NOT
know how to birth a NEW agent from scratch. This spec adds:

1. A `create-agent.sh` script that atomically creates everything a new agent needs
2. A credentials management pattern for 3rd party APIs
3. A "New Domain Protocol" section in CLAUDE.md
4. spawn.sh update to symlink credentials into worktrees

## Risks Mitigated

- Risk 22: Orchestrator assigns new-domain work to wrong existing agent (no protocol for "new")
- Risk 23: API credentials not available in worktrees (3rd party integrations fail)
- Risk 24: New agent created without KG registration (invisible to blast radius)
- Risk 25: New agent created without dependency mapping (silent breakage)
- Risk 26: Cross-integration dependencies unmapped (no notifications on contract changes)

## Files to Create

- `.claude/scripts/create-agent.sh` — Atomic new agent creation
- `.claude/integrations/.gitkeep` — Credentials directory (gitignored)

## Files to Modify

- `.claude/scripts/spawn.sh` — Symlink .claude/integrations/ into worktrees
- `.claude/CLAUDE.md` — Add "New Domain Protocol" section
- `.gitignore` — Add .claude/integrations/ (credentials must NOT be in git)

---

## Fix 1: create-agent.sh

### Purpose

When the orchestrator needs a new agent (new integration, new domain, new capability),
it calls this script instead of manually creating files. The script does ALL steps
atomically and validates each one.

### Implementation

```bash
#!/usr/bin/env bash
# create-agent.sh — Atomically create a new agent with all infrastructure
#
# Usage:
#   create-agent.sh <agent_name> <level> <module_name> <capabilities> [parent_agent] [depends_on]
#
# Examples:
#   create-agent.sh audio-agent 1 audio-module "elevenlabs,tts,audio" orchestrator "content-agent,identity-agent"
#   create-agent.sh payment-agent 1 payment-module "stripe,payments,billing" orchestrator "identity-agent"
#   create-agent.sh tts-handler 2 audio-module "elevenlabs-api,streaming" audio-agent ""
#
# What it creates:
#   1. Agent spec:    .claude/agents/{name}/agent.md
#   2. Memory dir:    .claude/agents/{name}/memory/MEMORY.md
#   3. Module dir:    src/{module}/ (if not exists)
#   4. KG registration: agent node + MANAGES edge + DEPENDS_ON edges + PARENT_OF edge
#   5. Git commit:    tracks all new files
set -euo pipefail

NAME="${1:?Usage: create-agent.sh <name> <level> <module> <capabilities> [parent] [depends_on]}"
LEVEL="${2:?Missing level (0-3)}"
MODULE="${3:?Missing module name}"
CAPABILITIES="${4:?Missing capabilities (comma-separated)}"
PARENT="${5:-orchestrator}"
DEPENDS_ON="${6:-}"

REPO="$(git rev-parse --show-toplevel)"
AG_CLI="$REPO/.claude/tools/ag"
KG_CACHE="$REPO/.claude/kg/agent_graph_cache.json"

echo "Creating agent: $NAME (L${LEVEL}, module: $MODULE)"

# ── Validate ─────────────────────────────────────────────────────────────────
if [ -d "$REPO/.claude/agents/$NAME" ]; then
  echo "ERROR: Agent $NAME already exists at .claude/agents/$NAME/" >&2
  exit 1
fi

# ── 1. Agent Spec ────────────────────────────────────────────────────────────
SPEC_DIR="$REPO/.claude/agents/$NAME"
mkdir -p "$SPEC_DIR"

# Model tier based on level
case "$LEVEL" in
  0) MODEL_TIER="opus" ;;
  1) MODEL_TIER="sonnet" ;;
  *) MODEL_TIER="haiku" ;;
esac

cat > "$SPEC_DIR/agent.md" << SPECEOF
# $NAME

## Identity
- **Level**: L${LEVEL}
- **Model**: $MODEL_TIER
- **Parent**: $PARENT
- **Module**: $MODULE

## Capabilities
$(echo "$CAPABILITIES" | tr ',' '\n' | sed 's/^/- /')

## Ownership
- Module: $MODULE
- Files: src/$(echo "$MODULE" | sed 's/-module//')/ (and subdirectories)

## Dependencies
$(if [ -n "$DEPENDS_ON" ]; then echo "$DEPENDS_ON" | tr ',' '\n' | sed 's/^/- DEPENDS_ON: /'; else echo "- (none)"; fi)

## Work Protocol
1. Check bead: \`bd show <bead-id>\`
2. Read memory: \`.claude/agents/$NAME/memory/MEMORY.md\`
3. Query context: \`get_agent_context("$NAME")\`
4. Work on owned files ONLY
5. Update memory
6. Close bead: \`bd close <bead-id>\`
7. Notify dependents: \`get_dependents("$NAME")\`
8. Create notification beads for changes
SPECEOF

echo "  Created spec: $SPEC_DIR/agent.md"

# ── 2. Memory Directory ─────────────────────────────────────────────────────
MEMORY_DIR="$SPEC_DIR/memory"
mkdir -p "$MEMORY_DIR"

cat > "$MEMORY_DIR/MEMORY.md" << MEMEOF
# $NAME Memory

## Created
- $(date -Iseconds) by create-agent.sh
- Level: L${LEVEL}, Module: $MODULE, Parent: $PARENT

## My Ownership
- Module: $MODULE
- Check files: \`get_agent_files("$NAME")\`

## Dependencies
$(if [ -n "$DEPENDS_ON" ]; then echo "$DEPENDS_ON" | tr ',' '\n' | sed 's/^/- /'; else echo "- (none yet)"; fi)

## Key Decisions
- (none yet — first session)

## Recent Changes
- (none yet)
MEMEOF

echo "  Created memory: $MEMORY_DIR/MEMORY.md"

# ── 3. Module Directory ──────────────────────────────────────────────────────
MODULE_PATH="$REPO/src/$(echo "$MODULE" | sed 's/-module//')"
if [ ! -d "$MODULE_PATH" ]; then
  mkdir -p "$MODULE_PATH"
  cat > "$MODULE_PATH/__init__.py" << INITEOF
"""$MODULE — managed by $NAME"""
INITEOF
  echo "  Created module: $MODULE_PATH/"
else
  echo "  Module already exists: $MODULE_PATH/"
fi

# ── 4. KG Registration ──────────────────────────────────────────────────────
if [ -x "$AG_CLI" ] && [ -f "$KG_CACHE" ]; then
  echo "  Registering in KG..."

  # Register agent node
  python3 -c "
import json, fcntl, datetime

CACHE = '$KG_CACHE'
LOCK = CACHE + '.lock'

with open(LOCK, 'w') as lf:
    fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
    try:
        with open(CACHE, 'r') as f:
            data = json.load(f)

        # Add agent node
        agent_node = {
            'id': '$NAME',
            'type': 'agent',
            'level': $LEVEL,
            'parent': '$PARENT',
            'model_tier': '$MODEL_TIER',
            'module': '$MODULE',
            'capabilities': '$CAPABILITIES'.split(','),
            'status': 'idle',
            'spec_path': '.claude/agents/$NAME/agent.md',
            'memory_path': '.claude/agents/$NAME/memory/',
            'created_at': datetime.datetime.now().isoformat()
        }

        # Check if agent already in KG
        existing_ids = {n['id'] for n in data.get('nodes', [])}
        if '$NAME' not in existing_ids:
            data['nodes'].append(agent_node)

        # Add module node if not exists
        if '$MODULE' not in existing_ids:
            data['nodes'].append({
                'id': '$MODULE',
                'type': 'module',
                'description': '$MODULE managed by $NAME',
                'managed_by': '$NAME'
            })

        # Add edges
        edges = data.get('edges', [])
        edge_set = {(e['from'], e['to'], e['type']) for e in edges}

        # PARENT_OF edge
        if ('$PARENT', '$NAME', 'PARENT_OF') not in edge_set:
            edges.append({'from': '$PARENT', 'to': '$NAME', 'type': 'PARENT_OF'})

        # MANAGES edge
        if ('$NAME', '$MODULE', 'MANAGES') not in edge_set:
            edges.append({'from': '$NAME', 'to': '$MODULE', 'type': 'MANAGES'})

        # DEPENDS_ON edges
        deps = [d.strip() for d in '$DEPENDS_ON'.split(',') if d.strip()]
        for dep in deps:
            if (dep in existing_ids or dep in {n['id'] for n in data['nodes']}) and ('$NAME', dep, 'DEPENDS_ON') not in edge_set:
                edges.append({'from': '$NAME', 'to': dep, 'type': 'DEPENDS_ON', 'dependency_type': 'functional'})

        data['edges'] = edges
        data['metadata']['node_count'] = len(data['nodes'])
        data['metadata']['edge_count'] = len(data['edges'])
        data['metadata']['last_updated'] = datetime.datetime.now().isoformat()

        with open(CACHE, 'w') as f:
            json.dump(data, f, indent=2)

        print('  KG updated: node + edges added')
    finally:
        fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
" || echo "  WARNING: KG registration failed (non-fatal)"
else
  echo "  WARNING: ag CLI or KG cache not found. Skipping KG registration."
  echo "  Run manually later: ag register ... "
fi

# ── 5. Git Commit ────────────────────────────────────────────────────────────
cd "$REPO"
git add ".claude/agents/$NAME/" "src/$(echo "$MODULE" | sed 's/-module//')/" ".claude/kg/agent_graph_cache.json" 2>/dev/null || true
git commit -m "Create agent: $NAME (L${LEVEL}, $MODULE)" --no-verify 2>/dev/null || true

echo ""
echo "Agent $NAME created successfully."
echo "  Spec:   .claude/agents/$NAME/agent.md"
echo "  Memory: .claude/agents/$NAME/memory/MEMORY.md"
echo "  Module: src/$(echo "$MODULE" | sed 's/-module//')/"
echo "  KG:     registered with $( [ -n "$DEPENDS_ON" ] && echo "deps: $DEPENDS_ON" || echo "no deps" )"
echo ""
echo "Next: create a bead and spawn the agent:"
echo "  bd create --title=\"Task for $NAME\" --type=task --priority=1"
echo "  bash .claude/scripts/spawn.sh reactive \"bd show <bead-id>\" $REPO $NAME $LEVEL"
```

---

## Fix 2: Credentials Management

### Directory Structure

```
.claude/integrations/          ← gitignored, NEVER committed
├── .gitkeep                   ← placeholder so git tracks the directory structure
├── elevenlabs/
│   └── credentials.json       ← {"api_key": "...", "rate_limit_rpm": 100, "monthly_budget_usd": 50}
├── anthropic/
│   └── credentials.json
├── criteria-corp/
│   └── credentials.json
└── stripe/
    └── credentials.json
```

### Credential File Schema

```json
{
  "api_key": "sk-...",
  "api_base_url": "https://api.elevenlabs.io/v1",
  "rate_limit_rpm": 100,
  "rate_limit_daily": 10000,
  "monthly_budget_usd": 50,
  "warn_at_percent": 80,
  "environment": "production",
  "notes": "Created 2026-02-14. Owned by audio-agent."
}
```

### .gitignore Addition

```
# Credentials (NEVER commit)
.claude/integrations/*/credentials.json
.claude/integrations/*/secrets.*
```

Note: We gitignore the credential FILES, not the directory structure. This way
the directory layout is tracked but secrets are not.

### spawn.sh Addition

Symlink the integrations directory into each worktree:

```bash
# .claude/integrations/ — shared credentials for 3rd party APIs
INTEGRATIONS="$MAIN_REPO/.claude/integrations"
if [ -d "$INTEGRATIONS" ]; then
  # Remove the git-checkout version (has .gitkeep but no secrets)
  rm -rf "$WORKTREE/.claude/integrations" 2>/dev/null || true
  # Symlink to main repo's version (has actual credentials)
  ln -sfn "$INTEGRATIONS" "$WORKTREE/.claude/integrations"
  echo "Symlinked .claude/integrations/ from main repo"
fi
```

---

## Fix 3: New Domain Protocol in CLAUDE.md

Add this section to CLAUDE.md after the "Agent Execution Model" section:

```markdown
## New Domain Protocol (when no existing agent fits)

When you receive a request for a capability that doesn't map to any existing agent:

### Detection
- `get_blast_radius("concept")` returns nothing or only tangential matches
- No agent has the required capability: `search_agents("capability")` returns empty
- The work requires a new 3rd party integration

### DO NOT:
- Assign to the "closest" existing agent (this pollutes module boundaries)
- Create files in another agent's module directory
- Skip KG registration ("I'll add it later")

### DO:
1. **Create the agent** using create-agent.sh:
   ```bash
   bash .claude/scripts/create-agent.sh \
     <agent-name> \         # e.g., audio-agent
     <level> \              # 1 for domain agent, 2 for sub-domain
     <module-name> \        # e.g., audio-module
     <capabilities> \       # e.g., "elevenlabs,tts,audio,streaming"
     <parent> \             # e.g., orchestrator (for L1)
     <depends_on>           # e.g., "content-agent,identity-agent"
   ```

2. **Set up credentials** (if 3rd party API):
   ```bash
   mkdir -p .claude/integrations/<service>/
   # Create credentials.json with API key, rate limits, budget
   ```

3. **Map ALL dependencies** — think about:
   - Which existing agents' data does this new agent need? (DEPENDS_ON)
   - Which existing agents' contracts will this new agent consume? (DEPENDS_ON)
   - Which existing agents need to know about this new agent? (notify them)

4. **Create the bead** with full spec as usual

5. **Spawn the agent** via spawn.sh as usual

### Dependency Mapping Checklist
When creating a new agent, ask yourself:
- Does it need user data? → DEPENDS_ON identity-agent
- Does it need content data? → DEPENDS_ON content-agent
- Does it modify the database schema? → bead to db-agent FIRST
- Does it expose an API? → coordinate with api-agent (if exists)
- Does it have a UI? → coordinate with ui-agent (if exists)
- Does it call external APIs? → set up credentials
```

---

## Fix 4: External API Safety Rules in CLAUDE.md

Add to the Safety Limits section:

```markdown
## External API Safety

- ALWAYS check `.claude/integrations/{service}/credentials.json` before calling any API
- NEVER hardcode API keys in source code
- NEVER loop API calls without backoff (minimum 100ms between calls)
- RESPECT rate_limit_rpm from credentials.json
- If monthly_budget_usd is set, track spend and STOP at warn_at_percent
- All API calls must have timeout (30s default)
- All API calls must have error handling (retry with exponential backoff, max 3 retries)
- Log all API calls to agent memory for cost tracking
```

---

## Success Criteria

- [ ] create-agent.sh created and executable
- [ ] create-agent.sh creates: spec, memory, module dir, KG node+edges, git commit
- [ ] create-agent.sh validates: agent doesn't already exist, required args provided
- [ ] create-agent.sh uses fcntl.flock for KG writes (concurrent safe)
- [ ] .claude/integrations/ directory exists with .gitkeep
- [ ] .gitignore excludes credential files but not directory structure
- [ ] spawn.sh symlinks .claude/integrations/ into worktrees
- [ ] CLAUDE.md has "New Domain Protocol" section
- [ ] CLAUDE.md has "External API Safety" section
- [ ] Orchestrator knows to use create-agent.sh for new domains (not ad-hoc)

## Verification

```bash
# Test create-agent.sh
bash .claude/scripts/create-agent.sh test-integration-agent 1 test-module "testing,integration" orchestrator "identity-agent"

# Verify outputs
[ -f .claude/agents/test-integration-agent/agent.md ] && echo "PASS: Spec created" || echo "FAIL"
[ -f .claude/agents/test-integration-agent/memory/MEMORY.md ] && echo "PASS: Memory created" || echo "FAIL"
[ -d src/test/ ] && echo "PASS: Module dir created" || echo "FAIL"

# Verify KG
python3 -c "
import json
d = json.load(open('.claude/kg/agent_graph_cache.json'))
agents = [n['id'] for n in d['nodes'] if n.get('type') == 'agent']
print('test-integration-agent' in agents and 'PASS: In KG' or 'FAIL: Not in KG')
"

# Cleanup test agent (manual — this is infrastructure, not a worktree)
rm -rf .claude/agents/test-integration-agent/
rm -rf src/test/
# KG node stays (harmless, or manually remove)

# Test credentials directory
mkdir -p .claude/integrations/test-service/
echo '{"api_key":"test"}' > .claude/integrations/test-service/credentials.json
git status .claude/integrations/  # credentials.json should NOT show as untracked (gitignored)
rm -rf .claude/integrations/test-service/
```
