/**
 * NewspaperInstrument — 신문 "계기(instrument)" (앱 모드)
 *
 * 디자인(제호·섹션·카드 그리드)은 이 컴포넌트에 있고, 내용은 어휘로 채운다:
 * 키워드마다 [sense:search_gnews] 를 불러 섹션으로 배치한다. 앱 = 어휘 조합 + 약간의 코딩.
 * (구 방식: [engines:newspaper] 가 수집+조립+디자인을 한 어휘에 박제 → HTML 파일 생성 후 외부
 *  브라우저로 열기. 그 어휘는 은퇴했고, 디자인은 여기로, 팬아웃(키워드별)은 이 컴포넌트 코드로.)
 *
 * 키워드/제목은 편집 가능(localStorage 결정화).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { iblExecuteApp } from '../lib/instrument';  // 앱모드 IBL 호출 공용 헬퍼(project_id 내장)

const KW_KEY = 'newspaper.keywords';
const TITLE_KEY = 'newspaper.title';

const DEFAULT_KEYWORDS = ['청주', 'AI', '문화', '드라마', '영화', '만화', '세종', '경제', '주식'];
const DEFAULT_TITLE = '청주 데일리';

interface NewsItem { title?: string; meta?: string; summary?: string; url?: string }
interface Section { keyword: string; items: NewsItem[]; error?: boolean }

function loadKeywords(): string[] {
  try {
    const raw = localStorage.getItem(KW_KEY);
    if (raw) { const a = JSON.parse(raw); if (Array.isArray(a) && a.length) return a; }
  } catch { /* ignore */ }
  return DEFAULT_KEYWORDS;
}

const openExternal = (url?: string) => { if (url) window.electron?.openExternal?.(url); };

// [sense:search_gnews] 한 키워드 → items. /ibl/execute 응답을 견고하게 파싱.
async function fetchNews(keyword: string): Promise<NewsItem[]> {
  const result = await iblExecuteApp(`[sense:search_gnews]{query: ${JSON.stringify(keyword)}}`);
  const items = (result as { items?: NewsItem[] } | null)?.items;
  return Array.isArray(items) ? items : [];
}

const todayStr = () => {
  const d = new Date();
  const wd = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${wd})`;
};

export function NewspaperInstrument() {
  const [keywords, setKeywords] = useState<string[]>(loadKeywords);
  const [title, setTitle] = useState<string>(() => localStorage.getItem(TITLE_KEY) || DEFAULT_TITLE);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const date = useMemo(todayStr, []);

  const persistKw = (kw: string[]) => { setKeywords(kw); localStorage.setItem(KW_KEY, JSON.stringify(kw)); };
  const addKeyword = () => {
    const k = draft.trim();
    if (k && !keywords.includes(k)) persistKw([...keywords, k]);
    setDraft('');
  };
  const removeKeyword = (k: string) => persistKw(keywords.filter((x) => x !== k));
  const resetKeywords = () => persistKw(DEFAULT_KEYWORDS);
  const onTitle = (t: string) => { setTitle(t); localStorage.setItem(TITLE_KEY, t); };

  // 키워드마다 search_gnews 팬아웃 → 섹션. (약간의 앱 코드; 언어로 팬아웃하지 않는다.)
  const load = useCallback(async () => {
    if (!keywords.length) { setSections([]); return; }
    setLoading(true); setError(null);
    try {
      const results = await Promise.all(
        keywords.map(async (kw): Promise<Section> => {
          try { return { keyword: kw, items: await fetchNews(kw) }; }
          catch { return { keyword: kw, items: [], error: true }; }
        })
      );
      setSections(results);
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }, [keywords]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="h-full w-full flex flex-col bg-[#f0f2f5] text-stone-800">
      {/* 상단 바: 편집 토글 + 새로고침 */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-stone-200 bg-white/70">
        <div className="text-xs text-stone-400">{loading ? '뉴스 불러오는 중…' : `${keywords.length}개 섹션`}</div>
        <div className="flex items-center gap-2">
          <button onClick={() => setEditing((e) => !e)}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50">
            {editing ? '완료' : '키워드 편집'}
          </button>
          <button onClick={load} disabled={loading}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50 disabled:opacity-40">
            ↻ 새로고침
          </button>
        </div>
      </div>

      {/* 편집 패널 */}
      {editing && (
        <div className="shrink-0 px-4 py-3 border-b border-stone-200 bg-white space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-stone-400 shrink-0">제호</span>
            <input value={title} onChange={(e) => onTitle(e.target.value)} placeholder={DEFAULT_TITLE}
              className="flex-1 px-3 py-1.5 rounded-lg border border-stone-200 text-sm outline-none focus:border-stone-400" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {keywords.map((k) => (
              <span key={k} className="inline-flex items-center gap-1 pl-2.5 pr-1.5 py-1 rounded-full bg-stone-50 border border-stone-200 text-sm">
                {k}
                <button onClick={() => removeKeyword(k)} className="text-stone-300 hover:text-rose-500 leading-none">✕</button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input value={draft} onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
              placeholder="키워드 추가 후 Enter (예: 반도체)"
              className="flex-1 px-3 py-1.5 rounded-lg border border-stone-200 text-sm outline-none focus:border-stone-400" />
            <button onClick={addKeyword} className="px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-50">추가</button>
            <button onClick={resetKeywords} className="px-3 py-1.5 rounded-lg text-sm text-stone-400 hover:text-stone-600 underline">기본값</button>
          </div>
        </div>
      )}

      {/* 신문 본문 */}
      <div className="flex-1 min-h-0 overflow-auto px-4 py-6">
        <div className="max-w-5xl mx-auto bg-white rounded-xl shadow-sm px-8 py-8">
          {/* 제호 */}
          <h1 className="text-center text-4xl font-black tracking-tight text-[#1a1a2e] border-b-4 border-[#1a1a2e] pb-4"
            style={{ fontFamily: "'Noto Serif KR', serif" }}>
            {title || DEFAULT_TITLE}
          </h1>
          <div className="text-center text-sm text-stone-500 mt-3 mb-2">{date}</div>

          {error && <div className="text-center text-rose-500 text-sm py-6">{error}</div>}
          {loading && sections.length === 0 && <div className="text-center text-stone-400 text-sm py-10">뉴스를 불러오는 중…</div>}

          {sections.map((sec) => (
            <section key={sec.keyword} className="mt-9">
              <h2 className="text-2xl font-bold text-[#1a1a2e] border-b-2 border-stone-200 pb-2 mb-4">{sec.keyword}</h2>
              {sec.items.length === 0 ? (
                <div className="text-sm text-stone-400 py-2">{sec.error ? '뉴스를 불러오지 못했습니다.' : '관련 뉴스가 없습니다.'}</div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  {sec.items.map((it, i) => (
                    <article key={i} className="border border-stone-200 rounded-lg p-4 flex flex-col bg-white">
                      <h3 className="text-base font-semibold leading-snug text-[#22223b] mb-1.5">{it.title}</h3>
                      {it.meta && <div className="text-xs text-stone-400 mb-1.5">{it.meta}</div>}
                      {it.summary && <p className="text-sm text-stone-600 leading-relaxed mb-3 flex-1 line-clamp-4">{it.summary}</p>}
                      {it.url && (
                        <button onClick={() => openExternal(it.url)}
                          className="mt-auto self-start text-sm font-semibold text-[#3d5a80] hover:underline">
                          기사 보기 →
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
