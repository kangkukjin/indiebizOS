/**
 * NewspaperInstrument — 신문 "계기(instrument)" (앱 모드)
 *
 * 디자인(제호·섹션·카드 그리드)은 이 컴포넌트에 있고, 내용은 어휘로 채운다:
 * 키워드마다 [sense:search_gnews] 를 불러 섹션으로 배치한다. 앱 = 어휘 조합 + 약간의 코딩.
 * (구 방식: [engines:newspaper] 가 수집+조립+디자인을 한 어휘에 박제 → HTML 파일 생성 후 외부
 *  브라우저로 열기. 그 어휘는 은퇴했고, 디자인은 여기로, 팬아웃(키워드별)은 이 컴포넌트 코드로.)
 *
 * ★발행 모델: 신문은 열 때마다 재취재하지 않는다. '새로 발행'을 누를 때만 뉴스를 긁어
 *  판(edition)을 만들고, 그 판을 데이터 레이어(outputs/newspaper_current.json, [self:write])에
 *  최신 하나 저장한다. 다음에 열면 저장된 판을 [self:read] 로 그대로 보여준다(재취재 없음).
 *
 * 키워드/제목은 편집 가능(localStorage 결정화) — '다음 판'에 쓸 편집 설정이다.
 */
import { useCallback, useEffect, useState } from 'react';
import { iblExecuteApp } from '../lib/instrument';  // 앱모드 IBL 호출 공용 헬퍼(project_id 내장)

const KW_KEY = 'newspaper.keywords';
const TITLE_KEY = 'newspaper.title';

// 발행된 최신 판(edition)이 사는 곳 — 앱모드 프로젝트 outputs/ (self:write/read 가 project_id 기준 해소).
// 최신 판 하나만 유지: 새로 발행하면 덮어쓴다.
//  · JSON = 데스크톱이 카드 그리드로 다시 그리기 위한 구조화 판(이 컴포넌트 전용).
//  · MD   = 폰/원격 뷰어(정기보고식)가 읽고, 파일로 공유하기 위한 사람이 읽는 판.
//    둘 다 '새로 발행' 시 같은 sections 에서 파생 — PC 가 만들고 폰은 MD 를 보여주기만 한다.
const EDITION_PATH = 'outputs/newspaper_current.json';
const MD_PATH = 'outputs/newspaper_current.md';
// 공유용 자기완결 HTML — 폰 뷰어의 "폰에 저장·공유" 버튼이 읽어 카톡 등으로 보낸다(친구가 브라우저로 바로 열람).
const HTML_PATH = 'outputs/newspaper_current.html';

const DEFAULT_KEYWORDS = ['청주', 'AI', '문화', '드라마', '영화', '만화', '세종', '경제', '주식'];
const DEFAULT_TITLE = '청주 데일리';

interface NewsItem { title?: string; meta?: string; summary?: string; url?: string; role?: string; why?: string }

// 편집장 역할 배지 — hot(널리 다룸)/delta(관점 코어 기준 새 정보)/surface(지배 프레임과 결이 다름)
const ROLE_BADGE: Record<string, { icon: string; label: string; cls: string }> = {
  hot:     { icon: '🔥', label: '많이 다룸',   cls: 'bg-orange-50 text-orange-600' },
  delta:   { icon: '💡', label: '관점에 새 것', cls: 'bg-sky-50 text-sky-700' },
  surface: { icon: '⚡', label: '결이 다름',   cls: 'bg-violet-50 text-violet-700' },
};
function RoleBadge({ it }: { it: NewsItem }) {
  const b = it.role ? ROLE_BADGE[it.role] : undefined;
  if (!b) return null;
  return (
    <span title={it.why || b.label}
      className={`self-start text-[11px] px-1.5 py-0.5 rounded mb-1 cursor-help ${b.cls}`}>
      {b.icon} {b.label}
    </span>
  );
}
interface Section { keyword: string; items: NewsItem[]; error?: boolean }
// 저장되는 판. sections=스냅샷 내용, dateLabel/issuedAt=발행 시점. title/keywords 는 발행 당시 설정 사본.
// perspective=이 판이 관점 코어(개인화) 반영으로 편성됐는지 — silent 폴백을 사용자에게 노출(감독 가능성).
interface Edition { title: string; keywords: string[]; sections: Section[]; dateLabel: string; issuedAt: string; perspective?: boolean }

