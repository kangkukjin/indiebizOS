/* 시트 엔진 바인딩 — `engine` 뷰(kind=sheet)의 실체. 엑셀 얼굴(ExcelFrame) + 격자 엔진(GridEngine, 기본) 또는
 * 사무 엔진(SpreadsheetEditor=ONLYOFFICE, 격자가 못 그리는 부품이 있을 때). docs/SPREADSHEET_APP_ON_IBL_PLAN_2026_10_07.md.
 *   · 세션은 문서 엔진과 같은 규약(한 창이 쥔다·죽은 창은 조용히 이어받는다·떠날 때 놓는다).
 *   · 자동 초안: 격자가 바뀌면 2초 뒤 grid-capture(격자 → XLSX → 세션 blob). Ctrl+S = 원본 저장.
 *   · `[self:workspace]` 의 snapshot/apply/save 는 편집창에 접수(pending 큐)되고 여기서 소비한다 — 플러그인이 하던 일.
 *   · 선택은 뷰-이벤트 selection 으로($sel={sheet,range}·$table·$text), AI 작업창(ai_dock)은 같은 페이로드로 제안을 받아 미리보기 → 반영. */
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import type { AppFormField, AppMode, InstrumentMenu } from '../manifest';
import { actionRequest, runIBL, InstrumentMenuContext } from '../manifest';
import { sheetCommand, sheetRequest, sessionArgs, releaseSheetSession, type SheetDetail, type Session, type SheetSnapshot } from '../../../lib/api-spreadsheets';
import { BACKEND_ORIGIN } from '../../../lib/backend-origin';
import { openDocuments } from '../../../lib/surface-navigation';
import { SpreadsheetEditor } from '../../spreadsheets/SpreadsheetEditor';
import { SpreadsheetConversion } from '../../spreadsheets/SpreadsheetConversion';
import { GridEngine, type Selection } from './grid-engine';
import { ExcelFrame } from './ExcelFrame';
import type { GridWorkbook } from './grid-schema';
import { parseRange, rangeA1, a1 } from './grid-schema';

type Dock = NonNullable<AppFormField['ai_dock']>;
type Payload = Record<string, unknown>;
type Result = Record<string, unknown>;
export type SheetHost = { dock?: Dock; vars?: Record<string, unknown>; block?: AppMode; menu?: InstrumentMenu | null; clientId: string; holderAlive: (holder: string) => Promise<boolean> };
type Emit = (event: 'selection' | 'saved', payload: Payload) => void;
type Proposal = { sel: Selection; before: (string | number | boolean | null)[][]; values: (string | number | boolean | null)[][]; changes: { addr: string; from: string; to: string }[] };

const CELL_CAP = 10000, WHOLE_CAP = 20000;
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '(비어 있음)' : String(v));

export function SheetEngine({ id, emit, host }: { id: string; emit: Emit; host: SheetHost }) {
  const [detail, setDetail] = useState<SheetDetail | null>(null);
  const [error, setError] = useState('');
  const [office, setOffice] = useState(false);     // 사무 편집기로 전환(파일 탭)
  const menu = useContext(InstrumentMenuContext);
  const claim = menu?.claim;
  useEffect(() => claim?.(), [claim]);
  const me = host.clientId;
  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        let d = await sheetRequest<SheetDetail>(`/${encodeURIComponent(id)}`);
        if (d.capabilities.edit_native) {
          if (!d.session) d = await sheetCommand<SheetDetail>(id, 'sessions', { client_id: me });
          else if (d.session.client_id !== me && !(await host.holderAlive(d.session.client_id))) {
            const epoch = d.session.engine_epoch;
            d = await sheetCommand<SheetDetail>(id, 'reclaim', { client_id: me, expected_epoch: epoch }).catch(() => sheetRequest<SheetDetail>(`/${encodeURIComponent(id)}`));
          }
        }
        if (!dead) { setDetail(d); setOffice(d.capabilities.engine === 'office'); }
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); }
    })();
    return () => { dead = true; };
  }, [id, me]); // eslint-disable-line react-hooks/exhaustive-deps
  const latest = useRef(detail);
  useEffect(() => { latest.current = detail; }, [detail]);
  useEffect(() => {
    const release = () => {
      const d = latest.current;
      if (d?.session && d.session.client_id === me) { latest.current = null; void releaseSheetSession(d.document.id, d.session); }
    };
    window.addEventListener('pagehide', release);
    return () => { window.removeEventListener('pagehide', release); release(); };
  }, [id, me]);
  if (error) return <p role="alert" className="text-sm text-red-600">{error}</p>;
  if (!detail) return <p className="text-sm text-stone-400">통합문서를 여는 중…</p>;
  if (detail.session && detail.session.client_id !== me) return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-stone-600">
      <span>다른 작성 창이 이 통합문서를 쥐고 있습니다. 이 창으로 가져오면 그 창의 저장 권한이 끝납니다.</span>
      <button className="px-3 py-1.5 rounded-lg border border-stone-300 hover:border-stone-500" onClick={() => {
        const s = detail.session; if (!s) return;
        sheetCommand<SheetDetail>(id, 'reclaim', { client_id: me, expected_epoch: s.engine_epoch }).then(setDetail, (e) => setError(e instanceof Error ? e.message : String(e)));
      }}>이 창에서 초안 이어 쓰기</button>
    </div>
  );
  const caps = detail.capabilities;
  if (!caps.edit_native || (office && !caps.office)) return <Unavailable detail={detail} menu={menu} onRetry={() => sheetRequest<SheetDetail>(`/${encodeURIComponent(id)}`).then(setDetail)} />;
  if (office) return <OfficeSheet detail={detail} onChange={setDetail} emit={emit} menu={menu} onGrid={caps.grid ? () => setOffice(false) : undefined} />;
  return <GridSheet key={`${detail.document.id}:${detail.session?.engine_epoch}`} detail={detail} onChange={setDetail} emit={emit} host={{ ...host, menu }} onOffice={caps.office_available ? () => setOffice(true) : undefined} />;
}

