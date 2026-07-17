/**
 * ForageBrowser — 계기판에 박힌 "포식 브라우저" (개인 검색엔진 + 도로)
 *
 * 외골격형 공동 포식. 두 상태로 동작한다:
 *   1) search — 구글 같은 검색홈. 프롬프트를 치면 포식 에이전트(/forage/chat)가
 *      "가볼 만한 곳"의 링크를 내준다. *무엇을·어디로*는 전부 에이전트(프롬프트+IBL) 몫.
 *   2) browse — 링크를 클릭하면 진짜 크로미움(webview)으로 그 장소에 진입. 인간이 직접 운전.
 *
 * 핵심: AI는 운전석이 아니라 *목적지를 까는 자리*에 앉는다. 클릭·진입은 100% 인간.
 * 검색 결과의 링크(마크다운 [제목](url) + [MAP:] 마커의 url)를 클릭하면 외부 브라우저가
 * 아니라 이 창의 webview로 열린다 — "검색 → 클릭해서 들어감"이 한 창에서 닫힌다.
 *
 * webview 는 main.js 의 webviewTag=true 필요(앱 재시작 후 적용).
 */
import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useFileAttachments } from './chat/useFileAttachments';
// 지원층(상수·JS 조각·타입·파서)과 서브컴포넌트는 forage/ 로 분리 (2026-07-18 모듈화 — 1500줄 규칙).
import {
  API, EXTRACT_JS, replaceJs, RESTORE_JS, parseCandidates,
  pwApi, hasPwVault, DETECT_PW_JS, READ_PW_JS, fillPwJs, extractDestinations,
} from './forage/support';
import type { Destination, PoolItem, Hunt, Tab } from './forage/support';
import {
  BrowserTabView, FavoritesPage, PoolRow, PoolCard, HistoryPage, BoardsPage, TabFav, NavBtn,
} from './forage/views';

