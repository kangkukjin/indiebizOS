/**
 * GenericInstrument — 매니페스트 해석 계기 (앱 표면 제네릭 렌더러의 데스크탑판)
 *
 * 진실 소스: ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
 * 원격 런처(api_launcher_web.py 웹앱)와 동일한 렌더 어휘를 React로 해석한다 —
 * 새 IBL 액션에 app: 블록만 달면 데스크탑·원격에 동시 등장.
 *
 * 어휘 명세: docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md
 *  - view 프리미티브 10종: metric / kv / kv_list / card_list(+item_click 드릴·탭) /
 *    image_grid / sparkline / list_action / thread(채팅 버블+status) /
 *    form(편집 필드+저장) / editable_list(행 CRUD)
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

export interface AppButton { label: string; action: string; refresh?: boolean }

export interface AppCompose {
  placeholder?: string;
  action: string;   // $text=작성 내용, {field}=드릴 행 필드 (예: 대화 상대의 channel/name)
  button?: string;  // 전송 버튼 라벨 (기본 '전송')
  channels?: AppComposeChannels;  // 발신 채널 선택 — 다채널 이웃에서 어느 연락처로 보낼지($channel_type/$to 주입)
}

// compose 채널 선택 — 드릴 데이터의 연락처 배열에서 발신 가능한 채널만 골라 드롭다운 제공.
// 단일(또는 0)이면 드롭다운 없이 기본값 사용. 선택값은 action 의 $channel_type/$to 로 주입.
export interface AppComposeChannels {
  from: string;       // 드릴 데이터의 연락처 배열 필드 (예: contacts)
  type: string;       // 연락처 항목의 채널 타입 필드 (예: contact_type) → channel_type
  value: string;      // 연락처 항목의 주소 필드 (예: contact_value) → to
  sendable?: string[]; // 발신 가능한 채널 타입 화이트리스트 (예: [gmail, nostr]). 생략 시 전부.
}

export interface AppViewPrim {
  type: 'metric' | 'kv' | 'kv_list' | 'card_list' | 'image_grid' | 'sparkline' | 'list_action' | 'thread' | 'form' | 'editable_list';
  [k: string]: unknown;
}

export interface AppFormField {
  key: string;
  label?: string;
  type: 'text' | 'select' | 'toggle' | 'textarea' | 'images';
  value?: string;        // 초기값 템플릿 (데이터에서 채움)
  placeholder?: string;
  options?: { value: string | number; label: string }[];
  // type:'images' 전용 — 업로드 즉시 영속(form save 와 무관). add 는 데스크탑(window.electron)만.
  add_action?: string;    // [..]{op:add_image, ..., path:"$path"} — $path=소스 파일경로
  remove_action?: string; // [..]{op:remove_image, ..., path:"$path"} — $path=제거할 첨부
}

// form 보조 액션 — 저장 외 부가 동작(즐겨찾기 토글·삭제 등). 드릴 데이터 컨텍스트로 실행.
export interface FormAction {
  label: string;       // 표시 템플릿 ({path} 치환 가능)
  action: string;      // IBL 코드 — {path}는 드릴 데이터로 치환
  style?: 'danger';    // 위험(삭제) 스타일
  confirm?: string;    // 클릭 시 확인 다이얼로그 문구
  back?: boolean;      // 성공 후 목록으로 복귀(상세가 사라지는 삭제 등)
}

// 액션 실행기: $field 치환 + {path}(rowContext, 기본 드릴 데이터) 치환 → 실행 → 현재 뷰 새로고침
// opts.back: 성공 시 새로고침 대신 드릴을 닫고 목록으로 복귀(삭제 등 — 현재 상세가 사라지는 경우)
type Dispatch = (template: string, fieldValues?: Record<string, string>, rowContext?: Json, opts?: { back?: boolean }) => Promise<boolean>;

export interface AppFilter {
  key?: string;  // 액션 템플릿이 참조하는 파라미터명 ($key) — 기본 'filter'
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
  filter?: AppFilter;  // 단일선택 필터 칩(기간·레벨 양용) — 클릭 즉시 그 값으로 재조회
  compose?: AppCompose;  // 하단 작성바 (커뮤니티 글 작성 등) — 전송 후 현재 뷰 자동 새로고침
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
  const data = await res.json();
  // 합성(>>) 액션은 final_result(마지막 단계)를 펼쳐 단일 액션처럼 노출 — view의 from/{필드}가 풀리도록
  if (data && typeof data === 'object' && 'final_result' in data) {
    const fr = (data as Record<string, unknown>).final_result;
    if (typeof fr === 'string') {
      try { return JSON.parse(fr) as Json; } catch { return { message: fr } as Json; }
    }
    if (fr && typeof fr === 'object') return fr as Json;
  }
  return data;
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
    // IBL 값은 JSON5 문자열 리터럴로 파싱됨 → 스트립이 아니라 이스케이프(백슬래시·따옴표).
    // 스트립하면 Windows 경로(C:\Users\…)의 백슬래시가 사라져 깨짐. 이스케이프하면 파서가 복원.
    return v == null ? '' : String(v).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
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

// compose 채널 선택 후보 — 연락처 배열에서 발신 가능한 채널만, 없으면 기본(primary) 채널로 폴백.
type ChannelOpt = { key: string; channel_type: string; to: string; label: string };
function composeChannelOptions(cmp: AppCompose | undefined, data: unknown): ChannelOpt[] {
  const ch = cmp?.channels;
  if (!ch || !data || typeof data !== 'object') return [];
  const mk = (channel_type: string, to: string, label: string): ChannelOpt => ({ key: channel_type + '|' + to, channel_type, to, label });
  let opts = asList(data, ch.from)
    .map((c) => ({ ct: String(jget(c, ch.type) ?? ''), to: String(jget(c, ch.value) ?? '') }))
    .filter((o) => o.to && (!ch.sendable || ch.sendable.includes(o.ct)))
    .map((o) => mk(o.ct, o.to, o.ct + ' · ' + o.to));
  if (opts.length === 0) {
    const ct = String(jget(data, 'channel') ?? ''); const to = String(jget(data, 'to') ?? '');
    if (to) opts = [mk(ct, to, ct || '기본')];
  }
  const seen = new Set<string>();
  return opts.filter((o) => (seen.has(o.key) ? false : (seen.add(o.key), true)));
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

const fieldCls = 'px-3 py-2 rounded-lg border border-stone-200 bg-white text-sm text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-stone-400';

function statusGlyph(s: string): string {
  return s === 'sent' ? '✓' : s === 'pending' ? '⏳' : s === 'failed' ? '⚠' : '';
}

// ===== 편집 프리미티브 (form / editable_list) =====

const IMAGE_BASE = IBL_ENDPOINT.replace(/\/ibl\/execute$/, '');  // 'http://127.0.0.1:8765'
const imageUrl = (p: string) => `${IMAGE_BASE}/image?path=${encodeURIComponent(p)}`;

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

function FormPrim({ p, data, dispatch }: { p: AppViewPrim; data: unknown; dispatch: Dispatch }) {
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
              <textarea value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} rows={3} placeholder={f.placeholder || ''} className={`${fieldCls} resize-y`} />
            ) : f.type === 'images' ? (
              <ImagesField f={f} value={vals[f.key] ?? ''} dispatch={dispatch} busy={saving} setBusy={setSaving} />
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

function EditableListPrim({ p, data, dispatch }: { p: AppViewPrim; data: unknown; dispatch: Dispatch }) {
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

function ViewPrim({ p, data, onDrill, onRowAction, busyRow, dispatch }: {
  p: AppViewPrim; data: unknown;
  onDrill: (p: AppViewPrim, item: Json) => void;
  onRowAction: (action: string, item: Json, rowKey: string) => void;
  busyRow: string | null;
  dispatch: Dispatch;
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

  if (p.type === 'form') return <FormPrim p={p} data={data} dispatch={dispatch} />;
  if (p.type === 'editable_list') return <EditableListPrim p={p} data={data} dispatch={dispatch} />;

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

function ViewRenderer({ view, data, onDrill, onRowAction, busyRow, dispatch }: {
  view: AppViewPrim[]; data: Json;
  onDrill: (p: AppViewPrim, item: Json) => void;
  onRowAction: (action: string, item: Json, rowKey: string) => void;
  busyRow: string | null;
  dispatch: Dispatch;
}) {
  if (data.error) return <p className="text-sm text-stone-400">{String(data.error)}</p>;
  if (data.success === false) return <p className="text-sm text-stone-400">{String(data.message || '실패')}</p>;
  return (
    <>
      {view.map((p, i) => (
        <ViewPrim key={i} p={p} data={data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} dispatch={dispatch} />
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
  const [tabIdx, setTabIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyRow, setBusyRow] = useState<string | null>(null);
  const [composeText, setComposeText] = useState('');
  const [composeCh, setComposeCh] = useState('');  // 선택된 발신 채널 키 (빈값=첫 후보)
  const [sending, setSending] = useState(false);
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
    setValues(v); setData(null); setDrill(null); setError(null); setComposeText(''); setComposeCh('');
    if (mode.auto_run) run(v);
  }, [mode, initVals, run]);

  const onDrill = useCallback(async (p: AppViewPrim, item: Json) => {
    const dc = p.item_click as { action: string; view?: AppViewPrim[]; compose?: AppCompose; tabs?: DrillTab[] } | undefined;
    if (!dc) return;
    setLoading(true); setError(null); setComposeText(''); setComposeCh(''); setTabIdx(0);
    try {
      const code = rowAction(dc.action, item);
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
      let code = buildAction(template, fieldValues || {});
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
    const extra = sel ? { channel_type: sel.channel_type, to: sel.to } : {};
    const ok = await dispatch(cmp.action, { text, ...extra });
    if (ok) setComposeText('');
    setSending(false);
  }, [composeText, composeCh, drill, dispatch]);

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
      if (d?.error) { alert(String(d.error)); return; }
      if (b.refresh) run();  // 실행 후 현재 모드 재조회(토글/재생성 결과 즉시 반영)
    } catch (e) {
      alert('실행 실패: ' + (e instanceof Error ? e.message : String(e)));
    }
  }, [run]);

  const inputs = mode.inputs || [];
  // master_detail card_list → 반응형 2분할(PC: 리스트 좌+상세 우 동시 / 폰: 리스트→선택→상세→뒤로)
  const isSplit = !mode.modes && (mode.view || []).some((p) => p.type === 'card_list' && !!p.master_detail);
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
      data={drill.data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} dispatch={dispatch} />
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

      {/* === master-detail 반응형: PC=2분할(리스트+상세 동시) / 폰=드릴(선택→상세→뒤로) === */}
      {isSplit && !loading && data && (
        <div className="flex flex-col md:flex-row gap-3 md:h-[calc(100vh-210px)]">
          <div className={`md:w-72 md:shrink-0 md:overflow-y-auto md:pr-1 ${drill ? 'hidden md:block' : 'block'}`}>
            <ViewRenderer view={mode.view || []} data={data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} dispatch={dispatch} />
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
      {!isSplit && !loading && !drill && data && mode.view && (
        <ViewRenderer view={mode.view} data={data} onDrill={onDrill} onRowAction={onRowAction} busyRow={busyRow} dispatch={dispatch} />
      )}
      {!isSplit && (() => {
        const cmp = drill ? activeCompose : mode.compose;
        if (!cmp || loading || (!drill && !data)) return null;
        return <div className="-mx-5 px-5">{composeBarEl(cmp)}</div>;
      })()}
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
