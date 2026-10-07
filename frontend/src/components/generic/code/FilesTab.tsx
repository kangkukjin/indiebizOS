/* 코드 파일 탭 — 왼쪽 트리(AI 가 방금 고친 파일은 ●), 오른쪽 원문(줄 번호·읽기 전용). 편집 → 저장 = 파일 쓰기 + 기록.
 * 이전 기록 보기 = 그 파일만 기록으로 되돌리기. 기본적으로 코드를 읽지 않는 사람의 화면이라 트리·원문 둘뿐이다. */
import { useEffect, useMemo, useState } from 'react';
import type { codeIBL, FileItem, ProjectDetail, Version } from './ibl';

const btn = 'px-2.5 py-1 rounded-md text-xs border border-stone-200 bg-white text-stone-700 hover:border-stone-400 disabled:opacity-40';
type Node = { name: string; path: string; dir: boolean; children: Node[]; file?: FileItem };

function tree(items: FileItem[]): Node[] {
  const root: Node = { name: '', path: '', dir: true, children: [] };
  for (const f of items) {
    const parts = f.path.split('/');
    let cur = root;
    parts.forEach((part, i) => {
      const last = i === parts.length - 1;
      let next = cur.children.find((c) => c.name === part && c.dir === !last);
      if (!next) {
        next = { name: part, path: parts.slice(0, i + 1).join('/'), dir: !last, children: [], file: last ? f : undefined };
        cur.children.push(next);
      }
      cur = next;
    });
  }
  const sort = (n: Node) => { n.children.sort((a, b) => Number(b.dir) - Number(a.dir) || a.name.localeCompare(b.name)); n.children.forEach(sort); };
  sort(root);
  return root.children;
}

