import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { api } from '../../lib/api';
import { bytesFrom64, message, newId, post } from './client';

type Poll = { state: string; reason: string; data: string; cursor: number; gap: boolean };
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
    let disposed = false, ready = false, closed = false, cursor = 0, sequence = 0;
    let pending = 0, chain = Promise.resolve();
    const close = () => api.request(endpoint, { method: 'DELETE', keepalive: true }).catch(() => {});
    const fail = (error: unknown) => {
      if (disposed || closed) return;
      closed = true; ready = false; setEnded(true); setStatus(message(error)); void close();
    };
    const send = (data: string) => {
      if (!ready || closed) return;
      if (pending + data.length > 65536) { fail(new Error('입력이 너무 많아 연결을 닫았습니다.')); return; }
      pending += data.length;
      // Serialize keystrokes. Never retry an ambiguous request (it may have run).
      chain = chain.then(async () => {
        for (let i = 0; i < data.length; i += 4096) {
          if (disposed || closed) return;
          await post(endpoint, { type: 'input', data: data.slice(i, i + 4096), sequence: ++sequence });
        }
        pending -= data.length;
      }).catch(fail);
    };
    const onData = term.onData(send);
    const observer = new ResizeObserver(() => {
      if (!host.current?.clientWidth || !host.current.clientHeight) return;
      fit.fit();
      if (ready && !closed) void post(endpoint, { type: 'resize', cols: term.cols, rows: term.rows }).catch(fail);
    });
    observer.observe(host.current);
    setEnded(false); setStatus('원격 셸 연결 중…');
    void (async () => {
      try {
        await post('/remote-pcs/terminals', { target: device, id, cols: term.cols, rows: term.rows });
        if (disposed) { await close(); return; }
        while (!disposed && !closed) {
          const state = await api.request<Poll>(`${endpoint}?cursor=${cursor}`);
          if (disposed) break;
          if (state.gap) term.writeln('\r\n[출력 버퍼를 초과한 구간이 있습니다.]');
          if (state.data) term.write(bytesFrom64(state.data));
          cursor = state.cursor;
          if (state.state === 'closed' && !state.data) {
            closed = true; ready = false; setStatus(`세션 종료 · ${state.reason}`); setEnded(true); break;
          }
          if (state.state === 'running' && !ready) { ready = true; setStatus('연결됨'); term.focus(); }
          await new Promise(resolve => setTimeout(resolve, state.data ? 30 : 120));
        }
      } catch (e) { fail(e); }
    })();
    const onUnload = () => { void close(); };
    window.addEventListener('pagehide', onUnload);
    return () => {
      disposed = true; ready = false; void close();
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
