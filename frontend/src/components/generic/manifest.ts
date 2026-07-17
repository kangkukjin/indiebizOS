/**
 * generic/manifest.ts — 매니페스트 타입 + IBL 실행 + 템플릿 엔진 (비-JSX 공용층)
 *
 * GenericInstrument.tsx 에서 분리(2026-07-18, 1500줄 규칙 모듈화).
 * 진실 소스: ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
 * 원격 런처(api_launcher_web.py 웹앱)와 동일한 렌더 어휘의 데스크탑판 해석기 —
 * 여기엔 타입·runIBL·"{path|filter}" 템플릿·$key 액션 빌드·URL 헬퍼만(비-JSX).
 * JSX 프리미티브는 prims-basic/prims-edit/prims-map-calendar.tsx, 디스패처·본체는
 * GenericInstrument.tsx.
 */

export const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';

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
// phone_only: 폰 네이티브 동작([limbs:phone] 등 runs_on:phone_only)만 하는 버튼 — 맥 데스크탑에선
// 실행 불가(phone_unreachable)라 숨긴다. GenericInstrument(데스크탑 전용 렌더러)만 이 필드를 거른다;
// 원격/폰 렌더러(api_launcher_web)는 무시하고 그대로 노출(폰에선 정상 동작). 계기-레벨 phone_render:false
// (폰에서 mac_only 숨김)의 반대 방향 짝 — 맥에서 phone_only 숨김.
export interface AppButton { label: string; action?: string; refresh?: boolean; stream?: boolean; phone_only?: boolean; confirm?: string }

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
  type: 'metric' | 'kv' | 'kv_list' | 'card_list' | 'image_grid' | 'sparkline' | 'list_action' | 'thread' | 'form' | 'editable_list' | 'map' | 'group' | 'calendar' | 'blocks' | 'media_player';
  [k: string]: unknown;
}

export interface AppFormField {
  key: string;
  label?: string;
  type: 'text' | 'select' | 'toggle' | 'textarea' | 'images' | 'date' | 'time' | 'datetime' | 'recurrence' | 'folder';
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
export type Dispatch = (template: string, fieldValues?: Record<string, string>, rowContext?: Json, opts?: { back?: boolean }) => Promise<boolean>;

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
  top_buttons?: AppButton[];  // 탭과 무관하게 계기 최상단에 항상 보이는 버튼(예: 소개발행). 탭 전환과 독립.
}

export type Json = Record<string, unknown>;

// 뷰-이벤트 콜백 — 프리미티브(현재 map)가 사용자 조작을 액션 템플릿+페이로드로 흘린다. ModePane 가 재조회.
export type ViewEvent = (template: string, payload: Record<string, string>) => void;

export async function runIBL(code: string): Promise<Json> {
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

export function jget(o: unknown, path?: string): unknown {
  if (!path) return o;
  return String(path).split('.').reduce<unknown>((a, k) => (a == null ? undefined : (a as Json)[k]), o);
}

export function applyFilter(v: unknown, f: string): unknown {
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
export function tpl(t: unknown, data: unknown): string {
  if (t == null) return '';
  return String(t).replace(/\{([^{}]+)\}/g, (_, expr: string) => {
    const parts = expr.split('|');
    let v = jget(data, parts[0].trim());
    for (let i = 1; i < parts.length; i++) v = applyFilter(v, parts[i].trim());
    return v == null ? '' : String(v);
  });
}

/** $key 치환 + 빈 입력 'param: ""' 쌍 자동 제거 */
export function buildAction(template: string, values: Record<string, string>): string {
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
export function rowAction(template: string, item: unknown): string {
  return template.replace(/\{([\w.]+)\}/g, (_, path: string) => {
    const v = jget(item, path);
    return v == null ? '' : String(v).replace(/"/g, '');
  });
}

// 한국색: 상승=빨강, 하락=파랑
export function trendClass(p: AppViewPrim, data: unknown): string | null {
  if (!p.trend) return null;
  return (Number(jget(data, p.trend as string)) || 0) >= 0 ? 'text-red-500' : 'text-blue-600';
}

export function asList(data: unknown, from: unknown): Json[] {
  if (from === '.') return [data as Json]; // 응답 자체를 1행으로 (단일 객체에 행 버튼 달기)
  const arr = jget(data, from as string);
  return Array.isArray(arr) ? (arr as Json[]) : [];
}

// compose 채널 선택 후보 — 연락처 배열에서 발신 가능한 채널만, 없으면 기본(primary) 채널로 폴백.
export type ChannelOpt = { key: string; channel_type: string; to: string; label: string };
export function composeChannelOptions(cmp: AppCompose | undefined, data: unknown): ChannelOpt[] {
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

// 메시지 등 텍스트 속 URL 을 인앱 브라우저(런처의 포식 브라우저)로 여는 헬퍼.
// Electron 이면 openInLauncherBrowser(런처 창의 ForageBrowser 탭)로, 아니면 새 탭 폴백.
export function openUrlInApp(url: string) {
  const w = window as unknown as { electron?: { openInLauncherBrowser?: (u: string) => void; openExternal?: (u: string) => void } };
  if (w.electron?.openInLauncherBrowser) w.electron.openInLauncherBrowser(url);
  else if (w.electron?.openExternal) w.electron.openExternal(url);
  else window.open(url, '_blank', 'noopener');
}

// ===== 공용 스타일·포맷 헬퍼 =====

export const fieldCls = 'px-3 py-2 rounded-lg border border-stone-200 bg-white text-sm text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-stone-400';

export function statusGlyph(s: string): string {
  return s === 'sent' ? '✓' : s === 'pending' ? '⏳' : s === 'failed' ? '⚠' : '';
}

// ===== URL 헬퍼 (백엔드 미디어 서빙) =====

export const IMAGE_BASE = IBL_ENDPOINT.replace(/\/ibl\/execute$/, '');  // 'http://127.0.0.1:8765'
export const imageUrl = (p: string) => `${IMAGE_BASE}/image?path=${encodeURIComponent(p)}`;
// view 통화의 image 필드: 절대 URL(http…·data:)이면 그대로, 백엔드 상대경로(/photo/thumbnail?path=…)면 IMAGE_BASE 부착.
// 데스크탑(file://·dev 5173)은 origin이 백엔드와 달라 상대경로가 깨지므로 필수. book/invest 외부 http URL은 무영향.
export const mediaSrc = (u: string) => (u && u.startsWith('/')) ? `${IMAGE_BASE}${u}` : u;
// media_player 오디오 소스: 절대 URL(http/data)은 그대로, 그 외(백엔드 파일 절대경로)는 /launcher/file 로 서빙.
export const audioUrl = (u: string) => !u ? '' : (/^(https?:|data:)/.test(u) ? u : `${IMAGE_BASE}/launcher/file?path=${encodeURIComponent(u)}`);

// 반복 주기 표준 어휘 — recurrence 필드 타입의 baked 옵션(manage_events repeat 값과 일치). date/time 은 네이티브 input.
export const RECURRENCE_OPTS: [string, string][] = [['none', '한 번'], ['daily', '매일'], ['weekly', '매주'], ['monthly', '매월'], ['yearly', '매년']];
export const dateInputType = (t: string) => (t === 'datetime' ? 'datetime-local' : t); // date/time 은 그대로, datetime → datetime-local
