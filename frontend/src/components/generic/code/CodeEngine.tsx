/* 코드 엔진 — `engine` 뷰(kind=code)의 실체: 코딩 프로젝트를 문서처럼 (docs/CODING_APP_ON_IBL_PLAN_2026_10_07.md §1-2).
 *   상단: ← 프로젝트 · 이름 · [목표 문서 | 코드 파일 | 실행] · AI 상태 칩 · 목표대로 코딩 · ⚙
 *   목표 문서 탭(기본): 목표.md 캔버스 + AI 한 줄(ai_dock — 선언의 action, 보통 [self:ask]) → 제안 → 반영. 저장 = 파일 쓰기 + 기록.
 *   코드 파일 탭: 트리 + 원문(읽기 전용 → 편집 → 저장=기록). 실행 탭: 프로젝트 명령 실행·출력·미리보기(엔진 I/O).
 *   AI 코딩: [others:delegate]{scope:"system", role:"coding"} 한 문장 → 접수증 → [self:task] 로 상태. 끝나면 자동 기록 + 새로 읽기.
 * 몸은 전부 기존 낱말이다(ibl.ts). diff·도구 카드·권한 모드·승인 단추는 일부러 없다. */
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { AppFormField, AppMode, InstrumentMenu } from '../manifest';
import { actionRequest, runIBL, suggestionText, InstrumentMenuContext } from '../manifest';
import { AiDockPanel } from '../prims-edit';
import { codeIBL, delegationMessage, elapsed, GOAL_NAME, type ProjectDetail, type TaskRef, type Version } from './ibl';
import { FilesTab } from './FilesTab';
import { RunTab } from './RunTab';

type Dock = NonNullable<AppFormField['ai_dock']>;
export type CodeHost = { dock?: Dock; vars?: Record<string, unknown>; block?: AppMode; menu?: InstrumentMenu | null };
type Emit = (event: 'selection' | 'saved', payload: Record<string, unknown>) => void;
type Tab = 'goal' | 'files' | 'run';

const btn = 'px-3 py-1.5 rounded-lg text-sm border border-stone-200 bg-white text-stone-700 hover:border-stone-400 disabled:opacity-40';
const primary = 'px-3.5 py-1.5 rounded-lg text-sm font-semibold text-white bg-teal-700 hover:bg-teal-800 disabled:opacity-40';

