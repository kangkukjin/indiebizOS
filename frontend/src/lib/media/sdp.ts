/** Pure helpers: SDP fingerprint, stats → contract quality/path, gathering wait. No DOM at module level. */
import type { MediaPath, Quality, QualityProfile } from './types.ts';
import { EMPTY_QUALITY } from './types.ts';

/** `a=fingerprint:sha-256 AB:CD:…` → `sha-256 AB:CD:…` (contract §3 payload.fingerprint). */
export function extractFingerprint(sdp: string): string {
  const match = /^a=fingerprint:\s*([A-Za-z0-9-]+)\s+([0-9A-Fa-f:]+)\s*$/m.exec(sdp || '');
  return match ? `${match[1].toLowerCase()} ${match[2].toUpperCase()}` : '';
}

export function fingerprintsMatch(sdp: string, declared: string | undefined): boolean {
  if (!declared) return true;  // nothing declared: nothing to compare (the hub verifies the mac)
  return extractFingerprint(sdp).toUpperCase() === declared.trim().replace(/\s+/g, ' ').toUpperCase();
}

/** Minimal stats shapes we read (a subset of RTCStats). */
export interface StatLike { id?: string; type: string; timestamp?: number; [key: string]: unknown }

export interface QualitySample { bytes: number; timestamp: number }

function num(value: unknown): number { return typeof value === 'number' && Number.isFinite(value) ? value : 0; }

function selectedPair(entries: StatLike[]): StatLike | undefined {
  const byId = new Map(entries.filter(e => e.id).map(e => [e.id as string, e]));
  const transport = entries.find(e => e.type === 'transport' && typeof e.selectedCandidatePairId === 'string');
  const fromTransport = transport ? byId.get(transport.selectedCandidatePairId as string) : undefined;
  if (fromTransport) return fromTransport;
  return entries.find(e => e.type === 'candidate-pair' && e.state === 'succeeded' && (e.nominated === true || e.nominated === undefined));
}

/** direct|relay from the selected candidate pair (`candidateType === 'relay'` on either side). */
export function pathFromStats(entries: StatLike[]): MediaPath {
  const pair = selectedPair(entries);
  if (!pair) return null;
  const byId = new Map(entries.filter(e => e.id).map(e => [e.id as string, e]));
  const local = byId.get(String(pair.localCandidateId ?? ''));
  const remote = byId.get(String(pair.remoteCandidateId ?? ''));
  if (!local && !remote) return null;
  return local?.candidateType === 'relay' || remote?.candidateType === 'relay' ? 'relay' : 'direct';
}

/** Contract `quality` from one stats report. `previous` enables bitrate from byte deltas. */
export function qualityFromStats(entries: StatLike[], previous?: QualitySample): { quality: Quality; sample: QualitySample } {
  const quality: Quality = { ...EMPTY_QUALITY };
  const pair = selectedPair(entries);
  if (pair) quality.rtt_ms = Math.round(num(pair.currentRoundTripTime) * 1000);
  let lost = 0, received = 0, bytes = 0, timestamp = 0, jitterSum = 0, jitterCount = 0;
  for (const e of entries) {
    if (e.type === 'inbound-rtp') {
      lost += num(e.packetsLost); received += num(e.packetsReceived); bytes += num(e.bytesReceived);
      timestamp = Math.max(timestamp, num(e.timestamp));
      if (typeof e.jitter === 'number') { jitterSum += e.jitter; jitterCount++; }
      if (e.kind === 'video') {
        quality.fps = Math.round(num(e.framesPerSecond));
        quality.width = num(e.frameWidth); quality.height = num(e.frameHeight);
        quality.dropped += num(e.framesDropped);
      }
    } else if (e.type === 'outbound-rtp') {
      bytes += num(e.bytesSent); timestamp = Math.max(timestamp, num(e.timestamp));
      if (e.kind === 'video' && !quality.width) {
        quality.fps = quality.fps || Math.round(num(e.framesPerSecond));
        quality.width = num(e.frameWidth); quality.height = num(e.frameHeight);
      }
    } else if (e.type === 'remote-inbound-rtp' && !received && typeof e.fractionLost === 'number') {
      quality.loss = Math.round(e.fractionLost * 1000) / 1000;
    }
  }
  if (received + lost > 0) quality.loss = Math.round((lost / (lost + received)) * 1000) / 1000;
  if (jitterCount) quality.jitter_ms = Math.round((jitterSum / jitterCount) * 1000);
  if (previous && timestamp > previous.timestamp && bytes >= previous.bytes) {
    quality.bitrate_kbps = Math.round(((bytes - previous.bytes) * 8) / (timestamp - previous.timestamp));
  }
  return { quality, sample: { bytes, timestamp } };
}

