/**
 * DirectionsInstrument — 길찾기 + CCTV "계기(instrument)" (앱 모드)
 *
 * 지도 중심 인터랙티브 앱(LLM 없음, 0 토큰):
 *   1) 길찾기 — 지도를 클릭해 출발지·도착지를 찍거나(또는 텍스트/우리집 입력) → [sense:navigate_route]
 *      → 경로 폴리라인 + 거리·시간·톨비 + 주요 안내.
 *   2) CCTV — "CCTV 표시"를 켜면 경로 주변(경로 없으면 현재 화면 중심)의 도로 CCTV를
 *      [sense:cctv]{op:"nearby"}로 찾아 지도에 📹로 표시. 마커를 누르면 실시간 영상(StreamPlayer, HLS).
 *
 * CCTV는 카카오(전국, 좌표 보강 완료)·TOPIS·UTIC·ITS를 좌표 기준으로 통합 조회한다(radius_km, km).
 * "우리집"은 localStorage에 굳혀, 버튼 하나로 출발지에 채운다.
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml (navigate_route, cctv op),
 *   location-services/handler.py (kakao_navigation), cctv/handler.py (cctv_query)
 */
import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { StreamPlayer } from './StreamPlayer';
import type { StreamData } from './chat/chatUtils';
import { useRetryingLoad } from '../lib/use-retrying-load';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'directions.instrument.last';
const HOME_KEY = 'directions.instrument.home';
const DEFAULT_CENTER = { lat: 37.4979, lng: 127.0276 }; // 강남역

interface LatLng { lat: number; lng: number }
interface Point { text: string; coord: LatLng | null }
interface KeyGuide { name?: string; guidance?: string; distance?: number }
interface RouteSummary { distance_km?: number; duration_min?: number; toll?: number; fare?: { toll?: number } }
interface RouteMapData {
  origin: { lat: number; lng: number; name: string };
  destination: { lat: number; lng: number; name: string };
  path: [number, number][];
  summary: { distance_km: number; duration_min: number; toll: number; fare?: { toll?: number } };
}
interface RouteInfo { summary?: RouteSummary; key_guides?: KeyGuide[] }
interface RouteResult { summary?: RouteSummary; key_guides?: KeyGuide[]; routes?: RouteInfo[]; map_data?: RouteMapData; message?: string; error?: string }

interface Cctv { name?: string; url?: string; lat?: number; lng?: number; road_type?: string; format?: string; distance_km?: number; source?: string; playable?: boolean }
interface CctvResult { items?: Cctv[]; count?: number; error?: string }

/* ── IBL 직접 실행 ──────────────────────────────── */
// 연결 실패는 throw — 호출부(runSearch)가 에러 표시·재시도를 다룬다.
async function runRoute(origin: string, destination: string): Promise<RouteResult> {
  const o = origin.replace(/"/g, ''); const d = destination.replace(/"/g, '');
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: `[sense:navigate_route]{origin: "${o}", destination: "${d}"}`, project_id: PROJECT_ID }),
  });
  return await res.json();
}
async function runCctvNearby(lat: number, lng: number, radius_km: number, count: number): Promise<CctvResult> {
  try {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: `[sense:cctv]{op: "nearby", lat: ${lat.toFixed(6)}, lng: ${lng.toFixed(6)}, radius_km: ${radius_km}, count: ${count}}`, project_id: PROJECT_ID }),
    });
    return await res.json();
  } catch { return { error: 'CCTV 조회 실패' }; }
}

