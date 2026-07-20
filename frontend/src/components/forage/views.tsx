/**
 * ForageBrowser 서브컴포넌트 층 (2026-07-18 모듈화 — 1500줄 규칙)
 *
 * ForageBrowser.tsx 에서 verbatim 이동: 탭 webview·즐겨찾기/방문기록/판 도서관
 * 내부 페이지·사냥판 행/카드·파비콘·내비 버튼. 본체(모놀리식 상태)와 달리
 * 전부 props 만 받는 독립 컴포넌트라 그대로 옮겨진다.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { API, WebView } from './support';
import type { Tab, PoolItem } from './support';
import { useRetryingLoad } from '../../lib/use-retrying-load';

// 탭 하나 = webview 하나. 자기 네비 이벤트를 부모 Tab 상태로 올리고, 팝업(target=_blank 등)은 새 탭으로.
// src 는 initialUrl 로 최초 1회만 로드 — 이후 이동은 goBack/reload 등 imperative 로만(재로드 튐 방지).
export function BrowserTabView({ tab, onUpdate, registerRef, onOpenTab }: {
  tab: Tab;
  onUpdate: (id: string, patch: Partial<Tab>) => void;
  registerRef: (id: string, el: any) => void;
  onOpenTab: (url: string) => void;
}) {
  const ref = useRef<any>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    registerRef(tab.id, el);
    const sync = (e?: any) => {
      const u = e?.url || el.getURL?.();
      onUpdate(tab.id, {
        url: u || tab.url,
        title: el.getTitle?.() || u || tab.url,
        canBack: !!el.canGoBack?.(),
        canFwd: !!el.canGoForward?.(),
      });
    };
    const onStart = () => onUpdate(tab.id, { loading: true, translated: false });
    const onStop = () => { onUpdate(tab.id, { loading: false }); sync(); };
    const onTitle = (e: any) => onUpdate(tab.id, { title: e?.title || el.getTitle?.() || tab.url });
    const onNew = (e: any) => { if (e?.url) onOpenTab(e.url); };  // target=_blank / window.open → 새 탭
    el.addEventListener('did-navigate', sync);
    el.addEventListener('did-navigate-in-page', sync);
    el.addEventListener('did-start-loading', onStart);
    el.addEventListener('did-stop-loading', onStop);
    el.addEventListener('page-title-updated', onTitle);
    el.addEventListener('new-window', onNew);
    return () => {
      el.removeEventListener('did-navigate', sync);
      el.removeEventListener('did-navigate-in-page', sync);
      el.removeEventListener('did-start-loading', onStart);
      el.removeEventListener('did-stop-loading', onStop);
      el.removeEventListener('page-title-updated', onTitle);
      el.removeEventListener('new-window', onNew);
    };
  }, [tab.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <WebView ref={ref} src={tab.initialUrl} partition="persist:forage" allowpopups="true"
      style={{ width: '100%', height: '100%', border: 'none' }} />
  );
}

// 즐겨찾기 바둑판 페이지 — 스위치로 새 탭에서 열림. 타일 클릭=새 탭으로 방문, 모서리 흰 × =즐겨찾기에서 제거.
export function FavoritesPage({ favorites, onOpen, onRemove }: {
  favorites: { name: string; url: string }[];
  onOpen: (url: string) => void;
  onRemove: (name: string) => void;
}) {
  return (
    <div className="w-full h-full overflow-auto bg-white">
      <div className="max-w-4xl mx-auto px-8 py-10">
        <h2 className="text-2xl font-light tracking-tight text-stone-700 mb-8 text-center">즐겨찾기</h2>
        {favorites.length === 0 ? (
          <div className="text-center text-sm text-stone-400 mt-16">
            아직 즐겨찾기가 없어요. 사이트를 방문해 주소창의 ☆ 를 눌러 담아 보세요.
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-x-4 gap-y-7">
            {favorites.map((f, i) => (
              <div key={i} className="group relative flex flex-col items-center">
                <button onClick={() => onRemove(f.name)} title="즐겨찾기에서 제거"
                  className="absolute -top-1 -right-1 z-10 w-5 h-5 rounded-full bg-white shadow-sm text-stone-500 hover:bg-red-500 hover:text-white text-[11px] leading-none flex items-center justify-center transition">×</button>
                <button onClick={() => onOpen(f.url)} title={f.url}
                  className="flex flex-col items-center gap-2 p-2 rounded-2xl hover:bg-stone-100 transition w-full">
                  <FavIcon url={f.url} name={f.name} />
                  <span className="text-xs leading-tight text-stone-600 text-center line-clamp-2 w-full">{f.name}</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 사냥판 후보 한 줄 — 밀도 우선(한 눈에 여러 개). 파비콘 + 제목 한 줄 + 이유 한 줄로 압축,
// 전체 URL 줄은 뺐다(파비콘·클릭이 대신함). ✕=치우기(가봤으면 '삭제', 아니면 '제외'),
// 치운 건 흐려지고 ↩ 로 복구. 📌=직접 담은 후보, ☆=즐겨찾기 승격. "다녀옴 N초"가 체류 신호.
export function PoolRow({ item, onOpen, onRemove, onRestore, onSave, drag, dragOver }: {
  item: PoolItem; onOpen: () => void; onRemove: () => void; onRestore: () => void; onSave: () => void;
  drag?: React.HTMLAttributes<HTMLDivElement>; dragOver?: boolean;
}) {
  const removed = !!item.removed;
  return (
    <div {...drag} className={`flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-lg border transition ${
      removed ? 'border-transparent bg-stone-50 opacity-50' : 'border-stone-200 hover:border-stone-300 hover:bg-stone-50 cursor-grab active:cursor-grabbing'
    }${dragOver ? ' ring-2 ring-sky-400' : ''}`}>
      <span className="shrink-0"><TabFav url={item.url} /></span>
      <button onClick={onOpen} disabled={removed} className="flex-1 min-w-0 text-left">
        <div className={`flex items-baseline gap-1.5 ${removed ? 'line-through' : ''}`}>
          {item.source === 'human' && <span title="브라우징 중 직접 담은 후보" className="shrink-0">📌</span>}
          <span className="text-[13px] font-medium text-stone-800 truncate">{item.title}</span>
          {item.visited && item.source !== 'human' && (
            <span className="shrink-0 text-[10px] text-stone-400">· 다녀옴{item.dwellMs >= 1000 ? ` ${Math.round(item.dwellMs / 1000)}초` : ''}</span>
          )}
        </div>
        {item.reason && <div className="text-[11px] text-stone-500 truncate" title={item.reason}>{item.reason}</div>}
      </button>
      {removed ? (
        <button onClick={onRestore} title="되살리기"
          className="shrink-0 w-6 h-6 rounded-lg text-stone-400 hover:bg-stone-200 hover:text-stone-600 text-sm flex items-center justify-center">↩</button>
      ) : (
        <>
          <button onClick={onSave} title="즐겨찾기로 저장"
            className="shrink-0 w-6 h-6 rounded-lg text-stone-300 hover:bg-amber-50 hover:text-amber-500 text-sm flex items-center justify-center">☆</button>
          <button onClick={onRemove} title={item.visited ? '가봤는데 아님 — 치우기' : '아님 — 치우기'}
            className="shrink-0 w-6 h-6 rounded-lg text-stone-300 hover:bg-stone-200 hover:text-stone-600 text-sm flex items-center justify-center">✕</button>
        </>
      )}
    </div>
  );
}

// 사냥판 후보 카드(그리드) — 썸네일(대표 이미지) + 제목 + 한 줄 이유. 발견용(사진으로 한눈에 스캔).
// PoolRow 와 같은 동작(✕치우기·📌·☆승격·↩복구·다녀옴·치운 카드 흐리기), 배치만 카드 코너로.
export function PoolCard({ item, onOpen, onRemove, onRestore, onSave, drag, dragOver }: {
  item: PoolItem; onOpen: () => void; onRemove: () => void; onRestore: () => void; onSave: () => void;
  drag?: React.HTMLAttributes<HTMLDivElement>; dragOver?: boolean;
}) {
  const removed = !!item.removed;
  return (
    <div {...drag} className={`group relative rounded-xl border overflow-hidden transition ${
      removed ? 'border-transparent bg-stone-50 opacity-50' : 'border-stone-200 hover:border-stone-300 cursor-grab active:cursor-grabbing'
    }${dragOver ? ' ring-2 ring-sky-400 ring-offset-1' : ''}`}>
      <button onClick={onOpen} disabled={removed} className="block w-full">
        <CardThumb url={item.url} image={item.image} />
      </button>
      {/* 왼쪽 위 — 직접 담음(📌) 또는 체류 배지 */}
      {item.source === 'human' ? (
        <span className="absolute top-1.5 left-1.5 w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-[11px] flex items-center justify-center" title="직접 담음">📌</span>
      ) : (item.visited && item.dwellMs >= 1000 && (
        <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded bg-white/90 border border-stone-200 text-[10px] text-stone-500">다녀옴 {Math.round(item.dwellMs / 1000)}초</span>
      ))}
      {/* 오른쪽 위 — 액션(호버 시 노출). 치운 카드는 ↩ 복구만 상시. */}
      <div className="absolute top-1.5 right-1.5 flex gap-1">
        {removed ? (
          <button onClick={onRestore} title="되살리기"
            className="w-6 h-6 rounded-full bg-white/90 border border-stone-200 text-stone-500 hover:text-stone-700 text-xs flex items-center justify-center">↩</button>
        ) : (
          <>
            <button onClick={onSave} title="즐겨찾기로 저장"
              className="w-6 h-6 rounded-full bg-white/90 border border-stone-200 text-stone-400 hover:text-amber-500 text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition">☆</button>
            <button onClick={onRemove} title={item.visited ? '가봤는데 아님 — 치우기' : '아님 — 치우기'}
              className="w-6 h-6 rounded-full bg-white/90 border border-stone-200 text-stone-400 hover:text-stone-700 text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition">✕</button>
          </>
        )}
      </div>
      <button onClick={onOpen} disabled={removed} className="block w-full text-left px-2.5 py-2">
        <div className={`text-[13px] font-medium text-stone-800 truncate ${removed ? 'line-through' : ''}`}>{item.title}</div>
        {item.reason && <div className="text-[11px] text-stone-500 mt-0.5 line-clamp-2" title={item.reason}>{item.reason}</div>}
      </button>
    </div>
  );
}

