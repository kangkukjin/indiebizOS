import { useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import { BACKEND_ORIGIN, WEBSOCKET_ORIGIN } from '../../lib/backend-origin';

export function ScreenShare({ device }: { device: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const keyboard = useRef<HTMLTextAreaElement>(null);
  const socket = useRef<WebSocket | null>(null);
  const [state, setState] = useState('연결 중…');
  const [phone, setPhone] = useState(false);
  const [ready, setReady] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const composing = useRef(false);
  const frameCounter = useRef(0);
  function send(value: object) {
    if (socket.current?.readyState === WebSocket.OPEN && socket.current.bufferedAmount < 65536) socket.current.send(JSON.stringify(value));
  }
  useEffect(() => {
    const sid = crypto.randomUUID().replaceAll('-', '');
    let disposed = false, ended = false, ws: WebSocket | undefined;
    setReady(false); setState('연결 중…');
    const closeSession = () => {
      ws?.close();
      void fetch(`${BACKEND_ORIGIN}/remote-pcs/screens/${sid}`, { method: 'DELETE', keepalive: true }).catch(() => {});
    };
    void Promise.resolve().then(() => {
      if (disposed) return;
      return api.request<{ device_kind: string }>('/remote-pcs/screens', { method: 'POST', body: JSON.stringify({ target: device, id: sid }) });
    }).then(result => {
      setPhone(result?.device_kind === 'phone');
      if (disposed) { closeSession(); return; }
      ws = new WebSocket(`${WEBSOCKET_ORIGIN}/remote-pcs/screens/${sid}/stream`);
      socket.current = ws;
      ws.onmessage = event => {
        if (typeof event.data === 'string') {
          const message = JSON.parse(event.data);
          if (message.type === 'status') {
            if (message.state === 'closed') ended = true;
            setReady(message.state === 'running');
            setState(message.state === 'running' ? '' : message.message || '연결 중…');
          }
          return;
        }
        const seq = ++frameCounter.current;
        void createImageBitmap(event.data).then(bitmap => {
          if (!disposed && !ended && seq === frameCounter.current && canvas.current) {
            const target = canvas.current;
            if (target.width !== bitmap.width || target.height !== bitmap.height) { target.width = bitmap.width; target.height = bitmap.height; }
            target.getContext('2d')?.drawImage(bitmap, 0, 0);
            setReady(true); setState('');
          }
          bitmap.close();
        }).catch(() => { if (!disposed && !ended) { setReady(false); setState('화면을 불러오지 못했습니다.'); } });
      };
      ws.onclose = () => { ended = true; if (!disposed) { setReady(false); setState(previous => previous || '연결이 종료됐습니다.'); } };
      ws.onerror = () => { if (!disposed) setState('화면 공유에 연결하지 못했습니다.'); };
    }).catch(error => { if (!disposed) setState(error instanceof Error ? error.message : '화면 공유에 연결하지 못했습니다.'); });
    const blur = () => send({ type: 'reset' });
    window.addEventListener('blur', blur);
    window.addEventListener('pagehide', closeSession);
    return () => { disposed = true; blur(); closeSession(); socket.current = null; window.removeEventListener('blur', blur); window.removeEventListener('pagehide', closeSession); };
  }, [device, attempt]);
  function position(event: { clientX: number; clientY: number }) {
    const rect = canvas.current!.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
  }
  function pointer(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!ready) return;
    if (phone && event.type === 'pointermove' && !event.buttons) return;
    event.preventDefault();
    if (event.type === 'pointerdown') { keyboard.current?.focus(); event.currentTarget.setPointerCapture(event.pointerId); }
    send({ type: 'pointer', ...position(event), buttons: event.buttons & 7 });
  }
  function key(event: React.KeyboardEvent, down: boolean) {
    if (!ready || composing.current || event.nativeEvent.isComposing) return;
    if ((event.metaKey || event.ctrlKey) && event.code === 'KeyV') return;
    if (phone && (event.metaKey || event.ctrlKey || event.altKey)) { event.preventDefault(); return; }
    event.preventDefault();
    send({ type: 'key', code: event.code, key: event.key, down });
  }
  return <main className="flex h-screen flex-col bg-stone-950 text-white">
    <header className="flex shrink-0 items-center gap-3 border-b border-white/10 px-4 py-2 text-sm">
      <strong className="flex-1">화면 공유</strong>
      {phone && <nav className="flex gap-3" aria-label="폰 탐색">
        {(['back', 'home', 'recents'] as const).map((action, i) => <button key={action} disabled={!ready} onClick={() => send({ type: 'navigation', action })}>{['뒤로', '홈', '최근 앱'][i]}</button>)}
      </nav>}
      <button onClick={() => void document.documentElement.requestFullscreen().catch(() => {})}>전체 화면</button>
      <button onClick={() => window.close()}>닫기</button>
    </header>
    <section className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
      <canvas ref={canvas} aria-label="원격 기기 화면" className="max-h-full max-w-full touch-none object-contain"
        onPointerDown={pointer} onPointerUp={pointer} onPointerMove={pointer} onPointerCancel={() => send({ type: 'reset' })}
        onContextMenu={event => event.preventDefault()} onWheel={event => { if (ready) send({ type: 'wheel', ...position(event), dx: Math.max(-2000, Math.min(2000, event.deltaX)), dy: Math.max(-2000, Math.min(2000, event.deltaY)) }); }} />
      <textarea ref={keyboard} aria-label="원격 키보드 입력" className="absolute left-0 top-0 h-px w-px opacity-0" autoCapitalize="off" autoCorrect="off" spellCheck={false}
        onKeyDown={event => key(event, true)} onKeyUp={event => key(event, false)}
        onCompositionStart={() => { composing.current = true; send({ type: 'reset' }); }}
        onCompositionEnd={event => { composing.current = false; if (ready) send({ type: 'text', text: event.data }); event.currentTarget.value = ''; }}
        onPaste={event => { event.preventDefault(); const text = event.clipboardData.getData('text/plain'); if (ready && new TextEncoder().encode(text).length <= 16384) { send({ type: 'reset' }); send({ type: 'text', text }); } }} />
      {state && <div role="status" className="absolute rounded bg-stone-900/95 px-5 py-4 text-center"><p>{state}</p>{state !== '연결 중…' && <button className="mt-3 rounded border border-white/30 px-3 py-1" onClick={() => setAttempt(value => value + 1)}>다시 연결</button>}</div>}
    </section>
  </main>;
}
