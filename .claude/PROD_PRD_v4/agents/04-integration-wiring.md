# Phase 4: Integration Wiring — Connect Approval to Dispatch

**Type**: Sequential (depends on Phase 3a, 3b)
**Output**: Modified `thinktank_service.py`, new route endpoints, new WSEventType members
**Gate**: approve() triggers full dispatch pipeline

## Purpose

Wire everything together. Modify the existing `thinktank_service.approve()` to trigger the DispatchEngine, add API endpoints for dispatch status/control, and register new WebSocket event types.

## What to Modify

### 1. Add New WSEventType Members

Read `backend/models.py` and find the `WSEventType` enum. Add these members:

```python
# In the WSEventType enum, add:
DISPATCH_STARTED = "DISPATCH_STARTED"
DISPATCH_PROGRESS = "DISPATCH_PROGRESS"
DISPATCH_COMPLETE = "DISPATCH_COMPLETE"
DISPATCH_ERROR = "DISPATCH_ERROR"
AGENT_PROGRESS = "AGENT_PROGRESS"
AGENT_RETRYING = "AGENT_RETRYING"
BEAD_STATUS_CHANGE = "BEAD_STATUS_CHANGE"
FAILURE_HANDLED = "FAILURE_HANDLED"
```

**IMPORTANT**: Read the actual models.py first. The WSEventType enum may use different naming conventions (e.g., string values vs auto-numbered). Match the existing pattern exactly.

### 2. Modify thinktank_service.py

The current `approve()` method at the end does:
```python
session.phase = ThinkTankPhase.BUILDING
session.status = "approved"
# ... events ...
return True
```

Add dispatch trigger AFTER the existing code:

```python
async def approve(self, session_id: str, modifications: str = "") -> bool:
    """Approve the spec-kit and transition to building phase."""
    session = self._sessions.get(session_id)
    if not session:
        return False

    now = datetime.now(timezone.utc).isoformat()

    if modifications:
        await self.send_message(session_id, f"Approved with modifications: {modifications}")
    else:
        await self.send_message(session_id, "Approved. Start building.")

    session.phase = ThinkTankPhase.BUILDING
    session.status = "approved"
    session.updated_at = now
    self._persist_now(session_id)

    if self._event_bus:
        await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
            "session_id": session_id,
            "phase": "building",
        })
        await self._event_bus.publish(WSEventType.TOAST, {
            "message": "Spec-kit approved! Creating build plan...",
            "type": "success",
        })

    # ═══ NEW: Trigger dispatch engine ═══
    try:
        result = await self._dispatch_engine.dispatch_approved_session(session)

        # Store epic ID in session for later reference
        if result.get("epic_id"):
            session.epic_id = result["epic_id"]  # May need to add this field to model
            self._persist_now(session_id)

        if self._event_bus:
            await self._event_bus.publish(WSEventType.TOAST, {
                "message": f"Build started: {result.get('task_count', 0)} tasks dispatched",
                "type": "success",
            })

    except Exception as e:
        logger.error(f"Dispatch failed: {e}")
        if self._event_bus:
            await self._event_bus.publish(WSEventType.TOAST, {
                "message": f"Dispatch failed: {e}. You can retry from the dashboard.",
                "type": "error",
            })
        # Don't fail the approve — the spec is still approved
        # User can retry dispatch manually

    return True
```

Also add DispatchEngine initialization in `__init__`:

```python
def __init__(self, event_bus=None):
    # ... existing code ...
    self._claude_available = True

    # ═══ NEW: Dispatch engine ═══
    from services.dispatch_engine import DispatchEngine
    self._dispatch_engine = DispatchEngine(event_bus=event_bus)
```

### 3. Add Dispatch Routes

Create new endpoints in `backend/routes/thinktank.py` (or a new `backend/routes/dispatch.py`):

