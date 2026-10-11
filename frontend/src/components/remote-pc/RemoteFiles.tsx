import { useEffect, useRef, useState } from 'react';
import { bytesFrom64, bytesTo64, message, post, run } from './client';

type Entry = { name: string; path: string; dir: boolean; bytes: number };
type Transfer = { id: string; size: number; sha256: string; offset: number };
const maxFile = 128 * 1024 * 1024;
async function digest(data: ArrayBuffer) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(b => b.toString(16).padStart(2, '0')).join('');
}
export function RemoteFiles({ device }: { device: string }) {
  const [path, setPath] = useState(''), [draft, setDraft] = useState('');
  const [files, setFiles] = useState<Entry[]>([]), [busy, setBusy] = useState(''), [error, setError] = useState('');
  const [preview, setPreview] = useState<{ path: string; content: string } | null>(null);
  const controller = useRef(new AbortController());
  const home = useRef('');
  const upload = useRef<HTMLInputElement>(null);
  const list = async (next: string, signal: AbortSignal) => {
    const result = await run(device, { op: 'list', path: next }, signal);
    if (signal.aborted) return;
    setPath(String(result.path)); setDraft(String(result.path)); setFiles(result.files as Entry[]); setPreview(null);
  };
  const act = async (label: string, fn: (signal: AbortSignal) => Promise<void>) => {
    setBusy(label); setError('');
    const signal = controller.current.signal;
    try { await fn(signal); } catch (e) { if (!signal.aborted) setError(message(e)); }
    finally { if (!signal.aborted) setBusy(''); }
  };
  useEffect(() => {
    const control = new AbortController(); controller.current = control;
    void act('폴더 조회 중…', async signal => {
      const info = await run(device, { op: 'info' }, signal);
      home.current = String(info.home || info.cwd);
      await list(home.current, signal);
    });
    return () => control.abort();
    // A new device mounts a fresh workbench.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [device]);
  const parent = () => {
    const separator = path.includes('\\') ? '\\' : '/';
    const clean = path.replace(/[\\/]+$/, '');
    const index = clean.lastIndexOf(separator);
    return index <= 0 ? separator : clean.slice(0, index) + separator;
  };
  const download = (entry: Entry) => void act('파일 가져오는 중…', async signal => {
    if (entry.bytes > maxFile) throw new Error('작업창 파일 전송은 파일당 128 MiB까지 지원합니다.');
    const transfer = await post<Transfer>('/remote-pcs/transfers', { target: device, direction: 'from_pc', name: entry.name });
    await run(device, { op: 'transfer', transfer_id: transfer.id, path: entry.path, timeout: 300 }, signal);
    const meta = await post<Transfer>(`/remote-pcs/transfers/${transfer.id}`, { action: 'info' });
    if (meta.size > maxFile) throw new Error('파일이 128 MiB를 초과합니다.');
    const output = new Uint8Array(meta.size);
    let offset = 0;
    while (offset < meta.size && !signal.aborted) {
      const chunk = await post<{ data: string; offset: number }>(`/remote-pcs/transfers/${transfer.id}`, { action: 'read', offset });
      if (chunk.offset <= offset) throw new Error('파일 전송이 중단되었습니다.');
      output.set(bytesFrom64(chunk.data), offset); offset = chunk.offset;
    }
    if (signal.aborted) return;
    if (await digest(output.buffer) !== meta.sha256) throw new Error('파일 검증에 실패했습니다.');
    const url = URL.createObjectURL(new Blob([output]));
    const a = document.createElement('a'); a.href = url; a.download = entry.name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  });
  const sendFile = (file: File) => void act('파일 보내는 중…', async signal => {
    if (file.size > maxFile) throw new Error('작업창 파일 전송은 파일당 128 MiB까지 지원합니다.');
    const data = await file.arrayBuffer();
    const sha256 = await digest(data);
    const transfer = await post<Transfer>('/remote-pcs/transfers', { target: device, direction: 'to_pc', name: file.name, size: file.size, sha256 });
    for (let offset = 0; offset < data.byteLength; offset += 128 * 1024) {
      if (signal.aborted) return;
      await post(`/remote-pcs/transfers/${transfer.id}`, { action: 'write', offset, data: bytesTo64(new Uint8Array(data.slice(offset, offset + 128 * 1024))) });
    }
    await post(`/remote-pcs/transfers/${transfer.id}`, { action: 'commit' });
    const separator = path.includes('\\') ? '\\' : '/';
    const target = path.replace(/[\\/]+$/, '') + separator + file.name;
    await run(device, { op: 'transfer', transfer_id: transfer.id, path: target, timeout: 300 }, signal);
    await list(path, signal);
  });
  return <div className="flex h-full min-h-0 flex-col p-4 text-sm">
    <form className="mb-3 flex gap-2" onSubmit={e => { e.preventDefault(); void act('폴더 조회 중…', s => list(draft, s)); }}>
      <button type="button" disabled={!!busy} onClick={() => void act('폴더 조회 중…', s => list(home.current, s))} className="rounded border px-3">홈</button>
      <button type="button" disabled={!!busy || !path} onClick={() => void act('폴더 조회 중…', s => list(parent(), s))} className="rounded border px-3">상위</button>
      <input aria-label="원격 폴더 경로" value={draft} onChange={e => setDraft(e.target.value)} className="min-w-0 flex-1 rounded border px-3 py-2 font-mono" />
      <button disabled={!!busy} className="rounded border px-3">이동</button>
      <button type="button" disabled={!!busy || !path} onClick={() => upload.current?.click()} className="rounded bg-stone-800 px-3 text-white">파일 보내기</button>
      <input ref={upload} type="file" className="hidden" onChange={e => { const file = e.target.files?.[0]; if (file) sendFile(file); e.target.value = ''; }} />
    </form>
    {busy && <p role="status" className="mb-2 text-stone-500">{busy}</p>}
    {error && <p role="alert" className="mb-2 text-red-700">{error}</p>}
    <div className="min-h-0 flex-1 overflow-auto rounded border">
      {files.map(entry => <div key={entry.path} className="flex items-center gap-3 border-b px-3 py-2">
        <button disabled={!!busy} className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => void act(entry.dir ? '폴더 조회 중…' : '파일 읽는 중…', async signal => {
          if (entry.dir) await list(entry.path, signal);
          else {
            if (entry.bytes > 1024 * 1024) throw new Error('미리보기는 1 MiB 이하 파일만 가능합니다. 파일 가져오기를 사용하세요.');
            const result = await run(device, { op: 'read', path: entry.path }, signal);
            if (!signal.aborted) setPreview({ path: entry.path, content: String(result.content) + (result.truncated ? '\n[일부 내용만 표시됨]' : '') });
          }
        })}>{entry.dir ? '📁' : '📄'} {entry.name}</button>
        {!entry.dir && <><span className="text-xs text-stone-500">{entry.bytes.toLocaleString()} B</span><button disabled={!!busy} className="rounded border px-2 py-1 text-xs" onClick={() => download(entry)}>가져오기</button></>}
      </div>)}
      {!busy && !files.length && <p className="p-4 text-stone-500">폴더가 비어 있습니다.</p>}
    </div>
    {preview && <div className="mt-3 flex h-1/2 min-h-0 flex-col rounded border bg-stone-50"><div className="flex gap-2 border-b px-3 py-2"><span className="min-w-0 flex-1 truncate">{preview.path}</span><button onClick={() => setPreview(null)}>닫기</button></div><pre className="overflow-auto p-3 text-xs">{preview.content}</pre></div>}
  </div>;
}