// 편집장이 관점 코어(vault/위키/관점 코어.md)를 반영했는지 — curate 응답의 perspective 필드.
// 모듈 변수로 최근 값을 기억: 발행/편집 풀 로드 직후의 setState 렌더에서 읽힌다.
let PERSPECTIVE_ON: boolean | undefined;
function notePerspective(result: unknown) {
  const p = (result as { perspective?: boolean } | null)?.perspective;
  if (typeof p === 'boolean') PERSPECTIVE_ON = p;
}

// 저장된 최신 판을 읽어온다. 없으면(파일 부재 → "Error: ..." 문자열) null.
async function loadEdition(): Promise<Edition | null> {
  try {
    const r = await iblExecuteApp(`[self:read]{path: ${JSON.stringify(EDITION_PATH)}}`);
    if (r && typeof r === 'object' && Array.isArray((r as Edition).sections)) return r as Edition;
  } catch { /* 파일 없음/파싱 실패 → 저장된 판 없음 */ }
  return null;
}

// 판을 데이터 레이어에 저장(최신 하나 덮어쓰기). content 는 JSON 문자열(이중 stringify 로 IBL 문자열 리터럴).
async function saveEdition(ed: Edition): Promise<void> {
  const content = JSON.stringify(ed);
  await iblExecuteApp(`[self:write]{path: ${JSON.stringify(EDITION_PATH)}, content: ${JSON.stringify(content)}}`);
}

// 폰/원격 뷰어(정기보고식)가 읽을 마크다운 판을 PC 에 쓴다 — sections → 어휘 파이프(table:document
// 마크다운 emitter)로 사람이 읽는 문서 텍스트를 얻어 self:write. 파생물이라 실패해도 발행 자체는
// 유지(best-effort)하되, 성공 여부를 반환해 상단바에 부분 실패를 노출한다(조용한 삼킴 금지).
async function saveMarkdownFile(title: string, dateLabel: string, sections: Section[]): Promise<boolean> {
  try {
    const items = sections.flatMap((sec) => sec.items.map((it) => ({ ...it, section: sec.keyword })));
    const doc = (await iblExecuteApp(
      `[table:document]{format: "markdown", title: ${JSON.stringify(title)}, ` +
      `meta: ${JSON.stringify(dateLabel)}, group_by: "section", items: ${JSON.stringify(items)}}`
    )) as { markdown?: string } | null;
    const md = doc?.markdown;
    if (typeof md === 'string' && md) {
      await iblExecuteApp(`[self:write]{path: ${JSON.stringify(MD_PATH)}, content: ${JSON.stringify(md)}}`);
      return true;
    }
  } catch { /* 파생 파일 실패는 발행을 막지 않는다 */ }
  return false;
}

// 마스트헤드(제호 아래 한 줄)에 얹을 날씨·지수 — 이미 가진 어휘로 best-effort 수집.
// 도시는 오디오브리핑과 같은 설정(localStorage 'audioBriefing.city')을 공유, 없으면 '청주'.
// 실패는 조용히 생략(신문 발행은 뉴스가 본질 — 마스트헤드 장식이 없어도 발행은 진행).
interface MastheadData { weather?: string; index?: string }
async function fetchMasthead(): Promise<MastheadData> {
  let city = '청주';
  try { city = localStorage.getItem('audioBriefing.city') || '청주'; } catch { /* ignore */ }
  const [wRes, kRes] = await Promise.all([
    iblExecuteApp(`[sense:weather]{city: ${JSON.stringify(city)}}`).catch(() => null),
    iblExecuteApp(`[sense:stock]{op: "quote", ticker: "^KS11"}`).catch(() => null),
  ]);
  const md: MastheadData = {};
  const w = (wRes as { current?: { temp?: number; condition?: string } } | null)?.current;
  if (w && w.temp != null) md.weather = `${city} ${w.condition || ''} ${Math.round(w.temp)}°`.replace(/\s+/g, ' ').trim();
  const k = (kRes as { data?: { current_price?: number; change_percent?: number } } | null)?.data;
  if (k && k.current_price != null) {
    const pct = k.change_percent ?? 0;
    const arrow = pct > 0 ? '▲' : pct < 0 ? '▼' : '·';
    md.index = `코스피 ${k.current_price.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${arrow}${Math.abs(pct).toFixed(2)}%`;
  }
  return md;
}

// 공유용 자기완결 HTML 판을 PC 에 쓴다 — 폰 뷰어의 공유 버튼이 이 파일을 카톡 등으로 보낸다(친구=브라우저 열람).
async function saveHtmlFile(title: string, dateLabel: string, sections: Section[]): Promise<boolean> {
  try {
    const masthead = await fetchMasthead().catch(() => ({} as MastheadData));
    const html = buildNewspaperHtml(title, dateLabel, sections, masthead);
    await iblExecuteApp(`[self:write]{path: ${JSON.stringify(HTML_PATH)}, content: ${JSON.stringify(html)}}`);
    return true;
  } catch { /* 파생 파일 실패는 발행을 막지 않는다 */ }
  return false;
}

