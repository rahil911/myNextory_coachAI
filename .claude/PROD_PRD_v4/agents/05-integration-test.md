# Phase 5: Integration Test — End-to-End Verification

**Type**: Sequential (depends on Phase 4)
**Output**: Validation report — all tests pass
**Gate**: Full pipeline works end-to-end

## Purpose

Verify that the complete pipeline works: approval → beads → assignment → spawn → monitor → completion. This is NOT automated unit tests — it's a live verification of the integrated system.

## Prerequisites

- Server is running on port 8002
- All Phase 1-4 files are deployed
- Beads CLI (`bd`) is available
- KG cache is loaded
- spawn.sh and cleanup.sh are executable

## Test Procedure

### Test 1: Service Imports

Verify all new services are importable without errors:

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.bead_generator import BeadGenerator
from services.agent_assigner import AgentAssigner
from services.beads_bridge import BeadsBridge
from services.dispatch_engine import DispatchEngine
from services.progress_bridge import ProgressBridge
from services.failure_recovery import FailureRecovery
print('All services importable: OK')
"
```

Expected: "All services importable: OK"

### Test 2: BeadGenerator Can Decompose

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
import asyncio
from services.bead_generator import BeadGenerator

async def test():
    bg = BeadGenerator()
    # Test with a mock session-like object
    class MockSpecKit:
        project_brief = type('obj', (object,), {'content': 'Build a task manager'})()
        requirements = type('obj', (object,), {'content': '- CRUD for tasks\n- User auth\n- Dashboard'})()
        constraints = None
        pre_mortem = None
        execution_plan = type('obj', (object,), {'content': 'Phase 1: DB schema. Phase 2: API. Phase 3: UI.'})()

    class MockSession:
        id = 'tt_test_integration'
        topic = 'Build a task manager'
        phase = 'building'
        status = 'approved'
        spec_kit = MockSpecKit()
        messages = []

    plan = await bg.spec_to_beads(MockSession())
    print(f'Epic ID: {plan.epic_id}')
    print(f'Tasks: {len(plan.tasks)}')
    for t in plan.tasks:
        print(f'  Phase {t.phase}: {t.title} → {t.suggested_agent}')
    print(f'Dependencies: {plan.dependency_map}')

asyncio.run(test())
"
```

Expected: Epic created, multiple tasks with phase ordering, agents assigned.

**IMPORTANT**: This creates REAL beads. After the test, clean them up:
```bash
bd list --status=open | grep "test" | awk '{print $1}' | xargs -I{} bd close {} --reason="integration test"
```

### Test 3: AgentAssigner Scores Correctly

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.agent_assigner import AgentAssigner
from services.bead_generator import TaskBead

a = AgentAssigner()
agents = a.get_available_agents()
print(f'Available agents: {agents}')

# Test scoring
task = TaskBead(
    title='Add user authentication with JWT',
    description='Implement login, signup, and token refresh endpoints',
    phase=1, priority=1,
    requirements=['users table', 'JWT library', 'password hashing'],
    acceptance_criteria=['POST /auth/login works', 'Token refresh works'],
)

for agent in agents:
    score = a.score_agent_for_task(agent, task)
    if score > 0:
        print(f'  {agent}: {score:.2f}')

best = a.find_best_agent(task)
print(f'Best agent for auth task: {best}')
"
```

Expected: identity-agent scores highest for auth-related task. If KG is loaded, shows file ownership scores too.

### Test 4: BeadsBridge Links

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.beads_bridge import BeadsBridge

b = BeadsBridge()
b.link_session('tt_test_001', 'beads-test-001')
assert b.get_epic_for_session('tt_test_001') == 'beads-test-001'
assert b.get_session_for_epic('beads-test-001') == 'tt_test_001'
print('BeadsBridge links: OK')
"
```

### Test 5: DispatchEngine Instantiates

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.dispatch_engine import DispatchEngine

d = DispatchEngine()
print('DispatchEngine: OK')
print('Methods:', [m for m in dir(d) if not m.startswith('_') and callable(getattr(d, m))])

# Verify it can find spawn.sh
from pathlib import Path
spawn = Path.home() / 'Projects' / 'baap' / '.claude' / 'scripts' / 'spawn.sh'
print(f'spawn.sh exists: {spawn.exists()}')
"
```

### Test 6: FailureRecovery Classifications

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.failure_recovery import FailureRecovery

f = FailureRecovery()
# Test error classification
tests = [
    ('timeout after 120 minutes', 0, 'retry'),
    ('permission denied: /etc/shadow', 0, 'escalate'),
    ('connection reset by peer', 0, 'retry'),
    ('unknown error', 3, 'escalate'),  # max retries
    ('rate limit exceeded', 1, 'retry'),
    ('import error: module not found', 0, 'escalate'),
]
for error, retries, expected in tests:
    result = f._determine_action(error, retries)
    status = '✓' if result['action'] == expected else '✗'
    print(f'  {status} \"{error}\" (retry={retries}) → {result[\"action\"]} (expected {expected})')
"
```

### Test 7: Approve Triggers Dispatch (API Test)

```bash
# Only run this if the server is running with the new code deployed

# Create a test session
curl -s -X POST http://localhost:8002/api/thinktank/start \
  -H "Content-Type: application/json" \
  -d '{"topic": "Integration test: build a simple counter"}' | python3 -m json.tool

# Note the session ID from the response, then approve it:
# curl -s -X POST http://localhost:8002/api/thinktank/approve | python3 -m json.tool

# Check dispatch status:
# curl -s http://localhost:8002/api/thinktank/dispatch/{session_id} | python3 -m json.tool
```

### Test 8: WebSocket Events Flow

Open the Command Center UI in a browser. Navigate to Dashboard view. Then approve a session via API. Verify:
- Toast appears: "Build started..."
- Agent status updates appear
- Timeline shows dispatch events

## Cleanup After Tests

```bash
# Close any test beads
bd list --status=open | grep -i "test\|integration\|counter" | awk '{print $1}' | xargs -I{} bd close {} --reason="test cleanup"

# Remove test sessions
rm -f ~/Projects/baap/.claude/command-center/sessions/tt_test*.json

# Clean up test worktrees
ls ~/agents/ 2>/dev/null && echo "WARNING: Agent worktrees exist. Review before deleting."
```

## Success Criteria

All 8 tests pass:
- [ ] Test 1: All services importable
- [ ] Test 2: BeadGenerator decomposes specs into phased tasks
- [ ] Test 3: AgentAssigner routes to correct agents
- [ ] Test 4: BeadsBridge links sessions ↔ epics
- [ ] Test 5: DispatchEngine instantiates with spawn.sh
- [ ] Test 6: FailureRecovery classifies errors correctly
- [ ] Test 7: Approve API triggers dispatch (creates beads, starts agents)
- [ ] Test 8: WebSocket events visible in UI

## What to Report

After running all tests, report:
1. Which tests passed/failed
2. Any import errors or missing dependencies
3. Whether beads were created successfully
4. Whether agent assignment worked (KG-based or fallback)
5. Whether spawn.sh was called (check tmux sessions)
6. Any errors in the server logs
