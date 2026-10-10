/** PC registration belongs to the cockpit; tasks are requested through the central AI. */
import { useCallback, useEffect, useState } from 'react';
import { Usb, Loader2, Check, Trash2, ChevronDown, ChevronRight, Copy, FolderOpen, RefreshCw } from 'lucide-react';
import { api } from '../../lib/api';

type Registration = {
  state: 'active' | 'removal_pending' | 'removed';
  paused?: boolean;
  capabilities?: { os?: string; hostname?: string };
};
type PC = { alias: string; device_id: string; connected: boolean; revoked?: boolean; registration: Registration };
type USB = { folder: string; ready: boolean };
type PCList = { items: PC[]; usb: USB };

export function LimbSwitch() {
  const [open, setOpen] = useState(false);
  const [pcs, setPCs] = useState<PC[]>([]);
  const [usb, setUSB] = useState<USB | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.request<PCList>('/remote-pcs');
      setPCs(data.items);
      setUSB(data.usb);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '등록 PC 목록을 불러오지 못했습니다.');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!open) return;
    void load();
    const timer = window.setInterval(() => { void load(); }, 15000);
    return () => window.clearInterval(timer);
  }, [open, load]);

  const prepare = async () => {
    setBusy('usb'); setErr(null);
    try { setUSB(await api.request<USB>('/remote-pcs/usb', { method: 'POST' })); }
    catch (e) { setErr(e instanceof Error ? e.message : 'USB 폴더 준비 실패'); }
    finally { setBusy(null); }
  };
  const remove = async (pc: PC) => {
    setBusy(pc.device_id); setErr(null);
    try {
      await api.request('/remote-pcs/state', { method: 'POST', body: JSON.stringify({ target: pc.device_id, remove: true }) });
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : '등록 해제 실패'); }
    finally { setBusy(null); }
  };
  const revokeUSB = async () => {
    setBusy('usb'); setErr(null);
    try { setUSB(await api.request<USB>('/remote-pcs/usb/revoke', { method: 'POST' })); }
    catch (e) { setErr(e instanceof Error ? e.message : 'USB 등록 키 폐기 실패'); }
    finally { setBusy(null); }
  };
  const active = pcs.filter((pc) => !pc.revoked && pc.registration.state !== 'removed');
  const status = (pc: PC) => pc.registration.state === 'removal_pending'
    ? '해제 요청됨 · PC가 연결되면 헬퍼 제거'
    : pc.registration.paused ? '작업 중지됨' : pc.connected ? '연결됨' : '오프라인';

  return (
    <div className="rounded-lg border border-stone-200 bg-white/60 text-[12px]">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-stone-600 hover:text-stone-800">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Usb size={14} /><span className="font-medium">손발 (USB)</span>
        {active.length > 0 && <span className="ml-auto text-[11px] text-stone-400">{active.length}대 등록됨</span>}
      </button>
      {open && <div className="border-t border-stone-100 px-3 py-3">
        <p className="mb-2 text-[11px] leading-relaxed text-stone-500">
          아래 폴더를 통째로 USB에 복사하고, 대상 PC에서 맞는 헬퍼를 실행하세요. PC 이름은 그곳에서 정합니다.
          같은 USB로 여러 PC를 등록할 수 있고, 등록 후에는 USB를 빼도 됩니다.
        </p>
        <div className="rounded border border-stone-200 bg-stone-50 px-2.5 py-2 text-stone-600">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">USB에 복사할 공용 헬퍼 폴더</span>
            <button onClick={prepare} disabled={busy !== null} className="ml-auto rounded bg-stone-800 px-2 py-1 text-[11px] text-white disabled:opacity-50">
              {busy === 'usb' ? '준비 중…' : usb?.ready ? '폴더 갱신' : '폴더 준비'}
            </button>
          </div>
          {usb && <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 select-text break-all text-[11px]">{usb.folder}</code>
            <button title="경로 복사" onClick={async () => {
              try { await navigator.clipboard.writeText(usb.folder); setCopied(true); }
              catch { setErr('경로를 복사하지 못했습니다. 표시된 경로를 직접 복사하세요.'); }
            }} className="rounded border border-stone-200 p-1.5">{copied ? <Check size={13} /> : <Copy size={13} />}</button>
            {usb.ready && window.electron?.openPCManagerWindow && <button title="폴더 열기" onClick={async () => {
              try { await window.electron?.openPCManagerWindow(usb.folder); }
              catch { setErr('폴더를 열지 못했습니다. 표시된 경로를 확인하세요.'); }
            }} className="rounded border border-stone-200 p-1.5"><FolderOpen size={13} /></button>}
          </div>}
          <p className="mt-2 text-[11px] text-stone-500">Windows · Mac Intel · Mac Apple Silicon · Linux 실행파일과 연결 설정이 함께 들어 있습니다.</p>
          {usb && !usb.ready && <p className="mt-1 text-[11px] text-amber-700">폴더 준비를 누른 뒤 USB에 복사하세요.</p>}
        </div>
        <div className="mt-3 flex items-center gap-2 font-medium text-stone-700">
          등록된 PC
          <button title="목록 새로고침" onClick={() => void load()} disabled={loading} className="ml-auto p-1">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          </button>
        </div>
        {!active.length && <p className="py-2 text-[11px] text-stone-400">아직 등록된 PC가 없습니다. 대상 PC에서 등록하면 여기에 표시됩니다.</p>}
        <ul className="mt-1 space-y-1">
          {active.map((pc) => <li key={pc.device_id} className="flex items-center gap-2 rounded border border-stone-100 bg-white px-2 py-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${pc.connected && pc.registration.state === 'active' ? 'bg-emerald-500' : 'bg-stone-300'}`} />
            <div className="min-w-0 flex-1">
              <div className="break-all font-medium text-stone-700">{pc.alias}</div>
              <div className="text-[10px] text-stone-400">{status(pc)}{pc.registration.capabilities?.os ? ` · ${pc.registration.capabilities.os}` : ''}</div>
            </div>
            <button onClick={() => void remove(pc)} disabled={busy !== null || pc.registration.state !== 'active'}
              title="등록 해제 및 원격 헬퍼 제거" className="flex items-center gap-1 rounded border border-stone-200 px-2 py-1 text-[11px] text-stone-500 hover:text-red-600 disabled:opacity-50">
              {busy === pc.device_id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}해제
            </button>
          </li>)}
        </ul>
        <p className="mt-3 text-[11px] leading-relaxed text-stone-500">작업은 중앙 AI에게 “맥12에 음악 틀어줘”, “맥12에서 파일 가져와”처럼 부탁하세요. 해제하면 헬퍼와 자동 시작 설정이 제거되며 작업 파일은 남습니다.</p>
        <details className="mt-2 text-[11px] text-stone-400">
          <summary className="cursor-pointer">USB를 분실했을 때</summary>
          <p className="my-1">USB 등록 키를 폐기하면 그 USB로 새 PC를 등록할 수 없습니다. 이미 등록된 PC는 계속 연결됩니다. 새 USB는 폴더를 다시 준비해 복사하세요.</p>
          <button onClick={() => void revokeUSB()} disabled={busy !== null || !usb} className="rounded border border-stone-200 px-2 py-1 text-stone-500 disabled:opacity-50">USB 등록 키 폐기</button>
        </details>
        {err && <div role="alert" className="mt-2 rounded bg-red-50 px-2 py-1 text-[11px] text-red-600">{err}</div>}
      </div>}
    </div>
  );
}
