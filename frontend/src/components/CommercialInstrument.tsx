/**
 * CommercialInstrument — 상권(상가) "계기"
 *
 * IBL 액션 [sense:commercial] (소상공인 상가정보) — 반경 모드.
 * 본질적으로 공간 데이터라 지도 기반:
 *   지도를 클릭/핀을 끌어 중심 설정 → 반경 슬라이더 → 조회 → 상가 마커 + 목록
 *
 * 결정화: 마지막 중심/반경/결과를 localStorage에 굳혀 다음 방문에 복원.
 * 스키마 출처: real-estate/tool_commercial_district.py (storeListInRadius)
 */
import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'commercial.instrument.last';
const DEFAULT_CENTER = { lat: 37.4979, lng: 127.0276 }; // 강남역
const MAP_CAP = 1500; // 지도 마커 성능 캡 (점은 상한)
const LIST_CAP = 500; // 목록 렌더 성능 캡 — 업종 필터로 좁히면 그 업종은 전부 보인다

interface Store { name?: string; branch?: string; category?: string; subcategory?: string; address?: string; lat: number; lng: number }
interface Result { success?: boolean; total_count?: number; count?: number; truncated?: boolean; data?: Store[]; error?: string }
interface LatLng { lat: number; lng: number }
interface RestMatch { name?: string; category?: string; address?: string; phone?: string; url?: string; source?: string }
interface StoreDetail { store: Store; match: RestMatch | null; loading: boolean }

function buildCode(c: LatLng, radius: number): string {
  return `[sense:commercial]{lat: ${c.lat.toFixed(6)}, lng: ${c.lng.toFixed(6)}, radius: ${radius}, project_id: "${PROJECT_ID}"}`;
}
async function runCommercial(c: LatLng, radius: number): Promise<Result> {
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: buildCode(c, radius), project_path: '.' }),
  });
  return res.json();
}

// 가게 클릭 enrichment: 이름+좌표로 sense:restaurant 조회 → 카카오 평점 페이지(place.map.kakao.com) 우선.
const _norm = (s?: string) => (s || '').replace(/\s/g, '');
async function runRestaurant(name: string, s: Store): Promise<RestMatch | null> {
  const code = `[sense:restaurant]{query: "${name.replace(/"/g, '')}", x: ${s.lng}, y: ${s.lat}, radius: 300}`;
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, project_id: PROJECT_ID }),
  });
  const d = await res.json();
  const comb: RestMatch[] = (d && d.combined) || [];
  if (!comb.length) return null;
  const t = _norm(name);
  const named = comb.filter((r) => _norm(r.name).includes(t) || t.includes(_norm(r.name)));
  const pool = named.length ? named : comb;
  // 카카오 place 페이지(평점·리뷰 있음) 우선 → 카카오 → 첫 결과
  return pool.find((r) => r.source === 'kakao' && (r.url || '').includes('place.map.kakao.com'))
    || pool.find((r) => r.source === 'kakao')
    || pool[0];
}
const CENTER_ICON = L.divIcon({
  className: '', html: '<div style="font-size:26px;line-height:26px">📍</div>',
  iconSize: [26, 26], iconAnchor: [13, 26],
});

