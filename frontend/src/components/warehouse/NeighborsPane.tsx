/**
 * NeighborsPane — 이웃 탭. 창고이웃 등기부(이웃 DB 의 창고 축) + 변화 피드(카드
 * 타임라인, cards=1) + 전수 검색 + 즐겨찾기 + 인앱 파인더(NeighborBrowser).
 * 폴러(warehouse_feed.py)가 이웃 매니페스트를 30분 주기 폴링(AI·토큰 0) — 피드는
 * 그 '변화의 강'을 카드로, 파인더는 스냅샷의 '현재의 창고' 전체를 보여준다(이웃
 * 이름 클릭). 백엔드: /warehouse-feed/*.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Package, RefreshCw, Trash2, ExternalLink, Search, Plus, Pencil, Rss, Repeat2,
  Star, Heart, KeyRound,
} from 'lucide-react';
import { API, fmtBytes, fileIcon, openExternalUrl, openWarehouseInBrowser } from './shared';
import type { WfNeighbor, WfFeedItem, WfCard } from './shared';
import { FeedCard } from './FeedCard';
import { NeighborBrowser } from './NeighborBrowser';
import { useRetryingLoad } from '../../lib/use-retrying-load';

/** 이웃 창고의 파일 한 줄 — 검색 결과가 쓴다(행마다 이웃이 달라 행 단위가 맞다).
    피드는 FeedCard(카드 단위), 전체 열람은 NeighborBrowser(파인더)가 맡는다. */
function FileRow({ f, onRetweet, onLike, label }: { f: WfFeedItem; onRetweet: (f: WfFeedItem) => void; onLike: (f: WfFeedItem) => void; label?: string }) {
  const Icon = fileIcon(f.path);
  return (
    <li className="group flex items-center gap-3 px-3 py-2 rounded-xl bg-white border border-stone-200 hover:border-[#D97706]/40">
      <Icon className="w-5 h-5 text-stone-400 shrink-0 mx-1" />
      <div className="flex-1 min-w-0 cursor-pointer" title={f.path} onClick={() => openExternalUrl(f.url)}>
        <div className="text-sm text-stone-800 truncate group-hover:text-[#D97706] group-hover:underline">{label ?? f.path}</div>
        <div className="text-[11px] text-stone-400">
          <span className="text-[#B45309]/70 mr-1.5">{f.neighbor_name}</span>
          {f.kind === 'new' && <span className="mr-1.5 px-1 rounded bg-amber-100 text-[#B45309]">새 파일</span>}
          {f.kind === 'changed' && <span className="mr-1.5 px-1 rounded bg-stone-100 text-stone-500">갱신</span>}
          {fmtBytes(f.bytes || 0)} · {(f.mtime || '').replace('T', ' ')}
        </div>
      </div>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-rose-500 hover:bg-rose-50 flex items-center gap-0.5"
        title="좋아요 — 카운트는 이 파일의 창고 주인에게 쌓입니다"
        onClick={() => onLike(f)}
      >
        <Heart className="w-4 h-4" />
        {(f.likes || 0) > 0 && <span className="text-[11px] tabular-nums">{f.likes}</span>}
      </button>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
        title="파일 열기"
        onClick={() => openExternalUrl(f.url)}
      >
        <ExternalLink className="w-4 h-4" />
      </button>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
        title={`${f.neighbor_name}의 창고 열기 — 파일 링크 우클릭으로 리트윗`}
        onClick={() => { if (f.neighbor_home) openWarehouseInBrowser(f.neighbor_home); }}
      >
        <Package className="w-4 h-4" />
      </button>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
        title="리트윗 — 내 창고 리트윗 폴더에 소개(링크=추천 / 복사=소장·재서빙, 레벨 선택)"
        onClick={() => onRetweet(f)}
      >
        <Repeat2 className="w-4 h-4" />
      </button>
    </li>
  );
}

