// ==========================================================================
// VOICE-CHAT.JS — Reusable Full-Duplex Voice Chat Component
// Handles mic capture, WebSocket streaming, audio playback, and visual states.
// ==========================================================================

// Build both ws:// and wss:// base URLs for fallback logic.
// When the page is served over HTTPS but uvicorn has no TLS, wss:// will fail.
// We try wss:// first (if HTTPS), then fall back to ws:// after a timeout.
const _host = window.location.host;
const _isSecure = window.location.protocol === 'https:';
const WS_BASE_PRIMARY   = `${_isSecure ? 'wss:' : 'ws:'}//${_host}`;
const WS_BASE_FALLBACK  = _isSecure ? `ws://${_host}` : null;

// ── Audio worklet processor (inline) ──────────────────────────────────────

const WORKLET_CODE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._bufferSize = 2048; // ~128ms at 16kHz
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const samples = input[0];
    // Convert float32 to int16
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      this._buffer.push(s < 0 ? s * 0x8000 : s * 0x7FFF);
    }
    if (this._buffer.length >= this._bufferSize) {
      const int16 = new Int16Array(this._buffer.splice(0, this._bufferSize));
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
`;

// ── VoiceChat class ─────────────────────────────────────────────────────────

export class VoiceChat {
  /**
   * @param {Object} opts
   * @param {string} opts.role - "companion" or "curator"
   * @param {number} opts.userId - User ID
   * @param {HTMLElement} opts.container - Container element to mount the mic button into
   * @param {Function} [opts.onTranscript] - Callback when user speech is transcribed
   * @param {Function} [opts.onResponse] - Callback when AI text response arrives
   * @param {Function} [opts.onStateChange] - Callback for state changes (idle/listening/thinking/speaking)
   */
  constructor(opts) {
    this.role = opts.role;
    this.userId = opts.userId;
    this.container = opts.container;
    this.onTranscript = opts.onTranscript || (() => {});
    this.onResponse = opts.onResponse || (() => {});
    this.onStateChange = opts.onStateChange || (() => {});

    this._state = 'idle'; // idle | listening | thinking | speaking | error
    this._ws = null;
    this._audioCtx = null;
    this._mediaStream = null;
    this._workletNode = null;
    this._sourceNode = null;
    this._playbackQueue = [];
    this._isPlaying = false;
    this._nextPlayTime = 0;

    this._render();
  }

  // ── Public API ──────────────────────────────────────────────────────────

  get state() { return this._state; }

  async toggle() {
    if (this._state === 'idle' || this._state === 'error') {
      await this.start();
    } else {
      this.stop();
    }
  }

  async start() {
    if (this._state !== 'idle' && this._state !== 'error') return;

    try {
      // Get mic permission
      this._mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      // Create AudioContext at 16kHz for PCM capture
      this._audioCtx = new AudioContext({ sampleRate: 16000 });

      // Register worklet
      const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' });
      const url = URL.createObjectURL(blob);
      await this._audioCtx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);

      // Create processing pipeline
      this._sourceNode = this._audioCtx.createMediaStreamSource(this._mediaStream);
      this._workletNode = new AudioWorkletNode(this._audioCtx, 'pcm-capture-processor');

      // When worklet sends PCM buffer, forward to WebSocket
      this._workletNode.port.onmessage = (e) => {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
          this._ws.send(e.data);
        }
      };

      this._sourceNode.connect(this._workletNode);
      this._workletNode.connect(this._audioCtx.destination); // needed to keep processing alive

      // Connect WebSocket
      this._connectWs();
      this._setState('listening');

    } catch (err) {
      console.error('Voice start failed:', err);
      this._cleanup();
      this._setState('error');
      throw err;
    }
  }

  stop() {
    this._sendControl({ action: 'stop' });
    this._cleanup();
    this._setState('idle');
  }

  destroy() {
    this.stop();
    if (this._btn) {
      this._btn.remove();
    }
  }

  // ── WebSocket ───────────────────────────────────────────────────────────

  _connectWs() {
    const path = `/api/voice/ws/${this.role}/${this.userId}`;
    const primaryUrl = `${WS_BASE_PRIMARY}${path}`;

    if (WS_BASE_FALLBACK) {
      // HTTPS page → try wss:// first, fall back to ws:// after 3s
      const fallbackUrl = `${WS_BASE_FALLBACK}${path}`;
      this._tryConnect(primaryUrl, () => {
        console.log('[VoiceChat] wss:// failed, falling back to ws://');
        this._tryConnect(fallbackUrl, null);
      });
    } else {
      // HTTP page → ws:// directly, no fallback needed
      this._tryConnect(primaryUrl, null);
    }
  }

  /**
   * Attempt a WebSocket connection. If it fails within 3s and fallbackFn is
   * provided, call fallbackFn instead of entering error state.
   */
  _tryConnect(url, fallbackFn) {
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';

    const fallbackTimer = fallbackFn
      ? setTimeout(() => {
          // Connection didn't open in time — try fallback
          ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
          ws.close();
          fallbackFn();
        }, 3000)
      : null;

    ws.onopen = () => {
      clearTimeout(fallbackTimer);
      this._ws = ws;
      console.log(`[VoiceChat] Connected: ${url}`);
    };

    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        this._enqueueAudio(e.data);
      } else {
        try {
          const msg = JSON.parse(e.data);
          this._handleServerMsg(msg);
        } catch { /* ignore */ }
      }
    };

    ws.onclose = () => {
      clearTimeout(fallbackTimer);
      console.log('[VoiceChat] Disconnected');
      if (this._state !== 'idle' && this._state !== 'error') {
        this._cleanup();
        this._setState('error');
      }
    };

    ws.onerror = (err) => {
      clearTimeout(fallbackTimer);
      console.error('[VoiceChat] WebSocket error:', err);
      if (fallbackFn) {
        ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
        ws.close();
        fallbackFn();
      }
    };
  }

  _handleServerMsg(msg) {
    switch (msg.type) {
      case 'ready':
        // Connection established
        break;

      case 'vad':
        if (msg.event === 'speech_start') {
          this._setState('listening');
        }
        break;

      case 'barge_in':
        // Server cancelled TTS — stop local playback
        this._stopPlayback();
        this._setState('listening');
        break;

      case 'transcript':
        this.onTranscript(msg.text);
        this._setState('thinking');
        break;

      case 'thinking':
        this._setState('thinking');
        break;

      case 'response_text':
        this.onResponse(msg.text);
        this._setState('speaking');
        break;

      case 'tts_done':
        if (this._state === 'speaking') {
          this._setState('listening');
        }
        break;

      case 'error':
        console.error('[VoiceChat] Server error:', msg.message);
        this._setState('listening');
        break;
    }
  }

  _sendControl(msg) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(msg));
    }
  }

  // ── Audio playback ──────────────────────────────────────────────────────

  _enqueueAudio(arrayBuffer) {
    this._playbackQueue.push(arrayBuffer);
    if (!this._isPlaying) {
      this._playNextChunk();
    }
  }

  async _playNextChunk() {
    if (this._playbackQueue.length === 0) {
      this._isPlaying = false;
      return;
    }

    this._isPlaying = true;

    // Create a playback context at standard rate for MP3 decoding
    if (!this._playbackCtx) {
      this._playbackCtx = new AudioContext({ sampleRate: 24000 });
    }

    const chunk = this._playbackQueue.shift();
    try {
      const audioBuffer = await this._playbackCtx.decodeAudioData(chunk.slice(0));
      const source = this._playbackCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this._playbackCtx.destination);

      const startTime = Math.max(this._playbackCtx.currentTime, this._nextPlayTime);
      source.start(startTime);
      this._nextPlayTime = startTime + audioBuffer.duration;

      source.onended = () => {
        this._playNextChunk();
      };
    } catch (err) {
      console.warn('[VoiceChat] Audio decode error:', err);
      this._playNextChunk();
    }
  }

  _stopPlayback() {
    this._playbackQueue = [];
    this._isPlaying = false;
    this._nextPlayTime = 0;
    if (this._playbackCtx) {
      this._playbackCtx.close().catch(() => {});
      this._playbackCtx = null;
    }
  }

  // ── Cleanup ─────────────────────────────────────────────────────────────

  _cleanup() {
    // Stop mic
    if (this._workletNode) {
      this._workletNode.disconnect();
      this._workletNode = null;
    }
    if (this._sourceNode) {
      this._sourceNode.disconnect();
      this._sourceNode = null;
    }
    if (this._mediaStream) {
      this._mediaStream.getTracks().forEach(t => t.stop());
      this._mediaStream = null;
    }
    if (this._audioCtx) {
      this._audioCtx.close().catch(() => {});
      this._audioCtx = null;
    }

    // Stop playback
    this._stopPlayback();

    // Close WebSocket
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
  }

  // ── State management ───────────────────────────────────────────────────

  _setState(newState) {
    if (this._state === newState) return;
    this._state = newState;
    this._updateUI();
    this.onStateChange(newState);
  }

  // ── UI ─────────────────────────────────────────────────────────────────

  _render() {
    this._btn = document.createElement('button');
    this._btn.className = 'vc-mic-btn vc-state-idle';
    this._btn.title = 'Voice chat';
    this._btn.innerHTML = `
      <span class="vc-mic-icon">${this._micSvg()}</span>
      <span class="vc-pulse-ring"></span>
      <span class="vc-wave-bars">
        <span></span><span></span><span></span><span></span><span></span>
      </span>
      <span class="vc-thinking-dots"><span></span><span></span><span></span></span>
    `;

    this._btn.addEventListener('click', () => this.toggle());
    this.container.appendChild(this._btn);
  }

  _updateUI() {
    if (!this._btn) return;
    this._btn.className = `vc-mic-btn vc-state-${this._state}`;

    const titles = {
      idle: 'Start voice chat',
      listening: 'Listening... (click to stop)',
      thinking: 'Processing...',
      speaking: 'AI speaking... (click to interrupt)',
      error: 'Connection failed — click to retry',
    };
    this._btn.title = titles[this._state] || '';
  }

  _micSvg() {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>`;
  }
}
