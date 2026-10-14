/**
 * Entry helpers shared by contacts (calls) and the limb list (extension sessions), plus the contact buttons.
 * Messenger cards supply the saved Nostr contact; users never enter a call address.
 */
import { useState } from 'react';
import { Phone, Video, Loader2 } from 'lucide-react';
import { sessions, type CreateSessionBody } from '../../lib/media/session-client';
import type { MediaSession, SessionPurpose } from '../../lib/media/types';

export function callWindowHash(sessionId: string): string { return `#/media-call/${encodeURIComponent(sessionId)}`; }

/** Electron: one BrowserWindow per session. Browser shell: a new tab on the same document. */
export async function openCallWindow(sessionId: string): Promise<void> {
  const bridge = window.electron;
  if (bridge?.openMediaCall) { await bridge.openMediaCall(sessionId); return; }
  window.open(`${window.location.pathname}${callWindowHash(sessionId)}`, `indiebiz-media-${sessionId}`, 'noopener,width=960,height=680');
}

export async function createAndOpen(body: CreateSessionBody): Promise<MediaSession> {
  const session = await sessions.create(body);
  await openCallWindow(session.session_id);
  return session;
}

/** Voice/video call to a nostr identity (npub). */
export function startCall(purpose: 'voice_call' | 'video_call', npub: string): Promise<MediaSession> {
  return createAndOpen({ kind: 'call', purpose, target: npub, request_id: crypto.randomUUID() });
}

/** Extension session with a registered device (camera | microphone | speaker). */
export function startExtension(purpose: Extract<SessionPurpose, 'camera' | 'microphone' | 'speaker' | 'playback'>, deviceId: string): Promise<MediaSession> {
  return createAndOpen({ kind: 'extension', purpose, target: deviceId, request_id: crypto.randomUUID() });
}

/** Content delivery: hand a file path or URL and a start position to the device's player. */
export function startPlayback(deviceId: string, content: { path?: string; url?: string; position_s?: number }): Promise<MediaSession> {
  return createAndOpen({ kind: 'extension', purpose: 'playback', delivery: 'content', target: deviceId, request_id: crypto.randomUUID(), content: { ...content, position_s: content.position_s ?? 0 } });
}

/** Only messenger rows with a saved Nostr target render these controls. */
export function CallButtons({ target, name, compact = true }: {
  target: string; name: string; compact?: boolean;
}) {
  const [busy, setBusy] = useState<SessionPurpose | null>(null);
  const [error, setError] = useState('');
  const start = async (purpose: 'voice_call' | 'video_call') => {
    setBusy(purpose); setError('');
    try { await startCall(purpose, target); }
    catch (e) { setError(e instanceof Error ? e.message : '통화를 시작하지 못했습니다.'); }
    finally { setBusy(null); }
  };
  const cls = compact ? 'p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0 disabled:opacity-50'
    : 'flex items-center gap-1 rounded border border-stone-200 px-2 py-1 text-[11px] text-stone-600 hover:text-[#D97706] disabled:opacity-50';
  return (
    <div className="flex flex-wrap items-center gap-2 mt-2" onClick={e => e.stopPropagation()}>
      <button className={cls} disabled={busy !== null} title={`${name} 에게 음성 통화`} aria-label="음성 통화" onClick={() => void start('voice_call')}>
        {busy === 'voice_call' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Phone className="w-4 h-4" />}{!compact && '음성 통화'}
      </button>
      <button className={cls} disabled={busy !== null} title={`${name} 에게 영상 통화`} aria-label="영상 통화" onClick={() => void start('video_call')}>
        {busy === 'video_call' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Video className="w-4 h-4" />}{!compact && '영상 통화'}
      </button>
      {error && <span role="alert" className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
