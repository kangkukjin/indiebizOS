/* engine 뷰 프리미티브 (2026-10-05, docs/APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md §3-c)
 *
 * 외부 편집 엔진 표면을 `ref`(작업 공간 자료 ID)로 바인딩한다. 어떤 엔진을 띄울지는 자료의
 * capabilities(office / rhwp / source / 시트)가 정한다 — 선언은 "이 자료를 편집 표면으로 보여라"뿐.
 * 사용자 조작은 뷰-이벤트로 흘린다(상호작용도 데이터):
 *   · selection — 선택 고정: $sel(selector Record)·$start/$end(Number)/$text(원문) · $sheet/$range(시트) · $resource/$revision
 *   · saved     — 원본 저장 완료: $resource/$revision
 * on: 의 템플릿이 없거나 'keep' 이면 페이로드를 $변수로만 남긴다(이후 ai_dock·버튼·폼이 쓴다).
 * ai_dock(2026-10-05, docs/DOCUMENT_APP_ON_BINNOTE_PLAN_2026_10_05.md): 캔버스 아래 AI 한 줄. action 은
 *   $resource/$sel/$start/$end/$text(선택이 없으면 글 전체)/$dock(요청)을 받아 본문을 돌려주고, 반영은 엔진이
 *   사람의 편집으로 캔버스에 넣는다 — 초안·저장·버전은 평소 편집과 같은 길. 지금은 원문 엔진만 독을 띄운다.
 * 편집기 컴포넌트(Office/Hwp/Spreadsheet)는 이 낱말 밑의 바인딩이다 — escape 가 아니다. */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { AppViewPrim, AppFormField, AppMode, ViewEvent } from './manifest';
import { jget, tpl, actionRequest, runIBL, suggestionText } from './manifest';
import { AiDockPanel } from './prims-edit';
import { documentCommand, documentRequest, sessionArgs, PREVIEWABLE, type Detail } from '../../lib/api-documents';
import { sheetCommand, sheetRequest, type SheetDetail } from '../../lib/api-spreadsheets';
import { OfficeDocumentEditor } from '../OfficeDocumentEditor';
import { HwpDocumentEditor } from '../HwpDocumentEditor';
import { SpreadsheetEditor } from '../spreadsheets/SpreadsheetEditor';
import './engine-editors.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { SourceTools } from './engine-source-tools';

type Dock = NonNullable<AppFormField['ai_dock']>;
type Host = { dock?: Dock; vars?: Record<string, unknown>; block?: AppMode };  // 독 선언과 그 action 이 읽을 $변수·실행 블록
type Payload = Record<string, unknown>;  // 타입 보존 — sel 은 Record, start/end 는 Number(판본 2 inputs 로 그대로 간다)
const CLIENT_KEY = 'indiebiz-engine-client';
function clientId(): string {
  try {
    const v = sessionStorage.getItem(CLIENT_KEY);
    if (v) return v;
    const fresh = 'engine-' + crypto.randomUUID();
    sessionStorage.setItem(CLIENT_KEY, fresh);
    return fresh;
  } catch { return 'engine-' + crypto.randomUUID(); }
}

export function EnginePrim({ p, data, onViewEvent, vars, block }: {
  p: AppViewPrim; data: unknown; onViewEvent?: ViewEvent; vars?: Record<string, unknown>; block?: AppMode;
}) {
  const ref = tpl(String(p.ref || ''), data).trim();
  const kind = (p.kind ? tpl(String(p.kind), data) : String(jget(data, 'kind') ?? '')).trim();
  const on = (p.on as Record<string, string> | undefined) || {};
  const emit = useCallback((event: 'selection' | 'saved', payload: Payload) => {
    onViewEvent?.(on[event] || 'keep', { resource: ref, ...payload });
  }, [on, onViewEvent, ref]);
  if (!ref) return <p className="text-sm text-stone-400">열 자료가 없습니다 — <code>[self:workspace]{'{op:"open"}'}</code> 결과의 <code>resource</code> 를 <code>ref</code> 로 주세요.</p>;
  if (kind === 'code') return <p className="text-sm text-stone-400">코딩 작업 공간은 엔진 표면이 없습니다 — <code>blocks</code>(diff·파일)와 <code>selection</code> 으로 봅니다.</p>;
  if (kind === 'sheet') return <SheetEngine id={ref} emit={emit} />;
  return <DocumentEngine id={ref} emit={emit} host={{ dock: p.ai_dock as Dock | undefined, vars, block }} />;
}

