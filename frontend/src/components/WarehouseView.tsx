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
import { Package, RefreshCw, FilePlus, Trash2, Download, ExternalLink, FileText, Film, Music, Archive, File as FileIcon, Users, Search, Plus, Pencil, Rss, Repeat2, Star, Folder, ChevronRight, Globe, Building2, Heart } from 'lucide-react';
import { runIBL } from './generic/manifest';
import { useRetryingLoad } from '../lib/use-retrying-load';
import { BusinessInstrumentView } from './BusinessInstrumentView';

const API = 'http://127.0.0.1:8765';

interface WhFile { name: string; bytes: number; path: string; mtime: string }
interface WhData {
  title: string; public_url: string; level: number;
  levels: Record<string, number>; files: WhFile[];
  level_labels: Record<string, string>;
  root_path?: string; folder_path?: string;
}
interface WfNeighbor {
  contact_id: number; neighbor_id: number; name: string; info_level: number;
  warehouse_url: string; warehouse_memo: string; favorite: boolean;
  last_poll: string | null; ok: number | null; error: string | null;
  file_count: number | null; title: string; has_restricted: boolean;
}
interface WfFeedItem {
  id?: number; wh_url: string; path: string; mtime: string; bytes: number;
  url: string; kind?: string; seen_at: string; likes?: number;
  neighbor_name: string; neighbor_home: string;
  /* 폴더 단위로 접힌 줄 — 한 폴링에서 같은 폴더에 GROUP_MIN 이상 들어왔을 때.
     원장은 파일 단위 그대로고 여기 표현만 접힌다(warehouse_feed._group_feed). */
  group?: boolean; folder?: string; count?: number; items?: WfFeedItem[];
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

/* 창고 안 상대경로("매매/망의 시대.txt")를 폴더 트리로 되접는다. 임의 깊이.
   표시만 짧아지고(파일명), 열기·내려받기·빼기의 키는 전체 경로 f.name 그대로 쓴다. */
/* path = 창고 루트 기준 폴더 경로(루트는 ''). 드래그 이동의 목적지 키로 쓴다. */
interface WhNode { dirs: Record<string, WhNode>; files: { f: WhFile; label: string }[]; path: string }

function whTree(files: WhFile[]): WhNode {
  const root: WhNode = { dirs: {}, files: [], path: '' };
  for (const f of files) {
    const parts = f.name.split('/');
    let node = root;
    for (const seg of parts.slice(0, -1)) {
      if (!node.dirs[seg]) {
        node.dirs[seg] = { dirs: {}, files: [], path: node.path ? `${node.path}/${seg}` : seg };
      }
      node = node.dirs[seg];
    }
    node.files.push({ f, label: parts[parts.length - 1] });
  }
  return root;
}

/* 창고 안 드래그 = 이 MIME 로 옮길 항목의 상대경로를 싣는다. 바깥에서 끌어온 파일
   투입(dataTransfer.files)과 구별하는 표식 — 없으면 둘이 같은 drop 핸들러에서 엉킨다. */
const WH_DRAG = 'application/x-indiebiz-warehouse-path';

/* 폴더 요약 = 하위 전체 개수·크기 + 가장 최근 mtime(폴더 정렬 키 — 목록이 최신순이므로) */
function whAgg(node: WhNode): { count: number; bytes: number; mtime: string } {
  let count = node.files.length;
  let bytes = node.files.reduce((s, { f }) => s + (f.bytes || 0), 0);
  let mtime = node.files.reduce((m, { f }) => (f.mtime > m ? f.mtime : m), '');
  for (const sub of Object.values(node.dirs)) {
    const a = whAgg(sub);
    count += a.count;
    bytes += a.bytes;
    if (a.mtime > mtime) mtime = a.mtime;
  }
  return { count, bytes, mtime };
}

function openExternalUrl(url: string) {
  const el = (window as any).electron;
  if (el?.openExternal) el.openExternal(url);
  else window.open(url, '_blank', 'noopener');
}

/** 이웃 창고 방문은 내부(포식) 브라우저로 — 창틀이 내 것이어야 파일 링크 우클릭 리트윗이 산다.
    Launcher 가 'indiebiz:open-forage-url' 을 받아 브라우저 오버레이를 그 URL 로 연다. */
function openWarehouseInBrowser(url: string) {
  window.dispatchEvent(new CustomEvent('indiebiz:open-forage-url', { detail: url }));
}

/** 이웃 창고의 파일 한 줄 — 피드와 검색이 같은 줄을 쓴다. */
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

/** 폴더 단위로 접힌 피드 줄 — "이웃이 폴더 하나를 올렸다"를 한 줄로. 펼치면 안의 파일들. */
function GroupRow({ g, onRetweet, onLike }: { g: WfFeedItem; onRetweet: (f: WfFeedItem) => void; onLike: (f: WfFeedItem) => void }) {
  const shown = g.items || [];
  const rest = (g.count || shown.length) - shown.length;
  return (
    <li>
      <details className="group/fd rounded-xl bg-white border border-stone-200">
        <summary className="flex items-center gap-3 px-3 py-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
          <ChevronRight className="w-4 h-4 text-stone-400 shrink-0 transition-transform group-open/fd:rotate-90" />
          <Folder className="w-5 h-5 text-stone-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm text-stone-800 truncate">{g.folder}</div>
            <div className="text-[11px] text-stone-400">
              <span className="text-[#B45309]/70 mr-1.5">{g.neighbor_name}</span>
              {g.kind === 'new' && <span className="mr-1.5 px-1 rounded bg-amber-100 text-[#B45309]">새 파일 {g.count}개</span>}
              {g.kind === 'changed' && <span className="mr-1.5 px-1 rounded bg-stone-100 text-stone-500">갱신 {g.count}개</span>}
              {g.kind === 'seed' && <span className="mr-1.5 px-1 rounded bg-stone-100 text-stone-500">{g.count}개</span>}
              {fmtBytes(g.bytes || 0)} · {(g.mtime || '').replace('T', ' ')}
            </div>
          </div>
          <button
            className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
            title={`${g.neighbor_name}의 창고 열기`}
            onClick={(e) => { e.preventDefault(); if (g.neighbor_home) openWarehouseInBrowser(g.neighbor_home); }}
          >
            <Package className="w-4 h-4" />
          </button>
        </summary>
        <ul className="pl-4 pr-2 pb-2 space-y-1.5 border-l border-stone-100 ml-5">
          {shown.map((f) => (
            <FileRow
              key={`${f.wh_url}:${f.id ?? f.path}`}
              f={{ ...f, neighbor_name: g.neighbor_name, neighbor_home: g.neighbor_home }}
              label={f.path.split('/').pop()}
              onRetweet={onRetweet}
              onLike={onLike}
            />
          ))}
          {rest > 0 && (
            <li className="px-3 py-1.5 text-[11px] text-stone-400">
              외 {rest}개 — 창고를 열어 전부 보기
            </li>
          )}
        </ul>
      </details>
    </li>
  );
}

/** 이웃찾기 탭 — #IndieNet 발견 노트(소개발행)의 수신면.
 *  런처 IndieNet 창의 보드 스트림과 같은 데이터([others:feed]{op:"read"}, 활성 보드 #indienet)를
 *  창고 문맥으로 보여준다: 소개 본문의 "공유창고 : <url>" 을 파싱해 그 자리에서
 *  창고이웃 등록(/warehouse-feed/neighbors/add)으로 잇는다 — 소개발행(발신)의 짝. */
function DiscoverPane() {
  interface IntroItem { author: string; author_full: string; content: string; time: string; id?: string }
  const [items, setItems] = useState<IntroItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const r = (await runIBL('[others:feed]{op: "read", limit: 50}')) as Record<string, unknown>;
      if (r?.error) throw new Error(String(r.error));
      // 보드 통화는 채팅방 관례(과거→최신)로 온다 — 게시판형 목록은 최신 글이 맨 위.
      const arr = Array.isArray(r?.items) ? (r.items as IntroItem[]) : [];
      setItems(arr.slice().reverse());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      throw e;                        // 실패를 굳히지 않는다 — 훅이 백오프 재시도
    }
    setBusy(false);
  }, []);
  const { retry, retrying } = useRetryingLoad(load);

  // 소개 본문에서 공유창고 주소를 뽑는다 — 계약: "공유창고 Warehouse : <url>" 라벨
  // (indienet_publish.publish_intro, 한/영 병기). ★키워드 게이트: "공유창고"와 "warehouse"가
  // **둘 다** 있어야 창고 글로 간주 — 정식 발행은 항상 병기하므로, 잡담에 한쪽 단어가
  // 등장해도 버튼이 안 붙는다(+URL 존재까지 삼중 조건). 라벨 형식이 아니면 마지막 URL 폴백.
  const whUrlOf = (content: string): string | null => {
    if (!(/공유창고/.test(content) && /warehouse/i.test(content))) return null;
    const m = content.match(/(?:공유창고|warehouse)[^\n]*?:\s*(https?:\/\/\S+)/i);
    if (m) return m[1];
    const urls = content.match(/https?:\/\/\S+/g);
    return urls?.length ? urls[urls.length - 1] : null;
  };
  const openUrl = (url: string) => {
    const el = (window as any).electron;
    if (el?.openExternal) el.openExternal(url);
    else window.open(url, '_blank', 'noopener');
  };
  // 본문 속 URL을 클릭 가능한 링크로 — Electron 창 안 내비게이션을 막고 기본 브라우저로 연다.
  const linkify = (text: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    const re = /https?:\/\/\S+/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(text))) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      const url = m[0];
      parts.push(
        <a
          key={k++}
          href={url}
          className="text-[#B45309] underline underline-offset-2 hover:text-[#D97706] break-all"
          title="브라우저로 열기"
          onClick={(e) => { e.preventDefault(); openUrl(url); }}
        >{url}</a>,
      );
      last = m.index + url.length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return parts;
  };
  // 작성자 클릭 = DM — 이웃이면 그 이웃으로, 아니면 npub 로 이웃 등록부터([others:neighbor] save 는
  // npub 멱등: 같은 npub 이웃이 있으면 그대로 반환). 그 뒤 메신저 창을 그 이웃의 대화로 딥링크
  // (localStorage 핸드오프 — MessengerInstrumentView 가 마운트/storage 이벤트로 소비).
  const openDm = async (it: IntroItem) => {
    const npub = it.author_full || '';
    if (!npub.startsWith('npub')) { window.alert('작성자의 nostr 주소를 확인할 수 없어요.'); return; }
    try {
      const r = (await runIBL(
        `[others:neighbor]{op: "save", name: ${JSON.stringify(it.author)}, npub: ${JSON.stringify(npub)}}`,
      )) as Record<string, unknown>;
      const nb = (r?.neighbor ?? null) as { id?: number } | null;
      if (!nb?.id) throw new Error(String(r?.error || r?.message || '이웃 등록 실패'));
      localStorage.setItem('indiebiz_messenger_dm_nid', String(nb.id));
      const el = (window as any).electron;
      if (el?.openMessengerWindow) el.openMessengerWindow();
      else window.location.hash = '#/messenger';   // 브라우저 폴백 (런처 연락처 버튼과 동일)
    } catch (e) {
      window.alert(`DM 열기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // 게시판처럼 한마디 — [others:feed]{op:"post"} 로 #IndieNet 보드에 kind:1 발행(커뮤니티 계기와 동일 경로).
  // 소개만이 아니라 일반 대화도 이 스트림에서 오간다. ★내용은 JSON.stringify 로 이스케이프(따옴표·줄바꿈).
  const postMsg = async () => {
    const t = draft.trim();
    if (!t || posting) return;
    setPosting(true);
    try {
      const r = (await runIBL(`[others:feed]{op: "post", content: ${JSON.stringify(t)}}`)) as Record<string, unknown>;
      if (r?.error || r?.success === false) throw new Error(String(r.error || r.message || '게시 실패'));
      setDraft('');
      await retry();  // 릴레이 반영이 늦으면 목록에 아직 없을 수 있다 — 새로고침으로 다시 확인
    } catch (e) {
      window.alert(`게시 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
    setPosting(false);
  };

  // npub = 소개 작성자의 서명 신원 — 서버가 창고(풀)+nostr(푸시) 두 접점을 한 이웃에 모으고,
  // 같은 npub 의 기존 이웃이 있으면 새 레코드 대신 그에게 창고를 단다(신원 앵커).
  const addNeighbor = async (url: string, npub: string) => {
    try {
      const body: Record<string, unknown> = { url };
      if (npub) body.npub = npub;
      const r = await fetch(`${API}/warehouse-feed/neighbors/add`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => null);
        throw new Error(d?.detail || `HTTP ${r.status}`);
      }
      setAdded((a) => ({ ...a, [url]: true }));
      window.alert('창고이웃으로 등록했어요 — 이웃 탭 피드에 이 창고의 소식이 흐릅니다.');
    } catch (e) {
      window.alert(`등록 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <div className="max-w-3xl mx-auto space-y-3">
        <div className="flex items-center gap-2">
          <p className="text-xs text-stone-500">
            #IndieNet 게시판 — 자기소개도 일반 대화도 여기서 흐릅니다. <strong>공유창고 Warehouse</strong> 병기
            표시가 있는 글은 그 자리에서 창고이웃으로 등록할 수 있어요. (정식 소개는 위의 <strong>소개발행</strong> 버튼으로)
          </p>
          <div className="flex-1" />
          <button
            className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100 shrink-0"
            title="새로고침" onClick={() => retry()}
          >
            <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {/* 작성바 — 게시판처럼 한마디. 공개 발행임을 placeholder 로 명시. */}
        <div className="flex items-end gap-2 px-3 py-2.5 rounded-xl bg-white border border-stone-200">
          <textarea
            rows={draft.includes('\n') || draft.length > 60 ? 3 : 1}
            className="flex-1 resize-none text-sm text-stone-800 placeholder:text-stone-400 outline-none bg-transparent"
            placeholder="#IndieNet 게시판에 한마디 — 소개도, 일반 대화도 좋아요 (모두에게 공개 발행됩니다)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            className="px-3 py-1.5 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] disabled:opacity-50 shrink-0"
            disabled={posting || !draft.trim()}
            onClick={postMsg}
          >
            {posting ? '게시 중…' : '게시'}
          </button>
        </div>
        {error && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2">
            <span className="flex-1">{error}{retrying && <span className="ml-1 text-red-400">— 백엔드를 기다리는 중…</span>}</span>
            <button className="shrink-0 px-2 py-0.5 rounded-md border border-red-200 bg-white hover:bg-red-50"
                    onClick={() => retry()}>다시 시도</button>
          </div>
        )}
        {busy && !items.length && <div className="text-sm text-stone-400 py-8 text-center">릴레이에서 소개를 모으는 중…</div>}
        {!busy && !items.length && !error && (
          <div className="text-center text-stone-400 py-10">
            <Search className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-sm">아직 소개가 없어요 — 먼저 소개발행으로 나를 알려보세요</p>
          </div>
        )}
        <ul className="space-y-2">
          {items.map((it, i) => {
            const wh = whUrlOf(it.content);
            return (
              <li key={it.id || i} className="px-4 py-3 rounded-xl bg-white border border-stone-200">
                <div className="flex items-center gap-2 text-xs text-stone-400 mb-1">
                  <button
                    className="font-medium text-stone-600 hover:text-[#B45309] hover:underline underline-offset-2"
                    title="DM 보내기 — 메신저에서 이 사람과의 대화를 엽니다 (이웃이 아니면 등록부터)"
                    onClick={() => openDm(it)}
                  >
                    💬 {it.author}
                  </button>
                  <span>{it.time}</span>
                </div>
                <p className="text-sm text-stone-800 whitespace-pre-wrap break-words">{linkify(it.content)}</p>
                {wh && (
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-stone-200 text-stone-600 hover:border-[#D97706]/40 hover:text-[#B45309]"
                      title="이 사람의 공개 창고를 브라우저로 열기"
                      onClick={() => openUrl(wh)}
                    >
                      <Package className="w-3.5 h-3.5" /> 창고 열기
                    </button>
                    <button
                      className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] disabled:opacity-50"
                      title="창고이웃으로 등록 — 이웃 탭 피드에 이 창고의 새 파일이 흐릅니다"
                      disabled={!!added[wh]}
                      onClick={() => addNeighbor(wh, it.author_full || '')}
                    >
                      <Plus className="w-3.5 h-3.5" /> {added[wh] ? '등록됨' : '창고이웃 등록'}
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
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
  const [retweetPick, setRetweetPick] = useState<{ item: WfFeedItem; level: number; mode: 'link' | 'copy' } | null>(null);
  // 피드 필터 — 내가 이웃에게 준 레벨(이상) + 즐겨찾기만. 레벨=숫자, 의미 라벨 없음.
  const [feedMinLevel, setFeedMinLevel] = useState(0);
  const [feedFavOnly, setFeedFavOnly] = useState(false);

  const load = useCallback(async () => {
    try {
      const [rn, rf] = await Promise.all([
        fetch(`${API}/warehouse-feed/neighbors`),
        fetch(`${API}/warehouse-feed/feed?limit=100&min_level=${feedMinLevel}&favorites=${feedFavOnly ? 1 : 0}`),
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
  }, [feedMinLevel, feedFavOnly]);

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
  }, [addUrl, addName, addCandidate, load]);

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
      const patch = (arr: WfFeedItem[]) => arr.map((x) => {
        if (x.wh_url === f.wh_url && x.path === f.path) return { ...x, likes: d.count };
        if (x.group && x.items) {
          return { ...x, items: x.items.map((y) => (y.wh_url === f.wh_url && y.path === f.path ? { ...y, likes: d.count } : y)) };
        }
        return x;
      });
      setFeed((cur) => patch(cur));
      setResults((cur) => (cur ? patch(cur) : cur));
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
                onClick={() => openWarehouseInBrowser(n.warehouse_url + '/')}
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
              onClick={() => setSub(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
                sub === key ? 'bg-amber-50 text-[#B45309] font-medium' : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              <SubIcon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
          {/* 피드 필터 — 내가 이웃에게 준 레벨(이상) + 즐겨찾기만 (레벨=숫자, 의미 라벨 없음) */}
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
              <button
                onClick={() => setFeedFavOnly((v) => !v)}
                title="즐겨찾기한 이웃만"
                className={`flex items-center gap-1 px-2 py-1 rounded-lg border text-xs transition-colors ${
                  feedFavOnly ? 'border-[#D97706] bg-amber-50 text-[#B45309]' : 'border-stone-200 text-stone-500 hover:text-stone-700'
                }`}
              >
                <Star className={`w-3.5 h-3.5 ${feedFavOnly ? 'fill-[#D97706] text-[#D97706]' : ''}`} /> 즐겨찾기만
              </button>
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

      {/* 피드(변화) / 검색 결과(현재) */}
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
                        onClick={() => openWarehouseInBrowser(n.warehouse_url + '/')}
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
              f.group ? (
                <GroupRow
                  key={`g:${f.wh_url}:${f.folder}:${f.seen_at}:${f.kind}`}
                  g={f}
                  onRetweet={(picked) => setRetweetPick({ item: picked, level: 0, mode: 'link' })}
                  onLike={doLike}
                />
              ) : (
                <FileRow
                  key={`${f.wh_url}:${f.id ?? f.path}:${f.seen_at}`}
                  f={f}
                  onRetweet={(picked) => setRetweetPick({ item: picked, level: 0, mode: 'link' })}
                  onLike={doLike}
                />
              )
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function WarehouseView() {
  const [tab, setTab] = useState<'mine' | 'neighbors' | 'discover' | 'business'>(() => {
    const saved = localStorage.getItem('indiebiz_warehouse_tab');
    return saved === 'neighbors' || saved === 'discover' || saved === 'business' ? saved : 'mine';
  });
  const [level, setLevel] = useState<number>(() => {
    const saved = Number(localStorage.getItem('indiebiz_warehouse_level'));
    return Number.isInteger(saved) && saved >= 0 && saved <= 4 ? saved : 0;
  });
  const [data, setData] = useState<WhData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);   // 지금 조준된 폴더 경로
  const [innerDrag, setInnerDrag] = useState(false);                   // 창고 안 이동 vs 바깥 투입
  const [busy, setBusy] = useState<string | null>(null);

  // ★실패를 굳히지 않는다 — 앱 시작 직후엔 백엔드(8765)가 아직 안 떠 있을 수 있어
  //   첫 조회가 실패한다. throw 해서 useRetryingLoad 가 백오프 재시도하게 둔다
  //   (예전엔 에러만 세팅하고 끝나 창을 나갔다 와야 회복됐다 — 2026-07-20 윈도우 실측).
  const load = useCallback(async (lv: number) => {
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/list?level=${lv}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, []);

  useEffect(() => {
    localStorage.setItem('indiebiz_warehouse_level', String(level));
  }, [level]);
  const { retry, retrying } = useRetryingLoad(
    useCallback(() => load(level), [load, level]));

  const addPaths = useCallback(async (paths: string[]) => {
    if (!paths.length) return;
    setBusy(`${paths.length}개 넣는 중…`);
    let msg: string | null = null;
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, paths }),
      });
      const d = await r.json();
      if (d.skipped?.length) {
        msg = `건너뜀 ${d.skipped.length}건: ${d.skipped[0].reason}`;
      }
    } catch (e) {
      msg = e instanceof Error ? e.message : String(e);
    }
    setBusy(null);
    await load(level).catch(() => {});   // load 가 setError(null) 을 하므로 사유는 그 뒤에 담는다
    if (msg) setError(msg);
  }, [level, load]);

  /* 창고 안에서 옮기기 — dest='' 는 창고 루트. 같은 레벨 안에서만 움직인다. */
  const moveItem = useCallback(async (name: string, dest: string) => {
    if (!name) return;
    const parent = name.includes('/') ? name.slice(0, name.lastIndexOf('/')) : '';
    if (parent === dest) return;                 // 제자리 — 서버 왕복도 아깝다
    setError(null);
    let msg: string | null = null;
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, name, dest }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        msg = d.detail || `HTTP ${r.status}`;
      }
    } catch (e) {
      msg = e instanceof Error ? e.message : String(e);
    }
    // ★목록 새로고침이 먼저다 — load 가 성공 시 setError(null) 을 하므로 순서가 뒤집히면
    //   방금 담은 실패 사유가 지워져 "끌었는데 아무 일도 안 일어남"이 된다.
    await load(level).catch(() => {});
    if (msg) setError(msg);
  }, [level, load]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    /* 창고 안 항목을 빈 곳에 떨어뜨림 = 창고 루트로 빼기(바깥 파일 투입과 구별) */
    setInnerDrag(false);
    const inner = e.dataTransfer.getData(WH_DRAG);
    if (inner) { moveItem(inner, ''); return; }
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
  }, [addPaths, moveItem]);

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
    retry();
  }, [level, retry]);

  const hasElectron = typeof (window as any).electron?.selectFiles === 'function';

  /* 소개발행 — 공개 인사 프로필 + 공개 창고 주소를 #IndieNet 에 발행 (명함 kind:0 + 발견 노트 kind:1).
     "나를 알리는" 행위라 비즈니스 계기가 아니라 창고 표면에 산다 (2026-07-19 이동). */
  const [introBusy, setIntroBusy] = useState(false);
  const publishIntro = useCallback(async () => {
    if (!window.confirm('공개 인사 프로필과 공개 창고 주소를 #IndieNet 에 발행할까요? (명함 kind:0 + 발견 노트 kind:1)')) return;
    setIntroBusy(true);
    try {
      const r = (await runIBL('[self:business_document]{op: "publish"}')) as Record<string, unknown>;
      const msg = typeof r?.message === 'string' ? r.message
        : r?.error ? String(r.error) : '소개를 발행했어요.';
      window.alert(msg);
    } catch (e) {
      window.alert(`소개발행 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
    setIntroBusy(false);
  }, []);

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
          {([['mine', '내 창고', Package], ['neighbors', '이웃', Users], ['discover', '이웃찾기', Search], ['business', '비즈니스', Building2]] as const).map(([key, label, TabIcon]) => (
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
        <button
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-[#D97706]/40 text-[#B45309] hover:bg-amber-50 disabled:opacity-50"
          title="나를 알리기 — 공개 인사 프로필과 공개 창고 주소를 #IndieNet 에 발행합니다 (창고이웃을 구하는 첫걸음)"
          disabled={introBusy}
          onClick={publishIntro}
        >
          <Globe className="w-3.5 h-3.5" /> {introBusy ? '발행 중…' : '소개발행'}
        </button>
        {tab === 'mine' && busy && <span className="text-xs text-stone-500 animate-pulse">{busy}</span>}
        {tab === 'mine' && (
          <button
            className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100"
            title="새로고침"
            onClick={() => retry()}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        )}
      </div>

      {tab === 'neighbors' && <NeighborsPane />}
      {tab === 'discover' && <DiscoverPane />}
      {/* 비즈니스 관리 — 창고에 진열되는 카탈로그(아이템·공개문서·자동응답)의 저작면.
          2026-07-19 런처 모드에서 창고 탭으로 이동: 비즈니스=창고를 채우는 관리 기능. */}
      {tab === 'business' && <div className="flex-1 min-h-0"><BusinessInstrumentView /></div>}

      {tab === 'mine' && (<>
      {/* 창고 폴더 위치 — 이 몸의 창고가 디스크 어디에 사는지 (클릭 = 파일 탐색기로 열기) */}
      {data?.root_path && (
        <div className="flex items-center gap-1.5 px-5 py-1.5 border-b border-stone-100 bg-stone-50/70 shrink-0 text-[11px] text-stone-500 min-w-0">
          <Folder className="w-3.5 h-3.5 text-stone-400 shrink-0" />
          <span className="shrink-0">창고 폴더:</span>
          <button
            className="font-mono text-stone-600 hover:text-[#B45309] hover:underline truncate"
            title="파일 탐색기로 열기"
            onClick={() => (window as any).electron?.openExternal?.('file://' + data.root_path)}
          >
            {data.root_path}
          </button>
          <span className="text-stone-400 shrink-0 hidden sm:inline">— 0~4 하위폴더에 파일을 직접 넣어도 됩니다</span>
        </div>
      )}
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
        <div className="flex-1" />
        {/* 파일·폴더 넣기 — 헤더가 붐벼 레벨 줄로 내림(2026-07-19). 넣는 대상 레벨과 같은 줄이라 맥락도 맞다. */}
        {hasElectron && (
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] shrink-0"
            onClick={pickFiles}
          >
            <FilePlus className="w-3.5 h-3.5" /> 파일·폴더 넣기
          </button>
        )}
      </div>

      {/* 폴더 뷰 = 드롭존 */}
      <div
        className={`flex-1 min-h-0 overflow-auto relative ${dragOver && !dropTarget ? 'bg-amber-50' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setInnerDrag(e.dataTransfer.types.includes(WH_DRAG));
          setDragOver(true);
        }}
        onDragLeave={(e) => { if (e.currentTarget === e.target) { setDragOver(false); setDropTarget(null); } }}
        onDrop={onDrop}
      >
        {/* 폴더를 조준 중이면 그 폴더가 스스로 표시한다 — 루트 안내는 비켜준다 */}
        {dragOver && !dropTarget && (
          <div className="absolute inset-3 z-10 border-2 border-dashed border-[#D97706] rounded-2xl flex items-center justify-center pointer-events-none bg-amber-50/80">
            <div className="text-[#B45309] font-medium">
              {innerDrag ? '창고 맨 위로 빼기' : `레벨 ${level} 창고에 넣기`}
            </div>
          </div>
        )}

        {error && (
          <div className="mx-5 mt-3 px-3 py-2 text-xs rounded-lg bg-red-50 text-red-600 border border-red-100 flex items-center gap-2">
            <span className="flex-1">
              {error}
              {retrying && <span className="ml-1 text-red-400">— 백엔드를 기다리는 중…</span>}
            </span>
            <button
              className="shrink-0 px-2 py-0.5 rounded-md border border-red-200 bg-white hover:bg-red-50"
              onClick={() => retry()}
            >
              다시 시도
            </button>
          </div>
        )}

        {!data ? (
          <div className="h-full flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-stone-200 border-t-stone-600 rounded-full animate-spin" />
          </div>
        ) : data.files.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
            <Package className="w-10 h-10" />
            <p className="text-sm">비어 있어요 — 파일이나 폴더를 끌어다 놓으세요</p>
          </div>
        ) : (
          <ul className="px-5 py-3 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-2 content-start">
            {renderWhNode(whTree(data.files))}
          </ul>
        )}
      </div>
      </>)}
    </div>
  );

  /* 파일 먼저(최신순 — 백엔드 정렬 유지), 폴더 나중(안에서 가장 최근 것 순).
     레이아웃: 파일=타일 그리드(넓은 창에서 한 줄 여러 개 — 행 하나에 파일 하나는 빈공간 낭비),
     폴더=col-span-full 전체 폭 행(드롭 대상 + 펼침 목록이라 행이 자연스럽다). */
  function renderWhNode(node: WhNode, depth = 0): React.ReactNode {
    const dirNames = Object.keys(node.dirs).sort(
      (a, b) => (whAgg(node.dirs[b]).mtime > whAgg(node.dirs[a]).mtime ? 1 : -1)
    );
    return (
      <>
        {node.files.map(({ f, label }) => renderWhFile(f, label))}
        {dirNames.map((name) => {
          const sub = node.dirs[name];
          const a = whAgg(sub);
          const isOver = dropTarget === sub.path;
          return (
            <li
              key={`d:${depth}:${name}`}
              className="col-span-full"
              draggable
              onDragStart={(e) => {
                e.stopPropagation();
                e.dataTransfer.setData(WH_DRAG, sub.path);
                e.dataTransfer.effectAllowed = 'move';
              }}
              /* 폴더 = 드롭 대상. stopPropagation 이 없으면 안쪽 폴더에 떨어뜨린 게
                 바깥 폴더·루트까지 함께 처리돼 목적지가 뒤집힌다. */
              onDragOver={(e) => {
                if (!e.dataTransfer.types.includes(WH_DRAG)) return;
                e.preventDefault();
                e.stopPropagation();
                e.dataTransfer.dropEffect = 'move';
                setDropTarget(sub.path);
              }}
              onDragLeave={(e) => { e.stopPropagation(); setDropTarget((t) => (t === sub.path ? null : t)); }}
              onDrop={(e) => {
                const dragged = e.dataTransfer.getData(WH_DRAG);
                if (!dragged) return;                 // 바깥 파일 투입은 패널이 받는다
                e.preventDefault();
                e.stopPropagation();
                setDropTarget(null);
                moveItem(dragged, sub.path);
              }}
            >
              <details className={`group/fd rounded-xl bg-white border ${isOver ? 'border-[#D97706] bg-amber-50' : 'border-stone-200'}`}>
                <summary className="flex items-center gap-3 px-3 py-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                  <ChevronRight className="w-4 h-4 text-stone-400 shrink-0 transition-transform group-open/fd:rotate-90" />
                  <Folder className={`w-5 h-5 shrink-0 ${isOver ? 'text-[#D97706]' : 'text-stone-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-stone-800 truncate">{name}</div>
                    <div className="text-[11px] text-stone-400">
                      {isOver ? '여기로 옮기기' : `${a.count}개 · ${fmtBytes(a.bytes)}`}
                    </div>
                  </div>
                </summary>
                <ul className="ml-5 pl-4 pr-2 pb-2 border-l border-stone-100 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-2 content-start">
                  {renderWhNode(sub, depth + 1)}
                </ul>
              </details>
            </li>
          );
        })}
      </>
    );
  }

  function renderWhFile(f: WhFile, label: string): React.ReactNode {
    const Icon = fileIcon(f.name);
    const isImg = IMG_EXT.test(f.name);
    return (
                <li
                  key={f.name}
                  draggable
                  onDragStart={(e) => {
                    e.stopPropagation();
                    e.dataTransfer.setData(WH_DRAG, f.name);
                    e.dataTransfer.effectAllowed = 'move';
                  }}
                  className="group flex items-center gap-2 px-2.5 py-2 rounded-xl bg-white border border-stone-200 hover:border-[#D97706]/40 min-w-0"
                >
                  {isImg ? (
                    <img
                      src={fileUrl(f.name)}
                      className="w-10 h-10 rounded-lg object-cover bg-stone-100 shrink-0 cursor-pointer"
                      onClick={() => openFile(f.name)}
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  ) : (
                    <Icon className="w-5 h-5 text-stone-400 shrink-0 mx-1.5" />
                  )}
                  <div
                    className="flex-1 min-w-0 cursor-pointer"
                    title="열기 (사진 보기 · 동영상 재생 · 텍스트 읽기)"
                    onClick={() => openFile(f.name)}
                  >
                    <div className="text-sm text-stone-800 truncate group-hover:text-[#D97706] group-hover:underline" title={f.name}>{label}</div>
                    <div className="text-[11px] text-stone-400 truncate" title={`${fmtBytes(f.bytes)} · ${f.mtime.replace('T', ' ')}`}>
                      {fmtBytes(f.bytes)} · {f.mtime.replace('T', ' ')}
                    </div>
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
  }
}
