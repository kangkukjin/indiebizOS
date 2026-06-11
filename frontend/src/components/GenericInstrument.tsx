/**
 * GenericInstrument — 매니페스트 해석 계기 (앱 표면 제네릭 렌더러의 데스크탑판)
 *
 * 진실 소스: ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
 * 원격 런처(api_launcher_web.py 웹앱)와 동일한 렌더 어휘를 React로 해석한다 —
 * 새 IBL 액션에 app: 블록만 달면 데스크탑·원격에 동시 등장.
 *
 * 어휘 명세: docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md
 *  - view 프리미티브 7종: metric / kv / kv_list / card_list(+item_click 드릴) /
 *    image_grid / sparkline / list_action
 *  - 표시 템플릿 "{path|filter}": round·num·abs·arrow·opt:앞,뒤·trunc:N
 *  - action 템플릿: $key=사용자 입력(빈 입력 파라미터 자동 제거), {path}=데이터 행 필드
 *
 * 더 풍부한 데스크탑 전용 계기(도서·투자·라디오 등)는 ActionDesktop의
 * OVERRIDES(escape hatch)로 이 렌더러 대신 자기 컴포넌트를 쓴다.
 */
import { useState, useEffect, useRef, useCallback } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';

// ===== 매니페스트 타입 (느슨하게 — 서버 파생 JSON이 진실) =====

export interface AppInput {
  key: string;
  type: 'text' | 'select';
  default?: string;
  placeholder?: string;
  required?: boolean;
  chips?: string[];
  label?: string;
  options?: { value: string; label: string }[];  // 정적 옵션 (IBL 호출 없음)
  options_action?: string;                         // 동적 옵션 — $key 로 형제 입력값 치환(cascade)
  options_from?: string;
  option_value?: string;
  option_label?: string;
}

export interface AppButton { label: string; action: string }

export interface AppViewPrim {
  type: 'metric' | 'kv' | 'kv_list' | 'card_list' | 'image_grid' | 'sparkline' | 'list_action';
  [k: string]: unknown;
}

export interface AppPeriods {
  key?: string;  // 액션 템플릿이 참조하는 파라미터명 ($key) — 기본 'period'
  items: { label: string; value: string | number; default?: boolean }[];
}

export interface AppMode {
  id?: string;
  name?: string;
  note?: string;
  auto_run?: boolean;
  inputs?: AppInput[];
  buttons?: AppButton[];
  action?: string;
  view?: AppViewPrim[];
  periods?: AppPeriods;  // 차트 기간 토글 — 클릭 즉시 그 기간으로 재조회
}

export interface AppInstrument extends AppMode {
  id: string;
  icon: string;
  name: string;
  modes?: AppMode[];
}

type Json = Record<string, unknown>;

async function runIBL(code: string): Promise<Json> {
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, project_id: '앱모드', project_path: '.' }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ===== 템플릿 엔진 (원격 webapp과 동일 의미) =====

function jget(o: unknown, path?: string): unknown {
  if (!path) return o;
  return String(path).split('.').reduce<unknown>((a, k) => (a == null ? undefined : (a as Json)[k]), o);
}

function applyFilter(v: unknown, f: string): unknown {
  if (f === 'round') return v == null ? v : Math.round(Number(v));
  if (f === 'num') return v == null ? null : Number(v).toLocaleString();
  if (f === 'abs') return v == null ? v : Math.abs(Number(v));
  if (f === 'arrow') return (Number(v) || 0) >= 0 ? '▲' : '▼';
  if (f.startsWith('opt:')) {
    const a = f.slice(4).split(',');
    return v == null || v === '' || Number(v) === 0 ? '' : (a[0] || '') + String(v) + (a[1] || '');
  }
  if (f.startsWith('trunc:')) {
    const n = parseInt(f.slice(6)) || 40;
    const s = String(v ?? '');
    return s.length > n ? s.slice(0, n) + '…' : s;
  }
  return v;
}

/** "{path|filter|...}" → 문자열 치환 (React가 이스케이프하므로 esc 불필요) */
function tpl(t: unknown, data: unknown): string {
  if (t == null) return '';
  return String(t).replace(/\{([^{}]+)\}/g, (_, expr: string) => {
    const parts = expr.split('|');
    let v = jget(data, parts[0].trim());
    for (let i = 1; i < parts.length; i++) v = applyFilter(v, parts[i].trim());
    return v == null ? '' : String(v);
  });
}