/* ── 문서: capabilities.engine 으로 office / rhwp / source 를 고른다 ── */
function DocumentEngine({ id, emit, host }: { id: string; emit: (e: 'selection' | 'saved', p: Payload) => void; host: Host }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [me] = useState(clientId);
  const capture = useRef<(() => Promise<unknown>) | null>(null);
  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        let d = await documentRequest<Detail>(`/${encodeURIComponent(id)}`);
        if (d.capabilities.edit_native && (!d.session || d.session.client_id !== me)) {
          d = await documentCommand<Detail>(id, 'sessions', { client_id: me });
        }
        if (!dead) setDetail(d);
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); }
    })();
    return () => { dead = true; };
  }, [id, me]);
  if (error) return <p role="alert" className="text-sm text-red-600">{error}</p>;
  if (!detail) return <p className="text-sm text-stone-400">편집 표면을 여는 중…</p>;
  const onChange = (d: Detail) => setDetail(d);
  const saved = (d: Detail) => emit('saved', { revision: d.document.revision_id });
  if (!detail.capabilities.edit_native) return <p className="text-sm text-stone-500">{detail.capabilities.reason} — 열람만 가능합니다.</p>;
  if (detail.session && detail.session.client_id !== me) return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-stone-600">
      <span>다른 작성 창이 이 문서를 쥐고 있습니다. 이 창으로 가져오면 그 창의 저장 권한이 끝납니다.</span>
      <button className="px-3 py-1.5 rounded-lg border border-stone-300 hover:border-stone-500" onClick={() => {
        const s = detail.session; if (!s) return;
        documentCommand<Detail>(id, 'reclaim', { client_id: me, expected_epoch: s.engine_epoch })
          .then(setDetail, (e) => setError(e instanceof Error ? e.message : String(e)));
      }}>이 창에서 초안 이어 쓰기</button>
    </div>
  );
  if (detail.capabilities.engine === 'rhwp')
    return <div className="engine-editor"><HwpDocumentEditor key={`${detail.document.id}:${detail.session?.engine_epoch}`} detail={detail} onChange={onChange}
      captureRef={capture as never} onSaved={saved} /></div>;
  if (detail.capabilities.engine === 'office')
    return <div className="engine-editor"><OfficeDocumentEditor key={detail.document.id} detail={detail} onChange={onChange} captureRef={capture as never}
      onSelection={(sel) => emit('selection', { sel: { bookmark: sel.bookmark }, text: sel.text, revision: detail.document.revision_id })}
      onSaved={saved} /></div>;
  return <SourceEngine detail={detail} onChange={onChange} emit={emit} host={host} />;
}

/* ── 원문(TXT/MD/HTML/LaTeX…): 넓은 캔버스 + 자동 초안(작업 저장) + 원본 저장 + AI 독. ──
 * 캔버스는 줄바꿈을 \n 으로만 보여 주고 서버에는 원본의 줄바꿈으로 되돌려 보낸다. 선택 주소는 서버가 세는
 * 단위(코드포인트, 원본 줄바꿈 기준)로 내보낸다. 줄바꿈이 섞인 문서는 원문 보호를 위해 열람만. */
const cp = (text: string) => Array.from(text).length;
function newlineOf(source: string): { nl: string; mixed: boolean } {
  const crlf = (source.match(/\r\n/g) || []).length;
  const rest = source.replace(/\r\n/g, '');
  const lf = (rest.match(/\n/g) || []).length;
  return { nl: crlf && !lf ? '\r\n' : '\n', mixed: rest.includes('\r') || !!(crlf && lf) };
}

