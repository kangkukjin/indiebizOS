/**
 * MediaEngine — one RTCPeerConnection behind the contract's offer/answer/candidate vocabulary.
 * Pure helpers live in sdp.ts so they can be unit-tested without a browser.
 */
import type { CandidatePayload, MediaPath, OfferPayload, Quality, QualityProfile } from './types.ts';
import { EMPTY_QUALITY } from './types.ts';
import {
  encodingForProfile, extractFingerprint, fingerprintsMatch, orderCodecs, pathFromStats, qualityFromStats,
  waitForGathering, type QualitySample,
} from './sdp.ts';

export type EngineState = 'new' | 'connecting' | 'active' | 'reconnecting' | 'failed' | 'closed';
export type EngineSignalType = 'offer' | 'answer' | 'candidate' | 'candidates_done' | 'renegotiate';

export interface EngineOptions {
  iceServers?: RTCIceServer[];
  refreshIceServers?: () => Promise<RTCIceServer[]>;
  /** false = non-trickle (contract §5 nostr route): one complete SDP after gathering. */
  trickle?: boolean;
  /** Seconds allowed in `reconnecting` before the engine gives up (lease.reconnect_s). */
  reconnectS?: number;
  qualityProfile?: QualityProfile;
  /** The offerer owns ICE restarts; the answerer asks for one with `renegotiate`. */
  offerer: boolean;
  generation?: number;
  onSignal: (type: EngineSignalType, payload: Record<string, unknown>, generation: number) => void;
  onState?: (state: EngineState, detail?: string) => void;
  onTrack?: (track: MediaStreamTrack, streams: readonly MediaStream[]) => void;
  /** Grace before a `disconnected` ICE state triggers a restart (ms). */
  disconnectGraceMs?: number;
  gatheringTimeoutMs?: number;
  /** Liveness ping interval over the DTLS-authenticated DataChannel (ms). */
  livenessIntervalMs?: number;
}

export class MediaEngine {
  readonly pc: RTCPeerConnection;
  generation: number;
  private options: EngineOptions;
  private _state: EngineState = 'new';
  /** Candidates buffered per generation until that generation's remote description is applied (contract §3). */
  private pendingCandidates = new Map<number, CandidatePayload[]>();
  private remoteApplied = false;
  private remoteGeneration = -1;
  private reconnectDeadline: ReturnType<typeof setTimeout> | null = null;
  private disconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private restarting = false;
  private sample: QualitySample | undefined;
  private lastFingerprint = '';
  private liveness: RTCDataChannel | null = null;
  private livenessTimer: ReturnType<typeof setInterval> | null = null;
  private lastPong = 0;
  private mediaCheck: ReturnType<typeof setTimeout> | null = null;
  private mediaDeadline = 0;

  constructor(options: EngineOptions) {
    this.options = options;
    this.generation = options.generation ?? 0;
    this.pc = new RTCPeerConnection({ iceServers: options.iceServers ?? [], bundlePolicy: 'max-bundle' });
    this.pc.onicecandidate = event => {
      if (this.options.trickle === false) return;
      if (event.candidate) {
        const { candidate, sdpMid, sdpMLineIndex } = event.candidate;
        this.options.onSignal('candidate', { candidate, sdpMid, sdpMLineIndex }, this.generation);
      } else this.options.onSignal('candidates_done', {}, this.generation);
    };
    this.pc.ontrack = event => this.options.onTrack?.(event.track, event.streams);
    // The offerer opens the liveness channel (it rides the offer); the answerer adopts it on arrival.
    if (options.offerer) this.attachLiveness(this.pc.createDataChannel('liveness', { ordered: true }));
    else this.pc.ondatachannel = event => { if (event.channel.label === 'liveness') this.attachLiveness(event.channel); };
    this.pc.oniceconnectionstatechange = () => this.onIceState();
    this.pc.onconnectionstatechange = () => {
      if (this.pc.connectionState === 'failed') this.onIceState('failed');
      else if (this.pc.connectionState === 'connected') this.onIceState();
    };
  }

  get state(): EngineState { return this._state; }

  /** True while the peer answered a ping over the DTLS-authenticated DataChannel recently (lease evidence for calls). */
  get peerAlive(): boolean {
    const interval = this.options.livenessIntervalMs ?? 2000;
    return this.liveness?.readyState === 'open' && Date.now() - this.lastPong < interval * 2.5;
  }

