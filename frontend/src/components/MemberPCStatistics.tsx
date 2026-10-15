import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../lib/api';

type Task = {
  id: string; request: string; status: string; started: number; finished: number | null;
  tokens: number | null; models: {role: string; provider: string; model: string}[];
  actions: {tool: string; status: string}[];
};
type Statistics = {period_start: string; period_end: string; tokens_month: number; turns_month: number; tasks: Task[]; next_offset: number | null};
const labels: Record<string, string> = {completed: '완료', failed: '실패', cancelled: '취소', running: '진행 중', waiting_input: '입력 대기'};
const date = (value: number) => new Date(value * 1000).toLocaleString();
export function MemberPCStatistics({deviceId, name, onClose}: {deviceId: string; name: string; onClose: () => void}) {
  const [data, setData] = useState<Statistics | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let alive = true;
    setBusy(true); setError(''); setData(null);
    api.request<Statistics>(`/member-pcs/${encodeURIComponent(deviceId)}/statistics`)
      .then(value => { if (alive) setData(value); }).catch(e => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [deviceId, refresh]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [onClose]);
  const more = async () => {
    if (data?.next_offset == null) return;
    setBusy(true); setError('');
    try {
      const value = await api.request<Statistics>(`/member-pcs/${encodeURIComponent(deviceId)}/statistics?offset=${data.next_offset}`);
      setData({...value, tasks: [...data.tasks, ...value.tasks.filter(t => !data.tasks.some(old => old.id === t.id))]});
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
    <section role="dialog" aria-modal="true" aria-labelledby="pc-statistics-title" className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl bg-white shadow-xl">
      <header className="flex items-center justify-between border-b p-5"><h2 id="pc-statistics-title" className="font-semibold">{name} · 통계</h2>
        <div className="flex gap-4"><button disabled={busy} className="text-sm disabled:opacity-40" onClick={() => setRefresh(v => v + 1)}>새로고침</button><button autoFocus aria-label="통계 닫기" onClick={onClose}><X size={20} /></button></div></header>
      <div className="space-y-5 overflow-auto p-5">
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {busy && <p role="status" className="text-sm text-stone-500">불러오는 중…</p>}
        {data && <>
          <section className="rounded-lg bg-stone-50 p-4"><h3 className="text-sm font-semibold">최근 1달 누적 사용량 · 오늘 포함 30일</h3>
            <p className="mt-1 text-xs text-stone-500">{data.period_start} ~ {data.period_end} · 중앙 PC 날짜 기준</p>
            <p className="mt-3 text-2xl font-semibold">{data.tokens_month.toLocaleString()} <span className="text-sm font-normal">토큰</span></p>
            <p className="mt-1 text-sm text-stone-500">요청 {data.turns_month.toLocaleString()}건 · 실패·취소된 작업의 측정 사용량도 포함</p>
            <p className="mt-2 text-xs text-stone-500">입력·출력 토큰의 합계입니다. 진행 중인 작업의 사용량은 작업이 끝난 뒤 반영됩니다.</p></section>
          <section><h3 className="mb-3 text-sm font-semibold">작업별 기록 · 최신순</h3>
            {!data.tasks.length && <p className="text-sm text-stone-500">기록된 작업이 없습니다. 상세 기록을 남기기 전의 사용량도 위 누적 통계에 포함됩니다.</p>}
            {data.tasks.map(task => <details key={task.id} className="border-b py-3">
              <summary className="cursor-pointer text-sm"><span className="font-medium">{task.request.slice(0, 100) || '요청 내용 없음'}{task.request.length > 100 ? '…' : ''}</span>
                <span className="mt-1 block text-xs text-stone-500">{date(task.started)} · {labels[task.status] || task.status} · {task.tokens == null ? '토큰 미측정' : `${task.tokens.toLocaleString()} 토큰`}</span></summary>
              <p className="my-3 whitespace-pre-wrap break-words text-sm">{task.request}</p>
              {task.finished && <p className="text-xs text-stone-500">종료: {date(task.finished)}</p>}
              <p className="mt-2 break-words text-xs text-stone-500">{task.models.map(m => `${m.role}: ${m.provider}/${m.model}`).join(' · ')}</p>
              <ol className="mt-2 list-inside list-decimal space-y-1 text-xs">{task.actions.map((a, i) => <li key={i}>{a.tool} · {labels[a.status] || a.status}</li>)}</ol>
            </details>)}
            {data.next_offset != null && <button disabled={busy} className="mt-4 rounded-lg border px-4 py-2 text-sm" onClick={() => void more()}>이전 작업 더 보기</button>}
          </section>
        </>}
      </div>
    </section>
  </div>;
}
