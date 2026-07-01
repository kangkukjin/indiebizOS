/**
 * NewspaperInstrument — 신문 "계기(instrument)" (앱 모드)
 *
 * 키워드별 뉴스를 모아 HTML 신문을 생성([engines:newspaper])하고 브라우저에서 열어 읽는다.
 * 키워드는 편집 가능(localStorage 결정화). 생성은 Google News 수집이라 수십 초 걸릴 수 있다.
 *
 * 출력: { success, file: "<절대경로>.html" } → file:// 로 외부 브라우저에서 연다.
 * 스키마 출처: data/ibl_nodes_src/engines.yaml (newspaper), web/handler.py (generate_newspaper)
 */
import { useMemo, useState } from 'react';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const KW_KEY = 'newspaper.keywords';
const TITLE_KEY = 'newspaper.title';
const LAST_KEY = 'newspaper.lastfile';

const DEFAULT_KEYWORDS = ['청주', 'AI', '문화', '드라마', '영화', '만화', '세종', '경제', '주식'];
const DEFAULT_TITLE = '청주 데일리';

interface NewspaperResult { success?: boolean; file?: string; path?: string; total_news?: number; sections?: number; error?: string; message?: string }

function loadKeywords(): string[] {
  try {
    const raw = localStorage.getItem(KW_KEY);
    if (raw) { const a = JSON.parse(raw); if (Array.isArray(a) && a.length) return a; }
  } catch { /* ignore */ }
  return DEFAULT_KEYWORDS;
}

const openInBrowser = (filepath: string) => {
  if (filepath) window.electron?.openExternal?.('file://' + encodeURI(filepath));
};

export function NewspaperInstrument() {
  const [keywords, setKeywords] = useState<string[]>(loadKeywords);
  const [title, setTitle] = useState<string>(() => localStorage.getItem(TITLE_KEY) || DEFAULT_TITLE);
  const [draft, setDraft] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const lastFile = useMemo(() => localStorage.getItem(LAST_KEY) || '', []);
  const [last, setLast] = useState<string>(lastFile);

  const persistKw = (kw: string[]) => { setKeywords(kw); localStorage.setItem(KW_KEY, JSON.stringify(kw)); };
  const addKeyword = () => {
    const k = draft.trim();
    if (k && !keywords.includes(k)) persistKw([...keywords, k]);
    setDraft('');
  };
  const removeKeyword = (k: string) => persistKw(keywords.filter((x) => x !== k));
  const resetKeywords = () => persistKw(DEFAULT_KEYWORDS);
  const onTitle = (t: string) => { setTitle(t); localStorage.setItem(TITLE_KEY, t); };

  const generate = async () => {
    if (!keywords.length) { setError('키워드를 하나 이상 넣어주세요.'); return; }
    setGenerating(true); setError(null); setInfo(null);
    try {
      const t = (title || DEFAULT_TITLE).replace(/"/g, "'");
      // 신문 = 뉴스 수집(문서 IR 생산) >> 문서 렌더(신문 테마). 같은 IR이 pdf/docx로도 흐름.
      const code = `[engines:newspaper]{keywords: ${JSON.stringify(keywords)}, title: "${t}"} >> [table:document]{theme: "newspaper", format: "html"}`;
      const res = await fetch(IBL_ENDPOINT, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, project_id: PROJECT_ID }),
      });
      const d = await res.json();
      // 합성 결과: final_result=document 출력(file/path), results[0]=newspaper(total_news)
      let doc: NewspaperResult = d?.final_result ?? ((d && typeof d === 'object' && 'result' in d) ? d.result : d);
      if (typeof doc === 'string') { try { doc = JSON.parse(doc); } catch { /* keep */ } }
      let total: number | undefined;
      try {
        let s0 = d?.results?.[0]?.result;
        if (typeof s0 === 'string') s0 = JSON.parse(s0);
        total = s0?.total_news;
      } catch { /* ignore */ }
      const file = doc?.file || doc?.path;
      if (doc?.success && file) {
        localStorage.setItem(LAST_KEY, file);
        setLast(file);
        setInfo(`신문 생성 완료 — 기사 ${total ?? '?'}개. 브라우저에서 엽니다.`);
        openInBrowser(file);
      } else {
        setError(doc?.error || doc?.message || '신문 생성에 실패했습니다.');
      }
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="h-full w-full flex flex-col bg-[#FAFAF8] text-stone-800">
      <div className="flex-1 min-h-0 overflow-auto px-5 py-5">
        <div className="max-w-xl mx-auto space-y-5">
          {/* 제목 */}
          <div>
            <div className="text-xs text-stone-400 mb-1">신문 제목</div>
            <input value={title} onChange={(e) => onTitle(e.target.value)}
              placeholder={DEFAULT_TITLE}
              className="w-full px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
          </div>

          {/* 키워드 편집 */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-xs text-stone-400">키워드 ({keywords.length}) — 섹션별로 뉴스를 모읍니다</div>
              <button onClick={resetKeywords} className="text-[11px] text-stone-400 hover:text-stone-600 underline">기본값</button>
            </div>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {keywords.map((k) => (
                <span key={k} className="inline-flex items-center gap-1 pl-2.5 pr-1.5 py-1 rounded-full bg-white border border-stone-200 text-sm">
                  {k}
                  <button onClick={() => removeKeyword(k)} className="text-stone-300 hover:text-rose-500 leading-none">✕</button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input value={draft} onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
                placeholder="키워드 추가 후 Enter (예: 반도체)"
                className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
              <button onClick={addKeyword} className="px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-50">추가</button>
            </div>
          </div>

          {/* 생성 */}
          <button onClick={generate} disabled={generating || !keywords.length}
            className="w-full px-4 py-3 rounded-xl bg-stone-800 text-white text-sm font-medium hover:bg-stone-700 disabled:opacity-40">
            {generating ? '신문 만드는 중… (수십 초 걸릴 수 있어요)' : '📰 신문 생성'}
          </button>

          {error && <div className="text-center text-rose-500 text-sm">{error}</div>}
          {info && <div className="text-center text-emerald-600 text-sm">{info}</div>}

          {/* 최근 생성본 다시 열기 */}
          {last && !generating && (
            <button onClick={() => openInBrowser(last)}
              className="w-full px-4 py-2 rounded-xl border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-50">
              방금 만든 신문 다시 열기 ↗
            </button>
          )}

          <p className="text-[11px] text-stone-400 leading-relaxed">
            생성된 신문은 HTML 파일로 저장되어 기본 브라우저에서 열립니다. 키워드를 바꾸면 다음 생성부터 반영됩니다.
          </p>
        </div>
      </div>
    </div>
  );
}
