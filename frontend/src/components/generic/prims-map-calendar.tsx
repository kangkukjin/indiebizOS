/**
 * generic/prims-map-calendar.tsx — 지도(leaflet)·달력 프리미티브
 *
 * GenericInstrument.tsx 에서 분리(2026-07-18, 1500줄 규칙 모듈화).
 * MapPrim(정적+인터랙티브 `on:` 뷰-이벤트)·CalendarPrim(월 그리드+추가/삭제)·CalField.
 * p.type 디스패치는 GenericInstrument.tsx ViewPrim(정본 if-chain)에 있다.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  type AppViewPrim, type AppFormField, type Dispatch, type Json, type ViewEvent,
  jget, asList, fieldCls, RECURRENCE_OPTS, dateInputType,
} from './manifest';
import { Card } from './prims-basic';

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

/** map 프리미티브 — leaflet. 정적(원격 initMaps 동치) + 인터랙티브(`on:` 뷰-이벤트).
 *  봉투(p.from, 기본 map_data): {center, markers:[{lat,lng,name}], path:[[lat,lng]], origin, destination}
 *  p.markers: 추가 마커 리스트 경로(예: items) — 각 {lat,lng,name|title,meta,url,id}. p.max=마커 상한.
 *  p.on(인터랙티브): {moveend|center_drag: 재조회 템플릿($lat/$lng/$radius), marker_click: 마커 액션($id/$name/$lat/$lng/$url) | {stream:true}=마커 영상 재생(CCTV)}.
 *  ★루프 가드: fitBounds 는 첫 로드만(interactive 면 didFit 후 안 함) — 재조회→마커갱신은 viewport 유지.
 *           moveend 는 progMove(프로그래매틱 이동) 무시 + 디바운스. */
export function MapPrim({ p, data, onViewEvent, onStream }: { p: AppViewPrim; data: unknown; onViewEvent?: ViewEvent; onStream?: (item: Json) => void }) {
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
  const searchHereTpl = (on && typeof on.search_here === 'string') ? on.search_here : undefined;
  // viewport 보존(첫 로드만 fit) 모드는 *이동/버튼 재조회*(moveend/center_drag/search_here)가 있을 때만.
  // marker_click(스트림/액션)만 있는 경우는 정적 fit 유지(CCTV 키워드검색: 매 검색마다 새 결과로 재fit).
  // search_here(이 지역 검색 버튼)도 viewport 보존 — 사용자가 잡은 영역에 결과가 뜨고 지도가 튀지 않게.
  const interactive = !!(on && (on.moveend || on.center_drag || on.search_here));

  const fireMove = useCallback((lat: number, lng: number) => {
    const pon = pRef.current.on as Record<string, string | { stream?: boolean }> | undefined;
    const tpl = (pon?.moveend || pon?.center_drag) as string | undefined;
    const map = mapRef.current;
    if (!tpl || !map || !evRef.current) return;
    const r = Math.round(map.distance(map.getCenter(), map.getBounds().getNorthEast())); // viewport 반경(m)
    evRef.current(tpl, { lat: lat.toFixed(6), lng: lng.toFixed(6), radius: String(r), radius_km: (r / 1000).toFixed(2) });
  }, []);

  // "이 지역에서 검색" 버튼 — 현재 지도 중심·반경을 액션 템플릿($lat/$lng/$radius/$radius_km)에 실어 재조회.
  // moveend 자동 재조회와 달리 사용자가 영역을 잡고 명시적으로 누를 때만 실행(불필요한 팬-재조회 방지).
  const fireSearchHere = useCallback(() => {
    const map = mapRef.current;
    if (!searchHereTpl || !map || !evRef.current) return;
    const c = map.getCenter();
    const r = Math.round(map.distance(c, map.getBounds().getNorthEast())); // viewport 반경(m)
    evRef.current(searchHereTpl, { lat: c.lat.toFixed(6), lng: c.lng.toFixed(6), radius: String(r), radius_km: (r / 1000).toFixed(2) });
  }, [searchHereTpl]);

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
  // ★isolate: leaflet 내부 pane/컨트롤 z-index(400~1000)를 이 스택 컨텍스트 안에 가둔다 —
  //  안 그러면 지도가 런처 모드 드롭다운(z-50) 등 상위 오버레이 위로 새어 나와 가린다.
  return (
    <div className="relative mb-2.5">
      <div ref={ref} style={{ height: 320 }} className="isolate rounded-xl overflow-hidden bg-stone-100" />
      {searchHereTpl && (
        <button onClick={fireSearchHere}
          className="absolute top-2 left-1/2 -translate-x-1/2 z-[500] px-3 py-1.5 rounded-full bg-white shadow-md border border-stone-300 text-sm font-medium text-stone-700 hover:bg-stone-50 active:scale-95 transition">
          📍 이 지역에서 검색
        </button>
      )}
    </div>
  );
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

export function CalendarPrim({ p, data, dispatch }: { p: AppViewPrim; data: unknown; dispatch: Dispatch }) {
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
              {(add.fields || [{ key: 'title', type: 'text', placeholder: '일정 제목' }] as AppFormField[]).map((f, i) => (
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