/* ── 열 수 없는 자료: 이유 + 할 수 있는 일(편집 서버 시작·계기 탭) ── */
function Unavailable({ detail, menu, onRetry }: { detail: SheetDetail; menu: InstrumentMenu | null; onRetry: () => void }) {
  const [msg, setMsg] = useState('');
  const caps = detail.capabilities;
  return (
    <div className="flex flex-col gap-3 text-sm text-stone-600">
      {menu && menu.modes.some(Boolean) && <div className="flex flex-wrap gap-1.5">{menu.modes.map((n, i) => n && <button key={i} onClick={() => menu.go(i)} className="px-3 py-1 rounded-lg border border-stone-200 bg-white hover:border-stone-500">{n}</button>)}</div>}
      <p><b>{detail.document.title}</b> — {caps.reason}</p>
      {caps.grid_blockers && caps.grid_blockers.length > 0 && !caps.office_available && (
        <button className="self-start px-3 py-1.5 rounded-lg border border-stone-300 hover:border-stone-500" onClick={async () => {
          setMsg('편집 서버를 시작하는 중… (1~3분)');
          try { const r = await fetch(`${BACKEND_ORIGIN}/documents/engine/start`, { method: 'POST', credentials: 'include' }); const j = await r.json(); if (!r.ok) throw new Error(j.detail); setMsg(String(j.message)); onRetry(); }
          catch (e) { setMsg('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
        }}>사무 편집 서버 시작</button>)}
      {msg && <p role="status">{msg}</p>}
    </div>
  );
}

/* ── 사무 엔진(ONLYOFFICE) — 격자가 못 그리는 부품이 있는 통합문서. 옛 편집기를 그대로 싣는다. ── */
function OfficeSheet({ detail, onChange, emit, menu, onGrid }: { detail: SheetDetail; onChange: (d: SheetDetail) => void; emit: Emit; menu: InstrumentMenu | null; onGrid?: () => void }) {
  const capture = useRef<null | (() => Promise<void>)>(null);
  const [open, setOpen] = useState(false);
  return (
    <div className="engine-editor">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button onClick={() => setOpen((v) => !v)} className="px-2.5 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-100">⚙ 도구</button>
        <span className="text-xs text-stone-500">사무 편집기(ONLYOFFICE) — {detail.capabilities.reason}</span>
        {onGrid && <button onClick={onGrid} className="px-2.5 py-1 rounded-lg border border-stone-300 text-xs hover:border-stone-500">격자로 돌아가기</button>}
      </div>
      {open && menu && menu.modes.some(Boolean) && <div className="flex flex-wrap gap-1.5">{menu.modes.map((n, i) => n && <button key={i} onClick={() => menu.go(i)} className="px-3 py-1 rounded-lg border border-stone-200 bg-white text-sm hover:border-stone-500">{n}</button>)}</div>}
      <SpreadsheetEditor key={detail.document.id} detail={detail} onChange={onChange} captureRef={capture} onSaved={(d) => emit('saved', { revision: d.document.revision_id })} />
    </div>
  );
}

/* ── 격자 엔진: 엑셀 얼굴 + Univer ── */
function GridSheet({ detail, onChange, emit, host, onOffice }: { detail: SheetDetail; onChange: (d: SheetDetail) => void; emit: Emit; host: SheetHost; onOffice?: () => void }) {
  const [engine, setEngine] = useState<GridEngine | null>(null);
  const [tick, setTick] = useState(0);
  const [status, setStatus] = useState('통합문서를 읽는 중…');
  const [overlay, setOverlay] = useState<string | null>('통합문서를 읽는 중…');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [paneOpen, setPaneOpen] = useState(false);
  const current = useRef(detail); current.current = detail;
  const dirtyRef = useRef(false);
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const working = useRef(false);
  const publish = useCallback((d: SheetDetail) => { current.current = d; onChange(d); }, [onChange]);
  // 엔진 수명: 격자 자리(div)가 서면 effect 에서 만들고(Univer 는 안에서 React 를 띄우므로 render 중에 만들면 안 된다) 언마운트 때 내린다.
  const [gridHost, setGridHost] = useState<HTMLDivElement | null>(null);
  const hostRef = useCallback((el: HTMLDivElement | null) => setGridHost(el), []);
  useEffect(() => {
    if (!gridHost) return;
    const e = new GridEngine(gridHost);
    setEngine(e);
    return () => { e.dispose(); setEngine(null); };
  }, [gridHost]);
  // 통합문서 읽기 → 격자에 싣기
  useEffect(() => {
    if (!engine) return;
    let dead = false;
    (async () => {
      try {
        const r = await sheetCommand<{ grid: GridWorkbook }>(detail.document.id, 'grid', {});
        if (dead) return;
        engine.load(r.grid);
        dirtyRef.current = false; setDirty(detail.session?.state === 'draft');
        setOverlay(null); setStatus(detail.session?.state === 'draft' ? '작업 초안을 읽었습니다 · 원본에는 저장되지 않음' : '원본을 읽었습니다');
        setTick((t) => t + 1);
      } catch (e) { if (!dead) { setOverlay(null); setStatus('⚠️ ' + (e instanceof Error ? e.message : String(e))); } }
    })();
    return () => { dead = true; };
  }, [engine, detail.document.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // 격자 → 세션 초안(grid-capture). 세션 개정 번호를 물고 가므로 한 줄로 세운다.
  const capture = useCallback((): Promise<SheetDetail> => {
    const task = chain.current.catch(() => undefined).then(async () => {
      const d = current.current;
      if (!engine || !engine.loaded) throw new Error('격자가 아직 서지 않았습니다');
      if (!d.session) throw new Error('작성 세션이 없습니다');
      if (!dirtyRef.current) return d;
      await engine.settle();
      const grid = engine.export();
      dirtyRef.current = false;
      const r = await sheetCommand<{ session: Session; engine_state: string }>(d.document.id, 'grid-capture', { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), grid })
        .catch((e) => { dirtyRef.current = true; throw e; });
      const next = { ...current.current, session: r.session };
      publish(next);
      return next;
    });
    chain.current = task;
    return task;
  }, [engine, publish]);
  // 엔진 이벤트 → 얼굴 갱신·자동 초안·선택 이벤트. 콜백은 ref 로 — 부모가 매 렌더마다 새 emit 을 주어도 재구독(타이머 소실)하지 않게.
  const emitRef = useRef(emit); emitRef.current = emit;
  const captureRef = useRef(capture); captureRef.current = capture;
  useEffect(() => {
    if (!engine) return;
    const emit = (e: 'selection' | 'saved', p: Payload) => emitRef.current(e, p);
    const capture = () => captureRef.current();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let selTimer: ReturnType<typeof setTimeout> | null = null;
    const offChange = engine.onChange(() => {
      dirtyRef.current = true; setDirty(true); setStatus('수정됨 · 원본에는 저장되지 않음'); setTick((t) => t + 1);
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { if (!dirtyRef.current) return;  // 그 사이 저장(Ctrl+S)이 올렸으면 상태 문구를 덮지 않는다
        capture().then((d) => { if (!dirtyRef.current) { setStatus('작업 저장됨 · 원본에는 저장되지 않음'); setDirty(d.session?.state === 'draft'); } },
        (e) => setStatus('⚠️ 작업 저장 실패 — ' + (e instanceof Error ? e.message : String(e)))); }, 2000);
    });
    const offSel = engine.onSelection(() => {
      setTick((t) => t + 1);
      if (selTimer) clearTimeout(selTimer);
      selTimer = setTimeout(() => {
        const sel = engine.selection(); if (!sel) return;
        let table: unknown = undefined, text = '';
        try { if (sel.rows * sel.cols <= CELL_CAP) { const v = engine.values(sel); table = v; text = v.map((row) => row.map((c) => (c == null ? '' : String(c))).join('\t')).join('\n'); } } catch { /* 상한 초과 */ }
        emit('selection', { sel: { sheet: sel.sheet, range: sel.range }, sheet: sel.sheet, range: sel.range, table, text, revision: current.current.document.revision_id });
      }, 400);
    });
    const offSheets = engine.onSheets(() => setTick((t) => t + 1));
    return () => { offChange(); offSel(); offSheets(); if (timer) clearTimeout(timer); if (selTimer) clearTimeout(selTimer); };
  }, [engine]);
  const run = async (fn: () => Promise<void>) => {
    if (working.current) return;
    working.current = true; setBusy(true);
    try { await fn(); } catch (e) { setStatus('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { working.current = false; setBusy(false); }
  };
  const refresh = async () => { const d = await sheetRequest<SheetDetail>(`/${encodeURIComponent(current.current.document.id)}`); publish(d); return d; };
  const save = () => void run(async () => {
    const d = await capture();
    if (!d.session) throw new Error('작성 세션이 없습니다');
    await sheetCommand(d.document.id, 'save', { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), expected_revision: d.document.revision_id });
    const next = await refresh();
    setDirty(false); setStatus('저장됨 · 원본 파일 기록 확인');
    emit('saved', { revision: next.document.revision_id });
  });
  // `[self:workspace]` 스냅샷 — 초안을 올린 뒤 engine_state(격자가 만든 값·수식·서식 JSON)를 고정한다.
  const takeSnapshot = async (): Promise<SheetSnapshot> => {
    const d = await capture();
    if (!d.session || !engine) throw new Error('작성 세션이 없습니다');
    const snap = await sheetCommand<SheetSnapshot>(d.document.id, 'snapshot', { ...sessionArgs(d.session), engine_state: engine.engineState(), calculation: 'fresh' });
    return snap;
  };
  // 접수된 제안 적용(플러그인 apply 와 같은 계약) — 제안 이후 격자가 바뀌었으면 거절.
  const applyCommand = (cmd: Result): Result => {
    if (!engine) return { error: '격자가 없습니다', applied: false };
    if (cmd.engine_state !== engine.engineState()) return { error: '제안 이후 셀·시트 구조가 바뀌었습니다. 스냅샷을 다시 만드세요', applied: false };
    const range = parseRange(String(cmd.range || '')); const values = cmd.values as (string | number | boolean | null)[][];
    if (!range || !Array.isArray(values) || !values.length) return { error: '대상 범위 또는 값이 없습니다', applied: false };
    const sel: Selection = { sheet: String(cmd.sheet_name), range: String(cmd.range), rows: range.r2 - range.r1 + 1, cols: range.c2 - range.c1 + 1, ...range };
    if (values.length !== sel.rows || values.some((r) => r.length !== sel.cols)) return { error: '수정 값의 행열 수가 다릅니다', applied: false };
    if (sel.rows * sel.cols > CELL_CAP) return { error: '수정 범위 상한(10,000셀)을 확인하세요', applied: false };
    const kind = String(cmd.kind);
    try {
      if (kind === 'restore_cells') engine.setValues(sel, values.map((row) => row.map((v) => { const e = v as unknown as { formula?: string; value?: unknown }; return (e?.formula || ((e?.value as string | number | boolean | null) ?? null)); })));
      else engine.setValues(sel, values, kind === 'set_formulas');
    } catch (e) { return { error: String(e), applied: false }; }
    return { applied: true, affected_cells: sel.rows * sel.cols, calculation: 'fresh' };
  };
  // pending 큐 소비 — 시스템 AI·IBL 이 접수한 snapshot/save/apply.
  useEffect(() => {
    if (!engine) return;
    let stopped = false;
    const completed = new Map<string, Result>();
    const timer = setInterval(() => {
      const d = current.current;
      if (stopped || working.current || !d.session || !engine.loaded) return;
      void (async () => {
        const queue = await sheetCommand<{ id: string; command: Result }[]>(d.document.id, 'pending', sessionArgs(d.session!)).catch(() => []);
        if (!queue.length || stopped || working.current) return;
        await run(async () => {
          for (const op of queue) {
            let result = completed.get(op.id);
            if (!result) {
              try {
                if (op.command.kind === 'snapshot') result = { snapshot: await takeSnapshot(), completed: true };
                else if (op.command.kind === 'save') {
                  const captured = await capture();
                  result = await sheetCommand<Result>(d.document.id, 'save', { ...sessionArgs(captured.session!), expected_revision: op.command.expected_revision, operation_id: String(op.command.operation_id) });
                  await refresh(); setDirty(false);
                } else {
                  const captured = await capture();
                  await sheetCommand(d.document.id, 'preflight', { ...sessionArgs(captured.session!), operation_id: op.id });
                  result = applyCommand(op.command);
                  if (result.applied) { try { result.snapshot_id = (await takeSnapshot()).id; } catch (e) { result.capture_warning = String(e); } }
                }
              } catch (e) { result = { error: e instanceof Error ? e.message : String(e), applied: false }; }
              completed.set(op.id, result);
            }
            result = await sheetCommand<Result>(d.document.id, 'receipt', { ...sessionArgs(current.current.session!), operation_id: op.id, result });
            completed.set(op.id, result);
            if (result.applied) setStatus('변경 묶음 적용됨 · 원본 저장 전'); else if (result.error) throw new Error(String(result.error));
          }
        });
      })().catch((e) => { if (!stopped) setStatus('⚠️ ' + (e instanceof Error ? e.message : String(e))); });
    }, 1500);
    return () => { stopped = true; clearInterval(timer); };
  }, [engine]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── AI 작업창: 선택(없으면 사용 범위 전체) → 독 action → 제안(values 2차원) 미리보기 → 반영 ── */
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [input, setInput] = useState('');
  const dock = host.dock;
  const ask = async () => {
    const instruction = input.trim();
    if (!instruction || asking || !engine?.loaded || !dock) return;
    setAsking(true); setAnswer(null); setProposal(null); engine.clearHighlight();
    try {
      const d = await capture();
      const picked = engine.selection();
      const sel = picked && (picked.rows > 1 || picked.cols > 1) ? picked : engine.usedSelection() || picked;
      if (!sel) throw new Error('표에 내용이 없습니다');
      if (sel.rows * sel.cols > (picked === sel ? CELL_CAP : WHOLE_CAP)) throw new Error('범위가 큽니다 — 범위를 골라 주세요');
      const table = engine.cellsForAI(sel, WHOLE_CAP);  // 수식이 있으면 수식 — 제안의 "그대로" 셀을 수식째 지킨다
      const text = table.map((row) => row.map((c) => (c == null ? '' : String(c))).join('\t')).join('\n');
      const out = await runIBL(actionRequest(host.block, dock.action, {
        ...(host.vars || {}), resource: d.document.id, revision: d.document.revision_id,
        sel: { sheet: sel.sheet, range: sel.range }, sheet: sel.sheet, range: sel.range, table, text, dock: instruction,
      }));
      const values = findValues(out);
      if (!values) { setAnswer(textOf(out)); return; }
      if (values.length !== sel.rows || values.some((r) => !Array.isArray(r) || r.length !== sel.cols)) throw new Error(`제안의 행·열 수(${values.length}×${values[0]?.length ?? 0})가 선택 범위(${sel.rows}×${sel.cols})와 다릅니다`);
      const changes: Proposal['changes'] = [];
      values.forEach((row, i) => row.forEach((v, j) => { const b = table[i][j]; if (String(b ?? '') !== String(v ?? '')) changes.push({ addr: a1(sel.r1 + i, sel.c1 + j), from: show(b), to: show(v) }); }));
      setProposal({ sel, before: table, values, changes });
      engine.highlightCells(sel, changes.map((c) => c.addr));
      setInput('');
    } catch (e) { setAnswer('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { setAsking(false); }
  };
  const applyProposal = () => {
    try { applyProposalInner(); } catch (e) { console.error('[sheet] 제안 반영 실패', e); setAnswer('⚠️ 반영 실패 — ' + (e instanceof Error ? e.message : String(e))); }
  };
  const applyProposalInner = () => {
    if (!proposal || !engine?.loaded) return;
    const now = engine.cellsForAI(proposal.sel, WHOLE_CAP);
    if (JSON.stringify(now) !== JSON.stringify(proposal.before)) { setAnswer('⚠️ 요청한 뒤 그 범위가 바뀌어 반영하지 않았습니다 — 다시 요청하세요'); engine.clearHighlight(); setProposal(null); return; }
    const cells: { row: number; col: number; value: string | number | boolean | null }[] = [];
    proposal.values.forEach((row, i) => row.forEach((v, j) => { if (String(proposal.before[i][j] ?? '') !== String(v ?? '')) cells.push({ row: proposal.sel.r1 + i, col: proposal.sel.c1 + j, value: v }); }));
    try { engine.applyCells(proposal.sel, cells); } catch (e) { setAnswer('⚠️ ' + (e instanceof Error ? e.message : String(e))); return; }
    engine.clearHighlight(); setProposal(null);
    setTimeout(() => setStatus('AI 제안 반영됨 (Ctrl+Z 로 되돌리기) · 원본 저장 전'), 0);  // 변경 이벤트의 '수정됨' 뒤에 쓴다
  };
  const closeProposal = () => { engine?.clearHighlight(); setProposal(null); setAnswer(null); };
  const sel = engine?.loaded ? engine.selection() : null;
  const pane: ReactNode | null = dock ? (
    <div className="xl-pane-body">
      <div><span className="xl-chip">{sel && (sel.rows > 1 || sel.cols > 1) ? `선택: ${sel.sheet}!${sel.range} · ${(sel.rows * sel.cols).toLocaleString()}셀` : '선택 없음 → 사용 범위 전체'}</span></div>
      <div className="xl-ask">
        <textarea aria-label="AI 요청" value={input} disabled={asking} placeholder={dock.placeholder || '예: 구분이 "경비"인 행의 금액을 지출 열로 옮겨 줘 (Enter 전송)'} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void ask(); } }} />
        <small>{asking ? 'AI가 생각 중…' : 'Enter 전송 · Shift+Enter 줄바꿈 · 값·수식 2차원이 오면 미리보기, 글이 오면 답으로'}</small>
      </div>
      {proposal && (
        <div className="xl-proposal">
          <div className="xl-ptitle">제안 — 바뀌는 셀 {proposal.changes.length.toLocaleString()}개{proposal.changes.length ? ' (격자에 노란 미리보기)' : ' — 지금과 같습니다'}</div>
          <ul>{proposal.changes.slice(0, 200).map((c) => <li key={c.addr}>{c.addr} <b>→ {c.to}</b> <span style={{ color: '#888' }}>({c.from})</span></li>)}{proposal.changes.length > 200 && <li>… 외 {(proposal.changes.length - 200).toLocaleString()}개</li>}</ul>
          <div className="xl-acts"><button type="button" className="p" disabled={!proposal.changes.length} onClick={applyProposal}>반영</button><button type="button" className="g" onClick={closeProposal}>닫기</button></div>
        </div>
      )}
      {answer && <div className="xl-proposal"><div className="xl-answer">{answer}</div><div className="xl-acts"><button type="button" className="g" onClick={closeProposal}>닫기</button></div></div>}
      <p className="xl-hint">반영은 평소 편집과 같은 길입니다 — Ctrl+Z 로 되돌리고, 자동 초안·Ctrl+S 저장을 거칩니다. 요청 뒤 격자가 바뀌면 제안은 버려집니다.</p>
    </div>
  ) : null;

  const backstage = (close: () => void) => <Backstage detail={detail} menu={host.menu ?? null} close={close} capture={capture} takeSnapshot={takeSnapshot} refresh={refresh} engine={engine} onOffice={onOffice} setStatus={setStatus} busy={busy} />;
  return <ExcelFrame engine={engine} tick={tick} hostRef={hostRef} title={detail.document.title} dirty={dirty} status={status} busy={busy} overlay={overlay}
    onSave={save} backstage={backstage} pane={pane} paneOpen={paneOpen} onPane={setPaneOpen} />;
}

/* ── 파일 탭(백스테이지): 계기 모드 탭 + 엔진 도구(정보·버전·사본·변환·보고서·사무 편집기) ── */
function Backstage({ detail, menu, close, capture, takeSnapshot, refresh, engine, onOffice, setStatus, busy }: {
  detail: SheetDetail; menu: InstrumentMenu | null; close: () => void; capture: () => Promise<SheetDetail>; takeSnapshot: () => Promise<SheetSnapshot>;
  refresh: () => Promise<SheetDetail>; engine: GridEngine | null; onOffice?: () => void; setStatus: (s: string) => void; busy: boolean;
}) {
  const [section, setSection] = useState<'info' | 'copy' | 'versions' | 'report' | 'office'>('info');
  const [filename, setFilename] = useState('사본_' + detail.document.title);
  const [versions, setVersions] = useState<{ id: string; created_at: number; label?: string }[] | null>(null);
  const [msg, setMsg] = useState('');
  const [working, setWorking] = useState(false);
  const guard = async (fn: () => Promise<void>) => { if (working) return; setWorking(true); setMsg(''); try { await fn(); } catch (e) { setMsg('⚠️ ' + (e instanceof Error ? e.message : String(e))); } finally { setWorking(false); } };
  const modes = menu && menu.modes.some(Boolean) ? menu.modes : [];
  return (
    <>
      <nav>
        <button type="button" className="back" aria-label="뒤로" onClick={close}>←</button>
        {modes.map((n, i) => n && <button key={i} type="button" onClick={() => { close(); menu!.go(i); }}>{n}</button>)}
        {modes.length > 0 && <div style={{ height: 1, background: 'rgba(255,255,255,.25)', margin: '6px 0' }} />}
        <button type="button" className={section === 'info' ? 'on' : ''} onClick={() => setSection('info')}>정보</button>
        <button type="button" className={section === 'copy' ? 'on' : ''} onClick={() => setSection('copy')}>다른 이름으로 · 변환</button>
        <button type="button" className={section === 'versions' ? 'on' : ''} onClick={() => { setSection('versions'); void guard(async () => setVersions((await sheetRequest<{ items: { id: string; created_at: number; label?: string }[] }>(`/${detail.document.id}/versions`)).items)); }}>버전</button>
        <button type="button" className={section === 'report' ? 'on' : ''} onClick={() => setSection('report')}>문서에 표 보고서</button>
        {onOffice && <button type="button" className={section === 'office' ? 'on' : ''} onClick={() => setSection('office')}>사무 편집기</button>}
      </nav>
      <section>
        {section === 'info' && <>
          <h2>정보</h2>
          <div className="xl-card"><h3>{detail.document.title}</h3><p>{detail.document.source_uri}</p><p>엔진: 브라우저 격자 · {detail.session?.state === 'draft' ? '원본에 저장되지 않은 작업 초안이 있습니다' : '원본과 같습니다'}</p></div>
          <div className="xl-card"><h3>이 통합문서로 할 수 있는 일</h3><p>셀·수식·서식·병합·틀 고정·정렬·필터·찾기. 차트·피벗·그림이 필요하면 왼쪽 "사무 편집기".</p></div>
        </>}
        {section === 'copy' && <>
          <h2>다른 이름으로 · 변환</h2>
          <div className="xl-card"><h3>같은 형식 사본</h3><div className="xl-row"><input type="text" aria-label="사본 이름" value={filename} onChange={(e) => setFilename(e.target.value)} />
            <button type="button" className="act" disabled={working || busy} onClick={() => void guard(async () => { const d = await capture(); if (!d.session) throw new Error('작성 세션이 없습니다'); const r = await sheetCommand<{ path: string }>(d.document.id, 'export', { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), filename }); setMsg('사본 저장됨: ' + r.path); })}>사본 저장</button></div></div>
          <div className="xl-card"><h3>다른 형식 사본(ods·xltx·ots·fods)</h3><p>원본은 그대로 두고 새 자료를 만듭니다. 만든 사본은 "열기"로 엽니다.</p>
            <SpreadsheetConversion key={'conv-' + detail.document.id} detail={detail} beforeConvert={async () => { await capture(); }} onConverted={async (d) => { setMsg('사본이 만들어졌습니다: ' + d.document.title + ' — ' + d.document.source_uri); }} onBusyChange={() => undefined} disabled={working || busy} /></div>
        </>}
        {section === 'versions' && <>
          <h2>버전</h2>
          <div className="xl-card"><h3>저장 버전 되살리기</h3><p>고른 버전이 작업 초안이 됩니다(원본은 저장을 눌러야 바뀝니다).</p>
            {versions === null ? <p>읽는 중…</p> : versions.length === 0 ? <p>저장 버전이 없습니다.</p> : <div className="xl-row">{versions.map((v) => (
              <button key={v.id} type="button" className="act g" disabled={working || busy} onClick={() => void guard(async () => {
                const d = await capture(); if (!d.session) throw new Error('작성 세션이 없습니다');
                await sheetCommand(d.document.id, 'restore', { ...sessionArgs(d.session), revision_id: v.id, operation_id: crypto.randomUUID() });
                const next = await refresh(); const r = await sheetCommand<{ grid: GridWorkbook }>(next.document.id, 'grid', {}); engine?.load(r.grid); setStatus('버전을 되살렸습니다 · 작업 초안'); close();
              })}>{new Date(v.created_at * 1000).toLocaleString()} {v.label || '저장 버전'}</button>))}</div>}</div>
        </>}
        {section === 'report' && <>
          <h2>문서에 표 보고서</h2>
          <div className="xl-card"><h3>선택 범위(없으면 사용 범위)를 마크다운 표 보고서로</h3><p>고정된 스냅샷에서 만들고 출처(원본 버전·범위·계산 상태)를 남깁니다. 문서 앱에서 열 수 있습니다.</p>
            <div className="xl-row"><button type="button" className="act" disabled={working || busy || !engine?.loaded} onClick={() => void guard(async () => {
              const e = engine!; const picked = e.selection(); const sel = picked && (picked.rows > 1 || picked.cols > 1) ? picked : e.usedSelection() || picked; if (!sel) throw new Error('표에 내용이 없습니다');
              const snap = await takeSnapshot();
              const sheetId = detail.workbook.sheets?.find((s) => s.name === sel.sheet)?.sheet_id || (await refresh()).workbook.sheets?.find((s) => s.name === sel.sheet)?.sheet_id;
              if (!sheetId) throw new Error('시트를 찾지 못했습니다: ' + sel.sheet);
              const r = await sheetCommand<{ document: { title: string; source_uri: string } }>(detail.document.id, 'report', { snapshot_id: snap.id, sheet_id: sheetId, range: rangeA1(sel.r1, sel.c1, sel.r2, sel.c2), operation_id: crypto.randomUUID(), allow_stale: false, linked: false });
              setMsg('보고서 문서를 만들었습니다: ' + r.document.source_uri);
            })}>보고서 만들기</button><button type="button" className="act g" onClick={() => openDocuments()}>문서 앱 열기</button></div></div>
        </>}
        {section === 'office' && onOffice && <>
          <h2>사무 편집기</h2>
          <div className="xl-card"><h3>ONLYOFFICE 로 열기</h3><p>차트·피벗·그림·인쇄 설정이 필요할 때. 같은 작업 초안을 이어서 편집하며, 격자로 돌아올 수 있습니다.</p>
            <div className="xl-row"><button type="button" className="act" disabled={working || busy} onClick={() => void guard(async () => { await capture(); close(); onOffice(); })}>사무 편집기로 열기</button></div></div>
        </>}
        {msg && <p role="status" className={msg.startsWith('⚠️') ? 'warn' : ''}>{msg}</p>}
      </section>
    </>
  );
}

/* AI 응답에서 2차원 값 배열을 찾는다 — [table:ai] 의 items[0].values / values / result.values, 또는 응답 자체가 2차원. */
function findValues(out: unknown): (string | number | boolean | null)[][] | null {
  const is2d = (v: unknown): v is (string | number | boolean | null)[][] => Array.isArray(v) && v.length > 0 && v.every((r) => Array.isArray(r) && r.every((c) => c === null || ['string', 'number', 'boolean'].includes(typeof c)));
  const raw = out && typeof out === 'object' ? (out as Record<string, unknown>) : null;
  const o = raw && raw.value && typeof raw.value === 'object' && !Array.isArray(raw.value) ? (raw.value as Record<string, unknown>) : raw;  // 풀리지 않은 판본 2 봉투도 받는다
  const candidates: unknown[] = [out, o?.values, o?.result, (o?.result as Record<string, unknown> | undefined)?.values, o?.table];
  const items = (o?.items ?? (o?.result as Record<string, unknown> | undefined)?.items) as unknown;
  if (Array.isArray(items) && items.length === 1 && items[0] && typeof items[0] === 'object') candidates.push((items[0] as Record<string, unknown>).values, (items[0] as Record<string, unknown>).cells, (items[0] as Record<string, unknown>).rows);
  for (const c of candidates) if (is2d(c)) return c;
  const tbl = (o?.table as Record<string, unknown> | undefined)?.rows;
  return is2d(tbl) ? tbl : null;
}
function textOf(out: unknown): string {
  if (typeof out === 'string') return out || '(빈 응답)';
  const o = out && typeof out === 'object' ? (out as Record<string, unknown>) : null;
  if (o?.error || o?.success === false) return '⚠️ ' + String(o.error || o.message || '실패');
  const v = o?.result ?? o?.text ?? o?.answer ?? o?.message;
  if (typeof v === 'string' && v) return v;
  const items = o?.items as unknown;
  if (Array.isArray(items) && items.length && typeof items[0] === 'object') { const f = items[0] as Record<string, unknown>; const t = f.text ?? f.answer ?? f.result; if (typeof t === 'string') return t; }
  return v != null && typeof v !== 'object' ? String(v) : JSON.stringify(out).slice(0, 2000);
}
