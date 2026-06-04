/**
 * RealtyInstrument — 부동산 실거래가 "계기(instrument)"
 *
 * IBL 액션 [sense:realty] 를 사람이 직접 조작하는 첫 계기.
 * - 다이얼: 지역 / 유형(apt|house) / 거래(trade|rent) / 기간 / 건수
 * - 발화: POST /ibl/execute  (LLM 없음, 순수 코드 실행 — 0 토큰)
 * - 결정화: 마지막 조회를 localStorage에 굳혀, 다음 방문에 '이미 떠 있게'
 * - 드릴다운: 행 클릭 → 그 단지의 기간 추이
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml (realty), real-estate/handler.py
 */
import { useEffect, useMemo, useState, useCallback, useRef } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'realty.instrument.last';
const RECENT_KEY = 'realty.recent.regions';
const RECENT_MAX = 8;
function loadRecents(): { code: string; name: string }[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
}

// 주요 서울 자치구 법정동 코드 5자리 (district_codes 액션이 추후 이 자리를 자동완성으로 대체)
const SEOUL_GU: { name: string; code: string }[] = [
  { name: '강남', code: '11680' }, { name: '서초', code: '11650' },
  { name: '송파', code: '11710' }, { name: '강동', code: '11740' },
  { name: '마포', code: '11440' }, { name: '용산', code: '11170' },
  { name: '성동', code: '11200' }, { name: '영등포', code: '11560' },
  { name: '종로', code: '11110' }, { name: '양천', code: '11470' },
  { name: '노원', code: '11350' }, { name: '광진', code: '11215' },
];

type Deal = 'trade' | 'rent';
type RType = 'apt' | 'house';
interface Txn {
  아파트명?: string; 주택유형?: string; 건물명?: string; 명칭?: string; 법정동: string; 거래금액: string;
  전용면적?: string; 면적?: string; 층?: string; 건축년도: string;
  거래년도: string; 거래월: string; 거래일: string;
}
interface Summary { 총거래건수?: number; 평균가?: string; 최고가?: string; 최저가?: string; 조회기간?: string }
interface RealtyResult { success?: boolean; region_code?: string; period?: string; summary?: Summary; data?: Txn[]; error?: string }

interface Params { region_code: string; type: RType; deal: Deal; start_month: string; end_month: string; count: number; regionName?: string }

// 전국 시/도 (구/군 코드는 district_codes 액션이 제공 — 정적 행정 테이블)
const PROVINCES = ['서울', '경기', '부산', '인천', '대구', '대전', '광주', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'];
const _districtCache: Record<string, { name: string; code: string }[]> = {};
async function loadDistricts(province: string): Promise<{ name: string; code: string }[]> {
  if (_districtCache[province]) return _districtCache[province];
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: `[sense:realty]{op: "codes", city: "${province}", project_id: "${PROJECT_ID}"}`, project_path: '.' }),
  });
  const d = await res.json();
  const list = Object.entries((d && d.regions) || {}).map(([name, code]) => ({ name, code: String(code) }));
  _districtCache[province] = list;
  return list;
}

