/**
 * GenericInstrument — 매니페스트 해석 계기 (앱 표면 제네릭 렌더러의 데스크탑판)
 *
 * 진실 소스: ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
 * 원격 런처(api_launcher_web.py 웹앱)와 동일한 렌더 어휘를 React로 해석한다 —
 * 새 IBL 액션에 app: 블록만 달면 데스크탑·원격에 동시 등장.
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
import { useState, useEffect, useRef, useCallback, useMemo, type ReactNode } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { StreamPlayer } from './StreamPlayer';
import type { StreamData } from './chat/chatUtils';

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

// stream:true 버튼은 클라이언트 측 스트림 재생(StreamPlayer) — 행 데이터(url/playable)를
// 직접 플레이어로 연다. 이 경우 action 은 불필요(서버 IBL 호출 없음).
export interface AppButton { label: string; action?: string; refresh?: boolean; stream?: boolean }

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
  type: 'metric' | 'kv' | 'kv_list' | 'card_list' | 'image_grid' | 'sparkline' | 'list_action' | 'thread' | 'form' | 'editable_list' | 'map' | 'group' | 'calendar' | 'blocks';
  [k: string]: unknown;
}

export interface AppFormField {
  key: string;
  label?: string;
  type: 'text' | 'select' | 'toggle' | 'textarea' | 'images' | 'date' | 'time' | 'datetime' | 'recurrence';
  value?: string;        // 초기값 템플릿 (데이터에서 채움)
  placeholder?: string;
  options?: { value: string | number; label: string }[];
  // type:'images' 전용 — 업로드 즉시 영속(form save 와 무관). add 는 데스크탑(window.electron)만.
  add_action?: string;    // [..]{op:add_image, ..., path:"$path"} — $path=소스 파일경로
  remove_action?: string; // [..]{op:remove_image, ..., path:"$path"} — $path=제거할 첨부
  // type:'textarea' 전용 — ai_dock 어피던스(요청→제안→반영/첨부/닫기). BinNote 656 UX 를 어휘로.
  // action 은 $<필드키>(현재 텍스트)·$dock(요청)을 주입받고, 결과 스칼라 텍스트가 제안이 된다.
  ai_dock?: { action: string; modes?: ('replace' | 'append')[]; placeholder?: string };
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
  key?: string;  // 정적 필터: 액션 템플릿이 참조하는 파라미터명 ($key) — 기본 'filter'
  items?: { label: string; value: string | number; default?: boolean }[];  // 정적 칩(선택 시 재조회)
  // 동적 필터: 결과 items 의 이 필드 distinct 값으로 칩 생성 + 클라이언트 측 거르기(재조회 없음).
  from_field?: string;
  from?: string;  // 거를 배열 경로 (기본 'items')
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
  system?: boolean;  // 런처 직속 시스템 표면(메신저·커뮤니티) — 데스크탑 앱 그리드에서 제외
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
// view 통화의 image 필드: 절대 URL(http…·data:)이면 그대로, 백엔드 상대경로(/photo/thumbnail?path=…)면 IMAGE_BASE 부착.
// 데스크탑(file://·dev 5173)은 origin이 백엔드와 달라 상대경로가 깨지므로 필수. book/invest 외부 http URL은 무영향.
const mediaSrc = (u: string) => (u && u.startsWith('/')) ? `${IMAGE_BASE}${u}` : u;

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

// 반복 주기 표준 어휘 — recurrence 필드 타입의 baked 옵션(manage_events repeat 값과 일치). date/time 은 네이티브 input.
const RECURRENCE_OPTS: [string, string][] = [['none', '한 번'], ['daily', '매일'], ['weekly', '매주'], ['monthly', '매월'], ['yearly', '매년']];
const dateInputType = (t: string) => (t === 'datetime' ? 'datetime-local' : t); // date/time 은 그대로, datetime → datetime-local

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
              <>
                <textarea value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} rows={3} placeholder={f.placeholder || ''} className={`${fieldCls} resize-y`} />
                {f.ai_dock && <AiDock field={f} value={vals[f.key] ?? ''} vals={vals} onApply={(v) => set(f.key, v)} />}
              </>
            ) : f.type === 'images' ? (
              <ImagesField f={f} value={vals[f.key] ?? ''} dispatch={dispatch} busy={saving} setBusy={setSaving} />
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

// 지도 마커 아이콘 — 번들러 이미지 의존 없는 divIcon (DirectionsInstrument 선례)
const dotIcon = (color: string) => L.divIcon({
  className: '',
  html: `<div style="width:16px;height:16px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
  iconSize: [16, 16], iconAnchor: [8, 8],
});
const escHtml = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));

type MapEnvelope = {
  path?: [number, number][]; center?: { lat: number; lng: number };
  origin?: { lat: number; lng: number; name?: string }; destination?: { lat: number; lng: number; name?: string };
  markers?: { lat?: number; lng?: number; name?: string }[];
};
// 뷰-이벤트 콜백 — 프리미티브(현재 map)가 사용자 조작을 액션 템플릿+페이로드로 흘린다. ModePane 가 재조회.
type ViewEvent = (template: string, payload: Record<string, string>) => void;

/** map 프리미티브 — leaflet. 정적(원격 initMaps 동치) + 인터랙티브(`on:` 뷰-이벤트).
 *  봉투(p.from, 기본 map_data): {center, markers:[{lat,lng,name}], path:[[lat,lng]], origin, destination}
 *  p.markers: 추가 마커 리스트 경로(예: items) — 각 {lat,lng,name|title,meta,url,id}. p.max=마커 상한.
 *  p.on(인터랙티브): {moveend|center_drag: 재조회 템플릿($lat/$lng/$radius), marker_click: 마커 액션($id/$name/$lat/$lng/$url) | {stream:true}=마커 영상 재생(CCTV)}.
 *  ★루프 가드: fitBounds 는 첫 로드만(interactive 면 didFit 후 안 함) — 재조회→마커갱신은 viewport 유지.
 *           moveend 는 progMove(프로그래매틱 이동) 무시 + 디바운스. */
