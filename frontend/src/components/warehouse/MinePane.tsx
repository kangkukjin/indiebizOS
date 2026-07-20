/**
 * MinePane — 내 창고 탭, 파인더 모델 (2026-07-20 재편).
 *
 * 항해: 한 번에 한 폴더만 렌더(더블클릭 진입 + 경로 바) — 파일이 수백이어도 안 무너진다.
 * 표시: 아이콘 그리드/목록 토글. 동작: 우클릭 컨텍스트 메뉴(열기·내려받기·이름변경·빼기),
 * 다중 선택(⌘·⇧)+Delete, 드래그 이동(폴더·경로 바·레벨로). 바깥에서 끌어넣으면 복사.
 * 왼쪽 사이드바 = 레벨 0~4 + 휴지통. 레벨에 드롭 = 공개 범위 변경(사용자 승인 의미론).
 *
 * 서버 배관은 /portal/warehouse-admin/* — IBL 어휘 아님(AI 는 self:move·mkdir 로 같은 일).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Package, RefreshCw, FilePlus, FolderPlus, Trash2, Download, Folder,
  ChevronRight, LayoutGrid, List, RotateCcw, ExternalLink,
} from 'lucide-react';
import { API, IMG_EXT, WH_DRAG, fmtBytes, fileIcon, openExternalUrl } from './shared';
import type { WhFile, WhData, TrashItem } from './shared';
import { useRetryingLoad } from '../../lib/use-retrying-load';

/* ── 폴더 트리 — 서버는 평면 목록(files + dirs)을 준다. 빈 폴더는 dirs 로만 온다. ── */
interface WhNode { dirs: Record<string, WhNode>; files: WhFile[]; path: string }

function ensureDir(root: WhNode, rel: string): WhNode {
  let node = root;
  if (!rel) return node;
  for (const seg of rel.split('/')) {
    if (!node.dirs[seg]) {
      node.dirs[seg] = { dirs: {}, files: [], path: node.path ? `${node.path}/${seg}` : seg };
    }
    node = node.dirs[seg];
  }
  return node;
}

function buildTree(files: WhFile[], dirs: string[]): WhNode {
  const root: WhNode = { dirs: {}, files: [], path: '' };
  for (const d of dirs) ensureDir(root, d);
  for (const f of files) {
    const idx = f.name.lastIndexOf('/');
    (idx >= 0 ? ensureDir(root, f.name.slice(0, idx)) : root).files.push(f);
  }
  return root;
}

function findNode(root: WhNode, path: string): WhNode | null {
  if (!path) return root;
  let node: WhNode | null = root;
  for (const seg of path.split('/')) {
    node = node?.dirs[seg] ?? null;
    if (!node) return null;
  }
  return node;
}

function aggOf(node: WhNode): { count: number; bytes: number; mtime: string } {
  let count = node.files.length;
  let bytes = node.files.reduce((s, f) => s + (f.bytes || 0), 0);
  let mtime = node.files.reduce((m, f) => (f.mtime > m ? f.mtime : m), '');
  for (const sub of Object.values(node.dirs)) {
    const a = aggOf(sub);
    count += a.count; bytes += a.bytes;
    if (a.mtime > mtime) mtime = a.mtime;
  }
  return { count, bytes, mtime };
}

/* 현재 폴더의 표시 항목 — 폴더 먼저, 그 다음 파일(파인더 관례). */
interface Entry {
  kind: 'dir' | 'file';
  label: string;          // basename
  path: string;           // 창고 루트 기준 상대경로 = 서버 키
  bytes: number; mtime: string; count?: number;
}

type SortKey = 'name' | 'mtime' | 'bytes';

interface CtxMenu {
  x: number; y: number;
  kind: 'entry' | 'empty' | 'trash' | 'trash-empty';
  entry?: Entry;
  trash?: TrashItem;
}

const parentOf = (p: string) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');

