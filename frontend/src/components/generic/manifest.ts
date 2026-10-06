import { createContext } from 'react';
import { iblSurface } from '../../lib/remote-session';
/**
 * generic/manifest.ts — 매니페스트 타입 + IBL 실행 + 데스크탑 전용 헬퍼 (비-JSX 공용층)
 *
 * GenericInstrument.tsx 에서 분리(2026-07-18, 1500줄 규칙 모듈화).
 * 진실 소스: ibl_nodes_src 액션의 app: 블록 → GET /launcher/instruments 자동 파생.
 *
 * ★렌더 어휘의 *순수 로직*(템플릿 엔진·액션 빌드·스파크라인 좌표·달력 월 산식·compose 채널·
 *   미디어 소스 결정…)은 원격/폰 표면과 **단일 소스**다 — backend/static/app_render_core.js.
 *   여기서는 그것을 import 해 재수출하고(기존 import 경로 보존), 데스크탑에만 있는 것
 *   (runIBL 엔드포인트·Tailwind 색·백엔드 origin URL 헬퍼·타입)만 직접 갖는다.
 *   로직을 여기 다시 적지 말 것 — scripts/check_render_core.py 가 재정의를 막는다.
 *
 * JSX 프리미티브는 prims-basic/prims-edit/prims-map-calendar.tsx, 디스패처·본체는
 * GenericInstrument.tsx.
 */
import { BACKEND_ORIGIN } from '../../lib/backend-origin';
import {
  jget, applyFilter, tplWith, templateNames, requestCode, approvalChallenge, viewList,
  appRequest, actionRequest,
  emptyText, trendUp, statusGlyph, unwrapFinalResult,
  groupPartition, fmtSpark, sparkModel,
  calendarModel, calShift, pad2,
  composeChannelOptions, isSlowNet, preloadOf, mediaModel, shuffleNext,
  isBackendRoute, resolveMediaUrl,
  hasMasterDetail, dynFilterCats, applyDynFilter, parseImagePaths,
  RECURRENCE_OPTS, dateInputType,
} from '../../../../backend/static/app_render_core.js';

// 공용 코어 재수출 — 소비자(프리미티브들)는 종전처럼 './generic/manifest' 에서 가져간다.
export {
  jget, applyFilter, tplWith, templateNames, requestCode, approvalChallenge, appRequest, actionRequest,
  emptyText, statusGlyph, unwrapFinalResult,
  groupPartition, fmtSpark, sparkModel,
  calendarModel, calShift, pad2,
  composeChannelOptions, isSlowNet, preloadOf, mediaModel, shuffleNext,
  isBackendRoute, resolveMediaUrl,
  hasMasterDetail, dynFilterCats, applyDynFilter, parseImagePaths,
  RECURRENCE_OPTS, dateInputType,
};

export const IBL_ENDPOINT = `${BACKEND_ORIGIN}/ibl/execute`;

// 판본 2 표면 바인딩 요청 봉투(공용 코어 appRequest 의 반환) — 치환 없는 원문 + 타입 보존 inputs + 참조 이름.
export interface AppRequest { code: string; edition: 2; inputs: Record<string, unknown>; declared_inputs: string[] }
export type ActionReq = string | AppRequest;  // 빌더(appRequest·actionRequest)는 공용 코어 — JSDoc 타입을 TS 가 그대로 읽는다.

// ===== 매니페스트 타입 (느슨하게 — 서버 파생 JSON이 진실) =====

export interface AppInput {
  key: string;
  type: 'text' | 'select' | 'file';   // file: 선택 즉시 /launcher/upload 로 올리고 값=서버 절대경로
  browse?: string;  // text 입력이 파일 경로일 때: 데스크탑은 이 폴더에서 시작하는 파일 창으로 고른다(그 외 표면은 글자 입력 그대로)
  accept?: string;                     // file 전용 — <input accept> 필터 (예 'image/*,.pdf')
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
// (폰에서 pc_only 숨김)의 반대 방향 짝 — 맥에서 phone_only 숨김.
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
  type: 'metric' | 'kv' | 'kv_list' | 'card_list' | 'image_grid' | 'sparkline' | 'list_action' | 'thread' | 'form' | 'editable_list' | 'map' | 'group' | 'calendar' | 'blocks' | 'media_player' | 'engine';
  [k: string]: unknown;
}