  private attachLiveness(channel: RTCDataChannel): void {
    this.liveness = channel;
    channel.onmessage = event => {
      if (event.data === 'ping') { try { channel.send('pong'); } catch { /* closing */ } }
      else if (event.data === 'pong') this.lastPong = Date.now();
    };
    channel.onopen = () => {
      this.lastPong = Date.now();
      if (this.livenessTimer) clearInterval(this.livenessTimer);
      this.livenessTimer = setInterval(() => { if (channel.readyState === 'open') { try { channel.send('ping'); } catch { /* closing */ } } }, this.options.livenessIntervalMs ?? 2000);
    };
    channel.onclose = () => { if (this.livenessTimer) { clearInterval(this.livenessTimer); this.livenessTimer = null; } };
  }

  private setState(state: EngineState, detail?: string): void {
    if (this._state === state || this._state === 'closed') return;
    this._state = state;
    this.options.onState?.(state, detail);
  }

  // ── local media ──

  addStream(stream: MediaStream, contentHint?: 'speech' | 'music'): void {
    for (const track of stream.getTracks()) {
      if (contentHint && 'contentHint' in track) track.contentHint = contentHint;
      this.pc.addTrack(track, stream);
    }
  }

  /** Receive-only slot (e.g. the hub watching a device camera). */
  addReceiver(kind: 'audio' | 'video'): void { this.pc.addTransceiver(kind, { direction: 'recvonly' }); }

  async replaceTrack(kind: 'audio' | 'video', track: MediaStreamTrack | null): Promise<void> {
    for (const sender of this.pc.getSenders()) {
      if (sender.track?.kind === kind || (!sender.track && kind === this.transceiverKind(sender))) await sender.replaceTrack(track);
    }
    if (track && kind === 'video') await this.applyQualityProfile();
  }

  private transceiverKind(sender: RTCRtpSender): string | undefined {
    return this.pc.getTransceivers().find(t => t.sender === sender)?.receiver.track.kind;
  }

  /** Local mute wins over anything remote: the track simply stops producing. */
  setEnabled(kind: 'audio' | 'video', enabled: boolean): void {
    for (const sender of this.pc.getSenders()) if (sender.track?.kind === kind) sender.track.enabled = enabled;
  }

  private applyCodecPreferences(): void {
    for (const transceiver of this.pc.getTransceivers()) {
      if (typeof transceiver.setCodecPreferences !== 'function') continue;
      const kind = (transceiver.sender.track?.kind ?? transceiver.receiver.track?.kind) as 'audio' | 'video' | undefined;
      if (!kind) continue;
      const caps = (transceiver.direction === 'recvonly' ? RTCRtpReceiver : RTCRtpSender).getCapabilities?.(kind);
      if (!caps?.codecs?.length) continue;
      try { transceiver.setCodecPreferences(orderCodecs(kind, caps.codecs)); } catch { /* unsupported codec list: keep defaults */ }
    }
  }

  async applyQualityProfile(profile = this.options.qualityProfile): Promise<void> {
    this.options.qualityProfile = profile;
    if (!profile) return;
    for (const sender of this.pc.getSenders()) {
      if (sender.track?.kind !== 'video') continue;
      const params = sender.getParameters();
      if (!params.encodings?.length) params.encodings = [{}];
      Object.assign(params.encodings[0], encodingForProfile(profile, sender.track.getSettings().width));
      try { await sender.setParameters(params); } catch { /* some engines reject before the first negotiation */ }
    }
  }

  // ── negotiation ──

  private async localDescriptionPayload(): Promise<OfferPayload> {
    if (this.options.trickle === false) await waitForGathering(this.pc, this.options.gatheringTimeoutMs ?? 5000);
    const sdp = this.pc.localDescription?.sdp ?? '';
    return { sdp, fingerprint: extractFingerprint(sdp) };
  }

  /** Offerer only. Emits `offer` through onSignal (with ICE restart when `restart`). */
  async createOffer(restart = false): Promise<OfferPayload> {
    if (this._state === 'closed') throw new Error('engine closed');
    this.applyCodecPreferences();
    if (restart && this.options.refreshIceServers) {
      const iceServers = await this.options.refreshIceServers();
      this.pc.setConfiguration({ ...this.pc.getConfiguration(), iceServers });
    }
    if (restart) { this.generation += 1; this.pc.restartIce?.(); }
    const offer = await this.pc.createOffer(restart ? { iceRestart: true } : undefined);
    await this.pc.setLocalDescription(offer);
    await this.applyQualityProfile();
    if (this._state === 'new') this.setState('connecting');
    const payload = await this.localDescriptionPayload();
    this.options.onSignal('offer', { ...payload }, this.generation);
    return payload;
  }