/** $key 치환 + 빈 입력 'param: ""' 쌍 자동 제거 */
function buildAction(template: string, values: Record<string, string>): string {
  let code = template.replace(/\$(\w+)/g, (_, k: string) => {
    const v = values[k];
    return v == null ? '' : String(v).replace(/\\/g, '').replace(/"/g, '');
  });
  code = code.replace(/\w+:\s*"",?\s*/g, '');
  code = code.replace(/,\s*\}/g, '}').replace(/\{\s*,/g, '{');
  return code;
}

/** 행 데이터 {path} 치환 (드릴·행 버튼용) */
function rowAction(template: string, item: unknown): string {
  return template.replace(/\{([\w.]+)\}/g, (_, path: string) => {
    const v = jget(item, path);
    return v == null ? '' : String(v).replace(/"/g, '');
  });
}

// 한국색: 상승=빨강, 하락=파랑
function trendClass(p: AppViewPrim, data: unknown): string | null {
  if (!p.trend) return null;
  return (Number(jget(data, p.trend as string)) || 0) >= 0 ? 'text-red-500' : 'text-blue-600';
}

function asList(data: unknown, from: unknown): Json[] {
  if (from === '.') return [data as Json]; // 응답 자체를 1행으로 (단일 객체에 행 버튼 달기)
  const arr = jget(data, from as string);
  return Array.isArray(arr) ? (arr as Json[]) : [];
}

// ===== 뷰 프리미티브 =====

function Card({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <div onClick={onClick}
      className={`bg-white rounded-xl border border-stone-200 p-4 mb-3 ${onClick ? 'cursor-pointer hover:border-stone-400 transition' : ''}`}>
      {children}
    </div>
  );
}

function EmptyMsg({ p, data }: { p: AppViewPrim; data: unknown }) {
  const m = (p.empty_from ? jget(data, p.empty_from as string) : null) || p.empty || '결과가 없습니다';
  return <p className="text-sm text-stone-400 mt-2">{String(m)}</p>;
}

function KvRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-stone-100 last:border-0 text-sm">
      <span className="text-stone-500">{k}</span>
      <span className="text-stone-800 text-right">{v}</span>
    </div>
  );
}

function Sparkline({ p, data }: { p: AppViewPrim; data: unknown }) {
  const arr = asList(data, p.from);
  const vals = arr.map((x) => Number(p.y ? (x as Json)[p.y as string] : x)).filter((v) => !isNaN(v));
  if (vals.length < 2) return null;
  const up = !trendClass(p, data) || trendClass(p, data) === 'text-red-500';
  const w = 280, h = 50;
  const mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1;
  const pts = vals.map((v, i) => `${((i / (vals.length - 1)) * w).toFixed(1)},${(h - ((v - mn) / rg) * h).toFixed(1)}`).join(' ');
  return (
    <Card>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-12">
        <polyline points={pts} fill="none" strokeWidth={2} className={up ? 'stroke-red-400' : 'stroke-blue-500'} />
      </svg>
    </Card>
  );
}