export interface AppFormField {
  key: string;
  label?: string;
  type: 'text' | 'select' | 'toggle' | 'textarea' | 'images' | 'date' | 'time' | 'datetime' | 'recurrence' | 'folder' | 'files';
  value?: string;        // 초기값 템플릿 (데이터에서 채움)
  placeholder?: string;
  rows?: number;         // type:'textarea' — 줄 수(기본 3; 문서 편집 폼은 크게)
  options?: { value: string | number; label: string }[];
  // type:'images'·'files' 전용 — 고르는 즉시 영속(form save 와 무관). 선택은 데스크탑(window.electron)만.
  //   images = 이미지 썸네일 격자, files = 임의 파일 다중 선택(고른 파일마다 add_action 1회).
  add_action?: string;    // [..]{op:add_image|add, ..., path:"$path"} — $path=소스 파일경로
  remove_action?: string; // [..]{op:remove_image, ..., path:"$path"} — $path=제거할 첨부
  // type:'textarea' 전용 — ai_dock 어피던스(요청→제안→반영/첨부/닫기). 옛 빈노트의 편집 UX 를 어휘로(engine 뷰에도 붙는다).
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
export type Dispatch = (template: string, fieldValues?: Record<string, unknown>, rowContext?: Json, opts?: { back?: boolean }) => Promise<boolean>;

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
  edition?: number;  // 템플릿 판본(2026-10-05 ①): 2 — 치환 없이 원문+inputs 로 실행(전 블록 필수). 구형 치환 경로는 은퇴.
  note?: string;
  auto_run?: boolean;
  inputs?: AppInput[];
  buttons?: AppButton[];
  action?: string;
  view?: AppViewPrim[];
  filter?: AppFilter;  // 단일선택 필터 칩(기간·레벨 양용) — 클릭 즉시 그 값으로 재조회
  compose?: AppCompose;  // 하단 작성바 (커뮤니티 글 작성 등) — 전송 후 현재 뷰 자동 새로고침
  run_label?: string;  // 입력줄 실행 버튼 라벨(기본 '조회') — 쓰기 모드는 '올리기'/'저장' 등
}

export interface AppInstrument extends AppMode {
  web_app?: string;
  id: string;
  icon: string;
  name: string;
  modes?: AppMode[];
  system?: boolean;  // 런처 직속 시스템 표면(메신저·커뮤니티) — 데스크탑 앱 그리드에서 제외
  top_buttons?: AppButton[];  // 탭과 무관하게 계기 최상단에 항상 보이는 버튼(예: 소개발행). 탭 전환과 독립.
  principal?: { kind: string; level?: number | null; id?: string };  // 보고 있는 주체(서버가 요청마다 붙임) — 템플릿 $principal(읽기 전용)
}

export type Json = Record<string, unknown>;

// 뷰-이벤트 콜백 — 프리미티브(map·engine)가 사용자 조작을 액션 템플릿+페이로드로 흘린다. ModePane 가 재조회.
// 페이로드는 타입을 보존한다(좌표는 Number, selection 의 sel 은 Record) — 판본 2 는 inputs 로 그대로 간다.
export type ViewEvent = (template: string, payload: Record<string, unknown>) => void;

// AI 응답에서 제안 본문을 꺼낸다 — 스칼라, 또는 관용구가 돌려준 Record 의 본문 필드. 실패는 ⚠️ 로 시작(반영 버튼 숨김).
export function suggestionText(d: unknown): string {
  if (typeof d === 'string') return d || '(빈 응답)';
  const o = d && typeof d === 'object' ? (d as Json) : null;
  if (o?.error || o?.success === false) return '⚠️ ' + String(o.error || o.message || '실패');
  const v = o?.result ?? o?.text ?? o?.answer ?? o?.after ?? o?.fixed ?? o?.message;
  return typeof v === 'string' && v ? v : v != null && typeof v !== 'object' ? String(v) : '(빈 응답)';
}

