"""
routes/voice.py — Full-duplex realtime voice for Companion and Curator AI.

WebSocket at /api/voice/{role}/{user_id}
- role: "companion" or "curator"
- Receives PCM 16kHz audio from browser as binary frames
- Streams to Sarvam STT (saaras:v3) for transcription
- Feeds transcript to existing chat pipelines
- Streams TTS audio (bulbul:v2) back to browser
- Handles barge-in: new speech cancels in-flight TTS
"""

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Add RAG directory to path
_RAG_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "rag")
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")

# Fallback: load from project .env if not in environment
if not SARVAM_API_KEY:
    _env_path = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            if line.startswith("SARVAM_API_KEY="):
                SARVAM_API_KEY = line.split("=", 1)[1].strip()
                break


# ── Chat pipeline wrappers ──────────────────────────────────────────────────

async def _companion_chat(user_id: int, message: str, session_id: int) -> str:
    """Call companion _process_chat in a thread (it's synchronous)."""
    from routes.companion import _process_chat, _get_or_create_session

    if not session_id:
        session = _get_or_create_session(user_id)
        session_id = session["session_id"]

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _process_chat, user_id, message, session_id, None
    )
    return result.get("response", "I couldn't process that. Try again?")


async def _curator_chat(user_id: int, message: str, session_id: int) -> str:
    """Call CuratorEngine.chat in a thread (it's synchronous)."""
    from curator_prompts import CuratorEngine

    def _do_chat():
        engine = CuratorEngine()
        result = engine.chat(
            nx_user_id=user_id,
            message=message,
            session_id=session_id,
        )
        return result.get("response", "I couldn't process that. Try again?")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_chat)


# ── Voice session ───────────────────────────────────────────────────────────

