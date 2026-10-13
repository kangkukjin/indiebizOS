/**
 * MediaSessionClient — REST (contract §2) + the local control WebSocket (contract §5 `local` route).
 * The hub signs frames (mac); this client only sequences them (generation/seq) and keeps the lease alive.
 */
import { api } from '../api';
import { WEBSOCKET_ORIGIN } from '../backend-origin';
import type {
  Envelope, MediaSession, ParticipantRole, SessionError, SessionKind, SessionPurpose, SignalFrame, SignalType,
} from './types.ts';
import { SignalSequencer, isSignalFrame } from './signal.ts';

export class MediaRequestError extends Error {
  code: string;
  constructor(error: SessionError) { super(error.message || error.code); this.code = error.code; }
}

/** `{success:false,error}` arrives with HTTP 200 or 400; api.request already surfaces the 400 message. */
export async function mediaRequest<T = MediaSession>(endpoint: string, body?: unknown, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
  const result = await api.request<Envelope<T>>(endpoint, body === undefined ? { method } : { method, body: JSON.stringify(body) });
  if (!result || typeof result !== 'object') throw new MediaRequestError({ code: 'invalid_response', message: '서버 응답을 읽을 수 없습니다.' });
  if (result.success === false) throw new MediaRequestError(result.error);
  return (result as { success: true; session: T }).session;
}

export interface CreateSessionBody {
  kind: SessionKind; purpose: SessionPurpose; target: string; request_id: string;
  tracks?: unknown[]; delivery?: 'realtime' | 'content';
  content?: { path?: string; url?: string; position_s?: number; volume?: number };
}

export const sessions = {
  create: (body: CreateSessionBody) => mediaRequest('/media/sessions', body),
  status: (id: string) => mediaRequest(`/media/sessions/${encodeURIComponent(id)}`),
  accept: (id: string, device = 'local') => mediaRequest(`/media/sessions/${encodeURIComponent(id)}/accept`, { device }),
  reject: (id: string, reason = 'rejected') => mediaRequest(`/media/sessions/${encodeURIComponent(id)}/reject`, { reason }),
  end: (id: string, reason = 'local_end') => mediaRequest(`/media/sessions/${encodeURIComponent(id)}/end`, { reason }),
  update: (id: string, expected_revision: number, changes: Record<string, unknown>) =>
    mediaRequest(`/media/sessions/${encodeURIComponent(id)}/update`, { expected_revision, changes }),
  signal: (id: string, frame: SignalFrame) => mediaRequest(`/media/sessions/${encodeURIComponent(id)}/signal`, frame),
  list: () => api.request<{ success?: boolean; items?: MediaSession[]; sessions?: MediaSession[] }>('/media/sessions?active=1'),
};

/** The participant whose device is this browser: `device.id === 'local'` (or `user.id === 'self'`). */
export function localRole(session: MediaSession): ParticipantRole {
  const mine = session.participants?.find(p => p.device?.id === 'local') ?? session.participants?.find(p => p.user?.id === 'self');
  if (mine) return mine.role;
  return session.kind === 'extension' ? 'hub' : 'caller';
}

export function remoteRole(session: MediaSession, mine = localRole(session)): ParticipantRole {
  const other = session.participants?.find(p => p.role !== mine);
  if (other) return other.role;
  if (session.kind === 'extension') return mine === 'hub' ? 'device' : 'hub';
  return mine === 'caller' ? 'callee' : 'caller';
}

export function remoteParticipant(session: MediaSession) {
  const mine = localRole(session);
  return session.participants?.find(p => p.role !== mine);
}

export interface ClientEvents {
  onSession?: (session: MediaSession) => void;
  onSignal?: (frame: SignalFrame) => void;
  onError?: (error: SessionError) => void;
  onSocket?: (open: boolean) => void;
  /** Extra keepalive payload, e.g. `{peer_alive:true}` once the DataChannel proved the peer alive (calls only). */
  keepalivePayload?: () => Record<string, unknown>;
}

export class MediaSessionClient {
  readonly sessionId: string;
  session: MediaSession | null = null;
  sequencer: SignalSequencer | null = null;
  private ws: WebSocket | null = null;
  private keepalive: ReturnType<typeof setInterval> | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;
  private events: ClientEvents;

  constructor(sessionId: string, events: ClientEvents = {}) { this.sessionId = sessionId; this.events = events; }

