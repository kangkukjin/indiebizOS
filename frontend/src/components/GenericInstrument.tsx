/**
 * GenericInstrument — 매니페스트 해석 계기 (앱 표면 제네릭 렌더러의 데스크탑판)
 *
 * 진실 소스: ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
 * 원격 런처(api_launcher_web.py 웹앱)와 동일한 렌더 어휘를 React로 해석한다 —
 * 새 IBL 액션에 app: 블록만 달면 데스크탑·원격에 동시 등장.
 *
 * 2026-07-18 모듈화(1500줄 규칙): generic/ 하위로 분할 —
 *   generic/manifest.ts            타입·runIBL·템플릿 엔진·URL 헬퍼 (비-JSX 공용층)
 *   generic/prims-basic.tsx        Card·KvRow·Sparkline·linkify·DocBlock
 *   generic/prims-edit.tsx         FormPrim·EditableListPrim (+이미지/폴더/AI독 필드)
 *   generic/prims-map-calendar.tsx MapPrim(leaflet)·CalendarPrim
 * 이 파일에는 ViewPrim(★p.type 디스패치 정본 if-chain — build --check 뷰-어휘 가드가
 * 이 파일을 스캔한다)·ViewRenderer·계기 본체(ModePane·GenericInstrument)만 남는다.
 *
 * 어휘 명세: docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md
 *  - view 프리미티브 목록의 정본 = build_ibl_nodes.APP_VIEW_TYPES (+ ibl.md 앱 절 어휘 줄,
 *    뷰-어휘 문서-동기 가드가 대조). 여기 주석에 열거하지 않는다 — 박제 방지.
 *  - compose: 하단 작성바 — $text=작성, {field}=드릴 데이터. 전송 후 새로고침.
 *  - item_click.tabs: 드릴 상세 탭(대화↔이웃정보) — 한 액션 데이터를 탭별 view 로.
 *  - form/editable_list: $field=입력값, {field}=드릴 데이터 → 저장/추가/삭제 후 새로고침(dispatch).
 *  - 표시 템플릿 "{path|filter}": round·num·abs·arrow·opt:앞,뒤·trunc:N
 *  - action 템플릿: $key=사용자 입력(빈 입력 파라미터 자동 제거), {path}=데이터 행 필드
 *
 * 더 풍부한 데스크탑 전용 계기(도서·투자·라디오 등)는 ActionDesktop의
 * OVERRIDES(escape hatch)로 이 렌더러 대신 자기 컴포넌트를 쓴다.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { StreamPlayer } from './StreamPlayer';
import type { StreamData } from './chat/chatUtils';
import {
  type AppInput, type AppButton, type AppCompose, type AppViewPrim, type AppMode,
  type AppInstrument, type Json, type Dispatch, type ViewEvent,
  runIBL, jget, tpl, buildAction, rowAction, trendClass, asList,
  composeChannelOptions, mediaSrc, audioUrl, statusGlyph,
} from './generic/manifest';
import { linkify, Card, EmptyMsg, KvRow, Sparkline, DocBlock } from './generic/prims-basic';
import { FormPrim, EditableListPrim } from './generic/prims-edit';
import { MapPrim, CalendarPrim } from './generic/prims-map-calendar';

// 기존 import 경로 호환 재수출 — 다른 컴포넌트·계기 뷰가 './GenericInstrument' 에서 타입을 가져간다.
export type {
  AppInput, AppButton, AppCompose, AppComposeChannels, AppViewPrim, AppFormField,
  FormAction, AppFilter, AppMode, AppInstrument, Json, Dispatch, ViewEvent,
} from './generic/manifest';

function ViewPrim({ p, data, onDrill, onRowAction, onStream, busyRow, dispatch, onViewEvent }: {
  p: AppViewPrim; data: unknown;
  onDrill: (p: AppViewPrim, item: Json) => void;
  onRowAction: (action: string, item: Json, rowKey: string, refresh?: boolean) => void;
  onStream: (item: Json) => void;
  busyRow: string | null;
  dispatch: Dispatch;
  onViewEvent?: ViewEvent;
}) {
  if (p.type === 'map') return <MapPrim p={p} data={data} onViewEvent={onViewEvent} onStream={onStream} />;

  // group — 파티션 콤비네이터. from 리스트를 by 키로 나눠(입력 순서 보존) 그룹마다 헤더 + 내부 view 재귀 렌더.
  // 각 그룹은 단일통화 {items: 멤버}로 내부 view 에 전달 → 내부 프리미티브는 from:items 로 슬라이스 참조.
  // table:groupby(집계)와 달리 멤버 유지 = 뷰-계층의 groupby(신문 섹션 등). ★뷰-계층에 유일한 재귀 지점.
  if (p.type === 'group') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    const order: string[] = [];
    const groups: Record<string, Json[]> = {};
    for (const it of arr) {
      const key = tpl(p.by, it);
      if (!(key in groups)) { groups[key] = []; order.push(key); }
      groups[key].push(it);
    }
    const cap = typeof p.max_groups === 'number' ? p.max_groups : undefined;
    const keys = cap ? order.slice(0, cap) : order;
    const inner = (p.view as AppViewPrim[]) || [];
    return (
      <>
        {keys.map((key) => {
          const members = groups[key];
          const header = p.label ? tpl(p.label, members[0]) : key;
          const gdata = { items: members };
          return (
            <div key={key} className="mb-6">
              <h3 className="text-lg font-bold text-stone-800 border-b-2 border-stone-300 pb-1.5 mb-3">{header}</h3>
              {inner.map((ip, j) => (
                <ViewPrim key={j} p={ip} data={gdata} onDrill={onDrill} onRowAction={onRowAction}
                  onStream={onStream} busyRow={busyRow} dispatch={dispatch} onViewEvent={onViewEvent} />
              ))}
            </div>
          );
        })}
      </>
    );
  }

  if (p.type === 'metric') {
    const col = trendClass(p, data);
    return (
      <Card>
        {p.label != null && <div className="text-sm text-stone-500">{tpl(p.label, data)}</div>}
        <div className={`text-3xl font-bold ${col || 'text-stone-800'}`}>
          {tpl(p.big, data)}
          {p.unit != null && <span className="text-sm font-normal ml-1">{tpl(p.unit, data)}</span>}
        </div>
        {p.sub != null && <div className={`text-sm ${col ? `${col} font-semibold` : 'text-stone-500'}`}>{tpl(p.sub, data)}</div>}
      </Card>
    );
  }

  if (p.type === 'kv') {
    return (
      <Card>
        {p.title != null && <div className="text-xs font-semibold text-stone-400 uppercase mb-1">{String(p.title)}</div>}
        {((p.rows as { k: string; v: string }[]) || []).map((r, i) => (
          <KvRow key={i} k={tpl(r.k, data)} v={tpl(r.v, data)} />
        ))}
      </Card>
    );
  }

  if (p.type === 'kv_list') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    return (
      <Card>
        {p.title != null && <div className="text-xs font-semibold text-stone-400 uppercase mb-1">{String(p.title)}</div>}
        {arr.map((it, i) => (
          <KvRow key={i} k={tpl(p.k, it)} v={tpl(p.v, it)} />
        ))}
      </Card>
    );
  }

  if (p.type === 'card_list') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    const c = (p.card as Json) || {};
    const link = c.link as { href?: string; label?: string } | undefined;
    return (
      <>
        {arr.map((it, i) => {
          const img = c.image ? tpl(c.image, it) : '';
          const body = (
            <div className="min-w-0">
              <div className="font-semibold text-sm text-stone-800">{tpl(c.title, it)}</div>
              <div className="text-xs text-stone-500 leading-relaxed">
                {((c.lines as string[]) || []).map((l, j) => <div key={j}>{linkify(tpl(l, it))}</div>)}
              </div>
              {link?.href && tpl(link.href, it) && (
                <a href={tpl(link.href, it)} target="_blank" rel="noreferrer"
                  onClick={(e) => e.stopPropagation()} className="text-xs text-blue-600 hover:underline">
                  {link.label || '상세 →'}
                </a>
              )}
            </div>
          );
          return (
            <Card key={i} onClick={p.item_click ? () => onDrill(p, it) : undefined}>
              {c.image ? (
                <div className="flex gap-3">
                  {img ? <img src={mediaSrc(img)} loading="lazy" className="w-14 h-20 object-cover rounded-md bg-stone-100 shrink-0" />
                       : <div className="w-14 h-20 rounded-md bg-stone-100 shrink-0" />}
                  {body}
                </div>
              ) : body}
            </Card>
          );
        })}
      </>
    );
  }

  if (p.type === 'image_grid') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {arr.map((it, i) => {
          const img = p.image ? tpl(p.image, it) : '';
          return (
            <div key={i}>
              {img ? <img src={mediaSrc(img)} loading="lazy" className="w-full aspect-[3/4] object-cover rounded-lg bg-stone-100" />
                   : <div className="w-full aspect-[3/4] rounded-lg bg-stone-100" />}
              <div className="font-semibold text-xs text-stone-800 mt-1.5">{tpl(p.title, it)}</div>
              <div className="text-[11px] text-stone-500">
                {((p.lines as string[]) || []).map((l, j) => <div key={j}>{linkify(tpl(l, it))}</div>)}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (p.type === 'thread') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    return (
      <div className="flex flex-col gap-1.5 py-1">
        {arr.map((it, i) => {
          const mine = p.mine ? !!jget(it, p.mine as string) : false;
          const meta = p.meta ? tpl(p.meta, it) : '';
          const time = p.time ? tpl(p.time, it) : '';
          const status = p.status ? statusGlyph(String(jget(it, p.status as string) || '')) : '';
          const foot = [meta, time, status].filter(Boolean).join(' · ');
          return (
            <div key={i} className={`flex flex-col ${mine ? 'items-end' : 'items-start'}`}>
              <div className={`max-w-[78%] px-3.5 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
                mine ? 'bg-stone-800 text-white rounded-br-sm' : 'bg-white border border-stone-200 text-stone-800 rounded-bl-sm'}`}>
                {tpl(p.text, it)}
              </div>
              {foot && <div className="text-[10px] text-stone-400 mt-0.5 px-1">{foot}</div>}
            </div>
          );
        })}
      </div>
    );
  }

  if (p.type === 'sparkline') return <Sparkline p={p} data={data} />;

  // blocks — 문서 IR 렌더. from 배열의 각 원소 = 블록 {type, ...}.
  if (p.type === 'blocks') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    return (
      <div className="bg-white border border-stone-200 rounded-xl px-5 py-4">
        {arr.map((b, i) => <DocBlock key={i} b={b} />)}
      </div>
    );
  }

  if (p.type === 'media_player') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    return (
      <div className="flex flex-col gap-3">
        {arr.map((it, i) => {
          const src = audioUrl(p.src ? tpl(p.src, it) : '');
          const title = p.title ? tpl(p.title, it) : '';
          return (
            <div key={i} className="bg-white border border-stone-200 rounded-xl px-4 py-3">
              {title && <div className="text-sm font-semibold text-stone-800 mb-2">{title}</div>}
              {src ? <audio controls preload="metadata" src={src} className="w-full" />
                   : <div className="text-xs text-stone-400">재생할 오디오가 없습니다.</div>}
            </div>
          );
        })}
      </div>
    );
  }

  if (p.type === 'form') return <FormPrim p={p} data={data} dispatch={dispatch} />;
  if (p.type === 'editable_list') return <EditableListPrim p={p} data={data} dispatch={dispatch} />;
  if (p.type === 'calendar') return <CalendarPrim p={p} data={data} dispatch={dispatch} />;

  if (p.type === 'list_action') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    const btn = p.button as AppButton | undefined;
    const btn2 = p.button2 as AppButton | undefined;
    // 행 드롭다운(select) — 선택 즉시 action 실행({sel}=고른 값). button 과 공존 가능.
    const sel = p.select as { value?: string; options?: { value: string; label: string }[]; action?: string; refresh?: boolean } | undefined;
    return (
      <>
        {arr.map((it, i) => {
          const rowKey = `${p.type}-${i}`;
          const rowKey2 = `${p.type}-${i}-2`;
          const rowKeyS = `${p.type}-${i}-sel`;
          return (
            <Card key={i} onClick={p.item_click ? () => onDrill(p, it) : undefined}>
              <div className="flex items-center gap-3">
                {p.icon != null && <span className="text-lg">{String(p.icon)}</span>}
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-stone-800">{tpl(p.title, it)}</div>
                  <div className="text-xs text-stone-500 truncate">{tpl(p.sub, it)}</div>
                </div>
                {sel && sel.action && (
                  <select disabled={busyRow === rowKeyS} value={tpl(sel.value, it)}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => { e.stopPropagation(); onRowAction(sel.action!, { ...it, sel: e.target.value }, rowKeyS, sel.refresh); }}
                    className="px-2 py-1.5 rounded-lg border border-stone-200 text-sm text-stone-800 hover:border-stone-400 disabled:opacity-40 bg-white">
                    {(sel.options || []).map((o, j) => <option key={j} value={String(o.value)}>{o.label}</option>)}
                  </select>
                )}
                {btn && (
                  <button disabled={busyRow === rowKey}
                    onClick={(e) => { e.stopPropagation(); btn.stream ? onStream(it) : btn.action && onRowAction(btn.action, it, rowKey, btn.refresh); }}
                    className="px-3 py-1.5 rounded-lg border border-stone-200 text-sm text-stone-800 hover:border-stone-400 disabled:opacity-40">
                    {busyRow === rowKey ? '…' : btn.label || '▶'}
                  </button>
                )}
                {btn2 && (
                  <button disabled={busyRow === rowKey2}
                    onClick={(e) => { e.stopPropagation(); btn2.stream ? onStream(it) : btn2.action && onRowAction(btn2.action, it, rowKey2, btn2.refresh); }}
                    className="px-3 py-1.5 rounded-lg border border-stone-200 text-sm text-stone-800 hover:border-stone-400 disabled:opacity-40">
                    {busyRow === rowKey2 ? '…' : btn2.label || '⬇'}
                  </button>
                )}
              </div>
            </Card>
          );
        })}
      </>
    );
  }

  return null;
}

function ViewRenderer({ view, data, onDrill, onRowAction, onStream, busyRow, dispatch, onViewEvent }: {
  view: AppViewPrim[]; data: Json;
  onDrill: (p: AppViewPrim, item: Json) => void;
  onRowAction: (action: string, item: Json, rowKey: string, refresh?: boolean) => void;
  onStream: (item: Json) => void;
  busyRow: string | null;
  dispatch: Dispatch;
  onViewEvent?: ViewEvent;
}) {
  if (data.error) return <p className="text-sm text-stone-400">{String(data.error)}</p>;
  if (data.success === false) return <p className="text-sm text-stone-400">{String(data.message || '실패')}</p>;
  return (
    <>
      {view.map((p, i) => (
        <ViewPrim key={i} p={p} data={data} onDrill={onDrill} onRowAction={onRowAction} onStream={onStream} busyRow={busyRow} dispatch={dispatch} onViewEvent={onViewEvent} />
      ))}
    </>
  );
}

// ===== 계기 본체 =====

// options_action 의 $key 를 형제 입력값으로 치환 — 비어 있으면 missing(종속 대기)
function resolveOptionsAction(template: string, values: Record<string, string>): { code: string; missing: boolean } {
  let missing = false;
  const code = template.replace(/\$(\w+)/g, (_, k: string) => {
    const v = values[k] || '';
    if (!v) missing = true;
    return v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  });
  return { code, missing };
}
// 배열은 option_value/option_label로, 딕셔너리({이름:코드})는 entries로 정규화
function normalizeOptions(raw: unknown, inp: AppInput): { value: string; label: string }[] {
  if (Array.isArray(raw)) return raw.map((o) => ({
    value: String((o as Json)[inp.option_value || 'value'] ?? ''),
    label: String((o as Json)[inp.option_label || 'label'] ?? ''),
  }));
  if (raw && typeof raw === 'object') return Object.entries(raw as Json).map(([k, v]) => ({ value: String(v), label: k }));
  return [];
}

function SelectInput({ inp, values, onChange }: { inp: AppInput; values: Record<string, string>; onChange: (v: string) => void }) {
  const staticOpts = inp.options ? inp.options.map((o) => ({ value: String(o.value), label: String(o.label) })) : null;
  const [options, setOptions] = useState<{ value: string; label: string }[]>(staticOpts || []);
  const value = values[inp.key] || '';

  // 종속 옵션: $형제 치환된 액션이 바뀌면 다시 불러온다 (cascade)
  const resolved = !staticOpts && inp.options_action ? resolveOptionsAction(inp.options_action, values) : null;
  const actionCode = resolved && !resolved.missing ? resolved.code : '';
  useEffect(() => {
    if (staticOpts) return;
    if (!actionCode) { setOptions([]); return; }
    let alive = true;
    runIBL(actionCode).then((d) => { if (alive) setOptions(normalizeOptions(jget(d, inp.options_from), inp)); }).catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionCode]);

  // 옵션이 갱신돼 현재 값이 더 이상 유효하지 않으면 자동 해제 (부모 변경 시 stale 정리)
  useEffect(() => {
    if (value && options.length && !options.some((o) => o.value === value)) onChange('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2 rounded-lg border border-stone-200 bg-white text-sm text-stone-900">
      <option value="">{inp.label || '전체'}</option>
      {options.map((o, i) => <option key={i} value={o.value}>{o.label}</option>)}
    </select>
  );
}

type DrillTab = { name: string; view: AppViewPrim[]; compose?: AppCompose };
type DrillState = { data: Json; action: string; item: Json; view?: AppViewPrim[]; compose?: AppCompose; tabs?: DrillTab[] };

function ModePane({ mode }: { mode: AppMode }) {
  const initVals = useCallback(() => {
    const v: Record<string, string> = {};
    (mode.inputs || []).forEach((inp) => { v[inp.key] = inp.default || ''; });
    if (mode.filter?.items?.length) {
      const def = mode.filter.items.find((x) => x.default) || mode.filter.items[0];
      v[mode.filter.key || 'filter'] = String(def.value);
    }
    return v;
  }, [mode]);

  const [values, setValues] = useState<Record<string, string>>(initVals);
  const [data, setData] = useState<Json | null>(null);
  const [drill, setDrill] = useState<DrillState | null>(null);
  const [catFilter, setCatFilter] = useState<string | null>(null);  // 동적 필터(from_field) 선택값 — 클라이언트 측 거르기
  const [tabIdx, setTabIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyRow, setBusyRow] = useState<string | null>(null);
  const [stream, setStream] = useState<Json | null>(null);  // 스트림 재생 오버레이(CCTV '▶ 보기' 등) — 행 데이터를 StreamPlayer 로
  const [notice, setNotice] = useState<string | null>(null);  // 행 액션 성공 메시지(즐겨찾기 추가 등) — 잠깐 표시
  const [composeText, setComposeText] = useState('');
  const [composeCh, setComposeCh] = useState('');  // 선택된 발신 채널 키 (빈값=첫 후보)
  const [sending, setSending] = useState(false);
  const valuesRef = useRef(values);
  valuesRef.current = values;

  const run = useCallback(async (override?: Record<string, string>) => {
    if (!mode.action) return;
    const vals = override || valuesRef.current;
    for (const inp of mode.inputs || []) if (inp.required && !vals[inp.key]) return;
    setLoading(true); setError(null); setDrill(null); setCatFilter(null);
    try {
      setData(await runIBL(buildAction(mode.action, vals)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [mode]);

  // 모드 진입 시 초기화 + auto_run
  useEffect(() => {
    const v = initVals();
    setValues(v); setData(null); setDrill(null); setError(null); setComposeText(''); setComposeCh(''); setCatFilter(null);
    if (mode.auto_run) run(v);
  }, [mode, initVals, run]);

  const onDrill = useCallback(async (p: AppViewPrim, item: Json) => {
    const dc = p.item_click as { action: string; view?: AppViewPrim[]; compose?: AppCompose; tabs?: DrillTab[] } | undefined;
    if (!dc) return;
    setLoading(true); setError(null); setComposeText(''); setComposeCh(''); setTabIdx(0);
    try {
      // 드릴 액션의 $입력(현재 다이얼 값) + {필드}(클릭 행) 둘 다 치환 — realty 추이처럼
      // "현재 지역·유형 + 클릭한 단지"를 합쳐 묻는 드릴을 지원.
      const code = rowAction(buildAction(dc.action, valuesRef.current), item);
      const d = await runIBL(code);
      if (d && typeof d === 'object') (d as Json)._item = item; // 드릴 뷰에서 클릭 행 참조용
      setDrill({ data: d, action: code, item, view: dc.view, compose: dc.compose, tabs: dc.tabs });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // 현재 뷰 새로고침 (드릴이면 드릴 액션 재실행, 아니면 모드 액션)
  const refreshCurrent = useCallback(async () => {
    if (drill) {
      const nd = await runIBL(drill.action);
      if (nd && typeof nd === 'object') (nd as Json)._item = drill.item;
      setDrill((s) => (s ? { ...s, data: nd } : s));
    } else {
      run();
    }
  }, [drill, run]);

  // 액션 실행기: $field 치환 + {path}(rowContext, 기본 드릴 데이터) 치환 → 실행 → 새로고침
  const dispatch = useCallback<Dispatch>(async (template, fieldValues, rowContext, opts) => {
    try {
      // 모드 입력값도 $key 치환에 합류 — form/행 액션이 상단 셀렉터(포털 선택 등)를 참조 가능.
      // 필드값이 우선이라 키 충돌 시 기존 동작 그대로. (원격 dispatchAction 과 파리티)
      let code = buildAction(template, { ...valuesRef.current, ...(fieldValues || {}) });
      const ctx = rowContext ?? (drill ? drill.data : undefined);
      if (ctx) code = rowAction(code, ctx);
      const d = await runIBL(code);
      if (d?.error || d?.success === false) { alert(String(d.error || d.message || '실패')); return false; }
      if (opts?.back && drill) { setDrill(null); setComposeText(''); setComposeCh(''); }
      else await refreshCurrent();
      return true;
    } catch (e) {
      alert('실패: ' + (e instanceof Error ? e.message : String(e)));
      return false;
    }
  }, [drill, refreshCurrent]);

  // 작성바 전송 — $text + {path}(드릴 데이터) 치환 → 실행 → 새로고침
  const composeSend = useCallback(async (cmp: AppCompose) => {
    const text = composeText.trim();
    if (!text) return;
    setSending(true);
    const opts = composeChannelOptions(cmp, drill?.data);
    const sel = opts.find((o) => o.key === composeCh) || opts[0];
    const extra: Record<string, string> = sel ? { channel_type: sel.channel_type, to: sel.to } : {};
    const ok = await dispatch(cmp.action, { text, ...extra });
    if (ok) setComposeText('');
    setSending(false);
  }, [composeText, composeCh, drill, dispatch]);

  const onRowAction = useCallback(async (action: string, item: Json, rowKey: string, refresh?: boolean) => {
    setBusyRow(rowKey);
    try {
      const d = await runIBL(rowAction(action, item));
      if (d?.error || d?.success === false) alert(String(d.error || d.message || '실패'));
      else {
        if (d?.message) { setNotice(String(d.message)); setTimeout(() => setNotice(null), 2500); }
        if (refresh) await refreshCurrent();
      }
    } catch (e) {
      alert('실행 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusyRow(null);
    }
  }, [refreshCurrent]);

  // 스트림 재생 — 행 데이터(url/playable/name/lat/lng)를 클라이언트 StreamPlayer 로 연다(서버 호출 없음)
  const onStream = useCallback((item: Json) => setStream(item), []);

  // 뷰-이벤트(map moveend/marker_click) → 액션 재조회. ★loading 안 켬: 지도를 언마운트하지 않아야
  // viewport 가 보존되고(마커만 in-place 갱신) 재조회 피드백 루프가 안 생긴다(MapPrim didFit 가드와 짝).
  const onViewEvent = useCallback<ViewEvent>((template, payload) => {
    (async () => {
      try {
        const code = buildAction(template, { ...valuesRef.current, ...payload });
        const d = await runIBL(code);
        if (d && !d.error) { setData(d); setCatFilter(null); }  // 지도 재조회=새 결과 → 동적 필터 초기화
      } catch { /* 재조회 실패는 현재 화면 유지 */ }
    })();
  }, []);

  const fireButton = useCallback(async (b: AppButton) => {
    if (!b.action) return;
    try {
      // $key=모드 입력값 치환(팔로우 $npub·보드 만들기 $name/$tag 등) — 빈 입력 파라미터는 제거됨
      const d = await runIBL(buildAction(b.action, valuesRef.current));
      if (d?.error) { alert(String(d.error)); return; }
      if (b.refresh) run();  // 실행 후 현재 모드 재조회(토글/재생성 결과 즉시 반영)
    } catch (e) {
      alert('실행 실패: ' + (e instanceof Error ? e.message : String(e)));
    }
  }, [run]);

  const inputs = mode.inputs || [];
  // master_detail card_list → 반응형 2분할(PC: 리스트 좌+상세 우 동시 / 폰: 리스트→선택→상세→뒤로)
  const isSplit = !(mode as { modes?: AppMode[] }).modes && (mode.view || []).some((p) => p.type === 'card_list' && !!p.master_detail);

  // 동적 필터(filter.from_field): 결과 items 의 그 필드 distinct 값으로 칩 + 클라이언트 측 거르기(재조회 없음).
  // viewData=필터 적용된 데이터(map 마커·card_list 동시 거름). 정적 필터(items)는 별개 경로(재조회).
  const dynField = mode.filter?.from_field;
  const dynFrom = (mode.filter?.from as string) || 'items';
  const dynCats = (dynField && data)
    ? Array.from(new Set(asList(data, dynFrom).map((it) => jget(it, dynField)).filter(Boolean).map(String)))
    : [];
  const activeCat = dynField && catFilter && dynCats.includes(catFilter) ? catFilter : null;
  const viewData: Json | null = (dynField && activeCat && data)
    ? ({ ...data, [dynFrom]: asList(data, dynFrom).filter((it) => String(jget(it, dynField)) === activeCat) })
    : data;
  const drillTabs = drill?.tabs;
  const activeCompose = drill
    ? (drillTabs ? drillTabs[Math.min(tabIdx, drillTabs.length - 1)]?.compose : drill.compose)
    : mode.compose;

  const composeBarEl = (cmp?: AppCompose) => {
    if (!cmp || loading) return null;
    const chOpts = composeChannelOptions(cmp, drill?.data);
    const selKey = chOpts.find((o) => o.key === composeCh) ? composeCh : (chOpts[0]?.key || '');
    return (
      <div className="sticky bottom-0 mt-2 px-1 py-2.5 bg-stone-50/95 backdrop-blur border-t border-stone-200 flex gap-2 shrink-0">
        {chOpts.length >= 2 && (
          <select value={selKey} onChange={(e) => setComposeCh(e.target.value)}
            title="발신 채널"
            className="shrink-0 px-2 py-2 rounded-full border border-stone-200 bg-white text-xs text-stone-700 focus:outline-none focus:border-stone-400 max-w-[42%]">
            {chOpts.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        )}
        <input value={composeText} onChange={(e) => setComposeText(e.target.value)}
          placeholder={cmp.placeholder || '메시지 입력…'}
          onKeyDown={(e) => { if (e.key === 'Enter' && !sending) composeSend(cmp); }}
          className="flex-1 min-w-0 px-3.5 py-2 rounded-full border border-stone-200 bg-white text-sm text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-stone-400" />
        <button disabled={sending || !composeText.trim()} onClick={() => composeSend(cmp)}
          className="px-4 py-2 rounded-full bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40 shrink-0">
          {sending ? '…' : (cmp.button || '전송')}
        </button>
      </div>
    );
  };

  const drillTabsEl = drillTabs && drillTabs.length > 0 ? (
    <div className="flex gap-1.5 mb-3 shrink-0">
      {drillTabs.map((t, i) => (
        <button key={i} onClick={() => { setTabIdx(i); setComposeText(''); setComposeCh(''); }}
          className={`px-3.5 py-1.5 rounded-lg text-sm border transition ${
            i === tabIdx ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200 hover:border-stone-400'}`}>
          {t.name}
        </button>
      ))}
    </div>
  ) : null;

  const drillViewEl = drill ? (
    <ViewRenderer
      view={drillTabs ? (drillTabs[Math.min(tabIdx, drillTabs.length - 1)]?.view || []) : (drill.view || [])}
      data={drill.data} onDrill={onDrill} onRowAction={onRowAction} onStream={onStream} busyRow={busyRow} dispatch={dispatch} onViewEvent={onViewEvent} />
  ) : null;

  return (
    <div className={`${isSplit ? 'max-w-5xl' : 'max-w-2xl'} mx-auto p-5`}>
      {mode.note && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
          {mode.note}
        </div>
      )}

      {inputs.length > 0 && (
        <div className="flex gap-2 mb-2">
          {inputs.map((inp) =>
            inp.type === 'select' ? (
              <SelectInput key={inp.key} inp={inp} values={values}
                onChange={(v) => setValues((s) => ({ ...s, [inp.key]: v }))} />
            ) : (
              <input key={inp.key} value={values[inp.key] || ''} placeholder={inp.placeholder || ''}
                onChange={(e) => setValues((s) => ({ ...s, [inp.key]: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && run()}
                className="flex-1 px-3 py-2 rounded-lg border border-stone-200 bg-white text-sm text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-stone-400" />
            )
          )}
          <button onClick={() => run()}
            className="px-4 py-2 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
        </div>
      )}

      {inputs.filter((i) => i.chips?.length).map((inp) => (
        <div key={inp.key} className="flex flex-wrap gap-1.5 mb-3">
          {inp.chips!.map((c) => (
            <button key={c}
              onClick={() => { const v = { ...valuesRef.current, [inp.key]: c }; setValues(v); run(v); }}
              className="px-3 py-1 rounded-full border border-stone-200 bg-white text-xs text-stone-800 hover:border-stone-400">
              {c}
            </button>
          ))}
        </div>
      ))}

      {mode.filter?.items?.length && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {mode.filter.items.map((x) => {
            const pk = mode.filter!.key || 'filter';
            const on = String(values[pk]) === String(x.value);
            return (
              <button key={String(x.value)}
                onClick={() => { const v = { ...valuesRef.current, [pk]: String(x.value) }; setValues(v); run(v); }}
                className={`px-3 py-1 rounded-full text-xs border transition ${
                  on ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200 hover:border-stone-400'}`}>
                {x.label}
              </button>
            );
          })}
        </div>
      )}

      {/* 동적 필터(from_field) 칩 — 결과 필드 distinct 값. 클라이언트 측 거르기(재조회 없음). */}
      {dynField && !loading && !drill && dynCats.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          <button onClick={() => setCatFilter(null)}
            className={`px-3 py-1 rounded-full text-xs border transition ${
              !activeCat ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200 hover:border-stone-400'}`}>전체</button>
          {dynCats.slice(0, 12).map((c) => (
            <button key={c} onClick={() => setCatFilter(c)}
              className={`px-3 py-1 rounded-full text-xs border transition ${
                activeCat === c ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200 hover:border-stone-400'}`}>
              {c}
            </button>
          ))}
        </div>
      )}

      {(() => {
        // 맥 데스크탑 전용 렌더러 — phone_only 버튼([limbs:phone] 등)은 여기서 실행 불가라 숨긴다.
        const visibleButtons = (mode.buttons || []).filter((b) => !b.phone_only);
        return visibleButtons.length > 0 && (
          <div className="flex gap-2 mb-3">
            {visibleButtons.map((b, i) => (
              <button key={i} onClick={() => fireButton(b)}
                className="px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-sm text-stone-800 hover:border-stone-400">
                {b.label}
              </button>
            ))}
          </div>
        );
      })()}

      {loading && <div className="flex justify-center py-8"><div className="w-6 h-6 border-2 border-stone-200 border-t-stone-600 rounded-full animate-spin" /></div>}
      {error && <p className="text-sm text-stone-400">오류: {error}</p>}
      {notice && <p className="mb-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5">{notice}</p>}

      {/* === master-detail 반응형: PC=2분할(리스트+상세 동시) / 폰=드릴(선택→상세→뒤로) === */}
      {isSplit && !loading && data && (
        <div className="flex flex-col md:flex-row gap-3 md:h-[calc(100vh-210px)]">
          <div className={`md:w-72 md:shrink-0 md:overflow-y-auto md:pr-1 ${drill ? 'hidden md:block' : 'block'}`}>
            <ViewRenderer view={mode.view || []} data={data} onDrill={onDrill} onRowAction={onRowAction} onStream={onStream} busyRow={busyRow} dispatch={dispatch} onViewEvent={onViewEvent} />
          </div>
          <div className={`flex-1 min-w-0 md:border-l md:border-stone-200 md:pl-4 ${drill ? 'flex flex-col min-h-0' : 'hidden md:flex md:flex-col'}`}>
            {drill ? (
              <>
                <button onClick={() => { setDrill(null); setComposeText(''); setComposeCh(''); }}
                  className="md:hidden self-start text-xs text-stone-500 hover:text-stone-800 mb-2">‹ 목록</button>
                {drillTabsEl}
                <div className="flex-1 min-h-0 md:overflow-y-auto">{drillViewEl}</div>
                {composeBarEl(activeCompose)}
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center min-h-[280px] text-sm text-stone-400">← 목록에서 대화를 선택하세요</div>
            )}
          </div>
        </div>
      )}

      {!isSplit && !loading && drill && (
        <>
          <button onClick={() => { setDrill(null); setComposeText(''); setComposeCh(''); }}
            className="text-xs text-stone-500 hover:text-stone-800 mb-2">‹ 결과 목록으로</button>
          {drillTabsEl}
          {drillViewEl}
        </>
      )}
      {!isSplit && !loading && !drill && viewData && mode.view && (
        <ViewRenderer view={mode.view} data={viewData} onDrill={onDrill} onRowAction={onRowAction} onStream={onStream} busyRow={busyRow} dispatch={dispatch} onViewEvent={onViewEvent} />
      )}
      {!isSplit && (() => {
        const cmp = drill ? activeCompose : mode.compose;
        if (!cmp || loading || (!drill && !data)) return null;
        return <div className="-mx-5 px-5">{composeBarEl(cmp)}</div>;
      })()}

      {/* 스트림 재생 오버레이 — CCTV '▶ 보기' 등. 행 데이터(url/playable)를 StreamPlayer 로 재생 */}
      {stream && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setStream(null)}>
          <div className="w-full max-w-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-end mb-1">
              <button onClick={() => setStream(null)}
                className="px-3 py-1 rounded-lg bg-white/90 text-stone-800 text-sm hover:bg-white">닫기 ✕</button>
            </div>
            <StreamPlayer data={stream as unknown as StreamData} />
          </div>
        </div>
      )}
    </div>
  );
}

