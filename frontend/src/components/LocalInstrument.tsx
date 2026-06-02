/**
 * LocalInstrument — 지역정보 "계기(instrument)" (앱 모드)
 *
 * [sense:restaurant]{query} 직접 실행(LLM 없음, 0 토큰) — 카카오+네이버 Local 통합.
 * 지역 + 카테고리 다이얼 → 지도(leaflet 핀) + 목록. 카드 클릭 시 카카오맵 외부 열기.
 * 마지막 지역/카테고리는 localStorage에 굳힘.
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml (restaurant), location-services/handler.py
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { LocationMap, type LocationMapData } from './LocationMap';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'local.instrument.last';

interface Place {
  name: string; category?: string; address?: string; phone?: string;
  url?: string; x?: string; y?: string; source?: string;
}
interface RestaurantResult { combined?: Place[]; message?: string; error?: string }

const CATEGORIES = ['맛집', '카페', '병원', '약국', '주유소', '은행', '마트', '편의점'];

async function runIBL(query: string): Promise<RestaurantResult> {
  try {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: `[sense:restaurant]{query: "${query.replace(/"/g, '')}"}`, project_id: PROJECT_ID }),
    });
    return await res.json();
  } catch {
    return { error: '서버에 연결할 수 없습니다.' };
  }
}
// "음식점 > 카페 > 커피전문점" → "카페" (마지막 의미 토큰)
const shortCat = (c?: string) => (c ? c.split('>').map((s) => s.trim()).filter(Boolean).slice(-1)[0] || c : '');

interface Cache { region: string; category: string }
function loadCache(): Cache {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}'); } catch { return { region: '', category: '맛집' }; }
}

export function LocalInstrument() {
  const init = useMemo(loadCache, []);
  const [region, setRegion] = useState(init.region || '');
  const [category, setCategory] = useState(init.category || '맛집');
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapKey, setMapKey] = useState(0); // 검색마다 지도 리마운트(마커 갱신)

  const search = useCallback(async (rg: string, cat: string) => {
    const q = `${rg.trim()} ${cat}`.trim();
    if (!q) return;
    setLoading(true); setError(null); setPlaces(null);
    const r = await runIBL(q);
    setLoading(false);
    if (r.error) setError(r.error);
    else {
      setPlaces(r.combined || []);
      setMapKey((k) => k + 1);
      localStorage.setItem(CACHE_KEY, JSON.stringify({ region: rg, category: cat }));
    }
  }, []);

  // 첫 진입: 마지막(또는 기본) 검색
  useEffect(() => { search(region, category); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const pickCategory = (c: string) => { setCategory(c); search(region, c); };

  // 지도 데이터 구성 (x=경도, y=위도)
  const mapData: LocationMapData | null = useMemo(() => {
    const markers = (places || [])
      .map((p) => ({ name: p.name, lat: parseFloat(p.y || ''), lng: parseFloat(p.x || '') }))
      .filter((m) => !isNaN(m.lat) && !isNaN(m.lng));
    if (!markers.length) return null;
    return { type: 'location_map', center: { ...markers[0] }, zoom: 14, markers };
  }, [places]);

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 지역 + 카테고리 다이얼 */}
      <div className="shrink-0 px-5 pt-4 pb-2">
        <div className="flex gap-2">
          <input value={region} onChange={(e) => setRegion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search(region, category)}
            placeholder="지역 (예: 강남, 홍대, 제주시) — 비우면 전국"
            className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
          <button onClick={() => search(region, category)}
            className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {CATEGORIES.map((c) => (
            <button key={c} onClick={() => pickCategory(c)}
              className={`px-2.5 py-1 rounded-full text-xs border ${
                category === c ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50'
              }`}>
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto px-5 pb-6">
        {loading && <div className="py-10 text-center text-stone-400 text-sm">불러오는 중…</div>}
        {error && !loading && <div className="py-6 text-center text-rose-500 text-sm">{error}</div>}

        {places && !loading && !error && (
          <div className="max-w-2xl mx-auto">
            {/* 지도 */}
            {mapData && (
              <div className="mb-3 rounded-2xl overflow-hidden border border-stone-200">
                <LocationMap key={mapKey} data={mapData} />
              </div>
            )}

            {/* 목록 */}
            {places.length === 0 ? (
              <div className="py-12 text-center text-stone-400 text-sm">검색 결과가 없습니다.</div>
            ) : (
              <div className="space-y-1.5">
                {places.map((p, i) => (
                  <button key={`${p.name}-${i}`}
                    onClick={() => p.url && window.electron?.openExternal?.(p.url)}
                    className="w-full text-left bg-white rounded-xl border border-stone-200 hover:border-stone-400 px-4 py-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium text-sm truncate">{p.name}
                        {p.category && <span className="ml-2 text-[11px] text-stone-400">{shortCat(p.category)}</span>}
                      </div>
                      {p.address && <div className="text-xs text-stone-500 mt-0.5 truncate">{p.address}</div>}
                      {p.phone && <div className="text-xs text-stone-400 mt-0.5">{p.phone}</div>}
                    </div>
                    <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-md ${p.source === 'kakao' ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'}`}>
                      {p.source === 'kakao' ? '카카오' : p.source === 'naver' ? '네이버' : p.source}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
