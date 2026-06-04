/**
 * BookInstrument.tsx - 도서검색 앱 (앱 모드 계기)
 *
 * 세 소스를 한 표면에서 (같은 IBL 위):
 *   국내(domestic)  [sense:book]            도서관정보나루 — 대출통계·추천
 *   글로벌(global)  [sense:search_books]    Google Books — 원서·요약
 *   고전(classic)   [sense:classic]{op:western} Project Gutenberg — 저작권 만료 원문 읽기
 * 검색은 LLM 없이 IBL 직접 실행(0 토큰). 클릭 상세는 '리스트에 없는 정보'가 있을 때만.
 */
import { useMemo, useState, useRef } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';

type Field = 'keyword' | 'title' | 'author' | 'publisher';
type Source = 'domestic' | 'naver' | 'global' | 'classic';

interface Book {
  bookname: string;
  authors?: string;
  publisher?: string;
  publication_year?: string;
  isbn13?: string;
  bookImageURL?: string;
  bookDtlUrl?: string;
  loan_count?: string;
  class_nm?: string;
  description?: string;
  // global (Google Books)
  categories?: string;
  page_count?: number;
  infoLink?: string;
  // classic (Gutenberg)
  text_url?: string;
  html_url?: string;
  subjects?: string[];
  languages?: string[];
  download_count?: number;
  // naver
  link?: string;
  price?: string;
}
interface SearchResult { count?: number; data?: Book[]; message?: string; error?: string }
interface LoanStat { name?: string; loanCnt?: string }
interface LoanStats { total?: string; by_region?: LoanStat[]; by_age?: LoanStat[]; by_gender?: LoanStat[] }
interface DetailState { book: Book; source: Source; stats: LoanStats | null; recs: Book[] | null }