function MapPrim({ p, data, onViewEvent, onStream }: { p: AppViewPrim; data: unknown; onViewEvent?: ViewEvent; onStream?: (item: Json) => void }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const readyRef = useRef(false);   // 초기 fit 정착 후 true — 그 전(프로그래매틱 fit)의 moveend 는 무시(피드백 루프 차단)
  const didFit = useRef(false);
  const debounceRef = useRef<number | null>(null);
  const pRef = useRef(p);
  const evRef = useRef(onViewEvent);
  const streamRef = useRef(onStream);
  // 최신값 ref 동기화 — 렌더 중 ref 쓰기(react-hooks/refs 위반) 대신 커밋 후 effect 로. 이 ref 들은 이벤트 핸들러(마커클릭·moveend)에서만 읽혀 한 틱 지연 무관.
  useEffect(() => { pRef.current = p; evRef.current = onViewEvent; streamRef.current = onStream; });

  const on = (p.on as Record<string, string | { stream?: boolean }> | undefined) || undefined;
  // viewport 보존(첫 로드만 fit) 모드는 *이동 재조회*(moveend/center_drag)가 있을 때만.
  // marker_click(스트림/액션)만 있는 경우는 정적 fit 유지(CCTV: 매 검색마다 새 결과로 재fit).
  const interactive = !!(on && (on.moveend || on.center_drag));

  const fireMove = useCallback((lat: number, lng: number) => {
    const pon = pRef.current.on as Record<string, string | { stream?: boolean }> | undefined;
    const tpl = (pon?.moveend || pon?.center_drag) as string | undefined;
    const map = mapRef.current;
    if (!tpl || !map || !evRef.current) return;
    const r = Math.round(map.distance(map.getCenter(), map.getBounds().getNorthEast())); // viewport 반경(m)
    evRef.current(tpl, { lat: lat.toFixed(6), lng: lng.toFixed(6), radius: String(r) });
  }, []);

  // 지도 1회 생성 + 사용자 이동 이벤트 바인딩 (data 변경에도 재생성 안 함 → viewport 보존)
  useEffect(() => {
    const el = ref.current;
    if (!el || mapRef.current) return;
    const map = L.map(el, { attributionControl: false });
    mapRef.current = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    const pon = pRef.current.on as Record<string, string | { stream?: boolean }> | undefined;
    const moveTpl = pon?.moveend || pon?.center_drag;
    if (moveTpl) {
      map.on('moveend', () => {
        if (!readyRef.current) return; // 초기 fit 정착 전(프로그래매틱 이동)은 무시
        if (debounceRef.current) window.clearTimeout(debounceRef.current);
        const c = map.getCenter();
        debounceRef.current = window.setTimeout(() => fireMove(c.lat, c.lng), 600); // 잦은 팬 디바운스
      });
    }
    setTimeout(() => map.invalidateSize(), 60);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      map.remove(); mapRef.current = null; layerRef.current = null; didFit.current = false;
    };
  }, [fireMove]);

  // data 변경 → 마커/경로 다시 그림 (지도 유지). fit 은 첫 로드만(인터랙티브)·매번(정적).
  useEffect(() => {
    const map = mapRef.current, layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const md = ((p.from ? jget(data, p.from as string) : data) || {}) as MapEnvelope;
    let mk = p.markers ? asList(data, p.markers) : [];
    const max = typeof p.max === 'number' ? p.max : undefined;
    if (max && mk.length > max) mk = mk.slice(0, max); // 마커 폭주 방지(상권 등 수천건)
    const B: [number, number][] = [];
    if (md.path && md.path.length) {
      L.polyline(md.path, { color: '#e11d48', weight: 5, opacity: 0.85 }).addTo(layer);
      md.path.forEach((ll) => B.push(ll));
      if (md.origin) { L.marker([md.origin.lat, md.origin.lng], { icon: dotIcon('#22C55E') }).addTo(layer).bindPopup('출발 · ' + escHtml(md.origin.name || '')); B.push([md.origin.lat, md.origin.lng]); }
      if (md.destination) { L.marker([md.destination.lat, md.destination.lng], { icon: dotIcon('#EF4444') }).addTo(layer).bindPopup('도착 · ' + escHtml(md.destination.name || '')); B.push([md.destination.lat, md.destination.lng]); }
    }
    (md.markers || []).forEach((m) => { if (m.lat == null || m.lng == null) return; L.marker([m.lat, m.lng], { icon: dotIcon('#0284c7') }).addTo(layer).bindPopup(escHtml(m.name || '')); B.push([m.lat, m.lng]); });
    // marker_click: IBL 템플릿(문자열·재조회) | {stream:true}(마커 url 영상 재생, IBL 없음) | 없음(팝업).
    const clickSpec = on?.marker_click;
    const clickStream = !!(clickSpec && typeof clickSpec === 'object' && (clickSpec as { stream?: boolean }).stream);
    const clickTpl = typeof clickSpec === 'string' ? clickSpec : undefined;
    mk.forEach((m) => {
      const r = m as { lat?: number; lng?: number; name?: string; title?: string; meta?: string; url?: string; id?: string | number };
      if (r.lat == null || r.lng == null) return;
      const marker = L.marker([r.lat, r.lng], { icon: dotIcon('#0284c7') }).addTo(layer);
      if (clickStream && streamRef.current) {
        marker.on('click', () => streamRef.current!(m as Json));  // 행 데이터(url/playable/name/lat/lng) → StreamPlayer
      } else if (clickTpl && evRef.current) {
        marker.on('click', () => evRef.current!(clickTpl, {
          id: String(r.id ?? ''), name: String(r.name ?? r.title ?? ''),
          lat: String(r.lat), lng: String(r.lng), url: String(r.url ?? ''),
        }));
      } else {
        const popup = '<b>' + escHtml(r.name || r.title || '마커') + '</b>' + (r.meta ? '<br>' + escHtml(r.meta) : '') +
          (r.url ? '<br><a href="' + escHtml(r.url) + '" target="_blank">상세 →</a>' : '');
        marker.bindPopup(popup);
      }
      B.push([r.lat, r.lng]);
    });
    const shouldFit = !interactive || !didFit.current; // 인터랙티브는 첫 로드만 fit(이후 viewport 보존)
    if (shouldFit && B.length) { map.fitBounds(B, { padding: [28, 28], maxZoom: 15, animate: false }); didFit.current = true; }
    else if (shouldFit && md.center && md.center.lat != null) { map.setView([md.center.lat, md.center.lng], 13, { animate: false }); didFit.current = true; }
    else if (shouldFit) { map.setView([37.4979, 127.0276], 11); didFit.current = true; }
    // 초기 fit 정착 후 사용자 이동만 재조회로 인정(프로그래매틱 fit 의 moveend 무시)
    if (interactive && shouldFit) setTimeout(() => { readyRef.current = true; }, 700);
    setTimeout(() => map.invalidateSize(), 0);
  }, [p, data, interactive, on]);
  return <div ref={ref} style={{ height: 320 }} className="rounded-xl overflow-hidden bg-stone-100 mb-2.5" />;
}

