"""
Baap Telegram Bot — Two-way bridge between Telegram and the Baap agent swarm.

Polls Telegram for incoming messages and routes them to the appropriate handler.
Free-text messages are answered by Claude (via `claude -p`) using your subscription.
Voice messages are transcribed via Sarvam AI, answered by Claude.
Supports audio replies in Hindi, English, and Kannada (mixed dialects OK).

Usage:
    python .claude/integrations/telegram/bot.py                  # run polling loop
    python .claude/integrations/telegram/bot.py --send "hello"   # send a one-off message

Commands:
    /status  — Show agent swarm status
    /beads   — List active beads
    /help    — Show available commands
    (free text) — Answered by Claude via your subscription
    (voice)     — Transcribed via Sarvam AI, answered by Claude
    "reply in audio" — Claude replies with voice message
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import tempfile
import time
import uuid
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
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
POLL_INTERVAL = 2  # seconds between getUpdates calls
CLAUDE_BIN = "claude"  # uses your subscription via OAuth
CLAUDE_MODEL = "sonnet"  # capable enough for DB queries + contextual answers

# Sarvam AI (voice: STT + TTS)
SARVAM_API_KEY = "sk_lwifrj09_hX85mAePWRYrEcXyOpl4mbHP"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_VOICE = "priya"  # female voice
SARVAM_PACE = 1.5  # 1.5x speed
SARVAM_DEFAULT_LANG = "en-IN"

SYSTEM_PROMPT = """You are Baap Bot, the Telegram interface to the Baap agent swarm platform.
You are talking to Rahil, the platform owner and operator.
Keep replies concise (under 200 words) — this is a mobile chat interface.
You have access to the MyNextory coaching/learning platform database (38 tables).
The Command Center dashboard is at https://rahil911.duckdns.org:8002
If asked about agent status, suggest using /status command.
If asked about beads/tasks, suggest using /beads command."""

# Patterns that trigger audio reply from text input
AUDIO_TRIGGER_RE = re.compile(
    r'\b(?:(?:reply|explain|respond|answer|tell)\s+in\s+(?:\w+\s+)?audio|'
    r'in\s+(?:english\s+|hindi\s+|kannada\s+)?audio|'
    r'audio\s+(?:reply|explain|message|mein)|'
    r'voice\s+(?:reply|message|mein)|'
    r'bol\s*ke\s*bata|bolke\s*bata|awaaz\s+mein|'
    r'send\s+(?:voice|audio)|speak\s+to\s+me|bolo)\b',
    re.IGNORECASE
)


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


async def download_tg_file(client: "httpx.AsyncClient", file_id: str) -> bytes | None:
    """Download a file from Telegram by file_id."""
    data = await tg_request(client, "getFile", file_id=file_id)
    if not data.get("ok"):
        return None
    file_path = data["result"]["file_path"]
    resp = await client.get(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=30
    )
    if resp.status_code == 200:
        return resp.content
    return None


async def send_voice_msg(client: "httpx.AsyncClient", chat_id: str,
                         audio_bytes: bytes, caption: str | None = None) -> dict:
    """Send a voice message via Telegram (multipart upload)."""
    url = f"{TELEGRAM_API}/sendVoice"
    files = {"voice": ("reply.mp3", audio_bytes, "audio/mpeg")}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:1024]
    resp = await client.post(url, files=files, data=data, timeout=30)
    result = resp.json()
    if not result.get("ok"):
        logger.warning(f"sendVoice error: {result}")
    return result


# ── Sarvam AI helpers ─────────────────────────────────────────────────────────

CHUNK_DURATION = 25  # seconds per chunk (Sarvam limit is 30s, use 25 for safety)


async def _get_audio_duration(path: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return 0.0


async def _split_audio(path: str, chunk_sec: int = CHUNK_DURATION) -> list[str]:
    """Split audio file into chunks of chunk_sec seconds. Returns list of chunk paths."""
    duration = await _get_audio_duration(path)
    if duration <= chunk_sec:
        return [path]

    chunks = []
    offset = 0.0
    idx = 0
    base, ext = os.path.splitext(path)
    while offset < duration:
        chunk_path = f"{base}_chunk{idx}.ogg"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", path,
            "-ss", str(offset), "-t", str(chunk_sec),
            "-c:a", "libopus", "-b:a", "48k", chunk_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            chunks.append(chunk_path)
        offset += chunk_sec
        idx += 1

    return chunks


async def _stt_single(client: "httpx.AsyncClient", audio_bytes: bytes,
                      filename: str, headers: dict) -> tuple[str | None, str | None]:
    """Transcribe a single audio chunk (must be <= 30s)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "ogg"
    ct_map = {
        "ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg",
        "wav": "audio/wav", "m4a": "audio/mp4", "opus": "audio/opus",
        "webm": "audio/webm", "aac": "audio/aac", "amr": "audio/amr",
    }
    content_type = ct_map.get(ext, "audio/ogg")
    files = {"file": (filename, audio_bytes, content_type)}
    form_data = {"model": "saaras:v3", "language_code": "unknown"}

    resp = await client.post(
        SARVAM_STT_URL, headers=headers,
        files=files, data=form_data, timeout=30
    )
    if resp.status_code == 200:
        result = resp.json()
        return result.get("transcript", ""), result.get("language_code", "en-IN")
    logger.error(f"Sarvam STT {resp.status_code}: {resp.text[:300]}")
    return None, None


