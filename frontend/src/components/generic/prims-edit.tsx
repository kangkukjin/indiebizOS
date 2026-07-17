/**
 * generic/prims-edit.tsx — 편집 프리미티브 (form / editable_list)
 *
 * GenericInstrument.tsx 에서 분리(2026-07-18, 1500줄 규칙 모듈화).
 * FormPrim(필드 편집+저장+보조액션)·EditableListPrim(행 CRUD)·이미지/폴더/AI독 필드.
 * p.type 디스패치는 GenericInstrument.tsx ViewPrim(정본 if-chain)에 있다.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  type AppViewPrim, type AppFormField, type FormAction, type Dispatch, type Json,
  tpl, asList, buildAction, runIBL,
  fieldCls, imageUrl, RECURRENCE_OPTS, dateInputType,
} from './manifest';
import { Card } from './prims-basic';

/** attachment_path(JSON 배열 또는 레거시 단일 문자열) → 경로 배열 */
function parseImagePaths(v: unknown): string[] {
  const s = String(v ?? '').trim();
  if (!s) return [];
  try { const a = JSON.parse(s); if (Array.isArray(a)) return a.map(String); } catch { /* 레거시 단일 */ }
  return [s];
}

// 첨부 이미지 필드 — 썸네일(전 표면, /image?path=) + 제거(어디서나) + 추가(데스크탑 window.electron 만).
// form save 와 무관: 업로드 즉시 add_image/remove_image 로 영속 후 새로고침.
function ImagesField({ f, value, dispatch, busy, setBusy }:
  { f: AppFormField; value: string; dispatch: Dispatch; busy: boolean; setBusy: (b: boolean) => void }) {
  const paths = parseImagePaths(value);
  const electron = (window as unknown as { electron?: { selectImages?: () => Promise<string[]> } }).electron;
  const canAdd = !!(electron?.selectImages && f.add_action);
  const add = async () => {
    if (!electron?.selectImages || !f.add_action) return;
    const picked = await electron.selectImages();
    if (!picked || !picked.length) return;
    setBusy(true);
    for (const src of picked) await dispatch(f.add_action, { path: src });  // 각 파일 즉시 첨부+새로고침
    setBusy(false);
  };
  const remove = async (p: string) => {
    if (!f.remove_action) return;
    setBusy(true);
    await dispatch(f.remove_action, { path: p });
    setBusy(false);
  };
  return (
    <div className="flex flex-wrap gap-2 items-center">
      {paths.map((p, i) => (
        <div key={i} className="relative group">
          <img src={imageUrl(p)} alt="" className="w-16 h-16 object-cover rounded-lg border border-stone-200" />
          {f.remove_action && (
            <button disabled={busy} onClick={() => remove(p)} title="제거"
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-stone-800 text-white text-xs leading-none opacity-0 group-hover:opacity-100 disabled:opacity-40">×</button>
          )}
        </div>
      ))}
      {canAdd && (
        <button disabled={busy} onClick={add}
          className="w-16 h-16 rounded-lg border border-dashed border-stone-300 text-stone-400 text-2xl hover:border-stone-500 hover:text-stone-600 disabled:opacity-40">＋</button>
      )}
      {paths.length === 0 && !canAdd && <span className="text-xs text-stone-400">이미지 없음</span>}
    </div>
  );
}

// 폴더 선택 필드 — 데스크탑은 네이티브 다이얼로그(window.electron.selectFolder), 원격은 텍스트 폴백.
function FolderField({ f, value, onPick }: { f: AppFormField; value: string; onPick: (v: string) => void }) {
  const electron = (window as unknown as { electron?: { selectFolder?: () => Promise<string | null> } }).electron;
  const canPick = !!electron?.selectFolder;
  return (
    <div className="flex gap-2">
      <input value={value} onChange={(e) => onPick(e.target.value)}
        placeholder={f.placeholder || '찾아보기로 폴더를 선택하세요'}
        className={`${fieldCls} flex-1 min-w-0`} />
      {canPick && (
        <button type="button" onClick={async () => { const p = await electron!.selectFolder!(); if (p) onPick(p); }}
          className="px-3 py-2 rounded-lg border border-stone-300 text-sm text-stone-600 hover:border-stone-500 shrink-0 whitespace-nowrap">
          📁 찾아보기
        </button>
      )}
    </div>
  );
}

