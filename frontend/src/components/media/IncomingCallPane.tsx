/** Callee view while ringing: who is calling, what they ask for, accept/reject. Sensors stay off until accept. */
import { Phone, PhoneOff, Mic, Video } from 'lucide-react';
import type { MediaSession } from '../../lib/media/types';
import { remoteParticipant } from '../../lib/media/session-client';

export function IncomingCallPane({ session, busy, onAccept, onReject }: {
  session: MediaSession; busy: boolean; onAccept: () => void; onReject: () => void;
}) {
  const caller = remoteParticipant(session);
  const wantsCamera = session.purpose === 'video_call' || session.tracks?.some(t => t.kind === 'video' && t.to !== 'caller' && t.state !== 'rejected');
  const wantsMic = session.purpose !== 'camera';
  return (
    <section aria-label="수신 통화" className="flex flex-1 flex-col items-center justify-center gap-5 text-center text-white">
      <div className="flex h-24 w-24 items-center justify-center rounded-full bg-stone-800 text-3xl">
        {(caller?.user?.name || caller?.user?.id || '?').slice(0, 1).toUpperCase()}
      </div>
      <div>
        <p className="text-lg font-semibold">{caller?.user?.name || caller?.user?.id || '알 수 없는 상대'}</p>
        <p className="text-sm text-stone-400">{session.purpose === 'video_call' ? '영상 통화 요청' : '음성 통화 요청'}</p>
        {caller?.device?.name && <p className="mt-1 text-xs text-stone-500">장치: {caller.device.name}</p>}
      </div>
      <ul className="flex gap-3 text-xs text-stone-300">
        {wantsMic && <li className="flex items-center gap-1 rounded-full border border-white/20 px-3 py-1"><Mic size={12} /> 마이크 사용</li>}
        {wantsCamera && <li className="flex items-center gap-1 rounded-full border border-white/20 px-3 py-1"><Video size={12} /> 카메라 사용</li>}
      </ul>
      <p className="text-xs text-stone-500">수락하기 전에는 카메라·마이크를 켜지 않습니다.</p>
      <div className="flex gap-4">
        <button disabled={busy} onClick={onReject} className="flex items-center gap-2 rounded-full bg-red-600 px-5 py-3 hover:bg-red-500 disabled:opacity-50">
          <PhoneOff size={18} /> 거절
        </button>
        <button disabled={busy} onClick={onAccept} className="flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-3 hover:bg-emerald-500 disabled:opacity-50">
          <Phone size={18} /> 수락
        </button>
      </div>
    </section>
  );
}
