import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { api } from '../../lib/api';
import { WEBSOCKET_ORIGIN } from '../../lib/backend-origin';
import { bytesFrom64, message, newId, post } from './client';

type Poll = { state: string; reason: string; data: string; cursor: number; gap: boolean; route?: string };
export function RemoteTerminal({ device, supported }: { device: string; supported: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const [generation, setGeneration] = useState(0);
  const [status, setStatus] = useState('연결 준비');
  const [ended, setEnded] = useState(false);
  useEffect(() => {
    if (!host.current || !supported) return;
    const term = new Terminal({ cursorBlink: true, fontSize: 14, fontFamily: 'Menlo, Consolas, monospace', scrollback: 5000, theme: { background: '#10151d', foreground: '#d9e2ef' } });
    const fit = new FitAddon(); term.loadAddon(fit); term.open(host.current); fit.fit();
    const id = newId(), endpoint = `/remote-pcs/terminals/${id}`;
    let disposed = false, ready = false, closed = false, sequence = 0;
    let socket: WebSocket | undefined;
    let lastMessage = Date.now();
    const close = () => api.request(endpoint, { method: 'DELETE', keepalive: true }).catch(() => {});
    const fail = (error: unknown) => {
      if (disposed || closed) return;
      closed = true; ready = false; socket?.close(); setEnded(true); setStatus(message(error)); void close();
    };
    const sendMessage = (value: object) => {
      if (!ready || closed || socket?.readyState !== WebSocket.OPEN) return;
      if (socket.bufferedAmount > 65536) { fail(new Error('입력이 너무 많아 연결을 닫았습니다.')); return; }
      socket.send(JSON.stringify(value));
    };
    const send = (data: string) => {
      if (!ready || closed) return;
      // One ordered socket; keystrokes never wait for an HTTP round trip or replay.
      for (let i = 0; i < data.length;) {
        let end = Math.min(i + 4096, data.length);
        if (end < data.length && /[\uD800-\uDBFF]/.test(data[end - 1])) end--;
        sendMessage({ type: 'input', data: data.slice(i, end), sequence: ++sequence });
        i = end;
      }
    };
    const onData = term.onData(send);
    const observer = new ResizeObserver(() => {
      if (!host.current?.clientWidth || !host.current.clientHeight) return;
      fit.fit();
      sendMessage({ type: 'resize', cols: term.cols, rows: term.rows });
    });
    observer.observe(host.current);
    setEnded(false); setStatus('원격 셸 연결 중…');
    void (async () => {
      try {
        await post('/remote-pcs/terminals', { target: device, id, cols: term.cols, rows: term.rows });
        if (disposed) { await close(); return; }
        socket = new WebSocket(`${WEBSOCKET_ORIGIN}${endpoint}/stream`);
        socket.onmessage = event => {
          if (disposed || closed) return;
          try {
            lastMessage = Date.now();
            const state: Poll = JSON.parse(event.data);
            if (state.gap) term.writeln('\r\n[출력 버퍼를 초과한 구간이 있습니다.]');
            if (state.data) term.write(bytesFrom64(state.data));
            if (state.state === 'closed' && !state.data) {
              closed = true; ready = false; setStatus(`세션 종료 · ${state.reason}`); setEnded(true); socket?.close(); return;
            }
            if (state.state === 'running') {
              if (!ready) { ready = true; term.focus(); }
              setStatus(state.route === 'lan' ? '연결됨 · 내부망 직결' : '연결됨 · 외부 터널');
            }
          } catch (e) { fail(e); }
        };
        socket.onerror = () => fail(new Error('터미널 연결 오류 · 새 터미널을 연결하세요.'));
        socket.onclose = () => fail(new Error('터미널 연결이 종료되었습니다.'));
      } catch (e) { fail(e); }
    })();
    const watchdog = window.setInterval(() => {
      if (Date.now() - lastMessage > 30000) fail(new Error('터미널 응답이 끊겼습니다.'));
    }, 5000);
    const onUnload = () => { void close(); };
    window.addEventListener('pagehide', onUnload);
    return () => {
      disposed = true; ready = false; socket?.close(); window.clearInterval(watchdog); void close();
      window.removeEventListener('pagehide', onUnload);
      observer.disconnect(); onData.dispose(); term.dispose();
    };
  }, [device, supported, generation]);
  return <div className="flex h-full min-h-0 flex-col bg-[#10151d]">
    <div className="flex items-center gap-3 px-4 py-2 text-xs text-slate-300">
      <span role="status">{supported ? status : '이 PC의 헬퍼를 교체하면 터미널을 사용할 수 있습니다.'}</span>
      {ended && <button className="rounded border border-slate-500 px-2 py-1" onClick={() => setGeneration(v => v + 1)}>새 터미널 연결</button>}
      <span className="ml-auto text-slate-400">창을 닫으면 셸이 종료됩니다.</span>
    </div>
    <div ref={host} aria-label="원격 터미널" className="min-h-0 flex-1 px-3 pb-3" />
  </div>;
}