// ---------- helpers ----------
async function runIBL<T>(code: string): Promise<T> {
  const res = await fetch(IBL_ENDPOINT, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, project_id: PROJECT_ID }),
  });
  return res.json();
}
const esc = (s: string) => s.replace(/"/g, '');
function buildCode(q: string, field: Field, source: Source): string {
  if (source === 'naver') return `[sense:search_naver]{query: "${esc(q)}", type: "book", display: 20, _raw: true}`;
  if (source === 'global') return `[sense:search_books]{query: "${esc(q)}"}`;
  if (source === 'classic') return `[sense:classic]{op: "western", query: "${esc(q)}"}`;
  return `[sense:book]{${field}: "${esc(q)}"}`;
}
// 네이버 isbn 필드는 "10자리 13자리" 형태일 수 있어 13자리만 추출
const isbn13of = (s?: string) => (String(s || '').split(/\s+/).find((t) => t.length === 13) || String(s || ''));
// 응답을 공통 Book[] 형태로 정규화
function normalize(raw: unknown, source: Source): SearchResult {
  const r = raw as Record<string, unknown>;
  if (!r || typeof r !== 'object') return { error: '응답 형식 오류' };
  if (typeof r.error === 'string') return { error: r.error };
  if (source === 'classic') {
    const data: Book[] = ((r.results as Record<string, unknown>[]) || []).map((x) => ({
      bookname: (x.title as string) || '',
      authors: ((x.authors as string[]) || []).join(', '),
      bookImageURL: (x.cover_url as string) || '',
      subjects: (x.subjects as string[]) || [],
      languages: (x.languages as string[]) || [],
      text_url: x.text_url as string,
      html_url: x.html_url as string,
      download_count: x.download_count as number,
    }));
    return { count: r.count as number, data };
  }
  if (source === 'naver') {
    const data: Book[] = ((r.items as Record<string, unknown>[]) || []).map((x) => ({
      bookname: (x.title as string) || '',
      authors: (x.author as string) || '',
      publisher: (x.publisher as string) || '',
      publication_year: String(x.pub_date || '').slice(0, 4),
      isbn13: isbn13of(x.isbn as string),
      bookImageURL: (x.image as string) || '',
      description: (x.snippet as string) || '',
      link: (x.link as string) || '',
      price: (x.price as string) || '',
    }));
    return { count: r.total as number, data };
  }
  return { count: r.count as number, data: (r.data as Book[]) || [] };
}
const num = (s?: string) => { const n = parseInt(String(s || '').replace(/[^0-9]/g, ''), 10); return Number.isFinite(n) ? n : 0; };
const comma = (s?: string | number) => num(String(s ?? '')).toLocaleString();
const cleanAuthors = (s?: string) => (s || '').replace(/^지은이\s*:\s*/, '').trim();

const FIELDS: { v: Field; l: string }[] = [
  { v: 'keyword', l: '전체' }, { v: 'title', l: '제목' }, { v: 'author', l: '저자' }, { v: 'publisher', l: '출판사' },
];
const SOURCES: { v: Source; l: string }[] = [
  { v: 'domestic', l: '정보나루' }, { v: 'naver', l: '네이버' }, { v: 'global', l: '글로벌' }, { v: 'classic', l: '고전' },
];

// ---------- component ----------
export function BookInstrument() {
  const [query, setQuery] = useState('');
  const [field, setField] = useState<Field>('keyword');
  const [source, setSource] = useState<Source>('domestic');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const lastCode = useRef('');

  const search = async () => {
    const q = query.trim();
    if (!q) return;
    const code = buildCode(q, field, source);
    lastCode.current = code;
    setLoading(true); setDetail(null); setResult(null);
    try {
      setResult(normalize(await runIBL(code), source));
    } catch (e) {
      setResult({ error: e instanceof Error ? e.message : '검색 실패' });
    } finally {
      setLoading(false);
    }
  };

  // 클릭 → 상세. 국내만 추가 조회(대출통계+추천); 글로벌/고전은 검색 결과에 이미 상세가 들어있어 그대로 띄운다.
  const openDetail = async (b: Book, src: Source) => {
    setDetail({ book: b, source: src, stats: null, recs: null });
    if (src !== 'domestic' || !b.isbn13) return;
    try {
      const [dr, rr] = await Promise.all([
        runIBL<{ book?: Book & { loan_stats?: LoanStats } }>(`[sense:book]{isbn: "${b.isbn13}", detail: true}`),
        runIBL<{ data?: Book[] }>(`[sense:book]{op: "recommended", isbn13: "${b.isbn13}"}`),
      ]);
      const full = { ...b, ...(dr.book || {}) };
      setDetail((d) => (d && d.book === b) ? { book: full, source: src, stats: dr.book?.loan_stats || null, recs: rr.data || [] } : d);
    } catch {
      setDetail((d) => (d && d.book === b) ? { ...d, stats: null, recs: [] } : d);
    }
  };

  const books = result?.data || [];

  return (
    <div className="h-full w-full bg-[#F5F1EB] flex items-start justify-center p-6 overflow-auto">
      <div className="w-full max-w-3xl bg-white rounded-2xl shadow-lg border border-stone-200 overflow-hidden">
        {/* 제목줄 */}
        <div className="flex items-center gap-2 px-5 py-3 bg-stone-50 border-b border-stone-200 text-stone-800 font-semibold">
          <span className="text-lg">📚</span><span>도서검색</span>
          <span className="text-stone-400 font-normal text-sm">· {source === 'domestic' ? '도서관정보나루' : source === 'naver' ? '네이버 책' : source === 'global' ? 'Google Books' : 'Project Gutenberg'}</span>
          {result?.count != null && <span className="ml-auto text-xs text-stone-400">{comma(result.count)}건</span>}
        </div>

        {/* 검색 다이얼 */}
        <div className="px-5 py-4 space-y-3 border-b border-stone-100">
          <div className="flex flex-wrap items-center gap-2">
            {/* 소스 토글 */}
            <div className="inline-flex rounded-full bg-stone-100 p-0.5">
              {SOURCES.map((s) => (
                <button key={s.v} onClick={() => { setSource(s.v); setResult(null); }}
                  className={`px-3 py-1 rounded-full text-sm transition ${source === s.v ? 'bg-amber-700 text-white' : 'text-stone-500 hover:text-stone-700'}`}>
                  {s.l}
                </button>
              ))}
            </div>
            {/* 검색 필드 토글 — 국내만 (글로벌/고전은 단일 쿼리) */}
            {source === 'domestic' && (
              <div className="inline-flex rounded-full bg-stone-100 p-0.5">
                {FIELDS.map((f) => (
                  <button key={f.v} onClick={() => setField(f.v)}
                    className={`px-3 py-1 rounded-full text-sm transition ${field === f.v ? 'bg-stone-800 text-white' : 'text-stone-500 hover:text-stone-700'}`}>
                    {f.l}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <input value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !loading) search(); }}
              placeholder={source === 'naver' ? '책 제목·저자  예) 한강' : source === 'global' ? '원서·해외 도서  예) sapiens' : source === 'classic' ? '서양 고전  예) sherlock, austen' : field === 'author' ? '저자명  예) 한강' : field === 'publisher' ? '출판사명' : field === 'title' ? '책 제목' : '제목·저자·출판사'}
              className="flex-1 px-4 py-2.5 rounded-xl border border-stone-300 bg-white text-stone-800 text-sm focus:outline-none focus:ring-2 focus:ring-stone-400" />
            <button onClick={search} disabled={loading || !query.trim()}
              className="px-5 py-2.5 rounded-xl bg-amber-700 text-white font-medium hover:bg-amber-800 disabled:opacity-50">
              {loading ? '…' : '검색'}
            </button>
          </div>
        </div>

        {/* 결과 리스트 */}
        <div className="max-h-[52vh] overflow-auto">
          {!result ? (
            <div className="p-12 text-center text-stone-400 text-sm">검색어를 입력해 책을 찾아보세요</div>
          ) : result.error ? (
            <div className="p-6 text-center text-red-500 text-sm whitespace-pre-wrap">{result.error}</div>
          ) : books.length === 0 && !loading ? (
            <div className="p-10 text-center text-stone-400 text-sm">검색 결과 없음</div>
          ) : (
            <ul className="divide-y divide-stone-50">
              {books.map((b, i) => (
                <li key={b.isbn13 || i} onClick={() => openDetail(b, source)}
                  className="flex gap-3 px-5 py-3 hover:bg-amber-50 cursor-pointer">
                  <Cover url={b.bookImageURL} className="w-12 h-16 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-stone-800 font-medium truncate">{b.bookname}</div>
                    <div className="text-sm text-stone-500 truncate">{cleanAuthors(b.authors)}</div>
                    <div className="text-xs text-stone-400 truncate">{[b.publisher, b.publication_year].filter(Boolean).join(' · ')}</div>
                  </div>
                  {b.loan_count != null ? (
                    <Metric value={comma(b.loan_count)} label="대출" />
                  ) : b.download_count != null ? (
                    <Metric value={comma(b.download_count)} label="내려받기" />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* IBL 투명성 푸터 */}
        <div className="px-5 py-2 bg-stone-50 border-t border-stone-200 text-[11px] text-stone-400 font-mono truncate">
          {lastCode.current || buildCode(query || '검색어', field, source)}
        </div>
      </div>

      {detail && <BookDetail d={detail} onClose={() => setDetail(null)} onPick={(b) => openDetail(b, 'domestic')} />}
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="shrink-0 text-right">
      <div className="text-sm font-semibold text-amber-700 tabular-nums">{value}</div>
      <div className="text-[10px] text-stone-400">{label}</div>
    </div>
  );
}

// 표지 (없으면 회색 책 자리)
function Cover({ url, className }: { url?: string; className?: string }) {
  const [ok, setOk] = useState(true);
  if (!url || !ok) {
    return <div className={`${className} rounded bg-stone-100 flex items-center justify-center text-stone-300 text-lg`}>📖</div>;
  }
  return <img src={url} alt="" onError={() => setOk(false)} className={`${className} rounded object-cover bg-stone-100`} />;
}

// 상세: 소스별로 '리스트에 없는 정보'만
function BookDetail({ d, onClose, onPick }: { d: DetailState; onClose: () => void; onPick: (b: Book) => void }) {
  const { book, source, stats, recs } = d;
  const ageMax = useMemo(() => Math.max(1, ...(stats?.by_age || []).map((a) => num(a.loanCnt))), [stats]);
  const loading = source === 'domestic' && stats === null && recs === null;

  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl border border-stone-200 w-full max-w-lg max-h-[85vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        {/* 헤더 */}
        <div className="flex items-start gap-3 px-5 py-4 border-b border-stone-100">
          <Cover url={book.bookImageURL} className="w-16 h-24 shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-stone-800">{book.bookname}</div>
            <div className="text-sm text-stone-500">{cleanAuthors(book.authors)}</div>
            <div className="text-xs text-stone-400">{[book.publisher, book.publication_year].filter(Boolean).join(' · ')}</div>
            {book.class_nm && <div className="mt-1 inline-block text-[11px] text-stone-500 bg-stone-100 px-1.5 py-0.5 rounded">{book.class_nm}</div>}
          </div>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600">✕</button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-stone-400 text-sm">불러오는 중…</div>
        ) : (
          <div className="px-5 py-4 space-y-5">
            {/* 책소개 (국내 상세 / 글로벌) */}
            {book.description && <p className="text-sm text-stone-600 leading-relaxed">{book.description}</p>}

            {/* 국내: 대출통계 */}
            {source === 'domestic' && stats && (stats.total || (stats.by_age && stats.by_age.length > 0)) && (
              <div>
                <div className="flex items-baseline justify-between mb-2">
                  <span className="text-xs text-stone-400">대출 통계</span>
                  {stats.total && <span className="text-sm text-stone-700">전국 누적 <b className="text-amber-700">{comma(stats.total)}</b>회</span>}
                </div>
                <div className="space-y-1.5">
                  {(stats.by_age || []).map((a, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="w-20 shrink-0 text-stone-500 text-right">{a.name}</span>
                      <div className="flex-1 h-3 rounded bg-stone-100 overflow-hidden">
                        <div className="h-full bg-amber-400" style={{ width: `${(num(a.loanCnt) / ageMax) * 100}%` }} />
                      </div>
                      <span className="w-14 shrink-0 text-stone-500 tabular-nums text-right">{comma(a.loanCnt)}</span>
                    </div>
                  ))}
                </div>
                {stats.by_gender && stats.by_gender.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-stone-400">
                    {stats.by_gender.map((g, i) => <span key={i}>{g.name} {comma(g.loanCnt)}</span>)}
                  </div>
                )}
              </div>
            )}

            {/* 국내: 추천도서 */}
            {source === 'domestic' && recs && recs.length > 0 && (
              <div>
                <div className="text-xs text-stone-400 mb-2">이 책을 빌린 사람들이 함께 본 책</div>
                <div className="flex gap-3 overflow-x-auto pb-1">
                  {recs.map((r, i) => (
                    <button key={r.isbn13 || i} onClick={() => onPick(r)} className="shrink-0 w-20 text-left group">
                      <Cover url={r.bookImageURL} className="w-20 h-28" />
                      <div className="mt-1 text-[11px] text-stone-600 leading-tight line-clamp-2 group-hover:text-stone-900">{r.bookname}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 네이버: 가격 + 네이버 책 링크 */}
            {source === 'naver' && (
              <div className="space-y-2 text-sm">
                {book.price && num(book.price) > 0 && <div className="text-stone-600">가격 <b>{comma(book.price)}</b>원</div>}
                {book.link && (
                  <a href={book.link} target="_blank" rel="noreferrer" className="inline-block text-xs text-amber-700 hover:underline">네이버 책에서 보기 →</a>
                )}
              </div>
            )}

            {/* 글로벌(Google): 카테고리·페이지 + 링크 */}
            {source === 'global' && (
              <div className="space-y-2 text-sm">
                {(book.categories || book.page_count != null) && (
                  <div className="flex flex-wrap gap-x-3 text-xs text-stone-500">
                    {book.categories && <span>분류: {book.categories}</span>}
                    {book.page_count != null && <span>{book.page_count}쪽</span>}
                  </div>
                )}
                {book.infoLink && (
                  <a href={book.infoLink} target="_blank" rel="noreferrer" className="inline-block text-xs text-amber-700 hover:underline">Google Books에서 보기 →</a>
                )}
              </div>
            )}

            {/* 고전(Gutenberg): 주제 + 원문 읽기/내려받기 */}
            {source === 'classic' && (
              <div className="space-y-3">
                {book.subjects && book.subjects.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {book.subjects.slice(0, 6).map((s, i) => (
                      <span key={i} className="text-[11px] text-stone-500 bg-stone-100 px-1.5 py-0.5 rounded">{s}</span>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  {book.html_url && (
                    <a href={book.html_url} target="_blank" rel="noreferrer" className="px-3 py-1.5 rounded-lg bg-amber-700 text-white text-sm hover:bg-amber-800">원문 읽기</a>
                  )}
                  {book.text_url && (
                    <a href={book.text_url} target="_blank" rel="noreferrer" className="px-3 py-1.5 rounded-lg border border-stone-300 text-stone-600 text-sm hover:bg-stone-50">텍스트(.txt)</a>
                  )}
                </div>
                {book.download_count != null && <div className="text-[11px] text-stone-400">누적 내려받기 {comma(book.download_count)}회</div>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
