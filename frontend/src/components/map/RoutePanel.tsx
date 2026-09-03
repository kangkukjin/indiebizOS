/**
 * RoutePanel — 길찾기 패널(출발·도착 입력, 우리집, 경로 요약·주요 안내, 경로 주변 CCTV 목록).
 * 상태는 부모(MapInstrument)가 소유한다 — 핀·폴리라인·CCTV 마커가 같은 상태를 그리기 때문.
 * 능력: [sense:navigate_route] · [sense:cctv]{op:nearby} (부모의 api.ts 경유).
 */
import { useState } from 'react';
import type { Cctv, KeyGuide, Point, RouteResult, RouteSummary } from './types';

const HOME_KEY = 'directions.instrument.home';

interface Props {
  origin: Point; destination: Point;
  setOrigin: (p: Point) => void; setDestination: (p: Point) => void;
  pick: 'origin' | 'destination'; setPick: (p: 'origin' | 'destination') => void;
  onSearch: () => void; onReset: () => void; loading: boolean; error: string | null;
  result: RouteResult | null;
  cctvOn: boolean; cctvs: Cctv[]; cctvLoading: boolean; onToggleCctv: () => void; onSelectCctv: (c: Cctv) => void;
  onBack: () => void;
}

export function RoutePanel(p: Props) {
  const { origin, destination, setOrigin, setDestination, pick, setPick, onSearch, onReset, loading, error, result,
    cctvOn, cctvs, cctvLoading, onToggleCctv, onSelectCctv, onBack } = p;
  const [home, setHome] = useState<string>(() => localStorage.getItem(HOME_KEY) || '');
  const [editHome, setEditHome] = useState(false);
  const [homeDraft, setHomeDraft] = useState(home);

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
  const canSearch = (origin.text.trim() || origin.coord) && (destination.text.trim() || destination.coord);

  // 백엔드는 summary·key_guides 를 최상위로 반환(과거 routes[0] 중첩에서 평탄화됨). map_data.summary 폴백.
  const summary: RouteSummary | undefined = result?.summary || result?.routes?.[0]?.summary || result?.map_data?.summary;
  const guides: KeyGuide[] = (result?.key_guides || result?.routes?.[0]?.key_guides || []).filter((g) => g.name || g.guidance);
  const toll = summary ? (summary.toll ?? summary.fare?.toll) : undefined;

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-4 pt-3 pb-2 border-b border-stone-100 space-y-2">
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="-ml-1 px-1.5 py-0.5 rounded-lg text-stone-500 hover:bg-stone-100 text-sm">‹</button>
          <h2 className="text-sm font-semibold text-stone-800">🛣️ 길찾기</h2>
          <span className="ml-auto text-[11px] text-stone-400">지도를 눌러 <b className={pick === 'origin' ? 'text-green-600' : 'text-rose-600'}>{pick === 'origin' ? '출발지' : '도착지'}</b> 찍기</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setPick('origin')} title="다음 지도 클릭 → 출발지"
            className={`w-8 shrink-0 text-sm rounded-lg py-1.5 border ${pick === 'origin' ? 'bg-green-50 border-green-300' : 'bg-white border-stone-200'}`}>📍</button>
          <input value={origin.text} onChange={(e) => setOrigin({ text: e.target.value, coord: null })} onFocus={() => setPick('origin')}
            onKeyDown={(e) => e.key === 'Enter' && onSearch()} placeholder="출발지 — 지도 클릭 / 우리집 / 강남역"
            className="flex-1 min-w-0 px-3 py-1.5 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
          <button onClick={useHome} title={home ? `우리집: ${home}` : '우리집 주소 등록'}
            className={`shrink-0 px-2 py-1.5 rounded-xl text-sm border ${home ? 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>🏠</button>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setPick('destination')} title="다음 지도 클릭 → 도착지"
            className={`w-8 shrink-0 text-sm rounded-lg py-1.5 border ${pick === 'destination' ? 'bg-rose-50 border-rose-300' : 'bg-white border-stone-200'}`}>🏁</button>
          <input value={destination.text} onChange={(e) => setDestination({ text: e.target.value, coord: null })} onFocus={() => setPick('destination')}
            onKeyDown={(e) => e.key === 'Enter' && onSearch()} placeholder="도착지 — 지도 클릭 / 수원역 / 시청"
            className="flex-1 min-w-0 px-3 py-1.5 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
          <button onClick={swap} title="출발↔도착 바꾸기" className="shrink-0 px-2 py-1.5 rounded-xl text-sm border bg-white border-stone-200 text-stone-600 hover:bg-stone-50">⇅</button>
        </div>
        {editHome && (
          <div className="flex gap-1.5 items-center">
            <input value={homeDraft} onChange={(e) => setHomeDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && saveHome()}
              placeholder="우리집 주소 (예: 서울 강남구 테헤란로 152)"
              className="flex-1 min-w-0 px-3 py-1.5 rounded-xl border border-amber-200 bg-amber-50 text-sm outline-none focus:border-amber-400" />
            <button onClick={saveHome} className="px-3 py-1.5 rounded-xl bg-amber-600 text-white text-sm hover:bg-amber-500">저장</button>
          </div>
        )}
        <div className="flex gap-1.5">
          <button onClick={onSearch} disabled={loading || !canSearch}
            className="flex-1 px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40">{loading ? '경로 찾는 중…' : '길찾기'}</button>
          <button onClick={onToggleCctv} title="경로 주변 도로 CCTV"
            className={`px-3 py-2 rounded-xl text-sm border ${cctvOn ? 'bg-red-500 text-white border-red-500' : 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50'}`}>
            📹{cctvLoading ? '…' : cctvOn && cctvs.length ? ` ${cctvs.length}` : ''}
          </button>
          <button onClick={() => { setEditHome((v) => !v); setHomeDraft(home); }} title="집 주소 설정" className="px-2.5 py-2 rounded-xl text-sm border bg-white border-stone-200 text-stone-500 hover:bg-stone-50">⚙</button>
          <button onClick={onReset} title="초기화" className="px-2.5 py-2 rounded-xl text-sm border bg-white border-stone-200 text-stone-500 hover:bg-stone-50">↺</button>
        </div>
        {error && <div className="px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">{error}</div>}
      </div>

      <div className="flex-1 min-h-0 overflow-auto px-4 py-2.5 space-y-3">
        {summary && (
          <div className="flex flex-wrap gap-1.5">
            {summary.distance_km != null && <span className="px-3 py-1.5 rounded-full bg-white border border-stone-200 text-sm">🚗 {summary.distance_km}km</span>}
            {summary.duration_min != null && <span className="px-3 py-1.5 rounded-full bg-white border border-stone-200 text-sm">⏱ {summary.duration_min}분</span>}
            {toll ? <span className="px-3 py-1.5 rounded-full bg-white border border-stone-200 text-sm">💳 톨비 {toll.toLocaleString()}원</span> : null}
          </div>
        )}
        {cctvOn && cctvs.length > 0 && (
          <div>
            <div className="text-xs text-stone-400 mb-1.5">주변 CCTV {cctvs.length}대 · 누르면 영상</div>
            <div className="flex gap-1.5 flex-wrap">
              {cctvs.map((c, i) => (
                <button key={i} onClick={() => onSelectCctv(c)}
                  className="px-2.5 py-1 rounded-lg text-xs border bg-white border-stone-200 text-stone-600 hover:border-red-300 hover:text-red-600">
                  📹 {c.name}{c.distance_km != null ? <span className="text-stone-400 ml-1">{c.distance_km}km</span> : null}
                </button>
              ))}
            </div>
          </div>
        )}
        {guides.length > 0 && (
          <div>
            <div className="text-xs text-stone-400 mb-1.5">주요 안내</div>
            <div className="space-y-1">
              {guides.map((g, i) => (
                <div key={i} className="bg-white rounded-xl border border-stone-200 px-3 py-2 flex items-center justify-between gap-3">
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
        {!summary && !error && <div className="text-xs text-stone-400">출발지와 도착지를 입력하거나 지도를 눌러 찍고 <b>길찾기</b>를 누르세요. 가게 상세의 <b>출발/도착</b> 버튼으로도 채워집니다.</div>}
      </div>
    </div>
  );
}
