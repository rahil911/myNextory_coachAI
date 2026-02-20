set dotenv-load
set shell := ["bash", "-c"]

project_root := justfile_directory()

default:
    @just --list

# ─── Agent Operations ─────────────────────────────────

# Spawn an agent via spawn.sh
spawn agent="platform-agent" prompt="" level="1":
    bash .claude/scripts/spawn.sh reactive "{{prompt}}" ~/Projects/baap {{agent}} {{level}}

# Merge agent work to main
merge name:
    bash .claude/scripts/cleanup.sh {{name}} merge

# Merge without browser QA gate
merge-skip-qa name:
    SKIP_BROWSER_QA=true bash .claude/scripts/cleanup.sh {{name}} merge

# Discard agent work
discard name:
    bash .claude/scripts/cleanup.sh {{name}} discard

# Monitor all agents
monitor:
    bash .claude/scripts/monitor.sh --watch

# Monitor specific agent
monitor-agent name:
    bash .claude/scripts/monitor.sh --agent {{name}}

# ─── Dashboard ────────────────────────────────────────

# Start/restart the Command Center dashboard
dashboard:
    @pkill -f 'uvi[c]orn main:app.*8002' 2>/dev/null && sleep 1 || true
    @cd {{project_root}}/.claude/command-center/backend && nohup {{project_root}}/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8002 --log-level info > /tmp/dashboard.log 2>&1 &
    @sleep 2
    @echo "Dashboard running at http://localhost:8002"

# Show dashboard logs
dashboard-logs:
    @tail -50 /tmp/dashboard.log 2>/dev/null || echo "No dashboard log found"

# Stop dashboard
dashboard-stop:
    @pkill -f 'uvi[c]orn main:app.*8002' 2>/dev/null && echo "Dashboard stopped" || echo "Dashboard not running"

# ─── Browser QA ───────────────────────────────────────

# Run browser QA gate manually
qa:
    bash .claude/scripts/browser-qa-gate.sh manual .

# ─── Beads ────────────────────────────────────────────

# Show open and in-progress beads
status:
    @bd list --status=open 2>/dev/null; bd list --status=in_progress 2>/dev/null

# Show ready work
ready:
    @bd ready 2>/dev/null
