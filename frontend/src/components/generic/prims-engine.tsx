/* engine 뷰 프리미티브 (2026-10-05, docs/APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md §3-c)
 *
 * 외부 편집 엔진 표면을 `ref`(작업 공간 자료 ID)로 바인딩한다. 어떤 엔진을 띄울지는 자료의
 * capabilities(office / rhwp / source / 시트)가 정한다 — 선언은 "이 자료를 편집 표면으로 보여라"뿐.
 * 사용자 조작은 뷰-이벤트로 흘린다(상호작용도 데이터):
 *   · selection — 선택 고정: $sel(selector Record)·$start/$end(Number)/$text(원문) · $sheet/$range(시트) · $resource/$revision
 *   · saved     — 원본 저장 완료: $resource/$revision
 * on: 의 템플릿이 없거나 'keep' 이면 페이로드를 $변수로만 남긴다(이후 ai_dock·버튼·폼이 쓴다).
 * 편집기 컴포넌트(Office/Hwp/Spreadsheet)는 이 낱말 밑의 바인딩이다 — escape 가 아니다. */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { AppViewPrim, ViewEvent } from './manifest';
import { jget, tpl } from './manifest';
import { documentCommand, documentRequest, sessionArgs, type Detail } from '../../lib/api-documents';
import { sheetCommand, sheetRequest, type SheetDetail } from '../../lib/api-spreadsheets';
import { OfficeDocumentEditor } from '../OfficeDocumentEditor';
import { HwpDocumentEditor } from '../HwpDocumentEditor';
import { SpreadsheetEditor } from '../spreadsheets/SpreadsheetEditor';

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

export function EnginePrim({ p, data, onViewEvent }: { p: AppViewPrim; data: unknown; onViewEvent?: ViewEvent }) {
  const ref = tpl(String(p.ref || ''), data).trim();
  const kind = (p.kind ? tpl(String(p.kind), data) : String(jget(data, 'kind') ?? '')).trim();
  const on = (p.on as Record<string, string> | undefined) || {};
  const emit = useCallback((event: 'selection' | 'saved', payload: Payload) => {
    onViewEvent?.(on[event] || 'keep', { resource: ref, ...payload });
  }, [on, onViewEvent, ref]);
  if (!ref) return <p className="text-sm text-stone-400">열 자료가 없습니다 — <code>[self:workspace]{'{op:"open"}'}</code> 결과의 <code>resource</code> 를 <code>ref</code> 로 주세요.</p>;
  if (kind === 'code') return <p className="text-sm text-stone-400">코딩 작업 공간은 엔진 표면이 없습니다 — <code>blocks</code>(diff·파일)와 <code>selection</code> 으로 봅니다.</p>;
  if (kind === 'sheet') return <SheetEngine id={ref} emit={emit} />;
  return <DocumentEngine id={ref} emit={emit} />;
}

/* ── 문서: capabilities.engine 으로 office / rhwp / source 를 고른다 ── */
function DocumentEngine({ id, emit }: { id: string; emit: (e: 'selection' | 'saved', p: Payload) => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const client = useRef(clientId());
  const capture = useRef<(() => Promise<unknown>) | null>(null);
  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        let d = await documentRequest<Detail>(`/${encodeURIComponent(id)}`);
        if (d.capabilities.edit_native && (!d.session || d.session.client_id !== client.current)) {
          d = await documentCommand<Detail>(id, 'sessions', { client_id: client.current });
        }
        if (!dead) setDetail(d);
      } catch (e) { if (!dead) setError(e instanceof Error ? e.message : String(e)); }
    })();
    return () => { dead = true; };
  }, [id]);
  if (error) return <p role="alert" className="text-sm text-red-600">{error}</p>;
  if (!detail) return <p className="text-sm text-stone-400">편집 표면을 여는 중…</p>;
  const onChange = (d: Detail) => setDetail(d);
  const saved = (d: Detail) => emit('saved', { revision: d.document.revision_id });
  if (!detail.capabilities.edit_native) return <p className="text-sm text-stone-500">{detail.capabilities.reason} — 열람만 가능합니다.</p>;
  if (detail.capabilities.engine === 'rhwp')
    return <HwpDocumentEditor key={`${detail.document.id}:${detail.session?.engine_epoch}`} detail={detail} onChange={onChange}
      captureRef={capture as never} onSaved={saved} />;
  if (detail.capabilities.engine === 'office')
    return <OfficeDocumentEditor key={detail.document.id} detail={detail} onChange={onChange} captureRef={capture as never}
      onSelection={(sel) => emit('selection', { sel: { bookmark: sel.bookmark }, text: sel.text, revision: detail.document.revision_id })}
      onSaved={saved} />;
  return <SourceEngine detail={detail} onChange={onChange} emit={emit} />;
}