/* ── 마커 아이콘(이미지 의존 없는 divIcon) ──────────── */
const dotIcon = (color: string) => L.divIcon({
  className: '',
  html: `<div style="width:16px;height:16px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
  iconSize: [16, 16], iconAnchor: [8, 8],
});
const CCTV_ICON = L.divIcon({
  className: '',
  html: `<div style="font-size:20px;line-height:20px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))">📹</div>`,
  iconSize: [20, 20], iconAnchor: [10, 10],
});

const fmtCoord = (ll: LatLng) => `${ll.lat.toFixed(5)}, ${ll.lng.toFixed(5)}`;

interface Cache { origin: Point; destination: Point }
function loadCache(): Cache {
  try { const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); if (c?.origin && c?.destination) return c; } catch { /* ignore */ }
  return { origin: { text: '', coord: null }, destination: { text: '', coord: null } };
}

export function DirectionsInstrument() {
  const init = useMemo(loadCache, []);
  const [origin, setOrigin] = useState<Point>(init.origin);
  const [destination, setDestination] = useState<Point>(init.destination);
  const [pick, setPick] = useState<'origin' | 'destination'>('origin'); // 다음 지도 클릭이 찍을 점
  const [result, setResult] = useState<RouteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [home, setHome] = useState<string>(() => localStorage.getItem(HOME_KEY) || '');
  const [editHome, setEditHome] = useState(false);
  const [homeDraft, setHomeDraft] = useState(home);

  const [cctvOn, setCctvOn] = useState(false);
  const [cctvs, setCctvs] = useState<Cctv[]>([]);
  const [cctvLoading, setCctvLoading] = useState(false);
  const [selected, setSelected] = useState<StreamData | null>(null);

  // 지도 refs
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const routeLayerRef = useRef<L.LayerGroup | null>(null);
  const cctvLayerRef = useRef<L.LayerGroup | null>(null);
  const originMarkerRef = useRef<L.Marker | null>(null);
  const destMarkerRef = useRef<L.Marker | null>(null);
  const pickRef = useRef(pick); pickRef.current = pick;
  const cctvOnRef = useRef(cctvOn); cctvOnRef.current = cctvOn;

  /* ── 경로 주변 CCTV: 경로를 몇 점 샘플링해 [sense:cctv]{op:nearby} 병렬 조회 ── */
  const loadCctvAlongRoute = useCallback(async (path: [number, number][]) => {
    if (!path?.length) return;
    setCctvLoading(true);
    const N = Math.min(8, path.length);
    const step = Math.max(1, Math.floor(path.length / N));
    const samples: [number, number][] = [];
    for (let i = 0; i < path.length; i += step) samples.push(path[i]);
    const last = path[path.length - 1];
    if (samples[samples.length - 1]?.[0] !== last[0]) samples.push(last);
    const results = await Promise.all(samples.map(([lat, lng]) => runCctvNearby(lat, lng, 2.8, 2)));
    const seen = new Set<string>(); const all: Cctv[] = [];
    for (const r of results) for (const c of (r.items || [])) {
      const k = c.url || `${c.lat},${c.lng}`;
      if (c.lat && c.lng && !seen.has(k)) { seen.add(k); all.push(c); }
    }
    setCctvs(all);
    setCctvLoading(false);
  }, []);

  /* ── 현재 화면 중심 주변 CCTV(경로 없을 때) ── */
  const loadCctvNearCenter = useCallback(async () => {
    const map = mapRef.current; if (!map) return;
    const c = map.getCenter();
    setCctvLoading(true);
    const r = await runCctvNearby(c.lat, c.lng, 5.5, 12);
    setCctvs((r.items || []).filter((x) => x.lat && x.lng));
    setCctvLoading(false);
  }, []);

  /* ── 길찾기 실행 ── */
  const runSearch = useCallback(async (o: Point, d: Point) => {
    const os = o.coord ? `${o.coord.lng},${o.coord.lat}` : o.text.trim();
    const ds = d.coord ? `${d.coord.lng},${d.coord.lat}` : d.text.trim();
    if (!os || !ds) return;
    setLoading(true); setError(null);
    let r: RouteResult;
    try {
      r = await runRoute(os, ds);
    } catch (e) {
      setLoading(false);
      setError('서버에 연결할 수 없습니다.');
      throw e;                        // 실패를 굳히지 않는다 — 훅이 백오프 재시도
    }
    setLoading(false);
    if (r.error) { setError(r.error); setResult(null); return; }
    setResult(r);
    if (r.map_data) {
      // 텍스트로 입력했으면 해소된 좌표/이름으로 핀을 옮긴다
      const no: Point = { text: r.map_data.origin.name || o.text, coord: { lat: r.map_data.origin.lat, lng: r.map_data.origin.lng } };
      const nd: Point = { text: r.map_data.destination.name || d.text, coord: { lat: r.map_data.destination.lat, lng: r.map_data.destination.lng } };
      setOrigin(no); setDestination(nd);
      localStorage.setItem(CACHE_KEY, JSON.stringify({ origin: no, destination: nd }));
      if (cctvOnRef.current) loadCctvAlongRoute(r.map_data.path);
    }
  }, [loadCctvAlongRoute]);

  // 수동 실행(버튼·Enter)용 — 연결 실패 에러는 runSearch 안에서 이미 화면에 표시된다.
  const searchNow = (o: Point, d: Point) => { runSearch(o, d).catch(() => {}); };

  // 캐시 복원분 자동 길찾기 — 마운트 1회. 백엔드가 아직 안 떠 있으면 훅이 백오프 재시도.
  const hasCache = !!((init.origin.text || init.origin.coord) && (init.destination.text || init.destination.coord));
  useRetryingLoad(
    useCallback(() => runSearch(init.origin, init.destination), [init, runSearch]),
    { enabled: hasCache });

  /* ── 지도 1회 초기화 ── */
  useEffect(() => {
    if (!mapDiv.current || mapRef.current) return;
    const c0 = init.origin.coord || init.destination.coord || DEFAULT_CENTER;
    const map = L.map(mapDiv.current, { scrollWheelZoom: true }).setView([c0.lat, c0.lng], 12);
    mapRef.current = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);
    routeLayerRef.current = L.layerGroup().addTo(map);
    cctvLayerRef.current = L.layerGroup().addTo(map);

    map.on('click', (e: L.LeafletMouseEvent) => {
      const ll = { lat: e.latlng.lat, lng: e.latlng.lng };
      if (pickRef.current === 'origin') { setOrigin({ text: fmtCoord(ll), coord: ll }); setPick('destination'); }
      else { setDestination({ text: fmtCoord(ll), coord: ll }); }
    });

    setTimeout(() => map.invalidateSize(), 120);
    return () => { map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── 출발/도착 핀(클릭·해소 좌표 반영) ── */
  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    const upsert = (ref: React.MutableRefObject<L.Marker | null>, coord: LatLng | null, color: string, label: string) => {
      if (coord) {
        if (!ref.current) ref.current = L.marker([coord.lat, coord.lng], { icon: dotIcon(color) }).bindTooltip(label, { direction: 'top', offset: [0, -8] }).addTo(map);
        else ref.current.setLatLng([coord.lat, coord.lng]);
      } else if (ref.current) { map.removeLayer(ref.current); ref.current = null; }
    };
    upsert(originMarkerRef, origin.coord, '#22C55E', '출발');
    upsert(destMarkerRef, destination.coord, '#EF4444', '도착');
  }, [origin.coord, destination.coord]);

  /* ── 경로 폴리라인 ── */
  useEffect(() => {
    const layer = routeLayerRef.current; const map = mapRef.current; if (!layer || !map) return;
    layer.clearLayers();
    const path = result?.map_data?.path;
    if (path?.length) {
      const pl = L.polyline(path as L.LatLngExpression[], { color: '#3B82F6', weight: 5, opacity: 0.85 }).addTo(layer);
      map.fitBounds(pl.getBounds(), { padding: [40, 40] });
    }
  }, [result]);

  /* ── CCTV 마커 ── */
  useEffect(() => {
    const layer = cctvLayerRef.current; if (!layer) return;
    layer.clearLayers();
    if (!cctvOn) return;
    cctvs.forEach((c) => {
      if (!c.lat || !c.lng) return;
      L.marker([c.lat, c.lng], { icon: CCTV_ICON })
        .bindTooltip(c.name || 'CCTV', { direction: 'top', offset: [0, -8] })
        .on('click', () => setSelected({ url: c.url || '', name: c.name, source: c.source, lat: c.lat, lng: c.lng, playable: c.playable }))
        .addTo(layer);
    });
  }, [cctvs, cctvOn]);

  /* ── 핸들러 ── */
  const useHome = () => {
    if (home) { setOrigin({ text: home, coord: null }); setPick('destination'); }
    else { setEditHome(true); setHomeDraft(''); }
  };
  const saveHome = () => {
    const v = homeDraft.trim();
    setHome(v);
    if (v) localStorage.setItem(HOME_KEY, v); else localStorage.removeItem(HOME_KEY);
    if (v && !origin.text.trim()) setOrigin({ text: v, coord: null });
    setEditHome(false);
  };
  const swap = () => { setOrigin(destination); setDestination(origin); };
  const reset = () => {
    setOrigin({ text: '', coord: null }); setDestination({ text: '', coord: null });
    setResult(null); setError(null); setPick('origin');
    routeLayerRef.current?.clearLayers();
  };
  const toggleCctv = () => {
    const next = !cctvOn; setCctvOn(next);
    if (next) { if (result?.map_data?.path) loadCctvAlongRoute(result.map_data.path); else loadCctvNearCenter(); }
    else setCctvs([]);
  };

  // 백엔드는 summary·key_guides 를 최상위로 반환(과거 routes[0] 중첩에서 평탄화됨). map_data.summary 폴백.
  const summary = result?.summary || result?.routes?.[0]?.summary || result?.map_data?.summary;
  const guides = (result?.key_guides || result?.routes?.[0]?.key_guides || []).filter((g) => g.name || g.guidance);

  return (
    <div className="h-full w-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* ── 컨트롤 ── */}
      <div className="shrink-0 px-4 pt-3 pb-2 border-b border-stone-100">
        <div className="max-w-3xl mx-auto space-y-2">
          <div className="flex items-center gap-2">
            <button onClick={() => setPick('origin')} title="다음 지도 클릭 → 출발지"
              className={`w-9 shrink-0 text-base rounded-lg py-1.5 border ${pick === 'origin' ? 'bg-green-50 border-green-300' : 'bg-white border-stone-200'}`}>📍</button>
            <input value={origin.text} onChange={(e) => setOrigin({ text: e.target.value, coord: null })}
              onFocus={() => setPick('origin')}
              onKeyDown={(e) => e.key === 'Enter' && searchNow(origin, destination)}
              placeholder="출발지 — 지도 클릭 / 우리집 / 강남역"
              className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
            <button onClick={useHome} title={home ? `우리집: ${home}` : '우리집 주소 등록'}
              className={`shrink-0 px-2.5 py-2 rounded-xl text-sm border ${home ? 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>🏠</button>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setPick('destination')} title="다음 지도 클릭 → 도착지"
              className={`w-9 shrink-0 text-base rounded-lg py-1.5 border ${pick === 'destination' ? 'bg-rose-50 border-rose-300' : 'bg-white border-stone-200'}`}>🏁</button>
            <input value={destination.text} onChange={(e) => setDestination({ text: e.target.value, coord: null })}
              onFocus={() => setPick('destination')}
              onKeyDown={(e) => e.key === 'Enter' && searchNow(origin, destination)}
              placeholder="목적지 — 지도 클릭 / 수원역 / 시청"
              className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
            <button onClick={swap} title="출발↔도착 바꾸기"
              className="shrink-0 px-2.5 py-2 rounded-xl text-sm border bg-white border-stone-200 text-stone-600 hover:bg-stone-50">⇅</button>
            <button onClick={() => searchNow(origin, destination)} disabled={loading || (!origin.text.trim() && !origin.coord) || (!destination.text.trim() && !destination.coord)}
              className="shrink-0 px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40">
              {loading ? '…' : '길찾기'}
            </button>
          </div>
          {editHome && (
            <div className="flex gap-2 items-center pt-1">
              <input value={homeDraft} onChange={(e) => setHomeDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && saveHome()}
                placeholder="우리집 주소 (예: 서울 강남구 테헤란로 152)"
                className="flex-1 px-3 py-2 rounded-xl border border-amber-200 bg-amber-50 text-sm outline-none focus:border-amber-400" />
              <button onClick={saveHome} className="px-3 py-2 rounded-xl bg-amber-600 text-white text-sm hover:bg-amber-500">저장</button>
            </div>
          )}
        </div>
      </div>

      {/* ── 지도 ──
          isolate: Leaflet 내부 컨트롤(z-index 1000)·팬이 이 지도 영역을 벗어나
          CCTV 영상 모달(fixed z-[1000]) 위로 새어 나오지 않도록 독립 스태킹 컨텍스트로 가둔다. */}
      <div className="relative isolate flex-1 min-h-[240px]">
        <div ref={mapDiv} className="absolute inset-0 bg-stone-100" />
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-[500] px-3 py-1 rounded-full bg-white/90 border border-stone-200 text-[11px] text-stone-500 shadow-sm pointer-events-none">
          지도를 클릭해 <b className={pick === 'origin' ? 'text-green-600' : 'text-rose-600'}>{pick === 'origin' ? '출발지' : '도착지'}</b>를 찍으세요
          {cctvOn && ' · 📹를 누르면 실시간 영상'}
        </div>
        {/* 지도 위 플로팅 컨트롤 — CCTV 토글 / 초기화 / 집 주소 설정 */}
        <div className="absolute top-2 right-2 z-[500] flex flex-col items-end gap-1.5">
          <button onClick={toggleCctv} title="도로 CCTV 표시"
            className={`px-2.5 py-1.5 rounded-lg text-xs border shadow-sm ${cctvOn ? 'bg-red-500 text-white border-red-500' : 'bg-white/90 border-stone-200 text-stone-600 hover:bg-white'}`}>
            📹{cctvLoading ? '…' : cctvOn && cctvs.length ? ` ${cctvs.length}` : ''}
          </button>
          <button onClick={reset} title="초기화"
            className="px-2.5 py-1.5 rounded-lg text-xs border shadow-sm bg-white/90 border-stone-200 text-stone-500 hover:bg-white">↺</button>
          <button onClick={() => { setEditHome((v) => !v); setHomeDraft(home); }} title="집 주소 설정"
            className="px-2.5 py-1.5 rounded-lg text-xs border shadow-sm bg-white/90 border-stone-200 text-stone-500 hover:bg-white">⚙</button>
        </div>
        {error && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-[500] px-4 py-2 rounded-lg bg-rose-500 text-white text-sm shadow">{error}</div>
        )}
      </div>

      {/* ── 하단 패널: 요약 + 안내 + CCTV 목록 ── */}
      {(summary || guides.length > 0 || (cctvOn && cctvs.length > 0)) && (
        <div className="shrink-0 max-h-[36%] overflow-auto px-4 py-2 border-t border-stone-100">
          <div className="max-w-3xl mx-auto">
            {summary && (
              <div className="flex flex-wrap gap-2">
                {summary.distance_km != null && <span className="px-3 py-1.5 rounded-full bg-white border border-stone-200 text-sm">🚗 {summary.distance_km}km</span>}
                {summary.duration_min != null && <span className="px-3 py-1.5 rounded-full bg-white border border-stone-200 text-sm">⏱ {summary.duration_min}분</span>}
                {(() => { const toll = summary.toll ?? summary.fare?.toll; return toll ? <span className="px-3 py-1.5 rounded-full bg-white border border-stone-200 text-sm">💳 톨비 {toll.toLocaleString()}원</span> : null; })()}
              </div>
            )}

            {cctvOn && cctvs.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-stone-400 mb-1.5">주변 CCTV {cctvs.length}대 · 누르면 영상</div>
                <div className="flex gap-1.5 flex-wrap">
                  {cctvs.map((c, i) => (
                    <button key={i} onClick={() => setSelected({ url: c.url || '', name: c.name, source: c.source, lat: c.lat, lng: c.lng, playable: c.playable })}
                      className="px-2.5 py-1 rounded-lg text-xs border bg-white border-stone-200 text-stone-600 hover:border-red-300 hover:text-red-600">
                      📹 {c.name}{c.distance_km != null ? <span className="text-stone-400 ml-1">{c.distance_km}km</span> : null}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {guides.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-stone-400 mb-1.5">주요 안내</div>
                <div className="space-y-1">
                  {guides.map((g, i) => (
                    <div key={i} className="bg-white rounded-xl border border-stone-200 px-4 py-2 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <span className="text-sm">{g.guidance || '경유'}</span>
                        {g.name && <span className="ml-2 text-xs text-stone-500 truncate">{g.name}</span>}
                      </div>
                      {g.distance != null && <span className="shrink-0 text-xs text-stone-400">{(g.distance / 1000).toFixed(1)}km</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 선택한 CCTV 영상 모달 ── */}
      {selected && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[1000] p-4" onClick={() => setSelected(null)}>
          <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <StreamPlayer data={selected} variant="neutral" />
            <button onClick={() => setSelected(null)}
              className="mt-2 w-full px-4 py-2 rounded-xl bg-white/90 text-stone-700 text-sm hover:bg-white">닫기</button>
          </div>
        </div>
      )}
    </div>
  );
}
