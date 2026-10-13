import { useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import { sessions } from '../../lib/media/session-client';
import { handoff } from '../../lib/media/handoff';
import { openCallWindow } from './CallButtons';

export function PlaybackHandoff() {
  const anchor = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const [devices, setDevices] = useState<{ device_id: string; alias: string }[] | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => () => abort.current?.abort(), []);
  const load = async () => {
    try { const r = await api.request<{ items: { device_id: string; alias: string }[] }>('/remote-pcs'); setDevices(r.items); }
    catch { setMessage('확장 장치 목록을 읽지 못했습니다.'); }
  };
  const move = async (target: string) => {
    const player = anchor.current?.parentElement?.querySelector('audio,video') as HTMLMediaElement | null;
    if (!player) return;
    setBusy(true); setMessage('장치 재생을 확인하고 있습니다…');
    abort.current = new AbortController();
    try {
      const s = await handoff(player, target, sessions, { signal: abort.current.signal });
      setMessage('재생을 옮겼습니다.'); await openCallWindow(s.session_id);
    } catch (e) { setMessage(e instanceof Error ? e.message : '재생 이동 실패'); }
    finally { setBusy(false); }
  };
  return <div ref={anchor} className="mt-2 text-xs text-stone-500">
    {!devices ? <button onClick={() => void load()}>다른 장치에서 이어 듣기</button> :
      <select disabled={busy} value="" aria-label="재생할 확장 장치" onChange={e => void move(e.target.value)}>
        <option value="">{devices.length ? '재생할 장치를 선택하세요' : '등록된 확장 장치가 없습니다'}</option>
        {devices.map(d => <option key={d.device_id} value={d.device_id}>{d.alias || d.device_id}</option>)}
      </select>}
    {busy && <button onClick={() => abort.current?.abort()} className="ml-2">취소</button>}
    {message && <p role="status">{message}</p>}
  </div>;
}
