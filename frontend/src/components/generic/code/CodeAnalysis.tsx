import { useEffect, useRef, useState } from 'react';
import { analysisIO, type CodeDraft, type codeIBL } from './ibl';

const button = 'px-2 py-1 text-xs border rounded disabled:opacity-40';
export function useCodeDraft(resource: string, path: string, text: string, editing: boolean) {
  const client = useRef(crypto.randomUUID()), state = useRef<CodeDraft | null>(null);
  const latest = useRef({path, text, editing}); latest.current = {path, text, editing};
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const sync = () => {
    const current = {...latest.current};
    const run = queue.current.catch(() => undefined).then(async () => {
      if (!current.editing) return state.current?.view;
      const before = state.current;
      if (before?.files[current.path] === current.text) return before.view;
      state.current = await analysisIO.draft(resource, {client: client.current, view: before?.view,
        expected: before?.revision, path: current.path, text: current.text});
      setDirty(true); setError('');
      return state.current.view;
    });
    queue.current = run; return run;
  };
  const close = () => {
    const run = queue.current.catch(() => undefined).then(async () => {
      const before = state.current;
      if (before) await analysisIO.draft(resource, {client: client.current, view: before.view, expected: before.revision, action: 'close'});
      state.current = null;
      latest.current.editing = false;
      setDirty(false); setError('');
    });
    queue.current = run;
    return run;
  };
  useEffect(() => {
    if (!editing || !path) return;
    const timer = window.setTimeout(() => { void sync().catch(e => setError(String(e))); }, 450);
    return () => clearTimeout(timer);
  }, [editing, path, text, resource]);
  useEffect(() => () => { void close().catch(() => undefined); }, [resource]);
  return {sync, close, error, dirty, text: (file: string) => state.current?.files[file],
    client: client.current, accept: (value: CodeDraft) => { state.current = value; setDirty(true); },
    save: async () => {
      await sync(); const before = state.current;
      if (!before) throw new Error('저장할 초안이 없습니다');
      state.current = await analysisIO.draft(resource, {client: client.current, view: before.view, expected: before.revision, action: 'save'});
      setDirty(false);
    }};
}

type Item = {name?: string; label?: string; title?: string; message?: string; path?: string; ref?: string;
  range?: {start: {line: number; column: number}}; target?: Record<string, unknown>; [key: string]: unknown};
export function CodeAnalysis({ibl, path, draft, onChanged, onPick, onBusy, editing, locked}: {
  ibl: ReturnType<typeof codeIBL>; path: string; draft: ReturnType<typeof useCodeDraft>;
  onChanged: (text: string) => void; onPick: (path: string) => void; editing: boolean; locked: boolean;
  onBusy: (busy: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [line, setLine] = useState(1), [column, setColumn] = useState(1);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [items, setItems] = useState<Item[]>([]), [selected, setSelected] = useState<Item | null>(null);
  const [newName, setNewName] = useState('');
  const [servers, setServers] = useState<Awaited<ReturnType<typeof analysisIO.servers>> | null>(null);
  useEffect(() => { if (expanded) void analysisIO.servers().then(setServers, e => setError(String(e))); }, [expanded]);
  const run = async (analysis: string, propose = false, extra: Record<string, unknown> = {}) => {
    setBusy(true); onBusy(true); setError('');
    try {
      const view = await draft.sync();
      const selector = {analysis, path, line, column, ...(view ? {view} : {}), ...extra};
      const value = propose ? await ibl.analysisPropose(selector) : await ibl.analysis(selector);
      if (propose) {
        await draft.sync(); // flush keystrokes typed while the server was preparing edits
        const applied = await ibl.analysisApply(String(value.proposal), draft.client);
        if (applied.view) {
          draft.accept(applied as unknown as CodeDraft);
          const content = (applied.files as Record<string, string | null>)[path];
          if (typeof content === 'string') onChanged(content);
        } else onPick(path);
        setResult(applied);
      } else { setResult(value); setItems((value.items || []) as Item[]); setSelected(null); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); onBusy(false); }
  };
  return <div className="border-t border-stone-200 p-2 bg-stone-50 text-xs">
    <button className={button} onClick={() => setExpanded(v => !v)}>코드 분석 {expanded ? '접기' : '열기'}</button>
    {expanded && <>
      <div className="flex gap-2 items-center flex-wrap my-2">
        <span>{editing || draft.dirty ? '미저장 초안' : '저장본'} · 행/열은 1부터</span>
        <input aria-label="분석 행" type="number" min={1} value={line} onChange={e => setLine(Number(e.target.value))} className="w-16 border" />
        <input aria-label="분석 열" type="number" min={1} value={column} onChange={e => setColumn(Number(e.target.value))} className="w-16 border" />
        {['definition', 'references', 'hover', 'signature', 'symbols', 'diagnostics', 'completion', 'actions', 'calls', 'types'].map((op, i) =>
          <button key={op} className={button} disabled={busy || locked || !path} onClick={() => void run(op, false,
            op === 'actions' ? {range: {start: {line, column}, end: {line, column}}} : op === 'diagnostics' ? {wait: 2} : {})}>
            {['정의', '참조', '타입 설명', '인자', '심볼', '진단', '자동완성', '코드 액션', '호출 계층', '타입 계층'][i]}</button>)}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <input aria-label="새 심볼 이름" placeholder="새 이름" value={newName} onChange={e => setNewName(e.target.value)} className="border px-1" />
        <button className={button} disabled={busy || locked || !newName} onClick={() => void run('rename', true, {new_name: newName, ...(selected?.target ? {target: selected.target, path: selected.target.path} : {})})}>이름 변경</button>
        <button className={button} disabled={busy || locked || !path} onClick={() => void run('format', true)}>포맷 적용</button>
        {selected?.ref && <>
          <button className={button} disabled={busy || locked} onClick={() => void run(selected.title ? 'code_action' : 'completion', true, {ref: selected.ref})}>선택한 편집 적용</button>
          {['incoming', 'outgoing', 'supertypes', 'subtypes'].map(direction => <button key={direction} className={button} disabled={busy}
            onClick={() => void run(direction.endsWith('types') ? 'types' : 'calls', false, {ref: selected.ref, direction})}>{direction}</button>)}
        </>}
      </div>
      {(error || draft.error) && <p role="alert" className="text-red-700 my-2">{error || draft.error}</p>}
      <div className="max-h-48 overflow-auto my-2">
        {items.map((item, index) => <div key={index} className={`flex gap-2 py-1 ${selected === item ? 'bg-teal-100' : ''}`}>
          <button className="text-left flex-1" onClick={() => setSelected(item)}>{item.name || item.label || item.title || item.message || item.path || JSON.stringify(item)}</button>
          {item.path && <button className={button} disabled={busy} onClick={() => { if (item.range) { setLine(item.range.start.line); setColumn(item.range.start.column); } onPick(item.path!); }}>{item.path}:{item.range?.start.line}</button>}
        </div>)}
        {result && <details><summary>분석 상태·판본과 전체 결과</summary><pre className="whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre></details>}
      </div>
      <details><summary>언어 서버 설정</summary>
        {servers?.items.map(s => <p key={s.server}>{s.server} · {s.version || '미설치'} · {s.installed ? '사용 가능' : '설치 필요'}</p>)}
        <button className={button} disabled={busy} onClick={() => { setBusy(true); void analysisIO.install().then(() => analysisIO.servers()).then(setServers).catch(e => setError(String(e))).finally(() => setBusy(false)); }}>고정 버전 설치·복구</button>
      </details>
    </>}
  </div>;
}