  /** Apply a remote offer (answerer) and emit the answer. Fingerprint mismatch is refused. */
  async acceptOffer(payload: OfferPayload, generation = this.generation): Promise<OfferPayload> {
    if (!fingerprintsMatch(payload.sdp, payload.fingerprint)) throw new Error('fingerprint_mismatch');
    if (payload.ice_servers) this.pc.setConfiguration({ ...this.pc.getConfiguration(), iceServers: payload.ice_servers });
    if (generation > this.generation) this.generation = generation;
    this.remoteApplied = false;
    await this.pc.setRemoteDescription({ type: 'offer', sdp: payload.sdp });
    this.remoteApplied = true; this.remoteGeneration = generation;
    this.applyCodecPreferences();
    const answer = await this.pc.createAnswer();
    await this.pc.setLocalDescription(answer);
    await this.applyQualityProfile();
    await this.flushCandidates(generation);
    if (this._state === 'new') this.setState('connecting');
    const local = await this.localDescriptionPayload();
    this.lastFingerprint = payload.fingerprint || extractFingerprint(payload.sdp);
    this.options.onSignal('answer', { ...local }, this.generation);
    this.onIceState();
    return local;
  }

  async acceptAnswer(payload: OfferPayload, generation = this.generation): Promise<void> {
    if (!fingerprintsMatch(payload.sdp, payload.fingerprint)) throw new Error('fingerprint_mismatch');
    if (generation < this.generation) return;  // answer to an older offer: ignore
    if (this.pc.signalingState !== 'have-local-offer') return;
    this.remoteApplied = false;
    await this.pc.setRemoteDescription({ type: 'answer', sdp: payload.sdp });
    this.remoteApplied = true; this.remoteGeneration = generation;
    this.lastFingerprint = payload.fingerprint || extractFingerprint(payload.sdp);
    this.restarting = false;
    await this.flushCandidates(generation);
    // An ICE restart on an unchanged path can finish without any state event: reconcile with the live state.
    this.onIceState();
  }

  /** A candidate for a newer generation than the applied description waits; an older one is dropped. */
  async addCandidate(candidate: CandidatePayload, generation = this.remoteGeneration): Promise<void> {
    if (generation < this.remoteGeneration) return;
    if (generation > this.remoteGeneration || !this.remoteApplied) {
      const list = this.pendingCandidates.get(generation) ?? [];
      list.push(candidate); this.pendingCandidates.set(generation, list);
      return;
    }
    try { await this.pc.addIceCandidate(candidate as RTCIceCandidateInit); } catch { /* stale candidate for a replaced generation */ }
  }

  async candidatesDone(): Promise<void> {
    if (!this.remoteApplied) return;
    try { await this.pc.addIceCandidate({ candidate: '' }); } catch { /* end-of-candidates is advisory */ }
  }

  private async flushCandidates(generation: number): Promise<void> {
    for (const key of Array.from(this.pendingCandidates.keys())) if (key < generation) this.pendingCandidates.delete(key);
    const list = this.pendingCandidates.get(generation) ?? [];
    this.pendingCandidates.delete(generation);
    for (const candidate of list) await this.addCandidate(candidate, generation);
  }

  /** Route one incoming signal payload. `generation` is the frame's generation. */
  async receive(type: EngineSignalType, payload: Record<string, unknown>, generation: number): Promise<void> {
    switch (type) {
      case 'offer': await this.acceptOffer(payload as unknown as OfferPayload, generation); break;
      case 'answer': await this.acceptAnswer(payload as unknown as OfferPayload, generation); break;
      case 'candidate': await this.addCandidate(payload as unknown as CandidatePayload, generation); break;
      case 'candidates_done': await this.candidatesDone(); break;
      case 'renegotiate': if (this.options.offerer) await this.restart(); break;
    }
  }

  // ── recovery ──

