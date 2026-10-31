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
  const [textEntry, setTextEntry] = useState(false);
  const [text, setText] = useState('');
  const [textError, setTextError] = useState('');
  const composing = useRef(false);
  const frameCounter = useRef(0);
  function send(value: object) {
    if (socket.current?.readyState !== WebSocket.OPEN || socket.current.bufferedAmount >= 65536) return false;
    socket.current.send(JSON.stringify(value));
    return true;
  }
  useEffect(() => {
    const sid = crypto.randomUUID().replaceAll('-', '');
    let disposed = false, ended = false, ws: WebSocket | undefined;
    let generation = 0, reconnectMs = 0, disconnectedAt = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    setReady(false); setState('연결 중…');
    const closeSession = () => {
      ended = true; clearTimeout(retry); ++frameCounter.current;
      ws?.close();
      void fetch(`${BACKEND_ORIGIN}/remote-pcs/screens/${sid}`, { method: 'DELETE', keepalive: true }).catch(() => {});
    };
    const connect = () => {
      if (disposed || ended) return;
      const token = ++generation;
      const current = new WebSocket(`${WEBSOCKET_ORIGIN}/remote-pcs/screens/${sid}/stream?connection=${token}`);
      ws = current; socket.current = current;
      current.onmessage = event => {
        if (disposed || ended || token !== generation) return;
        if (typeof event.data === 'string') {
          const message = JSON.parse(event.data);
          if (message.type === 'status') {
            if (message.state === 'closed') { ended = true; clearTimeout(retry); }
            if (message.state !== 'running') {
              ++frameCounter.current; setReady(false);
              setState(message.message || (message.state === 'reconnecting' ? '연결을 복구하고 있습니다…' : '연결 중…'));
            }
          }
          return;
        }
        const seq = ++frameCounter.current;
        void createImageBitmap(event.data).then(bitmap => {
          if (!disposed && !ended && token === generation && seq === frameCounter.current && canvas.current) {
            const target = canvas.current;
            if (target.width !== bitmap.width || target.height !== bitmap.height) { target.width = bitmap.width; target.height = bitmap.height; }
            target.getContext('2d')?.drawImage(bitmap, 0, 0);
            disconnectedAt = 0; setReady(true); setState('');
          }
          bitmap.close();
        }).catch(() => { if (!disposed && !ended && token === generation && seq === frameCounter.current) { setReady(false); setState('화면을 불러오지 못했습니다.'); } });
      };
      current.onclose = () => {
        if (disposed || token !== generation) return;
        ++frameCounter.current; setReady(false);
        if (ended) return;
        disconnectedAt ||= Date.now();
        if (reconnectMs > 0 && Date.now() - disconnectedAt < reconnectMs) {
          setState('연결을 복구하고 있습니다…'); retry = setTimeout(connect, 500);
        } else { ended = true; setState('연결이 종료됐습니다. 다시 연결하세요.'); }
      };
      current.onerror = () => { if (!disposed && !ended && token === generation) setState('연결을 복구하고 있습니다…'); };
    };
    void api.request<{ device_kind: string; reconnect_s?: number }>('/remote-pcs/screens', {
      method: 'POST', body: JSON.stringify({ target: device, id: sid, reconnect: true }),
    }).then(result => {
      if (disposed) { closeSession(); return; }
      setPhone(result.device_kind === 'phone'); reconnectMs = (result.reconnect_s || 0) * 1000;
      connect();
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
    if (event.type === 'pointerdown') {
      // Touch/pen selects the remote screen without opening the local software keyboard.
      if (event.pointerType === 'mouse') keyboard.current?.focus({ preventScroll: true });
      else event.currentTarget.focus({ preventScroll: true });
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    send({ type: 'pointer', ...position(event), buttons: event.buttons & 7 });
  }
  function key(event: React.KeyboardEvent, down: boolean) {
    if (!ready || composing.current || event.nativeEvent.isComposing) return;
    if ((event.metaKey || event.ctrlKey) && event.code === 'KeyV') return;
    if (phone && (event.metaKey || event.ctrlKey || event.altKey)) { event.preventDefault(); return; }
    event.preventDefault();
    send({ type: 'key', code: event.code, key: event.key, down });
  }
  function sendText(event: React.FormEvent) {
    event.preventDefault();
    if (!ready || !text) return;
    if (new TextEncoder().encode(text).length > 16384) {
      setTextError('입력할 글이 너무 깁니다. 나누어 보내 주세요.');
      return;
    }
    send({ type: 'reset' });
    if (!send({ type: 'text', text })) {
      setTextError('연결이 원활하지 않습니다. 잠시 뒤 다시 보내 주세요.');
      return;
    }
    setText(''); setTextError('');
  }
  return <main className="flex h-screen flex-col bg-stone-950 text-white">
    <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-white/10 px-4 py-2 text-sm">
      <strong className="flex-1">화면 공유</strong>
      {phone && <nav className="flex gap-3" aria-label="폰 탐색">
        {(['back', 'home', 'recents'] as const).map((action, i) => <button key={action} disabled={!ready} onClick={() => send({ type: 'navigation', action })}>{['뒤로', '홈', '최근 앱'][i]}</button>)}
      </nav>}
      <button disabled={!ready} aria-expanded={textEntry} aria-controls="screen-text-entry" onClick={() => setTextEntry(open => !open)}>문자 입력</button>
      <button onClick={() => void document.documentElement.requestFullscreen().catch(() => {})}>전체 화면</button>
      <button onClick={() => window.close()}>닫기</button>
    </header>
    {textEntry && <form id="screen-text-entry" onSubmit={sendText} className="flex shrink-0 flex-wrap items-center gap-2 border-b border-white/10 px-4 py-2">
      <textarea aria-label="보낼 글" value={text} onChange={event => { setText(event.target.value); setTextError(''); }}
        rows={2} placeholder="원격 화면에서 입력할 곳을 선택한 뒤 글을 보내세요."
        className="min-w-0 flex-1 rounded border border-white/30 bg-stone-900 p-2 text-base" />
      <button type="submit" disabled={!ready || !text} className="rounded border border-white/30 px-3 py-2 disabled:opacity-50">보내기</button>
      {textError && <p role="alert" className="w-full text-sm text-amber-300">{textError}</p>}
    </form>}
    <section className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
      <canvas ref={canvas} tabIndex={0} aria-label="원격 기기 화면" className="max-h-full max-w-full touch-none object-contain"
        onKeyDown={event => key(event, true)} onKeyUp={event => key(event, false)}
        onPointerDown={pointer} onPointerUp={pointer} onPointerMove={pointer} onPointerCancel={() => send({ type: 'reset' })}
        onContextMenu={event => event.preventDefault()} onWheel={event => { if (ready) send({ type: 'wheel', ...position(event), dx: Math.max(-2000, Math.min(2000, event.deltaX)), dy: Math.max(-2000, Math.min(2000, event.deltaY)) }); }} />
      <textarea ref={keyboard} tabIndex={-1} aria-label="원격 키보드 입력" className="absolute left-0 top-0 h-px w-px opacity-0" autoCapitalize="off" autoCorrect="off" spellCheck={false}
        onKeyDown={event => key(event, true)} onKeyUp={event => key(event, false)}
        onCompositionStart={() => { composing.current = true; send({ type: 'reset' }); }}
        onCompositionEnd={event => { composing.current = false; if (ready) send({ type: 'text', text: event.data }); event.currentTarget.value = ''; }}
        onPaste={event => { event.preventDefault(); const text = event.clipboardData.getData('text/plain'); if (ready && new TextEncoder().encode(text).length <= 16384) { send({ type: 'reset' }); send({ type: 'text', text }); } }} />
      {state && <div role="status" className="absolute rounded bg-stone-900/95 px-5 py-4 text-center"><p>{state}</p>{state !== '연결 중…' && <button className="mt-3 rounded border border-white/30 px-3 py-1" onClick={() => setAttempt(value => value + 1)}>다시 연결</button>}</div>}
    </section>
  </main>;
}
