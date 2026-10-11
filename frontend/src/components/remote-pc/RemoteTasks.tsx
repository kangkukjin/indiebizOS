import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { message, post } from './client';
import type { History, Task } from './client';

const names: Record<string, string> = { queued: '대기', running: '실행 중', succeeded: '완료', failed: '실패', cancelled: '중지됨', cancel_requested: '중지 요청됨', unknown: '결과 불명', expired: '만료' };
export function RemoteTasks({ device }: { device: string }) {
  const [tasks, setTasks] = useState<Task[]>([]), [selected, setSelected] = useState('');
  const [log, setLog] = useState(''), [result, setResult] = useState<unknown>(null), [error, setError] = useState('');
  useEffect(() => {
    let stopped = false;
    void (async () => {
      while (!stopped) {
        try {
          const history = await api.request<History>(`/remote-pcs/history?device=${encodeURIComponent(device)}`);
          if (!stopped) setTasks(history.tasks);
        } catch (e) { if (!stopped) setError(message(e)); }
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    })();
    return () => { stopped = true; };
  }, [device]);
  useEffect(() => {
    if (!selected) return;
    let stopped = false, cursor = 0;
    setLog(''); setResult(null);
    void (async () => {
      while (!stopped) {
        try {
          const history = await api.request<History>(`/remote-pcs/history?device=${encodeURIComponent(device)}&job=${selected}&cursor=${cursor}`);
          if (stopped) break;
          cursor = history.cursor;
          const text = history.events.map(e => e.kind === 'log' ? e.payload.text || '' : e.kind === 'log_gap' ? '\n[원격 로그 저장 한도 초과]\n' : '').join('');
          if (text) setLog(old => { const full = old + text; return full.length > 200000 ? '[이전 출력 생략]\n' + full.slice(-200000) : full; });
          setResult(history.tasks[0]?.result);
          await new Promise(resolve => setTimeout(resolve, history.events.length >= 100 ? 50 : 1000));
        } catch (e) { if (!stopped) setError(message(e)); break; }
      }
    })();
    return () => { stopped = true; };
  }, [device, selected]);
  return <div className="flex h-full min-h-0 flex-col p-4 text-sm">
    <p className="mb-3 text-xs text-stone-500">사람과 AI가 실행한 작업을 함께 표시합니다. 터미널 입력·화면은 이 로그에 저장하지 않습니다.</p>
    {error && <p role="alert" className="mb-2 text-red-700">{error}</p>}
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(220px,1fr)_2fr] gap-3">
      <div className="overflow-auto rounded border">
        {tasks.map(task => <div key={task.id} className={`flex items-center gap-2 border-b p-3 ${selected === task.id ? 'bg-blue-50' : ''}`}>
          <button onClick={() => setSelected(task.id)} className="min-w-0 flex-1 text-left"><div className="truncate font-medium">{task.summary.op} {task.summary.cmd || task.summary.path || ''}</div><div className="mt-1 text-xs text-stone-500">{names[task.state] || task.state} · {new Date(task.created * 1000).toLocaleTimeString()}</div></button>
          {!task.result && !['unknown', 'expired', 'cancelled'].includes(task.state) && <button className="rounded border px-2 py-1 text-xs text-red-700" onClick={() => void post('/remote-pcs/cancel', { job_id: task.id }).catch(e => setError(message(e)))}>중지</button>}
        </div>)}
        {!tasks.length && <p className="p-4 text-stone-500">작업 기록이 없습니다.</p>}
      </div>
      <div className="overflow-auto rounded bg-[#10151d] p-4 font-mono text-xs text-slate-200"><pre className="whitespace-pre-wrap break-words">{selected ? log || '출력 대기 중…' : '작업을 선택하면 로그가 표시됩니다.'}</pre>{result != null && <pre className="mt-4 whitespace-pre-wrap break-words border-t border-slate-700 pt-4">{JSON.stringify(result, null, 2)}</pre>}</div>
    </div>
  </div>;
}