export function MinePane() {
  const [level, setLevel] = useState<number>(() => {
    const saved = Number(localStorage.getItem('indiebiz_warehouse_level'));
    return Number.isInteger(saved) && saved >= 0 && saved <= 4 ? saved : 0;
  });
  const [inTrash, setInTrash] = useState(false);
  const [path, setPath] = useState('');
  const [view, setView] = useState<'grid' | 'list'>(() =>
    localStorage.getItem('indiebiz_warehouse_view') === 'list' ? 'list' : 'grid');
  const [sortKey, setSortKey] = useState<SortKey>('mtime');
  const [sortAsc, setSortAsc] = useState(false);
  const [data, setData] = useState<WhData | null>(null);
  const [trash, setTrash] = useState<TrashItem[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const anchor = useRef<number | null>(null);
  const [ctx, setCtx] = useState<CtxMenu | null>(null);
  const [renaming, setRenaming] = useState<{ path: string; draft: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);  // 'dir:<path>' | 'level:<n>' | 'crumb:<path>'
  const [innerDrag, setInnerDrag] = useState(false);
  /* 새로 만든 폴더는 목록이 다시 온 뒤 이름변경 모드로 — 응답의 created 경로를 예약해 둔다 */
  const pendingRename = useRef<string | null>(null);

  useEffect(() => { localStorage.setItem('indiebiz_warehouse_level', String(level)); }, [level]);
  useEffect(() => { localStorage.setItem('indiebiz_warehouse_view', view); }, [view]);

  const loadTrash = useCallback(async () => {
    const r = await fetch(`${API}/portal/warehouse-admin/trash`);
    if (r.ok) setTrash((await r.json()).items || []);
  }, []);

  // ★실패를 굳히지 않는다 — 콜드스타트(8765 바인딩 전)엔 throw 로 훅 백오프에 맡긴다.
  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/list?level=${level}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    }
    loadTrash().catch(() => {});   // 휴지통 배지는 부차 — 본 목록을 막지 않는다
  }, [level, loadTrash]);
  // onFocus — 창고는 그냥 디스크 폴더라 AI(self:move·mkdir)·Finder 도 만진다.
  // 다른 데 다녀오면 재조회해 바깥 변경을 흡수한다.
  const { retry, retrying } = useRetryingLoad(load, { onFocus: true });

  const tree = useMemo(() => buildTree(data?.files ?? [], data?.dirs ?? []), [data]);
  const node = findNode(tree, path);
  // 보고 있던 폴더가 사라지면(이동·이름변경) 루트로 — 죽은 경로에 머물지 않는다
  useEffect(() => { if (data && !findNode(tree, path)) setPath(''); }, [data, tree, path]);

  const entries: Entry[] = useMemo(() => {
    if (!node) return [];
    const dirs: Entry[] = Object.entries(node.dirs).map(([name, sub]) => {
      const a = aggOf(sub);
      return { kind: 'dir' as const, label: name, path: sub.path, bytes: a.bytes, mtime: a.mtime, count: a.count };
    });
    const files: Entry[] = node.files.map((f) => ({
      kind: 'file' as const, label: f.name.split('/').pop() || f.name,
      path: f.name, bytes: f.bytes, mtime: f.mtime,
    }));
    const cmp = (a: Entry, b: Entry) => {
      let c = 0;
      if (sortKey === 'name') c = a.label.localeCompare(b.label, 'ko');
      else if (sortKey === 'bytes') c = a.bytes - b.bytes;
      else c = a.mtime < b.mtime ? -1 : a.mtime > b.mtime ? 1 : 0;
      return sortAsc ? c : -c;
    };
    return [...dirs.sort(cmp), ...files.sort(cmp)];
  }, [node, sortKey, sortAsc]);

  // 목록이 새로 오면 선택에서 사라진 항목을 걷어낸다 + 예약된 새 폴더 이름변경 시작
  useEffect(() => {
    setSel((s) => s.filter((p) => entries.some((e) => e.path === p)));
    if (pendingRename.current) {
      const p = pendingRename.current;
      if (entries.some((e) => e.path === p)) {
        pendingRename.current = null;
        setSel([p]);
        setRenaming({ path: p, draft: p.split('/').pop() || p });
      }
    }
  }, [entries]);

  /* ── 서버 동작 — 전부 "실행 → 재조회". 재조회가 진실. ── */

  const reload = useCallback(async () => { await load().catch(() => {}); }, [load]);

  const addPaths = useCallback(async (paths: string[], dest: string, lv = level) => {
    if (!paths.length) return;
    setBusy(`${paths.length}개 넣는 중…`);
    let msg: string | null = null;
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/add`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: lv, dest, paths }),
      });
      const d = await r.json();
      if (!r.ok) msg = d?.detail || `HTTP ${r.status}`;
      else if (d.skipped?.length) msg = `건너뜀 ${d.skipped.length}건: ${d.skipped[0].reason}`;
    } catch (e) {
      msg = e instanceof Error ? e.message : String(e);
    }
    setBusy(null);
    await reload();          // load 가 setError(null) 하므로 사유는 그 뒤에 담는다
    if (msg) setError(msg);
  }, [level, reload]);

  const moveItems = useCallback(async (paths: string[], dest: string, destLevel = level) => {
    const work = paths.filter((p) => !(destLevel === level && parentOf(p) === dest));
    if (!work.length) return;
    let msg: string | null = null;
    for (const name of work) {
      // 폴더를 자기 자신/하위로 — 서버도 막지만 왕복 전에 거른다
      if (destLevel === level && (dest === name || dest.startsWith(name + '/'))) continue;
      try {
        const r = await fetch(`${API}/portal/warehouse-admin/move`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ level, name, dest, dest_level: destLevel }),
        });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          msg = d.detail || `HTTP ${r.status}`;
        }
      } catch (e) {
        msg = e instanceof Error ? e.message : String(e);
      }
    }
    await reload();
    if (msg) setError(msg);
  }, [level, reload]);

  const removeItems = useCallback(async (paths: string[]) => {
    setBusy('휴지통으로 빼는 중…');
    for (const name of paths) {
      try {
        await fetch(`${API}/portal/warehouse-admin/remove`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ level, name }),
        });
      } catch { /* 재조회가 진실 */ }
    }
    setBusy(null);
    await reload();
  }, [level, reload]);

  const mkdir = useCallback(async () => {
    let msg: string | null = null;
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/mkdir`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, dest: path, name: '새 폴더' }),
      });
      const d = await r.json();
      if (!r.ok) msg = d?.detail || `HTTP ${r.status}`;
      else pendingRename.current = d.created;   // 목록이 오면 바로 이름변경 모드
    } catch (e) {
      msg = e instanceof Error ? e.message : String(e);
    }
    await reload();
    if (msg) setError(msg);
  }, [level, path, reload]);

  const commitRename = useCallback(async () => {
    if (!renaming) return;
    const cur = renaming.path.split('/').pop() || renaming.path;
    const next = renaming.draft.trim();
    setRenaming(null);
    if (!next || next === cur) return;
    let msg: string | null = null;
    try {
      const r = await fetch(`${API}/portal/warehouse-admin/move`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, name: renaming.path, dest: parentOf(renaming.path), new_name: next }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        msg = d.detail || `HTTP ${r.status}`;
      }
    } catch (e) {
      msg = e instanceof Error ? e.message : String(e);
    }
    await reload();
    if (msg) setError(msg);
  }, [renaming, level, reload]);

  const restoreItem = useCallback(async (it: TrashItem) => {
    try {
      await fetch(`${API}/portal/warehouse-admin/restore`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: it.level, name: it.name }),
      });
    } catch { /* 재조회가 진실 */ }
    await reload();
  }, [reload]);

  const trashDelete = useCallback(async (it: TrashItem | null) => {
    const ok = window.confirm(it
      ? `'${it.name}' 을(를) 영구 삭제할까요? 되돌릴 수 없어요.`
      : '휴지통을 비울까요? 전부 영구 삭제되고 되돌릴 수 없어요.');
    if (!ok) return;
    try {
      await fetch(`${API}/portal/warehouse-admin/trash-delete`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(it ? { level: it.level, name: it.name } : { all: true }),
      });
    } catch { /* 재조회가 진실 */ }
    await reload();
  }, [reload]);

  /* ── 열기·내려받기 ── */
  const fileUrl = useCallback(
    (name: string) => `${API}/portal/warehouse-admin/file?level=${level}&name=${encodeURIComponent(name)}`,
    [level],
  );
  const openFile = useCallback((name: string) => openExternalUrl(fileUrl(name)), [fileUrl]);
  const downloadFile = useCallback((name: string) => {
    const a = document.createElement('a');
    a.href = `${fileUrl(name)}&download=1`;
    a.download = '';
    a.click();
  }, [fileUrl]);

  /* ── 선택 ── */
  const clickEntry = useCallback((e: React.MouseEvent, idx: number) => {
    e.stopPropagation();
    const p = entries[idx].path;
    if (e.shiftKey && anchor.current != null) {
      const [a, b] = [Math.min(anchor.current, idx), Math.max(anchor.current, idx)];
      setSel(entries.slice(a, b + 1).map((x) => x.path));
    } else if (e.metaKey || e.ctrlKey) {
      setSel((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]));
      anchor.current = idx;
    } else {
      setSel([p]);
      anchor.current = idx;
    }
  }, [entries]);

  const openEntry = useCallback((en: Entry) => {
    if (en.kind === 'dir') { setPath(en.path); setSel([]); }
    else openFile(en.path);
  }, [openFile]);

  /* 키보드 — 파인더 문법: Delete=빼기, Enter=이름변경, Esc=선택 해제 */
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (renaming || inTrash) return;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && sel.length) {
        e.preventDefault();
        removeItems(sel);
      } else if (e.key === 'Escape') {
        setSel([]); setCtx(null);
      } else if (e.key === 'Enter' && sel.length === 1) {
        e.preventDefault();
        setRenaming({ path: sel[0], draft: sel[0].split('/').pop() || sel[0] });
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [sel, renaming, inTrash, removeItems]);

  /* 컨텍스트 메뉴 — 어디든 클릭하면 닫힘 */
  useEffect(() => {
    if (!ctx) return;
    const close = () => setCtx(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [ctx]);

  /* ── 드래그 ── */
  const dragPayload = useCallback((en: Entry): string[] => (
    sel.includes(en.path) ? sel : [en.path]
  ), [sel]);

  const extractExternalPaths = useCallback((e: React.DragEvent): string[] => {
    const el = (window as any).electron;
    if (!el?.getPathForFile) {
      setError('파일 경로 배선이 아직 없어요 — 앱을 재시작해 주세요.');
      return [];
    }
    const paths: string[] = [];
    for (const f of Array.from(e.dataTransfer.files)) {
      try {
        const p = el.getPathForFile(f);
        if (p) paths.push(p);
      } catch { /* 개별 실패 무시 */ }
    }
    return paths;
  }, []);

  /** 폴더 셀·경로 조각·레벨 항목이 공유하는 드롭 수신부 */
  const dropInto = useCallback((e: React.DragEvent, dest: string, destLevel = level) => {
    e.preventDefault();
    e.stopPropagation();
    setDropTarget(null); setDragOver(false); setInnerDrag(false);
    const inner = e.dataTransfer.getData(WH_DRAG);
    if (inner) {
      try { moveItems(JSON.parse(inner) as string[], dest, destLevel); } catch { /* 형식 불량 무시 */ }
      return;
    }
    addPaths(extractExternalPaths(e), dest, destLevel);
  }, [level, moveItems, addPaths, extractExternalPaths]);

  const acceptDrag = useCallback((e: React.DragEvent, key: string) => {
    const kinds = e.dataTransfer.types;
    if (!kinds.includes(WH_DRAG) && !kinds.includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    setDropTarget(key);
  }, []);

  const hasElectron = typeof (window as any).electron?.selectFiles === 'function';
  const pickFiles = useCallback(async () => {
    const el = (window as any).electron;
    if (!el?.selectFiles) return;
    const picked: string[] | null = await el.selectFiles();
    if (picked?.length) addPaths(picked, path);
  }, [addPaths, path]);

  /* ── 조각 렌더 ── */

  const crumbs = useMemo(() => {
    const list: { label: string; p: string }[] = [{ label: `레벨 ${level}`, p: '' }];
    let acc = '';
    for (const seg of path ? path.split('/') : []) {
      acc = acc ? `${acc}/${seg}` : seg;
      list.push({ label: seg, p: acc });
    }
    return list;
  }, [level, path]);

  const renameBox = (en: Entry) => (
    <input
      autoFocus
      className="w-full px-1 py-0.5 text-xs rounded border border-[#D97706] outline-none bg-white text-stone-800"
      value={renaming!.draft}
      onChange={(e) => setRenaming({ path: en.path, draft: e.target.value })}
      onFocus={(e) => {
        const v = e.target.value;
        const dot = en.kind === 'file' ? v.lastIndexOf('.') : -1;
        e.target.setSelectionRange(0, dot > 0 ? dot : v.length);
      }}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === 'Enter') commitRename();
        if (e.key === 'Escape') setRenaming(null);
      }}
      onBlur={commitRename}
      onClick={(e) => e.stopPropagation()}
    />
  );

  const gridCell = (en: Entry, idx: number) => {
    const selected = sel.includes(en.path);
    const isOver = dropTarget === `dir:${en.path}`;
    const Icon = en.kind === 'dir' ? Folder : fileIcon(en.label);
    const isImg = en.kind === 'file' && IMG_EXT.test(en.label);
    return (
      <li
        key={en.path}
        draggable={!renaming}
        onDragStart={(e) => {
          e.stopPropagation();
          if (!sel.includes(en.path)) { setSel([en.path]); anchor.current = idx; }
          e.dataTransfer.setData(WH_DRAG, JSON.stringify(dragPayload(en)));
          e.dataTransfer.effectAllowed = 'move';
        }}
        onDragOver={en.kind === 'dir' ? (e) => acceptDrag(e, `dir:${en.path}`) : undefined}
        onDragLeave={en.kind === 'dir' ? () => setDropTarget((t) => (t === `dir:${en.path}` ? null : t)) : undefined}
        onDrop={en.kind === 'dir' ? (e) => dropInto(e, en.path) : undefined}
        onClick={(e) => clickEntry(e, idx)}
        onDoubleClick={() => openEntry(en)}
        onContextMenu={(e) => {
          e.preventDefault(); e.stopPropagation();
          if (!sel.includes(en.path)) { setSel([en.path]); anchor.current = idx; }
          setCtx({ x: e.clientX, y: e.clientY, kind: 'entry', entry: en });
        }}
        className={`flex flex-col items-center gap-1 p-2 rounded-xl cursor-default select-none min-w-0 ${
          isOver ? 'bg-amber-100 ring-2 ring-[#D97706]'
            : selected ? 'bg-amber-100/80'
            : 'hover:bg-stone-100'
        }`}
        title={`${en.label}\n${en.kind === 'dir' ? `${en.count}개 · ` : ''}${fmtBytes(en.bytes)} · ${en.mtime.replace('T', ' ')}`}
      >
        {isImg ? (
          <img
            src={fileUrl(en.path)}
            className="w-14 h-14 rounded-lg object-cover bg-stone-100 shrink-0 pointer-events-none"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <Icon className={`w-12 h-12 shrink-0 ${en.kind === 'dir' ? 'text-[#F59E0B]' : 'text-stone-400'}`} strokeWidth={1.2} />
        )}
        {renaming?.path === en.path ? renameBox(en) : (
          <span className={`w-full text-[11px] leading-tight text-center break-all line-clamp-2 ${
            selected ? 'text-[#92400E] font-medium' : 'text-stone-700'
          }`}>
            {en.label}
          </span>
        )}
      </li>
    );
  };

  const listRow = (en: Entry, idx: number) => {
    const selected = sel.includes(en.path);
    const isOver = dropTarget === `dir:${en.path}`;
    const Icon = en.kind === 'dir' ? Folder : fileIcon(en.label);
    return (
      <li
        key={en.path}
        draggable={!renaming}
        onDragStart={(e) => {
          e.stopPropagation();
          if (!sel.includes(en.path)) { setSel([en.path]); anchor.current = idx; }
          e.dataTransfer.setData(WH_DRAG, JSON.stringify(dragPayload(en)));
          e.dataTransfer.effectAllowed = 'move';
        }}
        onDragOver={en.kind === 'dir' ? (e) => acceptDrag(e, `dir:${en.path}`) : undefined}
        onDragLeave={en.kind === 'dir' ? () => setDropTarget((t) => (t === `dir:${en.path}` ? null : t)) : undefined}
        onDrop={en.kind === 'dir' ? (e) => dropInto(e, en.path) : undefined}
        onClick={(e) => clickEntry(e, idx)}
        onDoubleClick={() => openEntry(en)}
        onContextMenu={(e) => {
          e.preventDefault(); e.stopPropagation();
          if (!sel.includes(en.path)) { setSel([en.path]); anchor.current = idx; }
          setCtx({ x: e.clientX, y: e.clientY, kind: 'entry', entry: en });
        }}
        className={`grid grid-cols-[minmax(0,1fr)_90px_150px] items-center gap-2 px-3 py-1.5 rounded-lg cursor-default select-none text-sm ${
          isOver ? 'bg-amber-100 ring-2 ring-[#D97706]'
            : selected ? 'bg-amber-100/80'
            : 'hover:bg-stone-100'
        }`}
      >
        <span className="flex items-center gap-2 min-w-0">
          <Icon className={`w-4 h-4 shrink-0 ${en.kind === 'dir' ? 'text-[#F59E0B]' : 'text-stone-400'}`} />
          {renaming?.path === en.path ? renameBox(en) : (
            <span className="truncate text-stone-800">{en.label}</span>
          )}
        </span>
        <span className="text-[11px] text-stone-400 text-right tabular-nums">
          {en.kind === 'dir' ? `${en.count}개` : fmtBytes(en.bytes)}
        </span>
        <span className="text-[11px] text-stone-400 tabular-nums">{en.mtime.replace('T', ' ')}</span>
      </li>
    );
  };

  const sortHeader = (key: SortKey, label: string, cls = '') => (
    <button
      className={`text-[11px] font-medium ${sortKey === key ? 'text-[#B45309]' : 'text-stone-400'} hover:text-stone-700 ${cls}`}
      onClick={() => {
        if (sortKey === key) setSortAsc((v) => !v);
        else { setSortKey(key); setSortAsc(key === 'name'); }
      }}
    >
      {label}{sortKey === key ? (sortAsc ? ' ↑' : ' ↓') : ''}
    </button>
  );

  const menuItem = (label: string, onClick: () => void, danger = false, IconC?: any) => (
    <button
      className={`w-full px-3 py-1.5 text-left text-xs flex items-center gap-2 hover:bg-stone-100 ${
        danger ? 'text-red-600' : 'text-stone-700'
      }`}
      onClick={(e) => { e.stopPropagation(); setCtx(null); onClick(); }}
    >
      {IconC && <IconC className="w-3.5 h-3.5" />}{label}
    </button>
  );

  /* ── 본체 ── */
  return (
    <div className="flex-1 min-h-0 flex">
      {/* 사이드바 — 레벨 0~4 + 휴지통. 레벨에 드롭 = 공개 범위 변경. */}
      <div className="w-44 shrink-0 border-r border-stone-200 bg-white/60 flex flex-col py-2 px-2 gap-0.5">
        {[0, 1, 2, 3, 4].map((lv) => {
          const active = !inTrash && lv === level;
          const isOver = dropTarget === `level:${lv}`;
          return (
            <button
              key={lv}
              onClick={() => { setInTrash(false); setLevel(lv); setPath(''); setSel([]); }}
              onDragOver={(e) => acceptDrag(e, `level:${lv}`)}
              onDragLeave={() => setDropTarget((t) => (t === `level:${lv}` ? null : t))}
              onDrop={(e) => dropInto(e, '', lv)}
              className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-left transition-colors ${
                isOver ? 'bg-amber-100 ring-2 ring-[#D97706]'
                  : active ? 'bg-[#D97706] text-white'
                  : 'text-stone-600 hover:bg-stone-100'
              }`}
              title={lv === 0 ? '레벨 0 — 누구나 볼 수 있어요' : `레벨 ${lv} 이상 이웃에게 보입니다`}
            >
              <Package className={`w-3.5 h-3.5 ${active && !isOver ? 'text-white' : 'text-stone-400'}`} />
              <span className="flex-1 font-medium">레벨 {lv}</span>
              <span className={`px-1.5 rounded-full text-[10px] ${
                active && !isOver ? 'bg-white/25' : 'bg-stone-100 text-stone-500'
              }`}>{data?.levels?.[String(lv)] ?? 0}</span>
            </button>
          );
        })}
        <div className="my-1.5 border-t border-stone-200" />
        <button
          onClick={() => { setInTrash(true); setSel([]); setCtx(null); }}
          className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-left transition-colors ${
            inTrash ? 'bg-stone-700 text-white' : 'text-stone-600 hover:bg-stone-100'
          }`}
        >
          <Trash2 className={`w-3.5 h-3.5 ${inTrash ? 'text-white' : 'text-stone-400'}`} />
          <span className="flex-1 font-medium">휴지통</span>
          <span className={`px-1.5 rounded-full text-[10px] ${
            inTrash ? 'bg-white/25' : 'bg-stone-100 text-stone-500'
          }`}>{trash.length}</span>
        </button>
        <div className="flex-1" />
        {data?.root_path && (
          <button
            className="px-2 py-1 text-[10px] text-stone-400 hover:text-[#B45309] text-left truncate font-mono"
            title={`창고 폴더를 파일 탐색기로 열기\n${data.root_path}`}
            onClick={() => (window as any).electron?.openExternal?.('file://' + data.root_path)}
          >
            {data.root_path}
          </button>
        )}
      </div>

      {/* 오른쪽 — 툴바 + 내용 */}
      <div className="flex-1 min-h-0 flex flex-col">
        {/* 툴바: 경로 바(드롭 대상) + 보기 전환 + 동작 버튼 */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-stone-200 bg-white/60 shrink-0 min-w-0">
          {inTrash ? (
            <span className="text-xs font-medium text-stone-700 flex items-center gap-1.5">
              <Trash2 className="w-3.5 h-3.5 text-stone-400" /> 휴지통
              <span className="text-stone-400 font-normal">— 복구는 우클릭</span>
            </span>
          ) : (
            <div className="flex items-center gap-0.5 min-w-0 overflow-hidden">
              {crumbs.map((c, i) => (
                <span key={c.p || 'root'} className="flex items-center gap-0.5 min-w-0">
                  {i > 0 && <ChevronRight className="w-3 h-3 text-stone-300 shrink-0" />}
                  <button
                    className={`px-1.5 py-0.5 rounded text-xs truncate max-w-[160px] ${
                      dropTarget === `crumb:${c.p}` ? 'bg-amber-100 ring-2 ring-[#D97706]'
                        : i === crumbs.length - 1 ? 'font-medium text-stone-800'
                        : 'text-stone-500 hover:text-[#B45309] hover:bg-stone-100'
                    }`}
                    onClick={() => { setPath(c.p); setSel([]); }}
                    onDragOver={(e) => acceptDrag(e, `crumb:${c.p}`)}
                    onDragLeave={() => setDropTarget((t) => (t === `crumb:${c.p}` ? null : t))}
                    onDrop={(e) => dropInto(e, c.p)}
                  >
                    {c.label}
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex-1" />
          {busy && <span className="text-xs text-stone-500 animate-pulse mr-1 shrink-0">{busy}</span>}
          {!inTrash && (
            <>
              <div className="flex items-center p-0.5 rounded-lg bg-stone-100 mr-1 shrink-0">
                <button
                  className={`p-1 rounded-md ${view === 'grid' ? 'bg-white text-[#B45309] shadow-sm' : 'text-stone-400 hover:text-stone-600'}`}
                  title="아이콘 보기" onClick={() => setView('grid')}
                >
                  <LayoutGrid className="w-3.5 h-3.5" />
                </button>
                <button
                  className={`p-1 rounded-md ${view === 'list' ? 'bg-white text-[#B45309] shadow-sm' : 'text-stone-400 hover:text-stone-600'}`}
                  title="목록 보기" onClick={() => setView('list')}
                >
                  <List className="w-3.5 h-3.5" />
                </button>
              </div>
              {view === 'grid' && (
                <select
                  className="px-1.5 py-1 rounded-lg border border-stone-200 bg-white text-[11px] text-stone-600 mr-1 shrink-0"
                  value={`${sortKey}:${sortAsc ? 'a' : 'd'}`}
                  onChange={(e) => {
                    const [k, d] = e.target.value.split(':');
                    setSortKey(k as SortKey); setSortAsc(d === 'a');
                  }}
                  title="정렬"
                >
                  <option value="mtime:d">최신순</option>
                  <option value="name:a">이름순</option>
                  <option value="bytes:d">큰 파일순</option>
                </select>
              )}
              <button
                className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
                title="새 폴더" onClick={mkdir}
              >
                <FolderPlus className="w-4 h-4" />
              </button>
              {hasElectron && (
                <button
                  className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] shrink-0"
                  title="파일·폴더를 골라 이 폴더로 복사" onClick={pickFiles}
                >
                  <FilePlus className="w-3.5 h-3.5" /> 넣기
                </button>
              )}
            </>
          )}
          {inTrash && trash.length > 0 && (
            <button
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-red-200 text-red-500 hover:bg-red-50 shrink-0"
              onClick={() => trashDelete(null)}
            >
              <Trash2 className="w-3.5 h-3.5" /> 휴지통 비우기
            </button>
          )}
          <button
            className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100 shrink-0"
            title="새로고침" onClick={() => retry()}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {error && (
          <div className="mx-4 mt-2 px-3 py-2 text-xs rounded-lg bg-red-50 text-red-600 border border-red-100 flex items-center gap-2 shrink-0">
            <span className="flex-1">{error}{retrying && <span className="ml-1 text-red-400">— 백엔드를 기다리는 중…</span>}</span>
            <button className="shrink-0 px-2 py-0.5 rounded-md border border-red-200 bg-white hover:bg-red-50"
                    onClick={() => retry()}>다시 시도</button>
          </div>
        )}

        {/* 내용 — 빈 곳 클릭=선택 해제, 우클릭=새 폴더 메뉴, 드롭=현재 폴더로 */}
        {inTrash ? (
          <div className="flex-1 min-h-0 overflow-auto px-4 py-2"
               onContextMenu={(e) => { e.preventDefault(); setCtx({ x: e.clientX, y: e.clientY, kind: 'trash-empty' }); }}>
            {trash.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
                <Trash2 className="w-10 h-10" />
                <p className="text-sm">휴지통이 비어 있어요</p>
              </div>
            ) : (
              <ul className="space-y-0.5">
                {trash.map((it) => (
                  <li
                    key={`${it.level}:${it.name}`}
                    className="grid grid-cols-[minmax(0,1fr)_60px_90px_150px] items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-stone-100 text-sm select-none"
                    onContextMenu={(e) => {
                      e.preventDefault(); e.stopPropagation();
                      setCtx({ x: e.clientX, y: e.clientY, kind: 'trash', trash: it });
                    }}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      {it.is_dir
                        ? <Folder className="w-4 h-4 shrink-0 text-[#F59E0B]" />
                        : (() => { const I = fileIcon(it.name); return <I className="w-4 h-4 shrink-0 text-stone-400" />; })()}
                      <span className="truncate text-stone-800">{it.name}</span>
                    </span>
                    <span className="text-[11px] text-stone-400">레벨 {it.level}</span>
                    <span className="text-[11px] text-stone-400 text-right tabular-nums">
                      {it.is_dir ? `${it.count}개` : fmtBytes(it.bytes)}
                    </span>
                    <span className="text-[11px] text-stone-400 tabular-nums">{it.mtime.replace('T', ' ')}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div
            className={`flex-1 min-h-0 overflow-auto relative ${dragOver && !dropTarget ? 'bg-amber-50' : ''}`}
            onClick={() => setSel([])}
            onContextMenu={(e) => { e.preventDefault(); setCtx({ x: e.clientX, y: e.clientY, kind: 'empty' }); }}
            onDragOver={(e) => {
              e.preventDefault();
              setInnerDrag(e.dataTransfer.types.includes(WH_DRAG));
              setDragOver(true);
            }}
            onDragLeave={(e) => { if (e.currentTarget === e.target) { setDragOver(false); } }}
            onDrop={(e) => dropInto(e, path)}
          >
            {dragOver && !dropTarget && (
              <div className="absolute inset-3 z-10 border-2 border-dashed border-[#D97706] rounded-2xl flex items-center justify-center pointer-events-none bg-amber-50/80">
                <div className="text-[#B45309] font-medium">
                  {innerDrag
                    ? (path ? `'${crumbs[crumbs.length - 1].label}' 폴더로 옮기기` : '창고 맨 위로 옮기기')
                    : (path ? `'${crumbs[crumbs.length - 1].label}' 폴더에 넣기` : `레벨 ${level} 창고에 넣기`)}
                </div>
              </div>
            )}
            {!data ? (
              <div className="h-full flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-stone-200 border-t-stone-600 rounded-full animate-spin" />
              </div>
            ) : entries.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-2">
                <Package className="w-10 h-10" />
                <p className="text-sm">비어 있어요 — 파일을 끌어다 놓거나, 우클릭으로 새 폴더를 만드세요</p>
              </div>
            ) : view === 'grid' ? (
              <ul className="px-4 py-3 grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-1 content-start">
                {entries.map((en, i) => gridCell(en, i))}
              </ul>
            ) : (
              <div className="px-4 py-2">
                <div className="grid grid-cols-[minmax(0,1fr)_90px_150px] gap-2 px-3 pb-1 border-b border-stone-200">
                  {sortHeader('name', '이름')}
                  {sortHeader('bytes', '크기', 'text-right')}
                  {sortHeader('mtime', '수정일')}
                </div>
                <ul className="pt-1 space-y-0.5">
                  {entries.map((en, i) => listRow(en, i))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 컨텍스트 메뉴 */}
      {ctx && (
        <div
          className="fixed bg-white rounded-lg shadow-xl border border-stone-200 py-1 z-50 min-w-[170px]"
          style={{
            left: Math.min(ctx.x, window.innerWidth - 190),
            top: Math.min(ctx.y, window.innerHeight - 200),
          }}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => e.preventDefault()}
        >
          {ctx.kind === 'entry' && ctx.entry && sel.length <= 1 && (<>
            {menuItem('열기', () => openEntry(ctx.entry!),
              false, ctx.entry.kind === 'dir' ? Folder : ExternalLink)}
            {ctx.entry.kind === 'file' && menuItem('내려받기', () => downloadFile(ctx.entry!.path), false, Download)}
            {menuItem('이름 바꾸기', () => setRenaming({
              path: ctx.entry!.path, draft: ctx.entry!.label,
            }))}
            <div className="my-1 border-t border-stone-100" />
            {menuItem('빼기 (휴지통으로)', () => removeItems([ctx.entry!.path]), true, Trash2)}
          </>)}
          {ctx.kind === 'entry' && sel.length > 1 && (<>
            <div className="px-3 py-1 text-[11px] text-stone-400">{sel.length}개 선택됨</div>
            {menuItem(`빼기 (휴지통으로)`, () => removeItems(sel), true, Trash2)}
          </>)}
          {ctx.kind === 'empty' && (<>
            {menuItem('새 폴더', mkdir, false, FolderPlus)}
            {hasElectron && menuItem('파일·폴더 넣기…', pickFiles, false, FilePlus)}
            {menuItem('새로고침', () => retry(), false, RefreshCw)}
          </>)}
          {ctx.kind === 'trash' && ctx.trash && (<>
            {menuItem(`복구 (레벨 ${ctx.trash.level}로)`, () => restoreItem(ctx.trash!), false, RotateCcw)}
            <div className="my-1 border-t border-stone-100" />
            {menuItem('영구 삭제', () => trashDelete(ctx.trash!), true, Trash2)}
          </>)}
          {ctx.kind === 'trash-empty' && (<>
            {trash.length > 0 && menuItem('휴지통 비우기', () => trashDelete(null), true, Trash2)}
            {menuItem('새로고침', () => retry(), false, RefreshCw)}
          </>)}
        </div>
      )}
    </div>
  );
}