/** Opus first for audio; H.264 then VP8 first for video; everything else keeps its order. */
export function orderCodecs<T extends { mimeType: string }>(kind: 'audio' | 'video', codecs: T[]): T[] {
  const preferred = kind === 'audio' ? ['audio/opus'] : ['video/h264', 'video/vp8'];
  const rank = (c: T) => { const i = preferred.indexOf(c.mimeType.toLowerCase()); return i === -1 ? preferred.length : i; };
  return codecs.map((c, i) => ({ c, i })).sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i).map(x => x.c);
}

/** Sender encoding parameters for a quality profile (applied through RTCRtpSender.setParameters). */
export function encodingForProfile(profile: QualityProfile | undefined, trackWidth?: number): Record<string, number> {
  const encoding: Record<string, number> = {};
  if (!profile) return encoding;
  if (profile.maxBitrateKbps) encoding.maxBitrate = Math.round(profile.maxBitrateKbps * 1000);
  if (profile.maxFramerate) encoding.maxFramerate = profile.maxFramerate;
  if (profile.width && trackWidth && trackWidth > profile.width) encoding.scaleResolutionDownBy = trackWidth / profile.width;
  return encoding;
}

/** Non-trickle mode: resolve when ICE gathering is complete (or after `timeoutMs`, with what we have). */
export function waitForGathering(
  pc: { iceGatheringState: string; addEventListener(type: string, fn: () => void): void; removeEventListener(type: string, fn: () => void): void },
  timeoutMs = 5000,
): Promise<'complete' | 'timeout'> {
  if (pc.iceGatheringState === 'complete') return Promise.resolve('complete');
  return new Promise(resolve => {
    const done = (result: 'complete' | 'timeout') => { clearTimeout(timer); pc.removeEventListener('icegatheringstatechange', check); resolve(result); };
    const check = () => { if (pc.iceGatheringState === 'complete') done('complete'); };
    const timer = setTimeout(() => done('timeout'), timeoutMs);
    pc.addEventListener('icegatheringstatechange', check);
  });
}

/** Audio constraints: voice processing ON for calls, OFF for music/playback tracks. */
export function audioConstraints(source: 'mic' | 'playback', deviceId?: string): MediaTrackConstraints {
  const processing = source === 'mic';
  const constraints: MediaTrackConstraints = { echoCancellation: processing, noiseSuppression: processing, autoGainControl: processing };
  if (deviceId) constraints.deviceId = { exact: deviceId };
  return constraints;
}

export function videoConstraints(profile?: QualityProfile, deviceId?: string, facingMode?: 'user' | 'environment'): MediaTrackConstraints {
  const constraints: MediaTrackConstraints = {};
  if (profile?.width) constraints.width = { ideal: profile.width };
  if (profile?.height) constraints.height = { ideal: profile.height };
  if (profile?.maxFramerate) constraints.frameRate = { ideal: profile.maxFramerate, max: profile.maxFramerate };
  if (deviceId) constraints.deviceId = { exact: deviceId };
  else if (facingMode) constraints.facingMode = facingMode;
  return constraints;
}
