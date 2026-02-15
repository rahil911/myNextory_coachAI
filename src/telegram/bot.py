"""
Baap Telegram Bot — Two-way bridge between Telegram and the Baap agent swarm.

Polls Telegram for incoming messages and routes them to the appropriate handler.
Replies via OpenClaw Gateway CLI (primary) or direct Bot API (fallback).

Usage:
    python -m src.telegram.bot                  # run polling loop
    python -m src.telegram.bot --send "hello"   # send a one-off message

Commands:
    /status  — Show agent swarm status
    /beads   — List active beads
    /help    — Show available commands
    (free text) — Echoed back + logged for orchestrator review
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    httpx = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("baap.telegram")

# ── Config ────────────────────────────────────────────────────────────────────

BOT_TOKEN = "8595926634:AAHWQ-ee7JYrR4WOgBfUKZRPEYpvyLab6M0"
CHAT_ID = "8288652266"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENCLAW_BIN = "/home/rahil/.npm-global/bin/openclaw"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POLL_INTERVAL = 2  # seconds between getUpdates calls


# ── Telegram API helpers ──────────────────────────────────────────────────────

async def tg_request(client: "httpx.AsyncClient", method: str, **kwargs) -> dict:
    """Make a Telegram Bot API request."""
    resp = await client.post(f"{TELEGRAM_API}/{method}", json=kwargs)
    data = resp.json()
    if not data.get("ok"):
        logger.warning(f"Telegram API error: {data}")
    return data


async def send_message(client: "httpx.AsyncClient", text: str,
                       chat_id: str = CHAT_ID, parse_mode: str = "HTML") -> dict:
    """Send a message via Telegram Bot API."""
    return await tg_request(client, "sendMessage",
                            chat_id=chat_id, text=text, parse_mode=parse_mode,
                            disable_web_page_preview=True)


# ── Command handlers ──────────────────────────────────────────────────────────

async def handle_status(client: "httpx.AsyncClient", chat_id: str):
    """Show agent swarm status."""
    try:
        status_dir = PROJECT_ROOT / ".claude" / "command-center" / "backend"
        # Try to get status from Command Center API
        resp = await client.get("http://localhost:8002/api/dashboard/overview", timeout=5)
        if resp.status_code == 200:
            d = resp.json()
            text = (
                f"<b>Baap Swarm Status</b>\n\n"
                f"Agents: {d.get('active_agents', 0)} active / {d.get('total_agents', 0)} total\n"
                f"Stale: {d.get('stale_agents', 0)}\n\n"
                f"Beads: {d.get('in_progress_beads', 0)} in progress, "
                f"{d.get('blocked_beads', 0)} blocked, "
                f"{d.get('done_beads', 0)} done\n"
                f"Epics: {d.get('epic_count', 0)} (avg {d.get('avg_epic_progress', 0)}% complete)\n"
                f"ThinkTank: {'active' if d.get('thinktank_active') else 'idle'}"
            )
        else:
            text = "Command Center not responding. Check https://rahil911.duckdns.org:8002"
    except Exception as e:
        text = f"Could not reach Command Center: {e}"

    await send_message(client, text, chat_id)


async def handle_beads(client: "httpx.AsyncClient", chat_id: str):
    """List active beads."""
    try:
        resp = await client.get("http://localhost:8002/api/beads", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            beads = data if isinstance(data, list) else data.get("beads", [])
            active = [b for b in beads if b.get("status") in ("open", "in_progress")]
            if not active:
                text = "No active beads."
            else:
                lines = ["<b>Active Beads</b>\n"]
                for b in active[:10]:
                    status_icon = {"open": "🔵", "in_progress": "🟡"}.get(b.get("status"), "⚪")
                    lines.append(f"{status_icon} <code>{b['id']}</code> {b.get('title', 'Untitled')}")
                if len(active) > 10:
                    lines.append(f"\n... and {len(active) - 10} more")
                text = "\n".join(lines)
        else:
            text = "Could not fetch beads."
    except Exception as e:
        text = f"Error: {e}"

    await send_message(client, text, chat_id)


async def handle_help(client: "httpx.AsyncClient", chat_id: str):
    """Show available commands."""
    text = (
        "<b>Baap Bot Commands</b>\n\n"
        "/status — Agent swarm status\n"
        "/beads — List active beads\n"
        "/help — This message\n\n"
        "Send any text and it will be logged for orchestrator review.\n"
        "Dashboard: https://rahil911.duckdns.org:8002"
    )
    await send_message(client, text, chat_id)


async def handle_text(client: "httpx.AsyncClient", chat_id: str, text: str, from_user: str):
    """Handle free-text messages."""
    logger.info(f"Message from {from_user}: {text}")
    # Log to a file for orchestrator review
    log_path = PROJECT_ROOT / "src" / "telegram" / "inbox.log"
    with open(log_path, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {from_user} | {text}\n")

    reply = f"Got it. Logged for orchestrator review.\n\n<i>{text}</i>"
    await send_message(client, reply, chat_id)


# ── Routing ───────────────────────────────────────────────────────────────────

COMMANDS = {
    "/status": handle_status,
    "/beads": handle_beads,
    "/help": handle_help,
    "/start": handle_help,
}


async def process_message(client: "httpx.AsyncClient", message: dict):
    """Route an incoming Telegram message to the appropriate handler."""
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()
    from_user = message.get("from", {}).get("first_name", "Unknown")

    if not text:
        return

    # Check commands
    cmd = text.split()[0].lower().split("@")[0]  # handle /command@botname
    handler = COMMANDS.get(cmd)
    if handler:
        await handler(client, chat_id)
    else:
        await handle_text(client, chat_id, text, from_user)


# ── Polling loop ──────────────────────────────────────────────────────────────

async def poll_loop():
    """Long-poll Telegram for updates and process them."""
    if not httpx:
        logger.error("httpx not installed. Run: pip install httpx")
        return

    async with httpx.AsyncClient(timeout=60) as client:
        offset = 0
        logger.info("Baap Telegram bot started. Polling for messages...")

        # Delete any stale webhook
        await tg_request(client, "deleteWebhook")

        while True:
            try:
                data = await tg_request(client, "getUpdates",
                                        offset=offset, timeout=30,
                                        allowed_updates=["message"])
                updates = data.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if msg:
                        await process_message(client, msg)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(5)

            await asyncio.sleep(POLL_INTERVAL)


async def send_one(text: str, chat_id: str = CHAT_ID):
    """Send a single message and exit."""
    if not httpx:
        logger.error("httpx not installed")
        return
    async with httpx.AsyncClient(timeout=15) as client:
        result = await send_message(client, text, chat_id)
        logger.info(f"Send result: {result}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--send" in sys.argv:
        idx = sys.argv.index("--send")
        msg = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Test"
        asyncio.run(send_one(msg))
    else:
        asyncio.run(poll_loop())
