import {useEffect, useRef, useState} from 'react';
import {createChatVoice} from '../../../surfaces/shared/chat-voice.js';
import {sessionCall, type SessionTarget} from './useConversationSession';

export function VoiceConversation({sid, target}: {sid: string; target: SessionTarget}) {
  const current = useRef<ReturnType<typeof createChatVoice> | null>(null);
  const [phase,setPhase] = useState('off');
  const [notice,setNotice] = useState('');
  useEffect(() => () => {
    const voice = current.current;
    current.current = null;
    voice?.stop();
  }, [sid, target]);
  function toggle() {
    if (current.current) { current.current.stop(); return; }
    const call = createChatVoice(
      (path: string, method: string, body: Record<string,string>) => sessionCall(
        '/' + encodeURIComponent(sid) + path, method === 'GET' ? {...target,...body} : target, method, body),
      (next: string, message: string) => {
        if (current.current !== call) return;
        if (next === 'off') current.current = null;
        setPhase(next); setNotice(message);
      });
    current.current = call;
    void call.start();
  }
  return <div className="flex flex-wrap items-center gap-2 px-3 py-1">
    <button type="button" aria-pressed={phase !== 'off'} onClick={toggle}
      className="rounded-lg border border-stone-300 px-3 py-1 text-sm hover:bg-amber-50">
      {phase === 'off' ? '음성대화 시작' : phase === 'starting' ? '연결 취소' : '음성대화 종료'}
    </button>
    {notice && <span role="status" className="text-sm text-red-700">{notice}</span>}
  </div>;
}
