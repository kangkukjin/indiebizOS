/**
 * NeighborBrowser — 이웃 창고 인앱 파인더(읽기 전용). 폴러 스냅샷(현재 색인)을
 * 내 창고 탭(MinePane)과 같은 아이콘 그리드 문법으로 보여준다. 피드가 '변화의 강'이면
 * 여기는 '현재의 창고' — 전체를 보러 외부 브라우저로 이탈하지 않는다.
 * 데이터=GET /warehouse-feed/browse (폴링이 모아둔 로컬 DB, 창고 왕복 0).
 * 클릭 한 번 = 폴더 진입/파일 열기(브라우저 관례 — 편집이 없어 선택이 필요 없다).
 */
import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, ChevronRight, ExternalLink, Folder, RefreshCw } from 'lucide-react';
import { API, fmtBytes, fileIcon, openExternalUrl, openWarehouseInBrowser, IMG_EXT } from './shared';
import type { WfBrowseDir, WfFeedItem } from './shared';
import { ChipActions } from './FeedCard';

interface Props {
  url: string;
  name: string;
  /** 피드 카드의 폴더 칩에서 들어올 때 — 그 폴더를 바로 연다 */
  initialPath?: string;
  onBack: () => void;
  onLike: (f: WfFeedItem) => Promise<void> | void;
  onRetweet: (f: WfFeedItem) => void;
}

export function NeighborBrowser({ url, name, initialPath, onBack, onLike, onRetweet }: Props) {
  const [path, setPath] = useState(initialPath || '');
  const [dirs, setDirs] = useState<WfBrowseDir[]>([]);
  const [files, setFiles] = useState<WfFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (p: string) => {
    try {
      const r = await fetch(
        `${API}/warehouse-feed/browse?url=${encodeURIComponent(url)}&path=${encodeURIComponent(p)}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setDirs(d.dirs || []);
      setFiles(d.files || []);
      setTotal(d.total || 0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [url]);

  useEffect(() => { load(path); }, [path, load]);
  // 다른 이웃·다른 폴더 칩으로 갈아타면 그 자리로 (initialPath 없으면 루트부터)
  useEffect(() => { setPath(initialPath || ''); }, [url, initialPath]);

  // 지금 둘러보기 — 스냅샷이 오래됐을 때 이 창고만 폴링하고 다시 읽는다.
  const pollThis = useCallback(async () => {
    setBusy(true);
    try {
      await fetch(`${API}/warehouse-feed/poll`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
    } catch { /* 재조회가 진실 */ }
    setBusy(false);
    load(path);
  }, [url, path, load]);

  const like = useCallback(async (f: WfFeedItem) => {
    await onLike(f);
    load(path);                                // 좋아요 수는 로컬 스냅샷에 쌓인다 — 재조회로 반영
  }, [onLike, load, path]);

  const crumbs = path ? path.split('/') : [];

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* 헤더 — 피드로 복귀 · 이웃 이름 · 경로 부스러기 · 외부 열기 */}
      <div className="px-5 py-2.5 border-b border-stone-200 bg-white/60 shrink-0 flex items-center gap-2 text-sm">
        <button
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-stone-500 hover:text-[#D97706] hover:bg-amber-50 text-xs"
          onClick={onBack}
        >
          <ArrowLeft className="w-3.5 h-3.5" /> 피드
        </button>
        <div className="flex items-center gap-1 min-w-0 flex-1">
          <button
            className={`font-medium truncate ${path ? 'text-stone-500 hover:text-[#D97706] hover:underline' : 'text-stone-800'}`}
            onClick={() => setPath('')}
          >
            {name}
          </button>
          {crumbs.map((seg, i) => (
            <span key={i} className="flex items-center gap-1 min-w-0">
              <ChevronRight className="w-3.5 h-3.5 text-stone-300 shrink-0" />
              <button
                className={`truncate ${i === crumbs.length - 1 ? 'text-stone-800' : 'text-stone-500 hover:text-[#D97706] hover:underline'}`}
                onClick={() => setPath(crumbs.slice(0, i + 1).join('/'))}
              >
                {seg}
              </button>
            </span>
          ))}
        </div>
        <span className="text-[11px] text-stone-400 shrink-0">파일 {total}개</span>
        <button
          className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
          title="이 창고만 지금 둘러보기 (스냅샷 새로고침)"
          onClick={pollThis}
        >
          <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
        </button>
        <button
          className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
          title="브라우저로 창고 열기 (이웃 쪽 표면)"
          onClick={() => openWarehouseInBrowser(url + '/')}
        >
          <ExternalLink className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {error && (
          <div className="mx-5 mt-3 px-3 py-2 text-xs rounded-lg bg-red-50 text-red-600 border border-red-100">
            {error}
          </div>
        )}
        {dirs.length === 0 && files.length === 0 && !error ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            <Folder className="w-10 h-10" />
            <p className="text-sm">이 폴더엔 아직 아무것도 없어요</p>
            <p className="text-xs">마지막 둘러보기 이후 상대가 올렸을 수 있어요 — ↻ 로 새로고침</p>
          </div>
        ) : (
          <ul className="px-4 py-3 grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-1 content-start">
            {dirs.map((d) => (
              <li
                key={`d:${d.name}`}
                className="flex flex-col items-center gap-1 p-2 rounded-xl cursor-pointer select-none min-w-0 hover:bg-stone-100"
                title={`${d.name}\n${d.count}개 · ${fmtBytes(d.bytes)}`}
                onClick={() => setPath(path ? `${path}/${d.name}` : d.name)}
              >
                <Folder className="w-12 h-12 shrink-0 text-[#F59E0B]" strokeWidth={1.2} />
                <span className="w-full text-[11px] leading-tight text-center break-all line-clamp-2 text-stone-700">
                  {d.name}
                </span>
              </li>
            ))}
            {files.map((f) => {
              const label = f.path.split('/').pop() || f.path;
              const Icon = fileIcon(label);
              const isImg = IMG_EXT.test(label);
              return (
                <li
                  key={f.path}
                  className="group/chip relative flex flex-col items-center gap-1 p-2 rounded-xl cursor-pointer select-none min-w-0 hover:bg-stone-100"
                  title={`${label}\n${fmtBytes(f.bytes || 0)} · ${(f.mtime || '').replace('T', ' ')}`}
                  onClick={() => openExternalUrl(f.url)}
                >
                  {isImg ? (
                    <img
                      src={f.url}
                      loading="lazy"
                      className="w-14 h-14 rounded-lg object-cover bg-stone-100 shrink-0 pointer-events-none"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  ) : (
                    <Icon className="w-12 h-12 shrink-0 text-stone-400" strokeWidth={1.2} />
                  )}
                  <span className="w-full text-[11px] leading-tight text-center break-all line-clamp-2 text-stone-700">
                    {label}
                  </span>
                  {(f.likes || 0) > 0 && (
                    <span className="absolute left-1 top-1 px-1 rounded bg-white/85 text-[10px] text-rose-500">♥{f.likes}</span>
                  )}
                  <ChipActions f={f} onLike={like} onRetweet={onRetweet} />
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
