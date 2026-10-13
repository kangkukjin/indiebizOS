/**
 * Global incoming-call banner. Listens for `indiebiz:media-event` (dispatched where chat WS messages arrive
 * with `{type:'media_event', event, session}`) and offers 수락/거절. Accepting only opens the call window —
 * the real accept (and any sensor capture) happens inside it.
 */
import { useEffect, useState } from 'react';
import { Phone, PhoneOff } from 'lucide-react';
import type { MediaSession } from '../../lib/media/types';
import { localRole, remoteParticipant, sessions } from '../../lib/media/session-client';
import { openCallWindow } from './CallButtons';

export const MEDIA_EVENT = 'indiebiz:media-event';
export interface MediaEventDetail { type?: string; event?: string; session?: MediaSession }

export function dispatchMediaEvent(detail: MediaEventDetail): void {
  window.dispatchEvent(new CustomEvent<MediaEventDetail>(MEDIA_EVENT, { detail }));
}

export function IncomingCallBanner() {
  const [ringing, setRinging] = useState<MediaSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const onEvent = (event: Event) => {
      const detail = (event as CustomEvent<MediaEventDetail>).detail;
      const session = detail?.session;
      if (!session) return;
      if (detail.event === 'ringing' && session.kind === 'call' && localRole(session) === 'callee' && session.state === 'ringing') { setRinging(session); setError(null); return; }
      if (session.state === 'ended' || detail.event === 'ended' || detail.event === 'accepted') setRinging(previous => (previous?.session_id === session.session_id ? null : previous));
    };
    window.addEventListener(MEDIA_EVENT, onEvent);
    return () => window.removeEventListener(MEDIA_EVENT, onEvent);
  }, []);
  if (!ringing) return null;
  const caller = remoteParticipant(ringing);
  const name = caller?.user?.name || caller?.user?.id || '알 수 없는 상대';
  const accept = async () => {
    try { await openCallWindow(ringing.session_id); setRinging(null); }
    catch (e) { setError(e instanceof Error ? e.message : '통화 창을 열지 못했습니다.'); }
  };
  const reject = async () => {
    try { await sessions.reject(ringing.session_id, 'rejected'); } catch (e) { setError(e instanceof Error ? e.message : '거절을 보내지 못했습니다.'); return; }
    setRinging(null);
  };
  return (
    <div role="alertdialog" aria-label="수신 통화" className="fixed left-1/2 top-4 z-[1000] flex -translate-x-1/2 items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm shadow-xl">
      <div className="min-w-0">
        <div className="font-medium text-stone-800">{name}</div>
        <div className="text-xs text-stone-500">{ringing.purpose === 'video_call' ? '영상 통화 요청' : '음성 통화 요청'}{error ? ` · ${error}` : ''}</div>
      </div>
      <button className="flex items-center gap-1 rounded-full bg-red-600 px-3 py-1.5 text-white hover:bg-red-500" onClick={() => void reject()}><PhoneOff size={14} /> 거절</button>
      <button className="flex items-center gap-1 rounded-full bg-emerald-600 px-3 py-1.5 text-white hover:bg-emerald-500" onClick={() => void accept()}><Phone size={14} /> 수락</button>
    </div>
  );
}