function ViewPrim({ p, data, onDrill, onRowAction, busyRow }: {
  p: AppViewPrim; data: unknown;
  onDrill: (p: AppViewPrim, item: Json) => void;
  onRowAction: (action: string, item: Json, rowKey: string) => void;
  busyRow: string | null;
}) {
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
                {((c.lines as string[]) || []).map((l, j) => <div key={j}>{tpl(l, it)}</div>)}
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
                  {img ? <img src={img} loading="lazy" className="w-14 h-20 object-cover rounded-md bg-stone-100 shrink-0" />
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
              {img ? <img src={img} loading="lazy" className="w-full aspect-[3/4] object-cover rounded-lg bg-stone-100" />
                   : <div className="w-full aspect-[3/4] rounded-lg bg-stone-100" />}
              <div className="font-semibold text-xs text-stone-800 mt-1.5">{tpl(p.title, it)}</div>
              <div className="text-[11px] text-stone-500">
                {((p.lines as string[]) || []).map((l, j) => <div key={j}>{tpl(l, it)}</div>)}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (p.type === 'sparkline') return <Sparkline p={p} data={data} />;

  if (p.type === 'list_action') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    const btn = p.button as AppButton | undefined;
    return (
      <>
        {arr.map((it, i) => {
          const rowKey = `${p.type}-${i}`;
          return (
            <Card key={i}>
              <div className="flex items-center gap-3">
                {p.icon != null && <span className="text-lg">{String(p.icon)}</span>}
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-stone-800">{tpl(p.title, it)}</div>
                  <div className="text-xs text-stone-500 truncate">{tpl(p.sub, it)}</div>
                </div>
                {btn && (
                  <button disabled={busyRow === rowKey}
                    onClick={() => onRowAction(btn.action, it, rowKey)}
                    className="px-3 py-1.5 rounded-lg border border-stone-200 text-sm text-stone-800 hover:border-stone-400 disabled:opacity-40">
                    {busyRow === rowKey ? '…' : btn.label || '▶'}
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

function ViewRenderer({ view, data, onDrill, onRowAction, busyRow }: {
  view: AppViewPrim[]; data: Json;
  onDrill: (p: AppViewPrim, item: Json) => void;
  onRowAction: (action: string, item: Json, rowKey: string) => void;
  busyRow: string | null;
}) {
  if (data.error) return <p className="text-sm text-stone-400">{String(data.error)}</p>;
  if (data.success === false) return <p className="text-sm text-stone-400">{String(data.message || '실패')}</p>;
  return (
    <>
      {view.map((p, i) => (
        <ViewPrim key={i} p={p} data={data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} />
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
    return v.replace(/"/g, '');
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

function ModePane({ mode }: { mode: AppMode }) {
  const initVals = useCallback(() => {
    const v: Record<string, string> = {};
    (mode.inputs || []).forEach((inp) => { v[inp.key] = inp.default || ''; });
    if (mode.periods?.items?.length) {
      const def = mode.periods.items.find((x) => x.default) || mode.periods.items[0];
      v[mode.periods.key || 'period'] = String(def.value);
    }
    return v;
  }, [mode]);

  const [values, setValues] = useState<Record<string, string>>(initVals);
  const [data, setData] = useState<Json | null>(null);
  const [drill, setDrill] = useState<{ view: AppViewPrim[]; data: Json } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyRow, setBusyRow] = useState<string | null>(null);
  const valuesRef = useRef(values);
  valuesRef.current = values;

  const run = useCallback(async (override?: Record<string, string>) => {
    if (!mode.action) return;
    const vals = override || valuesRef.current;
    for (const inp of mode.inputs || []) if (inp.required && !vals[inp.key]) return;
    setLoading(true); setError(null); setDrill(null);
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
    setValues(v); setData(null); setDrill(null); setError(null);
    if (mode.auto_run) run(v);
  }, [mode, initVals, run]);

  const onDrill = useCallback(async (p: AppViewPrim, item: Json) => {
    const dc = p.item_click as { action: string; view: AppViewPrim[] } | undefined;
    if (!dc) return;
    setLoading(true); setError(null);
    try {
      const d = await runIBL(rowAction(dc.action, item));
      if (d && typeof d === 'object') (d as Json)._item = item; // 드릴 뷰에서 클릭 행 참조용
      setDrill({ view: dc.view, data: d });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const onRowAction = useCallback(async (action: string, item: Json, rowKey: string) => {
    setBusyRow(rowKey);
    try {
      const d = await runIBL(rowAction(action, item));
      if (d?.error) alert(String(d.error));
    } catch (e) {
      alert('실행 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusyRow(null);
    }
  }, []);

  const fireButton = useCallback(async (b: AppButton) => {
    try {
      const d = await runIBL(b.action);
      if (d?.error) alert(String(d.error));
    } catch (e) {
      alert('실행 실패: ' + (e instanceof Error ? e.message : String(e)));
    }
  }, []);

  const inputs = mode.inputs || [];
  return (
    <div className="max-w-2xl mx-auto p-5">
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

      {mode.periods?.items?.length && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {mode.periods.items.map((x) => {
            const pk = mode.periods!.key || 'period';
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

      {(mode.buttons || []).length > 0 && (
        <div className="flex gap-2 mb-3">
          {mode.buttons!.map((b, i) => (
            <button key={i} onClick={() => fireButton(b)}
              className="px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-sm text-stone-800 hover:border-stone-400">
              {b.label}
            </button>
          ))}
        </div>
      )}

      {loading && <div className="flex justify-center py-8"><div className="w-6 h-6 border-2 border-stone-200 border-t-stone-600 rounded-full animate-spin" /></div>}
      {error && <p className="text-sm text-stone-400">오류: {error}</p>}

      {!loading && drill && (
        <>
          <button onClick={() => setDrill(null)}
            className="text-xs text-stone-500 hover:text-stone-800 mb-2">‹ 결과 목록으로</button>
          <ViewRenderer view={drill.view} data={drill.data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} />
        </>
      )}
      {!loading && !drill && data && mode.view && (
        <ViewRenderer view={mode.view} data={data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} />
      )}
    </div>
  );
}

export function GenericInstrument({ instrument }: { instrument: AppInstrument }) {
  const modes: AppMode[] = instrument.modes || [instrument];
  const [modeIdx, setModeIdx] = useState(0);
  const mode = modes[Math.min(modeIdx, modes.length - 1)];

  return (
    <div className="h-full w-full overflow-auto bg-stone-50">
      {instrument.modes && (
        <div className="flex gap-1.5 max-w-2xl mx-auto px-5 pt-4">
          {instrument.modes.map((m, i) => (
            <button key={i} onClick={() => setModeIdx(i)}
              className={`px-3.5 py-1.5 rounded-lg text-sm border transition ${
                i === modeIdx ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-500 border-stone-200 hover:border-stone-400'}`}>
              {m.name}
            </button>
          ))}
        </div>
      )}
      <ModePane mode={mode} />
    </div>
  );
}
