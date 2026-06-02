/**
 * CultureInstrument — 문화·공연 "계기(instrument)" (앱 모드)
 *
 * 같은 IBL 위 두 탭:
 *   공연  [sense:performance]{genre, keyword} (KOPIS) + [sense:genres] 장르 다이얼
 *   전시  [sense:exhibit]{keyword} (KCISA)
 * 검색은 LLM 없이 IBL 직접 실행(0 토큰). 포스터/썸네일로 시각적 브라우즈. 마지막 탭은 localStorage에 굳힘.
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml (culture), culture/handler.py
 */
import { useEffect, useMemo, useState, useCallback } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'culture.instrument.tab';

type Tab = 'performance' | 'exhibit';

interface Perf {
  mt20id: string; prfnm: string; prfpdfrom?: string; prfpdto?: string;
  fcltynm?: string; poster?: string; area?: string; genrenm?: string; prfstate?: string;
}
interface Exhibit {
  seq: string; title: string; startDate?: string; endDate?: string;
  place?: string; area?: string; sigungu?: string; thumbnail?: string; realmName?: string;
}
interface Genre { code: string; name: string }
interface IblResp<T> { count?: number; data?: T[]; genres?: Genre[]; error?: string }

async function runIBL<T>(code: string): Promise<IblResp<T>> {
  try {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, project_id: PROJECT_ID }),
    });
    return await res.json();
  } catch {
    return { error: '서버에 연결할 수 없습니다.' };
  }
}
const esc = (s: string) => s.replace(/"/g, '');
// API가 &#39; &amp; 등 HTML 엔티티를 그대로 보내므로 디코드 (Electron 렌더러에 document 존재)
function decode(s?: string): string {
  if (!s) return '';
  const t = document.createElement('textarea');
  t.innerHTML = s;
  return t.value;
}
// 20250701 → 2025.07.01
const fmtDate = (s?: string) => (s && /^\d{8}$/.test(s) ? `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}` : s || '');

export function CultureInstrument() {
  const init = useMemo(() => (localStorage.getItem(CACHE_KEY) as Tab) || 'performance', []);
  const [tab, setTab] = useState<Tab>(init);

  const [genres, setGenres] = useState<Genre[]>([]);
  const [genre, setGenre] = useState('');       // '' = 전체
  const [pQuery, setPQuery] = useState('');
  const [perfs, setPerfs] = useState<Perf[] | null>(null);

  const [eQuery, setEQuery] = useState('');
  const [exhibits, setExhibits] = useState<Exhibit[] | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { localStorage.setItem(CACHE_KEY, tab); }, [tab]);

  // 장르 목록 (다이얼)
  useEffect(() => {
    runIBL<Genre>('[sense:genres]{}').then((r) => { if (r.genres) setGenres(r.genres); });
  }, []);

  const loadPerf = useCallback(async (g: string, q: string) => {
    setLoading(true); setError(null); setPerfs(null);
    const parts = [g ? `genre: "${g}"` : '', q.trim() ? `keyword: "${esc(q.trim())}"` : ''].filter(Boolean).join(', ');
    const r = await runIBL<Perf>(`[sense:performance]{${parts}}`);
    setLoading(false);
    if (r.error) setError(r.error);
    else setPerfs(r.data || []);
  }, []);

  const loadExhibit = useCallback(async (q: string) => {
    setLoading(true); setError(null); setExhibits(null);
    const r = await runIBL<Exhibit>(`[sense:exhibit]{keyword: "${esc(q.trim() || '전시')}"}`);
    setLoading(false);
    if (r.error) setError(r.error);
    else setExhibits(r.data || []);
  }, []);

  // 탭 진입 시 자동 로드
  useEffect(() => {
    if (tab === 'performance' && !perfs) loadPerf(genre, pQuery);
    if (tab === 'exhibit' && !exhibits) loadExhibit(eQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const selectGenre = (g: string) => { setGenre(g); setPQuery(''); loadPerf(g, ''); };

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 탭 */}
      <div className="shrink-0 flex gap-1 px-5 pt-4">
        {([['performance', '공연'], ['exhibit', '전시']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => { setTab(t); setError(null); }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              tab === t ? 'bg-stone-800 text-white' : 'bg-white text-stone-500 border border-stone-200 hover:bg-stone-50'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* 검색/필터 */}
      <div className="shrink-0 px-5 pt-3 pb-2">
        {tab === 'performance' ? (
          <>
            <div className="flex gap-2">
              <input value={pQuery} onChange={(e) => setPQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadPerf(genre, pQuery)}
                placeholder="공연명 검색 (비우면 장르 전체)"
                className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
              <button onClick={() => loadPerf(genre, pQuery)}
                className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              <GenreChip label="전체" active={genre === ''} onClick={() => selectGenre('')} />
              {genres.map((g) => (
                <GenreChip key={g.code} label={g.name} active={genre === g.code} onClick={() => selectGenre(g.code)} />
              ))}
            </div>
          </>
        ) : (
          <div className="flex gap-2">
            <input value={eQuery} onChange={(e) => setEQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadExhibit(eQuery)}
              placeholder="전시·행사 검색 (예: 미술, 국립중앙박물관)"
              className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
            <button onClick={() => loadExhibit(eQuery)}
              className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
          </div>
        )}
      </div>

      {/* 본문 */}
      <div className="flex-1 min-h-0 overflow-auto px-5 pb-6">
        {loading && <div className="py-10 text-center text-stone-400 text-sm">불러오는 중…</div>}
        {error && !loading && <div className="py-6 text-center text-rose-500 text-sm">{error}</div>}

        {tab === 'performance' && perfs && !loading && (
          perfs.length === 0
            ? <Empty />
            : <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-3xl mx-auto">
                {perfs.map((p) => (
                  <Card key={p.mt20id} img={p.poster} title={decode(p.prfnm)}
                    badge={p.prfstate} sub={`${p.genrenm || ''}${p.area ? ' · ' + p.area : ''}`}
                    line={p.fcltynm} date={`${p.prfpdfrom || ''} ~ ${p.prfpdto || ''}`} />
                ))}
              </div>
        )}

        {tab === 'exhibit' && exhibits && !loading && (
          exhibits.length === 0
            ? <Empty />
            : <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-3xl mx-auto">
                {exhibits.map((x) => (
                  <Card key={x.seq} img={x.thumbnail} title={decode(x.title)}
                    badge={x.realmName} sub={`${x.area || ''}${x.sigungu ? ' ' + x.sigungu : ''}`}
                    line={x.place} date={`${fmtDate(x.startDate)} ~ ${fmtDate(x.endDate)}`} />
                ))}
              </div>
        )}
      </div>
    </div>
  );
}

function GenreChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`px-2.5 py-1 rounded-full text-xs border ${
        active ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50'
      }`}>
      {label}
    </button>
  );
}

function Card({ img, title, badge, sub, line, date }: {
  img?: string; title: string; badge?: string; sub?: string; line?: string; date?: string;
}) {
  const [broken, setBroken] = useState(false);
  return (
    <div className="bg-white rounded-2xl border border-stone-200 overflow-hidden flex flex-col">
      <div className="aspect-[3/4] bg-stone-100 relative">
        {img && !broken ? (
          <img src={img} alt={title} onError={() => setBroken(true)}
            className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-3xl text-stone-300">🎭</div>
        )}
        {badge && (
          <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded-md bg-black/55 text-white text-[10px]">{badge}</span>
        )}
      </div>
      <div className="p-2.5 flex-1 flex flex-col gap-0.5">
        <div className="text-sm font-medium leading-snug line-clamp-2">{title}</div>
        {sub && <div className="text-[11px] text-stone-500">{sub}</div>}
        {line && <div className="text-[11px] text-stone-400 truncate">{line}</div>}
        {date && <div className="text-[11px] text-stone-400 mt-0.5">{date}</div>}
      </div>
    </div>
  );
}

function Empty() {
  return <div className="py-16 text-center text-stone-400 text-sm">결과가 없습니다.</div>;
}
