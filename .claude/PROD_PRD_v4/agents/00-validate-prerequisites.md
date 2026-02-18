# Phase 0: Validate Prerequisites

**Type**: Sequential (blocks all other phases)
**Output**: Validation report — all checks pass
**Gate**: Every check below returns OK

## What to Validate

Run each check. If any fails, fix it before proceeding.

### 1. Beads CLI Available
```bash
which bd && bd --version
```
Expected: bd binary found, version printed.

### 2. Beads Initialized
```bash
ls -la ~/Projects/baap/.beads/beads.db
bd stats
```
Expected: beads.db exists, stats show counts.

### 3. KG Cache Exists and Valid
```bash
python3 -c "
import json
d = json.load(open('$HOME/Projects/baap/.claude/kg/agent_graph_cache.json'))
meta = d.get('metadata', d.get('graph', {}))
print(f'Nodes: {len(d.get(\"nodes\", []))}')
print(f'Edges: {len(d.get(\"edges\", []))}')
"
```
Expected: Nodes > 0, Edges > 0.

### 4. MCP Config Exists
```bash
cat ~/Projects/baap/.mcp.json
```
Expected: JSON with `ownership-graph` and `db-tools` entries.

### 5. Spawn Infrastructure Exists
```bash
ls -la ~/Projects/baap/.claude/scripts/spawn.sh
ls -la ~/Projects/baap/.claude/scripts/cleanup.sh
ls -la ~/Projects/baap/.claude/scripts/heartbeat.sh
ls -la ~/Projects/baap/.claude/scripts/retry-agent.sh
ls -la ~/Projects/baap/.claude/scripts/kill-agent.sh
```
Expected: All files exist and are executable.

### 6. Agent Specs Exist
```bash
ls ~/Projects/baap/.claude/agents/*/agent.md | wc -l
```
Expected: >= 8 agent specs.

### 7. Command Center Backend Running
```bash
curl -s http://localhost:8002/api/dashboard | python3 -m json.tool | head -5
```
Expected: JSON response (or at least confirm the backend structure exists in code).

### 8. Event Bus Importable
```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "from services.event_bus import EventBus; print('OK')"
```
Expected: "OK" — EventBus class is importable.

### 9. Existing Models Available
```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from models import ThinkTankSession, ThinkTankPhase, SpecKit, WSEventType
print('ThinkTankSession:', ThinkTankSession.__fields__.keys() if hasattr(ThinkTankSession, '__fields__') else dir(ThinkTankSession))
print('WSEventType members:', [e.name for e in WSEventType])
"
```
Expected: Models importable, fields visible. Note down the WSEventType members — you'll need to add new ones.

### 10. Think Tank Service Approve Method
```bash
cd ~/Projects/baap/.claude/command-center/backend
grep -n "async def approve" services/thinktank_service.py
```
Expected: Shows the approve method location. Read it fully — this is what Phase 4 will modify.

## Success Criteria

All 10 checks pass. Document any findings (unexpected WSEventType names, model field names, etc.) in notes — downstream phases will need them.