  /** Offerer: ICE restart with a new generation. Answerer: ask the offerer to restart. */
  async restart(): Promise<void> {
    if (this._state === 'closed' || this.restarting) return;
    this.restarting = true;
    this.armReconnectDeadline();
    this.setState('reconnecting');
    if (this.options.offerer) {
      try { await this.createOffer(true); } catch { this.restarting = false; }
    } else {
      this.options.onSignal('renegotiate', {}, this.generation);
      this.restarting = false;
    }
  }

  private armReconnectDeadline(): void {
    if (this.reconnectDeadline) return;
    const seconds = this.options.reconnectS ?? 30;
    this.reconnectDeadline = setTimeout(() => {
      this.reconnectDeadline = null;
      const ice = this.pc.iceConnectionState;
      if (ice === 'connected' || ice === 'completed') { this.onIceState(); return; }
      if (this._state === 'reconnecting' || this._state === 'connecting') this.setState('failed', 'connectivity_failed');
    }, seconds * 1000);
  }

  private clearTimers(): void {
    if (this.mediaCheck) { clearTimeout(this.mediaCheck); this.mediaCheck = null; }
    if (this.reconnectDeadline) { clearTimeout(this.reconnectDeadline); this.reconnectDeadline = null; }
    if (this.disconnectTimer) { clearTimeout(this.disconnectTimer); this.disconnectTimer = null; }
  }

  private clearLiveness(): void {
    if (this.livenessTimer) { clearInterval(this.livenessTimer); this.livenessTimer = null; }
    try { this.liveness?.close(); } catch { /* already closed */ }
    this.liveness = null;
  }

  private onIceState(forced?: 'failed'): void {
    const state = forced ?? this.pc.iceConnectionState;
    if (this._state === 'closed') return;
    if (state === 'connected' || state === 'completed') {
      if (this._state !== 'active' && !this.mediaCheck) { this.mediaDeadline = Date.now() + 15000; void this.confirmMediaFlow(); }
      return;
    }
    if (state === 'failed') { void this.restart(); return; }
    if (state === 'disconnected') {
      this.setState('reconnecting');
      this.armReconnectDeadline();
      if (!this.disconnectTimer) this.disconnectTimer = setTimeout(() => {
        this.disconnectTimer = null;
        if (this.pc.iceConnectionState === 'disconnected') void this.restart();
      }, this.options.disconnectGraceMs ?? 3000);
    }
  }

  /** ICE connectivity alone does not prove that a camera or decoder is producing media. */
  private async confirmMediaFlow(): Promise<void> {
    if (this._state === 'closed' || this._state === 'failed') return;
    const receives = this.pc.getTransceivers().some(t => ['recvonly', 'sendrecv'].includes(t.currentDirection ?? ''));
    let flowing = false;
    try {
      const report = await this.pc.getStats();
      report.forEach(s => {
        if (receives && s.type === 'inbound-rtp' && (s.framesDecoded > 0 || s.totalSamplesReceived > 0 || s.totalSamplesDuration > 0)) flowing = true;
        if (!receives && s.type === 'outbound-rtp' && s.bytesSent > 0) flowing = true;
      });
    } catch { /* retry until the output deadline */ }
    if (this.state === 'closed') return;
    if (flowing) { this.clearTimers(); this.restarting = false; this.setState('active'); return; }
    if (Date.now() >= this.mediaDeadline) { this.setState('failed', 'media_output_timeout'); return; }
    this.mediaCheck = setTimeout(() => { this.mediaCheck = null; void this.confirmMediaFlow(); }, 100);
  }

  // ── observation ──

  async getQuality(): Promise<{ quality: Quality; path: MediaPath }> {
    if (this._state === 'closed') return { quality: { ...EMPTY_QUALITY }, path: null };
    try {
      const report = await this.pc.getStats();
      const entries = Array.from(report.values()) as { type: string; [key: string]: unknown }[];
      const { quality, sample } = qualityFromStats(entries, this.sample);
      this.sample = sample;
      return { quality, path: pathFromStats(entries) };
    } catch { return { quality: { ...EMPTY_QUALITY }, path: null }; }
  }

  get remoteFingerprint(): string { return this.lastFingerprint; }

  close(): void {
    this.clearTimers(); this.clearLiveness();
    for (const sender of this.pc.getSenders()) sender.track?.stop();
    try { this.pc.close(); } catch { /* already closed */ }
    this._state = 'closed';
    this.options.onState?.('closed');
  }
}