// textarea 위 ephemeral AI 제안 독 — 요청→제안→반영(대체)/첨부/닫기. 실행 후 제안 사라짐(비누적).
// action 은 $<필드키>(현재 텍스트)·$dock(요청)을 주입받아 스칼라 텍스트를 낸다(runIBL: project_id='앱모드').
function AiDock({ field, value, vals, onApply }: {
  field: AppFormField; value: string; vals: Record<string, string>; onApply: (v: string) => void;
}) {
  const dock = field.ai_dock!;
  const modes = dock.modes && dock.modes.length ? dock.modes : (['replace', 'append'] as const);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const ask = async () => {
    const instruction = input.trim();
    if (!instruction || busy) return;
    setInput(''); setBusy(true); setSuggestion(null);
    try {
      const code = buildAction(dock.action, { ...vals, [field.key]: value, dock: instruction });
      const d = await runIBL(code);
      const o = d && typeof d === 'object' ? (d as Json) : null;
      const text = typeof d === 'string' ? d
        : String(o?.result ?? o?.text ?? o?.answer ?? o?.message ?? o?.error ?? '');
      setSuggestion(text || '(빈 응답)');
    } catch {
      setSuggestion('⚠️ AI 응답을 받지 못했습니다. 백엔드 연결을 확인하세요.');
    } finally {
      setBusy(false);
    }
  };
  const apply = (mode: 'replace' | 'append') => {
    if (suggestion == null) return;
    onApply(mode === 'append' ? (value.trim() ? `${value}\n\n${suggestion}` : suggestion) : suggestion);
    setSuggestion(null);
  };
  const isErr = suggestion != null && suggestion.startsWith('⚠️');
  return (
    <div className="mt-1.5 flex flex-col gap-1.5">
      {busy && <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-400">AI가 생각 중…</div>}
      {!busy && suggestion != null && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 overflow-hidden">
          <div className="max-h-40 overflow-auto px-3 py-2 text-sm whitespace-pre-wrap leading-relaxed text-stone-800">{suggestion}</div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 border-t border-amber-100">
            {!isErr && modes.includes('replace') && (
              <button type="button" onClick={() => apply('replace')} className="px-2.5 py-1 rounded-md text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700">반영 (대체)</button>
            )}
            {!isErr && modes.includes('append') && (
              <button type="button" onClick={() => apply('append')} className="px-2.5 py-1 rounded-md text-xs font-semibold text-amber-700 border border-amber-300 hover:bg-amber-100">첨부</button>
            )}
            <div className="flex-1" />
            <button type="button" onClick={() => setSuggestion(null)} className="px-2 py-1 rounded-md text-xs text-stone-500 hover:bg-stone-100">닫기</button>
          </div>
        </div>
      )}
      <div className="flex items-end gap-1.5">
        <textarea value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }}
          placeholder={dock.placeholder || 'AI에게 시키기 — 예: 더 간결하게 (Enter 전송)'} rows={1}
          className={`${fieldCls} resize-none flex-1`} />
        <button type="button" onClick={ask} disabled={busy || !input.trim()}
          className="px-3 py-2 rounded-lg text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-40 shrink-0">✨ AI</button>
      </div>
    </div>
  );
}