export function CommercialInstrument() {
  const [center, setCenter] = useState<LatLng>(DEFAULT_CENTER);
  const [radius, setRadius] = useState(500);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [catFilter, setCatFilter] = useState<string | null>(null);
  const [detail, setDetail] = useState<StoreDetail | null>(null);

  // 가게 클릭 → 상세(카카오 평점 링크·전화 등)
  const openStore = async (s: Store) => {
    setDetail({ store: s, match: null, loading: true });
    try {
      const m = await runRestaurant(s.name || '', s);
      setDetail((d) => (d && d.store === s) ? { store: s, match: m, loading: false } : d);
    } catch {
      setDetail((d) => (d && d.store === s) ? { store: s, match: null, loading: false } : d);
    }
  };

  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const circleRef = useRef<L.Circle | null>(null);
  const shopsRef = useRef<L.LayerGroup | null>(null);
  const centerRef = useRef(center); centerRef.current = center;
  const radiusRef = useRef(radius); radiusRef.current = radius;

  // 지도 1회 초기화 (+ 캐시 복원)
  useEffect(() => {
    if (!mapDiv.current || mapRef.current) return;
    let init = DEFAULT_CENTER, initR = 500;
    try {
      const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
      if (c?.center) { init = c.center; initR = c.radius; setCenter(c.center); setRadius(c.radius); setResult(c.result); }
    } catch { /* ignore */ }

    const map = L.map(mapDiv.current, { scrollWheelZoom: true }).setView([init.lat, init.lng], 15);
    mapRef.current = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);

    const marker = L.marker([init.lat, init.lng], { draggable: true, icon: CENTER_ICON }).addTo(map);
    marker.on('dragend', () => { const ll = marker.getLatLng(); setCenter({ lat: ll.lat, lng: ll.lng }); });
    markerRef.current = marker;

    circleRef.current = L.circle([init.lat, init.lng], { radius: initR, color: '#b45309', fillColor: '#f59e0b', fillOpacity: 0.1, weight: 1 }).addTo(map);
    shopsRef.current = L.layerGroup().addTo(map);
    map.on('click', (e: L.LeafletMouseEvent) => setCenter({ lat: e.latlng.lat, lng: e.latlng.lng }));

    setTimeout(() => map.invalidateSize(), 100);
    return () => { map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 중심/반경 → 마커·원 갱신
  useEffect(() => {
    markerRef.current?.setLatLng([center.lat, center.lng]);
    circleRef.current?.setLatLng([center.lat, center.lng]);
    circleRef.current?.setRadius(radius);
  }, [center, radius]);

  // 결과 → 상가 마커 렌더 (업종 필터 반영)
  useEffect(() => {
    const layer = shopsRef.current; if (!layer) return;
    layer.clearLayers();
    (result?.data || [])
      .filter((s) => isFinite(s.lat) && isFinite(s.lng) && (!catFilter || s.category === catFilter))
      .slice(0, MAP_CAP)  // 마커는 성능상 상한 (목록은 전부)
      .forEach((s) => {
        L.circleMarker([s.lat, s.lng], { radius: 5, color: '#0284c7', fillColor: '#38bdf8', fillOpacity: 0.9, weight: 1 })
          .bindPopup(`<b>${s.name || ''}</b><br>${[s.category, s.subcategory].filter(Boolean).join(' · ')}<br>${s.address || ''}`)
          .addTo(layer);
      });
  }, [result, catFilter]);

  const fire = async () => {
    setLoading(true); setCatFilter(null);
    try {
      const c = centerRef.current, r = radiusRef.current;
      const res = await runCommercial(c, r);
      setResult(res);
      localStorage.setItem(CACHE_KEY, JSON.stringify({ center: c, radius: r, result: res }));
    } catch (e) { setResult({ error: String(e) }); } finally { setLoading(false); }
  };

  const stores = result?.data || [];
  const cats = Array.from(new Set(stores.map((s) => s.category).filter(Boolean))) as string[];
  const shown = catFilter ? stores.filter((s) => s.category === catFilter) : stores;

  return (
    <div className="h-full w-full bg-[#F5F1EB] flex items-start justify-center p-6 overflow-auto">
      <div className="w-full max-w-3xl bg-white rounded-2xl shadow-lg border border-stone-200 overflow-hidden">
        {/* 제목줄 */}
        <div className="flex items-center justify-between px-5 py-3 bg-stone-50 border-b border-stone-200">
          <div className="flex items-center gap-2 text-stone-800 font-semibold">
            <span className="text-lg">🏪</span><span>상권</span>
            <span className="text-stone-400 font-normal text-sm">· 반경 {radius}m</span>
          </div>
          <div className="text-xs text-stone-400">{loading ? '조회 중…' : result?.total_count != null ? `총 ${result.total_count.toLocaleString()}개` : ''}</div>
        </div>

        {/* 컨트롤 */}
        <div className="px-5 py-3 border-b border-stone-100 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-stone-400 text-xs">지도를 클릭하거나 📍을 끌어 중심을 정하세요</span>
          <label className="flex items-center gap-2 text-stone-500">
            반경
            <input type="range" min={100} max={1000} step={100} value={radius}
              onChange={(e) => setRadius(Number(e.target.value))} className="accent-amber-700" />
            <span className="tabular-nums w-12">{radius}m</span>
          </label>
          <button onClick={fire} disabled={loading}
            className="ml-auto px-4 py-1.5 rounded-lg bg-amber-700 text-white font-medium hover:bg-amber-800 disabled:opacity-50">
            {loading ? '…' : '조회'}
          </button>
        </div>

        {/* 지도 */}
        <div ref={mapDiv} style={{ height: '320px', width: '100%' }} className="bg-stone-100" />

        {/* 요약 + 업종 필터 */}
        {result?.error ? (
          <div className="p-6 text-center text-red-500 text-sm whitespace-pre-wrap">{result.error}</div>
        ) : stores.length > 0 ? (
          <>
            <div className="px-5 py-2 bg-amber-50/40 text-sm text-stone-600 flex items-center gap-2 flex-wrap">
              <span>
                {catFilter
                  ? <><b>{catFilter}</b> {shown.length.toLocaleString()}개</>
                  : <>이 반경에 총 <b>{(result?.total_count ?? stores.length).toLocaleString()}</b>개</>}
                {result?.truncated && <span className="text-amber-700"> · 상위 {stores.length.toLocaleString()}개만 (반경을 좁히세요)</span>}
              </span>
              <button onClick={() => setCatFilter(null)}
                className={`px-2 py-0.5 rounded-full text-xs ${!catFilter ? 'bg-stone-800 text-white' : 'bg-stone-100 text-stone-500'}`}>전체</button>
              {cats.slice(0, 10).map((c) => (
                <button key={c} onClick={() => setCatFilter(c)}
                  className={`px-2 py-0.5 rounded-full text-xs ${catFilter === c ? 'bg-stone-800 text-white' : 'bg-stone-100 text-stone-500 hover:bg-stone-200'}`}>{c}</button>
              ))}
            </div>
            <div className="max-h-[30vh] overflow-auto divide-y divide-stone-50">
              {shown.slice(0, LIST_CAP).map((s, i) => (
                <div key={i} onClick={() => openStore(s)}
                  className="px-5 py-2 text-sm flex items-baseline gap-2 hover:bg-amber-50 cursor-pointer">
                  <span className="text-stone-800 font-medium">{s.name}</span>
                  <span className="text-stone-400 text-xs">{[s.category, s.subcategory].filter(Boolean).join(' · ')}</span>
                  <span className="ml-auto text-stone-400 text-xs truncate max-w-[45%]">{s.address}</span>
                </div>
              ))}
              {shown.length > LIST_CAP && (
                <div className="px-5 py-2 text-xs text-amber-700 text-center">
                  {shown.length.toLocaleString()}개 중 {LIST_CAP}개 표시 — 위 업종 칩으로 좁히면 그 업종은 전부 보입니다
                </div>
              )}
            </div>
          </>
        ) : !loading ? (
          <div className="p-8 text-center text-stone-400 text-sm">중심을 정하고 <b>조회</b>를 누르세요</div>
        ) : null}

        {/* 푸터: IBL 투명성 */}
        <div className="px-5 py-2 bg-stone-50 border-t border-stone-200 text-[11px] text-stone-400 font-mono truncate">
          {buildCode(center, radius)}
        </div>
      </div>

      {/* 가게 상세 — 소상공인 데이터(즉시) + 카카오 평점 링크·전화(클릭 시 조회) */}
      {detail && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-[1000] p-4" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-2xl shadow-xl border border-stone-200 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between px-5 py-4 border-b border-stone-100">
              <div className="min-w-0">
                <div className="font-semibold text-stone-800">{detail.store.name}</div>
                <div className="text-xs text-stone-400">{[detail.store.category, detail.store.subcategory].filter(Boolean).join(' · ')}</div>
                {detail.store.address && <div className="text-xs text-stone-500 mt-0.5">{detail.store.address}</div>}
              </div>
              <button onClick={() => setDetail(null)} className="text-stone-400 hover:text-stone-600 shrink-0">✕</button>
            </div>
            <div className="px-5 py-4 text-sm">
              {detail.loading ? (
                <div className="text-stone-400 text-center py-2">평점·연락처 불러오는 중…</div>
              ) : detail.match ? (
                <div className="space-y-2">
                  {detail.match.phone && <div className="text-stone-600">전화 <a href={`tel:${detail.match.phone}`} className="text-amber-700">{detail.match.phone}</a></div>}
                  {detail.match.category && detail.match.category !== detail.store.category && (
                    <div className="text-stone-500 text-xs">{detail.match.category}</div>
                  )}
                  {detail.match.url ? (
                    <a href={detail.match.url} target="_blank" rel="noreferrer"
                      className="inline-block px-3 py-1.5 rounded-lg bg-amber-700 text-white text-sm hover:bg-amber-800">
                      {detail.match.url.includes('place.map.kakao.com') ? '카카오맵에서 평점·리뷰 보기 →' : '상세 페이지 보기 →'}
                    </a>
                  ) : (
                    <div className="text-stone-400 text-xs">연결된 평점 페이지가 없습니다.</div>
                  )}
                </div>
              ) : (
                <div className="text-stone-400 text-center py-2">
                  카카오/네이버에서 일치하는 가게를 찾지 못했습니다.
                  <div className="mt-1 text-[11px]">소상공인 등록 정보만 표시됩니다.</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