async def sarvam_stt(client: "httpx.AsyncClient", audio_bytes: bytes,
                     filename: str = "voice.ogg") -> tuple[str | None, str | None]:
    """Transcribe audio via Sarvam AI. Splits long audio into chunks automatically."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write audio to temp file
        src_path = os.path.join(tmpdir, filename)
        with open(src_path, "wb") as f:
            f.write(audio_bytes)

        duration = await _get_audio_duration(src_path)
        logger.info(f"Audio duration: {duration:.1f}s")

        if duration <= 30:
            # Short audio — transcribe directly
            transcript, lang = await _stt_single(client, audio_bytes, filename, headers)
            if transcript:
                logger.info(f"STT ok: lang={lang}, len={len(transcript)}")
            return transcript, lang

        # Long audio — split into chunks and transcribe each
        logger.info(f"Audio > 30s ({duration:.0f}s), splitting into {CHUNK_DURATION}s chunks")
        chunks = await _split_audio(src_path)
        logger.info(f"Split into {len(chunks)} chunks")

        transcripts = []
        detected_lang = "en-IN"
        lang_votes = {}

        for i, chunk_path in enumerate(chunks):
            with open(chunk_path, "rb") as cf:
                chunk_bytes = cf.read()
            chunk_name = os.path.basename(chunk_path)
            t, l = await _stt_single(client, chunk_bytes, chunk_name, headers)
            if t:
                transcripts.append(t)
                if l:
                    lang_votes[l] = lang_votes.get(l, 0) + 1
                logger.info(f"Chunk {i+1}/{len(chunks)}: lang={l}, len={len(t)}")

        if not transcripts:
            return None, None

        # Pick most common detected language
        if lang_votes:
            detected_lang = max(lang_votes, key=lang_votes.get)

        full_transcript = " ".join(transcripts)
        logger.info(f"STT ok (chunked): lang={detected_lang}, total_len={len(full_transcript)}")
        return full_transcript, detected_lang


def strip_markdown_for_speech(text: str) -> str:
    """Strip markdown formatting so TTS reads clean text, not syntax."""
    # Links: [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Bold/italic: ***text***, **text**, *text* → text
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    # Headings: ## Heading → Heading
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Bullet/list markers at line start: - item, * item, + item → item
    text = re.sub(r'^[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    # Numbered lists: 1. item → item
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    # Inline code: `code` → code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Code blocks: ```...``` → (contents)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Horizontal rules
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    # HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse multiple newlines/spaces
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


async def sarvam_tts(client: "httpx.AsyncClient", text: str,
                     lang: str = "en-IN") -> bytes | None:
    """Convert text to speech via Sarvam AI. Returns MP3 bytes."""
    # Clean markdown so TTS doesn't read ** as "times times" etc.
    text = strip_markdown_for_speech(text)

    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json",
    }
    if len(text) > 2500:
        text = text[:2497] + "..."

    payload = {
        "text": text,
        "target_language_code": lang,
        "model": "bulbul:v3",
        "speaker": SARVAM_VOICE,
        "pace": SARVAM_PACE,
        "speech_sample_rate": 24000,
        "output_audio_codec": "mp3",
    }
    try:
        resp = await client.post(
            SARVAM_TTS_URL, headers=headers, json=payload, timeout=30
        )
        if resp.status_code == 200:
            result = resp.json()
            audios = result.get("audios", [])
            if audios:
                logger.info(f"TTS ok: lang={lang}, audio chunks={len(audios)}")
                return base64.b64decode(audios[0])
        logger.error(f"Sarvam TTS {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        logger.error(f"Sarvam TTS error: {e}")
    return None


# ── Language helpers ──────────────────────────────────────────────────────────

def detect_script_language(text: str) -> str:
    """Detect language from Unicode script in text."""
    devanagari = len(re.findall(r'[\u0900-\u097F]', text))
    kannada = len(re.findall(r'[\u0C80-\u0CFF]', text))
    if devanagari > 3:
        return "hi-IN"
    if kannada > 3:
        return "kn-IN"
    return "en-IN"


def wants_audio_reply(text: str) -> bool:
    """Check if the user wants an audio reply."""
    return bool(AUDIO_TRIGGER_RE.search(text))


def strip_audio_trigger(text: str) -> str:
    """Remove audio trigger phrases from text, clean up residual punctuation."""
    cleaned = AUDIO_TRIGGER_RE.sub("", text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,.')
    return cleaned


# ── Command handlers ──────────────────────────────────────────────────────────

async def handle_status(client: "httpx.AsyncClient", chat_id: str):
    """Show agent swarm status."""
    try:
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
                    status_icon = {"open": "\U0001f535", "in_progress": "\U0001f7e1"}.get(b.get("status"), "\u26aa")
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
        "/status \u2014 Agent swarm status\n"
        "/beads \u2014 List active beads\n"
        "/help \u2014 This message\n\n"
        "<b>Voice Features</b>\n"
        "\U0001f3a4 Send a voice message \u2014 transcribed + answered\n"
        "\U0001f4ac Say \"reply in audio\" \u2014 get voice reply\n"
        "\U0001f5e3 Supports Hindi, English, Kannada (mixed OK)\n\n"
        "Dashboard: https://rahil911.duckdns.org:8002"
    )
    await send_message(client, text, chat_id)


# ── Claude (with session memory) ──────────────────────────────────────────────

# Namespace UUID for generating deterministic session IDs from chat IDs
_SESSION_NS = uuid.UUID("b4a7c0d1-2e3f-4a5b-8c6d-7e8f9a0b1c2d")
# Session memory: always try --resume first (survives bot restarts),
# fall back to --session-id only if the session does not exist yet.


def _session_id_for_chat(chat_id: str) -> str:
    """Generate a deterministic UUID session ID from a Telegram chat ID."""
    return str(uuid.uuid5(_SESSION_NS, f"tg-{chat_id}"))


async def _run_claude(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    """Run claude CLI and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def ask_claude(prompt: str, chat_id: str = CHAT_ID) -> str:
    """Send a prompt to Claude via `claude -p` with persistent session memory.

    Strategy: try --resume first (works across bot restarts since sessions
    are persisted on disk by Claude Code). If the session doesn't exist yet,
    fall back to --session-id to create it.
    """
    session_id = _session_id_for_chat(chat_id)

    try:
        # Try resuming existing session (most common path)
        rc, out, err = await _run_claude([
            CLAUDE_BIN, "-p", prompt,
            "--model", CLAUDE_MODEL,
            "--resume", session_id,
        ])
        if rc == 0 and out:
            return out

        # Resume failed — session might not exist yet. Create it.
        if "not found" in err.lower() or "no session" in err.lower() or rc != 0:
            logger.info(f"Session {session_id[:8]}... not found, creating new session")
            rc2, out2, err2 = await _run_claude([
                CLAUDE_BIN, "-p", prompt,
                "--model", CLAUDE_MODEL,
                "--session-id", session_id,
                "--system-prompt", SYSTEM_PROMPT,
            ])
            if rc2 == 0 and out2:
                return out2
            logger.warning(f"claude -p fresh session failed (rc={rc2}): {err2[:200]}")
            return f"(Claude is unavailable right now: {err2[:100]})"

        logger.warning(f"claude -p resume failed (rc={rc}): {err[:200]}")
        return f"(Claude is unavailable right now: {err[:100]})"

    except asyncio.TimeoutError:
        return "(Claude timed out after 90s — try a shorter question)"
    except FileNotFoundError:
        return "(claude CLI not found — is Claude Code installed?)"
    except Exception as e:
        logger.error(f"ask_claude error: {e}")
        return f"(Error calling Claude: {e})"