function SourceEngine({ detail, onChange, emit, host }: {
  detail: Detail; onChange: (d: Detail) => void; emit: (e: 'selection' | 'saved', p: Payload) => void; host: Host;
}) {
  const source = detail.text ?? '';
  const style = useRef(newlineOf(source));
  const toView = (v: string) => (style.current.mixed ? v : v.replace(/\r\n/g, '\n'));
  const toSource = (v: string) => (style.current.nl === '\n' ? v : v.replace(/\n/g, style.current.nl));
  const [text, setText] = useState(() => toView(source));
  const [message, setMessage] = useState('원본을 읽었습니다');
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState(0);            // 지금 선택된 글자 수(독이 무엇을 고칠지 보여 준다)
  const [undo, setUndo] = useState<string | null>(null);  // AI 반영 직전 본문(한 번 되돌리기)
  const [scope, setScope] = useState<'선택' | '전체'>('전체');
  const [tools, setTools] = useState(false);          // ⚙ 도구 패널(사본·변환·버전·연결) — 평소엔 접어 둔다
  const [preview, setPreview] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const live = useRef(text); live.current = text;
  const acknowledged = useRef(text);                  // 서버 초안과 같은 본문
  const range = useRef({ a: 0, b: 0 });               // 캔버스 선택(포커스가 독으로 옮겨가도 남는다)
  const pinned = useRef<{ a: number; b: number; before: string } | null>(null);  // 독 요청 때 고정한 범위
  const composing = useRef(false);
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const current = useRef(detail); current.current = detail;
  const writable = !style.current.mixed && !!detail.session;
  const adopt = (d: Detail) => {  // 서버가 준 본문을 캔버스의 기준으로 삼는다(열기·세션 교체·버전 복구)
    style.current = newlineOf(d.text ?? '');
    const v = toView(d.text ?? '');
    setText(v); live.current = v; acknowledged.current = v;
    range.current = { a: 0, b: 0 }; pinned.current = null; setPicked(0); setUndo(null);
  };
  useEffect(() => { adopt(detail); setPreview(false); }, [detail.document.id, detail.session?.engine_epoch]); // eslint-disable-line react-hooks/exhaustive-deps

  // 초안 저장은 한 줄로 세운다 — 세션 개정 번호(expected)를 물고 가므로 겹치면 뒤의 것이 거절된다.
  const draft = useCallback((): Promise<Detail> => {
    const task = chain.current.catch(() => undefined).then(async () => {
      const d = current.current, value = live.current;
      if (!d.session) throw new Error('작성 세션이 없습니다');
      if (acknowledged.current === value) return d;
      const result = await documentCommand<{ session: Detail['session'] }>(d.document.id, 'draft',
        { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), text: toSource(value) });
      acknowledged.current = value;
      const next = { ...d, session: result.session, text: toSource(value) };
      current.current = next; onChange(next);
      return next;
    });
    chain.current = task;
    return task;
  }, [onChange]);

  // 자동 초안 — 창을 잘못 닫아도 글이 남는다(서버 초안. 원본은 그대로).
  useEffect(() => {
    if (!writable || text === acknowledged.current) return;
    const timer = setTimeout(() => {
      if (composing.current) return;
      draft().then(() => { if (live.current === acknowledged.current) setMessage('작업 저장됨 · 원본에는 저장되지 않음'); },
        (e) => setMessage('⚠️ 작업 저장 실패 — ' + (e instanceof Error ? e.message : String(e))));
    }, 900);
    return () => clearTimeout(timer);
  }, [text, writable, draft]);

  const run = async (fn: () => Promise<void>) => {
    if (busy || composing.current) return;
    setBusy(true);
    try { await fn(); } catch (e) { setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { setBusy(false); }
  };
  const save = () => void run(async () => {
    const d = await draft();
    if (!d.session) throw new Error('작성 세션이 없습니다');
    await documentCommand(d.document.id, 'save', { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), expected_revision: d.document.revision_id });
    const next = await documentRequest<Detail>(`/${d.document.id}`);
    current.current = next; onChange(next);
    setMessage('저장됨 · 원본 파일 기록 확인');
    emit('saved', { revision: next.document.revision_id });
  });
  const replaceFrom = (next: Detail) => { current.current = next; onChange(next); adopt(next); };
  // 선택은 요청하는 순간 캔버스에서 직접 읽는다 — 포커스가 독·도구로 옮겨가도 textarea 는 선택을 쥐고 있다.
  const selected = () => {
    const el = editor.current;
    if (el) range.current = { a: el.selectionStart, b: el.selectionEnd };
    return range.current;
  };
  const pick = () => {
    const { a, b } = selected();
    return a === b ? null : { ...address(a, b), text: toSource(live.current.slice(a, b)) };
  };
  const address = (a: number, b: number) => {  // 캔버스 범위 → 서버 주소(코드포인트·원본 줄바꿈)
    const start = cp(toSource(live.current.slice(0, a)));
    return { start, end: start + cp(toSource(live.current.slice(a, b))) };
  };
  const track = () => {
    const el = editor.current; if (!el) return;
    range.current = { a: el.selectionStart, b: el.selectionEnd };
    setPicked(cp(el.value.slice(el.selectionStart, el.selectionEnd)));
  };
  const select = () => {
    track();
    const { a, b } = range.current;
    if (a === b) return;
    const at = address(a, b);
    emit('selection', { sel: at, ...at, text: toSource(live.current.slice(a, b)), revision: current.current.document.revision_id });
  };
  const edit = (value: string) => { setText(value); live.current = value; setMessage('수정됨 · 원본에는 저장되지 않음'); };
  const rewrite = (value: string) => {  // AI 반영·되돌리기 — 글이 통째로 바뀌므로 이전 선택 범위는 버린다
    setUndo(live.current); edit(value);
    range.current = { a: 0, b: 0 }; pinned.current = null; setPicked(0);
  };

  // 독 — 선택이 있으면 선택만, 없으면 글 전체를 묻는다. 묻기 전에 초안을 올려 자료를 읽는 action 도 같은 글을 본다.
  const ask = async (instruction: string) => {
    if (!host.dock) return '';
    if (writable) await draft();
    const value = live.current, now = selected();
    const has = now.a !== now.b;
    const a = has ? now.a : 0, b = has ? now.b : value.length;
    pinned.current = { a, b, before: value.slice(a, b) };
    setScope(has ? '선택' : '전체');
    const at = address(a, b);
    return suggestionText(await runIBL(actionRequest(host.block, host.dock.action, {
      ...(host.vars || {}), resource: current.current.document.id, revision: current.current.document.revision_id,
      sel: at, ...at, text: toSource(value.slice(a, b)), dock: instruction,
    })));
  };
  const applySuggestion = (mode: 'replace' | 'append', suggestion: string) => {
    const s = toView(suggestion), value = live.current, pin = pinned.current;
    if (mode === 'append') { rewrite(value.trim() ? `${value}\n\n${s}` : s); return; }
    if (!pin || value.slice(pin.a, pin.b) !== pin.before) { setMessage('⚠️ 요청한 뒤 그 자리의 글이 바뀌어 반영하지 않았습니다 — 다시 요청하세요'); return; }
    // 고른 범위 양 끝의 공백·줄바꿈은 원문 것을 지킨다 — 문단째 고르면 끝 줄바꿈이 딸려 오고 AI 는 그것을 떼고 답한다.
    const lead = /^\s*/.exec(pin.before)![0], trail = /\s*$/.exec(pin.before.slice(lead.length))![0];
    rewrite(value.slice(0, pin.a) + lead + s.trim() + trail + value.slice(pin.b));
  };
  const dirty = text !== toView(source) || detail.session?.state === 'draft';
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-stone-800 truncate max-w-[40%]" title={detail.document.source_uri}>{detail.document.title}</span>
        {dirty && <span className="text-xs text-amber-600 shrink-0">● 원본 저장 안 됨</span>}
        <span role="status" className="text-xs text-stone-500 truncate">{message}</span>
        <div className="flex-1" />
        <span className="text-xs text-stone-400 shrink-0">{picked ? `선택 ${picked.toLocaleString()}자 · ` : ''}{cp(text).toLocaleString()}자</span>
        {undo != null && <button disabled={busy} onClick={() => { rewrite(undo); setUndo(null); }}
          className="px-2.5 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-100">AI 반영 되돌리기</button>}
        <button onClick={() => setTools((v) => !v)} title="사본·변환·버전·시트 표 연결"
          className={`px-2.5 py-1.5 rounded-lg text-sm hover:bg-stone-100 ${tools ? 'bg-stone-100 text-stone-800' : 'text-stone-600'}`}>⚙ 도구</button>
        <button disabled={busy || !writable} onClick={save}
          className="px-3 py-1.5 rounded-lg text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-40">저장</button>
      </div>
      {tools && <SourceTools detail={detail} text={text} busy={busy} writable={writable} run={run} draft={draft} pick={pick}
        replaceFrom={replaceFrom} setMessage={setMessage} preview={preview} setPreview={setPreview} />}
      {style.current.mixed && <p role="alert" className="text-sm text-amber-700">줄바꿈이 섞인 문서입니다. 원문을 보호하기 위해 이 화면의 편집을 막습니다.</p>}
      {preview && PREVIEWABLE.includes(detail.document.source_format) && (
        ['md', 'markdown'].includes(detail.document.source_format)
          ? <div className="engine-preview w-full min-h-[calc(100vh-320px)] bg-white rounded-xl shadow-sm border border-stone-200 px-10 py-9 text-[15px] leading-8">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span>[그림: {alt || '첨부 이미지'}]</span> }}>{text}</ReactMarkdown>
            </div>
          : <iframe title="HTML 비실행 미리보기" sandbox="" className="w-full min-h-[calc(100vh-320px)] bg-white rounded-xl border border-stone-200"
              srcDoc={`<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'"><style>body{font:16px/1.7 sans-serif;padding:24px;overflow-wrap:anywhere}</style>${text}`} />
      )}
      <textarea ref={editor} aria-label="문서 원문" hidden={preview} spellCheck={false} value={text} readOnly={!writable}
        placeholder="여기에 자유롭게 글을 쓰세요…"
        onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
        onChange={(e) => edit(e.target.value)} onSelect={track}
        onMouseUp={select} onKeyUp={(e) => { if (e.shiftKey || e.key.startsWith('Arrow')) select(); }}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save(); } }}
        className="w-full min-h-[calc(100vh-320px)] resize-none bg-white rounded-xl shadow-sm border border-stone-200 px-10 py-9 text-[15px] leading-8 outline-none focus:border-amber-300"
        style={{ fontFamily: "'Noto Serif KR', serif" }} />
      {host.dock && writable && (
        <div className="sticky bottom-0 -mx-1 px-1 pb-2 bg-stone-50/95 backdrop-blur">
          <AiDockPanel dock={{ ...host.dock, placeholder: host.dock.placeholder || (picked ? `선택한 ${picked.toLocaleString()}자를 AI에게 — 예: 더 간결하게 (Enter 전송)` : '글 전체를 AI에게 — 예: 문장을 다듬어줘 (Enter 전송)') }}
            ask={ask} onApply={applySuggestion} applyLabel={`반영 (${scope} 대체)`} />
        </div>
      )}
    </div>
  );
}

