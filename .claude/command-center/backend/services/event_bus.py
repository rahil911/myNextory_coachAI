"""
event_bus.py — In-process async pub/sub for WebSocket broadcast.

Services call `event_bus.publish(event)` to push events.
The WebSocket handler calls `event_bus.subscribe()` to get an async generator of events.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from models import WSEvent, WSEventType


class EventBus:
    """Simple in-process pub/sub using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def publish(self, event_type: WSEventType, payload: dict[str, Any]) -> None:
        """Publish an event to all subscribers."""
        event = WSEvent(
            type=event_type,
            payload=payload,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        event_json = event.model_dump_json()
        async with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event_json)
                except asyncio.QueueFull:
                    dead.append(q)
            # Remove dead subscribers
            for q in dead:
                self._subscribers.remove(q)

    async def subscribe(self) -> asyncio.Queue:
        """Create a new subscription queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscription queue."""
        async with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Singleton instance
event_bus = EventBus()