/* ── 원문(TXT/MD/HTML/LaTeX…): textarea + 작업 저장(draft) + 원본 저장. 선택은 문자 범위. ── */
function SourceEngine({ detail, onChange, emit }: { detail: Detail; onChange: (d: Detail) => void; emit: (e: 'selection' | 'saved', p: Payload) => void }) {
  const [text, setText] = useState(detail.text ?? '');
  const [message, setMessage] = useState('원본을 읽었습니다');
  const [busy, setBusy] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const acknowledged = useRef(detail.text ?? '');
  const composing = useRef(false);
  const current = useRef(detail); current.current = detail;
  useEffect(() => { setText(detail.text ?? ''); acknowledged.current = detail.text ?? ''; }, [detail.document.id, detail.session?.engine_epoch]); // eslint-disable-line react-hooks/exhaustive-deps

  const draft = useCallback(async (): Promise<Detail> => {
    const d = current.current;
    if (!d.session) throw new Error('작성 세션이 없습니다');
    if (acknowledged.current === text) return d;
    const result = await documentCommand<{ session: Detail['session'] }>(d.document.id, 'draft',
      { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), text });
    acknowledged.current = text;
    const next = { ...d, session: result.session, text };
    current.current = next; onChange(next);
    return next;
  }, [text, onChange]);

  const run = async (fn: () => Promise<void>) => {
    if (busy || composing.current) return;
    setBusy(true);
    try { await fn(); } catch (e) { setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { setBusy(false); }
  };
  const select = () => {
    const el = editor.current; if (!el) return;
    const start = el.selectionStart, end = el.selectionEnd;
    if (start === end) return;
    emit('selection', { sel: { start, end }, start, end,
      text: text.slice(start, end), revision: current.current.document.revision_id });
    setMessage(`선택 고정 ${start}–${end}`);
  };
  return (
    <div className="flex flex-col gap-2">
      <textarea ref={editor} aria-label="문서 원문" spellCheck={false} value={text} rows={18}
        onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
        onChange={(e) => { setText(e.target.value); setMessage('수정됨 · 원본에는 저장되지 않음'); }}
        onMouseUp={select} onKeyUp={(e) => { if (e.shiftKey || e.key.startsWith('Arrow')) select(); }}
        className="w-full rounded-lg border border-stone-200 p-3 font-mono text-sm leading-relaxed" />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button disabled={busy} onClick={() => void run(async () => { await draft(); setMessage('작업 저장됨 · 원본에는 저장되지 않음'); })}
          className="px-3 py-1.5 rounded-lg border border-stone-300 hover:border-stone-500 disabled:opacity-40">작업 저장</button>
        <button disabled={busy} onClick={() => void run(async () => {
          const d = await draft();
          if (!d.session) throw new Error('작성 세션이 없습니다');
          await documentCommand(d.document.id, 'save', { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), expected_revision: d.document.revision_id });
          const next = await documentRequest<Detail>(`/${d.document.id}`);
          current.current = next; onChange(next);
          setMessage('저장됨 · 원본 파일 기록 확인');
          emit('saved', { revision: next.document.revision_id });
        })} className="px-3 py-1.5 rounded-lg bg-stone-800 text-white hover:bg-stone-900 disabled:opacity-40">원본 저장</button>
        <span className="text-stone-500">{message}</span>
      </div>
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