// ---------- helpers ----------
function ym(d: Date): string { return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`; }
function monthsAgo(n: number): string { const d = new Date(); d.setMonth(d.getMonth() - n); return ym(d); }
function toMonthInput(yyyymm: string): string { return `${yyyymm.slice(0, 4)}-${yyyymm.slice(4, 6)}`; }
function fromMonthInput(v: string): string { return v.replace('-', ''); }

/** "85,000" (만원) → "8억 5,000" */
function won(manwon: string): string {
  const n = parseInt(String(manwon).replace(/,/g, '').trim(), 10);
  if (!Number.isFinite(n)) return manwon;
  const eok = Math.floor(n / 10000);
  const rest = n % 10000;
  if (eok <= 0) return `${rest.toLocaleString()}만`;
  return rest ? `${eok}억 ${rest.toLocaleString()}` : `${eok}억`;
}
function pyeong(m2: string): string { const a = parseFloat(m2); return Number.isFinite(a) ? `${a.toFixed(0)}㎡` : m2; }
function dateOf(t: Txn): string { return `${String(t.거래년도).slice(2)}.${String(t.거래월).padStart(2, '0')}.${String(t.거래일).padStart(2, '0')}`; }
function nameOf(t: Txn): string { return t.명칭 || t.아파트명 || t.건물명 || t.주택유형 || '-'; }
function codeName(code: string): string { return SEOUL_GU.find((g) => g.code === code)?.name ?? code; }

function relTime(ts: number): string {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return '방금';
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}

function buildCode(p: Params): string {
  return `[sense:realty]{type: "${p.type}", deal: "${p.deal}", region_code: "${p.region_code}", start_month: "${p.start_month}", end_month: "${p.end_month}", count_per_month: ${p.count}, project_id: "${PROJECT_ID}"}`;
}

async function runRealty(p: Params): Promise<RealtyResult> {
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: buildCode(p), project_path: '.' }),
  });
  return res.json();
}

// ---------- component ----------
const DEFAULT_PARAMS: Params = {
  region_code: '', type: 'apt', deal: 'trade', // 지역은 미선택으로 시작 — 사용자가 고른다
  start_month: monthsAgo(3), end_month: monthsAgo(0), count: 30,
};

export function RealtyInstrument() {
  const [params, setParams] = useState<Params>(DEFAULT_PARAMS);
  const [result, setResult] = useState<RealtyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [, force] = useState(0); // 상대시간 갱신용
  const [drill, setDrill] = useState<{ t: Txn; trend: Txn[] | null } | null>(null); // 클릭한 거래 1건 + (아파트면) 같은 단지 추이. trend null = 추이 조회 중/해당없음
  const paramsRef = useRef(params);
  paramsRef.current = params; // 항상 최신 다이얼 값을 가리킨다 (조회/드릴이 클로저 staleness에 안 걸리도록)
  const [recents, setRecents] = useState<{ code: string; name: string }[]>(() => loadRecents());

  // 최근 본 지역 갱신: 중복 제거하고 맨 앞으로, 최대 RECENT_MAX개
  const pushRecent = (code: string, name: string) => {
    setRecents((prev) => {
      const next = [{ code, name }, ...prev.filter((r) => r.code !== code)].slice(0, RECENT_MAX);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      return next;
    });
  };

  const fire = useCallback(async (p: Params) => {
    setLoading(true); setDrill(null);
    try {
      const r = await runRealty(p);
      setResult(r);
      const ts = Date.now();
      setFetchedAt(ts);
      // 결정화: 마지막 조회를 굳힌다
      localStorage.setItem(CACHE_KEY, JSON.stringify({ params: p, result: r, ts }));
    } catch (e) {
      setResult({ error: String(e) });
    } finally { setLoading(false); }
  }, []);

  // 안착: 캐시가 있으면 '이미 떠 있는' 상태로 복원. 없으면 지역 미선택 빈 상태로 시작(자동 조회 안 함).
  useEffect(() => {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return;
    try {
      const c = JSON.parse(raw);
      setParams(c.params); setResult(c.result); setFetchedAt(c.ts);
    } catch { /* ignore */ }
  }, []);

  // 상대시간 똑딱
  useEffect(() => { const id = setInterval(() => force((n) => n + 1), 30000); return () => clearInterval(id); }, []);

  const setP = (patch: Partial<Params>) => setParams((prev) => ({ ...prev, ...patch }));

  // 지역 선택: 그 지역으로 즉시 조회 (지역=항해, 즉시 발화 / 나머지 다이얼=정제, 조회 버튼)
  const pickRegion = (code: string, name: string) => {
    const next = { ...paramsRef.current, region_code: code, regionName: name };
    setParams(next);
    pushRecent(code, name);
    fire(next);
  };

  // 행 클릭: 아파트만 '같은 단지 최근 12개월 추이'(리스트에 없는 추가 정보)를 띄운다.
  // 주택/단독·다가구는 행이 곧 그 거래의 전부라, 클릭해도 더 보여줄 게 없으므로 창을 띄우지 않는다.
  const openDrill = async (t: Txn) => {
    const aptName = t.아파트명;
    if (!aptName) return;
    setDrill({ t, trend: null });
    // 도구 제한: 최대 12개월. monthsAgo(11)~monthsAgo(0) = 12개월 (경계 포함)
    const wide: Params = { ...paramsRef.current, start_month: monthsAgo(11), end_month: monthsAgo(0), count: 100 };
    const r = await runRealty(wide);
    const rows = (r.data || []).filter((x) => x.아파트명 === aptName)
      .sort((a, b) => `${a.거래년도}${a.거래월}${a.거래일}`.localeCompare(`${b.거래년도}${b.거래월}${b.거래일}`));
    setDrill((d) => (d && d.t === t) ? { t, trend: rows } : d);  // 그새 다른 행을 누르지 않았을 때만 반영
  };

  const rows = result?.data || [];
  const summary = result?.summary;
  const dealLabel = params.deal === 'trade' ? '매매' : '전월세';

  const headerNote = useMemo(() => {
    if (loading) return '조회 중…';
    if (fetchedAt) return `⟳ ${relTime(fetchedAt)}`;
    return '';
  }, [loading, fetchedAt, result]);

  return (
    <div className="h-full w-full bg-[#F5F1EB] flex items-start justify-center p-6 overflow-auto">
      <div className="w-full max-w-3xl bg-white rounded-2xl shadow-lg border border-stone-200 overflow-hidden">
        {/* 제목줄 */}
        <div className="flex items-center justify-between px-5 py-3 bg-stone-50 border-b border-stone-200">
          <div className="flex items-center gap-2 text-stone-800 font-semibold">
            <span className="text-lg">🏢</span>
            <span>실거래가</span>
            <span className="text-stone-400 font-normal text-sm">· {params.region_code ? `${params.regionName || codeName(params.region_code)} ${dealLabel}` : '지역 미선택'}</span>
          </div>
          <div className="text-xs text-stone-400 tabular-nums">{headerNote}</div>
        </div>

        {/* 다이얼 */}
        <div className="px-5 py-4 space-y-3 border-b border-stone-100">
          {/* 지역: 최근 본 지역 칩(자주 보는 곳이 자연스레 앞에) + 전국 선택기 */}
          <div className="flex flex-wrap items-center gap-1.5">
            {recents.map((r) => (
              <button key={r.code} onClick={() => pickRegion(r.code, r.name)}
                className={`px-2.5 py-1 rounded-full text-sm transition ${params.region_code === r.code ? 'bg-stone-800 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}>
                {r.name}
              </button>
            ))}
            <RegionPicker onPick={pickRegion} />
            {recents.length === 0 && (
              <span className="text-sm text-stone-400">← 전국에서 지역을 고르면 여기 쌓입니다</span>
            )}
          </div>

          {/* 토글 + 기간 */}
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Segmented value={params.type} onChange={(v) => setP({ type: v as RType })}
              options={[{ v: 'apt', l: '아파트' }, { v: 'house', l: '주택' }]} />
            <Segmented value={params.deal} onChange={(v) => setP({ deal: v as Deal })}
              options={[{ v: 'trade', l: '매매' }, { v: 'rent', l: '전월세' }]} />
            <div className="flex items-center gap-1 text-stone-500">
              <input type="month" value={toMonthInput(params.start_month)}
                onChange={(e) => setP({ start_month: fromMonthInput(e.target.value) })}
                className="px-2 py-1 rounded-lg border border-stone-200 bg-white" />
              <span>~</span>
              <input type="month" value={toMonthInput(params.end_month)}
                onChange={(e) => setP({ end_month: fromMonthInput(e.target.value) })}
                className="px-2 py-1 rounded-lg border border-stone-200 bg-white" />
            </div>
            <button onClick={() => fire(paramsRef.current)} disabled={loading || params.region_code.trim().length < 5}
              className="ml-auto px-4 py-1.5 rounded-lg bg-amber-700 text-white font-medium hover:bg-amber-800 disabled:opacity-50">
              {loading ? '…' : '조회'}
            </button>
          </div>
        </div>

        {/* 요약 스트립 */}
        {summary && (
          <div className="flex divide-x divide-stone-100 bg-amber-50/40 text-center">
            <Stat label="거래" value={`${summary.총거래건수 ?? rows.length}건`} />
            <Stat label="평균" value={won(summary.평균가 || '')} />
            <Stat label="최고" value={won(summary.최고가 || '')} />
            <Stat label="최저" value={won(summary.최저가 || '')} />
          </div>
        )}

        {/* 결과 표 */}
        <div className="max-h-[46vh] overflow-auto">
          {!params.region_code && !result ? (
            <div className="p-12 text-center text-stone-400 text-sm">위에서 지역을 골라 실거래가를 확인하세요</div>
          ) : result?.error ? (
            <div className="p-6 text-center text-red-500 text-sm whitespace-pre-wrap">{result.error}</div>
          ) : rows.length === 0 && !loading ? (
            <div className="p-10 text-center text-stone-400 text-sm">해당 기간 거래 없음</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white text-stone-400 text-xs">
                <tr className="border-b border-stone-100">
                  <th className="text-left font-normal px-4 py-2">단지</th>
                  <th className="text-left font-normal px-2 py-2">동</th>
                  <th className="text-right font-normal px-2 py-2">면적</th>
                  <th className="text-right font-normal px-2 py-2">거래가</th>
                  <th className="text-right font-normal px-2 py-2">층</th>
                  <th className="text-right font-normal px-2 py-2">건축</th>
                  <th className="text-right font-normal px-4 py-2">날짜</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t, i) => (
                  <tr key={i} onClick={t.아파트명 ? () => openDrill(t) : undefined}
                    className={`border-b border-stone-50 ${t.아파트명 ? 'hover:bg-amber-50 cursor-pointer' : ''}`}>
                    {/* 아파트만 클릭→단지 추이. 주택/단독·다가구는 행이 곧 전부라 클릭 불가 */}
                    <td className="px-4 py-2 text-stone-800 font-medium">{nameOf(t)}</td>
                    <td className="px-2 py-2 text-stone-400">{t.법정동}</td>
                    <td className="px-2 py-2 text-right text-stone-500 tabular-nums">{pyeong(t.면적 || t.전용면적 || '')}</td>
                    <td className="px-2 py-2 text-right text-stone-900 font-semibold tabular-nums">{won(t.거래금액)}</td>
                    <td className="px-2 py-2 text-right text-stone-400 tabular-nums">{t.층}</td>
                    <td className="px-2 py-2 text-right text-stone-400 tabular-nums">{t.건축년도}</td>
                    <td className="px-4 py-2 text-right text-stone-400 tabular-nums">{dateOf(t)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 푸터: IBL 투명성 */}
        <div className="px-5 py-2 bg-stone-50 border-t border-stone-200 text-[11px] text-stone-400 font-mono truncate">
          {buildCode(params)}
        </div>
      </div>

      {/* 같은 단지 최근 12개월 추이 — 리스트에 없는 추가 정보(아파트만 클릭 가능) */}
      {drill && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4" onClick={() => setDrill(null)}>
          <div className="bg-white rounded-2xl shadow-xl border border-stone-200 w-full max-w-md max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-stone-200 flex items-center justify-between">
              <div className="font-semibold text-stone-800">{nameOf(drill.t)} <span className="text-stone-400 font-normal text-sm">· 같은 단지 최근 12개월</span></div>
              <button onClick={() => setDrill(null)} className="text-stone-400 hover:text-stone-600">✕</button>
            </div>
            {drill.trend === null ? (
              <div className="p-8 text-center text-stone-400 text-sm">불러오는 중…</div>
            ) : drill.trend.length === 0 ? (
              <div className="p-8 text-center text-stone-400 text-sm">최근 12개월 거래 없음</div>
            ) : (
              <ul className="divide-y divide-stone-50">
                {drill.trend.map((t, i) => (
                  <li key={i} className="px-5 py-2.5 flex items-center justify-between text-sm">
                    <span className="text-stone-400 tabular-nums">{dateOf(t)}</span>
                    <span className="text-stone-500">{pyeong(t.면적 || t.전용면적 || '')} · {t.층}층</span>
                    <span className="text-stone-900 font-semibold tabular-nums">{won(t.거래금액)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// 전국 지역 선택기: 시/도 드롭다운 + 구/군 검색 (district_codes 액션이 목록 제공)
function RegionPicker({ onPick }: { onPick: (code: string, name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [province, setProvince] = useState('서울');
  const [query, setQuery] = useState('');
  const [list, setList] = useState<{ name: string; code: string }[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    loadDistricts(province).then((l) => { if (alive) { setList(l); setLoading(false); } });
    return () => { alive = false; };
  }, [open, province]);

  const q = query.trim();
  const filtered = q ? list.filter((r) => r.name.includes(q)) : list;

  return (
    <div className="relative inline-block">
      <button onClick={() => setOpen((o) => !o)}
        className="px-2.5 py-1 rounded-full text-sm bg-stone-100 text-stone-600 hover:bg-stone-200 transition">
        전국 ▾
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full mt-1 z-50 w-80 bg-white rounded-xl shadow-xl border border-stone-200 overflow-hidden">
            <div className="p-2 flex gap-2 border-b border-stone-100">
              <select value={province} onChange={(e) => { setProvince(e.target.value); setQuery(''); }}
                className="px-2 py-1 rounded-lg border border-stone-200 text-sm bg-white text-stone-700">
                {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="구/군 검색"
                className="flex-1 px-2 py-1 rounded-lg border border-stone-200 text-sm" autoFocus />
            </div>
            <div className="max-h-64 overflow-auto p-2 flex flex-wrap gap-1.5">
              {loading ? (
                <span className="text-stone-400 text-sm p-2">불러오는 중…</span>
              ) : filtered.length === 0 ? (
                <span className="text-stone-400 text-sm p-2">검색 결과 없음</span>
              ) : (
                filtered.map((r) => (
                  <button key={r.code} onClick={() => { onPick(r.code, r.name); setOpen(false); setQuery(''); }}
                    className="px-2.5 py-1 rounded-full text-sm bg-stone-100 text-stone-700 hover:bg-stone-800 hover:text-white transition">
                    {r.name}
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Segmented({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { v: string; l: string }[] }) {
  return (
    <div className="inline-flex rounded-lg bg-stone-100 p-0.5">
      {options.map((o) => (
        <button key={o.v} onClick={() => onChange(o.v)}
          className={`px-3 py-1 rounded-md transition ${value === o.v ? 'bg-white text-stone-800 shadow-sm' : 'text-stone-500'}`}>
          {o.l}
        </button>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex-1 py-2.5">
      <div className="text-[11px] text-stone-400">{label}</div>
      <div className="text-sm font-semibold text-stone-800 tabular-nums">{value}</div>
    </div>
  );
}
