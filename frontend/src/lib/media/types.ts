/** Wire contract for media sessions — mirrors docs/MEDIA_SESSION_CONTRACT.md (protocol_version 1). */

export type SessionKind = 'call' | 'extension';
export type SessionPurpose = 'voice_call' | 'video_call' | 'camera' | 'microphone' | 'speaker' | 'playback';
export type ParticipantRole = 'caller' | 'callee' | 'hub' | 'device';
export type TrackSource = 'mic' | 'camera' | 'playback' | 'screen';
export type TrackState = 'requested' | 'active' | 'muted' | 'rejected' | 'ended';
export type SessionState =
  | 'inviting' | 'ringing' | 'accepted' | 'authorized' | 'connecting' | 'active'
  | 'reconnecting' | 'needs_local_action' | 'ended';
export type SignalRoute = 'local' | 'extension' | 'nostr' | 'relay' | 'auto';
export type MediaPath = 'direct' | 'relay' | null;

export interface Participant {
  role: ParticipantRole;
  user: { id: string; name?: string };
  device: { id: string; name?: string; body?: 'pc' | 'phone' | 'helper' };
}

export interface SessionTrack {
  id: string;
  kind: 'audio' | 'video';
  source: TrackSource;
  from: ParticipantRole;
  to: ParticipantRole;
  state: TrackState;
}

export interface Quality {
  rtt_ms: number; loss: number; jitter_ms: number; bitrate_kbps: number;
  fps: number; width: number; height: number; dropped: number;
}

export interface Lease { lease_s: number; keepalive_s: number; reconnect_s: number; remaining_s?: number }

export interface SessionContent {
  ref?: string; url?: string; path?: string; position_s: number; paused?: boolean; volume?: number;
  /** Reported by the target player (contract §7: the source is not stopped before `playing`). */
  playing?: boolean; duration_s?: number;
}

export interface SessionError { code: string; message: string }

export interface MediaSession {
  session_id: string;
  protocol_version: number;
  kind: SessionKind;
  purpose: SessionPurpose;
  authorization_basis?: 'accepted_call' | 'extension_grant';
  participants: Participant[];
  tracks: SessionTrack[];
  delivery: 'realtime' | 'content';
  consent_scope?: { inputs: string[]; outputs: string[]; record: boolean };
  relation_generation?: string | null;
  state: SessionState;
  revision: number;
  generation: number;
  lease: Lease;
  expires_at?: number;
  ice_servers?: RTCIceServer[];
  signaling: { route: SignalRoute; relay?: string | null; pending_offer?: OfferPayload | null };
  path: MediaPath;
  quality?: Quality | null;
  content?: SessionContent | null;
  needs_local_action?: SessionError | null;
  error?: SessionError | null;
  created_at?: number; ended_at?: number; end_reason?: string;
}

export type SignalType =
  | 'invite' | 'accept' | 'reject' | 'offer' | 'answer' | 'candidate' | 'candidates_done'
  | 'keepalive' | 'ack' | 'state' | 'renegotiate' | 'end';

export interface OfferPayload { sdp: string; fingerprint: string }
export interface CandidatePayload { candidate: string; sdpMid?: string | null; sdpMLineIndex?: number | null }

export interface SignalFrame<P = Record<string, unknown>> {
  v: 1;
  session_id: string;
  msg_id: string;
  from: ParticipantRole;
  to: ParticipantRole;
  generation: number;
  seq: number;
  expires_at?: number;
  type: SignalType;
  payload: P;
  /** Added by the backend; the browser never signs. */
  mac?: string;
}

export type SessionPush = { type: 'session'; session: MediaSession };
export type ErrorPush = { type: 'error'; error: SessionError };

export type Envelope<T = MediaSession> =
  | { success: true; session: T }
  | { success: false; error: SessionError };

export interface QualityProfile { maxBitrateKbps?: number; maxFramerate?: number; width?: number; height?: number }

export const SIGNAL_TYPES: ReadonlySet<string> = new Set<SignalType>([
  'invite', 'accept', 'reject', 'offer', 'answer', 'candidate', 'candidates_done',
  'keepalive', 'ack', 'state', 'renegotiate', 'end',
]);

export const EMPTY_QUALITY: Quality = { rtt_ms: 0, loss: 0, jitter_ms: 0, bitrate_kbps: 0, fps: 0, width: 0, height: 0, dropped: 0 };