```python
# Add to existing thinktank routes:

@router.get("/api/thinktank/dispatch/{session_id}")
async def get_dispatch_status(session_id: str):
    """Get dispatch status for a session."""
    service = get_thinktank_service()
    status = service._dispatch_engine.get_dispatch_status(session_id)
    if not status:
        return {"status": "not_dispatched"}
    return status


@router.post("/api/thinktank/dispatch/{session_id}/cancel")
async def cancel_dispatch(session_id: str):
    """Cancel an active dispatch."""
    service = get_thinktank_service()
    success = await service._dispatch_engine.cancel_dispatch(session_id)
    return {"cancelled": success}


@router.post("/api/thinktank/dispatch/{session_id}/retry")
async def retry_dispatch(session_id: str):
    """Retry dispatch for an approved session."""
    service = get_thinktank_service()
    session = service.get_session(session_id)
    if not session or session.status != "approved":
        return {"error": "Session not found or not approved"}

    result = await service._dispatch_engine.dispatch_approved_session(session)
    return result
```

### 4. Handle New Events in Frontend WebSocket

In `frontend/js/api.js`, add handlers for new event types in `handleEventMessage()`:

```javascript
// Add these cases to handleEventMessage switch:

case 'DISPATCH_STARTED':
  showToast(`Build started: ${payload.topic || 'project'}`, 'info');
  break;

case 'DISPATCH_PROGRESS':
  showToast(`Build progress: ${payload.status}`, 'info');
  break;

case 'DISPATCH_COMPLETE': {
  const statusMsg = payload.status === 'completed'
    ? `Build complete! ${payload.completed}/${payload.total} tasks done.`
    : `Build finished with issues. ${payload.completed}/${payload.total} completed, ${payload.failed} failed.`;
  showToast(statusMsg, payload.status === 'completed' ? 'success' : 'warning');
  break;
}

case 'DISPATCH_ERROR':
  showToast(`Build error: ${payload.error}`, 'error');
  break;

case 'AGENT_PROGRESS':
  // Could update agent cards in dashboard view
  break;

case 'AGENT_RETRYING':
  showToast(`Retrying ${payload.agent} (attempt ${payload.attempt})`, 'warning');
  break;
```

### 5. Also Handle in Think Tank WebSocket

In `handleThinktankMessage()`, the Think Tank WS handler should also process dispatch events when they arrive tagged with a session_id:

```javascript
case 'DISPATCH_STARTED':
case 'DISPATCH_PROGRESS':
case 'DISPATCH_COMPLETE':
case 'DISPATCH_ERROR':
  // These arrive on the thinktank WS channel too
  // Update the session state to reflect build progress
  if (data.payload) {
    setState({
      thinktank: {
        ...getState().thinktank,
        dispatchStatus: data.payload,
      }
    });
  }
  break;
```

## Key Decision: Where to Route Dispatch Events

The dispatch engine publishes events via `event_bus`. Currently the event_bus has two WebSocket routes:
- `/ws` — general events (agents, beads, timeline, approvals)
- `/ws/thinktank` — Think Tank specific events

Dispatch events should go to BOTH:
- `/ws` — so Dashboard, Agents, Kanban views can update
- `/ws/thinktank?session=xxx` — so the Think Tank view shows build progress

**Read `backend/services/event_bus.py`** to understand how it routes events to different WebSocket endpoints. You may need to:
- Add a new event category
- Or ensure `publish()` broadcasts to all connected WebSocket clients
- Or have DispatchEngine publish to both explicitly

## What NOT to Change

- Do NOT modify `bead_generator.py`, `agent_assigner.py`, `beads_bridge.py`, `dispatch_engine.py`, `progress_bridge.py`, `failure_recovery.py` — those were created in earlier phases
- Do NOT modify `event_bus.py` structure — only add event type handling
- Do NOT modify frontend views (Dashboard, Kanban, etc.) — they'll naturally pick up new events through existing handlers

## Success Criteria

```bash
# 1. Verify approve triggers dispatch
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.thinktank_service import ThinkTankService
ts = ThinkTankService()
print('ThinkTankService has dispatch_engine:', hasattr(ts, '_dispatch_engine'))
"

# 2. Verify new routes exist
grep -n "dispatch" routes/thinktank.py

# 3. Verify WSEventType has new members
python3 -c "
from models import WSEventType
print([e.name for e in WSEventType if 'DISPATCH' in e.name or 'PROGRESS' in e.name])
"
```
