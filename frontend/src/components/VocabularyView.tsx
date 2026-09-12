/** 내 어휘: 제목 없이 아이콘으로 만지는 몸별 단어묶음 데스크톱. */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { ArrowLeft, Boxes, Folder, Archive, Trash2, LockKeyhole, X } from 'lucide-react';
import { api } from '../lib/api';
import { getBackendOrigin } from '../lib/backend-origin';
import type { VocabularyPackage } from '../lib/api-packages';
import { useFolderWindowMotion } from './vocabulary/useFolderWindowMotion';
import { VocabularyIcon } from './vocabulary/VocabularyIcon';
import { VocabularyOverlay } from './vocabulary/VocabularyOverlay';
import { ROOT, STORE, CORE, TRASH, SPECIAL } from './vocabulary/types';
import type { VocabularyDesktop, DesktopEdit, Word } from './vocabulary/types';
import { PackageDeveloperDialog } from './launcher-components/dialogs/PackageDeveloperDialog';
import { ToolSearchDialog } from './launcher-components/dialogs/ToolSearchDialog';
import './vocabulary/desktop.css';

interface Menu { x: number; y: number; item?: string; parent: string; canvasX: number; canvasY: number }
interface Detail { pkg: VocabularyPackage; kind: 'description' | 'words'; words?: Word[] }