/** 이웃 탭 — 창고이웃 등기부 + [피드 | 검색 | 즐겨찾기] 섹션 + 인앱 파인더. */
export function NeighborsPane() {
  const [neighbors, setNeighbors] = useState<WfNeighbor[]>([]);
  const [candidates, setCandidates] = useState<{ id: number; name: string }[]>([]);
  const [feed, setFeed] = useState<WfCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addName, setAddName] = useState('');
  const [addCandidate, setAddCandidate] = useState<number | ''>('');
  const [addUrl, setAddUrl] = useState('');
  const [sub, setSub] = useState<'feed' | 'search' | 'favorites'>('feed');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<'recent' | 'match'>('recent');
  const [results, setResults] = useState<WfFeedItem[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [memoEdit, setMemoEdit] = useState<{ id: number; text: string } | null>(null);
  const [loginEdit, setLoginEdit] = useState<{ url: string; name: string; user: string; pw: string } | null>(null);
  // 리트윗 레벨 선택 — 레벨은 0~4 숫자일 뿐, 의미는 사용자가 정한다(이름표 붙이지 않음)
  const [retweetPick, setRetweetPick] = useState<{ item: WfFeedItem; level: number; mode: 'link' | 'copy' } | null>(null);
  // 피드 필터 — 내가 이웃에게 준 레벨(이상) + 내가 창고에 준 즐겨찾기 점수(이상).
  // 두 축은 독립(레벨=접근 계약 / 점수=내 평가). 레벨·점수 모두 숫자, 의미 라벨 없음.
  const [feedMinLevel, setFeedMinLevel] = useState(0);
  const [feedMinScore, setFeedMinScore] = useState(0);
  // 인앱 파인더 — 이웃 이름·카드 헤더·폴더 칩 클릭으로 그 창고의 스냅샷을 앱 안에서 연다.
  const [browse, setBrowse] = useState<{ url: string; name: string; path?: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [rn, rf] = await Promise.all([
        fetch(`${API}/warehouse-feed/neighbors`),
        fetch(`${API}/warehouse-feed/feed?limit=50&cards=1&min_level=${feedMinLevel}&min_score=${feedMinScore}`),
      ]);
      if (!rn.ok || !rf.ok) throw new Error(`HTTP ${rn.status}/${rf.status}`);
      const dn = await rn.json();
      const df = await rf.json();
      setNeighbors(dn.neighbors || []);
      setCandidates(dn.candidates || []);
      setFeed(df.items || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;                        // 실패를 굳히지 않는다 — 훅이 백오프 재시도
    }
  }, [feedMinLevel, feedMinScore]);

  const { retry, retrying } = useRetryingLoad(load);

  const pollAll = useCallback(async () => {
    setBusy('이웃 창고 둘러보는 중…');
    try {
      await fetch(`${API}/warehouse-feed/poll`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
    } catch { /* 재조회가 진실 */ }
    setBusy(null);
    retry();
  }, [retry]);

  const addNeighbor = useCallback(async () => {
    if (!addUrl.trim()) return;
    setBusy('창고 등록·첫 폴링 중…');
    try {
      // 이름을 비우면 서버가 창고 제목(매니페스트 title)·호스트명으로 이웃을 만든다
      // — 창고주소만 아는 상대도 주소가 곧 연락처라 정상 이웃.
      const body: Record<string, unknown> = { url: addUrl.trim() };
      if (addCandidate !== '') body.neighbor_id = addCandidate;
      else if (addName.trim()) body.name = addName.trim();
      const r = await fetch(`${API}/warehouse-feed/neighbors/add`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        throw new Error(d?.detail || `HTTP ${r.status}`);
      }
      setAddOpen(false); setAddName(''); setAddUrl(''); setAddCandidate('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(null);
    retry();
  }, [addUrl, addName, addCandidate, retry]);

  const removeNeighbor = useCallback(async (contactId: number) => {
    try {
      await fetch(`${API}/warehouse-feed/neighbors/remove`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contact_id: contactId }),
      });
    } catch { /* 재조회가 진실 */ }
    retry();
  }, [retry]);

  // 좋아요 — 카운터는 파일 주인(그 창고)이 센다. 응답 count 로 화면·로컬 스냅샷 즉시 갱신.
  const doLike = useCallback(async (f: WfFeedItem) => {
    try {
      const r = await fetch(`${API}/warehouse-feed/like`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wh_url: f.wh_url, path: f.path }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        throw new Error(d?.detail || `HTTP ${r.status}`);
      }
      const d = await r.json();
      const hit = (x: WfFeedItem) => x.wh_url === f.wh_url && x.path === f.path;
      setFeed((cur) => cur.map((c) => ({
        ...c, items: c.items.map((y) => (hit(y) ? { ...y, likes: d.count } : y)),
      })));
      setResults((cur) => (cur ? cur.map((x) => (hit(x) ? { ...x, likes: d.count } : x)) : cur));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const doRetweet = useCallback(async () => {
    if (!retweetPick) return;
    const { item, level, mode } = retweetPick;
    setRetweetPick(null);
    setBusy(mode === 'copy' ? '파일을 내 창고로 복사하는 중…' : '내 창고에 소개하는 중…');
    try {
      const r = await fetch(`${API}/warehouse-feed/retweet`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: item.url, name: item.path, level, mode, warehouse: item.wh_url || '' }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        throw new Error(d?.detail || `HTTP ${r.status}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(null);
  }, [retweetPick]);

  // DM — 메신저 창을 이 창고 주인(이웃)의 대화로 딥링크 (localStorage 핸드오프,
  // MessengerInstrumentView 가 마운트/storage 이벤트로 소비 — DiscoverPane 과 동일 경로).
  const openDm = useCallback((whUrl: string) => {
    const nb = neighbors.find((n) => n.warehouse_url === whUrl);
    if (!nb) return;
    localStorage.setItem('indiebiz_messenger_dm_nid', String(nb.neighbor_id));
    const el = (window as any).electron;
    if (el?.openMessengerWindow) el.openMessengerWindow();
    else window.location.hash = '#/messenger';   // 브라우저 폴백 (런처 연락처 버튼과 동일)
  }, [neighbors]);

  // 즐겨찾기 점수(0~3) — 내가 이 창고에 주는 평가. 키=창고 url(창고=주소가 정체).
  const setScore = useCallback(async (url: string, score: number) => {
    try {
      const r = await fetch(`${API}/warehouse-feed/score`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, score }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    retry();
  }, [retry]);

  const saveMemo = useCallback(async () => {
    if (!memoEdit) return;
    try {
      await fetch(`${API}/warehouse-feed/neighbors/memo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ neighbor_id: memoEdit.id, memo: memoEdit.text }),
      });
    } catch { /* 재조회가 진실 */ }
    setMemoEdit(null);
    retry();
  }, [memoEdit, retry]);

  // 창고 계정 저장(빈 아이디=해제) — 서버가 즉시 로그인 확인 + 성공 시 재폴링까지 한다.
  const saveLogin = useCallback(async (clear = false) => {
    if (!loginEdit) return;
    setBusy(clear ? '로그인 해제 중…' : '로그인 확인 중…');
    try {
      const r = await fetch(`${API}/warehouse-feed/credentials`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: loginEdit.url,
          user_id: clear ? '' : loginEdit.user.trim(),
          password: clear ? '' : loginEdit.pw,
        }),
      });
      const d = await r.json().catch(() => null);
      if (!r.ok) throw new Error(d?.detail || `HTTP ${r.status}`);
      if (!clear && !d?.ok) throw new Error(d?.error || '로그인에 실패했어요');
      setLoginEdit(null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(null);
    retry();
  }, [loginEdit, retry]);

  const doSearch = useCallback(async (query: string, order: 'recent' | 'match') => {
    const t = query.trim();
    if (!t) { setResults(null); setSearching(false); return; }
    setSearching(true);
    try {
      const r = await fetch(
        `${API}/warehouse-feed/search?q=${encodeURIComponent(t)}&sort=${order}&limit=300`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setResults(d.items || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setSearching(false);
  }, []);

  // 타자마다 서버를 때리지 않도록 잠깐 묵힌다 (검색어·정렬 어느 쪽이 바뀌어도 같은 경로).
  useEffect(() => {
    if (sub !== 'search') return;
    const t = setTimeout(() => doSearch(q, sort), 200);
    return () => clearTimeout(t);
  }, [q, sort, sub, doSearch]);

  // 즐겨찾기 탭 = 점수 준 창고(점수 높은 순 — 정렬이 곧 점수의 첫 쓸모)
  const favorites = neighbors.filter((n) => (n.score ?? 0) > 0)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  // 창고별 최근 파일 — 피드 카드에 이미 있는 것에서 뽑는다(추가 조회 없음).
  const recentOf = (whUrl: string) =>
    feed.filter((c) => c.wh_url === whUrl).flatMap((c) => c.items).slice(0, 3);

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* 이웃 카드 줄 */}
      <div className="px-5 py-3 border-b border-stone-200 bg-white/60 shrink-0 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          {neighbors.map((n) => (
            <div key={n.contact_id} className="group flex items-center gap-2 pl-2 pr-1.5 py-1.5 rounded-xl bg-white border border-stone-200 text-xs">
              <button
                className={`flex items-center gap-0.5 p-0.5 rounded ${(n.score ?? 0) > 0 ? 'text-[#D97706]' : 'text-stone-300 hover:text-[#D97706]'}`}
                title={`즐겨찾기 점수 ${n.score ?? 0} — 누르면 0→1→2→3 순환. 점수는 피드 필터·즐겨찾기 탭이 씁니다 (내 평가라 상대에겐 안 보여요)`}
                onClick={() => setScore(n.warehouse_url, ((n.score ?? 0) + 1) % 4)}
              >
                <Star className={`w-3.5 h-3.5 ${(n.score ?? 0) > 0 ? 'fill-current' : ''}`} />
                {(n.score ?? 0) > 0 && <span className="text-[10px] font-semibold">{n.score}</span>}
              </button>
              <button
                className="font-medium text-stone-700 hover:text-[#D97706] hover:underline"
                title={`${n.title || n.name} 창고를 앱 안에서 둘러보기\n${n.warehouse_url}`}
                onClick={() => setBrowse({ url: n.warehouse_url, name: n.title || n.name })}
              >
                {n.name}
              </button>
              <span className={`px-1.5 rounded-full ${n.ok === 0 ? 'bg-red-50 text-red-500' : 'bg-stone-100 text-stone-500'}`}>
                {n.ok === 0 ? '연결 안 됨' : `${n.file_count ?? '?'}개`}
              </span>
              {n.adapter && n.adapter !== 'native' && (
                <span
                  className="px-1.5 rounded-full bg-sky-50 text-sky-600"
                  title="창고 방언 — indiebizOS 창고가 아닌 표면(색인·RSS·Nextcloud·페이지)을 어댑터가 읽어옵니다"
                >
                  {n.adapter_label || n.adapter}
                </span>
              )}
              {/* 회원 로그인 상태 — 계정으로 폴링하면 승급받은 레벨의 파일까지 피드에 들어온다 */}
              {n.login_user && n.login_ok === 1 && (
                <span
                  className="px-1.5 rounded-full bg-emerald-50 text-emerald-600"
                  title={`'${n.login_user}' 계정으로 폴링 중 — 이 창고가 나에게 준 레벨`}
                >
                  레벨 {n.viewer_level ?? '?'}
                </span>
              )}
              {n.login_user && n.login_ok === 0 && (
                <span
                  className="px-1.5 rounded-full bg-red-50 text-red-500"
                  title={`로그인 실패: ${n.login_error || '원인 미상'} — 열쇠 버튼으로 다시 등록하세요`}
                >
                  로그인 실패
                </span>
              )}
              {(!n.adapter || n.adapter === 'native') && (
                <button
                  className={`p-1 rounded opacity-0 group-hover:opacity-100 ${n.login_user ? 'text-emerald-500 hover:text-emerald-600' : 'text-stone-300 hover:text-[#D97706]'}`}
                  title="이 창고에 내가 가입한 계정 등록 — 폴러가 로그인해 승급받은 레벨로 읽어요"
                  onClick={() => setLoginEdit({ url: n.warehouse_url, name: n.name, user: n.login_user || '', pw: '' })}
                >
                  <KeyRound className="w-3 h-3" />
                </button>
              )}
              <button
                className="p-1 rounded text-stone-300 hover:text-[#D97706] opacity-0 group-hover:opacity-100"
                title={n.warehouse_memo ? `창고 메모: ${n.warehouse_memo}` : '창고 메모 쓰기'}
                onClick={() => setMemoEdit({ id: n.neighbor_id, text: n.warehouse_memo })}
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                className="p-1 rounded text-stone-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                title="등기부에서 떼기 (이웃은 남고 창고 연락처만 지움)"
                onClick={() => removeNeighbor(n.contact_id)}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
          <button
            className="flex items-center gap-1 px-3 py-1.5 rounded-xl border border-dashed border-stone-300 text-xs text-stone-500 hover:border-[#D97706] hover:text-[#D97706]"
            onClick={() => setAddOpen((v) => !v)}
          >
            <Plus className="w-3.5 h-3.5" /> 창고이웃 등록
          </button>
          <div className="flex-1" />
          {busy && <span className="text-xs text-stone-500 animate-pulse">{busy}</span>}
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]"
            title="모든 이웃 창고를 지금 둘러보기 (평소엔 30분마다 자동)"
            onClick={pollAll}
          >
            <RefreshCw className="w-3.5 h-3.5" /> 지금 둘러보기
          </button>
        </div>

        {addOpen && (
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <select
              className="px-2 py-1.5 rounded-lg border border-stone-200 bg-white text-stone-700"
              value={addCandidate}
              onChange={(e) => setAddCandidate(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">새 이웃으로…</option>
              {candidates.map((c) => <option key={c.id} value={c.id}>기존 이웃: {c.name}</option>)}
            </select>
            {addCandidate === '' && (
              <input
                className="px-2 py-1.5 rounded-lg border border-stone-200 w-44"
                placeholder="이웃 이름 (비우면 창고 제목)"
                value={addName}
                onChange={(e) => setAddName(e.target.value)}
              />
            )}
            <input
              className="px-2 py-1.5 rounded-lg border border-stone-200 flex-1 min-w-[220px]"
              placeholder="창고 주소 (https://…)"
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') addNeighbor(); }}
            />
            <button
              className="px-3 py-1.5 rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]"
              onClick={addNeighbor}
            >
              등록
            </button>
          </div>
        )}

        {loginEdit && (
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <KeyRound className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            <span className="text-stone-500 shrink-0">{loginEdit.name} 창고 내 계정:</span>
            <input
              autoFocus
              className="px-2 py-1.5 rounded-lg border border-stone-200 w-36"
              placeholder="아이디"
              value={loginEdit.user}
              onChange={(e) => setLoginEdit({ ...loginEdit, user: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Escape') setLoginEdit(null); }}
            />
            <input
              type="password"
              className="px-2 py-1.5 rounded-lg border border-stone-200 w-36"
              placeholder="비밀번호"
              value={loginEdit.pw}
              onChange={(e) => setLoginEdit({ ...loginEdit, pw: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') saveLogin(); if (e.key === 'Escape') setLoginEdit(null); }}
            />
            <button className="px-3 py-1.5 rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]" onClick={() => saveLogin()}>로그인 확인·저장</button>
            {neighbors.find((n) => n.warehouse_url === loginEdit.url)?.login_user && (
              <button className="px-3 py-1.5 rounded-lg border border-stone-200 text-stone-500 hover:text-red-500 hover:border-red-300" onClick={() => saveLogin(true)}>해제</button>
            )}
            <span className="text-stone-400">가입은 창고 홈에서 — 여기엔 그때 만든 아이디·비밀번호를 넣어요</span>
          </div>
        )}

        {memoEdit && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-stone-500 shrink-0">창고 메모 — {neighbors.find((n) => n.neighbor_id === memoEdit.id)?.name}:</span>
            <input
              autoFocus
              className="px-2 py-1.5 rounded-lg border border-stone-200 flex-1"
              placeholder="이 창고에 뭐가 사는지 (예: 부동산 자료가 많은 창고)"
              value={memoEdit.text}
              onChange={(e) => setMemoEdit({ ...memoEdit, text: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') saveMemo(); if (e.key === 'Escape') setMemoEdit(null); }}
            />
            <button className="px-3 py-1.5 rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]" onClick={saveMemo}>저장</button>
          </div>
        )}

        {retweetPick && (
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <Repeat2 className="w-3.5 h-3.5 text-[#B45309] shrink-0" />
            <span className="text-stone-600 truncate max-w-[280px]">'{retweetPick.item.path}'</span>
            <span className="text-stone-500 shrink-0">을(를) 내 창고 레벨</span>
            <select
              className="px-2 py-1.5 rounded-lg border border-stone-200 bg-white text-stone-700"
              value={retweetPick.level}
              onChange={(e) => setRetweetPick({ ...retweetPick, level: Number(e.target.value) })}
            >
              {[0, 1, 2, 3, 4].map((lv) => <option key={lv} value={lv}>{lv}</option>)}
            </select>
            <span className="text-stone-500 shrink-0">의 리트윗 폴더에</span>
            {/* 링크=추천(포인터, 원 창고 직행·저장 0) / 복사=전파·소유(내 창고가 재서빙, 원본 꺼져도 생존) */}
            <select
              className="px-2 py-1.5 rounded-lg border border-stone-200 bg-white text-stone-700"
              value={retweetPick.mode}
              onChange={(e) => setRetweetPick({ ...retweetPick, mode: e.target.value as 'link' | 'copy' })}
            >
              <option value="link">링크로 소개 (원 창고 직행)</option>
              <option value="copy">복사해 소장 (내 창고가 서빙)</option>
            </select>
            <button className="px-3 py-1.5 rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]" onClick={doRetweet}>리트윗</button>
            <button className="px-3 py-1.5 rounded-lg border border-stone-200 text-stone-500 hover:text-stone-700" onClick={() => setRetweetPick(null)}>취소</button>
          </div>
        )}

        {/* 섹션 — 피드(변화) | 검색(현재) | 즐겨찾기(자주 가는 창고). */}
        <div className="flex items-center gap-1">
          {([['feed', '피드', Rss], ['search', '검색', Search], ['favorites', '즐겨찾기', Star]] as const).map(([key, label, SubIcon]) => (
            <button
              key={key}
              onClick={() => { setSub(key); setBrowse(null); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                sub === key ? 'bg-amber-50 text-[#B45309] font-medium' : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <SubIcon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
          {/* 피드 필터 — 두 독립 축: 내가 이웃에게 준 레벨(접근 계약) + 내가 창고에 준
              즐겨찾기 점수(평가). 레벨·점수 모두 숫자, 의미 라벨 없음. */}
          {sub === 'feed' && (
            <div className="ml-auto flex items-center gap-1.5">
              <select
                className="px-2 py-1 rounded-lg border border-stone-200 bg-white text-xs text-stone-600"
                value={feedMinLevel}
                onChange={(e) => setFeedMinLevel(Number(e.target.value))}
                title="이 레벨 이상의 이웃이 보낸 소식만"
              >
                <option value={0}>모든 레벨</option>
                {[1, 2, 3, 4].map((lv) => <option key={lv} value={lv}>레벨 {lv} 이상</option>)}
              </select>
              <select
                className={`px-2 py-1 rounded-lg border text-xs ${
                  feedMinScore > 0 ? 'border-[#D97706] bg-amber-50 text-[#B45309]' : 'border-stone-200 bg-white text-stone-600'
                }`}
                value={feedMinScore}
                onChange={(e) => setFeedMinScore(Number(e.target.value))}
                title="내가 준 즐겨찾기 점수(이상)의 창고만 — 점수는 이웃 칩의 별로 줍니다"
              >
                <option value={0}>즐겨찾기 무관</option>
                {[1, 2, 3].map((s) => <option key={s} value={s}>★{s} 이상</option>)}
              </select>
            </div>
          )}
        </div>

        {/* 전수 파일명 검색 — 폴러 스냅샷 = 내 동네 전체 색인 */}
        {sub === 'search' && (
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <input
              autoFocus
              className="flex-1 px-2 py-1.5 rounded-lg border border-stone-200 text-xs"
              placeholder="이웃 창고 전체에서 파일 이름으로 찾기 (예: 축구)"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <select
              className="px-2 py-1.5 rounded-lg border border-stone-200 bg-white text-xs text-stone-700 shrink-0"
              value={sort}
              onChange={(e) => setSort(e.target.value as 'recent' | 'match')}
              title="결과 순서"
            >
              <option value="recent">최신순</option>
              <option value="match">이름 일치순</option>
            </select>
            {q.trim() && (
              <span className="text-[11px] text-stone-400 shrink-0 w-16 text-right">
                {searching ? '찾는 중…' : `${(results ?? []).length}개`}
              </span>
            )}
          </div>
        )}
      </div>

      {/* 인앱 파인더(현재의 창고 전체) — 피드·검색 위에 겹치지 않고 자리를 대신한다 */}
      {browse ? (
        <NeighborBrowser
          url={browse.url}
          name={browse.name}
          initialPath={browse.path}
          onBack={() => setBrowse(null)}
          onLike={doLike}
          onRetweet={(picked) => setRetweetPick({ item: picked, level: 0, mode: 'link' })}
        />
      ) : (
      <div className="flex-1 min-h-0 overflow-auto">
        {error && (
          <div className="mx-5 mt-3 px-3 py-2 text-xs rounded-lg bg-red-50 text-red-600 border border-red-100 flex items-center gap-2">
            <span className="flex-1">{error}{retrying && <span className="ml-1 text-red-400">— 백엔드를 기다리는 중…</span>}</span>
            <button className="shrink-0 px-2 py-0.5 rounded-md border border-red-200 bg-white hover:bg-red-50"
                    onClick={() => retry()}>다시 시도</button>
          </div>
        )}
        {neighbors.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            <Rss className="w-10 h-10" />
            <p className="text-sm">창고이웃이 아직 없어요 — 위에서 이웃의 창고 주소를 등록하세요</p>
            <p className="text-xs">등록하면 창고의 변화가 여기로 흘러옵니다</p>
          </div>
        ) : sub === 'favorites' ? (
          favorites.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
              <Star className="w-10 h-10" />
              <p className="text-sm">즐겨찾기한 창고가 없어요</p>
              <p className="text-xs">위 이웃 칩의 ☆ 를 눌러 점수(1~3)를 주면 그 창고가 여기 모입니다</p>
            </div>
          ) : (
            <ul className="px-5 py-3 space-y-2">
              {favorites.map((n) => {
                const recent = recentOf(n.warehouse_url);
                return (
                  <li key={n.contact_id} className="px-4 py-3 rounded-xl bg-white border border-stone-200 hover:border-[#D97706]/40">
                    <div className="flex items-center gap-2">
                      {/* 점수만큼 별 — 클릭=순환(3 다음은 1, 해제는 오른쪽 버튼) */}
                      <button
                        className="flex items-center shrink-0"
                        title={`즐겨찾기 점수 ${n.score ?? 0} — 누르면 순환`}
                        onClick={() => setScore(n.warehouse_url, ((n.score ?? 0) % 3) + 1)}
                      >
                        {Array.from({ length: n.score ?? 0 }, (_, k) => (
                          <Star key={k} className="w-4 h-4 text-[#D97706] fill-current" />
                        ))}
                      </button>
                      <button
                        className="text-sm font-medium text-stone-800 hover:text-[#D97706] hover:underline truncate"
                        title={`${n.warehouse_url} — 앱 안에서 둘러보기`}
                        onClick={() => setBrowse({ url: n.warehouse_url, name: n.title || n.name })}
                      >
                        {n.name}
                      </button>
                      {n.title && n.title !== n.name && (
                        <span className="text-xs text-stone-400 truncate">{n.title}</span>
                      )}
                      {n.has_restricted && (
                        <span className="text-[11px] px-1.5 rounded-full bg-stone-100 text-stone-500 shrink-0"
                              title="내 레벨 위에 더 있다는 신호 — 제목은 안 보입니다">더 있음</span>
                      )}
                      <div className="flex-1" />
                      <button
                        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
                        title="창고 열기"
                        onClick={() => openWarehouseInBrowser(n.warehouse_url + '/')}
                      >
                        <ExternalLink className="w-4 h-4" />
                      </button>
                      <button
                        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
                        title="즐겨찾기 해제 (점수 0)"
                        onClick={() => setScore(n.warehouse_url, 0)}
                      >
                        <Star className="w-4 h-4 fill-current" />
                      </button>
                    </div>

                    {n.warehouse_memo && (
                      <p className="mt-1.5 text-xs text-stone-600">{n.warehouse_memo}</p>
                    )}

                    <div className="mt-1.5 text-[11px] text-stone-400 truncate">
                      <span className="text-stone-500">{n.warehouse_url}</span>
                      {' · '}
                      {n.ok === 0
                        ? <span className="text-red-500">연결 안 됨{n.error ? ` (${n.error})` : ''}</span>
                        : <>파일 {n.file_count ?? '?'}개</>}
                      {n.last_poll && ` · 둘러본 때 ${n.last_poll.replace('T', ' ')}`}
                    </div>

                    {recent.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-stone-100 space-y-1">
                        {recent.map((f) => (
                          <button
                            key={`${f.id ?? f.path}:${f.seen_at}`}
                            className="block w-full text-left text-xs text-stone-500 hover:text-[#D97706] truncate"
                            title={`${f.path} 열기`}
                            onClick={() => openExternalUrl(f.url)}
                          >
                            {f.kind === 'new' ? '새 파일 · ' : f.kind === 'changed' ? '갱신 · ' : ''}{f.path}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )
        ) : sub === 'search' && !q.trim() ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            <Search className="w-10 h-10" />
            <p className="text-sm">이웃 창고 {neighbors.length}곳의 파일 이름에서 찾습니다</p>
            <p className="text-xs">찾을 말을 입력하세요 — 지난 둘러보기에서 본 파일 전부가 대상입니다</p>
          </div>
        ) : sub === 'search' ? (
          (results ?? []).length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
              <Search className="w-10 h-10" />
              <p className="text-sm">{`'${q.trim()}' 이(가) 든 파일 이름이 없어요`}</p>
              <p className="text-xs">이웃이 아직 안 올렸거나, 마지막 둘러보기 뒤에 올렸을 수 있어요</p>
            </div>
          ) : (
            <ul className="px-5 py-3 space-y-1.5">
              {(results ?? []).map((f) => (
                <FileRow
                  key={`${f.wh_url}:${f.id ?? f.path}:${f.seen_at}`}
                  f={f}
                  onRetweet={(picked) => setRetweetPick({ item: picked, level: 0, mode: 'link' })}
                  onLike={doLike}
                />
              ))}
            </ul>
          )
        ) : feed.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            <Rss className="w-10 h-10" />
            <p className="text-sm">아직 새 소식이 없어요</p>
          </div>
        ) : (
          <ul className="px-5 py-3 space-y-2">
            {feed.map((c) => (
              <FeedCard
                key={`c:${c.wh_url}:${c.seen_at}:${c.kind}`}
                c={c}
                onRetweet={(picked) => setRetweetPick({ item: picked, level: 0, mode: 'link' })}
                onLike={doLike}
                onDm={openDm}
                onOpenBrowser={(whUrl, path) => {
                  const nb = neighbors.find((n) => n.warehouse_url === whUrl);
                  setBrowse({
                    url: whUrl,
                    name: c.neighbor_title || nb?.title || nb?.name || c.neighbor_name,
                    path,
                  });
                }}
              />
            ))}
          </ul>
        )}
      </div>
      )}
    </div>
  );
}
