/* 실행 탭 — 프로젝트 명령(목표 문서 "실행 방법" 의 `명령`)을 샌드박스에서 돌리고 출력을 본다. URL 이 있으면 오른쪽 미리보기.
 * 몸은 엔진 I/O(/coding/projects/{id}/run · /coding/runs/{id}) — 선언이 부르지 않는 길. 서버형 실행은 중지할 때까지 산다. */
import { useEffect, useRef, useState } from 'react';
import { elapsed, runIO, type ProjectDetail, type RunRecord } from './ibl';

const btn = 'px-3 py-1.5 rounded-lg text-sm border border-stone-200 bg-white text-stone-700 hover:border-stone-400 disabled:opacity-40';
const primary = 'px-3.5 py-1.5 rounded-lg text-sm font-semibold text-white bg-teal-700 hover:bg-teal-800 disabled:opacity-40';
const label: Record<string, string> = { running: '실행 중', passed: '성공', failed: '실패', cancelled: '중지됨', interrupted: '끊김' };

export function RunTab({ resource, detail }: { resource: string; detail: ProjectDetail }) {
  const [command, setCommand] = useState(detail.run_command || '');
  const [run, setRun] = useState<RunRecord | null>(detail.run);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const offset = useRef(0);
  const out = useRef<HTMLPreElement>(null);
  const serve = !!detail.run_url;
  useEffect(() => { if (!command && detail.run_command) setCommand(detail.run_command); }, [detail.run_command, command]);
  // 출력 스트림 — 실행 중이면 1초마다, 끝난 실행은 한 번 전부.
  useEffect(() => {
    if (!run) return;
    let dead = false;
    offset.current = 0; setText('');
    const pull = async () => {
      try {
        const r = await runIO.output(run.id, offset.current);
        if (dead) return;
        if (r.text) { setText((t) => t + r.text); offset.current = r.offset; }
        if (r.run.state !== run.state) setRun(r.run);
        return r.run.state;
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); return 'failed'; }
    };
    void pull();
    const timer = setInterval(async () => { const st = await pull(); if (st && st !== 'running') clearInterval(timer); }, 1000);
    return () => { dead = true; clearInterval(timer); };
  }, [run?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const el = out.current; if (el) el.scrollTop = el.scrollHeight; }, [text]);
  const start = async () => {
    if (busy || !command.trim()) return;
    setBusy(true); setError('');
    try { const r = await runIO.start(resource, command.trim(), serve); setRun(r.run); setPreviewKey((k) => k + 1); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const stop = async () => {
    if (!run || busy) return;
    setBusy(true);
    try { setRun(await runIO.stop(run.id)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const running = run?.state === 'running';
  return (
    <div className="flex flex-col rounded-xl border border-stone-200 bg-white overflow-hidden min-h-[calc(100vh-170px-var(--app-chrome,0px))]">
      <div className="flex flex-wrap items-center gap-2 px-4 h-12 border-b border-stone-200">
        <input aria-label="실행 명령" value={command} onChange={(e) => setCommand(e.target.value)} placeholder="실행 명령 — 예: python app.py (목표 문서의 실행 방법에서 읽어 옵니다)"
          onKeyDown={(e) => { if (e.key === 'Enter') void start(); }}
          className="flex-1 min-w-[240px] h-8 px-3 rounded-lg border border-stone-200 bg-stone-50 font-mono text-xs outline-none focus:border-teal-300" />
        {running ? <button className={btn} disabled={busy} onClick={stop}>■ 중지</button>
                 : <button className={primary} disabled={busy || !command.trim()} onClick={start}>▶ 실행</button>}
        {run && (
          <span className={`inline-flex items-center gap-1.5 px-2.5 h-7 rounded-full text-xs border ${running ? 'border-sky-300 bg-sky-50 text-sky-800' : run.state === 'passed' ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-stone-200 bg-stone-50 text-stone-600'}`}>
            {running && <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />}
            {label[run.state] || run.state}{running ? ` · ${elapsed(run.started_at * 1000)}` : run.exit_code != null ? ` · 종료 ${run.exit_code}` : ''}
          </span>
        )}
        {serve && <button className={btn} onClick={() => setPreviewKey((k) => k + 1)} title={detail.run_url}>미리보기 새로 고침</button>}
      </div>
      {error && <p role="alert" className="px-4 py-2 text-sm text-red-600">{error}</p>}
      <div className={`flex-1 grid ${serve ? 'grid-cols-2' : 'grid-cols-1'} min-h-0`}>
        <pre ref={out} className="m-0 p-4 overflow-auto bg-stone-900 text-stone-200 text-[12.5px] leading-[1.6] font-mono whitespace-pre-wrap">
          {text || (run ? '' : '실행하면 출력이 여기에 흐릅니다.')}
        </pre>
        {serve && (
          <div className="flex flex-col border-l border-stone-200">
            <div className="h-8 flex items-center gap-2 px-3 border-b border-stone-200 text-xs text-stone-500 font-mono">🌐 {detail.run_url}<span className="flex-1" />
              <a href={detail.run_url} target="_blank" rel="noreferrer" className="text-teal-700 hover:underline font-sans">새 창</a></div>
            {running ? <iframe key={previewKey} title="실행 미리보기" src={detail.run_url} className="flex-1 w-full border-0 bg-white" />
                     : <div className="flex-1 flex items-center justify-center text-sm text-stone-400">실행 중일 때 미리보기가 뜹니다</div>}
          </div>
        )}
      </div>
    </div>
  );
}
