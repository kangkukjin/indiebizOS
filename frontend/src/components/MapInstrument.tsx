/**
 * MapInstrument — "지도" 앱 계기(앱 모드, 카카오맵 앱 모양). LLM 없음, 0 토큰.
 *
 *   지도 위 왼쪽 떠 있는 기둥 = 검색창 → 카테고리 칩 → 패널(검색 결과 / 가게 상세 / 저장한 장소 / 길찾기).
 *   · 장소 검색: [sense:place] — 키워드(지도 중심 편향)·카테고리(현 화면 반경)·"이 지역 재검색"
 *   · 가게 상세: [sense:place]{op:detail}(네이버 설명·블로그 언급) + 카카오 장소 페이지 <webview>
 *   · 장소 저장: outputs/map/places.json 원장([self:read]/[self:write]{format:json}) — 폴더(tag)·메모
 *   · 지도 클릭: [sense:reverse_geocode] 주소 카드(출발/도착/저장) — 길찾기 패널이 열려 있으면 출발/도착 핀
 *   · 내 위치: [sense:here] · 길찾기·CCTV: [sense:navigate_route]·[sense:cctv] (구 길찾기 계기 흡수)
 *
 * 표현만 여기, 능력은 어휘(custom_app_instrument.md 철칙 0). 어휘 호출은 map/api.ts 한 곳.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { StreamPlayer } from './StreamPlayer';
import type { StreamData } from './chat/chatUtils';
import { useRetryingLoad } from '../lib/use-retrying-load';
import type { Cctv, LatLng, Place, Point, RouteResult, SavedPlace } from './map/types';
import { CATEGORY_CHIPS, DEFAULT_CENTER, DEFAULT_TAG, fmtCoord, fmtDistance } from './map/types';
import { cctvNearby, loadSaved, placeDetail, reverseGeocode, runRoute, searchPlaces, whereAmI, writeSaved } from './map/api';
import type { Here, SearchOpts } from './map/api';
import { CCTV_ICON, dotIcon, hereIcon, pinIcon, spotIcon, starIcon } from './map/icons';
import { PlaceDetail } from './map/PlaceDetail';
import { SavedPanel } from './map/SavedPanel';
import { RoutePanel } from './map/RoutePanel';

const CACHE_KEY = 'directions.instrument.last';   // 마지막 출발·도착(구 길찾기 계기와 호환)
type Panel = 'none' | 'results' | 'detail' | 'saved' | 'route';

interface RouteCache { origin: Point; destination: Point }
function loadRouteCache(): RouteCache {
  try { const c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); if (c?.origin && c?.destination) return c; } catch { /* ignore */ }
  return { origin: { text: '', coord: null }, destination: { text: '', coord: null } };
}