function loadKeywords(): string[] {
  try {
    const raw = localStorage.getItem(KW_KEY);
    if (raw) { const a = JSON.parse(raw); if (Array.isArray(a) && a.length) return a; }
  } catch { /* ignore */ }
  return DEFAULT_KEYWORDS;
}

const openExternal = (url?: string) => { if (url) window.electron?.openExternal?.(url); };

// [sense:search_gnews] 한 키워드 → items. /ibl/execute 응답을 견고하게 파싱.
// curate: 경량 AI 섹션 편집자가 오버페치 pool에서 같은 사건 중복을 묶고 뉴스가치 순 7개 선별.
async function fetchNews(keyword: string): Promise<NewsItem[]> {
  const result = await iblExecuteApp(`[sense:search_gnews]{query: ${JSON.stringify(keyword)}, curate: 7}`);
  notePerspective(result);
  const items = (result as { items?: NewsItem[] } | null)?.items;
  return Array.isArray(items) ? items : [];
}

// 오늘의 핫토픽 — 키워드 없는 톱 헤드라인을 경량 AI가 군집·랭킹(가장 많이 다뤄진 사건 = 핫).
const HOT_KEYWORD = '🔥 오늘의 핫토픽';
async function fetchHotTopics(): Promise<NewsItem[]> {
  const result = await iblExecuteApp(`[sense:search_gnews]{headlines: true, curate: 7}`);
  notePerspective(result);
  const items = (result as { items?: NewsItem[] } | null)?.items;
  return Array.isArray(items) ? items : [];
}

// ── 편집신문(사용자 큐레이션) ─────────────────────────────────
// 자동발간은 섹션당 N=7 을 그대로 싣지만, 편집신문은 사용자가 마음에 안 드는 기사를 빼면
// '다른 뉴스'로 빈칸을 메워야 한다. 그러려면 섹션마다 N 보다 큰 후보 풀(pool)을 미리 확보해
// 두고, 화면엔 앞 N 개(selected)만 보인다 — 검색 브라우저를 섹션마다 반복하는 셈.
const SECTION_SIZE = 7;    // 최종 신문에 실리는 섹션당 기사 수(자동발간과 동일)
// 중복 판정 키: 링크 우선, 없으면 제목.
const itemKey = (it: NewsItem) => it.url || it.title || '';

// 편집 풀 = 편집장 픽(role/why 부착, 앞줄) + 안 뽑힌 나머지(pool, 대체 후보) —
// EditFlow의 '앞 N개=selected' 논리가 그대로 편집장 편성을 첫 화면으로 만든다.
function mergePicksAndPool(result: unknown): NewsItem[] {
  notePerspective(result);
  const r = result as { items?: NewsItem[]; pool?: NewsItem[] } | null;
  const picks = Array.isArray(r?.items) ? r!.items! : [];
  const rest = Array.isArray(r?.pool) ? r!.pool! : [];
  return [...picks, ...rest];
}
async function fetchNewsPool(keyword: string): Promise<NewsItem[]> {
  const result = await iblExecuteApp(`[sense:search_gnews]{query: ${JSON.stringify(keyword)}, curate: ${SECTION_SIZE}}`);
  return mergePicksAndPool(result);
}
async function fetchHotTopicsPool(): Promise<NewsItem[]> {
  const result = await iblExecuteApp(`[sense:search_gnews]{headlines: true, curate: ${SECTION_SIZE}}`);
  return mergePicksAndPool(result);
}

// ── 자기완결 HTML 내보내기(친구에게 파일로 공유) ─────────────────
const esc = (s?: string) =>
  (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));

