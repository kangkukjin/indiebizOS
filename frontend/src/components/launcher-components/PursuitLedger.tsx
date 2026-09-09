import { useCallback, useEffect, useState } from 'react';
import { BookOpen, ChevronDown, ChevronRight, Loader2, RefreshCw } from 'lucide-react';
import { api } from '../../lib/api';

type Pursuit = {
  id: string; agent_key: string; title: string; status: string; version: number;
  goal_criteria: string; framing: string; progress: string; next: string;
  assumptions: { text: string; status: string; evidence: string }[];
  open_questions: string[]; artifacts: string[];
};
type Detail = {
  pursuit: Pursuit;
  pending_turns: { task_id: string; state: string; response: string }[];
  events: { id: number; kind: string; payload: unknown }[];
};
const labels: Record<string, string> = { active: '진행 중', parked: '보류', done: '완료', abandoned: '보관' };

export function PursuitLedger() {
  const [open, setOpen] = useState(false);
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<Pursuit[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const result = await api.request<{ items: Pursuit[]; total: number }>(
        `/ibl/pursuits?archived=${archived}&offset=${offset}&limit=20`);
      setRows(result.items); setTotal(result.total);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }, [archived, offset]);
  useEffect(() => { if (open) void load(); }, [open, load]);
  const read = async (id: string) => {
    setBusy(true); setError(''); setCopied(false);
    try { setDetail(await api.request<Detail>(`/ibl/pursuits/${encodeURIComponent(id)}`)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  const change = async (status: string) => {
    if (!detail) return;
    const p = detail.pursuit;
    setBusy(true); setError('');
    try {
      await api.request(`/ibl/pursuits/${encodeURIComponent(p.id)}`, {
        method: 'PATCH', body: JSON.stringify({ version: p.version, status, why: `사용자가 조종실에서 ${labels[status]} 선택` }),
      });
      await read(p.id); await load();
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!detail || !window.confirm(`“${detail.pursuit.title}”의 과제와 사건 기록을 삭제할까요?`)) return;
    setBusy(true); setError('');
    try {
      const p = detail.pursuit;
      await api.request(`/ibl/pursuits/${encodeURIComponent(p.id)}?version=${p.version}`, { method: 'DELETE' });
      setDetail(null); await load();
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  return <section className="rounded-xl border border-stone-200 bg-white text-stone-700">
    <button className="flex w-full items-center gap-2 p-3 text-sm font-medium" onClick={() => setOpen(!open)} aria-expanded={open}>
      {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}<BookOpen size={16} /> 이어가는 과제
    </button>
    {open && <div className="space-y-3 border-t border-stone-100 p-3 text-sm">
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1"><input type="checkbox" checked={archived} onChange={e => { setArchived(e.target.checked); setOffset(0); setDetail(null); }} />완료·보관 보기</label>
        <button onClick={() => void load()} disabled={busy} aria-label="과제 새로고침"><RefreshCw size={14} /></button>
        {busy && <Loader2 size={14} className="animate-spin" />}
      </div>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {!busy && rows.length === 0 && <p className="text-stone-500">아직 기록된 과제가 없습니다. 대화에서 “과제로 잡아 둬”라고 요청할 수 있습니다.</p>}
      <ul className="divide-y divide-stone-100">{rows.map(p => <li key={p.id}>
        <button onClick={() => void read(p.id)} className="w-full py-2 text-left hover:bg-stone-50">
          <span className="font-medium">{p.title}</span><span className="ml-2 text-xs text-stone-500">{labels[p.status]} · {p.agent_key}</span>
          {p.next && <p className="mt-1 truncate text-xs text-stone-500">다음: {p.next}</p>}
        </button>
      </li>)}</ul>
      {total > 20 && <div className="flex gap-3">
        <button disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 20))}>이전</button>
        <span>{offset + 1}–{Math.min(offset + 20, total)} / {total}</span>
        <button disabled={offset + 20 >= total || busy} onClick={() => setOffset(offset + 20)}>다음</button>
      </div>}
      {detail && <article className="space-y-3 rounded-lg bg-stone-50 p-3">
        <h3 className="font-semibold">{detail.pursuit.title} · {labels[detail.pursuit.status]}</h3>
        {detail.pending_turns.length > 0 && <p className="text-amber-800">요약 대기 또는 중단된 턴 {detail.pending_turns.length}건이 있습니다. 실제 산출물을 확인하며 이어갑니다.</p>}
        {([['전체 완료 기준', detail.pursuit.goal_criteria], ['현재 규정', detail.pursuit.framing], ['확보한 결과', detail.pursuit.progress], ['다음 할 일', detail.pursuit.next]] as const).map(([label, text]) => text && <div key={label}>
          <p className="mb-1 text-xs font-medium text-stone-500">{label}</p><p className="whitespace-pre-wrap break-words">{text}</p>
        </div>)}
        {detail.pursuit.assumptions.filter(a => a.status === 'broken').map((a, i) => <p key={i} className="text-amber-800">깨진 전제: {a.text} — {a.evidence}</p>)}
        <div className="flex flex-wrap gap-3 text-xs">
          {Object.entries(labels).filter(([s]) => s !== detail.pursuit.status).map(([s, label]) => <button disabled={busy} key={s} onClick={() => void change(s)} className="rounded border border-stone-300 px-2 py-1">{s === 'active' ? '재개' : label}</button>)}
          <button onClick={async () => {
            try { await navigator.clipboard.writeText(`${detail.pursuit.id} 과제를 이어서 진행해줘`); setCopied(true); }
            catch (e) { setError(String(e)); }
          }} className="rounded border border-stone-300 px-2 py-1">{copied ? '복사됨' : '이어갈 요청 복사'}</button>
          <button disabled={busy} onClick={() => void remove()} className="px-2 py-1 text-red-700">삭제</button>
        </div>
        <details><summary className="cursor-pointer text-xs text-stone-500">사건 기록</summary>
          {detail.events.map(e => <div key={e.id} className="mt-2"><p className="text-xs font-medium">{e.kind}</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(e.payload, null, 2)}</pre></div>)}
        </details>
      </article>}
    </div>}
  </section>;
}