export function MapInstrument() {
  /* ── 검색 ── */
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Place[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [activeChip, setActiveChip] = useState<string | null>(null);
  const [moved, setMoved] = useState(false);
  const lastSearchRef = useRef<SearchOpts | null>(null);
  const programmaticMove = useRef(false);   // panTo/fitBounds 는 '이 지역 재검색' 을 켜지 않는다

  /* ── 선택·상세 ── */
  const [panel, setPanel] = useState<Panel>('none');
  const [selected, setSelected] = useState<Place | null>(null);
  const [detail, setDetail] = useState<Place | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailCache = useRef(new Map<string, Place>());

  /* ── 저장 장소 ── */
  const [saved, setSaved] = useState<SavedPlace[]>([]);
  const [saving, setSaving] = useState(false);
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  /* ── 지도 클릭 카드 · 내 위치 ── */
  const [spot, setSpot] = useState<{ ll: LatLng; address: string } | null>(null);
  const [here, setHere] = useState<Here | null>(null);

  /* ── 길찾기 · CCTV ── */
  const routeInit = useMemo(loadRouteCache, []);
  const [origin, setOrigin] = useState<Point>(routeInit.origin);
  const [destination, setDestination] = useState<Point>(routeInit.destination);
  const [pick, setPick] = useState<'origin' | 'destination'>('origin');
  const [routeResult, setRouteResult] = useState<RouteResult | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [cctvOn, setCctvOn] = useState(false);
  const [cctvs, setCctvs] = useState<Cctv[]>([]);
  const [cctvLoading, setCctvLoading] = useState(false);
  const [selectedCctv, setSelectedCctv] = useState<StreamData | null>(null);

  /* ── 지도 refs ── */
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const resultsLayer = useRef<L.LayerGroup | null>(null);
  const savedLayer = useRef<L.LayerGroup | null>(null);
  const routeLayer = useRef<L.LayerGroup | null>(null);
  const cctvLayer = useRef<L.LayerGroup | null>(null);
  const spotMarker = useRef<L.Marker | null>(null);
  const hereLayer = useRef<L.LayerGroup | null>(null);
  const originMarker = useRef<L.Marker | null>(null);
  const destMarker = useRef<L.Marker | null>(null);
  const panelRef = useRef(panel); panelRef.current = panel;
  const pickRef = useRef(pick); pickRef.current = pick;
  const cctvOnRef = useRef(cctvOn); cctvOnRef.current = cctvOn;

  const flash = (msg: string) => { setToast(msg); window.setTimeout(() => setToast(null), 3500); };
  const center = (): LatLng | null => { const m = mapRef.current; if (!m) return null; const c = m.getCenter(); return { lat: c.lat, lng: c.lng }; };
  // 현 화면 반경(m) — 중심→모서리 거리의 0.8, 300m~20km(카카오 상한).
  const viewRadius = (): number => {
    const m = mapRef.current; if (!m) return 2000;
    const d = m.distance(m.getCenter(), m.getBounds().getNorthEast());
    return Math.round(Math.min(20000, Math.max(300, d * 0.8)));
  };

  /* ══ 장소 검색 ══ */
  const runPlaceSearch = useCallback(async (o: SearchOpts, fit = true) => {
    setSearching(true);
    try {
      const r = await searchPlaces(o);
      if (r.error) { flash(r.error); setResults([]); setTotal(0); }
      else {
        setResults(r.items); setTotal(r.total);
        if (r.items.length === 0) flash('검색 결과가 없습니다');
        const m = mapRef.current;
        if (fit && m && r.items.length) {
          const b = L.latLngBounds(r.items.map((p) => [p.lat, p.lng] as L.LatLngTuple));
          programmaticMove.current = true; m.fitBounds(b.pad(0.2), { maxZoom: 16 });
        }
      }
      lastSearchRef.current = o; setMoved(false);
      setPanel('results'); setSelected(null); setSpot(null);
    } catch { flash('서버에 연결할 수 없습니다'); }
    setSearching(false);
  }, []);

  const searchKeyword = () => {
    const q = query.trim(); if (!q) return;
    setActiveChip(null);
    runPlaceSearch({ query: q, center: center(), limit: 30 });
  };
  const searchCategory = (label: string) => {
    if (activeChip === label) { setActiveChip(null); setResults([]); setPanel('none'); lastSearchRef.current = null; return; }
    setActiveChip(label); setQuery('');
    runPlaceSearch({ category: label, center: center(), radius: viewRadius(), sort: 'distance', limit: 30 }, false);
  };
  const researchHere = () => {
    const last = lastSearchRef.current; if (!last) return;
    runPlaceSearch({ ...last, center: center(), radius: viewRadius(), sort: last.category ? 'distance' : 'accuracy' }, false);
  };

  /* ══ 선택 → 상세 ══ */
  const select = useCallback(async (p: Place, pan = true) => {
    setSelected(p); setPanel('detail'); setSpot(null);
    const m = mapRef.current;
    if (pan && m) { programmaticMove.current = true; m.panTo([p.lat, p.lng], { animate: true }); }
    const cached = detailCache.current.get(p.id);
    if (cached) { setDetail(cached); return; }
    setDetail(null); setDetailLoading(true);
    try {
      const d = await placeDetail(p);
      if (d) { detailCache.current.set(p.id, d); setDetail(d); }
    } catch { /* 상세는 보너스 — 실패해도 기본 정보는 있다 */ }
    setDetailLoading(false);
  }, []);

  /* ══ 저장 장소 원장 ══ */
  useRetryingLoad(useCallback(async () => { setSaved(await loadSaved()); }, []));
  const persist = async (next: SavedPlace[]) => {
    setSaved(next); setSaving(true);
    const ok = await writeSaved(next).catch(() => false);
    setSaving(false);
    if (!ok) flash('저장 원장 기록에 실패했습니다');
  };
  const savedOf = (p: Place | null) => (p ? saved.find((x) => x.id === p.id) || null : null);
  const savePlace = (p: Place, tag: string) => {
    if (saved.some((x) => x.id === p.id)) return;
    const row: SavedPlace = { ...p, tag: tag || DEFAULT_TAG, memo: '', saved_at: new Date().toISOString() };
    delete (row as Partial<Place>).distance;
    persist([...saved, row]);
  };
  const unsave = (id: string) => persist(saved.filter((x) => x.id !== id));
  const updateSaved = (id: string, patch: Partial<SavedPlace>) => persist(saved.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  const tags = Array.from(new Set(saved.map((x) => x.tag || DEFAULT_TAG)));

  /* ══ 길찾기 ══ */
  const loadCctvAlongRoute = useCallback(async (path: [number, number][]) => {
    if (!path?.length) return;
    setCctvLoading(true);
    const N = Math.min(8, path.length); const step = Math.max(1, Math.floor(path.length / N));
    const samples: [number, number][] = [];
    for (let i = 0; i < path.length; i += step) samples.push(path[i]);
    const last = path[path.length - 1];
    if (samples[samples.length - 1]?.[0] !== last[0]) samples.push(last);
    const lists = await Promise.all(samples.map(([lat, lng]) => cctvNearby({ lat, lng }, 2.8, 2)));
    const seen = new Set<string>(); const all: Cctv[] = [];
    for (const l of lists) for (const c of l) { const k = c.url || `${c.lat},${c.lng}`; if (!seen.has(k)) { seen.add(k); all.push(c); } }
    setCctvs(all); setCctvLoading(false);
  }, []);
  const loadCctvNearCenter = useCallback(async () => {
    const c = center(); if (!c) return;
    setCctvLoading(true); setCctvs(await cctvNearby(c, 5.5, 12)); setCctvLoading(false);
  }, []);

  const doRoute = useCallback(async (o: Point, d: Point) => {
    const os = o.coord ? `${o.coord.lng},${o.coord.lat}` : o.text.trim();
    const ds = d.coord ? `${d.coord.lng},${d.coord.lat}` : d.text.trim();
    if (!os || !ds) return;
    setRouteLoading(true); setRouteError(null);
    let r: RouteResult;
    try { r = await runRoute(os, ds); }
    catch (e) { setRouteLoading(false); setRouteError('서버에 연결할 수 없습니다.'); throw e; }
    setRouteLoading(false);
    if (r.error) { setRouteError(r.error); setRouteResult(null); return; }
    setRouteResult(r);
    if (r.map_data) {
      const no: Point = { text: r.map_data.origin.name || o.text, coord: { lat: r.map_data.origin.lat, lng: r.map_data.origin.lng } };
      const nd: Point = { text: r.map_data.destination.name || d.text, coord: { lat: r.map_data.destination.lat, lng: r.map_data.destination.lng } };
      setOrigin(no); setDestination(nd);
      localStorage.setItem(CACHE_KEY, JSON.stringify({ origin: no, destination: nd }));
      if (cctvOnRef.current) loadCctvAlongRoute(r.map_data.path);
    }
  }, [loadCctvAlongRoute]);
  const routeNow = (o: Point, d: Point) => { doRoute(o, d).catch(() => {}); };
  const resetRoute = () => {
    setOrigin({ text: '', coord: null }); setDestination({ text: '', coord: null });
    setRouteResult(null); setRouteError(null); setPick('origin'); routeLayer.current?.clearLayers();
  };
  const toggleCctv = () => {
    const next = !cctvOn; setCctvOn(next);
    if (next) { if (routeResult?.map_data?.path) loadCctvAlongRoute(routeResult.map_data.path); else loadCctvNearCenter(); }
    else setCctvs([]);
  };
  // 가게 상세/주소 카드 → 출발지·도착지 채우기. 둘 다 차면 바로 경로.
  const routeFrom = (text: string, coord: LatLng) => {
    const o: Point = { text, coord }; setOrigin(o); setPick('destination'); setPanel('route'); setSpot(null);
    if (destination.text.trim() || destination.coord) routeNow(o, destination);
  };
  const routeTo = (text: string, coord: LatLng) => {
    const d: Point = { text, coord }; setDestination(d); setPanel('route'); setSpot(null);
    if (origin.text.trim() || origin.coord) routeNow(origin, d); else setPick('origin');
  };

  /* ══ 내 위치 ══ */
  const goHere = async () => {
    try {
      const h = await whereAmI();
      if (!h) { flash('위치를 알 수 없습니다'); return; }
      setHere(h); mapRef.current?.flyTo([h.lat, h.lng], h.accuracy_m && h.accuracy_m > 1500 ? 13 : 15);
    } catch { flash('서버에 연결할 수 없습니다'); }
  };

  /* ══ 지도 1회 초기화 ══ */
  useEffect(() => {
    if (!mapDiv.current || mapRef.current) return;
    const c0 = routeInit.origin.coord || routeInit.destination.coord || DEFAULT_CENTER;
    const map = L.map(mapDiv.current, { scrollWheelZoom: true, zoomControl: false }).setView([c0.lat, c0.lng], 13);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    mapRef.current = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);
    savedLayer.current = L.layerGroup().addTo(map);
    routeLayer.current = L.layerGroup().addTo(map);
    cctvLayer.current = L.layerGroup().addTo(map);
    resultsLayer.current = L.layerGroup().addTo(map);
    hereLayer.current = L.layerGroup().addTo(map);

    map.on('click', async (e: L.LeafletMouseEvent) => {
      const ll = { lat: e.latlng.lat, lng: e.latlng.lng };
      if (panelRef.current === 'route') {
        // 길찾기 모드: 클릭 = 출발/도착 핀
        if (pickRef.current === 'origin') { setOrigin({ text: fmtCoord(ll), coord: ll }); setPick('destination'); }
        else setDestination({ text: fmtCoord(ll), coord: ll });
        return;
      }
      // 그 밖: 주소 카드(카카오맵의 지도 탭 → 주소)
      setSpot({ ll, address: '' });
      const addr = await reverseGeocode(ll);
      setSpot((s) => (s && s.ll.lat === ll.lat && s.ll.lng === ll.lng ? { ll, address: addr || fmtCoord(ll) } : s));
    });
    map.on('moveend', () => {
      if (programmaticMove.current) { programmaticMove.current = false; return; }
      if (lastSearchRef.current) setMoved(true);
    });
    setTimeout(() => map.invalidateSize(), 120);
    return () => { map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 캐시 복원분 자동 길찾기 — 마운트 1회(백엔드가 아직 안 떠 있으면 훅이 백오프 재시도).
  const hasRouteCache = !!((routeInit.origin.text || routeInit.origin.coord) && (routeInit.destination.text || routeInit.destination.coord));
  useRetryingLoad(useCallback(() => doRoute(routeInit.origin, routeInit.destination), [routeInit, doRoute]), { enabled: hasRouteCache });

  /* ══ 레이어 반영 ══ */
  // 검색 결과 번호 핀
  useEffect(() => {
    const layer = resultsLayer.current; if (!layer) return;
    layer.clearLayers();
    results.forEach((p, i) => {
      const active = selected?.id === p.id;
      const mk = L.marker([p.lat, p.lng], { icon: pinIcon(i + 1, active), zIndexOffset: active ? 1000 : 0 })
        .bindTooltip(p.name, { direction: 'top' })
        .on('click', () => select(p, false));
      mk.addTo(layer);
    });
  }, [results, selected, select]);

  // 저장 장소 별 — 항상 표시(검색 결과와 겹치면 결과 핀이 위)
  useEffect(() => {
    const layer = savedLayer.current; if (!layer) return;
    layer.clearLayers();
    const list = tagFilter && panel === 'saved' ? saved.filter((x) => (x.tag || DEFAULT_TAG) === tagFilter) : saved;
    list.forEach((p) => {
      if (results.some((r) => r.id === p.id)) return;
      L.marker([p.lat, p.lng], { icon: starIcon(selected?.id === p.id) })
        .bindTooltip(p.memo ? `${p.name} · ${p.memo}` : p.name, { direction: 'top' })
        .on('click', () => select(p, false))
        .addTo(layer);
    });
  }, [saved, results, selected, select, tagFilter, panel]);

  // 지도 클릭 지점
  useEffect(() => {
    const m = mapRef.current; if (!m) return;
    if (spotMarker.current) { m.removeLayer(spotMarker.current); spotMarker.current = null; }
    if (spot) spotMarker.current = L.marker([spot.ll.lat, spot.ll.lng], { icon: spotIcon, zIndexOffset: 1200 }).addTo(m);
  }, [spot]);

  // 내 위치
  useEffect(() => {
    const layer = hereLayer.current; if (!layer) return;
    layer.clearLayers();
    if (!here) return;
    if (here.accuracy_m) L.circle([here.lat, here.lng], { radius: here.accuracy_m, color: '#2563EB', weight: 1, fillOpacity: 0.08 }).addTo(layer);
    L.marker([here.lat, here.lng], { icon: hereIcon }).bindTooltip(here.address || '내 위치', { direction: 'top' }).addTo(layer);
  }, [here]);

  // 출발/도착 핀 · 경로 폴리라인 · CCTV
  useEffect(() => {
    const m = mapRef.current; if (!m) return;
    const upsert = (ref: React.MutableRefObject<L.Marker | null>, coord: LatLng | null, color: string, label: string) => {
      if (coord) {
        if (!ref.current) ref.current = L.marker([coord.lat, coord.lng], { icon: dotIcon(color), zIndexOffset: 900 }).bindTooltip(label, { direction: 'top', offset: [0, -8] }).addTo(m);
        else ref.current.setLatLng([coord.lat, coord.lng]);
      } else if (ref.current) { m.removeLayer(ref.current); ref.current = null; }
    };
    upsert(originMarker, origin.coord, '#22C55E', '출발');
    upsert(destMarker, destination.coord, '#EF4444', '도착');
  }, [origin.coord, destination.coord]);
  useEffect(() => {
    const layer = routeLayer.current; const m = mapRef.current; if (!layer || !m) return;
    layer.clearLayers();
    const path = routeResult?.map_data?.path;
    if (path?.length) {
      const pl = L.polyline(path as L.LatLngExpression[], { color: '#3B82F6', weight: 5, opacity: 0.85 }).addTo(layer);
      programmaticMove.current = true; m.fitBounds(pl.getBounds(), { padding: [40, 40], paddingTopLeft: [400, 40] });
    }
  }, [routeResult]);
  useEffect(() => {
    const layer = cctvLayer.current; if (!layer) return;
    layer.clearLayers();
    if (!cctvOn) return;
    cctvs.forEach((c) => {
      if (!c.lat || !c.lng) return;
      L.marker([c.lat, c.lng], { icon: CCTV_ICON }).bindTooltip(c.name || 'CCTV', { direction: 'top', offset: [0, -8] })
        .on('click', () => setSelectedCctv({ url: c.url || '', name: c.name, source: c.source, lat: c.lat, lng: c.lng, playable: c.playable }))
        .addTo(layer);
    });
  }, [cctvs, cctvOn]);

  // 패널이 열리고 닫힐 때 지도 크기 재계산(레이아웃은 오버레이라 필요 없지만 안전).
  useEffect(() => { setTimeout(() => mapRef.current?.invalidateSize(), 60); }, [panel]);

  /* ══ 렌더 ══ */
  const backToResults = () => { setPanel(results.length ? 'results' : 'none'); setSelected(null); };
  const iconBtn = (active: boolean) => `shrink-0 w-9 h-9 rounded-xl text-base border shadow-sm ${active ? 'bg-stone-800 text-white border-stone-800' : 'bg-white/95 border-stone-200 text-stone-600 hover:bg-white'}`;

  return (
    <div className="h-full w-full relative isolate bg-stone-100 text-stone-800 overflow-hidden">
      {/* 지도 — isolate: leaflet 컨트롤(z 1000)이 CCTV 영상 모달(fixed z-[1000]) 위로 새지 않게 */}
      <div ref={mapDiv} className="absolute inset-0" />

      {/* 왼쪽 떠 있는 기둥: 검색창 → 칩 → 패널 */}
      <div className="absolute z-[500] left-3 top-3 bottom-3 w-[390px] max-w-[calc(100%-1.5rem)] flex flex-col gap-2 pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-1.5">
          <div className="flex-1 flex items-center gap-1 h-11 px-3 rounded-2xl bg-white shadow-md border border-stone-200">
            <span className="text-stone-400 text-sm">🔍</span>
            <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyUp={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && searchKeyword()}
              placeholder="장소·가게·주소 검색 (예: 성수동 카페, 서울시청)"
              className="flex-1 min-w-0 bg-transparent text-sm outline-none placeholder:text-stone-400" />
            {query && <button onClick={() => { setQuery(''); }} className="text-stone-400 hover:text-stone-600 text-xs px-1">✕</button>}
            <button onClick={searchKeyword} disabled={searching || !query.trim()} className="text-sm px-2 py-1 rounded-lg bg-stone-800 text-white disabled:opacity-30">{searching ? '…' : '검색'}</button>
          </div>
          <button onClick={() => setPanel(panel === 'saved' ? 'none' : 'saved')} title="저장한 장소" className={iconBtn(panel === 'saved')}>⭐</button>
          <button onClick={() => setPanel(panel === 'route' ? 'none' : 'route')} title="길찾기" className={iconBtn(panel === 'route')}>🛣️</button>
        </div>

        <div className="pointer-events-auto flex gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden pb-0.5">
          {CATEGORY_CHIPS.map((c) => (
            <button key={c.label} onClick={() => searchCategory(c.label)}
              className={`shrink-0 px-2.5 py-1 rounded-full text-xs border shadow-sm ${activeChip === c.label ? 'bg-blue-600 text-white border-blue-600' : 'bg-white/95 border-stone-200 text-stone-700 hover:bg-white'}`}>
              {c.icon} {c.label}
            </button>
          ))}
        </div>

        {panel !== 'none' && (
          <div className="pointer-events-auto flex-1 min-h-0 rounded-2xl bg-[#FAFAF8] shadow-lg border border-stone-200 overflow-hidden flex flex-col">
            {panel === 'results' && (
              <div className="flex flex-col h-full min-h-0">
                <div className="px-4 pt-3 pb-2 border-b border-stone-100 flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-stone-800">{activeChip ? `${activeChip} 주변` : `‘${lastSearchRef.current?.query || query}’`}</h2>
                  <span className="text-xs text-stone-400">{results.length}곳{total > results.length ? ` / ${total.toLocaleString()}` : ''}</span>
                  <button onClick={() => { setPanel('none'); setResults([]); setActiveChip(null); lastSearchRef.current = null; }} className="ml-auto text-stone-400 hover:text-stone-600 text-sm px-1">✕</button>
                </div>
                <div className="flex-1 min-h-0 overflow-auto">
                  {results.map((p, i) => {
                    const isSaved = saved.some((x) => x.id === p.id);
                    return (
                      <div key={p.id} onClick={() => select(p)} className="px-4 py-2.5 border-b border-stone-100 hover:bg-white cursor-pointer">
                        <div className="flex items-start gap-2.5">
                          <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full bg-blue-600 text-white text-[11px] font-bold flex items-center justify-center">{i + 1}</span>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-baseline gap-2">
                              <span className="text-sm font-medium text-stone-800 truncate">{p.name}</span>
                              {p.cat && <span className="text-[11px] text-stone-400 shrink-0">{p.cat}</span>}
                              {isSaved && <span className="text-[11px] shrink-0">⭐</span>}
                            </div>
                            <div className="text-xs text-stone-500 truncate">{p.address}</div>
                            <div className="text-[11px] text-stone-400 flex gap-2">
                              {p.distance != null && <span>📏 {fmtDistance(p.distance)}</span>}
                              {p.phone && <span>☎ {p.phone}</span>}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {results.length === 0 && !searching && <div className="px-4 py-8 text-center text-xs text-stone-400">결과가 없습니다</div>}
                </div>
              </div>
            )}
            {panel === 'detail' && selected && (
              <PlaceDetail place={selected} detail={detail} detailLoading={detailLoading} saved={savedOf(selected)} tags={tags}
                onBack={backToResults}
                onSave={(tag) => savePlace(selected, tag)} onUnsave={() => unsave(selected.id)}
                onUpdateSaved={(patch) => updateSaved(selected.id, patch)}
                onRouteFrom={() => routeFrom(selected.name, { lat: selected.lat, lng: selected.lng })}
                onRouteTo={() => routeTo(selected.name, { lat: selected.lat, lng: selected.lng })} />
            )}
            {panel === 'saved' && (
              <SavedPanel saved={saved} tagFilter={tagFilter} onTagFilter={setTagFilter} saving={saving}
                onSelect={(p) => { select(p); mapRef.current?.setView([p.lat, p.lng], Math.max(mapRef.current.getZoom(), 15)); }}
                onDelete={unsave} onBack={() => setPanel('none')} />
            )}
            {panel === 'route' && (
              <RoutePanel origin={origin} destination={destination} setOrigin={setOrigin} setDestination={setDestination}
                pick={pick} setPick={setPick} onSearch={() => routeNow(origin, destination)} onReset={resetRoute}
                loading={routeLoading} error={routeError} result={routeResult}
                cctvOn={cctvOn} cctvs={cctvs} cctvLoading={cctvLoading} onToggleCctv={toggleCctv}
                onSelectCctv={(c) => setSelectedCctv({ url: c.url || '', name: c.name, source: c.source, lat: c.lat, lng: c.lng, playable: c.playable })}
                onBack={() => setPanel('none')} />
            )}
          </div>
        )}
      </div>

      {/* 지도 위 오른쪽 컨트롤: 내 위치 · CCTV(경로 패널 밖에서도) */}
      <div className="absolute z-[500] right-3 top-3 flex flex-col gap-1.5">
        <button onClick={goHere} title="내 위치" className={iconBtn(false)}>📍</button>
        <button onClick={toggleCctv} title="주변 도로 CCTV" className={`${iconBtn(cctvOn)} ${cctvOn ? '!bg-red-500 !border-red-500' : ''} text-sm`}>📹{cctvLoading ? '…' : cctvOn && cctvs.length ? <span className="text-[10px] ml-0.5">{cctvs.length}</span> : ''}</button>
      </div>

      {/* 이 지역 재검색 */}
      {moved && lastSearchRef.current && (
        <button onClick={researchHere} className="absolute z-[500] top-3 left-1/2 -translate-x-1/2 ml-[195px] px-3.5 py-1.5 rounded-full bg-white shadow-md border border-stone-200 text-xs text-blue-700 hover:bg-blue-50">
          ↻ 이 지역에서 재검색
        </button>
      )}

      {/* 지도 클릭 주소 카드 */}
      {spot && panel !== 'route' && (
        <div className="absolute z-[500] bottom-4 left-1/2 -translate-x-1/2 ml-[195px] w-[340px] max-w-[calc(100%-2rem)] rounded-2xl bg-white shadow-lg border border-stone-200 px-4 py-3">
          <div className="flex items-start gap-2">
            <span>📍</span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-stone-800 truncate">{spot.address || '주소 확인 중…'}</div>
              <div className="text-[11px] text-stone-400">{fmtCoord(spot.ll)}</div>
            </div>
            <button onClick={() => setSpot(null)} className="text-stone-400 hover:text-stone-600 text-sm">✕</button>
          </div>
          <div className="mt-2 flex gap-1.5">
            <button onClick={() => routeFrom(spot.address || fmtCoord(spot.ll), spot.ll)} className="px-2.5 py-1.5 rounded-lg text-xs border bg-white border-stone-200 hover:bg-stone-50">출발</button>
            <button onClick={() => routeTo(spot.address || fmtCoord(spot.ll), spot.ll)} className="px-2.5 py-1.5 rounded-lg text-xs bg-stone-800 text-white hover:bg-stone-700">도착</button>
            <button onClick={() => runPlaceSearch({ category: '음식점', center: spot.ll, radius: 500, sort: 'distance', limit: 30 }, false)} className="px-2.5 py-1.5 rounded-lg text-xs border bg-white border-stone-200 hover:bg-stone-50">주변 음식점</button>
            <button onClick={() => { const id = `spot:${spot.ll.lat.toFixed(5)},${spot.ll.lng.toFixed(5)}`; savePlace({ id, name: spot.address || fmtCoord(spot.ll), address: spot.address, lat: spot.ll.lat, lng: spot.ll.lng, cat: '위치' }, DEFAULT_TAG); flash('위치를 저장했습니다'); }}
              className="ml-auto px-2.5 py-1.5 rounded-lg text-xs border bg-white border-stone-200 hover:border-amber-300 hover:text-amber-700">☆ 저장</button>
          </div>
        </div>
      )}

      {toast && <div className="absolute z-[600] bottom-4 right-4 px-4 py-2 rounded-lg bg-stone-800/90 text-white text-sm shadow">{toast}</div>}

      {/* 선택한 CCTV 영상 모달 */}
      {selectedCctv && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[1000] p-4" onClick={() => setSelectedCctv(null)}>
          <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <StreamPlayer data={selectedCctv} variant="neutral" />
            <button onClick={() => setSelectedCctv(null)} className="mt-2 w-full px-4 py-2 rounded-xl bg-white/90 text-stone-700 text-sm hover:bg-white">닫기</button>
          </div>
        </div>
      )}
    </div>
  );
}
