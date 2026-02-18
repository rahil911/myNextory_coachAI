"""
Notification Router — Routes agent events via OpenClaw Gateway.

Primary path: OpenClaw Gateway CLI (handles Telegram, Slack, etc.)
Fallback: Direct Telegram Bot API (one-way only)

Channels are defined in .claude/integrations/notifications/notifications.yaml.

Usage:
    router = NotificationRouter.from_config(".claude/integrations/notifications/notifications.yaml")
    await router.route("Agent Failed", "identity-agent crashed", priority=3)
"""

import asyncio
import json
import logging
import shutil
import yaml
from pathlib import Path
from typing import List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger("baap.notifications")

TELEGRAM_API = "https://api.telegram.org"
DASHBOARD_URL = "https://rahil911.duckdns.org:8002"
OPENCLAW_BIN = "/home/rahil/.npm-global/bin/openclaw"


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
    """Routes notifications via OpenClaw Gateway (primary) or direct API (fallback).

    Primary: `openclaw message send` CLI — supports two-way chat, session
    management, and all channels the gateway handles.

    Fallback: Direct Telegram Bot API — one-way notifications only, used
    when the gateway is down or openclaw binary is not found.
    """

    def __init__(self, routes: Optional[List[NotificationRoute]] = None,
                 enabled: bool = True,
                 telegram_token: Optional[str] = None,
                 telegram_chat_id: Optional[str] = None,
                 slack_webhook_url: Optional[str] = None,
                 dashboard_url: str = DASHBOARD_URL,
                 openclaw_bin: str = OPENCLAW_BIN):
        self.routes = routes or []
        self.enabled = enabled
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.slack_webhook_url = slack_webhook_url
        self.dashboard_url = dashboard_url
        self.openclaw_bin = openclaw_bin
        self._client: Optional[object] = None
        self._gateway_available: Optional[bool] = None  # lazy-checked

    @classmethod
    def from_config(cls, config_path: str = ".claude/integrations/notifications/notifications.yaml") -> "NotificationRouter":
        """Load router configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config not found at {config_path} — using defaults (log-only)")
            return cls(enabled=False)

        with open(path) as f:
            cfg = yaml.safe_load(f) or {}

        notif_cfg = cfg.get("notifications", {})
        enabled = notif_cfg.get("enabled", True)

        creds = notif_cfg.get("credentials", {})
        telegram_token = creds.get("telegram_bot_token")
        telegram_chat_id = str(creds.get("telegram_chat_id", ""))
        slack_webhook_url = creds.get("slack_webhook_url")
        dashboard_url = notif_cfg.get("dashboard_url", DASHBOARD_URL)
        openclaw_bin = notif_cfg.get("openclaw_bin", OPENCLAW_BIN)

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
            openclaw_bin=openclaw_bin,
        )

    def _check_gateway(self) -> bool:
        """Check if OpenClaw Gateway CLI is available (cached)."""
        if self._gateway_available is not None:
            return self._gateway_available
        self._gateway_available = Path(self.openclaw_bin).exists()
        if self._gateway_available:
            logger.info(f"OpenClaw Gateway CLI found at {self.openclaw_bin}")
        else:
            logger.warning(f"OpenClaw CLI not found at {self.openclaw_bin} — using direct API fallback")
        return self._gateway_available

    async def _send_via_gateway(self, channel: str, target: str, text: str) -> bool:
        """Send a message via OpenClaw Gateway CLI."""
        if not self._check_gateway():
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                self.openclaw_bin, "message", "send",
                "--channel", channel,
                "--target", target,
                "--message", text,
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                result = json.loads(stdout.decode())
                logger.info(f"[NOTIFY] Gateway sent to {channel}:{target} (msgId={result.get('payload', {}).get('messageId')})")
                return True
            else:
                logger.warning(f"[NOTIFY] Gateway send failed: {stderr.decode()[:200]}")
                return False
        except asyncio.TimeoutError:
            logger.warning("[NOTIFY] Gateway send timed out (15s)")
            return False
        except Exception as e:
            logger.warning(f"[NOTIFY] Gateway send error: {e}")
            return False

    async def _get_client(self):
        """Lazy-init httpx client for direct API fallback."""
        if not httpx:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _send_telegram_direct(self, text: str, chat_id: Optional[str] = None) -> bool:
        """Fallback: Send directly to Telegram Bot API."""
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
                logger.info(f"[NOTIFY] Direct Telegram send OK to {target_chat}")
                return True
            logger.warning(f"[NOTIFY] Direct Telegram API returned {resp.status_code}")
            return False
        except Exception as e:
            logger.warning(f"[NOTIFY] Direct Telegram send failed: {e}")
            return False

    def _format_message(self, title: str, body: str, html: bool = False) -> str:
        """Format notification message."""
        if html:
            lines = [f"<b>{title}</b>"]
            if body:
                lines.append(body)
            lines.append(f'\n<a href="{self.dashboard_url}">Open Command Center</a>')
            return "\n".join(lines)
        else:
            lines = [f"**{title}**"]
            if body:
                lines.append(body)
            lines.append(f"\n{self.dashboard_url}")
            return "\n".join(lines)

    async def _send_to_channel(self, channel: str, target: str, title: str, body: str) -> bool:
        """Send to a single channel:target, trying gateway first then fallback."""
        text = self._format_message(title, body, html=False)

        # Primary: OpenClaw Gateway
        ok = await self._send_via_gateway(channel, target, text)
        if ok:
            return True

        # Fallback: Direct API (Telegram only)
        if channel == "telegram":
            html_text = self._format_message(title, body, html=True)
            chat_id = target if target.lstrip("-").isdigit() else self.telegram_chat_id
            ok = await self._send_telegram_direct(html_text, chat_id)
            if ok:
                logger.info(f"[NOTIFY] Used direct Telegram fallback for {target}")
                return True

        return False

    async def route(self, title: str, body: str,
                    priority: Optional[int] = None,
                    event_type: Optional[str] = None) -> dict:
        """Route a notification to matching channels."""
        if not self.enabled:
            return {"sent": 0, "logged": True, "skipped_reason": "disabled"}

        matching_channels: List[str] = []
        for r in self.routes:
            if r.matches(priority=priority, event_type=event_type):
                matching_channels.extend(r.channels)

        matching_channels = list(dict.fromkeys(matching_channels))

        if not matching_channels:
            logger.info(f"[NOTIFY] No matching routes for: {title} (priority={priority}, type={event_type})")
            return {"sent": 0, "logged": True, "skipped_reason": "no_matching_routes"}

        logger.info(f"[NOTIFY] {title} -> {matching_channels}")

        sent = 0
        errors = []
        for channel_target in matching_channels:
            parts = channel_target.split(":", 1)
            if len(parts) != 2:
                errors.append(f"Invalid channel format: {channel_target}")
                continue

            channel, target = parts
            ok = await self._send_to_channel(channel, target, title, body)
            if ok:
                sent += 1
            else:
                errors.append(f"{channel}:{target}: all transports failed")

        return {
            "sent": sent,
            "total_channels": len(matching_channels),
            "errors": errors if errors else None,
            "mode": "gateway" if self._check_gateway() else "direct-fallback",
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
            body="Notification system online. Gateway + direct fallback configured.",
            priority=3,
            event_type="test",
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client and httpx:
            await self._client.aclose()  # type: ignore[union-attr]
            self._client = None