/** 실행 — 문자열(구형 치환 결과) 또는 판본 2 봉투(actionRequest). 봉투는 code·edition·inputs·declared_inputs 를 그대로 싣는다. */
export async function runIBL(req: ActionReq): Promise<Json> {
  const body = typeof req === 'string' ? { code: req } : { ...req };
  const post = async (extra: Record<string, unknown>) => {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...iblSurface, ...body, ...extra, project_id: '앱모드', project_path: '.' }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  };
  let raw = await post({});
  // 사람 승인(② 권한 연결): human_confirm 액션은 approval_required{challenge} 로 거절한다 — 여기(사람이 보는 표면)서 묻고
  // /ibl/approve 로 토큰을 받아 **같은 요청**을 approval 과 함께 한 번 재전송한다(토큰은 요청 지문에 묶여 1회).
  const ask = approvalChallenge(raw);
  if (ask && typeof window !== 'undefined' && window.confirm(`사람 확인이 필요한 동작입니다:\n${ask.summary || ask.action}\n\n실행할까요?`)) {
    const ok = await fetch(IBL_ENDPOINT.replace(/\/execute$/, '/approve'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...iblSurface, challenge: ask.challenge }),
    });
    if (ok.ok) {
      const t = await ok.json() as { token?: string };
      if (t.token) raw = await post({ approval: t.token });
    }
  }
  // 합성(>>) 액션의 final_result 펼치기는 공용 코어(원격 ibl() 과 같은 규칙)
  return unwrapFinalResult(raw) as Json;
}

// ===== 템플릿 (공용 코어 위의 데스크탑 얇은 층) =====

/** "{path|filter|...}" → 문자열 치환. 데스크탑은 React 가 이스케이프하므로 esc 를 안 넘긴다. */
export function tpl(t: unknown, data: unknown): string {
  return tplWith(t, data);
}

// 한국색: 상승=빨강, 하락=파랑 (방향 판정은 공용 코어 trendUp)
export function trendClass(p: AppViewPrim, data: unknown): string | null {
  const up = trendUp(p, data);
  return up == null ? null : up ? 'text-red-500' : 'text-blue-600';
}

/** view 통화 슬라이스 — 공용 코어 viewList 의 데스크탑 이름(타입만 좁힌다) */
export function asList(data: unknown, from: unknown): Json[] {
  return viewList(data, from) as Json[];
}

export type ChannelOpt = { key: string; channel_type: string; to: string; label: string };

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

// ===== URL 헬퍼 (백엔드 미디어 서빙) =====

export const IMAGE_BASE = IBL_ENDPOINT.replace(/\/ibl\/execute$/, '');  // 'http://127.0.0.1:8765'
export const imageUrl = (p: string) => `${IMAGE_BASE}/image?path=${encodeURIComponent(p)}`;
// view 통화의 image 필드: 절대 URL(http…·data:)이면 그대로, 백엔드 라우트(/photo/thumbnail?path=…)면
// IMAGE_BASE 부착, 파일 절대경로(/Users/…/x.jpg)면 /image 로 서빙.
// 데스크탑(file://·dev 5173)은 origin이 백엔드와 달라 상대경로가 깨지므로 필수. book/invest 외부 http URL은 무영향.
// ★'/' 로 시작한다고 라우트가 아니다 — 판정은 공용 코어 isBackendRoute 가 정본(원격 표면과 같은 규칙).
export const mediaSrc = (u: string) => !u ? u : (u.startsWith('/') ? (isBackendRoute(u) ? `${IMAGE_BASE}${u}` : imageUrl(u)) : u);
// media_player 소스: 해소 규칙 전부 공용 코어(resolveMediaUrl) — 표면 차이는 base 뿐이다.
export const audioUrl = (u: string) => resolveMediaUrl(u, IMAGE_BASE);

// RECURRENCE_OPTS(반복 주기 어휘)·dateInputType 은 공용 코어에서 재수출 — 위 export 블록 참조.

/* 계기 메뉴(모드 탭)를 캔버스가 맡는 통로 — 편집 캔버스(engine 뷰의 문서 엔진)가 서 있는 동안 모드 탭 줄은
 * 화면에서 빠지고 캔버스의 ⚙ 안에 접힌다(글 쓰는 자리가 화면의 대부분이어야 한다). 캔버스가 claim 하면
 * GenericInstrument 가 탭 줄을 걷고, 캔버스는 modes/go 로 같은 탭을 ⚙ 패널에 그린다. 선언에는 키가 없다. */
export interface InstrumentMenu { modes: string[]; idx: number; go: (i: number) => void; claim: () => () => void; claimed: boolean }
export const InstrumentMenuContext = createContext<InstrumentMenu | null>(null);
