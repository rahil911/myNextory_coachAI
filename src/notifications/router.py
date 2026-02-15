"""
Notification Router — Routes agent events to Telegram and Slack.

Sends directly to Telegram Bot API and Slack webhook (no gateway dependency).
Channels are defined in config/notifications.yaml.

Usage:
    router = NotificationRouter.from_config("config/notifications.yaml")
    await router.route("Agent Failed", "identity-agent crashed", priority=3)
"""

import logging
import yaml
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger("baap.notifications")

TELEGRAM_API = "https://api.telegram.org"
DASHBOARD_URL = "https://rahil911.duckdns.org:8002"


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
        if not self.priority and not self.event_types:
            return True
        return False


class NotificationRouter:
    """Routes notifications directly to Telegram Bot API and Slack webhooks.

    Falls back to log-only mode when httpx is not installed or no
    credentials are configured.
    """

    def __init__(self, routes: Optional[List[NotificationRoute]] = None,
                 enabled: bool = True,
                 telegram_token: Optional[str] = None,
                 telegram_chat_id: Optional[str] = None,
                 slack_webhook_url: Optional[str] = None,
                 dashboard_url: str = DASHBOARD_URL):
        self.routes = routes or []
        self.enabled = enabled
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.slack_webhook_url = slack_webhook_url
        self.dashboard_url = dashboard_url
        self._client: Optional[object] = None
        self._fallback_mode = False

        if not httpx:
            logger.warning("httpx not installed — notification router in log-only mode")
            self._fallback_mode = True
        elif not telegram_token and not slack_webhook_url:
            logger.info("No Telegram/Slack credentials — notification router in log-only mode")
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

        # Credentials
        creds = notif_cfg.get("credentials", {})
        telegram_token = creds.get("telegram_bot_token")
        telegram_chat_id = str(creds.get("telegram_chat_id", ""))
        slack_webhook_url = creds.get("slack_webhook_url")
        dashboard_url = notif_cfg.get("dashboard_url", DASHBOARD_URL)

        routes = []
        for route_cfg in notif_cfg.get("routes", []):
            routes.append(NotificationRoute(
                name=route_cfg.get("name", "unnamed"),
                channels=route_cfg.get("channels", []),
                priority=route_cfg.get("priority"),
                event_types=route_cfg.get("event_types"),
            ))

        return cls(
            routes=routes,
            enabled=enabled,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            slack_webhook_url=slack_webhook_url,
            dashboard_url=dashboard_url,
        )

    async def _get_client(self):
        """Lazy-init httpx client."""
        if self._fallback_mode or not httpx:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _send_telegram(self, text: str, chat_id: Optional[str] = None) -> bool:
        """Send a message via Telegram Bot API."""
        if not self.telegram_token:
            return False
        client = await self._get_client()
        if not client:
            return False
        target_chat = chat_id or self.telegram_chat_id
        if not target_chat:
            return False
        try:
            resp = await client.post(
                f"{TELEGRAM_API}/bot{self.telegram_token}/sendMessage",
                json={
                    "chat_id": target_chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code == 200:
                return True
            logger.warning(f"Telegram API returned {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")
            return False

    async def _send_slack(self, text: str) -> bool:
        """Send a message via Slack webhook."""
        if not self.slack_webhook_url:
            return False
        client = await self._get_client()
        if not client:
            return False
        try:
            resp = await client.post(
                self.slack_webhook_url,
                json={"text": text},
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Slack send failed: {e}")
            return False

    def _format_telegram(self, title: str, body: str) -> str:
        """Format message for Telegram (HTML)."""
        lines = [f"<b>{title}</b>"]
        if body:
            lines.append(body)
        lines.append(f'\n<a href="{self.dashboard_url}">Open Command Center</a>')
        return "\n".join(lines)

    def _format_slack(self, title: str, body: str) -> str:
        """Format message for Slack (mrkdwn)."""
        lines = [f"*{title}*"]
        if body:
            lines.append(body)
        lines.append(f"<{self.dashboard_url}|Open Command Center>")
        return "\n".join(lines)

    async def route(self, title: str, body: str,
                    priority: Optional[int] = None,
                    event_type: Optional[str] = None) -> dict:
        """Route a notification to matching channels."""
        if not self.enabled:
            return {"sent": 0, "logged": True, "skipped_reason": "disabled"}

        # Find matching routes
        matching_channels: List[str] = []
        for r in self.routes:
            if r.matches(priority=priority, event_type=event_type):
                matching_channels.extend(r.channels)

        matching_channels = list(dict.fromkeys(matching_channels))

        if not matching_channels:
            logger.info(f"[NOTIFY] No matching routes for: {title} (priority={priority}, type={event_type})")
            return {"sent": 0, "logged": True, "skipped_reason": "no_matching_routes"}

        # Log always
        logger.info(f"[NOTIFY] {title} -> {matching_channels}")

        if self._fallback_mode:
            logger.info(f"[NOTIFY] (log-only) {title}: {body[:200]}")
            return {"sent": 0, "logged": True, "channels": matching_channels, "mode": "log-only"}

        # Send to each channel
        sent = 0
        errors = []
        for channel_target in matching_channels:
            parts = channel_target.split(":", 1)
            if len(parts) != 2:
                errors.append(f"Invalid channel format: {channel_target}")
                continue

            channel, target = parts

            if channel == "telegram":
                text = self._format_telegram(title, body)
                # Use target as chat_id if it's numeric, otherwise use default
                chat_id = target if target.lstrip("-").isdigit() else self.telegram_chat_id
                ok = await self._send_telegram(text, chat_id)
                if ok:
                    sent += 1
                else:
                    errors.append(f"telegram:{target}: send failed")

            elif channel == "slack":
                text = self._format_slack(title, body)
                ok = await self._send_slack(text)
                if ok:
                    sent += 1
                else:
                    errors.append(f"slack:{target}: send failed (no webhook configured)")

            else:
                logger.info(f"[NOTIFY] Unknown channel type '{channel}' — logged only")
                errors.append(f"{channel}:{target}: unknown channel type")

        return {
            "sent": sent,
            "total_channels": len(matching_channels),
            "errors": errors if errors else None,
            "mode": "direct",
        }

    async def notify_agent_event(self, agent: str, event: str, detail: str = "") -> dict:
        """Convenience method for agent lifecycle events."""
        title = f"Agent {event}: {agent}"
        body = detail or f"Agent '{agent}' transitioned to '{event}'"
        return await self.route(title=title, body=body, event_type=f"agent_{event}")

    async def notify_bead_event(self, bead_id: str, event: str, detail: str = "") -> dict:
        """Convenience method for bead lifecycle events."""
        title = f"Bead {event}: {bead_id}"
        body = detail or f"Bead '{bead_id}' transitioned to '{event}'"
        return await self.route(title=title, body=body, event_type=f"bead_{event}")

    async def send_test(self) -> dict:
        """Send a test notification to all configured channels."""
        return await self.route(
            title="Baap Test Notification",
            body="This is a test from the Baap Command Center notification system.",
            priority=3,
            event_type="test",
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client and httpx:
            await self._client.aclose()  # type: ignore[union-attr]
            self._client = None
