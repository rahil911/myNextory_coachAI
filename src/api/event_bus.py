import asyncio
import json
from typing import Set
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

class EventBus:
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self._seq = 0

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, event: str, payload: dict):
        self._seq += 1
        frame = json.dumps({"type": "event", "event": event, "payload": payload, "seq": self._seq})
        dead = []
        for client in self.clients:
            try:
                await client.send_text(frame)
            except Exception:
                dead.append(client)
        for d in dead:
            self.clients.discard(d)

event_bus = EventBus()