/* ── 시트: 엔진 편집기 + 범위 선택 고정 바 ── */
function SheetEngine({ id, emit }: { id: string; emit: (e: 'selection' | 'saved', p: Payload) => void }) {
  const [detail, setDetail] = useState<SheetDetail | null>(null);
  const [error, setError] = useState('');
  const [sheet, setSheet] = useState('');
  const [range, setRange] = useState('A1:D10');
  const client = useRef(clientId());
  const capture = useRef<null | (() => Promise<void>)>(null);
  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        let d = await sheetRequest<SheetDetail>(`/${encodeURIComponent(id)}`);
        if (d.capabilities.edit_native && (!d.session || d.session.client_id !== client.current)) {
          d = await sheetCommand<SheetDetail>(id, 'sessions', { client_id: client.current });
        }
        if (!dead) { setDetail(d); setSheet(d.workbook.sheets?.[0]?.name || ''); }
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); }
    })();
    return () => { dead = true; };
  }, [id]);
  if (error) return <p role="alert" className="text-sm text-red-600">{error}</p>;
  if (!detail) return <p className="text-sm text-stone-400">시트 편집 표면을 여는 중…</p>;
  const fix = () => emit('selection', { sel: { sheet, range }, sheet, range, revision: detail.document.revision_id });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select value={sheet} onChange={(e) => setSheet(e.target.value)} className="rounded-lg border border-stone-200 px-2 py-1">
          {(detail.workbook.sheets || []).map((s) => <option key={s.sheet_id} value={s.name}>{s.name}</option>)}
        </select>
        <input value={range} onChange={(e) => setRange(e.target.value)} className="rounded-lg border border-stone-200 px-2 py-1 w-32" aria-label="범위" />
        <button onClick={fix} className="px-3 py-1.5 rounded-lg border border-stone-300 hover:border-stone-500">범위 선택 고정</button>
      </div>
      {detail.capabilities.edit_native
        ? <SpreadsheetEditor key={detail.document.id} detail={detail} onChange={setDetail} captureRef={capture}
            onSaved={(d) => emit('saved', { revision: d.document.revision_id })} />
        : <p className="text-sm text-stone-500">{detail.capabilities.reason} — 범위 읽기·제안은 <code>[self:workspace]</code> 로 할 수 있습니다.</p>}
    </div>
  );
}