export function FilesTab({ ibl, detail, locked, onChanged }: { ibl: ReturnType<typeof codeIBL>; detail: ProjectDetail; locked: boolean; onChanged: () => void }) {
  const [items, setItems] = useState<FileItem[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [picked, setPicked] = useState<string>('');
  const [file, setFile] = useState<{ path: string; text: string; binary: boolean; lines: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Version[] | null>(null);
  const nodes = useMemo(() => tree(items || []), [items]);
  useEffect(() => {
    let dead = false;
    ibl.files().then((f) => { if (!dead) setItems(f); }, (e) => { if (!dead) setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); });
    return () => { dead = true; };
  }, [ibl]);
  const pick = async (path: string) => {
    setPicked(path); setEditing(false); setHistory(null); setMessage('');
    try { const f = await ibl.file(path); setFile({ path, text: f.text, binary: f.binary, lines: f.lines }); setDraft(f.text); }
    catch (e) { setFile(null); setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
  };
  const save = async () => {
    if (!file || busy) return;
    setBusy(true);
    try {
      await ibl.write(file.path, draft, `직접 편집: ${file.path}`);
      await pick(file.path);
      setItems(await ibl.files());
      setMessage('저장·기록됨');
      onChanged();
    } catch (e) { setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { setBusy(false); }
  };
  const showHistory = async () => { setHistory(await ibl.versions()); };
  const restoreFile = async (v: Version) => {
    if (!file || busy) return;
    if (!window.confirm(`${file.path} 를 "${v.label}" 시점으로 되돌릴까요?`)) return;
    setBusy(true);
    try { await ibl.restore(v.id, file.path); await pick(file.path); setItems(await ibl.files()); setMessage('되돌림·기록됨'); onChanged(); }
    catch (e) { setMessage('⚠️ ' + (e instanceof Error ? e.message : String(e))); }
    finally { setBusy(false); }
  };
  const render = (ns: Node[], depth: number) => ns.map((n) => n.dir ? (
    <div key={n.path}>
      <button className="w-full text-left px-2 py-1 text-sm text-stone-700 hover:bg-stone-100 rounded" style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => setOpen((o) => ({ ...o, [n.path]: !(o[n.path] ?? true) }))}>{(open[n.path] ?? true) ? '📂' : '📁'} {n.name}</button>
      {(open[n.path] ?? true) && render(n.children, depth + 1)}
    </div>
  ) : (
    <button key={n.path} onClick={() => void pick(n.path)} title={n.path}
      className={`w-full text-left px-2 py-1 text-xs font-mono rounded truncate ${picked === n.path ? 'bg-teal-50 text-teal-800' : 'text-stone-700 hover:bg-stone-100'}`}
      style={{ paddingLeft: 8 + depth * 14 }}>
      {n.name}{n.file?.changed && <span className="ml-1 text-teal-600" title={n.file.changed === '?' ? '새 파일' : '바뀜'}>●</span>}
    </button>
  ));
  const lines = (file?.text || '').split('\n');
  return (
    <div className="grid grid-cols-[240px_1fr] gap-0 rounded-xl border border-stone-200 bg-white overflow-hidden min-h-[calc(100vh-170px-var(--app-chrome,0px))]">
      <div className="border-r border-stone-200 overflow-auto py-2">
        <div className="px-3 pb-1 text-xs text-stone-500 truncate" title={detail.path}>📁 {detail.name}</div>
        {items === null ? <p className="px-3 text-xs text-stone-400">읽는 중…</p> : items.length === 0 ? <p className="px-3 text-xs text-stone-400">아직 파일이 없습니다.</p> : render(nodes, 0)}
      </div>
      <div className="flex flex-col min-w-0">
        <div className="h-10 flex items-center gap-2 px-4 border-b border-stone-200 text-xs font-mono text-stone-700">
          {file ? <><span className="font-semibold">{file.path}</span><span className="text-stone-400">· {file.lines}줄</span></> : <span className="text-stone-400">왼쪽에서 파일을 고르세요</span>}
          <span className="text-stone-500 font-sans truncate">{message}</span>
          <div className="flex-1" />
          {file && !file.binary && !editing && <button className={btn} disabled={locked} onClick={() => { setEditing(true); setDraft(file.text); }}>편집</button>}
          {file && editing && <><button className={btn} onClick={() => { setEditing(false); setDraft(file.text); }}>취소</button><button className={`${btn} border-teal-600 text-teal-800 bg-teal-50`} disabled={busy || draft === file.text} onClick={() => void save()}>저장</button></>}
          {file && <button className={btn} disabled={busy} onClick={() => void showHistory()}>이전 기록 보기</button>}
        </div>
        {history && (
          <div className="px-4 py-2 border-b border-stone-200 text-xs bg-stone-50">
            <div className="flex items-center gap-2 mb-1"><span className="font-semibold">이 파일을 되돌릴 기록</span><div className="flex-1" /><button className={btn} onClick={() => setHistory(null)}>닫기</button></div>
            {history.length === 0 ? <span className="text-stone-500">기록이 없습니다.</span> : history.map((v) => (
              <div key={v.id} className="flex items-center gap-2 py-0.5"><span className="font-mono text-stone-400">{v.short}</span><span className="flex-1 truncate">{v.label}</span><span className="text-stone-400">{new Date(v.created_at * 1000).toLocaleString()}</span><button className={btn} disabled={busy || locked} onClick={() => void restoreFile(v)}>이 시점으로</button></div>
            ))}
          </div>
        )}
        {file?.binary && <p className="p-4 text-sm text-stone-500">이진 파일은 여기서 보지 않습니다.</p>}
        {file && !file.binary && !editing && (
          <pre className="flex-1 overflow-auto m-0 p-4 text-[12.5px] leading-[1.6] font-mono text-stone-800">
            {lines.map((ln, i) => <span key={i} className="block"><span className="inline-block w-9 mr-4 text-right text-stone-300 select-none">{i + 1}</span>{ln}</span>)}
          </pre>
        )}
        {file && editing && (
          <textarea aria-label="파일 내용" spellCheck={false} value={draft} onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); void save(); } }}
            className="flex-1 m-0 p-4 text-[12.5px] leading-[1.6] font-mono text-stone-800 outline-none resize-none" />
        )}
      </div>
    </div>
  );
}
