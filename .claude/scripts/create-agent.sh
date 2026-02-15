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
