/**
 * 지도 계기가 부르는 어휘 — 전부 iblExecuteApp(project_id:'앱모드' 내장) 경유. 표현 코드는 여기 없다.
 *
 *   장소 검색/상세   [sense:place]{op: search|detail}
 *   좌표→주소        [sense:reverse_geocode]
 *   내 위치          [sense:here]
 *   길찾기 / CCTV    [sense:navigate_route] / [sense:cctv]{op: nearby}
 *   저장 장소 원장   [self:read]{path} / [self:write]{path, format:"json"}  (outputs/map/places.json)
 *
 * IBL 문자열 리터럴 안에 큰따옴표·역슬래시가 들어가면 파서가 어긋날 수 있어(escape 절단 이력)
 * 검색어·이름 같은 짧은 값은 그 두 글자를 제거하고, 원장 본문은 JSON.stringify 이중 인용으로 넘긴다
 * (이중 인용 \" 경로는 라이브 프로브로 왕복 확인됨 — 2026-09-03).
 */
import { iblExecuteApp } from '../../lib/instrument';
import type { Cctv, LatLng, Place, RouteResult, SavedPlace } from './types';
import { DEFAULT_TAG, SAVED_PATH } from './types';

const s = (v: string) => `"${v.replace(/["\\]/g, '').trim()}"`;
const n = (v: number, d = 6) => v.toFixed(d);

type Obj = Record<string, unknown>;
const asObj = (r: unknown): Obj => (r && typeof r === 'object' ? (r as Obj) : {});
const errOf = (r: unknown): string | null => {
  const o = asObj(r);
  if (typeof o.error === 'string') return o.error;
  if (typeof o.result === 'string' && /^Error/i.test(o.result)) return o.result;
  return null;
};

/* ── 장소 ─────────────────────────────────────────── */
export interface SearchOpts {
  query?: string;
  category?: string;
  center?: LatLng | null;
  radius?: number;          // m
  sort?: 'accuracy' | 'distance';
  limit?: number;
}
export interface SearchOut { items: Place[]; total: number; error?: string }

export async function searchPlaces(o: SearchOpts): Promise<SearchOut> {
  const parts: string[] = [];
  if (o.query) parts.push(`query: ${s(o.query)}`);
  if (o.category) parts.push(`category: ${s(o.category)}`);
  if (o.center) parts.push(`lat: ${n(o.center.lat)}, lng: ${n(o.center.lng)}`);
  if (o.radius != null) parts.push(`radius: ${Math.round(o.radius)}`);
  if (o.sort) parts.push(`sort: "${o.sort}"`);
  parts.push(`limit: ${o.limit ?? 30}`);
  const r = await iblExecuteApp(`[sense:place]{${parts.join(', ')}}`);
  const e = errOf(r);
  if (e) return { items: [], total: 0, error: e };
  const ob = asObj(r);
  return { items: (ob.items as Place[]) || [], total: Number(ob.total || 0) };
}

export async function placeDetail(p: Place): Promise<Place | null> {
  const r = await iblExecuteApp(`[sense:place]{op: "detail", name: ${s(p.name)}, id: ${s(p.id)}, lat: ${n(p.lat)}, lng: ${n(p.lng)}}`);
  const it = (asObj(r).items as Place[] | undefined)?.[0];
  return it || null;
}

/* ── 좌표·위치 ─────────────────────────────────────── */
export async function reverseGeocode(ll: LatLng): Promise<string> {
  try {
    const r = await iblExecuteApp(`[sense:reverse_geocode]{lat: ${n(ll.lat)}, lng: ${n(ll.lng)}}`);
    return String(asObj(r).address || '');
  } catch { return ''; }
}

export interface Here extends LatLng { address?: string; accuracy_m?: number; source?: string }
export async function whereAmI(): Promise<Here | null> {
  const r = asObj(await iblExecuteApp('[sense:here]{}'));
  if (typeof r.lat !== 'number' || typeof r.lng !== 'number') return null;
  return { lat: r.lat, lng: r.lng, address: r.address as string, accuracy_m: r.accuracy_m as number, source: r.source as string };
}

/* ── 저장 장소 원장 ────────────────────────────────── */
// 없으면 빈 원장(첫 저장이 파일을 만든다). 연결 실패는 throw — 호출부가 재시도(useRetryingLoad).
export async function loadSaved(): Promise<SavedPlace[]> {
  const r = await iblExecuteApp(`[self:read]{path: "${SAVED_PATH}"}`);
  const items = asObj(r).items;
  if (!Array.isArray(items)) return [];
  return (items as SavedPlace[]).filter((x) => x && typeof x.lat === 'number' && typeof x.lng === 'number')
    .map((x) => ({ ...x, tag: x.tag || DEFAULT_TAG, memo: x.memo || '' }));
}

// 원장 전체를 다시 쓴다(단일 사용자 UI — 항목 수십~수백). 문자열 필드의 큰따옴표·역슬래시는 정리해 파서 안전.
const clean = (v: unknown) => (typeof v === 'string' ? v.replace(/"/g, '”').replace(/\\/g, '') : v);
export async function writeSaved(list: SavedPlace[]): Promise<boolean> {
  const rows = list.map((p) => Object.fromEntries(Object.entries(p).map(([k, v]) => [k, clean(v)])));
  const content = JSON.stringify({ items: rows, count: rows.length });
  const r = await iblExecuteApp(`[self:write]{path: "${SAVED_PATH}", format: "json", content: ${JSON.stringify(content)}}`);
  return !errOf(r) && asObj(r).success !== false;
}

/* ── 길찾기 · CCTV ────────────────────────────────── */
// 연결 실패는 throw — 호출부가 에러 표시·재시도를 다룬다.
export async function runRoute(origin: string, destination: string): Promise<RouteResult> {
  const r = await iblExecuteApp(`[sense:navigate_route]{origin: ${s(origin)}, destination: ${s(destination)}}`);
  return asObj(r) as unknown as RouteResult;
}

export async function cctvNearby(ll: LatLng, radius_km: number, count: number): Promise<Cctv[]> {
  try {
    const r = await iblExecuteApp(`[sense:cctv]{op: "nearby", lat: ${n(ll.lat)}, lng: ${n(ll.lng)}, radius_km: ${radius_km}, count: ${count}}`);
    return ((asObj(r).items as Cctv[]) || []).filter((c) => c.lat && c.lng);
  } catch { return []; }
}
