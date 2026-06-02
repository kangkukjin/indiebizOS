/**
 * WeatherInstrument — 날씨 "계기(instrument)" (앱 모드)
 *
 * [sense:weather]{city, days:7} 직접 실행(LLM 없음, 0 토큰).
 * 현재 날씨 + 7일 예보 카드 + 기온 추이 차트(recharts). 마지막 도시는 localStorage에 굳힘.
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml (weather), location-services/handler.py
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { ResponsiveContainer, LineChart, Line, YAxis, XAxis, Tooltip, CartesianGrid, Legend } from 'recharts';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'weather.instrument.city';

interface Current { temp?: number; feels_like?: number; humidity?: number; wind_speed?: number; condition?: string }
interface Day { date: string; max_temp?: number; min_temp?: number; condition?: string; precipitation_mm?: number }
interface WeatherResult { city?: string; current?: Current; forecast?: Day[]; error?: string }

const CITY_CHIPS = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '수원', '춘천', '제주'];

// 날씨 상태(한국어) → 이모지
function wIcon(cond?: string): string {
  const c = cond || '';
  if (c.includes('뇌우') || c.includes('우박')) return '⛈️';
  if (c.includes('눈')) return '❄️';
  if (c.includes('소나기')) return '🌦️';
  if (c.includes('비') || c.includes('이슬비')) return '🌧️';
  if (c.includes('안개')) return '🌫️';
  if (c.includes('흐림')) return '☁️';
  if (c.includes('구름')) return '⛅';
  if (c.includes('대체로 맑음')) return '🌤️';
  if (c.includes('맑음')) return '☀️';
  return '🌡️';
}
const WD = ['일', '월', '화', '수', '목', '금', '토'];
function dayLabel(date: string): string {
  const d = new Date(date + 'T00:00:00');
  return `${d.getMonth() + 1}/${d.getDate()} (${WD[d.getDay()]})`;
}
const t1 = (n?: number) => (n == null ? '—' : `${Math.round(n)}°`);

async function runIBL(city: string): Promise<WeatherResult> {
  try {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: `[sense:weather]{city: "${city.replace(/"/g, '')}", days: 7}`, project_id: PROJECT_ID }),
    });
    return await res.json();
  } catch {
    return { error: '서버에 연결할 수 없습니다.' };
  }
}

export function WeatherInstrument() {
  const initCity = useMemo(() => localStorage.getItem(CACHE_KEY) || '서울', []);
  const [city, setCity] = useState(initCity);
  const [input, setInput] = useState('');
  const [data, setData] = useState<WeatherResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (c: string) => {
    const name = c.trim();
    if (!name) return;
    setCity(name); setInput('');
    setLoading(true); setError(null); setData(null);
    const r = await runIBL(name);
    setLoading(false);
    if (r.error) setError(`'${name}' ${r.error}`);
    else { setData(r); localStorage.setItem(CACHE_KEY, name); }
  }, []);

  // 첫 진입: 마지막 도시 자동 조회
  useEffect(() => { load(city); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const chartData = (data?.forecast || []).map((d) => ({
    label: dayLabel(d.date), 최고: d.max_temp, 최저: d.min_temp,
  }));

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 검색 */}
      <div className="shrink-0 px-5 pt-4 pb-2">
        <div className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load(input)}
            placeholder="도시명 (예: 청주, 부산, Tokyo)"
            className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
          <button onClick={() => load(input)}
            className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {CITY_CHIPS.map((c) => (
            <button key={c} onClick={() => load(c)}
              className={`px-2.5 py-1 rounded-full text-xs border ${
                city === c ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50'
              }`}>
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto px-5 pb-6">
        {loading && <div className="py-10 text-center text-stone-400 text-sm">불러오는 중…</div>}
        {error && !loading && <div className="py-6 text-center text-rose-500 text-sm">{error}</div>}

        {data?.current && !loading && (
          <div className="max-w-2xl mx-auto">
            {/* 현재 날씨 */}
            <div className="bg-white rounded-2xl border border-stone-200 p-5 flex items-center gap-5">
              <div className="text-6xl leading-none">{wIcon(data.current.condition)}</div>
              <div className="flex-1">
                <div className="text-sm text-stone-400">{data.city}</div>
                <div className="text-4xl font-bold">{t1(data.current.temp)}</div>
                <div className="text-sm text-stone-600">{data.current.condition} · 체감 {t1(data.current.feels_like)}</div>
              </div>
              <div className="text-right text-xs text-stone-500 space-y-1">
                <div>습도 {data.current.humidity ?? '—'}%</div>
                <div>바람 {data.current.wind_speed ?? '—'} m/s</div>
              </div>
            </div>

            {/* 기온 추이 차트 */}
            {chartData.length > 1 && (
              <div className="mt-4 bg-white rounded-2xl border border-stone-200 p-4">
                <div className="text-xs text-stone-400 mb-2">7일 기온 추이</div>
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0ede8" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#a8a29e' }} minTickGap={20} />
                      <YAxis tick={{ fontSize: 10, fill: '#a8a29e' }} width={32} tickFormatter={(v) => `${v}°`} />
                      <Tooltip formatter={(v: number) => `${v}°`} contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e7e5e4' }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Line type="monotone" dataKey="최고" stroke="#e11d48" strokeWidth={2} dot={{ r: 2 }} />
                      <Line type="monotone" dataKey="최저" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* 7일 예보 */}
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(data.forecast || []).map((d) => (
                <div key={d.date} className="bg-white rounded-xl border border-stone-200 px-3 py-3 text-center">
                  <div className="text-xs text-stone-400">{dayLabel(d.date)}</div>
                  <div className="text-2xl my-1">{wIcon(d.condition)}</div>
                  <div className="text-sm">
                    <span className="text-rose-600 font-medium">{t1(d.max_temp)}</span>
                    <span className="text-stone-300 mx-1">/</span>
                    <span className="text-blue-600">{t1(d.min_temp)}</span>
                  </div>
                  {d.precipitation_mm != null && d.precipitation_mm > 0 && (
                    <div className="text-[11px] text-sky-500 mt-1">💧 {d.precipitation_mm}mm</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