# ── Voice handler ─────────────────────────────────────────────────────────────

async def handle_voice(client: "httpx.AsyncClient", chat_id: str,
                       voice_obj: dict, from_user: str):
    """Handle incoming voice/audio — transcribe via Sarvam, reply via Claude."""
    file_id = voice_obj.get("file_id")
    if not file_id:
        return

    duration = voice_obj.get("duration", "?")
    logger.info(f"Voice from {from_user} ({duration}s)")
    await tg_request(client, "sendChatAction", chat_id=chat_id, action="typing")

    # Download audio from Telegram
    audio_bytes = await download_tg_file(client, file_id)
    if not audio_bytes:
        await send_message(client, "(Could not download voice message)", chat_id, parse_mode="")
        return

    # Transcribe via Sarvam
    filename = voice_obj.get("file_name", "voice.ogg")
    transcript, lang = await sarvam_stt(client, audio_bytes, filename)
    if not transcript:
        await send_message(
            client, "(Could not transcribe \u2014 try again or send text)", chat_id, parse_mode=""
        )
        return

    logger.info(f"Transcribed ({lang}): {transcript}")

    # Log to inbox
    log_path = PROJECT_ROOT / ".claude" / "integrations" / "telegram" / "inbox.log"
    with open(log_path, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {from_user} | [VOICE:{lang}] {transcript}\n")

    # Always reply in English regardless of input language
    reply = await ask_claude(transcript, chat_id)

    # Send text reply with transcript
    text_msg = f"\U0001f3a4 \"{transcript}\"\n\n{reply}"
    await send_message(client, text_msg, chat_id, parse_mode="")

    # Also send voice reply in English for voice inputs
    await tg_request(client, "sendChatAction", chat_id=chat_id, action="record_voice")
    audio_reply = await sarvam_tts(client, reply, "en-IN")
    if audio_reply:
        await send_voice_msg(client, chat_id, audio_reply)


# ── Text handler ──────────────────────────────────────────────────────────────

async def handle_text(client: "httpx.AsyncClient", chat_id: str, text: str, from_user: str):
    """Handle free-text messages — route to Claude, with optional audio reply."""
    logger.info(f"Message from {from_user}: {text}")

    # Log to inbox for audit trail
    log_path = PROJECT_ROOT / ".claude" / "integrations" / "telegram" / "inbox.log"
    with open(log_path, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {from_user} | {text}\n")

    # Check if audio reply requested
    audio_requested = wants_audio_reply(text)
    prompt_text = text
    if audio_requested:
        prompt_text = strip_audio_trigger(text)
        if not prompt_text:
            prompt_text = "Hello, how can I help?"

    # Send typing indicator
    await tg_request(client, "sendChatAction", chat_id=chat_id, action="typing")

    # Ask Claude
    reply = await ask_claude(prompt_text, chat_id)

    # Always send text reply
    await send_message(client, reply, chat_id, parse_mode="")

    # If audio requested, also send voice (always English)
    if audio_requested:
        await tg_request(client, "sendChatAction", chat_id=chat_id, action="record_voice")
        audio_reply = await sarvam_tts(client, reply, "en-IN")
        if audio_reply:
            await send_voice_msg(client, chat_id, audio_reply)
        else:
            await send_message(client, "(Could not generate audio)", chat_id, parse_mode="")


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
    from_user = message.get("from", {}).get("first_name", "Unknown")

    # Voice messages (recorded in-app)
    voice = message.get("voice")
    if voice:
        await handle_voice(client, chat_id, voice, from_user)
        return

    # Audio files (sent as audio attachment)
    audio = message.get("audio")
    if audio:
        await handle_voice(client, chat_id, audio, from_user)
        return

    # Audio sent as document (some clients do this)
    doc = message.get("document")
    if doc and (doc.get("mime_type", "").startswith("audio/")
                or doc.get("file_name", "").endswith(
                    (".ogg", ".mp3", ".wav", ".m4a", ".opus", ".aac", ".webm"))):
        await handle_voice(client, chat_id, doc, from_user)
        return

    # Text messages
    text = message.get("text", "").strip()
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