export function FormPrim({ p, data, dispatch }: { p: AppViewPrim; data: unknown; dispatch: Dispatch }) {
  const fields = (p.fields as AppFormField[]) || [];
  const initVals = useCallback(
    () => Object.fromEntries(fields.map((f) => [f.key, tpl(f.value ?? '', data)])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data]
  );
  const [vals, setVals] = useState<Record<string, string>>(initVals);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setVals(initVals()); }, [initVals]);
  const set = (k: string, v: string) => setVals((s) => ({ ...s, [k]: v }));
  const save = async () => { setSaving(true); await dispatch(p.action as string, vals); setSaving(false); };
  // 보조 액션(즐겨찾기 토글·삭제 등): form 값이 아니라 드릴 데이터 컨텍스트로 실행. back=true면 성공 후 목록 복귀.
  const actions = (p.actions as FormAction[]) || [];
  const fire = async (a: FormAction) => {
    if (a.confirm && !window.confirm(a.confirm)) return;
    setSaving(true);
    await dispatch(a.action, {}, undefined, { back: a.back });
    setSaving(false);
  };

  return (
    <Card>
      {p.title != null && <div className="text-xs font-semibold text-stone-400 uppercase mb-2">{String(p.title)}</div>}
      <div className="flex flex-col gap-2.5">
        {fields.map((f, i) => (
          <div key={i} className="flex flex-col gap-1">
            {f.label && <label className="text-xs text-stone-500">{f.label}</label>}
            {f.type === 'select' ? (
              <select value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} className={fieldCls}>
                {(f.options || []).map((o, j) => <option key={j} value={String(o.value)}>{o.label}</option>)}
              </select>
            ) : f.type === 'toggle' ? (
              <button onClick={() => set(f.key, vals[f.key] === '1' ? '0' : '1')}
                className={`self-start px-3 py-1.5 rounded-lg border text-sm ${vals[f.key] === '1' ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200'}`}>
                {vals[f.key] === '1' ? '켜짐' : '꺼짐'}
              </button>
            ) : f.type === 'textarea' ? (
              <>
                <textarea value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} rows={3} placeholder={f.placeholder || ''} className={`${fieldCls} resize-y`} />
                {f.ai_dock && <AiDock field={f} value={vals[f.key] ?? ''} vals={vals} onApply={(v) => set(f.key, v)} />}
              </>
            ) : f.type === 'images' ? (
              <ImagesField f={f} value={vals[f.key] ?? ''} dispatch={dispatch} busy={saving} setBusy={setSaving} />
            ) : f.type === 'folder' ? (
              <FolderField f={f} value={vals[f.key] ?? ''} onPick={(v) => set(f.key, v)} />
            ) : f.type === 'recurrence' ? (
              <select value={vals[f.key] || 'none'} onChange={(e) => set(f.key, e.target.value)} className={fieldCls}>
                {RECURRENCE_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            ) : (f.type === 'date' || f.type === 'time' || f.type === 'datetime') ? (
              <input type={dateInputType(f.type)} value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} className={fieldCls} />
            ) : (
              <input value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} placeholder={f.placeholder || ''} className={fieldCls} />
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button disabled={saving} onClick={save}
          className="px-4 py-2 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40">
          {saving ? '…' : ((p.button as string) || '저장')}
        </button>
        {actions.map((a, i) => (
          <button key={i} disabled={saving} onClick={() => fire(a)}
            className={`px-3 py-2 rounded-lg text-sm border disabled:opacity-40 ${
              a.style === 'danger'
                ? 'border-red-200 text-red-600 hover:bg-red-50'
                : 'border-stone-200 text-stone-600 hover:border-stone-400'}`}>
            {tpl(a.label, data)}
          </button>
        ))}
      </div>
    </Card>
  );
}

export function EditableListPrim({ p, data, dispatch }: { p: AppViewPrim; data: unknown; dispatch: Dispatch }) {
  const arr = asList(data, p.from);
  const add = p.add as { fields: AppFormField[]; action: string; button?: string } | undefined;
  const [addVals, setAddVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const del = async (item: Json) => { setBusy(true); await dispatch(p.delete_action as string, {}, item); setBusy(false); };
  const doAdd = async () => { setBusy(true); const ok = await dispatch(add!.action, addVals); if (ok) setAddVals({}); setBusy(false); };

  return (
    <Card>
      {p.title != null && <div className="text-xs font-semibold text-stone-400 uppercase mb-2">{String(p.title)}</div>}
      {arr.length === 0 && <p className="text-sm text-stone-400 mb-2">{String(p.empty || '없음')}</p>}
      {arr.map((it, i) => (
        <div key={i} className="flex items-center justify-between py-1.5 border-b border-stone-100 last:border-0 text-sm">
          <span className="text-stone-800 min-w-0 truncate">{tpl(p.display, it)}</span>
          {p.delete_action != null && (
            <button disabled={busy} onClick={() => del(it)} className="text-xs text-stone-400 hover:text-red-500 shrink-0 ml-2 disabled:opacity-40">삭제</button>
          )}
        </div>
      ))}
      {add && (
        <div className="flex gap-2 mt-2.5">
          {add.fields.map((f, i) => f.type === 'select' ? (
            <select key={i} value={addVals[f.key] ?? ''} onChange={(e) => setAddVals((s) => ({ ...s, [f.key]: e.target.value }))}
              className={`${fieldCls} shrink-0`}>
              <option value="">{f.placeholder || '선택'}</option>
              {(f.options || []).map((o, j) => <option key={j} value={String(o.value)}>{o.label}</option>)}
            </select>
          ) : f.type === 'recurrence' ? (
            <select key={i} value={addVals[f.key] || 'none'} onChange={(e) => setAddVals((s) => ({ ...s, [f.key]: e.target.value }))}
              className={`${fieldCls} shrink-0`}>
              {RECURRENCE_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          ) : (f.type === 'date' || f.type === 'time' || f.type === 'datetime') ? (
            <input key={i} type={dateInputType(f.type)} value={addVals[f.key] ?? ''} onChange={(e) => setAddVals((s) => ({ ...s, [f.key]: e.target.value }))}
              className={`${fieldCls} shrink-0`} />
          ) : (
            <input key={i} value={addVals[f.key] ?? ''} onChange={(e) => setAddVals((s) => ({ ...s, [f.key]: e.target.value }))}
              placeholder={f.placeholder || ''} className={`${fieldCls} flex-1 min-w-0`} />
          ))}
          <button disabled={busy} onClick={doAdd}
            className="px-3 py-2 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40 shrink-0">
            {add.button || '추가'}
          </button>
        </div>
      )}
    </Card>
  );
}