// 카드 썸네일 — 대표 이미지가 있으면 표시, 없으면(undefined 로딩 중·'' 부재·로드 실패) 파비콘 폴백.
function CardThumb({ url, image }: { url: string; image?: string }) {
  const [err, setErr] = useState(false);
  let host = '';
  try { host = new URL(url).hostname; } catch { /* 잘못된 URL */ }
  if (image && !err) {
    return (
      <div className="w-full aspect-[16/9] bg-stone-100">
        <img src={image} alt="" onError={() => setErr(true)} className="w-full h-full object-cover" />
      </div>
    );
  }
  return (
    <div className="w-full aspect-[16/9] bg-stone-100 flex items-center justify-center">
      {host
        ? <img src={`https://www.google.com/s2/favicons?sz=64&domain=${host}`} alt="" className="w-8 h-8 opacity-50" />
        : <span className="text-stone-300 text-xl">◦</span>}
    </div>
  );
}

// 방문 기록 페이지 — 전부 기록·수동 삭제. 행 클릭=새 탭 방문, ×=개별 삭제, 전체 비우기, 검색.
export function HistoryPage({ onOpen, active }: { onOpen: (url: string) => void; active: boolean }) {
  const [items, setItems] = useState<{ id: number; ts: string; url: string; title: string; hunt_query: string }[]>([]);
  const [q, setQ] = useState('');
  const load = useCallback(async (query = '') => {
    try {
      const r = await fetch(`${API}/forage/history?limit=300${query ? `&q=${encodeURIComponent(query)}` : ''}`);
      const d = await r.json();
      setItems(Array.isArray(d.items) ? d.items : []);
    } catch (e) {
      setItems([]);
      throw e;                        // 실패를 굳히지 않는다 — 훅이 백오프 재시도
    }
  }, []);
  // 탭이 보일 때마다 최신 목록 — 브라우징하다 돌아와도 방금 방문이 반영되게.
  // 검색어는 ref 로 읽는다(타자마다 재조회하지 않게 — 조회는 활성화·제출 때만).
  const qRef = useRef(q); qRef.current = q;
  useRetryingLoad(useCallback(() => load(qRef.current), [load]), { enabled: active });
  const del = async (id: number) => {
    try { await fetch(`${API}/forage/history/${id}`, { method: 'DELETE' }); setItems((p) => p.filter((i) => i.id !== id)); } catch { /* */ }
  };
  const clearAll = async () => {
    if (!window.confirm('방문 기록을 전부 지울까요?')) return;
    try { await fetch(`${API}/forage/history`, { method: 'DELETE' }); setItems([]); } catch { /* */ }
  };
  return (
    <div className="w-full h-full overflow-auto bg-white">
      <div className="max-w-3xl mx-auto px-8 py-10">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-light tracking-tight text-stone-700">방문 기록</h2>
          <button onClick={clearAll}
            className="px-3 py-1.5 rounded-lg text-xs text-stone-400 hover:bg-red-50 hover:text-red-500 transition">전체 비우기</button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); load(q).catch(() => { /* 빈 목록 반영됨 */ }); }} className="mb-4">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="기록 검색"
            className="w-full px-3 py-2 rounded-xl border border-stone-200 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-stone-300" />
        </form>
        {items.length === 0 ? (
          <div className="text-center text-sm text-stone-400 mt-16">기록이 없어요.</div>
        ) : (
          <div className="space-y-0.5">
            {items.map((it) => (
              <div key={it.id} className="group flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-stone-50">
                <button onClick={() => onOpen(it.url)} className="flex-1 min-w-0 text-left flex items-baseline gap-2">
                  <span className="text-sm text-stone-700 truncate">{it.title || it.url}</span>
                  <span className="text-[11px] text-stone-400 truncate hidden sm:inline">{it.url}</span>
                </button>
                <span className="text-[11px] text-stone-400 whitespace-nowrap">{(it.ts || '').replace('T', ' ').slice(5, 16)}</span>
                <button onClick={() => del(it.id)} title="이 기록 삭제"
                  className="w-6 h-6 rounded text-stone-300 hover:bg-stone-200 hover:text-stone-600 text-xs opacity-0 group-hover:opacity-100 transition">×</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 판 도서관 페이지 — 보존한 판들을 카드로. 클릭=그 판 펼치기, ×=삭제. 목록은 미리보기만(가벼움),
// 펼칠 땐 개별 GET 으로 전체 상태를 당긴다(내가 떠난 그대로).
export function BoardsPage({ onOpenBoard, active }: {
  onOpenBoard: (b: { id: string; name: string; state: any }) => void;
  active: boolean;
}) {
  const [boards, setBoards] = useState<{ id: string; name: string; ts: string; updated: string; count: number; preview: string[] }[]>([]);
  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/forage/boards`);
      const d = await r.json();
      setBoards(Array.isArray(d.items) ? d.items : []);
    } catch (e) {
      setBoards([]);
      throw e;                        // 실패를 굳히지 않는다 — 훅이 백오프 재시도
    }
  }, []);
  // 탭이 보일 때마다 최신 목록 — 방금 보존한 판이 반영되게.
  useRetryingLoad(load, { enabled: active });
  const open = async (id: string) => {
    try {
      const r = await fetch(`${API}/forage/boards/${id}`);
      const d = await r.json();
      if (d?.ok) onOpenBoard({ id: d.id, name: d.name, state: d.state });
    } catch { /* */ }
  };
  const del = async (id: string) => {
    try { await fetch(`${API}/forage/boards/${id}`, { method: 'DELETE' }); setBoards((p) => p.filter((b) => b.id !== id)); } catch { /* */ }
  };
  return (
    <div className="w-full h-full overflow-auto bg-white">
      <div className="max-w-4xl mx-auto px-8 py-10">
        <h2 className="text-2xl font-light tracking-tight text-stone-700 mb-8 text-center">판 도서관</h2>
        {boards.length === 0 ? (
          <div className="text-center text-sm text-stone-400 mt-16">
            아직 보존한 판이 없어요. 사냥판에서 '판 보존'을 켜면 여기 남아요.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {boards.map((b) => (
              <div key={b.id} className="group relative rounded-2xl border border-stone-200 hover:border-stone-300 hover:bg-stone-50 transition">
                <button onClick={() => del(b.id)} title="이 판 삭제"
                  className="absolute top-2 right-2 z-10 w-6 h-6 rounded-full bg-stone-100 text-stone-400 hover:bg-red-500 hover:text-white text-xs leading-none flex items-center justify-center opacity-0 group-hover:opacity-100 transition">×</button>
                <button onClick={() => open(b.id)} className="w-full text-left p-4">
                  <div className="flex items-baseline gap-2 mb-1.5 pr-6">
                    <span className="text-sm font-medium text-stone-800 truncate">{b.name || '(제목 없음)'}</span>
                    <span className="shrink-0 text-[11px] text-stone-400">후보 {b.count}</span>
                  </div>
                  <div className="space-y-0.5">
                    {(b.preview || []).map((p, i) => (
                      <div key={i} className="text-[11px] text-stone-500 truncate">· {p}</div>
                    ))}
                  </div>
                  <div className="mt-2 text-[10px] text-stone-400">{(b.updated || '').replace('T', ' ').slice(0, 16)}</div>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 탭 파비콘(작게). 실패/무효 URL 은 점(◦)으로.
export function TabFav({ url }: { url: string }) {
  const [err, setErr] = useState(false);
  let host = '';
  try { host = new URL(url).hostname; } catch { /* 잘못된 URL */ }
  if (err || !host) return <span className="w-4 h-4 shrink-0 text-stone-400 text-[10px] flex items-center justify-center">◦</span>;
  return <img src={`https://www.google.com/s2/favicons?sz=32&domain=${host}`} alt="" onError={() => setErr(true)}
    className="w-4 h-4 shrink-0 rounded-sm" />;
}

// 즐겨찾기 타일 아이콘 — 사이트 파비콘, 실패 시 첫 글자 배지로 폴백.
function FavIcon({ url, name }: { url: string; name: string }) {
  const [err, setErr] = useState(false);
  let host = '';
  try { host = new URL(url).hostname; } catch { /* 잘못된 URL */ }
  if (err || !host) {
    const initial = (name || host || '?').trim().charAt(0).toUpperCase();
    return (
      <div className="w-12 h-12 rounded-2xl bg-stone-200 text-stone-500 flex items-center justify-center text-lg font-medium">
        {initial || '?'}
      </div>
    );
  }
  return (
    <img
      src={`https://www.google.com/s2/favicons?sz=64&domain=${host}`}
      alt=""
      onError={() => setErr(true)}
      className="w-12 h-12 rounded-2xl bg-white border border-stone-100 object-contain p-2"
    />
  );
}

export function NavBtn({ onClick, disabled, label, title }: { onClick: () => void; disabled?: boolean; label: string; title: string }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className={`w-8 h-8 rounded-lg text-base flex items-center justify-center transition ${
        disabled ? 'text-stone-300 cursor-default' : 'text-stone-600 hover:bg-stone-200'
      }`}>
      {label}
    </button>
  );
}
