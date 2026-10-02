import { useCallback, useEffect, useRef, useState } from 'react';
import { documentRequest, documentCommand, sessionArgs, type Detail, type Document, type Session, type Snapshot, type Proposal } from '../lib/api-documents';
import { useRetryingLoad } from '../lib/use-retrying-load';
import './document-workspace.css';

type Selection = { snapshot: Snapshot; start: number; end: number; text: string; hash: string };
type Pending = { args: Record<string, unknown>; text: string };
const clientKey = 'document-window-id';
function clientId() {
  let value = sessionStorage.getItem(clientKey);
  if (!value) { value = crypto.randomUUID(); sessionStorage.setItem(clientKey, value); }
  return value;
}
async function hash(text: string) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), v => v.toString(16).padStart(2, '0')).join('');
}

export function DocumentWorkspace() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [path, setPath] = useState('');
  const [encoding, setEncoding] = useState('');
  const [filename, setFilename] = useState('');
  const [text, setText] = useState('');
  const [message, setMessage] = useState('문서를 열어 작업을 시작하세요');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [replacement, setReplacement] = useState('');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [preview, setPreview] = useState(false);
  const [undo, setUndo] = useState<{ before: string; after: string } | null>(null);
  const current = useRef<Detail | null>(null);
  const draftText = useRef('');
  const acknowledged = useRef('');
  const pending = useRef<Pending | null>(null);
  const saving = useRef<Promise<Session | null> | null>(null);
  const composing = useRef(false);
  const working = useRef(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const client = useRef(clientId());
  const newline = useRef('\n');
  const [mixedNewlines, setMixedNewlines] = useState(false);

  const load = useCallback(async () => {
    const value = await documentRequest<{ items: Document[] }>('');
    setDocuments(value.items);
  }, []);
  const { retrying } = useRetryingLoad(load, { onFocus: true });

  const cacheKey = (id: string) => `document-draft:${id}:${client.current}`;
  const updateText = (value: string) => {
    draftText.current = value; setText(value);
    const id = current.current?.document.id;
    if (id) {
      try { localStorage.setItem(cacheKey(id), value); }
      catch { setError('이 브라우저에 복구 초안을 저장하지 못했습니다. 창을 닫지 말고 작업 저장을 실행하세요.'); }
    }
    setMessage('수정됨 · 원본에는 저장되지 않음');
  };

  const flush = async (): Promise<Session | null> => {
    if (composing.current) throw new Error('한글 입력 조합이 끝난 뒤 실행하세요');
    if (saving.current) { await saving.current; return flush(); }
    const d = current.current;
    if (!d?.session || d.session.client_id !== client.current) return null;
    if (!pending.current && acknowledged.current === draftText.current) return d.session;
    const request = pending.current || {
      args: { ...sessionArgs(d.session), operation_id: crypto.randomUUID(), text: draftText.current },
      text: draftText.current,
    };
    pending.current = request;
    const task = (async () => {
      const result = await documentCommand<{ session: Session }>(d.document.id, 'draft', request.args);
      acknowledged.current = request.text; pending.current = null;
      const next = { ...d, session: result.session };
      current.current = next; setDetail(next);
      if (draftText.current === request.text) setMessage('작업 저장됨 · 원본에는 저장되지 않음');
      return result.session;
    })();
    saving.current = task;
    try { await task; } finally { saving.current = null; }
    return flush();
  };

  const act = async (fn: () => Promise<unknown>) => {
    if (working.current) return;
    working.current = true; setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(String(e)); }
    finally { working.current = false; setBusy(false); }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      if (!working.current && !composing.current && current.current?.session?.client_id === client.current)
        void flush().catch(e => setError(String(e)));
    }, 900);
    return () => clearTimeout(timer);
  }, [text, detail?.document.id]); // Text changes schedule autosave, never an AI call.

  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (pending.current || draftText.current !== acknowledged.current || composing.current) {
        event.preventDefault(); event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, []);

  const display = async (d: Detail) => {
    if (d.capabilities.edit_native) {
      try { d = await documentCommand<Detail>(d.document.id, 'sessions', { client_id: client.current }); }
      catch (e) { setError(String(e)); }
    }
    current.current = d; setDetail(d); pending.current = null;
    acknowledged.current = d.text || '';
    const value = localStorage.getItem(cacheKey(d.document.id)) ?? acknowledged.current;
    const crlf = (value.match(/\r\n/g) || []).length;
    const lf = (value.replace(/\r\n/g, '').match(/\n/g) || []).length;
    const cr = value.replace(/\r\n/g, '').includes('\r');
    newline.current = crlf && !lf ? '\r\n' : '\n';
    setMixedNewlines(cr || !!(crlf && lf));
    draftText.current = value; setText(value); setSelection(null); setProposal(null); setUndo(null);
    const dot = d.document.title.lastIndexOf('.');
    setFilename(`${d.document.title.slice(0, dot)}_edited${d.document.title.slice(dot)}`);
    setMessage(value !== acknowledged.current ? '브라우저 복구 초안 · 작업 저장 필요' : d.session?.state === 'draft' ? '복구된 작업 초안 · 원본에는 저장되지 않음' : '원본을 읽었습니다');
  };

  const choose = (id: string) => act(async () => {
    await flush(); await display(await documentRequest<Detail>(`/${id}`));
  });
  const open = () => act(async () => {
    await flush();
    const d = await documentRequest<Detail>('/open', 'POST', { path, encoding: encoding || null });
    await display(d); await load();
  });
  const exportCopy = () => act(async () => {
    const session = await flush(); const d = current.current;
    if (!session || !d) return;
    const result = await documentCommand<{ path: string }>(d.document.id, 'export', {
      ...sessionArgs(session), operation_id: crypto.randomUUID(), filename,
    });
    setMessage(`사본 저장됨: ${result.path} · 원본은 별도로 유지됩니다`);
  });
  const select = () => act(async () => {
    if (!editor.current || !current.current) return;
    const a = editor.current.selectionStart, b = editor.current.selectionEnd;
    const view = editor.current.value;
    if (a === b) throw new Error('교체할 문구를 먼저 선택하세요');
    const start = Array.from(view.slice(0, a).replace(/\n/g, newline.current)).length;
    const chosen = view.slice(a, b).replace(/\n/g, newline.current);
    const session = await flush(); if (!session) return;
    const snapshot = await documentCommand<Snapshot>(current.current.document.id, 'snapshots', sessionArgs(session));
    setSelection({ snapshot, start, end: start + Array.from(chosen).length, text: chosen, hash: await hash(chosen) });
    setReplacement(chosen); setProposal(null);
  });
  const propose = () => act(async () => {
    if (!selection || !current.current) return;
    await flush();
    setProposal(await documentCommand<Proposal>(current.current.document.id, 'proposals', {
      snapshot_id: selection.snapshot.id, start: selection.start, end: selection.end,
      selected_sha256: selection.hash, replacement,
    }));
  });
  const apply = () => act(async () => {
    if (!proposal || !current.current) return;
    const session = await flush(); if (!session) return;
    const before = draftText.current;
    const result = await documentCommand<{ session: Session; text: string }>(current.current.document.id, 'apply', {
      ...sessionArgs(session), operation_id: crypto.randomUUID(), proposal_id: proposal.id,
    });
    const next = { ...current.current, session: result.session };
    current.current = next; setDetail(next); acknowledged.current = result.text;
    updateText(result.text); setUndo({ before, after: result.text }); setProposal(null); setSelection(null);
  });
  const editable = !!detail?.capabilities.edit_native && detail.session?.client_id === client.current && !mixedNewlines;
  const previewHtml = `<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'"><style>body{font:16px/1.7 sans-serif;padding:24px;overflow-wrap:anywhere}</style>${text}`;

  return <main className="document-workspace">
    <header><div><span className="document-eyebrow">INDIEBIZ OS</span><h1>문서</h1></div><span className="document-badge">개발 중 · 소스 문서 작업</span></header>
    <p className="document-limit">TXT·Markdown·HTML·LaTeX·Typst 원문을 편집하고 같은 형식의 사본을 저장합니다. 사무 문서·한글·PDF 편집, AI 생성과 원본 덮어쓰기는 아직 사용할 수 없습니다.</p>
    <form className="document-open" onSubmit={e => { e.preventDefault(); open(); }}>
      <label>로컬 파일 경로<input value={path} onChange={e => setPath(e.target.value)} placeholder="/Users/…/문서.txt" /></label>
      <label>인코딩<select aria-label="인코딩" value={encoding} onChange={e => setEncoding(e.target.value)}><option value="">UTF/BOM 자동 확인</option>{['utf-8', 'utf-8-sig', 'utf-16', 'cp949', 'euc-kr'].map(e => <option key={e}>{e}</option>)}</select></label>
      <button disabled={busy || !path}>파일 열기</button>
    </form>
    {error && <div role="alert" className="document-error">{error}<button onClick={() => void act(async () => { await flush(); })}>작업 저장 재시도</button></div>}
    <div className="document-body">
      <nav aria-label="등록 문서"><h2>최근 문서</h2>{retrying && <p>연결 중…</p>}{documents.map(d => <button key={d.id} className={detail?.document.id === d.id ? 'selected' : ''} onClick={() => void choose(d.id)} disabled={busy}><strong>{d.title}</strong><small>{d.source_format.toUpperCase()}</small></button>)}</nav>
      <section className="document-editor" aria-label="문서 편집">
        {detail ? <>
          <div className="document-title"><h2>{detail.document.title}</h2><small>{detail.document.encoding || detail.document.source_format} · {detail.document.source_uri}</small></div>
          {!detail.capabilities.edit_native && <p role="status">{detail.capabilities.reason}</p>}
          {detail.session && detail.session.client_id !== client.current && <div className="document-toolbar"><p>다른 작성 창의 세션입니다. 복구하면 이전 창의 저장 권한이 종료됩니다.</p><button disabled={busy} onClick={() => void act(async () => {
            if (!detail.session) return;
            const recovered = await documentCommand<Detail>(detail.document.id, 'reclaim', { client_id: client.current, expected_epoch: detail.session.engine_epoch });
            await display(recovered);
          })}>이 창에서 초안 복구</button></div>}
          {mixedNewlines && <p role="alert">혼합 줄바꿈 문서입니다. 원문을 보호하기 위해 이 화면의 편집을 제한합니다.</p>}
          <div className="document-toolbar"><button disabled={!editable || busy} onClick={() => void act(async () => { await flush(); })}>작업 저장</button><button disabled={!editable || busy} onClick={select}>선택 고정</button><button disabled={!undo || text !== undo.after || busy} onClick={() => { if (undo) { updateText(undo.before); setUndo(null); } }}>선택 교체 되돌리기</button>{['html', 'htm'].includes(detail.document.source_format) && <button onClick={() => setPreview(!preview)}>{preview ? '원문 보기' : '비실행 미리보기'}</button>}</div>
          {preview ? <iframe title="HTML 비실행 미리보기" sandbox="" srcDoc={previewHtml} /> : <textarea ref={editor} aria-label="문서 원문" spellCheck={false} value={text} readOnly={!editable || busy}
            onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
            onChange={e => updateText(e.target.value.replace(/\r\n/g, '\n').replace(/\n/g, newline.current))}
            onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); exportCopy(); } }} />}
          <div className="document-export"><label>사본 파일명<input value={filename} onChange={e => setFilename(e.target.value)} /></label><button disabled={!editable || busy || !filename} onClick={exportCopy}>사본 저장</button></div>
        </> : <div className="document-empty"><h2>원문과 초안을 함께 보존합니다</h2><p>파일을 열거나 왼쪽 목록에서 작업을 이어가세요.</p></div>}
      </section>
      <aside><h2>선택 교체</h2><p>고정한 선택과 작업 버전을 기준으로 교체합니다. 선택 이후 문서가 바뀌면 적용을 거절합니다.</p>{selection ? <><blockquote>{selection.text}</blockquote><label>교체할 문구<textarea value={replacement} onChange={e => { setReplacement(e.target.value); setProposal(null); }} /></label><button disabled={busy} onClick={propose}>제안 만들기</button><button disabled={busy || !proposal} onClick={apply}>제안 적용</button><button onClick={() => { setSelection(null); setProposal(null); }}>제안 버리기</button></> : <p>문구를 선택하고 ‘선택 고정’을 누르세요.</p>}</aside>
    </div><footer role="status" aria-live="polite">{busy ? '처리 중…' : message}<span>{Array.from(text).length.toLocaleString()}자</span></footer>
  </main>;
}