export function ForageBrowser({ open, onClose, openUrl, onUrlConsumed }: {
  open: boolean;
  onClose: () => void;
  // 외부(예: 런처 X-Ray 버튼)가 특정 URL을 새 탭으로 열도록 넘기는 신호. 열고 나면
  // onUrlConsumed 로 부모가 null 로 되돌려 재발화를 막는다.
  openUrl?: string | null;
  onUrlConsumed?: () => void;
}) {
  const [mode, setMode] = useState<'search' | 'browse'>('search');

  // --- 검색홈 상태 ---
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [error, setError] = useState<string | null>(null);
  // 첫화면 즐겨찾기 — 즐겨찾기 계기(🔖)와 같은 sites.json 을 IBL 로 공유(별도 저장소 없음).
  const [favorites, setFavorites] = useState<{ name: string; url: string }[]>([]);

  // 첨부(이미지·텍스트파일) — 프로젝트 에이전트 입력창과 같은 훅 재사용. 이건 에이전트 입력창이니까.
  const att = useFileAttachments();

  // --- 사냥판 상태 — AI가 채우고, 인간이 치우고(✕)·담는(📌) 공유 작업대 ---
  const [hunt, setHuntState] = useState<Hunt | null>(null);
  const huntRef = useRef<Hunt | null>(null);   // 비동기(보충·체류 합산)에서 최신값 접근용
  const setHunt = (updater: Hunt | null | ((h: Hunt | null) => Hunt | null)) => {
    setHuntState((prev) => {
      const next = typeof updater === 'function' ? (updater as (h: Hunt | null) => Hunt | null)(prev) : updater;
      huntRef.current = next;
      return next;
    });
  };
  const poolSeq = useRef(0);
  const [refilling, setRefilling] = useState(false);
  const refillBusy = useRef(false);
  const refillTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dwellRef = useRef<{ itemId: string; start: number } | null>(null);
  const dryRef = useRef(false);   // 직전 보충이 빈손(재고 고갈) → 자동 재보충 중지. 인간 행동(치움·판 크기 변경)이 리셋.
  // 사냥 궤적 — webview 이동 흐름(오래된→최신). 보충 라운드에 동봉되는 신호(끝=지금 관심).
  const trailRef = useRef<{ url: string; title: string; ts: number }[]>([]);

  // 판 크기(테이블 위 물건 수) — AI가 유지할 후보 수. 사용자 조정(5든 15든), localStorage 영속.
  // 보충 목표가 "치운 만큼"에서 "판을 N개로 유지"로 일반화된다(치우면 모자라니 전자를 포함).
  const [poolSize, setPoolSizeState] = useState<number>(() => {
    const v = parseInt(localStorage.getItem('forage_pool_size') || '10', 10);
    return Number.isFinite(v) ? Math.min(30, Math.max(3, v)) : 10;
  });
  const poolSizeRef = useRef(poolSize);
  const setPoolSize = (n: number) => {
    const v = Math.min(30, Math.max(3, n));
    poolSizeRef.current = v;
    setPoolSizeState(v);
    try { localStorage.setItem('forage_pool_size', String(v)); } catch { /* */ }
    dryRef.current = false;
    if (huntRef.current) scheduleRefill();   // 사냥 중 판을 키우면 모자란 만큼 채우러 간다
  };

  // 판 정리(+/−) — 치운 후보를 판에서 숨길지(−) 되살려 볼지(+). 치운 이력은 데이터로 남는다(숨김은 시야만).
  const [showRemoved, setShowRemoved] = useState(true);

  // 보기 모드 — 그리드(썸네일 카드) ↔ 목록(텍스트 행). 발견엔 그리드가 유리해 기본 그리드, localStorage 영속.
  const [viewMode, setViewModeState] = useState<'list' | 'grid'>(() => (localStorage.getItem('forage_view') === 'list' ? 'list' : 'grid'));
  const setViewMode = (m: 'list' | 'grid') => { setViewModeState(m); try { localStorage.setItem('forage_view', m); } catch { /* */ } };

  // 썸네일 지연·점진 로딩 — 아직 이미지 없는 후보(image===undefined)만 백엔드로 보내 og:image 를 받아 채운다.
  // 중복 요청 방지용 in-flight 집합. 백엔드가 캐시하므로 재방문·재보충은 거의 즉시.
  const enrichingRef = useRef<Set<string>>(new Set());
  const enrichImages = async (items: PoolItem[]) => {
    const urls = Array.from(new Set(items
      .filter((i) => i.image === undefined && i.url && /^https?:/.test(i.url) && !enrichingRef.current.has(i.url))
      .map((i) => i.url)));
    if (!urls.length) return;
    urls.forEach((u) => enrichingRef.current.add(u));
    try {
      const r = await fetch(`${API}/forage/enrich`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls }),
      });
      if (r.ok) {
        const d = await r.json();
        const map = d.images || {};
        setHunt((prev) => prev ? {
          ...prev, items: prev.items.map((it) => (it.image === undefined && map[it.url] !== undefined) ? { ...it, image: map[it.url] || '' } : it),
        } : prev);
      }
    } catch { /* 썸네일 실패는 조용히 — 폴백(파비콘)으로 렌더 */ }
    finally { urls.forEach((u) => enrichingRef.current.delete(u)); }
  };

  // 판 식별자 — 보존/복원용. 세션을 넘어 살아남아야 하므로 시간+난수.
  const newBoardId = () => `b${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;

  // 판으로 돌아오면 진행 중이던 체류 시계를 그 후보에 합산(탭 전환은 근사치로 무시).
  const stopDwell = () => {
    const d = dwellRef.current;
    if (!d) return;
    dwellRef.current = null;
    const ms = Date.now() - d.start;
    setHunt((h) => h ? { ...h, items: h.items.map((it) => it.id === d.itemId ? { ...it, dwellMs: it.dwellMs + ms } : it) } : h);
  };

  const patchItem = (id: string, patch: Partial<PoolItem>) =>
    setHunt((h) => h ? { ...h, items: h.items.map((it) => (it.id === id ? { ...it, ...patch } : it)) } : h);

  // 후보 클릭 → 방문 표시 + 체류 시계 시작 + webview 진입.
  const openPoolItem = (item: PoolItem) => {
    stopDwell();
    patchItem(item.id, { visited: true });
    dwellRef.current = { itemId: item.id, start: Date.now() };
    openTab(item.url);
  };

  // 치운 아이템은 순서상 맨끝으로 밀어낸다(활성 후보만 위에 남게). 안정 분할=각 블록 내부 순서 보존.
  const partitionRemoved = (items: PoolItem[]) => [...items.filter((x) => !x.removed), ...items.filter((x) => x.removed)];

  // ✕ = 치우기 — 가봤으면 '삭제'(강한 음성), 안 가봤으면 '제외'(음성). 판이 모자란 만큼 보충이 예약된다.
  const removePoolItem = (item: PoolItem) => {
    setHunt((h) => h ? { ...h, items: partitionRemoved(h.items.map((x) => x.id === item.id ? { ...x, removed: x.visited ? 'deleted' : 'excluded' } : x)) } : h);
    dryRef.current = false;
    scheduleRefill();
  };

  const restorePoolItem = (item: PoolItem) => {
    // 되살리면 활성 블록 끝으로 복귀(제거 블록에서 빠져나옴).
    setHunt((h) => h ? { ...h, items: partitionRemoved(h.items.map((x) => x.id === item.id ? { ...x, removed: null } : x)) } : h);
  };

  // ↕ 순서 바꾸기 — 사람이 아이콘을 끌어 판 위 순서를 직접 준다. 배열 순서 = 표시·저장 순서.
  // (AI가 이 순서를 어떻게 쓰는지·아이콘 주석은 별개 문제. 여기선 순수 입력만 담는다.)
  const dragId = useRef<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const reorderPoolItem = (draggedId: string, targetId: string) => {
    if (draggedId === targetId) return;
    setHunt((h) => {
      if (!h) return h;
      const arr = [...h.items];
      const from = arr.findIndex((x) => x.id === draggedId);
      const to = arr.findIndex((x) => x.id === targetId);
      if (from < 0 || to < 0) return h;
      const [moved] = arr.splice(from, 1);
      arr.splice(to, 0, moved);
      return { ...h, items: partitionRemoved(arr) };
    });
  };
  const dragProps = (it: PoolItem): React.HTMLAttributes<HTMLDivElement> =>
    it.removed ? {} : {
      draggable: true,
      onDragStart: (e) => { dragId.current = it.id; e.dataTransfer.effectAllowed = 'move'; },
      onDragOver: (e) => { if (dragId.current && dragId.current !== it.id) { e.preventDefault(); setDragOverId(it.id); } },
      onDragLeave: () => setDragOverId((c) => (c === it.id ? null : c)),
      onDrop: (e) => { e.preventDefault(); if (dragId.current) reorderPoolItem(dragId.current, it.id); dragId.current = null; setDragOverId(null); },
      onDragEnd: () => { dragId.current = null; setDragOverId(null); },
    };

  // 판 비우기 — 사냥을 접고 깨끗한 검색홈으로(새 시작). 방문 기록·즐겨찾기는 건드리지 않는다.
  const clearBoard = () => {
    setHunt(null); setAnswer(null); setDestinations([]); setError(null);
    dwellRef.current = null; trailRef.current = []; dryRef.current = false;
    if (refillTimer.current) { clearTimeout(refillTimer.current); refillTimer.current = null; }
  };

  // 치우기가 잦아든 뒤(1.8초) 한 번에 보충 — 5벌 연달아 치우면 5벌 한 번에 채운다.
  const scheduleRefill = () => {
    if (refillTimer.current) clearTimeout(refillTimer.current);
    refillTimer.current = setTimeout(() => { refillTimer.current = null; doRefill(); }, 1800);
  };

  const dwellSec = (it: PoolItem) => Math.round(it.dwellMs / 1000);

  // 사냥판 스냅샷 — 백엔드가 한국어 상태 블록으로 직렬화해 메시지에 접합한다(백엔드는 stateless).
  const buildHuntPayload = (h: Hunt, need: number) => ({
    query: h.query,
    round: h.round,
    need,
    // 활성 후보를 판 순서(위=사용자가 더 옳다고 느낀 상위 순위)대로 — 사람·AI 안 가르고 한 리스트(1층 순서 신호).
    order: h.items.filter((i) => !i.removed).map((i, idx) => ({ rank: idx + 1, title: i.title, url: i.url, reason: i.reason, pinned: i.source === 'human', dwell_s: dwellSec(i) })),
    deleted: h.items.filter((i) => i.removed === 'deleted').map((i) => ({ title: i.title, url: i.url, reason: i.reason, dwell_s: dwellSec(i) })),
    excluded: h.items.filter((i) => i.removed === 'excluded').map((i) => ({ title: i.title, url: i.url, reason: i.reason })),
    trail: trailRef.current.slice(-12).map((t) => ({ url: t.url, title: t.title.slice(0, 60) })),
  });

  // 보충 라운드 — 신호(담음·삭제·제외·체류·궤적)를 동봉해 판을 판 크기(N)로 채워 아래에 쌓는다.
  const doRefill = async () => {
    const h = huntRef.current;
    if (!h || refillBusy.current || dryRef.current) return;
    const active = h.items.filter((i) => !i.removed).length;
    const need = Math.min(Math.max(poolSizeRef.current - active, 0), 8);
    if (need <= 0) return;
    refillBusy.current = true;
    setRefilling(true);
    try {
      const r = await fetch(`${API}/forage/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: h.query, hunt: buildHuntPayload(h, need) }),
      });
      if (!r.ok) throw new Error(`보충 실패 (${r.status})`);
      const d = await r.json();
      const { text, destinations } = extractDestinations(d.response || '');
      const parsed = parseCandidates(text);
      const cand = [...parsed.items, ...destinations.map((dd) => ({ title: dd.label, url: dd.url, reason: dd.meta || '' }))];
      const cur = huntRef.current;
      if (cur) {
        const seen = new Set(cur.items.map((i) => normUrl(i.url)));
        const fresh = cand.filter((i) => i.url && !seen.has(normUrl(i.url))).slice(0, need + 2);
        if (fresh.length > 0) {
          const round = cur.round + 1;
          setHunt((prev) => prev ? {
            ...prev, round,
            items: partitionRemoved([...prev.items, ...fresh.map((i) => ({
              id: `c${++poolSeq.current}`, ...i, source: 'ai' as const, round, removed: null, visited: false, dwellMs: 0,
            }))]),
          } : prev);
        } else {
          // 재고 고갈 — 자동 재보충 중지(빈손 루프 방지). AI 의 되물음(사냥 틀 재제안)이 있으면 덧말로.
          dryRef.current = true;
          if (parsed.intro || parsed.outro) {
            setHunt((prev) => prev ? { ...prev, outro: parsed.intro || parsed.outro } : prev);
          }
        }
      }
    } catch { /* 보충 실패는 조용히 — 다음 치우기에서 재시도 */ }
    finally {
      refillBusy.current = false;
      setRefilling(false);
      const after = huntRef.current;
      if (after && !dryRef.current && poolSizeRef.current - after.items.filter((i) => !i.removed).length > 0) {
        scheduleRefill();   // 아직 판이 모자라면(중복 필터 등) 한 번 더
      }
    }
  };

  // 브라우징 중인 현재 페이지를 사냥판에 담기(📌) — 정답의 실물 예시(가장 강한 양성 신호).
  // ★즐겨찾기(★, 영구 북마크)와 다른 개념: 이번 사냥의 후보로만 담는다.
  const pinCurrentPage = () => {
    const h = huntRef.current;
    const url = addr;
    if (!h || !url || url === 'about:blank') return;
    if (h.items.some((i) => normUrl(i.url) === normUrl(url))) { flash('이미 후보 리스트에 있어요'); return; }
    let title = '';
    try { title = activeWebview()?.getTitle?.() || ''; } catch { /* 페이지 전환 중 */ }
    let host = url; try { host = new URL(url).hostname; } catch { /* */ }
    setHunt((prev) => prev ? {
      ...prev,
      items: partitionRemoved([...prev.items, {
        id: `c${++poolSeq.current}`, url, title: (title || host).slice(0, 80), reason: '직접 담음',
        source: 'human' as const, round: prev.round, removed: null as PoolItem['removed'], visited: true, dwellMs: 0,
      }]),
    } : prev);
    flash('후보 리스트에 담았어요 📌');
  };

  // 판의 후보를 즐겨찾기로 승격(☆→★) — 사냥의 수확을 영구 보관. 기존 limbs:launch 어휘 재사용.
  const savePoolFav = async (item: PoolItem) => {
    try {
      let host = item.url; try { host = new URL(item.url).hostname; } catch { /* */ }
      const name = (escq(item.title || host).slice(0, 60)) || host;
      await iblExec(`[limbs:launch]{action: "add", name: "${name}", url: "${escq(item.url)}"}`);
      flash('즐겨찾기에 담았어요 ★');
      await loadFavorites();
    } catch { flash('즐겨찾기 저장 실패'); }
  };

  // --- 판 보존(판 도서관) — 수동 토글. 켜면 backend 에 저장(내가 떠난 그대로), 끄면 삭제. ---
  // 즐겨찾기(개별 전리품)와 다른 층: 작업판 통째(후보·담기/치우기·라운드·궤적·판 크기)를 이름 붙여 남긴다.
  const serializeBoard = (h: Hunt) => ({
    query: h.query, intro: h.intro, outro: h.outro, round: h.round,
    items: h.items, poolSize: poolSizeRef.current, showRemoved,
    trail: trailRef.current.slice(-50),
  });

  const persistBoard = async (h: Hunt) => {
    try {
      await fetch(`${API}/forage/boards`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: h.id, name: h.query.slice(0, 120), state: serializeBoard(h) }),
      });
    } catch { /* 보존 실패는 조용히 — 다음 편집에서 재시도 */ }
  };

  // 보존 토글 — 즐겨찾기 별표처럼 켜고 끈다. 켜면 즉시 저장, 끄면 도서관에서 뺀다.
  const toggleBoardSave = async () => {
    const h = huntRef.current;
    if (!h) return;
    if (h.saved) {
      setHunt((prev) => prev ? { ...prev, saved: false } : prev);
      try { await fetch(`${API}/forage/boards/${h.id}`, { method: 'DELETE' }); } catch { /* */ }
      flash('판 보존을 껐어요');
    } else {
      setHunt((prev) => prev ? { ...prev, saved: true } : prev);
      await persistBoard({ ...h, saved: true });
      flash('판을 도서관에 보존했어요 📋');
    }
  };

  // 보존된 판 하나를 펼치기 — 내가 떠난 그대로(후보·담기/치우기·라운드·궤적·판 크기) 되살린다.
  const openBoard = (b: { id: string; name: string; state: any }) => {
    const st = b.state || {};
    const rawItems = Array.isArray(st.items) ? st.items : [];
    // id 충돌 방지 — 불러온 후보에 새 id 재부여(React key·체류 패치가 이 id 를 쓴다).
    const items: PoolItem[] = rawItems.map((i: any) => ({
      id: `c${++poolSeq.current}`,
      url: String(i.url || ''), title: String(i.title || ''), reason: String(i.reason || ''),
      source: i.source === 'human' ? 'human' : 'ai',
      round: Number(i.round) || 1,
      removed: i.removed === 'deleted' ? 'deleted' : i.removed === 'excluded' ? 'excluded' : null,
      visited: !!i.visited, dwellMs: Number(i.dwellMs) || 0,
      image: typeof i.image === 'string' ? i.image : undefined,  // 저장된 썸네일 유지(없으면 effect 가 채움)
    }));
    trailRef.current = Array.isArray(st.trail) ? st.trail.slice(-50) : [];
    dryRef.current = false;
    if (refillTimer.current) { clearTimeout(refillTimer.current); refillTimer.current = null; }
    // 판 크기 복원 — scheduleRefill 부작용 없이(내가 떠난 그대로여야 하므로 자동 보충 금지).
    if (typeof st.poolSize === 'number') {
      const v = Math.min(30, Math.max(3, st.poolSize));
      poolSizeRef.current = v; setPoolSizeState(v);
      try { localStorage.setItem('forage_pool_size', String(v)); } catch { /* */ }
    }
    setShowRemoved(st.showRemoved !== false);
    setAnswer(null); setDestinations([]); setError(null);
    setHunt({ id: b.id, saved: true, query: st.query || b.name || '', intro: st.intro || '', outro: st.outro || '', round: Number(st.round) || 1, items: partitionRemoved(items) });
    setMode('search');
  };

  // --- 브라우즈(탭) 상태 — 크롬처럼 여러 사이트를 탭으로 동시에. 각 탭 = 하나의 webview. ---
  const webviewRefs = useRef<Record<string, any>>({});   // 탭 id → webview DOM
  const tabSeq = useRef(0);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // 활성 탭에서 파생 — 주소/네비 버튼/로딩은 전부 활성 탭 값을 본다.
  const activeTab = tabs.find((t) => t.id === activeId) || null;
  const addr = activeTab?.url || '';
  const canBack = !!activeTab?.canBack;
  const canFwd = !!activeTab?.canFwd;
  const loading = !!activeTab?.loading;
  const activeWebview = (): any => (activeId ? webviewRefs.current[activeId] : null);

  const registerRef = (id: string, el: any) => { if (el) webviewRefs.current[id] = el; };
  const updateTab = (id: string, patch: Partial<Tab>) =>
    setTabs((prev) => prev.map((t) => {
      if (t.id !== id) return t;
      if (patch.url && patch.url !== t.url && t.kind === 'web') {
        // ① 사냥 궤적 — 진행 중 사냥이 있을 때만(보충 라운드 신호). 연속 중복 제거.
        if (huntRef.current) {
          const trail = trailRef.current;
          if (!trail.length || trail[trail.length - 1].url !== patch.url) {
            trail.push({ url: patch.url, title: patch.title || t.title || '', ts: Date.now() });
            if (trail.length > 50) trail.shift();
          }
        }
        // ② 영구 방문 기록 — 전부 기록·수동 삭제. fire-and-forget, 연속 중복은 백엔드가 걸러줌.
        fetch(`${API}/forage/history`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: patch.url, title: patch.title || t.title || '', hunt_query: huntRef.current?.query || '' }),
        }).catch(() => { /* 기록 실패는 조용히 */ });
      }
      return { ...t, ...patch };
    }));

  // 새 탭으로 사이트 열기 — 즐겨찾기·검색결과·링크 클릭이 전부 여기로(각각 별개 탭이 쌓인다).
  const openTab = (url: string) => {
    const id = `t${++tabSeq.current}`;
    setTabs((prev) => [...prev, { id, kind: 'web', initialUrl: url, url, title: url, canBack: false, canFwd: false, loading: true, translated: false }]);
    setActiveId(id);
    setMode('browse');
  };

  // 외부에서 openUrl 신호가 오면(브라우저가 열린 상태) 그 URL을 새 탭으로 열고 신호를 소비한다.
  useEffect(() => {
    if (open && openUrl) {
      openTab(openUrl);
      onUrlConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, openUrl]);

  // 스위치 → 즐겨찾기 바둑판 페이지를 새 탭으로(이미 있으면 그 탭으로 전환). 최신 목록 당김.
  const openFavoritesTab = () => {
    const existing = tabs.find((t) => t.kind === 'favorites');
    if (existing) { setActiveId(existing.id); setMode('browse'); loadFavorites(); return; }
    const id = `t${++tabSeq.current}`;
    setTabs((prev) => [...prev, { id, kind: 'favorites', initialUrl: '', url: '', title: '즐겨찾기', canBack: false, canFwd: false, loading: false, translated: false }]);
    setActiveId(id);
    setMode('browse');
    loadFavorites();
  };

  // 방문 기록 페이지 탭 — 전부 기록·수동 삭제. 이미 있으면 그 탭으로 전환.
  const openHistoryTab = () => {
    const existing = tabs.find((t) => t.kind === 'history');
    if (existing) { setActiveId(existing.id); setMode('browse'); return; }
    const id = `t${++tabSeq.current}`;
    setTabs((prev) => [...prev, { id, kind: 'history', initialUrl: '', url: '', title: '방문 기록', canBack: false, canFwd: false, loading: false, translated: false }]);
    setActiveId(id);
    setMode('browse');
  };

  // 판 도서관 페이지 탭 — 보존된 판들을 즐겨찾기처럼 나열. 이미 있으면 그 탭으로 전환.
  const openLibraryTab = () => {
    const existing = tabs.find((t) => t.kind === 'library');
    if (existing) { setActiveId(existing.id); setMode('browse'); return; }
    const id = `t${++tabSeq.current}`;
    setTabs((prev) => [...prev, { id, kind: 'library', initialUrl: '', url: '', title: '판 도서관', canBack: false, canFwd: false, loading: false, translated: false }]);
    setActiveId(id);
    setMode('browse');
  };

  // 탭 닫기 — 닫은 게 활성이면 인접 탭으로, 마지막이면 검색홈으로 복귀.
  const closeTab = (id: string) => {
    const idx = tabs.findIndex((t) => t.id === id);
    const next = tabs.filter((t) => t.id !== id);
    delete webviewRefs.current[id];
    setTabs(next);
    if (id === activeId) {
      if (next.length === 0) { setActiveId(null); setMode('search'); }
      else { setActiveId(next[Math.min(idx, next.length - 1)].id); setMode('browse'); }
    }
  };

  // 주소·검색줄 자동 숨김 — 본문 볼 땐 감췄다가 상단 얇은 센서에 마우스를 올리면 다시 나온다.
  // (본문 webview 위의 마우스 이동은 호스트로 안 올라오므로, flex 흐름 안의 센서 띠로 되살린다.)
  const [barHidden, setBarHidden] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showBar = () => { if (hideTimer.current) { clearTimeout(hideTimer.current); hideTimer.current = null; } setBarHidden(false); };
  // 주소창 직접 입력 — null 이면 표시 모드(네비게이션이 갱신), 문자열이면 편집 중(갱신이 덮지 않게).
  const [addrEdit, setAddrEdit] = useState<string | null>(null);
  const scheduleHide = () => {
    if (addrEdit !== null) return;   // 주소 편집 중엔 바를 숨기지 않는다
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setBarHidden(true), 700);
  };

  // --- 비밀번호 채우기 상태 ---
  const [pwHasField, setPwHasField] = useState(false);          // 현재 페이지에 로그인 폼이 있나
  const [pwAccounts, setPwAccounts] = useState<{ username: string }[]>([]); // 이 host 저장 계정들
  const [pwMenuOpen, setPwMenuOpen] = useState(false);
  const [pwToast, setPwToast] = useState<string | null>(null);
  // ms=0 이면 자동으로 안 사라짐(에러 진단용) — 토스트를 클릭하면 닫힌다.
  const flash = (msg: string, ms = 1800) => { setPwToast(msg); if (ms > 0) setTimeout(() => setPwToast(null), ms); };

  // 번역 진행중 플래그(활성 탭 기준). 번역 여부는 탭별로 Tab.translated 에 보관.
  const [translating, setTranslating] = useState(false);

  // 번역 토글 — 텍스트 노드 추출 → 백엔드 번역 → 제자리 치환, 다시 누르면 원문 복원. 활성 탭 대상.
  const toggleTranslation = async () => {
    const el = activeWebview();
    if (!el || translating || !activeTab) return;
    if (activeTab.translated) {
      try { await el.executeJavaScript(RESTORE_JS, true); } catch { /* 페이지 전환 중일 수 있음 */ }
      updateTab(activeTab.id, { translated: false });
      return;
    }
    setTranslating(true);
    try {
      const texts: string[] = await el.executeJavaScript(EXTRACT_JS, true);
      if (!texts || !texts.length) { setTranslating(false); return; }
      const r = await fetch(`${API}/forage/translate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts, target: 'ko' }),
      });
      if (!r.ok) throw new Error(`번역 실패 (${r.status})`);
      const d = await r.json();
      await el.executeJavaScript(replaceJs(d.translations || []), true);
      updateTab(activeTab.id, { translated: true });
    } catch (e: any) {
      flash(e?.message || '번역 중 오류가 발생했습니다.');
    } finally {
      setTranslating(false);
    }
  };

  // 페이지의 로그인 폼 감지 → 저장 계정 조회 → 단일 매칭이면 조용히 자동 채움(제출은 안 함).
  const detectAndAutofill = async () => {
    const el = activeWebview();
    if (!el || !hasPwVault()) return;
    try {
      const found = await el.executeJavaScript(DETECT_PW_JS, true);
      if (!found?.host) { setPwHasField(false); setPwAccounts([]); return; }
      setPwHasField(true);
      const accts = (await pwApi().foragePwListHost?.(found.origin)) || [];
      setPwAccounts(accts);
      if (accts.length === 1) {
        const cred = await pwApi().foragePwGet?.(found.origin, accts[0].username);
        if (cred) await el.executeJavaScript(fillPwJs(cred.username, cred.password), true);
      }
    } catch { /* 페이지가 막 바뀌는 중일 수 있음 — 무시 */ }
  };

  const fillCredential = async (username: string) => {
    const el = activeWebview();
    if (!el) return;
    const cred = await pwApi().foragePwGet?.(addr, username);
    if (cred) { await el.executeJavaScript(fillPwJs(cred.username, cred.password), true); flash('채웠어요'); }
    setPwMenuOpen(false);
  };

  const saveCurrentLogin = async () => {
    const el = activeWebview();
    if (!el) return;
    setPwMenuOpen(false);
    let data: any = null;
    try { data = await el.executeJavaScript(READ_PW_JS, true); } catch { /* */ }
    if (!data?.password) { flash('저장할 로그인 입력값이 없어요'); return; }
    const res = await pwApi().foragePwSave?.(data.origin, data.username || '', data.password);
    flash(res === true ? '이 로그인을 저장했어요' : '저장 실패');
    setPwAccounts((await pwApi().foragePwListHost?.(data.origin)) || []);
  };

  const importFromChrome = async () => {
    setPwMenuOpen(false);
    flash('크롬에서 가져오는 중…', 6000);
    const res = await pwApi().foragePwImportChrome?.();
    if (res && 'imported' in res) {
      flash(`크롬에서 ${res.imported}개 가져왔어요${res.total ? ` (총 ${res.total}개 중)` : ''}`, 3000);
    } else {
      // 실패 메시지는 자동으로 안 사라지게(ms=0) — 원인을 끝까지 읽을 수 있도록.
      flash(`가져오기 실패: ${(res as any)?.error || '알 수 없음'} — (탭하면 닫힘)`, 0);
    }
    setPwAccounts((await pwApi().foragePwListHost?.(addr)) || []);
  };

  // 브라우징 중에도 또 검색 — 검색홈으로 돌아갈 필요 없이, 슬림 검색바에서 바로.
  const searchAndShow = () => {
    if (!query.trim() && !att.hasAttachments) return;
    setMode('search');   // 결과를 보려면 검색홈으로(웹뷰는 mount 게이트로 자동 unmount)
    runSearch();
  };

  // overrideQ = 주소창 등에서 질의를 직접 넘길 때(setQuery 는 비동기라 state 를 기다리지 않는다).
  const runSearch = async (overrideQ?: string) => {
    const rawQ = overrideQ ?? query;
    const q = rawQ.trim();
    if ((!q && !att.hasAttachments) || searching) return;
    const message = att.prepareMessageContent(rawQ);   // 텍스트파일 내용은 메시지에 인라인
    const images = att.prepareImageData();               // 이미지는 base64 로 동봉
    setSearching(true); setError(null); setAnswer(null); setDestinations([]);
    // 새 검색 = 새 사냥 — 이전 판·궤적·체류 시계를 접는다(보존된 판은 backend 에 이미 남아 있다).
    setHunt(null); dwellRef.current = null; trailRef.current = []; dryRef.current = false; setShowRemoved(true);
    if (refillTimer.current) { clearTimeout(refillTimer.current); refillTimer.current = null; }
    try {
      const r = await fetch(`${API}/forage/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, images, count: poolSizeRef.current }),
      });
      if (!r.ok) throw new Error(`검색 실패 (${r.status})`);
      const d = await r.json();
      const { text, destinations } = extractDestinations(d.response || '');
      const parsed = parseCandidates(text);
      const cand = [...parsed.items, ...destinations.map((dd) => ({ title: dd.label, url: dd.url, reason: dd.meta || '' }))];
      if (cand.length > 0) {
        // 링크가 있으면 사냥판으로 — 이후 치우기(✕)·담기(📌)·보충 라운드가 이 판 위에서 돈다.
        const seen = new Set<string>();
        const pool = cand
          .filter((i) => { const k = normUrl(i.url); if (!i.url || seen.has(k)) return false; seen.add(k); return true; })
          .map((i) => ({ id: `c${++poolSeq.current}`, ...i, source: 'ai' as const, round: 1, removed: null, visited: false, dwellMs: 0 }));
        setHunt({ id: newBoardId(), saved: false, query: q || message.slice(0, 200), intro: parsed.intro, outro: parsed.outro, round: 1, items: pool });
        if (pool.length < poolSizeRef.current) scheduleRefill();   // 판 크기만큼 못 깔렸으면 채우러
      } else {
        setAnswer(text); setDestinations(destinations);   // 링크 없는 응답(희소 안내 등)은 본문 그대로
      }
      setQuery('');           // 결과가 나오면 검색창을 비운다
      att.clearAttachments();
    } catch (e: any) {
      setError(e?.message || '검색 중 오류가 발생했습니다.');
    } finally {
      setSearching(false);
    }
  };

  // 주소창 입력 → 이동. 스킴 있으면 그대로, 도메인꼴이면 https:// 보정, 둘 다 아니면 포식 검색으로.
  const navigateAddr = () => {
    const raw = (addrEdit ?? '').trim();
    setAddrEdit(null);
    if (!raw) return;
    let url = '';
    if (/^https?:\/\//i.test(raw)) url = raw;
    else if (/^[\w-]+(\.[\w-]+)+(:\d+)?([/?#]\S*)?$/.test(raw)) url = `https://${raw}`;
    if (url) {
      const el = activeWebview();
      if (el && activeTab?.kind === 'web') {
        // 현재 탭에서 이동(브라우저 관례) — did-navigate 가 상태·히스토리를 알아서 갱신.
        try { el.loadURL(url); updateTab(activeTab.id, { loading: true, url }); return; } catch { /* 폴백: 새 탭 */ }
      }
      openTab(url);
    } else {
      // URL 이 아니면 검색어 — 검색홈으로 돌아가 포식 검색(브라우저 주소창 관례).
      setQuery(raw);
      setMode('search');
      runSearch(raw);
    }
  };

  // 즐겨찾기 IBL 헬퍼 — 계기(🔖)와 같은 sites.json 을 공유(add/remove/list).
  const iblExec = async (code: string): Promise<any> => {
    const r = await fetch(`${API}/ibl/execute`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, project_id: '앱모드' }),
    });
    const d = await r.json();
    let res = (d && typeof d === 'object' && 'result' in d) ? (d as any).result : d;
    if (typeof res === 'string') { try { res = JSON.parse(res); } catch { /* keep */ } }
    return res;
  };

  const loadFavorites = async () => {
    try {
      const res = await iblExec('[limbs:launch]{action: "list"}');
      const items = res && Array.isArray(res.items) ? res.items : [];
      setFavorites(items.filter((s: any) => s?.url).map((s: any) => ({ name: s.name || s.url, url: s.url })));
    } catch { /* 즐겨찾기 없으면 조용히 비움 */ }
  };

  // 열릴 때마다 즐겨찾기를 당긴다(계기에서 편집한 게 즉시 반영).
  useEffect(() => { if (open) loadFavorites(); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // 현재 페이지가 이미 즐겨찾기인가 — 끝 슬래시 무시하고 비교.
  const normUrl = (u: string) => (u || '').replace(/\/+$/, '').toLowerCase();
  const currentFav = favorites.find((f) => normUrl(f.url) === normUrl(addr));

  // IBL 문자열 파라미터 이스케이프(따옴표·개행 제거).
  const escq = (s: string) => (s || '').replace(/"/g, "'").replace(/[\r\n]+/g, ' ').trim();

  // 현재 브라우징 중인 페이지를 즐겨찾기에 담기/빼기(토글). 추가는 자동 augmentation.
  const toggleFavorite = async () => {
    const url = addr;
    if (!url || url === 'about:blank') return;
    try {
      if (currentFav) {
        await iblExec(`[limbs:launch]{action: "remove", name: "${escq(currentFav.name)}"}`);
        flash('즐겨찾기에서 뺐어요');
      } else {
        let title = '';
        try { title = activeWebview()?.getTitle?.() || ''; } catch { /* 페이지 전환 중 */ }
        let host = url; try { host = new URL(url).hostname; } catch { /* */ }
        const name = (escq(title || host).slice(0, 60)) || host;
        await iblExec(`[limbs:launch]{action: "add", name: "${name}", url: "${escq(url)}"}`);
        flash('즐겨찾기에 담았어요');
      }
      await loadFavorites();
    } catch { flash('즐겨찾기 처리 실패'); }
  };

  // 즐겨찾기 페이지에서 항목 제거 — 이름으로 삭제 후 목록 최신화.
  const removeFavorite = async (name: string) => {
    try {
      await iblExec(`[limbs:launch]{action: "remove", name: "${escq(name)}"}`);
      flash('즐겨찾기에서 뺐어요');
      await loadFavorites();
    } catch { flash('삭제 실패'); }
  };

  // Esc 로 닫기 — webview 가 상단 바를 가려 버튼이 안 먹는 상황의 안전판.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // 활성 탭 로그인 폼 감지 — 탭 전환/로딩 완료/페이지 이동 시 다시 감지(이미 로드된 탭으로
  // 전환해도 자동 채움이 붙도록). 각 webview 이벤트는 자식(BrowserTabView)이 Tab 상태로 올린다.
  useEffect(() => {
    setPwMenuOpen(false);
    if (mode !== 'browse' || !activeId) { setPwHasField(false); setPwAccounts([]); return; }
    if (activeTab && !activeTab.loading) detectAndAutofill();
  }, [activeId, mode, activeTab?.loading, activeTab?.url]); // eslint-disable-line react-hooks/exhaustive-deps

  // 탭 전환 시 주소줄을 잠깐 보여준다(어디로 왔는지 확인) — 본문으로 내려가면 다시 숨는다.
  // 편집 중이던 주소는 버린다(다른 탭의 URL 위에 얹히는 사고 방지).
  useEffect(() => { showBar(); setAddrEdit(null); }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 판(검색홈)으로 돌아오면 체류 시계를 멈춰 후보에 합산 — "돌아왔다"가 다음 판의 신호가 된다.
  useEffect(() => { if (mode === 'search') stopDwell(); }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // 보존된 판은 편집(치우기·담기·보충·판 크기·정리)마다 backend 를 최신화 — 내가 떠난 그대로 남게. 디바운스.
  useEffect(() => {
    if (!hunt?.saved) return;
    const t = setTimeout(() => { const h = huntRef.current; if (h?.saved) persistBoard(h); }, 1000);
    return () => clearTimeout(t);
  }, [hunt, poolSize, showRemoved]); // eslint-disable-line react-hooks/exhaustive-deps

  // 아직 썸네일 없는 후보를 채운다 — 검색·보충·판 펼치기 어디서 새 후보가 들어오든 여기서 잡힌다.
  // enrich 후 image 가 undefined→값이 되어 pending 이 비므로 자기종료(무한 재요청 없음).
  useEffect(() => {
    if (!hunt) return;
    const pending = hunt.items.filter((i) => i.image === undefined && i.url);
    if (pending.length) enrichImages(pending);
  }, [hunt]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className={`absolute inset-0 z-30 flex-col bg-white ${open ? 'flex' : 'hidden'}`}
    >
      {/* 탭 스트립 — 탭이 하나라도 있으면 항상. 클릭=전환, +=새 탭(검색홈), ×=닫기. */}
      {tabs.length > 0 && (
        <div className="shrink-0 flex items-stretch gap-1 px-2 pt-1.5 bg-stone-100 border-b border-stone-200 overflow-x-auto">
          {tabs.map((t) => (
            <div key={t.id}
              onClick={() => { setActiveId(t.id); setMode('browse'); }}
              className={`group flex items-center gap-1.5 pl-2 pr-1 py-1.5 rounded-t-lg cursor-pointer shrink-0 w-44 ${
                mode === 'browse' && t.id === activeId ? 'bg-white' : 'bg-stone-200/50 hover:bg-stone-200'
              }`}>
              {t.kind !== 'web'
                ? <span className="w-4 h-4 shrink-0 text-sm leading-none flex items-center justify-center">{t.kind === 'favorites' ? '⊞' : t.kind === 'library' ? '📋' : '🕘'}</span>
                : <TabFav url={t.url} />}
              <span className="text-xs text-stone-700 truncate flex-1">{t.loading ? '불러오는 중…' : (t.title || t.url)}</span>
              <button onClick={(e) => { e.stopPropagation(); closeTab(t.id); }} title="탭 닫기"
                className="w-4 h-4 rounded text-stone-400 hover:bg-stone-300 hover:text-stone-700 text-xs leading-none shrink-0 flex items-center justify-center">×</button>
            </div>
          ))}
          <button onClick={() => setMode('search')} title="새 탭"
            className={`shrink-0 px-2.5 py-1.5 rounded-t-lg text-lg leading-none text-stone-500 hover:bg-stone-200 ${mode === 'search' ? 'bg-white' : ''}`}>+</button>
        </div>
      )}

      {/* 상단 바 — 모드별로 다르다. 브라우즈에선 주소·검색줄이 자동 숨김(센서 띠로 되살림). */}
      {mode === 'browse' ? (
        barHidden ? (
          <div onMouseEnter={showBar} title="주소·검색줄 보기"
            className="shrink-0 h-3 flex items-center justify-center bg-stone-100 border-b border-stone-200 cursor-pointer hover:bg-stone-200 transition">
            <span className="text-[10px] leading-none text-stone-400 select-none">⌄</span>
          </div>
        ) : (
        <div onMouseEnter={showBar} onMouseLeave={scheduleHide} className="shrink-0 border-b border-stone-200 bg-stone-50">
          {/* 슬림 검색바 — 브라우징 중에도 항상 떠 있어, 처음 자리로 안 돌아와도 또 검색. 길게·얇게. */}
          <form onSubmit={(e) => { e.preventDefault(); searchAndShow(); }} className="flex items-center gap-2 px-3 pt-2 pb-1">
            <span className="text-stone-400 text-sm select-none">🔍</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); searchAndShow(); } }}
              className="flex-1 px-3 py-1 rounded-full border border-stone-200 bg-white text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-stone-300"
            />
          </form>
          {/* 주소/네비 바 */}
          <div className="flex items-center gap-1.5 px-3 pb-2 pt-0.5">
            <button onClick={() => setMode('search')} className="px-3 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-200 whitespace-nowrap">＋ 새 탭</button>
            {activeTab && activeTab.kind !== 'web' ? (
              <>
                <span className="px-3 py-1.5 text-sm text-stone-500">{activeTab.kind === 'favorites' ? '⊞ 즐겨찾기' : activeTab.kind === 'library' ? '📋 판 도서관' : '🕘 방문 기록'}</span>
                <div className="flex-1" />
              </>
            ) : (
            <>
            <NavBtn onClick={() => activeWebview()?.goBack()} disabled={!canBack} label="‹" title="뒤로" />
            <NavBtn onClick={() => activeWebview()?.goForward()} disabled={!canFwd} label="›" title="앞으로" />
            <NavBtn onClick={() => activeWebview()?.reload()} label="⟳" title="새로고침" />
            <button
              onClick={toggleTranslation}
              disabled={translating}
              title={activeTab?.translated ? "원본 보기" : "한국어로 번역"}
              className={`px-2.5 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition flex items-center gap-1 disabled:opacity-50 ${
                activeTab?.translated
                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200 ring-1 ring-blue-300'
                  : 'text-stone-600 hover:bg-stone-200'
              }`}
            >
              <span>🌐</span>
              <span>{translating ? '번역 중…' : activeTab?.translated ? '원본' : '번역'}</span>
            </button>
            <button
              onClick={toggleFavorite}
              title={currentFav ? '즐겨찾기에서 빼기' : '이 페이지를 즐겨찾기에 추가'}
              className={`px-2.5 py-1.5 rounded-lg text-base leading-none whitespace-nowrap transition ${
                currentFav ? 'text-amber-500 hover:bg-amber-50' : 'text-stone-400 hover:bg-stone-200'
              }`}
            >
              {currentFav ? '★' : '☆'}
            </button>
            {/* 사냥판에 담기 — 진행 중 사냥이 있을 때만. 즐겨찾기(영구)와 달리 이번 사냥의 후보로. */}
            {hunt && (
              <button
                onClick={pinCurrentPage}
                title="이 페이지를 검색 후보 리스트에 담기"
                className="px-2.5 py-1.5 rounded-lg text-base leading-none whitespace-nowrap text-stone-400 hover:bg-stone-200 transition"
              >
                📌
              </button>
            )}
            {/* 주소창 — 클릭해 고쳐 입력하고 Enter 로 이동(URL 아니면 포식 검색). Esc=편집 취소. */}
            <input
              value={addrEdit ?? addr}
              onFocus={(e) => { showBar(); setAddrEdit(addr); const t = e.target; requestAnimationFrame(() => t.select()); }}
              onChange={(e) => setAddrEdit(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); navigateAddr(); (e.target as HTMLInputElement).blur(); }
                else if (e.key === 'Escape') { e.stopPropagation(); setAddrEdit(null); (e.target as HTMLInputElement).blur(); }
              }}
              onBlur={() => setAddrEdit(null)}
              spellCheck={false}
              className="flex-1 min-w-0 px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-sm text-stone-500 truncate focus:outline-none focus:ring-2 focus:ring-stone-300 focus:text-stone-800"
            />
            {loading && <span className="text-xs text-stone-400 px-1 whitespace-nowrap">불러오는 중…</span>}

            {/* 비밀번호 채우기 — Electron 금고가 있을 때만. 로그인 폼이 감지되면 강조. */}
            {hasPwVault() && (
              <div className="relative">
                <button
                  onClick={() => setPwMenuOpen((v) => !v)}
                  title="비밀번호 채우기"
                  className={`px-2.5 py-1.5 rounded-lg text-sm whitespace-nowrap transition ${
                    pwHasField ? 'bg-amber-100 text-amber-700 hover:bg-amber-200' : 'text-stone-500 hover:bg-stone-200'
                  }`}
                >
                  🔑{pwAccounts.length > 0 ? ` ${pwAccounts.length}` : ''}
                </button>
                {pwMenuOpen && (
                  <div className="absolute right-0 top-full mt-1 z-50 w-60 rounded-xl border border-stone-200 bg-white shadow-lg py-1.5 text-sm">
                    {pwAccounts.length > 0 && (
                      <>
                        <div className="px-3 py-1 text-[11px] text-stone-400">저장된 계정으로 채우기</div>
                        {pwAccounts.map((a, i) => (
                          <button key={i} onClick={() => fillCredential(a.username)}
                            className="w-full text-left px-3 py-1.5 hover:bg-stone-50 text-stone-700 truncate">
                            {a.username || '(아이디 없음)'}
                          </button>
                        ))}
                        <div className="my-1 border-t border-stone-100" />
                      </>
                    )}
                    <button onClick={saveCurrentLogin}
                      className="w-full text-left px-3 py-1.5 hover:bg-stone-50 text-stone-700">
                      💾 이 로그인 저장
                    </button>
                    <button onClick={importFromChrome}
                      className="w-full text-left px-3 py-1.5 hover:bg-stone-50 text-stone-700">
                      ⬇️ 크롬에서 비밀번호 가져오기
                    </button>
                  </div>
                )}
              </div>
            )}
            </>
            )}
          </div>
          {pwToast && (
            <div onClick={() => setPwToast(null)}
              className="px-3 pb-1.5 -mt-0.5 text-xs text-stone-500 cursor-pointer break-all">{pwToast}</div>
          )}
        </div>
        )
      ) : (
        <div className="shrink-0 flex items-center justify-between px-4 py-2">
          <div className="flex items-center gap-2">
            <button onClick={openFavoritesTab} title="즐겨찾기 모아보기"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-100 hover:border-stone-300 transition">
              <span className="text-base leading-none">⊞</span>
              <span>즐겨찾기</span>
            </button>
            <button onClick={openHistoryTab} title="방문 기록 (전부 기록 · 수동 삭제)"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-100 hover:border-stone-300 transition">
              <span className="text-base leading-none">🕘</span>
              <span>기록</span>
            </button>
            <button onClick={openLibraryTab} title="보존한 판 모아보기"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-stone-200 bg-white text-sm text-stone-600 hover:bg-stone-100 hover:border-stone-300 transition">
              <span className="text-base leading-none">📋</span>
              <span>판 도서관</span>
            </button>
          </div>
        </div>
      )}

      {/* 검색홈 — webview 와 공존(숨김)시켜 세션·페이지를 살려둔다 */}
      <div className={`flex-1 min-h-0 overflow-auto ${mode === 'search' ? 'block' : 'hidden'}`}>
        <div className={`${hunt ? 'max-w-4xl' : 'max-w-2xl'} mx-auto px-6 ${answer || searching || error ? 'pt-8' : 'pt-[18vh]'}`}>
          {!answer && !searching && !error && (
            // 나중에 로고 이미지로 교체 가능. 지금은 워드마크.
            <h1 className="text-center text-4xl font-light tracking-tight text-stone-700 mb-6">indiebizOS</h1>
          )}

          <form onSubmit={(e) => { e.preventDefault(); runSearch(); }}>
            {/* 첨부 미리보기 */}
            {(att.attachedImages.length > 0 || att.attachedTextFiles.length > 0) && (
              <div className="flex flex-wrap gap-2 mb-2">
                {att.attachedImages.map((img, i) => (
                  <div key={`img${i}`} className="relative">
                    <img src={img.preview} alt="" className="w-14 h-14 object-cover rounded-lg border border-stone-200" />
                    <button type="button" onClick={() => att.removeImage(i)}
                      className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-stone-700 text-white text-[11px] leading-none flex items-center justify-center">×</button>
                  </div>
                ))}
                {att.attachedTextFiles.map((tf, i) => (
                  <div key={`tf${i}`} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-stone-100 text-xs text-stone-600">
                    <span>📄 {tf.file.name}</span>
                    <button type="button" onClick={() => att.removeTextFile(i)} className="text-stone-400 hover:text-stone-600">×</button>
                  </div>
                ))}
              </div>
            )}

            <div className="relative flex items-center">
              <button type="button" onClick={() => att.fileInputRef.current?.click()} title="사진·파일 첨부"
                className="absolute left-2.5 w-8 h-8 rounded-lg text-stone-400 hover:text-stone-600 hover:bg-stone-100 flex items-center justify-center">📎</button>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onPaste={att.handlePaste}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runSearch(); } }}
                rows={1}
                autoFocus
                className="w-full resize-none pl-12 pr-20 py-3.5 rounded-2xl border border-stone-300 bg-white text-stone-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-stone-300 focus:border-stone-300"
              />
              <button type="submit" disabled={searching || (!query.trim() && !att.hasAttachments)}
                className="absolute right-2.5 px-4 py-1.5 rounded-xl bg-stone-800 text-white text-sm disabled:opacity-40 hover:bg-stone-700 transition">
                {searching ? '…' : '찾기'}
              </button>
            </div>
            <input ref={att.fileInputRef} type="file" multiple
              accept="image/*,.txt,.md,.json,.csv,.log,.py,.js,.ts,.html,.css"
              onChange={att.handleFileSelect} className="hidden" />
          </form>

          {/* 판 크기 — 테이블 위에 유지할 후보 수(5든 15든). 사냥 중 키우면 모자란 만큼 즉시 보충. */}
          <div className="mt-2 flex items-center justify-end gap-1.5 text-xs text-stone-400 select-none">
            {hunt && (
              <button type="button" onClick={toggleBoardSave}
                title={hunt.saved ? '판 보존 켜짐 — 도서관에 남아요 (눌러서 끄기)' : '이 판을 도서관에 보존'}
                className={`mr-1 px-2.5 py-1 rounded-lg transition ${
                  hunt.saved ? 'bg-amber-100 text-amber-700 hover:bg-amber-200' : 'text-stone-400 hover:bg-stone-100 hover:text-stone-600'
                }`}>{hunt.saved ? '📋 보존됨' : '📋 판 보존'}</button>
            )}
            {hunt && hunt.items.some((i) => i.removed) && (
              <span className="mr-2 inline-flex items-center gap-0.5" title="치운 후보 숨기기(−) · 되살려 보기(＋)">
                <span className="text-stone-400 mr-0.5">판 정리</span>
                <button type="button" onClick={() => setShowRemoved(false)} disabled={!showRemoved}
                  className={`w-6 h-6 rounded-lg flex items-center justify-center ${showRemoved ? 'hover:bg-stone-100 text-stone-500' : 'text-stone-300 cursor-default'}`}>−</button>
                <button type="button" onClick={() => setShowRemoved(true)} disabled={showRemoved}
                  className={`w-6 h-6 rounded-lg flex items-center justify-center ${!showRemoved ? 'hover:bg-stone-100 text-stone-500' : 'text-stone-300 cursor-default'}`}>＋</button>
              </span>
            )}
            {hunt && (
              <span className="mr-2 inline-flex items-center border border-stone-200 rounded-lg overflow-hidden">
                <button type="button" onClick={() => setViewMode('grid')} title="그리드(썸네일) 보기"
                  className={`px-2 py-1 ${viewMode === 'grid' ? 'bg-stone-200 text-stone-700' : 'text-stone-400 hover:bg-stone-100'}`}>그리드</button>
                <button type="button" onClick={() => setViewMode('list')} title="목록 보기"
                  className={`px-2 py-1 ${viewMode === 'list' ? 'bg-stone-200 text-stone-700' : 'text-stone-400 hover:bg-stone-100'}`}>목록</button>
              </span>
            )}
            {(hunt || answer || error) && (
              <button type="button" onClick={clearBoard} title="판을 비우고 새로 시작"
                className="mr-2 px-2.5 py-1 rounded-lg hover:bg-stone-100 text-stone-400 hover:text-stone-600 transition">판 비우기</button>
            )}
            <span title="AI가 판 위에 유지할 후보 수">판 크기</span>
            {/* ref 기준 증감 — 연타 시 stale closure 로 한 번만 먹는 것 방지(ref 는 동기 갱신) */}
            <button type="button" onClick={() => setPoolSize(poolSizeRef.current - 1)}
              className="w-6 h-6 rounded-lg hover:bg-stone-100 text-stone-500 flex items-center justify-center">−</button>
            <span className="w-6 text-center text-stone-600 font-medium">{poolSize}</span>
            <button type="button" onClick={() => setPoolSize(poolSizeRef.current + 1)}
              className="w-6 h-6 rounded-lg hover:bg-stone-100 text-stone-500 flex items-center justify-center">＋</button>
          </div>

          {error && <div className="mt-6 text-sm text-rose-500">{error}</div>}

          {searching && <div className="mt-8 text-center text-sm text-stone-400">포식 중… 가볼 만한 곳을 찾고 있어요</div>}

          {/* 사냥판 — AI가 채우고 인간이 치우고(✕)·담는(📌) 후보 풀. 클릭=webview 진입. */}
          {hunt && hunt.items.length > 0 && (() => {
            // 제거된 아이템은 항상 활성 후보(판 크기까지) 뒤에 — showRemoved(＋)여도 상위 순위를 차지하지 못하게.
            const visible = showRemoved
              ? [...hunt.items.filter((it) => !it.removed), ...hunt.items.filter((it) => it.removed)]
              : hunt.items.filter((it) => !it.removed);
            return (
            <div className="mt-6 pb-12">
              {hunt.intro && <div className="text-sm text-stone-500 mb-3">{hunt.intro}</div>}
              {visible.length === 0 && (
                <div className="text-center text-xs text-stone-400 py-6">치운 후보를 숨겼어요 (판 정리 ＋ 로 다시 보기)</div>
              )}
              <div className={viewMode === 'grid' ? 'grid grid-cols-2 sm:grid-cols-3 gap-3' : 'grid grid-cols-1 md:grid-cols-2 gap-x-3 gap-y-1'}>
                {visible.map((it) => (
                  viewMode === 'grid'
                    ? <PoolCard key={it.id} item={it} drag={dragProps(it)} dragOver={dragOverId === it.id} onOpen={() => openPoolItem(it)} onRemove={() => removePoolItem(it)} onRestore={() => restorePoolItem(it)} onSave={() => savePoolFav(it)} />
                    : <PoolRow key={it.id} item={it} drag={dragProps(it)} dragOver={dragOverId === it.id} onOpen={() => openPoolItem(it)} onRemove={() => removePoolItem(it)} onRestore={() => restorePoolItem(it)} onSave={() => savePoolFav(it)} />
                ))}
              </div>
              {refilling && (
                <div className="mt-3 text-center text-xs text-stone-400">치운 만큼 채우는 중…</div>
              )}
              {hunt.outro && <div className="mt-3 text-xs text-stone-400">{hunt.outro}</div>}
            </div>
            );
          })()}

          {/* 목적지 카드 (MAP 마커 등) — 클릭하면 webview 진입 */}
          {destinations.length > 0 && (
            <div className="mt-6 space-y-2">
              {destinations.map((d, i) => (
                <button key={i} onClick={() => openTab(d.url)}
                  className="w-full text-left p-3 rounded-xl border border-stone-200 hover:border-stone-300 hover:bg-stone-50 transition">
                  <div className="text-sm font-medium text-stone-800">{d.label}</div>
                  {d.meta && <div className="text-xs text-stone-500 mt-0.5">{d.meta}</div>}
                  <div className="text-[11px] text-sky-600 mt-0.5 truncate">{d.url}</div>
                </button>
              ))}
            </div>
          )}

          {/* 에이전트 본문 — 인라인 링크는 클릭 시 webview 로 */}
          {answer && (
            <div className="mt-6 pb-12 prose prose-sm prose-stone max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      onClick={(e) => { e.preventDefault(); if (href) openTab(href); }}
                      className="text-sky-600 hover:underline cursor-pointer"
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {answer}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      {/* 도로 — 탭별 크로미움 webview. 열려 있으면 전부 mount 유지(세션·페이지 보존), 활성 탭만 보임.
          검색홈(mode!=='browse')이면 스택 전체를 숨긴다. partition persist:forage 로 탭끼리 세션 공유. */}
      <div className={`flex-1 min-h-0 bg-stone-100 ${mode === 'browse' ? 'block' : 'hidden'}`}>
        {open && tabs.map((t) => (
          <div key={t.id} className="w-full h-full"
            style={{ display: mode === 'browse' && t.id === activeId ? 'block' : 'none' }}>
            {t.kind === 'favorites'
              ? <FavoritesPage favorites={favorites} onOpen={openTab} onRemove={removeFavorite} />
              : t.kind === 'history'
                ? <HistoryPage onOpen={openTab} active={mode === 'browse' && t.id === activeId} />
                : t.kind === 'library'
                  ? <BoardsPage onOpenBoard={openBoard} active={mode === 'browse' && t.id === activeId} />
                  : <BrowserTabView tab={t} onUpdate={updateTab} registerRef={registerRef} onOpenTab={openTab} />}
          </div>
        ))}
      </div>
    </div>
  );
}