// calendar 프리미티브 — 월 그리드 + 선택일 상세 + 정기목록 + 추가/삭제. 데이터=manifest items(자동 월필터),
// add/delete=dispatch. bespoke CalendarInstrument 를 대체(단일소스). add.fields 는 form 필드 어휘 재사용(date 자동주입).
const CAL_TYPE_COLOR: Record<string, string> = {
  birthday: 'bg-pink-400', anniversary: 'bg-rose-400', holiday: 'bg-red-400',
  meeting: 'bg-blue-400', task: 'bg-amber-400', report: 'bg-violet-400', schedule: 'bg-teal-400',
};
const CAL_REPEAT_LABEL: Record<string, string> = { daily: '매일', weekly: '매주', monthly: '매월', yearly: '매년', interval: '주기' };
const pad2 = (n: number) => String(n).padStart(2, '0');
type CalEvt = { id?: string; date?: string; time?: string; title?: string; repeat?: string; type?: string; description?: string };

function CalendarPrim({ p, data, dispatch }: { p: AppViewPrim; data: unknown; dispatch: Dispatch }) {
  const events = asList(data, p.from) as CalEvt[];
  const colorField = (p.color_field as string) || 'type';
  const colorOf = (e: CalEvt) => CAL_TYPE_COLOR[String((e as Record<string, unknown>)[colorField] ?? '')] || 'bg-stone-400';
  const today = useMemo(() => new Date(), []);
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1); // 1-12
  const [selDay, setSelDay] = useState<number | null>(today.getDate());
  const [addVals, setAddVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const add = p.add as { fields?: AppFormField[]; action: string; button?: string } | undefined;

  // 날짜 명확 이벤트(none/monthly/yearly)를 일자 → 이벤트[] 로 매핑 (bespoke 로직 그대로)
  const eventsByDay = useMemo(() => {
    const map: Record<number, CalEvt[]> = {};
    const daysInMonth = new Date(year, month, 0).getDate();
    for (const e of events) {
      const rep = e.repeat || 'none';
      const parsed = e.date ? e.date.split('-').map(Number) : null;
      let day: number | null = null;
      if (rep === 'none' && parsed && parsed[0] === year && parsed[1] === month) day = parsed[2];
      else if (rep === 'monthly' && parsed) day = parsed[2];
      else if (rep === 'yearly' && parsed && parsed[1] === month) day = parsed[2];
      if (day && day >= 1 && day <= daysInMonth) (map[day] ||= []).push(e);
    }
    return map;
  }, [events, year, month]);
  const recurring = useMemo(() => events.filter((e) => ['daily', 'weekly', 'interval'].includes(e.repeat || '')), [events]);
  const cells = useMemo(() => {
    const firstWd = new Date(year, month - 1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();
    const arr: (number | null)[] = Array(firstWd).fill(null);
    for (let d = 1; d <= daysInMonth; d++) arr.push(d);
    while (arr.length % 7 !== 0) arr.push(null);
    return arr;
  }, [year, month]);
  const go = (delta: number) => { let m = month + delta, y = year; if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; } setMonth(m); setYear(y); setSelDay(null); };
  const isToday = (d: number) => today.getFullYear() === year && today.getMonth() + 1 === month && today.getDate() === d;
  const selEvents = selDay ? (eventsByDay[selDay] || []) : [];

  const doAdd = async () => {
    if (!add || !selDay) return;
    const date = `${year}-${pad2(month)}-${pad2(selDay)}`;
    setBusy(true);
    const ok = await dispatch(add.action, { ...addVals, date });
    if (ok) setAddVals({});
    setBusy(false);
  };
  const del = async (e: CalEvt) => { if (!p.delete_action) return; setBusy(true); await dispatch(p.delete_action as string, {}, e as Json); setBusy(false); };

  const WD = ['일', '월', '화', '수', '목', '금', '토'];
  return (
    <Card>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <button onClick={() => go(-1)} className="w-7 h-7 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-500">‹</button>
          <div className="text-base font-semibold tabular-nums">{year}년 {month}월</div>
          <button onClick={() => go(1)} className="w-7 h-7 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-500">›</button>
        </div>
        <button onClick={() => { setYear(today.getFullYear()); setMonth(today.getMonth() + 1); setSelDay(today.getDate()); }}
          className="px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-xs text-stone-600 hover:bg-stone-50">오늘</button>
      </div>
      <div className="grid grid-cols-7 mb-1">
        {WD.map((w, i) => <div key={w} className={`text-center text-xs py-1 ${i === 0 ? 'text-rose-500' : i === 6 ? 'text-blue-500' : 'text-stone-400'}`}>{w}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (d === null) return <div key={i} className="min-h-[3.25rem]" />;
          const evs = eventsByDay[d] || [];
          const wd = i % 7;
          const sel = selDay === d;
          return (
            <button key={i} onClick={() => setSelDay(d)}
              className={`min-h-[3.25rem] rounded-lg border p-1 flex flex-col items-stretch text-left transition ${sel ? 'border-stone-800 bg-white shadow-sm' : 'border-stone-200 bg-white hover:border-stone-400'}`}>
              <span className={`self-start text-xs leading-none ${isToday(d) ? 'w-5 h-5 flex items-center justify-center rounded-full bg-stone-800 text-white' : wd === 0 ? 'text-rose-500' : wd === 6 ? 'text-blue-500' : 'text-stone-600'}`}>{d}</span>
              <div className="mt-0.5 space-y-0.5 overflow-hidden">
                {evs.slice(0, 2).map((e, k) => <div key={k} title={e.title} className={`truncate rounded px-1 py-0.5 text-[10px] leading-tight text-white ${colorOf(e)}`}>{e.title}</div>)}
                {evs.length > 2 && <div className="px-1 text-[10px] text-stone-400">+{evs.length - 2}</div>}
              </div>
            </button>
          );
        })}
      </div>
      {selDay && (
        <div className="mt-3">
          <div className="text-sm font-medium text-stone-700 mb-1.5">{month}월 {selDay}일 {isToday(selDay) && <span className="text-xs text-stone-400">(오늘)</span>}</div>
          {selEvents.length === 0 ? <div className="text-sm text-stone-400 py-1">일정 없음</div> : (
            <div className="space-y-1.5">
              {selEvents.map((e, k) => (
                <div key={k} className="bg-white rounded-xl border border-stone-200 px-3 py-2 flex items-start gap-2.5">
                  <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${colorOf(e)}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">{e.title}
                      {e.time && <span className="ml-2 text-xs text-stone-400">{e.time}</span>}
                      {e.repeat && e.repeat !== 'none' && <span className="ml-2 text-[11px] text-stone-400">{CAL_REPEAT_LABEL[e.repeat] || e.repeat}</span>}
                    </div>
                    {e.description && <div className="text-xs text-stone-500 mt-0.5">{e.description}</div>}
                  </div>
                  {p.delete_action != null && e.id && <button disabled={busy} onClick={() => del(e)} title="삭제" className="shrink-0 text-stone-300 hover:text-rose-500 leading-none disabled:opacity-40">✕</button>}
                </div>
              ))}
            </div>
          )}
          {add && (
            <div className="mt-2 flex flex-wrap gap-2 items-center">
              {(add.fields || [{ key: 'title', type: 'text', placeholder: '일정 제목' }]).map((f, i) => (
                <CalField key={i} f={f} value={addVals[f.key] ?? ''} onChange={(v) => setAddVals((s) => ({ ...s, [f.key]: v }))} />
              ))}
              <button disabled={busy} onClick={doAdd} className="px-3 py-2 rounded-lg bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40 shrink-0">{add.button || '추가'}</button>
            </div>
          )}
        </div>
      )}
      {recurring.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-stone-400 mb-1.5">정기 일정</div>
          <div className="flex flex-wrap gap-1.5">
            {recurring.map((e, k) => (
              <span key={k} className="px-2.5 py-1 rounded-full bg-white border border-stone-200 text-xs text-stone-600">
                <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${colorOf(e)}`} />
                {e.title}<span className="ml-1.5 text-stone-400">{CAL_REPEAT_LABEL[e.repeat || ''] || e.repeat}{e.time ? ` ${e.time}` : ''}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// calendar add 폼의 단일 필드 렌더 — form 필드 어휘 재사용(text/time/date/recurrence/select/textarea)
function CalField({ f, value, onChange }: { f: AppFormField; value: string; onChange: (v: string) => void }) {
  const cls = `${fieldCls} shrink-0`;
  if (f.type === 'select') return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={cls}>
      <option value="">{f.placeholder || '선택'}</option>
      {(f.options || []).map((o, j) => <option key={j} value={String(o.value)}>{o.label}</option>)}
    </select>
  );
  if (f.type === 'recurrence') return (
    <select value={value || 'none'} onChange={(e) => onChange(e.target.value)} className={cls}>
      {RECURRENCE_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
  if (f.type === 'textarea') return <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={f.placeholder || ''} className={`${fieldCls} flex-1 min-w-[8rem]`} />;
  if (f.type === 'date' || f.type === 'time' || f.type === 'datetime') return <input type={dateInputType(f.type)} value={value} onChange={(e) => onChange(e.target.value)} className={cls} />;
  return <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={f.placeholder || ''} className={`${fieldCls} flex-1 min-w-[8rem]`} />;
}

// ===== blocks — 문서 IR 렌더 (표현 언어 층위 조항: 페이로드 IR의 정적 부분집합이 표면 언어에 옴) =====
// [self:read]{blocks:true}·[table:structure] 출력(items=블록 배열 {type,...})을 문서로 그린다.
// 블록 구조는 IR이 정본 — 여기선 인라인 마크다운(**굵게**·`코드`·[링크](url))만 얇게 해석.
const MD_INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;
function mdInline(text: unknown): ReactNode[] {
  return String(text ?? '').split(MD_INLINE_RE).filter(Boolean).map((seg, i) => {
    if (seg.startsWith('**') && seg.endsWith('**') && seg.length > 4) return <strong key={i}>{seg.slice(2, -2)}</strong>;
    if (seg.startsWith('`') && seg.endsWith('`') && seg.length > 2) return <code key={i} className="bg-stone-100 px-1 rounded text-[0.88em]">{seg.slice(1, -1)}</code>;
    const m = seg.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (m) return <a key={i} href={m[2]} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">{m[1]}</a>;
    return <span key={i}>{seg}</span>;
  });
}

const HEADING_CLS: Record<number, string> = {
  1: 'text-xl mt-4 mb-2',
  2: 'text-lg mt-4 mb-1.5 border-b border-stone-200 pb-1',
  3: 'text-base mt-3 mb-1',
  4: 'text-sm mt-2.5 mb-1',
};

function DocBlock({ b }: { b: Json }) {
  const t = String(b.type || 'paragraph');
  if (t === 'heading') {
    const lvl = Math.min(6, Math.max(1, Number(b.level) || 2));
    return <div className={`font-bold text-stone-900 ${HEADING_CLS[lvl] || 'text-sm mt-2 mb-1'}`}>{mdInline(b.text)}</div>;
  }
  if (t === 'list') {
    const items = (Array.isArray(b.items) ? b.items : []) as unknown[];
    const Tag = (b.ordered ? 'ol' : 'ul') as 'ol' | 'ul';
    return (
      <Tag className={`${b.ordered ? 'list-decimal' : 'list-disc'} pl-5 my-1.5 space-y-1`}>
        {items.map((it, i) => {
          const o = (typeof it === 'object' && it !== null ? it : null) as Json | null;
          const text = o ? String(o.text ?? '') : String(it ?? '');
          const url = o?.url ? String(o.url) : '';
          return (
            <li key={i} className="text-sm text-stone-700 leading-relaxed whitespace-pre-wrap">
              {url
                ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">{text}</a>
                : mdInline(text)}
            </li>
          );
        })}
      </Tag>
    );
  }
  if (t === 'table') {
    const cols = (Array.isArray(b.columns) ? b.columns : []) as unknown[];
    const rows = (Array.isArray(b.rows) ? b.rows : []).filter((r) => Array.isArray(r)) as unknown[][];
    return (
      <div className="overflow-x-auto my-2">
        <table className="text-sm border-collapse w-full">
          {cols.length > 0 && (
            <thead><tr>{cols.map((c, i) => <th key={i} className="border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-left font-semibold text-stone-700">{String(c ?? '')}</th>)}</tr></thead>
          )}
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j} className="border border-stone-200 px-2.5 py-1.5 text-stone-700">{String(c ?? '')}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (t === 'quote') {
    return (
      <blockquote className="border-l-4 border-stone-300 pl-3 my-2 text-sm text-stone-500 whitespace-pre-wrap">
        {mdInline(b.text)}
        {!!b.cite && <cite className="block mt-1 text-xs not-italic text-stone-400">— {String(b.cite)}</cite>}
      </blockquote>
    );
  }
  if (t === 'code') {
    return <pre className="bg-stone-50 border border-stone-200 rounded-lg p-3 my-2 text-xs overflow-x-auto"><code>{String(b.text ?? '')}</code></pre>;
  }
  if (t === 'divider') return <hr className="my-3 border-stone-200" />;
  if (t === 'image') {
    const src = String(b.src || b.path || '');
    if (!src) return null;
    return (
      <figure className="my-2">
        <img src={src} alt={String(b.caption ?? '')} className="max-w-full rounded-lg" loading="lazy" />
        {!!b.caption && <figcaption className="text-xs text-stone-400 text-center mt-1">{String(b.caption)}</figcaption>}
      </figure>
    );
  }
  return <p className="text-sm text-stone-700 leading-relaxed my-1.5 whitespace-pre-wrap">{mdInline(b.text)}</p>;
}

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

  if (p.type === 'form') return <FormPrim p={p} data={data} dispatch={dispatch} />;
  if (p.type === 'editable_list') return <EditableListPrim p={p} data={data} dispatch={dispatch} />;
  if (p.type === 'calendar') return <CalendarPrim p={p} data={data} dispatch={dispatch} />;

  if (p.type === 'list_action') {
    const arr = asList(data, p.from);
    if (!arr.length) return <EmptyMsg p={p} data={data} />;
    const btn = p.button as AppButton | undefined;
    const btn2 = p.button2 as AppButton | undefined;
    return (
      <>
        {arr.map((it, i) => {
          const rowKey = `${p.type}-${i}`;
          const rowKey2 = `${p.type}-${i}-2`;
          return (
            <Card key={i} onClick={p.item_click ? () => onDrill(p, it) : undefined}>
              <div className="flex items-center gap-3">
                {p.icon != null && <span className="text-lg">{String(p.icon)}</span>}
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-stone-800">{tpl(p.title, it)}</div>
                  <div className="text-xs text-stone-500 truncate">{tpl(p.sub, it)}</div>
                </div>
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
