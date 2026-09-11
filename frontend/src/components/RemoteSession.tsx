import { useCallback, useEffect, useRef, useState, type ReactNode, type FormEvent } from 'react';
import { useAppStore } from '../stores/appStore';
import { SESSION_EXPIRED } from '../lib/remote-session';
import { iblExecuteApp } from '../lib/instrument';
import { ArrowLeft, Home, MoreHorizontal } from 'lucide-react';
import '../remote-mobile.css';

/** 원격 소유자 셸. 인증되기 전에는 데이터/소켓을 여는 App 자체를 마운트하지 않는다. */
export function RemoteSession({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'checking' | 'login' | 'ready' | 'error'>('checking');
  const [external, setExternal] = useState(true);
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [clipboard, setClipboard] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const check = useCallback(async () => {
    try {
      const res = await fetch('/launcher/auth/session', { cache: 'no-store' });
      if (!res.ok) throw new Error('접속 상태를 확인하지 못했습니다.');
      const data = await res.json();
      setExternal(data.external);
      setState(data.authenticated ? 'ready' : 'login');
    } catch (e) { setMessage(String(e)); setState(current => current === 'ready' ? current : 'error'); }
  }, []);
  useEffect(() => {
    void check();
    const expired = () => { setState('login'); setMessage('세션이 끝났습니다. 다시 로그인해주세요.'); };
    window.addEventListener(SESSION_EXPIRED, expired);
    if ('serviceWorker' in navigator) {
      void navigator.serviceWorker.register('/launcher/sw.js').catch(() => {});
    }
    return () => window.removeEventListener(SESSION_EXPIRED, expired);
  }, [check]);
  // 조용한 창에서도 회수된 세션의 내용을 오래 표시하지 않는다.
  useEffect(() => {
    if (state !== 'ready' || !external) return;
    const timer = window.setInterval(() => void check(), 30000);
    return () => window.clearInterval(timer);
  }, [state, external, check]);

  // iOS는 키보드가 떠도 레이아웃 뷰포트를 줄이지 않는다. 실제 보이는 높이에 맞춘다.
  useEffect(() => {
    const viewport = window.visualViewport;
    const shell = shellRef.current;
    if (state !== 'ready' || !viewport || !shell) return;
    const resize = () => {
      if (viewport.scale === 1) shell.style.setProperty('--remote-viewport-height', `${viewport.height}px`);
    };
    resize();
    viewport.addEventListener('resize', resize);
    return () => viewport.removeEventListener('resize', resize);
  }, [state]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const res = await fetch('/launcher/auth/login', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '로그인하지 못했습니다.');
      setPassword(''); await check();
    } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function logout() {
    setBusy(true);
    try {
      const res = await fetch('/launcher/auth/logout', { method: 'POST' });
      if (!res.ok) throw new Error('로그아웃하지 못했습니다. 다시 시도해주세요.');
      // 남은 컴포넌트/메모리도 버린다. 진행 중 승인 작업은 서버의 기존 수명 계약을 따른다.
      window.location.reload();
    } catch (e) { setMessage(String(e)); setBusy(false); }
  }

  async function sendClipboard() {
    if (!clipboard) return;
    setBusy(true); setMessage('');
    try {
      const result = await iblExecuteApp(`[self:output]{op:"clipboard",content:${JSON.stringify(clipboard)}}`) as { copied_length?: number; ok?: boolean; error?: string };
      if (!(result?.copied_length || result?.ok)) throw new Error(result?.error || '전송하지 못했습니다.');
      setClipboard(null); setMessage('PC 클립보드에 보냈습니다.');
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  }

  if (state !== 'ready') return (
    <main className="min-h-dvh bg-[#F5F1EB] flex items-center justify-center p-5">
      <form onSubmit={login} className="w-full max-w-sm rounded-2xl bg-white shadow p-7 space-y-4">
        <h1 className="text-2xl font-semibold">IndieBiz OS</h1>
        <p className="text-sm text-stone-600">{state === 'checking' ? '접속 확인 중…' : '내 시스템에 연결합니다.'}</p>
        {state === 'login' && <>
          <label className="block text-sm">비밀번호
            <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
              required className="mt-2 w-full rounded-lg border p-3" />
          </label>
          <button disabled={busy} className="w-full rounded-lg bg-amber-600 text-white p-3 disabled:opacity-50">로그인</button>
        </>}
        {message && <p role="status" className="text-sm text-stone-700 break-words">{message}</p>}
        {state === 'error' && <button type="button" onClick={() => void check()} className="underline">다시 시도</button>}
        <a href="/launcher/lite" className="block text-sm text-stone-500 underline">경량 화면 열기</a>
      </form>
    </main>
  );

  return <div ref={shellRef} className="remote-shell h-dvh flex flex-col overflow-hidden bg-[#F5F1EB]">
    <header className="remote-session-bar shrink-0 flex gap-3 items-center border-b px-3 py-2 text-sm bg-white">
      <button onClick={() => { useAppStore.getState().setCurrentView('launcher'); window.location.hash = '/'; }} className="font-semibold flex items-center gap-2"><Home size={17} /> IndieBiz 홈</button>
      <button onClick={() => window.history.back()} className="flex items-center gap-1"><ArrowLeft size={17} /> 뒤로</button>
      <button onClick={() => setMenuOpen(v => !v)} aria-expanded={menuOpen} aria-controls="remote-session-menu" className="ml-auto flex items-center gap-1"><MoreHorizontal size={20} /> 접속 메뉴</button>
    </header>
    {menuOpen && <div id="remote-session-menu" className="remote-session-menu shrink-0 flex flex-wrap gap-3 px-3 py-2 bg-white border-b text-sm">
      <button onClick={() => { setClipboard(''); setMessage(''); setMenuOpen(false); }}>PC로 보내기</button>
      <a href="/launcher/lite" className="text-stone-500">구형 기기용 경량 화면</a>
      {external && <button disabled={busy} onClick={() => void logout()}>로그아웃</button>}
    </div>}
    {message && <p role="status" className="px-3 py-1 text-sm">{message}</p>}
    {clipboard !== null && <div className="shrink-0 p-3 bg-white space-y-2">
      <label className="text-sm block">PC 클립보드로 보낼 내용
        <textarea value={clipboard} onChange={e => setClipboard(e.target.value)} className="block border rounded w-full p-2" rows={3} />
      </label>
      <div className="flex gap-4 text-sm">
        <button disabled={busy || !clipboard} onClick={() => void sendClipboard()}>보내기</button>
        <button onClick={() => setClipboard(null)}>닫기</button>
      </div>
    </div>}
    <div className="remote-content flex-1 min-h-0 overflow-hidden">{children}</div>
  </div>;
}
