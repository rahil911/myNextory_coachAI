"""
Notification Router — Routes agent events to Slack/Telegram via gateway.

Falls back to logging when no gateway is configured or reachable.
Channels are defined in config/notifications.yaml.

Usage:
    router = NotificationRouter.from_config("config/notifications.yaml")
    await router.route("Agent Failed", "identity-agent crashed", priority=3)
"""

import asyncio
import logging
import yaml
from pathlib import Path
from typing import List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger("baap.notifications")


class NotificationRoute:
    """A single routing rule mapping events to channels."""

    def __init__(self, name: str, channels: List[str],
                 priority: Optional[List[int]] = None,
                 event_types: Optional[List[str]] = None):
        self.name = name
        self.channels = channels
        self.priority = set(priority) if priority else None
        self.event_types = set(event_types) if event_types else None

    def matches(self, priority: Optional[int] = None,
                event_type: Optional[str] = None) -> bool:
        """Check if this route matches the given priority/event_type."""
        if self.priority and priority is not None:
            if priority in self.priority:
                return True
        if self.event_types and event_type is not None:
            if event_type in self.event_types:
                return True
        # If no filters set, match everything
        if not self.priority and not self.event_types:
            return True
        return False


class NotificationRouter:
    """Routes notifications to configured channels via OpenClaw Gateway.

    Falls back to log-only mode when:
    - httpx is not installed
    - Gateway URL is not configured
    - Gateway is unreachable
    """

    def __init__(self, gateway_url: Optional[str] = None,
                 routes: Optional[List[NotificationRoute]] = None,
                 enabled: bool = True):
        self.gateway_url = gateway_url
        self.routes = routes or []
        self.enabled = enabled
        self._client: Optional[object] = None
        self._fallback_mode = False

        if not httpx:
            logger.warning("httpx not installed — notification router in log-only mode")
            self._fallback_mode = True
        elif not gateway_url:
            logger.info("No gateway URL configured — notification router in log-only mode")
            self._fallback_mode = True

    @classmethod
    def from_config(cls, config_path: str = "config/notifications.yaml") -> "NotificationRouter":
        """Load router configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config not found at {config_path} — using defaults (log-only)")
            return cls(enabled=False)

        with open(path) as f:
            cfg = yaml.safe_load(f) or {}

        notif_cfg = cfg.get("notifications", {})
        enabled = notif_cfg.get("enabled", True)
        gateway_url = notif_cfg.get("openclaw_gateway")

        routes = []
        for route_cfg in notif_cfg.get("routes", []):
            routes.append(NotificationRoute(
                name=route_cfg.get("name", "unnamed"),
                channels=route_cfg.get("channels", []),
                priority=route_cfg.get("priority"),
                event_types=route_cfg.get("event_types"),
            ))

        return cls(gateway_url=gateway_url, routes=routes, enabled=enabled)

    async def _get_client(self) -> Optional[object]:
        """Lazy-init httpx client."""
        if self._fallback_mode or not httpx:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def route(self, title: str, body: str,
                    priority: Optional[int] = None,
                    event_type: Optional[str] = None) -> dict:
        """Route a notification to matching channels.

        Returns a summary of what was sent and where.
        """
        if not self.enabled:
            logger.debug(f"Notifications disabled — skipping: {title}")
            return {"sent": 0, "logged": True, "skipped_reason": "disabled"}

        # Find matching routes
        matching_channels: List[str] = []
        for route in self.routes:
            if route.matches(priority=priority, event_type=event_type):
                matching_channels.extend(route.channels)

        # Deduplicate
        matching_channels = list(dict.fromkeys(matching_channels))

        if not matching_channels:
            logger.info(f"[NOTIFY] No matching routes for: {title} (priority={priority}, type={event_type})")
            return {"sent": 0, "logged": True, "skipped_reason": "no_matching_routes"}

        # Log always (this is the fallback AND the audit trail)
        logger.info(f"[NOTIFY] {title} -> {matching_channels}")
        logger.info(f"[NOTIFY]   body: {body[:200]}")

        if self._fallback_mode:
            logger.info(f"[NOTIFY] (log-only mode — {len(matching_channels)} channel(s) would receive this)")
            return {"sent": 0, "logged": True, "channels": matching_channels, "mode": "log-only"}

        # Send via gateway
        client = await self._get_client()
        if not client:
            return {"sent": 0, "logged": True, "mode": "log-only"}

        sent = 0
        errors = []
        for channel_target in matching_channels:
            parts = channel_target.split(":", 1)
            if len(parts) != 2:
                errors.append(f"Invalid channel format: {channel_target}")
                continue

            channel, target = parts
            try:
                resp = await client.post(  # type: ignore[union-attr]
                    f"{self.gateway_url}/api/send",
                    json={
                        "channel": channel,
                        "to": target,
                        "text": f"**{title}**\n\n{body}",
                    },
                )
                if resp.status_code < 300:  # type: ignore[union-attr]
                    sent += 1
                else:
                    errors.append(f"{channel_target}: HTTP {resp.status_code}")  # type: ignore[union-attr]
            except Exception as e:
                errors.append(f"{channel_target}: {e}")
                logger.warning(f"[NOTIFY] Failed to send to {channel_target}: {e}")

        return {
            "sent": sent,
            "total_channels": len(matching_channels),
            "errors": errors if errors else None,
            "mode": "gateway",
        }

    async def notify_agent_event(self, agent: str, event: str, detail: str = "") -> dict:
        """Convenience method for agent lifecycle events."""
        title = f"Agent {event}: {agent}"
        body = detail or f"Agent '{agent}' transitioned to '{event}'"
        return await self.route(
            title=title,
            body=body,
            event_type=f"agent_{event}",
        )

    async def notify_bead_event(self, bead_id: str, event: str, detail: str = "") -> dict:
        """Convenience method for bead lifecycle events."""
        title = f"Bead {event}: {bead_id}"
        body = detail or f"Bead '{bead_id}' transitioned to '{event}'"
        return await self.route(
            title=title,
            body=body,
            event_type=f"bead_{event}",
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client and httpx:
            await self._client.aclose()  # type: ignore[union-attr]
            self._client = None