  /** Fetch the session, derive roles, then attach the control socket. */
  async connect(initial?: MediaSession): Promise<MediaSession> {
    const session = initial ?? await sessions.status(this.sessionId);
    this.adopt(session);
    this.openSocket();
    return session;
  }

  private adopt(session: MediaSession): void {
    this.session = session;
    if (!this.sequencer) this.sequencer = new SignalSequencer(session.session_id, localRole(session), remoteRole(session), session.generation ?? 0);
    else this.sequencer.adoptGeneration(session.generation ?? 0);
    this.events.onSession?.(session);
    if (session.state === 'ended') this.stopKeepalive();
    else this.startKeepalive(session.lease?.keepalive_s);
  }

  private openSocket(): void {
    if (this.disposed || this.session?.state === 'ended') return;
    const ws = new WebSocket(`${WEBSOCKET_ORIGIN}/media/sessions/${encodeURIComponent(this.sessionId)}/ws`);
    this.ws = ws;
    ws.onopen = () => this.events.onSocket?.(true);
    ws.onmessage = event => { if (typeof event.data === 'string') this.handle(event.data); };
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      this.events.onSocket?.(false);
      if (!this.disposed && this.session?.state !== 'ended') this.retry = setTimeout(() => this.openSocket(), 2000);
    };
    ws.onerror = () => { /* onclose follows and schedules the retry */ };
  }

  private handle(raw: string): void {
    let message: unknown;
    try { message = JSON.parse(raw); } catch { return; }
    if (!message || typeof message !== 'object') return;
    const envelope = message as { type?: string; session?: MediaSession; error?: SessionError };
    if (envelope.type === 'session' && envelope.session) { this.adopt(envelope.session); return; }
    if (envelope.type === 'error' && envelope.error) { this.events.onError?.(envelope.error); return; }
    if (isSignalFrame(message)) {
      if (!this.sequencer) return;
      const verdict = this.sequencer.accept(message);
      if (verdict === 'accept') this.events.onSignal?.(message);
    }
  }

  /** Send a contract frame over the control socket (REST fallback while the socket is down). */
  send<P extends Record<string, unknown>>(type: SignalType, payload: P, to?: ParticipantRole): SignalFrame<P> | null {
    if (!this.sequencer || this.session?.state === 'ended') return null;
    const frame = this.sequencer.frame(type, payload);
    if (to) frame.to = to;
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(frame));
    else void sessions.signal(this.sessionId, frame).catch(() => { /* surfaced by the next session push */ });
    return frame;
  }

  /** New negotiation generation (ICE restart): seq restarts, hub lease keeps the newest generation only. */
  bumpGeneration(): number { return this.sequencer?.bumpGeneration() ?? 0; }
  get generation(): number { return this.sequencer?.generation ?? 0; }

  private startKeepalive(seconds?: number): void {
    const interval = Math.max(1, seconds ?? 5) * 1000;
    if (this.keepalive) return;
    this.keepalive = setInterval(() => { if (this.ws?.readyState === WebSocket.OPEN) this.send('keepalive', this.events.keepalivePayload?.() ?? {}, 'hub'); }, interval);
  }

  private stopKeepalive(): void { if (this.keepalive) { clearInterval(this.keepalive); this.keepalive = null; } }

  // ── REST actions (results arrive as session pushes too; we adopt them immediately) ──

  async accept(device = 'local'): Promise<MediaSession> { const s = await sessions.accept(this.sessionId, device); this.adopt(s); return s; }
  async reject(reason = 'rejected'): Promise<MediaSession> { const s = await sessions.reject(this.sessionId, reason); this.adopt(s); return s; }
  async update(expectedRevision: number, changes: Record<string, unknown>): Promise<MediaSession> {
    const s = await sessions.update(this.sessionId, expectedRevision, changes); this.adopt(s); return s;
  }
  async end(reason = 'local_end'): Promise<MediaSession | null> {
    this.send('end', { reason });
    try { const s = await sessions.end(this.sessionId, reason); this.adopt(s); return s; }
    catch { return null; }
    finally { this.stopKeepalive(); }
  }

  dispose(): void {
    this.disposed = true;
    this.stopKeepalive();
    if (this.retry) { clearTimeout(this.retry); this.retry = null; }
    const ws = this.ws; this.ws = null;
    try { ws?.close(); } catch { /* already closed */ }
  }
}