function buildNewspaperHtml(title: string, date: string, sections: Section[], masthead?: MastheadData): string {
  // 기사 한 건. lead=1면 톱기사(큰 제목 + 드롭캡).
  const article = (it: NewsItem, lead = false): string => {
    const head = it.url
      ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>`
      : esc(it.title);
    return `<article class="art${lead ? ' lead' : ''}">
        <h3>${head}</h3>
        ${it.meta ? `<div class="meta">${esc(it.meta)}</div>` : ''}
        ${it.summary ? `<p>${esc(it.summary)}</p>` : ''}
      </article>`;
  };

  // 섹션. first=첫 섹션이면 첫 기사를 1면 리드(전폭)로 올리고 나머지는 컬럼 흐름.
  const sectionHtml = (sec: Section, first: boolean): string => {
    const items = sec.items || [];
    const rubric = `<h2 class="rubric"><span>${esc(sec.keyword)}</span></h2>`;
    if (!items.length) {
      return `<section class="sec">${rubric}<div class="empty">관련 뉴스가 없습니다.</div></section>`;
    }
    let body: string;
    if (first) {
      const [lead, ...rest] = items;
      body = article(lead, true) + (rest.length ? `<div class="cols">${rest.map((it) => article(it)).join('')}</div>` : '');
    } else {
      body = `<div class="cols">${items.map((it) => article(it)).join('')}</div>`;
    }
    return `<section class="sec">${rubric}${body}</section>`;
  };

  const strip = [esc(date), masthead?.weather && esc(masthead.weather), masthead?.index && esc(masthead.index)]
    .filter(Boolean)
    .join('&nbsp;&nbsp;·&nbsp;&nbsp;');
  const sectionsHtml = sections.map((sec, i) => sectionHtml(sec, i === 0)).join('\n');

  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>${esc(title)} — ${esc(date)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>
  :root { color-scheme:light; --paper:#fbf9f3; --ink:#1b1b1b; --muted:#6b675e; --rule:#1b1b1b; --hair:#cfc9ba; --accent:#7a1f1f; }
  * { box-sizing:border-box; }
  body { margin:0; background:#e9e4d8; color:var(--ink); line-height:1.6;
    font-family:'Noto Serif KR',Georgia,'Times New Roman',serif; -webkit-font-smoothing:antialiased; }
  .paper { max-width:1060px; margin:28px auto; background:var(--paper); padding:44px 52px 60px;
    box-shadow:0 2px 24px rgba(0,0,0,.14); border:1px solid #d8d2c4; }
  /* 마스트헤드 */
  .dateline { display:flex; justify-content:space-between; align-items:center;
    font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted);
    border-bottom:1px solid var(--hair); padding-bottom:8px; }
  .nameplate { text-align:center; font-weight:900; letter-spacing:-.02em; color:#111;
    font-size:clamp(2.6rem,7vw,4.4rem); line-height:1; margin:.28em 0 .14em; }
  .strip { text-align:center; font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.82rem; letter-spacing:.03em; color:var(--muted);
    border-top:3px double var(--rule); border-bottom:3px double var(--rule); padding:8px 0; margin-top:4px; }
  /* 섹션 루브릭(가로줄 관통 라벨) */
  .sec { margin-top:34px; }
  .rubric { display:flex; align-items:center; gap:16px; margin:0 0 18px; color:var(--accent);
    font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.9rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }
  .rubric::before, .rubric::after { content:''; flex:1; border-top:1.5px solid var(--rule); }
  .rubric span { white-space:nowrap; }
  /* 기사 컬럼 흐름 */
  .cols { columns:300px 3; column-gap:30px; }
  .art { break-inside:avoid; margin:0 0 20px; padding-bottom:16px; border-bottom:1px solid var(--hair); }
  .art h3 { font-size:1.05rem; font-weight:700; line-height:1.35; margin:0 0 6px; }
  .art h3 a { color:var(--ink); text-decoration:none; }
  .art h3 a:hover { text-decoration:underline; }
  .art .meta { font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin-bottom:6px; }
  .art p { font-size:.92rem; color:#33322e; margin:0; text-align:justify; hyphens:auto; }
  /* 1면 리드 */
  .lead { border-bottom:2px solid var(--rule); padding-bottom:20px; margin-bottom:22px; }
  .lead h3 { font-size:1.9rem; font-weight:900; line-height:1.18; letter-spacing:-.01em; }
  .lead p { font-size:1.02rem; color:#26251f; }
  .lead p::first-letter { float:left; font-size:3.1em; line-height:.72; font-weight:900; padding:.02em .1em 0 0; color:var(--accent); }
  .empty { color:var(--muted); font-style:italic; }
  footer { margin-top:52px; border-top:1px solid var(--hair); padding-top:18px; text-align:center; color:var(--muted);
    font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif; font-size:.72rem; letter-spacing:.1em; }
  @media (max-width:600px) {
    .paper { padding:26px 20px 40px; margin:0; border:none; }
    .cols { columns:1; }
    .lead h3 { font-size:1.5rem; }
  }
  @media print {
    body { background:#fff; }
    .paper { box-shadow:none; border:none; margin:0; max-width:none; padding:0; }
    .art h3 a { color:#000; }
    @page { margin:15mm; }
  }
</style></head>
<body><main class="paper">
  <div class="dateline"><span>IndieBiz OS</span><span>나만의 신문</span></div>
  <h1 class="nameplate">${esc(title)}</h1>
  <div class="strip">${strip}</div>
  ${sectionsHtml}
  <footer>IndieBiz OS · 나만의 신문 · 자동 편집 지면</footer>
</main></body></html>`;
}

const todayStr = () => {
  const d = new Date();
  const wd = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${wd})`;
};

// 발행 시각을 짧게 — 상단 바 신선도 표시용.
const whenLabel = (iso: string | null): string | null => {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return null; }
};

// 편집 중인 한 섹션: pool=후보 풀(>N), selected=현재 화면 N개, rejected=사용자가 뺀 기사 키(다시 안 나옴).
interface EditSection { keyword: string; pool: NewsItem[]; selected: NewsItem[]; rejected: string[]; error?: boolean }

// pool 앞에서부터 중복 없이 size 개를 고른다(이미 있는/거부된 키 제외).
function pickFromPool(pool: NewsItem[], size: number, exclude: Set<string>): NewsItem[] {
  const out: NewsItem[] = [];
  for (const it of pool) {
    const k = itemKey(it);
    if (!k || exclude.has(k)) continue;
    out.push(it);
    exclude.add(k);
    if (out.length >= size) break;
  }
  return out;
}

// 편집신문 마법사 — 섹션마다 후보를 보여주고, 사용자가 뺀 자리를 중복 없이 리필, OK 시 다음 섹션.
// 마지막 섹션 확정 시 onDone(final) 으로 완성 섹션을 부모에 넘긴다(저장·렌더는 부모의 자동발간 경로 재사용).
function EditFlow({ keywords, onDone, onCancel }: {
  keywords: string[];
  onDone: (sections: Section[]) => void;
  onCancel: () => void;
}) {
  const [secs, setSecs] = useState<EditSection[] | null>(null);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // 진입 시 모든 섹션의 후보 풀을 한 번에 팬아웃(핫토픽 + 키워드들).
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true); setErr(null);
      try {
        const [hot, kwPools] = await Promise.all([
          fetchHotTopicsPool().catch(() => [] as NewsItem[]),
          Promise.all(keywords.map(async (kw): Promise<{ kw: string; pool: NewsItem[]; error?: boolean }> => {
            try { return { kw, pool: await fetchNewsPool(kw) }; }
            catch { return { kw, pool: [], error: true }; }
          })),
        ]);
        if (!alive) return;
        const mk = (keyword: string, pool: NewsItem[], error?: boolean): EditSection => {
          const used = new Set<string>();
          return { keyword, pool, selected: pickFromPool(pool, SECTION_SIZE, used), rejected: [], error };
        };
        const built: EditSection[] = [];
        if (hot.length) built.push(mk(HOT_KEYWORD, hot));
        for (const { kw, pool, error } of kwPools) built.push(mk(kw, pool, error));
        if (!built.length) { setErr('불러올 섹션이 없습니다. 키워드를 확인하세요.'); }
        setSecs(built);
      } catch { if (alive) setErr('뉴스를 불러오지 못했습니다.'); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [keywords]);

  // 기사 제거 → 거부 목록에 넣고, 풀에서 아직 안 쓰고 안 거부된 다음 기사로 빈칸 보충(중복 없음).
  const removeItem = (idx: number) => {
    setSecs((prev) => {
      if (!prev) return prev;
      const next = prev.slice();
      const s = next[step];
      const removed = s.selected[idx];
      const rejected = removed ? [...s.rejected, itemKey(removed)] : s.rejected;
      const selected = s.selected.filter((_, i) => i !== idx);
      const exclude = new Set<string>([...selected.map(itemKey), ...rejected]);
      const fill = pickFromPool(s.pool, 1, exclude);
      next[step] = { ...s, selected: [...selected, ...fill], rejected };
      return next;
    });
  };

  const confirmSection = () => {
    if (!secs) return;
    if (step + 1 < secs.length) { setStep((n) => n + 1); return; }
    onDone(secs.map((s) => ({ keyword: s.keyword, items: s.selected, error: s.error })));
  };

  const cur = secs?.[step];
  const total = secs?.length ?? 0;
  const poolLeft = cur ? cur.pool.length - cur.selected.length - cur.rejected.length : 0;

  return (
    <div className="flex-1 min-h-0 overflow-auto px-4 py-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div className="text-sm text-stone-500">
            {loading ? '후보 뉴스를 모으는 중…'
              : total ? <>섹션 <b className="text-stone-800">{step + 1}</b> / {total} — 마음에 안 드는 기사를 빼면 다른 뉴스로 채워집니다.</>
              : ''}
          </div>
          <button onClick={onCancel}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-500 hover:bg-stone-50">
            편집 취소
          </button>
        </div>

        {err && <div className="text-center text-rose-500 text-sm py-6">{err}</div>}
        {loading && <div className="text-center text-stone-400 text-sm py-16">후보 뉴스를 모으는 중…</div>}

        {!loading && cur && (
          <div className="bg-white rounded-xl shadow-sm px-6 py-6">
            <h2 className="text-2xl font-bold text-[#1a1a2e] border-b-2 border-stone-200 pb-2 mb-1">{cur.keyword}</h2>
            <div className="text-xs text-stone-400 mb-4">
              {cur.selected.length}건 선택됨{poolLeft > 0 ? ` · 대체 후보 ${poolLeft}건 남음` : ' · 대체 후보 소진'}
              {PERSPECTIVE_ON === true ? ' · 💡 관점 편성' : PERSPECTIVE_ON === false ? ' · 일반 편성(관점 코어 없음)' : ''}
            </div>
            {cur.selected.length === 0 ? (
              <div className="text-sm text-stone-400 py-2">{cur.error ? '뉴스를 불러오지 못했습니다.' : '남은 후보가 없습니다.'}</div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {cur.selected.map((it, i) => (
                  <article key={itemKey(it) || i} className="relative border border-stone-200 rounded-lg p-4 pr-9 flex flex-col bg-white">
                    <button onClick={() => removeItem(i)} title="이 기사 빼기"
                      className="absolute top-2 right-2 w-6 h-6 rounded-full text-stone-300 hover:text-white hover:bg-rose-500 leading-none flex items-center justify-center">✕</button>
                    <RoleBadge it={it} />
                    <h3 className="text-base font-semibold leading-snug text-[#22223b] mb-1.5">{it.title}</h3>
                    {it.meta && <div className="text-xs text-stone-400 mb-1.5">{it.meta}</div>}
                    {it.summary && <p className="text-sm text-stone-600 leading-relaxed mb-3 flex-1 line-clamp-4">{it.summary}</p>}
                    {it.url && (
                      <button onClick={() => openExternal(it.url)}
                        className="mt-auto self-start text-sm font-semibold text-[#3d5a80] hover:underline">기사 보기 →</button>
                    )}
                  </article>
                ))}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 mt-6 pt-4 border-t border-stone-100">
              <button onClick={confirmSection}
                className="text-sm px-4 py-2 rounded-lg border border-stone-800 bg-[#1a1a2e] text-white hover:opacity-90">
                {step + 1 < total ? '이 섹션 확정 · 다음 →' : '✓ 편집 완료 · 신문 발행'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function NewspaperInstrument() {
  const [keywords, setKeywords] = useState<string[]>(loadKeywords);
  const [title, setTitle] = useState<string>(() => localStorage.getItem(TITLE_KEY) || DEFAULT_TITLE);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [editFlow, setEditFlow] = useState(false);  // 편집신문 마법사 활성 여부
  // date=마스트헤드에 찍히는 발행일(스냅샷). 새로 발행하면 오늘로, 저장된 판을 열면 그 판의 발행일.
  const [date, setDate] = useState<string>(todayStr);
  const [issuedAt, setIssuedAt] = useState<string | null>(null);
  const [perspective, setPerspective] = useState<boolean | null>(null);  // 이 판이 관점 반영인지(#5)
  const [deriveWarn, setDeriveWarn] = useState<string | null>(null);     // 파생 파일 부분 실패(#7)

  const persistKw = (kw: string[]) => { setKeywords(kw); localStorage.setItem(KW_KEY, JSON.stringify(kw)); };
  const addKeyword = () => {
    const k = draft.trim();
    if (k && !keywords.includes(k)) persistKw([...keywords, k]);
    setDraft('');
  };
  const removeKeyword = (k: string) => persistKw(keywords.filter((x) => x !== k));
  const resetKeywords = () => persistKw(DEFAULT_KEYWORDS);
  const onTitle = (t: string) => { setTitle(t); localStorage.setItem(TITLE_KEY, t); };

  // 자기완결 HTML 한 파일로 저장 → 친구에게 첨부 공유(백엔드·호스팅 불필요, Blob 다운로드).
  const exportHtml = () => {
    const html = buildNewspaperHtml(title || DEFAULT_TITLE, date, sections);
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const d = new Date();
    const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
    const safe = (title || DEFAULT_TITLE).replace(/[^\w가-힣]+/g, '_');
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safe}_${stamp}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  // Nostr(NIP-23) 공개 발행 → njump 링크. 친구에게 링크 하나로 공유(서버·계정 불필요).
  const publishLink = async () => {
    if (!sections.length) return;
    setPublishing(true); setShareUrl(null); setError(null);
    try {
      // 섹션 → 통화 items(섹션 태그) → [table:document] 마크다운 → [others:publish] 파이프.
      // 마크다운 직렬화가 어휘(table:document)라 원격/폰/스케줄러도 같은 경로를 쓴다.
      const items = sections.flatMap((sec) => sec.items.map((it) => ({ ...it, section: sec.keyword })));
      const d = new Date();
      const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
      const code =
        `[table:document]{format: "markdown", title: ${JSON.stringify(title || DEFAULT_TITLE)}, ` +
        `meta: ${JSON.stringify(date)}, group_by: "section", items: ${JSON.stringify(items)}} ` +
        `>> [others:publish]{title: ${JSON.stringify(`${title || DEFAULT_TITLE} · ${date}`)}, slug: ${JSON.stringify(`newspaper-${stamp}`)}}`;
      const result = (await iblExecuteApp(code)) as { url?: string; error?: string } | null;
      if (result?.url) setShareUrl(result.url);
      else setError(result?.error || '발행에 실패했습니다. Nostr 설정을 확인하세요.');
    } catch {
      setError('발행 중 오류가 발생했습니다.');
    } finally {
      setPublishing(false);
    }
  };

  const copyShare = () => { if (shareUrl) navigator.clipboard?.writeText(shareUrl); };

  // 완성된 섹션들을 최신 판으로 확정·저장 — 자동발간과 편집신문이 공유하는 저장 경로.
  //  JSON(데스크톱 카드 재렌더) + MD(폰/원격 뷰어·공유) + HTML(폰 공유) 셋 다 같은 sections 에서 파생.
  const commitEdition = useCallback(async (all: Section[]) => {
    const nowLabel = todayStr();
    const iso = new Date().toISOString();
    setSections(all);
    setDate(nowLabel);
    setIssuedAt(iso);
    setPerspective(PERSPECTIVE_ON ?? null);
    const ttl = title || DEFAULT_TITLE;
    await saveEdition({ title: ttl, keywords, sections: all, dateLabel: nowLabel, issuedAt: iso, perspective: PERSPECTIVE_ON });
    const mdOk = await saveMarkdownFile(ttl, nowLabel, all);   // 폰 뷰어 표시용
    const htmlOk = await saveHtmlFile(ttl, nowLabel, all);     // 폰 공유용(카톡 등)
    const fails = [...(mdOk ? [] : ['md(폰 뷰어)']), ...(htmlOk ? [] : ['html(공유)'])];
    setDeriveWarn(fails.length ? `${fails.join(' · ')} 저장 실패 — 데스크탑 판(JSON)은 정상` : null);
  }, [keywords, title]);

  // 새로 발행 = 키워드마다 search_gnews 팬아웃 → 섹션 → 판을 저장. (버튼을 눌러야만 실행; 열 때 자동 재취재 없음.)
  const issue = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      // 핫토픽(AI가 오늘의 사건 선정)과 키워드 섹션을 동시에 — 핫토픽을 맨 위에.
      const [hot, kwSections] = await Promise.all([
        fetchHotTopics().catch(() => [] as NewsItem[]),
        Promise.all(
          keywords.map(async (kw): Promise<Section> => {
            try { return { keyword: kw, items: await fetchNews(kw) }; }
            catch { return { keyword: kw, items: [], error: true }; }
          })
        ),
      ]);
      const all: Section[] = [];
      if (hot.length) all.push({ keyword: HOT_KEYWORD, items: hot });
      all.push(...kwSections);
      await commitEdition(all);
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }, [keywords, commitEdition]);

  // 편집신문 완료 → 사용자가 큐레이션한 섹션을 그대로 확정·저장(재취재 없음). 이후 일반 신문 뷰로 복귀.
  const finishEdit = useCallback(async (edited: Section[]) => {
    setEditFlow(false);
    setLoading(true); setError(null);
    try { await commitEdition(edited); }
    catch { setError('신문 저장 중 오류가 발생했습니다.'); }
    finally { setLoading(false); }
  }, [commitEdition]);

  // 열 때: 저장된 최신 판을 보여준다(재취재 없음). 없으면 빈 상태 → 사용자가 '새로 발행'을 눌러 첫 판을 만든다.
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const ed = await loadEdition();
      if (!alive) return;
      if (ed) {
        setSections(ed.sections || []);
        if (ed.dateLabel) setDate(ed.dateLabel);
        setIssuedAt(ed.issuedAt || null);
        setPerspective(typeof ed.perspective === 'boolean' ? ed.perspective : null);
      }
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  return (
    <div className="h-full w-full flex flex-col bg-[#f0f2f5] text-stone-800">
      {/* 상단 바: 편집 토글 + 발행 */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-stone-200 bg-white/70">
        <div className="text-xs text-stone-400">
          {loading ? '신문 발행 중…'
            : issuedAt ? `${whenLabel(issuedAt)} 발행 · ${sections.length}개 섹션${
                perspective === true ? ' · 💡 관점 반영' : perspective === false ? ' · 일반 판(관점 코어 없음)' : ''}`
            : '아직 발행되지 않음'}
          {deriveWarn && <span className="ml-2 text-amber-600">⚠ {deriveWarn}</span>}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setEditing((e) => !e)}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50">
            {editing ? '완료' : '키워드 편집'}
          </button>
          <button onClick={exportHtml} disabled={loading || !sections.length}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50 disabled:opacity-40">
            📄 HTML 내보내기
          </button>
          <button onClick={publishLink} disabled={publishing || loading || !sections.length}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50 disabled:opacity-40">
            {publishing ? '발행 중…' : '🔗 링크로 발행'}
          </button>
          <button onClick={() => { setError(null); setShareUrl(null); setEditFlow(true); }} disabled={loading || editFlow}
            className="text-xs px-2.5 py-1 rounded-lg border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-40">
            ✏️ 편집신문 만들기
          </button>
          <button onClick={issue} disabled={loading || editFlow}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-800 bg-[#1a1a2e] text-white hover:opacity-90 disabled:opacity-40">
            🗞 {loading ? '발행 중…' : '새로 발행'}
          </button>
        </div>
      </div>

      {/* 발행 링크 — 친구에게 이 링크를 보내면 됩니다 */}
      {shareUrl && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 border-b border-emerald-100 bg-emerald-50 text-sm">
          <span className="shrink-0 text-emerald-700">🔗 발행됨 · 친구에게 이 링크를:</span>
          <a href={shareUrl} onClick={(e) => { e.preventDefault(); openExternal(shareUrl); }}
            className="flex-1 min-w-0 truncate text-emerald-800 underline">{shareUrl}</a>
          <button onClick={copyShare}
            className="shrink-0 text-xs px-2.5 py-1 rounded-lg border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-100">복사</button>
        </div>
      )}

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

      {/* 편집신문 마법사 — 활성 시 본문 대신 단계별 큐레이션 화면 */}
      {editFlow && <EditFlow keywords={keywords} onDone={finishEdit} onCancel={() => setEditFlow(false)} />}

      {/* 신문 본문 */}
      {!editFlow && (
      <div className="flex-1 min-h-0 overflow-auto px-4 py-6">
        <div className="max-w-5xl mx-auto bg-white rounded-xl shadow-sm px-8 py-8">
          {/* 제호 */}
          <h1 className="text-center text-4xl font-black tracking-tight text-[#1a1a2e] border-b-4 border-[#1a1a2e] pb-4"
            style={{ fontFamily: "'Noto Serif KR', serif" }}>
            {title || DEFAULT_TITLE}
          </h1>
          <div className="text-center text-sm text-stone-500 mt-3 mb-2">{date}</div>

          {error && <div className="text-center text-rose-500 text-sm py-6">{error}</div>}
          {loading && sections.length === 0 && <div className="text-center text-stone-400 text-sm py-10">신문을 불러오는 중…</div>}
          {!loading && !error && sections.length === 0 && (
            <div className="text-center py-16">
              <div className="text-stone-400 text-sm mb-4">아직 발행된 신문이 없습니다.</div>
              <button onClick={issue}
                className="text-sm px-4 py-2 rounded-lg bg-[#1a1a2e] text-white hover:opacity-90">
                🗞 첫 신문 발행하기
              </button>
            </div>
          )}

          {sections.map((sec) => (
            <section key={sec.keyword} className="mt-9">
              <h2 className="text-2xl font-bold text-[#1a1a2e] border-b-2 border-stone-200 pb-2 mb-4">{sec.keyword}</h2>
              {sec.items.length === 0 ? (
                <div className="text-sm text-stone-400 py-2">{sec.error ? '뉴스를 불러오지 못했습니다.' : '관련 뉴스가 없습니다.'}</div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  {sec.items.map((it, i) => (
                    <article key={i} className="border border-stone-200 rounded-lg p-4 flex flex-col bg-white">
                      <RoleBadge it={it} />
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
      )}
    </div>
  );
}
