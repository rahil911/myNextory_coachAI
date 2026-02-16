"""
routes/websocket.py — WebSocket hub for real-time push.

Clients connect to /ws and receive all events from the event bus.
Think Tank messages are also routed through this connection.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


def _get_event_bus():
    from main import get_event_bus
    return get_event_bus()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Main WebSocket endpoint for real-time updates."""
    await ws.accept()
    bus = _get_event_bus()
    queue = await bus.subscribe()

    try:
        # Send welcome message
        await ws.send_json({
            "type": "CONNECTED",
            "payload": {"message": "Connected to Command Center"},
        })

        while True:
            try:
                # Wait for events with a timeout so we can detect disconnects
                event_json = await asyncio.wait_for(queue.get(), timeout=30)
                await ws.send_text(event_json)
            except asyncio.TimeoutError:
                # Send heartbeat ping
                try:
                    await ws.send_json({"type": "PING", "payload": {}})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await bus.unsubscribe(queue)


@router.websocket("/ws/thinktank")
async def thinktank_websocket(ws: WebSocket):
    """Dedicated WebSocket for Think Tank real-time chat + spec-kit streaming.

    This is a filtered view of the event bus that only sends Think Tank events.
    It also accepts messages from the client for bidirectional communication.
    """
    await ws.accept()

    # Subscribe FIRST so we don't miss events during catch-up
    bus = _get_event_bus()
    queue = await bus.subscribe()

    # Send existing messages as catch-up (fixes race condition where welcome
    # message fires before WebSocket connects)
    seen_timestamps = set()
    from main import get_thinktank_service
    svc = get_thinktank_service()
    session_id = ws.query_params.get("session")
    session = svc.get_session(session_id) if session_id else svc.get_active_session()
    if session:
        for msg in session.messages:
            seen_timestamps.add(msg.timestamp)
            await ws.send_json({
                "type": "THINKTANK_MESSAGE",
                "payload": {"session_id": session.id, "message": msg.model_dump()},
                "ts": msg.timestamp,
            })

    thinktank_events = {
        "THINKTANK_MESSAGE",
        "THINKTANK_SPECKIT_DELTA",
        "THINKTANK_PHASE_CHANGE",
        "APPROVAL_NEEDED",
        # Dispatch events (so Think Tank view shows build progress)
        "DISPATCH_STARTED",
        "DISPATCH_PROGRESS",
        "DISPATCH_COMPLETE",
        "DISPATCH_ERROR",
        "TOAST",
    }

    async def reader():
        """Read messages from the WebSocket client."""
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                # Route to think tank service
                if msg.get("type") == "message":
                    from main import get_thinktank_service
                    svc = get_thinktank_service()
                    session = svc.get_active_session()
                    if session:
                        await svc.send_message(session.id, msg.get("text", ""))
                elif msg.get("type") == "action":
                    from main import get_thinktank_service
                    svc = get_thinktank_service()
                    session = svc.get_active_session()
                    if session:
                        await svc.handle_action(session.id, msg.get("action", ""), msg.get("context", ""))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def writer():
        """Push Think Tank events to the WebSocket client."""
        try:
            while True:
                event_json = await queue.get()
                try:
                    event = json.loads(event_json)
                    if event.get("type") not in thinktank_events:
                        continue
                    # Deduplicate: skip messages already sent during catch-up
                    ts = event.get("ts")
                    if ts and event.get("type") == "THINKTANK_MESSAGE" and ts in seen_timestamps:
                        continue
                    if ts:
                        seen_timestamps.add(ts)
                    await ws.send_text(event_json)
                except (json.JSONDecodeError, Exception):
                    pass  # Skip bad event, don't crash the writer loop
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    # Run reader and writer concurrently
    reader_task = asyncio.create_task(reader())
    writer_task = asyncio.create_task(writer())

    try:
        await asyncio.gather(reader_task, writer_task)
    except Exception:
        pass
    finally:
        reader_task.cancel()
        writer_task.cancel()
        await bus.unsubscribe(queue)