export function GenericInstrument({ instrument }: { instrument: AppInstrument }) {
  const modes: AppMode[] = instrument.modes || [instrument];
  const [modeIdx, setModeIdx] = useState(0);
  const mode = modes[Math.min(modeIdx, modes.length - 1)];
  // 최상단 고정 버튼(탭 무관·항상 보임) — 데스크탑선 phone_only 숨김.
  const topButtons = (instrument.top_buttons || []).filter((b) => !b.phone_only);
  const [topBusy, setTopBusy] = useState(false);
  const [topMsg, setTopMsg] = useState('');
  const fireTop = async (b: AppButton) => {
    if (!b.action || topBusy) return;
    if (b.confirm && !window.confirm(b.confirm)) return;
    setTopBusy(true); setTopMsg('');
    try {
      const r = await runIBL(b.action);
      setTopMsg(String((r && (r.message as string)) || '완료'));
    } catch (e) {
      setTopMsg('오류: ' + String(e));
    } finally {
      setTopBusy(false);
    }
  };

  return (
    <div className="h-full w-full overflow-auto bg-stone-50">
      {(instrument.modes || topButtons.length > 0) && (
        <div className="flex items-center gap-1.5 max-w-2xl mx-auto px-5 pt-4">
          {(instrument.modes || []).map((m, i) => (
            <button key={i} onClick={() => setModeIdx(i)}
              className={`px-3.5 py-1.5 rounded-lg text-sm border transition ${
                i === modeIdx ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200 hover:border-stone-400'}`}>
              {m.name}
            </button>
          ))}
          {topButtons.map((b, i) => (
            <button key={'t' + i} onClick={() => fireTop(b)} disabled={topBusy}
              className={`${i === 0 ? 'ml-auto' : ''} px-3.5 py-1.5 rounded-lg text-sm font-semibold border border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition`}>
              {b.label}
            </button>
          ))}
        </div>
      )}
      {topMsg && <div className="max-w-2xl mx-auto px-5 pt-2 text-sm text-emerald-700">{topMsg}</div>}
      <ModePane mode={mode} />
    </div>
  );
}
