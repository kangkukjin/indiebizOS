import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Monitor, X } from 'lucide-react';
import { api } from '../../lib/api';
import { message } from './client';

type Profile = { direct_host: string; tunnel_host: string; port: number };
export function RemoteDesktop({ device, alias, onClose }: { device: string; alias: string; onClose: () => void }) {
  const [profile, setProfile] = useState<Profile>({ direct_host: '', tunnel_host: '', port: 5900 });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const endpoint = `/remote-pcs/desktop/${encodeURIComponent(device)}`;
  useEffect(() => {
    const controller = new AbortController();
    void api.request<Profile>(endpoint, { signal: controller.signal }).then(value => {
      setProfile(value); setReady(true);
    }).catch(e => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [endpoint]);
  async function save(open?: 'auto' | 'tunnel') {
    setBusy(true); setError(''); setStatus('');
    try {
      await api.request(endpoint, { method: 'PUT', body: JSON.stringify(profile) });
      if (open) {
        if (!window.electron?.openRemoteDesktop) throw new Error('Mac의 IndieBiz OS 앱을 다시 연 뒤 연결하세요. 웹 브라우저에서는 접속 주소 저장만 할 수 있습니다.');
        const result = await window.electron.openRemoteDesktop(device, open);
        setStatus(result.route === 'direct' ? '내부망으로 화면 공유 앱을 열었습니다. 대상 Mac 계정으로 로그인하세요.' : 'Cloudflare를 통해 화면 공유 앱을 열었습니다. 대상 Mac 계정으로 로그인하세요.');
      } else setStatus('접속 주소를 저장했습니다.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  return createPortal(<div className="fixed inset-0 z-[210] flex items-center justify-center bg-black/50 p-4">
    <section role="dialog" aria-modal="true" aria-label="화면 공유" className="w-full max-w-lg rounded-xl border border-stone-300 bg-white p-5 shadow-2xl">
      <header className="mb-4 flex items-center gap-2"><Monitor size={20} /><strong className="min-w-0 flex-1 truncate">{alias} · 화면 공유</strong><button aria-label="화면 공유 설정 닫기" onClick={onClose}><X size={20} /></button></header>
      <p className="mb-4 text-sm text-stone-600">대상 Mac의 화면과 마우스·키보드를 직접 조작합니다. 대상 PC에서 화면 공유가 켜져 있어야 합니다.</p>
      <form onSubmit={event => { event.preventDefault(); void save('auto'); }} className="space-y-3">
        <label className="block text-sm">내부망 주소
          <input value={profile.direct_host} onChange={e => setProfile({ ...profile, direct_host: e.target.value })} disabled={!ready || busy} placeholder="macbook.local" className="mt-1 block w-full rounded border p-2" autoComplete="off" />
        </label>
        <label className="block text-sm">Cloudflare 호스트 이름
          <input value={profile.tunnel_host} onChange={e => setProfile({ ...profile, tunnel_host: e.target.value })} disabled={!ready || busy} placeholder="remote.example.com" className="mt-1 block w-full rounded border p-2" autoComplete="off" />
        </label>
        <label className="block text-sm">화면 공유 포트
          <input type="number" min={1} max={65535} value={profile.port} onChange={e => setProfile({ ...profile, port: Number(e.target.value) })} disabled={!ready || busy} className="mt-1 block w-28 rounded border p-2" />
        </label>
        <p className="text-xs leading-relaxed text-stone-500">내부망에 연결되지 않으면 Cloudflare 터널을 사용합니다. 터널은 대상 PC의 화면 공유 포트로 연결되어 있어야 하며, 접속하는 Mac에는 cloudflared가 필요합니다. 계정과 비밀번호는 화면 공유 앱에 입력하세요.</p>
        <div className="flex flex-wrap gap-2 pt-2">
          <button type="submit" disabled={!ready || busy || (!profile.direct_host && !profile.tunnel_host)} className="rounded bg-stone-800 px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '연결 처리 중…' : '화면 공유 열기'}</button>
          <button type="button" disabled={!ready || busy || !profile.tunnel_host} onClick={() => void save('tunnel')} className="rounded border px-3 py-2 text-sm disabled:opacity-50">외부 터널로 연결</button>
          <button type="button" disabled={!ready || busy} onClick={() => void save()} className="rounded border px-3 py-2 text-sm disabled:opacity-50">주소 저장</button>
        </div>
      </form>
      {status && <p role="status" className="mt-3 text-sm text-emerald-700">{status}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <p className="mt-4 text-xs text-stone-500">이 설정창을 닫아도 화면 공유는 유지됩니다. IndieBiz OS 앱을 종료하면 이 앱이 연 Cloudflare 연결도 종료됩니다.</p>
    </section>
  </div>, document.body);
}
