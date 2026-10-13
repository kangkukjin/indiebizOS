/** Signal frame sequencing (contract §3): generation/seq, stale-frame rejection, candidate buffering. Pure. */
import type { CandidatePayload, ParticipantRole, SignalFrame, SignalType } from './types.ts';
import { SIGNAL_TYPES } from './types.ts';

export function randomHex(bytes: number): string {
  const array = new Uint8Array(bytes);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(array);
  else for (let i = 0; i < bytes; i++) array[i] = Math.floor(Math.random() * 256);
  return Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
}

export function isSignalFrame(value: unknown): value is SignalFrame {
  if (!value || typeof value !== 'object') return false;
  const frame = value as Record<string, unknown>;
  return frame.v === 1 && typeof frame.session_id === 'string' && typeof frame.type === 'string'
    && SIGNAL_TYPES.has(frame.type) && typeof frame.generation === 'number' && typeof frame.seq === 'number';
}

export type AcceptResult = 'accept' | 'stale_generation' | 'stale_seq' | 'expired' | 'duplicate' | 'other_session';

/** Outgoing sequencing + incoming ordering for one session as seen by one participant. */
export class SignalSequencer {
  readonly sessionId: string;
  readonly from: ParticipantRole;
  to: ParticipantRole;
  generation: number;
  private seq = 0;
  private seenGeneration = -1;
  private seenSeq = -1;
  private seenIds = new Set<string>();
  /** Candidates that arrived before the offer/answer of their generation. */
  private pending = new Map<number, CandidatePayload[]>();
  private now: () => number;

  constructor(sessionId: string, from: ParticipantRole, to: ParticipantRole, generation = 0, now: () => number = () => Date.now() / 1000) {
    this.sessionId = sessionId; this.from = from; this.to = to; this.generation = generation; this.now = now;
  }

  /** Start a new negotiation generation (reconnect / renegotiate): seq restarts at 1. */
  bumpGeneration(): number { this.generation += 1; this.seq = 0; return this.generation; }

  /** Adopt the hub's generation (e.g. after a session push) without going backwards. */
  adoptGeneration(generation: number): void { if (generation > this.generation) { this.generation = generation; this.seq = 0; } }

  frame<P extends Record<string, unknown>>(type: SignalType, payload: P, ttlSeconds = 60): SignalFrame<P> {
    this.seq += 1;
    return {
      v: 1, session_id: this.sessionId, msg_id: randomHex(8), from: this.from, to: this.to,
      generation: this.generation, seq: this.seq, expires_at: this.now() + ttlSeconds, type, payload,
    };
  }

  /** Decide whether an incoming frame is current. Lower generation / old seq / expired / duplicate → drop. */
  accept(frame: SignalFrame): AcceptResult {
    if (frame.session_id !== this.sessionId) return 'other_session';
    if (typeof frame.expires_at === 'number' && frame.expires_at < this.now()) return 'expired';
    if (frame.generation < this.seenGeneration) return 'stale_generation';
    if (frame.msg_id && this.seenIds.has(frame.msg_id)) return 'duplicate';
    if (frame.generation === this.seenGeneration && frame.seq <= this.seenSeq) return 'stale_seq';
    if (frame.generation > this.seenGeneration) { this.seenGeneration = frame.generation; this.seenSeq = -1; this.seenIds.clear(); }
    this.seenSeq = frame.seq;
    if (frame.msg_id) this.seenIds.add(frame.msg_id);
    // A remote negotiation at a newer generation moves our own outgoing generation forward too.
    if (frame.generation > this.generation) { this.generation = frame.generation; this.seq = 0; }
    return 'accept';
  }

  /** Buffer a candidate until the description of the same generation has been applied. */
  bufferCandidate(generation: number, candidate: CandidatePayload): void {
    const list = this.pending.get(generation) ?? [];
    list.push(candidate); this.pending.set(generation, list);
  }

  /** Release buffered candidates for `generation`; older generations are discarded. */
  drainCandidates(generation: number): CandidatePayload[] {
    for (const key of Array.from(this.pending.keys())) if (key < generation) this.pending.delete(key);
    const list = this.pending.get(generation) ?? [];
    this.pending.delete(generation);
    return list;
  }

  get lastSeq(): number { return this.seq; }
}