export function VocabularyView() {
  const [packages, setPackages] = useState<VocabularyPackage[]>([]);
  const [desktop, setDesktop] = useState<VocabularyDesktop | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [openFolder, setOpenFolder] = useState<string | null>(null);
  const folderMotion = useFolderWindowMotion(openFolder);
  const [selected, setSelected] = useState<string | null>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const detailRequest = useRef(0);
  const [folderForm, setFolderForm] = useState<{ item?: string; parent: string; name: string; x: number; y: number } | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [search, setSearch] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  const reload = useCallback(async () => {
    const [inventory, layout] = await Promise.all([api.getVocabulary(), api.getVocabularyDesktop()]);
    if (mounted.current) { setPackages(inventory.packages); setDesktop(layout); setError(''); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    void reload().catch(e => setError(e instanceof Error ? e.message : '어휘를 불러오지 못했습니다.'));
    const refresh = () => { if (!busyRef.current) void reload().catch(() => {}); };
    window.addEventListener('vocabulary-changed', refresh);
    window.addEventListener('focus', refresh);
    return () => { mounted.current = false; window.removeEventListener('vocabulary-changed', refresh); window.removeEventListener('focus', refresh); };
  }, [reload]);
  useEffect(() => {
    if (!menu) return;
    menuRef.current?.querySelector<HTMLButtonElement>('button:not([disabled])')?.focus();
    const close = (e: Event) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(null); };
    window.addEventListener('pointerdown', close);
    return () => window.removeEventListener('pointerdown', close);
  }, [menu]);
  const run = async (work: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(''); setMessage(''); setMenu(null);
    try { await work(); }
    catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했습니다.'); }
    finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  };
  const edit = (change: DesktopEdit) => run(async () => {
    setDesktop(await api.editVocabularyDesktop(change));
    if (change.op === 'move' || change.op === 'restore') {
      setPackages((await api.getVocabulary()).packages);
      window.dispatchEvent(new Event('vocabulary-changed'));
    }
    if (change.op === 'remove_folder' && openFolder === change.item) setOpenFolder(null);
  });
  const slot = (parent: string): { x: number; y: number } => {
    const used = [...Object.values(desktop?.folders || {}), ...Object.values(desktop?.placements || {})].filter(p => p.parent === parent);
    const columns = Math.max(1, Math.floor((parent === ROOT ? surface.current?.clientWidth || 600 : 460) / 116));
    let i = 0;
    while (used.some(p => Math.abs(p.x - (24 + i % columns * 116)) < 100 && Math.abs(p.y - (24 + Math.floor(i / columns) * 116)) < 100)) i++;
    return { x: 24 + i % columns * 116, y: 24 + Math.floor(i / columns) * 116 };
  };
  const move = (item: string, parent: string, x = -1, y = -1) => {
    const pos = x < 0 || y < 0 ? slot(parent) : { x, y };
    void edit({ op: 'move', item, parent, ...pos });
  };
  const receive = (file?: File) => {
    if (!file) return;
    void run(async () => {
      if (file.size > 20 * 1024 * 1024) throw new Error('어휘 파일은 최대 20MB입니다.');
      const result = await api.importVocabulary(file);
      if (!result.success) throw new Error(result.message || '가져오기 실패');
      await reload(); setOpenFolder(STORE);
      setMessage(result.status === 'already_owned' ? '이미 보유한 묶음입니다.' : '저장고에 넣었습니다. 밖으로 꺼내면 사용할 수 있습니다.');
      window.dispatchEvent(new Event('vocabulary-changed'));
    });
  };
  const download = (pkg: VocabularyPackage) => void run(async () => {
    const response = await fetch(`${await getBackendOrigin()}/vocabulary/${encodeURIComponent(pkg.id)}/export`);
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || '파일을 만들지 못했습니다.'); }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = url; link.download = `${pkg.id}.iblpack`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const describe = (pkg: VocabularyPackage, kind: Detail['kind']) => {
    setMenu(null); setDetail({ pkg, kind });
    const request = ++detailRequest.current;
    if (kind === 'words') void api.getVocabularyWords(pkg.id).then(result => {
      if (request === detailRequest.current) setDetail({ pkg, kind, words: result.words });
    }).catch(e => { if (request === detailRequest.current) { setDetail(null); setError(String(e)); } });
  };
  const context = (e: MouseEvent, parent: string, item?: string) => {
    e.preventDefault(); e.stopPropagation();
    const canvas = (e.currentTarget as HTMLElement | undefined)?.closest<HTMLElement>('[data-vocab-canvas]');
    const rect = canvas?.getBoundingClientRect();
    setSelected(item || null);
    setMenu({ x: Math.min(e.clientX, window.innerWidth - 235), y: Math.max(8, Math.min(e.clientY, window.innerHeight - 370)),
      item, parent, canvasX: Math.max(0, e.clientX - (rect?.left || 0)), canvasY: Math.max(0, e.clientY - (rect?.top || 0)) });
  };
  const arrange = (parent: string) => {
    const width = parent === ROOT ? surface.current?.clientWidth || 600 : Math.min(660, window.innerWidth - 180);
    void edit({ op: 'arrange', parent, columns: Math.max(1, Math.floor((width - 24) / 116)) });
  };
  const canvas = (parent: string) => {
    const entries = desktop ? [
      ...Object.entries(desktop.folders).filter(([, p]) => p.parent === parent).map(([id, p]) => ({ id, name: p.name, placement: p, folder: true, required: id === CORE })),
      ...packages.filter(p => desktop.placements[p.id]?.parent === parent).map(p => ({ id: p.id, name: p.name, placement: desktop.placements[p.id], folder: false, required: p.required })),
    ] : [];
    const width = Math.max(1, ...entries.map(e => e.placement.x + 120));
    const height = Math.max(parent === ROOT ? 400 : 260, ...entries.map(e => e.placement.y + 124));
    return <div data-vocab-canvas data-vocab-destination={parent} aria-label={parent === ROOT ? '내 어휘 바탕' : `${desktop?.folders[parent]?.name} 내용`}
      className="relative min-w-full min-h-full" style={{ width, height }} onContextMenu={e => context(e, parent)}>
      {entries.map(entry => <VocabularyIcon key={entry.id} id={entry.id} name={entry.name} placement={entry.placement}
        icon={entry.id === STORE ? <Archive size={38} /> : entry.id === TRASH ? <Trash2 size={29} /> : entry.id === CORE ? <LockKeyhole size={27} /> : entry.folder ? <Folder size={29} /> : <Boxes size={27} />}
        destination={entry.folder ? entry.id : undefined} fixed={SPECIAL.has(entry.id) && entry.id !== TRASH} large={entry.id === STORE}
        protectedIcon={entry.required} selected={selected === entry.id} disabled={busy}
        onSelect={() => setSelected(entry.id)} onMenu={e => context(e, parent, entry.id)}
        onOpen={() => entry.folder ? setOpenFolder(entry.id) : describe(packages.find(p => p.id === entry.id)!, 'description')}
        onMove={(target, x, y) => move(entry.id, target, x, y)} />)}
    </div>;
  };
  const pkg = menu?.item ? packages.find(p => p.id === menu.item) : undefined;
  const folder = menu?.item ? desktop?.folders[menu.item] : undefined;
  const menuButton = (label: string, onClick: () => void, disabled = false) => <button role="menuitem" disabled={busy || disabled}
    className="block w-full px-4 py-2 text-left text-sm hover:bg-amber-50 focus:bg-amber-50 outline-none disabled:opacity-40" onClick={onClick}>{label}</button>;
  const openName = openFolder && desktop?.folders[openFolder]?.name;
  return <div ref={surface} className="vocabulary-desktop relative h-full bg-[#F5F1EB] text-stone-700" aria-label="내 어휘" aria-busy={busy}
    onKeyDown={e => { if (e.key === 'Escape') { setMenu(null); setSelected(null); } }}>
    <div className="h-full overflow-auto">{canvas(ROOT)}</div>
    <input ref={fileInput} type="file" accept=".iblpack,.txt" className="hidden" onChange={e => { receive(e.target.files?.[0]); e.target.value = ''; }} />
    {!desktop && !error && <div role="status" className="absolute bottom-4 left-4 text-sm">불러오는 중…</div>}
    {(error || message || busy) && <div role={error ? 'alert' : 'status'} className={`absolute bottom-4 left-4 right-4 z-[90] flex items-center gap-3 rounded-lg p-3 text-sm shadow max-w-xl ${error ? 'bg-red-50 text-red-800' : 'bg-white text-stone-700'}`}>
      <span className="flex-1 break-words">{error || (busy ? '처리 중…' : message)}</span>
      {error && !desktop && <button onClick={() => void run(reload)}>다시 시도</button>}
      {!busy && <button aria-label="알림 닫기" onClick={() => { setError(''); setMessage(''); }}><X size={16} /></button>}
    </div>}
    {openFolder && openName && <div ref={folderMotion.windowRef} style={folderMotion.style} className="vocabulary-folder absolute z-30 flex flex-col rounded-2xl border border-stone-300 bg-[#faf8f4] shadow-xl overflow-hidden" role="region" aria-label={openName}>
      <div {...folderMotion.headerEvents} tabIndex={0} aria-label={`${openName} 창 이동`} style={{ touchAction: 'none', cursor: folderMotion.dragging ? 'grabbing' : 'grab' }} className="no-drag select-none flex items-center gap-2 px-3 py-2 border-b border-stone-200 shrink-0" onContextMenu={e => context(e, openFolder, openFolder)}>
        <button aria-label="상위 폴더" title="상위 폴더" data-vocab-destination={desktop!.folders[openFolder].parent}
          onClick={() => setOpenFolder(desktop!.folders[openFolder].parent === ROOT ? null : desktop!.folders[openFolder].parent)} className="p-2 hover:bg-stone-200 rounded"><ArrowLeft size={17} /></button>
        <span className="font-medium text-sm flex-1">{openName}</span>
        <button aria-label="폴더 닫기" onClick={() => setOpenFolder(null)} className="p-2 hover:bg-stone-200 rounded"><X size={17} /></button>
      </div>
      <div className="overflow-auto flex-1 min-h-0">{canvas(openFolder)}</div>
    </div>}
    {menu && <div ref={menuRef} role="menu" aria-label="어휘 메뉴" className="fixed z-[210] w-56 py-1 rounded-xl border border-stone-200 bg-white shadow-xl max-h-[85vh] overflow-y-auto" style={{ left: Math.max(8, menu.x), top: menu.y }}
      onContextMenu={e => { e.preventDefault(); e.stopPropagation(); }} onKeyDown={e => {
        const buttons = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])') || []);
        const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); buttons[(i + (e.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length]?.focus(); }
        if (e.key === 'Escape' || e.key === 'Tab') setMenu(null);
      }}>
      {pkg && <>
        {menuButton('기본설명', () => describe(pkg, 'description'))}
        {menuButton('단어소개', () => describe(pkg, 'words'))}
        {menuButton('내보내기', () => download(pkg), !!pkg.required)}
        {!pkg.required && (menu.parent === TRASH ? menuButton('복원', () => void edit({ op: 'restore', item: pkg.id })) : <>
          {menu.parent !== ROOT && menu.parent !== STORE && menuButton('바탕으로 꺼내기', () => move(pkg.id, ROOT))}
          {menuButton(menu.parent === STORE ? '바탕으로 꺼내기' : '저장고에 넣기', () => move(pkg.id, menu.parent === STORE ? ROOT : STORE))}
          {menuButton('쓰레기통으로 보내기', () => move(pkg.id, TRASH))}
        </>)}
      </>}
      {folder && <>
        {menuButton('열기', () => { setOpenFolder(menu.item!); setMenu(null); })}
        {menu.item === STORE && <>
          {menuButton('파일 가져오기', () => { setMenu(null); fileInput.current?.click(); })}
          {menuButton('공유 어휘 찾기', () => { setMenu(null); setSearch(true); })}
          {menuButton('제작 및 라이브러리 관리', () => { setMenu(null); setAdvanced(true); })}
        </>}
        {!SPECIAL.has(menu.item!) && <>
          {menuButton('이름 바꾸기', () => { setFolderForm({ item: menu.item, parent: menu.parent, name: folder.name, x: folder.x, y: folder.y }); setMenu(null); })}
          {menuButton('폴더 없애기 · 내용은 꺼내기', () => void edit({ op: 'remove_folder', item: menu.item }))}
        </>}
      </>}
      {!menu.item && !SPECIAL.has(menu.parent) && menuButton('새 폴더', () => {
        setFolderForm({ parent: menu.parent, name: '새 폴더', x: menu.canvasX, y: menu.canvasY }); setMenu(null);
      })}
      {!menu.item && menu.parent === STORE && menuButton('파일 가져오기', () => { setMenu(null); fileInput.current?.click(); })}
      {menuButton('아이콘 정렬', () => arrange(menu.parent))}
    </div>}
    {folderForm && <VocabularyOverlay title={folderForm.item ? '폴더 이름 바꾸기' : '새 폴더'} onClose={() => setFolderForm(null)}>
      <form onSubmit={e => { e.preventDefault(); void edit({ ...folderForm, op: folderForm.item ? 'rename' : 'create_folder' }); setFolderForm(null); }} className="flex gap-2">
        <input aria-label="폴더 이름" autoFocus maxLength={80} required value={folderForm.name} onChange={e => setFolderForm({ ...folderForm, name: e.target.value })} className="min-w-0 flex-1 rounded border border-stone-300 px-3 py-2" />
        <button type="submit" disabled={busy || !folderForm.name.trim()} className="rounded bg-amber-100 px-4 py-2">저장</button>
      </form>
    </VocabularyOverlay>}
    {detail && <VocabularyOverlay title={`${detail.pkg.name} · ${detail.kind === 'words' ? '단어소개' : '기본설명'}`} onClose={() => { detailRequest.current++; setDetail(null); }}>
      {detail.kind === 'description' ? <div className="space-y-4 text-sm">
        <p className="whitespace-pre-wrap break-words">{detail.pkg.description}</p>
        <p>{detail.pkg.required ? '필수 단어묶음 · 항상 사용' : detail.pkg.installed ? '사용 중' : '잠든 상태'}{detail.pkg.version ? ` · ${detail.pkg.version}` : ''}</p>
        {!!detail.pkg.preparation?.length && <p className="text-amber-800">{detail.pkg.preparation.join(' · ')}</p>}
        <button className="rounded border border-stone-300 px-3 py-2" onClick={() => describe(detail.pkg, 'words')}>단어소개</button>
      </div> : detail.words ? <div className="space-y-4">
        {!detail.words.length && <p className="text-sm">직접 등록된 IBL 단어가 없는 지원 묶음입니다.</p>}
        {detail.words.map(word => <article key={word.name} className="rounded-xl border border-stone-200 bg-white p-4 space-y-2">
          <h3 className="font-mono text-sm font-semibold">{word.name}</h3><p className="text-sm whitespace-pre-wrap break-words">{word.description}</p>
          {word.example && <pre className="whitespace-pre-wrap break-all text-xs bg-stone-50 rounded p-2">{word.example}</pre>}
        </article>)}
      </div> : <p role="status">단어를 불러오는 중…</p>}
    </VocabularyOverlay>}
    <PackageDeveloperDialog show={advanced} onClose={() => { setAdvanced(false); void reload().catch(e => setError(String(e))); }} />
    <ToolSearchDialog show={search} onClose={() => { setSearch(false); void reload().catch(e => setError(String(e))); }} />
  </div>;
}
