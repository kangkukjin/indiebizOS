/**
 * 지도 계기(MapInstrument) 공용 타입·상수.
 * 능력은 어휘([sense:place]·[sense:navigate_route]·[sense:cctv]·[sense:reverse_geocode]·[sense:here]·
 * [self:read]/[self:write] 원장)가 맡고, 이 폴더는 표현만 맡는다(custom_app_instrument.md 철칙 0).
 */
export interface LatLng { lat: number; lng: number }

/** [sense:place] 검색 항목 — 카카오 로컬 기본 필드 + detail 부착 필드(선택). */
export interface Place {
  id: string;
  name: string;
  category?: string;      // '음식점 > 양식 > 이탈리안'
  cat?: string;           // 둘째 단 요약
  group?: string;         // 카카오 대분류(음식점/카페/…)
  group_code?: string;
  address?: string;
  jibun_address?: string;
  phone?: string;
  url?: string;           // place.map.kakao.com/<id>
  distance?: number | null;   // m (좌표 기준 검색일 때만)
  lat: number;
  lng: number;
  // detail 부착
  description?: string;
  naver_url?: string;
  blog_count?: number;
  reason?: string;
  sources?: string[];
}

/** 저장한 장소 — 원장 outputs/map/places.json 의 한 행. */
export interface SavedPlace extends Place {
  tag: string;        // 폴더(그룹) — 기본 '기본'
  memo: string;
  saved_at: string;   // ISO
}

export interface Point { text: string; coord: LatLng | null }

export interface KeyGuide { name?: string; guidance?: string; distance?: number }
export interface RouteSummary { distance_km?: number; duration_min?: number; toll?: number; fare?: { toll?: number } }
export interface RouteMapData {
  origin: { lat: number; lng: number; name: string };
  destination: { lat: number; lng: number; name: string };
  path: [number, number][];
  summary: { distance_km: number; duration_min: number; toll: number; fare?: { toll?: number } };
}
export interface RouteInfo { summary?: RouteSummary; key_guides?: KeyGuide[] }
export interface RouteResult { summary?: RouteSummary; key_guides?: KeyGuide[]; routes?: RouteInfo[]; map_data?: RouteMapData; message?: string; error?: string }

export interface Cctv { name?: string; url?: string; lat?: number; lng?: number; road_type?: string; format?: string; distance_km?: number; source?: string; playable?: boolean }

/** 카카오맵 앱의 카테고리 칩 — 라벨은 [sense:place]{category} 가 받는 한글 라벨 그대로. */
export const CATEGORY_CHIPS: { label: string; icon: string }[] = [
  { label: '음식점', icon: '🍴' }, { label: '카페', icon: '☕' }, { label: '편의점', icon: '🏪' },
  { label: '주차장', icon: '🅿️' }, { label: '주유소', icon: '⛽' }, { label: '병원', icon: '🏥' },
  { label: '약국', icon: '💊' }, { label: '은행', icon: '🏦' }, { label: '마트', icon: '🛒' },
  { label: '숙박', icon: '🛏️' }, { label: '관광명소', icon: '🏛️' }, { label: '지하철', icon: '🚇' },
];

export const DEFAULT_TAG = '기본';
/** 저장 장소 원장 — 앱모드 컨텍스트 상대경로(projects/앱모드/outputs/map/places.json 로 해소). */
export const SAVED_PATH = 'outputs/map/places.json';
export const DEFAULT_CENTER: LatLng = { lat: 37.4979, lng: 127.0276 }; // 강남역

export const fmtDistance = (m?: number | null) =>
  m == null ? '' : m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`;
export const fmtCoord = (ll: LatLng) => `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`;
