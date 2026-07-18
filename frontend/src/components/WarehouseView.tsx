/**
 * WarehouseView — 공유창고 런처 표면. 두 탭:
 *
 * [내 창고] 레벨(0 손님 ~ 4 가족)을 고르면 보이는 폴더(공유창고/<level>/)가 바뀌고,
 *   드래그앤드롭=물리 복사 투입(그 레벨부터 공개면 /manifest·/f 에 즉시 서빙).
 *   빼기는 공유창고/휴지통/<level>/ 이동(가역). 백엔드: /portal/warehouse-admin/*.
 * [이웃] 창고이웃 등기부(이웃 DB 의 창고 축) + 변화 피드(트위터식 타임라인) + 전수 검색.
 *   폴러(warehouse_feed.py)가 이웃 매니페스트를 30분 주기 폴링(AI·토큰 0) — 여기선
 *   그 결과를 읽고, 클릭=이웃의 공개 창고가 브라우저로 열림(이웃 쪽 표면 재사용, 신규 0).
 *   백엔드: /warehouse-feed/*. 둘 다 로컬 전용 — 터널·Worker 미노출.
 */
import { useCallback, useEffect, useState } from 'react';
import { Package, RefreshCw, FilePlus, Trash2, Download, ExternalLink, FileText, Film, Music, Archive, File as FileIcon, Users, Search, Plus, Pencil, Rss, Repeat2, Star } from 'lucide-react';

const API = 'http://127.0.0.1:8765';

interface WhFile { name: string; bytes: number; path: string; mtime: string }
interface WhData {
  title: string; public_url: string; level: number;
  levels: Record<string, number>; files: WhFile[];
  level_labels: Record<string, string>;
}
interface WfNeighbor {
  contact_id: number; neighbor_id: number; name: string; info_level: number;
  warehouse_url: string; warehouse_memo: string; favorite: boolean;
  last_poll: string | null; ok: number | null; error: string | null;
  file_count: number | null; title: string; has_restricted: boolean;
}
interface WfFeedItem {
  id?: number; wh_url: string; path: string; mtime: string; bytes: number;
  url: string; kind?: string; seen_at: string;
  neighbor_name: string; neighbor_home: string;
}

const IMG_EXT = /\.(jpe?g|png|gif|webp)$/i;

function fmtBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)}GB`;
}

function fileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  if (/^(mp4|mov|avi|mkv|webm)$/.test(ext)) return Film;
  if (/^(mp3|m4a|wav|flac|ogg)$/.test(ext)) return Music;
  if (/^(zip|tar|gz|7z|rar)$/.test(ext)) return Archive;
  if (/^(md|txt|pdf|doc|docx|hwp|xlsx|csv)$/.test(ext)) return FileText;
  return FileIcon;
}

function openExternalUrl(url: string) {
  const el = (window as any).electron;
  if (el?.openExternal) el.openExternal(url);
  else window.open(url, '_blank', 'noopener');
}

/** 이웃 창고의 파일 한 줄 — 피드와 검색이 같은 줄을 쓴다. */
function FileRow({ f, onRetweet }: { f: WfFeedItem; onRetweet: (f: WfFeedItem) => void }) {
  const Icon = fileIcon(f.path);
  return (
    <li className="group flex items-center gap-3 px-3 py-2 rounded-xl bg-white border border-stone-200 hover:border-[#D97706]/40">
      <Icon className="w-5 h-5 text-stone-400 shrink-0 mx-1" />
      <div className="flex-1 min-w-0 cursor-pointer" title="파일 열기" onClick={() => openExternalUrl(f.url)}>
        <div className="text-sm text-stone-800 truncate group-hover:text-[#D97706] group-hover:underline">{f.path}</div>
        <div className="text-[11px] text-stone-400">
          <span className="text-[#B45309]/70 mr-1.5">{f.neighbor_name}</span>
          {f.kind === 'new' && <span className="mr-1.5 px-1 rounded bg-amber-100 text-[#B45309]">새 파일</span>}
          {f.kind === 'changed' && <span className="mr-1.5 px-1 rounded bg-stone-100 text-stone-500">갱신</span>}
          {fmtBytes(f.bytes || 0)} · {(f.mtime || '').replace('T', ' ')}
        </div>
      </div>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
        title="파일 열기"
        onClick={() => openExternalUrl(f.url)}
      >
        <ExternalLink className="w-4 h-4" />
      </button>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
        title={`${f.neighbor_name}의 창고 열기`}
        onClick={() => { if (f.neighbor_home) openExternalUrl(f.neighbor_home); }}
      >
        <Package className="w-4 h-4" />
      </button>
      <button
        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
        title="리트윗 — 내 창고에 이 파일을 소개(링크 파일 생성, 레벨 선택)"
        onClick={() => onRetweet(f)}
      >
        <Repeat2 className="w-4 h-4" />
      </button>
    </li>
  );
}

/** 이웃 탭 — 창고이웃 등기부 + [피드 | 검색] 두 섹션. */
function NeighborsPane() {
  const [neighbors, setNeighbors] = useState<WfNeighbor[]>([]);
  const [candidates, setCandidates] = useState<{ id: number; name: string }[]>([]);
  const [feed, setFeed] = useState<WfFeedItem[]>([]);
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
  // 리트윗 레벨 선택 — 레벨은 0~4 숫자일 뿐, 의미는 사용자가 정한다(이름표 붙이지 않음)
  const [retweetPick, setRetweetPick] = useState<{ item: WfFeedItem; level: number } | null>(null);

  const load = useCallback(async () => {
    try {
      const [rn, rf] = await Promise.all([
        fetch(`${API}/warehouse-feed/neighbors`),
        fetch(`${API}/warehouse-feed/feed?limit=100`),
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
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pollAll = useCallback(async () => {
    setBusy('이웃 창고 둘러보는 중…');
    try {
      await fetch(`${API}/warehouse-feed/poll`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
    } catch { /* 재조회가 진실 */ }
    setBusy(null);
    load();
  }, [load]);

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
    load();
  }, [addUrl, addName, addCandidate, load]);

  const removeNeighbor = useCallback(async (contactId: number) => {
    try {
      await fetch(`${API}/warehouse-feed/neighbors/remove`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contact_id: contactId }),
      });
    } catch { /* 재조회가 진실 */ }
    load();
  }, [load]);

  const doRetweet = useCallback(async () => {
    if (!retweetPick) return;
    const { item, level } = retweetPick;
    setRetweetPick(null);
    setBusy('내 창고에 소개하는 중…');
    try {
      const r = await fetch(`${API}/warehouse-feed/retweet`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: item.url, name: item.path, level, warehouse: item.wh_url || '' }),
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

  const toggleFavorite = useCallback(async (neighborId: number) => {
    try {
      const r = await fetch(`${API}/warehouse-feed/neighbors/favorite`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ neighbor_id: neighborId }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    load();
  }, [load]);

  const saveMemo = useCallback(async () => {
    if (!memoEdit) return;
    try {
      await fetch(`${API}/warehouse-feed/neighbors/memo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ neighbor_id: memoEdit.id, memo: memoEdit.text }),
      });
    } catch { /* 재조회가 진실 */ }
    setMemoEdit(null);
    load();
  }, [memoEdit, load]);

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

  const items = sub === 'search' ? (results ?? []) : feed;
  const favorites = neighbors.filter((n) => n.favorite);
  // 창고별 최근 파일 — 피드에 이미 있는 것에서 뽑는다(추가 조회 없음).
  const recentOf = (whUrl: string) => feed.filter((f) => f.wh_url === whUrl).slice(0, 3);

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* 이웃 카드 줄 */}
      <div className="px-5 py-3 border-b border-stone-200 bg-white/60 shrink-0 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          {neighbors.map((n) => (
            <div key={n.contact_id} className="group flex items-center gap-2 pl-2 pr-1.5 py-1.5 rounded-xl bg-white border border-stone-200 text-xs">
              <button
                className={`p-0.5 rounded ${n.favorite ? 'text-[#D97706]' : 'text-stone-300 hover:text-[#D97706]'}`}
                title={n.favorite ? '즐겨찾기 해제' : '즐겨찾기 — 즐겨찾기 탭에 모아 보여요'}
                onClick={() => toggleFavorite(n.neighbor_id)}
              >
                <Star className={`w-3.5 h-3.5 ${n.favorite ? 'fill-current' : ''}`} />
              </button>
              <button
                className="font-medium text-stone-700 hover:text-[#D97706] hover:underline"
                title={`${n.title || n.name} 창고 열기\n${n.warehouse_url}`}
                onClick={() => openExternalUrl(n.warehouse_url + '/')}
              >
                {n.name}
              </button>
              <span className={`px-1.5 rounded-full ${n.ok === 0 ? 'bg-red-50 text-red-500' : 'bg-stone-100 text-stone-500'}`}>
                {n.ok === 0 ? '연결 안 됨' : `${n.file_count ?? '?'}개`}
              </span>
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
            <span className="text-stone-500 shrink-0">에 링크 파일로 소개</span>
            <button className="px-3 py-1.5 rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]" onClick={doRetweet}>소개하기</button>
            <button className="px-3 py-1.5 rounded-lg border border-stone-200 text-stone-500 hover:text-stone-700" onClick={() => setRetweetPick(null)}>취소</button>
          </div>
        )}

        {/* 섹션 — 피드(변화) | 검색(현재) | 즐겨찾기(자주 가는 창고). */}
        <div className="flex items-center gap-1">
          {([['feed', '피드', Rss], ['search', '검색', Search], ['favorites', '즐겨찾기', Star]] as const).map(([key, label, SubIcon]) => (
            <button
              key={key}
              onClick={() => setSub(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                sub === key ? 'bg-amber-50 text-[#B45309] font-medium' : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <SubIcon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
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

      {/* 피드(변화) / 검색 결과(현재) */}
      <div className="flex-1 min-h-0 overflow-auto">
        {error && (
          <div className="mx-5 mt-3 px-3 py-2 text-xs rounded-lg bg-red-50 text-red-600 border border-red-100">{error}</div>
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
              <p className="text-xs">위 이웃 칩의 ☆ 를 누르면 그 창고가 여기 모입니다</p>
            </div>
          ) : (
            <ul className="px-5 py-3 space-y-2">
              {favorites.map((n) => {
                const recent = recentOf(n.warehouse_url);
                return (
                  <li key={n.contact_id} className="px-4 py-3 rounded-xl bg-white border border-stone-200 hover:border-[#D97706]/40">
                    <div className="flex items-center gap-2">
                      <Star className="w-4 h-4 text-[#D97706] fill-current shrink-0" />
                      <button
                        className="text-sm font-medium text-stone-800 hover:text-[#D97706] hover:underline truncate"
                        title={`${n.warehouse_url} 열기`}
                        onClick={() => openExternalUrl(n.warehouse_url + '/')}
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
                        onClick={() => openExternalUrl(n.warehouse_url + '/')}
                      >
                        <ExternalLink className="w-4 h-4" />
                      </button>
                      <button
                        className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
                        title="즐겨찾기 해제"
                        onClick={() => toggleFavorite(n.neighbor_id)}
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
        ) : items.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            {sub === 'search' ? <Search className="w-10 h-10" /> : <Rss className="w-10 h-10" />}
            <p className="text-sm">{sub === 'search' ? `'${q.trim()}' 이(가) 든 파일 이름이 없어요` : '아직 새 소식이 없어요'}</p>
            {sub === 'search' && <p className="text-xs">이웃이 아직 안 올렸거나, 마지막 둘러보기 뒤에 올렸을 수 있어요</p>}
          </div>
        ) : (
          <ul className="px-5 py-3 space-y-1.5">
            {items.map((f) => (
              <FileRow
                key={`${f.wh_url}:${f.id ?? f.path}:${f.seen_at}`}
                f={f}
                onRetweet={(picked) => setRetweetPick({ item: picked, level: 0 })}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function WarehouseView() {
  const [tab, setTab] = useState<'mine' | 'neighbors'>(() =>
    localStorage.getItem('indiebiz_warehouse_tab') === 'neighbors' ? 'neighbors' : 'mine');
  const [level, setLevel] = useState<number>(() => {
    const saved = Number(localStorage.getItem('indiebiz_warehouse_level'));
    return Number.isInteger(saved) && saved >= 0 && saved <= 4 ? saved : 0;
  });
  const [data, setData] = useState<WhData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async (lv: number) => {
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/list?level=${lv}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    localStorage.setItem('indiebiz_warehouse_level', String(level));
    load(level);
  }, [level, load]);

  const addPaths = useCallback(async (paths: string[]) => {
    if (!paths.length) return;
    setBusy(`${paths.length}개 넣는 중…`);
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, paths }),
      });
      const d = await r.json();
      if (d.skipped?.length) {
        setError(`건너뜀 ${d.skipped.length}건: ${d.skipped[0].reason}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
      load(level);
    }
  }, [level, load]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const el = (window as any).electron;
    if (!el?.getPathForFile) {
      setError('파일 경로 배선이 아직 없어요 — 앱을 재시작해 주세요.');
      return;
    }
    const paths: string[] = [];
    for (const f of Array.from(e.dataTransfer.files)) {
      try {
        const p = el.getPathForFile(f);
        if (p) paths.push(p);
      } catch { /* 개별 실패 무시 */ }
    }
    addPaths(paths);
  }, [addPaths]);

  const pickFiles = useCallback(async () => {
    const el = (window as any).electron;
    if (!el?.selectFiles) return;
    const picked: string[] | null = await el.selectFiles();
    if (picked?.length) addPaths(picked);
  }, [addPaths]);

  // 열람 URL — 사진 표시·동영상 재생(비호환 코덱은 서버가 H.264 변환)·텍스트 열람.
  const fileUrl = useCallback(
    (name: string) => `${API}/portal/warehouse-admin/file?level=${level}&name=${encodeURIComponent(name)}`,
    [level],
  );
  const openFile = useCallback((name: string) => {
    const url = fileUrl(name);
    const el = (window as any).electron;
    if (el?.openExternal) el.openExternal(url);   // 기본 브라우저로
    else window.open(url, '_blank', 'noopener');
  }, [fileUrl]);

  const removeFile = useCallback(async (name: string) => {
    try {
      await fetch(`${API}/portal/warehouse-admin/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, name }),
      });
    } catch { /* 재조회가 진실 */ }
    load(level);
  }, [level, load]);

  const hasElectron = typeof (window as any).electron?.selectFiles === 'function';

  return (
    <div className="h-full w-full flex flex-col bg-stone-50">
      {/* 헤더 */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-stone-200 bg-white shrink-0">
        <Package className="w-5 h-5 text-[#D97706]" />
        <span className="font-semibold text-stone-800">{data?.title || '공유창고'}</span>
        {data?.public_url && (
          <button
            className="flex items-center gap-1 text-xs text-stone-400 hover:text-[#D97706] ml-1"
            title="공개 주소 열기"
            onClick={() => (window as any).electron?.openExternal?.(data.public_url)}
          >
            {data.public_url.replace(/^https?:\/\//, '')}
            <ExternalLink className="w-3 h-3" />
          </button>
        )}
        {/* 탭 — 내 창고(발신) / 이웃(수신·피드) */}
        <div className="flex items-center gap-1 ml-3 p-0.5 rounded-lg bg-stone-100">
          {([['mine', '내 창고', Package], ['neighbors', '이웃', Users]] as const).map(([key, label, TabIcon]) => (
            <button
              key={key}
              onClick={() => { setTab(key); localStorage.setItem('indiebiz_warehouse_tab', key); }}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs transition-colors ${
                tab === key ? 'bg-white text-[#B45309] shadow-sm font-medium' : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <TabIcon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        {tab === 'mine' && busy && <span className="text-xs text-stone-500 animate-pulse">{busy}</span>}
        {tab === 'mine' && hasElectron && (
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309]"
            onClick={pickFiles}
          >
            <FilePlus className="w-3.5 h-3.5" /> 파일 넣기
          </button>
        )}
        {tab === 'mine' && (
          <button
            className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100"
            title="새로고침"
            onClick={() => load(level)}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}
      </div>

      {tab === 'neighbors' && <NeighborsPane />}

      {tab === 'mine' && (<>
      {/* 레벨 탭 — 선택 = 보이는 폴더 전환 */}
      <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-stone-200 bg-white/60 shrink-0">
        {[0, 1, 2, 3, 4].map((lv) => {
          const active = lv === level;
          const count = data?.levels?.[String(lv)] ?? 0;
          return (
            <button
              key={lv}
              onClick={() => setLevel(lv)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border transition-colors ${
                active
                  ? 'bg-[#D97706] border-[#D97706] text-white'
                  : 'bg-white border-stone-200 text-stone-600 hover:border-[#D97706]/50'
              }`}
            >
              <span className="font-medium">레벨 {lv}</span>
              <span className={`px-1.5 rounded-full ${active ? 'bg-white/25' : 'bg-stone-100 text-stone-500'}`}>{count}</span>
            </button>
          );
        })}
        <span className="ml-2 text-[11px] text-stone-400">
          레벨 {level} 이상 이웃에게 보입니다 {level === 0 ? '(누구나)' : ''}
        </span>
      </div>

      {/* 폴더 뷰 = 드롭존 */}
      <div
        className={`flex-1 min-h-0 overflow-auto relative ${dragOver ? 'bg-amber-50' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOver(false); }}
        onDrop={onDrop}
      >
        {dragOver && (
          <div className="absolute inset-3 z-10 border-2 border-dashed border-[#D97706] rounded-2xl flex items-center justify-center pointer-events-none bg-amber-50/80">
            <div className="text-[#B45309] font-medium">
              레벨 {level} 창고에 넣기
            </div>
          </div>
        )}

        {error && (
          <div className="mx-5 mt-3 px-3 py-2 text-xs rounded-lg bg-red-50 text-red-600 border border-red-100">
            {error}
          </div>
        )}

        {!data ? (
          <div className="h-full flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-stone-200 border-t-stone-600 rounded-full animate-spin" />
          </div>
        ) : data.files.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            <Package className="w-10 h-10" />
            <p className="text-sm">비어 있어요 — 파일을 끌어다 놓으세요</p>
          </div>
        ) : (
          <ul className="px-5 py-3 space-y-1.5">
            {data.files.map((f) => {
              const Icon = fileIcon(f.name);
              const isImg = IMG_EXT.test(f.name);
              return (
                <li
                  key={f.name}
                  className="group flex items-center gap-3 px-3 py-2 rounded-xl bg-white border border-stone-200 hover:border-[#D97706]/40"
                >
                  {isImg ? (
                    <img
                      src={fileUrl(f.name)}
                      className="w-10 h-10 rounded-lg object-cover bg-stone-100 shrink-0 cursor-pointer"
                      onClick={() => openFile(f.name)}
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  ) : (
                    <Icon className="w-5 h-5 text-stone-400 shrink-0 mx-2.5" />
                  )}
                  <div
                    className="flex-1 min-w-0 cursor-pointer"
                    title="열기 (사진 보기 · 동영상 재생 · 텍스트 읽기)"
                    onClick={() => openFile(f.name)}
                  >
                    <div className="text-sm text-stone-800 truncate group-hover:text-[#D97706] group-hover:underline">{f.name}</div>
                    <div className="text-[11px] text-stone-400">{fmtBytes(f.bytes)} · {f.mtime.replace('T', ' ')}</div>
                  </div>
                  <a
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 transition-opacity"
                    title="내려받기"
                    href={`${fileUrl(f.name)}&download=1`}
                    download
                  >
                    <Download className="w-4 h-4" />
                  </a>
                  <button
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-stone-400 hover:text-red-500 hover:bg-red-50 transition-opacity"
                    title="빼기 (휴지통으로 이동 — Finder에서 복구 가능)"
                    onClick={() => removeFile(f.name)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      </>)}
    </div>
  );
}
