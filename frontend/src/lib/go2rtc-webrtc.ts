/**
 * Client go2rtc — WebRTC direct (port 1984 + média 8555).
 * LIVE uniquement quand des frames arrivent ; repli MSE si écran noir.
 */

export type Go2RtcPlayerState = 'idle' | 'connecting' | 'live' | 'error' | 'fallback-mse';

export interface Go2RtcWebRtcOptions {
  src: string;
  origins?: string[];
  onState?: (state: Go2RtcPlayerState, detail?: string) => void;
}

const GO2RTC_PORT = 1984;
const FRAME_WAIT_MS = 8000;

export function resolveGo2RtcOrigins(): string[] {
  const out: string[] = [];
  const fromEnv = import.meta.env.VITE_GO2RTC_ORIGIN as string | undefined;
  if (fromEnv?.trim()) {
    out.push(fromEnv.trim().replace(/\/$/, ''));
  }
  if (typeof window !== 'undefined') {
    const { hostname, protocol, origin } = window.location;
    out.push(`${protocol}//${hostname}:${GO2RTC_PORT}`);
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      out.push(`http://127.0.0.1:${GO2RTC_PORT}`);
      out.push(`http://localhost:${GO2RTC_PORT}`);
    }
    out.push(`${origin}/go2rtc`);
  } else {
    out.push(`http://localhost:${GO2RTC_PORT}`);
  }
  return [...new Set(out)];
}

function httpOriginToWs(httpOrigin: string): string {
  const u = new URL(httpOrigin);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  return u.origin;
}

const H264_CODECS = [
  'avc1.640029',
  'avc1.64002A',
  'avc1.640033',
  'avc1.42E01E',
];

function pickMseCodec(): string {
  if (typeof MediaSource === 'undefined') return H264_CODECS[0];
  return H264_CODECS.filter((c) => MediaSource.isTypeSupported(`video/mp4; codecs="${c}"`)).join() || H264_CODECS[0];
}

export class Go2RtcWebRtcPlayer {
  private video: HTMLVideoElement;
  private ws: WebSocket | null = null;
  private pc: RTCPeerConnection | null = null;
  private mediaSource: MediaSource | null = null;
  private sourceBuffer: SourceBuffer | null = null;
  private pendingChunks: Uint8Array[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private frameTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private liveSince = 0;
  private origins: string[] = [];
  private originIndex = 0;
  private wsOpened = false;
  private mode: 'webrtc' | 'mse' = 'webrtc';

  constructor(
    private readonly opts: Go2RtcWebRtcOptions,
    videoEl: HTMLVideoElement,
  ) {
    this.video = videoEl;
    this.video.playsInline = true;
    this.video.autoplay = true;
    this.video.muted = true;
    this.video.preload = 'auto';
  }

  start(): void {
    this.stopped = false;
    this.mode = 'webrtc';
    this.origins = this.opts.origins?.length ? this.opts.origins : resolveGo2RtcOrigins();
    this.originIndex = 0;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.frameTimer) {
      clearTimeout(this.frameTimer);
      this.frameTimer = null;
    }
    this.teardown();
    this.opts.onState?.('idle');
  }

  private currentOrigin(): string {
    return this.origins[this.originIndex] ?? this.origins[0];
  }

  private wsUrl(): string {
    return `${httpOriginToWs(this.currentOrigin())}/api/ws?src=${encodeURIComponent(this.opts.src)}`;
  }

  private tryNextOrigin(): boolean {
    if (this.originIndex < this.origins.length - 1) {
      this.originIndex += 1;
      return true;
    }
    return false;
  }

  private connect(): void {
    if (this.stopped || this.ws) return;
    this.opts.onState?.(this.mode === 'mse' ? 'fallback-mse' : 'connecting');
    this.wsOpened = false;

    const ws = new WebSocket(this.wsUrl());
    ws.binaryType = 'arraybuffer';
    this.ws = ws;

    ws.onopen = () => {
      this.wsOpened = true;
      if (this.mode === 'mse') {
        this.startMse(ws);
      } else {
        this.startWebRtc(ws);
      }
    };
    ws.onclose = () => this.onWsClose();
    ws.onerror = () => this.onWsError();
  }

  private onWsError(): void {
    if (this.stopped) return;
    if (!this.wsOpened && this.tryNextOrigin()) {
      this.teardown(false);
      this.connect();
      return;
    }
    this.opts.onState?.('error', `WebSocket failed (${this.currentOrigin()})`);
  }