class VoiceSession:
    """Manages a single voice WebSocket connection with STT/TTS streaming."""

    def __init__(self, ws: WebSocket, role: str, user_id: int):
        self.ws = ws
        self.role = role
        self.user_id = user_id
        self.session_id = 0
        self.stt_client = None
        self.tts_client = None
        self.tts_playing = False
        self.tts_cancelled = False
        self._tts_task = None
        self._stt_recv_task = None
        self._closed = False

    async def start(self):
        """Initialize Sarvam connections and start processing."""
        from sarvamai import AsyncSarvamAI

        # Get companion/curator session ID
        if self.role == "companion":
            from routes.companion import _get_or_create_session
            session = _get_or_create_session(self.user_id)
            self.session_id = session["session_id"]

        # Send ready signal
        await self._send_json({
            "type": "ready",
            "session_id": self.session_id,
            "user_id": self.user_id,
            "role": self.role,
        })

        sarvam = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)

        # Open STT streaming connection
        async with sarvam.speech_to_text_streaming.connect(
            language_code="en-IN",
            model="saaras:v3",
            mode="transcribe",
            sample_rate="16000",
            input_audio_codec="pcm_s16le",
            vad_signals="true",
        ) as stt:
            self.stt_client = stt

            # Start STT receive loop in background
            self._stt_recv_task = asyncio.create_task(self._stt_receive_loop())

            try:
                # Main loop: receive audio from browser
                while not self._closed:
                    try:
                        data = await self.ws.receive()
                    except WebSocketDisconnect:
                        break

                    if data.get("type") == "websocket.disconnect":
                        break

                    if "bytes" in data and data["bytes"]:
                        # Binary audio frame from browser
                        audio_bytes = data["bytes"]
                        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

                        # Forward to Sarvam STT
                        try:
                            await stt.transcribe(
                                audio=audio_b64,
                                encoding="audio/pcm",
                                sample_rate=16000,
                            )
                        except Exception as e:
                            logger.warning("stt_send_error", error=str(e))

                    elif "text" in data and data["text"]:
                        # JSON control messages from browser
                        try:
                            msg = json.loads(data["text"])
                            await self._handle_control(msg)
                        except json.JSONDecodeError:
                            pass
            finally:
                self._closed = True
                if self._stt_recv_task:
                    self._stt_recv_task.cancel()
                if self._tts_task:
                    self._tts_task.cancel()

    async def _stt_receive_loop(self):
        """Receive transcription results from Sarvam STT."""
        while not self._closed:
            try:
                response = await self.stt_client.recv()

                if response.type == "events":
                    # VAD signal: speech_start or speech_end
                    signal = getattr(response.data, "signal_type", None)
                    if signal == "START_SPEECH":
                        await self._handle_speech_start()
                    elif signal == "END_SPEECH":
                        await self._handle_speech_end()

                elif response.type == "data":
                    # Transcription result
                    transcript = response.data.transcript
                    if transcript and transcript.strip():
                        await self._handle_transcript(transcript.strip())

                elif response.type == "error":
                    logger.warning("stt_error", data=str(response.data))

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._closed:
                    logger.warning("stt_recv_error", error=str(e))
                    await asyncio.sleep(0.1)

    async def _handle_speech_start(self):
        """User started speaking — barge-in if TTS is playing."""
        await self._send_json({"type": "vad", "event": "speech_start"})

        if self.tts_playing:
            # Barge-in: cancel current TTS playback
            self.tts_cancelled = True
            if self._tts_task and not self._tts_task.done():
                self._tts_task.cancel()
            await self._send_json({"type": "barge_in"})
            self.tts_playing = False

    async def _handle_speech_end(self):
        """User stopped speaking."""
        await self._send_json({"type": "vad", "event": "speech_end"})

    async def _handle_transcript(self, transcript: str):
        """Process a transcription result through the chat pipeline."""
        # Send transcript to browser for display
        await self._send_json({
            "type": "transcript",
            "text": transcript,
        })

        # Send thinking indicator
        await self._send_json({"type": "thinking"})

        # Call the appropriate chat pipeline
        try:
            if self.role == "companion":
                response_text = await _companion_chat(
                    self.user_id, transcript, self.session_id
                )
            else:
                response_text = await _curator_chat(
                    self.user_id, transcript, self.session_id
                )

            # Send response text for display
            await self._send_json({
                "type": "response_text",
                "text": response_text,
            })

            # Stream response as TTS audio
            self._tts_task = asyncio.create_task(
                self._stream_tts(response_text)
            )

        except Exception as e:
            logger.error("chat_pipeline_error", role=self.role, error=str(e))
            await self._send_json({
                "type": "error",
                "message": f"Chat error: {str(e)[:200]}",
            })

    async def _stream_tts(self, text: str):
        """Stream text through Sarvam TTS and send audio chunks to browser."""
        if not text or self._closed:
            return

        self.tts_playing = True
        self.tts_cancelled = False

        try:
            from sarvamai import AsyncSarvamAI
            sarvam = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)

            async with sarvam.text_to_speech_streaming.connect(
                model="bulbul:v2",
            ) as tts:
                self.tts_client = tts

                # Configure TTS for PCM output at 16kHz for browser playback
                await tts.configure(
                    target_language_code="en-IN",
                    speaker="meera",
                    speech_sample_rate=24000,
                    output_audio_codec="mp3",
                    output_audio_bitrate="128k",
                    pace=1.0,
                    enable_preprocessing=True,
                )

                # Send text to TTS
                # Split into chunks for better streaming
                chunks = self._split_text(text)
                for chunk in chunks:
                    if self.tts_cancelled:
                        break
                    await tts.convert(chunk)

                # Flush to get remaining audio
                if not self.tts_cancelled:
                    await tts.flush()

                # Receive and forward audio chunks
                while not self.tts_cancelled and not self._closed:
                    try:
                        response = await asyncio.wait_for(tts.recv(), timeout=10.0)

                        if hasattr(response, "type"):
                            if response.type == "audio":
                                # Audio chunk — send as binary to browser
                                audio_b64 = response.data.audio
                                audio_bytes = base64.b64decode(audio_b64)
                                await self.ws.send_bytes(audio_bytes)

                            elif response.type == "event":
                                # Completion event
                                if hasattr(response.data, "event_type") and response.data.event_type == "final":
                                    break

                    except asyncio.TimeoutError:
                        break
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.warning("tts_recv_error", error=str(e))
                        break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("tts_stream_error", error=str(e))
        finally:
            self.tts_playing = False
            self.tts_client = None
            if not self._closed:
                await self._send_json({"type": "tts_done"})

    def _split_text(self, text: str, max_len: int = 400) -> list[str]:
        """Split text into sentence-level chunks for TTS streaming."""
        if len(text) <= max_len:
            return [text]

        chunks = []
        current = ""
        # Split on sentence boundaries
        for part in text.replace(". ", ".|").replace("! ", "!|").replace("? ", "?|").split("|"):
            part = part.strip()
            if not part:
                continue
            if len(current) + len(part) + 1 > max_len and current:
                chunks.append(current.strip())
                current = part
            else:
                current = f"{current} {part}".strip() if current else part

        if current:
            chunks.append(current.strip())

        return chunks if chunks else [text]

    async def _handle_control(self, msg: dict):
        """Handle control messages from browser."""
        action = msg.get("action")

        if action == "stop":
            # Stop TTS playback
            self.tts_cancelled = True
            if self._tts_task and not self._tts_task.done():
                self._tts_task.cancel()
            self.tts_playing = False

        elif action == "flush":
            # Force flush STT buffer
            if self.stt_client:
                try:
                    await self.stt_client.flush()
                except Exception:
                    pass

    async def _send_json(self, data: dict):
        """Send JSON message to browser, swallowing errors if closed."""
        if self._closed:
            return
        try:
            await self.ws.send_json(data)
        except Exception:
            self._closed = True


# ── WebSocket endpoint ──────────────────────────────────────────────────────

@router.websocket("/ws/{role}/{user_id}")
async def voice_ws(ws: WebSocket, role: str, user_id: int):
    """Full-duplex voice WebSocket.

    Browser sends: binary PCM 16kHz audio frames, or JSON control messages.
    Server sends: JSON status messages + binary MP3 audio frames.
    """
    if role not in ("companion", "curator"):
        await ws.close(code=4000, reason="Invalid role. Use 'companion' or 'curator'.")
        return

    if not SARVAM_API_KEY:
        await ws.close(code=4001, reason="SARVAM_API_KEY not configured.")
        return

    await ws.accept()

    session = VoiceSession(ws, role, user_id)
    try:
        await session.start()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("voice_ws_error", role=role, user_id=user_id, error=str(e))
        try:
            await ws.send_json({"type": "error", "message": str(e)[:200]})
        except Exception:
            pass
    finally:
        session._closed = True