export function CodeEngine({ id, emit, host }: { id: string; emit: Emit; host: CodeHost }) {
  const ibl = useMemo(() => codeIBL(host.block, id), [host.block, id]);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<Tab>('goal');
  const [task, setTask] = useState<{ ref: TaskRef; since: number } | null>(null);
  const [report, setReport] = useState<{ ok: boolean; text: string } | null>(null);   // AI 가 끝나며 남긴 보고(닫을 수 있다)
  const [gear, setGear] = useState(false);
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);       // 파일이 바깥(AI)에서 바뀌면 탭 내용을 다시 읽게
  const menu = useContext(InstrumentMenuContext);
  const claim = menu?.claim;
  useEffect(() => claim?.(), [claim]);                 // 이 엔진이 서 있는 동안 계기 탭 줄은 ⚙ 안으로

  const load = useCallback(async () => {
    const d = await ibl.detail();
    setDetail(d);
    if (d.active_task && !task) setTask({ ref: d.active_task, since: Date.now() });
    return d;
  }, [ibl, task]);
  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        const d = await ibl.detail();
        if (dead) return;
        setDetail(d);
        if (d.active_task) setTask({ ref: d.active_task, since: Date.now() });
        else if (d.dirty) {                                   // 지난 AI 작업·바깥 편집이 기록되지 않은 채 남았으면 열 때 정리한다
          await ibl.save('자동 기록 (열 때 정리)');
          const again = await ibl.detail();
          if (!dead) setDetail(again);
        }
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); }
    })();
    return () => { dead = true; };
  }, [ibl]);

  // 위임 진행 — 접수증을 쥐고 [self:task] 로 묻는다. 끝나면 기록하고 다시 읽는다.
  useEffect(() => {
    if (!task) return;
    let dead = false;
    const finish = async (ok: boolean, text: string, state: string) => {
      setTask(null);
      setReport({ ok, text: text.slice(0, 2000) });
      try { await ibl.save(ok ? 'AI 코딩: ' + (detail?.summary || detail?.name || '목표대로') : 'AI 코딩 중단 시점의 상태'); } catch { /* 바뀐 것이 없으면 clean */ }
      setReloadKey((k) => k + 1);
      await load();
      emit('saved', { revision: state });
    };
    const tick = async () => {
      let v: Awaited<ReturnType<typeof ibl.status>>;
      try { v = await ibl.status(task.ref); }
      catch (e) {
        // 완료된 시스템 작업은 백엔드 재기동 때 정리된다(boot_common) — 접수증이 모르는 작업이 되면 끝난 것으로 보고 폴더를 다시 읽는다.
        const msg = e instanceof Error ? e.message : String(e);
        if (dead) return;
        if (/찾지 못했|unknown/.test(msg)) { await finish(true, '작업의 끝을 접수증으로 확인하지 못했습니다(백엔드 재기동). 폴더의 결과를 기록하고 다시 읽었습니다 — 진행 기록을 확인하세요.', 'unknown'); return; }
        setError(msg); return;
      }
      if (dead) return;
      if (v.state === 'unknown') { await finish(true, '작업의 끝을 접수증으로 확인하지 못했습니다(백엔드 재기동). 폴더의 결과를 기록하고 다시 읽었습니다 — 진행 기록을 확인하세요.', 'unknown'); return; }
      if (!v.terminal) return;
      const ok = v.state === 'succeeded';
      const text = ok ? String((v.result as { response?: string } | string | null) && (typeof v.result === 'string' ? v.result : (v.result as { response?: string })?.response) || '작업을 끝냈습니다.')
                      : `AI 작업이 끝나지 않았습니다 (${v.state}${v.failure ? ' — ' + v.failure : ''})`;
      try { await finish(ok, text, v.state); } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); }
    };
    void tick();
    const timer = setInterval(tick, 4000);
    return () => { dead = true; clearInterval(timer); };
  }, [task, ibl, load, emit, detail?.summary, detail?.name]);

  const run = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const startCoding = () => run(async () => {
    if (!detail) return;
    if (!detail.goal_exists) throw new Error('목표 문서가 없습니다 — 목표 문서 탭에서 먼저 쓰세요');
    await ibl.save('AI 코딩 전 상태');                       // 되돌릴 자리를 남긴다
    const r = await ibl.delegate(detail.path, detail.goal_path, delegationMessage(detail));
    const ref = (r.task_ref as TaskRef) || null;
    if (!ref) throw new Error('위임 접수증이 없습니다');
    setReport(null);
    setTask({ ref, since: Date.now() });
  });
  const stopCoding = () => run(async () => { if (task) { await ibl.cancel(task.ref); } });
  const openVersions = () => run(async () => { setVersions(await ibl.versions()); });
  const unregister = () => run(async () => {
    if (!detail || !window.confirm(`「${detail.name}」의 프로젝트 등록을 해제할까요?\n폴더·파일·기록은 그대로 남고, 진행 중인 작업은 계속됩니다.\n기존 폴더 가져오기로 다시 등록할 수 있습니다.`)) return;
    await ibl.unregister();
    menu?.go(0);
  });
  const restoreTo = (v: Version) => run(async () => {
    if (!window.confirm(`"${v.label}" 시점으로 프로젝트 전체를 되돌릴까요? 지금 상태는 먼저 기록해 둡니다.`)) return;
    await ibl.restore(v.id);
    setVersions(null); setGear(false);
    setReloadKey((k) => k + 1);
    await load();
  });

  if (error && !detail) return <p role="alert" className="text-sm text-red-600">{error}</p>;
  if (!detail) return <p className="text-sm text-stone-400">프로젝트를 여는 중…</p>;
  const aiBusy = !!task;
  const tabs: [Tab, string][] = [['goal', '목표 문서'], ['files', '코드 파일'], ['run', '실행']];
  return (
    <div className="flex flex-col gap-2 min-h-[calc(100vh-96px-var(--app-chrome,0px))]">
      <div className="flex flex-wrap items-center gap-2">
        <button className="px-2 py-1.5 rounded-lg text-sm text-stone-500 hover:bg-stone-100" onClick={() => menu?.go(0)}>← 프로젝트</button>
        <span className="font-semibold text-stone-800 truncate max-w-[30%]" title={detail.path}>{detail.icon} {detail.name}</span>
        <div className="flex-1" />
        <div className="flex gap-1 rounded-xl border border-stone-200 bg-stone-100 p-0.5">
          {tabs.map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)} aria-pressed={tab === k}
              className={`px-4 py-1.5 rounded-lg text-sm ${tab === k ? 'bg-white text-teal-700 font-semibold shadow-sm' : 'text-stone-600 hover:text-stone-800'}`}>{label}</button>
          ))}
        </div>
        <div className="flex-1" />
        {aiBusy ? (
          <>
            <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-full border border-teal-600 bg-teal-50 text-teal-800 text-xs">
              <span className="w-2 h-2 rounded-full bg-teal-600 animate-pulse" />AI 작업 중 · {elapsed(task!.since)}
            </span>
            <button className={btn} disabled={busy} onClick={stopCoding}>중지</button>
          </>
        ) : (
          <button className={primary} disabled={busy || !detail.goal_exists} title={detail.goal_exists ? '목표 문서대로 AI 가 코딩합니다' : '목표 문서를 먼저 쓰세요'} onClick={startCoding}>목표대로 코딩</button>
        )}
        <button className={`px-2.5 py-1.5 rounded-lg text-sm hover:bg-stone-100 ${gear ? 'bg-stone-100' : 'text-stone-600'}`} onClick={() => setGear((v) => !v)} title="프로젝트 도구">⚙</button>
      </div>
      {gear && (
        <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm flex flex-wrap items-center gap-2">
          <span className="text-xs text-stone-500 font-mono truncate max-w-full" title={detail.path}>{detail.path}</span>
          <span className="text-xs text-stone-400">{detail.head ? `기록 ${detail.head}` : '아직 기록 없음'}{detail.dirty ? ' · 기록 안 된 변경 있음' : ''}</span>
          <div className="flex-1" />
          <button className={btn} disabled={busy || !detail.dirty} onClick={() => run(async () => { await ibl.save('직접 기록'); await load(); })}>지금 기록</button>
          <button className={btn} disabled={busy} onClick={openVersions}>이 작업 전으로…</button>
          {menu && <button className={btn} disabled={busy} onClick={unregister}>등록 해제</button>}
          {typeof window !== 'undefined' && (window as unknown as { electron?: { openPath?: (p: string) => Promise<void> } }).electron?.openPath && (
            <button className={btn} onClick={() => void (window as unknown as { electron: { openPath: (p: string) => Promise<void> } }).electron.openPath(detail.path)}>폴더 열기</button>
          )}
          {menu && menu.modes.some(Boolean) && menu.modes.map((name, i) => name && (
            <button key={i} className={btn} onClick={() => menu.go(i)}>{name}</button>
          ))}
        </div>
      )}
      {versions && (
        <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
          <div className="flex items-center gap-2 mb-2"><span className="font-semibold">기록</span><span className="text-xs text-stone-500">고르면 그 시점으로 프로젝트 전체를 되돌립니다</span><div className="flex-1" /><button className={btn} onClick={() => setVersions(null)}>닫기</button></div>
          {versions.length === 0 ? <p className="text-stone-500">아직 기록이 없습니다.</p> : (
            <ul className="divide-y divide-stone-100 max-h-72 overflow-auto">
              {versions.map((v) => (
                <li key={v.id} className="flex items-center gap-3 py-1.5">
                  <span className="font-mono text-xs text-stone-400">{v.short}</span>
                  <span className="flex-1 truncate">{v.label}</span>
                  <span className="text-xs text-stone-400">{new Date(v.created_at * 1000).toLocaleString()}</span>
                  <button className={btn} disabled={busy} onClick={() => restoreTo(v)}>이 시점으로</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {report && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${report.ok ? 'border-teal-200 bg-teal-50 text-teal-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
          <div className="flex items-start gap-2"><span className="font-semibold shrink-0">{report.ok ? 'AI 보고' : 'AI 중단'}</span><span className="whitespace-pre-wrap flex-1">{report.text}</span><button className="text-xs text-stone-500 hover:text-stone-800" onClick={() => setReport(null)}>닫기</button></div>
        </div>
      )}
      {tab === 'goal' && <GoalTab key={`goal-${reloadKey}`} ibl={ibl} detail={detail} host={host} locked={aiBusy} onSaved={() => void load()} />}
      {tab === 'files' && <FilesTab key={`files-${reloadKey}`} ibl={ibl} detail={detail} locked={aiBusy} onChanged={() => void load()} />}
      {tab === 'run' && <RunTab resource={id} detail={detail} />}
    </div>
  );
}

/* ── 목표 문서 탭: 넓은 캔버스 + AI 한 줄. 저장 = 파일 쓰기 + 기록("목표 문서 수정"). ── */
function GoalTab({ ibl, detail, host, locked, onSaved }: {
  ibl: ReturnType<typeof codeIBL>; detail: ProjectDetail; host: CodeHost; locked: boolean; onSaved: () => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const [saved, setSaved] = useState('');
  const [fingerprint, setFingerprint] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState(0);
  const [undo, setUndo] = useState<string | null>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const range = useRef({ a: 0, b: 0 });
  const pinned = useRef<{ a: number; b: number; before: string } | null>(null);
  const [scope, setScope] = useState<'선택' | '전체'>('전체');
  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        if (!detail.goal_exists) { if (!dead) { setText(''); setSaved(''); setFingerprint(''); } return; }
        const f = await ibl.file(GOAL_NAME);
        if (!dead) { setText(f.text); setSaved(f.text); setFingerprint(f.fingerprint); }
      } catch (e) { if (!dead) { setText(''); setSaved(''); setMessage('⚠️ 목표 문서를 읽지 못했습니다 — ' + (e instanceof Error ? e.message : String(e)) + ' (탭을 다시 누르면 다시 읽습니다)'); } }
    })();
    return () => { dead = true; };
  }, [ibl, detail.goal_exists]);
  const dirty = text !== null && text !== saved;
  const save = async () => {
    if (text === null || busy) return;
    setBusy(true);
    try {
      await ibl.write(GOAL_NAME, text, '목표 문서 수정');
      const f = await ibl.file(GOAL_NAME);
      setSaved(f.text); setText(f.text); setFingerprint(f.fingerprint);
      setMessage('저장·기록됨');
      onSaved();
    } catch (e) { setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { setBusy(false); }
  };
  const track = () => { const el = editor.current; if (!el) return; range.current = { a: el.selectionStart, b: el.selectionEnd }; setPicked(el.selectionEnd - el.selectionStart); };
  const ask = async (instruction: string) => {
    if (!host.dock || text === null) return '';
    const el = editor.current; if (el) range.current = { a: el.selectionStart, b: el.selectionEnd };
    const { a, b } = range.current; const has = a !== b;
    const s = has ? a : 0, e = has ? b : text.length;
    pinned.current = { a: s, b: e, before: text.slice(s, e) };
    setScope(has ? '선택' : '전체');
    return suggestionText(await runIBL(actionRequest(host.block, host.dock.action, {
      ...(host.vars || {}), resource: detail.resource, path: detail.path, sel: { start: s, end: e }, start: s, end: e,
      text: text.slice(s, e), dock: instruction,
    })));
  };
  const applySuggestion = (mode: 'replace' | 'append', suggestion: string) => {
    if (text === null) return;
    const pin = pinned.current;
    setUndo(text);
    if (mode === 'append' || !pin) { setText(text.trim() ? `${text}\n\n${suggestion}` : suggestion); return; }
    if (text.slice(pin.a, pin.b) !== pin.before) { setMessage('⚠️ 요청한 뒤 그 자리의 글이 바뀌어 반영하지 않았습니다 — 다시 요청하세요'); return; }
    setText(text.slice(0, pin.a) + suggestion.trim() + text.slice(pin.b));
  };
  if (text === null) return <p className="text-sm text-stone-400">목표 문서를 읽는 중…</p>;
  const tall = 'min-h-[calc(100vh-230px-var(--app-chrome,0px))]';
  const page = 'px-[max(2.5rem,calc(50%-26rem))]';
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-stone-600">{GOAL_NAME}</span>
        {dirty && <span className="text-xs text-amber-600">● 저장 안 됨</span>}
        <span role="status" className="text-xs text-stone-500 truncate">{message}</span>
        <div className="flex-1" />
        {undo != null && <button className={btn} onClick={() => { setText(undo); setUndo(null); }}>AI 반영 되돌리기</button>}
        <button className={primary} disabled={busy || !dirty || locked} onClick={save} title={locked ? 'AI 작업 중에는 저장하지 않습니다' : 'Ctrl+S'}>저장</button>
      </div>
      <textarea ref={editor} aria-label="목표 문서" spellCheck={false} value={text} readOnly={locked}
        placeholder={`# ${detail.name} — 코딩 목표\n\n## 무엇을 만드나\n\n만들고 싶은 것을 말하듯 쓰거나, 아래 AI 한 줄에 말하세요.`}
        onChange={(e) => setText(e.target.value)} onSelect={track} onMouseUp={track} onKeyUp={track}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); void save(); } }}
        className={`w-full ${tall} resize-none bg-white rounded-xl shadow-sm border border-stone-200 ${page} py-9 text-[15px] leading-8 outline-none focus:border-teal-300`}
        style={{ fontFamily: "'Noto Serif KR', serif" }} />
      {host.dock && !locked && (
        <div className="sticky bottom-0 -mx-1 px-1 pb-2 bg-stone-50/95 backdrop-blur">
          <AiDockPanel dock={{ ...host.dock, placeholder: host.dock.placeholder || (picked ? `선택한 ${picked}자를 AI에게 — 예: 더 구체적으로 (Enter 전송)` : '원하는 것을 말하세요 — AI 가 목표 문서로 정리합니다 (Enter 전송)') }}
            ask={ask} onApply={applySuggestion} applyLabel={`문서에 반영 (${scope})`} />
        </div>
      )}
      {locked && <p className="text-xs text-stone-500">AI 가 작업하는 동안 목표 문서는 읽기만 됩니다 — 끝나면 진행 기록이 붙어 다시 열립니다.</p>}
      <span className="sr-only">{fingerprint}</span>
    </div>
  );
}