  private startWebRtc(ws: WebSocket): void {
    const pc = new RTCPeerConnection({
      bundlePolicy: 'max-bundle',
      iceServers: [{ urls: ['stun:stun.l.google.com:19302', 'stun:stun.cloudflare.com:3478'] }],
    });
    this.pc = pc;

    pc.ontrack = (ev) => {
      if (ev.streams[0]) {
        this.video.srcObject = ev.streams[0];
        void this.play();
        this.waitForVideoFrames();
      }
    };

    pc.onicecandidate = (ev) => {
      if (ev.candidate && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'webrtc/candidate', value: ev.candidate.candidate }));
      }
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed') {
        this.tryMseFallback();
      }
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      const msg = JSON.parse(ev.data) as { type: string; value?: string };
      if (msg.type === 'webrtc/answer' && msg.value) {
        void pc.setRemoteDescription({ type: 'answer', sdp: msg.value });
      } else if (msg.type === 'webrtc/candidate' && msg.value) {
        void pc.addIceCandidate({ candidate: msg.value, sdpMid: '0' }).catch(() => {});
      } else if (msg.type === 'error') {
        this.opts.onState?.('error', msg.value);
      }
    };

    pc.addTransceiver('video', { direction: 'recvonly' });
    void pc.createOffer().then((offer) => {
      void pc.setLocalDescription(offer);
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'webrtc/offer', value: offer.sdp }));
      }
    });
  }

  private startMse(ws: WebSocket): void {
    const ms = new MediaSource();
    this.mediaSource = ms;

    ms.addEventListener(
      'sourceopen',
      () => {
        ws.send(JSON.stringify({ type: 'mse', value: pickMseCodec() }));
      },
      { once: true },
    );

    this.video.srcObject = null;
    this.video.src = URL.createObjectURL(ms);
    void this.play();

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data) as { type: string; value?: string };
        if (msg.type === 'mse' && msg.value && ms.readyState === 'open' && !this.sourceBuffer) {
          try {
            this.sourceBuffer = ms.addSourceBuffer(msg.value);
            this.sourceBuffer.mode = 'segments';
            this.sourceBuffer.addEventListener('updateend', () => this.flushMseBuffer());
            this.waitForVideoFrames();
          } catch {
            this.opts.onState?.('error', 'MSE init failed');
          }
        } else if (msg.type === 'error') {
          this.opts.onState?.('error', msg.value);
        }
        return;
      }
      if (this.sourceBuffer) {
        this.pendingChunks.push(new Uint8Array(ev.data as ArrayBuffer));
        this.flushMseBuffer();
      }
    };
  }

  private flushMseBuffer(): void {
    if (!this.sourceBuffer || this.sourceBuffer.updating || this.pendingChunks.length === 0) return;
    const chunk = this.pendingChunks.shift();
    if (!chunk) return;
    try {
      this.sourceBuffer.appendBuffer(chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength) as ArrayBuffer);
    } catch {
      /* buffer full — drop */
    }
  }

  private waitForVideoFrames(): void {
    if (this.frameTimer) clearTimeout(this.frameTimer);
    const started = Date.now();

    const tick = () => {
      if (this.stopped) return;
      if (this.video.videoWidth > 0 && this.video.readyState >= 2) {
        this.liveSince = Date.now();
        this.opts.onState?.('live');
        return;
      }
      if (Date.now() - started > FRAME_WAIT_MS) {
        this.tryMseFallback();
        return;
      }
      this.frameTimer = setTimeout(tick, 200);
    };
    tick();
  }

  private tryMseFallback(): void {
    if (this.stopped || this.mode === 'mse' || typeof MediaSource === 'undefined') {
      this.opts.onState?.('error', 'Flux média indisponible (port 8555 ?)');
      return;
    }
    this.mode = 'mse';
    this.originIndex = 0;
    this.teardown(false);
    this.connect();
  }

  private onWsClose(): void {
    this.teardown(false);
    if (this.stopped) return;
    if (!this.wsOpened && this.tryNextOrigin()) {
      this.connect();
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer) return;
    this.originIndex = 0;
    const delay = this.liveSince ? 2000 : 3000;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private teardown(clearVideo = true): void {
    if (this.frameTimer) {
      clearTimeout(this.frameTimer);
      this.frameTimer = null;
    }
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
    this.sourceBuffer = null;
    this.pendingChunks = [];
    if (this.mediaSource) {
      try {
        if (this.mediaSource.readyState === 'open') this.mediaSource.endOfStream();
      } catch {
        /* ignore */
      }
      this.mediaSource = null;
    }
    if (clearVideo) {
      if (this.video.src.startsWith('blob:')) URL.revokeObjectURL(this.video.src);
      this.video.srcObject = null;
      this.video.removeAttribute('src');
    }
  }

  private async play(): Promise<void> {
    try {
      await this.video.play();
    } catch {
      this.video.muted = true;
      await this.video.play().catch(() => {});
    }
  }
}
