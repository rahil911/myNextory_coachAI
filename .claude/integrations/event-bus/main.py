"""
Baap Event Bus API — Lightweight WebSocket server for bead lifecycle events.

Usage:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8003
"""

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from src.api.event_bus import event_bus

app = FastAPI(
    title="Baap Event Bus",
    version="1.0.0",
    description="WebSocket event bus for real-time bead lifecycle coordination",
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "clients": len(event_bus.clients),
        "seq": event_bus._seq,
    }


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    """Subscribe to all bead lifecycle events.

    Events:
        bead.ready — A bead is ready for pickup
        bead.claimed — An agent claimed a bead
        bead.completed — A bead was completed
        bead.blocked — A bead is blocked
        agent.spawned — An agent was spawned
        agent.completed — An agent finished
        agent.failed — An agent failed
    """
    await event_bus.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        event_bus.disconnect(websocket)


@app.post("/api/emit")
async def emit_event(event: dict):
    """Emit an event to all connected clients.

    Body: {"event": "bead.ready", "payload": {"bead_id": "...", ...}}
    """
    event_name = event.get("event", "unknown")
    payload = event.get("payload", {})
    await event_bus.broadcast(event_name, payload)
    return {"ok": True, "event": event_name, "clients": len(event_bus.clients)}
